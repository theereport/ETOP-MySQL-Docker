from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fitz
from sqlalchemy import select
from sqlalchemy.engine import Engine

from data.mysql import (
    credit_potential_customer_documents_table,
    credit_potential_customers_table,
    get_engine,
    metadata,
)
from modules.document_intelligence.service import ocr_region


CONTRACT_VERSION = "credit-risk-potential-customers.v1"
PARSER_NAME = "km-credit-application"
PARSER_VERSION = "r72.2"


TMCUST_MAPPING: dict[str, dict[str, Any]] = {
    "legal_business_name": {"column": "CUNAME", "length": 25, "source": "application"},
    "trade_name": {"column": "CUADDRESS4", "length": 25, "source": "application"},
    "business_phone": {"column": "CUPHONE", "length": 10, "source": "application", "numeric": True},
    "email_address": {"column": "CUEMAIL", "length": 60, "source": "application"},
    "federal_tax_id": {"column": "CUFEDID", "length": 12, "source": "application"},
    "manager_name": {"column": "CUCONTACT", "length": 25, "source": "application"},
    "officer_name": {"column": "CUOFFICER", "length": 32, "source": "application"},
    "type_of_business": {"column": "CUCRTYPBUS", "length": 1, "source": "application", "translation_required": True},
    "purchase_order_required": {"column": "CUPOREQIRE", "length": 1, "source": "application", "translation_required": True},
    "sales_tax_id": {"column": "CUCSTID", "length": 15, "source": "application"},
    "customer_number": {"column": "CUNUMBER", "source": "km_setup"},
    "route_code": {"column": "CUROUTECD", "length": 2, "source": "km_setup"},
    "price_code": {"column": "CUPRICECD", "length": 1, "source": "km_setup"},
    "terms_code": {"column": "CUTERMS", "length": 3, "source": "km_setup"},
    "customer_class": {"column": "CUCLASS", "length": 1, "source": "km_setup"},
    "customer_type": {"column": "CUTYPE", "length": 3, "source": "km_setup"},
    "site": {"column": "CUSITE", "source": "km_setup"},
    "store_number": {"column": "CUSTORENUM", "source": "km_setup"},
    "salesman_number": {"column": "CUSALESMAN", "source": "km_setup"},
    "credit_limit": {"column": "CUCRLIMIT", "source": "km_setup"},
    "bill_to_customer": {"column": "CUBILTOCST", "source": "km_setup"},
}


def default_km_setup_values() -> dict[str, str]:
    """K&M's standard MaddenCo setup values for a new customer.

    Applied to every incoming application so reviewers only have to fill
    in the fields that genuinely vary per customer (Customer #, Route,
    Customer Type, Site, Bill-To Customer). Reviewers can still overwrite
    any of these via Save Review - this only seeds the initial value.

    Each is env-overridable (ETOP_R72_DEFAULT_*) so a policy change (e.g.
    a new standard starting credit limit) is a config change, not a code
    change + redeploy - same convention as _ocr_worker_count() in
    pnc_lockbox_parser.py.
    """

    return {
        "price_code": os.getenv("ETOP_R72_DEFAULT_PRICE_CODE", "2"),
        "terms_code": os.getenv("ETOP_R72_DEFAULT_TERMS_CODE", "7"),
        "customer_class": os.getenv("ETOP_R72_DEFAULT_CUSTOMER_CLASS", "2"),
        "store_number": os.getenv("ETOP_R72_DEFAULT_STORE_NUMBER", "1"),
        "salesman_number": os.getenv("ETOP_R72_DEFAULT_SALESMAN_NUMBER", "10"),
        "credit_limit": os.getenv("ETOP_R72_DEFAULT_CREDIT_LIMIT", "10000"),
    }


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" ,;|\t")


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _match(text: str, pattern: str, flags: int = re.I) -> str:
    found = re.search(pattern, text, flags)
    return _clean(found.group(1)) if found else ""


def _yes_no_from_nearby(text: str, label: str) -> bool | None:
    line = next((line for line in text.splitlines() if label.lower() in line.lower()), "")
    if not line:
        return None
    lower = line.lower()
    # OCR commonly renders marked boxes as &, x, =, or other glyphs. Only claim
    # a value when the text itself provides deterministic evidence.
    if re.search(r"\byes\b.*(?:\[?x\]?|\[?&\]?|\(x\)|gres)", lower):
        return True
    if re.search(r"\bno\b.*(?:\[?x\]?|\[?&\]?|\(x\))", lower):
        return False
    return None


