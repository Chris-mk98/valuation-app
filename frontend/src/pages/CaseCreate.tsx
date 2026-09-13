import { useState } from "react";
import { api } from "../api/client";
import { PURPOSES, type CaseOut } from "../types";

export default function CaseCreate({ onCreated }: { onCreated: (c: CaseOut) => void }) {
  const [company, setCompany] = useState("005930");
  const [date, setDate] = useState("2023-12-28");
  const [purpose, setPurpose] = useState(PURPOSES[0].key);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const c = await api.createCase({ company, valuation_date: date, purpose });
      onCreated(c);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="max-w-md space-y-4 rounded-lg border border-slate-200 bg-white p-6">
      <h2 className="text-lg font-semibold">새 평가 케이스</h2>
      <label className="block text-sm">
        <span className="text-slate-600">대상회사 (회사명 또는 종목코드)</span>
        <input
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
          value={company}
          onChange={(e) => setCompany(e.target.value)}
        />
      </label>
      <label className="block text-sm">
        <span className="text-slate-600">평가기준일</span>
        <input
          type="date"
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </label>
      <label className="block text-sm">
        <span className="text-slate-600">평가목적</span>
        <select
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
          value={purpose}
          onChange={(e) => setPurpose(e.target.value)}
        >
          {PURPOSES.map((p) => (
            <option key={p.key} value={p.key}>
              {p.label}
            </option>
          ))}
        </select>
      </label>
      {err && <p className="text-sm text-red-600">{err}</p>}
      <button
        type="submit"
        disabled={busy}
        className="rounded bg-slate-800 px-4 py-2 text-sm text-white disabled:opacity-50"
      >
        {busy ? "생성 중…" : "케이스 생성"}
      </button>
    </form>
  );
}
