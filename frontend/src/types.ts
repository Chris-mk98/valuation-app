export interface CaseOut {
  case_id: string;
  corp_code: string;
  corp_name: string;
  stock_code: string | null;
  induty_code: string | null;
  valuation_date: string;
  purpose: string;
  purpose_label: string;
  currency: string;
  unit: string;
}

export interface StageStatus {
  stage_no: number;
  status: "DRAFT" | "REVIEWED" | "APPROVED";
  approved_by?: string | null;
  approved_at?: string | null;
  invalidated_by?: string | null;
}

export interface Stage1Run {
  case_id: string;
  corp_name: string;
  years: number[];
  collected: { year: number; rows: number; ok: boolean }[];
}

export interface Cell {
  value: number | null;
  source_type: string;
  overridden: boolean;
  system_value: number | null;
  rationale: string | null;
}

export interface Stage2Review {
  case_id: string;
  years: number[];
  accounts: Record<string, Record<string, Cell>>;
  unmapped: Record<string, string[]>;
  warnings: Record<string, string[]>;
  stage2_status: string;
  stage1_status: string;
}

export interface PeerMetrics {
  revenue: number | null;
  net_income: number | null;
  market_cap: number | null;
  years_reported: number | null;
  sector: string | null;
  induty_code: string | null;
  passed: boolean | null;
  filters: { industry: boolean; size: boolean; profit: boolean; age: boolean } | null;
}

export interface Peer {
  corp_code: string;
  corp_name: string;
  stock_code: string | null;
  included: boolean;
  source: string;
  rationale: string | null;
  metrics: PeerMetrics;
}

export interface Stage3ReviewData {
  case_id: string;
  peers: Peer[];
  target: { induty_code: string | null; corp_name: string };
  stage3_status: string;
  stage2_status: string;
}

export interface WaccCell {
  value: number | null;
  source_ref: string | null;
  overridden: boolean;
  system_value: number | null;
  rationale: string | null;
}

export interface Stage4ReviewData {
  case_id: string;
  components: Record<string, WaccCell>;
  stage4_status: string;
  stage3_status: string;
}

export const WACC_ORDER: { key: string; label: string; pct: boolean }[] = [
  { key: "rf", label: "무위험이자율 Rf", pct: true },
  { key: "beta_u_median", label: "언레버 베타(중앙값)", pct: false },
  { key: "target_de", label: "목표 D/E", pct: false },
  { key: "beta_relevered", label: "리레버 베타", pct: false },
  { key: "erp", label: "시장위험프리미엄 ERP", pct: true },
  { key: "country_risk", label: "국가위험", pct: true },
  { key: "size_premium", label: "규모프리미엄", pct: true },
  { key: "ke", label: "자기자본비용 Ke", pct: true },
  { key: "kd", label: "타인자본비용 Kd", pct: true },
  { key: "tax_rate", label: "법인세율", pct: true },
  { key: "equity_value", label: "자기자본가치(백만원)", pct: false },
  { key: "debt_value", label: "타인자본가치(백만원)", pct: false },
  { key: "wacc", label: "WACC", pct: true },
];

export interface AssumptionCell {
  value: number | null;
  source_ref: string | null;
  overridden: boolean;
  system_value: number | null;
  rationale: string | null;
  editable: boolean;
}

export interface DcfRow {
  t: number;
  revenue: number;
  ebit: number;
  nopat: number;
  dna: number;
  capex: number;
  delta_nwc: number;
  fcff: number;
  pv: number;
}

export interface DcfResult {
  error: string | null;
  rows: DcfRow[];
  pv_sum: number | null;
  tv: number | null;
  pv_tv: number | null;
  tv_ratio: number | null;
  ev: number | null;
  equity_value: number | null;
  per_share: number | null;
}

export interface Stage5ReviewData {
  case_id: string;
  assumptions: Record<string, AssumptionCell>;
  result: DcfResult;
  warnings: string[];
  stage5_status: string;
  stage4_status: string;
}

export const DCF_ASSUMPTION_LABELS: { key: string; label: string; pct: boolean }[] = [
  { key: "forecast_years", label: "예측기간(년)", pct: false },
  { key: "revenue_growth", label: "매출성장률", pct: true },
  { key: "ebit_margin", label: "영업이익률", pct: true },
  { key: "dna_ratio", label: "D&A/매출", pct: true },
  { key: "capex_ratio", label: "CAPEX/매출", pct: true },
  { key: "nwc_ratio", label: "운전자본/매출", pct: true },
  { key: "terminal_growth", label: "영구성장률", pct: true },
  { key: "tax", label: "법인세율", pct: true },
  { key: "non_operating_assets", label: "비영업자산 조정(백만원)", pct: false },
  { key: "wacc", label: "WACC", pct: true },
  { key: "net_debt", label: "순차입금(백만원)", pct: false },
  { key: "shares", label: "상장주식수", pct: false },
];

