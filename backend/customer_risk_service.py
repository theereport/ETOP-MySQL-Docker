from __future__ import annotations

from typing import Any


RISK_REVIEW_CRITERIA = [
    "Credit utilization is at or above the selected threshold.",
    "A balance is present in the 60-, 90-, or 120-day aging buckets.",
    "Priority is determined from utilization, past-due concentration, and severe aging.",
]


def _number(row: dict[str, Any], key: str) -> float:
    value = row.get(key)

    if value in (None, ""):
        return 0.0

    return float(value)


def _risk_priority(
    utilization: float,
    past_due: float,
    credit_limit: float,
    days_60_plus: float,
    days_90_plus: float,
) -> str:
    past_due_ratio = past_due / credit_limit if credit_limit > 0 else 0

    if (
        utilization >= 120
        or days_90_plus > 0
        or (utilization >= 100 and past_due > 0)
    ):
        return "Critical"

    if (
        utilization >= 90
        or days_60_plus > 0
        or past_due_ratio >= 0.25
    ):
        return "High"

    return "Elevated"


def _risk_score(
    utilization: float,
    past_due: float,
    credit_limit: float,
    days_60_plus: float,
    days_90_plus: float,
) -> int:
    past_due_ratio = past_due / credit_limit if credit_limit > 0 else 0
    utilization_points = min(
        65,
        max(0, 35 + ((utilization - 75) * 1.2)),
    )
    past_due_points = min(20, max(0, past_due_ratio * 40))
    aging_points = 0

    if days_60_plus > 0:
        aging_points += 7
    if days_90_plus > 0:
        aging_points += 8

    return round(min(100, utilization_points + past_due_points + aging_points))


def _risk_reasons(
    utilization: float,
    exposure: float,
    credit_limit: float,
    past_due: float,
    days_60_plus: float,
    days_90_plus: float,
) -> list[str]:
    reasons: list[str] = []
    amount_over_limit = max(0, exposure - credit_limit)

    if amount_over_limit > 0:
        reasons.append(
            f"Exposure is ${amount_over_limit:,.2f} over the approved credit line."
        )
    elif utilization >= 75:
        reasons.append(
            f"Credit utilization is {utilization:.1f}% of the approved line."
        )

    if days_90_plus > 0:
        reasons.append(
            f"${days_90_plus:,.2f} is aged 90 days or more."
        )
    elif days_60_plus > 0:
        reasons.append(
            f"${days_60_plus:,.2f} is aged 60 days or more."
        )

    if past_due > 0:
        reasons.append(f"${past_due:,.2f} is currently past due.")

    if not reasons:
        reasons.append("The account meets the configured credit-risk threshold.")

    return reasons


def rank_customer_risk(
    rows: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []

    for row in rows:
        credit_limit = _number(row, "credit_limit")
        balance = _number(row, "balance")
        exposure = _number(row, "exposure") or balance
        past_due = _number(row, "past_due_amount")
        days_60_plus = _number(row, "days_60_plus")
        days_90_plus = _number(row, "days_90_plus")
        utilization = (
            _number(row, "utilization_percent")
            if row.get("utilization_percent") is not None
            else ((exposure / credit_limit) * 100 if credit_limit > 0 else 0)
        )
        priority = _risk_priority(
            utilization,
            past_due,
            credit_limit,
            days_60_plus,
            days_90_plus,
        )
        score = _risk_score(
            utilization,
            past_due,
            credit_limit,
            days_60_plus,
            days_90_plus,
        )

        ranked.append(
            {
                "customer_number": int(row["customer_number"]),
                "customer_name": str(row.get("customer_name") or "").strip(),
                "dba_name": "",
                "route_code": str(row.get("route_code") or "").strip(),
                "store_number": None,
                "salesman_number": None,
                "customer_type": "",
                "customer_class": "",
                "active": True,
                "phone": "",
                "email": "",
                "credit_limit": round(credit_limit, 2),
                "balance": round(balance, 2),
                "on_order": 0,
                "credit_on_order": 0,
                "exposure": round(exposure, 2),
                "available_credit": round(credit_limit - exposure, 2),
                "amount_over_limit": round(
                    max(0, exposure - credit_limit),
                    2,
                ),
                "utilization_percent": round(utilization, 2),
                "past_due_amount": round(past_due, 2),
                "is_over_limit": exposure > credit_limit,
                "is_past_due": past_due > 0,
                "risk_score": score,
                "risk_priority": priority,
                "risk_reasons": _risk_reasons(
                    utilization,
                    exposure,
                    credit_limit,
                    past_due,
                    days_60_plus,
                    days_90_plus,
                ),
                "days_60_plus": round(days_60_plus, 2),
                "days_90_plus": round(days_90_plus, 2),
            }
        )

    priority_order = {
        "Critical": 3,
        "High": 2,
        "Elevated": 1,
    }
    ranked.sort(
        key=lambda customer: (
            priority_order[customer["risk_priority"]],
            customer["risk_score"],
            customer["days_90_plus"],
            customer["past_due_amount"],
            customer["exposure"],
        ),
        reverse=True,
    )

    selected = ranked[:limit]

    for index, customer in enumerate(selected, start=1):
        customer["rank"] = index

    return selected
