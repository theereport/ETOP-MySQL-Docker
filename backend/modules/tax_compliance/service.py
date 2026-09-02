from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from .notes_repository import (
    TaxComplianceNotesRepository,
    tax_compliance_notes_repository,
)
from .repository import TaxComplianceRepository, tax_compliance_repository
from .schemas import (
    CustomerExemptionCheckBatchResponse,
    CustomerExemptionCheckResponse,
    CustomerExemptionCheckResult,
    SourceEvidence,
    TaxAuthorityRecord,
    TaxAuthoritySearchResponse,
    TaxComplianceGap,
    TaxComplianceNoteCreate,
    TaxComplianceNoteHistoryResponse,
    TaxComplianceNoteRecord,
    TaxExemptionCodeRecord,
    TaxExemptionCodeSearchResponse,
)


class TaxAuthorityNotFound(LookupError):
    """Raised when MaddenCo has no TMTAX row for the requested key."""


class ExemptionCodeNotFound(LookupError):
    """Raised when MaddenCo has no TMTAXE row for the requested code."""


class CustomerNotFound(LookupError):
    """Raised when MaddenCo has no TMCUST row for the requested number."""


def _now() -> datetime:
    return datetime.now(UTC)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.upper() == "NONE" else text


def _parse_erp_date(value: Any) -> str | None:
    raw = _clean_text(value)
    if not raw or raw == "0" * len(raw):
        return None
    for pattern in ("%Y%m%d", "%m%d%Y"):
        try:
            return datetime.strptime(raw, pattern).date().isoformat()
        except ValueError:
            continue
    return raw


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 5)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed != 0 else None


_GAPS = [
    TaxComplianceGap(
        code="exemption_certificate_document_storage",
        label="Exemption certificate document / custody history",
        explanation=(
            "TMCUST carries only one current exempt code (CUTAXEXCD) and "
            "one current expiration date (CUDTETXEXP) per customer. There "
            "is no MaddenCo table storing the scanned/imaged certificate "
            "itself, prior certificates, or per-jurisdiction certificates "
            "for customers exempt in multiple states. Certificate custody "
            "and history must be tracked in this module's local append-only "
            "notes instead."
        ),
    ),
    TaxComplianceGap(
        code="jurisdiction_nexus_table",
        label="Jurisdiction nexus / registration tracking",
        explanation=(
            "No table in the current MaddenCo schema records which tax "
            "jurisdictions this company (or a given customer) has nexus or "
            "registration obligations in. This module cannot report nexus "
            "status."
        ),
    ),
    TaxComplianceGap(
        code="tax_compliance_risk_score",
        label="Tax compliance risk score",
        explanation=(
            "No approved risk-weighting model is configured. This module "
            "reports deterministic matches and expiration comparisons only; "
            "it computes no compliance risk score, rank, or recommendation."
        ),
    ),
]


