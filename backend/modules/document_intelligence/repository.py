from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import Any

from .settings import settings


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _add_column(
    connection: sqlite3.Connection,
    table: str,
    definition: str,
) -> None:
    column = definition.split()[0]
    if column not in _columns(connection, table):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _legacy_run_id(job_id: str, created_at: str) -> str:
    digest = hashlib.sha256(
        f"legacy:{job_id}:{created_at}".encode("utf-8")
    ).hexdigest()[:24]
    return f"doc-run-{digest}"


def initialize_database() -> None:
    settings.data_root.mkdir(parents=True, exist_ok=True)
    settings.upload_root.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(settings.database_path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS doc_jobs (
                job_id TEXT PRIMARY KEY,
                original_file_name TEXT NOT NULL,
                stored_file_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                content_type TEXT NOT NULL,
                file_size_bytes INTEGER NOT NULL,
                document_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source_sha256 TEXT,
                intake_document_type TEXT,
                intake_source TEXT,
                duplicate_of_job_id TEXT
            )
            """
        )
        for definition in (
            "source_sha256 TEXT",
            "intake_document_type TEXT",
            "intake_source TEXT",
            "duplicate_of_job_id TEXT",
        ):
            _add_column(connection, "doc_jobs", definition)

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS doc_results (
                job_id TEXT PRIMARY KEY,
                classifier TEXT NOT NULL,
                classification_evidence TEXT NOT NULL,
                extraction_json TEXT NOT NULL,
                parsed_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                processing_run_id TEXT,
                processing_run_number INTEGER,
                processor_version TEXT,
                source_sha256 TEXT,
                FOREIGN KEY(job_id) REFERENCES doc_jobs(job_id)
            )
            """
        )
        for definition in (
            "processing_run_id TEXT",
            "processing_run_number INTEGER",
            "processor_version TEXT",
            "source_sha256 TEXT",
        ):
            _add_column(connection, "doc_results", definition)

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS doc_processing_runs (
                processing_run_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                run_number INTEGER NOT NULL CHECK (run_number > 0),
                processor_version TEXT NOT NULL,
                source_sha256 TEXT,
                status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
                classifier TEXT,
                classification_evidence TEXT NOT NULL,
                extraction_json TEXT NOT NULL,
                parsed_json TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                UNIQUE (job_id, run_number),
                FOREIGN KEY(job_id) REFERENCES doc_jobs(job_id)
            );

            CREATE INDEX IF NOT EXISTS idx_doc_runs_job
                ON doc_processing_runs(job_id, run_number DESC);

            CREATE INDEX IF NOT EXISTS idx_doc_jobs_type_status
                ON doc_jobs(document_type, status, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_doc_jobs_source_hash
                ON doc_jobs(source_sha256, created_at DESC);

            CREATE TRIGGER IF NOT EXISTS doc_processing_runs_no_update
            BEFORE UPDATE ON doc_processing_runs
            BEGIN
                SELECT RAISE(ABORT, 'Document processing runs are append-only.');
            END;

            CREATE TRIGGER IF NOT EXISTS doc_processing_runs_no_delete
            BEFORE DELETE ON doc_processing_runs
            BEGIN
                SELECT RAISE(ABORT, 'Document processing runs are append-only.');
            END;
            """
        )

        # Preserve every pre-v2 current result as an immutable legacy run before
        # a later reprocess can advance the compatibility projection.
        legacy_rows = connection.execute(
            """
            SELECT r.*, j.source_sha256
            FROM doc_results AS r
            JOIN doc_jobs AS j ON j.job_id = r.job_id
            WHERE r.processing_run_id IS NULL
            ORDER BY r.created_at, r.job_id
            """
        ).fetchall()
        for row in legacy_rows:
            values = tuple(row)
            column_names = [item[0] for item in connection.execute(
                "SELECT r.*, j.source_sha256 AS job_source_sha256 "
                "FROM doc_results AS r JOIN doc_jobs AS j ON j.job_id = r.job_id "
                "LIMIT 0"
            ).description]
            record = dict(zip(column_names, values, strict=False))
            run_id = _legacy_run_id(record["job_id"], record["created_at"])
            connection.execute(
                """
                INSERT OR IGNORE INTO doc_processing_runs (
                    processing_run_id, job_id, run_number, processor_version,
                    source_sha256, status, classifier,
                    classification_evidence, extraction_json, parsed_json,
                    message, created_at, completed_at
                ) VALUES (?, ?, 1, ?, ?, 'completed', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    record["job_id"],
                    "legacy-unversioned",
                    record.get("job_source_sha256"),
                    record["classifier"],
                    record["classification_evidence"],
                    record["extraction_json"],
                    record["parsed_json"],
                    "Migrated current result; original processor version was not recorded.",
                    record["created_at"],
                    record["updated_at"],
                ),
            )
            connection.execute(
                """
                UPDATE doc_results
                SET processing_run_id = ?, processing_run_number = 1,
                    processor_version = ?, source_sha256 = ?
                WHERE job_id = ? AND processing_run_id IS NULL
                """,
                (
                    run_id,
                    "legacy-unversioned",
                    record.get("job_source_sha256"),
                    record["job_id"],
                ),
            )
        connection.commit()


