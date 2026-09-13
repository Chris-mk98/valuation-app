"""Stage별 Excel 다운로드 (openpyxl). 모든 Stage 결과는 다운로드 가능(CLAUDE.md 원칙 3).

- stage1_raw_dump: DART 원본 재무 덤프(연도별 시트)
- stage2_normalized: 정규화 재무(연도 × 내부계정 매트릭스)
"""

from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Font

from app.stages.s2_normalize import REQUIRED_ACCOUNTS

_HEADER = Font(bold=True)


def _to_bytes(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def stage1_raw_dump(raw_by_year: dict[int, list[dict]]) -> bytes:
    """연도별 시트에 원본 계정(sj_div, account_id, account_nm, 당기금액)을 덤프."""
    wb = Workbook()
    wb.remove(wb.active)
    for year in sorted(raw_by_year):
        ws = wb.create_sheet(title=str(year))
        ws.append(["sj_div", "account_id", "account_nm", "thstrm_amount"])
        for c in ws[1]:
            c.font = _HEADER
        for r in raw_by_year[year]:
            ws.append([
                r.get("sj_div"), r.get("account_id"), r.get("account_nm"),
                r.get("thstrm_amount"),
            ])
    if not wb.sheetnames:  # 빈 입력 방어
        wb.create_sheet(title="empty")
    return _to_bytes(wb)


def stage2_normalized(normalized: dict) -> bytes:
    """정규화 결과(연도 × 내부계정). 값은 백만원. 미분류·경고는 별도 시트."""
    wb = Workbook()
    ws = wb.active
    ws.title = "정규화재무(백만원)"
    years = normalized.get("years", [])
    accounts = normalized.get("accounts", {})

    # 계정 순서: 필수계정 우선 + 나머지
    ordered: list[str] = list(REQUIRED_ACCOUNTS)
    for y in years:
        for k in accounts.get(y, {}):
            if k not in ordered:
                ordered.append(k)

    ws.append(["account", *[str(y) for y in years]])
    for c in ws[1]:
        c.font = _HEADER
    for acc in ordered:
        ws.append([acc, *[accounts.get(y, {}).get(acc) for y in years]])

    # 미분류 시트
    ws2 = wb.create_sheet(title="미분류·경고")
    ws2.append(["year", "unmapped", "warnings"])
    for c in ws2[1]:
        c.font = _HEADER
    for y in years:
        ws2.append([
            y,
            ", ".join(normalized.get("unmapped", {}).get(y, [])),
            " / ".join(normalized.get("warnings", {}).get(y, [])),
        ])
    return _to_bytes(wb)


_WACC_LABEL_KR = {
    "rf": "무위험이자율 Rf(%)", "beta_u_median": "언레버 베타(중앙값)",
    "target_de": "목표 D/E", "beta_relevered": "리레버 베타",
    "erp": "시장위험프리미엄 ERP(%)", "country_risk": "국가위험(%)",
    "size_premium": "규모프리미엄(%)", "ke": "자기자본비용 Ke(%)",
    "kd": "타인자본비용 Kd(%)", "tax_rate": "법인세율(%)",
    "equity_value": "자기자본가치(백만원)", "debt_value": "타인자본가치(백만원)",
    "wacc": "WACC(%)",
}


def stage4_wacc(components: dict) -> bytes:
    """WACC 빌드업(구성요소별 값·출처·오버라이드 여부)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "WACC빌드업"
    ws.append(["구성요소", "값", "출처", "오버라이드", "사유"])
    for c in ws[1]:
        c.font = _HEADER
    for key, label in _WACC_LABEL_KR.items():
        cell = components.get(key)
        if not cell:
            continue
        ws.append([label, cell.get("value"), cell.get("source_ref"),
                   "Y" if cell.get("overridden") else "", cell.get("rationale") or ""])
    return _to_bytes(wb)


def stage5_dcf(review: dict) -> bytes:
    """DCF 예측 가정 + 연도별 FCFF·현가 + 요약(EV·주주가치·주당가치)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "예측가정"
    ws.append(["가정", "값", "출처", "오버라이드", "사유"])
    for c in ws[1]:
        c.font = _HEADER
    for name, cell in (review.get("assumptions") or {}).items():
        ws.append([name, cell.get("value"), cell.get("source_ref"),
                   "Y" if cell.get("overridden") else "", cell.get("rationale") or ""])

    ws2 = wb.create_sheet("DCF")
    ws2.append(["연차", "매출", "EBIT", "NOPAT", "D&A", "CAPEX", "ΔNWC", "FCFF", "현가PV"])
    for c in ws2[1]:
        c.font = _HEADER
    result = review.get("result") or {}
    for r in result.get("rows", []):
        ws2.append([r.get("t"), r.get("revenue"), r.get("ebit"), r.get("nopat"), r.get("dna"),
                    r.get("capex"), r.get("delta_nwc"), r.get("fcff"), r.get("pv")])
    ws2.append([])
    for label, key in [("현가합", "pv_sum"), ("TV", "tv"), ("PV(TV)", "pv_tv"),
                       ("TV비중", "tv_ratio"), ("EV", "ev"),
                       ("주주가치", "equity_value"), ("주당가치(원)", "per_share")]:
        ws2.append([label, result.get(key)])
    return _to_bytes(wb)


def stage6_multiples(review: dict) -> bytes:
    """유사기업 멀티플 테이블 + 적용가치 요약."""
    wb = Workbook()
    ws = wb.active
    ws.title = "멀티플"
    ws.append(["회사", "시총", "순차입금", "EBITDA", "순이익", "순자산",
               "EV/EBITDA", "PER", "PBR"])
    for c in ws[1]:
        c.font = _HEADER
    for p in review.get("peers", []):
        ws.append([p.get("corp_name"), p.get("market_cap"), p.get("net_debt"), p.get("ebitda"),
                   p.get("net_income"), p.get("net_asset"),
                   p.get("ev_ebitda"), p.get("per"), p.get("pbr")])

    ws2 = wb.create_sheet("적용가치")
    ws2.append(["방법", "대표배수", "오버라이드", "주주가치(백만원)", "주당가치(원)"])
    for c in ws2[1]:
        c.font = _HEADER
    reps = review.get("reps", {})
    applied = review.get("applied", {})
    for m, label in [("ev_ebitda", "EV/EBITDA"), ("per", "PER"), ("pbr", "PBR")]:
        rep = reps.get(m, {})
        ap = applied.get(m, {})
        ws2.append([label, rep.get("value"), "Y" if rep.get("overridden") else "",
                    ap.get("equity_value"), ap.get("per_share")])
    rng = review.get("range", {})
    ws2.append([])
    ws2.append(["가치범위(백만원)", rng.get("min"), rng.get("median"), rng.get("max")])
    return _to_bytes(wb)


def stage7_asset(review: dict) -> bytes:
    """자산접근: 장부순자산·조정내역·할증·조정순자산가치."""
    wb = Workbook()
    ws = wb.active
    ws.title = "조정순자산"
    r = review.get("result", {})
    ws.append(["항목", "금액(백만원)", "사유"])
    for c in ws[1]:
        c.font = _HEADER
    ws.append(["장부 순자산(지배주주지분)", r.get("book_equity"), ""])
    for a in r.get("adjustments", []):
        ws.append([a.get("label"), a.get("amount"), a.get("rationale")])
    ws.append(["조정합계", r.get("adjustments_total"), ""])
    ws.append(["조정순자산", r.get("adjusted_net_asset"), ""])
    ws.append(["최대주주 할증률", r.get("control_premium_rate"), ""])
    ws.append(["조정순자산가치(할증후)", r.get("value_with_premium"), ""])
    ws.append(["주당가치(원)", r.get("per_share"), ""])
    return _to_bytes(wb)


def adjustments_template() -> bytes:
    """자산조정 항목 업로드 템플릿."""
    wb = Workbook()
    ws = wb.active
    ws.title = "adjustments"
    ws.append(["label", "amount", "rationale"])
    for c in ws[1]:
        c.font = _HEADER
    ws.append(["예: 투자부동산 시가조정", 30000, "감정평가 반영"])
    ws.append(["예: 소송충당부채", -5000, "계류 소송 반영"])
    g = wb.create_sheet("설명")
    g.append(["amount 는 백만원(자산가산 +, 부채/차감 −). rationale 필수."])
    return _to_bytes(wb)


def transactions_template() -> bytes:
    """거래사례(M&A 배수) 업로드 템플릿."""
    wb = Workbook()
    ws = wb.active
    ws.title = "transactions"
    ws.append(["target_name", "deal_ev", "ebitda", "multiple"])
    for c in ws[1]:
        c.font = _HEADER
    ws.append(["예: OO기업 인수", 500000, 50000, ""])  # multiple 비우면 deal_ev/ebitda 자동
    g = wb.create_sheet("설명")
    g.append(["deal_ev·ebitda 는 백만원. multiple 비우면 deal_ev/ebitda 로 자동 계산."])
    return _to_bytes(wb)


def stage8_montecarlo(review: dict) -> bytes:
    """몬테카를로: 분포 파라미터·통계·토네이도·히스토그램."""
    wb = Workbook()
    ws = wb.active
    ws.title = "분포설정"
    ws.append(["변수", "평균", "σ", "오버라이드"])
    for c in ws[1]:
        c.font = _HEADER
    for var, d in (review.get("distributions") or {}).items():
        ws.append([var, d.get("mean"), d.get("sigma"), "Y" if d.get("overridden") else ""])

    stats = review.get("stats", {})
    ws2 = wb.create_sheet("통계")
    ws2.append(["지표", "값(백만원)"])
    for c in ws2[1]:
        c.font = _HEADER
    for label, key in [("유효표본", "n_valid"), ("평균", "mean"), ("중앙값(P50)", "p50"),
                       ("표준편차", "std"), ("P10", "p10"), ("P90", "p90"),
                       ("최소", "min"), ("최대", "max")]:
        ws2.append([label, stats.get(key)])

    ws3 = wb.create_sheet("토네이도")
    ws3.append(["변수", "-1σ", "+1σ", "스윙"])
    for c in ws3[1]:
        c.font = _HEADER
    for t in stats.get("tornado", []):
        ws3.append([t.get("var"), t.get("low"), t.get("high"), t.get("swing")])
    return _to_bytes(wb)


def full_workbook(case_json: dict, summary: dict) -> bytes:
    """전체 계산 워크북 — 요약·정규화·유사기업·WACC·DCF·멀티플·순자산·MC·최종·감사추적."""
    wb = Workbook()
    ws = wb.active
    ws.title = "요약"
    c = case_json.get("case", {})
    ws.append(["대상회사", c.get("corp_name")])
    ws.append(["기준일", c.get("valuation_date")])
    ws.append(["평가목적", summary.get("purpose_label")])
    ws.append(["최종가치(백만원)", summary.get("final_value")])
    ws.append([])
    ws.append(["방법", "low", "base", "high"])
    for f in summary.get("football_field", []):
        ws.append([f["method"], f.get("low"), f.get("base"), f.get("high")])

    # 정규화재무 매트릭스
    fin = case_json.get("financials_normalized", [])
    years = sorted({f["year"] for f in fin})
    accts: dict[str, dict] = {}
    for f in fin:
        accts.setdefault(f["account"], {})[f["year"]] = f["value"]
    wsf = wb.create_sheet("정규화재무")
    wsf.append(["account", *[str(y) for y in years]])
    for acc, byyear in accts.items():
        wsf.append([acc, *[byyear.get(y) for y in years]])

    wsp = wb.create_sheet("유사기업")
    wsp.append(["회사", "포함", "출처", "사유"])
    for p in case_json.get("peers", []):
        wsp.append([p.get("corp_name"), p.get("included"), p.get("source"), p.get("rationale")])

    wsw = wb.create_sheet("WACC")
    wsw.append(["구성요소", "값"])
    for k, v in (case_json.get("wacc") or {}).items():
        wsw.append([k, v])

    wsd = wb.create_sheet("DCF")
    dcf = case_json.get("dcf_result") or {}
    wsd.append(["연차", "매출", "FCFF", "현가"])
    for r in dcf.get("rows", []):
        wsd.append([r.get("t"), r.get("revenue"), r.get("fcff"), r.get("pv")])
    for label, key in [("EV", "ev"), ("주주가치", "equity_value"), ("주당가치", "per_share")]:
        wsd.append([label, dcf.get(key)])

    wsm = wb.create_sheet("멀티플")
    mkt = case_json.get("market_result") or {}
    wsm.append(["회사", "EV/EBITDA", "PER", "PBR"])
    for p in mkt.get("peers", []):
        wsm.append([p.get("corp_name"), p.get("ev_ebitda"), p.get("per"), p.get("pbr")])

    wsa = wb.create_sheet("순자산")
    asset = case_json.get("asset_result") or {}
    wsa.append(["항목", "값"])
    wsa.append(["조정순자산", asset.get("adjusted_net_asset")])
    wsa.append(["조정순자산가치", asset.get("value_with_premium")])

    wsmc = wb.create_sheet("몬테카를로")
    mc = case_json.get("mc_result") or {}
    for label, key in [("평균", "mean"), ("P10", "p10"), ("P50", "p50"), ("P90", "p90")]:
        wsmc.append([label, mc.get(key)])

    wsfin = wb.create_sheet("최종")
    final = case_json.get("final_value") or {}
    syn = final.get("synthesis", {})
    wsfin.append(["종합방식", syn.get("mode")])
    wsfin.append(["최종가치", syn.get("final")])
    wsfin.append([])
    wsfin.append(["레드플래그", "발동", "심각도"])
    for fl in final.get("flags", []):
        wsfin.append([fl.get("description"), "Y" if fl.get("triggered") else "", fl.get("severity")])

    wsl = wb.create_sheet("감사추적")
    wsl.append(["field", "value", "source_type", "source_ref", "rationale", "changed_by"])
    for row in case_json.get("lineage", []):
        wsl.append([row.get("field_name"), row.get("value"), row.get("source_type"),
                    row.get("source_ref"), row.get("rationale"), row.get("changed_by")])
    return _to_bytes(wb)


def stage9_final(payload: dict) -> bytes:
    """목적별 종합: 방법론 가치·가중·최종·레드플래그."""
    wb = Workbook()
    ws = wb.active
    ws.title = "방법론가치"
    ws.append(["방법", "가치(백만원)"])
    for c in ws[1]:
        c.font = _HEADER
    mv = payload.get("method_values", {})
    for k, label in [("income", "수익가치(DCF)"), ("asset", "자산가치"), ("market", "시장가치")]:
        ws.append([label, mv.get(k)])
    syn = payload.get("synthesis", {})
    ws.append([])
    ws.append(["종합방식", syn.get("mode")])
    if syn.get("mode") == "parallel":
        ws.append(["사용가치(DCF)", syn.get("value_in_use")])
        ws.append(["공정가치(시장)", syn.get("fair_value")])
        ws.append(["회수가능액", syn.get("recoverable_amount")])
    else:
        ws.append(["가중치", str(syn.get("weights"))])
        ws.append(["최종가치", syn.get("final")])

    ws2 = wb.create_sheet("레드플래그")
    ws2.append(["항목", "심각도", "발동", "값", "임계치", "승인"])
    for c in ws2[1]:
        c.font = _HEADER
    approvals = payload.get("flag_approvals", {})
    for f in payload.get("flags", []):
        ws2.append([f.get("description"), f.get("severity"),
                    "Y" if f.get("triggered") else "", f.get("value"), f.get("threshold"),
                    "승인" if f.get("key") in approvals else ""])
    return _to_bytes(wb)


def stage3_candidates(peers: list[dict]) -> bytes:
    """유사기업 후보 리스트(필터 통과 여부·지표·포함사유)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "유사기업후보"
    cols = ["corp_code", "corp_name", "stock_code", "induty_code", "sector",
            "매출(백만원)", "순이익(백만원)", "시총(백만원)", "상장연수",
            "업종", "규모", "흑자", "상장연수통과", "passed", "included", "source", "사유"]
    ws.append(cols)
    for c in ws[1]:
        c.font = _HEADER
    for p in peers:
        m = p.get("metrics") or {}
        f = m.get("filters") or {}
        ws.append([
            p.get("corp_code"), p.get("corp_name"), p.get("stock_code"),
            m.get("induty_code"), m.get("sector"),
            m.get("revenue"), m.get("net_income"), m.get("market_cap"), m.get("years_reported"),
            f.get("industry"), f.get("size"), f.get("profit"), f.get("age"),
            m.get("passed"), p.get("included"), p.get("source"), p.get("rationale"),
        ])
    return _to_bytes(wb)
