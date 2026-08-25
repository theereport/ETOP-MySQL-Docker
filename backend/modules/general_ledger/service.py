from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .notes_repository import (
    GeneralLedgerNotesRepository,
    general_ledger_notes_repository,
)
from .repository import GeneralLedgerRepository, general_ledger_repository
from .schemas import (
    AccountBalanceEvidence,
    AccountEvidenceGap,
    AccountEvidenceResponse,
    AccountIdentityEvidence,
    AccountPeriodBalance,
    AccountSearchResponse,
    AccountSearchResult,
    GLNoteCreate,
    GLNoteHistoryResponse,
    GLNoteRecord,
    JournalEntryHeaderReference,
    PostedTransaction,
    ReconciliationCheck,
    SourceEvidence,
    StandardJournalEntryTemplateDetail,
    StandardJournalEntryTemplateLine,
    StandardJournalEntryTemplateResponse,
    StandardJournalEntryTemplateSummary,
    TransactionEvidence,
    UnpostedJournalEntryLine,
)


class AccountNotFound(LookupError):
    """Raised when MaddenCo has no G/L account matching the requested key."""


class TemplateNotFound(LookupError):
    """Raised when MaddenCo has no standard JE template with that name."""


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


def _number(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return default


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 2)
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
    AccountEvidenceGap(
        code="reconciliation_tolerance_threshold",
        label="Approved reconciliation tolerance",
        explanation=(
            "No approved tolerance threshold for the difference between "
            "GMAD posted-detail totals and the GMBL period balance is "
            "configured. The reconciliation check below reports only the "
            "literal arithmetic difference; it does not judge whether that "
            "difference is acceptable."
        ),
    ),
    AccountEvidenceGap(
        code="close_period_lock_authority",
        label="Close-period lock authority",
        explanation=(
            "Close-cycle status and the authority to lock or reopen a "
            "period belong to the financial_close module, not to this "
            "read-only G/L viewer."
        ),
    ),
    AccountEvidenceGap(
        code="automatic_balance_verdict",
        label='Automatic "in balance" / "out of balance" verdict',
        explanation=(
            "This module computes no automatic in-balance or out-of-"
            "balance judgment for any account or period. Only the stated "
            "arithmetic difference is reported."
        ),
    ),
    AccountEvidenceGap(
        code="unposted_je_line_retention",
        label="Historical unposted journal entry line detail",
        explanation=(
            "MaddenCo's GTJD table retains journal entry line detail only "
            "while an entry is being entered and before it posts to GMAD. "
            "There is no historical archive of unposted-then-posted "
            "journal entry line detail beyond what GMAD itself records."
        ),
    ),
]


def _map_account_search_row(row: dict[str, Any]) -> AccountSearchResult:
    return AccountSearchResult(
        account_number=int(row["GMNB"]),
        division=int(row["GMNBDIV"]),
        department=int(row["GMNBDPT"]),
        description=_clean_text(row.get("GMDCRACT")),
        short_name=_clean_text(row.get("GMDCRACTSH")),
        debit_or_credit=_clean_text(row.get("GMCDDBCR")),
        account_type=_clean_text(row.get("GMTYPACT")),
        active=_clean_text(row.get("GMYNACTIVE")).upper() == "Y",
    )


