from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from .extraction import (
    PROVISIONAL_OCR_REVIEW_THRESHOLD,
    extract_field_evidence,
    extraction_warnings,
    normalize_invoice_number,
    normalize_vendor_identity,
)
from .schemas import SourceInvoiceProjection


SOURCE_SYSTEM = "document_intelligence"
SOURCE_ADAPTER_VERSION = "ap-document-intelligence-adapter.v1"
REVIEW_UNAVAILABLE_FIELDS = frozenset(
    {
        "vendor_number",
        "vendor_name",
        "invoice_number",
        "invoice_date",
        "due_date",
        "purchase_order_number",
        "terms",
        "subtotal",
        "tax",
        "freight",
        "discount",
        "total_amount",
        "currency",
    }
)


class APSourceUnavailable(RuntimeError):
    """Raised when the local Document Intelligence source cannot be read."""


class DocumentEvidenceSource(Protocol):
    def list_vendor_invoice_evidence(self) -> list[dict[str, Any]]:
        """Return completed vendor-invoice jobs with saved results/reviews."""

    def get_vendor_invoice_evidence(
        self,
        job_id: str,
    ) -> dict[str, Any] | None:
        """Return one eligible vendor-invoice source by exact job identity."""


class ExistingDocumentIntelligenceSource:
    """Adapter over existing Document Intelligence persistence.

    This adapter never opens a source file, invokes a parser, or runs OCR. It
    reads only saved job/result/review evidence through the existing module.
    """

    def list_vendor_invoice_evidence(self) -> list[dict[str, Any]]:
        try:
            from modules.document_intelligence.service import (
                get_document_evidence_result,
                get_document_evidence_review,
                list_document_evidence_jobs,
            )

            jobs = list_document_evidence_jobs(limit=2_147_483_647)
            evidence: list[dict[str, Any]] = []
            for job in jobs:
                if (
                    job.get("document_type") != "vendor_invoice"
                    or job.get("status") != "completed"
                ):
                    continue
                result = get_document_evidence_result(str(job["job_id"]))
                if result is None:
                    evidence.append(
                        {
                            "job": job,
                            "result": None,
                            "review": None,
                            "source_warning": (
                                "Completed vendor-invoice job has no saved "
                                "Document Intelligence result."
                            ),
                        }
                    )
                    continue
                evidence.append(
                    {
                        "job": job,
                        "result": result,
                        "review": get_document_evidence_review(str(job["job_id"])),
                        "source_warning": None,
                    }
                )
            return evidence
        except Exception as exc:
            raise APSourceUnavailable(
                "The local Document Intelligence evidence store could not be read."
            ) from exc

    def get_vendor_invoice_evidence(
        self,
        job_id: str,
    ) -> dict[str, Any] | None:
        try:
            from modules.document_intelligence.service import (
                get_document_evidence_job,
                get_document_evidence_result,
                get_document_evidence_review,
            )

            job = get_document_evidence_job(job_id)
            if (
                job is None
                or job.get("document_type") != "vendor_invoice"
                or job.get("status") != "completed"
            ):
                return None
            result = get_document_evidence_result(job_id)
            if result is None:
                return {
                    "job": job,
                    "result": None,
                    "review": None,
                    "source_warning": (
                        "Completed vendor-invoice job has no saved "
                        "Document Intelligence result."
                    ),
                }
            return {
                "job": job,
                "result": result,
                "review": get_document_evidence_review(job_id),
                "source_warning": None,
            }
        except Exception as exc:
            raise APSourceUnavailable(
                "The local Document Intelligence evidence store could not be read."
            ) from exc


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _source_key(job_id: str, record_index: int | None) -> str:
    suffix = "document" if record_index is None else f"record:{record_index}"
    return f"{SOURCE_SYSTEM}:job:{job_id}:{suffix}"


def _invoice_id(source_key: str) -> str:
    digest = hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:24]
    return f"ap-invoice-{digest}"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _record_sources(
    parsed: dict[str, Any],
) -> list[tuple[int | None, dict[str, Any]]]:
    records = parsed.get("records")
    if isinstance(records, list):
        usable = [item for item in records if isinstance(item, dict)]
        if usable:
            return list(enumerate(usable))
    return [(None, {})]


def _corrected_sources(
    corrected_fields: dict[str, Any],
    record_index: int | None,
) -> list[tuple[dict[str, Any], str]]:
    sources: list[tuple[dict[str, Any], str]] = []
    records = corrected_fields.get("records")
    if (
        record_index is not None
        and isinstance(records, list)
        and record_index < len(records)
        and isinstance(records[record_index], dict)
    ):
        sources.append(
            (
                records[record_index],
                f"corrected_fields.records[{record_index}]",
            )
        )
    root = {
        key: value
        for key, value in corrected_fields.items()
        if key != "records"
    }
    if root:
        sources.append((root, "corrected_fields"))
    return sources