def create_job(record: dict[str, Any]) -> dict[str, Any]:
    initialize_database()

    with closing(sqlite3.connect(settings.database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO doc_jobs (
                job_id, original_file_name, stored_file_name, stored_path,
                content_type, file_size_bytes, document_type, confidence,
                status, message, created_at, updated_at, source_sha256,
                intake_document_type, intake_source, duplicate_of_job_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["job_id"],
                record["original_file_name"],
                record["stored_file_name"],
                record["stored_path"],
                record["content_type"],
                record["file_size_bytes"],
                record["document_type"],
                record["confidence"],
                record["status"],
                record["message"],
                record["created_at"],
                record["updated_at"],
                record.get("source_sha256"),
                record.get("intake_document_type"),
                record.get("intake_source"),
                record.get("duplicate_of_job_id"),
            ),
        )
        connection.commit()

    job = get_job(record["job_id"])
    if job is None:
        raise RuntimeError("Document job could not be reloaded after creation.")
    return job


def update_job(
    job_id: str,
    *,
    document_type: str | None = None,
    confidence: float | None = None,
    status: str | None = None,
    message: str | None = None,
) -> dict[str, Any] | None:
    initialize_database()
    current = get_job(job_id)
    if not current:
        return None

    values = {
        "document_type": document_type or current["document_type"],
        "confidence": current["confidence"] if confidence is None else confidence,
        "status": status or current["status"],
        "message": message or current["message"],
        "updated_at": utc_now_iso(),
    }

    with closing(sqlite3.connect(settings.database_path)) as connection, connection:
        connection.execute(
            """
            UPDATE doc_jobs
            SET document_type = ?, confidence = ?, status = ?, message = ?,
                updated_at = ?
            WHERE job_id = ?
            """,
            (
                values["document_type"],
                values["confidence"],
                values["status"],
                values["message"],
                values["updated_at"],
                job_id,
            ),
        )
        connection.commit()

    return get_job(job_id)


def set_source_sha256(job_id: str, source_sha256: str) -> dict[str, Any] | None:
    """Backfill a missing immutable source hash without changing file content."""
    initialize_database()
    with closing(sqlite3.connect(settings.database_path)) as connection, connection:
        connection.execute(
            """
            UPDATE doc_jobs
            SET source_sha256 = ?, updated_at = ?
            WHERE job_id = ? AND source_sha256 IS NULL
            """,
            (source_sha256, utc_now_iso(), job_id),
        )
        connection.commit()
    return get_job(job_id)


def find_duplicate_job(
    source_sha256: str,
    *,
    exclude_job_id: str | None = None,
) -> dict[str, Any] | None:
    initialize_database()
    query = "SELECT * FROM doc_jobs WHERE source_sha256 = ?"
    parameters: list[Any] = [source_sha256]
    if exclude_job_id:
        query += " AND job_id <> ?"
        parameters.append(exclude_job_id)
    query += " ORDER BY created_at ASC LIMIT 1"
    with closing(sqlite3.connect(settings.database_path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(query, parameters).fetchone()
    return dict(row) if row else None


def record_processing_run(
    job_id: str,
    *,
    processing_run_id: str,
    processor_version: str,
    source_sha256: str | None,
    status: str,
    classifier: str | None,
    classification_evidence: list[str],
    extraction: dict[str, Any],
    parsed: dict[str, Any],
    message: str,
    created_at: str,
    completed_at: str,
    make_current: bool,
) -> dict[str, Any]:
    initialize_database()
    if status not in {"completed", "failed"}:
        raise ValueError(f"Unsupported processing run status: {status}")

    with closing(sqlite3.connect(settings.database_path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT COALESCE(MAX(run_number), 0) + 1
            FROM doc_processing_runs
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        run_number = int(row[0])
        classification_json = json.dumps(
            classification_evidence, ensure_ascii=False
        )
        extraction_json = json.dumps(extraction, ensure_ascii=False, default=str)
        parsed_json = json.dumps(parsed, ensure_ascii=False, default=str)
        connection.execute(
            """
            INSERT INTO doc_processing_runs (
                processing_run_id, job_id, run_number, processor_version,
                source_sha256, status, classifier,
                classification_evidence, extraction_json, parsed_json,
                message, created_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                processing_run_id,
                job_id,
                run_number,
                processor_version,
                source_sha256,
                status,
                classifier,
                classification_json,
                extraction_json,
                parsed_json,
                message,
                created_at,
                completed_at,
            ),
        )
        if make_current:
            connection.execute(
                """
                INSERT INTO doc_results (
                    job_id, classifier, classification_evidence,
                    extraction_json, parsed_json, created_at, updated_at,
                    processing_run_id, processing_run_number,
                    processor_version, source_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    classifier = excluded.classifier,
                    classification_evidence = excluded.classification_evidence,
                    extraction_json = excluded.extraction_json,
                    parsed_json = excluded.parsed_json,
                    updated_at = excluded.updated_at,
                    processing_run_id = excluded.processing_run_id,
                    processing_run_number = excluded.processing_run_number,
                    processor_version = excluded.processor_version,
                    source_sha256 = excluded.source_sha256
                """,
                (
                    job_id,
                    classifier or "unavailable",
                    classification_json,
                    extraction_json,
                    parsed_json,
                    completed_at,
                    completed_at,
                    processing_run_id,
                    run_number,
                    processor_version,
                    source_sha256,
                ),
            )
        connection.commit()
    run = get_processing_run(job_id, processing_run_id)
    if run is None:
        raise RuntimeError("Processing run could not be reloaded after creation.")
    return run


def save_result(
    job_id: str,
    *,
    classifier: str,
    classification_evidence: list[str],
    extraction: dict,
    parsed: dict,
) -> None:
    """Compatibility writer retained for older call sites.

    New processing code must call ``record_processing_run`` so the prior
    result remains reconstructable.
    """
    now = utc_now_iso()
    record_processing_run(
        job_id,
        processing_run_id=(
            "doc-run-" + hashlib.sha256(
                f"compat:{job_id}:{now}".encode("utf-8")
            ).hexdigest()[:24]
        ),
        processor_version="compatibility-writer.v1",
        source_sha256=(get_job(job_id) or {}).get("source_sha256"),
        status="completed",
        classifier=classifier,
        classification_evidence=classification_evidence,
        extraction=extraction,
        parsed=parsed,
        message="Compatibility result writer completed.",
        created_at=now,
        completed_at=now,
        make_current=True,
    )


def _decode_result(record: dict[str, Any]) -> dict[str, Any]:
    record["classification_evidence"] = json.loads(
        record["classification_evidence"]
    )
    record["extraction"] = json.loads(record.pop("extraction_json"))
    record["parsed"] = json.loads(record.pop("parsed_json"))
    return record


def get_result(job_id: str) -> dict[str, Any] | None:
    initialize_database()
    with closing(sqlite3.connect(settings.database_path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM doc_results WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    return _decode_result(dict(row)) if row else None


def get_processing_run(
    job_id: str,
    processing_run_id: str,
) -> dict[str, Any] | None:
    initialize_database()
    with closing(sqlite3.connect(settings.database_path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT * FROM doc_processing_runs
            WHERE job_id = ? AND processing_run_id = ?
            """,
            (job_id, processing_run_id),
        ).fetchone()
    return _decode_result(dict(row)) if row else None


def list_processing_runs(job_id: str) -> list[dict[str, Any]]:
    initialize_database()
    with closing(sqlite3.connect(settings.database_path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT processing_run_id, job_id, run_number, processor_version,
                   source_sha256, status, classifier, message, created_at,
                   completed_at, parsed_json, extraction_json
            FROM doc_processing_runs
            WHERE job_id = ?
            ORDER BY run_number DESC
            """,
            (job_id,),
        ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        parsed = json.loads(record.pop("parsed_json"))
        extraction = json.loads(record.pop("extraction_json"))
        record["parser"] = parsed.get("parser") if isinstance(parsed, dict) else None
        record["parser_version"] = (
            parsed.get("parser_version") if isinstance(parsed, dict) else None
        )
        record["ocr_engine"] = (
            extraction.get("ocr_engine")
            if isinstance(extraction, dict)
            else None
        )
        record["ocr_engine_version"] = (
            extraction.get("ocr_engine_version")
            if isinstance(extraction, dict)
            else None
        )
        results.append(record)
    return results


def get_job(job_id: str) -> dict[str, Any] | None:
    initialize_database()
    with closing(sqlite3.connect(settings.database_path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM doc_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    return dict(row) if row else None


def list_jobs(
    limit: int = 50,
    *,
    document_type: str | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    initialize_database()
    query = "SELECT * FROM doc_jobs"
    parameters: list[Any] = []
    if document_type:
        query += " WHERE document_type = ?"
        parameters.append(document_type)
    query += " ORDER BY created_at DESC, job_id DESC LIMIT ? OFFSET ?"
    parameters.extend((limit, offset))
    with closing(sqlite3.connect(settings.database_path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


def count_jobs(*, document_type: str | None = None) -> int:
    initialize_database()
    query = "SELECT COUNT(*) FROM doc_jobs"
    parameters: tuple[Any, ...] = ()
    if document_type:
        query += " WHERE document_type = ?"
        parameters = (document_type,)
    with closing(sqlite3.connect(settings.database_path)) as connection, connection:
        return int(connection.execute(query, parameters).fetchone()[0])
