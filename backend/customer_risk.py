from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

from core.database import madden_database
from customer_risk_service import (
    RISK_REVIEW_CRITERIA,
    rank_customer_risk,
)


router = APIRouter(
    prefix="/api/v1/customer-risk",
    tags=["Customer Intelligence"],
)


RISK_REVIEW_SQL = """
WITH risk_candidates AS (
    SELECT
        CUNUMBER AS customer_number,
        TRIM(CUNAME) AS customer_name,
        TRIM(CUROUTECD) AS route_code,
        COALESCE(CUCRLIMIT, 0) AS credit_limit,
        COALESCE(CUBALANCE, 0) AS balance,
        COALESCE(CUBALANCE, 0) AS exposure,
        (
            GREATEST(COALESCE(CURVCPM30, 0), 0)
            + GREATEST(COALESCE(CURVCPM60, 0), 0)
            + GREATEST(COALESCE(CURVCPM90, 0), 0)
            + GREATEST(COALESCE(CURVCPM120, 0), 0)
        ) AS past_due_amount,
        (
            GREATEST(COALESCE(CURVCPM60, 0), 0)
            + GREATEST(COALESCE(CURVCPM90, 0), 0)
            + GREATEST(COALESCE(CURVCPM120, 0), 0)
        ) AS days_60_plus,
        (
            GREATEST(COALESCE(CURVCPM90, 0), 0)
            + GREATEST(COALESCE(CURVCPM120, 0), 0)
        ) AS days_90_plus,
        (
            COALESCE(CUBALANCE, 0)
            / NULLIF(COALESCE(CUCRLIMIT, 0), 0)
        ) * 100 AS utilization_percent
    FROM DTA273.TMCUST
    WHERE COALESCE(CUCRLIMIT, 0) > 0
      AND COALESCE(CUBALANCE, 0) > 0
)
SELECT
    customer_number,
    customer_name,
    route_code,
    credit_limit,
    balance,
    exposure,
    past_due_amount,
    days_60_plus,
    days_90_plus,
    utilization_percent
FROM risk_candidates
WHERE utilization_percent >= %s
   OR days_60_plus > 0
ORDER BY
    CASE
        WHEN utilization_percent >= 120 OR days_90_plus > 0 THEN 3
        WHEN utilization_percent >= 90 OR days_60_plus > 0 THEN 2
        ELSE 1
    END DESC,
    utilization_percent DESC,
    past_due_amount DESC
LIMIT 1000
"""


@router.get("/review")
def get_customer_risk_review(
    minimum_utilization: float = Query(default=75, ge=1, le=200),
    limit: int = Query(default=100, ge=1, le=250),
) -> dict[str, Any]:
    """
    Return a live, deterministic credit-review queue.

    Madden data remains read-only. Local application code calculates and
    explains priority after the database returns exposure and aging values.
    """
    rows = madden_database.fetch_all(
        RISK_REVIEW_SQL,
        (minimum_utilization,),
    )
    customers = rank_customer_risk(rows, limit)

    return {
        "customers": customers,
        "count": len(customers),
        "threshold_percent": minimum_utilization,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "criteria": RISK_REVIEW_CRITERIA,
    }
