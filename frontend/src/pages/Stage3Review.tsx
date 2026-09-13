import { useEffect, useState } from "react";
import { api, fmt } from "../api/client";
import type { CaseOut, Peer, Stage3ReviewData } from "../types";

interface Props {
  caseData: CaseOut;
  locked: boolean;
  approved: boolean;
  onChanged: () => void;
}

function FilterBadge({ ok, label }: { ok: boolean | undefined; label: string }) {
  if (ok === undefined) return null;
  return (
    <span
      className={`rounded px-1 text-[10px] ${
        ok ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-600"
      }`}
    >
      {label}
    </span>
  );
}

export default function Stage3Review({ caseData, locked, approved, onChanged }: Props) {
  const [data, setData] = useState<Stage3ReviewData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [addCompany, setAddCompany] = useState("");
  const [addReason, setAddReason] = useState("");

  async function load() {
    try {
      setData(await api.reviewStage3(caseData.case_id));
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
        Stage 3 · 유사기업 — Stage 2 승인 후 잠금 해제됩니다.
      </section>
    );
  }

  async function runScreen() {
    setBusy(true);
    setErr(null);
    try {
      await api.runStage3(caseData.case_id);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function toggle(p: Peer) {
    const rationale = window.prompt(
      `${p.corp_name} 을(를) ${p.included ? "제외" : "포함"}하는 사유(필수):`,
    );
    if (!rationale) return;
    try {
      await api.togglePeer(caseData.case_id, p.corp_code, !p.included, rationale);
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function addManual() {
    if (!addCompany.trim() || !addReason.trim()) {
      setErr("회사와 사유를 모두 입력하세요.");
      return;
    }
    try {
      await api.addPeer(caseData.case_id, addCompany, addReason);
      setAddCompany("");
      setAddReason("");
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function approve() {
    try {
      await api.approveStage(caseData.case_id, 3);
      onChanged();
      await load();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  const peers = data?.peers ?? [];
  const includedCount = peers.filter((p) => p.included).length;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">
          Stage 3 · 유사기업 스크리닝{" "}
          <span className="text-sm font-normal text-slate-500">
            (확정 {includedCount}개 / 후보 {peers.length}개)
          </span>
        </h2>
        <div className="flex flex-wrap gap-2 text-sm">
          <button onClick={runScreen} disabled={busy} className="rounded bg-slate-700 px-3 py-1 text-white disabled:opacity-50">
            {busy ? "스크리닝 중…" : "자동 스크리닝"}
          </button>
          {peers.length > 0 && (
            <a href={api.stage3DownloadUrl(caseData.case_id)} className="rounded border border-slate-300 px-3 py-1">
              후보 다운로드
            </a>
          )}
          <button onClick={approve} disabled={approved || includedCount === 0} className="rounded bg-emerald-600 px-3 py-1 text-white disabled:opacity-50">
            {approved ? "승인됨 ✓" : "확정 후 승인"}
          </button>
        </div>
      </div>

      {err && <p className="mb-2 text-sm text-red-600">{err}</p>}

      {peers.length === 0 ? (
        <p className="text-sm text-slate-400">
          ‘자동 스크리닝’으로 동일 KSIC 중분류·규모·흑자·상장연수 필터를 적용합니다.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-b text-left text-slate-500">
                <th className="py-1">포함</th>
                <th>회사</th>
                <th className="text-right">매출</th>
                <th className="text-right">순이익</th>
                <th className="text-right">시총</th>
                <th>필터</th>
                <th>사유</th>
              </tr>
            </thead>
            <tbody>
              {peers.map((p) => (
                <tr key={p.corp_code} className={`border-b border-slate-100 ${p.included ? "bg-emerald-50/40" : ""}`}>
                  <td className="py-1">
                    <input type="checkbox" checked={p.included} onChange={() => toggle(p)} disabled={approved} />
                  </td>
                  <td>
                    {p.corp_name}
                    {p.source === "MANUAL" && <span className="ml-1 text-[10px] text-blue-500">수동</span>}
                  </td>
                  <td className="text-right">{fmt(p.metrics.revenue)}</td>
                  <td className="text-right">{fmt(p.metrics.net_income)}</td>
                  <td className="text-right">{fmt(p.metrics.market_cap)}</td>
                  <td>
                    <div className="flex gap-1">
                      <FilterBadge ok={p.metrics.filters?.industry} label="업종" />
                      <FilterBadge ok={p.metrics.filters?.size} label="규모" />
                      <FilterBadge ok={p.metrics.filters?.profit} label="흑자" />
                      <FilterBadge ok={p.metrics.filters?.age} label="연수" />
                    </div>
                  </td>
                  <td className="max-w-[160px] truncate text-xs text-slate-500" title={p.rationale ?? ""}>
                    {p.rationale ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
            <span className="text-slate-500">수동 추가:</span>
            <input
              placeholder="회사명/종목코드"
              className="rounded border border-slate-300 px-2 py-1"
              value={addCompany}
              onChange={(e) => setAddCompany(e.target.value)}
            />
            <input
              placeholder="사유(필수)"
              className="rounded border border-slate-300 px-2 py-1"
              value={addReason}
              onChange={(e) => setAddReason(e.target.value)}
            />
            <button onClick={addManual} disabled={approved} className="rounded border border-slate-300 px-3 py-1 disabled:opacity-50">
              추가
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
