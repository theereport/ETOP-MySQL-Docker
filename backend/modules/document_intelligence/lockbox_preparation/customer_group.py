"""Governed TMCUST CUNUMENT relationship assessment.

The relationship may broaden the read-only invoice context after ETOP has a
uniquely supported customer anchor. It does not authorize cross-customer cash
application, select an account without identity evidence, or hide an invoice
owner conflict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import CustomerGroupSnapshot, dataclass_payload
from .customer_conflict import CustomerConflictAssessment


ENTERPRISE_GROUP_RULE_VERSION = "lockbox-tmcust-cunument-group@1.1.0"


@dataclass(frozen=True)
class EnterpriseGroupAssessment:
    status: str
    anchor_customer_number: str = ""
    enterprise_number: str = ""
    candidate_customer_numbers: tuple[str, ...] = ()
    group_customer_numbers: tuple[str, ...] = ()
    current_open_customer_numbers: tuple[str, ...] = ()
    explanation: str = ""
    rule_version: str = ENTERPRISE_GROUP_RULE_VERSION
    requires_human_review: bool = True
    can_auto_approve: bool = False
    erp_write_performed: bool = False

    def payload(self) -> dict[str, Any]:
        return dataclass_payload(self)


def assess_enterprise_group_conflict(
    *,
    anchor_customer_number: str,
    group: CustomerGroupSnapshot,
    conflict: CustomerConflictAssessment,
) -> EnterpriseGroupAssessment:
    """Resolve only a split-current-owner conflict inside one verified group."""

    anchor = str(anchor_customer_number or "").strip().removesuffix(".0")
    enterprise_number = str(
        group.enterprise_number or ""
    ).strip().removesuffix(".0")
    candidates = tuple(sorted(set(conflict.candidate_customer_numbers)))
    group_customers = tuple(
        sorted(
            {
                str(account.customer_number or "").strip().removesuffix(".0")
                for account in group.accounts
                if str(account.customer_number or "").strip()
            }
        )
    )
    current_owner_sets = tuple(
        tuple(owners)
        for owners in conflict.current_open_invoice_owners.values()
    )
    current_customers = tuple(
        sorted(
            {
                owner
                for owners in current_owner_sets
                for owner in owners
            }
        )
    )
    base = {
        "anchor_customer_number": anchor,
        "enterprise_number": enterprise_number,
        "candidate_customer_numbers": candidates,
        "group_customer_numbers": group_customers,
        "current_open_customer_numbers": current_customers,
    }

    if not anchor or not enterprise_number or enterprise_number == "0":
        return EnterpriseGroupAssessment(
            status="not_applicable",
            explanation=(
                "A unique phone-and-ZIP customer anchor with a nonzero "
                "TMCUST.CUNUMENT relationship was not available."
            ),
            **base,
        )
    if not group.complete:
        return EnterpriseGroupAssessment(
            status="incomplete",
            explanation=(
                "The TMCUST.CUNUMENT account lookup reached its bounded read "
                "limit, so group completeness is not established."
            ),
            **base,
        )
    if conflict.status == "evidence_unavailable":
        return EnterpriseGroupAssessment(
            status="evidence_unavailable",
            explanation=(
                "Current open AR was unavailable for at least one invoice "
                "owner candidate; the enterprise relationship was not used."
            ),
            **base,
        )
    if conflict.missing_current_open_invoices:
        return EnterpriseGroupAssessment(
            status="incomplete",
            explanation=(
                "At least one remittance invoice was absent from current "
                "open AR; the enterprise relationship was not used."
            ),
            **base,
        )
    if not current_owner_sets or any(
        len(owners) != 1
        for owners in current_owner_sets
    ):
        return EnterpriseGroupAssessment(
            status="ambiguous",
            explanation=(
                "Every remittance invoice must have exactly one current ERP "
                "owner before a CUNUMENT relationship can broaden review."
            ),
            **base,
        )

    group_set = set(group_customers)
    if anchor not in group_set or not set(candidates) <= group_set:
        return EnterpriseGroupAssessment(
            status="ambiguous",
            explanation=(
                "The unique phone-and-ZIP anchor and every invoice-owner "
                "candidate do not belong to the same TMCUST.CUNUMENT group."
            ),
            **base,
        )
    if not set(current_customers) <= group_set:
        return EnterpriseGroupAssessment(
            status="ambiguous",
            explanation=(
                "A current remittance invoice owner falls outside the "
                "verified TMCUST.CUNUMENT group."
            ),
            **base,
        )

    return EnterpriseGroupAssessment(
        status="resolved",
        explanation=(
            "A unique normalized phone-and-five-digit-ZIP match identifies "
            f"ERP customer {anchor}, and every current remittance invoice "
            f"owner belongs to TMCUST.CUNUMENT group {enterprise_number}. "
            "Linked-account invoices are available for professional "
            "verification; cross-customer application is not authorized."
        ),
        **base,
    )
