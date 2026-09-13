"""ECOS(한국은행) 어댑터 — 기준일 국고채 10Y 수익률. 캐시 우선, 원본 보존.

통계표 817Y002(시장금리, 일별), 국고채(10년) 항목코드 010210000. (실측 확인)
"""

from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import ApiCallLog, RawEcos

BASE = "https://ecos.bok.or.kr/api"
STAT_GOV_BOND = "817Y002"
ITEM_GOV_BOND_10Y = "010210000"
CYCLE_DAILY = "D"
STAT_GDP = "200Y113"        # 국내총생산과 지출(명목, 연간)
ITEM_GDP = "10106"          # 국내총생산
CYCLE_ANNUAL = "A"


class EcosError(RuntimeError):
    """ECOS 응답 오류."""


def _client(client: httpx.Client | None) -> tuple[httpx.Client, bool]:
    if client is not None:
        return client, False
    return httpx.Client(timeout=30), True


def _log(db: Session, endpoint: str, status: str | None, message: str | None,
         cache_hit: bool) -> None:
    db.add(ApiCallLog(source="ECOS", endpoint=endpoint, params=None, status=status,
                      message=message, cache_hit=1 if cache_hit else 0))


def get_gov_bond_10y(
    db: Session,
    date: str,
    *,
    client: httpx.Client | None = None,
) -> float:
    """기준일(YYYY-MM-DD 또는 YYYYMMDD) 국고채 10년 수익률(%)을 반환. 캐시 우선.

    ECOS StatisticSearch 는 날짜를 YYYYMMDD 로 받는다. 해당일 데이터가 없으면 EcosError.
    """
    d = date.replace("-", "")
    cached = (
        db.query(RawEcos)
        .filter_by(stat_code=STAT_GOV_BOND, item_code=ITEM_GOV_BOND_10Y, cycle=CYCLE_DAILY, date=d)
        .one_or_none()
    )
    if cached is not None:
        _log(db, "StatisticSearch/817Y002", "OK", "cache", cache_hit=True)
        return float(cached.payload["value"])

    key = get_settings().ecos_api_key or ""
    url = (f"{BASE}/StatisticSearch/{key}/json/kr/1/1/"
           f"{STAT_GOV_BOND}/{CYCLE_DAILY}/{d}/{d}/{ITEM_GOV_BOND_10Y}")
    cl, owns = _client(client)
    try:
        data = cl.get(url).json()
    finally:
        if owns:
            cl.close()

    if "StatisticSearch" not in data:
        err = data.get("RESULT", {})
        _log(db, "StatisticSearch/817Y002", err.get("CODE"), err.get("MESSAGE"), cache_hit=False)
        raise EcosError(f"ECOS 오류: {err.get('CODE')} {err.get('MESSAGE')} (date={date})")

    rows = data["StatisticSearch"].get("row", [])
    if not rows:
        _log(db, "StatisticSearch/817Y002", "NO_DATA", f"no data for {d}", cache_hit=False)
        raise EcosError(f"국고채 10Y 데이터 없음: {date} (영업일 아님?)")

    value = float(rows[0]["DATA_VALUE"])
    _log(db, "StatisticSearch/817Y002", "OK", None, cache_hit=False)
    db.add(RawEcos(stat_code=STAT_GOV_BOND, item_code=ITEM_GOV_BOND_10Y, cycle=CYCLE_DAILY,
                   date=d, payload={"value": value, "raw": rows[0]}))
    return value


def get_nominal_gdp_growth(db: Session, as_of_year: int, *, window: int = 5,
                           client: httpx.Client | None = None) -> float:
    """최근 window년 명목GDP CAGR(소수). 영구성장률 상한·레드플래그 기준.

    200Y113/10106(연간 명목 국내총생산). 캐시 우선.
    """
    start = as_of_year - window
    date_key = f"{start}-{as_of_year}"
    cached = (db.query(RawEcos)
              .filter_by(stat_code=STAT_GDP, item_code=ITEM_GDP, cycle=CYCLE_ANNUAL, date=date_key)
              .one_or_none())
    if cached is not None:
        _log(db, "StatisticSearch/200Y113", "OK", "cache", cache_hit=True)
        return float(cached.payload["value"])

    key = get_settings().ecos_api_key or ""
    url = (f"{BASE}/StatisticSearch/{key}/json/kr/1/100/"
           f"{STAT_GDP}/{CYCLE_ANNUAL}/{start}/{as_of_year}/{ITEM_GDP}")
    cl, owns = _client(client)
    try:
        data = cl.get(url).json()
    finally:
        if owns:
            cl.close()
    if "StatisticSearch" not in data:
        err = data.get("RESULT", {})
        _log(db, "StatisticSearch/200Y113", err.get("CODE"), err.get("MESSAGE"), cache_hit=False)
        raise EcosError(f"명목GDP 조회 실패: {err.get('MESSAGE')}")
    rows = sorted(data["StatisticSearch"].get("row", []), key=lambda r: r["TIME"])
    vals = [float(r["DATA_VALUE"]) for r in rows if r.get("DATA_VALUE")]
    if len(vals) < 2:
        raise EcosError("명목GDP 표본 부족")
    periods = len(vals) - 1
    cagr = (vals[-1] / vals[0]) ** (1.0 / periods) - 1.0
    _log(db, "StatisticSearch/200Y113", "OK", None, cache_hit=False)
    db.add(RawEcos(stat_code=STAT_GDP, item_code=ITEM_GDP, cycle=CYCLE_ANNUAL, date=date_key,
                   payload={"value": cagr, "levels": vals}))
    return cagr
