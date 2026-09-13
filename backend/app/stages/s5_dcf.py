"""Stage 5 · 수익접근법(DCF/FCFF) (순수 함수, DB·HTTP 접근 금지).

산식(docs/data_flow.md §5):
  FCFFₜ = EBITₜ·(1−t) + D&Aₜ − CAPEXₜ − ΔNWCₜ
  EBITₜ = 매출ₜ · 영업이익률,  D&Aₜ = 매출ₜ · (D&A/매출),  CAPEXₜ = 매출ₜ · (CAPEX/매출)
  NWCₜ  = 매출ₜ · (NWC/매출),  ΔNWCₜ = NWCₜ − NWCₜ₋₁
  PV    = Σ FCFFₜ / (1+WACC)ᵗ
  TV    = FCFFₙ·(1+g) / (WACC−g)   (고든 성장),  PV(TV) = TV / (1+WACC)ⁿ
  EV    = ΣPV + PV(TV)
  주주가치 = EV − 순차입금 + 비영업자산조정,   주당가치 = 주주가치 / 상장주식수

단위: 비율·성장률·WACC·세율은 소수(0.10, 0.087, 0.24). 금액은 백만원. 주당가치는 원.
"""

from __future__ import annotations


def _avg(vals: list[float]) -> float | None:
    v = [x for x in vals if x is not None]
    return sum(v) / len(v) if v else None


def historical_ratios(history: list[dict]) -> dict:
    """과거 재무에서 예측 기본값(비율) 산출.

    history: [{year, revenue, ebit, dna, capex, nwc}] (연도 오름차순)
    반환: {revenue_cagr, ebit_margin, dna_ratio, capex_ratio, nwc_ratio}
    """
    hist = [h for h in sorted(history, key=lambda x: x["year"]) if h.get("revenue")]
    if not hist:
        return {"revenue_cagr": None, "ebit_margin": None, "dna_ratio": None,
                "capex_ratio": None, "nwc_ratio": None}

    first, last = hist[0]["revenue"], hist[-1]["revenue"]
    periods = len(hist) - 1
    cagr = (last / first) ** (1.0 / periods) - 1.0 if periods > 0 and first > 0 else None

    def ratio(key: str) -> float | None:
        return _avg([h[key] / h["revenue"] for h in hist
                     if h.get(key) is not None and h.get("revenue")])

    return {
        "revenue_cagr": cagr,
        "ebit_margin": ratio("ebit"),
        "dna_ratio": ratio("dna"),
        "capex_ratio": ratio("capex"),
        "nwc_ratio": ratio("nwc"),
    }


def project_fcff(revenue0: float, nwc0: float, a: dict) -> list[dict]:
    """예측 가정 a 로 연도별 FCFF 시계열 생성.

    a: {forecast_years, revenue_growth, ebit_margin, dna_ratio, capex_ratio, nwc_ratio, tax}
    """
    years = int(a["forecast_years"])
    g = a["revenue_growth"]
    rows: list[dict] = []
    rev_prev, nwc_prev = revenue0, nwc0
    for t in range(1, years + 1):
        rev = rev_prev * (1.0 + g)
        ebit = rev * a["ebit_margin"]
        nopat = ebit * (1.0 - a["tax"])
        dna = rev * a["dna_ratio"]
        capex = rev * a["capex_ratio"]
        nwc = rev * a["nwc_ratio"]
        dnwc = nwc - nwc_prev
        fcff = nopat + dna - capex - dnwc
        rows.append({"t": t, "revenue": rev, "ebit": ebit, "nopat": nopat, "dna": dna,
                     "capex": capex, "nwc": nwc, "delta_nwc": dnwc, "fcff": fcff})
        rev_prev, nwc_prev = rev, nwc
    return rows


def terminal_value_gordon(fcff_n: float, g: float, wacc: float) -> float:
    """고든 성장 TV = FCFFₙ·(1+g)/(WACC−g). WACC ≤ g 이면 오류."""
    if wacc <= g:
        raise ValueError(f"WACC({wacc}) ≤ 영구성장률({g}) — TV 계산 불가")
    return fcff_n * (1.0 + g) / (wacc - g)


def dcf_valuation(history: list[dict], a: dict, *, wacc: float, net_debt: float,
                  non_operating_assets: float = 0.0, shares: float | None = None) -> dict:
    """전체 DCF 밸류에이션. 비율/성장/WACC/세율은 소수, 금액은 백만원.

    Returns: 연도별 FCFF·현가, TV·TV비중, EV, 주주가치, 주당가치(원).
    """
    hist = sorted(history, key=lambda x: x["year"])
    revenue0 = hist[-1]["revenue"]
    nwc0 = hist[-1].get("nwc") or 0.0

    rows = project_fcff(revenue0, nwc0, a)
    for r in rows:
        r["pv"] = r["fcff"] / (1.0 + wacc) ** r["t"]
    pv_sum = sum(r["pv"] for r in rows)

    n = len(rows)
    g = a["terminal_growth"]
    tv = terminal_value_gordon(rows[-1]["fcff"], g, wacc)
    pv_tv = tv / (1.0 + wacc) ** n
    ev = pv_sum + pv_tv
    equity = ev - net_debt + non_operating_assets
    per_share = (equity * 1_000_000 / shares) if shares else None

    return {
        "rows": rows,
        "pv_sum": pv_sum,
        "tv": tv,
        "pv_tv": pv_tv,
        "tv_ratio": pv_tv / ev if ev else None,
        "ev": ev,
        "equity_value": equity,
        "per_share": per_share,
    }
