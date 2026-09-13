"""KRX 주가 어댑터 (FinanceDataReader/pykrx). 캐시 우선, 원본 보존, CSV 폴백(§8).

- get_listing: 상장사 유니버스(종목·시장·시총·업종·상장일). 파일 캐시.
- get_ohlcv / get_index_ohlcv: 일별 종가. DB 캐시. 스크래핑 실패 시 CSV 폴백.
FDR/pykrx 는 import 시 부수효과가 있어 함수 내부에서 지연 import 한다.
"""

from __future__ import annotations

import io
import json
import math
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.db.models import ApiCallLog, RawPrice

LISTING_CACHE = DATA_DIR / "cache" / "krx_listing.json"


class PriceError(RuntimeError):
    """주가 조회 실패(스크래핑 차단 등)."""


def _log(db: Session | None, endpoint: str, status: str, cache_hit: bool) -> None:
    if db is not None:
        db.add(ApiCallLog(source="PRICE", endpoint=endpoint, params=None, status=status,
                          cache_hit=1 if cache_hit else 0))


# --------------------------------------------------------------------------- #
# 상장사 유니버스
# --------------------------------------------------------------------------- #
def get_listing(*, refresh: bool = False, cache_path: Path | None = None,
                db: Session | None = None) -> list[dict]:
    """상장사 목록 반환(파일 캐시).

    각 원소: {code, name, market, market_cap(원), shares, sector, industry, listing_date}
    """
    cache_path = cache_path or LISTING_CACHE
    if cache_path.exists() and not refresh:
        _log(db, "StockListing", "cache", cache_hit=True)
        with cache_path.open(encoding="utf-8") as f:
            return json.load(f)

    import FinanceDataReader as fdr

    krx = fdr.StockListing("KRX")          # Code,Name,Market,Marcap,Stocks,Close
    desc = fdr.StockListing("KRX-DESC")    # Code,Sector,Industry,ListingDate

    desc_by_code = {r["Code"]: r for r in desc.to_dict("records")}
    out: list[dict] = []
    for r in krx.to_dict("records"):
        code = r.get("Code")
        d = desc_by_code.get(code, {})
        ld = d.get("ListingDate")
        out.append({
            "code": code,
            "name": _clean(r.get("Name")),
            "market": _clean(r.get("Market")),
            "market_cap": _num(r.get("Marcap")),          # 원
            "shares": _num(r.get("Stocks")),
            # KRX-DESC 는 Sector 가 자주 비어 있고 Industry(업종명)가 채워짐 → industry 우선
            "sector": _clean(d.get("Sector")),
            "industry": _clean(d.get("Industry")),
            "listing_date": str(ld)[:10] if _clean(ld) is not None else None,
        })
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    _log(db, "StockListing", "ok", cache_hit=False)
    return out


def _num(v: object) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _clean(v: object) -> object | None:
    """pandas NaN → None 정규화."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


# --------------------------------------------------------------------------- #
# 주가/지수 시계열
# --------------------------------------------------------------------------- #
def _cached_series(db: Session, code: str, start: str, end: str, kind: str) -> list[dict] | None:
    row = (db.query(RawPrice)
           .filter_by(code=code, start=start, end=end, kind=kind).one_or_none())
    return row.payload if row else None


def get_ohlcv(db: Session, code: str, start: str, end: str, *,
              csv_bytes: bytes | None = None, kind: str = "ohlcv") -> list[dict]:
    """일별 종가 [{date, close}]. 캐시 우선. csv_bytes 제공 시 스크래핑 대신 CSV 사용(폴백).

    CSV 형식: 'date,close' 헤더 + 행. lineage source 는 CSV 로 기록.
    """
    cached = _cached_series(db, code, start, end, kind)
    if cached is not None:
        _log(db, f"DataReader/{code}", "cache", cache_hit=True)
        return cached

    if csv_bytes is not None:
        series = _parse_csv(csv_bytes)
        db.add(RawPrice(code=code, start=start, end=end, kind=kind, payload=series, source="CSV"))
        _log(db, f"DataReader/{code}", "csv", cache_hit=False)
        return series

    try:
        import FinanceDataReader as fdr
        df = fdr.DataReader(code, start, end)
    except Exception as e:  # noqa: BLE001 - 스크래핑 예외 폭넓게 폴백 유도
        _log(db, f"DataReader/{code}", "error", cache_hit=False)
        raise PriceError(f"주가 조회 실패({code}): {e}. CSV 업로드 폴백을 사용하세요.") from e

    series = [{"date": str(idx)[:10], "close": _num(row["Close"])}
              for idx, row in df.iterrows()]
    db.add(RawPrice(code=code, start=start, end=end, kind=kind, payload=series, source="FDR"))
    _log(db, f"DataReader/{code}", "ok", cache_hit=False)
    return series


def get_index_ohlcv(db: Session, start: str, end: str, *, index: str = "KS11") -> list[dict]:
    """지수 일별 종가(기본 KOSPI=KS11). 베타 회귀의 시장수익률."""
    return get_ohlcv(db, index, start, end, kind="index")


def _parse_csv(csv_bytes: bytes) -> list[dict]:
    import csv
    text = io.StringIO(csv_bytes.decode("utf-8-sig"))
    reader = csv.DictReader(text)
    cols = {c.lower(): c for c in (reader.fieldnames or [])}
    if "date" not in cols or "close" not in cols:
        raise PriceError("CSV 는 'date,close' 헤더가 필요합니다.")
    out = []
    for row in reader:
        out.append({"date": str(row[cols["date"]])[:10], "close": _num(row[cols["close"]])})
    return out
