from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from data.mysql import (
    document_review_history_table,
    document_reviews_table,
    get_engine,
    metadata,
)

from .review_schemas import SUPPORTED_UNAVAILABLE_FIELDS


_TABLES = [document_reviews_table, document_review_history_table]

VALID_STATUSES = {
    "pending",
    "approved",
    "rejected",
    "needs_correction",
    "needs_learning",
}

# This metadata lives inside the existing corrected_fields_json payload so the
# reviewer-clear contract is additive and requires no schema migration. The
# namespace cannot collide with a supported invoice field or legacy alias.
UNAVAILABLE_FIELDS_METADATA_KEY = (
    "__etop_document_review_unavailable_fields_v1__"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_review_database() -> None:
    metadata.create_all(get_engine(), checkfirst=True, tables=_TABLES)


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


def _row_review_fields(row: Any) -> tuple[dict[str, Any], list[str]]:
    return _split_review_fields(_decode_fields(row["corrected_fields_json"]))


def _review_from_row(row: Any) -> dict[str, Any]:
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


def _history_from_row(row: Any) -> dict[str, Any]:
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

    with get_engine().connect() as connection:
        row = connection.execute(
            select(document_reviews_table).where(
                document_reviews_table.c.job_id == job_id
            )
        ).mappings().first()

        history_rows = connection.execute(
            select(document_review_history_table)
            .where(document_review_history_table.c.job_id == job_id)
            .order_by(document_review_history_table.c.id.desc())
        ).mappings().all()

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

    with get_engine().begin() as connection:
        existing = connection.execute(
            select(document_reviews_table.c.created_at).where(
                document_reviews_table.c.job_id == job_id
            )
        ).first()

        created_at = existing[0] if existing is not None else now

        values = dict(
            status=status,
            reviewer=reviewer,
            notes=notes,
            corrected_fields_json=encoded_fields,
            processing_run_id=processing_run_id,
            updated_at=now,
        )
        if existing is None:
            connection.execute(
                document_reviews_table.insert().values(
                    job_id=job_id, created_at=created_at, **values
                )
            )
        else:
            connection.execute(
                document_reviews_table.update()
                .where(document_reviews_table.c.job_id == job_id)
                .values(**values)
            )

        connection.execute(
            document_review_history_table.insert().values(
                job_id=job_id,
                status=status,
                reviewer=reviewer,
                notes=notes,
                corrected_fields_json=encoded_fields,
                processing_run_id=processing_run_id,
                created_at=now,
            )
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
