from __future__ import annotations
import hashlib, json, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB = Path(__file__).resolve().parent / "document_learning.db"

def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def initialize_learning_database() -> None:
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS learning_examples(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            document_type TEXT NOT NULL,
            field_name TEXT NOT NULL,
            original_value_json TEXT NOT NULL,
            corrected_value_json TEXT NOT NULL,
            reviewer TEXT NOT NULL DEFAULT '',
            source_status TEXT NOT NULL,
            fingerprint TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_learning_job ON learning_examples(job_id);
        CREATE INDEX IF NOT EXISTS idx_learning_field ON learning_examples(field_name);
        """)

def decode(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value

def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
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
    with connect() as con:
        for field_name, corrected_value in corrected_fields.items():
            original_value = original_fields.get(field_name)
            if json.dumps(original_value, sort_keys=True, default=str) == json.dumps(corrected_value, sort_keys=True, default=str):
                skipped += 1
                continue
            payload = json.dumps({"job_id": job_id, "field_name": field_name, "original_value": original_value, "corrected_value": corrected_value}, sort_keys=True, default=str)
            fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            try:
                cursor = con.execute("""INSERT INTO learning_examples(job_id,document_type,field_name,original_value_json,corrected_value_json,reviewer,source_status,fingerprint,created_at) VALUES(?,?,?,?,?,?,?,?,?)""", (job_id, document_type, field_name, json.dumps(original_value, default=str), json.dumps(corrected_value, default=str), reviewer, source_status, fingerprint, now))
            except sqlite3.IntegrityError:
                skipped += 1
                continue
            created.append(row_to_dict(con.execute("SELECT * FROM learning_examples WHERE id=?", (cursor.lastrowid,)).fetchone()))
    return {"created": len(created), "skipped": skipped, "examples": created}

def list_examples(limit: int = 100) -> dict[str, Any]:
    initialize_learning_database()
    with connect() as con:
        rows = con.execute("SELECT * FROM learning_examples ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        total = con.execute("SELECT COUNT(*) total FROM learning_examples").fetchone()["total"]
    return {"examples": [row_to_dict(row) for row in rows], "total": total}

def get_summary() -> dict[str, Any]:
    initialize_learning_database()
    with connect() as con:
        total = con.execute("SELECT COUNT(*) total FROM learning_examples").fetchone()["total"]
        documents = con.execute("SELECT COUNT(DISTINCT job_id) total FROM learning_examples").fetchone()["total"]
        fields = con.execute("SELECT COUNT(DISTINCT field_name) total FROM learning_examples").fetchone()["total"]
        field_rows = con.execute("SELECT field_name,COUNT(*) total FROM learning_examples GROUP BY field_name ORDER BY total DESC").fetchall()
        type_rows = con.execute("SELECT document_type,COUNT(*) total FROM learning_examples GROUP BY document_type ORDER BY total DESC").fetchall()
        recent_rows = con.execute("SELECT * FROM learning_examples ORDER BY id DESC LIMIT 10").fetchall()
    return {"summary": {"total_examples": total, "unique_documents": documents, "unique_fields": fields, "field_counts": {row["field_name"]: row["total"] for row in field_rows}, "document_type_counts": {row["document_type"]: row["total"] for row in type_rows}, "recent_examples": [row_to_dict(row) for row in recent_rows]}}
