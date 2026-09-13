import type {
  AssetResultData,
  CaseOut,
  Peer,
  Stage1Run,
  Stage2Review,
  Stage3ReviewData,
  Stage4ReviewData,
  Stage5ReviewData,
  Stage6ReviewData,
  Stage7ReviewData,
  Stage8ReviewData,
  Stage9ReviewData,
  StageStatus,
  SummaryData,
  LineageRow,
} from "../types";

async function req<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  createCase: (body: { company: string; valuation_date: string; purpose: string }) =>
    req<CaseOut>("/api/cases", { method: "POST", body: JSON.stringify(body) }),

  getStages: (caseId: string) => req<StageStatus[]>(`/api/cases/${caseId}/stages`),

  runStage1: (caseId: string) =>
    req<Stage1Run>(`/api/cases/${caseId}/stages/1/run`, { method: "POST" }),

  approveStage: (caseId: string, stageNo: number, approvedBy = "analyst") =>
    req<{ stage_no: number; status: string }>(
      `/api/cases/${caseId}/stages/${stageNo}/approve`,
      { method: "POST", body: JSON.stringify({ approved_by: approvedBy }) },
    ),

  reviewStage2: (caseId: string) =>
    req<Stage2Review>(`/api/cases/${caseId}/stages/2/review`),

  override: (
    caseId: string,
    body: { year: number; account: string; value: number; rationale: string; changed_by?: string },
  ) =>
    req<{ overridden: boolean; value: number; system_value: number | null }>(
      `/api/cases/${caseId}/stages/2/override`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  runStage3: (caseId: string) =>
    req<{ target: Record<string, unknown>; screened: number; passed: number }>(
      `/api/cases/${caseId}/stages/3/run`,
      { method: "POST" },
    ),

  reviewStage3: (caseId: string) => req<Stage3ReviewData>(`/api/cases/${caseId}/stages/3/review`),

  togglePeer: (caseId: string, corpCode: string, included: boolean, rationale: string) =>
    req<Peer>(`/api/cases/${caseId}/stages/3/peers/toggle`, {
      method: "POST",
      body: JSON.stringify({ corp_code: corpCode, included, rationale }),
    }),

  addPeer: (caseId: string, company: string, rationale: string) =>
    req<Peer>(`/api/cases/${caseId}/stages/3/peers/add`, {
      method: "POST",
      body: JSON.stringify({ company, rationale }),
    }),

  runStage4: (caseId: string) =>
    req<{ peers: Record<string, unknown>[]; warnings: string[]; kd_default: boolean }>(
      `/api/cases/${caseId}/stages/4/run`,
      { method: "POST" },
    ),

  reviewStage4: (caseId: string) => req<Stage4ReviewData>(`/api/cases/${caseId}/stages/4/review`),

  overrideWacc: (caseId: string, component: string, value: number, rationale: string) =>
    req<{ component: string; value: number; wacc: number | null }>(
      `/api/cases/${caseId}/stages/4/override`,
      { method: "POST", body: JSON.stringify({ component, value, rationale }) },
    ),

  runStage5: (caseId: string) =>
    req<Stage5ReviewData>(`/api/cases/${caseId}/stages/5/run`, { method: "POST" }),

  reviewStage5: (caseId: string) => req<Stage5ReviewData>(`/api/cases/${caseId}/stages/5/review`),

  overrideDcf: (caseId: string, name: string, value: number, rationale: string) =>
    req<{ name: string; ev: number | null; equity_value: number | null }>(
      `/api/cases/${caseId}/stages/5/override`,
      { method: "POST", body: JSON.stringify({ name, value, rationale }) },
    ),

  runStage6: (caseId: string) =>
    req<Stage6ReviewData>(`/api/cases/${caseId}/stages/6/run`, { method: "POST" }),

  reviewStage6: (caseId: string) => req<Stage6ReviewData>(`/api/cases/${caseId}/stages/6/review`),

  overrideMarket: (caseId: string, method: string, value: number, rationale: string) =>
    req<{ method: string; range: { min: number; max: number } }>(
      `/api/cases/${caseId}/stages/6/override`,
      { method: "POST", body: JSON.stringify({ method, value, rationale }) },
    ),

  runStage7: (caseId: string) =>
    req<Stage7ReviewData>(`/api/cases/${caseId}/stages/7/run`, { method: "POST" }),

  reviewStage7: (caseId: string) => req<Stage7ReviewData>(`/api/cases/${caseId}/stages/7/review`),

  addAdjustment: (caseId: string, label: string, amount: number, rationale: string) =>
    req<AssetResultData>(`/api/cases/${caseId}/stages/7/adjustments`, {
      method: "POST",
      body: JSON.stringify({ label, amount, rationale }),
    }),

  removeAdjustment: (caseId: string, adjId: number) =>
    req<AssetResultData>(`/api/cases/${caseId}/stages/7/adjustments/${adjId}`, {
      method: "DELETE",
    }),

  overridePremium: (caseId: string, value: number, rationale: string) =>
    req<AssetResultData>(`/api/cases/${caseId}/stages/7/premium`, {
      method: "POST",
      body: JSON.stringify({ value, rationale }),
    }),

  runStage8: (caseId: string) =>
    req<Stage8ReviewData>(`/api/cases/${caseId}/stages/8/run`, { method: "POST" }),

  reviewStage8: (caseId: string) => req<Stage8ReviewData>(`/api/cases/${caseId}/stages/8/review`),

  overrideMcSigma: (caseId: string, varName: string, sigma: number, rationale: string) =>
    req<{ var: string; mean: number; p10: number; p90: number }>(
      `/api/cases/${caseId}/stages/8/distribution`,
      { method: "POST", body: JSON.stringify({ var: varName, sigma, rationale }) },
    ),

  runStage9: (caseId: string) =>
    req<Stage9ReviewData>(`/api/cases/${caseId}/stages/9/run`, { method: "POST" }),

  reviewStage9: (caseId: string) => req<Stage9ReviewData>(`/api/cases/${caseId}/stages/9/review`),

  overrideWeight: (caseId: string, method: string, value: number, rationale: string) =>
    req<{ method: string; final: number | null }>(`/api/cases/${caseId}/stages/9/weight`, {
      method: "POST",
      body: JSON.stringify({ method, value, rationale }),
    }),

  ackFlag: (caseId: string, key: string, note: string) =>
    req<{ key: string; approved: boolean }>(`/api/cases/${caseId}/stages/9/flags/ack`, {
      method: "POST",
      body: JSON.stringify({ key, note }),
    }),

  getSummary: (caseId: string) => req<SummaryData>(`/api/cases/${caseId}/summary`),
  getLineage: (caseId: string) => req<LineageRow[]>(`/api/cases/${caseId}/lineage`),
  lineageCsvUrl: (caseId: string) => `/api/cases/${caseId}/lineage.csv`,
  caseJsonUrl: (caseId: string) => `/api/cases/${caseId}/export.json`,
  workbookUrl: (caseId: string) => `/api/cases/${caseId}/workbook`,
  reportUrl: (caseId: string) => `/api/cases/${caseId}/report`,

  stage9DownloadUrl: (caseId: string) => `/api/cases/${caseId}/stages/9/download`,
  stage8DownloadUrl: (caseId: string) => `/api/cases/${caseId}/stages/8/download`,
  stage7DownloadUrl: (caseId: string) => `/api/cases/${caseId}/stages/7/download`,
  stage1DownloadUrl: (caseId: string) => `/api/cases/${caseId}/stages/1/download`,
  stage2DownloadUrl: (caseId: string) => `/api/cases/${caseId}/stages/2/download`,
  stage3DownloadUrl: (caseId: string) => `/api/cases/${caseId}/stages/3/download`,
  stage4DownloadUrl: (caseId: string) => `/api/cases/${caseId}/stages/4/download`,
  stage5DownloadUrl: (caseId: string) => `/api/cases/${caseId}/stages/5/download`,
  stage6DownloadUrl: (caseId: string) => `/api/cases/${caseId}/stages/6/download`,
  mappingTemplateUrl: () => `/api/stages/2/mapping-template`,

  uploadMapping: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/stages/2/mapping-upload", { method: "POST", body: fd });
    if (!res.ok) throw new Error(`${res.status}`);
    return res.json() as Promise<{
      valid: boolean;
      errors: { row: number; column: string; message: string }[];
      targets: number;
    }>;
  },
};

export function fmt(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("ko-KR", { maximumFractionDigits: 0 });
}
