from __future__ import annotations

import asyncio
import hashlib
import re
from contextlib import contextmanager
from threading import RLock
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import fitz
from fastapi import HTTPException, UploadFile

from . import repository
from .classifiers import classify_document
from .extractors import extract_pdf_text, extract_vendor_invoice_text
from .parsers import parser_registry
from .ocr_engine import ocr_region as _ocr_region
from .ocr_engine import tesseract_available
from .review_store import begin_review_for_processing_run, save_review
from .review_store import get_review as _get_review
from .settings import settings


ALLOWED_PDF_CONTENT_TYPES = {
    "",
    "application/octet-stream",
    "application/pdf",
    "application/x-pdf",
}
VENDOR_INVOICE_INTAKE_VERSION = "vendor-invoice-intake.v2"
_PROCESSING_REVIEW_LOCK = RLock()


def _vendor_invoice_review_message(
    parsed: dict[str, Any],
    extraction: dict[str, Any],
) -> str:
    """Describe extraction quality without implying accounting authority."""

    summary = parsed.get("field_summary")
    summary_message = (
        str(summary.get("message") or "").strip()
        if isinstance(summary, dict)
        else ""
    )
    if not summary_message:
        fields = parsed.get("fields") if isinstance(parsed, dict) else {}
        available = fields if isinstance(fields, dict) else {}
        missing = [
            label
            for field_name, label in (
                ("vendor_name", "vendor name"),
                ("invoice_number", "invoice number"),
                ("total_amount", "invoice total"),
            )
            if field_name not in available
        ]
        source_kind = str(extraction.get("text_source_summary") or "")
        if source_kind == "native_pdf_text":
            source_message = "Native PDF text was extracted"
        elif source_kind == "local_tesseract_ocr":
            source_message = "Local OCR text was extracted"
        elif source_kind == "mixed_native_and_ocr":
            source_message = "Native PDF and local OCR text were extracted"
        else:
            source_message = "Invoice text extraction completed"
        summary_message = (
            f"{source_message}, but key fields need review: {', '.join(missing)}."
            if missing
            else (
                f"{source_message}; all three key fields were recognized. "
                "Human review remains required."
            )
        )

    attempted_pages = extraction.get("ocr_attempted_pages") or []
    completed_pages = extraction.get("ocr_completed_pages") or []
    failed_pages = extraction.get("ocr_failed_pages") or []
    skipped_pages = extraction.get("ocr_skipped_pages") or []
    if failed_pages or skipped_pages:
        if attempted_pages:
            ocr_message = (
                f"Local OCR completed on {len(completed_pages)} of "
                f"{len(attempted_pages)} attempted pages; failed or skipped "
                "pages need review."
            )
        else:
            ocr_message = (
                "Local OCR was required, but failed or was skipped before any "
                "page was attempted; affected pages need review."
            )
    elif not attempted_pages and str(
        extraction.get("text_source_summary") or ""
    ) == "native_pdf_text":
        ocr_message = "OCR was not needed."
    elif attempted_pages:
        ocr_message = (
            f"Local OCR completed on {len(completed_pages)} of "
            f"{len(attempted_pages)} attempted pages."
        )
    else:
        ocr_message = "OCR status is unavailable."
    return f"{summary_message} {ocr_message}"


@contextmanager
def processing_review_boundary():
    """Serialize current result/review consumers in the supported local process."""

    with _PROCESSING_REVIEW_LOCK:
        yield


# --- Public surface for other modules -------------------------------------
# These delegate straight to internal storage/engine modules, exposed here so
# other modules depend on Document Intelligence's public service contract
# instead of importing its repository/review_store/ocr_engine internals.

def ocr_region(*args, **kwargs):
    """See `document_intelligence.ocr_engine.ocr_region`."""

    return _ocr_region(*args, **kwargs)


def list_document_evidence_jobs(
    limit: int = 50,
    *,
    document_type: str | None = None,
    offset: int = 0,
) -> list[dict]:
    """List jobs without the HTTP-facing raise-on-missing behavior of `list_jobs`."""

    return repository.list_jobs(
        limit=limit,
        document_type=document_type,
        offset=offset,
    )


def get_document_evidence_job(job_id: str) -> dict | None:
    """Return a job or None; unlike `get_job`, never raises on a missing job."""

    return repository.get_job(job_id)


