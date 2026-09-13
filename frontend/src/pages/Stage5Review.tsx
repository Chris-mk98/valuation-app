import { useEffect, useState } from "react";
import { api, fmt } from "../api/client";
import { DCF_ASSUMPTION_LABELS, type CaseOut, type Stage5ReviewData } from "../types";

interface Props {
  caseData: CaseOut;
  locked: boolean;
  approved: boolean;
  onChanged: () => void;
}

export default function Stage5Review({ caseData, locked, approved, onChanged }: Props) {
  const [data, setData] = useState<Stage5ReviewData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setData(await api.reviewStage5(caseData.case_id));
      onChanged();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  useEffect(() => {
    if (!locked) load().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locked]);

  if (locked) {
    return (
      <section className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-400">
        Stage 5 · DCF — Stage 4 승인 후 잠금 해제됩니다.
      </section>
    );
  }

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      await api.runStage5(caseData.case_id);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function override(name: string, label: string, pct: boolean) {
    const cur = data?.assumptions[name]?.value ?? 0;
    const raw = window.prompt(`${label} 새 값${pct ? " (소수, 예: 0.05=5%)" : ""}:`, String(cur));
    if (raw === null) return;
    const value = Number(raw);
    if (Number.isNaN(value)) return setErr("숫자를 입력하세요.");
    const rationale = window.prompt("사유(필수):");
    if (!rationale) return;
    try {
      await api.overrideDcf(caseData.case_id, name, value, rationale);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function approve() {
    try {
      await api.approveStage(caseData.case_id, 5);
      onChanged();
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  const a = data?.assumptions ?? {};
  const r = data?.result;
  const hasData = Object.keys(a).length > 0;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">
          Stage 5 · 수익접근법(DCF)
          {r?.equity_value != null && (
            <span className="ml-2 text-sm font-normal text-emerald-700">
              주주가치 {fmt(r.equity_value)} 백만원
              {r.per_share != null && ` · 주당 ${fmt(r.per_share)}원`}
            </span>
          )}
        </h2>
        <div className="flex flex-wrap gap-2 text-sm">
          <button onClick={run} disabled={busy} className="rounded bg-slate-700 px-3 py-1 text-white disabled:opacity-50">
            {busy ? "산출 중…" : "DCF 산출"}
          </button>
          {hasData && (
            <a href={api.stage5DownloadUrl(caseData.case_id)} className="rounded border border-slate-300 px-3 py-1">
              DCF 다운로드
            </a>
          )}
          <button onClick={approve} disabled={approved || !hasData} className="rounded bg-emerald-600 px-3 py-1 text-white disabled:opacity-50">
            {approved ? "승인됨 ✓" : "검토 후 승인"}
          </button>
        </div>
      </div>

      {err && <p className="mb-2 text-sm text-red-600">{err}</p>}
      {(data?.warnings ?? []).length > 0 && (
        <div className="mb-2 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700">
          {data!.warnings.map((w, i) => (
            <div key={i}>⚠ {w}</div>
          ))}
        </div>
      )}

      {hasData && (
        <div className="grid gap-4 lg:grid-cols-2">
          {/* 예측 가정 */}
          <div>
            <h3 className="mb-1 text-sm font-medium text-slate-600">예측 가정</h3>
            <table className="w-full text-sm">
              <tbody>
                {DCF_ASSUMPTION_LABELS.map(({ key, label, pct }) => {
                  const cell = a[key];
                  if (!cell) return null;
                  const disp =
                    cell.value == null
                      ? "—"
                      : pct
                        ? `${(cell.value * 100).toFixed(2)}%`
                        : fmt(cell.value);
                  return (
                    <tr key={key} className="border-b border-slate-100">
                      <td className="py-1 text-slate-600">{label}</td>
                      <td className={`py-1 text-right ${cell.overridden ? "text-blue-700" : ""}`}>
                        {cell.overridden && <span title={cell.rationale ?? ""}>✎ </span>}
                        {disp}
                      </td>
                      <td className="w-14 py-1 text-right">
                        {!approved && cell.editable && (
                          <button onClick={() => override(key, label, pct)} className="text-[10px] text-blue-500 underline">
                            수정
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* FCFF 예측 */}
          <div className="overflow-x-auto">
            <h3 className="mb-1 text-sm font-medium text-slate-600">FCFF 예측 (백만원)</h3>
            <table className="w-full min-w-[360px] text-xs">
              <thead>
                <tr className="border-b text-right text-slate-500">
                  <th className="text-left">연차</th>
                  <th>매출</th>
                  <th>FCFF</th>
                  <th>현가</th>
                </tr>
              </thead>
              <tbody>
                {(r?.rows ?? []).map((row) => (
                  <tr key={row.t} className="border-b border-slate-100 text-right">
                    <td className="text-left">{row.t}년</td>
                    <td>{fmt(row.revenue)}</td>
                    <td>{fmt(row.fcff)}</td>
                    <td>{fmt(row.pv)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {r && (
              <div className="mt-2 space-y-0.5 text-xs text-slate-600">
                <div>현가합 {fmt(r.pv_sum)} · PV(TV) {fmt(r.pv_tv)}</div>
                <div>
                  EV {fmt(r.ev)} · TV비중{" "}
                  <span className={r.tv_ratio && r.tv_ratio > 0.7 ? "text-red-600" : ""}>
                    {r.tv_ratio != null ? `${(r.tv_ratio * 100).toFixed(0)}%` : "—"}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
