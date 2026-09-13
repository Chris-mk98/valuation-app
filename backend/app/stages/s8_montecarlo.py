"""Stage 8 · 몬테카를로 시뮬레이션 (순수 함수, DB·HTTP 접근 금지).

DCF 핵심 변수 6종에 정규분포를 부여하고 촐레스키 분해로 상관을 반영한 난수를 생성해
N회 DCF(주주가치)를 재계산, 분포 통계·토네이도 민감도를 산출한다(docs/data_flow.md §8).

변수: revenue_growth, ebit_margin, wacc, terminal_growth, capex_ratio, nwc_ratio (모두 소수)
"""

from __future__ import annotations

import numpy as np

from app.stages import s5_dcf

VARS = ["revenue_growth", "ebit_margin", "wacc", "terminal_growth", "capex_ratio", "nwc_ratio"]

# σ 기본값(소수). 사용자 오버라이드 가능.
DEFAULT_SIGMA = {
    "revenue_growth": 0.02, "ebit_margin": 0.02, "wacc": 0.01,
    "terminal_growth": 0.005, "capex_ratio": 0.02, "nwc_ratio": 0.02,
}

# 사전정의 상관(실무 사전분포). 대칭·PSD.
_CORR_PAIRS = {
    ("revenue_growth", "ebit_margin"): 0.3,
    ("revenue_growth", "terminal_growth"): 0.2,
    ("revenue_growth", "capex_ratio"): 0.3,
    ("ebit_margin", "wacc"): -0.2,
    ("capex_ratio", "nwc_ratio"): 0.2,
}


def default_corr_matrix() -> list[list[float]]:
    """6×6 사전정의 상관행렬."""
    n = len(VARS)
    m = np.eye(n)
    idx = {v: i for i, v in enumerate(VARS)}
    for (a, b), r in _CORR_PAIRS.items():
        i, j = idx[a], idx[b]
        m[i, j] = m[j, i] = r
    return m.tolist()


def _psd_cholesky(corr: np.ndarray) -> np.ndarray:
    """상관행렬의 촐레스키 인자. PSD 아니면 고유값 클리핑으로 보정."""
    try:
        return np.linalg.cholesky(corr)
    except np.linalg.LinAlgError:
        w, v = np.linalg.eigh(corr)
        w = np.clip(w, 1e-8, None)
        fixed = v @ np.diag(w) @ v.T
        d = np.sqrt(np.diag(fixed))
        fixed = fixed / np.outer(d, d)  # 단위 대각 재정규화
        return np.linalg.cholesky(fixed)


def build_dist_specs(base_assumptions: dict, sigma: dict | None = None) -> dict:
    """평균=Stage5 가정값, σ=기본(or 오버라이드)로 분포 스펙 구성."""
    sig = {**DEFAULT_SIGMA, **(sigma or {})}
    means = {"wacc": base_assumptions.get("wacc", 0.0), **base_assumptions}
    return {v: {"mean": float(means.get(v, 0.0)), "sigma": float(sig[v])} for v in VARS}


def _equity(history: list[dict], base: dict, sample: dict, *, net_debt: float,
            non_operating: float, shares: float | None) -> float | None:
    """단일 표본으로 DCF 주주가치. WACC ≤ 영구성장률 등 무효 표본은 None."""
    a = {**base,
         "revenue_growth": sample["revenue_growth"], "ebit_margin": sample["ebit_margin"],
         "terminal_growth": sample["terminal_growth"], "capex_ratio": sample["capex_ratio"],
         "nwc_ratio": sample["nwc_ratio"]}
    wacc = sample["wacc"]
    if wacc <= sample["terminal_growth"]:
        return None
    try:
        return s5_dcf.dcf_valuation(history, a, wacc=wacc, net_debt=net_debt,
                                    non_operating_assets=non_operating, shares=shares)["equity_value"]
    except (ValueError, ZeroDivisionError):
        return None


def simulate(history: list[dict], base_assumptions: dict, *, dist_specs: dict | None = None,
             corr: list[list[float]] | None = None, net_debt: float = 0.0,
             non_operating: float = 0.0, shares: float | None = None,
             n: int = 10_000, seed: int = 42) -> dict:
    """상관 정규난수로 N회 DCF 재계산 → 분포 통계 + 토네이도."""
    specs = dist_specs or build_dist_specs(base_assumptions)
    corr_m = np.array(corr if corr is not None else default_corr_matrix(), dtype=float)
    means = np.array([specs[v]["mean"] for v in VARS])
    sigmas = np.array([specs[v]["sigma"] for v in VARS])

    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n, len(VARS)))
    correlated = z @ _psd_cholesky(corr_m).T          # 상관 반영
    draws = means + correlated * sigmas               # 평균·표준편차 스케일

    values: list[float] = []
    for row in draws:
        sample = dict(zip(VARS, row, strict=True))
        v = _equity(history, base_assumptions, sample, net_debt=net_debt,
                    non_operating=non_operating, shares=shares)
        if v is not None:
            values.append(v)

    arr = np.array(values) if values else np.array([0.0])
    counts, edges = np.histogram(arr, bins=30)
    return {
        "n_valid": len(values),
        "n_total": n,
        "mean": float(arr.mean()),
        "median": float(np.median(arr)),
        "std": float(arr.std()),
        "p10": float(np.percentile(arr, 10)),
        "p50": float(np.percentile(arr, 50)),
        "p90": float(np.percentile(arr, 90)),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "histogram": {"counts": counts.tolist(), "edges": edges.tolist()},
        "tornado": _tornado(history, base_assumptions, specs, net_debt, non_operating, shares),
    }


def _tornado(history: list[dict], base: dict, specs: dict, net_debt: float,
             non_operating: float, shares: float | None) -> list[dict]:
    """각 변수를 ±1σ 로 움직였을 때(나머지 평균) 주주가치 스윙. |스윙| 내림차순."""
    base_sample = {v: specs[v]["mean"] for v in VARS}
    out = []
    for var in VARS:
        lo = {**base_sample, var: specs[var]["mean"] - specs[var]["sigma"]}
        hi = {**base_sample, var: specs[var]["mean"] + specs[var]["sigma"]}
        e_lo = _equity(history, base, lo, net_debt=net_debt, non_operating=non_operating,
                       shares=shares)
        e_hi = _equity(history, base, hi, net_debt=net_debt, non_operating=non_operating,
                       shares=shares)
        if e_lo is not None and e_hi is not None:
            out.append({"var": var, "low": e_lo, "high": e_hi, "swing": abs(e_hi - e_lo)})
    out.sort(key=lambda x: x["swing"], reverse=True)
    return out
