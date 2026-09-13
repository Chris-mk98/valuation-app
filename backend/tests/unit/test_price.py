"""sources/price 테스트 — 캐시·CSV 폴백(네트워크 없이). FDR 라이브 경로는 e2e 에서 검증."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.sources import price
from app.sources.price import PriceError

FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_get_listing_from_cache_fixture():
    rows = price.get_listing(cache_path=FIXTURES / "krx_listing.json")
    by = {r["code"]: r for r in rows}
    assert by["005930"]["name"] == "삼성전자"
    assert by["005930"]["listing_date"] == "1975-06-11"
    assert by["000660"]["sector"] == "반도체 제조업"


def test_get_ohlcv_csv_fallback_and_cache(db):
    csv = b"date,close\n2023-01-02,1000\n2023-01-09,1010\n2023-01-16,990\n"
    series = price.get_ohlcv(db, "005930", "2023-01-01", "2023-02-01", csv_bytes=csv)
    assert series == [
        {"date": "2023-01-02", "close": 1000.0},
        {"date": "2023-01-09", "close": 1010.0},
        {"date": "2023-01-16", "close": 990.0},
    ]
    # 두 번째 호출은 캐시(csv 없이도)
    again = price.get_ohlcv(db, "005930", "2023-01-01", "2023-02-01")
    assert again == series
    from app.db.models import RawPrice
    assert db.query(RawPrice).filter_by(code="005930").count() == 1


def test_csv_requires_date_close_header(db):
    with pytest.raises(PriceError):
        price.get_ohlcv(db, "X", "a", "b", csv_bytes=b"foo,bar\n1,2\n")
