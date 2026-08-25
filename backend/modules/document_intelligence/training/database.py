from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..settings import settings

TRAINING_ROOT = settings.data_root / "training"
DATABASE_PATH = TRAINING_ROOT / "document_training.db"
GROUND_TRUTH_ROOT = TRAINING_ROOT / "ground_truth"


def initialize_database() -> None:
    TRAINING_ROOT.mkdir(parents=True, exist_ok=True)
    GROUND_TRUTH_ROOT.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS training_sessions (
                session_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                dataset_type TEXT NOT NULL,
                source_pdf_name TEXT NOT NULL,
                ground_truth_file_name TEXT NOT NULL,
                ground_truth_path TEXT NOT NULL,
                status TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                comparison_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_training_job_id ON training_sessions(job_id)"
        )
        connection.commit()


def save_session(record: dict[str, Any]) -> dict[str, Any]:
    initialize_database()
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            INSERT INTO training_sessions (
                session_id, job_id, dataset_type, source_pdf_name,
                ground_truth_file_name, ground_truth_path, status,
                metrics_json, comparison_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                ground_truth_file_name=excluded.ground_truth_file_name,
                ground_truth_path=excluded.ground_truth_path,
                status=excluded.status,
                metrics_json=excluded.metrics_json,
                comparison_json=excluded.comparison_json,
                updated_at=excluded.updated_at
            """,
            (
                record["session_id"], record["job_id"], record["dataset_type"],
                record["source_pdf_name"], record["ground_truth_file_name"],
                record["ground_truth_path"], record["status"],
                json.dumps(record["metrics"]), json.dumps(record["transactions"]),
                record["created_at"], record["updated_at"],
            ),
        )
        connection.commit()
    return get_session(record["session_id"])


def _deserialize(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    metrics = json.loads(item.pop("metrics_json"))
    item["transactions"] = json.loads(item.pop("comparison_json"))
    item.pop("ground_truth_path", None)
    item.update(metrics)
    return item


def get_session(session_id: str) -> dict[str, Any] | None:
    initialize_database()
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM training_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    return _deserialize(row) if row else None


def list_sessions(limit: int = 100) -> list[dict[str, Any]]:
    initialize_database()
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM training_sessions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_deserialize(row) for row in rows]
