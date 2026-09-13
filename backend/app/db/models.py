"""SQLAlchemy 모델.

docs/data_flow.md §6(감사추적 스키마)·§7(저장 구조)에 맞춘 횡단 테이블을 정의한다.
스켈레톤 이후 2단계: lineage · stage_status. 소스 원본/정규화/케이스 테이블은 3단계에서 추가.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """모든 ORM 모델의 공통 베이스."""

    pass


class SourceType(enum.StrEnum):
    """lineage 출처 유형 (CLAUDE.md 원칙 4). 이 6종 외의 값은 저장 금지."""

    USER = "USER"
    API = "API"
    PARAM_TABLE = "PARAM_TABLE"
    DERIVED = "DERIVED"
    EXPERT_OVERRIDE = "EXPERT_OVERRIDE"
    EXCEL_UPLOAD = "EXCEL_UPLOAD"


class StageState(enum.StrEnum):
    """Stage 승인 상태기계 (docs/data_flow.md 원칙 A)."""

    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Lineage(Base):
    """모든 숫자에 붙는 출처 메타데이터 (docs/data_flow.md §6).

    (case_id, field_name) 당 현재 값 1행. 전문가 오버라이드 시 prev_value/system_value/
    rationale/changed_by/changed_at 를 채운다.
    """

    __tablename__ = "lineage"
    __table_args__ = (UniqueConstraint("case_id", "field_name", name="uq_lineage_case_field"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    field_name: Mapped[str] = mapped_column(String, nullable=False)

    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_type: Mapped[SourceType] = mapped_column(SAEnum(SourceType), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # DERIVED 인 경우 상위 field_name 목록
    derived_from: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # EXPERT_OVERRIDE 인 경우
    system_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    rationale: Mapped[str | None] = mapped_column(String, nullable=True)

    # 사용자 덮어쓰기 이력
    changed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    prev_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class StageStatus(Base):
    """Stage별 승인 상태 (docs/data_flow.md §6).

    상위 Stage 입력이 바뀌면 하위 Stage 는 자동으로 DRAFT 로 되돌린다(invalidated_by 기록).
    """

    __tablename__ = "stage_status"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    stage_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[StageState] = mapped_column(
        SAEnum(StageState), default=StageState.DRAFT, nullable=False
    )
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 상위 Stage 변경으로 되돌려진 경우 원인 (field_name 또는 stage 식별자)
    invalidated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class Case(Base):
    """평가 케이스 (Stage 0 · docs/data_flow.md §4). 목적별 제약세트를 결정."""

    __tablename__ = "cases"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    corp_code: Mapped[str] = mapped_column(String, nullable=False)  # DART 8자리
    corp_name: Mapped[str] = mapped_column(String, nullable=False)
    stock_code: Mapped[str | None] = mapped_column(String, nullable=True)
    induty_code: Mapped[str | None] = mapped_column(String, nullable=True)
    valuation_date: Mapped[str] = mapped_column(String, nullable=False)  # YYYY-MM-DD
    purpose: Mapped[str] = mapped_column(String, nullable=False)  # rules.PURPOSE_FILES 키
    currency: Mapped[str] = mapped_column(String, default="KRW", nullable=False)
    unit: Mapped[str] = mapped_column(String, default="백만원", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class RawDart(Base):
    """DART 원본 응답 캐시 (🌐 원본 보존, 재호출 금지). 자연키로 재사용."""

    __tablename__ = "raw_dart"
    __table_args__ = (
        UniqueConstraint(
            "corp_code", "doc_type", "bsns_year", "reprt_code", "fs_div",
            name="uq_raw_dart_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    corp_code: Mapped[str] = mapped_column(String, index=True, nullable=False)
    doc_type: Mapped[str] = mapped_column(String, nullable=False)  # company | financials
    bsns_year: Mapped[str | None] = mapped_column(String, nullable=True)
    reprt_code: Mapped[str | None] = mapped_column(String, nullable=True)
    fs_div: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)  # 원본 JSON 그대로
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class RawEcos(Base):
    """ECOS 원본 응답 캐시 (기준일 단위)."""

    __tablename__ = "raw_ecos"
    __table_args__ = (
        UniqueConstraint("stat_code", "item_code", "cycle", "date", name="uq_raw_ecos_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stat_code: Mapped[str] = mapped_column(String, nullable=False)
    item_code: Mapped[str] = mapped_column(String, nullable=False)
    cycle: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ApiCallLog(Base):
    """외부 API 호출 로그 (일일 한도 관리 · docs/data_flow.md §7). 캐시 히트도 기록."""

    __tablename__ = "api_call_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String, nullable=False)  # DART | ECOS | PRICE
    endpoint: Mapped[str] = mapped_column(String, nullable=False)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 인증키 제거 후 저장
    status: Mapped[str | None] = mapped_column(String, nullable=True)  # 응답 status/코드
    message: Mapped[str | None] = mapped_column(String, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Integer, default=0, nullable=False)
    called_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class FinancialsNormalized(Base):
    """정규화 재무 (case × year × account · docs/data_flow.md §7). Stage 2 산출·검토 대상."""

    __tablename__ = "financials_normalized"
    __table_args__ = (
        UniqueConstraint("case_id", "year", "account", name="uq_fin_norm_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    account: Mapped[str] = mapped_column(String, nullable=False)  # 내부계정 키
    value: Mapped[float | None] = mapped_column(Float, nullable=True)  # 백만원
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class RawPrice(Base):
    """KRX 주가/지수 원본 캐시 (종목·기간 단위). 스크래핑 차단 시 CSV 업로드 폴백(§8)."""

    __tablename__ = "raw_price"
    __table_args__ = (
        UniqueConstraint("code", "start", "end", "kind", name="uq_raw_price_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, index=True, nullable=False)
    start: Mapped[str] = mapped_column(String, nullable=False)
    end: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, default="ohlcv", nullable=False)  # ohlcv | index
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)  # [{date, close}]
    source: Mapped[str] = mapped_column(String, default="FDR", nullable=False)  # FDR | CSV
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Peer(Base):
    """유사기업 후보/확정 (case × corp · docs/data_flow.md §7). 포함여부 + 사유."""

    __tablename__ = "peers"
    __table_args__ = (UniqueConstraint("case_id", "corp_code", name="uq_peer_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    corp_code: Mapped[str] = mapped_column(String, nullable=False)
    corp_name: Mapped[str] = mapped_column(String, nullable=False)
    stock_code: Mapped[str | None] = mapped_column(String, nullable=True)
    included: Mapped[bool] = mapped_column(Integer, default=0, nullable=False)
    source: Mapped[str] = mapped_column(String, default="SCREEN", nullable=False)  # SCREEN | MANUAL
    rationale: Mapped[str | None] = mapped_column(String, nullable=True)  # 포함/제외 사유(필수 기록)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # 지표·필터 결과
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class WaccBuild(Base):
    """WACC 구성요소 빌드업 (case × component · docs/data_flow.md §4)."""

    __tablename__ = "wacc_build"
    __table_args__ = (UniqueConstraint("case_id", "component", name="uq_wacc_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    component: Mapped[str] = mapped_column(String, nullable=False)  # rf, beta_u, ke, kd, wacc ...
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class DcfAssumption(Base):
    """DCF 예측 가정 (case × name · docs/data_flow.md §5). 오버라이드 대상."""

    __tablename__ = "dcf_assumptions"
    __table_args__ = (UniqueConstraint("case_id", "name", name="uq_dcf_assumption_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)  # revenue_growth, ebit_margin ...
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class DcfResult(Base):
    """DCF 산출 결과 (case 단위 · docs/data_flow.md §5). 연도별 FCFF·EV·주주가치 등 JSON."""

    __tablename__ = "dcf_result"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class MarketResult(Base):
    """시장접근법 결과 (case 단위 · docs/data_flow.md §6). 멀티플 테이블·적용가치 JSON."""

    __tablename__ = "market_result"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class AssetAdjustment(Base):
    """자산접근 순자산 조정항목 (case × 항목 · docs/data_flow.md §7). 사유 필수 기록."""

    __tablename__ = "asset_adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)  # 백만원, 부호 포함
    rationale: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, default="USER", nullable=False)  # USER | EXCEL_UPLOAD
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class AssetResult(Base):
    """자산접근법 결과 (case 단위). 조정순자산·할증·주당가치 JSON."""

    __tablename__ = "asset_result"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class McDistribution(Base):
    """몬테카를로 변수별 분포 σ (case × var · docs/data_flow.md §8). 오버라이드 대상."""

    __tablename__ = "mc_distributions"
    __table_args__ = (UniqueConstraint("case_id", "var", name="uq_mc_dist_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    var: Mapped[str] = mapped_column(String, nullable=False)
    sigma: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class McResult(Base):
    """몬테카를로 결과 (case 단위). 분포 통계·히스토그램·토네이도 JSON."""

    __tablename__ = "mc_result"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class FinalValue(Base):
    """Stage 9 목적별 종합 결과 (case 단위 · docs/data_flow.md §9).

    방법론별 가치·가중·최종범위·레드플래그·플래그 승인내역 JSON.
    """

    __tablename__ = "final_value"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
