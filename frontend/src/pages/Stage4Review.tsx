import { useEffect, useState } from "react";
import { api } from "../api/client";
import { WACC_ORDER, type CaseOut, type Stage4ReviewData, type WaccCell } from "../types";

interface Props {
  caseData: CaseOut;
  locked: boolean;
  approved: boolean;
  onChanged: () => void;
}

function cellText(cell: WaccCell | undefined, pct: boolean): string {
  if (!cell || cell.value === null) return "—";
  const v = cell.value;
  return pct ? `${v.toFixed(3)}%` : v.toLocaleString("ko-KR", { maximumFractionDigits: 4 });
}

export default function Stage4Review({ caseData, locked, approved, onChanged }: Props) {
  const [data, setData] = useState<Stage4ReviewData | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setData(await api.reviewStage4(caseData.case_id));
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
        Stage 4 · WACC — Stage 3 승인 후 잠금 해제됩니다.
      </section>
    );
  }

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      const res = await api.runStage4(caseData.case_id);
      setWarnings(res.warnings);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function override(component: string, label: string) {
    const raw = window.prompt(`${label} 새 값:`);
    if (raw === null) return;
    const value = Number(raw);
    if (Number.isNaN(value)) {
      setErr("숫자를 입력하세요.");
      return;
    }
    const rationale = window.prompt("사유(필수):");
    if (!rationale) return;
    try {
      await api.overrideWacc(caseData.case_id, component, value, rationale);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function approve() {
    try {
      await api.approveStage(caseData.case_id, 4);
      onChanged();
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  const comps = data?.components ?? {};
  const wacc = comps["wacc"];
  const hasData = Object.keys(comps).length > 0;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">
          Stage 4 · 할인율(WACC)
          {wacc?.value != null && (
            <span className="ml-2 text-sm font-normal text-emerald-700">
              = {wacc.value.toFixed(2)}%
            </span>
          )}
        </h2>
        <div className="flex flex-wrap gap-2 text-sm">
          <button onClick={run} disabled={busy} className="rounded bg-slate-700 px-3 py-1 text-white disabled:opacity-50">
            {busy ? "산출 중…" : "WACC 산출"}
          </button>
          {hasData && (
            <a href={api.stage4DownloadUrl(caseData.case_id)} className="rounded border border-slate-300 px-3 py-1">
              빌드업 다운로드
            </a>
          )}
          <button onClick={approve} disabled={approved || !hasData} className="rounded bg-emerald-600 px-3 py-1 text-white disabled:opacity-50">
            {approved ? "승인됨 ✓" : "검토 후 승인"}
          </button>
        </div>
      </div>

      {err && <p className="mb-2 text-sm text-red-600">{err}</p>}
      {warnings.length > 0 && (
        <div className="mb-2 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700">
          {warnings.map((w, i) => (
            <div key={i}>⚠ {w}</div>
          ))}
        </div>
      )}

      {!hasData ? (
        <p className="text-sm text-slate-400">
          ‘WACC 산출’: 유사기업 주간 베타(2년·KOSPI) → 언레버/리레버 → CAPM Ke → WACC.
        </p>
      ) : (
        <table className="w-full max-w-xl text-sm">
          <tbody>
            {WACC_ORDER.map(({ key, label, pct }) => {
              const cell = comps[key];
              if (!cell) return null;
              const isWacc = key === "wacc";
              return (
                <tr key={key} className={`border-b border-slate-100 ${isWacc ? "font-semibold" : ""}`}>
                  <td className="py-1 text-slate-600">{label}</td>
                  <td className={`py-1 text-right ${cell.overridden ? "text-blue-700" : ""}`}>
                    {cell.overridden && <span title={`시스템: ${cell.system_value} · ${cell.rationale}`}>✎ </span>}
                    {cellText(cell, pct)}
                  </td>
                  <td className="w-16 py-1 text-right">
                    {!approved && !isWacc && (
                      <button onClick={() => override(key, label)} className="text-[10px] text-blue-500 underline">
                        덮어쓰기
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
