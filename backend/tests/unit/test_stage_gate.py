"""core/stage_gate 단위 테스트 — 상태기계·하위 무효화."""

from __future__ import annotations

import pytest

from app.core import stage_gate
from app.db.models import StageState


def test_default_state_is_draft(db):
    assert stage_gate.get_state(db, "c1", 1) == StageState.DRAFT


def test_review_then_approve(db):
    stage_gate.mark_reviewed(db, "c1", 1)
    assert stage_gate.get_state(db, "c1", 1) == StageState.REVIEWED
    row = stage_gate.approve(db, "c1", 1, approved_by="analyst1")
    assert row.status == StageState.APPROVED
    assert row.approved_by == "analyst1"
    assert row.approved_at is not None


def test_approve_without_review_raises(db):
    with pytest.raises(stage_gate.InvalidTransition):
        stage_gate.approve(db, "c1", 1, approved_by="analyst1")


def test_approve_requires_approver(db):
    stage_gate.mark_reviewed(db, "c1", 1)
    with pytest.raises(ValueError):
        stage_gate.approve(db, "c1", 1, approved_by="")


def test_review_only_from_draft(db):
    stage_gate.mark_reviewed(db, "c1", 1)
    stage_gate.approve(db, "c1", 1, approved_by="a")
    with pytest.raises(stage_gate.InvalidTransition):
        stage_gate.mark_reviewed(db, "c1", 1)


def test_invalidate_downstream_resets_lower_stages(db):
    # Stage 1, 2 승인
    for s in (1, 2):
        stage_gate.mark_reviewed(db, "c1", s)
        stage_gate.approve(db, "c1", s, approved_by="a")

    # Stage 1 입력이 바뀌어 하위 무효화
    affected = stage_gate.invalidate_downstream(db, "c1", 1, reason="financials_normalized")
    assert affected == [2]
    assert stage_gate.get_state(db, "c1", 1) == StageState.APPROVED  # 자신은 유지
    assert stage_gate.get_state(db, "c1", 2) == StageState.DRAFT

    row2 = stage_gate._get_row(db, "c1", 2)
    assert row2.invalidated_by == "financials_normalized"
    assert row2.approved_by is None


def test_invalidate_skips_already_draft(db):
    stage_gate.mark_reviewed(db, "c1", 2)
    stage_gate.approve(db, "c1", 2, approved_by="a")
    # stage 3 은 행이 없어 암묵적 DRAFT → 되돌릴 것 없음
    affected = stage_gate.invalidate_downstream(db, "c1", 1, reason="x")
    assert affected == [2]


def test_stage_status_scoped_by_case(db):
    stage_gate.mark_reviewed(db, "c1", 1)
    assert stage_gate.get_state(db, "c2", 1) == StageState.DRAFT
