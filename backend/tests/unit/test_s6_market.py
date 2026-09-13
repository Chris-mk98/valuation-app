"""Stage 6 시장접근법 순수함수 — 손계산 대조."""

from __future__ import annotations

import pytest

from app.stages import s6_market


def test_peer_multiples():
    m = s6_market.peer_multiples({
        "market_cap": 800.0, "net_debt": 200.0, "ebitda": 100.0,
        "net_income": 50.0, "net_asset": 400.0,
    })
    assert m["ev_ebitda"] == pytest.approx((800 + 200) / 100, abs=1e-9)  # 10.0
    assert m["per"] == pytest.approx(800 / 50, abs=1e-9)                 # 16.0
    assert m["pbr"] == pytest.approx(800 / 400, abs=1e-9)               # 2.0


def test_peer_multiples_dna_missing_excludes_ev_ebitda():
    m = s6_market.peer_multiples({"market_cap": 800.0, "net_debt": 200.0, "ebitda": None,
                                  "net_income": 50.0, "net_asset": 400.0})
    assert m["ev_ebitda"] is None  # EBITDA 결손 → 제외
    assert m["per"] is not None and m["pbr"] is not None


def test_remove_outliers_iqr():
    # 10,11,12,13 정상 + 100 이상치
    o = s6_market.remove_outliers_iqr([10.0, 11.0, 12.0, 13.0, 100.0])
    assert 100.0 in o["removed"]
    assert set(o["kept"]) == {10.0, 11.0, 12.0, 13.0}


def test_remove_outliers_small_sample_kept():
    o = s6_market.remove_outliers_iqr([10.0, 100.0])  # n<4 → 제거 생략
    assert o["removed"] == []


def test_market_valuation_handcalc():
    # 유사기업 3사, EV/EBITDA = 10, 12, 14 → 중앙값 12
    peers = [
        {"corp_name": "A", "market_cap": 1000, "net_debt": 0, "ebitda": 100,
         "net_income": 50, "net_asset": 500},   # ev/ebitda 10, per 20, pbr 2
        {"corp_name": "B", "market_cap": 1200, "net_debt": 0, "ebitda": 100,
         "net_income": 60, "net_asset": 500},   # 12, 20, 2.4
        {"corp_name": "C", "market_cap": 1400, "net_debt": 0, "ebitda": 100,
         "net_income": 70, "net_asset": 700},   # 14, 20, 2.0
    ]
    target = {"ebitda": 200.0, "net_income": 100.0, "net_asset": 1000.0,
              "net_debt": 100.0, "shares": 1000.0}
    res = s6_market.market_valuation(peers, target)
    assert res["reps"]["ev_ebitda"] == pytest.approx(12.0, abs=1e-9)
    assert res["reps"]["per"] == pytest.approx(20.0, abs=1e-9)
    assert res["reps"]["pbr"] == pytest.approx(2.0, abs=1e-9)
    # EV/EBITDA: 12*200 - 100 = 2300
    assert res["applied"]["ev_ebitda"]["equity_value"] == pytest.approx(2300.0, abs=1e-9)
    # PER: 20*100 = 2000
    assert res["applied"]["per"]["equity_value"] == pytest.approx(2000.0, abs=1e-9)
    # PBR: 2*1000 = 2000
    assert res["applied"]["pbr"]["equity_value"] == pytest.approx(2000.0, abs=1e-9)
    assert res["range"]["min"] == pytest.approx(2000.0, abs=1e-9)
    assert res["range"]["max"] == pytest.approx(2300.0, abs=1e-9)
    # 주당가치 = equity*1e6/shares
    assert res["applied"]["per"]["per_share"] == pytest.approx(2000.0 * 1e6 / 1000.0, abs=1e-3)
