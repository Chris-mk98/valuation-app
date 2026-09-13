"""Stage 2 · 정규화 — DART 표준계정 → 내부 계정 (순수 함수, DB·HTTP 접근 금지).

입력: DART fnlttSinglAcntAll 원본 행 리스트 + 계정 매핑 정의(dict)
출력: 내부계정 값(백만원) dict + 매핑 실패(unmapped) 리스트 + 경고

산식(docs/data_flow.md §2, 회계 판단 확정본):
  ebit      = 공시 영업이익 (없으면 gross_profit − sga 폴백)
  dna       = 감가상각비 + 무형자산상각비 (또는 결합 라인; 모두 없으면 unmapped)
  capex     = 유형자산의 취득 + 무형자산의 취득          (CF, 취득=양수)
  nwc       = (매출채권 + 재고자산 + 기타유동자산)
              − (매입채무 + 미지급비용 + 선수금 + 기타유동부채)   (영업운전자본; 현금·차입금 제외)
  net_debt  = (단기차입금 + 유동성장기부채 + 사채 + 장기차입금) − 현금및현금성자산
모든 금액은 원 → 백만원(÷unit_divisor)으로 환산해 float 로 반환.
"""

from __future__ import annotations

# 하위 Stage(WACC·DCF·시장접근) 진행에 반드시 필요한 내부계정
REQUIRED_ACCOUNTS = ["revenue", "ebit", "dna", "capex", "nwc", "net_debt", "nci"]

# 정규화 결과로 노출하는 내부계정(직접매핑)
_DIRECT_TARGETS = [
    "revenue", "cost_of_sales", "gross_profit", "sga", "ebit",
    "pretax_income", "tax_expense", "net_income", "interest_expense",
    "cash", "nci", "total_equity", "owners_equity",
]


def _parse_amount(raw: str | float | int | None, divisor: float) -> float | None:
    """DART 금액 문자열('69,080,893,000,000' 등)을 백만원 float 로. 빈값/'-'은 None."""
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "")
    if s in ("", "-", "—"):
        return None
    try:
        return float(s) / divisor
    except ValueError:
        return None


def _match(rows_by_stmt: dict[str, list[dict]], spec: dict, divisor: float) -> float | None:
    """매핑 스펙(statement + account_ids + account_names)에 맞는 첫 행의 금액을 반환."""
    stmt = spec.get("statement")
    # 손익 계정은 별도 손익계산서(IS) 또는 포괄손익계산서(CIS)에 올 수 있다.
    # 소형사는 CIS 한 장만 제출 → IS 스펙일 때 CIS 도 포함(IS 우선).
    if stmt == "IS":
        candidates = rows_by_stmt.get("IS", []) + rows_by_stmt.get("CIS", [])
    else:
        candidates = rows_by_stmt.get(stmt, [])
    ids = spec.get("account_ids") or []
    names = spec.get("account_names") or []
    # account_id 우선
    for aid in ids:
        for r in candidates:
            if (r.get("account_id") or "").strip() == aid:
                return _parse_amount(r.get("thstrm_amount"), divisor)
    # account_nm 폴백
    for nm in names:
        for r in candidates:
            if (r.get("account_nm") or "").strip() == nm:
                return _parse_amount(r.get("thstrm_amount"), divisor)
    return None