def get_document_evidence_result(job_id: str) -> dict | None:
    """Return a saved processing result, or None if none exists."""

    return repository.get_result(job_id)


def get_document_evidence_review(job_id: str) -> dict:
    """See `document_intelligence.review_store.get_review`."""

    return _get_review(job_id)


def _safe_file_name(file_name: str) -> str:
    base_name = Path(file_name).name.strip()
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base_name)
    return cleaned or "document.pdf"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_preserved_pdf(path: Path) -> str | None:
    try:
        with fitz.open(path) as document:
            if document.needs_pass:
                return "Encrypted PDF invoices are not supported."
            if document.page_count < 1:
                return "The PDF contains no pages."
            if document.page_count > settings.max_pdf_pages:
                return (
                    f"The PDF contains {document.page_count} pages and exceeds "
                    f"the governed technical limit of {settings.max_pdf_pages}."
                )
            document.load_page(0)
    except Exception as exc:
        # Job messages are returned by public routes. Keep the failure class as
        # useful review evidence without reflecting a local file path from a
        # parser/runtime exception.
        return f"The preserved PDF could not be opened ({type(exc).__name__})."
    return None


def _managed_pdf_path(job: dict[str, Any]) -> Path:
    """Resolve one registered source without trusting a database path blindly."""

    stored_path_value = str(job.get("stored_path") or "").strip()
    if not stored_path_value:
        raise FileNotFoundError("The preserved source PDF path is unavailable.")
    stored_path = Path(stored_path_value).resolve()
    upload_root = settings.upload_root.resolve()
    try:
        stored_path.relative_to(upload_root)
    except ValueError as exc:
        raise RuntimeError(
            "The registered source path is outside the managed Document Intelligence upload root."
        ) from exc
    if stored_path.suffix.lower() != ".pdf":
        raise RuntimeError("The registered source is not a managed PDF.")
    return stored_path


async def create_upload_job(
    file: UploadFile,
    *,
    intake_document_type: str | None = None,
    intake_source: str | None = None,
) -> dict:
    original_name = file.filename or "document.pdf"
    safe_name = _safe_file_name(original_name)
    content_type = (file.content_type or "").strip().lower()

    if Path(safe_name).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=415,
            detail="Document Intelligence accepts PDF files only.",
        )
    if content_type not in ALLOWED_PDF_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                "The uploaded content type is not supported. Vendor invoice "
                "intake accepts application/pdf only."
            ),
        )
    if intake_document_type not in {None, "vendor_invoice"}:
        raise HTTPException(status_code=400, detail="Unsupported intake document type.")

    job_id = str(uuid4())
    now = datetime.now(timezone.utc)
    target_directory = (
        settings.upload_root / f"{now.year:04d}" / f"{now.month:02d}" / job_id
    )
    target_directory.mkdir(parents=True, exist_ok=True)
    stored_path = target_directory / safe_name

    total_bytes = 0
    first_bytes = b""
    digest = hashlib.sha256()
    try:
        with stored_path.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                if not first_bytes:
                    first_bytes = chunk[:16]
                total_bytes += len(chunk)
                if total_bytes > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"File exceeds the governed "
                            f"{settings.max_upload_bytes // 1048576} MB limit."
                        ),
                    )
                digest.update(chunk)
                output.write(chunk)
    except Exception:
        stored_path.unlink(missing_ok=True)
        try:
            target_directory.rmdir()
        except OSError:
            pass
        raise
    finally:
        await file.close()

    if total_bytes == 0:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if not first_bytes.startswith(b"%PDF"):
        stored_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=415,
            detail="Uploaded file does not contain a PDF signature.",
        )

    source_sha256 = digest.hexdigest()
    duplicate = repository.find_duplicate_job(source_sha256)
    validation_error = _validate_preserved_pdf(stored_path)
    status = "failed" if validation_error else "uploaded"
    duplicate_message = (
        f" Exact file bytes were previously registered as job {duplicate['job_id']}."
        if duplicate
        else ""
    )
    message = (
        f"PDF preserved, but intake validation failed: {validation_error}{duplicate_message}"
        if validation_error
        else f"PDF preserved with SHA-256 and ready for processing.{duplicate_message}"
    )
    created_at = now.isoformat()
    return repository.create_job(
        {
            "job_id": job_id,
            "original_file_name": original_name,
            "stored_file_name": safe_name,
            "stored_path": str(stored_path),
            "content_type": content_type or "application/pdf",
            "file_size_bytes": total_bytes,
            "source_sha256": source_sha256,
            "intake_document_type": intake_document_type,
            "intake_source": intake_source,
            "duplicate_of_job_id": duplicate.get("job_id") if duplicate else None,
            "document_type": intake_document_type or "unknown",
            "confidence": 0.0,
            "status": status,
            "message": message,
            "created_at": created_at,
            "updated_at": created_at,
        }
    )


