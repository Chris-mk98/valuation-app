"""API 공용 의존성."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import Case
from app.db.session import get_db  # re-export

__all__ = ["get_db", "get_case_or_404"]


def get_case_or_404(db: Session, case_id: str) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"케이스 없음: {case_id}")
    return case
