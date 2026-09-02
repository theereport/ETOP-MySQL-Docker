from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from .notes_repository import (
    ARCollectionsNotesRepository,
    ar_collections_notes_repository,
)
from .repository import ARCollectionsRepository, ar_collections_repository
from .schemas import (
    AgingHistoryEvidence,
    AgingSnapshot,
    ARCollectionsEvidenceGap,
    ARCollectionsNoteCreate,
    ARCollectionsNoteHistoryResponse,
    ARCollectionsNoteRecord,
    AROpenItemHistoryEvidence,
    ARTransaction,
    ARTransactionApplication,
    ARTransactionHistoryEvidence,
    CustomerARCollectionsResponse,
    CustomerIdentityEvidence,
    ERPCollectionNote,
    ERPCollectionNotesEvidence,
    ERPCreditManagementNote,
    ERPCreditManagementNotesEvidence,
    GLDistributionEvidence,
    GLDistributionLine,
    OpenAREvidence,
    OpenARItem,
    SourceEvidence,
)


class ARCollectionsCustomerNotFound(LookupError):
    """Raised when Customer 360 has no matching ERP customer."""


class ARCollectionsSourceUnavailable(RuntimeError):
    """Raised when live Customer 360 facts cannot be retrieved."""


class ARCollectionsSourceIntegrityError(RuntimeError):
    """Raised when Customer 360 returns evidence for another customer."""


_GAPS = [
    ARCollectionsEvidenceGap(
        code="collections_priority_ranking",
        label="Collections priority ranking / weighting",
        explanation=(
            "No approved definition, weighting, or tie-breaking rule for "
            "'collections priority' is configured. This module presents "
            "open-item, transaction, GL, and note evidence only; it "
            "computes no priority score, rank, or automatic "
            "recommendation."
        ),
    ),
    ARCollectionsEvidenceGap(
        code="dunning_cadence_policy",
        label="Dunning / statement cadence policy",
        explanation=(
            "No approved dunning schedule or statement cadence policy is "
            "configured, so ETOP does not compute or suggest when a "
            "customer should next be contacted or statemented."
        ),
    ),
    ARCollectionsEvidenceGap(
        code="erp_disposition_write_back",
        label="Write-back of a collection disposition into MaddenCo",
        explanation=(
            "Writing a collection disposition, hold, or promise-to-pay "
            "back into MaddenCo is out of scope. This module is read-only "
            "against the ERP; a saved local note is append-only ETOP "
            "evidence and creates no ERP record."
        ),
    ),
]


def _now() -> datetime:
    return datetime.now(UTC)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.upper() == "NONE" else text


def _parse_erp_date(value: Any) -> str | None:
    if isinstance(value, (datetime, date)):
        if isinstance(value, datetime):
            return value.date().isoformat()
        return value.isoformat()

    raw = _clean_text(value)
    if not raw or raw == "0" * len(raw):
        return None
    for pattern in ("%Y%m%d", "%m%d%Y"):
        try:
            return datetime.strptime(raw, pattern).date().isoformat()
        except ValueError:
            continue
    return raw


