"""Stage 0~2 서비스 로직 — 라우터가 얇게 호출. core(lineage·stage_gate) 경유.

트랜잭션(commit)은 라우터에서 관리.
"""

from __future__ import annotations

import math
import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.core import lineage, rules, stage_gate
from app.core.lineage import RationaleRequiredError
from app.db.models import (
    AssetAdjustment,
    AssetResult,
    Case,
    DcfAssumption,
    DcfResult,
    FinalValue,
    FinancialsNormalized,
    MarketResult,
    McDistribution,
    McResult,
    Peer,
    SourceType,
    StageState,
    WaccBuild,
)
from app.params import param_tables
from app.params.account_map import load_account_map
from app.sources import dart, ecos, price
from app.stages import (
    s2_normalize,
    s3_peers,
    s4_wacc,
    s5_dcf,
    s6_market,
    s7_asset,
    s8_montecarlo,
    s9_review,
)

MC_RUNS = 10_000

SHORTLIST_N = 30  # KSIC 확인 전 시총 근접 압축 개수(DART 호출 상한)
BETA_YEARS = 2    # 레버 베타 회귀 기간(주간, KOSPI)
BETA_MIN_WEEKS = 30
KD_DEFAULT_SPREAD = 1.5  # Kd 산출 불가 시 Rf + 스프레드(%) 기본값


def _field(year: int, account: str) -> str:
    return f"fin.{year}.{account}"


def fiscal_years(valuation_date: str, n: int = 5) -> list[int]:
    """기준일 기준 최근 n개 회계연도(기준일 연도 포함, 과거로)."""
    base = int(valuation_date[:4])
    return list(range(base - n + 1, base + 1))


# --------------------------------------------------------------------------- #
# Stage 0
# --------------------------------------------------------------------------- #
def create_case(db: Session, *, company: str, valuation_date: str, purpose: str,
                created_by: str) -> Case:
    if purpose not in rules.list_purposes():
        raise ValueError(f"지원하지 않는 평가목적: {purpose}")
    found = dart.resolve_corp_code(company, db=db)
    comp = dart.get_company(db, found["corp_code"])
    case = Case(
        case_id=uuid.uuid4().hex[:12],
        corp_code=found["corp_code"],
        corp_name=comp.get("corp_name") or found["corp_name"],
        stock_code=(comp.get("stock_code") or found.get("stock_code")) or None,
        induty_code=comp.get("induty_code"),
        valuation_date=valuation_date,
        purpose=purpose,
    )
    db.add(case)
    # Stage 0(설정)은 케이스 생성으로 확정 → REVIEWED→APPROVED
    stage_gate.mark_reviewed(db, case.case_id, 0)
    stage_gate.approve(db, case.case_id, 0, approved_by=created_by)
    return case


# --------------------------------------------------------------------------- #
# Stage 1 · 수집
# --------------------------------------------------------------------------- #
def run_stage1(db: Session, case: Case) -> dict:
    if stage_gate.get_state(db, case.case_id, 0) != StageState.APPROVED:
        raise PermissionError("Stage 0 미승인")
    years = fiscal_years(case.valuation_date)
    raw = dart.get_financials_multi(db, case.corp_code, years)
    collected = [{"year": y, "rows": len(raw.get(y, [])), "ok": bool(raw.get(y))} for y in years]
    # 수집 후 Stage 1 은 DRAFT(검토 대기). 이전 승인이 있었다면 되돌림.
    st = stage_gate._get_or_create(db, case.case_id, 1)
    st.status = StageState.DRAFT
    st.approved_by = None
    st.approved_at = None
    stage_gate.invalidate_downstream(db, case.case_id, 1, reason="stage1_rerun")
    return {"case_id": case.case_id, "corp_name": case.corp_name, "years": years,
            "collected": collected}


# --------------------------------------------------------------------------- #
# Stage 2 · 정규화
# --------------------------------------------------------------------------- #
def _raw_by_year(db: Session, case: Case, years: list[int]) -> dict[int, list[dict]]:
    from app.db.models import RawDart
    out: dict[int, list[dict]] = {}
    for y in years:
        row = (db.query(RawDart)
               .filter_by(corp_code=case.corp_code, doc_type="financials", bsns_year=str(y))
               .first())
        out[y] = row.payload.get("list", []) if row else []
    return out


def review_stage2(db: Session, case: Case) -> dict:
    """캐시된 원본을 정규화하고 FinancialsNormalized + lineage(DERIVED) 반영 후 검토 데이터 반환.

    이미 EXPERT_OVERRIDE 된 셀은 시스템값으로 덮어쓰지 않는다.
    """
    if stage_gate.get_state(db, case.case_id, 1) != StageState.APPROVED:
        raise PermissionError("Stage 1 미승인 — 정규화 잠금")

    years = fiscal_years(case.valuation_date)
    mapping = load_account_map()
    norm = s2_normalize.normalize(_raw_by_year(db, case, years), mapping)
    version = mapping.get("version", "unknown")

    accounts_out: dict[int, dict[str, dict]] = {}
    unmapped_out: dict[int, list[str]] = {}
    for y in years:
        accounts_out[y] = {}
        overridden_accts: set[str] = set()
        for acc, val in norm["accounts"].get(y, {}).items():
            field = _field(y, acc)
            existing = lineage.get_field(db, case.case_id, field)
            overridden = existing is not None and existing.source_type == SourceType.EXPERT_OVERRIDE
            if overridden:
                overridden_accts.add(acc)
                shown = existing.value
                cell = {"value": shown, "source_type": "EXPERT_OVERRIDE", "overridden": True,
                        "system_value": existing.system_value, "rationale": existing.rationale}
            else:
                lineage.record_value(db, case_id=case.case_id, field_name=field, value=val,
                                     source_type=SourceType.DERIVED,
                                     source_ref=f"account_map@{version}",
                                     derived_from=["raw_dart"])
                shown = val
                cell = {"value": shown, "source_type": "DERIVED", "overridden": False,
                        "system_value": None, "rationale": None}
            _upsert_normalized(db, case.case_id, y, acc, shown)
            accounts_out[y][acc] = cell
        # 오버라이드로 채워진 계정은 미분류에서 제외
        unmapped_out[y] = [a for a in norm["unmapped"].get(y, []) if a not in overridden_accts]

    # 검토 준비 완료 → REVIEWED (승인은 별도)
    if stage_gate.get_state(db, case.case_id, 2) == StageState.DRAFT:
        stage_gate.mark_reviewed(db, case.case_id, 2)

    return {
        "case_id": case.case_id,
        "years": years,
        "accounts": accounts_out,
        "unmapped": unmapped_out,
        "warnings": norm["warnings"],
        "stage2_status": stage_gate.get_state(db, case.case_id, 2).value,
        "stage1_status": stage_gate.get_state(db, case.case_id, 1).value,
    }


def _upsert_normalized(db: Session, case_id: str, year: int, account: str,
                       value: float | None) -> None:
    row = (db.query(FinancialsNormalized)
           .filter_by(case_id=case_id, year=year, account=account).one_or_none())
    if row is None:
        db.add(FinancialsNormalized(case_id=case_id, year=year, account=account, value=value))
    else:
        row.value = value


def override_stage2(db: Session, case: Case, *, year: int, account: str, value: float,
                    rationale: str, changed_by: str) -> dict:
    field = _field(year, account)
    row = lineage.record_override(db, case_id=case.case_id, field_name=field, value=value,
                                  rationale=rationale, changed_by=changed_by)
    _upsert_normalized(db, case.case_id, year, account, value)
    # 상위(Stage 2) 값 변경 → 하위 무효화
    stage_gate.invalidate_downstream(db, case.case_id, 2, reason=field)
    return {"field": field, "value": row.value, "system_value": row.system_value,
            "rationale": row.rationale, "overridden": True}


def approve_stage(db: Session, case: Case, stage_no: int, approved_by: str) -> dict:
    """검토 화면에서의 승인: DRAFT면 REVIEWED 경유 후 APPROVED.

    Stage 9 는 발동된 레드플래그가 모두 승인되어야 진행(원칙 B: 경고 승인 기록).
    """
    if stage_no == 9:
        _require_flags_acknowledged(db, case)
    state = stage_gate.get_state(db, case.case_id, stage_no)
    if state == StageState.DRAFT:
        stage_gate.mark_reviewed(db, case.case_id, stage_no)
    st = stage_gate.approve(db, case.case_id, stage_no, approved_by=approved_by)
    return {"stage_no": stage_no, "status": st.status.value, "approved_by": st.approved_by}


