from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from data.mysql import (
    doc_jobs_table,
    doc_processing_runs_table,
    doc_results_table,
    get_engine,
    metadata,
)

from .settings import settings


_TABLES = [doc_jobs_table, doc_results_table, doc_processing_runs_table]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _legacy_run_id(job_id: str, created_at: str) -> str:
    digest = hashlib.sha256(
        f"legacy:{job_id}:{created_at}".encode("utf-8")
    ).hexdigest()[:24]
    return f"doc-run-{digest}"


def initialize_database() -> None:
    settings.data_root.mkdir(parents=True, exist_ok=True)
    settings.upload_root.mkdir(parents=True, exist_ok=True)
    metadata.create_all(get_engine(), checkfirst=True, tables=_TABLES)


def create_job(record: dict[str, Any]) -> dict[str, Any]:
    initialize_database()

    with get_engine().begin() as connection:
        connection.execute(
            doc_jobs_table.insert().values(
                job_id=record["job_id"],
                original_file_name=record["original_file_name"],
                stored_file_name=record["stored_file_name"],
                stored_path=record["stored_path"],
                content_type=record["content_type"],
                file_size_bytes=record["file_size_bytes"],
                document_type=record["document_type"],
                confidence=record["confidence"],
                status=record["status"],
                message=record["message"],
                created_at=record["created_at"],
                updated_at=record["updated_at"],
                source_sha256=record.get("source_sha256"),
                intake_document_type=record.get("intake_document_type"),
                intake_source=record.get("intake_source"),
                duplicate_of_job_id=record.get("duplicate_of_job_id"),
            )
        )

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

    with get_engine().begin() as connection:
        connection.execute(
            doc_jobs_table.update()
            .where(doc_jobs_table.c.job_id == job_id)
            .values(**values)
        )

    return get_job(job_id)


def set_source_sha256(job_id: str, source_sha256: str) -> dict[str, Any] | None:
    """Backfill a missing immutable source hash without changing file content."""
    initialize_database()
    with get_engine().begin() as connection:
        connection.execute(
            doc_jobs_table.update()
            .where(
                doc_jobs_table.c.job_id == job_id,
                doc_jobs_table.c.source_sha256.is_(None),
            )
            .values(source_sha256=source_sha256, updated_at=utc_now_iso())
        )
    return get_job(job_id)


def find_duplicate_job(
    source_sha256: str,
    *,
    exclude_job_id: str | None = None,
) -> dict[str, Any] | None:
    initialize_database()
    table = doc_jobs_table
    query = select(table).where(table.c.source_sha256 == source_sha256)
    if exclude_job_id:
        query = query.where(table.c.job_id != exclude_job_id)
    query = query.order_by(table.c.created_at.asc()).limit(1)
    with get_engine().connect() as connection:
        row = connection.execute(query).mappings().first()
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

    runs = doc_processing_runs_table
    results = doc_results_table
    with get_engine().begin() as connection:
        row = connection.execute(
            select(func.coalesce(func.max(runs.c.run_number), 0) + 1)
            .where(runs.c.job_id == job_id)
            .with_for_update()
        ).first()
        run_number = int(row[0])
        classification_json = json.dumps(
            classification_evidence, ensure_ascii=False
        )
        extraction_json = json.dumps(extraction, ensure_ascii=False, default=str)
        parsed_json = json.dumps(parsed, ensure_ascii=False, default=str)
        connection.execute(
            runs.insert().values(
                processing_run_id=processing_run_id,
                job_id=job_id,
                run_number=run_number,
                processor_version=processor_version,
                source_sha256=source_sha256,
                status=status,
                classifier=classifier,
                classification_evidence=classification_json,
                extraction_json=extraction_json,
                parsed_json=parsed_json,
                message=message,
                created_at=created_at,
                completed_at=completed_at,
            )
        )
        if make_current:
            existing = connection.execute(
                select(results.c.job_id).where(results.c.job_id == job_id)
            ).first()
            values = dict(
                classifier=classifier or "unavailable",
                classification_evidence=classification_json,
                extraction_json=extraction_json,
                parsed_json=parsed_json,
                updated_at=completed_at,
                processing_run_id=processing_run_id,
                processing_run_number=run_number,
                processor_version=processor_version,
                source_sha256=source_sha256,
            )
            if existing is None:
                connection.execute(
                    results.insert().values(job_id=job_id, created_at=completed_at, **values)
                )
            else:
                connection.execute(
                    results.update().where(results.c.job_id == job_id).values(**values)
                )
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
    with get_engine().connect() as connection:
        row = connection.execute(
            select(doc_results_table).where(doc_results_table.c.job_id == job_id)
        ).mappings().first()
    return _decode_result(dict(row)) if row else None


def get_processing_run(
    job_id: str,
    processing_run_id: str,
) -> dict[str, Any] | None:
    initialize_database()
    table = doc_processing_runs_table
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(
                table.c.job_id == job_id,
                table.c.processing_run_id == processing_run_id,
            )
        ).mappings().first()
    return _decode_result(dict(row)) if row else None


def list_processing_runs(job_id: str) -> list[dict[str, Any]]:
    initialize_database()
    table = doc_processing_runs_table
    with get_engine().connect() as connection:
        rows = connection.execute(
            select(
                table.c.processing_run_id,
                table.c.job_id,
                table.c.run_number,
                table.c.processor_version,
                table.c.source_sha256,
                table.c.status,
                table.c.classifier,
                table.c.message,
                table.c.created_at,
                table.c.completed_at,
                table.c.parsed_json,
                table.c.extraction_json,
            )
            .where(table.c.job_id == job_id)
            .order_by(table.c.run_number.desc())
        ).mappings().all()
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
    with get_engine().connect() as connection:
        row = connection.execute(
            select(doc_jobs_table).where(doc_jobs_table.c.job_id == job_id)
        ).mappings().first()
    return dict(row) if row else None


def list_jobs(
    limit: int = 50,
    *,
    document_type: str | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    initialize_database()
    table = doc_jobs_table
    query = select(table)
    if document_type:
        query = query.where(table.c.document_type == document_type)
    query = (
        query.order_by(table.c.created_at.desc(), table.c.job_id.desc())
        .limit(limit)
        .offset(offset)
    )
    with get_engine().connect() as connection:
        rows = connection.execute(query).mappings().all()
    return [dict(row) for row in rows]


def count_jobs(*, document_type: str | None = None) -> int:
    initialize_database()
    table = doc_jobs_table
    query = select(func.count()).select_from(table)
    if document_type:
        query = query.where(table.c.document_type == document_type)
    with get_engine().connect() as connection:
        return int(connection.execute(query).scalar())
