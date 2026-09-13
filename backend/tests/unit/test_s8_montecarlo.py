"""Stage 8 몬테카를로 순수함수 — 재현성·통계·토네이도."""

from __future__ import annotations

import numpy as np
import pytest

from app.stages import s5_dcf, s8_montecarlo

HISTORY = [
    {"year": 2022, "revenue": 1000.0, "ebit": 100.0, "dna": 50.0, "capex": 60.0, "nwc": 200.0},
    {"year": 2023, "revenue": 1100.0, "ebit": 110.0, "dna": 55.0, "capex": 66.0, "nwc": 220.0},
]
BASE = {
    "forecast_years": 5, "revenue_growth": 0.05, "ebit_margin": 0.10, "dna_ratio": 0.05,
    "capex_ratio": 0.06, "nwc_ratio": 0.20, "tax": 0.24, "terminal_growth": 0.01, "wacc": 0.10,
}


def test_default_corr_matrix_is_psd():
    m = np.array(s8_montecarlo.default_corr_matrix())
    assert m.shape == (6, 6)
    np.linalg.cholesky(m)  # PSD 면 예외 없음
    assert np.allclose(np.diag(m), 1.0)


def test_zero_sigma_collapses_to_base():
    specs = {v: {"mean": BASE.get(v, BASE["wacc"] if v == "wacc" else 0.0), "sigma": 0.0}
             for v in s8_montecarlo.VARS}
    specs["wacc"]["mean"] = 0.10
    res = s8_montecarlo.simulate(HISTORY, BASE, dist_specs=specs, net_debt=220.0, shares=100.0,
                                 n=500, seed=1)
    base_equity = s5_dcf.dcf_valuation(HISTORY, BASE, wacc=0.10, net_debt=220.0,
                                       shares=100.0)["equity_value"]
    assert res["std"] == pytest.approx(0.0, abs=1e-6)
    assert res["mean"] == pytest.approx(base_equity, abs=1e-6)


def test_reproducible_with_seed():
    r1 = s8_montecarlo.simulate(HISTORY, BASE, net_debt=220.0, shares=100.0, n=1000, seed=7)
    r2 = s8_montecarlo.simulate(HISTORY, BASE, net_debt=220.0, shares=100.0, n=1000, seed=7)
    assert r1["mean"] == pytest.approx(r2["mean"], abs=1e-9)
    assert r1["p90"] == pytest.approx(r2["p90"], abs=1e-9)


def test_percentiles_ordered_and_tornado():
    res = s8_montecarlo.simulate(HISTORY, BASE, net_debt=220.0, shares=100.0, n=2000, seed=3)
    assert res["p10"] <= res["p50"] <= res["p90"]
    assert res["n_valid"] > 0
    assert len(res["tornado"]) >= 1
    # 토네이도는 |스윙| 내림차순
    swings = [t["swing"] for t in res["tornado"]]
    assert swings == sorted(swings, reverse=True)


def test_histogram_bins():
    res = s8_montecarlo.simulate(HISTORY, BASE, net_debt=220.0, shares=100.0, n=500, seed=2)
    assert len(res["histogram"]["counts"]) == 30
    assert len(res["histogram"]["edges"]) == 31