def _require_flags_acknowledged(db: Session, case: Case) -> None:
    row = db.query(FinalValue).filter_by(case_id=case.case_id).one_or_none()
    if row is None:
        raise ValueError("Stage 9 를 먼저 산출하세요(run).")
    approvals = row.payload.get("flag_approvals", {})
    pending = [f["key"] for f in row.payload.get("flags", [])
               if f["triggered"] and f["key"] not in approvals]
    if pending:
        raise ValueError(f"미승인 레드플래그: {', '.join(pending)} — 먼저 승인하세요.")


# --------------------------------------------------------------------------- #
# Stage 3 · 유사기업 스크리닝
# --------------------------------------------------------------------------- #
def _latest_account(db: Session, case_id: str, account: str) -> float | None:
    rows = [r for r in db.query(FinancialsNormalized)
            .filter_by(case_id=case_id, account=account).all() if r.value is not None]
    return max(rows, key=lambda x: x.year).value if rows else None


def _years_since(listing_date: str | None, valuation_date: str) -> int:
    if not listing_date:
        return 0
    try:
        ld = date.fromisoformat(listing_date[:10])
        vd = date.fromisoformat(valuation_date[:10])
    except ValueError:
        return 0
    return max(0, (vd - ld).days // 365)


def _candidate_metrics(db: Session, corp_code: str, base_year: int,
                       mapping: dict) -> tuple[float | None, float | None]:
    """후보의 최근 매출·순이익(백만원). 연결(CFS) 없으면 별도(OFS), 기준연도 없으면 직전연도 폴백.

    (연결재무제표를 제출하지 않는 소형사는 별도만 존재)
    """
    for y in (base_year, base_year - 1):
        for fs_div in ("CFS", "OFS"):
            try:
                rows = dart.get_financials(db, corp_code, str(y), fs_div=fs_div)
            except dart.DartError:
                rows = []
            if rows:
                n = s2_normalize.normalize_year(rows, mapping)
                return n["accounts"].get("revenue"), n["accounts"].get("net_income")
    return None, None


def run_stage3(db: Session, case: Case, *, shortlist_n: int = SHORTLIST_N) -> dict:
    """유사기업 자동 스크리닝. KRX 섹터+시총으로 압축 후 DART KSIC 중분류로 확정, 재무로 필터.

    호출 통제: DART 재무/개황은 압축된 shortlist(기본 30개)에 한해 호출한다.
    """
    if stage_gate.get_state(db, case.case_id, 2) != StageState.APPROVED:
        raise PermissionError("Stage 2 미승인 — 유사기업 스크리닝 잠금")

    listing = price.get_listing(db=db)
    by_code = {r["code"]: r for r in listing}
    target_row = by_code.get(case.stock_code or "")
    # KRX-DESC 는 Sector 가 비는 경우가 많아 Industry(업종명)를 프리필터 기준으로 사용
    t_industry = target_row.get("industry") if target_row else None
    t_mktcap = target_row.get("market_cap") if target_row else None
    t_revenue = _latest_account(db, case.case_id, "revenue")
    mapping = load_account_map()
    base_year = int(case.valuation_date[:4])

    # 1) KRX 업종 프리필터 + 시총 근접 정렬 → shortlist (DART 호출 통제)
    #    업종명이 없으면 시총 근접만으로 압축(이후 DART KSIC 중분류로 엄격 확정)
    pre = [r for r in listing
           if r["code"] != case.stock_code and (not t_industry or r.get("industry") == t_industry)]
    if t_mktcap:
        pre.sort(key=lambda r: abs(math.log((r.get("market_cap") or 1e-9) / t_mktcap))
                 if r.get("market_cap") else math.inf)
    shortlist = pre[:shortlist_n]

    # 2) shortlist 를 DART 로 KSIC·재무 확정
    candidates: list[dict] = []
    for r in shortlist:
        try:
            found = dart.resolve_corp_code(r["code"], db=db)
            comp = dart.get_company(db, found["corp_code"])
        except dart.DartError:
            continue
        rev, ni = _candidate_metrics(db, found["corp_code"], base_year, mapping)
        candidates.append({
            "corp_code": found["corp_code"],
            "corp_name": comp.get("corp_name") or r.get("name"),
            "stock_code": r.get("code"),
            "induty_code": comp.get("induty_code"),
            "revenue": rev,
            "net_income": ni,
            "market_cap": (r.get("market_cap") or 0) / 1_000_000,  # 원→백만원
            "years_reported": _years_since(r.get("listing_date"), case.valuation_date),
            "sector": r.get("sector"),
        })

    target = {"corp_code": case.corp_code, "induty_code": case.induty_code, "revenue": t_revenue}
    screened = s3_peers.screen_peers(target, candidates)

    # 3) Peer 영속(자동 통과 = included). 기존 SCREEN 행은 초기화, MANUAL 은 보존.
    db.query(Peer).filter_by(case_id=case.case_id, source="SCREEN").delete()
    for r in screened["results"]:
        db.add(Peer(
            case_id=case.case_id, corp_code=r["corp_code"], corp_name=r["corp_name"],
            stock_code=r.get("stock_code"), included=1 if r["passed"] else 0,
            source="SCREEN", rationale=None,
            metrics={k: r.get(k) for k in
                     ("revenue", "net_income", "market_cap", "years_reported",
                      "sector", "induty_code", "filters", "passed")},
        ))

    st = stage_gate._get_or_create(db, case.case_id, 3)
    st.status = StageState.DRAFT
    st.approved_by = None
    st.approved_at = None
    stage_gate.invalidate_downstream(db, case.case_id, 3, reason="stage3_rerun")

    return {
        "case_id": case.case_id,
        "target": {"revenue": t_revenue, "induty_code": case.induty_code,
                   "industry": t_industry, "market_cap": (t_mktcap or 0) / 1_000_000},
        "criteria": screened["criteria"],
        "screened": len(candidates),
        "passed": screened["passed_count"],
    }


def review_stage3(db: Session, case: Case) -> dict:
    peers = db.query(Peer).filter_by(case_id=case.case_id).all()
    return {
        "case_id": case.case_id,
        "peers": [_peer_out(p) for p in peers],
        "target": {"induty_code": case.induty_code, "corp_name": case.corp_name},
        "stage3_status": stage_gate.get_state(db, case.case_id, 3).value,
        "stage2_status": stage_gate.get_state(db, case.case_id, 2).value,
    }


def _peer_out(p: Peer) -> dict:
    return {
        "corp_code": p.corp_code, "corp_name": p.corp_name, "stock_code": p.stock_code,
        "included": bool(p.included), "source": p.source, "rationale": p.rationale,
        "metrics": p.metrics or {},
    }


def set_peer_inclusion(db: Session, case: Case, corp_code: str, included: bool,
                       rationale: str) -> dict:
    """포함/제외 확정 — 사유 필수(감사추적)."""
    if not rationale or not rationale.strip():
        raise RationaleRequiredError("포함/제외에는 사유가 필요합니다.")
    peer = (db.query(Peer)
            .filter_by(case_id=case.case_id, corp_code=corp_code).one_or_none())
    if peer is None:
        raise ValueError(f"후보 없음: {corp_code}")
    peer.included = 1 if included else 0
    peer.rationale = rationale
    stage_gate.invalidate_downstream(db, case.case_id, 3, reason=f"peer:{corp_code}")
    return _peer_out(peer)


def add_manual_peer(db: Session, case: Case, company: str, rationale: str) -> dict:
    """수동 추가 — 사유 필수."""
    if not rationale or not rationale.strip():
        raise RationaleRequiredError("수동 추가에는 사유가 필요합니다.")
    found = dart.resolve_corp_code(company, db=db)
    comp = dart.get_company(db, found["corp_code"])
    listing = {r["code"]: r for r in price.get_listing(db=db)}
    lr = listing.get(found.get("stock_code") or "", {})
    rev, ni = _candidate_metrics(db, found["corp_code"], int(case.valuation_date[:4]),
                                 load_account_map())
    existing = (db.query(Peer)
                .filter_by(case_id=case.case_id, corp_code=found["corp_code"]).one_or_none())
    metrics = {"revenue": rev, "net_income": ni,
               "market_cap": (lr.get("market_cap") or 0) / 1_000_000,
               "years_reported": _years_since(lr.get("listing_date"), case.valuation_date),
               "sector": lr.get("sector"), "induty_code": comp.get("induty_code"),
               "filters": None, "passed": True}
    if existing is None:
        peer = Peer(case_id=case.case_id, corp_code=found["corp_code"],
                    corp_name=comp.get("corp_name") or found["corp_name"],
                    stock_code=found.get("stock_code"), included=1, source="MANUAL",
                    rationale=rationale, metrics=metrics)
        db.add(peer)
    else:
        existing.included = 1
        existing.source = "MANUAL"
        existing.rationale = rationale
        existing.metrics = metrics
        peer = existing
    stage_gate.invalidate_downstream(db, case.case_id, 3, reason=f"peer_add:{found['corp_code']}")
    return _peer_out(peer)


# --------------------------------------------------------------------------- #
# Stage 4 · 할인율(WACC)
# --------------------------------------------------------------------------- #
def _rf_10y(db: Session, valuation_date: str) -> float:
    """기준일 국고채 10Y(%) — 영업일이 아니면 최대 7일 소급."""
    d = date.fromisoformat(valuation_date[:10])
    for back in range(0, 8):
        try:
            return ecos.get_gov_bond_10y(db, (d.fromordinal(d.toordinal() - back)).isoformat())
        except ecos.EcosError:
            continue
    raise ecos.EcosError(f"국고채 10Y 조회 실패(기준일 전후): {valuation_date}")


def _norm_years(db: Session, corp_code: str, base_year: int, mapping: dict) -> dict[int, dict]:
    """최근 2개년 정규화 계정(연결 없으면 별도). {year: accounts}."""
    out: dict[int, dict] = {}
    for y in (base_year, base_year - 1):
        for fs in ("CFS", "OFS"):
            try:
                rows = dart.get_financials(db, corp_code, str(y), fs_div=fs)
            except dart.DartError:
                rows = []
            if rows:
                out[y] = s2_normalize.normalize_year(rows, mapping)["accounts"]
                break
    return out


def _weekly_window(valuation_date: str) -> tuple[str, str]:
    end = date.fromisoformat(valuation_date[:10])
    start = end.replace(year=end.year - BETA_YEARS)
    return start.isoformat(), end.isoformat()


def run_stage4(db: Session, case: Case) -> dict:
    """WACC 빌드업. 유사기업 주간 β → 언레버 중앙값 → 리레버 → CAPM Ke, 자동 Kd → WACC."""
    if stage_gate.get_state(db, case.case_id, 3) != StageState.APPROVED:
        raise PermissionError("Stage 3 미승인 — WACC 잠금")

    mapping = load_account_map()
    base_year = int(case.valuation_date[:4])
    tax_row = param_tables.get_tax_rate("KR")
    tax = tax_row["value"] / 100.0

    rf = _rf_10y(db, case.valuation_date)
    start, end = _weekly_window(case.valuation_date)
    market_weekly = s4_wacc.to_weekly_returns(price.get_index_ohlcv(db, start, end))

    # 유사기업 레버 β + D/E → 언레버 β
    peer_rows: list[dict] = []
    for p in db.query(Peer).filter_by(case_id=case.case_id, included=1).all():
        if not p.stock_code:
            continue
        try:
            prices = price.get_ohlcv(db, p.stock_code, start, end)
        except price.PriceError:
            continue
        sa, ma = s4_wacc.align_returns(s4_wacc.to_weekly_returns(prices), market_weekly)
        if len(sa) < BETA_MIN_WEEKS:
            continue
        reg = s4_wacc.beta_ols(sa, ma)
        nd = None
        for accts in _norm_years(db, p.corp_code, base_year, mapping).values():
            if accts.get("net_debt") is not None:
                nd = accts["net_debt"]
                break
        equity = (p.metrics or {}).get("market_cap")
        de = (nd / equity) if (nd is not None and equity) else None
        beta_u = s4_wacc.unlever_beta(reg["beta"], de, tax) if de is not None else None
        peer_rows.append({"corp_name": p.corp_name, "beta_l": reg["beta"], "r2": reg["r2"],
                          "n": reg["n"], "de": de, "beta_u": beta_u})

    betas_u = [r["beta_u"] for r in peer_rows if r["beta_u"] is not None]
    des = [r["de"] for r in peer_rows if r["de"] is not None]
    beta_u_med = s4_wacc.median(betas_u)
    target_de = s4_wacc.median(des)
    r2_min = min((r["r2"] for r in peer_rows), default=None)  # Stage 9 레드플래그용

    # 대상 지표
    tacc = _norm_years(db, case.corp_code, base_year, mapping)
    latest = tacc.get(base_year) or (tacc.get(base_year - 1) or {})
    gross_list = [a.get("gross_debt") for a in tacc.values() if a.get("gross_debt") is not None]
    avg_gross = sum(gross_list) / len(gross_list) if gross_list else None
    net_debt = latest.get("net_debt")
    ie = latest.get("interest_expense")
    interest_expense = abs(ie) if ie is not None else None  # CF 이자지급은 부호 다양 → 절대값
    listing = {r["code"]: r for r in price.get_listing(db=db)}
    target_mktcap = (listing.get(case.stock_code or "", {}).get("market_cap") or 0) / 1_000_000

    erp = param_tables.get_erp("KR")
    crp = param_tables.get_country_risk("KR")
    size = param_tables.get_size_premium(target_mktcap)

    kd = s4_wacc.cost_of_debt_from_interest(interest_expense, avg_gross) if (
        interest_expense and avg_gross) else None
    if kd is None:
        kd = rf + KD_DEFAULT_SPREAD

    # 저장할 기본 구성요소(파생은 _recompute 에서 계산)
    equity_value = target_mktcap
    debt_value = max(net_debt or 0.0, 0.0)  # 순현금(음수)이면 자본구조상 부채가중 0으로 단순화
    comps = [
        ("rf", rf, SourceType.API, f"ECOS/817Y002@{case.valuation_date}"),
        ("beta_u_median", beta_u_med, SourceType.DERIVED, "peer_unlever_median"),
        ("target_de", target_de, SourceType.DERIVED, "peer_de_median"),
        ("erp", erp["value"], SourceType.PARAM_TABLE, erp["source"]),
        ("country_risk", crp["value"], SourceType.PARAM_TABLE, crp["source"]),
        ("size_premium", size["value"], SourceType.PARAM_TABLE, size["source"]),
        ("kd", kd, SourceType.DERIVED, "interest/avg_debt" if interest_expense else "rf+spread"),
        ("tax_rate", tax_row["value"], SourceType.PARAM_TABLE, tax_row["source"]),
        ("equity_value", equity_value, SourceType.DERIVED, "market_cap"),
        ("debt_value", debt_value, SourceType.DERIVED, "max(net_debt,0)"),
        ("beta_r2_min", r2_min, SourceType.DERIVED, "min peer 회귀 R²"),
    ]
    for name, val, stype, ref in comps:
        _save_wacc_component(db, case.case_id, name, val, stype, ref)

    _recompute_wacc(db, case.case_id)

    st = stage_gate._get_or_create(db, case.case_id, 4)
    st.status = StageState.DRAFT
    st.approved_by = None
    st.approved_at = None
    stage_gate.invalidate_downstream(db, case.case_id, 4, reason="stage4_rerun")

    return {
        "case_id": case.case_id,
        "peers": peer_rows,
        "warnings": _wacc_warnings(peer_rows, interest_expense, avg_gross, net_debt),
        "kd_default": not (interest_expense and avg_gross),
    }


def _save_wacc_component(db: Session, case_id: str, name: str, value: float | None,
                         source_type: SourceType, source_ref: str) -> None:
    """WaccBuild upsert + lineage. 이미 EXPERT_OVERRIDE 된 값은 건드리지 않는다."""
    field = f"wacc.{name}"
    existing = lineage.get_field(db, case_id, field)
    if existing is not None and existing.source_type == SourceType.EXPERT_OVERRIDE:
        return
    row = db.query(WaccBuild).filter_by(case_id=case_id, component=name).one_or_none()
    if row is None:
        db.add(WaccBuild(case_id=case_id, component=name, value=value, source_ref=source_ref))
    else:
        row.value = value
        row.source_ref = source_ref
    if value is not None:
        lineage.record_value(db, case_id=case_id, field_name=field, value=value,
                             source_type=source_type, source_ref=source_ref)


def _wacc_values(db: Session, case_id: str) -> dict[str, float | None]:
    return {c.component: c.value
            for c in db.query(WaccBuild).filter_by(case_id=case_id).all()}


def _is_overridden(db: Session, case_id: str, name: str) -> bool:
    f = lineage.get_field(db, case_id, f"wacc.{name}")
    return f is not None and f.source_type == SourceType.EXPERT_OVERRIDE


def _recompute_wacc(db: Session, case_id: str) -> None:
    """저장된 기본 구성요소(오버라이드 반영)로 파생값(β_리레버·Ke·WACC) 재계산."""
    v = _wacc_values(db, case_id)
    tax = (v.get("tax_rate") or 0.0) / 100.0

    if not _is_overridden(db, case_id, "beta_relevered"):
        if v.get("beta_u_median") is not None and v.get("target_de") is not None:
            br = s4_wacc.relever_beta(v["beta_u_median"], v["target_de"], tax)
            _save_wacc_component(db, case_id, "beta_relevered", br,
                                 SourceType.DERIVED, "relever(beta_u_median,target_de)")
            v["beta_relevered"] = br

    if not _is_overridden(db, case_id, "ke") and v.get("beta_relevered") is not None:
        ke = s4_wacc.cost_of_equity(v.get("rf") or 0.0, v["beta_relevered"], v.get("erp") or 0.0,
                                    size_premium=v.get("size_premium") or 0.0,
                                    country_risk=v.get("country_risk") or 0.0)
        _save_wacc_component(db, case_id, "ke", ke, SourceType.DERIVED, "CAPM buildup")
        v["ke"] = ke

    if not _is_overridden(db, case_id, "wacc") and v.get("ke") is not None:
        ev, dv = v.get("equity_value") or 0.0, v.get("debt_value") or 0.0
        if ev + dv > 0:
            w = s4_wacc.wacc(v["ke"], v.get("kd") or 0.0, ev, dv, tax)
            _save_wacc_component(db, case_id, "wacc", w, SourceType.DERIVED, "E/V·Ke+D/V·Kd(1-t)")


def _wacc_warnings(peer_rows: list[dict], interest_expense, avg_gross, net_debt) -> list[str]:
    w = []
    low_r2 = [r["corp_name"] for r in peer_rows if r["r2"] < 0.10]
    if low_r2:
        w.append(f"베타 회귀 R²<0.1: {', '.join(low_r2)} (레드플래그)")
    if len(peer_rows) < 5:
        w.append(f"유효 베타 표본 {len(peer_rows)}개(<5) — 신뢰도 낮음")
    if not (interest_expense and avg_gross):
        w.append("Kd 자동산출 불가 → Rf+스프레드 기본값 사용(오버라이드 권장)")
    if (net_debt or 0) < 0:
        w.append("순현금(net cash) — 자본구조상 부채가중 0으로 단순화")
    return w


_WACC_LABELS = ["rf", "beta_u_median", "target_de", "beta_relevered", "erp", "country_risk",
                "size_premium", "ke", "kd", "tax_rate", "equity_value", "debt_value", "wacc"]


def review_stage4(db: Session, case: Case) -> dict:
    rows = {c.component: c for c in db.query(WaccBuild).filter_by(case_id=case.case_id).all()}
    components: dict[str, dict] = {}
    for name in _WACC_LABELS:
        r = rows.get(name)
        if r is None:
            continue
        lf = lineage.get_field(db, case.case_id, f"wacc.{name}")
        overridden = lf is not None and lf.source_type == SourceType.EXPERT_OVERRIDE
        components[name] = {
            "value": r.value, "source_ref": r.source_ref, "overridden": overridden,
            "system_value": lf.system_value if overridden else None,
            "rationale": lf.rationale if overridden else None,
        }
    return {
        "case_id": case.case_id,
        "components": components,
        "stage4_status": stage_gate.get_state(db, case.case_id, 4).value,
        "stage3_status": stage_gate.get_state(db, case.case_id, 3).value,
    }


def override_stage4(db: Session, case: Case, *, component: str, value: float, rationale: str,
                    changed_by: str) -> dict:
    field = f"wacc.{component}"
    lineage.record_override(db, case_id=case.case_id, field_name=field, value=value,
                            rationale=rationale, changed_by=changed_by)
    row = db.query(WaccBuild).filter_by(case_id=case.case_id, component=component).one_or_none()
    if row is None:
        db.add(WaccBuild(case_id=case.case_id, component=component, value=value,
                         source_ref="EXPERT_OVERRIDE"))
    else:
        row.value = value
        row.source_ref = "EXPERT_OVERRIDE"
    _recompute_wacc(db, case.case_id)  # 하위 파생 재계산
    stage_gate.invalidate_downstream(db, case.case_id, 4, reason=field)
    return {"component": component, "value": value, "wacc": _wacc_values(db, case.case_id).get("wacc")}


# --------------------------------------------------------------------------- #
# Stage 5 · 수익접근법(DCF)
# --------------------------------------------------------------------------- #
DCF_OVERRIDABLE = {"forecast_years", "revenue_growth", "ebit_margin", "dna_ratio",
                   "capex_ratio", "nwc_ratio", "terminal_growth", "tax",
                   "non_operating_assets", "net_debt"}
DCF_FIXED_TERMINAL_GROWTH = 0.01  # 영구성장률 기본 1.0% (사용자 확정)


def _dcf_history(db: Session, case: Case) -> list[dict]:
    """정규화 재무에서 DCF 입력 과거 시계열 구성."""
    keys = ("revenue", "ebit", "dna", "capex", "nwc")
    by_year: dict[int, dict] = {}
    rows = db.query(FinancialsNormalized).filter_by(case_id=case.case_id).all()
    for r in rows:
        if r.account in keys:
            by_year.setdefault(r.year, {"year": r.year})[r.account] = r.value
    return [by_year[y] for y in sorted(by_year)]


def _dcf_assumptions(db: Session, case_id: str) -> dict[str, float | None]:
    return {a.name: a.value for a in db.query(DcfAssumption).filter_by(case_id=case_id).all()}


def _save_dcf_assumption(db: Session, case_id: str, name: str, value: float | None,
                         source_type: SourceType, source_ref: str) -> None:
    field = f"dcf.{name}"
    existing = lineage.get_field(db, case_id, field)
    if existing is not None and existing.source_type == SourceType.EXPERT_OVERRIDE:
        return
    row = db.query(DcfAssumption).filter_by(case_id=case_id, name=name).one_or_none()
    if row is None:
        db.add(DcfAssumption(case_id=case_id, name=name, value=value, source_ref=source_ref))
    else:
        row.value = value
        row.source_ref = source_ref
    if value is not None:
        lineage.record_value(db, case_id=case_id, field_name=field, value=value,
                             source_type=source_type, source_ref=source_ref)


def _compute_and_store_dcf(db: Session, case: Case) -> dict:
    """저장된 가정(오버라이드 반영)으로 DCF 재계산 후 DcfResult 저장."""
    a = _dcf_assumptions(db, case.case_id)
    history = _dcf_history(db, case)
    result = {"error": None}
    try:
        assumptions = {
            "forecast_years": int(a.get("forecast_years") or 5),
            "revenue_growth": a.get("revenue_growth") or 0.0,
            "ebit_margin": a.get("ebit_margin") or 0.0,
            "dna_ratio": a.get("dna_ratio") or 0.0,
            "capex_ratio": a.get("capex_ratio") or 0.0,
            "nwc_ratio": a.get("nwc_ratio") or 0.0,
            "tax": a.get("tax") or 0.0,
            "terminal_growth": a.get("terminal_growth") or DCF_FIXED_TERMINAL_GROWTH,
        }
        val = s5_dcf.dcf_valuation(
            history, assumptions, wacc=a.get("wacc") or 0.0,
            net_debt=a.get("net_debt") or 0.0,
            non_operating_assets=a.get("non_operating_assets") or 0.0,
            shares=a.get("shares"),
        )
        result = {"error": None, **val}
    except (ValueError, IndexError) as e:
        result = {"error": str(e), "rows": [], "ev": None, "equity_value": None,
                  "per_share": None, "tv_ratio": None, "pv_sum": None, "tv": None, "pv_tv": None}

    row = db.query(DcfResult).filter_by(case_id=case.case_id).one_or_none()
    if row is None:
        db.add(DcfResult(case_id=case.case_id, payload=result))
    else:
        row.payload = result
    return result


def run_stage5(db: Session, case: Case) -> dict:
    """DCF 자동 산출: 과거 비율로 예측 가정 기본값 채우고 FCFF·EV·주주가치 계산."""
    if stage_gate.get_state(db, case.case_id, 4) != StageState.APPROVED:
        raise PermissionError("Stage 4 미승인 — DCF 잠금")

    history = _dcf_history(db, case)
    if not history:
        raise ValueError("정규화 재무가 없습니다(Stage 2 필요).")
    ratios = s5_dcf.historical_ratios(history)

    wacc_pct = _wacc_values(db, case.case_id).get("wacc")
    wacc = (wacc_pct or 0.0) / 100.0
    tax = param_tables.get_tax_rate("KR")["value"] / 100.0
    net_debt = _latest_account(db, case.case_id, "net_debt") or 0.0
    listing = {r["code"]: r for r in price.get_listing(db=db)}
    shares = listing.get(case.stock_code or "", {}).get("shares")

    defaults = [
        ("forecast_years", 5.0, SourceType.PARAM_TABLE, "기본 예측기간"),
        ("revenue_growth", ratios["revenue_cagr"] or 0.0, SourceType.DERIVED, "과거 CAGR"),
        ("ebit_margin", ratios["ebit_margin"] or 0.0, SourceType.DERIVED, "과거 평균 영업이익률"),
        ("dna_ratio", ratios["dna_ratio"] or 0.0, SourceType.DERIVED, "과거 평균 D&A/매출"),
        ("capex_ratio", ratios["capex_ratio"] or 0.0, SourceType.DERIVED, "과거 평균 CAPEX/매출"),
        ("nwc_ratio", ratios["nwc_ratio"] or 0.0, SourceType.DERIVED, "과거 평균 NWC/매출"),
        ("tax", tax, SourceType.PARAM_TABLE, "법인세율"),
        ("terminal_growth", DCF_FIXED_TERMINAL_GROWTH, SourceType.PARAM_TABLE, "영구성장률 기본 1.0%"),
        ("non_operating_assets", 0.0, SourceType.USER, "비영업자산 조정(기본 0)"),
        ("wacc", wacc, SourceType.DERIVED, "Stage4 WACC"),
        ("net_debt", net_debt, SourceType.DERIVED, "정규화 순차입금"),
        ("shares", shares, SourceType.API, "FDR 상장주식수"),
    ]
    for name, val, stype, ref in defaults:
        _save_dcf_assumption(db, case.case_id, name, val, stype, ref)

    _compute_and_store_dcf(db, case)

    st = stage_gate._get_or_create(db, case.case_id, 5)
    st.status = StageState.DRAFT
    st.approved_by = None
    st.approved_at = None
    stage_gate.invalidate_downstream(db, case.case_id, 5, reason="stage5_rerun")
    return review_stage5(db, case)


def _dcf_warnings(payload: dict, assumptions: dict) -> list[str]:
    w: list[str] = []
    if payload.get("error"):
        w.append(f"DCF 계산 오류: {payload['error']}")
    if not assumptions.get("dna_ratio"):
        w.append("D&A/매출=0 — Stage 2 에서 D&A 미입력(삼성 등 unmapped). FCFF 왜곡 가능 → 오버라이드 필요")
    if payload.get("ev") is not None and payload["ev"] < 0:
        w.append("EV<0 — 예측 FCFF 가 지속 음수(가정 점검 필요)")
    if payload.get("tv_ratio") and payload["tv_ratio"] > 0.70:
        w.append(f"TV 비중 {payload['tv_ratio']*100:.0f}% > 70% (레드플래그)")
    tg = assumptions.get("terminal_growth")
    if tg is not None and tg > 0.03:
        w.append("영구성장률 > 3% — 명목GDP 대비 과도 가능")
    return w


def review_stage5(db: Session, case: Case) -> dict:
    a = {x.name: x for x in db.query(DcfAssumption).filter_by(case_id=case.case_id).all()}
    assumptions: dict[str, dict] = {}
    for name, row in a.items():
        lf = lineage.get_field(db, case.case_id, f"dcf.{name}")
        overridden = lf is not None and lf.source_type == SourceType.EXPERT_OVERRIDE
        assumptions[name] = {
            "value": row.value, "source_ref": row.source_ref, "overridden": overridden,
            "system_value": lf.system_value if overridden else None,
            "rationale": lf.rationale if overridden else None,
            "editable": name in DCF_OVERRIDABLE,
        }
    res = db.query(DcfResult).filter_by(case_id=case.case_id).one_or_none()
    payload = res.payload if res else {}
    return {
        "case_id": case.case_id,
        "assumptions": assumptions,
        "result": payload,
        "warnings": _dcf_warnings(payload, {k: v["value"] for k, v in assumptions.items()}),
        "stage5_status": stage_gate.get_state(db, case.case_id, 5).value,
        "stage4_status": stage_gate.get_state(db, case.case_id, 4).value,
    }


def override_stage5(db: Session, case: Case, *, name: str, value: float, rationale: str,
                    changed_by: str) -> dict:
    if name not in DCF_OVERRIDABLE:
        raise ValueError(f"오버라이드 불가 항목: {name}")
    lineage.record_override(db, case_id=case.case_id, field_name=f"dcf.{name}", value=value,
                            rationale=rationale, changed_by=changed_by)
    row = db.query(DcfAssumption).filter_by(case_id=case.case_id, name=name).one_or_none()
    if row is None:
        db.add(DcfAssumption(case_id=case.case_id, name=name, value=value,
                             source_ref="EXPERT_OVERRIDE"))
    else:
        row.value = value
        row.source_ref = "EXPERT_OVERRIDE"
    result = _compute_and_store_dcf(db, case)
    stage_gate.invalidate_downstream(db, case.case_id, 5, reason=f"dcf.{name}")
    return {"name": name, "value": value, "ev": result.get("ev"),
            "equity_value": result.get("equity_value")}


# --------------------------------------------------------------------------- #
# Stage 6 · 시장접근법
# --------------------------------------------------------------------------- #
def _target_market_metrics(db: Session, case: Case) -> dict:
    """대상 LTM 지표 (Stage 2 오버라이드 반영된 FinancialsNormalized 기준)."""
    ebit = _latest_account(db, case.case_id, "ebit")
    dna = _latest_account(db, case.case_id, "dna")
    ebitda = (ebit + dna) if (ebit is not None and dna is not None) else None
    net_asset = (_latest_account(db, case.case_id, "owners_equity")
                 or _latest_account(db, case.case_id, "total_equity"))
    listing = {r["code"]: r for r in price.get_listing(db=db)}
    return {
        "ebitda": ebitda,
        "net_income": _latest_account(db, case.case_id, "net_income"),
        "net_asset": net_asset,
        "net_debt": _latest_account(db, case.case_id, "net_debt") or 0.0,
        "shares": listing.get(case.stock_code or "", {}).get("shares"),
    }


def _peer_market_metrics(db: Session, peer: Peer, base_year: int, mapping: dict) -> dict:
    """유사기업 LTM 지표(캐시된 원본 정규화). D&A 결손 시 EBITDA None."""
    accts: dict = {}
    for accs in _norm_years(db, peer.corp_code, base_year, mapping).values():
        accts = accs
        break
    ebit, dna = accts.get("ebit"), accts.get("dna")
    ebitda = (ebit + dna) if (ebit is not None and dna is not None) else None
    net_asset = accts.get("owners_equity") or accts.get("total_equity")
    return {
        "corp_name": peer.corp_name, "corp_code": peer.corp_code,
        "market_cap": (peer.metrics or {}).get("market_cap"),
        "net_debt": accts.get("net_debt"),
        "ebitda": ebitda, "net_income": accts.get("net_income"), "net_asset": net_asset,
    }


def run_stage6(db: Session, case: Case) -> dict:
    if stage_gate.get_state(db, case.case_id, 5) != StageState.APPROVED:
        raise PermissionError("Stage 5 미승인 — 시장접근 잠금")

    mapping = load_account_map()
    base_year = int(case.valuation_date[:4])
    peers = [_peer_market_metrics(db, p, base_year, mapping)
             for p in db.query(Peer).filter_by(case_id=case.case_id, included=1).all()]
    target = _target_market_metrics(db, case)

    payload = s6_market.market_valuation(peers, target)
    payload["target"] = target
    # 적용배수 오버라이드가 있으면 반영해 재적용
    _apply_market_overrides(db, case.case_id, payload)
    _store_market(db, case.case_id, payload)

    st = stage_gate._get_or_create(db, case.case_id, 6)
    st.status = StageState.DRAFT
    st.approved_by = None
    st.approved_at = None
    stage_gate.invalidate_downstream(db, case.case_id, 6, reason="stage6_rerun")
    return review_stage6(db, case)


def _apply_market_overrides(db: Session, case_id: str, payload: dict) -> None:
    """lineage 의 적용배수 오버라이드(market.{method})를 reps 에 반영 후 재적용."""
    changed = False
    for m in s6_market.METHODS:
        lf = lineage.get_field(db, case_id, f"market.{m}")
        if lf is not None and lf.source_type == SourceType.EXPERT_OVERRIDE:
            payload["reps"][m] = lf.value
            changed = True
    if changed:
        payload["applied"] = s6_market.apply_to_target(payload["reps"], payload["target"])
        eqs = [v["equity_value"] for v in payload["applied"].values()
               if v.get("equity_value") is not None]
        payload["range"] = {"min": min(eqs) if eqs else None,
                            "median": s6_market._median(eqs),
                            "max": max(eqs) if eqs else None}


def _store_market(db: Session, case_id: str, payload: dict) -> None:
    row = db.query(MarketResult).filter_by(case_id=case_id).one_or_none()
    if row is None:
        db.add(MarketResult(case_id=case_id, payload=payload))
    else:
        row.payload = payload


def _market_warnings(payload: dict) -> list[str]:
    w: list[str] = []
    n_ev = payload["summaries"]["ev_ebitda"]["n"]
    total_peers = len(payload.get("peers", []))
    if total_peers < 5:
        w.append(f"유사기업 {total_peers}개(<5) — 멀티플 신뢰도 낮음(레드플래그)")
    if n_ev == 0:
        w.append("EV/EBITDA 표본 0 — 유사기업 D&A 미상(EBITDA 산출 불가)")
    return w


def review_stage6(db: Session, case: Case) -> dict:
    row = db.query(MarketResult).filter_by(case_id=case.case_id).one_or_none()
    payload = row.payload if row else {}
    reps_meta = {}
    for m in s6_market.METHODS:
        lf = lineage.get_field(db, case.case_id, f"market.{m}")
        reps_meta[m] = {
            "value": (payload.get("reps") or {}).get(m),
            "overridden": lf is not None and lf.source_type == SourceType.EXPERT_OVERRIDE,
            "rationale": lf.rationale if (lf and lf.source_type == SourceType.EXPERT_OVERRIDE) else None,
        }
    return {
        "case_id": case.case_id,
        "peers": payload.get("peers", []),
        "summaries": payload.get("summaries", {}),
        "reps": reps_meta,
        "applied": payload.get("applied", {}),
        "range": payload.get("range", {}),
        "warnings": _market_warnings(payload) if payload else [],
        "stage6_status": stage_gate.get_state(db, case.case_id, 6).value,
        "stage5_status": stage_gate.get_state(db, case.case_id, 5).value,
    }


def override_stage6(db: Session, case: Case, *, method: str, value: float, rationale: str,
                    changed_by: str) -> dict:
    if method not in s6_market.METHODS:
        raise ValueError(f"알 수 없는 멀티플: {method}")
    lineage.record_override(db, case_id=case.case_id, field_name=f"market.{method}", value=value,
                            rationale=rationale, changed_by=changed_by)
    row = db.query(MarketResult).filter_by(case_id=case.case_id).one_or_none()
    if row is None:
        raise ValueError("먼저 시장접근을 산출하세요(run).")
    payload = dict(row.payload)
    payload["reps"][method] = value
    payload["applied"] = s6_market.apply_to_target(payload["reps"], payload["target"])
    eqs = [v["equity_value"] for v in payload["applied"].values()
           if v.get("equity_value") is not None]
    payload["range"] = {"min": min(eqs) if eqs else None, "median": s6_market._median(eqs),
                        "max": max(eqs) if eqs else None}
    row.payload = payload
    stage_gate.invalidate_downstream(db, case.case_id, 6, reason=f"market.{method}")
    return {"method": method, "value": value, "range": payload["range"]}


# --------------------------------------------------------------------------- #
# Stage 7 · 자산접근법
# --------------------------------------------------------------------------- #
def _asset_premium_rate(db: Session, case: Case) -> float:
    """최대주주 할증률. 상증세법 목적이면 규칙 기본값, 오버라이드 우선."""
    lf = lineage.get_field(db, case.case_id, "asset.control_premium")
    if lf is not None and lf.source_type == SourceType.EXPERT_OVERRIDE:
        return lf.value
    if case.purpose == "inheritance_gift":
        cons = rules.load_rules("inheritance_gift").get("constraints", {})
        prem = cons.get("controlling_shareholder_premium", {})
        if prem.get("enabled"):
            return float(prem.get("default_rate", 0.0))
    return 0.0


def _compute_and_store_asset(db: Session, case: Case) -> dict:
    book = (_latest_account(db, case.case_id, "owners_equity")
            or _latest_account(db, case.case_id, "total_equity"))
    adjustments = db.query(AssetAdjustment).filter_by(case_id=case.case_id).all()
    adj_list = [{"id": a.id, "label": a.label, "amount": a.amount, "rationale": a.rationale,
                 "source": a.source} for a in adjustments]
    rate = _asset_premium_rate(db, case)
    listing = {r["code"]: r for r in price.get_listing(db=db)}
    shares = listing.get(case.stock_code or "", {}).get("shares")

    res = s7_asset.asset_valuation(book, adj_list, control_premium_rate=rate, shares=shares)
    res["adjustments"] = adj_list
    row = db.query(AssetResult).filter_by(case_id=case.case_id).one_or_none()
    if row is None:
        db.add(AssetResult(case_id=case.case_id, payload=res))
    else:
        row.payload = res
    return res


def run_stage7(db: Session, case: Case) -> dict:
    if stage_gate.get_state(db, case.case_id, 6) != StageState.APPROVED:
        raise PermissionError("Stage 6 미승인 — 자산접근 잠금")
    # 할증 기본값 lineage 기록(오버라이드 대상)
    rate = _asset_premium_rate(db, case)
    if not (lineage.get_field(db, case.case_id, "asset.control_premium")
            and lineage.get_field(db, case.case_id, "asset.control_premium").source_type
            == SourceType.EXPERT_OVERRIDE):
        lineage.record_value(db, case_id=case.case_id, field_name="asset.control_premium",
                             value=rate, source_type=SourceType.PARAM_TABLE,
                             source_ref="inheritance_gift 규칙" if rate else "할증 미적용")
    _compute_and_store_asset(db, case)
    st = stage_gate._get_or_create(db, case.case_id, 7)
    st.status = StageState.DRAFT
    st.approved_by = None
    st.approved_at = None
    stage_gate.invalidate_downstream(db, case.case_id, 7, reason="stage7_rerun")
    return review_stage7(db, case)


def add_asset_adjustment(db: Session, case: Case, *, label: str, amount: float,
                         rationale: str, source: str = "USER") -> dict:
    if not rationale or not rationale.strip():
        raise RationaleRequiredError("조정항목에는 사유가 필요합니다.")
    db.add(AssetAdjustment(case_id=case.case_id, label=label, amount=amount,
                           rationale=rationale, source=source))
    db.flush()
    res = _compute_and_store_asset(db, case)
    stage_gate.invalidate_downstream(db, case.case_id, 7, reason="asset_adjustment_add")
    return res


def remove_asset_adjustment(db: Session, case: Case, adj_id: int) -> dict:
    row = db.query(AssetAdjustment).filter_by(case_id=case.case_id, id=adj_id).one_or_none()
    if row is None:
        raise ValueError(f"조정항목 없음: {adj_id}")
    db.delete(row)
    db.flush()
    res = _compute_and_store_asset(db, case)
    stage_gate.invalidate_downstream(db, case.case_id, 7, reason="asset_adjustment_remove")
    return res


def override_asset_premium(db: Session, case: Case, *, value: float, rationale: str,
                           changed_by: str) -> dict:
    lineage.record_override(db, case_id=case.case_id, field_name="asset.control_premium",
                            value=value, rationale=rationale, changed_by=changed_by)
    res = _compute_and_store_asset(db, case)
    stage_gate.invalidate_downstream(db, case.case_id, 7, reason="asset.control_premium")
    return res


def review_stage7(db: Session, case: Case) -> dict:
    row = db.query(AssetResult).filter_by(case_id=case.case_id).one_or_none()
    payload = row.payload if row else {}
    lf = lineage.get_field(db, case.case_id, "asset.control_premium")
    return {
        "case_id": case.case_id,
        "result": payload,
        "premium_overridden": lf is not None and lf.source_type == SourceType.EXPERT_OVERRIDE,
        "stage7_status": stage_gate.get_state(db, case.case_id, 7).value,
        "stage6_status": stage_gate.get_state(db, case.case_id, 6).value,
    }


# --------------------------------------------------------------------------- #
# Stage 8 · 몬테카를로
# --------------------------------------------------------------------------- #
def _mc_sigma(db: Session, case_id: str) -> dict:
    """변수별 σ(오버라이드 우선, 없으면 기본값)."""
    overrides = {d.var: d.sigma for d in db.query(McDistribution).filter_by(case_id=case_id).all()}
    return {v: overrides.get(v, s8_montecarlo.DEFAULT_SIGMA[v]) for v in s8_montecarlo.VARS}


def _compute_and_store_mc(db: Session, case: Case) -> dict:
    base = _dcf_assumptions(db, case.case_id)
    history = _dcf_history(db, case)
    sigma = _mc_sigma(db, case.case_id)
    specs = s8_montecarlo.build_dist_specs(base, sigma)
    stats = s8_montecarlo.simulate(
        history, base, dist_specs=specs, net_debt=base.get("net_debt") or 0.0,
        non_operating=base.get("non_operating_assets") or 0.0, shares=base.get("shares"),
        n=MC_RUNS,
    )
    stats["specs"] = specs
    row = db.query(McResult).filter_by(case_id=case.case_id).one_or_none()
    if row is None:
        db.add(McResult(case_id=case.case_id, payload=stats))
    else:
        row.payload = stats
    return stats


def run_stage8(db: Session, case: Case) -> dict:
    if stage_gate.get_state(db, case.case_id, 5) != StageState.APPROVED:
        raise PermissionError("Stage 5(DCF) 미승인 — 몬테카를로 잠금")
    _compute_and_store_mc(db, case)
    st = stage_gate._get_or_create(db, case.case_id, 8)
    st.status = StageState.DRAFT
    st.approved_by = None
    st.approved_at = None
    stage_gate.invalidate_downstream(db, case.case_id, 8, reason="stage8_rerun")
    return review_stage8(db, case)


def override_mc_sigma(db: Session, case: Case, *, var: str, sigma: float, rationale: str,
                      changed_by: str) -> dict:
    if var not in s8_montecarlo.VARS:
        raise ValueError(f"알 수 없는 변수: {var}")
    if sigma < 0:
        raise ValueError("σ 는 음수가 될 수 없습니다.")
    lineage.record_override(db, case_id=case.case_id, field_name=f"mc.sigma.{var}", value=sigma,
                            rationale=rationale, changed_by=changed_by)
    row = db.query(McDistribution).filter_by(case_id=case.case_id, var=var).one_or_none()
    if row is None:
        db.add(McDistribution(case_id=case.case_id, var=var, sigma=sigma))
    else:
        row.sigma = sigma
    stats = _compute_and_store_mc(db, case)
    stage_gate.invalidate_downstream(db, case.case_id, 8, reason=f"mc.sigma.{var}")
    return {"var": var, "sigma": sigma, "mean": stats["mean"], "p10": stats["p10"],
            "p90": stats["p90"]}


def _mc_warnings(payload: dict) -> list[str]:
    w: list[str] = []
    n_valid, n_total = payload.get("n_valid", 0), payload.get("n_total", 1)
    if n_total and n_valid / n_total < 0.9:
        w.append(f"무효 표본 {n_total - n_valid}/{n_total} — WACC≤영구성장률 등(가정 점검)")
    if payload.get("p10", 0) < 0:
        w.append("P10 주주가치 < 0 — 하방 시나리오에서 음(-)의 가치")
    return w


def review_stage8(db: Session, case: Case) -> dict:
    row = db.query(McResult).filter_by(case_id=case.case_id).one_or_none()
    payload = row.payload if row else {}
    sigma_meta = {}
    for v in s8_montecarlo.VARS:
        lf = lineage.get_field(db, case.case_id, f"mc.sigma.{v}")
        spec = (payload.get("specs") or {}).get(v, {})
        sigma_meta[v] = {
            "mean": spec.get("mean"), "sigma": spec.get("sigma"),
            "overridden": lf is not None and lf.source_type == SourceType.EXPERT_OVERRIDE,
        }
    return {
        "case_id": case.case_id,
        "stats": payload,
        "distributions": sigma_meta,
        "warnings": _mc_warnings(payload) if payload else [],
        "stage8_status": stage_gate.get_state(db, case.case_id, 8).value,
        "stage5_status": stage_gate.get_state(db, case.case_id, 5).value,
    }


# --------------------------------------------------------------------------- #
# Stage 9 · 목적별 조정 & 리뷰
# --------------------------------------------------------------------------- #
def _method_values(db: Session, case: Case) -> tuple[dict, dict]:
    """방법론별 대표가치(수익=DCF, 자산=Stage7, 시장=Stage6 중앙값) + 시장 범위."""
    dcf = db.query(DcfResult).filter_by(case_id=case.case_id).one_or_none()
    asset = db.query(AssetResult).filter_by(case_id=case.case_id).one_or_none()
    market = db.query(MarketResult).filter_by(case_id=case.case_id).one_or_none()
    m_range = (market.payload.get("range") if market else {}) or {}
    values = {
        "income": (dcf.payload.get("equity_value") if dcf else None),
        "asset": (asset.payload.get("value_with_premium") if asset else None),
        "market": m_range.get("median"),
    }
    return values, m_range


def _stage9_weights(db: Session, case: Case, purpose_rules: dict, values: dict) -> dict:
    """목적별 기본 가중 + (편집가능 시) 사용자 오버라이드."""
    mw = purpose_rules.get("method_weights", {})
    editable = mw.get("editable", False)
    if editable:
        # 일반 M&A: 기본 가용 3법 균등, 오버라이드 반영
        base = {k: (1.0 if values.get(k) is not None else 0.0)
                for k in s9_review.METHOD_KEYS}
        for k in s9_review.METHOD_KEYS:
            lf = lineage.get_field(db, case.case_id, f"final.weight.{k}")
            if lf is not None and lf.source_type == SourceType.EXPERT_OVERRIDE:
                base[k] = lf.value
        return base
    # 잠금: 규칙 값 그대로(None→0)
    return {k: (mw.get(k) or 0.0) for k in s9_review.METHOD_KEYS}


def _stage9_metrics(db: Session, case: Case, nominal_gdp: float | None) -> dict:
    a = _dcf_assumptions(db, case.case_id)
    dcf = db.query(DcfResult).filter_by(case_id=case.case_id).one_or_none()
    history = _dcf_history(db, case)
    peak_margin = max((h["ebit"] / h["revenue"] for h in history
                       if h.get("ebit") is not None and h.get("revenue")), default=None)
    peers = db.query(Peer).filter_by(case_id=case.case_id, included=1).count()
    wacc_vals = _wacc_values(db, case.case_id)
    return {
        "tv_ratio": (dcf.payload.get("tv_ratio") if dcf else None),
        "terminal_growth": a.get("terminal_growth"),
        "nominal_gdp": nominal_gdp,
        "forecast_margin": a.get("ebit_margin"),
        "historical_peak_margin": peak_margin,
        "capex_ratio": a.get("capex_ratio"),
        "dna_ratio": a.get("dna_ratio"),
        "peers_count": peers,
        "beta_r2_min": wacc_vals.get("beta_r2_min"),
    }


def _compute_and_store_final(db: Session, case: Case, nominal_gdp: float | None) -> dict:
    values, m_range = _method_values(db, case)
    prules = rules.load_rules(case.purpose)
    parallel = case.purpose == "impairment"
    weights = _stage9_weights(db, case, prules, values)
    floor = None
    if case.purpose == "inheritance_gift":
        floor = prules.get("constraints", {}).get("net_asset_floor_ratio")

    synth = s9_review.synthesize(values, weights, market_range=m_range,
                                 net_asset_floor=floor, parallel=parallel)

    flag_thresholds = {}
    for k, v in rules.load_review_flags().get("review_flags", {}).items():
        if k == "terminal_value_ratio_max":
            flag_thresholds["tv_ratio_max"] = v.get("threshold")
        elif k == "peers_min":
            flag_thresholds["peers_min"] = v.get("threshold")
        elif k == "beta_regression_r2_min":
            flag_thresholds["beta_r2_min"] = v.get("threshold")
    metrics = _stage9_metrics(db, case, nominal_gdp)
    flags = s9_review.evaluate_flags(metrics, flag_thresholds)

    prev = db.query(FinalValue).filter_by(case_id=case.case_id).one_or_none()
    approvals = (prev.payload.get("flag_approvals", {}) if prev else {})
    # 여전히 발동 중인 플래그의 승인만 유지
    triggered_keys = {f["key"] for f in flags if f["triggered"]}
    approvals = {k: v for k, v in approvals.items() if k in triggered_keys}

    payload = {
        "method_values": values, "market_range": m_range, "purpose": case.purpose,
        "purpose_label": prules.get("label"), "synthesis": synth, "metrics": metrics,
        "flags": flags, "flag_approvals": approvals,
    }
    if prev is None:
        db.add(FinalValue(case_id=case.case_id, payload=payload))
    else:
        prev.payload = payload
    return payload


def run_stage9(db: Session, case: Case) -> dict:
    if stage_gate.get_state(db, case.case_id, 5) != StageState.APPROVED:
        raise PermissionError("Stage 5(DCF) 미승인 — 종합 잠금")
    try:
        nominal_gdp = ecos.get_nominal_gdp_growth(db, int(case.valuation_date[:4]))
    except ecos.EcosError:
        nominal_gdp = None  # 조회 실패 시 해당 플래그만 생략
    _compute_and_store_final(db, case, nominal_gdp)
    st = stage_gate._get_or_create(db, case.case_id, 9)
    st.status = StageState.DRAFT
    st.approved_by = None
    st.approved_at = None
    stage_gate.invalidate_downstream(db, case.case_id, 9, reason="stage9_rerun")
    return review_stage9(db, case)


def override_final_weight(db: Session, case: Case, *, method: str, value: float, rationale: str,
                          changed_by: str) -> dict:
    if method not in s9_review.METHOD_KEYS:
        raise ValueError(f"알 수 없는 방법: {method}")
    prules = rules.load_rules(case.purpose)
    if not prules.get("method_weights", {}).get("editable", False):
        raise ValueError(f"{prules.get('label')} 목적은 가중치가 잠겨 있습니다(편집 불가).")
    lineage.record_override(db, case_id=case.case_id, field_name=f"final.weight.{method}",
                            value=value, rationale=rationale, changed_by=changed_by)
    nominal_gdp = _current_nominal_gdp(db, case)
    payload = _compute_and_store_final(db, case, nominal_gdp)
    stage_gate.invalidate_downstream(db, case.case_id, 9, reason=f"final.weight.{method}")
    return {"method": method, "value": value, "final": payload["synthesis"].get("final")}


def acknowledge_flag(db: Session, case: Case, *, key: str, note: str, by: str) -> dict:
    row = db.query(FinalValue).filter_by(case_id=case.case_id).one_or_none()
    if row is None:
        raise ValueError("Stage 9 를 먼저 산출하세요.")
    triggered = {f["key"] for f in row.payload.get("flags", []) if f["triggered"]}
    if key not in triggered:
        raise ValueError(f"발동되지 않은 플래그: {key}")
    payload = dict(row.payload)
    approvals = dict(payload.get("flag_approvals", {}))
    approvals[key] = {"by": by, "note": note}
    payload["flag_approvals"] = approvals
    row.payload = payload
    return {"key": key, "approved": True, "approvals": list(approvals)}


def _current_nominal_gdp(db: Session, case: Case) -> float | None:
    """캐시된 명목GDP(있으면). 재계산 시 네트워크 없이 재사용."""
    row = db.query(FinalValue).filter_by(case_id=case.case_id).one_or_none()
    if row is not None:
        return row.payload.get("metrics", {}).get("nominal_gdp")
    return None


def review_stage9(db: Session, case: Case) -> dict:
    row = db.query(FinalValue).filter_by(case_id=case.case_id).one_or_none()
    payload = row.payload if row else {}
    editable = rules.load_rules(case.purpose).get("method_weights", {}).get("editable", False)
    return {
        "case_id": case.case_id,
        "final": payload,
        "weights_editable": editable,
        "stage9_status": stage_gate.get_state(db, case.case_id, 9).value,
        "stage5_status": stage_gate.get_state(db, case.case_id, 5).value,
    }


# --------------------------------------------------------------------------- #
# Stage 10 · 산출물 (풋볼필드·감사추적·스냅샷)
# --------------------------------------------------------------------------- #
def football_field(db: Session, case: Case) -> list[dict]:
    """방법론별 가치 범위(풋볼필드). 수익가치는 MC P10~P90, 시장은 min~max, 자산은 점추정."""
    ff: list[dict] = []
    dcf = db.query(DcfResult).filter_by(case_id=case.case_id).one_or_none()
    mc = db.query(McResult).filter_by(case_id=case.case_id).one_or_none()
    market = db.query(MarketResult).filter_by(case_id=case.case_id).one_or_none()
    asset = db.query(AssetResult).filter_by(case_id=case.case_id).one_or_none()

    if dcf and dcf.payload.get("equity_value") is not None:
        base = dcf.payload["equity_value"]
        if mc and mc.payload.get("p50") is not None:
            ff.append({"method": "수익가치(DCF)", "low": mc.payload["p10"],
                       "base": mc.payload["p50"], "high": mc.payload["p90"]})
        else:
            ff.append({"method": "수익가치(DCF)", "low": base, "base": base, "high": base})
    if market and (market.payload.get("range") or {}).get("median") is not None:
        r = market.payload["range"]
        ff.append({"method": "시장가치", "low": r.get("min"), "base": r.get("median"),
                   "high": r.get("max")})
    if asset and asset.payload.get("value_with_premium") is not None:
        v = asset.payload["value_with_premium"]
        ff.append({"method": "자산가치", "low": v, "base": v, "high": v})
    return ff


def stage10_summary(db: Session, case: Case) -> dict:
    ff = football_field(db, case)
    final_row = db.query(FinalValue).filter_by(case_id=case.case_id).one_or_none()
    final_payload = final_row.payload if final_row else {}
    from app.db.models import StageStatus
    statuses = {s.stage_no: s.status.value
                for s in db.query(StageStatus).filter_by(case_id=case.case_id)}
    return {
        "case_id": case.case_id,
        "corp_name": case.corp_name,
        "valuation_date": case.valuation_date,
        "purpose_label": rules.load_rules(case.purpose).get("label"),
        "football_field": ff,
        "final_value": (final_payload.get("synthesis") or {}).get("final"),
        "synthesis": final_payload.get("synthesis", {}),
        "flags": final_payload.get("flags", []),
        "flag_approvals": final_payload.get("flag_approvals", {}),
        "stage_status": statuses,
    }


def lineage_rows(db: Session, case: Case) -> list[dict]:
    """감사추적: 케이스의 모든 lineage(출처·값·오버라이드 사유)."""
    out = []
    for r in lineage.get_lineage(db, case.case_id):
        out.append({
            "field_name": r.field_name, "value": r.value, "source_type": r.source_type.value,
            "source_ref": r.source_ref,
            "retrieved_at": r.retrieved_at.isoformat() if r.retrieved_at else None,
            "system_value": r.system_value, "rationale": r.rationale,
            "changed_by": r.changed_by, "prev_value": r.prev_value,
            "changed_at": r.changed_at.isoformat() if r.changed_at else None,
        })
    return out


def export_case_json(db: Session, case: Case) -> dict:
    """전체 케이스 스냅샷(재현성). 원본 캐시는 제외, 산출·가정·lineage 포함."""
    def payload(model):
        row = db.query(model).filter_by(case_id=case.case_id).one_or_none()
        return row.payload if row else None

    from app.db.models import StageStatus
    return {
        "case": {"case_id": case.case_id, "corp_code": case.corp_code,
                 "corp_name": case.corp_name, "stock_code": case.stock_code,
                 "induty_code": case.induty_code, "valuation_date": case.valuation_date,
                 "purpose": case.purpose, "currency": case.currency, "unit": case.unit},
        "financials_normalized": [
            {"year": f.year, "account": f.account, "value": f.value}
            for f in db.query(FinancialsNormalized).filter_by(case_id=case.case_id)
        ],
        "peers": [_peer_out(p) for p in db.query(Peer).filter_by(case_id=case.case_id)],
        "wacc": _wacc_values(db, case.case_id),
        "dcf_assumptions": _dcf_assumptions(db, case.case_id),
        "dcf_result": payload(DcfResult),
        "market_result": payload(MarketResult),
        "asset_result": payload(AssetResult),
        "mc_result": payload(McResult),
        "final_value": payload(FinalValue),
        "lineage": lineage_rows(db, case),
        "stage_status": {s.stage_no: s.status.value
                         for s in db.query(StageStatus).filter_by(case_id=case.case_id)},
    }
