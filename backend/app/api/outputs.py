"""Stage 10 · 산출물 라우터 — 풋볼필드 요약·감사추적(웹/CSV)·케이스 JSON·워크북·리포트."""

from __future__ import annotations

import csv
import io
import json
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.api import service
from app.api.deps import get_case_or_404, get_db
from app.excel import exporters
from app.reports import report

router = APIRouter(prefix="/api/cases", tags=["outputs"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _attach(data: bytes, filename: str, media: str) -> Response:
    return Response(content=data, media_type=media,
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})


@router.get("/{case_id}/summary")
def summary(case_id: str, db: Session = Depends(get_db)) -> dict:
    return service.stage10_summary(db, get_case_or_404(db, case_id))


@router.get("/{case_id}/lineage")
def lineage(case_id: str, db: Session = Depends(get_db)) -> list[dict]:
    return service.lineage_rows(db, get_case_or_404(db, case_id))


@router.get("/{case_id}/lineage.csv")
def lineage_csv(case_id: str, db: Session = Depends(get_db)) -> Response:
    case = get_case_or_404(db, case_id)
    rows = service.lineage_rows(db, case)
    buf = io.StringIO()
    cols = ["field_name", "value", "source_type", "source_ref", "retrieved_at",
            "system_value", "rationale", "changed_by", "prev_value", "changed_at"]
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)
    return _attach(buf.getvalue().encode("utf-8-sig"), f"{case.corp_name}_lineage.csv",
                   "text/csv; charset=utf-8")


@router.get("/{case_id}/export.json")
def export_json(case_id: str, db: Session = Depends(get_db)) -> Response:
    case = get_case_or_404(db, case_id)
    data = json.dumps(service.export_case_json(db, case), ensure_ascii=False, indent=2)
    return _attach(data.encode("utf-8"), f"{case.corp_name}_case.json", "application/json")


@router.get("/{case_id}/workbook")
def workbook(case_id: str, db: Session = Depends(get_db)) -> Response:
    case = get_case_or_404(db, case_id)
    cj = service.export_case_json(db, case)
    summ = service.stage10_summary(db, case)
    return _attach(exporters.full_workbook(cj, summ), f"{case.corp_name}_workbook.xlsx", XLSX)


@router.get("/{case_id}/report")
def report_html(case_id: str, db: Session = Depends(get_db)) -> HTMLResponse:
    case = get_case_or_404(db, case_id)
    cj = service.export_case_json(db, case)
    summ = service.stage10_summary(db, case)
    return HTMLResponse(content=report.render_report(cj, summ))
