"""core/lineage 단위 테스트 — 출처 기록·오버라이드(사유 필수)."""

from __future__ import annotations

import pytest

from app.core import lineage
from app.db.models import SourceType


def test_record_value_creates_row_with_source(db):
    row = lineage.record_value(
        db,
        case_id="c1",
        field_name="risk_free_rate",
        value=3.25,
        source_type=SourceType.API,
        source_ref="ECOS/817Y002?date=2026-09-12",
    )
    assert row.value == pytest.approx(3.25, abs=1e-6)
    assert row.source_type == SourceType.API
    assert row.source_ref.startswith("ECOS")


def test_record_value_rejects_override_source(db):
    with pytest.raises(ValueError, match="record_override"):
        lineage.record_value(
            db,
            case_id="c1",
            field_name="wacc",
            value=0.1,
            source_type=SourceType.EXPERT_OVERRIDE,
        )


def test_record_value_upserts_same_field(db):
    lineage.record_value(
        db, case_id="c1", field_name="ebit", value=100.0, source_type=SourceType.DERIVED,
        derived_from=["revenue", "opex"],
    )
    lineage.record_value(
        db, case_id="c1", field_name="ebit", value=120.0, source_type=SourceType.DERIVED,
        derived_from=["revenue", "opex"],
    )
    rows = lineage.get_lineage(db, "c1")
    assert len(rows) == 1
    assert rows[0].value == pytest.approx(120.0, abs=1e-6)
    assert rows[0].derived_from == ["revenue", "opex"]


def test_record_override_without_rationale_raises(db):
    lineage.record_value(
        db, case_id="c1", field_name="terminal_growth", value=0.02,
        source_type=SourceType.DERIVED,
    )
    with pytest.raises(lineage.RationaleRequiredError):
        lineage.record_override(
            db, case_id="c1", field_name="terminal_growth", value=0.015,
            rationale="   ", changed_by="analyst1",
        )


def test_record_override_records_prev_and_system_value(db):
    lineage.record_value(
        db, case_id="c1", field_name="terminal_growth", value=0.02,
        source_type=SourceType.DERIVED,
    )
    row = lineage.record_override(
        db, case_id="c1", field_name="terminal_growth", value=0.015,
        rationale="명목GDP 대비 보수적 적용", changed_by="analyst1",
    )
    assert row.source_type == SourceType.EXPERT_OVERRIDE
    assert row.value == pytest.approx(0.015, abs=1e-6)
    assert row.prev_value == pytest.approx(0.02, abs=1e-6)
    assert row.system_value == pytest.approx(0.02, abs=1e-6)  # 직전 값이 시스템 제안값
    assert row.changed_by == "analyst1"
    assert row.changed_at is not None


def test_reoverride_preserves_original_system_value(db):
    lineage.record_value(
        db, case_id="c1", field_name="kd", value=0.05, source_type=SourceType.DERIVED,
    )
    lineage.record_override(
        db, case_id="c1", field_name="kd", value=0.045,
        rationale="1차 조정", changed_by="a",
    )
    row = lineage.record_override(
        db, case_id="c1", field_name="kd", value=0.048,
        rationale="2차 조정", changed_by="a",
    )
    # 시스템 제안값은 최초 시스템 값(0.05)을 유지, prev_value 는 직전 오버라이드(0.045)
    assert row.system_value == pytest.approx(0.05, abs=1e-6)
    assert row.prev_value == pytest.approx(0.045, abs=1e-6)


def test_get_lineage_scoped_by_case(db):
    lineage.record_value(db, case_id="c1", field_name="a", value=1.0, source_type=SourceType.USER)
    lineage.record_value(db, case_id="c2", field_name="a", value=2.0, source_type=SourceType.USER)
    assert len(lineage.get_lineage(db, "c1")) == 1
    assert lineage.get_lineage(db, "c1")[0].value == pytest.approx(1.0, abs=1e-6)
