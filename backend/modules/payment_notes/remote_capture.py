"""Strict parser and exact balancing validation for remote-capture evidence."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .matching import BankPaymentItem, normalize_check_number
from .route_reference import normalize_store


REMOTE_CAPTURE_PARSER_VERSION = "payment-notes-remote-capture@1.1.0"
VIRTUAL_CREDIT_ITEM_TYPE = "Virtual Credit"
SUPPORTED_PHYSICAL_ITEM_TYPES = frozenset({"Business Check", "Personal Check"})
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_SOURCE_ROWS = 25_000
REQUIRED_HEADERS = (
    "createDate",
    "transmitTime",
    "postingCycle",
    "location",
    "locationNo",
    "accountName",
    "depositNo",
    "itemType",
    "amount",
    "accountNo",
    "routingNo",
    "checkNo",
    "CaptureChannel",
)
SENSITIVE_BANK_FIELDS = frozenset({"accountNo", "routingNo"})
REDACTED_BANK_VALUE = "[REDACTED]"
OPTIONAL_TRAILING_HEADERS = ("checkNo", "CaptureChannel")


class RemoteCaptureError(ValueError):
    """Remote-capture input cannot be preserved and interpreted safely."""


@dataclass(frozen=True)
class ParsedBankRow:
    source_row_number: int
    source_record_sha256: str
    raw_values: dict[str, str]
    deposit_key: str
    location_key: str
    store_number: str
    location_name: str
    account_name: str
    create_business_date: str
    deposit_number: str
    item_type: str
    amount: Decimal
    raw_amount: str
    raw_check_number: str
    normalized_check_number: str
    is_balancing_item: bool
    warnings: tuple[str, ...]

    def redacted_raw_values(self) -> dict[str, str]:
        return {
            key: REDACTED_BANK_VALUE if key in SENSITIVE_BANK_FIELDS else value
            for key, value in self.raw_values.items()
        }

    def public_dict(self, item_id: str) -> dict[str, Any]:
        return {
            "item_id": item_id,
            "source_row_number": self.source_row_number,
            "source_record_sha256": self.source_record_sha256,
            "deposit_key": self.deposit_key,
            "location_key": self.location_key,
            "store_number": self.store_number,
            "location_name": self.location_name,
            "account_name": self.account_name,
            "create_business_date": self.create_business_date,
            "deposit_number": self.deposit_number,
            "item_type": self.item_type,
            "amount": str(self.amount),
            "raw_amount": self.raw_amount,
            "raw_check_number": self.raw_check_number,
            "normalized_check_number": self.normalized_check_number,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class QuarantinedBankRow:
    source_row_number: int
    source_record_sha256: str
    raw_values: tuple[str, ...]
    reason_codes: tuple[str, ...]
    provisional_deposit_key: str
    provisional_item_type: str
    provisional_amount: Decimal | None
    provisional_is_physical: bool

    def redacted_raw_values(self) -> tuple[str, ...]:
        values = list(self.raw_values)
        for field_name in SENSITIVE_BANK_FIELDS:
            position = REQUIRED_HEADERS.index(field_name)
            if position < len(values):
                values[position] = REDACTED_BANK_VALUE
        return tuple(values)

    def public_dict(self) -> dict[str, Any]:
        return {
            "source_row_number": self.source_row_number,
            "source_record_sha256": self.source_record_sha256,
            "reason_codes": list(self.reason_codes),
            "provisional_deposit_key": self.provisional_deposit_key,
            "provisional_item_type": self.provisional_item_type,
            "provisional_amount": (
                str(self.provisional_amount)
                if self.provisional_amount is not None
                else None
            ),
            "provisional_is_physical": self.provisional_is_physical,
        }


@dataclass(frozen=True)
class DepositBalance:
    deposit_key: str
    location_key: str
    store_number: str
    location_name: str
    account_name: str
    create_business_date: str
    deposit_number: str
    physical_item_count: int
    balancing_item_count: int
    quarantined_row_count: int
    physical_total: Decimal
    balancing_total: Decimal
    difference: Decimal
    status: str
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("physical_total", "balancing_total", "difference"):
            payload[key] = str(payload[key])
        payload["warnings"] = list(self.warnings)
        return payload


@dataclass(frozen=True)
class ParsedRemoteCapture:
    source_name: str
    source_sha256: str
    source_size: int
    parser_version: str
    source_row_count: int
    rows: tuple[ParsedBankRow, ...]
    quarantined_rows: tuple[QuarantinedBankRow, ...]
    omitted_row_count: int
    deposits: tuple[DepositBalance, ...]


def _strict_positive_money(value: str) -> Decimal:
    text = value.strip()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", text):
        raise ValueError("Amount must be a positive ordinary decimal with at most 2 places.")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Amount is not a valid decimal.") from exc
    if not amount.is_finite() or amount <= Decimal("0.00"):
        raise ValueError("Amount must be greater than zero.")
    return amount.quantize(Decimal("0.01"))


def _create_business_date(raw_value: str) -> str:
    text = raw_value.strip()
    for pattern in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError("createDate is not in the supported bank timestamp format.")


# Bank remote-capture store numbers that do not match this platform's
# canonical store/location numbering. Confirmed by the business owner:
# the bank reports Detroit as store "05", but the canonical store number
# used elsewhere in ETOP (route references, etc.) is "4" / "L4".
_LOCATION_NUMBER_OVERRIDES: dict[str, tuple[str, str]] = {
    "5": ("4", "L4"),
}

# Store number "00"/"0" is an administrative (Corporate) posting, not a
# real store deposit - rows for it are omitted entirely, not quarantined.
_EXCLUDED_STORE_NUMBERS = frozenset({"0"})


def _location(raw_value: str) -> tuple[str, str, str]:
    text = raw_value.strip()
    match = re.fullmatch(r"\s*([0-9]+)\s*-\s*(.+?)\s*", text)
    if not match:
        raise ValueError("location must contain '<store> - <name>'.")
    raw_store = match.group(1)
    name = match.group(2).strip()
    store = normalize_store(raw_store)
    if not store or not name:
        raise ValueError("location has no usable store number or name.")
    if store in _LOCATION_NUMBER_OVERRIDES:
        store, location_key = _LOCATION_NUMBER_OVERRIDES[store]
    else:
        location_key = f"L{str(int(raw_store)).zfill(2)}"
    return store, location_key, name


def _normalized_account_name(value: str) -> str:
    return " ".join(value.strip().upper().split())


def _record_hash(values: list[str] | tuple[str, ...] | dict[str, str]) -> str:
    canonical = json.dumps(values, sort_keys=isinstance(values, dict), separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _deposit_key(
    account_name: str,
    location_key: str,
    deposit_number: str,
    create_business_date: str,
) -> str:
    return hashlib.sha256(
        "\x1f".join(
            (
                _normalized_account_name(account_name),
                location_key,
                deposit_number.strip(),
                create_business_date,
            )
        ).encode("utf-8")
    ).hexdigest()


def _provisional_deposit_key(values: list[str]) -> str:
    if len(values) < 9:
        return ""
    try:
        create_date = _create_business_date(values[0])
        _, location_key, _ = _location(values[3])
        account_name = values[5].strip()
        deposit_number = values[6].strip()
        if not account_name or not deposit_number:
            return ""
        return _deposit_key(account_name, location_key, deposit_number, create_date)
    except (ValueError, IndexError):
        return ""


def _quarantine(
    row_number: int,
    values: list[str],
    *reason_codes: str,
) -> QuarantinedBankRow:
    item_type = values[7].strip() if len(values) > 7 else ""
    try:
        provisional_amount = _strict_positive_money(values[8]) if len(values) > 8 else None
    except ValueError:
        provisional_amount = None
    return QuarantinedBankRow(
        source_row_number=row_number,
        source_record_sha256=_record_hash(values),
        raw_values=tuple(values),
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        provisional_deposit_key=_provisional_deposit_key(values),
        provisional_item_type=item_type,
        provisional_amount=provisional_amount,
        provisional_is_physical=item_type in SUPPORTED_PHYSICAL_ITEM_TYPES,
    )


def parse_remote_capture(content: bytes, source_name: str) -> ParsedRemoteCapture:
    if not content:
        raise RemoteCaptureError("Remote-capture CSV is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise RemoteCaptureError(
            f"Remote-capture CSV exceeds the {MAX_FILE_BYTES}-byte limit."
        )
    if not source_name.lower().endswith(".csv"):
        raise RemoteCaptureError("Remote-capture source must be a .csv file.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RemoteCaptureError("Remote-capture CSV must be UTF-8.") from exc
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        headers = tuple(str(value).strip() for value in next(reader))
    except StopIteration as exc:
        raise RemoteCaptureError("Remote-capture CSV has no header row.") from exc
    if headers != REQUIRED_HEADERS:
        raise RemoteCaptureError(
            "Remote-capture CSV headers or order do not match the governed bank export contract."
        )

    parsed_rows: list[ParsedBankRow] = []
    quarantined: list[QuarantinedBankRow] = []
    omitted_row_count = 0
    source_row_count = 0
    for row_number, values in enumerate(reader, start=2):
        if not any(value.strip() for value in values):
            continue
        source_row_count += 1
        if source_row_count > MAX_SOURCE_ROWS:
            raise RemoteCaptureError(
                f"Remote-capture CSV exceeds the {MAX_SOURCE_ROWS}-row limit."
            )
        padded_headers: tuple[str, ...] = ()
        if len(values) < len(REQUIRED_HEADERS):
            missing_headers = REQUIRED_HEADERS[len(values):]
            if missing_headers and all(
                header in OPTIONAL_TRAILING_HEADERS for header in missing_headers
            ):
                padded_headers = missing_headers
                values = [*values, *("" for _ in missing_headers)]
            else:
                quarantined.append(
                    _quarantine(row_number, values, "SOURCE_COLUMN_COUNT_MISMATCH")
                )
                continue
        elif len(values) > len(REQUIRED_HEADERS):
            quarantined.append(
                _quarantine(row_number, values, "SOURCE_COLUMN_COUNT_MISMATCH")
            )
            continue
        raw = dict(zip(REQUIRED_HEADERS, values, strict=True))
        reason_codes: list[str] = []
        try:
            store, location_key, location_name = _location(raw["location"])
        except ValueError:
            reason_codes.append("LOCATION_FORMAT_INVALID")
            store, location_key, location_name = "", "", ""
        if store in _EXCLUDED_STORE_NUMBERS:
            # Administrative/Corporate rows are not a real store deposit -
            # omitted entirely rather than quarantined or reconciled.
            omitted_row_count += 1
            continue
        try:
            create_date = _create_business_date(raw["createDate"])
        except ValueError:
            reason_codes.append("CREATE_DATE_INVALID")
            create_date = ""
        account_name = raw["accountName"].strip()
        deposit_number = raw["depositNo"].strip()
        item_type = raw["itemType"].strip()
        if not account_name:
            reason_codes.append("ACCOUNT_NAME_BLANK")
        if not deposit_number:
            reason_codes.append("DEPOSIT_NUMBER_BLANK")
        if item_type not in SUPPORTED_PHYSICAL_ITEM_TYPES | {VIRTUAL_CREDIT_ITEM_TYPE}:
            reason_codes.append("ITEM_TYPE_UNSUPPORTED")
        row_warnings: list[str] = []
        if padded_headers:
            row_warnings.append("SOURCE_TRAILING_OPTIONAL_COLUMNS_PADDED")
        if not raw["CaptureChannel"].strip():
            row_warnings.append("CAPTURE_CHANNEL_BLANK")
        try:
            amount = _strict_positive_money(raw["amount"])
        except ValueError:
            reason_codes.append("AMOUNT_INVALID")
            amount = Decimal("0.00")
        if reason_codes:
            quarantined.append(_quarantine(row_number, values, *reason_codes))
            continue
        deposit_key = _deposit_key(
            account_name, location_key, deposit_number, create_date
        )
        raw_check = raw["checkNo"].strip()
        is_balancing = item_type == VIRTUAL_CREDIT_ITEM_TYPE
        if not is_balancing and not raw_check:
            row_warnings.append("CHECK_NUMBER_MISSING")
        parsed_rows.append(
            ParsedBankRow(
                source_row_number=row_number,
                source_record_sha256=_record_hash(raw),
                raw_values=raw,
                deposit_key=deposit_key,
                location_key=location_key,
                store_number=store,
                location_name=location_name,
                account_name=account_name,
                create_business_date=create_date,
                deposit_number=deposit_number,
                item_type=item_type,
                amount=amount,
                raw_amount=raw["amount"],
                raw_check_number=raw_check,
                normalized_check_number=normalize_check_number(raw_check),
                is_balancing_item=is_balancing,
                warnings=tuple(row_warnings),
            )
        )
    if not parsed_rows and not quarantined and not omitted_row_count:
        raise RemoteCaptureError("Remote-capture CSV has no data rows.")

    grouped: dict[str, list[ParsedBankRow]] = {}
    for row in parsed_rows:
        grouped.setdefault(row.deposit_key, []).append(row)
    quarantined_by_deposit: dict[str, list[QuarantinedBankRow]] = {}
    for row in quarantined:
        if row.provisional_deposit_key:
            quarantined_by_deposit.setdefault(row.provisional_deposit_key, []).append(row)

    deposits: list[DepositBalance] = []
    for deposit_key in sorted(set(grouped) | set(quarantined_by_deposit)):
        rows = grouped.get(deposit_key, [])
        quarantined_rows = quarantined_by_deposit.get(deposit_key, [])
        if not rows:
            # A fully quarantined deposit cannot establish its public dimensions;
            # the row remains visible in the quarantine collection.
            continue
        physical = [row for row in rows if not row.is_balancing_item]
        balancing = [row for row in rows if row.is_balancing_item]
        provisional_physical = [
            row
            for row in quarantined_rows
            if row.provisional_is_physical and row.provisional_amount is not None
        ]
        physical_total = sum((row.amount for row in physical), Decimal("0.00")) + sum(
            (row.provisional_amount for row in provisional_physical),
            Decimal("0.00"),
        )
        balancing_total = sum((row.amount for row in balancing), Decimal("0.00"))
        difference = (balancing_total - physical_total).quantize(Decimal("0.01"))
        warnings: list[str] = []
        if quarantined_rows:
            status = "SOURCE_ROWS_QUARANTINED"
            warnings.append(
                "Deposit has quarantined source rows; totals and balance are not final."
            )
        elif not balancing:
            status = "MISSING_BALANCING_ITEM"
            warnings.append("Deposit has no Virtual Credit balancing item.")
        elif len(balancing) > 1:
            status = "MULTIPLE_BALANCING_ITEMS"
            warnings.append("Deposit has more than one Virtual Credit balancing item.")
        elif difference != Decimal("0.00"):
            status = "OUT_OF_BALANCE"
            warnings.append("Virtual Credit does not exactly equal physical item total.")
        else:
            status = "BALANCED"
        first = rows[0]
        deposits.append(
            DepositBalance(
                deposit_key=deposit_key,
                location_key=first.location_key,
                store_number=first.store_number,
                location_name=first.location_name,
                account_name=first.account_name,
                create_business_date=first.create_business_date,
                deposit_number=first.deposit_number,
                physical_item_count=len(physical) + len(provisional_physical),
                balancing_item_count=len(balancing),
                quarantined_row_count=len(quarantined_rows),
                physical_total=physical_total,
                balancing_total=balancing_total,
                difference=difference,
                status=status,
                warnings=tuple(warnings),
            )
        )
    return ParsedRemoteCapture(
        source_name=source_name,
        source_sha256=hashlib.sha256(content).hexdigest(),
        source_size=len(content),
        parser_version=REMOTE_CAPTURE_PARSER_VERSION,
        source_row_count=source_row_count,
        rows=tuple(parsed_rows),
        quarantined_rows=tuple(quarantined),
        omitted_row_count=omitted_row_count,
        deposits=tuple(deposits),
    )


def physical_items(parsed: ParsedRemoteCapture, run_id: str) -> tuple[BankPaymentItem, ...]:
    result: list[BankPaymentItem] = []
    for row in parsed.rows:
        if row.is_balancing_item:
            continue
        item_id = "PNI-" + hashlib.sha256(
            f"{run_id}\x1f{row.source_row_number}\x1f{row.source_record_sha256}".encode(
                "utf-8"
            )
        ).hexdigest()[:24]
        result.append(
            BankPaymentItem(
                item_id=item_id,
                source_row_number=row.source_row_number,
                location_key=row.location_key,
                store_number=row.store_number,
                deposit_number=row.deposit_number,
                item_type=row.item_type,
                raw_check_number=row.raw_check_number,
                normalized_check_number=row.normalized_check_number,
                amount=row.amount,
                raw_amount=row.raw_amount,
                source_record_sha256=row.source_record_sha256,
            )
        )
    return tuple(result)


__all__ = [
    "DepositBalance",
    "ParsedBankRow",
    "ParsedRemoteCapture",
    "QuarantinedBankRow",
    "REMOTE_CAPTURE_PARSER_VERSION",
    "REDACTED_BANK_VALUE",
    "RemoteCaptureError",
    "SUPPORTED_PHYSICAL_ITEM_TYPES",
    "VIRTUAL_CREDIT_ITEM_TYPE",
    "parse_remote_capture",
    "physical_items",
]
