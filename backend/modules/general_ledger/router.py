from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query, status

from .schemas import (
    AccountBalanceEvidence,
    AccountEvidenceResponse,
    AccountSearchResponse,
    GLNoteCreate,
    GLNoteHistoryResponse,
    GLNoteRecord,
    StandardJournalEntryTemplateDetail,
    StandardJournalEntryTemplateResponse,
    TransactionEvidence,
)
from .service import (
    AccountNotFound,
    GeneralLedgerService,
    TemplateNotFound,
    general_ledger_service,
)


router = APIRouter(
    prefix="/api/v1/general-ledger",
    tags=["General Ledger"],
)


def _account_number_path() -> int:
    return Path(ge=1)


@router.get("/health")
def get_health() -> dict:
    return {"status": "ok", "module": "general_ledger"}


@router.get("/accounts/search", response_model=AccountSearchResponse)
def search_accounts(
    q: str = Query(default="", max_length=100),
    active_only: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AccountSearchResponse:
    return general_ledger_service.search_accounts(
        search=q,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/accounts/{account_number}",
    response_model=AccountEvidenceResponse,
)
def get_account_evidence(
    account_number: int = _account_number_path(),
    division: int = Query(default=0, ge=0),
    department: int = Query(default=0, ge=0),
) -> AccountEvidenceResponse:
    try:
        return general_ledger_service.get_account_evidence(
            account_number, division, department
        )
    except AccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "account_not_found", "message": str(exc)},
        ) from exc


@router.get(
    "/accounts/{account_number}/balances",
    response_model=AccountBalanceEvidence,
)
def get_account_balances(
    account_number: int = _account_number_path(),
    division: int = Query(default=0, ge=0),
    department: int = Query(default=0, ge=0),
    year_from: int = Query(..., ge=1900, le=2999),
    period_from: int = Query(default=0, ge=0, le=13),
    year_to: int = Query(..., ge=1900, le=2999),
    period_to: int = Query(default=13, ge=0, le=13),
) -> AccountBalanceEvidence:
    try:
        return general_ledger_service.get_account_balances(
            account_number,
            division,
            department,
            year_from=year_from,
            period_from=period_from,
            year_to=year_to,
            period_to=period_to,
        )
    except AccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "account_not_found", "message": str(exc)},
        ) from exc


@router.get(
    "/accounts/{account_number}/transactions",
    response_model=TransactionEvidence,
)
def get_account_transactions(
    account_number: int = _account_number_path(),
    division: int = Query(default=0, ge=0),
    department: int = Query(default=0, ge=0),
    year: int = Query(..., ge=1900, le=2999),
    period: int = Query(..., ge=0, le=13),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> TransactionEvidence:
    try:
        return general_ledger_service.get_account_transactions(
            account_number,
            division,
            department,
            year=year,
            period=period,
            limit=limit,
            offset=offset,
        )
    except AccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "account_not_found", "message": str(exc)},
        ) from exc


@router.get(
    "/accounts/{account_number}/notes",
    response_model=GLNoteHistoryResponse,
)
def get_account_notes(
    account_number: int = _account_number_path(),
) -> GLNoteHistoryResponse:
    return general_ledger_service.list_notes(account_number)


@router.post(
    "/accounts/{account_number}/notes",
    response_model=GLNoteRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_account_note(
    payload: GLNoteCreate,
    account_number: int = _account_number_path(),
) -> GLNoteRecord:
    try:
        return general_ledger_service.create_note(account_number, payload)
    except AccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "account_not_found", "message": str(exc)},
        ) from exc


@router.get(
    "/templates",
    response_model=StandardJournalEntryTemplateResponse,
)
def list_templates(
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
) -> StandardJournalEntryTemplateResponse:
    return general_ledger_service.list_templates(search=q, limit=limit)


@router.get(
    "/templates/{name}",
    response_model=StandardJournalEntryTemplateDetail,
)
def get_template(name: str) -> StandardJournalEntryTemplateDetail:
    try:
        return general_ledger_service.get_template_detail(name)
    except TemplateNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "template_not_found", "message": str(exc)},
        ) from exc
