"""Stage 9 목적별 종합 오케스트레이션 — monkeypatch(네트워크 없이)."""

from __future__ import annotations

import pytest

from app.api import service
from app.core import stage_gate
from app.db.models import (
    AssetResult,
    Case,
    DcfAssumption,
    DcfResult,
    FinancialsNormalized,
    MarketResult,
    Peer,
    WaccBuild,
)
from app.sources import ecos


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(ecos, "get_nominal_gdp_growth", lambda db, y, **k: 0.037)


def _seed(db, purpose="merger_ratio") -> Case:
    case = Case(case_id="c9", corp_code="00126380", corp_name="삼성전자", stock_code="005930",
                induty_code="264", valuation_date="2023-12-28", purpose=purpose)
    db.add(case)
    # 세 방법 결과: 수익 1000, 자산 800, 시장 중앙값 1200
    db.add(DcfResult(case_id="c9", payload={"equity_value": 1000.0, "tv_ratio": 0.75}))
    db.add(AssetResult(case_id="c9", payload={"value_with_premium": 800.0}))
    db.add(MarketResult(case_id="c9", payload={"range": {"min": 1100.0, "median": 1200.0,
                                                         "max": 1300.0}}))
    # DCF 가정·과거·베타R²·유사기업(플래그용)
    for name, val in [("terminal_growth", 0.02), ("ebit_margin", 0.15), ("capex_ratio", 0.05),
                      ("dna_ratio", 0.06)]:
        db.add(DcfAssumption(case_id="c9", name=name, value=val))
    for y, rev, ebit in [(2022, 1000.0, 100.0), (2023, 1100.0, 120.0)]:
        db.add(FinancialsNormalized(case_id="c9", year=y, account="revenue", value=rev))
        db.add(FinancialsNormalized(case_id="c9", year=y, account="ebit", value=ebit))
    db.add(WaccBuild(case_id="c9", component="beta_r2_min", value=0.05))
    db.add(Peer(case_id="c9", corp_code="p1", corp_name="p1", included=1, source="SCREEN"))
    for s in range(6):
        stage_gate.mark_reviewed(db, "c9", s)
        stage_gate.approve(db, "c9", s, approved_by="a")
    db.flush()
    return case


def test_merger_weighting_locked_1_5_to_1(db, patched):
    case = _seed(db, purpose="merger_ratio")
    res = service.run_stage9(db, case)
    syn = res["final"]["synthesis"]
    # 0.6*1000 + 0.4*800 = 920 (시장 미사용)
    assert syn["final"] == pytest.approx(920.0, abs=1e-6)
    assert res["weights_editable"] is False


def test_merger_weight_override_rejected_when_locked(db, patched):
    case = _seed(db, purpose="merger_ratio")
    service.run_stage9(db, case)
    with pytest.raises(ValueError, match="잠"):
        service.override_final_weight(db, case, method="market", value=1.0, rationale="x",
                                      changed_by="a")


def test_inheritance_net_asset_floor(db, patched):
    case = _seed(db, purpose="inheritance_gift")
    res = service.run_stage9(db, case)
    # 3:2 → 0.6*1000+0.4*800=920; 하한 0.8*800=640 → 920
    assert res["final"]["synthesis"]["final"] == pytest.approx(920.0, abs=1e-6)


def test_impairment_parallel(db, patched):
    case = _seed(db, purpose="impairment")
    res = service.run_stage9(db, case)
    syn = res["final"]["synthesis"]
    assert syn["mode"] == "parallel"
    assert syn["value_in_use"] == 1000.0    # DCF
    assert syn["fair_value"] == 1200.0       # 시장
    assert syn["recoverable_amount"] == 1200.0


def test_general_ma_equal_weights_and_override(db, patched):
    case = _seed(db, purpose="general_ma")
    res = service.run_stage9(db, case)
    # 균등: (1000+800+1200)/3 = 1000
    assert res["final"]["synthesis"]["final"] == pytest.approx(1000.0, abs=1e-6)
    assert res["weights_editable"] is True
    out = service.override_final_weight(db, case, method="income", value=2.0,
                                        rationale="수익 비중 상향", changed_by="a")
    # income 2, asset 1, market 1 → (2*1000+1*800+1*1200)/4 = 1000
    assert out["final"] == pytest.approx(1000.0, abs=1e-6)


def test_flags_must_be_acknowledged_before_approve(db, patched):
    case = _seed(db, purpose="merger_ratio")
    res = service.run_stage9(db, case)
    triggered = [f["key"] for f in res["final"]["flags"] if f["triggered"]]
    assert "tv_ratio" in triggered  # 0.75 > 0.70
    assert "peers_min" in triggered  # 1 < 5
    # 미승인 상태 승인 시도 → 거부
    with pytest.raises(ValueError, match="미승인"):
        service.approve_stage(db, case, 9, "analyst")
    for k in triggered:
        service.acknowledge_flag(db, case, key=k, note="검토 완료", by="analyst")
    out = service.approve_stage(db, case, 9, "analyst")
    assert out["status"] == "APPROVED"


def test_locked_before_stage5(db, patched):
    case = Case(case_id="c9b", corp_code="x", corp_name="t", stock_code="005930",
                induty_code="264", valuation_date="2023-12-28", purpose="general_ma")
    db.add(case)
    db.flush()
    with pytest.raises(PermissionError):
        service.run_stage9(db, case)
