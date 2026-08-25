from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .review_schemas import SUPPORTED_UNAVAILABLE_FIELDS

MODULE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = MODULE_DIR / "document_reviews.db"

VALID_STATUSES = {
    "pending",
    "approved",
    "rejected",
    "needs_correction",
    "needs_learning",
}

# This metadata lives inside the existing corrected_fields_json payload so the
# reviewer-clear contract is additive and requires no SQLite migration. The
# namespace cannot collide with a supported invoice field or legacy alias.
UNAVAILABLE_FIELDS_METADATA_KEY = (
    "__etop_document_review_unavailable_fields_v1__"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_review_database() -> None:
    # sqlite3.Connection.__exit__ commits or rolls back but does not close the
    # OS handle. Keep the transaction context and close deterministically so
    # Windows can immediately reuse, move, or back up the database file.
    with closing(connect()) as connection, connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS document_reviews (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                reviewer TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                corrected_fields_json TEXT NOT NULL DEFAULT '{}',
                processing_run_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS document_review_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                status TEXT NOT NULL,
                reviewer TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                corrected_fields_json TEXT NOT NULL DEFAULT '{}',
                processing_run_id TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_review_history_job_id
                ON document_review_history(job_id, created_at DESC);

            CREATE TRIGGER IF NOT EXISTS document_review_history_no_update
            BEFORE UPDATE ON document_review_history
            BEGIN
                SELECT RAISE(ABORT, 'Document review history is append-only.');
            END;

            CREATE TRIGGER IF NOT EXISTS document_review_history_no_delete
            BEFORE DELETE ON document_review_history
            BEGIN
                SELECT RAISE(ABORT, 'Document review history is append-only.');
            END;
            """
        )
        current_columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(document_reviews)"
            ).fetchall()
        }
        if "processing_run_id" not in current_columns:
            connection.execute(
                "ALTER TABLE document_reviews ADD COLUMN processing_run_id TEXT"
            )
        history_columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(document_review_history)"
            ).fetchall()
        }
        if "processing_run_id" not in history_columns:
            connection.execute(
                "ALTER TABLE document_review_history ADD COLUMN processing_run_id TEXT"
            )


def _decode_fields(value: str | None) -> dict[str, Any]:
    if not value:
        return {}

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}

    return parsed if isinstance(parsed, dict) else {}


def _split_review_fields(
    fields: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    corrected_fields = dict(fields)
    raw_unavailable = corrected_fields.pop(
        UNAVAILABLE_FIELDS_METADATA_KEY,
        [],
    )
    unavailable_fields = (
        list(
            dict.fromkeys(
                item
                for item in raw_unavailable
                if isinstance(item, str)
                and item in SUPPORTED_UNAVAILABLE_FIELDS
            )
        )
        if isinstance(raw_unavailable, list)
        else []
    )
    return corrected_fields, unavailable_fields


def pack_review_fields(
    corrected_fields: dict[str, Any],
    unavailable_fields: list[str],
) -> dict[str, Any]:
    """Pack additive reviewer dispositions into the existing JSON payload."""

    if UNAVAILABLE_FIELDS_METADATA_KEY in corrected_fields:
        raise ValueError("The corrected-fields payload contains a reserved key.")
    unsupported = sorted(
        field_name
        for field_name in unavailable_fields
        if field_name not in SUPPORTED_UNAVAILABLE_FIELDS
    )
    if unsupported:
        raise ValueError(
            "Unavailable fields must be supported AP invoice business "
            f"fields; unsupported: {', '.join(unsupported)}"
        )
    normalized_unavailable = list(dict.fromkeys(unavailable_fields))
    conflicts = sorted(
        set(corrected_fields).intersection(normalized_unavailable)
    )
    if conflicts:
        raise ValueError(
            "A review field cannot be both corrected and marked unavailable: "
            + ", ".join(conflicts)
        )
    packed = dict(corrected_fields)
    if normalized_unavailable:
        packed[UNAVAILABLE_FIELDS_METADATA_KEY] = normalized_unavailable
    return packed


def _row_review_fields(row: sqlite3.Row) -> tuple[dict[str, Any], list[str]]:
    return _split_review_fields(_decode_fields(row["corrected_fields_json"]))


def _review_from_row(row: sqlite3.Row) -> dict[str, Any]:
    corrected_fields, unavailable_fields = _row_review_fields(row)
    return {
        "job_id": row["job_id"],
        "status": row["status"],
        "reviewer": row["reviewer"],
        "notes": row["notes"],
        "corrected_fields": corrected_fields,
        "unavailable_fields": unavailable_fields,
        "processing_run_id": row["processing_run_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _history_from_row(row: sqlite3.Row) -> dict[str, Any]:
    corrected_fields, unavailable_fields = _row_review_fields(row)
    return {
        "id": row["id"],
        "job_id": row["job_id"],
        "status": row["status"],
        "reviewer": row["reviewer"],
        "notes": row["notes"],
        "corrected_fields": corrected_fields,
        "unavailable_fields": unavailable_fields,
        "processing_run_id": row["processing_run_id"],
        "created_at": row["created_at"],
    }


def get_review(job_id: str) -> dict[str, Any]:
    initialize_review_database()

    with closing(connect()) as connection, connection:
        row = connection.execute(
            """
            SELECT *
            FROM document_reviews
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()

        history_rows = connection.execute(
            """
            SELECT *
            FROM document_review_history
            WHERE job_id = ?
            ORDER BY id DESC
            """,
            (job_id,),
        ).fetchall()

    if row is None:
        now = utc_now()
        review = {
            "job_id": job_id,
            "status": "pending",
            "reviewer": "",
            "notes": "",
            "corrected_fields": {},
            "unavailable_fields": [],
            "processing_run_id": None,
            "created_at": now,
            "updated_at": now,
        }
    else:
        review = _review_from_row(row)

    return {
        "review": review,
        "history": [
            _history_from_row(history_row)
            for history_row in history_rows
        ],
    }


def save_review(
    job_id: str,
    *,
    processing_run_id: str | None = None,
    status: str,
    reviewer: str,
    notes: str,
    corrected_fields: dict[str, Any],
) -> dict[str, Any]:
    initialize_review_database()

    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid review status: {status}")

    now = utc_now()
    encoded_fields = json.dumps(
        corrected_fields,
        ensure_ascii=False,
        default=str,
    )

    with closing(connect()) as connection, connection:
        existing = connection.execute(
            """
            SELECT created_at
            FROM document_reviews
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()

        created_at = (
            existing["created_at"]
            if existing is not None
            else now
        )

        connection.execute(
            """
            INSERT INTO document_reviews (
                job_id,
                status,
                reviewer,
                notes,
                corrected_fields_json,
                processing_run_id,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                status = excluded.status,
                reviewer = excluded.reviewer,
                notes = excluded.notes,
                corrected_fields_json =
                    excluded.corrected_fields_json,
                processing_run_id = excluded.processing_run_id,
                updated_at = excluded.updated_at
            """,
            (
                job_id,
                status,
                reviewer,
                notes,
                encoded_fields,
                processing_run_id,
                created_at,
                now,
            ),
        )

        connection.execute(
            """
            INSERT INTO document_review_history (
                job_id,
                status,
                reviewer,
                notes,
                corrected_fields_json,
                processing_run_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                status,
                reviewer,
                notes,
                encoded_fields,
                processing_run_id,
                now,
            ),
        )

    return get_review(job_id)


def begin_review_for_processing_run(
    job_id: str,
    processing_run_id: str,
) -> dict[str, Any]:
    """Bind current extraction review state to a newly current run.

    A new parser/OCR result must never inherit a prior run's approval or
    corrections. The prior review record already remains in append-only
    history; this appends an explicit pending boundary for the new run.
    """

    initialize_review_database()
    current = get_review(job_id)["review"]
    if (
        current.get("processing_run_id") == processing_run_id
        and current.get("status") == "pending"
    ):
        return get_review(job_id)
    return save_review(
        job_id,
        processing_run_id=processing_run_id,
        status="pending",
        reviewer="",
        notes=(
            "A new processing run is current. Review and corrections from "
            "prior runs remain in history but do not apply to this extraction."
        ),
        corrected_fields={},
    )
