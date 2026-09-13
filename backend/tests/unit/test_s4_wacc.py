"""Stage 4 WACC 순수함수 — 손계산 대조 (tol 1e-6)."""

from __future__ import annotations

import pytest

from app.params import param_tables
from app.stages import s4_wacc


def test_beta_ols_exact_linear():
    market = [1.0, 2.0, 3.0, 4.0, 5.0]
    stock = [2.0, 4.0, 6.0, 8.0, 10.0]  # 정확히 β=2, α=0
    res = s4_wacc.beta_ols(stock, market)
    assert res["beta"] == pytest.approx(2.0, abs=1e-9)
    assert res["alpha"] == pytest.approx(0.0, abs=1e-9)
    assert res["r2"] == pytest.approx(1.0, abs=1e-9)
    assert res["n"] == 5


def test_beta_ols_with_intercept_and_r2():
    market = [-2.0, -1.0, 0.0, 1.0, 2.0]
    stock = [1.0 + 1.5 * m for m in market]  # β=1.5, α=1
    res = s4_wacc.beta_ols(stock, market)
    assert res["beta"] == pytest.approx(1.5, abs=1e-9)
    assert res["alpha"] == pytest.approx(1.0, abs=1e-9)
    assert res["r2"] == pytest.approx(1.0, abs=1e-9)


def test_unlever_relever_roundtrip():
    beta_u = s4_wacc.unlever_beta(1.2, de=0.5, tax=0.24)
    # 1.2 / (1 + 0.76*0.5) = 1.2 / 1.38
    assert beta_u == pytest.approx(1.2 / 1.38, abs=1e-9)
    back = s4_wacc.relever_beta(beta_u, de=0.5, tax=0.24)
    assert back == pytest.approx(1.2, abs=1e-9)


def test_cost_of_equity_buildup():
    ke = s4_wacc.cost_of_equity(3.183, 1.0, 4.60, size_premium=0.5, country_risk=0.90)
    # 3.183 + 1.0*(4.60+0.90) + 0.5 = 3.183 + 5.5 + 0.5
    assert ke == pytest.approx(9.183, abs=1e-9)


def test_cost_of_debt_from_interest():
    kd = s4_wacc.cost_of_debt_from_interest(interest_expense=30.0, avg_debt=600.0)
    assert kd == pytest.approx(5.0, abs=1e-9)  # 30/600 = 5%
    assert s4_wacc.cost_of_debt_from_interest(10.0, 0.0) is None


def test_wacc_handcalc():
    w = s4_wacc.wacc(ke=9.183, kd=4.0, equity_value=800.0, debt_value=200.0, tax=0.24)
    # 0.8*9.183 + 0.2*4.0*0.76 = 7.3464 + 0.608
    assert w == pytest.approx(7.9544, abs=1e-6)


def test_median():
    assert s4_wacc.median([1.0, 3.0, 2.0]) == 2.0
    assert s4_wacc.median([1.0, 2.0, 3.0, 4.0]) == 2.5
    assert s4_wacc.median([]) is None


def test_weekly_returns_and_align():
    # 3주치 주간 종가 100→110→121 → 수익률 10%, 10%
    prices = [
        {"date": "2023-01-06", "close": 100},  # W01
        {"date": "2023-01-13", "close": 110},  # W02
        {"date": "2023-01-20", "close": 121},  # W03
    ]
    wr = s4_wacc.to_weekly_returns(prices)
    vals = [wr[k] for k in sorted(wr)]
    assert vals == pytest.approx([0.10, 0.10], abs=1e-9)

    mkt = {"2023-W02": 0.05, "2023-W03": 0.05, "2023-W04": 0.01}
    a, b = s4_wacc.align_returns(wr, mkt)
    assert len(a) == 2 and len(b) == 2  # 공통 주 W02, W03


def test_param_tables_seed_values():
    assert param_tables.get_erp("KR")["value"] == pytest.approx(4.60, abs=1e-6)
    assert param_tables.get_country_risk("KR")["value"] == pytest.approx(0.90, abs=1e-6)
    assert param_tables.get_tax_rate("KR")["value"] == pytest.approx(24.0, abs=1e-6)
    # 삼성급 초대형(시총 400조=4e8 백만원) → 규모프리미엄 0
    assert param_tables.get_size_premium(400_000_000)["value"] == pytest.approx(0.0, abs=1e-6)
    # 소형(5천억=500,000 백만원) → 3.0%
    assert param_tables.get_size_premium(500_000)["value"] == pytest.approx(3.0, abs=1e-6)
