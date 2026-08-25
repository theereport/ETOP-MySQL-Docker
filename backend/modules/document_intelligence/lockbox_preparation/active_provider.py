"""Adapters for ETOP's active read-only ERP/customer services.

This module translates the existing customer-match and receivables contracts
into the durable Lockbox preparation contracts. It does not own customer
matching policy and it exposes no ERP write operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from customer_match import (
    CustomerMatchRequest,
    _find_invoice_owners,
    _select_exact_address_postal_records,
    _resolve_customer_columns,
    _select_enterprise_customer_records,
    _select_exact_phone_records,
    _select_customer_records,
)
from customer_match_service import (
    CUSTOMER_MATCH_RULE_VERSION,
    CustomerMatchInput,
    exact_address_postal_matches,
    exact_phone_matches,
    exact_phone_postal_matches,
    rank_customer_matches,
)

from .contracts import (
    CustomerResolution,
    CustomerGroupSnapshot,
    CustomerSnapshot,
    InvoiceOwnerEvidence,
    OpenARSnapshot,
    OpenInvoice,
    SourceTransaction,
)
from .policy import normalize_invoice


InvoiceOwnerLoader = Callable[
    [list[str]],
    tuple[dict[str, set[str]], list[str]],
]
CustomerColumnsLoader = Callable[[], dict[str, str | None]]
CustomerRecordLoader = Callable[
    [dict[str, str | None], CustomerMatchRequest, set[str]],
    list[dict[str, Any]],
]
CustomerGroupRecordLoader = Callable[
    [dict[str, str | None], str, str],
    list[dict[str, Any]],
]
ExactPhoneLoader = Callable[
    [dict[str, str | None], str],
    tuple[list[dict[str, Any]], bool],
]
ExactAddressLoader = Callable[
    [dict[str, str | None], str, str],
    tuple[list[dict[str, Any]], bool],
]


@dataclass(frozen=True)
class _InternalCustomerMatchRequest:
    """Untrusted OCR fields prepared for an internal read-only query.

    The public FastAPI request model intentionally enforces HTTP payload
    limits.  Durable preparation must not reuse that model for already-saved
    OCR data because one large remit or overlong OCR field would raise a
    deterministic Pydantic ValidationError before evidence could be saved.
    """

    invoice_numbers: tuple[str, ...] = ()
    phone: str = ""
    address_line_1: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    customer_name: str = ""
    search_text: str = ""
    limit: int = 8


def _safe_match_text(
    value: Any,
    *,
    maximum: int,
    field_name: str,
) -> tuple[str, str]:
    if value is None or value == "":
        return "", ""
    if not isinstance(value, (str, int, float)):
        return "", f"{field_name}:unsupported_type"
    text = str(value).strip()
    if len(text) > maximum:
        return "", f"{field_name}:overlength"
    return text, ""


def _ranked_matching_evidence(
    ranked: Mapping[str, Any],
    *,
    valid_invoice_count: int,
    rejected_inputs: Sequence[str] = (),
    candidate_query_returned_count: int = 0,
    candidate_query_bound: int = 250,
    candidate_query_complete: bool | None = None,
) -> dict[str, Any]:
    ranked_candidates = [
        {
            **_customer_fields(candidate),
            "score": float(candidate.get("score") or 0),
            "confidence": float(candidate.get("confidence") or 0),
            "match_type": str(candidate.get("match_type") or ""),
            "matched_on": list(candidate.get("matched_on") or []),
            "matched_invoice_numbers": list(
                candidate.get("matched_invoice_numbers") or []
            ),
        }
        for candidate in ranked.get("candidates", [])
    ]
    return {
        "valid_invoice_count": valid_invoice_count,
        "invoice_owner_conflict": bool(
            ranked.get("invoice_owner_conflict")
        ),
        "unresolved_invoice_owner_count": int(
            ranked.get("unresolved_invoice_owner_count") or 0
        ),
        "partial_invoice_owner_evidence": bool(
            ranked.get("partial_invoice_owner_evidence")
        ),
        "ranked_candidate_count": int(
            ranked.get("ranked_candidate_count") or 0
        ),
        "exact_phone_postal_match_count": int(
            ranked.get("exact_phone_postal_match_count") or 0
        ),
        "exact_phone_match_count": int(
            ranked.get("exact_phone_match_count") or 0
        ),
        "contact_candidate_complete": bool(
            ranked.get("contact_candidate_complete")
        ),
        "phone_candidate_complete": bool(
            ranked.get("contact_candidate_complete")
        ),
        "top_score": ranked.get("top_score"),
        "runner_up_score": ranked.get("runner_up_score"),
        "score_lead": ranked.get("score_lead"),
        "selected_basis": str(ranked.get("selected_basis") or ""),
        "failed_selection_gates": list(
            ranked.get("failed_selection_gates") or []
        ),
        "candidate_snapshot_version": "lockbox-candidate-evidence@1.0.0",
        "ranked_candidates": ranked_candidates,
        "candidate_query_returned_count": candidate_query_returned_count,
        "candidate_query_bound": candidate_query_bound,
        "candidate_query_complete": (
            bool(candidate_query_complete)
            if candidate_query_complete is not None
            else candidate_query_returned_count < candidate_query_bound
        ),
        "rejected_input_fields": list(rejected_inputs),
        "rule_version": str(
            ranked.get("rule_version") or CUSTOMER_MATCH_RULE_VERSION
        ),
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _customer_number(value: Any) -> str:
    return str(value or "").strip().removesuffix(".0")


def _customer_fields(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "customer_number": _customer_number(record.get("customer_number")),
        "customer_name": str(record.get("customer_name") or "").strip(),
        "phone": str(record.get("phone") or "").strip(),
        "address_line_1": str(record.get("address_line_1") or "").strip(),
        "address_line_2": str(record.get("address_line_2") or "").strip(),
        "city": str(record.get("city") or "").strip(),
        "state": str(record.get("state") or "").strip(),
        "postal_code": str(record.get("postal_code") or "").strip(),
        "enterprise_number": _customer_number(
            record.get("enterprise_number")
        ),
    }


class ExistingReadOnlyPreparationProvider:
    """Reuse ETOP's established customer and open-AR read services."""

    def __init__(
        self,
        receivables_repository: Any,
        *,
        invoice_owner_loader: InvoiceOwnerLoader = _find_invoice_owners,
        customer_columns_loader: CustomerColumnsLoader = (
            _resolve_customer_columns
        ),
        customer_record_loader: CustomerRecordLoader = (
            _select_customer_records
        ),
        customer_group_record_loader: CustomerGroupRecordLoader = (
            _select_enterprise_customer_records
        ),
        exact_phone_loader: ExactPhoneLoader = (
            _select_exact_phone_records
        ),
        exact_address_loader: ExactAddressLoader = (
            _select_exact_address_postal_records
        ),
    ) -> None:
        self.receivables_repository = receivables_repository
        self._invoice_owner_loader = invoice_owner_loader
        self._customer_columns_loader = customer_columns_loader
        self._customer_record_loader = customer_record_loader
        self._customer_group_record_loader = customer_group_record_loader
        self._exact_phone_loader = exact_phone_loader
        self._exact_address_loader = exact_address_loader

    def resolve_invoice_owners(
        self,
        invoice_numbers: Sequence[str],
    ) -> Mapping[str, InvoiceOwnerEvidence]:
        normalized = list(
            dict.fromkeys(
                invoice
                for value in invoice_numbers
                if (invoice := normalize_invoice(value))
            )
        )
        if not normalized:
            return {}

        owners, warnings = self._invoice_owner_loader(normalized)
        as_of_time = _utc_now()
        warning_text = "; ".join(warnings)
        return {
            invoice: InvoiceOwnerEvidence(
                invoice_number=invoice,
                customer_numbers=tuple(
                    sorted(
                        _customer_number(value)
                        for value in owners.get(invoice, set())
                        if _customer_number(value)
                    )
                ),
                source_reference=(
                    "ERP invoice-owner lookup"
                    + (f"; {warning_text}" if warning_text else "")
                ),
                as_of_time=as_of_time,
            )
            for invoice in normalized
        }

    def resolve_current_invoice_owners(
        self,
        invoice_numbers: Sequence[str],
    ) -> Mapping[str, InvoiceOwnerEvidence]:
        normalized = tuple(
            dict.fromkeys(
                invoice
                for value in invoice_numbers
                if (invoice := normalize_invoice(value))
            )
        )
        if not normalized:
            return {}
        owners = self.receivables_repository.get_current_invoice_owners(
            normalized
        )
        as_of_time = _utc_now()
        return {
            invoice: InvoiceOwnerEvidence(
                invoice_number=invoice,
                customer_numbers=tuple(
                    sorted(
                        _customer_number(value)
                        for value in owners.get(invoice, set())
                        if _customer_number(value)
                    )
                ),
                source_reference="ERP TMAROP current open invoice ownership",
                as_of_time=as_of_time,
            )
            for invoice in normalized
        }

    def resolve_customer(
        self,
        transaction: SourceTransaction,
        invoice_owners: Mapping[str, InvoiceOwnerEvidence],
    ) -> CustomerResolution:
        valid_invoices = tuple(
            dict.fromkeys(
                invoice
                for value in transaction.extracted_invoice_numbers
                if (invoice := normalize_invoice(value))
            )
        )
        owner_sets = [
            set(invoice_owners[invoice].customer_numbers)
            for invoice in valid_invoices
            if invoice in invoice_owners
        ]
        all_invoices_have_one_owner = bool(valid_invoices) and (
            len(owner_sets) == len(valid_invoices)
            and all(len(owners) == 1 for owners in owner_sets)
        )
        unique_owners = set().union(*owner_sets) if owner_sets else set()

        if all_invoices_have_one_owner and len(unique_owners) == 1:
            customer_number = next(iter(unique_owners))
            customer = self.load_customer(customer_number)
            return CustomerResolution(
                status="resolved",
                customer_number=customer_number,
                customer_snapshot=customer.fields,
                matched_on=(
                    "All valid remittance invoices identify one ERP customer.",
                ),
                source_reference=(
                    "ERP invoice ownership and customer master"
                ),
                as_of_time=customer.as_of_time,
                selection_basis="broad_invoice_owner",
                matching_evidence={
                    "valid_invoice_count": len(valid_invoices),
                    "invoice_owner_conflict": False,
                    "unresolved_invoice_owner_count": 0,
                    "partial_invoice_owner_evidence": False,
                    "selected_basis": "broad_invoice_owner",
                    "rule_version": CUSTOMER_MATCH_RULE_VERSION,
                },
                selected_confidence=1.0,
                confidence_basis="unique_remittance_invoice_owner",
            )

        source = transaction.original_source
        supplied_customer_number = _customer_number(
            source.get("printed_customer_number")
        )
        supplied_customer_number_valid = bool(
            supplied_customer_number.isdigit()
            and 4 <= len(supplied_customer_number) <= 12
        )
        supplied_customer_number_conflict = bool(
            supplied_customer_number_valid
            and any(
                owners and owners != {supplied_customer_number}
                for owners in owner_sets
            )
        )
        directive_warnings: list[str] = []
        if supplied_customer_number_valid:
            try:
                supplied_customer = self.load_customer(
                    supplied_customer_number
                )
            except Exception as error:
                supplied_customer = None
                directive_warnings.append(
                    "The payer supplied ERP customer account "
                    f"{supplied_customer_number}, but the exact read-only "
                    f"customer lookup did not verify it: {type(error).__name__}."
                )
            if supplied_customer and not supplied_customer_number_conflict:
                unresolved_owner_count = sum(
                    not owners for owners in owner_sets
                )
                return CustomerResolution(
                    status="resolved",
                    customer_number=supplied_customer_number,
                    customer_snapshot=supplied_customer.fields,
                    candidates=(supplied_customer_number,),
                    matched_on=(
                        "The payer explicitly directed this payment to one "
                        "verified ERP customer account.",
                    ),
                    source_reference=(
                        "PNC check payer directive and ERP customer master"
                    ),
                    as_of_time=supplied_customer.as_of_time,
                    selection_basis="payer_supplied_customer_number",
                    matching_evidence={
                        "valid_invoice_count": len(valid_invoices),
                        "invoice_owner_conflict": False,
                        "unresolved_invoice_owner_count": (
                            unresolved_owner_count
                        ),
                        "partial_invoice_owner_evidence": bool(
                            any(owner_sets) and unresolved_owner_count
                        ),
                        "payer_supplied_customer_number": (
                            supplied_customer_number
                        ),
                        "payer_account_directive_verified": True,
                        "payer_account_directive_conflict": False,
                        "selected_basis": (
                            "payer_supplied_customer_number"
                        ),
                        "rule_version": CUSTOMER_MATCH_RULE_VERSION,
                    },
                    selected_confidence=1.0,
                    confidence_basis="payer_supplied_customer_number",
                )
            if supplied_customer_number_conflict:
                directive_warnings.append(
                    "The payer-supplied ERP customer account conflicts with "
                    "preserved invoice-owner evidence and cannot select a "
                    "customer."
                )

        statement_customer_number = _customer_number(
            source.get("statement_customer_number")
        )
        statement_customer_number_valid = bool(
            statement_customer_number.isdigit()
            and len(statement_customer_number) in (6, 7)
        )
        statement_customer_number_conflict = bool(
            statement_customer_number_valid
            and any(
                owners and owners != {statement_customer_number}
                for owners in owner_sets
            )
        )
        if statement_customer_number_valid:
            try:
                statement_customer = self.load_customer(
                    statement_customer_number
                )
            except Exception as error:
                statement_customer = None
                directive_warnings.append(
                    "The K&M statement supplied ERP customer account "
                    f"{statement_customer_number}, but the exact read-only "
                    f"customer lookup did not verify it: {type(error).__name__}."
                )
            if statement_customer and not statement_customer_number_conflict:
                unresolved_owner_count = sum(
                    not owners for owners in owner_sets
                )
                return CustomerResolution(
                    status="resolved",
                    customer_number=statement_customer_number,
                    customer_snapshot=statement_customer.fields,
                    candidates=(statement_customer_number,),
                    matched_on=(
                        "A K&M statement identifies one verified ERP "
                        "customer account.",
                    ),
                    source_reference=(
                        "K&M statement customer block and ERP customer master"
                    ),
                    as_of_time=statement_customer.as_of_time,
                    selection_basis="km_statement_customer_number",
                    matching_evidence={
                        "valid_invoice_count": len(valid_invoices),
                        "invoice_owner_conflict": False,
                        "unresolved_invoice_owner_count": (
                            unresolved_owner_count
                        ),
                        "partial_invoice_owner_evidence": bool(
                            any(owner_sets) and unresolved_owner_count
                        ),
                        "km_statement_customer_number": (
                            statement_customer_number
                        ),
                        "km_statement_customer_verified": True,
                        "km_statement_customer_conflict": False,
                        "selected_basis": "km_statement_customer_number",
                        "rule_version": CUSTOMER_MATCH_RULE_VERSION,
                    },
                    selected_confidence=1.0,
                    confidence_basis="km_statement_customer_number",
                )
            if statement_customer_number_conflict:
                directive_warnings.append(
                    "The K&M statement customer account conflicts with "
                    "preserved invoice-owner evidence and cannot select a "
                    "customer."
                )

        for_customer_number = _customer_number(
            source.get("for_customer_number")
        )
        for_customer_number_valid = bool(
            for_customer_number.isdigit()
            and len(for_customer_number) in (6, 7)
        )
        for_customer_number_conflict = bool(
            for_customer_number_valid
            and any(
                owners and owners != {for_customer_number}
                for owners in owner_sets
            )
        )
        if for_customer_number_valid:
            try:
                for_customer = self.load_customer(for_customer_number)
            except Exception as error:
                for_customer = None
                directive_warnings.append(
                    "The check FOR line supplied ERP customer account "
                    f"{for_customer_number}, but the exact read-only "
                    f"customer lookup did not verify it: {type(error).__name__}."
                )
            if for_customer and not for_customer_number_conflict:
                unresolved_owner_count = sum(
                    not owners for owners in owner_sets
                )
                return CustomerResolution(
                    status="resolved",
                    customer_number=for_customer_number,
                    customer_snapshot=for_customer.fields,
                    candidates=(for_customer_number,),
                    matched_on=(
                        "The check FOR line identifies one verified ERP "
                        "customer account after stronger account and "
                        "statement evidence was exhausted.",
                    ),
                    source_reference=(
                        "PNC check FOR line and ERP customer master"
                    ),
                    as_of_time=for_customer.as_of_time,
                    selection_basis="check_for_customer_number",
                    matching_evidence={
                        "valid_invoice_count": len(valid_invoices),
                        "invoice_owner_conflict": False,
                        "unresolved_invoice_owner_count": (
                            unresolved_owner_count
                        ),
                        "partial_invoice_owner_evidence": bool(
                            any(owner_sets) and unresolved_owner_count
                        ),
                        "check_for_customer_number": for_customer_number,
                        "check_for_customer_verified": True,
                        "check_for_customer_conflict": False,
                        "selected_basis": "check_for_customer_number",
                        "rule_version": CUSTOMER_MATCH_RULE_VERSION,
                    },
                    selected_confidence=1.0,
                    confidence_basis="check_for_customer_number",
                )
            if for_customer_number_conflict:
                directive_warnings.append(
                    "The check FOR-line customer account conflicts with "
                    "preserved invoice-owner evidence and cannot select a "
                    "customer."
                )

        source_fields = {
            "phone": (source.get("customer_phone"), 80),
            "address_line_1": (
                source.get("customer_address_line_1"),
                200,
            ),
            "city": (source.get("customer_city"), 100),
            "state": (source.get("customer_state"), 40),
            "postal_code": (source.get("customer_postal_code"), 40),
            "customer_name": (source.get("customer_name"), 200),
            "search_text": (
                source.get("erp_customer_number")
                or source.get("printed_customer_number")
                or source.get("statement_customer_number")
                or source.get("customer_number"),
                200,
            ),
        }
        prepared_fields: dict[str, str] = {}
        rejected_inputs: list[str] = []
        for field_name, (value, maximum) in source_fields.items():
            prepared, rejection = _safe_match_text(
                value,
                maximum=maximum,
                field_name=field_name,
            )
            prepared_fields[field_name] = prepared
            if rejection:
                rejected_inputs.append(rejection)
        request = _InternalCustomerMatchRequest(
            invoice_numbers=valid_invoices,
            **prepared_fields,
        )
        owner_map = {
            invoice: set(
                invoice_owners.get(
                    invoice,
                    InvoiceOwnerEvidence(invoice),
                ).customer_numbers
            )
            for invoice in valid_invoices
        }
        owner_numbers = set().union(*owner_map.values()) if owner_map else set()

        try:
            customers = self._customer_record_loader(
                self._customer_columns_loader(),
                request,
                owner_numbers,
            )
            match_input = CustomerMatchInput(
                invoice_numbers=valid_invoices,
                phone=request.phone or "",
                address_line_1=request.address_line_1 or "",
                city=request.city or "",
                state=request.state or "",
                postal_code=request.postal_code or "",
                customer_name=request.customer_name or "",
                search_text=request.search_text or "",
            )
            phone_rows, phone_candidate_complete = (
                self._exact_phone_loader(
                    self._customer_columns_loader(),
                    request.phone or "",
                )
            )
            address_rows, address_candidate_complete = (
                self._exact_address_loader(
                    self._customer_columns_loader(),
                    request.address_line_1 or "",
                    request.postal_code or "",
                )
            )
            customer_by_number = {
                _customer_number(customer.get("customer_number")): customer
                for customer in (*customers, *phone_rows, *address_rows)
                if _customer_number(customer.get("customer_number"))
            }
            complete_customers = list(customer_by_number.values())
            ranked = rank_customer_matches(
                complete_customers,
                match_input,
                owner_map,
                request.limit,
                contact_candidate_complete=phone_candidate_complete,
                address_candidate_complete=address_candidate_complete,
            )
            phone_matches = exact_phone_matches(
                complete_customers,
                match_input,
            )
            contact_matches = exact_phone_postal_matches(
                complete_customers,
                match_input,
            )
            address_matches = exact_address_postal_matches(
                complete_customers,
                match_input,
            )
        except Exception as error:
            return CustomerResolution(
                status="unavailable",
                candidates=tuple(sorted(owner_numbers)),
                warnings=(
                    f"ERP customer matching was unavailable: {error}",
                ),
                source_reference="ERP customer-match service",
                as_of_time=_utc_now(),
                matching_evidence={
                    "valid_invoice_count": len(valid_invoices),
                    "rejected_input_fields": rejected_inputs,
                    "rule_version": CUSTOMER_MATCH_RULE_VERSION,
                },
            )

        recommended = ranked.get("recommended_customer")
        matching_evidence = _ranked_matching_evidence(
            ranked,
            valid_invoice_count=len(valid_invoices),
            rejected_inputs=rejected_inputs,
            candidate_query_returned_count=len(phone_rows),
            candidate_query_complete=phone_candidate_complete,
        )
        matching_evidence.update(
            {
                "exact_address_postal_match_count": len(address_matches),
                "address_candidate_complete": address_candidate_complete,
                "address_candidate_query_returned_count": len(address_rows),
                "address_candidate_query_bound": 250,
                "payer_supplied_customer_number": (
                    supplied_customer_number
                    if supplied_customer_number_valid
                    else ""
                ),
                "payer_account_directive_verified": False,
                "payer_account_directive_conflict": (
                    supplied_customer_number_conflict
                ),
                "km_statement_customer_number": (
                    statement_customer_number
                    if statement_customer_number_valid
                    else ""
                ),
                "km_statement_customer_verified": False,
                "km_statement_customer_conflict": (
                    statement_customer_number_conflict
                ),
                "check_for_customer_number": (
                    for_customer_number
                    if for_customer_number_valid
                    else ""
                ),
                "check_for_customer_verified": False,
                "check_for_customer_conflict": (
                    for_customer_number_conflict
                ),
            }
        )
        candidates = tuple(
            _customer_number(candidate.get("customer_number"))
            for candidate in ranked.get("candidates", [])
            if _customer_number(candidate.get("customer_number"))
        )
        if recommended:
            fields = _customer_fields(recommended)
            selection_basis = str(ranked.get("selected_basis") or "")
            matched_on = tuple(recommended.get("matched_on", []))
            address_confirmed = any(
                "street address" in reason.lower()
                for reason in matched_on
            )
            selected_confidence = float(
                recommended.get("confidence") or 0
            )
            confidence_basis = selection_basis
            if selection_basis == "exact_phone_and_zip" and address_confirmed:
                selected_confidence = 1.0
                confidence_basis = (
                    "unique_phone_zip_with_address_confirmation"
                )
            elif selection_basis == "unique_exact_phone":
                corroborated = bool(
                    address_confirmed
                    or any(
                        reason.startswith("ZIP code ")
                        for reason in matched_on
                    )
                    or any(
                        "customer name" in reason.lower()
                        for reason in matched_on
                    )
                )
                if corroborated:
                    selected_confidence = 1.0
                    confidence_basis = (
                        "unique_phone_with_contact_confirmation"
                    )
            elif selection_basis == "exact_address_and_zip":
                selected_confidence = 1.0
                confidence_basis = "unique_exact_address_and_zip"
            return CustomerResolution(
                status="resolved",
                customer_number=fields["customer_number"],
                customer_snapshot=fields,
                candidates=candidates,
                matched_on=matched_on,
                warnings=tuple(directive_warnings),
                source_reference="ERP customer-match service",
                as_of_time=_utc_now(),
                selection_basis=selection_basis,
                matching_evidence=matching_evidence,
                selected_confidence=selected_confidence,
                confidence_basis=confidence_basis,
            )

        message = str(ranked.get("message") or "").strip()
        failed_selection_gates = set(
            ranked.get("failed_selection_gates") or []
        )
        exact_phone_zip_anchor = bool(
            phone_candidate_complete and len(contact_matches) == 1
        )
        unique_phone_anchor = bool(
            phone_candidate_complete
            and len(phone_matches) == 1
            and "unique_phone_postal_conflict" not in failed_selection_gates
        )
        exact_address_anchor = bool(
            address_candidate_complete
            and len(address_matches) == 1
            and "address_phone_conflict" not in failed_selection_gates
        )
        anchor_record = (
            contact_matches[0]
            if exact_phone_zip_anchor
            else phone_matches[0]
            if unique_phone_anchor
            else address_matches[0]
            if exact_address_anchor
            else None
        )
        supporting_fields = (
            _customer_fields(anchor_record) if anchor_record else {}
        )
        anchor_basis = (
            "exact_phone_and_zip"
            if exact_phone_zip_anchor
            else "unique_exact_phone"
            if unique_phone_anchor
            else "exact_address_and_zip"
            if exact_address_anchor
            else ""
        )
        anchor_confidence = (
            1.0
            if exact_phone_zip_anchor or exact_address_anchor
            else 0.99 if unique_phone_anchor else 0.0
        )
        anchor_explanation = (
            "Phone number and first five ZIP digits uniquely match one ERP "
            "customer, but conflicting invoice owners still require "
            "relationship verification."
            if exact_phone_zip_anchor
            else "The normalized phone uniquely matches one ERP customer, "
            "but conflicting invoice owners still require relationship "
            "verification."
            if unique_phone_anchor
            else "The normalized street and first five ZIP digits uniquely "
            "match one ERP customer, but conflicting invoice owners still "
            "require relationship verification."
        )
        return CustomerResolution(
            status="ambiguous" if candidates or owner_numbers else "not_found",
            customer_snapshot=supporting_fields,
            candidates=candidates or tuple(sorted(owner_numbers)),
            matched_on=(
                (
                    anchor_explanation
                ),
            ) if supporting_fields else (),
            warnings=tuple(
                dict.fromkeys(
                    (
                        *((message,) if message else ()),
                        *directive_warnings,
                    )
                )
            ),
            source_reference="ERP customer-match service",
            as_of_time=_utc_now(),
            selection_basis=anchor_basis,
            matching_evidence=matching_evidence,
            selected_confidence=anchor_confidence,
            confidence_basis=anchor_basis,
        )

    def load_customer(
        self,
        customer_number: str,
    ) -> CustomerSnapshot:
        normalized_number = _customer_number(customer_number)
        records = self._customer_record_loader(
            self._customer_columns_loader(),
            CustomerMatchRequest(),
            {normalized_number},
        )
        exact = next(
            (
                record
                for record in records
                if _customer_number(record.get("customer_number"))
                == normalized_number
            ),
            None,
        )
        if exact is None:
            raise LookupError(
                f"ERP customer {normalized_number} was not found."
            )
        return CustomerSnapshot(
            customer_number=normalized_number,
            fields=_customer_fields(exact),
            source_reference="ERP customer master",
            as_of_time=_utc_now(),
        )

    def load_open_ar(
        self,
        customer_number: str,
        as_of_date: date,
    ) -> OpenARSnapshot:
        invoices = self.receivables_repository.get_open_invoices(
            customer_number=customer_number,
            aging_as_of_date=as_of_date,
        )
        recorded_at = _utc_now()
        rows = tuple(
            OpenInvoice(
                customer_number=_customer_number(invoice.customer_number),
                invoice_number=str(invoice.invoice_number or ""),
                open_amount=invoice.open_amount,
                due_date=invoice.due_date,
                invoice_date=invoice.invoice_date,
                raw_transaction_type=(
                    str(invoice.transaction_type or "").strip()
                    or str(invoice.debit_credit or "").strip()
                ),
                signed_source_amount=(
                    -abs(invoice.open_amount)
                    if invoice.open_amount < 0
                    else -abs(invoice.original_amount)
                    if invoice.original_amount < 0
                    else abs(invoice.open_amount)
                ),
                aging_bucket=str(invoice.aging_bucket or ""),
                source_reference=(
                    "ERP open AR"
                    f"; customer={_customer_number(invoice.customer_number)}"
                    f"; invoice={invoice.invoice_number}"
                    f"; aging_as_of={as_of_date.isoformat()}"
                ),
                invoice_count=getattr(invoice, "invoice_count", None),
                open_item_key="|".join(
                    (
                        _customer_number(invoice.customer_number),
                        str(invoice.transaction_type or "").strip().upper(),
                        str(invoice.invoice_number or "").strip(),
                        str(getattr(invoice, "invoice_count", None) or ""),
                    )
                ),
            )
            for invoice in invoices
        )
        return OpenARSnapshot(
            customer_number=_customer_number(customer_number),
            invoices=rows,
            as_of_time=recorded_at,
            source_reference=(
                "ERP open AR"
                f"; customer={_customer_number(customer_number)}"
                f"; aging_as_of={as_of_date.isoformat()}"
            ),
        )

    def load_customer_group(
        self,
        customer: CustomerSnapshot,
    ) -> CustomerGroupSnapshot:
        matched_number = _customer_number(customer.customer_number)
        enterprise_number = _customer_number(
            customer.fields.get("enterprise_number")
        )
        recorded_at = _utc_now()
        if not enterprise_number or enterprise_number == "0":
            return CustomerGroupSnapshot(
                matched_customer_number=matched_number,
                accounts=(customer,),
                source_reference=(
                    "ERP TMCUST customer master; CUNUMENT=0"
                ),
                as_of_time=recorded_at,
            )

        records = self._customer_group_record_loader(
            self._customer_columns_loader(),
            matched_number,
            enterprise_number,
        )
        account_by_number: dict[str, CustomerSnapshot] = {
            matched_number: customer,
        }
        for record in records:
            fields = _customer_fields(record)
            account_number = fields["customer_number"]
            linked_enterprise = fields["enterprise_number"]
            if not account_number:
                continue
            if not (
                account_number in {matched_number, enterprise_number}
                or linked_enterprise == enterprise_number
            ):
                continue
            account_by_number[account_number] = CustomerSnapshot(
                customer_number=account_number,
                fields=fields,
                source_reference=(
                    "ERP TMCUST customer master; "
                    f"CUNUMENT={enterprise_number}"
                ),
                as_of_time=recorded_at,
            )

        accounts = tuple(
            account_by_number[number]
            for number in sorted(account_by_number)
        )
        warnings: list[str] = []
        if len(accounts) == 1:
            warnings.append(
                "TMCUST CUNUMENT is nonzero, but no additional linked "
                "customer account was returned."
            )
        complete = len(records) < 251 and len(accounts) > 1
        if not complete:
            if len(records) >= 251:
                warnings.append(
                    "TMCUST CUNUMENT lookup reached the 250-account safety "
                    "limit; group completeness is not established."
                )
            elif len(accounts) == 1 and not warnings:
                warnings.append(
                    "TMCUST CUNUMENT is nonzero, but no additional linked "
                    "customer account was returned."
                )
        return CustomerGroupSnapshot(
            matched_customer_number=matched_number,
            enterprise_number=enterprise_number,
            accounts=accounts,
            source_reference=(
                "ERP TMCUST enterprise relationship; "
                f"CUNUMENT={enterprise_number}"
            ),
            as_of_time=recorded_at,
            complete=complete,
            warnings=tuple(warnings),
        )