def _vendor_invoice_classification(
    preliminary: dict[str, Any],
    *,
    constrained_by_intake: bool,
) -> dict[str, Any]:
    if not constrained_by_intake:
        return preliminary
    evidence = [
        "Operator selected the governed vendor-invoice intake route; this constrains parser selection only."
    ]
    evidence.extend(str(item) for item in preliminary.get("evidence", []))
    detected_type = str(preliminary.get("document_type") or "unknown")
    if detected_type == "vendor_invoice":
        confidence = float(preliminary.get("confidence") or 0.0)
    else:
        confidence = 0.0
        evidence.append(
            f"Content classifier returned {detected_type}; no vendor-invoice classification confidence is asserted and no financial authority follows."
        )
    return {
        "document_type": "vendor_invoice",
        "confidence": confidence,
        "classifier": "governed_vendor_invoice_intake.v1",
        "evidence": list(dict.fromkeys(evidence)),
    }


def process_job(job_id: str) -> dict:
    # ETOP's supported local deployment runs one backend process. Serializing
    # processing and review CAS prevents two local runs from interleaving the
    # current-result and current-review projections.
    #
    # This is a threading.RLock, in-process only. Do NOT scale the backend to
    # multiple container replicas or run multiple uvicorn workers without
    # first replacing this with a DB-level lock (e.g. a MySQL advisory lock,
    # `GET_LOCK()`/`RELEASE_LOCK()`) - a second process is not blocked by this
    # lock at all, so two replicas could race on the same job's
    # current-result/current-review projection and corrupt it, rather than
    # just failing to get a throughput benefit.
    with processing_review_boundary():
        return _process_job(job_id)


