from __future__ import annotations

import os
import re
from collections import defaultdict
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.database import madden_database
from customer_match_service import (
    CustomerMatchInput,
    normalize_address,
    normalize_invoice,
    normalize_phone,
    normalize_postal,
    normalize_text,
    rank_customer_matches,
)


router = APIRouter(
    prefix="/api/v1/customer-match",
    tags=["Customer Matching"],
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9_$#@]+$")
_SCHEMA = os.getenv("MADDEN_SCHEMA", "DTA273")
_CUSTOMER_TABLE = os.getenv("MADDEN_CUSTOMER_TABLE", "TMCUST")

_COLUMN_ALIASES = {
    "customer_number": (
        "CUNUMBER",
        "CUSTOMER_NUMBER",
        "CUST_NUMBER",
        "CUSTNO",
    ),
    "customer_name": (
        "CUNAME",
        "CUSTOMER_NAME",
        "CUST_NAME",
        "NAME",
    ),
    "phone": (
        "CUPHONE",
        "CUPHONENO",
        "CUPHON",
        "PHONE",
        "PHONE_NUMBER",
    ),
    "address_line_1": (
        "CUADDRESS",
        "CUADDRESS1",
        "CUADDR1",
        "CUADDR",
        "CUADR1",
        "ADDRESS1",
        "ADDRESS_LINE_1",
    ),
    "address_line_2": (
        "CUADDRESS2",
        "CUADDR2",
        "CUADR2",
        "ADDRESS2",
        "ADDRESS_LINE_2",
    ),
    "city": (
        "CUCITY",
        "CITY",
    ),
    "state": (
        "CUSTATE",
        "CUSTATECD",
        "CUST",
        "STATE",
        "STATE_CODE",
    ),
    "postal_code": (
        "CUZIP",
        "CUZIPCODE",
        "CUZIPCD",
        "CUPOSTAL",
        "ZIP",
        "ZIP_CODE",
        "POSTAL_CODE",
    ),
    "enterprise_number": (
        "CUNUMENT",
    ),
}

_INVOICE_COLUMN_MARKERS = (
    "INVOICE",
    "INVNUM",
    "INVNBR",
    "INVNO",
    "NUMINV",
)
_CUSTOMER_COLUMN_MARKERS = (
    "CUNUMBER",
    "CUSTOMER_NUMBER",
    "CUSTNUM",
    "CUSTNO",
    "NUMCST",
)


class CustomerMatchRequest(BaseModel):
    invoice_numbers: list[str] = Field(default_factory=list, max_length=100)
    phone: str | None = Field(default=None, max_length=80)
    address_line_1: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=40)
    postal_code: str | None = Field(default=None, max_length=40)
    customer_name: str | None = Field(default=None, max_length=200)
    search_text: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=8, ge=1, le=25)


class BulkInvoiceOwnerRequest(BaseModel):
    invoice_numbers: list[str] = Field(default_factory=list, max_length=500)


def _identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Unsafe database identifier: {value!r}")
    return f"`{value}`"


def _load_table_columns(schema: str, table: str) -> dict[str, str]:
    rows = madden_database.fetch_all(
        """
        SELECT COLUMN_NAME AS column_name
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = %s
        """,
        (schema, table),
    )
    return {
        str(row["column_name"]).upper(): str(row["column_name"])
        for row in rows
    }


@lru_cache(maxsize=1)
def _resolve_customer_columns() -> dict[str, str | None]:
    available = _load_table_columns(_SCHEMA, _CUSTOMER_TABLE)
    resolved: dict[str, str | None] = {}
    for field, aliases in _COLUMN_ALIASES.items():
        configured = os.getenv(f"ETOP_CUSTOMER_{field.upper()}_COLUMN")
        choices = ((configured,) if configured else ()) + aliases
        resolved[field] = next(
            (
                available[choice.upper()]
                for choice in choices
                if choice and choice.upper() in available
            ),
            None,
        )
    return resolved


