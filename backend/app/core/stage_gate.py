"""Stage 승인 상태기계 (CLAUDE.md 원칙 1, docs/data_flow.md 원칙 A).

DRAFT → REVIEWED → APPROVED. 승인 전에는 후속 Stage 계산이 잠긴다(API 계층에서 강제).
상위 Stage 입력이 바뀌면 하위 Stage 는 자동으로 DRAFT 로 되돌린다(invalidate_downstream).

세션 트랜잭션은 호출자가 관리(여기서는 flush 만).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import StageState, StageStatus


class InvalidTransition(Exception):
    """허용되지 않은 상태 전이."""


def _get_row(db: Session, case_id: str, stage_no: int) -> StageStatus | None:
    stmt = select(StageStatus).where(
        StageStatus.case_id == case_id, StageStatus.stage_no == stage_no
    )
    return db.execute(stmt).scalar_one_or_none()


def _get_or_create(db: Session, case_id: str, stage_no: int) -> StageStatus:
    row = _get_row(db, case_id, stage_no)
    if row is None:
        row = StageStatus(case_id=case_id, stage_no=stage_no, status=StageState.DRAFT)
        db.add(row)
        db.flush()
    return row


def get_state(db: Session, case_id: str, stage_no: int) -> StageState:
    """현재 상태(행이 없으면 DRAFT)."""
    row = _get_row(db, case_id, stage_no)
    return row.status if row is not None else StageState.DRAFT


def mark_reviewed(db: Session, case_id: str, stage_no: int) -> StageStatus:
    """DRAFT → REVIEWED. 그 외 상태에서 호출하면 InvalidTransition."""
    row = _get_or_create(db, case_id, stage_no)
    if row.status != StageState.DRAFT:
        raise InvalidTransition(
            f"stage {stage_no}: REVIEWED 는 DRAFT 에서만 가능(현재 {row.status.value})"
        )
    row.status = StageState.REVIEWED
    db.flush()
    return row


def approve(db: Session, case_id: str, stage_no: int, approved_by: str) -> StageStatus:
    """REVIEWED → APPROVED. 검토 전 승인은 InvalidTransition."""
    if not approved_by or not approved_by.strip():
        raise ValueError("approved_by 는 필수입니다.")
    row = _get_or_create(db, case_id, stage_no)
    if row.status != StageState.REVIEWED:
        raise InvalidTransition(
            f"stage {stage_no}: APPROVED 는 REVIEWED 에서만 가능(현재 {row.status.value})"
        )
    row.status = StageState.APPROVED
    row.approved_by = approved_by
    row.approved_at = datetime.now(UTC)
    row.invalidated_by = None
    db.flush()
    return row


def invalidate_downstream(db: Session, case_id: str, stage_no: int, reason: str) -> list[int]:
    """stage_no 초과의 모든 하위 Stage 를 DRAFT 로 되돌린다.

    상위 Stage 값이 바뀌었을 때(재수집·오버라이드) 호출한다. 이미 DRAFT 인 stage 는 건드리지 않는다.
    reason 은 원인 field_name 또는 stage 식별자. 되돌린 stage_no 목록을 반환.
    """
    stmt = select(StageStatus).where(
        StageStatus.case_id == case_id,
        StageStatus.stage_no > stage_no,
        StageStatus.status != StageState.DRAFT,
    )
    affected: list[int] = []
    for row in db.execute(stmt).scalars():
        row.status = StageState.DRAFT
        row.approved_by = None
        row.approved_at = None
        row.invalidated_by = reason
        affected.append(row.stage_no)
    db.flush()
    return sorted(affected)
