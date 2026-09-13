import { useEffect, useState } from "react";
import { api, fmt } from "../api/client";
import type { CaseOut, LineageRow, SummaryData } from "../types";

interface Props {
  caseData: CaseOut;
  refreshKey: number;
}

const SRC_LABEL: Record<string, string> = {
  USER: "사용자",
  API: "API",
  PARAM_TABLE: "파라미터",
  DERIVED: "파생",
  EXPERT_OVERRIDE: "오버라이드",
  EXCEL_UPLOAD: "엑셀",
};

export default function Stage10Summary({ caseData, refreshKey }: Props) {
  const [data, setData] = useState<SummaryData | null>(null);
  const [lineage, setLineage] = useState<LineageRow[]>([]);
  const [showAudit, setShowAudit] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.getSummary(caseData.case_id).then(setData).catch((e) => setErr((e as Error).message));
  }, [caseData.case_id, refreshKey]);

  async function loadAudit() {
    setShowAudit((s) => !s);
    if (lineage.length === 0) {
      try {
        setLineage(await api.getLineage(caseData.case_id));
      } catch (e) {
        setErr((e as Error).message);
      }
    }
  }

  if (err) return <section className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-red-600">{err}</section>;
  if (!data) return null;

  const ff = data.football_field;
  const vals = [
    ...ff.flatMap((f) => [f.low, f.high]).filter((v): v is number => v != null),
    ...(data.final_value != null ? [data.final_value] : []),
  ];
  const lo = vals.length ? Math.min(...vals) : 0;
  const hi = vals.length ? Math.max(...vals) : 1;
  const span = hi - lo || 1;
  const pct = (v: number) => ((v - lo) / span) * 100;

  const triggered = data.flags.filter((f) => f.triggered);

  return (
    <section className="rounded-lg border border-slate-300 bg-white p-4 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">
          Stage 10 · 산출물
          {data.final_value != null && (
            <span className="ml-2 text-sm font-normal text-emerald-700">
              최종 가치 {fmt(data.final_value)} 백만원
            </span>
          )}
        </h2>
        <div className="flex flex-wrap gap-2 text-sm">
          <a href={api.reportUrl(caseData.case_id)} target="_blank" rel="noreferrer" className="rounded border border-slate-300 px-3 py-1">리포트(HTML)</a>
          <a href={api.workbookUrl(caseData.case_id)} className="rounded border border-slate-300 px-3 py-1">전체 워크북</a>
          <a href={api.lineageCsvUrl(caseData.case_id)} className="rounded border border-slate-300 px-3 py-1">감사추적 CSV</a>
          <a href={api.caseJsonUrl(caseData.case_id)} className="rounded border border-slate-300 px-3 py-1">케이스 JSON</a>
        </div>
      </div>

      {/* 풋볼필드 */}
      {ff.length > 0 ? (
        <div className="space-y-2">
          {ff.map((f) => (
            <div key={f.method} className="flex items-center gap-3 text-xs">
              <div className="w-28 text-slate-600">{f.method}</div>
              <div className="relative h-5 flex-1 rounded bg-slate-100">
                {f.low != null && f.high != null && (
                  <div className="absolute h-4 top-0.5 rounded bg-blue-300"
                       style={{ left: `${pct(f.low)}%`, width: `${Math.max(pct(f.high) - pct(f.low), 0.5)}%` }} />
                )}
                {f.base != null && (
                  <div className="absolute top-0 h-5 w-0.5 bg-blue-700" style={{ left: `${pct(f.base)}%` }} />
                )}
              </div>
              <div className="w-40 text-right text-slate-500">{fmt(f.low)} ~ {fmt(f.high)}</div>
            </div>
          ))}
          {data.final_value != null && (
            <div className="flex items-center gap-3 text-xs">
              <div className="w-28 font-semibold">최종</div>
              <div className="relative h-5 flex-1">
                <div className="absolute top-0 h-5 w-1 bg-red-600" style={{ left: `${pct(data.final_value)}%` }} />
              </div>
              <div className="w-40 text-right font-semibold">{fmt(data.final_value)}</div>
            </div>
          )}
        </div>
      ) : (
        <p className="text-sm text-slate-400">방법론 가치가 아직 없습니다(Stage 5~7 산출 필요).</p>
      )}

      {/* 레드플래그 요약 */}
      {triggered.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {triggered.map((f) => (
            <span key={f.key} className={`rounded px-2 py-0.5 text-[11px] ${
              data.flag_approvals[f.key] ? "bg-emerald-100 text-emerald-700"
                : f.severity === "flag" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"
            }`}>
              {f.description}{data.flag_approvals[f.key] ? " ✓" : ""}
            </span>
          ))}
        </div>
      )}

      <button onClick={loadAudit} className="mt-3 text-xs text-blue-500 underline">
        {showAudit ? "감사추적 접기" : "감사추적 보기"}
      </button>
      {showAudit && (
        <div className="mt-2 max-h-64 overflow-auto rounded border border-slate-100">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-slate-50">
              <tr className="text-left text-slate-500">
                <th className="p-1">항목</th><th>값</th><th>출처</th><th>사유</th>
              </tr>
            </thead>
            <tbody>
              {lineage.map((r, i) => (
                <tr key={i} className={`border-t border-slate-100 ${r.source_type === "EXPERT_OVERRIDE" ? "bg-blue-50/40" : ""}`}>
                  <td className="p-1 text-slate-600">{r.field_name}</td>
                  <td>{fmt(r.value)}</td>
                  <td>{SRC_LABEL[r.source_type] ?? r.source_type}</td>
                  <td className="max-w-[200px] truncate text-slate-400" title={r.rationale ?? ""}>{r.rationale ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