def _select_customer_records(
    columns: dict[str, str | None],
    request: CustomerMatchRequest,
    owner_numbers: set[str],
) -> list[dict[str, Any]]:
    number_column = columns["customer_number"]
    name_column = columns["customer_name"]
    if not number_column or not name_column:
        raise HTTPException(
            status_code=503,
            detail=(
                "TMCUST customer-number or customer-name columns could not "
                "be resolved. Configure ETOP_CUSTOMER_*_COLUMN values."
            ),
        )

    select_parts = []
    for field in (
        "customer_number",
        "customer_name",
        "phone",
        "address_line_1",
        "address_line_2",
        "city",
        "state",
        "postal_code",
        "enterprise_number",
    ):
        column = columns[field]
        if column:
            select_parts.append(f"{_identifier(column)} AS {_identifier(field)}")
        else:
            select_parts.append(f"'' AS {_identifier(field)}")

    predicates: list[str] = []
    parameters: list[Any] = []

    if owner_numbers:
        placeholders = ", ".join(["%s"] * len(owner_numbers))
        predicates.append(
            f"CAST({_identifier(number_column)} AS CHAR) IN ({placeholders})"
        )
        parameters.extend(sorted(owner_numbers))

    search_text = str(request.search_text or "").strip()
    if search_text:
        digits = re.sub(r"\D", "", search_text)
        if digits:
            predicates.append(
                f"CAST({_identifier(number_column)} AS CHAR) LIKE %s"
            )
            parameters.append(f"{digits}%")
        predicates.append(
            f"UPPER(TRIM({_identifier(name_column)})) LIKE %s"
        )
        parameters.append(f"%{normalize_text(search_text)}%")

    phone = normalize_phone(request.phone)
    if phone and columns["phone"]:
        phone_expression = (
            "REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(" 
            f"CAST({_identifier(columns['phone'])} AS CHAR), "
            "'-', ''), '(', ''), ')', ''), ' ', ''), '.', '')"
        )
        predicates.append(
            f"{phone_expression} LIKE %s"
        )
        parameters.append(f"%{phone[-7:]}%")

    postal = normalize_postal(request.postal_code)
    if postal and columns["postal_code"]:
        predicates.append(
            f"UPPER(CAST({_identifier(columns['postal_code'])} AS CHAR)) "
            "LIKE %s"
        )
        parameters.append(f"{postal}%")

    address_words = [
        word
        for word in normalize_text(request.address_line_1).split()
        if len(word) >= 4 and not word.isdigit()
    ]
    if address_words and columns["address_line_1"]:
        strongest_word = max(address_words, key=len)
        predicates.append(
            f"UPPER(CAST({_identifier(columns['address_line_1'])} AS CHAR)) "
            "LIKE %s"
        )
        parameters.append(f"%{strongest_word}%")

    name_words = [
        word
        for word in normalize_text(request.customer_name).split()
        if len(word) >= 3
    ]
    if name_words:
        predicates.append(
            f"UPPER(TRIM({_identifier(name_column)})) LIKE %s"
        )
        parameters.append(f"%{name_words[0]}%")

    if not predicates:
        return []

    query = f"""
        SELECT {", ".join(select_parts)}
        FROM {_identifier(_SCHEMA)}.{_identifier(_CUSTOMER_TABLE)}
        WHERE {" OR ".join(f"({predicate})" for predicate in predicates)}
        LIMIT 250
    """
    return madden_database.fetch_all(query, tuple(parameters))


def _select_exact_phone_records(
    columns: dict[str, str | None],
    phone_value: str,
) -> tuple[list[dict[str, Any]], bool]:
    """Return the bounded universe that can contain an exact phone match.

    SQL uses the normalized phone's last seven digits only to bound the read.
    Python performs the exact ten-digit comparison. Reaching 251 rows makes
    completeness false, so the caller cannot claim uniqueness from a
    truncated set.
    """

    normalized_phone = normalize_phone(phone_value)
    phone_column = columns.get("phone")
    if len(normalized_phone) != 10 or not phone_column:
        return [], True

    select_parts = []
    for field in (
        "customer_number",
        "customer_name",
        "phone",
        "address_line_1",
        "address_line_2",
        "city",
        "state",
        "postal_code",
        "enterprise_number",
    ):
        column = columns.get(field)
        if column:
            select_parts.append(f"{_identifier(column)} AS {_identifier(field)}")
        else:
            select_parts.append(f"'' AS {_identifier(field)}")

    phone_expression = (
        "REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE("
        f"CAST({_identifier(phone_column)} AS CHAR), "
        "'-', ''), '(', ''), ')', ''), ' ', ''), '.', ''), '/', ''), "
        "'+', '')"
    )
    query = f"""
        SELECT {", ".join(select_parts)}
        FROM {_identifier(_SCHEMA)}.{_identifier(_CUSTOMER_TABLE)}
        WHERE {phone_expression} LIKE %s
        LIMIT 251
    """
    rows = madden_database.fetch_all(
        query,
        (f"%{normalized_phone[-7:]}%",),
    )
    return rows[:250], len(rows) < 251


