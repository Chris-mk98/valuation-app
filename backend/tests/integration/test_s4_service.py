"""Stage 4 WACC 오케스트레이션 — 소스 monkeypatch(네트워크 없이). 빌드업 손검증 + 오버라이드 재계산."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.api import service
from app.core import stage_gate
from app.core.lineage import RationaleRequiredError
from app.db.models import Case, Peer
from app.sources import dart, ecos, price

TARGET_CORP = "00126380"


def _series(returns, c0=100.0, start="2022-01-07"):
    d = date.fromisoformat(start)
    c = c0
    pts = [{"date": d.isoformat(), "close": c}]
    for r in returns:
        d = d + timedelta(days=7)
        c = c * (1 + r)
        pts.append({"date": d.isoformat(), "close": c})
    return pts


def _rows(pairs):
    return [{"account_id": aid, "account_nm": nm, "sj_div": sj, "thstrm_amount": str(int(amt))}
            for aid, nm, sj, amt in pairs]


@pytest.fixture
def patched(monkeypatch):
    market_ret = [((i % 7) - 3) * 0.005 for i in range(40)]  # 분산 있는 시장수익률
    peer_ret = [1.2 * r for r in market_ret]                 # β=1.2 정확
    market_series = _series(market_ret)
    peer_series = _series(peer_ret)

    monkeypatch.setattr(ecos, "get_gov_bond_10y", lambda db, d, **k: 3.183)
    monkeypatch.setattr(price, "get_index_ohlcv", lambda db, s, e, **k: market_series)
    monkeypatch.setattr(price, "get_ohlcv", lambda db, code, s, e, **k: peer_series)
    monkeypatch.setattr(price, "get_listing",
                        lambda **k: [{"code": "005930", "market_cap": 8e11}])  # 800,000 백만원

    target_rows = _rows([
        ("ifrs-full_InterestPaidClassifiedAsOperatingActivities", "이자의 지급", "CF",
         8_000 * 1_000_000),
        ("-표준계정코드 미사용-", "단기차입금", "BS", 200_000 * 1_000_000),  # gross=net_debt=200,000
    ])
    peer_rows = _rows([
        ("-표준계정코드 미사용-", "단기차입금", "BS", 500_000 * 1_000_000),  # net_debt=500,000
    ])

    def fake_financials(db, corp_code, year, **k):
        return target_rows if corp_code == TARGET_CORP else peer_rows

    monkeypatch.setattr(dart, "get_financials", fake_financials)


def _seed(db) -> Case:
    case = Case(case_id="c4", corp_code=TARGET_CORP, corp_name="삼성전자", stock_code="005930",
                induty_code="264", valuation_date="2023-12-28", purpose="general_ma")
    db.add(case)
    # 유사기업 2개(시총 1,000,000 백만원) → D/E = 500,000/1,000,000 = 0.5
    for i in (1, 2):
        db.add(Peer(case_id="c4", corp_code=f"cp{i}", corp_name=f"peer{i}", stock_code=f"P{i}",
                    included=1, source="SCREEN", metrics={"market_cap": 1_000_000}))
    for s in (0, 1, 2, 3):
        stage_gate.mark_reviewed(db, "c4", s)
        stage_gate.approve(db, "c4", s, approved_by="a")
    db.flush()
    return case


def test_wacc_buildup_handcalc(db, patched):
    case = _seed(db)
    service.run_stage4(db, case)
    v = service._wacc_values(db, "c4")
    assert v["rf"] == pytest.approx(3.183, abs=1e-6)
    assert v["beta_u_median"] == pytest.approx(1.2 / 1.38, abs=1e-6)  # 언레버
    assert v["target_de"] == pytest.approx(0.5, abs=1e-6)
    assert v["beta_relevered"] == pytest.approx(1.2, abs=1e-6)        # 리레버 복원
    assert v["erp"] == pytest.approx(4.60, abs=1e-6)
    assert v["size_premium"] == pytest.approx(3.0, abs=1e-6)          # 시총 80만백만원=8천억 → 소형
    assert v["kd"] == pytest.approx(4.0, abs=1e-6)                    # 8,000/200,000
    # Ke = 3.183 + 1.2*(4.6+0.9) + 3.0 = 12.783
    assert v["ke"] == pytest.approx(12.783, abs=1e-5)
    # WACC = 0.8*12.783 + 0.2*4.0*0.76 = 10.8344
    assert v["wacc"] == pytest.approx(10.8344, abs=1e-4)


def test_wacc_locked_before_stage3(db, patched):
    case = Case(case_id="c4b", corp_code=TARGET_CORP, corp_name="t", stock_code="005930",
                induty_code="264", valuation_date="2023-12-28", purpose="general_ma")
    db.add(case)
    db.flush()
    with pytest.raises(PermissionError):
        service.run_stage4(db, case)


def test_override_recomputes_downstream(db, patched):
    case = _seed(db)
    service.run_stage4(db, case)
    # 사유 없으면 거부
    with pytest.raises(RationaleRequiredError):
        service.override_stage4(db, case, component="beta_relevered", value=1.5, rationale=" ",
                                changed_by="a")
    # β_리레버를 1.5로 오버라이드 → Ke·WACC 재계산
    service.override_stage4(db, case, component="beta_relevered", value=1.5,
                            rationale="목표 자본구조 조정", changed_by="a")
    v = service._wacc_values(db, "c4")
    assert v["beta_relevered"] == pytest.approx(1.5, abs=1e-9)
    # Ke = 3.183 + 1.5*5.5 + 3.0 = 14.433
    assert v["ke"] == pytest.approx(14.433, abs=1e-5)
    # WACC = 0.8*14.433 + 0.608 = 12.1544
    assert v["wacc"] == pytest.approx(12.1544, abs=1e-4)


def test_override_persists_through_rerun_review(db, patched):
    case = _seed(db)
    service.run_stage4(db, case)
    service.override_stage4(db, case, component="ke", value=10.0, rationale="심사역 판단",
                            changed_by="a")
    review = service.review_stage4(db, case)
    assert review["components"]["ke"]["overridden"] is True
    assert review["components"]["ke"]["value"] == pytest.approx(10.0, abs=1e-9)
