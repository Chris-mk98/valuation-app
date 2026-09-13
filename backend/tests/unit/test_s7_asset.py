"""Stage 7 자산접근법 순수함수 — 손계산."""

from __future__ import annotations

import pytest

from app.stages import s7_asset

ADJ = [
    {"label": "투자부동산 시가조정", "amount": 300.0},
    {"label": "소송충당부채", "amount": -80.0},
]


def test_adjusted_net_asset():
    r = s7_asset.adjusted_net_asset(1000.0, ADJ)
    assert r["adjustments_total"] == pytest.approx(220.0, abs=1e-9)  # 300 - 80
    assert r["adjusted"] == pytest.approx(1220.0, abs=1e-9)


def test_control_premium():
    assert s7_asset.apply_control_premium(1000.0, 0.20) == pytest.approx(1200.0, abs=1e-9)
    assert s7_asset.apply_control_premium(1000.0, 0.0) == pytest.approx(1000.0, abs=1e-9)


def test_asset_valuation_with_premium_and_pershare():
    res = s7_asset.asset_valuation(1000.0, ADJ, control_premium_rate=0.20, shares=100.0)
    assert res["adjusted_net_asset"] == pytest.approx(1220.0, abs=1e-9)
    # 할증: 1220 * 1.20 = 1464
    assert res["value_with_premium"] == pytest.approx(1464.0, abs=1e-9)
    # 주당: 1464 백만원 * 1e6 / 100 주
    assert res["per_share"] == pytest.approx(1464.0 * 1e6 / 100.0, abs=1e-3)


def test_asset_valuation_no_premium_no_shares():
    res = s7_asset.asset_valuation(500.0, [], control_premium_rate=0.0, shares=None)
    assert res["value_with_premium"] == pytest.approx(500.0, abs=1e-9)
    assert res["per_share"] is None
