from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from data.mysql import (
    get_engine,
    lockbox_customer_notes_table,
    lockbox_reviews_table,
    lockbox_transaction_reviews_table,
    metadata,
)

_TABLES = [lockbox_transaction_reviews_table, lockbox_customer_notes_table]


def initialize_database() -> None:
    metadata.create_all(get_engine(), checkfirst=True, tables=_TABLES)


def migrate_legacy_reviews(
    job_id: str,
    original_allocations: dict[str, list[dict[str, Any]]],
) -> int:
    """Copy legacy human reviews once without deleting their source store."""

    initialize_database()
    # lockbox_reviews belongs to the legacy lockbox_service module, but a
    # fresh test engine may not have created it yet - ensure it exists here
    # too (idempotent) so this read never hits a missing-table error.
    metadata.create_all(get_engine(), checkfirst=True, tables=[lockbox_reviews_table])
    legacy = lockbox_reviews_table
    target = lockbox_transaction_reviews_table
    with get_engine().begin() as connection:
        rows = connection.execute(
            select(legacy).where(legacy.c.job_id == job_id)
        ).mappings().all()

        migrated = 0
        for row in rows:
            existing = connection.execute(
                select(target.c.job_id).where(
                    target.c.job_id == job_id,
                    target.c.transaction_id == row["transaction_id"],
                )
            ).first()
            if existing is not None:
                continue
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
            connection.execute(
                target.insert().values(
                    job_id=job_id,
                    transaction_id=row["transaction_id"],
                    original_allocations_json=json.dumps(
                        original_allocations.get(row["transaction_id"], []),
                        ensure_ascii=False,
                    ),
                    allocations_json=json.dumps(
                        payload.get("allocations", []), ensure_ascii=False
                    ),
                    customer_json=json.dumps(customer, ensure_ascii=False),
                    status=str(payload.get("status") or "corrected"),
                    reviewer=str(payload.get("reviewer") or ""),
                    notes=str(payload.get("notes") or ""),
                    override_reason=str(payload.get("override_reason") or ""),
                    misc_gl_json="{}",
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )
            migrated += 1
    return migrated


def get_reviews(job_id: str) -> dict[str, dict[str, Any]]:
    initialize_database()
    table = lockbox_transaction_reviews_table
    with get_engine().connect() as connection:
        rows = connection.execute(
            select(table).where(table.c.job_id == job_id)
        ).mappings().all()
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
    table = lockbox_transaction_reviews_table
    values = dict(
        allocations_json=json.dumps(allocations, ensure_ascii=False),
        customer_json=json.dumps(customer, ensure_ascii=False),
        status=status,
        reviewer=reviewer,
        notes=notes,
        override_reason=override_reason,
        misc_gl_json=json.dumps(misc_gl or {}, ensure_ascii=False),
        updated_at=now,
    )
    with get_engine().begin() as connection:
        existing = connection.execute(
            select(table.c.job_id).where(
                table.c.job_id == job_id, table.c.transaction_id == transaction_id
            )
        ).first()
        if existing is None:
            connection.execute(
                table.insert().values(
                    job_id=job_id,
                    transaction_id=transaction_id,
                    original_allocations_json=json.dumps(
                        original_allocations, ensure_ascii=False
                    ),
                    created_at=now,
                    **values,
                )
            )
        else:
            connection.execute(
                table.update()
                .where(
                    table.c.job_id == job_id, table.c.transaction_id == transaction_id
                )
                .values(**values)
            )


def get_customer_notes(
    customer_number: str,
    *,
    limit: int = 250,
) -> list[dict[str, Any]]:
    """Return durable notes for one exact ERP customer identity."""

    initialize_database()
    table = lockbox_customer_notes_table
    safe_limit = max(1, min(int(limit), 1000))
    recent = (
        select(table)
        .where(table.c.customer_number == customer_number)
        .order_by(table.c.created_at.desc(), table.c.note_id.desc())
        .limit(safe_limit)
        .subquery()
    )
    with get_engine().connect() as connection:
        rows = connection.execute(
            select(recent).order_by(recent.c.created_at, recent.c.note_id)
        ).mappings().all()
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
    table = lockbox_customer_notes_table
    with get_engine().begin() as connection:
        result = connection.execute(
            table.insert().values(
                customer_number=customer_number,
                customer_name=customer_name,
                body=body,
                author=author,
                source_job_id=source_job_id,
                source_transaction_id=source_transaction_id,
                source_check_number=source_check_number,
                created_at=now,
            )
        )
        note_id = result.inserted_primary_key[0]
        row = connection.execute(
            select(table).where(table.c.note_id == note_id)
        ).mappings().first()
    if row is None:  # pragma: no cover - the database returned the inserted id.
        raise RuntimeError("The customer note could not be reloaded.")
    return dict(row)