def _select_exact_phone_postal_records(
    columns: dict[str, str | None],
    phone_value: str,
    postal_value: str,
) -> tuple[list[dict[str, Any]], bool]:
    """Compatibility wrapper for callers that still request phone plus ZIP.

    Completeness is proved over the wider exact-phone candidate universe,
    then the returned rows are narrowed by first-five ZIP in Python.
    """

    rows, complete = _select_exact_phone_records(columns, phone_value)
    normalized_postal = normalize_postal(postal_value)
    if len(normalized_postal) != 5:
        return [], complete
    return (
        [
            row
            for row in rows
            if normalize_postal(row.get("postal_code")) == normalized_postal
        ],
        complete,
    )


def _select_exact_address_postal_records(
    columns: dict[str, str | None],
    address_value: str,
    postal_value: str,
) -> tuple[list[dict[str, Any]], bool]:
    """Return the bounded exact street-and-ZIP candidate universe.

    The ERP query is bounded by the first five ZIP digits. Python applies the
    shared exact street normalization. Reaching 251 rows fails completeness,
    so a truncated ZIP population can never establish uniqueness.
    """

    normalized_address = normalize_address(address_value)
    normalized_postal = normalize_postal(postal_value)
    address_column = columns.get("address_line_1")
    postal_column = columns.get("postal_code")
    if (
        not normalized_address
        or len(normalized_postal) != 5
        or not address_column
        or not postal_column
    ):
        return [], True

    select_parts = []
    for field in (
        "customer_number",
        "customer_name",
        "phone",
        "address_line_1",
        "address_line_2",
        "city",
        "state",
        "postal_code",
        "enterprise_number",
    ):
        column = columns.get(field)
        if column:
            select_parts.append(f"{_identifier(column)} AS {_identifier(field)}")
        else:
            select_parts.append(f"'' AS {_identifier(field)}")

    postal_expression = (
        "REPLACE(REPLACE("
        f"CAST({_identifier(postal_column)} AS CHAR), '-', ''), ' ', '')"
    )
    query = f"""
        SELECT {", ".join(select_parts)}
        FROM {_identifier(_SCHEMA)}.{_identifier(_CUSTOMER_TABLE)}
        WHERE LEFT({postal_expression}, 5) = %s
        LIMIT 251
    """
    rows = madden_database.fetch_all(query, (normalized_postal,))
    complete = len(rows) < 251
    exact_rows = [
        row
        for row in rows[:250]
        if normalize_address(row.get("address_line_1"))
        == normalized_address
        and normalize_postal(row.get("postal_code"))
        == normalized_postal
    ]
    return exact_rows, complete


def _select_enterprise_customer_records(
    columns: dict[str, str | None],
    customer_number: str,
    enterprise_number: str,
) -> list[dict[str, Any]]:
    """Read the matched TMCUST account and every CUNUMENT-linked account."""

    number_column = columns["customer_number"]
    name_column = columns["customer_name"]
    enterprise_column = columns.get("enterprise_number")
    if not number_column or not name_column:
        raise HTTPException(
            status_code=503,
            detail=(
                "TMCUST customer-number or customer-name columns could not "
                "be resolved. Configure ETOP_CUSTOMER_*_COLUMN values."
            ),
        )

    select_parts = []
    for field in (
        "customer_number",
        "customer_name",
        "phone",
        "address_line_1",
        "address_line_2",
        "city",
        "state",
        "postal_code",
        "enterprise_number",
    ):
        column = columns.get(field)
        if column:
            select_parts.append(f"{_identifier(column)} AS {_identifier(field)}")
        else:
            select_parts.append(f"'' AS {_identifier(field)}")

    normalized_customer = str(customer_number or "").strip().removesuffix(
        ".0"
    )
    normalized_enterprise = str(
        enterprise_number or ""
    ).strip().removesuffix(".0")
    if not normalized_customer:
        return []

    predicates = [
        f"CAST({_identifier(number_column)} AS CHAR) = %s",
    ]
    parameters: list[Any] = [normalized_customer]
    if normalized_enterprise and normalized_enterprise != "0":
        predicates.append(
            f"CAST({_identifier(number_column)} AS CHAR) = %s"
        )
        parameters.append(normalized_enterprise)
        if enterprise_column:
            predicates.append(
                f"CAST({_identifier(enterprise_column)} AS CHAR) = %s"
            )
            parameters.append(normalized_enterprise)

    query = f"""
        SELECT {", ".join(select_parts)}
        FROM {_identifier(_SCHEMA)}.{_identifier(_CUSTOMER_TABLE)}
        WHERE {" OR ".join(f"({predicate})" for predicate in predicates)}
        LIMIT 251
    """
    return madden_database.fetch_all(query, tuple(parameters))