def _process_job(job_id: str) -> dict:
    job = get_job(job_id)
    started_at = datetime.now(timezone.utc).isoformat()
    processing_run_id = f"doc-run-{uuid4().hex}"
    successful_run_persisted = False
    repository.update_job(
        job_id,
        status="processing",
        message="Extracting, classifying, parsing, and validating document evidence.",
    )

    extraction: dict[str, Any] = {}
    classification: dict[str, Any] = {
        "classifier": "unavailable",
        "evidence": [],
    }
    parsed: dict[str, Any] = {}
    try:
        stored_path = _managed_pdf_path(job)
        if not stored_path.exists() or not stored_path.is_file():
            raise FileNotFoundError("The preserved source PDF is unavailable.")
        actual_sha256 = _sha256_file(stored_path)
        expected_sha256 = job.get("source_sha256")
        if expected_sha256 and actual_sha256 != expected_sha256:
            raise RuntimeError(
                "The preserved source PDF hash no longer matches its registered SHA-256."
            )
        if not expected_sha256:
            updated_job = repository.set_source_sha256(job_id, actual_sha256)
            job = updated_job or job

        validation_error = _validate_preserved_pdf(stored_path)
        if validation_error:
            raise RuntimeError(
                f"The preserved upload cannot be processed: {validation_error}"
            )

        native_extraction = extract_pdf_text(stored_path)
        preliminary = classify_document(
            str(job["original_file_name"]),
            str(native_extraction.get("full_text") or ""),
        )
        constrained_vendor_invoice = (
            job.get("intake_document_type") == "vendor_invoice"
        )
        document_type = (
            "vendor_invoice"
            if constrained_vendor_invoice
            else preliminary["document_type"]
        )
        if document_type == "vendor_invoice":
            extraction = extract_vendor_invoice_text(
                stored_path,
                native_extraction=native_extraction,
                max_ocr_pages=settings.max_targeted_ocr_pages,
                ocr_page_timeout_seconds=settings.ocr_page_timeout_seconds,
                ocr_total_timeout_seconds=settings.ocr_total_timeout_seconds,
                max_ocr_render_dimension_pixels=(
                    settings.max_ocr_render_dimension_pixels
                ),
                max_ocr_render_pixels=settings.max_ocr_render_pixels,
            )
            content_classification = classify_document(
                str(job["original_file_name"]),
                str(extraction.get("full_text") or ""),
            )
            classification = _vendor_invoice_classification(
                content_classification,
                constrained_by_intake=constrained_vendor_invoice,
            )
        else:
            extraction = native_extraction
            classification = preliminary

        parser = parser_registry.get(classification["document_type"])
        parsed = parser.parse(
            {
                "job": job,
                "document_type": classification["document_type"],
                "classification": classification,
                "extraction": extraction,
            }
        )
        vendor_invoice_message = (
            _vendor_invoice_review_message(parsed, extraction)
            if classification["document_type"] == "vendor_invoice"
            else ""
        )
        completed_at = datetime.now(timezone.utc).isoformat()
        run = repository.record_processing_run(
            job_id,
            processing_run_id=processing_run_id,
            processor_version=settings.processor_version,
            source_sha256=str(job.get("source_sha256") or actual_sha256),
            status="completed",
            classifier=classification["classifier"],
            classification_evidence=classification["evidence"],
            extraction=extraction,
            parsed=parsed,
            message=(
                f"{vendor_invoice_message} Extraction remains evidence only."
                if vendor_invoice_message
                else "Document processing run completed; extraction remains evidence only."
            ),
            created_at=started_at,
            completed_at=completed_at,
            make_current=True,
        )
        successful_run_persisted = True
        begin_review_for_processing_run(job_id, run["processing_run_id"])
        completed_job = repository.update_job(
            job_id,
            document_type=classification["document_type"],
            confidence=classification["confidence"],
            status="completed",
            message=(
                vendor_invoice_message
                if classification["document_type"] == "vendor_invoice"
                else "Document processing completed."
            ),
        )
        return {
            "job": completed_job,
            "classifier": classification["classifier"],
            "classification_evidence": classification["evidence"],
            "extraction": extraction,
            "parsed": parsed,
            "processing_run_id": run["processing_run_id"],
            "processing_run_number": run["run_number"],
            "processor_version": run["processor_version"],
            "source_sha256": run.get("source_sha256"),
        }

    except HTTPException:
        raise
    except Exception as exc:
        completed_at = datetime.now(timezone.utc).isoformat()
        job = get_job(job_id)
        if not successful_run_persisted:
            repository.record_processing_run(
                job_id,
                processing_run_id=processing_run_id,
                processor_version=settings.processor_version,
                source_sha256=job.get("source_sha256"),
                status="failed",
                classifier=str(classification.get("classifier") or "unavailable"),
                classification_evidence=[
                    str(item) for item in classification.get("evidence", [])
                ],
                extraction=extraction,
                parsed=parsed,
                message=f"Document processing failed: {type(exc).__name__}: {exc}",
                created_at=started_at,
                completed_at=completed_at,
                make_current=False,
            )
        current_result = repository.get_result(job_id)
        retained_current = current_result is not None
        repository.update_job(
            job_id,
            status="completed" if retained_current else "failed",
            message=(
                "The latest reprocess run failed and requires review; the last "
                f"successful current result remains available: {exc}"
                if retained_current
                else f"Document processing failed and requires review: {exc}"
            ),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Document processing failed: {exc}",
        ) from exc


async def create_vendor_invoice_intake(file: UploadFile) -> dict[str, Any]:
    job = await create_upload_job(
        file,
        intake_document_type="vendor_invoice",
        intake_source="accounts_payable_vendor_invoice_capture",
    )
    if job["status"] == "failed":
        return {
            "intake_status": "failed",
            "job": job,
            "result": None,
            "review_required": True,
            "message": (
                "The original was preserved with its hash, but the PDF is corrupt, "
                "encrypted, or unreadable and requires human review."
            ),
        }
    try:
        result = await asyncio.to_thread(process_job, str(job["job_id"]))
    except HTTPException as exc:
        return {
            "intake_status": "failed",
            "job": get_job(str(job["job_id"])),
            "result": None,
            "review_required": True,
            "message": str(exc.detail),
        }
    parsed = result.get("parsed") if isinstance(result, dict) else {}
    extraction = result.get("extraction") if isinstance(result, dict) else {}
    review_message = _vendor_invoice_review_message(
        parsed if isinstance(parsed, dict) else {},
        extraction if isinstance(extraction, dict) else {},
    )
    return {
        "intake_status": "processed",
        "job": result["job"],
        "result": result,
        "review_required": bool(
            isinstance(parsed, dict) and parsed.get("review_required", True)
        ),
        "message": (
            f"Vendor invoice preserved and processed locally. {review_message} "
            "Review field evidence before synchronizing the current extraction "
            "into Accounts Payable."
        ),
    }


