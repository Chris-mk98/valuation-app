import { useEffect, useState } from "react";
import { api, fmt } from "../api/client";
import type { CaseOut, Stage7ReviewData } from "../types";

interface Props {
  caseData: CaseOut;
  locked: boolean;
  approved: boolean;
  onChanged: () => void;
}

export default function Stage7Review({ caseData, locked, approved, onChanged }: Props) {
  const [data, setData] = useState<Stage7ReviewData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [label, setLabel] = useState("");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");

  async function load() {
    try {
      setData(await api.reviewStage7(caseData.case_id));
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
        Stage 7 · 자산접근 — Stage 6 승인 후 잠금 해제됩니다.
      </section>
    );
  }

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      await api.runStage7(caseData.case_id);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function addAdj() {
    if (!label.trim() || !amount.trim() || !reason.trim()) {
      return setErr("항목·금액·사유를 모두 입력하세요.");
    }
    try {
      await api.addAdjustment(caseData.case_id, label, Number(amount), reason);
      setLabel("");
      setAmount("");
      setReason("");
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function removeAdj(id: number) {
    try {
      await api.removeAdjustment(caseData.case_id, id);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function editPremium() {
    const cur = data?.result.control_premium_rate ?? 0;
    const raw = window.prompt("최대주주 할증률 (소수, 예: 0.20=20%):", String(cur));
    if (raw === null) return;
    const value = Number(raw);
    if (Number.isNaN(value)) return setErr("숫자를 입력하세요.");
    const rationale = window.prompt("사유(필수):");
    if (!rationale) return;
    try {
      await api.overridePremium(caseData.case_id, value, rationale);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function approve() {
    try {
      await api.approveStage(caseData.case_id, 7);
      onChanged();
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  const r = data?.result;
  const hasData = !!r && r.book_equity !== undefined;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">
          Stage 7 · 자산접근법
          {r?.value_with_premium != null && (
            <span className="ml-2 text-sm font-normal text-emerald-700">
              조정순자산 {fmt(r.value_with_premium)} 백만원
              {r.per_share != null && ` · 주당 ${fmt(r.per_share)}원`}
            </span>
          )}
        </h2>
        <div className="flex flex-wrap gap-2 text-sm">
          <button onClick={run} disabled={busy} className="rounded bg-slate-700 px-3 py-1 text-white disabled:opacity-50">
            {busy ? "산출 중…" : "자산가치 산출"}
          </button>
          {hasData && (
            <a href={api.stage7DownloadUrl(caseData.case_id)} className="rounded border border-slate-300 px-3 py-1">
              조정순자산 다운로드
            </a>
          )}
          <a href="/api/stages/7/adjustments-template" className="rounded border border-slate-300 px-3 py-1">
            조정항목 템플릿
          </a>
          <button onClick={approve} disabled={approved || !hasData} className="rounded bg-emerald-600 px-3 py-1 text-white disabled:opacity-50">
            {approved ? "승인됨 ✓" : "검토 후 승인"}
          </button>
        </div>
      </div>

      {err && <p className="mb-2 text-sm text-red-600">{err}</p>}

      {hasData && r && (
        <>
          <table className="mb-3 w-full max-w-xl text-sm">
            <tbody>
              <tr className="border-b border-slate-100">
                <td className="py-1 text-slate-600">장부 순자산(지배주주지분)</td>
                <td className="py-1 text-right">{fmt(r.book_equity)}</td>
                <td></td>
              </tr>
              {r.adjustments.map((a) => (
                <tr key={a.id} className="border-b border-slate-100">
                  <td className="py-1 text-slate-600">
                    {a.label}
                    {a.source === "EXCEL_UPLOAD" && <span className="ml-1 text-[10px] text-blue-500">엑셀</span>}
                    <span className="ml-1 text-xs text-slate-400" title={a.rationale ?? ""}>
                      ({a.rationale})
                    </span>
                  </td>
                  <td className={`py-1 text-right ${a.amount < 0 ? "text-red-600" : ""}`}>{fmt(a.amount)}</td>
                  <td className="py-1 text-right">
                    {!approved && (
                      <button onClick={() => removeAdj(a.id)} className="text-[10px] text-red-500 underline">
                        삭제
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              <tr className="border-b border-slate-200 font-medium">
                <td className="py-1">조정순자산</td>
                <td className="py-1 text-right">{fmt(r.adjusted_net_asset)}</td>
                <td></td>
              </tr>
              <tr className="border-b border-slate-100">
                <td className="py-1 text-slate-600">
                  최대주주 할증률
                  {data?.premium_overridden && <span className="ml-1 text-blue-700">✎</span>}
                </td>
                <td className="py-1 text-right">{(r.control_premium_rate * 100).toFixed(1)}%</td>
                <td className="py-1 text-right">
                  {!approved && (
                    <button onClick={editPremium} className="text-[10px] text-blue-500 underline">
                      수정
                    </button>
                  )}
                </td>
              </tr>
              <tr className="font-semibold">
                <td className="py-1">조정순자산가치(할증후)</td>
                <td className="py-1 text-right">{fmt(r.value_with_premium)}</td>
                <td></td>
              </tr>
            </tbody>
          </table>

          {!approved && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-slate-500">조정항목 추가:</span>
              <input placeholder="항목명" className="rounded border border-slate-300 px-2 py-1" value={label} onChange={(e) => setLabel(e.target.value)} />
              <input placeholder="금액(±백만원)" type="number" className="w-32 rounded border border-slate-300 px-2 py-1" value={amount} onChange={(e) => setAmount(e.target.value)} />
              <input placeholder="사유(필수)" className="rounded border border-slate-300 px-2 py-1" value={reason} onChange={(e) => setReason(e.target.value)} />
              <button onClick={addAdj} className="rounded border border-slate-300 px-3 py-1">추가</button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