@lru_cache(maxsize=1)
def _discover_invoice_sources() -> list[tuple[str, str, str]]:
    rows = madden_database.fetch_all(
        """
        SELECT TABLE_NAME AS table_name, COLUMN_NAME AS column_name
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND (
            UPPER(COLUMN_NAME) LIKE '%%INV%%'
            OR UPPER(COLUMN_NAME) LIKE '%%CUST%%'
            OR UPPER(COLUMN_NAME) LIKE '%%CST%%'
            OR UPPER(COLUMN_NAME) = 'CUNUMBER'
          )
        ORDER BY TABLE_NAME, ORDINAL_POSITION
        """,
        (_SCHEMA,),
    )
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        grouped[str(row["table_name"])].append(str(row["column_name"]))

    sources: list[tuple[str, str, str]] = []
    for table, table_columns in grouped.items():
        invoice_columns = [
            column
            for column in table_columns
            if any(marker in column.upper() for marker in _INVOICE_COLUMN_MARKERS)
        ]
        customer_columns = [
            column
            for column in table_columns
            if any(marker in column.upper() for marker in _CUSTOMER_COLUMN_MARKERS)
        ]
        for invoice_column in invoice_columns[:2]:
            for customer_column in customer_columns[:2]:
                sources.append((table, invoice_column, customer_column))
    return sources[:30]


def _find_invoice_owners(
    invoice_numbers: list[str],
) -> tuple[dict[str, set[str]], list[str]]:
    normalized = {
        normalize_invoice(invoice)
        for invoice in invoice_numbers
        if normalize_invoice(invoice)
    }
    owners: dict[str, set[str]] = {
        invoice: set()
        for invoice in normalized
    }
    warnings: list[str] = []
    if not normalized:
        return owners, warnings

    try:
        sources = _discover_invoice_sources()
    except Exception as exc:
        return owners, [f"Invoice-source discovery was unavailable: {exc}"]

    placeholders = ", ".join(["%s"] * len(normalized))
    for table, invoice_column, customer_column in sources:
        query = f"""
            SELECT
                CAST({_identifier(invoice_column)} AS CHAR) AS invoice_number,
                CAST({_identifier(customer_column)} AS CHAR) AS customer_number
            FROM {_identifier(_SCHEMA)}.{_identifier(table)}
            WHERE TRIM(LEADING '0' FROM CAST(
                {_identifier(invoice_column)} AS CHAR
            )) IN ({placeholders})
            LIMIT 100
        """
        try:
            rows = madden_database.fetch_all(
                query,
                tuple(sorted(normalized)),
            )
        except Exception:
            continue

        for row in rows:
            invoice = normalize_invoice(row.get("invoice_number"))
            customer = str(row.get("customer_number") or "").strip()
            if customer.endswith(".0"):
                customer = customer[:-2]
            if invoice in owners and customer:
                owners[invoice].add(customer)

    if normalized and not any(owners.values()):
        warnings.append(
            "No supplied invoice number was found in the discoverable ERP "
            "invoice tables; contact details were used instead."
        )
    return owners, warnings


