"""OpenDART 어댑터 (🌐 원본 보존, 캐시 우선).

규칙(CLAUDE.md): 외부 호출은 sources/ 에서만. 호출 전 캐시(raw_dart) 확인 → 미존재 시 호출 →
원본 저장 + api_call_log 기록. 인증키는 로그·저장에 남기지 않는다.

corp_code 해석: DART corpCode.zip(전체 상장/비상장사 목록)을 1회 내려받아
data/cache/corp_codes.json 으로 캐시하고 종목코드/회사명으로 검색한다.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy.orm import Session

from app.config import DATA_DIR, get_settings
from app.db.models import ApiCallLog, RawDart

BASE = "https://opendart.fss.or.kr/api"
REPRT_ANNUAL = "11011"  # 사업보고서
CORP_CODE_CACHE = DATA_DIR / "cache" / "corp_codes.json"


class DartError(RuntimeError):
    """DART 응답 오류(status != 000)."""


def _client(client: httpx.Client | None) -> tuple[httpx.Client, bool]:
    if client is not None:
        return client, False
    return httpx.Client(timeout=30), True


def _log(db: Session, endpoint: str, params: dict, status: str | None, message: str | None,
         cache_hit: bool) -> None:
    safe = {k: v for k, v in params.items() if k != "crtfc_key"}
    db.add(ApiCallLog(source="DART", endpoint=endpoint, params=safe, status=status,
                      message=message, cache_hit=1 if cache_hit else 0))


# --------------------------------------------------------------------------- #
# corp_code 해석
# --------------------------------------------------------------------------- #
def _load_corp_code_cache(cache_path: Path) -> list[dict] | None:
    if cache_path.exists():
        with cache_path.open(encoding="utf-8") as f:
            return json.load(f)
    return None


def _download_corp_codes(client: httpx.Client, key: str) -> list[dict]:
    """corpCode.zip → 파싱해 [{corp_code, corp_name, stock_code}] 리스트."""
    r = client.get(f"{BASE}/corpCode.xml", params={"crtfc_key": key})
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        xml = z.read(z.namelist()[0])
    root = ET.fromstring(xml)
    out = []
    for e in root.iter("list"):
        out.append({
            "corp_code": (e.findtext("corp_code") or "").strip(),
            "corp_name": (e.findtext("corp_name") or "").strip(),
            "stock_code": (e.findtext("stock_code") or "").strip(),
        })
    return out


def resolve_corp_code(
    query: str,
    *,
    db: Session | None = None,
    client: httpx.Client | None = None,
    cache_path: Path | None = None,
) -> dict:
    """회사명 또는 종목코드로 corp_code 를 찾는다. 상장사(종목코드 보유) 우선.

    Returns: {"corp_code", "corp_name", "stock_code"}  (미발견 시 DartError)
    """
    cache_path = cache_path or CORP_CODE_CACHE
    corps = _load_corp_code_cache(cache_path)
    if corps is None:
        cl, owns = _client(client)
        try:
            corps = _download_corp_codes(cl, get_settings().dart_api_key or "")
        finally:
            if owns:
                cl.close()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(corps, f, ensure_ascii=False)
        if db is not None:
            _log(db, "corpCode.xml", {}, "downloaded", f"{len(corps)} corps", cache_hit=False)

    q = query.strip()
    # 종목코드 6자리 정확 일치 우선
    listed = [c for c in corps if c["stock_code"]]
    for c in listed:
        if c["stock_code"] == q:
            return c
    # 회사명 정확 일치(상장 우선) → 부분 일치
    for pool in (listed, corps):
        for c in pool:
            if c["corp_name"] == q:
                return c
    for c in listed:
        if q and q in c["corp_name"]:
            return c
    raise DartError(f"corp_code 를 찾을 수 없습니다: {query!r}")


# --------------------------------------------------------------------------- #
# 기업개황 · 재무제표
# --------------------------------------------------------------------------- #
def _cached_raw(db: Session, corp_code: str, doc_type: str, bsns_year: str | None,
                reprt_code: str | None, fs_div: str | None) -> RawDart | None:
    return (
        db.query(RawDart)
        .filter_by(corp_code=corp_code, doc_type=doc_type, bsns_year=bsns_year,
                   reprt_code=reprt_code, fs_div=fs_div)
        .one_or_none()
    )


def get_company(db: Session, corp_code: str, *, client: httpx.Client | None = None) -> dict:
    """기업개황(업종코드·상장시장·결산월). 캐시 우선."""
    cached = _cached_raw(db, corp_code, "company", None, None, None)
    if cached is not None:
        _log(db, "company.json", {"corp_code": corp_code}, "000", "cache", cache_hit=True)
        return cached.payload

    key = get_settings().dart_api_key or ""
    cl, owns = _client(client)
    try:
        r = cl.get(f"{BASE}/company.json", params={"crtfc_key": key, "corp_code": corp_code})
        data = r.json()
    finally:
        if owns:
            cl.close()
    _log(db, "company.json", {"corp_code": corp_code}, data.get("status"),
         data.get("message"), cache_hit=False)
    if data.get("status") != "000":
        raise DartError(f"company.json status={data.get('status')} {data.get('message')}")
    db.add(RawDart(corp_code=corp_code, doc_type="company", payload=data))
    return data


def get_financials(
    db: Session,
    corp_code: str,
    bsns_year: str,
    *,
    reprt_code: str = REPRT_ANNUAL,
    fs_div: str = "CFS",
    client: httpx.Client | None = None,
) -> list[dict]:
    """단일 연도 전체 재무제표(fnlttSinglAcntAll) 행 리스트. 캐시 우선, 원본 보존."""
    cached = _cached_raw(db, corp_code, "financials", bsns_year, reprt_code, fs_div)
    if cached is not None:
        _log(db, "fnlttSinglAcntAll.json",
             {"corp_code": corp_code, "bsns_year": bsns_year, "reprt_code": reprt_code,
              "fs_div": fs_div}, "000", "cache", cache_hit=True)
        return cached.payload.get("list", [])

    key = get_settings().dart_api_key or ""
    params = {"crtfc_key": key, "corp_code": corp_code, "bsns_year": bsns_year,
              "reprt_code": reprt_code, "fs_div": fs_div}
    cl, owns = _client(client)
    try:
        r = cl.get(f"{BASE}/fnlttSinglAcntAll.json", params=params)
        data = r.json()
    finally:
        if owns:
            cl.close()
    _log(db, "fnlttSinglAcntAll.json",
         {k: v for k, v in params.items() if k != "crtfc_key"},
         data.get("status"), data.get("message"), cache_hit=False)
    if data.get("status") != "000":
        # 연결(CFS) 미제출 소형·별도제출 기업은 별도(OFS)만 존재 → 자동 폴백(013: 데이터 없음)
        if fs_div == "CFS" and data.get("status") == "013":
            return get_financials(db, corp_code, bsns_year, reprt_code=reprt_code,
                                  fs_div="OFS", client=client)
        raise DartError(
            f"fnlttSinglAcntAll status={data.get('status')} {data.get('message')} "
            f"(corp={corp_code}, year={bsns_year})"
        )
    db.add(RawDart(corp_code=corp_code, doc_type="financials", bsns_year=bsns_year,
                   reprt_code=reprt_code, fs_div=fs_div, payload=data))
    return data.get("list", [])


def get_financials_multi(
    db: Session,
    corp_code: str,
    years: list[int],
    *,
    reprt_code: str = REPRT_ANNUAL,
    fs_div: str = "CFS",
    client: httpx.Client | None = None,
) -> dict[int, list[dict]]:
    """복수 연도 재무제표. {year: rows}. 특정 연도 실패는 건너뛰고 계속."""
    out: dict[int, list[dict]] = {}
    for y in years:
        try:
            out[y] = get_financials(db, corp_code, str(y), reprt_code=reprt_code,
                                    fs_div=fs_div, client=client)
        except DartError:
            out[y] = []
    return out
