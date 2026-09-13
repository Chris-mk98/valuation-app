"""core/rules 단위 테스트 — 목적별 제약 YAML 로더."""

from __future__ import annotations

import pytest

from app.core import rules


def test_list_purposes_has_four():
    purposes = rules.list_purposes()
    assert set(purposes) == {"impairment", "merger_ratio", "inheritance_gift", "general_ma"}


def test_impairment_forecast_and_growth_cap():
    r = rules.load_rules("impairment")
    assert r["constraints"]["forecast_years_max"] == 5
    assert r["constraints"]["terminal_growth_cap"] == "nominal_gdp"
    assert r["method_weights"]["editable"] is False


def test_merger_ratio_weights_locked():
    r = rules.load_rules("merger_ratio")
    mw = r["method_weights"]
    assert mw["editable"] is False
    assert mw["income"] == pytest.approx(1.5, abs=1e-6)
    assert mw["asset"] == pytest.approx(1.0, abs=1e-6)


def test_inheritance_gift_ratio_and_premium():
    r = rules.load_rules("inheritance_gift")
    assert r["method_weights"]["income"] == pytest.approx(3.0, abs=1e-6)
    assert r["method_weights"]["asset"] == pytest.approx(2.0, abs=1e-6)
    assert r["constraints"]["controlling_shareholder_premium"]["enabled"] is True


def test_general_ma_weights_editable():
    r = rules.load_rules("general_ma")
    assert r["method_weights"]["editable"] is True


def test_unknown_purpose_raises():
    with pytest.raises(KeyError):
        rules.load_rules("unknown_purpose")


def test_review_flags_thresholds():
    flags = rules.load_review_flags()["review_flags"]
    assert flags["terminal_value_ratio_max"]["threshold"] == pytest.approx(0.70, abs=1e-6)
    assert flags["peers_min"]["threshold"] == 5
    assert flags["beta_regression_r2_min"]["threshold"] == pytest.approx(0.10, abs=1e-6)
