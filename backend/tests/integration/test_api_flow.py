"""API 수직 슬라이스 통합 테스트 — 케이스 생성 → Stage1 수집·승인 → Stage2 검토·오버라이드·승인.

VCR 카세트(삼성전자) 재생, 네트워크 없이 통과.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import vcr
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.db.session import get_db
from app.main import app
from app.sources import dart, ecos

CASSETTES = Path(__file__).parent / "cassettes"
FIXTURES = Path(__file__).parents[1] / "fixtures"

myvcr = vcr.VCR(
    cassette_library_dir=str(CASSETTES),
    record_mode="none",
    filter_query_parameters=[("crtfc_key", "DUMMY")],
)


@pytest.fixture
def client(monkeypatch):
    # 인메모리 DB 를 앱 의존성에 주입. StaticPool 로 스레드 간 단일 연결 공유
    # (FastAPI 동기 핸들러는 별도 스레드에서 실행되므로 필수)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    app.dependency_overrides[get_db] = lambda: session

    # 키 DUMMY 고정 + corp_code 캐시를 픽스처로
    fake = SimpleNamespace(dart_api_key="DUMMY", ecos_api_key="DUMMY")
    monkeypatch.setattr(dart, "get_settings", lambda: fake)
    monkeypatch.setattr(ecos, "get_settings", lambda: fake)
    monkeypatch.setattr(dart, "CORP_CODE_CACHE", FIXTURES / "corp_codes.json")

    yield TestClient(app)
    app.dependency_overrides.clear()
    session.close()


def test_full_stage0_to_stage2_approval(client):
    with myvcr.use_cassette("dart_samsung.yaml"):
        # Stage 0: 케이스 생성
        r = client.post("/api/cases", json={
            "company": "005930", "valuation_date": "2023-12-28", "purpose": "impairment",
            "created_by": "analyst1",
        })
        assert r.status_code == 200, r.text
        case = r.json()
        cid = case["case_id"]
        assert "삼성전자" in case["corp_name"]
        assert case["purpose_label"] == "손상검사 (K-IFRS 1036)"

        # Stage 1: 수집
        r = client.post(f"/api/cases/{cid}/stages/1/run")
        assert r.status_code == 200, r.text
        run = r.json()
        assert run["years"] == [2019, 2020, 2021, 2022, 2023]
        by_year = {c["year"]: c for c in run["collected"]}
        assert by_year[2023]["ok"] and by_year[2023]["rows"] > 150

    # Stage 1 승인 (네트워크 불필요)
    r = client.post(f"/api/cases/{cid}/stages/1/approve", json={"approved_by": "analyst1"})
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"

    # Stage 2: 검토 (캐시된 원본 정규화)
    r = client.get(f"/api/cases/{cid}/stages/2/review")
    assert r.status_code == 200, r.text
    rev = r.json()
    a2023 = rev["accounts"]["2023"]
    assert 250_000_000 < a2023["revenue"]["value"] < 270_000_000
    assert a2023["revenue"]["source_type"] == "DERIVED"
    assert "dna" in rev["unmapped"]["2023"]           # 삼성 감가상각비 라인 없음
    assert rev["stage1_status"] == "APPROVED"
    assert rev["stage2_status"] == "REVIEWED"

    # 오버라이드: 사유 없으면 422
    r = client.post(f"/api/cases/{cid}/stages/2/override", json={
        "year": 2023, "account": "dna", "value": 35_000_000, "rationale": "  ",
        "changed_by": "analyst1"})
    assert r.status_code == 422

    # 오버라이드: dna 를 주석 기준으로 채움(사유 필수)
    r = client.post(f"/api/cases/{cid}/stages/2/override", json={
        "year": 2023, "account": "dna", "value": 35_000_000,
        "rationale": "사업보고서 주석 감가상각비 반영", "changed_by": "analyst1"})
    assert r.status_code == 200, r.text
    assert r.json()["overridden"] is True

    # 재검토: dna 셀이 오버라이드로 표시되고 미분류에서 빠짐
    r = client.get(f"/api/cases/{cid}/stages/2/review")
    rev2 = r.json()
    dna_cell = rev2["accounts"]["2023"]["dna"]
    assert dna_cell["overridden"] is True
    assert dna_cell["source_type"] == "EXPERT_OVERRIDE"
    assert dna_cell["value"] == pytest.approx(35_000_000, abs=1e-6)
    assert "dna" not in rev2["unmapped"]["2023"]

    # Stage 2 승인
    r = client.post(f"/api/cases/{cid}/stages/2/approve", json={"approved_by": "analyst1"})
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"

    # 스테퍼 상태
    r = client.get(f"/api/cases/{cid}/stages")
    statuses = {s["stage_no"]: s["status"] for s in r.json()}
    assert statuses[0] == "APPROVED"
    assert statuses[1] == "APPROVED"
    assert statuses[2] == "APPROVED"


def test_stage2_locked_until_stage1_approved(client):
    with myvcr.use_cassette("dart_samsung.yaml"):
        r = client.post("/api/cases", json={
            "company": "삼성전자", "valuation_date": "2023-12-28", "purpose": "general_ma"})
        cid = r.json()["case_id"]
        client.post(f"/api/cases/{cid}/stages/1/run")
    # Stage 1 미승인 상태에서 Stage 2 검토 → 409
    r = client.get(f"/api/cases/{cid}/stages/2/review")
    assert r.status_code == 409


def test_excel_downloads(client):
    with myvcr.use_cassette("dart_samsung.yaml"):
        r = client.post("/api/cases", json={
            "company": "005930", "valuation_date": "2023-12-28", "purpose": "impairment"})
        cid = r.json()["case_id"]
        client.post(f"/api/cases/{cid}/stages/1/run")
    client.post(f"/api/cases/{cid}/stages/1/approve", json={"approved_by": "a"})

    # Stage1 원본 덤프
    r = client.get(f"/api/cases/{cid}/stages/1/download")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxml")
    assert len(r.content) > 1000

    # Stage2 정규화
    r = client.get(f"/api/cases/{cid}/stages/2/download")
    assert r.status_code == 200

    # 매핑 템플릿
    r = client.get("/api/stages/2/mapping-template")
    assert r.status_code == 200
    assert len(r.content) > 1000


def test_mapping_upload_validation(client):
    # 정상 템플릿을 받아 그대로 업로드 → valid
    tmpl = client.get("/api/stages/2/mapping-template").content
    r = client.post("/api/stages/2/mapping-upload",
                    files={"file": ("map.xlsx", tmpl,
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200
    assert r.json()["valid"] is True
    assert r.json()["targets"] >= 10
