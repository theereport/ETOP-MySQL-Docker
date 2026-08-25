from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .pnc_lockbox_export import export_pnc_workbook
from .pnc_lockbox_parser import parse_pnc_lockbox, save_result
from core.test_path_override import resolve_test_path_override

MODULE_DIR = Path(__file__).resolve().parent
LOCKBOX_RESULT_DIR = resolve_test_path_override(
    "ETOP_TEST_LOCKBOX_RESULT_DIR",
    MODULE_DIR / "lockbox_results",
    kind="directory",
)
LOCKBOX_EXPORT_DIR = resolve_test_path_override(
    "ETOP_TEST_LOCKBOX_EXPORT_DIR",
    MODULE_DIR / "lockbox_exports",
    kind="directory",
)
LOCKBOX_DATABASE_PATH = resolve_test_path_override(
    "ETOP_TEST_LOCKBOX_DATABASE", MODULE_DIR / "lockbox_learning.db"
)

LOCKBOX_RESULT_DIR.mkdir(parents=True, exist_ok=True)
LOCKBOX_EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _normalize_phone(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits[-10:] if len(digits) >= 10 else digits


def _initialize_database() -> None:
    with sqlite3.connect(LOCKBOX_DATABASE_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS lockbox_reviews (
                job_id TEXT NOT NULL,
                transaction_id TEXT NOT NULL,
                review_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (job_id, transaction_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS customer_profiles (
                profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                customer_phone TEXT NOT NULL DEFAULT '',
                customer_address_line_1 TEXT NOT NULL DEFAULT '',
                customer_address_line_2 TEXT NOT NULL DEFAULT '',
                customer_city TEXT NOT NULL DEFAULT '',
                customer_state TEXT NOT NULL DEFAULT '',
                customer_postal_code TEXT NOT NULL DEFAULT '',
                aba_routing TEXT NOT NULL DEFAULT '',
                account_number TEXT NOT NULL DEFAULT '',
                times_confirmed INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_customer_profiles_bank
            ON customer_profiles(aba_routing, account_number)
            """
        )
        connection.commit()


def result_path(job_id: str) -> Path:
    return LOCKBOX_RESULT_DIR / f"{job_id}.json"


def process_lockbox(job_id: str, pdf_path: str | Path) -> dict[str, Any]:
    result = parse_pnc_lockbox(pdf_path)
    result["job_id"] = job_id
    save_result(result, result_path(job_id))
    return _apply_saved_reviews(result)


def get_lockbox_result(job_id: str) -> dict[str, Any]:
    return _apply_saved_reviews(get_raw_lockbox_result(job_id))


def get_raw_lockbox_result(job_id: str) -> dict[str, Any]:
    """Read immutable parser output without applying editable review state."""

    path = result_path(job_id)

    if not path.exists():
        raise FileNotFoundError("The lockbox job has not been processed.")

    return json.loads(path.read_text(encoding="utf-8"))


def _ensure_transaction_defaults(transaction: dict[str, Any]) -> None:
    transaction.setdefault("customer_name", "")
    transaction.setdefault("customer_phone", "")
    transaction.setdefault("customer_address_line_1", "")
    transaction.setdefault("customer_address_line_2", "")
    transaction.setdefault("customer_city", "")
    transaction.setdefault("customer_state", "")
    transaction.setdefault("customer_postal_code", "")
    transaction.setdefault("reviewer", "")
    transaction.setdefault("notes", "")
    transaction.setdefault("override_reason", "")
    transaction.setdefault(
        "original_allocations",
        [dict(item) for item in transaction.get("allocations", [])],
    )


def _recalculate_transaction(transaction: dict[str, Any]) -> None:
    allocation_total = round(
        sum(
            float(item.get("net_invoice_amount", 0.0) or 0.0)
            for item in transaction.get("allocations", [])
        ),
        2,
    )
    difference = round(float(transaction.get("check_amount", 0.0)) - allocation_total, 2)
    balanced = bool(transaction.get("allocations")) and abs(difference) <= 0.01

    transaction["allocation_total"] = allocation_total
    transaction["difference"] = difference
    transaction["balanced"] = balanced

    if transaction.get("status") not in {"corrected", "held", "approved"}:
        if balanced:
            transaction["status"] = "balanced"
        elif not transaction.get("allocations"):
            transaction["status"] = "no_remittance"
        else:
            transaction["status"] = "review_required"


def _recalculate_result(result: dict[str, Any]) -> None:
    transactions = result.get("transactions", [])
    for transaction in transactions:
        _ensure_transaction_defaults(transaction)
        _recalculate_transaction(transaction)

    result["transaction_count"] = len(transactions)
    result["allocation_count"] = sum(
        len(item.get("allocations", [])) for item in transactions
    )
    result["total_check_amount"] = round(
        sum(float(item.get("check_amount", 0.0)) for item in transactions), 2
    )
    result["total_allocation_amount"] = round(
        sum(float(item.get("allocation_total", 0.0)) for item in transactions), 2
    )
    result["total_difference"] = round(
        result["total_check_amount"] - result["total_allocation_amount"], 2
    )
    result["balanced_count"] = sum(
        1 for item in transactions if bool(item.get("balanced"))
    )
    result["review_count"] = sum(
        1 for item in transactions if item.get("status") not in {"balanced", "approved"}
    )


def _load_review(job_id: str, transaction_id: str) -> dict[str, Any] | None:
    _initialize_database()
    with sqlite3.connect(LOCKBOX_DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT review_json
            FROM lockbox_reviews
            WHERE job_id = ? AND transaction_id = ?
            """,
            (job_id, transaction_id),
        ).fetchone()

    return json.loads(row["review_json"]) if row else None


def _apply_saved_reviews(result: dict[str, Any]) -> dict[str, Any]:
    job_id = str(result.get("job_id", ""))
    for transaction in result.get("transactions", []):
        _ensure_transaction_defaults(transaction)
        if job_id:
            review = _load_review(job_id, str(transaction.get("transaction_id", "")))
            if review:
                transaction.update(review)

    _recalculate_result(result)
    return result


def save_lockbox_transaction_review(
    job_id: str,
    transaction_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    result = get_lockbox_result(job_id)
    transaction = next(
        (
            item
            for item in result.get("transactions", [])
            if item.get("transaction_id") == transaction_id
        ),
        None,
    )

    if transaction is None:
        raise KeyError(f"Transaction {transaction_id} was not found.")

    allocations = payload.get("allocations", [])
    if any(not str(item.get("invoice_number", "")).strip() for item in allocations):
        raise ValueError("Every allocation must have an invoice number.")

    check_amount = float(transaction.get("check_amount", 0.0))
    allocation_total = round(
        sum(float(item.get("net_invoice_amount", 0.0) or 0.0) for item in allocations),
        2,
    )
    difference = round(check_amount - allocation_total, 2)

    status = str(payload.get("status", "corrected"))
    override_reason = str(payload.get("override_reason", "")).strip()
    if status == "approved" and abs(difference) > 0.01 and not override_reason:
        raise ValueError(
            "An override reason is required before approving an unbalanced transaction."
        )

    review = {
        "allocations": allocations,
        "reviewer": str(payload.get("reviewer", "")).strip(),
        "notes": str(payload.get("notes", "")).strip(),
        "status": status,
        "override_reason": override_reason,
        "customer_name": str(payload.get("customer_name", "")).strip(),
        "customer_phone": str(payload.get("customer_phone", "")).strip(),
        "customer_address_line_1": str(
            payload.get("customer_address_line_1", "")
        ).strip(),
        "customer_address_line_2": str(
            payload.get("customer_address_line_2", "")
        ).strip(),
        "customer_city": str(payload.get("customer_city", "")).strip(),
        "customer_state": str(payload.get("customer_state", "")).strip(),
        "customer_postal_code": str(
            payload.get("customer_postal_code", "")
        ).strip(),
    }

    now = _utc_now()
    _initialize_database()
    with sqlite3.connect(LOCKBOX_DATABASE_PATH) as connection:
        connection.execute(
            """
            INSERT INTO lockbox_reviews (
                job_id, transaction_id, review_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(job_id, transaction_id) DO UPDATE SET
                review_json = excluded.review_json,
                updated_at = excluded.updated_at
            """,
            (
                job_id,
                transaction_id,
                json.dumps(review),
                now,
                now,
            ),
        )
        connection.commit()

    transaction.update(review)
    _recalculate_transaction(transaction)
    save_result(result, result_path(job_id))

    if status == "approved" and review["customer_name"]:
        _upsert_customer_profile(transaction)

    return get_lockbox_result(job_id)


def _upsert_customer_profile(transaction: dict[str, Any]) -> None:
    _initialize_database()

    name = str(transaction.get("customer_name", "")).strip()
    if not name:
        return

    phone = str(transaction.get("customer_phone", "")).strip()
    address1 = str(transaction.get("customer_address_line_1", "")).strip()
    address2 = str(transaction.get("customer_address_line_2", "")).strip()
    city = str(transaction.get("customer_city", "")).strip()
    state = str(transaction.get("customer_state", "")).strip()
    postal = str(transaction.get("customer_postal_code", "")).strip()
    routing = str(transaction.get("aba_routing", "")).strip()
    account = str(transaction.get("account_number", "")).strip()
    now = _utc_now()

    with sqlite3.connect(LOCKBOX_DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row
        candidates = connection.execute(
            "SELECT * FROM customer_profiles"
        ).fetchall()

        existing = None
        for row in candidates:
            same_bank = (
                routing
                and account
                and _normalize(row["aba_routing"]) == _normalize(routing)
                and _normalize(row["account_number"]) == _normalize(account)
            )
            same_name_phone = (
                _normalize(row["customer_name"]) == _normalize(name)
                and (
                    not phone
                    or _normalize_phone(row["customer_phone"]) == _normalize_phone(phone)
                )
            )
            if same_bank or same_name_phone:
                existing = row
                break

        if existing:
            connection.execute(
                """
                UPDATE customer_profiles
                SET customer_name = ?,
                    customer_phone = ?,
                    customer_address_line_1 = ?,
                    customer_address_line_2 = ?,
                    customer_city = ?,
                    customer_state = ?,
                    customer_postal_code = ?,
                    aba_routing = ?,
                    account_number = ?,
                    times_confirmed = times_confirmed + 1,
                    updated_at = ?
                WHERE profile_id = ?
                """,
                (
                    name,
                    phone or existing["customer_phone"],
                    address1 or existing["customer_address_line_1"],
                    address2 or existing["customer_address_line_2"],
                    city or existing["customer_city"],
                    state or existing["customer_state"],
                    postal or existing["customer_postal_code"],
                    routing or existing["aba_routing"],
                    account or existing["account_number"],
                    now,
                    existing["profile_id"],
                ),
            )
        else:
            connection.execute(
                """
                INSERT INTO customer_profiles (
                    customer_name, customer_phone,
                    customer_address_line_1, customer_address_line_2,
                    customer_city, customer_state, customer_postal_code,
                    aba_routing, account_number, times_confirmed,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    name,
                    phone,
                    address1,
                    address2,
                    city,
                    state,
                    postal,
                    routing,
                    account,
                    now,
                    now,
                ),
            )
        connection.commit()


def get_customer_suggestions(
    job_id: str,
    transaction_id: str,
    limit: int = 5,
) -> dict[str, Any]:
    result = get_lockbox_result(job_id)
    transaction = next(
        (
            item
            for item in result.get("transactions", [])
            if item.get("transaction_id") == transaction_id
        ),
        None,
    )
    if transaction is None:
        raise KeyError(f"Transaction {transaction_id} was not found.")

    _initialize_database()
    with sqlite3.connect(LOCKBOX_DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM customer_profiles"
        ).fetchall()

    suggestions: list[dict[str, Any]] = []
    for row in rows:
        score = 0.0
        matched_on: list[str] = []

        if (
            transaction.get("aba_routing")
            and transaction.get("account_number")
            and _normalize(row["aba_routing"])
            == _normalize(transaction.get("aba_routing"))
            and _normalize(row["account_number"])
            == _normalize(transaction.get("account_number"))
        ):
            score += 0.55
            matched_on.append("bank account")

        if (
            transaction.get("customer_name")
            and _normalize(row["customer_name"])
            == _normalize(transaction.get("customer_name"))
        ):
            score += 0.25
            matched_on.append("customer name")

        if (
            transaction.get("customer_phone")
            and _normalize_phone(row["customer_phone"])
            == _normalize_phone(transaction.get("customer_phone"))
        ):
            score += 0.10
            matched_on.append("phone")

        if (
            transaction.get("customer_postal_code")
            and _normalize(row["customer_postal_code"])
            == _normalize(transaction.get("customer_postal_code"))
        ):
            score += 0.05
            matched_on.append("ZIP code")

        if (
            transaction.get("customer_address_line_1")
            and _normalize(row["customer_address_line_1"])
            == _normalize(transaction.get("customer_address_line_1"))
        ):
            score += 0.05
            matched_on.append("address")

        confirmation_bonus = min(int(row["times_confirmed"]), 10) * 0.005
        score = min(score + confirmation_bonus, 0.99)

        if score <= 0:
            continue

        suggestions.append(
            {
                "profile_id": int(row["profile_id"]),
                "customer_name": row["customer_name"],
                "customer_phone": row["customer_phone"],
                "customer_address_line_1": row["customer_address_line_1"],
                "customer_address_line_2": row["customer_address_line_2"],
                "customer_city": row["customer_city"],
                "customer_state": row["customer_state"],
                "customer_postal_code": row["customer_postal_code"],
                "confidence": round(score, 4),
                "matched_on": matched_on,
                "times_confirmed": int(row["times_confirmed"]),
            }
        )

    suggestions.sort(
        key=lambda item: (item["confidence"], item["times_confirmed"]),
        reverse=True,
    )

    return {
        "job_id": job_id,
        "transaction_id": transaction_id,
        "suggestions": suggestions[:limit],
    }


def create_lockbox_export(
    job_id: str,
    template_path: str | Path | None = None,
) -> Path:
    result = get_lockbox_result(job_id)

    output = LOCKBOX_EXPORT_DIR / f"{job_id}_PNC_Lockbox.xlsx"

    return export_pnc_workbook(
        result,
        output,
        template_path=template_path,
    )
