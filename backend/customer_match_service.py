from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable

from invoice_number_rules import normalize_erp_invoice


CUSTOMER_MATCH_RULE_VERSION = (
    "lockbox-customer-match-evidence@0.7.0-wave2-increment3o"
)
_NON_ALPHANUMERIC = re.compile(r"[^A-Z0-9]+")
_STREET_REPLACEMENTS = {
    "STREET": "ST",
    "ROAD": "RD",
    "AVENUE": "AVE",
    "BOULEVARD": "BLVD",
    "DRIVE": "DR",
    "LANE": "LN",
    "HIGHWAY": "HWY",
    "ROUTE": "RTE",
    "NORTH": "N",
    "SOUTH": "S",
    "EAST": "E",
    "WEST": "W",
}


@dataclass(frozen=True)
class CustomerMatchInput:
    invoice_numbers: tuple[str, ...] = ()
    phone: str = ""
    address_line_1: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    customer_name: str = ""
    search_text: str = ""


def normalize_text(value: Any) -> str:
    return " ".join(
        _NON_ALPHANUMERIC.sub(" ", str(value or "").upper()).split()
    )


def normalize_phone(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    return digits


def normalize_postal(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))[:5]


normalize_invoice = normalize_erp_invoice


def normalize_address(value: Any) -> str:
    words = normalize_text(value).split()
    return " ".join(_STREET_REPLACEMENTS.get(word, word) for word in words)


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _customer_number(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def _invoice_evidence(
    customer_number: str,
    invoice_owners: dict[str, set[str]],
) -> list[str]:
    evidence: list[str] = []
    for invoice_number, owners in invoice_owners.items():
        if customer_number in owners:
            evidence.append(invoice_number)
    return evidence


def exact_phone_postal_matches(
    customers: Iterable[dict[str, Any]],
    match_input: CustomerMatchInput,
) -> list[dict[str, Any]]:
    """Return exact normalized phone plus first-five ZIP matches."""

    supplied_phone = normalize_phone(match_input.phone)
    supplied_postal = normalize_postal(match_input.postal_code)
    if len(supplied_phone) != 10 or len(supplied_postal) != 5:
        return []
    return [
        customer
        for customer in customers
        if len(normalize_phone(customer.get("phone"))) == 10
        and normalize_phone(customer.get("phone")) == supplied_phone
        and normalize_postal(customer.get("postal_code")) == supplied_postal
    ]


def exact_phone_matches(
    customers: Iterable[dict[str, Any]],
    match_input: CustomerMatchInput,
) -> list[dict[str, Any]]:
    """Return full ten-digit normalized phone matches.

    The caller must separately prove that the bounded ERP phone-candidate
    query was complete before treating one returned row as unique.
    """

    supplied_phone = normalize_phone(match_input.phone)
    if len(supplied_phone) != 10:
        return []
    return [
        customer
        for customer in customers
        if len(normalize_phone(customer.get("phone"))) == 10
        and normalize_phone(customer.get("phone")) == supplied_phone
    ]


def exact_address_postal_matches(
    customers: Iterable[dict[str, Any]],
    match_input: CustomerMatchInput,
) -> list[dict[str, Any]]:
    """Return exact normalized street plus first-five ZIP matches.

    The caller must separately prove that its bounded ZIP-candidate query was
    complete before treating one returned row as unique. Name similarity is
    deliberately excluded from this deterministic identity rule.
    """

    supplied_address = normalize_address(match_input.address_line_1)
    supplied_postal = normalize_postal(match_input.postal_code)
    if not supplied_address or len(supplied_postal) != 5:
        return []
    return [
        customer
        for customer in customers
        if normalize_address(customer.get("address_line_1"))
        == supplied_address
        and normalize_postal(customer.get("postal_code"))
        == supplied_postal
    ]


def score_candidate(
    customer: dict[str, Any],
    match_input: CustomerMatchInput,
    invoice_owners: dict[str, set[str]],
) -> dict[str, Any]:
    customer_number = _customer_number(customer.get("customer_number"))
    score = 0.0
    matched_on: list[str] = []
    match_strengths: list[str] = []

    owned_invoices = _invoice_evidence(customer_number, invoice_owners)
    if owned_invoices:
        score += 110 + (min(len(owned_invoices), 3) - 1) * 8
        matched_on.append(
            "Invoice "
            + ", ".join(owned_invoices)
            + " belongs to this ERP customer."
        )
        match_strengths.append("invoice")

    supplied_phone = normalize_phone(match_input.phone)
    customer_phone = normalize_phone(customer.get("phone"))
    if (
        len(supplied_phone) >= 7
        and len(customer_phone) >= 7
        and supplied_phone == customer_phone
    ):
        score += 72
        matched_on.append("Phone number matches the ERP customer.")
        match_strengths.append("phone")

    supplied_address = normalize_address(match_input.address_line_1)
    customer_address = normalize_address(customer.get("address_line_1"))
    address_similarity = _similarity(supplied_address, customer_address)
    if address_similarity >= 0.88:
        score += 38
        matched_on.append("Street address is an exact or near-exact match.")
        match_strengths.append("address")
    elif address_similarity >= 0.68:
        score += 22
        matched_on.append("Street address is a probable match.")
        match_strengths.append("address")

    supplied_postal = normalize_postal(match_input.postal_code)
    customer_postal = normalize_postal(customer.get("postal_code"))
    if len(supplied_postal) == 5 and supplied_postal == customer_postal:
        score += 26
        matched_on.append(f"ZIP code {supplied_postal} matches.")
        match_strengths.append("postal")

    supplied_city = normalize_text(match_input.city)
    customer_city = normalize_text(customer.get("city"))
    if supplied_city and supplied_city == customer_city:
        score += 5
        matched_on.append("City matches.")

    supplied_state = normalize_text(match_input.state)
    customer_state = normalize_text(customer.get("state"))
    if supplied_state and supplied_state == customer_state:
        score += 5
        matched_on.append("State matches.")

    supplied_name = normalize_text(
        match_input.customer_name or match_input.search_text
    )
    customer_name = normalize_text(customer.get("customer_name"))
    name_similarity = _similarity(supplied_name, customer_name)
    if name_similarity >= 0.94:
        score += 12
        matched_on.append("Customer name is a near-exact match.")
    elif name_similarity >= 0.72:
        score += 7
        matched_on.append("Customer name is similar.")

    search_text = normalize_text(match_input.search_text)
    if search_text:
        number_search = re.sub(r"\D", "", match_input.search_text)
        if number_search and customer_number.startswith(number_search):
            score += 60 if customer_number == number_search else 30
            matched_on.insert(0, "ERP customer number matches the search.")
            match_strengths.append("number")
        elif search_text in customer_name:
            score += 18
            matched_on.append("Customer name contains the search text.")

    if "invoice" in match_strengths:
        confidence = 0.99
        match_type = "invoice"
    elif "phone" in match_strengths and "postal" in match_strengths:
        confidence = 1.0 if "address" in match_strengths else 0.97
        match_type = "phone_and_zip"
    elif "address" in match_strengths and "postal" in match_strengths:
        confidence = 0.87
        match_type = "address_and_zip"
    elif "number" in match_strengths:
        confidence = 0.98 if score >= 60 else 0.72
        match_type = "customer_number"
    else:
        confidence = min(0.65, score / 100)
        match_type = "supporting_details"

    return {
        "customer_number": customer_number,
        "customer_name": str(customer.get("customer_name") or "").strip(),
        "phone": str(customer.get("phone") or "").strip(),
        "address_line_1": str(customer.get("address_line_1") or "").strip(),
        "address_line_2": str(customer.get("address_line_2") or "").strip(),
        "city": str(customer.get("city") or "").strip(),
        "state": str(customer.get("state") or "").strip(),
        "postal_code": str(customer.get("postal_code") or "").strip(),
        "enterprise_number": _customer_number(
            customer.get("enterprise_number")
        ),
        "score": round(score, 2),
        "confidence": confidence,
        "match_type": match_type,
        "matched_on": matched_on,
        "matched_invoice_numbers": owned_invoices,
    }


def rank_customer_matches(
    customers: Iterable[dict[str, Any]],
    match_input: CustomerMatchInput,
    invoice_owners: dict[str, set[str]] | None = None,
    limit: int = 8,
    *,
    contact_candidate_complete: bool = False,
    address_candidate_complete: bool = False,
) -> dict[str, Any]:
    owners = invoice_owners or {}
    customer_rows = list(customers)
    invoice_owner_candidates = sorted(
        {
            _customer_number(customer_number)
            for customer_numbers in owners.values()
            for customer_number in customer_numbers
            if _customer_number(customer_number)
        }
    )
    invoice_owner_conflict = len(invoice_owner_candidates) > 1
    owner_cardinalities = {
        invoice: len(
            {
                _customer_number(customer_number)
                for customer_number in customer_numbers
                if _customer_number(customer_number)
            }
        )
        for invoice, customer_numbers in owners.items()
    }
    has_invoice_owner_evidence = any(
        count > 0 for count in owner_cardinalities.values()
    )
    unresolved_invoice_owner_count = sum(
        count == 0 for count in owner_cardinalities.values()
    )
    partial_invoice_owner_evidence = bool(
        has_invoice_owner_evidence and unresolved_invoice_owner_count
    )
    exact_phone_candidates = exact_phone_matches(
        customer_rows,
        match_input,
    )
    exact_contact_matches = exact_phone_postal_matches(
        customer_rows,
        match_input,
    )
    exact_address_matches = exact_address_postal_matches(
        customer_rows,
        match_input,
    )
    exact_phone_unique = bool(
        contact_candidate_complete and len(exact_phone_candidates) == 1
    )
    exact_contact_unique = bool(
        contact_candidate_complete and len(exact_contact_matches) == 1
    )
    exact_address_unique = bool(
        address_candidate_complete and len(exact_address_matches) == 1
    )
    scored = [
        score_candidate(customer, match_input, owners)
        for customer in customer_rows
        if _customer_number(customer.get("customer_number"))
    ]
    scored = [candidate for candidate in scored if candidate["score"] > 0]
    scored.sort(
        key=lambda candidate: (
            candidate["score"],
            candidate["confidence"],
            candidate["customer_number"],
        ),
        reverse=True,
    )
    deterministic_phone_number = (
        _customer_number(exact_phone_candidates[0].get("customer_number"))
        if exact_phone_unique
        else _customer_number(
            exact_contact_matches[0].get("customer_number")
        )
        if exact_contact_unique
        else ""
    )
    deterministic_phone_candidate = next(
        (
            candidate
            for candidate in scored
            if candidate["customer_number"] == deterministic_phone_number
        ),
        None,
    )
    deterministic_address_number = (
        _customer_number(exact_address_matches[0].get("customer_number"))
        if exact_address_unique
        else ""
    )
    deterministic_address_candidate = next(
        (
            candidate
            for candidate in scored
            if candidate["customer_number"] == deterministic_address_number
        ),
        None,
    )
    unique_complete_invoice_owner = bool(
        has_invoice_owner_evidence
        and len(invoice_owner_candidates) == 1
        and not partial_invoice_owner_evidence
    )
    if (
        deterministic_phone_candidate is not None
        and not unique_complete_invoice_owner
    ):
        ordered = [
            deterministic_phone_candidate,
            *(
                candidate
                for candidate in scored
                if candidate["customer_number"]
                != deterministic_phone_number
            ),
        ]
    elif (
        deterministic_address_candidate is not None
        and not unique_complete_invoice_owner
    ):
        ordered = [
            deterministic_address_candidate,
            *(
                candidate
                for candidate in scored
                if candidate["customer_number"]
                != deterministic_address_number
            ),
        ]
    else:
        ordered = scored
    selected = ordered[:limit]

    top = selected[0] if selected else None
    runner_up = selected[1] if len(selected) > 1 else None
    lead = (
        float(top["score"]) - float(runner_up["score"])
        if top and runner_up
        else float(top["score"]) if top else 0
    )
    has_primary_evidence = bool(
        top
        and top["match_type"] in {
            "invoice",
            "phone_and_zip",
            "customer_number",
        }
    )
    generic_auto_select = bool(
        top
        and has_primary_evidence
        and not invoice_owner_conflict
        and not partial_invoice_owner_evidence
        and (
            top["match_type"] != "phone_and_zip"
            or exact_contact_unique
        )
        and float(top["score"]) >= 60
        and (runner_up is None or lead >= 15)
    )
    exact_contact_select = bool(
        deterministic_phone_candidate
        and exact_contact_unique
        and not has_invoice_owner_evidence
        and not invoice_owner_conflict
        and not partial_invoice_owner_evidence
    )
    supplied_postal = normalize_postal(match_input.postal_code)
    unique_phone_postal = normalize_postal(
        exact_phone_candidates[0].get("postal_code")
    ) if exact_phone_unique else ""
    unique_phone_postal_conflict = bool(
        exact_phone_unique
        and len(supplied_postal) == 5
        and len(unique_phone_postal) == 5
        and supplied_postal != unique_phone_postal
    )
    exact_phone_select = bool(
        deterministic_phone_candidate
        and exact_phone_unique
        and not unique_phone_postal_conflict
        and not has_invoice_owner_evidence
        and not invoice_owner_conflict
        and not partial_invoice_owner_evidence
    )
    supplied_phone = normalize_phone(match_input.phone)
    address_candidate_phone = normalize_phone(
        exact_address_matches[0].get("phone")
    ) if exact_address_unique else ""
    address_phone_conflict = bool(
        exact_address_unique
        and len(supplied_phone) == 10
        and (
            len(address_candidate_phone) != 10
            or supplied_phone != address_candidate_phone
        )
    )
    exact_address_select = bool(
        deterministic_address_candidate
        and exact_address_unique
        and not address_phone_conflict
        and not has_invoice_owner_evidence
        and not invoice_owner_conflict
        and not partial_invoice_owner_evidence
        and not exact_phone_select
        and not exact_contact_select
    )
    if exact_phone_select and not exact_contact_select:
        deterministic_phone_candidate["match_type"] = "unique_phone"
        deterministic_phone_candidate["confidence"] = 0.99
    if exact_address_select:
        deterministic_address_candidate["match_type"] = (
            "exact_address_and_zip"
        )
        deterministic_address_candidate["confidence"] = 1.0
    auto_select = (
        generic_auto_select
        or exact_contact_select
        or exact_phone_select
        or exact_address_select
    )
    selected_basis = (
        "exact_phone_and_zip"
        if exact_contact_select
        else "unique_exact_phone"
        if exact_phone_select
        else "exact_address_and_zip"
        if exact_address_select
        else str(top.get("match_type") or "") if auto_select and top else ""
    )

    failed_gates: list[str] = []
    if invoice_owner_conflict:
        failed_gates.append("invoice_owner_conflict")
    if partial_invoice_owner_evidence:
        failed_gates.append("partial_invoice_owner_evidence")
    if exact_contact_matches and not contact_candidate_complete:
        failed_gates.append("contact_candidate_set_incomplete")
    if exact_phone_candidates and not contact_candidate_complete:
        failed_gates.append("phone_candidate_set_incomplete")
    if exact_address_matches and not address_candidate_complete:
        failed_gates.append("address_candidate_set_incomplete")
    if len(exact_phone_candidates) > 1 and not exact_contact_select:
        failed_gates.append("duplicate_exact_phone")
    if unique_phone_postal_conflict:
        failed_gates.append("unique_phone_postal_conflict")
    if address_phone_conflict:
        failed_gates.append("address_phone_conflict")
    if len(exact_contact_matches) > 1:
        failed_gates.append("duplicate_exact_phone_zip")
    if (
        top
        and not has_primary_evidence
        and not exact_phone_select
        and not exact_address_select
    ):
        failed_gates.append("supporting_evidence_only")
    if (
        top
        and float(top["score"]) < 60
        and not exact_contact_select
        and not exact_address_select
    ):
        failed_gates.append("primary_score_below_existing_gate")
    if (
        top
        and runner_up
        and lead < 15
        and not exact_contact_select
        and not exact_address_select
    ):
        failed_gates.append("existing_rank_lead_not_met")

    if auto_select and top:
        message = (
            f"Recommended ERP customer {top['customer_number']} from "
            f"{top['match_type'].replace('_', ' ')} evidence."
        )
    elif invoice_owner_conflict:
        message = (
            "Remittance invoice evidence identifies multiple ERP customer "
            "owners. Current open AR or professional review must resolve the "
            "conflict; contact and ranking scores cannot select one."
        )
    elif partial_invoice_owner_evidence:
        message = (
            "At least one valid remittance invoice has an ERP owner while "
            "another valid invoice has no owner. The partial invoice evidence "
            "cannot be ignored or overridden by contact scoring."
        )
    elif unique_phone_postal_conflict:
        message = (
            "One ERP customer owns the exact normalized phone, but the "
            "supplied five-digit ZIP conflicts with that customer. The "
            "customer remains in review."
        )
    elif address_phone_conflict:
        message = (
            "One ERP customer owns the exact street-and-ZIP identity, but "
            "the supplied phone conflicts with that customer. The customer "
            "remains in review."
        )
    elif len(exact_phone_candidates) > 1 and not exact_contact_select:
        message = (
            "The exact normalized phone belongs to multiple ERP customers, "
            "and the available ZIP evidence did not identify one unique "
            "customer."
        )
    elif top and top["match_type"] == "phone_and_zip" and not exact_contact_unique:
        message = (
            "Phone and ZIP evidence did not establish exactly one customer "
            "across a complete bounded ERP candidate query."
        )
    elif top:
        message = (
            "Possible ERP customers were found, but the evidence is not "
            "strong enough to select one automatically."
        )
    else:
        message = "No ERP customer matched the available lockbox details."

    return {
        "recommended_customer": top if auto_select else None,
        "candidates": selected,
        "auto_select": auto_select,
        "message": message,
        "invoice_owner_conflict": invoice_owner_conflict,
        "invoice_owner_candidates": invoice_owner_candidates,
        "unresolved_invoice_owner_count": unresolved_invoice_owner_count,
        "partial_invoice_owner_evidence": partial_invoice_owner_evidence,
        "exact_phone_match_count": len(exact_phone_candidates),
        "exact_phone_postal_match_count": len(exact_contact_matches),
        "exact_address_postal_match_count": len(exact_address_matches),
        "contact_candidate_complete": contact_candidate_complete,
        "address_candidate_complete": address_candidate_complete,
        "ranked_candidate_count": len(scored),
        "top_score": float(top["score"]) if top else None,
        "runner_up_score": (
            float(runner_up["score"]) if runner_up else None
        ),
        "score_lead": lead,
        "selected_basis": selected_basis,
        "failed_selection_gates": failed_gates,
        "rule_version": CUSTOMER_MATCH_RULE_VERSION,
    }
