from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import HistoricalPaymentPattern
from core.test_path_override import resolve_test_path_override


class PaymentBehaviorRepository:
    def __init__(
        self,
        db_path: str | Path | None = None,
    ):
        self.db_path = Path(
            db_path
            if db_path is not None
            else resolve_test_path_override(
                "ETOP_TEST_CASH_PAYER_LEARNING_DB",
                "data/modules/document_intelligence/document_intelligence.db",
            )
        )

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS customer_payment_behavior (
                    behavior_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_number TEXT NOT NULL,
                    pattern_type TEXT NOT NULL,
                    pattern_key TEXT NOT NULL,
                    observation_count INTEGER NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    first_observed_at TEXT NOT NULL,
                    last_observed_at TEXT NOT NULL,
                    UNIQUE (
                        customer_number,
                        pattern_type,
                        pattern_key
                    )
                )
                """
            )

    def record_observation(
        self,
        customer_number: str,
        pattern_type: str,
        pattern_key: str,
        was_successful: bool,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO customer_payment_behavior (
                    customer_number,
                    pattern_type,
                    pattern_key,
                    observation_count,
                    success_count,
                    first_observed_at,
                    last_observed_at
                )
                VALUES (?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT (
                    customer_number,
                    pattern_type,
                    pattern_key
                )
                DO UPDATE SET
                    observation_count = observation_count + 1,
                    success_count = success_count + excluded.success_count,
                    last_observed_at = excluded.last_observed_at
                """,
                (
                    customer_number,
                    pattern_type,
                    pattern_key,
                    1 if was_successful else 0,
                    now,
                    now,
                ),
            )

    def get_best_pattern(
        self,
        customer_number: str,
        minimum_observations: int = 3,
    ) -> HistoricalPaymentPattern | None:
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT
                    customer_number,
                    pattern_type,
                    pattern_key,
                    observation_count,
                    success_count,
                    CAST(success_count AS REAL)
                        / NULLIF(observation_count, 0) AS confidence,
                    last_observed_at
                FROM customer_payment_behavior
                WHERE customer_number = ?
                  AND observation_count >= ?
                ORDER BY
                    confidence DESC,
                    observation_count DESC,
                    last_observed_at DESC
                LIMIT 1
                """,
                (customer_number, minimum_observations),
            ).fetchone()

        if not row:
            return None

        return HistoricalPaymentPattern(
            customer_number=row["customer_number"],
            pattern_type=row["pattern_type"],
            pattern_key=row["pattern_key"],
            observation_count=int(row["observation_count"]),
            success_count=int(row["success_count"]),
            confidence=float(row["confidence"] or 0.0),
            last_observed_at=row["last_observed_at"],
        )
