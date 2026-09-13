"""Stage 9 · 목적별 조정 & 리뷰 체크 (순수 함수, DB·HTTP 접근 금지).

방법론별 가치(수익·자산·시장)를 목적별 가중으로 종합하고 레드플래그를 평가한다
(docs/data_flow.md §9). 가중치·임계치는 core/rules 에서 로드해 인자로 주입받는다.
"""

from __future__ import annotations

METHOD_KEYS = ("income", "asset", "market")


def normalize_weights(weights: dict, values: dict) -> dict:
    """값이 있는 방법에 한해 가중치를 합=1 로 정규화."""
    usable = {k: (weights.get(k) or 0.0) for k in METHOD_KEYS
              if values.get(k) is not None and (weights.get(k) or 0.0) > 0}
    total = sum(usable.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in usable.items()}


def weighted_value(values: dict, weights: dict) -> float | None:
    """정규화 가중치로 가중평균. 가중치 없으면 None."""
    w = normalize_weights(weights, values)
    if not w:
        return None
    return sum(values[k] * w[k] for k in w)


def apply_net_asset_floor(final: float, asset_value: float | None, floor_ratio: float) -> float:
    """상증세법 순자산가치 하한: max(가중값, floor_ratio·순자산가치)."""
    if asset_value is None:
        return final
    return max(final, floor_ratio * asset_value)


def evaluate_flags(metrics: dict, thresholds: dict) -> list[dict]:
    """레드플래그 평가. 각 항목 {key, triggered, severity, description, value, threshold}."""
    flags: list[dict] = []

    def add(key, triggered, severity, desc, value, threshold):
        flags.append({"key": key, "triggered": bool(triggered), "severity": severity,
                      "description": desc, "value": value, "threshold": threshold})

    tvr = metrics.get("tv_ratio")
    if tvr is not None:
        thr = thresholds.get("tv_ratio_max", 0.70)
        add("tv_ratio", tvr > thr, "flag", f"TV 비중 > {thr*100:.0f}%", tvr, thr)

    tg, ng = metrics.get("terminal_growth"), metrics.get("nominal_gdp")
    if tg is not None and ng is not None:
        add("terminal_growth_vs_gdp", tg > ng, "flag", "영구성장률 > 명목GDP", tg, ng)

    fm, pk = metrics.get("forecast_margin"), metrics.get("historical_peak_margin")
    if fm is not None and pk is not None:
        add("forecast_margin_vs_peak", fm > pk, "flag", "예측 영업이익률 > 과거 최고", fm, pk)

    cr, dr = metrics.get("capex_ratio"), metrics.get("dna_ratio")
    if cr is not None and dr is not None:
        add("capex_below_dna", cr < dr, "warn", "CAPEX/매출 < D&A/매출", cr, dr)

    pc = metrics.get("peers_count")
    if pc is not None:
        thr = thresholds.get("peers_min", 5)
        add("peers_min", pc < thr, "warn", f"유사기업 < {thr}개", pc, thr)

    r2 = metrics.get("beta_r2_min")
    if r2 is not None:
        thr = thresholds.get("beta_r2_min", 0.10)
        add("beta_r2_min", r2 < thr, "warn", f"베타 회귀 R² < {thr}", r2, thr)

    return flags


def synthesize(values: dict, weights: dict, *, market_range: dict | None = None,
               net_asset_floor: float | None = None, parallel: bool = False) -> dict:
    """방법론 종합.

    parallel=True(손상검사): 가중 없이 사용가치(income)·공정가치(market) 병렬 + 회수가능액=max.
    아니면 가중평균(+선택적 순자산 하한).
    """
    if parallel:
        viu, fv = values.get("income"), values.get("market")
        recoverable = max([v for v in (viu, fv) if v is not None], default=None)
        return {"mode": "parallel", "value_in_use": viu, "fair_value": fv,
                "recoverable_amount": recoverable, "final": recoverable}

    final = weighted_value(values, weights)
    floored = final
    if final is not None and net_asset_floor is not None:
        floored = apply_net_asset_floor(final, values.get("asset"), net_asset_floor)
    return {"mode": "weighted", "weights": normalize_weights(weights, values),
            "weighted_value": final, "final": floored,
            "net_asset_floor_applied": floored != final if final is not None else False,
            "market_range": market_range}