def get_job(job_id: str) -> dict:
    job = repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Document job was not found.")
    return job


def get_job_result(job_id: str) -> dict:
    job = get_job(job_id)
    result = repository.get_result(job_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="No successful processing result exists for this job.",
        )
    return {
        "job": job,
        "classifier": result["classifier"],
        "classification_evidence": result["classification_evidence"],
        "extraction": result["extraction"],
        "parsed": result["parsed"],
        "processing_run_id": result.get("processing_run_id"),
        "processing_run_number": result.get("processing_run_number"),
        "processor_version": result.get("processor_version"),
        "source_sha256": result.get("source_sha256") or job.get("source_sha256"),
    }


def save_current_job_review(
    job_id: str,
    *,
    expected_processing_run_id: str,
    status: str,
    reviewer: str,
    notes: str,
    corrected_fields: dict[str, Any],
) -> dict[str, Any]:
    """Save review evidence against the current immutable processing run.

    The required expected ID gives every review caller optimistic concurrency.
    No caller can choose the run ID that is persisted; it is always resolved
    from the current result server-side.
    """

    with processing_review_boundary():
        current_result = get_job_result(job_id)
        current_processing_run_id = current_result.get("processing_run_id")
        if expected_processing_run_id != current_processing_run_id:
            raise HTTPException(
                status_code=409,
                detail=(
                    "The current processing run changed after this review was loaded. "
                    "Reload the extraction before saving review evidence."
                ),
            )
        return save_review(
            job_id,
            processing_run_id=current_processing_run_id,
            status=status,
            reviewer=reviewer,
            notes=notes,
            corrected_fields=corrected_fields,
        )


def delete_job(job_id: str) -> None:
    job = get_job(job_id)

    try:
        path = _managed_pdf_path(job)
    except (FileNotFoundError, RuntimeError):
        path = None
    if path is not None:
        path.unlink(missing_ok=True)

    repository.delete_job(job_id)


def get_managed_job_pdf_path(job_id: str) -> Path:
    job = get_job(job_id)
    try:
        path = _managed_pdf_path(job)
    except (FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not path.exists() or not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="The stored PDF file could not be found.",
        )
    return path


def get_job_processing_runs(job_id: str) -> list[dict[str, Any]]:
    get_job(job_id)
    return repository.list_processing_runs(job_id)


def get_job_processing_run(job_id: str, processing_run_id: str) -> dict[str, Any]:
    get_job(job_id)
    run = repository.get_processing_run(job_id, processing_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Processing run was not found.")
    return run


def list_jobs(
    limit: int = 50,
    *,
    document_type: str | None = None,
    offset: int = 0,
) -> list[dict]:
    return repository.list_jobs(
        limit=limit,
        document_type=document_type,
        offset=offset,
    )


def count_jobs(*, document_type: str | None = None) -> int:
    return repository.count_jobs(document_type=document_type)


def get_health() -> dict:
    repository.initialize_database()
    ocr_available = tesseract_available()
    return {
        "status": "healthy",
        "module": settings.module_key,
        "version": settings.module_version,
        "database_exists": True,
        "upload_directory_exists": settings.upload_root.exists(),
        "job_count": repository.count_jobs(),
        "capabilities": {
            "upload": True,
            "local_storage": True,
            "source_sha256": True,
            "job_tracking": True,
            "versioned_processing_runs": True,
            "native_pdf_text_extraction": True,
            "rule_based_classification": True,
            "parser_registry": True,
            "vendor_invoice_parser": True,
            "structured_json_output": True,
            "ocr": ocr_available,
            "ocr_local_only": True,
            "excel_generation": False,
        },
    }
