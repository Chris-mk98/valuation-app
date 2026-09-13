"""sources/ 통합 테스트 — VCR 카세트 재생(네트워크 없이). 실키는 DUMMY 로 대체.

카세트는 삼성전자(00126380) 기업개황 + 2019~2023 재무제표, ECOS 국고채 10Y(2023-12-28).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import vcr

from app.db.models import ApiCallLog, RawDart
from app.params.account_map import load_account_map
from app.sources import dart, ecos
from app.stages.s2_normalize import normalize_year

CASSETTES = Path(__file__).parent / "cassettes"
CORP = "00126380"

myvcr = vcr.VCR(
    cassette_library_dir=str(CASSETTES),
    record_mode="none",
    filter_query_parameters=[("crtfc_key", "DUMMY")],
)


@pytest.fixture(autouse=True)
def _dummy_keys(monkeypatch):
    """재생 시 요청 URI 가 카세트(키=DUMMY)와 일치하도록 키를 DUMMY 로 고정."""
    fake = SimpleNamespace(dart_api_key="DUMMY", ecos_api_key="DUMMY")
    monkeypatch.setattr(dart, "get_settings", lambda: fake)
    monkeypatch.setattr(ecos, "get_settings", lambda: fake)


def test_get_company_replays(db):
    with myvcr.use_cassette("dart_samsung.yaml"):
        comp = dart.get_company(db, CORP)
    assert "삼성전자" in comp["corp_name"]
    assert comp["induty_code"] == "264"
    assert comp["stock_code"] == "005930"
    # 원본 보존 + 호출 로그
    assert db.query(RawDart).filter_by(doc_type="company").count() == 1
    assert db.query(ApiCallLog).filter_by(endpoint="company.json").count() == 1


def test_get_financials_cache_second_call(db):
    with myvcr.use_cassette("dart_samsung.yaml"):
        rows = dart.get_financials(db, CORP, "2023")
        assert len(rows) > 150
        # 두 번째 호출은 캐시(HTTP 미발생)
        rows2 = dart.get_financials(db, CORP, "2023")
    assert len(rows2) == len(rows)
    assert db.query(RawDart).filter_by(doc_type="financials", bsns_year="2023").count() == 1
    logs = db.query(ApiCallLog).filter_by(endpoint="fnlttSinglAcntAll.json").all()
    assert any(x.cache_hit == 1 for x in logs)  # 캐시 히트 기록
    assert any(x.cache_hit == 0 for x in logs)  # 최초 호출 기록


def test_normalize_samsung_2023_real(db):
    """실제 삼성 2023 연결 → 정규화 손검증(회계 판단 확정본 반영)."""
    with myvcr.use_cassette("dart_samsung.yaml"):
        rows = dart.get_financials(db, CORP, "2023")
    res = normalize_year(rows, load_account_map())
    a = res["accounts"]
    # 매출 ~258.9조(백만원), 영업이익 양수
    assert 250_000_000 < a["revenue"] < 270_000_000
    assert a["ebit"] is not None and a["ebit"] > 0
    # capex = 유형취득 57,611,292 + 무형취득 2,922,875 = 60,534,167 백만원
    assert a["capex"] == pytest.approx(60_534_167, rel=1e-4)
    # 삼성은 순현금 → net_debt 음수
    assert a["net_debt"] < 0
    # 삼성 CF 에 감가상각비 개별 라인 없음 → dna unmapped (Q2)
    assert a["dna"] is None
    assert "dna" in res["unmapped"]


def test_ecos_gov_bond_10y_replays(db):
    with myvcr.use_cassette("ecos_gov_bond_10y.yaml"):
        val = ecos.get_gov_bond_10y(db, "2023-12-28")
    assert val == pytest.approx(3.183, abs=1e-6)
    assert db.query(ApiCallLog).filter_by(source="ECOS").count() == 1


def test_resolve_corp_code_offline():
    """corp_code 검색은 JSON 캐시 픽스처로(네트워크·VCR 불필요)."""
    fixture = Path(__file__).parents[1] / "fixtures" / "corp_codes.json"
    got = dart.resolve_corp_code("005930", cache_path=fixture)
    assert got["corp_code"] == CORP
    got2 = dart.resolve_corp_code("삼성전자", cache_path=fixture)
    assert got2["corp_code"] == CORP
    with pytest.raises(dart.DartError):
        dart.resolve_corp_code("존재하지않는회사명", cache_path=fixture)
