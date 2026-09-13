import { useEffect, useState } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, fmt } from "../api/client";
import { MC_VAR_LABELS, type CaseOut, type Stage8ReviewData } from "../types";

interface Props {
  caseData: CaseOut;
  locked: boolean;
  approved: boolean;
  onChanged: () => void;
}

export default function Stage8Review({ caseData, locked, approved, onChanged }: Props) {
  const [data, setData] = useState<Stage8ReviewData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setData(await api.reviewStage8(caseData.case_id));
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
        Stage 8 · 몬테카를로 — Stage 5(DCF) 승인 후 잠금 해제됩니다.
      </section>
    );
  }

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      await api.runStage8(caseData.case_id);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function editSigma(v: string, label: string) {
    const cur = data?.distributions[v]?.sigma ?? 0;
    const raw = window.prompt(`${label} σ (소수, 예: 0.02):`, String(cur));
    if (raw === null) return;
    const sigma = Number(raw);
    if (Number.isNaN(sigma)) return setErr("숫자를 입력하세요.");
    const rationale = window.prompt("사유(필수):");
    if (!rationale) return;
    try {
      await api.overrideMcSigma(caseData.case_id, v, sigma, rationale);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function approve() {
    try {
      await api.approveStage(caseData.case_id, 8);
      onChanged();
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  const stats = data?.stats;
  const hasData = !!stats && stats.n_valid > 0;

  const histData =
    stats?.histogram?.counts.map((c, i) => {
      const lo = stats.histogram.edges[i];
      const hi = stats.histogram.edges[i + 1];
      return { mid: Math.round((lo + hi) / 2), count: c };
    }) ?? [];

  const maxSwing = Math.max(...(stats?.tornado ?? []).map((t) => t.swing), 1);

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">
          Stage 8 · 몬테카를로
          {stats && hasData && (
            <span className="ml-2 text-sm font-normal text-emerald-700">
              P50 {fmt(stats.p50)} (P10 {fmt(stats.p10)} ~ P90 {fmt(stats.p90)}) 백만원
            </span>
          )}
        </h2>
        <div className="flex flex-wrap gap-2 text-sm">
          <button onClick={run} disabled={busy} className="rounded bg-slate-700 px-3 py-1 text-white disabled:opacity-50">
            {busy ? "시뮬레이션 중…" : "시뮬레이션 실행"}
          </button>
          {hasData && (
            <a href={api.stage8DownloadUrl(caseData.case_id)} className="rounded border border-slate-300 px-3 py-1">
              결과 다운로드
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

      {hasData && stats && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <h3 className="mb-1 text-sm font-medium text-slate-600">
              주주가치 분포 (유효 {stats.n_valid.toLocaleString()}/{stats.n_total.toLocaleString()}회)
            </h3>
            <div className="h-56 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={histData}>
                  <XAxis dataKey="mid" tick={{ fontSize: 10 }} tickFormatter={(v) => fmt(v)} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip formatter={(v) => [v, "빈도"]} labelFormatter={(l) => `${fmt(Number(l))} 백만원`} />
                  <Bar dataKey="count" fill="#3b82f6" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-1 text-xs text-slate-500">
              평균 {fmt(stats.mean)} · 표준편차 {fmt(stats.std)} · 범위 {fmt(stats.min)}~{fmt(stats.max)}
            </div>
          </div>

          <div>
            <h3 className="mb-1 text-sm font-medium text-slate-600">토네이도 민감도 (±1σ 스윙)</h3>
            <table className="w-full text-xs">
              <tbody>
                {stats.tornado.map((t) => (
                  <tr key={t.var}>
                    <td className="w-24 py-1 text-slate-600">{MC_VAR_LABELS[t.var] ?? t.var}</td>
                    <td className="py-1">
                      <div className="h-3 rounded bg-blue-400" style={{ width: `${(t.swing / maxSwing) * 100}%` }} />
                    </td>
                    <td className="w-24 py-1 text-right text-slate-500">{fmt(t.swing)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <h3 className="mb-1 mt-3 text-sm font-medium text-slate-600">분포 파라미터 (σ)</h3>
            <table className="w-full text-xs">
              <tbody>
                {Object.entries(data!.distributions).map(([v, d]) => (
                  <tr key={v} className="border-b border-slate-100">
                    <td className="py-1 text-slate-600">{MC_VAR_LABELS[v] ?? v}</td>
                    <td className={`py-1 text-right ${d.overridden ? "text-blue-700" : ""}`}>
                      {d.overridden && "✎ "}σ={d.sigma}
                    </td>
                    <td className="w-12 py-1 text-right">
                      {!approved && (
                        <button onClick={() => editSigma(v, MC_VAR_LABELS[v] ?? v)} className="text-[10px] text-blue-500 underline">
                          수정
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
