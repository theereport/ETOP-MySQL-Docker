from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from data.mysql import document_learning_examples_table, get_engine, metadata

_TABLE = document_learning_examples_table


def initialize_learning_database() -> None:
    metadata.create_all(get_engine(), checkfirst=True, tables=[_TABLE])

def decode(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value

def row_to_dict(row) -> dict[str, Any]:
    return {
        "id": row["id"], "job_id": row["job_id"], "document_type": row["document_type"],
        "field_name": row["field_name"], "original_value": decode(row["original_value_json"]),
        "corrected_value": decode(row["corrected_value_json"]), "reviewer": row["reviewer"],
        "source_status": row["source_status"], "fingerprint": row["fingerprint"],
        "created_at": row["created_at"],
    }

def create_examples(*, job_id: str, document_type: str, original_fields: dict[str, Any], corrected_fields: dict[str, Any], reviewer: str, source_status: str) -> dict[str, Any]:
    initialize_learning_database()
    created, skipped = [], 0
    now = datetime.now(timezone.utc).isoformat()
    with get_engine().begin() as connection:
        for field_name, corrected_value in corrected_fields.items():
            original_value = original_fields.get(field_name)
            if json.dumps(original_value, sort_keys=True, default=str) == json.dumps(corrected_value, sort_keys=True, default=str):
                skipped += 1
                continue
            payload = json.dumps({"job_id": job_id, "field_name": field_name, "original_value": original_value, "corrected_value": corrected_value}, sort_keys=True, default=str)
            fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            try:
                result = connection.execute(
                    _TABLE.insert().values(
                        job_id=job_id, document_type=document_type, field_name=field_name,
                        original_value_json=json.dumps(original_value, default=str),
                        corrected_value_json=json.dumps(corrected_value, default=str),
                        reviewer=reviewer, source_status=source_status,
                        fingerprint=fingerprint, created_at=now,
                    )
                )
            except IntegrityError:
                skipped += 1
                continue
            new_id = result.inserted_primary_key[0]
            row = connection.execute(select(_TABLE).where(_TABLE.c.id == new_id)).mappings().first()
            created.append(row_to_dict(row))
    return {"created": len(created), "skipped": skipped, "examples": created}

def list_examples(limit: int = 100) -> dict[str, Any]:
    initialize_learning_database()
    with get_engine().connect() as connection:
        rows = connection.execute(
            select(_TABLE).order_by(_TABLE.c.id.desc()).limit(limit)
        ).mappings().all()
        total = connection.execute(select(func.count()).select_from(_TABLE)).scalar()
    return {"examples": [row_to_dict(row) for row in rows], "total": total}

def get_summary() -> dict[str, Any]:
    initialize_learning_database()
    with get_engine().connect() as connection:
        total = connection.execute(select(func.count()).select_from(_TABLE)).scalar()
        documents = connection.execute(
            select(func.count(func.distinct(_TABLE.c.job_id)))
        ).scalar()
        fields = connection.execute(
            select(func.count(func.distinct(_TABLE.c.field_name)))
        ).scalar()
        field_rows = connection.execute(
            select(_TABLE.c.field_name, func.count().label("total"))
            .group_by(_TABLE.c.field_name)
            .order_by(func.count().desc())
        ).all()
        type_rows = connection.execute(
            select(_TABLE.c.document_type, func.count().label("total"))
            .group_by(_TABLE.c.document_type)
            .order_by(func.count().desc())
        ).all()
        recent_rows = connection.execute(
            select(_TABLE).order_by(_TABLE.c.id.desc()).limit(10)
        ).mappings().all()
    return {"summary": {"total_examples": total, "unique_documents": documents, "unique_fields": fields, "field_counts": {row[0]: row[1] for row in field_rows}, "document_type_counts": {row[0]: row[1] for row in type_rows}, "recent_examples": [row_to_dict(row) for row in recent_rows]}}
