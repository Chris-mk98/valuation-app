"""Stage 6 · 시장접근법 (순수 함수, DB·HTTP 접근 금지).

유사기업 멀티플(EV/EBITDA·PER·PBR)을 산출하고 IQR(1.5×) 이상치를 제거한 뒤 중앙값을
대상회사 지표에 적용한다(docs/data_flow.md §6).

정의:
  유사기업 EV = 시가총액 + 순차입금
  EV/EBITDA = EV / EBITDA        (EBITDA=EBIT+D&A; D&A 결손 시 해당 peer 제외)
  PER       = 시가총액 / 당기순이익  (순이익>0)
  PBR       = 시가총액 / 순자산      (순자산>0)
적용:
  EV/EBITDA → 대상 EV = 배수·대상EBITDA → 주주가치 = 대상EV − 대상순차입금
  PER       → 주주가치 = 배수·대상순이익
  PBR       → 주주가치 = 배수·대상순자산
"""

from __future__ import annotations

import numpy as np

METHODS = ("ev_ebitda", "per", "pbr")


def peer_multiples(peer: dict) -> dict:
    """단일 유사기업의 멀티플. 산출 불가한 항목은 None."""
    mc = peer.get("market_cap")
    nd = peer.get("net_debt")
    ebitda = peer.get("ebitda")
    ni = peer.get("net_income")
    na = peer.get("net_asset")
    ev = (mc + nd) if (mc is not None and nd is not None) else None
    return {
        "ev_ebitda": (ev / ebitda) if (ev is not None and ebitda and ebitda > 0) else None,
        "per": (mc / ni) if (mc is not None and ni and ni > 0) else None,
        "pbr": (mc / na) if (mc is not None and na and na > 0) else None,
    }


def remove_outliers_iqr(values: list[float]) -> dict:
    """IQR(1.5×) 밖 값을 이상치로 분리. 반환 {kept, removed, lower, upper}."""
    vals = [v for v in values if v is not None]
    if len(vals) < 4:  # 표본 부족 시 이상치 제거 생략
        return {"kept": sorted(vals), "removed": [], "lower": None, "upper": None}
    arr = np.array(vals, dtype=float)
    q1, q3 = np.percentile(arr, 25), np.percentile(arr, 75)
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    kept = [v for v in vals if lo <= v <= hi]
    removed = [v for v in vals if v < lo or v > hi]
    return {"kept": sorted(kept), "removed": sorted(removed), "lower": float(lo), "upper": float(hi)}


def _median(vals: list[float]) -> float | None:
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    m = len(v)
    return v[m // 2] if m % 2 else (v[m // 2 - 1] + v[m // 2]) / 2.0


def summarize(values: list[float]) -> dict:
    """이상치 제거 후 중앙값·표본수·제거값."""
    o = remove_outliers_iqr(values)
    return {"median": _median(o["kept"]), "n": len(o["kept"]),
            "kept": o["kept"], "removed": o["removed"]}


def apply_to_target(reps: dict, target: dict) -> dict:
    """대표배수(reps: {method: median})를 대상 지표에 적용해 방법별 주주가치·주당가치."""
    ebitda = target.get("ebitda")
    ni = target.get("net_income")
    na = target.get("net_asset")
    nd = target.get("net_debt") or 0.0
    shares = target.get("shares")

    out: dict[str, dict] = {}
    m = reps.get("ev_ebitda")
    if m is not None and ebitda is not None:
        equity = m * ebitda - nd
        out["ev_ebitda"] = {"multiple": m, "implied_ev": m * ebitda, "equity_value": equity}
    m = reps.get("per")
    if m is not None and ni is not None:
        out["per"] = {"multiple": m, "equity_value": m * ni}
    m = reps.get("pbr")
    if m is not None and na is not None:
        out["pbr"] = {"multiple": m, "equity_value": m * na}

    for v in out.values():
        v["per_share"] = (v["equity_value"] * 1_000_000 / shares) if shares else None
    return out


def market_valuation(peers: list[dict], target: dict) -> dict:
    """유사기업 멀티플 산출 → 이상치 제거·중앙값 → 대상 적용 → 가치 범위."""
    peer_rows = []
    for p in peers:
        mult = peer_multiples(p)
        peer_rows.append({**{k: p.get(k) for k in
                             ("corp_name", "corp_code", "market_cap", "net_debt",
                              "ebitda", "net_income", "net_asset")}, **mult})

    summaries = {m: summarize([pr[m] for pr in peer_rows]) for m in METHODS}
    reps = {m: summaries[m]["median"] for m in METHODS}
    applied = apply_to_target(reps, target)

    equities = [v["equity_value"] for v in applied.values() if v.get("equity_value") is not None]
    value_range = {
        "min": min(equities) if equities else None,
        "median": _median(equities),
        "max": max(equities) if equities else None,
    }
    return {"peers": peer_rows, "summaries": summaries, "reps": reps,
            "applied": applied, "range": value_range}
