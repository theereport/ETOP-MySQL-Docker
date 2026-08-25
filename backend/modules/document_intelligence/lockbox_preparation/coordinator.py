"""Bounded, restart-safe coordinator for durable Lockbox preparation."""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import date
from decimal import Decimal
from typing import Any

from .contracts import (
    CustomerGroupSnapshot,
    CustomerResolution,
    CustomerSnapshot,
    InvoiceOwnerEvidence,
    OpenARSnapshot,
    ReadOnlyPreparationProvider,
    SourceTransaction,
    StartPreparationRequest,
    UnconfiguredReadOnlyPreparationProvider,
    dataclass_payload,
)
from .customer_conflict import (
    CustomerConflictAssessment,
    assess_current_open_invoice_owners,
    assess_current_open_ar_ownership,
    invoice_owner_candidates,
)
from .customer_group import (
    EnterpriseGroupAssessment,
    assess_enterprise_group_conflict,
)
from .errors import PreparationPolicyError
from .policy import (
    AMOUNT_TOLERANCE,
    RULE_VERSION,
    assess_remittance_reconciliation,
    disambiguate_remittance_rows,
    normalize_invoice,
    recommend_allocation,
    recommend_enterprise_group_allocation,
)
from .repository import (
    SERVICE_VERSION,
    LockboxPreparationRepository,
)
from .reason_codes import classify_exception
from .states import FileState, TransactionState


DEFAULT_READ_WORKERS = 6
MAX_READ_WORKERS = 8


