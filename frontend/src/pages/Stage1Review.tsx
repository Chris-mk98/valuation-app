import { useState } from "react";
import { api } from "../api/client";
import type { CaseOut, Stage1Run } from "../types";

interface Props {
  caseData: CaseOut;
  approved: boolean;
  onChanged: () => void;
}

export default function Stage1Review({ caseData, approved, onChanged }: Props) {
  const [run, setRun] = useState<Stage1Run | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function collect() {
    setBusy(true);
    setErr(null);
    try {
      setRun(await api.runStage1(caseData.case_id));
      onChanged();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    setBusy(true);
    setErr(null);
    try {
      await api.approveStage(caseData.case_id, 1);
      onChanged();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-semibold">Stage 1 · 원천 데이터 수집 (DART)</h2>
        <div className="flex gap-2">
          <button onClick={collect} disabled={busy} className="rounded bg-slate-700 px-3 py-1 text-sm text-white disabled:opacity-50">
            {busy ? "…" : "수집 실행"}
          </button>
          {run && (
            <a href={api.stage1DownloadUrl(caseData.case_id)} className="rounded border border-slate-300 px-3 py-1 text-sm">
              원본 다운로드
            </a>
          )}
          <button
            onClick={approve}
            disabled={busy || !run || approved}
            className="rounded bg-emerald-600 px-3 py-1 text-sm text-white disabled:opacity-50"
          >
            {approved ? "승인됨 ✓" : "검토 후 승인"}
          </button>
        </div>
      </div>
      {err && <p className="mb-2 text-sm text-red-600">{err}</p>}
      {run ? (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-slate-500">
              <th className="py-1">연도</th>
              <th>계정 행 수</th>
              <th>상태</th>
            </tr>
          </thead>
          <tbody>
            {run.collected.map((c) => (
              <tr key={c.year} className="border-b border-slate-100">
                <td className="py-1">{c.year}</td>
                <td>{c.rows}</td>
                <td className={c.ok ? "text-emerald-600" : "text-red-600"}>
                  {c.ok ? "수집됨" : "데이터 없음"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-sm text-slate-400">‘수집 실행’으로 최근 5개년 재무제표를 가져옵니다.</p>
      )}
    </section>
  );
}
