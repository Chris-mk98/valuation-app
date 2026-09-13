"""정적 파라미터 테이블 로더 (📄 다모다란·수동표). 값은 오버라이드 가능(lineage).

data/params/*.csv 를 읽는다. 각 값에 source·version 을 함께 반환해 lineage 에 남긴다.
"""

from __future__ import annotations

import csv
from functools import lru_cache

from app.config import DATA_DIR

PARAMS_DIR = DATA_DIR / "params"


def _read_csv(name: str) -> list[dict]:
    path = PARAMS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"파라미터 파일 없음: {path}")
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


@lru_cache
def get_erp(region: str = "KR") -> dict:
    """시장위험프리미엄(성숙시장) %. {value, source, version}."""
    for r in _read_csv("erp.csv"):
        if r["region"] == region:
            return {"value": float(r["erp_pct"]), "source": r["source"], "version": r["version"]}
    raise KeyError(f"ERP 미정의 region: {region}")


@lru_cache
def get_country_risk(region: str = "KR") -> dict:
    """국가위험프리미엄 %."""
    for r in _read_csv("country_risk.csv"):
        if r["region"] == region:
            return {"value": float(r["crp_pct"]), "source": r["source"], "version": r["version"]}
    raise KeyError(f"국가위험 미정의 region: {region}")


@lru_cache
def get_tax_rate(region: str = "KR") -> dict:
    """법인세율 % (WACC·언레버링에 사용)."""
    for r in _read_csv("tax_rates.csv"):
        if r["region"] == region:
            return {"value": float(r["rate_pct"]), "source": r["source"], "version": r["version"]}
    raise KeyError(f"세율 미정의 region: {region}")


@lru_cache
def get_size_premium(market_cap_mn: float) -> dict:
    """시가총액(백만원) 구간별 규모프리미엄 %. 상한이 비면 무한대로 취급."""
    for r in _read_csv("size_premium.csv"):
        lo = float(r["min_mktcap_mn"] or 0)
        hi = float(r["max_mktcap_mn"]) if r["max_mktcap_mn"] else float("inf")
        if lo <= market_cap_mn < hi:
            return {"value": float(r["premium_pct"]), "source": r["source"], "version": "manual"}
    return {"value": 0.0, "source": "규모프리미엄 구간 외", "version": "manual"}
