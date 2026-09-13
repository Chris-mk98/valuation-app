"""Stage 3 유사기업 스크리닝 순수함수 — 필터 경계값 손검증."""

from __future__ import annotations

from app.stages.s3_peers import screen_peers

TARGET = {"corp_code": "A", "induty_code": "264", "revenue": 300_000}  # 백만원


def _cand(code, induty, rev, ni, years):
    return {"corp_code": code, "corp_name": code, "stock_code": code,
            "induty_code": induty, "revenue": rev, "net_income": ni,
            "years_reported": years, "market_cap": rev}


CANDIDATES = [
    _cand("B", "261", 200_000, 10_000, 3),      # 통과 (중분류26, 0.67x, 흑자, 3년)
    _cand("C", "264", 3_000_000, 50_000, 5),    # 규모 탈락 (10x > 5x)
    _cand("D", "264", 100_000, -5_000, 5),      # 흑자 탈락 (순손실)
    _cand("E", "331", 250_000, 8_000, 5),       # 업종 탈락 (중분류33)
    _cand("F", "262", 150_000, 4_000, 1),       # 상장연수 탈락 (1년)
    _cand("G", "26", 60_000, 2_000, 2),         # 통과 (경계 0.2x, 2년)
    _cand("A", "264", 300_000, 20_000, 5),      # 자기 자신 → 제외
]


def test_screen_passes_only_qualified():
    res = screen_peers(TARGET, CANDIDATES)
    passed = {r["corp_code"] for r in res["results"] if r["passed"]}
    assert passed == {"B", "G"}
    assert res["passed_count"] == 2
    # 자기 자신은 결과에서 제외
    assert all(r["corp_code"] != "A" for r in res["results"])


def test_filter_reasons_are_explicit():
    res = screen_peers(TARGET, CANDIDATES)
    by = {r["corp_code"]: r["filters"] for r in res["results"]}
    assert by["C"]["size"] is False and by["C"]["industry"] is True
    assert by["D"]["profit"] is False
    assert by["E"]["industry"] is False
    assert by["F"]["age"] is False


def test_size_boundaries_inclusive():
    # 0.2x(=60,000)와 5x(=1,500,000) 경계는 통과
    lo = _cand("LO", "264", 60_000, 1, 2)
    hi = _cand("HI", "264", 1_500_000, 1, 2)
    res = screen_peers(TARGET, [lo, hi])
    got = {r["corp_code"]: r["filters"]["size"] for r in res["results"]}
    assert got["LO"] is True and got["HI"] is True


def test_sorted_by_size_proximity():
    res = screen_peers(TARGET, CANDIDATES)
    codes = [r["corp_code"] for r in res["results"]]
    # B(200k, 가장 근접)가 G(60k)보다 앞
    assert codes.index("B") < codes.index("G")


def test_require_profit_toggle():
    res = screen_peers(TARGET, [_cand("D", "264", 100_000, -5_000, 5)],
                       criteria={"require_profit": False})
    assert res["results"][0]["passed"] is True
