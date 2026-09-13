"""Stage 7 · 자산접근법 (순수 함수, DB·HTTP 접근 금지).

조정순자산가치 = 장부 순자산 + Σ조정항목(부호 있음). 상증세법 목적 시 최대주주 할증 가산.
(docs/data_flow.md §7)

단위: 금액 백만원, 할증률 소수(0.20), 주당가치 원.
"""

from __future__ import annotations


def adjusted_net_asset(book_equity: float, adjustments: list[dict]) -> dict:
    """장부 순자산 + 조정합계. adjustments: [{label, amount}] (amount 부호 포함)."""
    total = sum(a.get("amount") or 0.0 for a in adjustments)
    return {"book_equity": book_equity, "adjustments_total": total,
            "adjusted": book_equity + total}


def apply_control_premium(value: float, rate: float) -> float:
    """최대주주 할증: value·(1+rate)."""
    return value * (1.0 + rate)


def asset_valuation(book_equity: float | None, adjustments: list[dict], *,
                    control_premium_rate: float = 0.0, shares: float | None = None) -> dict:
    """자산접근 가치. 조정 → (선택)할증 → 주당가치."""
    book = book_equity or 0.0
    adj = adjusted_net_asset(book, adjustments)
    value = apply_control_premium(adj["adjusted"], control_premium_rate)
    per_share = (value * 1_000_000 / shares) if shares else None
    return {
        "book_equity": book,
        "adjustments_total": adj["adjustments_total"],
        "adjusted_net_asset": adj["adjusted"],
        "control_premium_rate": control_premium_rate,
        "value_with_premium": value,
        "per_share": per_share,
    }
