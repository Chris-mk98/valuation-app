"""Stage 5 DCF 순수함수 — 손계산 대조 (tol)."""

from __future__ import annotations

import pytest

from app.stages import s5_dcf

HISTORY = [
    {"year": 2022, "revenue": 1000.0, "ebit": 100.0, "dna": 50.0, "capex": 60.0, "nwc": 200.0},
    {"year": 2023, "revenue": 1100.0, "ebit": 110.0, "dna": 55.0, "capex": 66.0, "nwc": 220.0},
]


def test_historical_ratios():
    r = s5_dcf.historical_ratios(HISTORY)
    assert r["revenue_cagr"] == pytest.approx(0.10, abs=1e-9)   # 1100/1000 - 1
    assert r["ebit_margin"] == pytest.approx(0.10, abs=1e-9)
    assert r["dna_ratio"] == pytest.approx(0.05, abs=1e-9)
    assert r["capex_ratio"] == pytest.approx(0.06, abs=1e-9)
    assert r["nwc_ratio"] == pytest.approx(0.20, abs=1e-9)


ASSUMPTIONS = {
    "forecast_years": 2, "revenue_growth": 0.10, "ebit_margin": 0.10,
    "dna_ratio": 0.05, "capex_ratio": 0.06, "nwc_ratio": 0.20,
    "tax": 0.24, "terminal_growth": 0.01,
}


def test_project_fcff_handcalc():
    rows = s5_dcf.project_fcff(1100.0, 220.0, ASSUMPTIONS)
    # 1년차: rev 1210, ebit 121, nopat 91.96, dna 60.5, capex 72.6, nwc 242, Δnwc 22
    #  fcff = 91.96 + 60.5 - 72.6 - 22 = 57.86
    assert rows[0]["fcff"] == pytest.approx(57.86, abs=1e-6)
    # 2년차: rev 1331, nopat 101.156, dna 66.55, capex 79.86, Δnwc 24.2 → 63.646
    assert rows[1]["fcff"] == pytest.approx(63.646, abs=1e-6)


def test_terminal_value_gordon():
    tv = s5_dcf.terminal_value_gordon(63.646, g=0.01, wacc=0.10)
    # 63.646*1.01/0.09
    assert tv == pytest.approx(63.646 * 1.01 / 0.09, abs=1e-6)
    with pytest.raises(ValueError):
        s5_dcf.terminal_value_gordon(100.0, g=0.10, wacc=0.10)


def test_dcf_valuation_full_handcalc():
    res = s5_dcf.dcf_valuation(HISTORY, ASSUMPTIONS, wacc=0.10, net_debt=220.0,
                               non_operating_assets=0.0, shares=100.0)
    # PV: 57.86/1.1 = 52.6, 63.646/1.21 = 52.6 → 합 105.2
    assert res["pv_sum"] == pytest.approx(105.2, abs=1e-6)
    tv = 63.646 * 1.01 / 0.09
    assert res["tv"] == pytest.approx(tv, abs=1e-6)
    pv_tv = tv / 1.21
    assert res["pv_tv"] == pytest.approx(pv_tv, abs=1e-6)
    ev = 105.2 + pv_tv
    assert res["ev"] == pytest.approx(ev, abs=1e-6)
    assert res["equity_value"] == pytest.approx(ev - 220.0, abs=1e-6)
    # TV 비중 > 70% (레드플래그)
    assert res["tv_ratio"] > 0.70
    # 주당가치(원) = 주주가치(백만원)*1e6 / 주식수
    assert res["per_share"] == pytest.approx((ev - 220.0) * 1_000_000 / 100.0, abs=1e-3)


def test_non_operating_assets_add_to_equity():
    base = s5_dcf.dcf_valuation(HISTORY, ASSUMPTIONS, wacc=0.10, net_debt=220.0, shares=100.0)
    adj = s5_dcf.dcf_valuation(HISTORY, ASSUMPTIONS, wacc=0.10, net_debt=220.0,
                               non_operating_assets=50.0, shares=100.0)
    assert adj["equity_value"] == pytest.approx(base["equity_value"] + 50.0, abs=1e-9)