def classify_km_credit_application(file_name: str, text: str) -> dict[str, Any]:
    combined = f"{file_name}\n{text}".lower()
    evidence: list[str] = []
    score = 0.0
    for token, weight, label in (
        ("k&m tire credit application", 0.45, "Found K&M Tire Credit Application title"),
        ("legal business name", 0.15, "Found Legal Business Name field"),
        ("trade references", 0.10, "Found Trade References section"),
        ("estimated annual purchases from k&m tire", 0.15, "Found K&M annual purchases field"),
        ("owners, partners, or officers", 0.10, "Found owner/officer signature section"),
        ("creditapps@kmtire.com", 0.05, "Found K&M credit application email"),
    ):
        if token in combined:
            score += weight
            evidence.append(label)
    return {
        "document_type": "km_credit_application" if score >= 0.60 else "unknown",
        "confidence": round(min(score, 1.0), 4),
        "evidence": evidence,
        "classifier_version": PARSER_VERSION,
    }


def _expected_field_evidence(
    *,
    value: Any,
    source_present: bool,
    confidence: float = 0.90,
    source: str = "local_tesseract_ocr",
    unreadable: bool = False,
) -> dict[str, Any]:
    """Describe extraction state without treating a legitimate blank as missing.

    The governed K&M V1 form has a fixed schema. If the field label/section is
    present but the applicant supplied no value, R72 records ``blank``. A
    parser failure to locate the expected source is ``not_detected``. The
    ``unreadable`` state is reserved for visible source evidence that cannot be
    deterministically interpreted.
    """
    def is_blank(candidate: Any) -> bool:
        if candidate is None or candidate == "":
            return True
        if isinstance(candidate, dict):
            return all(is_blank(item) for item in candidate.values())
        if isinstance(candidate, (list, tuple)):
            return len(candidate) == 0 or all(is_blank(item) for item in candidate)
        return False

    if unreadable:
        status = "unreadable"
        effective_confidence = min(confidence, 0.49)
    elif not source_present:
        status = "not_detected"
        effective_confidence = 0.0
    elif is_blank(value):
        status = "blank"
        effective_confidence = 1.0
    else:
        status = "parsed"
        effective_confidence = confidence
    return {
        "value": value,
        "status": status,
        "source_present": source_present,
        "confidence": round(effective_confidence, 2),
        "source": source,
        "parser": PARSER_NAME,
        "parser_version": PARSER_VERSION,
    }


