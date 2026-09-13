import { useEffect, useState } from "react";
import { api, fmt } from "../api/client";
import { MARKET_METHODS, type CaseOut, type Stage6ReviewData } from "../types";

interface Props {
  caseData: CaseOut;
  locked: boolean;
  approved: boolean;
  onChanged: () => void;
}

function num(v: number | string | null): number | null {
  return typeof v === "number" ? v : null;
}

export default function Stage6Review({ caseData, locked, approved, onChanged }: Props) {
  const [data, setData] = useState<Stage6ReviewData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setData(await api.reviewStage6(caseData.case_id));
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
        Stage 6 · 시장접근 — Stage 5 승인 후 잠금 해제됩니다.
      </section>
    );
  }

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      await api.runStage6(caseData.case_id);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function override(method: string, label: string) {
    const cur = data?.reps[method]?.value ?? 0;
    const raw = window.prompt(`${label} 적용배수 새 값:`, String(cur ?? ""));
    if (raw === null) return;
    const value = Number(raw);
    if (Number.isNaN(value)) return setErr("숫자를 입력하세요.");
    const rationale = window.prompt("사유(필수):");
    if (!rationale) return;
    try {
      await api.overrideMarket(caseData.case_id, method, value, rationale);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function approve() {
    try {
      await api.approveStage(caseData.case_id, 6);
      onChanged();
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  const peers = data?.peers ?? [];
  const hasData = peers.length > 0 || Object.keys(data?.applied ?? {}).length > 0;
  const rng = data?.range;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">
          Stage 6 · 시장접근법
          {rng?.median != null && (
            <span className="ml-2 text-sm font-normal text-emerald-700">
              가치범위 {fmt(rng.min)}~{fmt(rng.max)} (중앙 {fmt(rng.median)}) 백만원
            </span>
          )}
        </h2>
        <div className="flex flex-wrap gap-2 text-sm">
          <button onClick={run} disabled={busy} className="rounded bg-slate-700 px-3 py-1 text-white disabled:opacity-50">
            {busy ? "산출 중…" : "멀티플 산출"}
          </button>
          {hasData && (
            <a href={api.stage6DownloadUrl(caseData.case_id)} className="rounded border border-slate-300 px-3 py-1">
              멀티플 다운로드
            </a>
          )}
          <a href="/api/stages/6/transactions-template" className="rounded border border-slate-300 px-3 py-1">
            거래사례 템플릿
          </a>
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
        <>
          {/* 적용가치 요약 */}
          <table className="mb-4 w-full max-w-2xl text-sm">
            <thead>
              <tr className="border-b text-left text-slate-500">
                <th className="py-1">방법</th>
                <th className="text-right">대표배수</th>
                <th className="text-right">주주가치</th>
                <th className="text-right">주당가치(원)</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {MARKET_METHODS.map(({ key, label }) => {
                const rep = data!.reps[key];
                const ap = data!.applied[key];
                if (!rep) return null;
                return (
                  <tr key={key} className="border-b border-slate-100">
                    <td className="py-1">{label}</td>
                    <td className={`text-right ${rep.overridden ? "text-blue-700" : ""}`}>
                      {rep.overridden && "✎ "}
                      {rep.value != null ? rep.value.toFixed(2) : "—"}
                    </td>
                    <td className="text-right">{fmt(ap?.equity_value ?? null)}</td>
                    <td className="text-right">{fmt(ap?.per_share ?? null)}</td>
                    <td className="text-right">
                      {!approved && (
                        <button onClick={() => override(key, label)} className="text-[10px] text-blue-500 underline">
                          배수수정
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {/* 유사기업 멀티플 */}
          <div className="overflow-x-auto">
            <h3 className="mb-1 text-sm font-medium text-slate-600">유사기업 멀티플</h3>
            <table className="w-full min-w-[560px] text-xs">
              <thead>
                <tr className="border-b text-right text-slate-500">
                  <th className="text-left">회사</th>
                  <th>시총</th>
                  <th>EBITDA</th>
                  <th>EV/EBITDA</th>
                  <th>PER</th>
                  <th>PBR</th>
                </tr>
              </thead>
              <tbody>
                {peers.map((p, i) => (
                  <tr key={i} className="border-b border-slate-100 text-right">
                    <td className="text-left">{String(p.corp_name ?? "")}</td>
                    <td>{fmt(num(p.market_cap))}</td>
                    <td>{fmt(num(p.ebitda))}</td>
                    <td>{num(p.ev_ebitda) != null ? num(p.ev_ebitda)!.toFixed(1) : "—"}</td>
                    <td>{num(p.per) != null ? num(p.per)!.toFixed(1) : "—"}</td>
                    <td>{num(p.pbr) != null ? num(p.pbr)!.toFixed(1) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
