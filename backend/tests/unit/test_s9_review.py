"""Stage 9 종합·레드플래그 순수함수 — 손계산."""

from __future__ import annotations

import pytest

from app.stages import s9_review

VALUES = {"income": 1000.0, "asset": 800.0, "market": 1200.0}


def test_normalize_weights_over_available():
    w = s9_review.normalize_weights({"income": 1.5, "asset": 1.0, "market": 0.0}, VALUES)
    assert w["income"] == pytest.approx(0.6, abs=1e-9)
    assert w["asset"] == pytest.approx(0.4, abs=1e-9)
    assert "market" not in w  # 가중치 0 → 제외


def test_weighted_value_merger_1_5_to_1():
    # 합병 1.5:1 → 0.6*1000 + 0.4*800 = 920
    val = s9_review.weighted_value(VALUES, {"income": 1.5, "asset": 1.0})
    assert val == pytest.approx(920.0, abs=1e-9)


def test_net_asset_floor():
    # 가중값 700, 순자산 1000, 하한 0.8 → max(700, 800) = 800
    assert s9_review.apply_net_asset_floor(700.0, 1000.0, 0.8) == pytest.approx(800.0, abs=1e-9)
    assert s9_review.apply_net_asset_floor(900.0, 1000.0, 0.8) == pytest.approx(900.0, abs=1e-9)


def test_synthesize_parallel_impairment():
    res = s9_review.synthesize(VALUES, {}, parallel=True)
    assert res["mode"] == "parallel"
    assert res["value_in_use"] == 1000.0  # DCF
    assert res["fair_value"] == 1200.0     # 시장
    assert res["recoverable_amount"] == 1200.0  # max


def test_synthesize_weighted_with_floor():
    # 순손익:순자산 3:2 → 0.6*1000+0.4*800 = 920; 하한 0.8*800=640 → 920
    res = s9_review.synthesize(VALUES, {"income": 3.0, "asset": 2.0}, net_asset_floor=0.8)
    assert res["final"] == pytest.approx(920.0, abs=1e-9)


def test_evaluate_flags():
    metrics = {
        "tv_ratio": 0.75, "terminal_growth": 0.04, "nominal_gdp": 0.037,
        "forecast_margin": 0.15, "historical_peak_margin": 0.12,
        "capex_ratio": 0.05, "dna_ratio": 0.06, "peers_count": 3, "beta_r2_min": 0.05,
    }
    thresholds = {"tv_ratio_max": 0.70, "peers_min": 5, "beta_r2_min": 0.10}
    flags = {f["key"]: f for f in s9_review.evaluate_flags(metrics, thresholds)}
    assert flags["tv_ratio"]["triggered"] is True         # 0.75 > 0.70
    assert flags["terminal_growth_vs_gdp"]["triggered"] is True  # 0.04 > 0.037
    assert flags["forecast_margin_vs_peak"]["triggered"] is True  # 0.15 > 0.12
    assert flags["capex_below_dna"]["triggered"] is True  # 0.05 < 0.06
    assert flags["peers_min"]["triggered"] is True        # 3 < 5
    assert flags["beta_r2_min"]["triggered"] is True      # 0.05 < 0.10