export interface Stage6ReviewData {
  case_id: string;
  peers: Record<string, number | string | null>[];
  summaries: Record<string, { median: number | null; n: number; removed: number[] }>;
  reps: Record<string, { value: number | null; overridden: boolean; rationale: string | null }>;
  applied: Record<string, { multiple: number; equity_value: number; per_share: number | null }>;
  range: { min: number | null; median: number | null; max: number | null };
  warnings: string[];
  stage6_status: string;
  stage5_status: string;
}

export const MARKET_METHODS: { key: string; label: string }[] = [
  { key: "ev_ebitda", label: "EV/EBITDA" },
  { key: "per", label: "PER" },
  { key: "pbr", label: "PBR" },
];

export interface AssetAdjustmentRow {
  id: number;
  label: string;
  amount: number;
  rationale: string | null;
  source: string;
}

export interface AssetResultData {
  book_equity: number;
  adjustments_total: number;
  adjusted_net_asset: number;
  control_premium_rate: number;
  value_with_premium: number;
  per_share: number | null;
  adjustments: AssetAdjustmentRow[];
}

export interface Stage7ReviewData {
  case_id: string;
  result: AssetResultData;
  premium_overridden: boolean;
  stage7_status: string;
  stage6_status: string;
}

export interface McStats {
  n_valid: number;
  n_total: number;
  mean: number;
  median: number;
  std: number;
  p10: number;
  p50: number;
  p90: number;
  min: number;
  max: number;
  histogram: { counts: number[]; edges: number[] };
  tornado: { var: string; low: number; high: number; swing: number }[];
}

export interface Stage8ReviewData {
  case_id: string;
  stats: McStats;
  distributions: Record<string, { mean: number; sigma: number; overridden: boolean }>;
  warnings: string[];
  stage8_status: string;
  stage5_status: string;
}

export const MC_VAR_LABELS: Record<string, string> = {
  revenue_growth: "매출성장률",
  ebit_margin: "영업이익률",
  wacc: "WACC",
  terminal_growth: "영구성장률",
  capex_ratio: "CAPEX/매출",
  nwc_ratio: "운전자본/매출",
};

export interface ReviewFlag {
  key: string;
  triggered: boolean;
  severity: string;
  description: string;
  value: number | null;
  threshold: number | null;
}

export interface FinalPayload {
  method_values: { income: number | null; asset: number | null; market: number | null };
  market_range: { min: number | null; median: number | null; max: number | null };
  purpose: string;
  purpose_label: string;
  synthesis: {
    mode: string;
    final: number | null;
    value_in_use?: number | null;
    fair_value?: number | null;
    recoverable_amount?: number | null;
    weights?: Record<string, number>;
    net_asset_floor_applied?: boolean;
  };
  flags: ReviewFlag[];
  flag_approvals: Record<string, { by: string; note: string }>;
}

export interface Stage9ReviewData {
  case_id: string;
  final: FinalPayload;
  weights_editable: boolean;
  stage9_status: string;
  stage5_status: string;
}

export interface FootballFieldRow {
  method: string;
  low: number | null;
  base: number | null;
  high: number | null;
}

export interface SummaryData {
  case_id: string;
  corp_name: string;
  valuation_date: string;
  purpose_label: string | null;
  football_field: FootballFieldRow[];
  final_value: number | null;
  synthesis: { mode?: string; final?: number | null };
  flags: ReviewFlag[];
  flag_approvals: Record<string, { by: string; note: string }>;
  stage_status: Record<number, string>;
}

export interface LineageRow {
  field_name: string;
  value: number | null;
  source_type: string;
  source_ref: string | null;
  rationale: string | null;
  changed_by: string | null;
}

export const METHOD_LABELS: Record<string, string> = {
  income: "수익가치(DCF)",
  asset: "자산가치",
  market: "시장가치",
};

export const PURPOSES: { key: string; label: string }[] = [
  { key: "impairment", label: "손상검사 (K-IFRS 1036)" },
  { key: "merger_ratio", label: "합병비율 (자본시장법)" },
  { key: "inheritance_gift", label: "상증세법 보충적평가" },
  { key: "general_ma", label: "일반 M&A" },
];