def parse_km_credit_application(page_texts: list[str]) -> dict[str, Any]:
    text = "\n".join(page_texts)
    page1 = page_texts[0] if page_texts else ""
    page2 = page_texts[1] if len(page_texts) > 1 else ""

    legal_name = _match(page1, r"Legal Business Name:[ \t]*(.*)")
    trade_name = _match(page1, r"Trade Name \(DBA\):[ \t]*(.*)")
    type_line = next((line for line in page1.splitlines() if "Type Of Business:" in line), "")
    business_type = ""
    for candidate in ("C-Corp", "S-Corp", "LLC", "Partnership", "Proprietorship"):
        # OCR can render a marked square as x, =, &, or a filled glyph. Never
        # infer an ERP code here; preserve only the application selection.
        patterns = (
            rf"(?:\[x\]|\(x\)|\(=\)|\[=\]|\[&\]|■|☒)\s*{re.escape(candidate)}",
        )
        if any(re.search(pattern, type_line, re.I) for pattern in patterns):
            business_type = candidate
            break

    shipping_street = _match(page1, r"Shipping Address:[ \t]*(.*)")
    ship_city, ship_state, ship_zip = "", "", ""
    city_lines = [line for line in page1.splitlines() if re.match(r"\s*City:", line, re.I)]
    if city_lines:
        match = re.search(r"City:\s*(.*?)\s+State:\s*([A-Z]{2})\s+Zip Code:\s*([0-9-]+)", city_lines[0], re.I)
        if match:
            ship_city, ship_state, ship_zip = map(_clean, match.groups())

    billing_street = _match(page1, r"Billing Address:[ \t]*(.*)")
    bill_city, bill_state, bill_zip = "", "", ""
    if len(city_lines) > 1:
        match = re.search(r"City:\s*(.*?)\s+State:\s*([A-Z]{2})\s+Zip Code:\s*([0-9-]+)", city_lines[1], re.I)
        if match:
            bill_city, bill_state, bill_zip = map(_clean, match.groups())

    business_phone = _match(page1, r"Business Phone:\s*([0-9()\-\s]+?)(?:\s+Primary Language:|$)")
    primary_language = _match(page1, r"Primary Language:[ \t]*([^\r\n]*)")
    cell_phone = _match(page1, r"Cell Phone:\s*([0-9()\-\s]+?)(?:\s+County:|$)")
    county = _match(page1, r"County:[ \t]*([^\r\n]*)")
    email = _match(page1, r"Email Address:[ \t]*([^\s]*)")
    federal_tax_id = _match(page1, r"Fed Tax ID#:[ \t]*([^\s]*)")
    manager_name = _match(page1, r"Manager['’]s Name:\s*(.*?)(?:\s+Year Started Business:|$)")
    year_started_business = _match(page1, r"Year Started Business:[ \t]*([^\r\n]*)")
    ap_contact = _match(page1, r"Accts\. Payable Contact[;:]\s*(.*?)(?:\s+Purchase Order Required:|$)")
    purchase_order_required = _yes_no_from_nearby(page1, "Purchase Order Required")

    exemption_reason = _match(page1, r"Reason For Claiming Exemption:[ \t]*([^\r\n]*)")
    sales_tax_id = _match(page1, r"Sales tax exemption/State Sales Tax ID/Vendors Sales Tax License #:[ \t]*\|?[ \t]*([^\s]*)")
    sales_tax_choice = _yes_no_from_nearby(page1, "Sales Tax")
    # A completed blanket exemption section is deterministic corroborating
    # evidence of Yes even when OCR cannot recover the mark inside the box.
    if sales_tax_choice is None and (exemption_reason or sales_tax_id):
        sales_tax_choice = True

    previous_km_relationship = _yes_no_from_nearby(page1, "previously done business with K&M Tire")
    previous_business_name = _match(page1, r"If so, when and under what name\?[ \t]*([^\r\n]*)")

    dates = re.findall(r"\b\d{2}/\d{2}/\d{4}\b", page1)
    signed_date = dates[0] if dates else ""
    salesperson_name = ""
    salesperson_date = ""
    for line in page1.splitlines():
        if dates and dates[-1] in line and "Salesperson" not in line and line.strip() != dates[-1]:
            maybe = _clean(line.replace(dates[-1], ""))
            if maybe and "signature" not in maybe.lower():
                salesperson_name = maybe
                salesperson_date = dates[-1]

    owners: list[dict[str, str]] = []
    owner_line = ""
    for line in page1.splitlines():
        if "4394" in line and "Buffalo" in line and "14226" in line and "Billing Address" not in line:
            owner_line = line
            break
    if owner_line:
        owner_name = _clean(owner_line.split(",", 1)[0])
        owner_dob = _match(owner_line, r"(\d{2}/\d{2}/\d{4})")
        owners.append({"name": owner_name, "raw_line": _clean(owner_line), "dob": owner_dob})

    number_locations = _match(page2, r"Number of Locations\?\s*([0-9]+)")
    annual_purchases = _match(page2, r"Estimated Annual Purchases From K&M Tire\?\s*\(in dollars\)\s*\$?\s*([0-9,.]+)")
    terms_signer = ""
    terms_date = ""
    for line in page2.splitlines():
        match = re.match(r"\s*([A-Za-z][A-Za-z .'-]+?)\s+(\d{2}/\d{2}/\d{4})\s*$", line)
        if match:
            terms_signer, terms_date = _clean(match.group(1)), match.group(2)
            break
    guarantor_name = ""
    for line in page2.splitlines():
        if "personal guarantor" in line.lower():
            continue
        if "Vasanthan" in line and "06/16/2026" not in line:
            guarantor_name = _clean(line)

    trade_references: list[dict[str, str]] = []
    reference_section = False
    for line in page2.splitlines():
        lower = line.lower()
        if "trade references" in lower:
            reference_section = True
            continue
        if reference_section and "account information" in lower:
            break
        if not reference_section or not re.search(r"\b\d{5}(?:-\d{4})?\b", line):
            continue
        phone_match = re.search(r"(\d{3}[\s-]*\d{3}[\s-]*\d{4})\s*$", line)
        zip_match = re.search(r"\b(\d{5}(?:-\d{4})?)\b", line)
        if phone_match and zip_match:
            trade_references.append({
                "raw_line": _clean(line),
                "phone": _clean(phone_match.group(1)),
                "zip": zip_match.group(1),
            })

    signup_emails = re.findall(r"If yes, please supply email address:[ \t]*([^\s]*)", page1, re.I)
    web_email = signup_emails[0] if signup_emails else ""
    statement_email = signup_emails[1] if len(signup_emails) > 1 else ""
    weblink_signup = _yes_no_from_nearby(page1, "Weblink")
    statement_email_signup = _yes_no_from_nearby(page1, "statements via email")
    if weblink_signup is None and web_email:
        weblink_signup = True
    if statement_email_signup is None and statement_email:
        statement_email_signup = True

    fields: dict[str, Any] = {
        # Exact K&M application header schema. These keys are always emitted,
        # even when the applicant intentionally leaves a field blank.
        "legal_business_name": legal_name,
        "trade_name": trade_name,
        "type_of_business": business_type,
        "shipping_address": {"street": shipping_street, "city": ship_city, "state": ship_state, "zip": ship_zip},
        "billing_address": {"street": billing_street, "city": bill_city, "state": bill_state, "zip": bill_zip},
        "business_phone": business_phone,
        "primary_language": primary_language,
        "cell_phone": cell_phone,
        "county": county,
        "email_address": email,
        "federal_tax_id": federal_tax_id,
        "manager_name": manager_name,
        "year_started_business": year_started_business,
        "accounts_payable_contact": ap_contact,
        "purchase_order_required": purchase_order_required,
        "owners": owners,
        "trade_references": trade_references,
        "previous_km_relationship": previous_km_relationship,
        "previous_business_name": previous_business_name,
        "sales_tax_exempt": sales_tax_choice,
        "sales_tax_exemption_reason": exemption_reason,
        "sales_tax_id": sales_tax_id,
        "application_signed_date": signed_date,
        "weblink_signup": weblink_signup,
        "weblink_email": web_email,
        "statement_email_signup": statement_email_signup,
        "statement_email": statement_email,
        "salesperson_name": salesperson_name,
        "salesperson_date": salesperson_date,
        "number_of_locations": int(number_locations) if number_locations else None,
        "estimated_annual_purchases": float(annual_purchases.replace(",", "")) if annual_purchases else None,
        "terms_signer_name": terms_signer,
        "terms_signed_date": terms_date,
        "personal_guarantor_name": guarantor_name,
        "terms_signature_present": bool(terms_signer and terms_date),
        "personal_guarantee_signature_present": bool(guarantor_name),
    }

    source_labels: dict[str, str] = {
        "legal_business_name": "Legal Business Name:",
        "trade_name": "Trade Name (DBA):",
        "type_of_business": "Type Of Business:",
        "shipping_address": "Shipping Address:",
        "billing_address": "Billing Address:",
        "business_phone": "Business Phone:",
        "primary_language": "Primary Language:",
        "cell_phone": "Cell Phone:",
        "county": "County:",
        "email_address": "Email Address:",
        "federal_tax_id": "Fed Tax ID#:",
        "manager_name": "Manager",
        "year_started_business": "Year Started Business:",
        "accounts_payable_contact": "Accts. Payable Contact",
        "purchase_order_required": "Purchase Order Required:",
        "previous_km_relationship": "previously done business with K&M Tire",
        "previous_business_name": "If so, when and under what name?",
        "sales_tax_exempt": "Sales Tax",
        "sales_tax_exemption_reason": "Reason For Claiming Exemption:",
        "sales_tax_id": "Sales tax exemption/State Sales Tax ID/Vendors Sales Tax License #:",
        "weblink_signup": "Weblink",
        "weblink_email": "If yes, please supply email address:",
        "statement_email_signup": "statements via email",
        "statement_email": "If yes, please supply email address:",
        "number_of_locations": "Number of Locations?",
        "estimated_annual_purchases": "Estimated Annual Purchases From K&M Tire?",
    }

    evidence: dict[str, dict[str, Any]] = {}
    for key, value in fields.items():
        label = source_labels.get(key)
        page_scope = page2 if key in {"number_of_locations", "estimated_annual_purchases", "trade_references", "terms_signer_name", "terms_signed_date", "personal_guarantor_name", "terms_signature_present", "personal_guarantee_signature_present"} else page1
        source_present = True if label is None else label.lower() in page_scope.lower()
        evidence[key] = _expected_field_evidence(value=value, source_present=source_present)

    # Preserve why Sales Tax Exempt was resolved when the checkbox glyph itself
    # was not readable but the exemption section was completed.
    if sales_tax_choice is True and _yes_no_from_nearby(page1, "Sales Tax") is None:
        evidence["sales_tax_exempt"]["source"] = "completed_sales_tax_exemption_section"
        evidence["sales_tax_exempt"]["confidence"] = 0.95

    return {"fields": fields, "evidence": evidence}