def _max_timestamp(*values: Any) -> str:
    present = [str(value) for value in values if value not in (None, "")]
    return max(present) if present else "1970-01-01T00:00:00+00:00"


def _normalized_fields(
    *,
    parsed: dict[str, Any],
    record: dict[str, Any],
    corrected_fields: dict[str, Any],
    unavailable_fields: set[str],
    record_index: int | None,
    source_text: str,
    allow_text_candidate: bool,
) -> list[dict[str, Any]]:
    corrected_sources = _corrected_sources(corrected_fields, record_index)
    structured_sources: list[tuple[dict[str, Any], str]] = []
    if record:
        structured_sources.append(
            (record, f"parsed.records[{record_index}]")
        )
    structured_sources.append((parsed, "parsed"))

    return [
        extract_field_evidence(
            field_name=field_name,
            corrected_sources=corrected_sources,
            structured_sources=structured_sources,
            source_text=source_text,
            allow_text_candidate=allow_text_candidate,
            unavailable_fields=unavailable_fields,
        )
        for field_name in (
            "vendor_number",
            "vendor_name",
            "invoice_number",
            "invoice_date",
            "due_date",
            "purchase_order_number",
            "terms",
            "subtotal",
            "tax",
            "freight",
            "discount",
            "total_amount",
            "currency",
            "ocr_confidence",
        )
    ]


