import { useEffect, useState } from "react";
import { api, fmt } from "../api/client";
import { METHOD_LABELS, type CaseOut, type Stage9ReviewData } from "../types";

interface Props {
  caseData: CaseOut;
  locked: boolean;
  approved: boolean;
  onChanged: () => void;
}

export default function Stage9Review({ caseData, locked, approved, onChanged }: Props) {
  const [data, setData] = useState<Stage9ReviewData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setData(await api.reviewStage9(caseData.case_id));
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
        Stage 9 · 목적별 조정·리뷰 — Stage 5(DCF) 승인 후 잠금 해제됩니다.
      </section>
    );
  }

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      await api.runStage9(caseData.case_id);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function editWeight(method: string, label: string) {
    const raw = window.prompt(`${label} 가중치(상대값):`);
    if (raw === null) return;
    const value = Number(raw);
    if (Number.isNaN(value)) return setErr("숫자를 입력하세요.");
    const rationale = window.prompt("사유(필수):");
    if (!rationale) return;
    try {
      await api.overrideWeight(caseData.case_id, method, value, rationale);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function ack(key: string) {
    const note = window.prompt("플래그 검토 의견(필수):");
    if (!note) return;
    try {
      await api.ackFlag(caseData.case_id, key, note);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function approve() {
    try {
      await api.approveStage(caseData.case_id, 9);
      onChanged();
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  const fin = data?.final;
  const hasData = !!fin && !!fin.synthesis;
  const syn = fin?.synthesis;
  const flags = fin?.flags ?? [];
  const approvals = fin?.flag_approvals ?? {};
  const pending = flags.filter((f) => f.triggered && !approvals[f.key]);

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">
          Stage 9 · 목적별 조정·리뷰
          {fin?.purpose_label && <span className="ml-2 text-sm font-normal text-slate-500">{fin.purpose_label}</span>}
          {syn?.final != null && <span className="ml-2 text-sm font-normal text-emerald-700">최종 {fmt(syn.final)} 백만원</span>}
        </h2>
        <div className="flex flex-wrap gap-2 text-sm">
          <button onClick={run} disabled={busy} className="rounded bg-slate-700 px-3 py-1 text-white disabled:opacity-50">
            {busy ? "종합 중…" : "종합 산출"}
          </button>
          {hasData && (
            <a href={api.stage9DownloadUrl(caseData.case_id)} className="rounded border border-slate-300 px-3 py-1">
              최종요약 다운로드
            </a>
          )}
          <button onClick={approve} disabled={approved || !hasData || pending.length > 0}
                  title={pending.length > 0 ? "레드플래그 승인 필요" : ""}
                  className="rounded bg-emerald-600 px-3 py-1 text-white disabled:opacity-50">
            {approved ? "승인됨 ✓" : "검토 후 승인"}
          </button>
        </div>
      </div>

      {err && <p className="mb-2 text-sm text-red-600">{err}</p>}

      {hasData && fin && syn && (
        <div className="grid gap-4 lg:grid-cols-2">
          {/* 방법론별 가치 + 종합 */}
          <div>
            <h3 className="mb-1 text-sm font-medium text-slate-600">방법론별 가치 (백만원)</h3>
            <table className="w-full text-sm">
              <tbody>
                {(["income", "asset", "market"] as const).map((k) => (
                  <tr key={k} className="border-b border-slate-100">
                    <td className="py-1 text-slate-600">{METHOD_LABELS[k]}</td>
                    <td className="py-1 text-right">{fmt(fin.method_values[k])}</td>
                    <td className="w-12 py-1 text-right">
                      {data!.weights_editable && !approved && (
                        <button onClick={() => editWeight(k, METHOD_LABELS[k])} className="text-[10px] text-blue-500 underline">
                          가중
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="mt-3 rounded bg-slate-50 p-3 text-sm">
              {syn.mode === "parallel" ? (
                <>
                  <div className="font-medium text-slate-700">손상검사 병렬(회수가능액 = max)</div>
                  <div>사용가치(DCF): {fmt(syn.value_in_use ?? null)}</div>
                  <div>공정가치(시장): {fmt(syn.fair_value ?? null)}</div>
                  <div className="font-semibold">회수가능액: {fmt(syn.recoverable_amount ?? null)}</div>
                </>
              ) : (
                <>
                  <div className="font-medium text-slate-700">
                    가중: {Object.entries(syn.weights ?? {}).map(([k, v]) => `${METHOD_LABELS[k]} ${(v * 100).toFixed(0)}%`).join(" · ")}
                    {!data!.weights_editable && <span className="ml-1 text-xs text-slate-400">(목적 고정)</span>}
                  </div>
                  <div className="font-semibold">최종가치: {fmt(syn.final)}</div>
                  {syn.net_asset_floor_applied && <div className="text-xs text-amber-600">순자산 하한 적용됨</div>}
                </>
              )}
            </div>
          </div>

          {/* 레드플래그 */}
          <div>
            <h3 className="mb-1 text-sm font-medium text-slate-600">
              리뷰 체크(레드플래그){pending.length > 0 && <span className="ml-1 text-red-600">· 미승인 {pending.length}</span>}
            </h3>
            <ul className="space-y-1 text-sm">
              {flags.map((f) => {
                const acked = !!approvals[f.key];
                return (
                  <li key={f.key} className="flex items-center justify-between gap-2 border-b border-slate-100 py-1">
                    <span className="flex items-center gap-2">
                      <span className={`rounded px-1.5 text-[10px] ${
                        !f.triggered ? "bg-emerald-100 text-emerald-700"
                          : f.severity === "flag" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"
                      }`}>
                        {!f.triggered ? "통과" : f.severity === "flag" ? "플래그" : "경고"}
                      </span>
                      <span className={f.triggered ? "text-slate-700" : "text-slate-400"}>{f.description}</span>
                    </span>
                    {f.triggered && (
                      acked ? <span className="text-[10px] text-emerald-600">승인됨 ✓</span>
                        : !approved && <button onClick={() => ack(f.key)} className="text-[10px] text-blue-500 underline">승인</button>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}
