"""Excel 다운로드/업로드 라우터 (CLAUDE.md 원칙 3)."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api import service
from app.api.deps import get_case_or_404, get_db
from app.excel import exporters, importers, templates
from app.params.account_map import load_account_map

router = APIRouter(prefix="/api", tags=["excel"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(data: bytes, filename: str) -> Response:
    # RFC 5987: 비ASCII(한글) 파일명을 헤더에 안전하게 인코딩
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return Response(content=data, media_type=XLSX,
                    headers={"Content-Disposition": disposition})


@router.get("/cases/{case_id}/stages/1/download")
def download_stage1(case_id: str, db: Session = Depends(get_db)) -> Response:
    case = get_case_or_404(db, case_id)
    years = service.fiscal_years(case.valuation_date)
    raw = service._raw_by_year(db, case, years)
    return _xlsx(exporters.stage1_raw_dump(raw), f"{case.corp_name}_stage1_raw.xlsx")


@router.get("/cases/{case_id}/stages/2/download")
def download_stage2(case_id: str, db: Session = Depends(get_db)) -> Response:
    case = get_case_or_404(db, case_id)
    try:
        review = service.review_stage2(db, case)
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    db.commit()
    normalized = {
        "years": review["years"],
        "accounts": {y: {a: c["value"] for a, c in accs.items()}
                     for y, accs in review["accounts"].items()},
        "unmapped": review["unmapped"],
        "warnings": review["warnings"],
    }
    return _xlsx(exporters.stage2_normalized(normalized), f"{case.corp_name}_stage2_norm.xlsx")


@router.get("/cases/{case_id}/stages/3/download")
def download_stage3(case_id: str, db: Session = Depends(get_db)) -> Response:
    case = get_case_or_404(db, case_id)
    review = service.review_stage3(db, case)
    return _xlsx(exporters.stage3_candidates(review["peers"]), f"{case.corp_name}_stage3_peers.xlsx")


@router.get("/cases/{case_id}/stages/4/download")
def download_stage4(case_id: str, db: Session = Depends(get_db)) -> Response:
    case = get_case_or_404(db, case_id)
    review = service.review_stage4(db, case)
    return _xlsx(exporters.stage4_wacc(review["components"]), f"{case.corp_name}_stage4_wacc.xlsx")


@router.get("/cases/{case_id}/stages/5/download")
def download_stage5(case_id: str, db: Session = Depends(get_db)) -> Response:
    case = get_case_or_404(db, case_id)
    review = service.review_stage5(db, case)
    return _xlsx(exporters.stage5_dcf(review), f"{case.corp_name}_stage5_dcf.xlsx")


@router.get("/cases/{case_id}/stages/6/download")
def download_stage6(case_id: str, db: Session = Depends(get_db)) -> Response:
    case = get_case_or_404(db, case_id)
    review = service.review_stage6(db, case)
    return _xlsx(exporters.stage6_multiples(review), f"{case.corp_name}_stage6_multiples.xlsx")


@router.get("/stages/6/transactions-template")
def transactions_template() -> Response:
    return _xlsx(exporters.transactions_template(), "transactions_template.xlsx")


@router.post("/stages/6/transactions-upload")
async def transactions_upload(file: UploadFile) -> dict:
    """거래사례 업로드 검증 + 중앙값 배수(별도 트랙, 미영속)."""
    content = await file.read()
    try:
        txns, errors = importers.parse_transactions(content)
    except importers.ImportError_ as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    mults = sorted(t["multiple"] for t in txns)
    median = mults[len(mults) // 2] if mults else None
    return {"valid": len(errors) == 0, "errors": errors, "count": len(txns),
            "median_multiple": median, "transactions": txns}


@router.get("/cases/{case_id}/stages/7/download")
def download_stage7(case_id: str, db: Session = Depends(get_db)) -> Response:
    case = get_case_or_404(db, case_id)
    review = service.review_stage7(db, case)
    return _xlsx(exporters.stage7_asset(review), f"{case.corp_name}_stage7_asset.xlsx")


@router.get("/stages/7/adjustments-template")
def adjustments_template() -> Response:
    return _xlsx(exporters.adjustments_template(), "asset_adjustments_template.xlsx")


@router.post("/cases/{case_id}/stages/7/adjustments-upload")
async def adjustments_upload(case_id: str, file: UploadFile,
                            db: Session = Depends(get_db)) -> dict:
    """자산조정 업로드 → 검증 후 케이스에 반영(source=EXCEL_UPLOAD)."""
    case = get_case_or_404(db, case_id)
    content = await file.read()
    try:
        adjustments, errors = importers.parse_adjustments(content)
    except importers.ImportError_ as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if errors:
        return {"valid": False, "errors": errors, "applied": 0}
    for a in adjustments:
        service.add_asset_adjustment(db, case, label=a["label"], amount=a["amount"],
                                     rationale=a["rationale"], source="EXCEL_UPLOAD")
    db.commit()
    return {"valid": True, "errors": [], "applied": len(adjustments)}


@router.get("/cases/{case_id}/stages/8/download")
def download_stage8(case_id: str, db: Session = Depends(get_db)) -> Response:
    case = get_case_or_404(db, case_id)
    review = service.review_stage8(db, case)
    return _xlsx(exporters.stage8_montecarlo(review), f"{case.corp_name}_stage8_mc.xlsx")


@router.get("/cases/{case_id}/stages/9/download")
def download_stage9(case_id: str, db: Session = Depends(get_db)) -> Response:
    case = get_case_or_404(db, case_id)
    review = service.review_stage9(db, case)
    return _xlsx(exporters.stage9_final(review["final"]), f"{case.corp_name}_stage9_final.xlsx")


@router.get("/stages/2/mapping-template")
def mapping_template() -> Response:
    return _xlsx(templates.account_map_template(load_account_map()), "account_map_template.xlsx")


@router.post("/stages/2/mapping-upload")
async def mapping_upload(file: UploadFile) -> dict:
    """계정 매핑표 업로드 검증. 오류를 셀 단위로 반환(현재는 검증만, 미영속)."""
    content = await file.read()
    try:
        mapping, errors = importers.parse_account_map(content)
    except importers.ImportError_ as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "targets": len(mapping.get("targets", {})),
        "components": len(mapping.get("components", {})),
        "note": "검증 완료(현 버전은 케이스에 영속하지 않음).",
    }
