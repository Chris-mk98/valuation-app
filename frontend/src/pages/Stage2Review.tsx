import { useEffect, useState } from "react";
import { api } from "../api/client";
import OverrideCell from "../components/OverrideCell";
import type { CaseOut, Stage2Review as Review } from "../types";

const ACCOUNT_LABELS: Record<string, string> = {
  revenue: "매출",
  cost_of_sales: "매출원가",
  gross_profit: "매출총이익",
  sga: "판관비",
  ebit: "영업이익(EBIT)",
  pretax_income: "세전이익",
  tax_expense: "법인세비용",
  net_income: "당기순이익",
  dna: "감가상각비(D&A)",
  capex: "CAPEX",
  nwc: "순운전자본",
  net_debt: "순차입금",
  cash: "현금성자산",
  nci: "비지배지분",
  total_equity: "자본총계",
  owners_equity: "지배주주지분",
};
const ORDER = Object.keys(ACCOUNT_LABELS);

interface Props {
  caseData: CaseOut;
  locked: boolean; // Stage 1 미승인 시 잠금
  approved: boolean;
  onChanged: () => void;
}

export default function Stage2Review({ caseData, locked, approved, onChanged }: Props) {
  const [review, setReview] = useState<Review | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);

  async function load() {
    setErr(null);
    try {
      setReview(await api.reviewStage2(caseData.case_id));
      onChanged();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  useEffect(() => {
    if (!locked) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locked]);

  if (locked) {
    return (
      <section className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-400">
        Stage 2 · 정규화 — Stage 1 승인 후 잠금 해제됩니다.
      </section>
    );
  }

  async function saveOverride(year: number, account: string, value: number, rationale: string) {
    await api.override(caseData.case_id, { year, account, value, rationale });
    await load();
  }

  async function approve() {
    try {
      await api.approveStage(caseData.case_id, 2);
      onChanged();
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    try {
      const res = await api.uploadMapping(f);
      setUploadMsg(res.valid ? `검증 통과 (targets ${res.targets})` : `오류 ${res.errors.length}건`);
    } catch (e) {
      setUploadMsg((e as Error).message);
    }
  }

  const years = review?.years ?? [];

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Stage 2 · 정규화 검토 (계정 매핑)</h2>
        <div className="flex flex-wrap gap-2 text-sm">
          <a href={api.stage2DownloadUrl(caseData.case_id)} className="rounded border border-slate-300 px-3 py-1">
            정규화 다운로드
          </a>
          <a href={api.mappingTemplateUrl()} className="rounded border border-slate-300 px-3 py-1">
            매핑표 템플릿
          </a>
          <label className="cursor-pointer rounded border border-slate-300 px-3 py-1">
            매핑표 업로드
            <input type="file" accept=".xlsx" className="hidden" onChange={onUpload} />
          </label>
          <button
            onClick={approve}
            disabled={approved}
            className="rounded bg-emerald-600 px-3 py-1 text-white disabled:opacity-50"
          >
            {approved ? "승인됨 ✓" : "검토 후 승인"}
          </button>
        </div>
      </div>

      {err && <p className="mb-2 text-sm text-red-600">{err}</p>}
      {uploadMsg && <p className="mb-2 text-sm text-blue-600">업로드: {uploadMsg}</p>}

      {review && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b text-slate-500">
                  <th className="py-1 text-left">내부계정 (백만원)</th>
                  {years.map((y) => (
                    <th key={y} className="px-2 text-right">
                      {y}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ORDER.map((acc) => (
                  <tr key={acc} className="border-b border-slate-100">
                    <td className="py-1 text-left text-slate-700">{ACCOUNT_LABELS[acc]}</td>
                    {years.map((y) => {
                      const cell = review.accounts[String(y)]?.[acc];
                      if (!cell)
                        return (
                          <td key={y} className="px-2 text-right text-slate-300">
                            —
                          </td>
                        );
                      return (
                        <td key={y} className="px-2">
                          <OverrideCell
                            cell={cell}
                            disabled={approved}
                            onSave={(v, r) => saveOverride(y, acc, v, r)}
                          />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {years.some((y) => (review.unmapped[String(y)] ?? []).length > 0) && (
            <div className="mt-3 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700">
              <strong>미분류 계정</strong> (사용자 입력/오버라이드 필요):
              {years.map((y) => {
                const u = review.unmapped[String(y)] ?? [];
                return u.length ? (
                  <div key={y}>
                    {y}: {u.map((a) => ACCOUNT_LABELS[a] ?? a).join(", ")}
                  </div>
                ) : null;
              })}
            </div>
          )}
        </>
      )}
    </section>
  );
}
