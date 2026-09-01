from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.engine import Engine

from data.mysql import customer_payment_behavior_table, get_engine, metadata

from .models import HistoricalPaymentPattern


class PaymentBehaviorRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()

    def initialize(self) -> None:
        metadata.create_all(
            self._engine, checkfirst=True, tables=[customer_payment_behavior_table]
        )

    def record_observation(
        self,
        customer_number: str,
        pattern_type: str,
        pattern_key: str,
        was_successful: bool,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.initialize()
        table = customer_payment_behavior_table
        with self._engine.begin() as connection:
            existing = connection.execute(
                select(table.c.behavior_id).where(
                    table.c.customer_number == customer_number,
                    table.c.pattern_type == pattern_type,
                    table.c.pattern_key == pattern_key,
                )
            ).first()
            if existing is None:
                connection.execute(
                    table.insert().values(
                        customer_number=customer_number,
                        pattern_type=pattern_type,
                        pattern_key=pattern_key,
                        observation_count=1,
                        success_count=1 if was_successful else 0,
                        first_observed_at=now,
                        last_observed_at=now,
                    )
                )
            else:
                connection.execute(
                    table.update()
                    .where(table.c.behavior_id == existing[0])
                    .values(
                        observation_count=table.c.observation_count + 1,
                        success_count=table.c.success_count
                        + (1 if was_successful else 0),
                        last_observed_at=now,
                    )
                )

    def get_best_pattern(
        self,
        customer_number: str,
        minimum_observations: int = 3,
    ) -> HistoricalPaymentPattern | None:
        self.initialize()
        table = customer_payment_behavior_table
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(table).where(
                    table.c.customer_number == customer_number,
                    table.c.observation_count >= minimum_observations,
                )
            ).mappings().all()

        if not rows:
            return None

        def confidence(row) -> float:
            return (
                row["success_count"] / row["observation_count"]
                if row["observation_count"]
                else 0.0
            )

        best = max(
            rows,
            key=lambda row: (
                confidence(row),
                row["observation_count"],
                row["last_observed_at"],
            ),
        )

        return HistoricalPaymentPattern(
            customer_number=best["customer_number"],
            pattern_type=best["pattern_type"],
            pattern_key=best["pattern_key"],
            observation_count=int(best["observation_count"]),
            success_count=int(best["success_count"]),
            confidence=confidence(best),
            last_observed_at=best["last_observed_at"],
        )
