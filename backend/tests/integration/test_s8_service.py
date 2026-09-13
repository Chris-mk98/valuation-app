"""Stage 8 몬테카를로 오케스트레이션 — monkeypatch(네트워크 없이)."""

from __future__ import annotations

import pytest

from app.api import service
from app.core import stage_gate
from app.core.lineage import RationaleRequiredError
from app.db.models import Case, DcfAssumption, FinancialsNormalized


def _seed(db) -> Case:
    case = Case(case_id="c8", corp_code="00126380", corp_name="삼성전자", stock_code="005930",
                induty_code="264", valuation_date="2023-12-28", purpose="general_ma")
    db.add(case)
    for y, rev, nwc in [(2022, 1000.0, 200.0), (2023, 1100.0, 220.0)]:
        db.add(FinancialsNormalized(case_id="c8", year=y, account="revenue", value=rev))
        db.add(FinancialsNormalized(case_id="c8", year=y, account="ebit", value=rev * 0.1))
        db.add(FinancialsNormalized(case_id="c8", year=y, account="dna", value=rev * 0.05))
        db.add(FinancialsNormalized(case_id="c8", year=y, account="capex", value=rev * 0.06))
        db.add(FinancialsNormalized(case_id="c8", year=y, account="nwc", value=nwc))
    # Stage 5 가정 시드
    for name, val in [("forecast_years", 5), ("revenue_growth", 0.05), ("ebit_margin", 0.10),
                      ("dna_ratio", 0.05), ("capex_ratio", 0.06), ("nwc_ratio", 0.20),
                      ("tax", 0.24), ("terminal_growth", 0.01), ("wacc", 0.10),
                      ("net_debt", 220.0), ("non_operating_assets", 0.0), ("shares", 100.0)]:
        db.add(DcfAssumption(case_id="c8", name=name, value=val))
    for s in range(6):
        stage_gate.mark_reviewed(db, "c8", s)
        stage_gate.approve(db, "c8", s, approved_by="a")
    db.flush()
    return case


def test_mc_run_produces_distribution(db):
    case = _seed(db)
    res = service.run_stage8(db, case)
    st = res["stats"]
    assert st["n_valid"] > 0
    assert st["p10"] <= st["p50"] <= st["p90"]
    assert len(st["tornado"]) >= 1
    # 분포 파라미터 노출(평균=Stage5값)
    assert res["distributions"]["revenue_growth"]["mean"] == pytest.approx(0.05, abs=1e-9)
    assert res["distributions"]["wacc"]["mean"] == pytest.approx(0.10, abs=1e-9)


def test_mc_locked_before_stage5(db):
    case = Case(case_id="c8b", corp_code="x", corp_name="t", stock_code="005930",
                induty_code="264", valuation_date="2023-12-28", purpose="general_ma")
    db.add(case)
    db.flush()
    with pytest.raises(PermissionError):
        service.run_stage8(db, case)


def test_mc_sigma_override_changes_spread(db):
    case = _seed(db)
    base = service.run_stage8(db, case)["stats"]["std"]
    with pytest.raises(RationaleRequiredError):
        service.override_mc_sigma(db, case, var="revenue_growth", sigma=0.10, rationale=" ",
                                  changed_by="a")
    service.override_mc_sigma(db, case, var="revenue_growth", sigma=0.10,
                              rationale="불확실성 확대", changed_by="a")
    wider = service.review_stage8(db, case)["stats"]["std"]
    assert wider > base  # σ 상향 → 분포 확대
    assert service.review_stage8(db, case)["distributions"]["revenue_growth"]["overridden"] is True


def test_mc_sigma_negative_rejected(db):
    case = _seed(db)
    service.run_stage8(db, case)
    with pytest.raises(ValueError):
        service.override_mc_sigma(db, case, var="wacc", sigma=-0.1, rationale="x", changed_by="a")
