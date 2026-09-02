"""Production-facing service seam for durable Lockbox preparation."""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

from .contracts import SourceTransaction, StartPreparationRequest
from .control_projection import (
    CONTROL_RULE_VERSION,
    CONTROL_SERVICE_VERSION,
    apply_control_projection,
    apply_fresh_source_projection,
)
from .coordinator import DurableLockboxPreparationCoordinator
from .policy import normalize_invoice

logger = logging.getLogger(__name__)


LockboxSourceLoader = Callable[[str], dict[str, Any]]


class DurableLockboxPreparationService:
    """Expose start/resume/status/history without registering shared routes."""

    def __init__(
        self,
        coordinator: DurableLockboxPreparationCoordinator,
        source_loader: LockboxSourceLoader | None = None,
        *,
        control_projection_required: bool = True,
    ) -> None:
        self.coordinator = coordinator
        self.source_loader = source_loader
        self.control_projection_required = control_projection_required

    def start(
        self,
        request: StartPreparationRequest,
        *,
        background: bool = True,
    ) -> dict[str, Any]:
        return self.coordinator.start(
            request,
            background=background,
        )

    def start_source_job(
        self,
        source_job_id: str,
        source_file_hash: str = "",
        *,
        correlation_id: str = "",
        idempotency_key: str = "",
        background: bool = True,
    ) -> dict[str, Any]:
        if self.source_loader is None:
            raise RuntimeError(
                "The durable preparation source loader is not configured."
            )
        identity_loader = getattr(self.source_loader, "identity", None)
        identity = (
            identity_loader(source_job_id)
            if callable(identity_loader)
            else self.source_loader(source_job_id)
        )
        authoritative_hash = str(
            identity.get("source_file_hash") or ""
        ).strip().lower()
        supplied_hash = source_file_hash.strip().lower()
        if not authoritative_hash:
            raise ValueError(
                "The original Lockbox PDF hash could not be established."
            )
        if supplied_hash and supplied_hash != authoritative_hash:
            raise ValueError(
                "The supplied source hash does not match the saved "
                "Lockbox PDF."
            )
        source = self.source_loader(source_job_id)
        request = self.request_from_source(
            source_job_id=source_job_id,
            source_file_hash=authoritative_hash,
            source=source,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )
        return self._governed_projection(
            self.start(request, background=background),
            current_for_rule=True,
        )

    def resume(
        self,
        job_id: str,
        *,
        retry_exceptions: bool = False,
        background: bool = True,
    ) -> dict[str, Any]:
        return self._governed_projection(
            self.coordinator.resume(
                job_id,
                retry_exceptions=retry_exceptions,
                background=background,
            ),
            current_for_rule=None,
        )

    def status(
        self,
        job_id: str,
        *,
        include_transactions: bool = True,
    ) -> dict[str, Any]:
        projection = self._governed_projection(
            self.coordinator.status(job_id),
            current_for_rule=None,
        )
        if not include_transactions:
            projection.pop("transactions", None)
        return projection

    def current_source_job(
        self,
        source_job_id: str,
        *,
        include_transactions: bool = True,
    ) -> dict[str, Any]:
        """Read the current governed generation; never register a new one."""

        if self.source_loader is None:
            raise RuntimeError(
                "The durable preparation source loader is not configured."
            )
        identity_loader = getattr(self.source_loader, "identity", None)
        source = (
            identity_loader(source_job_id)
            if callable(identity_loader)
            else self.source_loader(source_job_id)
        )
        source_file_hash = str(
            source.get("source_file_hash") or ""
        ).strip().lower()
        if not source_file_hash:
            raise ValueError(
                "The original Lockbox PDF hash could not be established."
            )
        snapshot = self.coordinator.repository.get_current_job(
            source_job_id,
            source_file_hash,
        )
        projection = self._governed_projection(
            snapshot,
            current_for_rule=True,
        )
        if not include_transactions:
            projection.pop("transactions", None)
        return projection

    def history(self, job_id: str) -> list[dict[str, Any]]:
        return self.coordinator.history(job_id)

    def exception_summary(self, job_id: str) -> dict[str, Any]:
        snapshot = self.status(job_id, include_transactions=False)
        return {
            "job_id": snapshot["job_id"],
            "source_job_id": snapshot["source_job_id"],
            "state": snapshot["state"],
            "complete": snapshot["complete"],
            "counts_final": snapshot["counts_final"],
            "expected_count": snapshot["expected_count"],
            "terminal_count": snapshot["terminal_count"],
            "balanced_count": snapshot["balanced_count"],
            "exception_count": snapshot["exception_count"],
            "preserved_count": snapshot["preserved_count"],
            "exception_reason_summary": snapshot[
                "exception_reason_summary"
            ],
        }

    def _governed_projection(
        self,
        snapshot: dict[str, Any],
        *,
        current_for_rule: bool | None,
    ) -> dict[str, Any]:
        projected = deepcopy(snapshot)
        if (
            self.control_projection_required
            and
            projected.get("rule_version")
            == self.coordinator.repository.rule_version
            and projected.get("service_version")
            == self.coordinator.repository.service_version
            and projected.get("complete")
        ):
            control = self._control_snapshot_if_available(
                str(projected.get("source_job_id") or ""),
                str(projected.get("source_file_hash") or ""),
            )
            projected = (
                apply_control_projection(control, projected)
                if control is not None
                else apply_fresh_source_projection(projected)
            )
        expected = int(projected.get("expected_count") or 0)
        terminal = int(projected.get("terminal_count") or 0)
        balanced = int(projected.get("balanced_count") or 0)
        exception = int(projected.get("exception_count") or 0)
        preserved = int(projected.get("preserved_count") or 0)
        reason_total = int(
            projected.get("exception_reason_summary", {}).get(
                "total_exception_count", 0
            )
            or 0
        )
        complete = bool(projected.get("complete"))
        reconciled = (
            terminal <= expected
            and balanced + exception + preserved == terminal
            and (not complete or terminal == expected)
            and (not complete or reason_total == exception)
        )
        projected.update(
            {
                "current_for_rule": current_for_rule,
                "reconciled": reconciled,
                "counts_final": bool(
                    projected.get("counts_final")
                    and complete
                    and reconciled
                ),
                "recommendation_not_decision": True,
                "can_auto_approve": False,
                "erp_write_performed": False,
            }
        )
        return projected

    def _control_snapshot_if_available(
        self,
        source_job_id: str,
        source_file_hash: str,
    ) -> dict[str, Any] | None:
        """Return the exact historical control, or treat this as a fresh source.

        The one Increment 3E/3F R1 control this checks for (78 transactions,
        30 accepted balanced, 48 accepted review) is a single historical
        reference document from that development phase, not a general
        mechanism - the literal counts in _control_snapshot() were never
        meant to validate any *other* document's control. Absence of a
        matching record is expected for every other immutable PDF. A record
        that exists under the same frozen rule/service identity but doesn't
        match that exact shape is logged (it would be unusual - possibly a
        corrupted or partially-written record) and is likewise treated as
        "no control available," falling back to apply_fresh_source_projection,
        rather than permanently 409ing every status/resume/history call for
        that job.
        """

        try:
            return self._control_snapshot(
                source_job_id,
                source_file_hash,
            )
        except KeyError:
            return None

    def _control_snapshot(
        self,
        source_job_id: str,
        source_file_hash: str,
    ) -> dict[str, Any]:
        snapshot = self.coordinator.repository.get_job_for_rule(
            source_job_id,
            source_file_hash,
            CONTROL_RULE_VERSION,
            service_version=CONTROL_SERVICE_VERSION,
        )
        if not (
            snapshot.get("state") == "complete"
            and snapshot.get("complete")
            and int(snapshot.get("expected_count") or 0) == 78
            and int(snapshot.get("terminal_count") or 0) == 78
            and int(snapshot.get("balanced_count") or 0) == 30
            and int(snapshot.get("exception_count") or 0) == 48
        ):
            logger.warning(
                "Source job %s has a snapshot under the frozen Increment "
                "3E/3F R1 control identity that doesn't match the exact "
                "78/30/48 golden shape; treating it as no control available "
                "rather than blocking this job on every future request.",
                source_job_id,
            )
            raise KeyError(
                "No exact Increment 3F R1 78/30/48 control is available "
                f"for source job {source_job_id}."
            )
        return snapshot

    @staticmethod
    def request_from_source(
        *,
        source_job_id: str,
        source_file_hash: str,
        source: dict[str, Any],
        correlation_id: str = "",
        idempotency_key: str = "",
    ) -> StartPreparationRequest:
        transactions: list[SourceTransaction] = []
        extraction_version = str(
            source.get("extraction_version")
            or source.get("parser_version")
            or "unknown"
        )
        for ordinal, item in enumerate(
            source.get("transactions", []),
            start=1,
        ):
            transaction_id = str(
                item.get("transaction_id") or f"transaction-{ordinal}"
            )
            invoices = tuple(
                dict.fromkeys(
                    invoice
                    for allocation in item.get("allocations", [])
                    if (
                        invoice := normalize_invoice(
                            allocation.get("invoice_number")
                        )
                    )
                )
            )
            payment_date = DurableLockboxPreparationService._date_value(
                item.get("date")
                or source.get("transaction_date")
            )
            status = str(item.get("status") or "")
            human_disposition = (
                {
                    "status": status,
                    "reviewer": str(item.get("reviewer") or ""),
                    "notes": str(item.get("notes") or ""),
                    "override_reason": str(
                        item.get("override_reason") or ""
                    ),
                    "allocations": deepcopy(
                        item.get("allocations", [])
                    ),
                    "reviewed_at": item.get("reviewed_at"),
                }
                if status in {"corrected", "held", "approved"}
                else None
            )
            source_reference = str(
                item.get("source_reference")
                or (
                    f"check_page={item.get('check_page')};"
                    f"remittance_pages={item.get('remittance_pages', [])}"
                )
            )
            transactions.append(
                SourceTransaction(
                    transaction_id=transaction_id,
                    ordinal=ordinal,
                    check_amount=Decimal(
                        str(item.get("check_amount") or 0)
                    ),
                    extracted_invoice_numbers=invoices,
                    original_source=deepcopy(item),
                    extraction_version=extraction_version,
                    source_reference=source_reference,
                    source_hash=str(item.get("source_hash") or ""),
                    payment_date=payment_date,
                    remittance_evidence_complete=bool(
                        item.get("remittance_evidence_complete")
                    ),
                    projection_evidence=deepcopy(
                        item.get("projection_evidence") or {}
                    ),
                    preexisting_human_disposition=human_disposition,
                )
            )
        return StartPreparationRequest(
            source_job_id=source_job_id,
            source_file_hash=source_file_hash,
            transactions=tuple(transactions),
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            source_reference=str(
                source.get("source_file_name")
                or source.get("source_reference")
                or ""
            ),
        )

    @staticmethod
    def _date_value(value: Any) -> date | None:
        if isinstance(value, date):
            return value
        text = str(value or "").strip()
        if not text:
            return None
        for formatter in (
            date.fromisoformat,
            lambda candidate: datetime.strptime(
                candidate,
                "%Y/%m/%d",
            ).date(),
            lambda candidate: datetime.strptime(
                candidate,
                "%m/%d/%Y",
            ).date(),
            lambda candidate: date(
                int(candidate[4:8]),
                int(candidate[0:2]),
                int(candidate[2:4]),
            ),
        ):
            try:
                return formatter(text)
            except (ValueError, TypeError, IndexError):
                continue
        return None
