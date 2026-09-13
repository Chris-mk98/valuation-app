"""Stage 3 · 유사기업 스크리닝 (순수 함수, DB·HTTP 접근 금지).

입력: 대상회사 지표 + 후보 리스트 + 필터 기준 → 후보별 필터 통과/탈락 결과.
필터(docs/data_flow.md §4):
  1) 업종: KSIC 중분류(induty_code 앞 2자리) 일치
  2) 규모: 매출이 대상의 size_low ~ size_high 배 이내
  3) 흑자: 최근 순이익 > 0
  4) 상장연수: 보고 연수 ≥ min_years (상장일 부재로 재무제표 존재 연수로 프록시)
자기 자신(target corp_code)은 후보에서 제외한다.
"""

from __future__ import annotations

import math

DEFAULT_CRITERIA = {
    "size_low": 0.2,
    "size_high": 5.0,
    "require_profit": True,
    "min_years": 2,
    "industry_digits": 2,  # KSIC 중분류
}


def _mid_code(induty_code: str | None, digits: int) -> str | None:
    if not induty_code:
        return None
    return str(induty_code).strip()[:digits]


def screen_peers(target: dict, candidates: list[dict], criteria: dict | None = None) -> dict:
    """후보군을 4개 필터로 평가.

    Args:
        target: {"corp_code", "induty_code", "revenue"(백만원)}
        candidates: [{"corp_code","corp_name","stock_code","induty_code",
                      "revenue","net_income","years_reported","market_cap"}]
        criteria: DEFAULT_CRITERIA 오버라이드

    Returns:
        {"criteria": {...}, "results": [{...후보..., "filters": {...}, "passed": bool}],
         "passed_count": int}
        결과는 규모 근접도(매출 로그거리) 오름차순 정렬.
    """
    crit = {**DEFAULT_CRITERIA, **(criteria or {})}
    digits = crit["industry_digits"]
    t_mid = _mid_code(target.get("induty_code"), digits)
    t_rev = target.get("revenue")

    results: list[dict] = []
    for c in candidates:
        if c.get("corp_code") == target.get("corp_code"):
            continue  # 자기 자신 제외

        industry_ok = t_mid is not None and _mid_code(c.get("induty_code"), digits) == t_mid

        rev = c.get("revenue")
        if t_rev and t_rev > 0 and rev is not None:
            size_ok = crit["size_low"] * t_rev <= rev <= crit["size_high"] * t_rev
        else:
            size_ok = False

        ni = c.get("net_income")
        profit_ok = (ni is not None and ni > 0) if crit["require_profit"] else True

        age_ok = (c.get("years_reported") or 0) >= crit["min_years"]

        filters = {"industry": industry_ok, "size": size_ok,
                   "profit": profit_ok, "age": age_ok}
        results.append({**c, "filters": filters, "passed": all(filters.values())})

    # 규모 근접도(매출 로그거리) 정렬
    def _proximity(item: dict) -> float:
        rev = item.get("revenue")
        if not t_rev or not rev or rev <= 0:
            return math.inf
        return abs(math.log(rev / t_rev))

    results.sort(key=_proximity)
    return {
        "criteria": crit,
        "results": results,
        "passed_count": sum(1 for r in results if r["passed"]),
    }