class GeneralLedgerService:
    """Build source-grounded, evidence-only general ledger responses."""

    def __init__(
        self,
        *,
        repository: GeneralLedgerRepository = general_ledger_repository,
        notes_repository: GeneralLedgerNotesRepository = (
            general_ledger_notes_repository
        ),
        clock: Callable[[], datetime] = _now,
        note_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._notes_repository = notes_repository
        self._clock = clock
        self._note_id_factory = note_id_factory or (
            lambda: f"gl-note-{uuid4().hex}"
        )

    # ------------------------------------------------------------------
    # Chart of accounts
    # ------------------------------------------------------------------

    def search_accounts(
        self,
        *,
        search: str = "",
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> AccountSearchResponse:
        rows = self._repository.search_accounts(
            search=search,
            active_only=active_only,
            limit=limit,
            offset=offset,
        )
        retrieved_at = self._clock().astimezone(UTC).isoformat()
        results = [_map_account_search_row(row) for row in rows]
        return AccountSearchResponse(
            source=SourceEvidence(retrieved_at=retrieved_at),
            count=len(results),
            accounts=results,
        )

    def get_account_evidence(
        self,
        account_number: int,
        division: int,
        department: int,
    ) -> AccountEvidenceResponse:
        row = self._repository.get_account(account_number, division, department)
        if row is None:
            raise AccountNotFound(
                f"G/L account {account_number}/{division}/{department} was "
                "not found in MaddenCo."
            )

        retrieved_at = self._clock().astimezone(UTC).isoformat()
        identity = self._map_identity(row)

        return AccountEvidenceResponse(
            generated_at=retrieved_at,
            source=SourceEvidence(retrieved_at=retrieved_at),
            identity=identity,
            gaps=list(_GAPS),
        )

    @staticmethod
    def _map_identity(row: dict[str, Any]) -> AccountIdentityEvidence:
        return AccountIdentityEvidence(
            account_number=int(row["GMNB"]),
            division=int(row["GMNBDIV"]),
            department=int(row["GMNBDPT"]),
            company_number=_optional_int(row.get("GMNBCO")),
            description=_clean_text(row.get("GMDCRACT")),
            short_name=_clean_text(row.get("GMDCRACTSH")),
            debit_or_credit=_clean_text(row.get("GMCDDBCR")),
            account_type=_clean_text(row.get("GMTYPACT")),
            active=_clean_text(row.get("GMYNACTIVE")).upper() == "Y",
            requires_customer=_clean_text(row.get("GMYNCST")).upper() == "Y",
            requires_employee=_clean_text(row.get("GMYNEMP")).upper() == "Y",
            requires_job=_clean_text(row.get("GMYNJOB")).upper() == "Y",
            requires_po=_clean_text(row.get("GMYNPO")).upper() == "Y",
            date_created=_parse_erp_date(row.get("GMDTECRT")),
            date_changed=_parse_erp_date(row.get("GMDTECHG")),
            created_by=_clean_text(row.get("GMUSRCRT")),
            changed_by=_clean_text(row.get("GMUSRCHG")),
        )

    # ------------------------------------------------------------------
    # GMBL — balances
    # ------------------------------------------------------------------

    def get_account_balances(
        self,
        account_number: int,
        division: int,
        department: int,
        *,
        year_from: int,
        period_from: int,
        year_to: int,
        period_to: int,
    ) -> AccountBalanceEvidence:
        row = self._repository.get_account(account_number, division, department)
        if row is None:
            raise AccountNotFound(
                f"G/L account {account_number}/{division}/{department} was "
                "not found in MaddenCo."
            )

        rows = self._repository.get_balances(
            account_number,
            division,
            department,
            year_from=year_from,
            period_from=period_from,
            year_to=year_to,
            period_to=period_to,
        )
        balances = [
            AccountPeriodBalance(
                year=int(item["GBYR"]),
                period=int(item["GBPR"]),
                net_balance=_number(item.get("GBAMT")),
            )
            for item in rows
        ]
        return AccountBalanceEvidence(
            account_number=account_number,
            division=division,
            department=department,
            balances=balances,
        )

    # ------------------------------------------------------------------
    # GMAD / GTJT / GTJD — transaction drill-down
    # ------------------------------------------------------------------

    def get_account_transactions(
        self,
        account_number: int,
        division: int,
        department: int,
        *,
        year: int,
        period: int,
        limit: int = 200,
        offset: int = 0,
    ) -> TransactionEvidence:
        row = self._repository.get_account(account_number, division, department)
        if row is None:
            raise AccountNotFound(
                f"G/L account {account_number}/{division}/{department} was "
                "not found in MaddenCo."
            )

        transaction_rows = self._repository.get_posted_transactions(
            account_number,
            division,
            department,
            year=year,
            period=period,
            limit=limit,
            offset=offset,
        )
        transactions = [
            self._map_transaction(item) for item in transaction_rows
        ]

        reconciliation = self._build_reconciliation(
            account_number, division, department, year=year, period=period
        )

        unposted_rows = self._repository.get_unposted_journal_entry_lines(
            account_number, division, department
        )
        unposted = [self._map_unposted_line(item) for item in unposted_rows]

        return TransactionEvidence(
            account_number=account_number,
            division=division,
            department=department,
            year=year,
            period=period,
            count=len(transactions),
            transactions=transactions,
            reconciliation=reconciliation,
            unposted_journal_entry_lines=unposted,
        )

    @staticmethod
    def _map_transaction(row: dict[str, Any]) -> PostedTransaction:
        matched_je: JournalEntryHeaderReference | None = None
        if row.get("JE_REF") is not None:
            matched_je = JournalEntryHeaderReference(
                reference_number=int(row["JE_REF"]),
                period=int(row["JE_PR"]),
                year=int(row["JE_YR"]),
                company_number=_optional_int(row.get("JE_CO")),
                total_debit=_number(row.get("JE_TOTAL_DB")),
                total_credit=_number(row.get("JE_TOTAL_CR")),
                flag=_clean_text(row.get("JE_FLAG")),
            )

        return PostedTransaction(
            sequence=int(row["GASEQ"]),
            year=int(row["GAYR"]),
            period=int(row["GAPR"]),
            amount=_number(row.get("GAAMT")),
            debit_or_credit=_clean_text(row.get("GACDDBCR")),
            description=_clean_text(row.get("GADSR")),
            system_source=_clean_text(row.get("GACDSYS")),
            date_created=_parse_erp_date(row.get("GADTCRT")),
            date_posted=_parse_erp_date(row.get("GADTPST")),
            je_created_date=_parse_erp_date(row.get("GAJEDTECRT")),
            je_created_time=_clean_text(row.get("GAJETIMCRT")),
            je_created_by=_clean_text(row.get("GAJEUSRCRT")),
            je_created_workstation=_clean_text(row.get("GAJEWSCRT")),
            customer_number=_optional_int(row.get("GANBCST")),
            employee_number=_optional_int(row.get("GANBEMP")),
            job_number=_optional_int(row.get("GANBJOB")),
            po_number=_optional_int(row.get("GANBPO")),
            reference_number=_optional_int(row.get("GANBREF")),
            reconcile_reference_number=_optional_int(row.get("GANBREFRC")),
            memo_id=_optional_int(row.get("GAMEMOID")),
            matched_journal_entry=matched_je,
        )

    @staticmethod
    def _map_unposted_line(row: dict[str, Any]) -> UnpostedJournalEntryLine:
        return UnpostedJournalEntryLine(
            reference_number=int(row["GJHNBREF"]),
            sequence=int(row["GJDNBSEQ"]),
            account_number=int(row["GMNB"]),
            division=int(row["GMNBDIV"]),
            department=int(row["GMNBDPT"]),
            debit_amount=_number(row.get("GJDAMTDB")),
            credit_amount=_number(row.get("GJDAMTCR")),
            description=_clean_text(row.get("GJDDSC")),
            customer_number=_optional_int(row.get("GJDNBCST")),
            employee_number=_optional_int(row.get("GJDNBEMP")),
            job_number=_optional_int(row.get("GJDNBJOB")),
            po_number=_optional_int(row.get("GJDNBPO")),
        )

    def _build_reconciliation(
        self,
        account_number: int,
        division: int,
        department: int,
        *,
        year: int,
        period: int,
    ) -> ReconciliationCheck:
        totals_rows = self._repository.get_posted_totals(
            account_number, division, department, year=year, period=period
        )
        debit_total = 0.0
        credit_total = 0.0
        for item in totals_rows:
            side = _clean_text(item.get("GACDDBCR")).upper()
            amount = _number(item.get("TOTAL_AMT"))
            if side == "DB":
                debit_total = amount
            elif side == "CR":
                credit_total = amount

        posted_net_total = round(debit_total - credit_total, 2)

        balance_row = self._repository.get_balance_for_period(
            account_number, division, department, year, period
        )
        period_balance = (
            _optional_number(balance_row.get("GBAMT"))
            if balance_row is not None
            else None
        )
        difference = (
            round(posted_net_total - period_balance, 2)
            if period_balance is not None
            else None
        )

        return ReconciliationCheck(
            year=year,
            period=period,
            posted_debit_total=debit_total,
            posted_credit_total=credit_total,
            posted_net_total=posted_net_total,
            period_balance=period_balance,
            difference=difference,
        )

    # ------------------------------------------------------------------
    # GMSH / GMSD — standard journal entry templates
    # ------------------------------------------------------------------

    def list_templates(
        self, *, search: str = "", limit: int = 50
    ) -> StandardJournalEntryTemplateResponse:
        rows = self._repository.search_templates(search=search, limit=limit)
        retrieved_at = self._clock().astimezone(UTC).isoformat()
        templates = [
            StandardJournalEntryTemplateSummary(
                name=_clean_text(row.get("GSJNAME")),
                description=_clean_text(row.get("GSJHDSC")),
                je_description=_clean_text(row.get("GSJHDSCJE")),
                status_code=_clean_text(row.get("GSJHCDSTAT")),
            )
            for row in rows
        ]
        return StandardJournalEntryTemplateResponse(
            source=SourceEvidence(retrieved_at=retrieved_at),
            count=len(templates),
            templates=templates,
        )

    def get_template_detail(
        self, name: str
    ) -> StandardJournalEntryTemplateDetail:
        header = self._repository.get_template(name)
        if header is None:
            raise TemplateNotFound(
                f"Standard journal entry template '{name}' was not found "
                "in MaddenCo."
            )

        line_rows = self._repository.get_template_lines(
            _clean_text(header.get("GSJNAME")) or name
        )
        lines = [
            StandardJournalEntryTemplateLine(
                sequence=int(item["GSJDNBSEQ"]),
                account_number=int(item["GMNB"]),
                division=int(item["GMNBDIV"]),
                department=int(item["GMNBDPT"]),
                debit_amount=_number(item.get("GSJDAMTDB")),
                credit_amount=_number(item.get("GSJDAMTCR")),
                description=_clean_text(item.get("GSJDDSCJE")),
                customer_number=_optional_int(item.get("GSJDNBCST")),
                employee_number=_optional_int(item.get("GSJDNBEMP")),
                job_number=_optional_int(item.get("GSJDNBJOB")),
                po_number=_optional_int(item.get("GSJDNBPO")),
            )
            for item in line_rows
        ]

        return StandardJournalEntryTemplateDetail(
            name=_clean_text(header.get("GSJNAME")),
            description=_clean_text(header.get("GSJHDSC")),
            je_description=_clean_text(header.get("GSJHDSCJE")),
            status_code=_clean_text(header.get("GSJHCDSTAT")),
            next_sequence_number=_optional_int(header.get("GSJHNBSEQN")),
            created_by=_clean_text(header.get("GSJHUSRCRT")),
            last_changed_by=_clean_text(header.get("GSJHUSRLST")),
            lines=lines,
            line_debit_total=round(
                sum(line.debit_amount for line in lines), 2
            ),
            line_credit_total=round(
                sum(line.credit_amount for line in lines), 2
            ),
        )

    # ------------------------------------------------------------------
    # Local append-only reconciliation notes
    # ------------------------------------------------------------------

    def list_notes(self, account_number: int) -> GLNoteHistoryResponse:
        records = [
            GLNoteRecord(**record)
            for record in self._notes_repository.list_notes(account_number)
        ]
        return GLNoteHistoryResponse(
            account_number=account_number,
            count=len(records),
            notes=records,
        )

    def create_note(
        self,
        account_number: int,
        payload: GLNoteCreate,
    ) -> GLNoteRecord:
        account_row = self._repository.get_account(
            account_number, payload.division, payload.department
        )
        if account_row is None:
            raise AccountNotFound(
                f"G/L account {account_number}/{payload.division}/"
                f"{payload.department} was not found in MaddenCo."
            )

        identity = self._map_identity(account_row)
        retrieved_at = self._clock().astimezone(UTC).isoformat()

        snapshot: dict[str, Any] = {
            "identity": identity.model_dump(mode="json"),
            "source": SourceEvidence(retrieved_at=retrieved_at).model_dump(
                mode="json"
            ),
        }
        if payload.period is not None and payload.year is not None:
            snapshot["reconciliation"] = self._build_reconciliation(
                account_number,
                payload.division,
                payload.department,
                year=payload.year,
                period=payload.period,
            ).model_dump(mode="json")

        created_at = self._clock().astimezone(UTC).isoformat()
        record = {
            "note_id": self._note_id_factory(),
            "account_number": account_number,
            "division": payload.division,
            "department": payload.department,
            "period": payload.period,
            "year": payload.year,
            "account_description": identity.description,
            "author_identity": payload.author_identity,
            "note": payload.note,
            "created_at": created_at,
            "source_as_of": retrieved_at,
            "actor_identity_source": "operator_supplied",
            "actor_authority_status": "not_independently_verified",
            "note_classification": "professional_workflow_metadata",
            "decision_effect": "none",
            "evidence_snapshot": snapshot,
        }
        return GLNoteRecord(**self._notes_repository.create_note(record))


general_ledger_service = GeneralLedgerService()