class TaxComplianceService:
    """Build source-grounded, evidence-only tax compliance responses."""

    def __init__(
        self,
        *,
        repository: TaxComplianceRepository = tax_compliance_repository,
        notes_repository: TaxComplianceNotesRepository = (
            tax_compliance_notes_repository
        ),
        clock: Callable[[], datetime] = _now,
        note_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._notes_repository = notes_repository
        self._clock = clock
        self._note_id_factory = note_id_factory or (
            lambda: f"tax-compliance-note-{uuid4().hex}"
        )

    # -- Tax authority rate reference (TMTAX) --------------------------

    def _authority_from_row(self, row: dict[str, Any]) -> TaxAuthorityRecord:
        return TaxAuthorityRecord(
            tax_authority=int(row["TTAXAUTH"]),
            state_code=int(row["TTAXCODSTE"]),
            state_abbreviation=_clean_text(row.get("TTAXSTEABR")),
            description=_clean_text(row.get("TTAXDSC")),
            tax_type_code=_clean_text(row.get("TTAXTYPCD")),
            rate_percent=_number(row.get("TTAXRATPCT")),
            max_tax_amount=_number(row.get("TTAXAMTMAX")),
            fet_applicable=_clean_text(row.get("TTAXFETYN")).upper() == "Y",
            selectable_from_prompt=(
                _clean_text(row.get("TTAXSLCTFG")).upper() == "Y"
            ),
            next_tax_authority=_optional_int(row.get("TTAXAUTNXT")),
            next_state_code=_optional_int(row.get("TTAXSTENXT")),
            active=_clean_text(row.get("TTAXCODDEL")) in ("", "A"),
            date_created=_parse_erp_date(row.get("TTAXDTECRT")),
            date_changed=_parse_erp_date(row.get("TTAXDTECHG")),
            created_by=_clean_text(row.get("TTAXUSRCRT")),
            changed_by=_clean_text(row.get("TTAXUSRCHG")),
        )

    def search_tax_authorities(
        self,
        *,
        state_abbreviation: str = "",
        tax_type_code: str = "",
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> TaxAuthoritySearchResponse:
        rows = self._repository.search_tax_authorities(
            state_abbreviation=state_abbreviation,
            tax_type_code=tax_type_code,
            active_only=active_only,
            limit=limit,
            offset=offset,
        )
        retrieved_at = self._clock().astimezone(UTC).isoformat()
        authorities = [self._authority_from_row(row) for row in rows]
        return TaxAuthoritySearchResponse(
            source=SourceEvidence(retrieved_at=retrieved_at),
            count=len(authorities),
            authorities=authorities,
        )

    def get_tax_authority(
        self,
        tax_authority: int,
        state_code: int,
    ) -> TaxAuthorityRecord:
        row = self._repository.get_tax_authority(tax_authority, state_code)
        if row is None:
            raise TaxAuthorityNotFound(
                f"Tax authority {tax_authority} for state code {state_code} "
                "was not found in MaddenCo."
            )
        return self._authority_from_row(row)

    # -- Tax exemption code reference (TMTAXE) -------------------------

    def _exemption_from_row(
        self, row: dict[str, Any]
    ) -> TaxExemptionCodeRecord:
        return TaxExemptionCodeRecord(
            exempt_code=_clean_text(row.get("TTXECODEXE")),
            state_code=int(row["TTXECODSTE"]),
            description=_clean_text(row.get("TTXEDSC")),
            tax_type_code=_clean_text(row.get("TTXETYPCD")),
            override_or_percent_code=_clean_text(row.get("TTXEOORP")),
            percent_taxable=_number(row.get("TTXEPCTTAX")),
            rate_percent=_number(row.get("TTXERATPCT")),
            max_taxable_per_line=_number(row.get("TTXEMAXTAX")),
            active=_clean_text(row.get("TTXECODDEL")) in ("", "A"),
            date_created=_parse_erp_date(row.get("TTXEDTECRT")),
            date_changed=_parse_erp_date(row.get("TTXEDTECHG")),
            created_by=_clean_text(row.get("TTXEUSRCRT")),
            changed_by=_clean_text(row.get("TTXEUSRCHG")),
        )

    def search_exemption_codes(
        self,
        *,
        state_code: int | None = None,
        tax_type_code: str = "",
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> TaxExemptionCodeSearchResponse:
        rows = self._repository.search_exemption_codes(
            state_code=state_code,
            tax_type_code=tax_type_code,
            active_only=active_only,
            limit=limit,
            offset=offset,
        )
        retrieved_at = self._clock().astimezone(UTC).isoformat()
        codes = [self._exemption_from_row(row) for row in rows]
        return TaxExemptionCodeSearchResponse(
            source=SourceEvidence(retrieved_at=retrieved_at),
            count=len(codes),
            exemption_codes=codes,
        )

    def get_exemption_code(
        self, exempt_code: str
    ) -> list[TaxExemptionCodeRecord]:
        rows = self._repository.get_exemption_codes_by_code(exempt_code)
        if not rows:
            raise ExemptionCodeNotFound(
                f"Exemption code {exempt_code!r} was not found in MaddenCo."
            )
        return [self._exemption_from_row(row) for row in rows]

    # -- Customer exemption-code integrity check -----------------------

    def _expiration_status(
        self, expiration_date: str | None
    ) -> str:
        if expiration_date is None:
            return "no_expiration_date_on_file"
        try:
            parsed = date.fromisoformat(expiration_date)
        except ValueError:
            return "no_expiration_date_on_file"
        today = self._clock().astimezone(UTC).date()
        return "expired" if parsed < today else "current"

    def _check_customer_row(
        self,
        row: dict[str, Any],
        *,
        exemption_records_by_code: dict[str, list[TaxExemptionCodeRecord]]
        | None = None,
    ) -> CustomerExemptionCheckResult:
        exemption_code = _clean_text(row.get("CUTAXEXCD"))
        expiration_date = _parse_erp_date(row.get("CUDTETXEXP"))
        expiration_status = self._expiration_status(expiration_date)

        if not exemption_code:
            match_status = "no_exemption_code_on_customer"
            matched: list[TaxExemptionCodeRecord] = []
        elif exemption_records_by_code is not None:
            matched = exemption_records_by_code.get(exemption_code, [])
            match_status = (
                "matched" if matched else "no_matching_exemption_code_found"
            )
        else:
            matched_rows = self._repository.get_exemption_codes_by_code(
                exemption_code
            )
            matched = [self._exemption_from_row(r) for r in matched_rows]
            match_status = (
                "matched" if matched else "no_matching_exemption_code_found"
            )

        return CustomerExemptionCheckResult(
            customer_number=int(row["CUNUMBER"]),
            customer_name=_clean_text(row.get("CUNAME")),
            state_code=_optional_int(row.get("CUSTATE")),
            exemption_code_on_file=exemption_code,
            fet_exempt=_clean_text(row.get("CUFETEXMPT")).upper() == "Y",
            exemption_certificate_expiration_date=expiration_date,
            expiration_status=expiration_status,
            match_status=match_status,
            matched_exemption_codes=matched,
        )

    def check_customer_exemption(
        self, customer_number: int
    ) -> CustomerExemptionCheckResponse:
        row = self._repository.get_customer_tax_fields(customer_number)
        if row is None:
            raise CustomerNotFound(
                f"Customer {customer_number} was not found in MaddenCo."
            )
        retrieved_at = self._clock().astimezone(UTC).isoformat()
        result = self._check_customer_row(row)
        return CustomerExemptionCheckResponse(
            generated_at=retrieved_at,
            source=SourceEvidence(retrieved_at=retrieved_at),
            result=result,
            gaps=list(_GAPS),
        )

    def check_customers_exemption(
        self, customer_numbers: list[int]
    ) -> CustomerExemptionCheckBatchResponse:
        unique_numbers = list(dict.fromkeys(customer_numbers))
        rows = self._repository.get_customers_tax_fields(unique_numbers)
        rows_by_number = {int(row["CUNUMBER"]): row for row in rows}

        exemption_codes = sorted(
            {
                _clean_text(row.get("CUTAXEXCD"))
                for row in rows_by_number.values()
                if _clean_text(row.get("CUTAXEXCD"))
            }
        )
        exemption_records_by_code: dict[str, list[TaxExemptionCodeRecord]] = {}
        for exemption_row in self._repository.get_exemption_codes_by_codes(
            exemption_codes
        ):
            code = _clean_text(exemption_row.get("TTXECODEXE"))
            exemption_records_by_code.setdefault(code, []).append(
                self._exemption_from_row(exemption_row)
            )

        results: list[CustomerExemptionCheckResult] = []
        not_found: list[int] = []
        for number in unique_numbers:
            row = rows_by_number.get(number)
            if row is None:
                not_found.append(number)
                continue
            results.append(
                self._check_customer_row(
                    row,
                    exemption_records_by_code=exemption_records_by_code,
                )
            )

        retrieved_at = self._clock().astimezone(UTC).isoformat()
        return CustomerExemptionCheckBatchResponse(
            generated_at=retrieved_at,
            source=SourceEvidence(retrieved_at=retrieved_at),
            checked_count=len(results),
            not_found_customer_numbers=not_found,
            results=results,
            gaps=list(_GAPS),
        )

    # -- Local append-only professional notes ---------------------------

    def list_notes(self, customer_number: int) -> TaxComplianceNoteHistoryResponse:
        records = [
            TaxComplianceNoteRecord(**record)
            for record in self._notes_repository.list_notes(customer_number)
        ]
        return TaxComplianceNoteHistoryResponse(
            customer_number=customer_number,
            count=len(records),
            notes=records,
        )

    def create_note(
        self,
        customer_number: int,
        payload: TaxComplianceNoteCreate,
    ) -> TaxComplianceNoteRecord:
        evidence = self.check_customer_exemption(customer_number)
        created_at = self._clock().astimezone(UTC).isoformat()
        record = {
            "note_id": self._note_id_factory(),
            "customer_number": customer_number,
            "customer_name": evidence.result.customer_name,
            "author_identity": payload.author_identity,
            "note": payload.note,
            "created_at": created_at,
            "source_as_of": evidence.source.retrieved_at,
            "actor_identity_source": "operator_supplied",
            "actor_authority_status": "not_independently_verified",
            "note_classification": "professional_workflow_metadata",
            "decision_effect": "none",
            "evidence_snapshot": evidence.model_dump(mode="json"),
        }
        return TaxComplianceNoteRecord(
            **self._notes_repository.create_note(record)
        )


tax_compliance_service = TaxComplianceService()
