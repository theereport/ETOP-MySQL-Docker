from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.test_path_override import resolve_test_path_override

MODULE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = resolve_test_path_override(
    "ETOP_TEST_LOCKBOX_REVIEW_DB", MODULE_DIR / "lockbox_review.db"
)
LEGACY_DATABASE_PATH = resolve_test_path_override(
    "ETOP_TEST_LOCKBOX_REVIEW_LEGACY_DB",
    MODULE_DIR.parent / "lockbox_learning.db",
)


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def initialize_database() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect()) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS transaction_reviews (
                job_id TEXT NOT NULL,
                transaction_id TEXT NOT NULL,
                original_allocations_json TEXT NOT NULL,
                allocations_json TEXT NOT NULL,
                customer_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL,
                reviewer TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                override_reason TEXT NOT NULL DEFAULT '',
                misc_gl_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (job_id, transaction_id)
            );
            CREATE INDEX IF NOT EXISTS idx_transaction_reviews_job
                ON transaction_reviews(job_id);

            CREATE TABLE IF NOT EXISTS customer_notes (
                note_id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_number TEXT NOT NULL,
                customer_name TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL,
                author TEXT NOT NULL,
                source_job_id TEXT NOT NULL,
                source_transaction_id TEXT NOT NULL,
                source_check_number TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_customer_notes_customer_created
                ON customer_notes(customer_number, created_at, note_id);
            CREATE TRIGGER IF NOT EXISTS customer_notes_append_only_update
            BEFORE UPDATE ON customer_notes
            BEGIN
                SELECT RAISE(ABORT, 'customer notes are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS customer_notes_append_only_delete
            BEFORE DELETE ON customer_notes
            BEGIN
                SELECT RAISE(ABORT, 'customer notes are append-only');
            END;
            """
        )
        columns = {
            str(row["name"])
            for row in connection.execute(
                "PRAGMA table_info(transaction_reviews)"
            ).fetchall()
        }
        if "customer_json" not in columns:
            connection.execute(
                "ALTER TABLE transaction_reviews "
                "ADD COLUMN customer_json TEXT NOT NULL DEFAULT '{}'"
            )
        if "misc_gl_json" not in columns:
            connection.execute(
                "ALTER TABLE transaction_reviews "
                "ADD COLUMN misc_gl_json TEXT NOT NULL DEFAULT '{}'"
            )
        connection.commit()


def migrate_legacy_reviews(
    job_id: str,
    original_allocations: dict[str, list[dict[str, Any]]],
) -> int:
    """Copy legacy human reviews once without deleting their source store."""

    initialize_database()
    if not LEGACY_DATABASE_PATH.exists():
        return 0
    with closing(sqlite3.connect(LEGACY_DATABASE_PATH)) as legacy:
        legacy.row_factory = sqlite3.Row
        table = legacy.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'lockbox_reviews'"
        ).fetchone()
        if not table:
            return 0
        rows = legacy.execute(
            "SELECT * FROM lockbox_reviews WHERE job_id = ?",
            (job_id,),
        ).fetchall()

    migrated = 0
    with closing(_connect()) as connection:
        for row in rows:
            payload = json.loads(row["review_json"] or "{}")
            customer = {
                key: str(payload.get(key) or "").strip()
                for key in (
                    "customer_number",
                    "customer_name",
                    "customer_phone",
                    "customer_address_line_1",
                    "customer_address_line_2",
                    "customer_city",
                    "customer_state",
                    "customer_postal_code",
                )
            }
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO transaction_reviews (
                    job_id, transaction_id, original_allocations_json,
                    allocations_json, customer_json, status, reviewer,
                    notes, override_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    row["transaction_id"],
                    json.dumps(
                        original_allocations.get(row["transaction_id"], []),
                        ensure_ascii=False,
                    ),
                    json.dumps(payload.get("allocations", []), ensure_ascii=False),
                    json.dumps(customer, ensure_ascii=False),
                    str(payload.get("status") or "corrected"),
                    str(payload.get("reviewer") or ""),
                    str(payload.get("notes") or ""),
                    str(payload.get("override_reason") or ""),
                    row["created_at"],
                    row["updated_at"],
                ),
            )
            migrated += int(cursor.rowcount > 0)
        connection.commit()
    return migrated


def get_reviews(job_id: str) -> dict[str, dict[str, Any]]:
    initialize_database()
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM transaction_reviews WHERE job_id = ?",
            (job_id,),
        ).fetchall()
    return {
        row["transaction_id"]: {
            "original_allocations": json.loads(row["original_allocations_json"]),
            "allocations": json.loads(row["allocations_json"]),
            "customer": json.loads(row["customer_json"] or "{}"),
            "status": row["status"],
            "reviewer": row["reviewer"],
            "notes": row["notes"],
            "override_reason": row["override_reason"],
            "misc_gl": json.loads(row["misc_gl_json"] or "{}"),
            "reviewed_at": row["updated_at"],
        }
        for row in rows
    }


def save_review(
    job_id: str,
    transaction_id: str,
    *,
    original_allocations: list[dict[str, Any]],
    allocations: list[dict[str, Any]],
    customer: dict[str, str],
    status: str,
    reviewer: str,
    notes: str,
    override_reason: str,
    misc_gl: dict[str, Any] | None = None,
) -> None:
    initialize_database()
    now = datetime.now(timezone.utc).isoformat()
    with closing(_connect()) as connection:
        connection.execute(
            """
            INSERT INTO transaction_reviews (
                job_id, transaction_id, original_allocations_json,
                allocations_json, customer_json, status, reviewer, notes,
                override_reason, misc_gl_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, transaction_id) DO UPDATE SET
                allocations_json = excluded.allocations_json,
                customer_json = excluded.customer_json,
                status = excluded.status,
                reviewer = excluded.reviewer,
                notes = excluded.notes,
                override_reason = excluded.override_reason,
                misc_gl_json = excluded.misc_gl_json,
                updated_at = excluded.updated_at
            """,
            (
                job_id,
                transaction_id,
                json.dumps(original_allocations, ensure_ascii=False),
                json.dumps(allocations, ensure_ascii=False),
                json.dumps(customer, ensure_ascii=False),
                status,
                reviewer,
                notes,
                override_reason,
                json.dumps(misc_gl or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        connection.commit()


def get_customer_notes(
    customer_number: str,
    *,
    limit: int = 250,
) -> list[dict[str, Any]]:
    """Return durable notes for one exact ERP customer identity."""

    initialize_database()
    safe_limit = max(1, min(int(limit), 1000))
    with closing(_connect()) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM (
                SELECT note_id, customer_number, customer_name, body, author,
                       source_job_id, source_transaction_id,
                       source_check_number, created_at
                FROM customer_notes
                WHERE customer_number = ?
                ORDER BY created_at DESC, note_id DESC
                LIMIT ?
            ) AS recent_customer_notes
            ORDER BY created_at ASC, note_id ASC
            """,
            (customer_number, safe_limit),
        ).fetchall()
    return [dict(row) for row in rows]


def append_customer_note(
    customer_number: str,
    *,
    customer_name: str,
    body: str,
    author: str,
    source_job_id: str,
    source_transaction_id: str,
    source_check_number: str,
) -> dict[str, Any]:
    """Append one immutable customer note and return its stored projection."""

    initialize_database()
    now = datetime.now(timezone.utc).isoformat()
    with closing(_connect()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO customer_notes (
                customer_number, customer_name, body, author,
                source_job_id, source_transaction_id,
                source_check_number, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_number,
                customer_name,
                body,
                author,
                source_job_id,
                source_transaction_id,
                source_check_number,
                now,
            ),
        )
        note_id = int(cursor.lastrowid)
        connection.commit()
        row = connection.execute(
            """
            SELECT note_id, customer_number, customer_name, body, author,
                   source_job_id, source_transaction_id,
                   source_check_number, created_at
            FROM customer_notes
            WHERE note_id = ?
            """,
            (note_id,),
        ).fetchone()
    if row is None:  # pragma: no cover - SQLite returned the inserted id.
        raise RuntimeError("The customer note could not be reloaded.")
    return dict(row)
