"""Stage 6 시장접근 오케스트레이션 — 소스 monkeypatch(네트워크 없이)."""

from __future__ import annotations

import pytest

from app.api import service
from app.core import stage_gate
from app.db.models import Case, FinancialsNormalized, Peer
from app.sources import dart, price

# 대상 LTM(FinancialsNormalized): EBITDA=EBIT+D&A=120+30=150, 순이익 80, 순자산 500, 순차입금 100
TARGET_ACCTS = {"ebit": 120.0, "dna": 30.0, "net_income": 80.0, "owners_equity": 500.0,
                "total_equity": 520.0, "net_debt": 100.0, "revenue": 1000.0}

# 유사기업 원본(정규화 후): EV/EBITDA = (시총+순차입금)/EBITDA
PEERS = {
    "cp1": {"ebit": 90, "dna": 30, "net_income": 60, "owners_equity": 400, "net_debt": 0,
            "market_cap": 1200},   # ebitda 120, ev 1200 → 10x, per 20, pbr 3
    "cp2": {"ebit": 100, "dna": 20, "net_income": 50, "owners_equity": 500, "net_debt": 0,
            "market_cap": 1440},   # ebitda 120, ev 1440 → 12x, per 28.8, pbr 2.88
    "cp3": {"ebit": 110, "dna": 30, "net_income": 70, "owners_equity": 700, "net_debt": 0,
            "market_cap": 1680},   # ebitda 140, ev 1680 → 12x, per 24, pbr 2.4
}


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(price, "get_listing", lambda **k: [{"code": "005930", "shares": 1000.0}])

    def fake_financials(db, corp_code, year, **k):
        a = PEERS[corp_code]
        return [
            {"account_id": "dart_OperatingIncomeLoss", "account_nm": "영업이익", "sj_div": "IS",
             "thstrm_amount": str(int(a["ebit"] * 1_000_000))},
            {"account_id": "dart_DepreciationAndAmortisationExpense",
             "account_nm": "감가상각비및무형자산상각비", "sj_div": "CF",
             "thstrm_amount": str(int(a["dna"] * 1_000_000))},
            {"account_id": "ifrs-full_ProfitLoss", "account_nm": "당기순이익(손실)", "sj_div": "IS",
             "thstrm_amount": str(int(a["net_income"] * 1_000_000))},
            {"account_id": "ifrs-full_EquityAttributableToOwnersOfParent",
             "account_nm": "지배기업 소유주지분", "sj_div": "BS",
             "thstrm_amount": str(int(a["owners_equity"] * 1_000_000))},
            {"account_id": "-표준계정코드 미사용-", "account_nm": "단기차입금", "sj_div": "BS",
             "thstrm_amount": str(int(a["net_debt"] * 1_000_000))},  # net_debt 0 → EV=시총
        ]

    monkeypatch.setattr(dart, "get_financials", fake_financials)


def _seed(db) -> Case:
    case = Case(case_id="c6", corp_code="00126380", corp_name="삼성전자", stock_code="005930",
                induty_code="264", valuation_date="2023-12-28", purpose="general_ma")
    db.add(case)
    for acc, val in TARGET_ACCTS.items():
        db.add(FinancialsNormalized(case_id="c6", year=2023, account=acc, value=val))
    for code, m in PEERS.items():
        db.add(Peer(case_id="c6", corp_code=code, corp_name=code, stock_code=code,
                    included=1, source="SCREEN", metrics={"market_cap": m["market_cap"]}))
    for s in range(6):
        stage_gate.mark_reviewed(db, "c6", s)
        stage_gate.approve(db, "c6", s, approved_by="a")
    db.flush()
    return case


def test_market_run_handcalc(db, patched):
    case = _seed(db)
    res = service.run_stage6(db, case)
    # EV/EBITDA 배수 10,12,12 → 중앙값 12
    assert res["reps"]["ev_ebitda"]["value"] == pytest.approx(12.0, abs=1e-6)
    # 대상 적용: 12*150 - 100 = 1700
    assert res["applied"]["ev_ebitda"]["equity_value"] == pytest.approx(1700.0, abs=1e-6)
    # PBR 배수 3, 2.88, 2.4 → 중앙값 2.88; 적용 2.88*500 = 1440
    assert res["reps"]["pbr"]["value"] == pytest.approx(2.88, abs=1e-6)
    assert res["applied"]["pbr"]["equity_value"] == pytest.approx(2.88 * 500.0, abs=1e-6)


def test_market_locked_before_stage5(db, patched):
    case = Case(case_id="c6b", corp_code="x", corp_name="t", stock_code="005930",
                induty_code="264", valuation_date="2023-12-28", purpose="general_ma")
    db.add(case)
    db.flush()
    with pytest.raises(PermissionError):
        service.run_stage6(db, case)


def test_market_override_multiple_recomputes(db, patched):
    case = _seed(db)
    service.run_stage6(db, case)
    out = service.override_stage6(db, case, method="ev_ebitda", value=15.0,
                                  rationale="프리미엄 반영", changed_by="a")
    # 15*150 - 100 = 2150
    review = service.review_stage6(db, case)
    assert review["reps"]["ev_ebitda"]["overridden"] is True
    assert review["applied"]["ev_ebitda"]["equity_value"] == pytest.approx(2150.0, abs=1e-6)
    assert out["range"]["max"] >= 2150.0


def test_market_peers_under_5_warns(db, patched):
    case = _seed(db)
    res = service.run_stage6(db, case)
    assert any("유사기업" in w for w in res["warnings"])  # 3개 < 5
