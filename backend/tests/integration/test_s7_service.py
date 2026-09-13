"""Stage 7 자산접근 오케스트레이션 — 소스 monkeypatch(네트워크 없이)."""

from __future__ import annotations

import pytest

from app.api import service
from app.core import stage_gate
from app.core.lineage import RationaleRequiredError
from app.db.models import Case, FinancialsNormalized
from app.sources import price


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(price, "get_listing", lambda **k: [{"code": "005930", "shares": 100.0}])


def _seed(db, purpose="general_ma") -> Case:
    case = Case(case_id="c7", corp_code="00126380", corp_name="삼성전자", stock_code="005930",
                induty_code="264", valuation_date="2023-12-28", purpose=purpose)
    db.add(case)
    db.add(FinancialsNormalized(case_id="c7", year=2023, account="owners_equity", value=1000.0))
    db.add(FinancialsNormalized(case_id="c7", year=2023, account="total_equity", value=1100.0))
    for s in range(7):
        stage_gate.mark_reviewed(db, "c7", s)
        stage_gate.approve(db, "c7", s, approved_by="a")
    db.flush()
    return case


def test_asset_run_uses_owners_equity(db, patched):
    case = _seed(db)
    res = service.run_stage7(db, case)
    r = res["result"]
    assert r["book_equity"] == pytest.approx(1000.0, abs=1e-9)  # 지배주주지분
    assert r["control_premium_rate"] == pytest.approx(0.0, abs=1e-9)  # 일반 M&A → 할증 없음
    assert r["value_with_premium"] == pytest.approx(1000.0, abs=1e-9)


def test_adjustment_requires_rationale_and_recomputes(db, patched):
    case = _seed(db)
    service.run_stage7(db, case)
    with pytest.raises(RationaleRequiredError):
        service.add_asset_adjustment(db, case, label="x", amount=100.0, rationale=" ")
    res = service.add_asset_adjustment(db, case, label="투자부동산", amount=300.0,
                                       rationale="감정평가")
    assert res["adjusted_net_asset"] == pytest.approx(1300.0, abs=1e-9)
    # 삭제 시 원복
    adj_id = res["adjustments"][0]["id"]
    res2 = service.remove_asset_adjustment(db, case, adj_id)
    assert res2["adjusted_net_asset"] == pytest.approx(1000.0, abs=1e-9)


def test_inheritance_gift_applies_premium(db, patched):
    case = _seed(db, purpose="inheritance_gift")
    res = service.run_stage7(db, case)
    # 규칙 기본 할증 20% → 1000 * 1.2 = 1200
    assert res["result"]["control_premium_rate"] == pytest.approx(0.20, abs=1e-9)
    assert res["result"]["value_with_premium"] == pytest.approx(1200.0, abs=1e-9)


def test_premium_override(db, patched):
    case = _seed(db, purpose="inheritance_gift")
    service.run_stage7(db, case)
    res = service.override_asset_premium(db, case, value=0.10, rationale="중소기업 할증률",
                                         changed_by="a")
    assert res["control_premium_rate"] == pytest.approx(0.10, abs=1e-9)
    assert res["value_with_premium"] == pytest.approx(1100.0, abs=1e-9)
    assert service.review_stage7(db, case)["premium_overridden"] is True


def test_asset_locked_before_stage6(db, patched):
    case = Case(case_id="c7b", corp_code="x", corp_name="t", stock_code="005930",
                induty_code="264", valuation_date="2023-12-28", purpose="general_ma")
    db.add(case)
    db.flush()
    with pytest.raises(PermissionError):
        service.run_stage7(db, case)
