from __future__ import annotations

import hashlib
import json
import threading
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine

from data.mysql import (
    cash_flow_ap_due_date_cache_table,
    cash_flow_forecast_actuals_table,
    cash_flow_forecast_snapshots_table,
    cash_flow_forecast_weeks_table,
    get_engine,
    metadata,
)


class CashFlowForecastIntegrityError(RuntimeError):
    """Raised when a stored forecast/actual record fails its SHA-256
    integrity check."""


_CFF_TABLES = [
    cash_flow_forecast_snapshots_table,
    cash_flow_forecast_weeks_table,
    cash_flow_forecast_actuals_table,
    cash_flow_ap_due_date_cache_table,
]


class CashFlowForecastingNotesRepository:
    """Local ETOP-owned storage for cash flow forecasting.

    Three tables, two different durability rules:
    - `cash_flow_forecast_snapshots` / `_weeks`: append-only (enforced by
      convention in this repository layer). A snapshot is a permanent
      record of what this module projected as of a given date - it must
      never be silently rewritten, the same way every other ETOP
      evidence-note table in this codebase is append-only.
    - `cash_flow_forecast_actuals`: append-only for the same reason - once
      a week's actual figures are recorded, that record stands even if a
      later re-run recomputes it (multiple rows for the same week are
      allowed; callers read the most recent one).
    - `cash_flow_ap_due_date_cache`: NOT append-only. This is a plain
      performance cache of PMHD's open-payable-by-due-week totals
      (PMHD has 5M+ rows with no date-usable index - a live per-request
      query exceeds the platform's statement timeout, confirmed live).
      It is refreshed in place and carries no evidentiary/audit purpose
      of its own.
    """

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialization_lock = threading.Lock()

    def initialize(self) -> None:
        with self._initialization_lock:
            metadata.create_all(self._engine, checkfirst=True, tables=_CFF_TABLES)

    # -- forecast snapshots --------------------------------------------

    def create_snapshot(
        self,
        *,
        snapshot: dict[str, Any],
        weeks: list[dict[str, Any]],
    ) -> str:
        self.initialize()
        evidence_json = json.dumps(
            snapshot["evidence_snapshot"],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )
        evidence_sha256 = hashlib.sha256(evidence_json.encode("utf-8")).hexdigest()

        with self._engine.begin() as connection:
            connection.execute(
                cash_flow_forecast_snapshots_table.insert().values(
                    snapshot_id=snapshot["snapshot_id"],
                    as_of=snapshot["as_of"],
                    generated_at=snapshot["generated_at"],
                    horizon_weeks=snapshot["horizon_weeks"],
                    starting_balance_business_day=snapshot.get(
                        "starting_balance_business_day"
                    ),
                    starting_balance_amount=snapshot.get(
                        "starting_balance_amount"
                    ),
                    loc_balance=snapshot.get("loc_balance"),
                    loc_available=snapshot.get("loc_available"),
                    evidence_snapshot_json=evidence_json,
                    evidence_snapshot_sha256=evidence_sha256,
                )
            )
            for week in weeks:
                connection.execute(
                    cash_flow_forecast_weeks_table.insert().values(
                        week_id=week["week_id"],
                        snapshot_id=snapshot["snapshot_id"],
                        week_index=week["week_index"],
                        week_start=week["week_start"],
                        week_end=week["week_end"],
                        projected_ar=week["projected_ar"],
                        projected_ap=week.get("projected_ap"),
                        projected_ap_on_hold=week.get("projected_ap_on_hold"),
                        projected_other=week["projected_other"],
                        projected_ending_balance=week.get(
                            "projected_ending_balance"
                        ),
                    )
                )
        return snapshot["snapshot_id"]

    def list_snapshots(self, limit: int = 50) -> list[dict[str, Any]]:
        self.initialize()
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    cash_flow_forecast_snapshots_table.c.snapshot_id,
                    cash_flow_forecast_snapshots_table.c.as_of,
                    cash_flow_forecast_snapshots_table.c.generated_at,
                    cash_flow_forecast_snapshots_table.c.horizon_weeks,
                )
                .order_by(
                    cash_flow_forecast_snapshots_table.c.as_of.desc(),
                    cash_flow_forecast_snapshots_table.c.snapshot_id.desc(),
                )
                .limit(limit)
            ).mappings().all()
        return [dict(row) for row in rows]

    # -- actuals ---------------------------------------------------------

    def record_actual(self, record: dict[str, Any]) -> None:
        self.initialize()
        evidence_json = json.dumps(
            record["evidence_snapshot"],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )
        evidence_sha256 = hashlib.sha256(evidence_json.encode("utf-8")).hexdigest()

        with self._engine.begin() as connection:
            connection.execute(
                cash_flow_forecast_actuals_table.insert().values(
                    actual_id=record["actual_id"],
                    week_start=record["week_start"],
                    week_end=record["week_end"],
                    actual_ar=record["actual_ar"],
                    actual_ap=record["actual_ap"],
                    actual_other=record["actual_other"],
                    actual_ending_balance=record.get("actual_ending_balance"),
                    projected_ar=record.get("projected_ar"),
                    projected_ap=record.get("projected_ap"),
                    projected_other=record.get("projected_other"),
                    projected_ending_balance=record.get(
                        "projected_ending_balance"
                    ),
                    recorded_at=record["recorded_at"],
                    evidence_snapshot_json=evidence_json,
                    evidence_snapshot_sha256=evidence_sha256,
                )
            )

    def latest_actual_for_week(
        self, week_start: str, week_end: str
    ) -> dict[str, Any] | None:
        self.initialize()
        with self._engine.connect() as connection:
            row = connection.execute(
                select(cash_flow_forecast_actuals_table)
                .where(
                    cash_flow_forecast_actuals_table.c.week_start == week_start,
                    cash_flow_forecast_actuals_table.c.week_end == week_end,
                )
                .order_by(cash_flow_forecast_actuals_table.c.recorded_at.desc())
                .limit(1)
            ).mappings().first()
        if row is None:
            return None
        return self._actual_from_row(row)

    def list_actuals(self, limit: int = 200) -> list[dict[str, Any]]:
        self.initialize()
        # The original SQLite query used `SELECT * ... GROUP BY week_start,
        # week_end HAVING MAX(recorded_at)`, relying on SQLite's
        # non-standard "bare column in an aggregate query" extension to
        # pick a row per group - it isn't actually guaranteed to be the
        # row with the max recorded_at, and MySQL's default
        # ONLY_FULL_GROUP_BY mode rejects the query outright. A window
        # function is the portable way to get "the latest row per week"
        # on both engines.
        table = cash_flow_forecast_actuals_table
        row_number = (
            func.row_number()
            .over(
                partition_by=[table.c.week_start, table.c.week_end],
                order_by=table.c.recorded_at.desc(),
            )
            .label("row_number")
        )
        ranked = select(table, row_number).subquery()
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(ranked)
                .where(ranked.c.row_number == 1)
                .order_by(ranked.c.week_start.desc())
                .limit(limit)
            ).mappings().all()
        return [self._actual_from_row(row) for row in rows]

    @staticmethod
    def _actual_from_row(row) -> dict[str, Any]:
        snapshot_json = row["evidence_snapshot_json"]
        expected_hash = row["evidence_snapshot_sha256"]
        actual_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
        if actual_hash != expected_hash:
            raise CashFlowForecastIntegrityError(
                "Stored cash flow actual record failed its SHA-256 "
                "integrity check."
            )
        result = {
            key: value
            for key, value in dict(row).items()
            if key != "row_number"
        }
        result["evidence_snapshot"] = json.loads(
            result.pop("evidence_snapshot_json")
        )
        return result

    # -- AP due-date cache (plain, refreshable, not append-only) --------

    def replace_ap_due_date_cache(
        self, buckets: list[dict[str, Any]], *, refreshed_at: str
    ) -> None:
        self.initialize()
        with self._engine.begin() as connection:
            connection.execute(delete(cash_flow_ap_due_date_cache_table))
            for bucket in buckets:
                connection.execute(
                    cash_flow_ap_due_date_cache_table.insert().values(
                        week_start=bucket["week_start"],
                        week_end=bucket["week_end"],
                        open_amount=bucket["open_amount"],
                        open_on_hold_amount=bucket["open_on_hold_amount"],
                        refreshed_at=refreshed_at,
                    )
                )

    def get_ap_due_date_cache(
        self, week_start: str, week_end: str
    ) -> dict[str, Any] | None:
        self.initialize()
        with self._engine.connect() as connection:
            row = connection.execute(
                select(cash_flow_ap_due_date_cache_table).where(
                    cash_flow_ap_due_date_cache_table.c.week_start == week_start,
                    cash_flow_ap_due_date_cache_table.c.week_end == week_end,
                )
            ).mappings().first()
        return dict(row) if row is not None else None

    def ap_cache_refreshed_at(self) -> str | None:
        self.initialize()
        with self._engine.connect() as connection:
            return connection.execute(
                select(func.max(cash_flow_ap_due_date_cache_table.c.refreshed_at))
            ).scalar_one_or_none()


cash_flow_forecasting_notes_repository = CashFlowForecastingNotesRepository()


def initialize_cash_flow_forecasting_database() -> None:
    """Startup migration hook for the shared SQLite initialization boundary."""

    cash_flow_forecasting_notes_repository.initialize()
