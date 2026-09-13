"""API 요청/응답 스키마 (pydantic)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CaseCreate(BaseModel):
    company: str = Field(..., description="회사명 또는 종목코드")
    valuation_date: str = Field(..., description="YYYY-MM-DD")
    purpose: str = Field(..., description="rules.PURPOSE_FILES 키")
    created_by: str = Field(default="analyst")


class CaseOut(BaseModel):
    case_id: str
    corp_code: str
    corp_name: str
    stock_code: str | None
    induty_code: str | None
    valuation_date: str
    purpose: str
    purpose_label: str
    currency: str
    unit: str


class StageStatusOut(BaseModel):
    stage_no: int
    status: str
    approved_by: str | None = None
    approved_at: str | None = None
    invalidated_by: str | None = None


class Stage1YearResult(BaseModel):
    year: int
    rows: int
    ok: bool


class Stage1RunOut(BaseModel):
    case_id: str
    corp_name: str
    years: list[int]
    collected: list[Stage1YearResult]


class Cell(BaseModel):
    value: float | None
    source_type: str
    overridden: bool = False
    system_value: float | None = None
    rationale: str | None = None


class Stage2ReviewOut(BaseModel):
    case_id: str
    years: list[int]
    accounts: dict[int, dict[str, Cell]]
    unmapped: dict[int, list[str]]
    warnings: dict[int, list[str]]
    stage2_status: str
    stage1_status: str


class OverrideIn(BaseModel):
    year: int
    account: str
    value: float
    rationale: str
    changed_by: str = Field(default="analyst")


class ApproveIn(BaseModel):
    approved_by: str = Field(default="analyst")


class Stage3RunOut(BaseModel):
    case_id: str
    target: dict
    criteria: dict
    screened: int
    passed: int


class PeerOut(BaseModel):
    corp_code: str
    corp_name: str
    stock_code: str | None
    included: bool
    source: str
    rationale: str | None
    metrics: dict


class Stage3ReviewOut(BaseModel):
    case_id: str
    peers: list[PeerOut]
    target: dict
    stage3_status: str
    stage2_status: str


class PeerToggleIn(BaseModel):
    corp_code: str
    included: bool
    rationale: str


class PeerAddIn(BaseModel):
    company: str
    rationale: str


class Stage4RunOut(BaseModel):
    case_id: str
    peers: list[dict]
    warnings: list[str]
    kd_default: bool


class WaccCell(BaseModel):
    value: float | None
    source_ref: str | None = None
    overridden: bool = False
    system_value: float | None = None
    rationale: str | None = None


class Stage4ReviewOut(BaseModel):
    case_id: str
    components: dict[str, WaccCell]
    stage4_status: str
    stage3_status: str


class WaccOverrideIn(BaseModel):
    component: str
    value: float
    rationale: str
    changed_by: str = Field(default="analyst")


class AssumptionCell(BaseModel):
    value: float | None
    source_ref: str | None = None
    overridden: bool = False
    system_value: float | None = None
    rationale: str | None = None
    editable: bool = False


class Stage5ReviewOut(BaseModel):
    case_id: str
    assumptions: dict[str, AssumptionCell]
    result: dict
    warnings: list[str]
    stage5_status: str
    stage4_status: str


class DcfOverrideIn(BaseModel):
    name: str
    value: float
    rationale: str
    changed_by: str = Field(default="analyst")


class Stage6ReviewOut(BaseModel):
    case_id: str
    peers: list[dict]
    summaries: dict
    reps: dict
    applied: dict
    range: dict
    warnings: list[str]
    stage6_status: str
    stage5_status: str


class MarketOverrideIn(BaseModel):
    method: str
    value: float
    rationale: str
    changed_by: str = Field(default="analyst")


class Stage7ReviewOut(BaseModel):
    case_id: str
    result: dict
    premium_overridden: bool
    stage7_status: str
    stage6_status: str


class AssetAdjustmentIn(BaseModel):
    label: str
    amount: float
    rationale: str


class PremiumOverrideIn(BaseModel):
    value: float
    rationale: str
    changed_by: str = Field(default="analyst")


class Stage8ReviewOut(BaseModel):
    case_id: str
    stats: dict
    distributions: dict
    warnings: list[str]
    stage8_status: str
    stage5_status: str


class McSigmaOverrideIn(BaseModel):
    var: str
    sigma: float
    rationale: str
    changed_by: str = Field(default="analyst")


class Stage9ReviewOut(BaseModel):
    case_id: str
    final: dict
    weights_editable: bool
    stage9_status: str
    stage5_status: str


class WeightOverrideIn(BaseModel):
    method: str
    value: float
    rationale: str
    changed_by: str = Field(default="analyst")


class FlagAckIn(BaseModel):
    key: str
    note: str
    by: str = Field(default="analyst")
