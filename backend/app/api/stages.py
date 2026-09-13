"""Stage 실행·검토·승인·오버라이드 라우터."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import service
from app.api.deps import get_case_or_404, get_db
from app.api.schemas import (
    ApproveIn,
    AssetAdjustmentIn,
    AssumptionCell,
    Cell,
    DcfOverrideIn,
    FlagAckIn,
    MarketOverrideIn,
    McSigmaOverrideIn,
    OverrideIn,
    PeerAddIn,
    PeerToggleIn,
    PremiumOverrideIn,
    Stage1RunOut,
    Stage2ReviewOut,
    Stage3ReviewOut,
    Stage3RunOut,
    Stage4ReviewOut,
    Stage4RunOut,
    Stage5ReviewOut,
    Stage6ReviewOut,
    Stage7ReviewOut,
    Stage8ReviewOut,
    Stage9ReviewOut,
    WaccCell,
    WaccOverrideIn,
    WeightOverrideIn,
)
from app.core.lineage import RationaleRequiredError
from app.core.stage_gate import InvalidTransition
from app.sources.dart import DartError

router = APIRouter(prefix="/api/cases", tags=["stages"])


@router.post("/{case_id}/stages/1/run", response_model=Stage1RunOut)
def run_stage1(case_id: str, db: Session = Depends(get_db)) -> Stage1RunOut:
    case = get_case_or_404(db, case_id)
    try:
        res = service.run_stage1(db, case)
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except DartError as e:
        raise HTTPException(status_code=502, detail=f"DART 조회 실패: {e}") from e
    db.commit()
    return Stage1RunOut(**res)


@router.get("/{case_id}/stages/2/review", response_model=Stage2ReviewOut)
def review_stage2(case_id: str, db: Session = Depends(get_db)) -> Stage2ReviewOut:
    case = get_case_or_404(db, case_id)
    try:
        res = service.review_stage2(db, case)
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    db.commit()
    res["accounts"] = {y: {a: Cell(**c) for a, c in accs.items()}
                       for y, accs in res["accounts"].items()}
    return Stage2ReviewOut(**res)


@router.post("/{case_id}/stages/2/override")
def override_stage2(case_id: str, body: OverrideIn, db: Session = Depends(get_db)) -> dict:
    case = get_case_or_404(db, case_id)
    try:
        res = service.override_stage2(db, case, year=body.year, account=body.account,
                                      value=body.value, rationale=body.rationale,
                                      changed_by=body.changed_by)
    except RationaleRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    db.commit()
    return res


@router.post("/{case_id}/stages/3/run", response_model=Stage3RunOut)
def run_stage3(case_id: str, db: Session = Depends(get_db)) -> Stage3RunOut:
    case = get_case_or_404(db, case_id)
    try:
        res = service.run_stage3(db, case)
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except DartError as e:
        raise HTTPException(status_code=502, detail=f"수집 실패: {e}") from e
    db.commit()
    return Stage3RunOut(**res)


@router.get("/{case_id}/stages/3/review", response_model=Stage3ReviewOut)
def review_stage3(case_id: str, db: Session = Depends(get_db)) -> Stage3ReviewOut:
    case = get_case_or_404(db, case_id)
    return Stage3ReviewOut(**service.review_stage3(db, case))


@router.post("/{case_id}/stages/3/peers/toggle")
def toggle_peer(case_id: str, body: PeerToggleIn, db: Session = Depends(get_db)) -> dict:
    case = get_case_or_404(db, case_id)
    try:
        res = service.set_peer_inclusion(db, case, body.corp_code, body.included, body.rationale)
    except RationaleRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    db.commit()
    return res


@router.post("/{case_id}/stages/3/peers/add")
def add_peer(case_id: str, body: PeerAddIn, db: Session = Depends(get_db)) -> dict:
    case = get_case_or_404(db, case_id)
    try:
        res = service.add_manual_peer(db, case, body.company, body.rationale)
    except RationaleRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except DartError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    db.commit()
    return res


@router.post("/{case_id}/stages/4/run", response_model=Stage4RunOut)
def run_stage4(case_id: str, db: Session = Depends(get_db)) -> Stage4RunOut:
    case = get_case_or_404(db, case_id)
    try:
        res = service.run_stage4(db, case)
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001 - 외부 조회 실패를 502 로 표면화
        raise HTTPException(status_code=502, detail=f"WACC 산출 실패: {e}") from e
    db.commit()
    return Stage4RunOut(**res)


@router.get("/{case_id}/stages/4/review", response_model=Stage4ReviewOut)
def review_stage4(case_id: str, db: Session = Depends(get_db)) -> Stage4ReviewOut:
    case = get_case_or_404(db, case_id)
    res = service.review_stage4(db, case)
    res["components"] = {k: WaccCell(**v) for k, v in res["components"].items()}
    return Stage4ReviewOut(**res)


@router.post("/{case_id}/stages/4/override")
def override_stage4(case_id: str, body: WaccOverrideIn, db: Session = Depends(get_db)) -> dict:
    case = get_case_or_404(db, case_id)
    try:
        res = service.override_stage4(db, case, component=body.component, value=body.value,
                                      rationale=body.rationale, changed_by=body.changed_by)
    except RationaleRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    db.commit()
    return res


@router.post("/{case_id}/stages/5/run", response_model=Stage5ReviewOut)
def run_stage5(case_id: str, db: Session = Depends(get_db)) -> Stage5ReviewOut:
    case = get_case_or_404(db, case_id)
    try:
        res = service.run_stage5(db, case)
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    res["assumptions"] = {k: AssumptionCell(**v) for k, v in res["assumptions"].items()}
    return Stage5ReviewOut(**res)


@router.get("/{case_id}/stages/5/review", response_model=Stage5ReviewOut)
def review_stage5(case_id: str, db: Session = Depends(get_db)) -> Stage5ReviewOut:
    case = get_case_or_404(db, case_id)
    res = service.review_stage5(db, case)
    res["assumptions"] = {k: AssumptionCell(**v) for k, v in res["assumptions"].items()}
    return Stage5ReviewOut(**res)


@router.post("/{case_id}/stages/5/override")
def override_stage5(case_id: str, body: DcfOverrideIn, db: Session = Depends(get_db)) -> dict:
    case = get_case_or_404(db, case_id)
    try:
        res = service.override_stage5(db, case, name=body.name, value=body.value,
                                      rationale=body.rationale, changed_by=body.changed_by)
    except RationaleRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    return res


@router.post("/{case_id}/stages/6/run", response_model=Stage6ReviewOut)
def run_stage6(case_id: str, db: Session = Depends(get_db)) -> Stage6ReviewOut:
    case = get_case_or_404(db, case_id)
    try:
        res = service.run_stage6(db, case)
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"시장접근 산출 실패: {e}") from e
    db.commit()
    return Stage6ReviewOut(**res)


@router.get("/{case_id}/stages/6/review", response_model=Stage6ReviewOut)
def review_stage6(case_id: str, db: Session = Depends(get_db)) -> Stage6ReviewOut:
    case = get_case_or_404(db, case_id)
    return Stage6ReviewOut(**service.review_stage6(db, case))


@router.post("/{case_id}/stages/6/override")
def override_stage6(case_id: str, body: MarketOverrideIn, db: Session = Depends(get_db)) -> dict:
    case = get_case_or_404(db, case_id)
    try:
        res = service.override_stage6(db, case, method=body.method, value=body.value,
                                      rationale=body.rationale, changed_by=body.changed_by)
    except RationaleRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    return res


@router.post("/{case_id}/stages/7/run", response_model=Stage7ReviewOut)
def run_stage7(case_id: str, db: Session = Depends(get_db)) -> Stage7ReviewOut:
    case = get_case_or_404(db, case_id)
    try:
        res = service.run_stage7(db, case)
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    db.commit()
    return Stage7ReviewOut(**res)


@router.get("/{case_id}/stages/7/review", response_model=Stage7ReviewOut)
def review_stage7(case_id: str, db: Session = Depends(get_db)) -> Stage7ReviewOut:
    case = get_case_or_404(db, case_id)
    return Stage7ReviewOut(**service.review_stage7(db, case))


@router.post("/{case_id}/stages/7/adjustments")
def add_adjustment(case_id: str, body: AssetAdjustmentIn, db: Session = Depends(get_db)) -> dict:
    case = get_case_or_404(db, case_id)
    try:
        res = service.add_asset_adjustment(db, case, label=body.label, amount=body.amount,
                                           rationale=body.rationale)
    except RationaleRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    db.commit()
    return res


@router.delete("/{case_id}/stages/7/adjustments/{adj_id}")
def remove_adjustment(case_id: str, adj_id: int, db: Session = Depends(get_db)) -> dict:
    case = get_case_or_404(db, case_id)
    try:
        res = service.remove_asset_adjustment(db, case, adj_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    db.commit()
    return res


@router.post("/{case_id}/stages/7/premium")
def override_premium(case_id: str, body: PremiumOverrideIn, db: Session = Depends(get_db)) -> dict:
    case = get_case_or_404(db, case_id)
    try:
        res = service.override_asset_premium(db, case, value=body.value, rationale=body.rationale,
                                             changed_by=body.changed_by)
    except RationaleRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    db.commit()
    return res


@router.post("/{case_id}/stages/8/run", response_model=Stage8ReviewOut)
def run_stage8(case_id: str, db: Session = Depends(get_db)) -> Stage8ReviewOut:
    case = get_case_or_404(db, case_id)
    try:
        res = service.run_stage8(db, case)
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    db.commit()
    return Stage8ReviewOut(**res)


@router.get("/{case_id}/stages/8/review", response_model=Stage8ReviewOut)
def review_stage8(case_id: str, db: Session = Depends(get_db)) -> Stage8ReviewOut:
    case = get_case_or_404(db, case_id)
    return Stage8ReviewOut(**service.review_stage8(db, case))


@router.post("/{case_id}/stages/8/distribution")
def override_mc(case_id: str, body: McSigmaOverrideIn, db: Session = Depends(get_db)) -> dict:
    case = get_case_or_404(db, case_id)
    try:
        res = service.override_mc_sigma(db, case, var=body.var, sigma=body.sigma,
                                        rationale=body.rationale, changed_by=body.changed_by)
    except RationaleRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    return res


@router.post("/{case_id}/stages/9/run", response_model=Stage9ReviewOut)
def run_stage9(case_id: str, db: Session = Depends(get_db)) -> Stage9ReviewOut:
    case = get_case_or_404(db, case_id)
    try:
        res = service.run_stage9(db, case)
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    db.commit()
    return Stage9ReviewOut(**res)


@router.get("/{case_id}/stages/9/review", response_model=Stage9ReviewOut)
def review_stage9(case_id: str, db: Session = Depends(get_db)) -> Stage9ReviewOut:
    case = get_case_or_404(db, case_id)
    return Stage9ReviewOut(**service.review_stage9(db, case))


@router.post("/{case_id}/stages/9/weight")
def override_weight(case_id: str, body: WeightOverrideIn, db: Session = Depends(get_db)) -> dict:
    case = get_case_or_404(db, case_id)
    try:
        res = service.override_final_weight(db, case, method=body.method, value=body.value,
                                            rationale=body.rationale, changed_by=body.changed_by)
    except RationaleRequiredError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    return res


@router.post("/{case_id}/stages/9/flags/ack")
def acknowledge_flag(case_id: str, body: FlagAckIn, db: Session = Depends(get_db)) -> dict:
    case = get_case_or_404(db, case_id)
    try:
        res = service.acknowledge_flag(db, case, key=body.key, note=body.note, by=body.by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    return res


@router.post("/{case_id}/stages/{stage_no}/approve", response_model=dict)
def approve_stage(case_id: str, stage_no: int, body: ApproveIn,
                  db: Session = Depends(get_db)) -> dict:
    case = get_case_or_404(db, case_id)
    try:
        res = service.approve_stage(db, case, stage_no, approved_by=body.approved_by)
    except InvalidTransition as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    return res
