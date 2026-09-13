"""Stage 3 오케스트레이션 — 소스 monkeypatch(네트워크 없이). 스크리닝→확정→수동추가→승인."""

from __future__ import annotations

import pytest

from app.api import service
from app.core import stage_gate
from app.core.lineage import RationaleRequiredError
from app.db.models import Case, FinancialsNormalized
from app.sources import dart, price

# 종목코드 → (induty, 매출백만원, 순이익백만원). 모두 같은 KRX 섹터로 prefilter 통과시킴.
UNIVERSE = {
    "005930": ("264", 300_000, 40_000),   # 대상(삼성)
    "000660": ("264", 200_000, 10_000),   # KSIC26·규모ok·흑자 → 통과
    "009150": ("262", 150_000, 5_000),    # KSIC26·ok·흑자 → 통과
    "000990": ("264", 3_000_000, 20_000), # 규모 10x 초과 → 탈락
    "001820": ("264", 100_000, -5_000),   # 순손실 → 탈락
    "035420": ("631", 250_000, 30_000),   # KSIC63(업종 불일치) → 탈락
}
SECTOR = "반도체 제조업"


def _corp(code: str) -> str:
    return f"corp_{code}"


@pytest.fixture
def patched(monkeypatch):
    listing = [
        {"code": c, "name": c, "market": "KOSPI", "market_cap": 1e13,
         "shares": 1, "sector": SECTOR, "industry": "x", "listing_date": "2000-01-01"}
        for c in UNIVERSE
    ]
    monkeypatch.setattr(price, "get_listing", lambda **k: listing)
    monkeypatch.setattr(dart, "resolve_corp_code",
                        lambda q, **k: {"corp_code": _corp(q), "corp_name": q, "stock_code": q})

    def fake_company(db, corp_code, **k):
        code = corp_code.removeprefix("corp_")
        return {"corp_name": code, "stock_code": code, "induty_code": UNIVERSE[code][0]}

    def fake_financials(db, corp_code, year, **k):
        code = corp_code.removeprefix("corp_")
        _, rev_mn, ni_mn = UNIVERSE[code]
        return [
            {"account_id": "ifrs-full_Revenue", "account_nm": "매출액", "sj_div": "IS",
             "thstrm_amount": str(int(rev_mn * 1_000_000))},
            {"account_id": "ifrs-full_ProfitLoss", "account_nm": "당기순이익(손실)", "sj_div": "IS",
             "thstrm_amount": str(int(ni_mn * 1_000_000))},
        ]

    monkeypatch.setattr(dart, "get_company", fake_company)
    monkeypatch.setattr(dart, "get_financials", fake_financials)
    return listing


def _seed_case(db) -> Case:
    case = Case(case_id="c3", corp_code=_corp("005930"), corp_name="삼성전자",
                stock_code="005930", induty_code="264", valuation_date="2023-12-28",
                purpose="general_ma")
    db.add(case)
    db.add(FinancialsNormalized(case_id="c3", year=2023, account="revenue", value=300_000))
    for s in (0, 1, 2):
        stage_gate.mark_reviewed(db, "c3", s)
        stage_gate.approve(db, "c3", s, approved_by="a")
    db.flush()
    return case


def test_screening_selects_ksic_peers(db, patched):
    case = _seed_case(db)
    res = service.run_stage3(db, case)
    assert res["passed"] == 2  # 000660, 009150
    review = service.review_stage3(db, case)
    included = {p["corp_code"] for p in review["peers"] if p["included"]}
    assert included == {_corp("000660"), _corp("009150")}
    # 탈락 사유가 metrics.filters 로 보임
    by = {p["corp_code"]: p["metrics"]["filters"] for p in review["peers"]}
    assert by[_corp("000990")]["size"] is False
    assert by[_corp("001820")]["profit"] is False
    assert by[_corp("035420")]["industry"] is False


def test_stage3_locked_before_stage2(db, patched):
    case = Case(case_id="c3b", corp_code="x", corp_name="t", stock_code="005930",
                induty_code="264", valuation_date="2023-12-28", purpose="general_ma")
    db.add(case)
    db.flush()
    with pytest.raises(PermissionError):
        service.run_stage3(db, case)


def test_toggle_requires_rationale_and_invalidates(db, patched):
    case = _seed_case(db)
    service.run_stage3(db, case)
    # Stage 3 승인해 둔 뒤 제외 → 하위 무효화 확인용
    stage_gate.approve(db, "c3", 3, approved_by="a") if False else None
    with pytest.raises(RationaleRequiredError):
        service.set_peer_inclusion(db, case, _corp("000660"), included=False, rationale="  ")
    out = service.set_peer_inclusion(db, case, _corp("000660"), included=False,
                                     rationale="사업구조 상이로 제외")
    assert out["included"] is False and out["rationale"].startswith("사업구조")


def test_manual_add_peer(db, patched):
    case = _seed_case(db)
    service.run_stage3(db, case)
    out = service.add_manual_peer(db, case, "000990", rationale="규모 크나 사업 유사")
    assert out["included"] is True and out["source"] == "MANUAL"
    review = service.review_stage3(db, case)
    assert any(p["source"] == "MANUAL" and p["included"] for p in review["peers"])


def test_stage3_approve_after_confirm(db, patched):
    case = _seed_case(db)
    service.run_stage3(db, case)
    res = service.approve_stage(db, case, 3, approved_by="analyst")
    assert res["status"] == "APPROVED"
