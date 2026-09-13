import { useState } from "react";
import { fmt } from "../api/client";
import type { Cell } from "../types";

interface Props {
  cell: Cell;
  onSave: (value: number, rationale: string) => Promise<void>;
  disabled?: boolean;
}

export default function OverrideCell({ cell, onSave, disabled }: Props) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(cell.value ?? 0);
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    if (!rationale.trim()) {
      setErr("사유는 필수입니다.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await onSave(Number(value), rationale);
      setEditing(false);
      setRationale("");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (editing) {
    return (
      <div className="flex min-w-[190px] flex-col gap-1 rounded border border-blue-300 bg-blue-50 p-2 text-xs">
        <input
          type="number"
          className="rounded border border-slate-300 px-1 py-0.5 text-right"
          value={value}
          onChange={(e) => setValue(Number(e.target.value))}
        />
        <input
          type="text"
          placeholder="사유 입력(필수)"
          className="rounded border border-slate-300 px-1 py-0.5"
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
        />
        {err && <span className="text-red-600">{err}</span>}
        <div className="flex gap-1">
          <button
            onClick={save}
            disabled={busy}
            className="rounded bg-blue-600 px-2 py-0.5 text-white disabled:opacity-50"
          >
            저장
          </button>
          <button
            onClick={() => setEditing(false)}
            className="rounded bg-slate-200 px-2 py-0.5"
          >
            취소
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`group flex items-center justify-end gap-1 rounded px-1 py-0.5 text-right ${
        cell.overridden ? "bg-blue-50 font-medium text-blue-700" : ""
      }`}
      title={
        cell.overridden
          ? `전문가 오버라이드 · 시스템제안: ${fmt(cell.system_value)} · 사유: ${cell.rationale}`
          : cell.source_type
      }
    >
      {cell.overridden && <span aria-label="override">✎</span>}
      <span>{fmt(cell.value)}</span>
      {!disabled && (
        <button
          onClick={() => {
            setValue(cell.value ?? 0);
            setEditing(true);
          }}
          className="invisible text-[10px] text-blue-500 underline group-hover:visible"
        >
          덮어쓰기
        </button>
      )}
    </div>
  );
}
