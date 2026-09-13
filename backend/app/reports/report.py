"""평가 리포트 HTML 생성 (한글 안전·자체완결·브라우저 인쇄→PDF).

reportlab CJK 폰트 의존을 피하고, 인쇄 가능한 자체완결 HTML 로 리포트를 만든다.
풋볼필드는 인라인 막대로 렌더링한다.
"""

from __future__ import annotations

import html


def _fmt(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f}"


def _football_field_svg(ff: list[dict], final_value: float | None) -> str:
    vals = [x for f in ff for x in (f.get("low"), f.get("high")) if x is not None]
    if final_value is not None:
        vals.append(final_value)
    if not vals:
        return "<p>표시할 방법론 가치가 없습니다.</p>"
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    w = 640

    def x(v: float) -> float:
        return (v - lo) / span * w

    rows = []
    for f in ff:
        flo, fhi, fbase = f.get("low"), f.get("high"), f.get("base")
        if flo is None or fhi is None:
            continue
        x1, x2 = x(flo), x(fhi)
        bar_w = max(x2 - x1, 3)
        bx = x(fbase) if fbase is not None else x1
        rows.append(
            f'<div class="ffrow"><div class="fflabel">{html.escape(f["method"])}</div>'
            f'<div class=" fftrack" style="position:relative;height:22px;width:{w}px">'
            f'<div style="position:absolute;left:{x1:.0f}px;width:{bar_w:.0f}px;height:16px;'
            f'top:3px;background:#93c5fd;border-radius:3px"></div>'
            f'<div style="position:absolute;left:{bx:.0f}px;width:2px;height:22px;'
            f'background:#1d4ed8"></div></div>'
            f'<div class="ffval">{_fmt(flo)} ~ {_fmt(fhi)}</div></div>'
        )
    final_line = ""
    if final_value is not None:
        fx = x(final_value)
        final_line = (
            f'<div class="ffrow"><div class="fflabel"><b>최종</b></div>'
            f'<div style="position:relative;height:22px;width:{w}px">'
            f'<div style="position:absolute;left:{fx:.0f}px;width:3px;height:22px;'
            f'background:#dc2626"></div></div>'
            f'<div class="ffval"><b>{_fmt(final_value)}</b></div></div>'
        )
    return f'<div class="ff">{"".join(rows)}{final_line}</div>'


def render_report(case_json: dict, summary: dict) -> str:
    c = case_json.get("case", {})
    syn = (case_json.get("final_value") or {}).get("synthesis", {})
    flags = (case_json.get("final_value") or {}).get("flags", [])
    approvals = (case_json.get("final_value") or {}).get("flag_approvals", {})
    lineage = case_json.get("lineage", [])

    flag_rows = "".join(
        f'<tr class="{"trig" if f["triggered"] else ""}"><td>{html.escape(f["description"])}</td>'
        f'<td>{"발동" if f["triggered"] else "통과"}</td>'
        f'<td>{html.escape(f["severity"])}</td>'
        f'<td>{"승인" if f["key"] in approvals else ("검토필요" if f["triggered"] else "")}</td></tr>'
        for f in flags
    )
    override_rows = "".join(
        f'<tr><td>{html.escape(r["field_name"])}</td><td>{_fmt(r.get("system_value"))}</td>'
        f'<td>{_fmt(r.get("value"))}</td><td>{html.escape(r.get("rationale") or "")}</td>'
        f'<td>{html.escape(r.get("changed_by") or "")}</td></tr>'
        for r in lineage if r.get("source_type") == "EXPERT_OVERRIDE"
    ) or '<tr><td colspan="5">전문가 오버라이드 없음</td></tr>'

    src_counts: dict[str, int] = {}
    for r in lineage:
        src_counts[r["source_type"]] = src_counts.get(r["source_type"], 0) + 1
    src_summary = " · ".join(f"{k}: {v}" for k, v in sorted(src_counts.items()))

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>{html.escape(c.get('corp_name',''))} 가치평가 리포트</title>
<style>
  body {{ font-family: -apple-system, "Malgun Gothic", sans-serif; color:#1e293b;
          max-width: 820px; margin: 24px auto; padding: 0 16px; line-height:1.5; }}
  h1 {{ font-size: 22px; border-bottom:2px solid #1e293b; padding-bottom:6px; }}
  h2 {{ font-size: 16px; margin-top: 28px; color:#334155; }}
  table {{ border-collapse: collapse; width:100%; font-size:13px; margin-top:8px; }}
  th, td {{ border:1px solid #e2e8f0; padding:5px 8px; text-align:left; }}
  th {{ background:#f1f5f9; }}
  .meta td:first-child {{ width:140px; color:#64748b; }}
  .ffrow {{ display:flex; align-items:center; gap:10px; margin:4px 0; font-size:12px; }}
  .fflabel {{ width:110px; }} .ffval {{ color:#64748b; }}
  tr.trig td {{ background:#fef2f2; }}
  .final {{ font-size:20px; color:#059669; font-weight:700; }}
  @media print {{ body {{ margin:0; }} }}
</style></head><body>
<h1>{html.escape(c.get('corp_name',''))} 기업가치평가 리포트</h1>
<table class="meta">
  <tr><td>종목코드</td><td>{html.escape(c.get('stock_code') or '—')}</td></tr>
  <tr><td>평가기준일</td><td>{html.escape(c.get('valuation_date',''))}</td></tr>
  <tr><td>평가목적</td><td>{html.escape(summary.get('purpose_label') or '')}</td></tr>
  <tr><td>통화·단위</td><td>{html.escape(c.get('currency','KRW'))} · {html.escape(c.get('unit','백만원'))}</td></tr>
</table>

<h2>결론 — 최종 가치</h2>
<p class="final">{_fmt(summary.get('final_value'))} 백만원</p>
<p>종합방식: {html.escape(syn.get('mode') or '—')}</p>

<h2>방법론별 가치 범위 (풋볼필드)</h2>
{_football_field_svg(summary.get('football_field', []), summary.get('final_value'))}

<h2>리뷰 체크 (레드플래그)</h2>
<table><tr><th>항목</th><th>결과</th><th>심각도</th><th>승인</th></tr>{flag_rows}</table>

<h2>전문가 판단 적용 내역 (오버라이드)</h2>
<table><tr><th>항목</th><th>시스템값</th><th>적용값</th><th>사유</th><th>작성자</th></tr>{override_rows}</table>

<h2>데이터 출처 요약</h2>
<p>{html.escape(src_summary)}</p>
<p style="color:#94a3b8;font-size:12px;margin-top:24px">
  본 리포트는 내부 검토용이며, 모든 수치는 감사추적(lineage)에 출처가 기록되어 있습니다.
  브라우저 인쇄 기능으로 PDF 저장이 가능합니다.</p>
</body></html>"""
