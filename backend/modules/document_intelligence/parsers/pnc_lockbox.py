import re
from decimal import Decimal

from .base import DocumentParser


FIELD_ORDER = [
    "Date",
    "Lockbox",
    "Batch",
    "Batch Item",
    "Reported Amount",
    "Transit",
    "Account",
    "Check Number",
    "Env Num",
    "Group Name",
    "Group Id",
    "Num Pages",
    "TID",
]


def _value_after_label(lines: list[str], label: str) -> str | None:
    for index, line in enumerate(lines):
        if line.strip() == label and index + 1 < len(lines):
            return lines[index + 1].strip()
    return None


def _parse_amount(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.replace("$", "").replace(",", "").strip()
    try:
        return f"{Decimal(cleaned):.2f}"
    except Exception:
        return None


class PNCLockboxParser(DocumentParser):
    document_type = "pnc_lockbox"
    parser_name = "pnc_lockbox_parser"
    parser_version = "0.2.0"

    def parse(self, document: dict) -> dict:
        transactions: list[dict] = []
        warnings: list[str] = []

        for page in document["extraction"]["pages"]:
            text = page["text"]
            if "Transaction Level Details" not in text:
                continue

            lines = [line.strip() for line in text.splitlines() if line.strip()]
            transaction = {
                "source_page": page["page_number"],
                "date": _value_after_label(lines, "Date"),
                "lockbox": _value_after_label(lines, "Lockbox"),
                "batch": _value_after_label(lines, "Batch"),
                "batch_item": _value_after_label(lines, "Batch Item"),
                "reported_amount": _parse_amount(
                    _value_after_label(lines, "Reported Amount")
                ),
                "transit": _value_after_label(lines, "Transit"),
                "account": _value_after_label(lines, "Account"),
                "check_number": _value_after_label(lines, "Check Number"),
                "env_num": _value_after_label(lines, "Env Num"),
                "group_name": _value_after_label(lines, "Group Name"),
                "group_id": _value_after_label(lines, "Group Id"),
                "num_pages": _value_after_label(lines, "Num Pages"),
                "transaction_id": _value_after_label(lines, "TID"),
            }

            missing = [
                key
                for key in (
                    "date",
                    "lockbox",
                    "batch",
                    "batch_item",
                    "reported_amount",
                    "check_number",
                    "transaction_id",
                )
                if not transaction.get(key)
            ]

            transaction["validation"] = {
                "status": "valid" if not missing else "warning",
                "missing_fields": missing,
            }

            transactions.append(transaction)

        if not transactions:
            warnings.append(
                "No transaction detail pages were parsed from the PDF text."
            )

        total_reported = sum(
            Decimal(item["reported_amount"])
            for item in transactions
            if item.get("reported_amount")
        )

        ocr_pages = [
            page["page_number"]
            for page in document["extraction"]["pages"]
            if page["requires_ocr"]
        ]

        if ocr_pages:
            warnings.append(
                "Image-heavy pages require OCR or image analysis to extract "
                "invoice allocations and remittance details."
            )

        return {
            "parser": self.parser_name,
            "parser_version": self.parser_version,
            "document_type": self.document_type,
            "summary": {
                "page_count": document["extraction"]["page_count"],
                "character_count": document["extraction"]["character_count"],
                "transaction_count": len(transactions),
                "total_reported_amount": f"{total_reported:.2f}",
                "ocr_recommended": bool(ocr_pages),
                "ocr_pages": ocr_pages,
            },
            "records": {
                "transactions": transactions,
            },
            "validation": {
                "status": "preliminary",
                "errors": [],
                "warnings": warnings,
            },
        }