class DurableLockboxPreparationCoordinator:
    """Run read-only preparation independently from the browser lifecycle."""

    def __init__(
        self,
        repository: LockboxPreparationRepository,
        provider: ReadOnlyPreparationProvider | None = None,
        *,
        read_workers: int = DEFAULT_READ_WORKERS,
        recover_on_startup: bool = True,
    ) -> None:
        if read_workers < 1 or read_workers > MAX_READ_WORKERS:
            raise ValueError(
                f"read_workers must be between 1 and {MAX_READ_WORKERS}."
            )
        self.repository = repository
        self.provider = provider or UnconfiguredReadOnlyPreparationProvider()
        self.read_workers = read_workers
        self._job_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="etop-lockbox-job",
        )
        self._active_lock = threading.RLock()
        self._active: dict[str, Future[dict[str, Any]]] = {}
        self._recovered_job_ids = (
            self.repository.recover_incomplete()
            if recover_on_startup
            else []
        )

    @property
    def recovered_job_ids(self) -> tuple[str, ...]:
        return tuple(self._recovered_job_ids)

    def configure_provider(
        self,
        provider: ReadOnlyPreparationProvider,
    ) -> None:
        with self._active_lock:
            if any(not future.done() for future in self._active.values()):
                raise RuntimeError(
                    "The read-only provider cannot change while a job is active."
                )
            self.provider = provider

    def start(
        self,
        request: StartPreparationRequest,
        *,
        retry_exceptions: bool = False,
        background: bool = True,
    ) -> dict[str, Any]:
        registered = self.repository.register(request)
        return self.resume(
            str(registered["job_id"]),
            retry_exceptions=retry_exceptions,
            background=background,
        )

    def resume(
        self,
        job_id: str,
        *,
        retry_exceptions: bool = False,
        background: bool = True,
    ) -> dict[str, Any]:
        current = self.repository.get_job(job_id)
        if current["complete"] and not retry_exceptions:
            return current

        with self._active_lock:
            existing = self._active.get(job_id)
            if existing and not existing.done():
                return self.repository.get_job(job_id)
            if background:
                self._active[job_id] = self._job_executor.submit(
                    self._run_job,
                    job_id,
                    retry_exceptions,
                )
                return self.repository.get_job(job_id)

        return self._run_job(job_id, retry_exceptions)

    def resume_recovered(self) -> list[dict[str, Any]]:
        return [
            self.resume(job_id, background=True)
            for job_id in self._recovered_job_ids
        ]

    def wait(
        self,
        job_id: str,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        with self._active_lock:
            future = self._active.get(job_id)
        if future:
            return future.result(timeout=timeout)
        return self.repository.get_job(job_id)

    def is_active(self, job_id: str) -> bool:
        with self._active_lock:
            future = self._active.get(job_id)
            return bool(future and not future.done())

    def _run_job(
        self,
        job_id: str,
        retry_exceptions: bool,
    ) -> dict[str, Any]:
        transactions = self.repository.begin_run(
            job_id,
            retry_exceptions=retry_exceptions,
        )
        if not transactions:
            snapshot = self.repository.get_job(job_id)
            if int(snapshot["terminal_count"]) == int(
                snapshot["expected_count"]
            ):
                return self.repository.finalize(job_id)
            return snapshot

        invoice_numbers = tuple(
            dict.fromkeys(
                invoice
                for transaction in transactions
                for value in transaction.extracted_invoice_numbers
                if (invoice := normalize_invoice(value))
            )
        )
        try:
            invoice_owners = dict(
                self.provider.resolve_invoice_owners(invoice_numbers)
            )
            self.repository.append_event(
                job_id,
                "invoice_owners_loaded",
                {
                    "invoice_count": len(invoice_numbers),
                    "resolved_count": sum(
                        bool(evidence.customer_numbers)
                        for evidence in invoice_owners.values()
                    ),
                    "read_only": True,
                },
            )
        except Exception as error:
            invoice_owners = {}
            self.repository.append_event(
                job_id,
                "invoice_owner_read_degraded",
                {
                    "error_type": type(error).__name__,
                    "message": str(error),
                    "read_only": True,
                },
            )

        current_invoice_owners: dict[str, InvoiceOwnerEvidence] = {}
        current_owner_read_attempted = False
        current_owner_read_error = ""
        current_owner_loader = getattr(
            self.provider,
            "resolve_current_invoice_owners",
            None,
        )
        if invoice_numbers and callable(current_owner_loader):
            current_owner_read_attempted = True
            try:
                current_invoice_owners = dict(
                    current_owner_loader(invoice_numbers)
                )
                self.repository.append_event(
                    job_id,
                    "current_invoice_owners_loaded",
                    {
                        "invoice_count": len(invoice_numbers),
                        "resolved_count": sum(
                            bool(evidence.customer_numbers)
                            for evidence in current_invoice_owners.values()
                        ),
                        "source": "TMAROP current open AR",
                        "read_only": True,
                    },
                )
            except Exception as error:
                current_owner_read_error = (
                    f"{type(error).__name__}: {error}"
                )
                self.repository.append_event(
                    job_id,
                    "current_invoice_owner_read_degraded",
                    {
                        "error_type": type(error).__name__,
                        "message": str(error),
                        "read_only": True,
                    },
                )

        customer_cache: dict[str, Future[CustomerSnapshot]] = {}
        customer_group_cache: dict[
            str,
            Future[CustomerGroupSnapshot],
        ] = {}
        open_ar_cache: dict[
            tuple[str, date],
            Future[OpenARSnapshot],
        ] = {}
        cache_lock = threading.RLock()

        with ThreadPoolExecutor(
            max_workers=self.read_workers,
            thread_name_prefix="etop-lockbox-read",
        ) as executor:
            futures = [
                executor.submit(
                    self._prepare_transaction,
                    job_id,
                    transaction,
                    invoice_owners,
                    current_invoice_owners,
                    current_owner_read_attempted,
                    current_owner_read_error,
                    customer_cache,
                    customer_group_cache,
                    open_ar_cache,
                    cache_lock,
                )
                for transaction in transactions
            ]
            for future in as_completed(futures):
                # _prepare_transaction persists an explicit exception itself.
                future.result()

        return self.repository.finalize(job_id)

    def _prepare_transaction(
        self,
        job_id: str,
        transaction: SourceTransaction,
        invoice_owners: dict[str, InvoiceOwnerEvidence],
        current_invoice_owners: dict[str, InvoiceOwnerEvidence],
        current_owner_read_attempted: bool,
        current_owner_read_error: str,
        customer_cache: dict[str, Future[CustomerSnapshot]],
        customer_group_cache: dict[
            str,
            Future[CustomerGroupSnapshot],
        ],
        open_ar_cache: dict[
            tuple[str, date],
            Future[OpenARSnapshot],
        ],
        cache_lock: threading.RLock,
    ) -> None:
        transaction_id = transaction.transaction_id
        active_stage = "customer_resolution"
        conflict_assessment: CustomerConflictAssessment | None = None
        enterprise_group_assessment: EnterpriseGroupAssessment | None = None
        customer: CustomerSnapshot | None = None
        customer_group: CustomerGroupSnapshot | None = None
        group_open_ar: dict[str, OpenARSnapshot] = {}
        try:
            # begin_run() atomically claims queued work by moving each selected
            # transaction to RESOLVING_CUSTOMER before it is returned. Do not
            # repeat that durable transition here: on Windows the redundant
            # SQLite write serialized worker startup and defeated bounded
            # parallel reads.
            resolution = self.provider.resolve_customer(
                transaction,
                invoice_owners,
            )
            has_valid_invoice = any(
                normalize_invoice(value)
                for value in transaction.extracted_invoice_numbers
            )
            if (
                resolution.status == "ambiguous"
                or (has_valid_invoice and current_owner_read_attempted)
            ):
                active_stage = "customer_conflict_resolution"
                (
                    resolution,
                    conflict_assessment,
                    enterprise_group_assessment,
                ) = (
                    self._resolve_customer_conflict(
                        job_id,
                        transaction,
                        resolution,
                        invoice_owners,
                        current_invoice_owners,
                        current_owner_read_attempted,
                        current_owner_read_error,
                        customer_cache,
                        customer_group_cache,
                        open_ar_cache,
                        cache_lock,
                    )
                )
            if resolution.status != "resolved" or not resolution.customer_number:
                evidence = {
                    "customer_resolution": dataclass_payload(resolution),
                }
                if conflict_assessment is not None:
                    evidence["customer_conflict_assessment"] = (
                        conflict_assessment.payload()
                    )
                if enterprise_group_assessment is not None:
                    evidence["enterprise_group_assessment"] = (
                        enterprise_group_assessment.payload()
                    )
                self._save_exception(
                    job_id,
                    transaction,
                    stage="customer_resolution",
                    message=(
                        "ERP customer resolution requires professional review."
                    ),
                    retry_eligible=(
                        resolution.status == "unavailable"
                        or bool(
                            conflict_assessment
                            and conflict_assessment.status
                            == "evidence_unavailable"
                        )
                        or bool(
                            enterprise_group_assessment
                            and enterprise_group_assessment.status
                            == "evidence_unavailable"
                        )
                    ),
                    evidence=evidence,
                )
                return

            customer_number = resolution.customer_number
            as_of_date = transaction.payment_date or date.today()
            active_stage = "customer_master"
            customer = self._cached_read(
                customer_cache,
                customer_number,
                lambda: self.provider.load_customer(customer_number),
                cache_lock,
            )
            active_stage = "customer_group"
            customer_group = self._cached_read(
                customer_group_cache,
                customer_number,
                lambda: self.provider.load_customer_group(customer),
                cache_lock,
            )
            account_numbers = tuple(
                dict.fromkeys(
                    (
                        customer_number,
                        *(
                            account.customer_number
                            for account in customer_group.accounts
                            if account.customer_number
                        ),
                    )
                )
            )
            enterprise_number = str(
                customer_group.enterprise_number or ""
            ).strip().removesuffix(".0")
            group_evidence_incomplete = bool(
                enterprise_number
                and enterprise_number != "0"
                and (
                    not customer_group.complete
                    or len(account_numbers) < 2
                    or bool(customer_group.warnings)
                )
            )
            if group_evidence_incomplete:
                self._save_exception(
                    job_id,
                    transaction,
                    stage="enterprise_group_evidence",
                    message=(
                        "TMCUST.CUNUMENT was nonzero, but complete linked "
                        "customer-group evidence was not established."
                    ),
                    retry_eligible=False,
                    evidence={
                        "customer_resolution": dataclass_payload(resolution),
                        "customer_snapshot": dataclass_payload(customer),
                        "customer_group": dataclass_payload(customer_group),
                    },
                )
                return
            unavailable_group_accounts: list[str] = []
            group_failure_warnings: list[str] = []
            active_stage = "open_ar"
            for account_number in account_numbers:
                try:
                    group_open_ar[account_number] = self._cached_read(
                        open_ar_cache,
                        (account_number, as_of_date),
                        lambda account_number=account_number: (
                            self.provider.load_open_ar(
                                account_number,
                                as_of_date,
                            )
                        ),
                        cache_lock,
                    )
                except Exception as error:
                    unavailable_group_accounts.append(account_number)
                    group_failure_warnings.append(
                        "Current open AR was unavailable for CUNUMENT-linked "
                        f"ERP customer {account_number}: "
                        f"{type(error).__name__}: {error}"
                    )

            if unavailable_group_accounts:
                self._save_exception(
                    job_id,
                    transaction,
                    stage="enterprise_group_open_ar",
                    message=(
                        "Current open AR could not be read for every "
                        "CUNUMENT-linked ERP customer account."
                    ),
                    retry_eligible=True,
                    evidence={
                        "customer_resolution": dataclass_payload(resolution),
                        "customer_snapshot": dataclass_payload(customer),
                        "customer_group": dataclass_payload(customer_group),
                        "group_open_ar": dataclass_payload(group_open_ar),
                        "unavailable_customer_numbers": (
                            unavailable_group_accounts
                        ),
                        "warnings": group_failure_warnings,
                    },
                )
                return

            open_ar = group_open_ar[customer_number]
            if customer_group.enterprise_number:
                self.repository.append_event(
                    job_id,
                    "enterprise_customer_group_loaded",
                    {
                        "transaction_id": transaction.transaction_id,
                        "matched_customer_number": customer_number,
                        "enterprise_number": (
                            customer_group.enterprise_number
                        ),
                        "customer_numbers": list(account_numbers),
                        "group_complete": customer_group.complete,
                        "open_invoice_count": sum(
                            len(snapshot.invoices)
                            for snapshot in group_open_ar.values()
                        ),
                        "recommendation_not_decision": True,
                        "can_auto_approve": False,
                        "erp_write_performed": False,
                    },
                )

            active_stage = "allocation_evaluation"
            original_remittance_allocations = tuple(
                transaction.original_source.get("allocations", [])
            )
            row_disambiguation_assessment = disambiguate_remittance_rows(
                selected_customer_number=customer_number,
                rejected_candidates=tuple(
                    transaction.original_source.get(
                        "rejected_remittance_candidates",
                        [],
                    )
                ),
                open_invoices=open_ar.invoices,
            )
            effective_extracted_invoice_numbers = (
                transaction.extracted_invoice_numbers
            )
            effective_remittance_allocations = (
                original_remittance_allocations
            )
            if row_disambiguation_assessment.get("all_rows_resolved"):
                recovered_allocations = tuple(
                    row_disambiguation_assessment.get(
                        "recovered_allocations",
                        [],
                    )
                )
                effective_remittance_allocations = (
                    *original_remittance_allocations,
                    *recovered_allocations,
                )
                effective_extracted_invoice_numbers = tuple(
                    dict.fromkeys(
                        (
                            *transaction.extracted_invoice_numbers,
                            *(
                                str(row.get("invoice_number") or "")
                                for row in recovered_allocations
                            ),
                        )
                    )
                )
                self.repository.append_event(
                    job_id,
                    "remittance_rows_disambiguated",
                    {
                        "transaction_id": transaction.transaction_id,
                        "recovered_row_count": len(recovered_allocations),
                        "rule_version": (
                            row_disambiguation_assessment.get("rule_version")
                        ),
                        "original_rejections_preserved": True,
                        "recommendation_not_decision": True,
                        "can_auto_approve": False,
                        "erp_write_performed": False,
                    },
                )
            remittance_completion_assessment = (
                assess_remittance_reconciliation(
                    selected_customer_number=customer_number,
                    extracted_invoice_numbers=(
                        effective_extracted_invoice_numbers
                    ),
                    open_invoices=open_ar.invoices,
                    remittance_allocations=(
                        effective_remittance_allocations
                    ),
                    projection_evidence=transaction.projection_evidence,
                )
            )
            remittance_evidence_complete = bool(
                transaction.remittance_evidence_complete
                or remittance_completion_assessment.get(
                    "eligible_for_residual_completion"
                )
            )
            if (
                customer_group.enterprise_number
                and customer_group.complete
            ):
                recommendation = recommend_enterprise_group_allocation(
                    primary_customer_number=customer_number,
                    check_amount=transaction.check_amount,
                    extracted_invoice_numbers=(
                        effective_extracted_invoice_numbers
                    ),
                    primary_open_invoices=open_ar.invoices,
                    group_open_invoices=tuple(
                        invoice
                        for snapshot in group_open_ar.values()
                        for invoice in snapshot.invoices
                    ),
                    remittance_allocations=(
                        effective_remittance_allocations
                    ),
                    remittance_evidence_complete=(
                        remittance_evidence_complete
                    ),
                )
            else:
                recommendation = recommend_allocation(
                    check_amount=transaction.check_amount,
                    extracted_invoice_numbers=(
                        effective_extracted_invoice_numbers
                    ),
                    open_invoices=open_ar.invoices,
                    remittance_allocations=(
                        effective_remittance_allocations
                    ),
                    remittance_evidence_complete=(
                        remittance_evidence_complete
                    ),
                    payment_date=transaction.payment_date,
                )
            result = {
                "source": dataclass_payload(transaction),
                "customer_resolution": dataclass_payload(resolution),
                "customer_snapshot": dataclass_payload(customer),
                "open_ar": dataclass_payload(open_ar),
                "customer_group": dataclass_payload(customer_group),
                "group_open_ar": dataclass_payload(group_open_ar),
                "remittance_completion_assessment": (
                    remittance_completion_assessment
                ),
                "remittance_row_disambiguation_assessment": (
                    row_disambiguation_assessment
                ),
                "recommendation": dataclass_payload(recommendation),
                "rule_version": RULE_VERSION,
                "service_version": SERVICE_VERSION,
                "prepared_not_approved": True,
                "can_auto_approve": False,
                "erp_write_performed": False,
            }
            if conflict_assessment is not None:
                result["customer_conflict_assessment"] = (
                    conflict_assessment.payload()
                )
            if enterprise_group_assessment is not None:
                result["enterprise_group_assessment"] = (
                    enterprise_group_assessment.payload()
                )
            balanced = (
                recommendation.status == "recommended"
                and abs(
                    Decimal(str(recommendation.difference))
                ) <= AMOUNT_TOLERANCE
            )
            error_payload = (
                None
                if balanced
                else {
                    "stage": "allocation",
                    "message": "Allocation requires professional review.",
                    "warnings": list(recommendation.warnings),
                    "retry_eligible": False,
                }
            )
            if error_payload is not None:
                analysis = classify_exception(
                    state=TransactionState.PREPARED_EXCEPTION.value,
                    source=dataclass_payload(transaction),
                    result=result,
                    error=error_payload,
                )
                result["exception_analysis"] = analysis
                if analysis:
                    error_payload["reason_code"] = analysis[
                        "primary_reason"
                    ]["code"]
                    error_payload["reason_codes"] = analysis[
                        "reason_codes"
                    ]
            self.repository.complete_preparation_transaction(
                job_id,
                transaction_id,
                (
                    TransactionState.PREPARED_BALANCED
                    if balanced
                    else TransactionState.PREPARED_EXCEPTION
                ),
                result=result,
                error=error_payload,
                retry_eligible=False,
                terminal_event_type=(
                    "preparation_balanced"
                    if balanced
                    else "preparation_exception"
                ),
            )
        except Exception as error:
            evidence = {
                "error_type": type(error).__name__,
            }
            if conflict_assessment is not None:
                evidence["customer_conflict_assessment"] = (
                    conflict_assessment.payload()
                )
            if enterprise_group_assessment is not None:
                evidence["enterprise_group_assessment"] = (
                    enterprise_group_assessment.payload()
                )
            if customer is not None:
                evidence["customer_snapshot"] = dataclass_payload(customer)
            if customer_group is not None:
                evidence["customer_group"] = dataclass_payload(customer_group)
            if group_open_ar:
                evidence["group_open_ar"] = dataclass_payload(group_open_ar)
            self._save_exception(
                job_id,
                transaction,
                stage=active_stage,
                message=str(error),
                retry_eligible=not isinstance(
                    error,
                    PreparationPolicyError,
                ),
                evidence=evidence,
            )

    def _resolve_customer_conflict(
        self,
        job_id: str,
        transaction: SourceTransaction,
        resolution: CustomerResolution,
        invoice_owners: dict[str, InvoiceOwnerEvidence],
        current_invoice_owners: dict[str, InvoiceOwnerEvidence],
        current_owner_read_attempted: bool,
        current_owner_read_error: str,
        customer_cache: dict[str, Future[CustomerSnapshot]],
        customer_group_cache: dict[
            str,
            Future[CustomerGroupSnapshot],
        ],
        open_ar_cache: dict[
            tuple[str, date],
            Future[OpenARSnapshot],
        ],
        cache_lock: threading.RLock,
    ) -> tuple[
        CustomerResolution,
        CustomerConflictAssessment | None,
        EnterpriseGroupAssessment | None,
    ]:
        candidates = invoice_owner_candidates(
            transaction.extracted_invoice_numbers,
            invoice_owners,
        )
        assessment: CustomerConflictAssessment | None = None
        if current_owner_read_attempted:
            assessment = assess_current_open_invoice_owners(
                invoice_numbers=transaction.extracted_invoice_numbers,
                broad_invoice_owners=invoice_owners,
                current_invoice_owners=current_invoice_owners,
                read_unavailable=bool(current_owner_read_error),
            )
            candidates = tuple(
                dict.fromkeys(
                    (
                        *candidates,
                        *assessment.candidate_customer_numbers,
                    )
                )
            )
            self.repository.append_event(
                job_id,
                "current_invoice_ownership_assessed",
                {
                    "transaction_id": transaction.transaction_id,
                    "assessment": assessment.payload(),
                    "recommendation_not_decision": True,
                    "can_auto_approve": False,
                    "erp_write_performed": False,
                },
            )
            if assessment.status == "resolved" and assessment.customer_number:
                return (
                    CustomerResolution(
                        status="resolved",
                        customer_number=assessment.customer_number,
                        candidates=tuple(
                            dict.fromkeys(
                                (
                                    *resolution.candidates,
                                    *assessment.candidate_customer_numbers,
                                )
                            )
                        ),
                        matched_on=(assessment.explanation,),
                        warnings=resolution.warnings,
                        source_reference=(
                            "ERP TMAROP current open invoice ownership"
                        ),
                        as_of_time="; ".join(
                            sorted(
                                {
                                    evidence.as_of_time
                                    for evidence in current_invoice_owners.values()
                                    if evidence.as_of_time
                                }
                            )
                        ),
                        selection_basis="current_open_invoice_owner",
                        matching_evidence={
                            **dict(resolution.matching_evidence),
                            "selected_basis": (
                                "current_open_invoice_owner"
                            ),
                            "current_open_status": assessment.status,
                        },
                        selected_confidence=1.0,
                        confidence_basis="unique_current_open_invoice_owner",
                    ),
                    assessment,
                    None,
                )

            has_current_owner = any(
                owners
                for owners in assessment.current_open_invoice_owners.values()
            )
            must_hold = bool(
                assessment.status in {
                    "ambiguous",
                    "incomplete",
                    "evidence_unavailable",
                }
                or (
                    assessment.status == "not_found"
                    and len(candidates) >= 2
                )
            )
            if must_hold:
                resolution = CustomerResolution(
                    status="ambiguous",
                    customer_snapshot=(
                        resolution.customer_snapshot
                        if resolution.selection_basis
                        in {
                            "exact_phone_and_zip",
                            "unique_exact_phone",
                            "exact_address_and_zip",
                        }
                        else {}
                    ),
                    candidates=tuple(
                        dict.fromkeys(
                            (
                                *resolution.candidates,
                                *assessment.candidate_customer_numbers,
                            )
                        )
                    ),
                    matched_on=(
                        resolution.matched_on
                        if resolution.selection_basis
                        in {
                            "exact_phone_and_zip",
                            "unique_exact_phone",
                            "exact_address_and_zip",
                        }
                        else ()
                    ),
                    warnings=tuple(
                        dict.fromkeys(
                            (
                                *resolution.warnings,
                                assessment.explanation,
                                *(
                                    (current_owner_read_error,)
                                    if current_owner_read_error
                                    else ()
                                ),
                            )
                        )
                    ),
                    source_reference=resolution.source_reference,
                    as_of_time=resolution.as_of_time,
                    matching_evidence={
                        **dict(resolution.matching_evidence),
                        "current_open_status": assessment.status,
                        "current_open_owner_present": has_current_owner,
                    },
                )
                if assessment.status != "ambiguous":
                    return resolution, assessment, None
            else:
                return resolution, assessment, None

        if len(candidates) < 2:
            return resolution, assessment, None

        as_of_date = transaction.payment_date or date.today()
        snapshots: dict[str, OpenARSnapshot] = {}
        failure_warnings: list[str] = []
        if not current_owner_read_attempted:
            unavailable: list[str] = []
            for customer_number in candidates:
                try:
                    snapshots[customer_number] = self._cached_read(
                        open_ar_cache,
                        (customer_number, as_of_date),
                        lambda customer_number=customer_number: (
                            self.provider.load_open_ar(
                                customer_number,
                                as_of_date,
                            )
                        ),
                        cache_lock,
                    )
                except Exception as error:
                    unavailable.append(customer_number)
                    failure_warnings.append(
                        "Current open AR was unavailable for ERP customer "
                        f"{customer_number}: {type(error).__name__}: {error}"
                    )

            assessment = assess_current_open_ar_ownership(
                invoice_numbers=transaction.extracted_invoice_numbers,
                invoice_owners=invoice_owners,
                open_ar_by_customer=snapshots,
                unavailable_customer_numbers=unavailable,
            )
            self.repository.append_event(
                job_id,
                "customer_conflict_assessed",
                {
                    "transaction_id": transaction.transaction_id,
                    "assessment": assessment.payload(),
                    "recommendation_not_decision": True,
                    "can_auto_approve": False,
                    "erp_write_performed": False,
                },
            )
            if assessment.status == "resolved" and assessment.customer_number:
                return (
                    CustomerResolution(
                        status="resolved",
                        customer_number=assessment.customer_number,
                        candidates=tuple(
                            dict.fromkeys(
                                (
                                    *resolution.candidates,
                                    *assessment.candidate_customer_numbers,
                                )
                            )
                        ),
                        matched_on=(assessment.explanation,),
                        warnings=tuple(
                            dict.fromkeys(
                                (
                                    *resolution.warnings,
                                    "Broader ERP invoice-owner conflicts were "
                                    "retained; current open AR uniquely "
                                    "identified the recommended customer.",
                                )
                            )
                        ),
                        source_reference=(
                            "ERP current open AR invoice-owner reconciliation"
                        ),
                        as_of_time="; ".join(
                            sorted(
                                {
                                    snapshot.as_of_time
                                    for snapshot in snapshots.values()
                                    if snapshot.as_of_time
                                }
                            )
                        ),
                        selection_basis="current_open_invoice_owner",
                        matching_evidence={
                            **dict(resolution.matching_evidence),
                            "selected_basis": "current_open_invoice_owner",
                            "current_open_status": assessment.status,
                        },
                        selected_confidence=1.0,
                        confidence_basis="unique_current_open_invoice_owner",
                    ),
                    assessment,
                    None,
                )

        if assessment is None:
            return resolution, None, None

        enterprise_assessment: EnterpriseGroupAssessment | None = None
        anchor_number = str(
            resolution.customer_snapshot.get("customer_number") or ""
        ).strip().removesuffix(".0")
        if assessment.status == "ambiguous" and anchor_number:
            try:
                anchor_customer = self._cached_read(
                    customer_cache,
                    anchor_number,
                    lambda: self.provider.load_customer(anchor_number),
                    cache_lock,
                )
                group = self._cached_read(
                    customer_group_cache,
                    anchor_number,
                    lambda: self.provider.load_customer_group(anchor_customer),
                    cache_lock,
                )
                enterprise_assessment = assess_enterprise_group_conflict(
                    anchor_customer_number=anchor_number,
                    group=group,
                    conflict=assessment,
                )
            except Exception as error:
                enterprise_assessment = EnterpriseGroupAssessment(
                    status="evidence_unavailable",
                    anchor_customer_number=anchor_number,
                    candidate_customer_numbers=candidates,
                    explanation=(
                        "TMCUST CUNUMENT relationship evidence was "
                        f"unavailable: {type(error).__name__}: {error}"
                    ),
                )

            self.repository.append_event(
                job_id,
                "enterprise_customer_group_assessed",
                {
                    "transaction_id": transaction.transaction_id,
                    "assessment": enterprise_assessment.payload(),
                    "recommendation_not_decision": True,
                    "can_auto_approve": False,
                    "erp_write_performed": False,
                },
            )
            if enterprise_assessment.status == "resolved":
                return (
                    CustomerResolution(
                        status="resolved",
                        customer_number=anchor_number,
                        customer_snapshot=resolution.customer_snapshot,
                        candidates=tuple(
                            dict.fromkeys(
                                (
                                    *resolution.candidates,
                                    *assessment.candidate_customer_numbers,
                                    *enterprise_assessment.group_customer_numbers,
                                )
                            )
                        ),
                        matched_on=tuple(
                            dict.fromkeys(
                                (
                                    *resolution.matched_on,
                                    enterprise_assessment.explanation,
                                )
                            )
                        ),
                        warnings=tuple(
                            dict.fromkeys(
                                (
                                    *resolution.warnings,
                                    "Multiple customer accounts remain "
                                    "visible because cross-customer "
                                    "application requires human verification.",
                                )
                            )
                        ),
                        source_reference=(
                            "ERP normalized phone+ZIP identity and "
                            "TMCUST.CUNUMENT relationship"
                        ),
                        as_of_time=group.as_of_time,
                        selection_basis=(
                            "exact_phone_zip_cunument_group"
                        ),
                        matching_evidence={
                            **dict(resolution.matching_evidence),
                            "selected_basis": (
                                "exact_phone_zip_cunument_group"
                            ),
                        },
                        selected_confidence=(
                            resolution.selected_confidence
                        ),
                        confidence_basis=resolution.confidence_basis,
                    ),
                    assessment,
                    enterprise_assessment,
                )

        return (
            CustomerResolution(
                status=resolution.status,
                customer_number=resolution.customer_number,
                customer_snapshot=resolution.customer_snapshot,
                candidates=tuple(
                    dict.fromkeys(
                        (
                            *resolution.candidates,
                            *assessment.candidate_customer_numbers,
                        )
                    )
                ),
                matched_on=resolution.matched_on,
                warnings=tuple(
                    dict.fromkeys(
                        (
                            *resolution.warnings,
                            assessment.explanation,
                            *failure_warnings,
                        )
                    )
                ),
                source_reference=resolution.source_reference,
                as_of_time=resolution.as_of_time,
                selection_basis=resolution.selection_basis,
                matching_evidence=resolution.matching_evidence,
                selected_confidence=resolution.selected_confidence,
                confidence_basis=resolution.confidence_basis,
            ),
            assessment,
            enterprise_assessment,
        )

    def _save_exception(
        self,
        job_id: str,
        transaction: SourceTransaction,
        *,
        stage: str,
        message: str,
        retry_eligible: bool,
        evidence: dict[str, Any],
    ) -> None:
        current = self.repository.get_transaction(
            job_id,
            transaction.transaction_id,
        )
        state = TransactionState(current["state"])
        if state is TransactionState.PREPARED_EXCEPTION:
            return
        source_payload = dataclass_payload(transaction)
        result_payload = {
            "source": source_payload,
            "evidence": evidence,
            "rule_version": RULE_VERSION,
            "service_version": SERVICE_VERSION,
            "prepared_not_approved": True,
            "can_auto_approve": False,
            "erp_write_performed": False,
        }
        error_payload = {
            "stage": stage,
            "message": message,
            "retry_eligible": retry_eligible,
        }
        analysis = classify_exception(
            state=TransactionState.PREPARED_EXCEPTION.value,
            source=source_payload,
            result=result_payload,
            error=error_payload,
        )
        result_payload["exception_analysis"] = analysis
        if analysis:
            error_payload["reason_code"] = analysis["primary_reason"][
                "code"
            ]
            error_payload["reason_codes"] = analysis["reason_codes"]
        self.repository.transition_transaction(
            job_id,
            transaction.transaction_id,
            TransactionState.PREPARED_EXCEPTION,
            result=result_payload,
            error=error_payload,
            retry_eligible=retry_eligible,
            event_type="preparation_exception",
        )

    @staticmethod
    def _cached_read(
        cache: dict[Any, Future[Any]],
        key: Any,
        loader: Any,
        lock: threading.RLock,
    ) -> Any:
        owner = False
        with lock:
            pending = cache.get(key)
            if pending is None:
                pending = Future()
                cache[key] = pending
                owner = True
        if owner:
            try:
                pending.set_result(loader())
            except BaseException as error:
                pending.set_exception(error)
                with lock:
                    if cache.get(key) is pending:
                        cache.pop(key, None)
        return pending.result()

    def status(self, job_id: str) -> dict[str, Any]:
        return self.repository.get_job(job_id)

    def history(self, job_id: str) -> list[dict[str, Any]]:
        return self.repository.list_events(job_id)

    def shutdown(self, wait: bool = True) -> None:
        self._job_executor.shutdown(wait=wait, cancel_futures=False)

    def __enter__(self) -> "DurableLockboxPreparationCoordinator":
        return self

    def __exit__(self, *_: object) -> None:
        self.shutdown()
