"""케이스 라우터 (Stage 0 · 스테퍼 상태)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import service
from app.api.deps import get_case_or_404, get_db
from app.api.schemas import CaseCreate, CaseOut, StageStatusOut
from app.core import rules, stage_gate
from app.sources.dart import DartError

router = APIRouter(prefix="/api/cases", tags=["cases"])

TOTAL_STAGES = 10


def _case_out(db: Session, case) -> CaseOut:
    label = rules.load_rules(case.purpose)["label"]
    return CaseOut(
        case_id=case.case_id, corp_code=case.corp_code, corp_name=case.corp_name,
        stock_code=case.stock_code, induty_code=case.induty_code,
        valuation_date=case.valuation_date, purpose=case.purpose, purpose_label=label,
        currency=case.currency, unit=case.unit,
    )


@router.post("", response_model=CaseOut)
def create_case(body: CaseCreate, db: Session = Depends(get_db)) -> CaseOut:
    try:
        case = service.create_case(db, company=body.company, valuation_date=body.valuation_date,
                                   purpose=body.purpose, created_by=body.created_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except DartError as e:
        raise HTTPException(status_code=502, detail=f"DART 조회 실패: {e}") from e
    db.commit()
    return _case_out(db, case)


@router.get("/{case_id}", response_model=CaseOut)
def get_case(case_id: str, db: Session = Depends(get_db)) -> CaseOut:
    return _case_out(db, get_case_or_404(db, case_id))


@router.get("/{case_id}/stages", response_model=list[StageStatusOut])
def list_stage_status(case_id: str, db: Session = Depends(get_db)) -> list[StageStatusOut]:
    get_case_or_404(db, case_id)
    from app.db.models import StageStatus
    rows = {s.stage_no: s for s in db.query(StageStatus).filter_by(case_id=case_id)}
    out = []
    for n in range(0, TOTAL_STAGES + 1):
        r = rows.get(n)
        if r is None:
            out.append(StageStatusOut(stage_no=n, status=stage_gate.StageState.DRAFT.value))
        else:
            out.append(StageStatusOut(
                stage_no=n, status=r.status.value, approved_by=r.approved_by,
                approved_at=r.approved_at.isoformat() if r.approved_at else None,
                invalidated_by=r.invalidated_by,
            ))
    return out