def _field_map(fields: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {field["field_name"]: field for field in fields}


def _exception(
    code: str,
    label: str,
    severity: str,
    explanation: str,
    *,
    evidence: list[str] | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "severity": severity,
        "explanation": explanation,
        "evidence": evidence or [],
        "source": source,
    }


def _explicit_mismatch_exceptions(
    structured_sources: list[tuple[dict[str, Any], str]],
) -> list[dict[str, Any]]:
    definitions = (
        (
            "amount_match_status",
            ("amount_match_status", "amount_match", "total_match_status"),
            "amount_mismatch",
            "Amount Mismatch",
        ),
        (
            "po_match_status",
            ("po_match_status", "po_match", "purchase_order_match"),
            "purchase_order_mismatch",
            "Purchase Order Mismatch",
        ),
        (
            "receiving_match_status",
            ("receiving_match_status", "receiving_match", "receipt_match"),
            "receiving_mismatch",
            "Receiving Mismatch",
        ),
        (
            "tax_match_status",
            ("tax_match_status", "tax_match"),
            "tax_mismatch",
            "Tax Mismatch",
        ),
        (
            "price_match_status",
            ("price_match_status", "price_match"),
            "price_mismatch",
            "Price Mismatch",
        ),
        (
            "freight_match_status",
            ("freight_match_status", "freight_match"),
            "freight_mismatch",
            "Freight Mismatch",
        ),
    )
    exceptions: list[dict[str, Any]] = []
    for field_name, aliases, code, label in definitions:
        # The helper consumes the shared alias registry, so this deliberately
        # performs a narrowly bounded lookup for validation fields.
        match: tuple[Any, str] | None = None
        alias_set = set(aliases)
        for mapping, prefix in structured_sources:
            containers = [(mapping, prefix)]
            for container_key in ("fields", "validation", "match", "matches"):
                child = mapping.get(container_key)
                if isinstance(child, dict):
                    containers.append((child, f"{prefix}.{container_key}"))
            for container, container_path in containers:
                for key, value in container.items():
                    normalized_key = str(key).strip().lower().replace("-", "_")
                    if normalized_key in alias_set:
                        match = (value, f"{container_path}.{key}")
                        break
                if match:
                    break
            if match:
                break
        if match is None:
            continue
        raw_value, path = match
        is_mismatch = raw_value is False or str(raw_value).strip().lower() in {
            "mismatch",
            "not_matched",
            "failed",
            "false",
            "no",
        }
        if is_mismatch:
            exceptions.append(
                _exception(
                    code,
                    label,
                    "high",
                    "The saved Document Intelligence result explicitly reports a mismatch.",
                    evidence=[f"{field_name}={raw_value}"],
                    source=f"document_intelligence:{path}",
                )
            )
    return exceptions


def _build_exceptions(
    fields: list[dict[str, Any]],
    structured_sources: list[tuple[dict[str, Any], str]],
) -> tuple[list[dict[str, Any]], bool]:
    values = _field_map(fields)
    exceptions: list[dict[str, Any]] = []

    if (
        values["vendor_number"]["normalized_value"] is None
        and values["vendor_name"]["normalized_value"] is None
    ):
        exceptions.append(
            _exception(
                "missing_vendor_identity",
                "Missing Vendor Identity",
                "high",
                "Neither vendor number nor vendor name is available from source evidence.",
            )
        )
    for field_name, code, label, severity in (
        ("invoice_number", "missing_invoice_number", "Missing Invoice Number", "high"),
        ("invoice_date", "missing_invoice_date", "Missing Invoice Date", "medium"),
        ("total_amount", "missing_total_amount", "Missing Invoice Total", "high"),
        ("due_date", "missing_due_date", "Missing Due Date", "low"),
    ):
        field = values[field_name]
        if field["normalized_value"] is None:
            exceptions.append(
                _exception(
                    code,
                    label,
                    severity,
                    f"{field['label']} is unavailable from usable source evidence.",
                    evidence=(
                        [f"raw_source_value={field['value']}"]
                        if field["value"] is not None
                        else []
                    ),
                    source=(field["source"] if field["value"] is not None else None),
                )
            )

    inferred_fields = [
        field["label"]
        for field in fields
        if field["source"].startswith(
            "document_intelligence.extraction.full_text"
        )
        and field["normalized_value"] is not None
    ]
    if inferred_fields:
        exceptions.append(
            _exception(
                "source_text_candidates_require_review",
                "Source Text Candidates Require Review",
                "medium",
                "Header candidates came from deterministic matching over saved text, not a governed structured parser.",
                evidence=inferred_fields,
                source="document_intelligence.extraction.full_text",
            )
        )

    invoice_date_value = values["invoice_date"]["normalized_value"]
    due_date_value = values["due_date"]["normalized_value"]
    if invoice_date_value and due_date_value:
        if date.fromisoformat(due_date_value) < date.fromisoformat(invoice_date_value):
            exceptions.append(
                _exception(
                    "due_date_precedes_invoice_date",
                    "Due Date Precedes Invoice Date",
                    "high",
                    "The normalized due date precedes the normalized invoice date.",
                    evidence=[
                        f"invoice_date={invoice_date_value}",
                        f"due_date={due_date_value}",
                    ],
                    source="document_intelligence",
                )
            )

    amount_fields = ("subtotal", "tax", "freight", "discount", "total_amount")
    if all(values[name]["normalized_value"] is not None for name in amount_fields):
        expected = (
            Decimal(values["subtotal"]["normalized_value"])
            + Decimal(values["tax"]["normalized_value"])
            + Decimal(values["freight"]["normalized_value"])
            - Decimal(values["discount"]["normalized_value"])
        )
        actual = Decimal(values["total_amount"]["normalized_value"])
        if expected.quantize(Decimal("0.01")) != actual.quantize(Decimal("0.01")):
            exceptions.append(
                _exception(
                    "invoice_total_reconciliation_mismatch",
                    "Invoice Total Reconciliation Mismatch",
                    "high",
                    "Source-present subtotal, tax, freight, and discount do not reconcile exactly to the source total.",
                    evidence=[
                        f"calculated_total={expected.quantize(Decimal('0.01'))}",
                        f"source_total={actual.quantize(Decimal('0.01'))}",
                    ],
                    source="document_intelligence",
                )
            )

    exceptions.extend(_explicit_mismatch_exceptions(structured_sources))

    ocr_confidence = values["ocr_confidence"]["normalized_value"]
    ocr_review_required = (
        ocr_confidence is not None
        and ocr_confidence < PROVISIONAL_OCR_REVIEW_THRESHOLD
    )
    if ocr_review_required:
        exceptions.append(
            _exception(
                "low_ocr_confidence_provisional",
                "Low OCR Confidence",
                "medium",
                "OCR confidence is below the explicit provisional 90% review threshold inherited from the current Document Intelligence review UI. It is not an automation or approval threshold.",
                evidence=[f"ocr_confidence={ocr_confidence:.6f}"],
                source="observed_current_document_review_ui",
            )
        )
    return exceptions, ocr_review_required


def build_projections(evidence: dict[str, Any]) -> list[SourceInvoiceProjection]:
    job = _dict(evidence.get("job"))
    result = _dict(evidence.get("result"))
    if not job or not result:
        return []

    parsed = _dict(result.get("parsed"))
    extraction = _dict(result.get("extraction"))
    review_envelope = _dict(evidence.get("review"))
    document_review = _dict(review_envelope.get("review"))
    result_processing_run_id = result.get("processing_run_id")
    review_processing_run_id = document_review.get("processing_run_id")
    review_matches_current_run = (
        result_processing_run_id == review_processing_run_id
        if result_processing_run_id is not None
        else review_processing_run_id is None
    )
    corrected_fields = (
        _dict(document_review.get("corrected_fields"))
        if review_matches_current_run
        else {}
    )
    unavailable_fields = (
        {
            field_name
            for field_name in document_review.get("unavailable_fields", [])
            if isinstance(field_name, str)
            and field_name in REVIEW_UNAVAILABLE_FIELDS
        }
        if review_matches_current_run
        and isinstance(document_review.get("unavailable_fields"), list)
        else set()
    )
    review_history = review_envelope.get("history")
    review_evidence_present = review_matches_current_run and bool(
        corrected_fields
        or unavailable_fields
        or (isinstance(review_history, list) and review_history)
        or str(document_review.get("reviewer") or "").strip()
        or str(document_review.get("notes") or "").strip()
    )
    source_text = extraction.get("full_text")
    source_text = source_text if isinstance(source_text, str) else ""
    records = _record_sources(parsed)
    allow_text_candidate = len(records) == 1
    job_id = str(job["job_id"])
    source_as_of = _max_timestamp(
        job.get("updated_at"),
        result.get("updated_at"),
        document_review.get("updated_at") if review_evidence_present else None,
    )
    parser_name = parsed.get("parser")
    parser_version = parsed.get("parser_version")
    base_warnings = extraction_warnings(result)
    if not review_matches_current_run and document_review:
        base_warnings.append(
            "Document extraction review belongs to a prior processing run; its status and corrections were not applied to the current result."
        )
    if review_evidence_present and document_review.get("status") == "approved":
        base_warnings.append(
            "Document extraction review is marked approved, but that status is not AP invoice approval or payment authorization."
        )
    if unavailable_fields:
        base_warnings.append(
            "The current-run reviewer marked fields unavailable; machine and "
            "source-text fallback values for those fields were suppressed."
        )

    projections: list[SourceInvoiceProjection] = []
    for record_index, record in records:
        structured_sources: list[tuple[dict[str, Any], str]] = []
        if record:
            structured_sources.append(
                (record, f"parsed.records[{record_index}]")
            )
        structured_sources.append((parsed, "parsed"))
        fields = _normalized_fields(
            parsed=parsed,
            record=record,
            corrected_fields=corrected_fields,
            unavailable_fields=unavailable_fields,
            record_index=record_index,
            source_text=source_text,
            allow_text_candidate=allow_text_candidate,
        )
        field_map = _field_map(fields)
        exceptions, ocr_review_required = _build_exceptions(
            fields,
            structured_sources,
        )
        ambiguous_fields = parsed.get("ambiguous_fields")
        if isinstance(ambiguous_fields, dict):
            for field_name, candidates in ambiguous_fields.items():
                candidate_count = len(candidates) if isinstance(candidates, list) else 0
                exceptions.append(
                    _exception(
                        "ambiguous_extraction_field",
                        "Ambiguous Extraction Field",
                        "medium",
                        "The versioned vendor-invoice parser retained multiple distinct field candidates and did not select one.",
                        evidence=[
                            f"field={field_name}",
                            f"candidate_count={candidate_count}",
                        ],
                        source="document_intelligence.parsed.ambiguous_fields",
                    )
                )
        if (
            parsed.get("review_required") is True
            and (
                not review_matches_current_run
                or document_review.get("status") != "approved"
            )
        ):
            exceptions.append(
                _exception(
                    "document_extraction_review_pending",
                    "Document Extraction Review Pending",
                    "medium",
                    "The machine extraction has not been marked reviewed in Document Intelligence. This is extraction review only, never AP invoice approval.",
                    source="document_intelligence.document_review",
                )
            )
        normalized = {
            name: field_map[name]["normalized_value"]
            for name in field_map
        }
        source_key = _source_key(job_id, record_index)
        normalized_vendor = normalize_vendor_identity(
            normalized["vendor_number"],
            normalized["vendor_name"],
        )
        normalized_invoice = (
            normalize_invoice_number(normalized["invoice_number"])
            if normalized["invoice_number"]
            else None
        )
        warnings = list(dict.fromkeys(base_warnings))
        if normalized["ocr_confidence"] is None:
            warnings.append(
                "OCR confidence is unavailable; classifier confidence is retained separately and is not relabeled as OCR confidence."
            )

        source_snapshot = {
            "adapter_version": SOURCE_ADAPTER_VERSION,
            "source_key": source_key,
            "document": {
                "job_id": job_id,
                "result_id": str(result.get("job_id") or job_id),
                "document_type": job.get("document_type"),
                "job_status": job.get("status"),
                "file_name": job.get("original_file_name"),
                "source_sha256": job.get("source_sha256"),
                "duplicate_of_job_id": job.get("duplicate_of_job_id"),
                "classification_confidence": job.get("confidence"),
                "classifier": result.get("classifier"),
                "classification_evidence": result.get(
                    "classification_evidence"
                ),
                "parser_name": parser_name,
                "parser_version": parser_version,
                "processing_run_id": result.get("processing_run_id"),
                "processing_run_number": result.get("processing_run_number"),
                "processor_version": result.get("processor_version"),
                "extraction_version": extraction.get("extraction_version"),
                "ocr_profile_version": extraction.get("ocr_profile_version"),
                "ocr_engine": extraction.get("ocr_engine"),
                "ocr_engine_version": extraction.get("ocr_engine_version"),
                "job_created_at": job.get("created_at"),
                "job_updated_at": job.get("updated_at"),
                "result_created_at": result.get("created_at"),
                "result_updated_at": result.get("updated_at"),
                "source_record_index": record_index,
            },
            "document_extraction_review": {
                "evidence_present": review_evidence_present,
                "recorded_status": document_review.get("status"),
                "recorded_processing_run_id": review_processing_run_id,
                "status": (
                    document_review.get("status")
                    if review_evidence_present
                    else None
                ),
                "processing_run_id": (
                    review_processing_run_id
                    if review_evidence_present
                    else None
                ),
                "matches_current_processing_run": review_matches_current_run,
                "updated_at": (
                    document_review.get("updated_at")
                    if review_evidence_present
                    else None
                ),
                "corrected_fields_used": bool(corrected_fields),
                "unavailable_fields": sorted(unavailable_fields),
                "unavailable_fields_used": bool(unavailable_fields),
                "authority_boundary": (
                    "Document extraction review only; never AP invoice "
                    "approval or payment authorization."
                ),
            },
            "field_evidence": fields,
            "exceptions": exceptions,
            "warnings": warnings,
            "source_as_of": source_as_of,
        }
        source_hash = _sha256(source_snapshot)
        projections.append(
            SourceInvoiceProjection(
                ap_invoice_id=_invoice_id(source_key),
                source_key=source_key,
                document_job_id=job_id,
                document_result_id=str(result.get("job_id") or job_id),
                source_record_index=record_index,
                source_file_name=str(job.get("original_file_name") or ""),
                content_type=(
                    str(job["content_type"])
                    if job.get("content_type") is not None
                    else None
                ),
                document_type="vendor_invoice",
                document_status=str(job.get("status") or ""),
                classifier=(
                    str(result["classifier"])
                    if result.get("classifier") is not None
                    else None
                ),
                classification_confidence=(
                    float(job["confidence"])
                    if job.get("confidence") is not None
                    else None
                ),
                classification_evidence=[
                    str(item)
                    for item in result.get("classification_evidence", [])
                ],
                parser_name=(str(parser_name) if parser_name else None),
                parser_version=(str(parser_version) if parser_version else None),
                vendor_number=normalized["vendor_number"],
                vendor_name=normalized["vendor_name"],
                normalized_vendor_identity=normalized_vendor,
                invoice_number=normalized["invoice_number"],
                normalized_invoice_number=normalized_invoice,
                invoice_date=normalized["invoice_date"],
                due_date=normalized["due_date"],
                purchase_order_number=normalized["purchase_order_number"],
                subtotal=normalized["subtotal"],
                tax=normalized["tax"],
                freight=normalized["freight"],
                discount=normalized["discount"],
                total_amount=normalized["total_amount"],
                currency=normalized["currency"],
                terms=normalized["terms"],
                classification_confidence_source="document_intelligence.doc_jobs.confidence",
                ocr_confidence=normalized["ocr_confidence"],
                field_evidence=fields,
                exceptions=exceptions,
                warnings=warnings,
                base_review_required=bool(exceptions),
                ocr_review_required=ocr_review_required,
                received_at=(
                    str(job["created_at"])
                    if job.get("created_at") is not None
                    else None
                ),
                processed_at=(
                    str(job["updated_at"])
                    if job.get("updated_at") is not None
                    else None
                ),
                source_result_created_at=(
                    str(result["created_at"])
                    if result.get("created_at") is not None
                    else None
                ),
                source_result_updated_at=(
                    str(result["updated_at"])
                    if result.get("updated_at") is not None
                    else None
                ),
                source_as_of=source_as_of,
                source_evidence_sha256=source_hash,
                source_snapshot=source_snapshot,
            )
        )
    return projections


document_intelligence_source = ExistingDocumentIntelligenceSource()
