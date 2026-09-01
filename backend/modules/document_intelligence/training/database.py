from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from data.mysql import document_training_sessions_table, get_engine, metadata

from ..settings import settings

TRAINING_ROOT = settings.data_root / "training"
GROUND_TRUTH_ROOT = TRAINING_ROOT / "ground_truth"

_TABLE = document_training_sessions_table


def initialize_database() -> None:
    TRAINING_ROOT.mkdir(parents=True, exist_ok=True)
    GROUND_TRUTH_ROOT.mkdir(parents=True, exist_ok=True)
    metadata.create_all(get_engine(), checkfirst=True, tables=[_TABLE])


def save_session(record: dict[str, Any]) -> dict[str, Any]:
    initialize_database()
    values = dict(
        job_id=record["job_id"],
        dataset_type=record["dataset_type"],
        source_pdf_name=record["source_pdf_name"],
        ground_truth_file_name=record["ground_truth_file_name"],
        ground_truth_path=record["ground_truth_path"],
        status=record["status"],
        metrics_json=json.dumps(record["metrics"]),
        comparison_json=json.dumps(record["transactions"]),
        updated_at=record["updated_at"],
    )
    with get_engine().begin() as connection:
        existing = connection.execute(
            select(_TABLE.c.session_id).where(
                _TABLE.c.session_id == record["session_id"]
            )
        ).first()
        if existing is None:
            connection.execute(
                _TABLE.insert().values(
                    session_id=record["session_id"],
                    created_at=record["created_at"],
                    **values,
                )
            )
        else:
            connection.execute(
                _TABLE.update()
                .where(_TABLE.c.session_id == record["session_id"])
                .values(**values)
            )
    return get_session(record["session_id"])


def _deserialize(row) -> dict[str, Any]:
    item = dict(row)
    metrics = json.loads(item.pop("metrics_json"))
    item["transactions"] = json.loads(item.pop("comparison_json"))
    item.pop("ground_truth_path", None)
    item.update(metrics)
    return item


def get_session(session_id: str) -> dict[str, Any] | None:
    initialize_database()
    with get_engine().connect() as connection:
        row = connection.execute(
            select(_TABLE).where(_TABLE.c.session_id == session_id)
        ).mappings().first()
    return _deserialize(row) if row else None


def list_sessions(limit: int = 100) -> list[dict[str, Any]]:
    initialize_database()
    with get_engine().connect() as connection:
        rows = connection.execute(
            select(_TABLE).order_by(_TABLE.c.created_at.desc()).limit(limit)
        ).mappings().all()
    return [_deserialize(row) for row in rows]