def _sum_present(values: list[float | None]) -> float | None:
    """None 이 아닌 값들의 합. 전부 None 이면 None."""
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def normalize_year(rows: list[dict], mapping: dict) -> dict:
    """단일 연도 원본 행 → 내부계정 dict.

    Returns:
        {"accounts": {internal: value|None}, "unmapped": [내부계정,...], "warnings": [str,...]}
    """
    divisor = float(mapping.get("unit_divisor", 1_000_000))
    targets = mapping.get("targets", {})
    components = mapping.get("components", {})
    dna_cands = mapping.get("dna_candidates", {})

    # 재무제표(sj_div)별 인덱싱
    rows_by_stmt: dict[str, list[dict]] = {}
    for r in rows:
        rows_by_stmt.setdefault(r.get("sj_div"), []).append(r)

    accounts: dict[str, float | None] = {}
    warnings: list[str] = []

    # 1) 직접 매핑
    for name in _DIRECT_TARGETS:
        spec = targets.get(name)
        accounts[name] = _match(rows_by_stmt, spec, divisor) if spec else None

    # 2) EBIT 폴백: 공시 영업이익 없으면 매출총이익 − 판관비
    if accounts.get("ebit") is None:
        gp, sga = accounts.get("gross_profit"), accounts.get("sga")
        if gp is not None and sga is not None:
            accounts["ebit"] = gp - sga
            warnings.append("ebit: 공시 영업이익 미검출 → 매출총이익−판관비로 산출")

    # 3) 합성용 원천
    comp = {name: _match(rows_by_stmt, spec, divisor) for name, spec in components.items()}

    # 4) CAPEX = 유형취득 + 무형취득
    accounts["capex"] = _sum_present([comp.get("purchase_ppe"), comp.get("purchase_intangible")])

    # 5) NWC = 영업운전자산 − 영업운전부채
    nwc_assets = _sum_present(
        [comp.get("trade_receivables"), comp.get("inventories"), comp.get("other_current_assets")]
    )
    nwc_liabs = _sum_present(
        [
            comp.get("trade_payables"),
            comp.get("accrued_expenses"),
            comp.get("advances_received"),
            comp.get("other_current_liabilities"),
        ]
    )
    if nwc_assets is None and nwc_liabs is None:
        accounts["nwc"] = None
    else:
        accounts["nwc"] = (nwc_assets or 0.0) - (nwc_liabs or 0.0)

    # 6) 순차입금 = 총차입금 − 현금및현금성자산
    borrowings = _sum_present(
        [
            comp.get("short_term_borrowings"),
            comp.get("current_lt_debt"),
            comp.get("bonds"),
            comp.get("long_term_borrowings"),
        ]
    )
    cash = accounts.get("cash")
    if borrowings is None and cash is None:
        accounts["net_debt"] = None
    else:
        accounts["net_debt"] = (borrowings or 0.0) - (cash or 0.0)
    # 총차입금(자본구조·Kd 산정용). net_debt 과 달리 현금 차감 전.
    accounts["gross_debt"] = borrowings

    # 7) D&A: 결합 라인 → 감가상각비(+무형상각) 순으로 시도
    combined = _match(rows_by_stmt, dna_cands.get("dna_combined", {}), divisor)
    if combined is not None:
        accounts["dna"] = combined
    else:
        dep = _match(rows_by_stmt, dna_cands.get("depreciation", {}), divisor)
        amort = _match(rows_by_stmt, dna_cands.get("amortization", {}), divisor)
        accounts["dna"] = _sum_present([dep, amort])
    if accounts["dna"] is None:
        warnings.append("dna: fnlttSinglAcntAll 에 감가상각비 라인 없음 → 사용자 입력 필요")

    # 8) 매핑 실패(필수 내부계정)
    unmapped = [name for name in REQUIRED_ACCOUNTS if accounts.get(name) is None]

    return {"accounts": accounts, "unmapped": unmapped, "warnings": warnings}


def normalize(raw_by_year: dict[int, list[dict]], mapping: dict) -> dict:
    """다연도 정규화. 연도별 normalize_year 를 합쳐 반환.

    Returns:
        {
          "years": [연도,...],
          "accounts": {연도: {내부계정: 값}},
          "unmapped": {연도: [내부계정,...]},
          "warnings": {연도: [str,...]},
        }
    """
    years = sorted(raw_by_year)
    accounts, unmapped, warnings = {}, {}, {}
    for y in years:
        res = normalize_year(raw_by_year[y], mapping)
        accounts[y] = res["accounts"]
        unmapped[y] = res["unmapped"]
        warnings[y] = res["warnings"]
    return {"years": years, "accounts": accounts, "unmapped": unmapped, "warnings": warnings}
