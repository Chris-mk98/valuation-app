"""출처 기록·전문가 오버라이드 (CLAUDE.md 원칙 2·4, docs/data_flow.md §6).

- 어떤 숫자도 source_type 없이 저장하지 않는다.
- 시스템이 채운 파생값 덮어쓰기는 반드시 record_override() 로만 처리하고, 사유(rationale) 필수.
- 🌐 원본 데이터는 이 모듈로 수정하지 않는다(원본 보존은 sources/ 캐시가 담당).

세션 트랜잭션은 호출자가 관리한다(여기서는 flush 만). API 계층에서 commit.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Lineage, SourceType


class RationaleRequiredError(ValueError):
    """오버라이드 시 사유가 비어 있을 때."""


def get_field(db: Session, case_id: str, field_name: str) -> Lineage | None:
    """(case_id, field_name) 현재 lineage 행을 반환(없으면 None)."""
    stmt = select(Lineage).where(
        Lineage.case_id == case_id, Lineage.field_name == field_name
    )
    return db.execute(stmt).scalar_one_or_none()


def record_value(
    db: Session,
    *,
    case_id: str,
    field_name: str,
    value: float | None,
    source_type: SourceType,
    source_ref: str | None = None,
    retrieved_at: datetime | None = None,
    derived_from: list[str] | None = None,
) -> Lineage:
    """값 1건을 출처와 함께 기록(upsert). (case_id, field_name) 당 1행.

    EXPERT_OVERRIDE 는 이 함수로 저장할 수 없다 — record_override() 를 사용한다.
    """
    if source_type == SourceType.EXPERT_OVERRIDE:
        raise ValueError("EXPERT_OVERRIDE 는 record_override() 로만 기록하세요.")

    row = get_field(db, case_id, field_name)
    if row is None:
        row = Lineage(case_id=case_id, field_name=field_name)
        db.add(row)

    row.value = value
    row.source_type = source_type
    row.source_ref = source_ref
    row.retrieved_at = retrieved_at
    row.derived_from = derived_from if source_type == SourceType.DERIVED else None
    # 시스템 기록이므로 오버라이드 관련 필드는 비운다
    row.system_value = None
    row.rationale = None
    row.changed_by = None
    row.prev_value = None
    row.changed_at = None

    db.flush()
    return row


def record_override(
    db: Session,
    *,
    case_id: str,
    field_name: str,
    value: float | None,
    rationale: str,
    changed_by: str,
    system_value: float | None = None,
    source_ref: str | None = None,
) -> Lineage:
    """시스템이 채운 파생값을 전문가 판단으로 덮어쓴다(사유 필수).

    - source_type = EXPERT_OVERRIDE
    - system_value: 시스템 제안값(미지정 시 직전 값으로 자동 설정)
    - prev_value / changed_by / changed_at 로 덮어쓰기 이력 기록
    """
    if rationale is None or not rationale.strip():
        raise RationaleRequiredError("오버라이드에는 사유(rationale)가 필요합니다.")

    row = get_field(db, case_id, field_name)
    prev = row.value if row is not None else None
    if system_value is None:
        # 직전 시스템 제안값을 보존(기존 오버라이드 위에 재오버라이드하면 최초 system_value 유지)
        system_value = row.system_value if (row and row.system_value is not None) else prev

    if row is None:
        row = Lineage(case_id=case_id, field_name=field_name)
        db.add(row)

    row.value = value
    row.source_type = SourceType.EXPERT_OVERRIDE
    row.source_ref = source_ref
    row.system_value = system_value
    row.rationale = rationale
    row.changed_by = changed_by
    row.prev_value = prev
    row.changed_at = datetime.now(UTC)

    db.flush()
    return row


def get_lineage(db: Session, case_id: str) -> list[Lineage]:
    """케이스의 모든 lineage 행(field_name 정렬). 리포트 '데이터 출처' 표의 원천."""
    stmt = select(Lineage).where(Lineage.case_id == case_id).order_by(Lineage.field_name)
    return list(db.execute(stmt).scalars())