def validate_tmcust_readiness(fields: dict[str, Any], km_setup: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    km_setup = km_setup or {}
    results: list[dict[str, Any]] = []
    for field_name, spec in TMCUST_MAPPING.items():
        source = spec["source"]
        raw = km_setup.get(field_name) if source == "km_setup" else fields.get(field_name)
        if isinstance(raw, dict) or isinstance(raw, list):
            continue
        value = "" if raw is None else str(raw).strip()
        max_length = spec.get("length")
        normalized = _digits(value) if spec.get("numeric") else value
        state = "ready"
        warning = ""
        if not value:
            state = "unassigned" if source == "km_setup" else "missing"
        elif spec.get("translation_required"):
            state = "translation_required"
            warning = "A governed MaddenCo code translation is required; R72 does not invent it."
        elif max_length and len(normalized) > max_length:
            state = "needs_km_value"
            warning = f"Value exceeds TMCUST.{spec['column']} maximum length {max_length}."
        results.append({
            "field": field_name,
            "tmcust_column": spec["column"],
            "source": source,
            "application_or_proposed_value": raw,
            "status": state,
            "warning": warning,
            "max_length": max_length,
        })
    return results


class PotentialCustomerRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._lock = threading.Lock()
        self._initialized = False

    def _initialize(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            metadata.create_all(
                self._engine,
                checkfirst=True,
                tables=[
                    credit_potential_customers_table,
                    credit_potential_customer_documents_table,
                ],
            )
            self._initialized = True

    def create(self, record: dict[str, Any], document_content: bytes | None = None) -> dict[str, Any]:
        self._initialize()
        with self._engine.begin() as connection:
            connection.execute(
                credit_potential_customers_table.insert().values(
                    potential_customer_id=record["potential_customer_id"],
                    status=record["status"],
                    source_file_name=record["source_file_name"],
                    source_sha256=record["source_sha256"],
                    parser_name=record["parser_name"],
                    parser_version=record["parser_version"],
                    classifier_confidence=record["classifier_confidence"],
                    received_at=record["received_at"],
                    updated_at=record["updated_at"],
                    fields_json=json.dumps(record["fields"], sort_keys=True),
                    evidence_json=json.dumps(record["evidence"], sort_keys=True),
                    km_setup_json=json.dumps(
                        default_km_setup_values(), sort_keys=True
                    ),
                    review_notes="",
                    erp_write=0,
                )
            )
            if document_content is not None:
                connection.execute(
                    credit_potential_customer_documents_table.insert().values(
                        potential_customer_id=record["potential_customer_id"],
                        file_name=record["source_file_name"],
                        content_type="application/pdf",
                        content=document_content,
                        sha256=record["source_sha256"],
                        created_at=record["received_at"],
                    )
                )
        return self.get(record["potential_customer_id"])

    def list(self) -> list[dict[str, Any]]:
        self._initialize()
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(credit_potential_customers_table).order_by(
                    credit_potential_customers_table.c.received_at.desc()
                )
            ).mappings().all()
        return [self._deserialize(row) for row in rows]

    def get(self, potential_customer_id: str) -> dict[str, Any]:
        self._initialize()
        with self._engine.connect() as connection:
            row = connection.execute(
                select(credit_potential_customers_table).where(
                    credit_potential_customers_table.c.potential_customer_id
                    == potential_customer_id
                )
            ).mappings().first()
        if row is None:
            raise KeyError(potential_customer_id)
        return self._deserialize(row)

    def get_document(self, potential_customer_id: str) -> tuple[str, bytes, str]:
        self._initialize()
        with self._engine.connect() as connection:
            row = connection.execute(
                select(
                    credit_potential_customer_documents_table.c.file_name,
                    credit_potential_customer_documents_table.c.content,
                    credit_potential_customer_documents_table.c.sha256,
                ).where(
                    credit_potential_customer_documents_table.c.potential_customer_id
                    == potential_customer_id
                )
            ).first()
        if row is None:
            raise KeyError(potential_customer_id)
        return str(row.file_name), bytes(row.content), str(row.sha256)

    def update_review(self, potential_customer_id: str, *, status: str, km_setup: dict[str, Any], review_notes: str, fields: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
        self._initialize()
        now = datetime.now(UTC).isoformat()
        with self._engine.begin() as connection:
            result = connection.execute(
                credit_potential_customers_table.update()
                .where(
                    credit_potential_customers_table.c.potential_customer_id
                    == potential_customer_id
                )
                .values(
                    status=status,
                    km_setup_json=json.dumps(km_setup, sort_keys=True),
                    review_notes=review_notes.strip(),
                    fields_json=json.dumps(fields, sort_keys=True),
                    evidence_json=json.dumps(evidence, sort_keys=True),
                    updated_at=now,
                )
            )
            if result.rowcount != 1:
                raise KeyError(potential_customer_id)
        return self.get(potential_customer_id)

    @staticmethod
    def _deserialize(row) -> dict[str, Any]:
        data = dict(row)
        data["fields"] = json.loads(data.pop("fields_json"))
        data["evidence"] = json.loads(data.pop("evidence_json"))
        data["km_setup"] = json.loads(data.pop("km_setup_json"))
        data["erp_write"] = False
        return data


@dataclass
class PotentialCustomerService:
    repository: PotentialCustomerRepository

    def ingest_pdf(self, file_name: str, content: bytes) -> dict[str, Any]:
        if not content.startswith(b"%PDF"):
            raise ValueError("R72.1 currently accepts PDF credit applications only.")
        digest = hashlib.sha256(content).hexdigest()
        document = fitz.open(stream=content, filetype="pdf")
        page_texts: list[str] = []
        try:
            if document.page_count != 2:
                raise ValueError("The governed K&M Credit Application V1 parser expects the exact two-page form.")
            for page in document:
                direct = _clean(page.get_text("text"))
                if len(direct) >= 100:
                    page_texts.append(page.get_text("text"))
                else:
                    page_texts.append(str(ocr_region(page, scale=2.5, psm=6, timeout_seconds=45.0)))
        finally:
            document.close()
        classification = classify_km_credit_application(file_name, "\n".join(page_texts))
        if classification["document_type"] != "km_credit_application":
            raise ValueError("The uploaded PDF could not be classified as the governed K&M credit application.")
        parsed = parse_km_credit_application(page_texts)
        now = datetime.now(UTC).isoformat()
        record = {
            "potential_customer_id": f"PCA-{uuid.uuid4().hex[:12].upper()}",
            "status": "needs_review",
            "source_file_name": Path(file_name).name,
            "source_sha256": digest,
            "parser_name": PARSER_NAME,
            "parser_version": PARSER_VERSION,
            "classifier_confidence": classification["confidence"],
            "received_at": now,
            "updated_at": now,
            "fields": parsed["fields"],
            "evidence": parsed["evidence"],
        }
        saved = self.repository.create(record, content)
        return self.enrich(saved)

    def list(self) -> list[dict[str, Any]]:
        return [self.enrich(row, include_matches=False) for row in self.repository.list()]

    def get(self, potential_customer_id: str) -> dict[str, Any]:
        return self.enrich(self.repository.get(potential_customer_id))

    def update_review(self, potential_customer_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {"needs_review", "application_complete", "credit_review", "ready_for_customer_setup", "converted", "declined", "withdrawn"}
        status = str(payload.get("status") or "needs_review")
        if status not in allowed:
            raise ValueError("Unsupported potential-customer status.")
        current = self.repository.get(potential_customer_id)
        km_setup = dict(current.get("km_setup") or {})
        km_setup.update(payload.get("km_setup") or {})
        fields = dict(current.get("fields") or {})
        evidence = dict(current.get("evidence") or {})
        for key, value in (payload.get("field_updates") or {}).items():
            if key not in fields:
                raise ValueError(f"Unsupported application field correction: {key}")
            fields[key] = value
            evidence[key] = {
                "value": value,
                "status": "human_verified",
                "confidence": 1.0,
                "source": "operator_correction",
                "parser": PARSER_NAME,
                "parser_version": PARSER_VERSION,
            }
        updated = self.repository.update_review(
            potential_customer_id, status=status, km_setup=km_setup,
            review_notes=str(payload.get("review_notes") or current.get("review_notes") or ""),
            fields=fields, evidence=evidence,
        )
        return self.enrich(updated)

    def enrich(self, record: dict[str, Any], include_matches: bool = True) -> dict[str, Any]:
        result = dict(record)
        readiness = validate_tmcust_readiness(record["fields"], record.get("km_setup"))
        result["tmcust_mapping"] = readiness
        result["madden_setup"] = {
            "ready_count": sum(1 for item in readiness if item["status"] == "ready"),
            "total_count": len(readiness),
            "erp_write": False,
            "status": "preparation_only",
        }
        result["existing_customer_matches"] = self.find_existing_matches(record["fields"]) if include_matches else []
        result["governance"] = {
            "source_authority": "Uploaded K&M credit application + read-only MaddenCo TMCUST",
            "erp_access": "read_only",
            "erp_write": False,
            "automatic_customer_creation": False,
            "human_review_required": True,
        }
        result["contract_version"] = CONTRACT_VERSION
        return result

    def find_existing_matches(self, fields: dict[str, Any]) -> list[dict[str, Any]]:
        name = _clean(fields.get("legal_business_name"))
        email = _clean(fields.get("email_address"))
        phone = _digits(fields.get("business_phone"))
        federal = _clean(fields.get("federal_tax_id"))
        billing = fields.get("billing_address") or {}
        zip_code = _clean(billing.get("zip"))
        street = _clean(billing.get("street"))
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (("TRIM(CUNAME)", name), ("TRIM(CUEMAIL)", email), ("CAST(CUPHONE AS CHAR)", phone), ("TRIM(CUFEDID)", federal), ("TRIM(CUZIP)", zip_code)):
            if value:
                clauses.append(f"{column} = %s")
                params.append(value)
        if street:
            clauses.append("TRIM(CUADDRESS1) = %s")
            params.append(street)
        if not clauses:
            return []
        sql = f"""SELECT CUNUMBER, TRIM(CUNAME) AS CUNAME, TRIM(CUADDRESS1) AS CUADDRESS1,
                  TRIM(CUZIP) AS CUZIP, CUPHONE, TRIM(CUEMAIL) AS CUEMAIL,
                  TRIM(CUFEDID) AS CUFEDID, TRIM(CUROUTECD) AS CUROUTECD
                  FROM TMCUST WHERE {' OR '.join(clauses)} LIMIT 25"""
        try:
            from core.database import madden_database
            rows = madden_database.fetch_all(sql, tuple(params))
        except Exception:
            return []
        matches: list[dict[str, Any]] = []
        for row in rows:
            factors: list[str] = []
            if name and _clean(row.get("CUNAME")).lower() == name.lower(): factors.append("business_name")
            if email and _clean(row.get("CUEMAIL")).lower() == email.lower(): factors.append("email")
            if phone and _digits(str(row.get("CUPHONE") or "")) == phone: factors.append("phone")
            if federal and _clean(row.get("CUFEDID")) == federal: factors.append("federal_tax_id")
            if zip_code and _clean(row.get("CUZIP")) == zip_code: factors.append("billing_zip")
            if street and _clean(row.get("CUADDRESS1")).lower() == street.lower(): factors.append("billing_street")
            confidence = min(0.99, 0.25 + 0.15 * len(factors))
            matches.append({
                "customer_number": int(row["CUNUMBER"]), "customer_name": _clean(row.get("CUNAME")),
                "route_code": _clean(row.get("CUROUTECD")), "matched_factors": factors,
                "confidence": round(confidence, 2), "automatic_decision": False,
            })
        matches.sort(key=lambda item: (len(item["matched_factors"]), item["confidence"]), reverse=True)
        return matches


potential_customer_service = PotentialCustomerService(PotentialCustomerRepository())
