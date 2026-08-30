from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from modules.accounts_payable.service import accounts_payable_service
from modules.customer_360.service import customer_service

from .repository import ERPEvidenceRepository, erp_evidence_repository
from .schemas import (
    APBoundedCollection,
    APERPEvidenceResponse,
    APERPInvoiceLookupIdentity,
    APGLDistributionEvidence,
    APInputInvoiceHeaderEvidence,
    APInputPaymentSplitEvidence,
    APInvoiceDetailEvidence,
    APInvoiceSearchCandidate,
    APInvoiceSearchQuery,
    APInvoiceSearchResponse,
    APLocalInvoiceIdentity,
    APMappingCategory,
    APMappingReadinessResponse,
    APPostedInvoiceHeaderEvidence,
    APVendorSearchCandidate,
    APVendorEvidence,
    CreditCurrentEvidence,
    CreditERPEvidenceResponse,
    CreditOpenARCollection,
    CreditOpenItem,
    ERPEvidenceGatewayStatus,
    EvidenceCoverageItem,
    EvidenceGovernance,
    EvidenceSourceReference,
    RelatedAccountCollection,
    RelatedCustomerEvidence,
)


CONTRACT_VERSION = "erp-evidence-gateway@1.1.0"
AP_CATEGORY_LABELS = {
    "vendor_master": "Vendor master",
    "posted_invoice_history": "Posted invoice history",
    "po_receiver_reference": "PO/receiver references on invoice detail",
    "gl_distribution": "AP GL distribution history",
    "input_invoice": "AP invoice input",
    "input_invoice_detail": "AP invoice input detail",
    "input_payment_split": "AP input payment splits",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip().removesuffix(".0")


def _plain_text(value: Any) -> str:
    return str(value or "").strip()


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(Decimal(str(value)))


def _optional_float(value: Any, *, places: int = 2) -> float | None:
    if value in (None, ""):
        return None
    return round(float(Decimal(str(value))), places)


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return round(float(Decimal(str(value))), 2)


def _date_text(value: Any) -> str | None:
    if value in (None, "", 0):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = _text(value)
    for pattern in ("%Y%m%d", "%m%d%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, pattern).date().isoformat()
        except ValueError:
            continue
    return raw or None


def _canonical_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


class ERPEvidenceService:
    def __init__(
        self,
        *,
        repository: ERPEvidenceRepository = erp_evidence_repository,
        customer_source=customer_service,
        ap_source=accounts_payable_service,
        clock=_now,
    ) -> None:
        self.repository = repository
        self.customer_source = customer_source
        self.ap_source = ap_source
        self.clock = clock

    def status(self) -> ERPEvidenceGatewayStatus:
        return ERPEvidenceGatewayStatus(
            contract_version=CONTRACT_VERSION,
            service="Read-Only ERP Evidence Gateway",
            supported_queries=[
                "credit_customer_open_ar_and_cunument_group",
                "accounts_payable_confirmed_mapping_readiness",
                "accounts_payable_invoice_evidence_by_local_identity",
                "accounts_payable_bounded_vendor_and_exact_invoice_discovery",
                "accounts_payable_invoice_evidence_by_direct_erp_identity",
                "accounts_payable_deterministic_vendor_spend_questions",
            ],
            unavailable_actions=[
                "ERP mutation",
                "financial approval or decision",
                "automatic AP source mapping or status-code interpretation",
                "payment, posting, order, hold, or release execution",
            ],
            metadata={
                "credit_sources": ["TMCUST", "TMAROP"],
                "ap_sources": ["PMVEND", "PMHD", "PMDT", "PMGLDS", "PTHD", "PTDT", "PTPY"],
                "ap_mapping_state": "confirmed_source_record_with_runtime_schema_check",
                "ap_discovery": "bounded_candidates_with_human_selection",
                "ap_vendor_spend": "fixed_intents_and_parameterized_bounded_aggregates",
            },
        )

    def credit_customer(
        self,
        customer_number: int,
        *,
        open_item_limit: int,
    ) -> CreditERPEvidenceResponse | None:
        generated_at = self.clock()
        shared = self.customer_source.summary(customer_number)
        source_row = self.repository.get_credit_customer(customer_number)
        if shared is None or source_row is None:
            return None

        rows, open_ar_complete = self.repository.get_open_ar(
            customer_number,
            limit=open_item_limit,
        )
        open_items = [self._open_item(row) for row in rows]
        retrieved_open_amount = round(sum(item.open_amount for item in open_items), 2)
        master_balance = _number(source_row.get("CUBALANCE"))
        reconciliation = (
            round(master_balance - retrieved_open_amount, 2)
            if open_ar_complete
            else None
        )

        enterprise_number = _text(source_row.get("CUNUMENT")) or None
        related_rows, related_complete = self.repository.get_related_accounts(
            customer_number,
            enterprise_number,
        )
        related_accounts = [
            self._related_account(
                row,
                selected_customer=customer_number,
                enterprise_number=enterprise_number,
            )
            for row in related_rows
        ]
        related_status = "available" if related_complete else "partial"
        if not enterprise_number or enterprise_number == "0":
            related_status = "partial"

        credit = shared["credit"]
        activity = shared["activity"]
        current = CreditCurrentEvidence(
            credit_limit=_number(credit.get("credit_limit")),
            balance=master_balance,
            erp_on_order_aggregate=_number(credit.get("raw_on_order")),
            partial_exposure=_number(credit.get("total_exposure")),
            partial_available_credit=_number(credit.get("available_credit")),
            terms_code=_text(credit.get("terms_code")),
            terms_description=_text(credit.get("terms_description")),
            last_payment_amount=(
                _number(activity.get("last_payment_amount"))
                if activity.get("last_payment_amount") not in (None, "")
                else None
            ),
            last_payment_date=_date_text(activity.get("last_payment_date")),
        )
        source_schema = os.getenv("MYSQL_DATABASE", "configured_schema")
        source_refs = [
            EvidenceSourceReference(
                source_system="MaddenCo ERP",
                source_schema=source_schema,
                source_object="TMCUST",
                retrieved_at=generated_at,
                contract_version=CONTRACT_VERSION,
            ),
            EvidenceSourceReference(
                source_system="MaddenCo ERP",
                source_schema=source_schema,
                source_object="TMAROP",
                retrieved_at=generated_at,
                contract_version=CONTRACT_VERSION,
            ),
        ]
        coverage = self._credit_coverage(
            generated_at=generated_at,
            open_ar_count=len(open_items),
            open_ar_complete=open_ar_complete,
            related_count=len(related_accounts),
            related_complete=related_complete,
            enterprise_number=enterprise_number,
        )
        open_ar = CreditOpenARCollection(
            status="available" if open_ar_complete else "partial",
            items=open_items,
            retrieved_count=len(open_items),
            row_limit=max(1, min(open_item_limit, self.repository.OPEN_AR_MAX_LIMIT)),
            complete=open_ar_complete,
            retrieved_signed_open_amount=retrieved_open_amount,
            customer_master_balance=master_balance,
            reconciliation_difference=reconciliation,
            explanation=(
                "All current nonzero TMAROP rows fit inside the bounded read."
                if open_ar_complete
                else "The current Open A/R result exceeded the bounded row limit; totals describe only retrieved rows."
            ),
        )
        related = RelatedAccountCollection(
            status=related_status,
            relationship_basis="TMCUST.CUNUMENT",
            group_scope="verified_cunument_accounts_only",
            enterprise_number=(
                enterprise_number
                if enterprise_number and enterprise_number != "0"
                else None
            ),
            accounts=related_accounts,
            retrieved_count=len(related_accounts),
            complete=related_complete,
            partial_group_credit_limit=(
                round(sum(item.credit_limit for item in related_accounts), 2)
                if related_complete
                else None
            ),
            partial_group_exposure=(
                round(sum(item.partial_exposure for item in related_accounts), 2)
                if related_complete
                else None
            ),
            explanation=(
                "Accounts are linked only by the current CUNUMENT relationship. This is not proof of every guarantor, parent, or related entity."
            ),
        )
        governance = EvidenceGovernance(
            source_authority="MaddenCo remains authoritative for source facts; ETOP provides a current read-only evidence projection.",
            statements=[
                "Open-item and relationship evidence is current only at the recorded retrieval time.",
                "CUNUMENT grouping is source-backed relationship evidence, not complete enterprise exposure.",
                "No recommendation, Decision, approval, order action, or ERP mutation follows this query.",
            ],
        )
        warnings = [
            item.explanation
            for item in coverage
            if item.status in {"partial", "unavailable", "degraded"}
        ]
        evidence_without_hash = {
            "contract_version": CONTRACT_VERSION,
            "generated_at": generated_at,
            "customer_number": customer_number,
            "customer_name": _text(shared.get("customer_name")),
            "current": current.model_dump(),
            "open_ar": open_ar.model_dump(),
            "related_accounts": related.model_dump(),
            "coverage": [item.model_dump() for item in coverage],
            "source_references": [item.model_dump() for item in source_refs],
            "governance": governance.model_dump(),
            "warnings": warnings,
        }
        return CreditERPEvidenceResponse(
            **evidence_without_hash,
            evidence_sha256=_canonical_hash(evidence_without_hash),
        )

    def ap_mapping_readiness(self) -> APMappingReadinessResponse:
        generated_at = self.clock()
        source_schema = os.getenv("MYSQL_DATABASE", "configured_schema")
        warnings: list[str] = []
        try:
            candidates, column_count, complete = (
                self.repository.inspect_confirmed_ap_mapping()
            )
            catalog_status = "available" if complete else "partial"
            if not complete:
                warnings.append(
                    "The bounded runtime schema check reached its column limit; validation is incomplete."
                )
        except Exception as exc:
            candidates = {}
            for category, mapping in self.repository.AP_SOURCE_MAPPING.items():
                required = list(mapping["required_fields"])
                candidates[category] = [{
                    "category": category,
                    "table_name": mapping["table_name"],
                    "required_fields_matched": [],
                    "missing_fields": required,
                    "matched_columns": {},
                    "evidence_columns": mapping["evidence_columns"],
                    "selection_state": "confirmed_source_record",
                    "source_rows_read": False,
                }]
            column_count = 0
            complete = False
            catalog_status = "degraded"
            warnings.append(f"ERP runtime schema validation is unavailable: {exc}")

        categories: list[APMappingCategory] = []
        for key, required in self.repository.AP_CATEGORY_REQUIREMENTS.items():
            category_candidates = candidates.get(key, [])
            has_complete_candidate = any(
                not item["missing_fields"] for item in category_candidates
            )
            status = (
                "degraded"
                if catalog_status == "degraded"
                else "available"
                if has_complete_candidate
                else "partial"
            )
            explanation = (
                "The Product Owner supplied this source mapping and the required columns are present in the runtime schema."
                if has_complete_candidate
                else "The Product Owner supplied this source mapping, but one or more required columns were not verified in the runtime schema."
            )
            categories.append(
                APMappingCategory(
                    key=key,
                    label=AP_CATEGORY_LABELS[key],
                    status=status,
                    required_fields=list(required),
                    candidates=category_candidates,
                    explanation=explanation,
                )
            )

        return APMappingReadinessResponse(
            contract_version=CONTRACT_VERSION,
            generated_at=generated_at,
            source_schema=source_schema,
            schema_catalog_status=catalog_status,
            catalog_complete=complete,
            inspected_column_count=column_count,
            categories=categories,
            governance=EvidenceGovernance(
                source_authority="The supplied DTA273 table/column record defines the AP source mapping; MaddenCo remains authoritative for row values.",
                statements=[
                    "Readiness validation reads INFORMATION_SCHEMA column names only and never reads financial rows.",
                    "The mapping confirms raw fields, not undocumented status-code meanings or open/paid semantics.",
                    "No approval, payment, posting, export, automatic decision, or ERP mutation is permitted.",
                ],
            ),
            next_required_action=(
                "Search PMVEND by vendor name/number or PMHD by exact invoice number, select the intended vendor/invoice identity, and separately confirm status-code meanings before labeling workflow state."
            ),
            warnings=warnings,
        )

    def search_ap_invoices(
        self,
        *,
        vendor_query: str | None,
        invoice_number: str | None,
        limit: int,
    ) -> APInvoiceSearchResponse:
        generated_at = self.clock()
        normalized_vendor = _plain_text(vendor_query) or None
        normalized_invoice = _plain_text(invoice_number) or None
        if normalized_vendor is None and normalized_invoice is None:
            raise ValueError(
                "Enter a vendor name/number, an exact invoice number, or both."
            )
        if (
            normalized_vendor is not None
            and not normalized_vendor.isdigit()
            and len(normalized_vendor) < 2
        ):
            raise ValueError("Vendor-name search requires at least 2 characters.")

        bounded_limit = max(
            1,
            min(limit, self.repository.AP_INVOICE_SEARCH_LIMIT),
        )
        warnings: list[str] = []
        vendor_rows: list[dict[str, Any]] = []
        vendor_complete = True
        vendor_query_ok = True
        if normalized_vendor is not None:
            try:
                vendor_rows, vendor_complete = self.repository.search_ap_vendors(
                    normalized_vendor,
                    limit=self.repository.AP_VENDOR_SEARCH_LIMIT,
                )
            except Exception as exc:
                vendor_complete = False
                vendor_query_ok = False
                warnings.append(f"Vendor discovery is unavailable: {exc}")

        vendor_candidates = [
            APVendorSearchCandidate(
                vendor_number=_text(row.get("vendor_number")),
                vendor_name=_optional_text(row.get("vendor_name")),
                sort_name=_optional_text(row.get("sort_name")),
                match_basis=[
                    "exact_vendor_number"
                    if normalized_vendor and normalized_vendor.isdigit()
                    else "vendor_name_contains"
                ],
            )
            for row in vendor_rows
        ]
        vendor_numbers = [
            int(item.vendor_number)
            for item in vendor_candidates
            if item.vendor_number.isdigit()
        ]
        if normalized_vendor and normalized_vendor.isdigit():
            exact_vendor_number = int(normalized_vendor)
            if exact_vendor_number not in vendor_numbers:
                vendor_numbers.append(exact_vendor_number)

        invoice_rows: list[dict[str, Any]] = []
        invoice_complete = True
        can_query_invoices = (
            normalized_vendor is None
            or bool(vendor_numbers)
        ) and (
            vendor_query_ok
            or bool(normalized_vendor and normalized_vendor.isdigit())
        )
        if can_query_invoices:
            try:
                invoice_rows, invoice_complete = (
                    self.repository.search_ap_posted_invoice_identities(
                        vendor_numbers=vendor_numbers or None,
                        invoice_number=normalized_invoice,
                        limit=bounded_limit,
                    )
                )
            except Exception as exc:
                invoice_complete = False
                warnings.append(f"Posted invoice discovery is unavailable: {exc}")

        invoice_candidates = [
            APInvoiceSearchCandidate(
                vendor_number=_text(row.get("vendor_number")),
                vendor_name=_optional_text(row.get("vendor_name")),
                invoice_number=_plain_text(row.get("invoice_number")),
                posted_header_row_count=int(row.get("posted_header_row_count") or 0),
                latest_invoice_date=_date_text(row.get("latest_invoice_date")),
                latest_due_date=_date_text(row.get("latest_due_date")),
            )
            for row in invoice_rows
            if _plain_text(row.get("invoice_number"))
        ]
        if not vendor_complete:
            warnings.append(
                f"Vendor candidates reached the {self.repository.AP_VENDOR_SEARCH_LIMIT}-row safety limit or could not be completed."
            )
        if not invoice_complete:
            warnings.append(
                f"Invoice candidates reached the {bounded_limit}-row safety limit or could not be completed."
            )

        source_schema = os.getenv("MYSQL_DATABASE", "configured_schema")
        source_objects: list[str] = []
        if normalized_vendor is not None:
            source_objects.append("PMVEND")
        if can_query_invoices:
            source_objects.append("PMHD")
        sources = [
            EvidenceSourceReference(
                source_system="MaddenCo ERP",
                source_schema=source_schema,
                source_object=source_object,
                retrieved_at=generated_at,
                contract_version=CONTRACT_VERSION,
            )
            for source_object in source_objects
        ]
        governance = EvidenceGovernance(
            source_authority="MaddenCo PMVEND and PMHD remain authoritative; this result is bounded discovery evidence only.",
            statements=[
                "Vendor-name discovery returns bounded candidates for human selection; it does not resolve vendor identity automatically.",
                "Invoice-number discovery uses exact equality and returns every bounded vendor/invoice identity found.",
                "Selecting a candidate retrieves evidence but does not match, approve, pay, post, export, or change an ERP record.",
            ],
        )
        sensitive_fields_excluded = self._ap_sensitive_fields_excluded()
        query = APInvoiceSearchQuery(
            vendor_query=normalized_vendor,
            invoice_number=normalized_invoice,
            row_limit=bounded_limit,
        )
        payload = {
            "contract_version": CONTRACT_VERSION,
            "generated_at": generated_at,
            "query": query.model_dump(),
            "vendor_candidates": [item.model_dump() for item in vendor_candidates],
            "invoice_candidates": [item.model_dump() for item in invoice_candidates],
            "vendor_candidate_complete": vendor_complete,
            "invoice_candidate_complete": invoice_complete,
            "source_references": [item.model_dump() for item in sources],
            "governance": governance.model_dump(),
            "sensitive_fields_excluded": sensitive_fields_excluded,
            "warnings": warnings,
        }
        return APInvoiceSearchResponse(
            **payload,
            evidence_sha256=_canonical_hash(payload),
        )

    def ap_invoice(self, ap_invoice_id: str) -> APERPEvidenceResponse:
        generated_at = self.clock()
        local_model = self.ap_source.get_invoice(ap_invoice_id)
        local = (
            local_model.model_dump()
            if hasattr(local_model, "model_dump")
            else dict(local_model)
        )
        local_identity = APLocalInvoiceIdentity(
            ap_invoice_id=ap_invoice_id,
            vendor_number=_optional_text(local.get("vendor_number")),
            vendor_name=_optional_text(local.get("vendor_name")),
            invoice_number=_plain_text(local.get("invoice_number")) or None,
            invoice_date=_date_text(local.get("invoice_date")),
            due_date=_date_text(local.get("due_date")),
            purchase_order_number=_plain_text(local.get("purchase_order_number")) or None,
            total_amount=_optional_float(local.get("total_amount")),
            source_evidence_sha256=_plain_text(local.get("source_evidence_sha256")),
        )
        vendor_text = local_identity.vendor_number or ""
        invoice_number = local_identity.invoice_number or ""
        if not vendor_text.isdigit() or not invoice_number:
            warnings: list[str] = []
            missing = []
            if not vendor_text.isdigit():
                missing.append("a numeric vendor number")
            if not invoice_number:
                missing.append("an invoice number")
            warnings.append(
                "ERP evidence was not queried because the local invoice lacks "
                + " and ".join(missing)
                + "."
            )
            return self._empty_ap_invoice_response(
                generated_at=generated_at,
                lookup_identity=APERPInvoiceLookupIdentity(
                    lookup_origin="local_imported_invoice",
                    vendor_number=vendor_text,
                    invoice_number=invoice_number,
                    local_ap_invoice_id=ap_invoice_id,
                ),
                local_identity=local_identity,
                warnings=warnings,
                sensitive_fields_excluded=self._ap_sensitive_fields_excluded(),
            )
        return self._ap_invoice_by_identity(
            generated_at=generated_at,
            lookup_identity=APERPInvoiceLookupIdentity(
                lookup_origin="local_imported_invoice",
                vendor_number=vendor_text,
                invoice_number=invoice_number,
                local_ap_invoice_id=ap_invoice_id,
            ),
            local_identity=local_identity,
        )

    def ap_invoice_by_erp_identity(
        self,
        *,
        vendor_number: int,
        invoice_number: str,
    ) -> APERPEvidenceResponse:
        normalized_invoice = _plain_text(invoice_number)
        if not normalized_invoice:
            raise ValueError("An exact invoice number is required.")
        return self._ap_invoice_by_identity(
            generated_at=self.clock(),
            lookup_identity=APERPInvoiceLookupIdentity(
                lookup_origin="direct_erp_search",
                vendor_number=str(vendor_number),
                invoice_number=normalized_invoice,
            ),
            local_identity=None,
        )

    def _ap_invoice_by_identity(
        self,
        *,
        generated_at: str,
        lookup_identity: APERPInvoiceLookupIdentity,
        local_identity: APLocalInvoiceIdentity | None,
    ) -> APERPEvidenceResponse:
        warnings: list[str] = []
        sensitive_fields_excluded = self._ap_sensitive_fields_excluded()
        vendor_text = lookup_identity.vendor_number
        invoice_number = lookup_identity.invoice_number
        vendor_number = int(vendor_text)
        query_warnings: list[str] = []

        def bounded_query(label: str, loader):
            try:
                rows, complete = loader(vendor_number, invoice_number)
                return rows, complete, True
            except Exception as exc:
                query_warnings.append(f"{label} query is unavailable: {exc}")
                return [], False, False

        try:
            vendor_row = self.repository.get_ap_vendor(vendor_number)
            vendor_query_ok = True
        except Exception as exc:
            vendor_row = None
            vendor_query_ok = False
            query_warnings.append(f"Vendor master query is unavailable: {exc}")

        posted_headers_raw, posted_headers_complete, posted_headers_ok = bounded_query(
            "Posted invoice header",
            self.repository.get_ap_posted_headers,
        )
        posted_details_raw, posted_details_complete, posted_details_ok = bounded_query(
            "Posted invoice detail",
            self.repository.get_ap_posted_details,
        )
        gl_raw, gl_complete, gl_ok = bounded_query(
            "AP GL distribution",
            self.repository.get_ap_gl_distributions,
        )
        input_headers_raw, input_headers_complete, input_headers_ok = bounded_query(
            "AP invoice input header",
            self.repository.get_ap_input_headers,
        )
        input_details_raw, input_details_complete, input_details_ok = bounded_query(
            "AP invoice input detail",
            self.repository.get_ap_input_details,
        )
        payment_splits_raw, payment_splits_complete, payment_splits_ok = bounded_query(
            "AP input payment split",
            self.repository.get_ap_input_payment_splits,
        )
        warnings.extend(query_warnings)

        vendor = self._ap_vendor(
            vendor_number=vendor_text,
            row=vendor_row,
            query_ok=vendor_query_ok,
        )
        posted_headers = [self._ap_posted_header(row) for row in posted_headers_raw]
        posted_details = [self._ap_detail(row) for row in posted_details_raw]
        gl_account_pairs = [
            (int(row["gl_division"]), int(row["gl_account"]))
            for row in gl_raw
            if row.get("gl_division") is not None and row.get("gl_account") is not None
        ]
        try:
            gl_account_descriptions = self.repository.get_gl_account_descriptions(
                gl_account_pairs
            )
        except Exception:
            gl_account_descriptions = {}
        gl_distributions = [
            self._ap_gl_distribution(row, gl_account_descriptions)
            for row in gl_raw
        ]
        input_headers = [self._ap_input_header(row) for row in input_headers_raw]
        input_details = [self._ap_detail(row) for row in input_details_raw]
        payment_splits = [self._ap_payment_split(row) for row in payment_splits_raw]

        collections = {
            "posted_header_collection": self._ap_collection(
                count=len(posted_headers),
                limit=self.repository.AP_HEADER_LIMIT,
                complete=posted_headers_complete,
                query_ok=posted_headers_ok,
                label="PMHD posted invoice header",
            ),
            "posted_detail_collection": self._ap_collection(
                count=len(posted_details),
                limit=self.repository.AP_DETAIL_LIMIT,
                complete=posted_details_complete,
                query_ok=posted_details_ok,
                label="PMDT posted invoice detail",
            ),
            "gl_distribution_collection": self._ap_collection(
                count=len(gl_distributions),
                limit=self.repository.AP_GL_LIMIT,
                complete=gl_complete,
                query_ok=gl_ok,
                label="PMGLDS AP GL distribution",
            ),
            "input_header_collection": self._ap_collection(
                count=len(input_headers),
                limit=self.repository.AP_HEADER_LIMIT,
                complete=input_headers_complete,
                query_ok=input_headers_ok,
                label="PTHD AP invoice input header",
            ),
            "input_detail_collection": self._ap_collection(
                count=len(input_details),
                limit=self.repository.AP_INPUT_LIMIT,
                complete=input_details_complete,
                query_ok=input_details_ok,
                label="PTDT AP invoice input detail",
            ),
            "input_payment_collection": self._ap_collection(
                count=len(payment_splits),
                limit=self.repository.AP_HEADER_LIMIT,
                complete=payment_splits_complete,
                query_ok=payment_splits_ok,
                label="PTPY AP input payment split",
            ),
        }
        coverage = self._ap_coverage(
            generated_at=generated_at,
            vendor=vendor,
            posted_headers=collections["posted_header_collection"],
            posted_details=collections["posted_detail_collection"],
            gl_distributions=collections["gl_distribution_collection"],
            input_headers=collections["input_header_collection"],
            input_details=collections["input_detail_collection"],
            input_payments=collections["input_payment_collection"],
        )
        source_schema = os.getenv("MYSQL_DATABASE", "configured_schema")
        source_objects = ["PMVEND", "PMHD", "PMDT", "PMGLDS", "PTHD", "PTDT", "PTPY"]
        sources = [
            EvidenceSourceReference(
                source_system="MaddenCo ERP",
                source_schema=source_schema,
                source_object=source_object,
                retrieved_at=generated_at,
                contract_version=CONTRACT_VERSION,
            )
            for source_object in source_objects
        ]
        governance = EvidenceGovernance(
            source_authority="MaddenCo remains authoritative for AP row values; the supplied DTA273 mapping defines the selected fields.",
            statements=[
                (
                    "Lookup identity came from an imported ETOP invoice and was verified through exact vendor/invoice queries."
                    if lookup_identity.lookup_origin == "local_imported_invoice"
                    else "Lookup identity was selected by a human from bounded ERP discovery and was retrieved through exact vendor/invoice queries."
                ),
                "PMHD is presented as posted invoice history and PTHD/PTPY as input evidence; undocumented codes are shown raw and are not interpreted.",
                "PO/receiver values are references carried on invoice detail, not proof of a completed three-way match.",
                "No approval, payment, posting, export, recommendation, automatic selection, or ERP mutation follows this query.",
            ],
        )
        evidence_without_hash = {
            "contract_version": CONTRACT_VERSION,
            "generated_at": generated_at,
            "lookup_identity": lookup_identity.model_dump(),
            "local_invoice": local_identity.model_dump() if local_identity else None,
            "vendor_master": vendor.model_dump(),
            "posted_headers": [item.model_dump() for item in posted_headers],
            "posted_details": [item.model_dump() for item in posted_details],
            "gl_distributions": [item.model_dump() for item in gl_distributions],
            "input_headers": [item.model_dump() for item in input_headers],
            "input_details": [item.model_dump() for item in input_details],
            "input_payment_splits": [item.model_dump() for item in payment_splits],
            **{key: value.model_dump() for key, value in collections.items()},
            "coverage": [item.model_dump() for item in coverage],
            "source_references": [item.model_dump() for item in sources],
            "governance": governance.model_dump(),
            "sensitive_fields_excluded": sensitive_fields_excluded,
            "warnings": warnings,
        }
        return APERPEvidenceResponse(
            **evidence_without_hash,
            evidence_sha256=_canonical_hash(evidence_without_hash),
        )

    def _empty_ap_invoice_response(
        self,
        *,
        generated_at: str,
        lookup_identity: APERPInvoiceLookupIdentity,
        local_identity: APLocalInvoiceIdentity | None,
        warnings: list[str],
        sensitive_fields_excluded: list[str],
    ) -> APERPEvidenceResponse:
        unavailable = APBoundedCollection(
            status="unavailable",
            retrieved_count=0,
            row_limit=0,
            complete=False,
            explanation="The source was not queried because the exact ERP lookup identity is incomplete.",
        )
        vendor = APVendorEvidence(
            status="unavailable",
            vendor_number=lookup_identity.vendor_number,
            vendor_name=None,
            sort_name=None,
            vendor_type_code=None,
            delete_code=None,
            terms_code=None,
            po_required_code=None,
            no_ap_from_receipt_code=None,
            default_gl_division=None,
            default_gl_department=None,
            default_gl_account=None,
            last_paid_date=None,
            last_paid_amount=None,
            explanation="Vendor master evidence requires a numeric local vendor number.",
        )
        coverage = [
            EvidenceCoverageItem(
                key="erp_identity",
                label="Exact ERP invoice lookup identity",
                status="unavailable",
                complete=False,
                explanation="A numeric vendor number and invoice number are required before any ERP row is read.",
            )
        ]
        governance = EvidenceGovernance(
            source_authority="The local imported invoice remains the only evidence returned because no exact ERP identity was available.",
            statements=[
                "No discovery candidate was automatically selected as the invoice identity.",
                "No approval, payment, posting, export, recommendation, or ERP mutation occurred.",
            ],
        )
        payload = {
            "contract_version": CONTRACT_VERSION,
            "generated_at": generated_at,
            "lookup_identity": lookup_identity.model_dump(),
            "local_invoice": local_identity.model_dump() if local_identity else None,
            "vendor_master": vendor.model_dump(),
            "posted_headers": [],
            "posted_header_collection": unavailable.model_dump(),
            "posted_details": [],
            "posted_detail_collection": unavailable.model_dump(),
            "gl_distributions": [],
            "gl_distribution_collection": unavailable.model_dump(),
            "input_headers": [],
            "input_header_collection": unavailable.model_dump(),
            "input_details": [],
            "input_detail_collection": unavailable.model_dump(),
            "input_payment_splits": [],
            "input_payment_collection": unavailable.model_dump(),
            "coverage": [item.model_dump() for item in coverage],
            "source_references": [],
            "governance": governance.model_dump(),
            "sensitive_fields_excluded": sensitive_fields_excluded,
            "warnings": warnings,
        }
        return APERPEvidenceResponse(
            **payload,
            evidence_sha256=_canonical_hash(payload),
        )

    @staticmethod
    def _ap_sensitive_fields_excluded() -> list[str]:
        return [
            "PMVEND.PVACCBNK (bank account number)",
            "PMVEND.PVROUBNK (bank routing number)",
            "PMVEND.PVIDFED (federal tax identifier)",
            "PMVEND contact, phone, email, and address fields",
        ]

    @staticmethod
    def _ap_vendor(
        *,
        vendor_number: str,
        row: dict[str, Any] | None,
        query_ok: bool,
    ) -> APVendorEvidence:
        if row is None:
            return APVendorEvidence(
                status="unavailable" if query_ok else "degraded",
                vendor_number=vendor_number,
                vendor_name=None,
                sort_name=None,
                vendor_type_code=None,
                delete_code=None,
                terms_code=None,
                po_required_code=None,
                no_ap_from_receipt_code=None,
                default_gl_division=None,
                default_gl_department=None,
                default_gl_account=None,
                last_paid_date=None,
                last_paid_amount=None,
                explanation=(
                    "The exact vendor number was queried and no PMVEND row was returned."
                    if query_ok
                    else "The PMVEND query could not be completed."
                ),
            )
        return APVendorEvidence(
            status="available",
            vendor_number=_text(row.get("vendor_number")),
            vendor_name=_optional_text(row.get("vendor_name")),
            sort_name=_optional_text(row.get("sort_name")),
            vendor_type_code=_optional_text(row.get("vendor_type_code")),
            delete_code=_optional_text(row.get("delete_code")),
            terms_code=_optional_text(row.get("terms_code")),
            po_required_code=_optional_text(row.get("po_required_code")),
            no_ap_from_receipt_code=_optional_text(row.get("no_ap_from_receipt_code")),
            default_gl_division=_optional_text(row.get("default_gl_division")),
            default_gl_department=_optional_text(row.get("default_gl_department")),
            default_gl_account=_optional_text(row.get("default_gl_account")),
            last_paid_date=_date_text(row.get("last_paid_date")),
            last_paid_amount=_optional_float(row.get("last_paid_amount")),
            explanation="A safe, minimized PMVEND projection was retrieved; bank, tax-ID, contact, and address fields were not selected.",
        )

    @staticmethod
    def _ap_posted_header(row: dict[str, Any]) -> APPostedInvoiceHeaderEvidence:
        return APPostedInvoiceHeaderEvidence(
            vendor_number=_text(row.get("vendor_number")),
            invoice_number=_plain_text(row.get("invoice_number")),
            payment_number=_optional_int(row.get("payment_number")),
            invoice_amount=_number(row.get("invoice_amount")),
            discount_amount=_number(row.get("discount_amount")),
            invoice_description=_optional_text(row.get("invoice_description")),
            invoice_date=_date_text(row.get("invoice_date")),
            due_date=_date_text(row.get("due_date")),
            created_date=_date_text(row.get("created_date")),
            changed_date=_date_text(row.get("changed_date")),
            check_number=_optional_text(row.get("check_number")),
            check_date=_date_text(row.get("check_date")),
            hold_flag=_optional_text(row.get("hold_flag")),
            selection_code=_optional_text(row.get("selection_code")),
            discount_taken_code=_optional_text(row.get("discount_taken_code")),
            gl_reference=_optional_text(row.get("gl_reference")),
            check_gl_reference=_optional_text(row.get("check_gl_reference")),
            void_gl_reference=_optional_text(row.get("void_gl_reference")),
            void_check_gl_reference=_optional_text(row.get("void_check_gl_reference")),
            accounting_period=_optional_int(row.get("accounting_period")),
            accounting_year=_optional_int(row.get("accounting_year")),
        )

    @staticmethod
    def _ap_detail(row: dict[str, Any]) -> APInvoiceDetailEvidence:
        return APInvoiceDetailEvidence(
            sequence_number=_optional_int(row.get("sequence_number")),
            line_description=_optional_text(row.get("line_description")),
            line_amount=_number(row.get("line_amount")),
            quantity=_number(row.get("quantity")),
            gl_division=_optional_text(row.get("gl_division")),
            gl_department=_optional_text(row.get("gl_department")),
            gl_account=_optional_text(row.get("gl_account")),
            po_receiver_reference=_optional_text(row.get("po_receiver_reference")),
            customer_number=_optional_text(row.get("customer_number")),
            job_number=_optional_text(row.get("job_number")),
        )

    @staticmethod
    def _ap_gl_distribution(
        row: dict[str, Any],
        account_descriptions: dict[tuple[str, str], str] | None = None,
    ) -> APGLDistributionEvidence:
        gl_division = _optional_text(row.get("gl_division"))
        gl_account = _optional_text(row.get("gl_account"))
        account_description = (
            (account_descriptions or {}).get((gl_division or "", gl_account or ""))
            if gl_division and gl_account
            else None
        )
        return APGLDistributionEvidence(
            sequence_number=_optional_text(row.get("sequence_number")),
            payment_number=_optional_int(row.get("payment_number")),
            invoice_amount=_number(row.get("invoice_amount")),
            quantity=_number(row.get("quantity")),
            description=_optional_text(row.get("description")),
            invoice_date=_date_text(row.get("invoice_date")),
            gl_division=gl_division,
            gl_department=_optional_text(row.get("gl_department")),
            gl_account=gl_account,
            gl_account_description=account_description,
            accounting_period=_optional_int(row.get("accounting_period")),
            accounting_year=_optional_int(row.get("accounting_year")),
            program_code=_optional_text(row.get("program_code")),
        )

    @staticmethod
    def _ap_input_header(row: dict[str, Any]) -> APInputInvoiceHeaderEvidence:
        return APInputInvoiceHeaderEvidence(
            vendor_number=_text(row.get("vendor_number")),
            invoice_number=_plain_text(row.get("invoice_number")),
            invoice_amount=_number(row.get("invoice_amount")),
            discount_amount=_number(row.get("discount_amount")),
            discountable_amount=_number(row.get("discountable_amount")),
            invoice_description=_optional_text(row.get("invoice_description")),
            invoice_date=_date_text(row.get("invoice_date")),
            due_date=_date_text(row.get("due_date")),
            created_date=_date_text(row.get("created_date")),
            changed_date=_date_text(row.get("changed_date")),
            raw_status_code=_optional_text(row.get("raw_status_code")),
            payment_count=_optional_int(row.get("payment_count")),
            accounting_period=_optional_int(row.get("accounting_period")),
            accounting_year=_optional_int(row.get("accounting_year")),
        )

    @staticmethod
    def _ap_payment_split(row: dict[str, Any]) -> APInputPaymentSplitEvidence:
        return APInputPaymentSplitEvidence(
            sequence_number=_optional_int(row.get("sequence_number")),
            payment_amount=_number(row.get("payment_amount")),
            discount_amount=_number(row.get("discount_amount")),
            discountable_amount=_number(row.get("discountable_amount")),
            discount_percent=_optional_float(row.get("discount_percent"), places=4) or 0.0,
            due_date=_date_text(row.get("due_date")),
        )

    @staticmethod
    def _ap_collection(
        *,
        count: int,
        limit: int,
        complete: bool,
        query_ok: bool,
        label: str,
    ) -> APBoundedCollection:
        if not query_ok:
            return APBoundedCollection(
                status="degraded",
                retrieved_count=0,
                row_limit=limit,
                complete=False,
                explanation=f"The {label} query could not be completed.",
            )
        return APBoundedCollection(
            status="available" if complete else "partial",
            retrieved_count=count,
            row_limit=limit,
            complete=complete,
            explanation=(
                f"The exact vendor/invoice {label} query completed with {count} row(s)."
                if complete
                else f"The {label} result exceeded the {limit}-row safety limit; retrieved rows are incomplete."
            ),
        )

    @staticmethod
    def _ap_coverage(
        *,
        generated_at: str,
        vendor: APVendorEvidence,
        posted_headers: APBoundedCollection,
        posted_details: APBoundedCollection,
        gl_distributions: APBoundedCollection,
        input_headers: APBoundedCollection,
        input_details: APBoundedCollection,
        input_payments: APBoundedCollection,
    ) -> list[EvidenceCoverageItem]:
        return [
            EvidenceCoverageItem(
                key="vendor_master",
                label="Vendor master",
                status=vendor.status,
                source="MaddenCo PMVEND",
                as_of=generated_at,
                record_count=1 if vendor.status == "available" else 0,
                complete=vendor.status == "available",
                explanation=vendor.explanation,
            ),
            EvidenceCoverageItem(
                key="posted_invoice_history",
                label="Posted invoice header history",
                status=posted_headers.status,
                source="MaddenCo PMHD",
                as_of=generated_at,
                record_count=posted_headers.retrieved_count,
                complete=posted_headers.complete,
                explanation="PMHD rows are source-described as AP invoice headers; no undocumented code is interpreted as open or paid.",
            ),
            EvidenceCoverageItem(
                key="invoice_detail_po_receiver",
                label="Posted detail and PO/receiver references",
                status=posted_details.status,
                source="MaddenCo PMDT",
                as_of=generated_at,
                record_count=posted_details.retrieved_count,
                complete=posted_details.complete,
                explanation="PMDNBPORV is shown as a PO/receiver reference carried on detail, not proof of purchase-order or receipt validation.",
            ),
            EvidenceCoverageItem(
                key="gl_distribution",
                label="AP GL distribution",
                status=gl_distributions.status,
                source="MaddenCo PMGLDS",
                as_of=generated_at,
                record_count=gl_distributions.retrieved_count,
                complete=gl_distributions.complete,
                explanation="Bounded AP GL distribution rows are available without posting or reconciliation authority.",
            ),
            EvidenceCoverageItem(
                key="invoice_input",
                label="AP invoice input header and detail",
                status=(
                    "degraded"
                    if "degraded" in {input_headers.status, input_details.status}
                    else "partial"
                    if "partial" in {input_headers.status, input_details.status}
                    else "available"
                ),
                source="MaddenCo PTHD/PTDT",
                as_of=generated_at,
                record_count=input_headers.retrieved_count + input_details.retrieved_count,
                complete=input_headers.complete and input_details.complete,
                explanation="Input rows and raw PTHSTAT are shown without inferring approval, posting, or workflow state.",
            ),
            EvidenceCoverageItem(
                key="input_payment_split",
                label="AP input payment split",
                status=input_payments.status,
                source="MaddenCo PTPY",
                as_of=generated_at,
                record_count=input_payments.retrieved_count,
                complete=input_payments.complete,
                explanation="PTPY describes input payment splits and due dates; it is not treated as proof that a payment executed.",
            ),
            EvidenceCoverageItem(
                key="executed_payment_ledger",
                label="Executed payment ledger",
                status="unavailable",
                explanation="The supplied mapping does not identify a separate authoritative executed-payment table or documented payment-status semantics.",
            ),
            EvidenceCoverageItem(
                key="three_way_match",
                label="PO, receipt, and invoice three-way match",
                status="unavailable",
                explanation="The supplied mapping exposes PO/receiver references but not authoritative PO and receipt records with governed matching rules.",
            ),
        ]

    @staticmethod
    def _open_item(row: dict[str, Any]) -> CreditOpenItem:
        raw_open_amount = _number(row.get("open_amount"))
        debit_credit = _text(row.get("debit_credit")).upper()
        signed_open_amount = (
            -abs(raw_open_amount)
            if debit_credit in {"C", "CR", "CREDIT"}
            else abs(raw_open_amount)
        )
        due_date_text = _date_text(row.get("due_date"))
        try:
            due_date = date.fromisoformat(due_date_text) if due_date_text else None
        except ValueError:
            due_date = None
        today = date.today()
        days_past_due = (today - due_date).days if due_date else None
        if due_date is None:
            aging_bucket = "due_date_unavailable"
        elif days_past_due is not None and days_past_due <= 0:
            aging_bucket = "current_or_future"
        elif days_past_due <= 30:
            aging_bucket = "days_1_to_30"
        elif days_past_due <= 60:
            aging_bucket = "days_31_to_60"
        elif days_past_due <= 90:
            aging_bucket = "days_61_to_90"
        else:
            aging_bucket = "days_91_plus"
        customer_number = _text(row.get("customer_number"))
        invoice_number = _text(row.get("invoice_number"))
        invoice_count = (
            int(row["invoice_count"])
            if row.get("invoice_count") not in (None, "")
            else None
        )
        return CreditOpenItem(
            open_item_key="|".join(
                [
                    customer_number,
                    invoice_number,
                    str(invoice_count or ""),
                    _text(row.get("transaction_type")),
                    _text(row.get("reference_number")),
                ]
            ),
            customer_number=customer_number,
            invoice_number=invoice_number,
            invoice_count=invoice_count,
            invoice_date=_date_text(row.get("invoice_date")),
            due_date=due_date_text,
            original_amount=_number(row.get("original_amount")),
            open_amount=round(signed_open_amount, 2),
            raw_open_amount=raw_open_amount,
            debit_credit=debit_credit,
            transaction_type=_text(row.get("transaction_type")),
            reference_number=_text(row.get("reference_number")),
            selling_store=_text(row.get("selling_store")) or None,
            days_past_due=days_past_due,
            aging_bucket=aging_bucket,
        )

    @staticmethod
    def _related_account(
        row: dict[str, Any],
        *,
        selected_customer: int,
        enterprise_number: str | None,
    ) -> RelatedCustomerEvidence:
        number = _text(row.get("CUNUMBER"))
        row_enterprise = _text(row.get("CUNUMENT")) or None
        if number == str(selected_customer):
            relationship = "selected_customer"
        elif enterprise_number and number == enterprise_number:
            relationship = "enterprise_anchor"
        else:
            relationship = "linked_customer"
        balance = _number(row.get("CUBALANCE"))
        on_order = round(
            _number(row.get("CUONORDER")) + _number(row.get("CUONORDAR")),
            2,
        )
        return RelatedCustomerEvidence(
            customer_number=number,
            customer_name=_text(row.get("CUNAME")),
            enterprise_number=row_enterprise,
            relationship=relationship,
            credit_limit=_number(row.get("CUCRLIMIT")),
            balance=balance,
            erp_on_order_aggregate=on_order,
            partial_exposure=round(balance + max(on_order, 0), 2),
        )

    @staticmethod
    def _credit_coverage(
        *,
        generated_at: str,
        open_ar_count: int,
        open_ar_complete: bool,
        related_count: int,
        related_complete: bool,
        enterprise_number: str | None,
    ) -> list[EvidenceCoverageItem]:
        related_status = (
            "available"
            if related_complete and enterprise_number and enterprise_number != "0"
            else "partial"
        )
        return [
            EvidenceCoverageItem(
                key="customer_master",
                label="Customer master, current line, terms, and aggregate balances",
                status="available",
                source="MaddenCo TMCUST",
                as_of=generated_at,
                record_count=1,
                complete=True,
                explanation="Current TMCUST evidence is available through the established Customer 360 boundary.",
            ),
            EvidenceCoverageItem(
                key="open_ar_detail",
                label="Current Open A/R detail",
                status="available" if open_ar_complete else "partial",
                source="MaddenCo TMAROP",
                as_of=generated_at,
                record_count=open_ar_count,
                complete=open_ar_complete,
                explanation=(
                    "Current nonzero Open A/R rows were retrieved with signed credit treatment."
                    if open_ar_complete
                    else "Open A/R exceeded the bounded row limit; retrieved rows are incomplete."
                ),
            ),
            EvidenceCoverageItem(
                key="cunument_relationships",
                label="CUNUMENT-linked customer accounts",
                status=related_status,
                source="MaddenCo TMCUST.CUNUMENT",
                as_of=generated_at,
                record_count=related_count,
                complete=related_complete,
                explanation=(
                    "CUNUMENT-linked accounts are visible, but this relationship alone does not prove every related entity or guarantor."
                ),
            ),
            EvidenceCoverageItem(
                key="detailed_open_orders",
                label="Detailed open orders and releasable orders",
                status="unavailable",
                explanation="Only the TMCUST on-order aggregate is connected; governed order-level mappings are not confirmed.",
            ),
            EvidenceCoverageItem(
                key="unbilled_shipments",
                label="Unbilled shipments",
                status="unavailable",
                explanation="No authoritative unbilled-shipment mapping is connected.",
            ),
            EvidenceCoverageItem(
                key="payment_history",
                label="Complete payment behavior history",
                status="unavailable",
                explanation="Only the TMCUST last-payment amount/date is connected; complete history and derived timing metrics remain unavailable.",
            ),
            EvidenceCoverageItem(
                key="credit_line_history",
                label="Credit-line and terms change history",
                status="unavailable",
                explanation="Current line and terms are available; no governed historical-change source is connected.",
            ),
            EvidenceCoverageItem(
                key="full_exposure_adjustments",
                label="Unapplied cash, valid credits, and secured amounts",
                status="unavailable",
                explanation="The source mappings and applicability rules required for complete exposure are not confirmed.",
            ),
        ]


erp_evidence_service = ERPEvidenceService()
