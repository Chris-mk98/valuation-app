"""Stage 2 정규화 순수함수 — 손계산 기대값 대조 (CLAUDE.md: 계산 로직은 손계산 fixture).

금액은 원 단위로 입력하고 백만원(÷1e6)으로 검증한다. tol 1e-6.
"""

from __future__ import annotations

import pytest

from app.params.account_map import load_account_map
from app.stages.s2_normalize import normalize, normalize_year

MAP = load_account_map()
W = 1_000_000_000  # 십억원(원 단위) → 백만원으로는 1_000


def _r(account_id: str, account_nm: str, sj_div: str, amount_won: float) -> dict:
    return {
        "account_id": account_id,
        "account_nm": account_nm,
        "sj_div": sj_div,
        "thstrm_amount": str(int(amount_won)),
    }


def _base_rows() -> list[dict]:
    """감가상각비 라인이 없는(삼성형) 완전한 1개년 원본. 금액은 십억원 배수."""
    return [
        # IS
        _r("ifrs-full_Revenue", "매출액", "IS", 300 * W),
        _r("ifrs-full_CostOfSales", "매출원가", "IS", 200 * W),
        _r("ifrs-full_GrossProfit", "매출총이익", "IS", 100 * W),
        _r("dart_TotalSellingGeneralAdministrativeExpenses", "판매비와관리비", "IS", 40 * W),
        _r("dart_OperatingIncomeLoss", "영업이익", "IS", 60 * W),
        _r("ifrs-full_ProfitLossBeforeTax", "법인세비용차감전순이익(손실)", "IS", 55 * W),
        _r("ifrs-full_IncomeTaxExpenseContinuingOperations", "법인세비용", "IS", 11 * W),
        _r("ifrs-full_ProfitLoss", "당기순이익(손실)", "IS", 44 * W),
        # BS 자산
        _r("ifrs-full_CashAndCashEquivalents", "현금및현금성자산", "BS", 50 * W),
        _r("ifrs-full_CurrentTradeReceivables", "매출채권", "BS", 30 * W),
        _r("ifrs-full_Inventories", "재고자산", "BS", 20 * W),
        _r("ifrs-full_OtherCurrentAssets", "기타유동자산", "BS", 5 * W),
        # BS 부채
        _r("ifrs-full_TradeAndOtherCurrentPayablesToTradeSuppliers", "매입채무", "BS", 15 * W),
        _r("ifrs-full_AccrualsClassifiedAsCurrent", "미지급비용", "BS", 8 * W),
        _r("dart_ShortTermAdvancesCustomers", "선수금", "BS", 2 * W),
        _r("ifrs-full_OtherCurrentLiabilities", "기타유동부채", "BS", 3 * W),
        _r("-표준계정코드 미사용-", "단기차입금", "BS", 10 * W),  # account_id 없음 → 계정명 매칭
        _r("ifrs-full_CurrentPortionOfLongtermBorrowings", "유동성장기부채", "BS", 4 * W),
        _r("ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued", "사채", "BS", 6 * W),
        _r("ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived", "장기차입금", "BS", 5 * W),
        # BS 자본
        _r("ifrs-full_NoncontrollingInterests", "비지배지분", "BS", 7 * W),
        _r("ifrs-full_Equity", "자본총계", "BS", 120 * W),
        _r("ifrs-full_EquityAttributableToOwnersOfParent", "지배기업 소유주지분", "BS", 113 * W),
        # CF (취득=양수, 감가상각비 라인 없음)
        _r("ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
           "유형자산의 취득", "CF", 25 * W),
        _r("ifrs-full_PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities",
           "무형자산의 취득", "CF", 5 * W),
    ]


def test_direct_and_composite_handcalc():
    res = normalize_year(_base_rows(), MAP)
    a = res["accounts"]
    # 직접 매핑 (백만원)
    assert a["revenue"] == pytest.approx(300_000, abs=1e-6)
    assert a["ebit"] == pytest.approx(60_000, abs=1e-6)
    assert a["net_income"] == pytest.approx(44_000, abs=1e-6)
    assert a["cash"] == pytest.approx(50_000, abs=1e-6)
    assert a["nci"] == pytest.approx(7_000, abs=1e-6)
    # 합성: capex = 25,000 + 5,000
    assert a["capex"] == pytest.approx(30_000, abs=1e-6)
    # nwc = (30,000+20,000+5,000) − (15,000+8,000+2,000+3,000) = 55,000 − 28,000
    assert a["nwc"] == pytest.approx(27_000, abs=1e-6)
    # net_debt = (10,000+4,000+6,000+5,000) − 50,000 = −25,000 (순현금)
    assert a["net_debt"] == pytest.approx(-25_000, abs=1e-6)


def test_dna_missing_is_unmapped():
    res = normalize_year(_base_rows(), MAP)
    assert res["accounts"]["dna"] is None
    assert res["unmapped"] == ["dna"]
    assert any("dna" in w for w in res["warnings"])


def test_single_borrowing_by_account_name():
    """단기차입금(account_id 미사용)이 계정명으로 net_debt 에 반영되는지."""
    rows = [r for r in _base_rows() if r["account_nm"] != "단기차입금"]
    res = normalize_year(rows, MAP)
    # 단기차입금 10,000 제외 → net_debt = 15,000 − 50,000 = −35,000
    assert res["accounts"]["net_debt"] == pytest.approx(-35_000, abs=1e-6)


def test_ebit_fallback_gross_minus_sga():
    rows = [r for r in _base_rows() if r["account_id"] != "dart_OperatingIncomeLoss"]
    res = normalize_year(rows, MAP)
    assert res["accounts"]["ebit"] == pytest.approx(60_000, abs=1e-6)  # 100,000 − 40,000
    assert any("영업이익" in w for w in res["warnings"])


def test_dna_combined_line():
    rows = _base_rows() + [
        _r("dart_DepreciationAndAmortisationExpense", "감가상각비및무형자산상각비", "CF", 12 * W)
    ]
    res = normalize_year(rows, MAP)
    assert res["accounts"]["dna"] == pytest.approx(12_000, abs=1e-6)
    assert "dna" not in res["unmapped"]


def test_dna_depreciation_plus_amortization():
    rows = _base_rows() + [
        _r("dart_DepreciationExpense", "감가상각비", "CF", 9 * W),
        _r("dart_AmortisationExpense", "무형자산상각비", "CF", 3 * W),
    ]
    res = normalize_year(rows, MAP)
    assert res["accounts"]["dna"] == pytest.approx(12_000, abs=1e-6)


def test_multiyear_normalize():
    raw = {2022: _base_rows(), 2023: _base_rows()}
    res = normalize(raw, MAP)
    assert res["years"] == [2022, 2023]
    assert res["accounts"][2023]["revenue"] == pytest.approx(300_000, abs=1e-6)
    assert res["unmapped"][2022] == ["dna"]
