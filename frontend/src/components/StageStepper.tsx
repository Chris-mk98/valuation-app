import type { StageStatus } from "../types";

const STAGE_LABELS: Record<number, string> = {
  0: "설정",
  1: "수집",
  2: "정규화",
  3: "유사기업",
  4: "WACC",
  5: "DCF",
  6: "시장접근",
  7: "자산접근",
  8: "몬테카를로",
  9: "조정·리뷰",
  10: "산출물",
};

const STATUS_STYLE: Record<string, string> = {
  APPROVED: "bg-emerald-100 text-emerald-700 border-emerald-300",
  REVIEWED: "bg-amber-100 text-amber-700 border-amber-300",
  DRAFT: "bg-slate-100 text-slate-400 border-slate-200",
};

export default function StageStepper({ stages }: { stages: StageStatus[] }) {
  return (
    <ol className="flex flex-wrap gap-2">
      {stages.map((s) => (
        <li
          key={s.stage_no}
          title={s.invalidated_by ? `무효화 원인: ${s.invalidated_by}` : s.status}
          className={`rounded-full border px-3 py-1 text-xs font-medium ${
            STATUS_STYLE[s.status] ?? STATUS_STYLE.DRAFT
          }`}
        >
          {s.stage_no} {STAGE_LABELS[s.stage_no]}
          {s.status === "APPROVED" && " ✓"}
        </li>
      ))}
    </ol>
  );
}