def _parse_erp_timestamp(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return _parse_erp_date(value)


def _erp_date_object(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    raw = _clean_text(value)
    if not raw or raw == "0" * len(raw):
        return None
    for pattern in ("%Y%m%d", "%m%d%Y"):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    return None


def _number(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed != 0 else None


class ARCollectionsService:
    """Build source-grounded, evidence-only AR collections responses."""

    def __init__(
        self,
        *,
        repository: ARCollectionsRepository = ar_collections_repository,
        notes_repository: ARCollectionsNotesRepository = (
            ar_collections_notes_repository
        ),
        customer_summary_service: Any | None = None,
        clock: Callable[[], datetime] = _now,
        note_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._notes_repository = notes_repository
        self._customer_summary_service = customer_summary_service
        self._clock = clock
        self._note_id_factory = note_id_factory or (
            lambda: f"ar-collections-note-{uuid4().hex}"
        )

    def _customer_service(self) -> Any:
        if self._customer_summary_service is None:
            # Resolve the shared Customer 360 singleton only when live facts
            # are requested. This avoids creating a second ERP repository and
            # keeps this module's own local notes independent of ERP
            # availability.
            from modules.customer_360.service import customer_service

            self._customer_summary_service = customer_service
        return self._customer_summary_service

    def _load_customer_summary(
        self,
        customer_number: int,
    ) -> dict[str, Any]:
        try:
            summary = self._customer_service().summary(customer_number)
        except Exception as exc:
            raise ARCollectionsSourceUnavailable(
                "Customer 360 could not retrieve the read-only ERP facts."
            ) from exc
        if summary is None:
            raise ARCollectionsCustomerNotFound(
                f"Customer {customer_number} was not found in MaddenCo."
            )
        if not isinstance(summary, dict):
            raise ARCollectionsSourceIntegrityError(
                "Customer 360 returned an invalid customer summary "
                "envelope."
            )
        try:
            returned_customer_number = int(summary["customer_number"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ARCollectionsSourceIntegrityError(
                "Customer 360 returned no valid customer identity for the "
                f"requested customer {customer_number}."
            ) from exc
        if returned_customer_number != customer_number:
            raise ARCollectionsSourceIntegrityError(
                "Customer 360 returned customer "
                f"{returned_customer_number} for requested customer "
                f"{customer_number}; no AR collections evidence was "
                "attached."
            )
        return summary

    @staticmethod
    def _build_identity(summary: dict[str, Any]) -> CustomerIdentityEvidence:
        general = summary.get("general")
        general = general if isinstance(general, dict) else {}
        customer_name = str(summary.get("customer_name") or "").strip()
        if not customer_name:
            raise ARCollectionsSourceIntegrityError(
                "Customer 360 returned no customer name for the requested "
                "customer."
            )
        return CustomerIdentityEvidence(
            customer_number=int(summary["customer_number"]),
            customer_name=customer_name,
            dba_name=str(general.get("dba_name") or "").strip(),
            address_lines=list(general.get("address_lines") or []),
            zip_code=str(general.get("zip_code") or "").strip(),
            country=str(general.get("country") or "").strip(),
            phone=str(general.get("phone") or "").strip(),
            email=str(general.get("email") or "").strip(),
            route_code=str(general.get("route_code") or "").strip(),
            store_number=general.get("store_number"),
            salesman_number=general.get("salesman_number"),
            customer_type=str(general.get("customer_type") or "").strip(),
            customer_class=str(general.get("customer_class") or "").strip(),
            active=bool(general.get("active")),
        )

    def get_customer_collections(
        self,
        customer_number: int,
    ) -> CustomerARCollectionsResponse:
        summary = self._load_customer_summary(customer_number)
        identity = self._build_identity(summary)

        retrieved_at = self._clock().astimezone(UTC).isoformat()
        today = self._clock().astimezone(UTC).date()

        return CustomerARCollectionsResponse(
            generated_at=retrieved_at,
            source=SourceEvidence(retrieved_at=retrieved_at),
            customer=identity,
            open_ar=self._build_open_ar_evidence(customer_number, today),
            item_history=self._build_item_history_evidence(
                customer_number, today
            ),
            transactions=self._build_transaction_history_evidence(
                customer_number
            ),
            gl_distributions=self._build_gl_distribution_evidence(
                customer_number
            ),
            erp_collection_notes=self._build_erp_collection_notes_evidence(
                customer_number
            ),
            erp_credit_management_notes=(
                self._build_credit_management_notes_evidence(
                    customer_number
                )
            ),
            aging_history=self._build_aging_history_evidence(
                customer_number
            ),
            gaps=list(_GAPS),
        )

    @staticmethod
    def _map_arop_item(row: dict[str, Any], today: date) -> OpenARItem:
        due_date_object = _erp_date_object(row.get("TARODTEDUE"))
        days_past_due = (
            (today - due_date_object).days
            if due_date_object is not None
            else None
        )
        return OpenARItem(
            invoice_number=int(row.get("TARONUMINV") or 0),
            transaction_type=_clean_text(row.get("TAROTYPTRN")),
            entry_type=_clean_text(row.get("TAROENTTYP")),
            debit_credit=_clean_text(row.get("TARODBCR")),
            original_amount=_number(row.get("TAROAMTORG")),
            open_amount=_number(row.get("TAROAMTOPN")),
            discountable_amount=_number(row.get("TAROAMTDSC")),
            cash_discount=_number(row.get("TAROCSHDSC")),
            terms_code=_clean_text(row.get("TAROCDTERM")),
            adjustment_reason=_clean_text(row.get("TAROADJRSN")),
            reference_number=_clean_text(row.get("TARONUMREF")),
            transaction_date=_parse_erp_date(row.get("TARODTE")),
            due_date=_parse_erp_date(row.get("TARODTEDUE")),
            days_past_due=days_past_due,
            purged_to_history=(
                _clean_text(row.get("TAROHISTYN")).upper() == "Y"
            ),
        )

    def _build_open_ar_evidence(
        self,
        customer_number: int,
        today: date,
    ) -> OpenAREvidence:
        rows = self._repository.get_open_items(customer_number)
        items = [self._map_arop_item(row, today) for row in rows]
        return OpenAREvidence(
            item_count=len(items),
            total_open_amount=round(
                sum(item.open_amount for item in items), 2
            ),
            open_items=items,
        )

    def _build_item_history_evidence(
        self,
        customer_number: int,
        today: date,
    ) -> AROpenItemHistoryEvidence:
        rows = self._repository.get_item_history(customer_number)
        items = [self._map_arop_item(row, today) for row in rows]
        return AROpenItemHistoryEvidence(
            item_count=len(items),
            items=items,
        )

    def _build_transaction_history_evidence(
        self,
        customer_number: int,
    ) -> ARTransactionHistoryEvidence:
        header_rows = self._repository.get_transaction_history(
            customer_number
        )
        transactions = [
            ARTransaction(
                sequence=int(row.get("TNARSEQ") or 0),
                invoice_number=int(row.get("TNARNUMINV") or 0),
                transaction_date=_parse_erp_date(row.get("TNARDTE")),
                due_date=_parse_erp_date(row.get("TNARDTEDUE")),
                original_amount=_number(row.get("TNARAMTORG")),
                debit_credit=_clean_text(row.get("TNARDBCR")),
                entry_type=_clean_text(row.get("TNARENTTYP")),
                transaction_type=_clean_text(row.get("TNARTYPTRN")),
                reference_number=_clean_text(row.get("TNARNUMREF")),
                status=_clean_text(row.get("TNARSTATUS")),
                period=_optional_int(row.get("TNARPER")),
                year=_optional_int(row.get("TNARYEAR")),
                cash_discount=_number(row.get("TNARCSHDSC")),
            )
            for row in header_rows
        ]

        detail_rows = self._repository.get_transaction_applications(
            customer_number
        )
        applications = [
            ARTransactionApplication(
                header_sequence=int(row.get("HEADER_TNARSEQ") or 0),
                detail_sequence=int(row.get("TNARDTLSEQ") or 0),
                header_invoice_number=int(
                    row.get("HEADER_TNARNUMINV") or 0
                ),
                header_reference_number=_clean_text(
                    row.get("HEADER_TNARNUMREF")
                ),
                header_transaction_date=_parse_erp_date(
                    row.get("HEADER_TNARDTE")
                ),
                applied_invoice_number=int(row.get("TNARINVAPL") or 0),
                amount_applied=_number(row.get("TNARAMTAPL")),
                discount_applied=_number(row.get("TNARDISAPL")),
                gl_account=_optional_int(row.get("TNARGLACCT")),
                gl_division=_optional_int(row.get("TNARGLDIV")),
                gl_department=_optional_int(row.get("TNARGLDPT")),
                created_date=_parse_erp_date(row.get("TNARDTECRT")),
            )
            for row in detail_rows
        ]

        return ARTransactionHistoryEvidence(
            transaction_count=len(transactions),
            application_count=len(applications),
            transactions=transactions,
            applications=applications,
        )

    def _build_gl_distribution_evidence(
        self,
        customer_number: int,
    ) -> GLDistributionEvidence:
        rows = self._repository.get_gl_distributions(customer_number)
        lines = [
            GLDistributionLine(
                gl_account=_optional_int(row.get("TNGLNBACCT")),
                gl_division=_optional_int(row.get("TNGLNBDV")),
                gl_department=_optional_int(row.get("TNGLNBDP")),
                debit_amount=_number(row.get("TNGLAMTDB")),
                credit_amount=_number(row.get("TNGLAMTCR")),
                quantity=_number(row.get("TNGLQTY")),
                description=_clean_text(row.get("TNGLDSC")),
                created_date=_parse_erp_date(row.get("TNGLDTECRT")),
            )
            for row in rows
        ]
        return GLDistributionEvidence(
            line_count=len(lines),
            total_debit_amount=round(
                sum(line.debit_amount for line in lines), 2
            ),
            total_credit_amount=round(
                sum(line.credit_amount for line in lines), 2
            ),
            lines=lines,
        )

    def _build_erp_collection_notes_evidence(
        self,
        customer_number: int,
    ) -> ERPCollectionNotesEvidence:
        rows = self._repository.get_erp_collection_notes(customer_number)
        notes = [
            ERPCollectionNote(
                note_text=_clean_text(row.get("NOTES")),
                created_at=_parse_erp_timestamp(row.get("CRTSTAMP")),
                created_by=_clean_text(row.get("CRTUSER")),
                changed_at=_parse_erp_timestamp(row.get("CHGSTAMP")),
                changed_by=_clean_text(row.get("CHGUSER")),
            )
            for row in rows
        ]
        return ERPCollectionNotesEvidence(count=len(notes), notes=notes)

    def _build_credit_management_notes_evidence(
        self,
        customer_number: int,
    ) -> ERPCreditManagementNotesEvidence:
        header_rows = self._repository.get_credit_management_headers(
            customer_number
        )
        header_keys = [int(header.get("TCMOHNBKY") or 0) for header in header_rows]
        detail_rows_by_header: dict[int, list[dict[str, Any]]] = {}
        for detail in self._repository.get_credit_management_detail_for_headers(
            header_keys
        ):
            detail_rows_by_header.setdefault(
                int(detail.get("TCMOHNBKY") or 0), []
            ).append(detail)

        notes: list[ERPCreditManagementNote] = []
        for header in header_rows:
            header_key = int(header.get("TCMOHNBKY") or 0)
            detail_rows = detail_rows_by_header.get(header_key, [])
            detail_lines = [
                text
                for text in (
                    _clean_text(detail.get("TCMODTXT"))
                    for detail in detail_rows
                )
                if text
            ]
            notes.append(
                ERPCreditManagementNote(
                    header_key=header_key,
                    regarding=_clean_text(header.get("TCMOHTXT")),
                    date_to_do=_parse_erp_date(header.get("TCMOHDTDO")),
                    date_done=_parse_erp_date(header.get("TCMOHDTDN")),
                    created_at=_parse_erp_date(header.get("TCMOHDTCRT")),
                    created_by=_clean_text(header.get("TCMOHUSRCR")),
                    changed_at=_parse_erp_date(header.get("TCMOHDTCHG")),
                    changed_by=_clean_text(header.get("TCMOHUSRCH")),
                    detail_lines=detail_lines,
                )
            )
        return ERPCreditManagementNotesEvidence(
            count=len(notes),
            notes=notes,
        )

    def _build_aging_history_evidence(
        self,
        customer_number: int,
    ) -> AgingHistoryEvidence:
        rows = self._repository.get_aging_snapshots(customer_number)
        snapshots = [
            AgingSnapshot(
                snapshot_date=_parse_erp_date(row.get("TCCHDTE")),
                aging_future=_number(row.get("TCCHAGE1")),
                aging_current=_number(row.get("TCCHAGE2")),
                aging_30=_number(row.get("TCCHAGE3")),
                aging_60=_number(row.get("TCCHAGE4")),
                aging_90=_number(row.get("TCCHAGE5")),
                aging_120=_number(row.get("TCCHAGE6")),
                balance=_number(row.get("TCCHBAL")),
                balance_high=_number(row.get("TCCHBALHI")),
                discount_month_to_date=_number(row.get("TCCHDISMTD")),
                credit_limit=_number(row.get("TCCHCRDLMT")),
                date_last_paid=_parse_erp_date(row.get("TCCHDTELPD")),
                date_last_statement=_parse_erp_date(
                    row.get("TCCHDTELST")
                ),
                amount_last_paid=_number(row.get("TCCHAMTLPD")),
                salesman_number=_optional_int(row.get("TCCHNUMSLM")),
                sales_month_to_date=_number(row.get("TCCHSALMTD")),
            )
            for row in rows
        ]
        return AgingHistoryEvidence(
            snapshot_count=len(snapshots),
            snapshots=snapshots,
        )

    def list_notes(
        self,
        customer_number: int,
    ) -> ARCollectionsNoteHistoryResponse:
        records = [
            ARCollectionsNoteRecord(**record)
            for record in self._notes_repository.list_notes(
                customer_number
            )
        ]
        return ARCollectionsNoteHistoryResponse(
            customer_number=customer_number,
            count=len(records),
            notes=records,
        )

    def create_note(
        self,
        customer_number: int,
        payload: ARCollectionsNoteCreate,
    ) -> ARCollectionsNoteRecord:
        evidence = self.get_customer_collections(customer_number)
        created_at = self._clock().astimezone(UTC).isoformat()
        record = {
            "note_id": self._note_id_factory(),
            "customer_number": customer_number,
            "customer_name": evidence.customer.customer_name,
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
        return ARCollectionsNoteRecord(
            **self._notes_repository.create_note(record)
        )


ar_collections_service = ARCollectionsService()
