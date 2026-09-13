import { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import StageStepper from "./components/StageStepper";
import CaseCreate from "./pages/CaseCreate";
import Stage1Review from "./pages/Stage1Review";
import Stage2Review from "./pages/Stage2Review";
import Stage3Review from "./pages/Stage3Review";
import Stage4Review from "./pages/Stage4Review";
import Stage5Review from "./pages/Stage5Review";
import Stage6Review from "./pages/Stage6Review";
import Stage7Review from "./pages/Stage7Review";
import Stage8Review from "./pages/Stage8Review";
import Stage9Review from "./pages/Stage9Review";
import Stage10Summary from "./pages/Stage10Summary";
import type { CaseOut, StageStatus } from "./types";

export default function App() {
  const [caseData, setCaseData] = useState<CaseOut | null>(null);
  const [stages, setStages] = useState<StageStatus[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);

  const refreshStages = useCallback(async () => {
    if (!caseData) return;
    try {
      setStages(await api.getStages(caseData.case_id));
      setRefreshKey((k) => k + 1);
    } catch {
      /* ignore */
    }
  }, [caseData]);

  useEffect(() => {
    refreshStages();
  }, [refreshStages]);

  const statusOf = (n: number) => stages.find((s) => s.stage_no === n)?.status ?? "DRAFT";

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <header className="border-b border-slate-200 bg-white px-6 py-4">
        <h1 className="text-xl font-semibold">기업가치평가 대시보드</h1>
        <p className="text-sm text-slate-500">
          전문가 판단을 구조화·기록하는 내부 도구 · Stage 0~2 수직 슬라이스
        </p>
      </header>

      <main className="mx-auto max-w-5xl space-y-6 p-6">
        {!caseData ? (
          <CaseCreate onCreated={setCaseData} />
        ) : (
          <>
            <section className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <span className="font-semibold">{caseData.corp_name}</span>
                  <span className="ml-2 text-sm text-slate-500">
                    {caseData.stock_code} · 기준일 {caseData.valuation_date} · {caseData.purpose_label}
                  </span>
                </div>
                <button
                  onClick={() => {
                    setCaseData(null);
                    setStages([]);
                  }}
                  className="text-sm text-slate-400 underline"
                >
                  새 케이스
                </button>
              </div>
              <StageStepper stages={stages} />
            </section>

            <Stage10Summary caseData={caseData} refreshKey={refreshKey} />

            <Stage1Review
              caseData={caseData}
              approved={statusOf(1) === "APPROVED"}
              onChanged={refreshStages}
            />
            <Stage2Review
              caseData={caseData}
              locked={statusOf(1) !== "APPROVED"}
              approved={statusOf(2) === "APPROVED"}
              onChanged={refreshStages}
            />
            <Stage3Review
              caseData={caseData}
              locked={statusOf(2) !== "APPROVED"}
              approved={statusOf(3) === "APPROVED"}
              onChanged={refreshStages}
            />
            <Stage4Review
              caseData={caseData}
              locked={statusOf(3) !== "APPROVED"}
              approved={statusOf(4) === "APPROVED"}
              onChanged={refreshStages}
            />
            <Stage5Review
              caseData={caseData}
              locked={statusOf(4) !== "APPROVED"}
              approved={statusOf(5) === "APPROVED"}
              onChanged={refreshStages}
            />
            <Stage6Review
              caseData={caseData}
              locked={statusOf(5) !== "APPROVED"}
              approved={statusOf(6) === "APPROVED"}
              onChanged={refreshStages}
            />
            <Stage7Review
              caseData={caseData}
              locked={statusOf(6) !== "APPROVED"}
              approved={statusOf(7) === "APPROVED"}
              onChanged={refreshStages}
            />
            <Stage8Review
              caseData={caseData}
              locked={statusOf(5) !== "APPROVED"}
              approved={statusOf(8) === "APPROVED"}
              onChanged={refreshStages}
            />
            <Stage9Review
              caseData={caseData}
              locked={statusOf(5) !== "APPROVED"}
              approved={statusOf(9) === "APPROVED"}
              onChanged={refreshStages}
            />
          </>
        )}
      </main>
    </div>
  );
}
