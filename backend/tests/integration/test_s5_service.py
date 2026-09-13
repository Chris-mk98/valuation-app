"""Stage 5 DCF 오케스트레이션 — 소스 monkeypatch(네트워크 없이). 산출·오버라이드 재계산·게이트."""

from __future__ import annotations

import pytest

from app.api import service
from app.core import stage_gate
from app.core.lineage import RationaleRequiredError
from app.db.models import Case, FinancialsNormalized, WaccBuild
from app.sources import price

HIST = {
    2022: {"revenue": 1000.0, "ebit": 100.0, "dna": 50.0, "capex": 60.0, "nwc": 200.0,
           "net_debt": 220.0},
    2023: {"revenue": 1100.0, "ebit": 110.0, "dna": 55.0, "capex": 66.0, "nwc": 220.0,
           "net_debt": 220.0},
}


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(price, "get_listing",
                        lambda **k: [{"code": "005930", "shares": 100.0}])


def _seed(db) -> Case:
    case = Case(case_id="c5", corp_code="00126380", corp_name="삼성전자", stock_code="005930",
                induty_code="264", valuation_date="2023-12-28", purpose="general_ma")
    db.add(case)
    for y, accts in HIST.items():
        for acc, val in accts.items():
            db.add(FinancialsNormalized(case_id="c5", year=y, account=acc, value=val))
    db.add(WaccBuild(case_id="c5", component="wacc", value=10.0))  # WACC 10%
    for s in (0, 1, 2, 3, 4):
        stage_gate.mark_reviewed(db, "c5", s)
        stage_gate.approve(db, "c5", s, approved_by="a")
    db.flush()
    return case


def test_dcf_run_handcalc(db, patched):
    case = _seed(db)
    res = service.run_stage5(db, case)
    a = {k: v["value"] for k, v in res["assumptions"].items()}
    # 과거 비율 기본값
    assert a["revenue_growth"] == pytest.approx(0.10, abs=1e-9)
    assert a["ebit_margin"] == pytest.approx(0.10, abs=1e-9)
    assert a["dna_ratio"] == pytest.approx(0.05, abs=1e-9)
    assert a["terminal_growth"] == pytest.approx(0.01, abs=1e-9)
    assert a["forecast_years"] == 5.0
    r = res["result"]
    assert r["error"] is None
    assert r["ev"] is not None and r["ev"] > 0
    assert r["equity_value"] == pytest.approx(r["ev"] - 220.0, abs=1e-6)
    assert 0.0 < r["tv_ratio"] < 1.0
    assert len(r["rows"]) == 5  # 예측기간 5년
    assert r["per_share"] is not None  # 주식수 100


def test_dcf_locked_before_stage4(db, patched):
    case = Case(case_id="c5b", corp_code="x", corp_name="t", stock_code="005930",
                induty_code="264", valuation_date="2023-12-28", purpose="general_ma")
    db.add(case)
    db.add(FinancialsNormalized(case_id="c5b", year=2023, account="revenue", value=1.0))
    db.flush()
    with pytest.raises(PermissionError):
        service.run_stage5(db, case)


def test_dcf_override_recomputes(db, patched):
    case = _seed(db)
    base = service.run_stage5(db, case)
    base_ev = base["result"]["ev"]
    with pytest.raises(RationaleRequiredError):
        service.override_stage5(db, case, name="revenue_growth", value=0.20, rationale=" ",
                                changed_by="a")
    out = service.override_stage5(db, case, name="revenue_growth", value=0.20,
                                  rationale="신제품 매출 반영", changed_by="a")
    # 성장률 상향 → EV 증가
    assert out["ev"] > base_ev
    review = service.review_stage5(db, case)
    assert review["assumptions"]["revenue_growth"]["overridden"] is True
    assert review["assumptions"]["revenue_growth"]["value"] == pytest.approx(0.20, abs=1e-9)


def test_dcf_non_operating_override(db, patched):
    case = _seed(db)
    base = service.run_stage5(db, case)["result"]["equity_value"]
    out = service.override_stage5(db, case, name="non_operating_assets", value=100.0,
                                  rationale="투자부동산 가산", changed_by="a")
    assert out["equity_value"] == pytest.approx(base + 100.0, abs=1e-6)


def test_dcf_non_overridable_rejected(db, patched):
    case = _seed(db)
    service.run_stage5(db, case)
    with pytest.raises(ValueError):
        service.override_stage5(db, case, name="wacc", value=0.05, rationale="x", changed_by="a")
