from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Callable
from typing import Any

from data.database import get_connection


class CashFlowForecastIntegrityError(RuntimeError):
    """Raised when a stored forecast/actual record fails its SHA-256
    integrity check."""


class CashFlowForecastingNotesRepository:
    """Local ETOP-owned storage for cash flow forecasting.

    Three tables, two different durability rules:
    - `cash_flow_forecast_snapshots` / `_weeks`: append-only (update and
      delete blocked by trigger). A snapshot is a permanent record of
      what this module projected as of a given date - it must never be
      silently rewritten, the same way every other ETOP evidence-note
      table in this codebase is append-only.
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

    def __init__(
        self,
        connection_factory: Callable[[], sqlite3.Connection] = get_connection,
    ) -> None:
        self._connection_factory = connection_factory
        self._initialization_lock = threading.Lock()

    def _connection(self) -> sqlite3.Connection:
        connection = self._connection_factory()
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        return connection

    def initialize(self) -> None:
        with self._initialization_lock:
            connection = self._connection()
            try:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS cash_flow_forecast_snapshots (
                        snapshot_id TEXT PRIMARY KEY,
                        as_of TEXT NOT NULL,
                        generated_at TEXT NOT NULL,
                        horizon_weeks INTEGER NOT NULL,
                        starting_balance_business_day TEXT,
                        starting_balance_amount REAL,
                        loc_balance REAL,
                        loc_available REAL,
                        evidence_snapshot_json TEXT NOT NULL,
                        evidence_snapshot_sha256 TEXT NOT NULL
                            CHECK (length(evidence_snapshot_sha256) = 64)
                    );

                    CREATE INDEX IF NOT EXISTS idx_cff_snapshots_as_of
                    ON cash_flow_forecast_snapshots(as_of DESC, snapshot_id DESC);

                    CREATE TRIGGER IF NOT EXISTS cff_snapshots_no_update
                    BEFORE UPDATE ON cash_flow_forecast_snapshots
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'Cash flow forecast snapshots are append-only.'
                        );
                    END;

                    CREATE TRIGGER IF NOT EXISTS cff_snapshots_no_delete
                    BEFORE DELETE ON cash_flow_forecast_snapshots
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'Cash flow forecast snapshots are append-only.'
                        );
                    END;

                    CREATE TABLE IF NOT EXISTS cash_flow_forecast_weeks (
                        week_id TEXT PRIMARY KEY,
                        snapshot_id TEXT NOT NULL
                            REFERENCES cash_flow_forecast_snapshots(snapshot_id),
                        week_index INTEGER NOT NULL,
                        week_start TEXT NOT NULL,
                        week_end TEXT NOT NULL,
                        projected_ar REAL NOT NULL,
                        projected_ap REAL,
                        projected_ap_on_hold REAL,
                        projected_other REAL NOT NULL,
                        projected_ending_balance REAL
                    );

                    CREATE INDEX IF NOT EXISTS idx_cff_weeks_snapshot
                    ON cash_flow_forecast_weeks(snapshot_id, week_index);

                    CREATE TRIGGER IF NOT EXISTS cff_weeks_no_update
                    BEFORE UPDATE ON cash_flow_forecast_weeks
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'Cash flow forecast weeks are append-only.'
                        );
                    END;

                    CREATE TRIGGER IF NOT EXISTS cff_weeks_no_delete
                    BEFORE DELETE ON cash_flow_forecast_weeks
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'Cash flow forecast weeks are append-only.'
                        );
                    END;

                    CREATE TABLE IF NOT EXISTS cash_flow_forecast_actuals (
                        actual_id TEXT PRIMARY KEY,
                        week_start TEXT NOT NULL,
                        week_end TEXT NOT NULL,
                        actual_ar REAL NOT NULL,
                        actual_ap REAL NOT NULL,
                        actual_other REAL NOT NULL,
                        actual_ending_balance REAL,
                        projected_ar REAL,
                        projected_ap REAL,
                        projected_other REAL,
                        projected_ending_balance REAL,
                        recorded_at TEXT NOT NULL,
                        evidence_snapshot_json TEXT NOT NULL,
                        evidence_snapshot_sha256 TEXT NOT NULL
                            CHECK (length(evidence_snapshot_sha256) = 64)
                    );

                    CREATE INDEX IF NOT EXISTS idx_cff_actuals_week
                    ON cash_flow_forecast_actuals(
                        week_start, week_end, recorded_at DESC
                    );

                    CREATE TRIGGER IF NOT EXISTS cff_actuals_no_update
                    BEFORE UPDATE ON cash_flow_forecast_actuals
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'Cash flow forecast actuals are append-only.'
                        );
                    END;

                    CREATE TRIGGER IF NOT EXISTS cff_actuals_no_delete
                    BEFORE DELETE ON cash_flow_forecast_actuals
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'Cash flow forecast actuals are append-only.'
                        );
                    END;

                    CREATE TABLE IF NOT EXISTS cash_flow_ap_due_date_cache (
                        week_start TEXT PRIMARY KEY,
                        week_end TEXT NOT NULL,
                        open_amount REAL NOT NULL,
                        open_on_hold_amount REAL NOT NULL,
                        refreshed_at TEXT NOT NULL
                    );
                    """
                )
                connection.commit()
            finally:
                connection.close()

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

        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute(
                """
                INSERT INTO cash_flow_forecast_snapshots (
                    snapshot_id, as_of, generated_at, horizon_weeks,
                    starting_balance_business_day, starting_balance_amount,
                    loc_balance, loc_available,
                    evidence_snapshot_json, evidence_snapshot_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    snapshot["snapshot_id"],
                    snapshot["as_of"],
                    snapshot["generated_at"],
                    snapshot["horizon_weeks"],
                    snapshot.get("starting_balance_business_day"),
                    snapshot.get("starting_balance_amount"),
                    snapshot.get("loc_balance"),
                    snapshot.get("loc_available"),
                    evidence_json,
                    evidence_sha256,
                ),
            )
            for week in weeks:
                connection.execute(
                    """
                    INSERT INTO cash_flow_forecast_weeks (
                        week_id, snapshot_id, week_index, week_start,
                        week_end, projected_ar, projected_ap,
                        projected_ap_on_hold, projected_other,
                        projected_ending_balance
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        week["week_id"],
                        snapshot["snapshot_id"],
                        week["week_index"],
                        week["week_start"],
                        week["week_end"],
                        week["projected_ar"],
                        week.get("projected_ap"),
                        week.get("projected_ap_on_hold"),
                        week["projected_other"],
                        week.get("projected_ending_balance"),
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return snapshot["snapshot_id"]

    def list_snapshots(self, limit: int = 50) -> list[dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT snapshot_id, as_of, generated_at, horizon_weeks
                FROM cash_flow_forecast_snapshots
                ORDER BY as_of DESC, snapshot_id DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()
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

        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute(
                """
                INSERT INTO cash_flow_forecast_actuals (
                    actual_id, week_start, week_end, actual_ar, actual_ap,
                    actual_other, actual_ending_balance, projected_ar,
                    projected_ap, projected_other, projected_ending_balance,
                    recorded_at, evidence_snapshot_json,
                    evidence_snapshot_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record["actual_id"],
                    record["week_start"],
                    record["week_end"],
                    record["actual_ar"],
                    record["actual_ap"],
                    record["actual_other"],
                    record.get("actual_ending_balance"),
                    record.get("projected_ar"),
                    record.get("projected_ap"),
                    record.get("projected_other"),
                    record.get("projected_ending_balance"),
                    record["recorded_at"],
                    evidence_json,
                    evidence_sha256,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def latest_actual_for_week(
        self, week_start: str, week_end: str
    ) -> dict[str, Any] | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT * FROM cash_flow_forecast_actuals
                WHERE week_start = ? AND week_end = ?
                ORDER BY recorded_at DESC
                LIMIT 1;
                """,
                (week_start, week_end),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return self._actual_from_row(row)

    def list_actuals(self, limit: int = 200) -> list[dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT * FROM cash_flow_forecast_actuals
                GROUP BY week_start, week_end
                HAVING MAX(recorded_at)
                ORDER BY week_start DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()
        return [self._actual_from_row(row) for row in rows]

    @staticmethod
    def _actual_from_row(row: sqlite3.Row) -> dict[str, Any]:
        snapshot_json = row["evidence_snapshot_json"]
        expected_hash = row["evidence_snapshot_sha256"]
        actual_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
        if actual_hash != expected_hash:
            raise CashFlowForecastIntegrityError(
                "Stored cash flow actual record failed its SHA-256 "
                "integrity check."
            )
        result = dict(row)
        result["evidence_snapshot"] = json.loads(
            result.pop("evidence_snapshot_json")
        )
        return result

    # -- AP due-date cache (plain, refreshable, not append-only) --------

    def replace_ap_due_date_cache(
        self, buckets: list[dict[str, Any]], *, refreshed_at: str
    ) -> None:
        self.initialize()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute("DELETE FROM cash_flow_ap_due_date_cache;")
            connection.executemany(
                """
                INSERT INTO cash_flow_ap_due_date_cache (
                    week_start, week_end, open_amount, open_on_hold_amount,
                    refreshed_at
                ) VALUES (?, ?, ?, ?, ?);
                """,
                [
                    (
                        bucket["week_start"],
                        bucket["week_end"],
                        bucket["open_amount"],
                        bucket["open_on_hold_amount"],
                        refreshed_at,
                    )
                    for bucket in buckets
                ],
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_ap_due_date_cache(
        self, week_start: str, week_end: str
    ) -> dict[str, Any] | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT * FROM cash_flow_ap_due_date_cache
                WHERE week_start = ? AND week_end = ?;
                """,
                (week_start, week_end),
            ).fetchone()
        finally:
            connection.close()
        return dict(row) if row is not None else None

    def ap_cache_refreshed_at(self) -> str | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                "SELECT MAX(refreshed_at) AS refreshed_at "
                "FROM cash_flow_ap_due_date_cache;"
            ).fetchone()
        finally:
            connection.close()
        return row["refreshed_at"] if row is not None else None


cash_flow_forecasting_notes_repository = CashFlowForecastingNotesRepository()


def initialize_cash_flow_forecasting_database() -> None:
    """Startup migration hook for the shared SQLite initialization boundary."""

    cash_flow_forecasting_notes_repository.initialize()
