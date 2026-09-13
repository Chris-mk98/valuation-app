"""Stage 4 · 할인율(WACC) 계산 (순수 함수, DB·HTTP 접근 금지).

단위 규약: 이자율/프리미엄은 % (예: Rf 3.183), 세율·가중치·D/E 는 소수(0.24, 0.8, 0.5).

산식(docs/data_flow.md §4):
  β_L     = OLS( 개별주 주간수익률 vs 시장 주간수익률 ) 기울기
  β_u     = β_L / (1 + (1−t)·D/E)
  β_L'    = β_u · (1 + (1−t)·D/E)            # 목표 자본구조로 리레버
  Ke      = Rf + β·(ERP + 국가위험) + 규모프리미엄     # CAPM 빌드업 (%)
  Kd      = 이자비용 / 평균차입금                       # (%)
  WACC    = E/V·Ke + D/V·Kd·(1−t)                      # (%)
"""

from __future__ import annotations

from datetime import date

import numpy as np


def beta_ols(stock_returns: list[float], market_returns: list[float]) -> dict:
    """개별주 수익률을 시장수익률에 OLS 회귀한 기울기(β)·절편·R²·표본수.

    β = Cov(r_s, r_m) / Var(r_m). 회귀 설명력 R² 은 레드플래그(<0.1) 판정에 사용.
    """
    x = np.asarray(market_returns, dtype=float)
    y = np.asarray(stock_returns, dtype=float)
    n = len(x)
    if n < 2 or len(y) != n:
        raise ValueError("회귀에는 길이가 같은 2개 이상의 수익률이 필요합니다.")
    var = np.var(x)
    if var == 0:
        raise ValueError("시장수익률 분산이 0 입니다.")
    beta, alpha = np.polyfit(x, y, 1)
    yhat = beta * x + alpha
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return {"beta": float(beta), "alpha": float(alpha), "r2": float(r2), "n": n}


def unlever_beta(beta_l: float, de: float, tax: float) -> float:
    """β_u = β_L / (1 + (1−t)·D/E)."""
    return beta_l / (1.0 + (1.0 - tax) * de)


def relever_beta(beta_u: float, de: float, tax: float) -> float:
    """β_L = β_u · (1 + (1−t)·D/E)."""
    return beta_u * (1.0 + (1.0 - tax) * de)


def cost_of_equity(rf: float, beta: float, erp: float, *, size_premium: float = 0.0,
                   country_risk: float = 0.0) -> float:
    """Ke(%) = Rf + β·(ERP + 국가위험) + 규모프리미엄. 입력·출력 모두 %."""
    return rf + beta * (erp + country_risk) + size_premium


def cost_of_debt_from_interest(interest_expense: float, avg_debt: float) -> float | None:
    """Kd(%) = 이자비용 / 평균차입금 × 100. 차입금 0이면 None."""
    if not avg_debt:
        return None
    return interest_expense / avg_debt * 100.0


def wacc(ke: float, kd: float, equity_value: float, debt_value: float, tax: float) -> float:
    """WACC(%) = E/V·Ke + D/V·Kd·(1−t). ke/kd 는 %, 가치는 동일단위."""
    v = equity_value + debt_value
    if v <= 0:
        raise ValueError("기업가치(E+D)가 0 이하입니다.")
    we, wd = equity_value / v, debt_value / v
    return we * ke + wd * kd * (1.0 - tax)


def median(values: list[float]) -> float | None:
    """중앙값(빈 리스트면 None). 언레버 β 중앙값·목표 D/E 산정용."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    m = len(vals)
    mid = m // 2
    return vals[mid] if m % 2 else (vals[mid - 1] + vals[mid]) / 2.0


def to_weekly_returns(prices: list[dict]) -> dict[str, float]:
    """일별 종가 [{date, close}] → 주간(ISO 주) 수익률 {주키: 수익률}.

    각 ISO 주의 마지막 종가를 취해 주간 종가 시계열을 만들고 로그가 아닌 단순수익률 계산.
    """
    by_week: dict[str, tuple[str, float]] = {}
    for row in prices:
        c = row.get("close")
        d = row.get("date")
        if c is None or d is None:
            continue
        iso = date.fromisoformat(str(d)[:10]).isocalendar()
        key = f"{iso.year}-W{iso.week:02d}"
        # 같은 주의 더 늦은 날짜로 갱신(마지막 종가)
        if key not in by_week or str(d) >= by_week[key][0]:
            by_week[key] = (str(d), float(c))
    keys = sorted(by_week)
    out: dict[str, float] = {}
    for i in range(1, len(keys)):
        prev = by_week[keys[i - 1]][1]
        cur = by_week[keys[i]][1]
        if prev:
            out[keys[i]] = cur / prev - 1.0
    return out


def align_returns(a: dict[str, float], b: dict[str, float]) -> tuple[list[float], list[float]]:
    """두 주간수익률 dict 를 공통 주 기준으로 정렬해 (a_list, b_list) 반환."""
    common = sorted(set(a) & set(b))
    return [a[k] for k in common], [b[k] for k in common]