@router.post("/resolve")
def resolve_customer_match(
    request: CustomerMatchRequest,
) -> dict[str, Any]:
    if not any(
        (
            request.invoice_numbers,
            request.phone,
            request.address_line_1,
            request.postal_code,
            request.customer_name,
            request.search_text,
        )
    ):
        raise HTTPException(
            status_code=400,
            detail="Provide an invoice, phone, address, ZIP, name, or search value.",
        )

    try:
        columns = _resolve_customer_columns()
        valid_invoice_numbers = list(
            dict.fromkeys(
                invoice
                for value in request.invoice_numbers
                if (invoice := normalize_invoice(value))
            )
        )
        invoice_owners, warnings = _find_invoice_owners(
            valid_invoice_numbers
        )
        ignored_invoice_count = (
            len(request.invoice_numbers)
            - len(valid_invoice_numbers)
        )
        if ignored_invoice_count:
            warnings.insert(
                0,
                f"Ignored {ignored_invoice_count} OCR invoice value(s) "
                "because ERP invoices must contain exactly 8 or 9 digits.",
            )
        owner_numbers = {
            customer
            for customers in invoice_owners.values()
            for customer in customers
        }
        customers = _select_customer_records(
            columns,
            request,
            owner_numbers,
        )
        contact_rows, contact_candidate_complete = (
            _select_exact_phone_records(
                columns,
                request.phone or "",
            )
        )
        address_rows, address_candidate_complete = (
            _select_exact_address_postal_records(
                columns,
                request.address_line_1 or "",
                request.postal_code or "",
            )
        )
        customer_by_number = {
            str(customer.get("customer_number") or "").removesuffix(".0"): (
                customer
            )
            for customer in (*customers, *contact_rows, *address_rows)
            if str(customer.get("customer_number") or "").strip()
        }
        customers = list(customer_by_number.values())
        if not contact_candidate_complete:
            warnings.append(
                "The bounded exact-phone candidate query was incomplete; "
                "contact evidence cannot select a customer."
            )
        if not address_candidate_complete:
            warnings.append(
                "The bounded street-and-ZIP candidate query was incomplete; "
                "address evidence cannot select a customer."
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"ERP customer matching is unavailable: {exc}",
        ) from exc

    result = rank_customer_matches(
        customers,
        CustomerMatchInput(
            invoice_numbers=tuple(valid_invoice_numbers),
            phone=request.phone or "",
            address_line_1=request.address_line_1 or "",
            city=request.city or "",
            state=request.state or "",
            postal_code=request.postal_code or "",
            customer_name=request.customer_name or "",
            search_text=request.search_text or "",
        ),
        invoice_owners,
        request.limit,
        contact_candidate_complete=contact_candidate_complete,
        address_candidate_complete=address_candidate_complete,
    )
    return {
        **result,
        "warnings": warnings,
        "matching_priority": [
            "invoice ownership",
            "one unique exact normalized phone without contact conflict",
            "phone and first five ZIP digits when a phone is shared",
            "one unique exact normalized street and first five ZIP digits",
            "name as supporting evidence only",
        ],
    }


@router.post("/resolve-invoices")
def resolve_invoice_owners(
    request: BulkInvoiceOwnerRequest,
) -> dict[str, Any]:
    valid_invoice_numbers = list(
        dict.fromkeys(
            invoice
            for value in request.invoice_numbers
            if (invoice := normalize_invoice(value))
        )
    )
    if not valid_invoice_numbers:
        raise HTTPException(
            status_code=400,
            detail=(
                "Provide at least one 8- or 9-digit ERP invoice "
                "number."
            ),
        )

    try:
        invoice_owners, warnings = _find_invoice_owners(
            valid_invoice_numbers
        )
        owner_numbers = {
            customer
            for customers in invoice_owners.values()
            for customer in customers
        }
        customers = _select_customer_records(
            _resolve_customer_columns(),
            CustomerMatchRequest(),
            owner_numbers,
        )
        source_count = len(_discover_invoice_sources())
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Bulk ERP invoice resolution is unavailable: {exc}",
        ) from exc

    customer_records = []
    for customer in customers:
        customer_records.append({
            "customer_number": str(
                customer.get("customer_number") or ""
            ).removesuffix(".0"),
            "customer_name": str(
                customer.get("customer_name") or ""
            ).strip(),
            "phone": str(customer.get("phone") or "").strip(),
            "address_line_1": str(
                customer.get("address_line_1") or ""
            ).strip(),
            "address_line_2": str(
                customer.get("address_line_2") or ""
            ).strip(),
            "city": str(customer.get("city") or "").strip(),
            "state": str(customer.get("state") or "").strip(),
            "postal_code": str(
                customer.get("postal_code") or ""
            ).strip(),
            "enterprise_number": str(
                customer.get("enterprise_number") or ""
            ).strip().removesuffix(".0"),
        })

    return {
        "invoice_owners": {
            invoice: sorted(invoice_owners.get(invoice, set()))
            for invoice in valid_invoice_numbers
        },
        "customers": customer_records,
        "unresolved_invoice_numbers": [
            invoice
            for invoice in valid_invoice_numbers
            if not invoice_owners.get(invoice)
        ],
        "warnings": warnings,
        "invoice_count": len(valid_invoice_numbers),
        "source_query_count": source_count,
        "read_only": True,
    }
