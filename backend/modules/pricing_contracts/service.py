from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .notes_repository import PricingNotesRepository, pricing_notes_repository
from .repository import PricingContractsRepository, pricing_contracts_repository
from .schemas import (
    CustomerClassRecord,
    CustomerClassResponse,
    DiscountEvidenceResponse,
    DiscountRecord,
    DiscountSearchResponse,
    PricingEvidenceGap,
    PricingNoteCreate,
    PricingNoteHistoryResponse,
    PricingNoteRecord,
    SourceEvidence,
)


class DiscountNotFound(LookupError):
    """Raised when MaddenCo has no TMDISC row matching the requested key."""


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


def _parse_erp_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    text = _clean_text(value)
    return text or None


def _number(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


_GAPS = [
    PricingEvidenceGap(
        code="vendor_rebate_accrual_ledger",
        label="Vendor rebate accrual ledger",
        explanation=(
            "No vendor rebate accrual table exists in the current MaddenCo "
            "schema. Rebate program commitments can only be tracked as "
            "local, append-only pricing/contract notes attached to a "
            "customer and, optionally, a vendor code and/or product — not "
            "as a computed accrual balance."
        ),
    ),
    PricingEvidenceGap(
        code="contract_compliance_scoring",
        label="Contract compliance scoring",
        explanation=(
            "No approved contract-compliance scoring model is configured. "
            "This module presents TMDISC's own stored override values; it "
            "computes no compliance score, rank, or automatic flag."
        ),
    ),
    PricingEvidenceGap(
        code="vendor_code_identity_resolution",
        label="DCVENDOR to AP vendor number mapping",
        explanation=(
            "TMDISC.DCVENDOR is a 3-character product-vendor code. It has "
            "not been confirmed to map to the 7-digit AP vendor number "
            "(PMVEND.PVNUMVEN) used elsewhere in ETOP (for example, in "
            "Vendor Intelligence). No join between the two is performed; "
            "DCVENDOR is shown only as its own literal code."
        ),
    ),
    PricingEvidenceGap(
        code="price_code_mechanism_mapping",
        label="Price code to pricing-mechanism mapping",
        explanation=(
            "No governed mapping of DCPRICECD values to which pricing "
            "mechanic MaddenCo's engine actually applies is configured. "
            "DCPRICE, DCAMTFIX, DCFACTOR, and DCPRICECD are shown "
            "side by side as literal stored values; this module does not "
            "assert which one produces the final sale price."
        ),
    ),
]


class PricingContractsService:
    """Build source-grounded, evidence-only pricing/contract responses."""

    def __init__(
        self,
        *,
        repository: PricingContractsRepository = pricing_contracts_repository,
        notes_repository: PricingNotesRepository = pricing_notes_repository,
        clock: Callable[[], datetime] = _now,
        note_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._notes_repository = notes_repository
        self._clock = clock
        self._note_id_factory = note_id_factory or (
            lambda: f"pricing-note-{uuid4().hex}"
        )

    def _record_from_row(self, row: dict[str, Any]) -> DiscountRecord:
        customer_number = _integer(row.get("DCCUSTNO"))
        vendor_code = _clean_text(row.get("DCVENDOR"))
        product_class = _clean_text(row.get("DCPRODCLAS"))
        product_number = _clean_text(row.get("DCPRODNO"))
        product_type = _clean_text(row.get("DCPRODTYPE"))
        delete_code = _clean_text(row.get("DCDELETE"))
        class_active = _clean_text(row.get("PRODCLASSACTIVE"))
        record_key = ":".join(
            [
                str(customer_number),
                product_class,
                product_number,
                product_type,
                vendor_code,
            ]
        )
        return DiscountRecord(
            record_key=record_key,
            customer_number=customer_number,
            vendor_code=vendor_code,
            product_class=product_class,
            product_class_label=_clean_text(row.get("PRODCLASSNAME")),
            product_class_item_type=_clean_text(row.get("PRODCLASSITEMTYPE")),
            product_class_active=(
                class_active.upper() == "Y" if class_active else None
            ),
            product_number=product_number,
            product_type=product_type,
            delete_code=delete_code,
            active=delete_code == "",
            fixed_amount=_number(row.get("DCAMTFIX")),
            chain=_integer(row.get("DCCHAIN")),
            factor=_number(row.get("DCFACTOR")),
            override_price=_number(row.get("DCPRICE")),
            price_code=_integer(row.get("DCPRICECD")),
            date_added=_parse_erp_date(row.get("DCDTEADD")),
            date_changed=_parse_erp_date(row.get("DCDTECHG")),
            time_added=_clean_text(row.get("DCTIMADD")),
            time_changed=_clean_text(row.get("DCTIMCHG")),
            added_by=_clean_text(row.get("DCUSRADD")),
            changed_by=_clean_text(row.get("DCUSRCHG")),
        )

    def search_discounts(
        self,
        *,
        customer_number: int | None = None,
        product_number: str = "",
        product_class: str = "",
        vendor_code: str = "",
        active_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> DiscountSearchResponse:
        rows = self._repository.search_discounts(
            customer_number=customer_number,
            product_number=product_number,
            product_class=product_class,
            vendor_code=vendor_code,
            active_only=active_only,
            limit=limit,
            offset=offset,
        )
        retrieved_at = self._clock().astimezone(UTC).isoformat()
        discounts = [self._record_from_row(row) for row in rows]
        return DiscountSearchResponse(
            source=SourceEvidence(retrieved_at=retrieved_at),
            count=len(discounts),
            discounts=discounts,
            gaps=list(_GAPS),
        )

    def get_discount(
        self,
        *,
        customer_number: int,
        vendor_code: str,
        product_class: str,
        product_number: str,
        product_type: str,
    ) -> DiscountEvidenceResponse:
        row = self._repository.get_discount(
            customer_number=customer_number,
            vendor_code=vendor_code,
            product_class=product_class,
            product_number=product_number,
            product_type=product_type,
        )
        if row is None:
            raise DiscountNotFound(
                "No TMDISC row was found for customer "
                f"{customer_number}, vendor code '{vendor_code}', "
                f"product class '{product_class}', product number "
                f"'{product_number}', product type '{product_type}'."
            )
        retrieved_at = self._clock().astimezone(UTC).isoformat()
        return DiscountEvidenceResponse(
            generated_at=retrieved_at,
            source=SourceEvidence(retrieved_at=retrieved_at),
            discount=self._record_from_row(row),
            gaps=list(_GAPS),
        )

    def list_customer_classes(
        self,
        *,
        search: str = "",
        active_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> CustomerClassResponse:
        rows = self._repository.get_customer_classes(
            search=search,
            active_only=active_only,
            limit=limit,
            offset=offset,
        )
        retrieved_at = self._clock().astimezone(UTC).isoformat()
        classes = [
            CustomerClassRecord(
                id=_integer(row.get("ID")),
                class_num=_clean_text(row.get("CLASSNUM")),
                class_name=_clean_text(row.get("CLASSNAME")),
                active=_clean_text(row.get("ACTIVE")).upper() == "Y",
                created_at=_parse_erp_datetime(row.get("CRTSTAMP")),
                created_by=_clean_text(row.get("CRTUSER")),
                changed_at=_parse_erp_datetime(row.get("CHGSTAMP")),
                changed_by=_clean_text(row.get("CHGUSER")),
            )
            for row in rows
        ]
        return CustomerClassResponse(
            source=SourceEvidence(retrieved_at=retrieved_at),
            count=len(classes),
            customer_classes=classes,
        )

    def list_notes(
        self,
        customer_number: int,
        *,
        vendor_code: str | None = None,
        product_class: str | None = None,
        product_number: str | None = None,
        product_type: str | None = None,
    ) -> PricingNoteHistoryResponse:
        records = [
            PricingNoteRecord(**record)
            for record in self._notes_repository.list_notes(
                customer_number,
                vendor_code=vendor_code,
                product_class=product_class,
                product_number=product_number,
                product_type=product_type,
            )
        ]
        return PricingNoteHistoryResponse(
            customer_number=customer_number,
            count=len(records),
            notes=records,
        )

    def create_note(self, payload: PricingNoteCreate) -> PricingNoteRecord:
        # Notes deliberately do not require an existing TMDISC row: rebate
        # program commitments are often made ahead of (or entirely without)
        # a matching pricing override row, and this module has no other
        # place to record them (see the `vendor_rebate_accrual_ledger` gap).
        # The evidence snapshot embeds whatever TMDISC rows currently match
        # the supplied scope, including zero.
        matching_rows = self._repository.search_discounts(
            customer_number=payload.customer_number,
            vendor_code=payload.vendor_code or "",
            product_class=payload.product_class or "",
            product_number=payload.product_number or "",
            active_only=False,
            limit=200,
        )
        if payload.product_type:
            matching_rows = [
                row
                for row in matching_rows
                if _clean_text(row.get("DCPRODTYPE")) == payload.product_type
            ]

        matched_discounts = [self._record_from_row(row) for row in matching_rows]
        created_at = self._clock().astimezone(UTC).isoformat()
        evidence_snapshot = {
            "scope": {
                "customer_number": payload.customer_number,
                "vendor_code": payload.vendor_code,
                "product_class": payload.product_class,
                "product_number": payload.product_number,
                "product_type": payload.product_type,
            },
            "matched_discounts": [
                discount.model_dump(mode="json") for discount in matched_discounts
            ],
            "gaps": [gap.model_dump(mode="json") for gap in _GAPS],
        }
        record = {
            "note_id": self._note_id_factory(),
            "customer_number": payload.customer_number,
            "vendor_code": payload.vendor_code,
            "product_class": payload.product_class,
            "product_number": payload.product_number,
            "product_type": payload.product_type,
            "author_identity": payload.author_identity,
            "note": payload.note,
            "created_at": created_at,
            "source_as_of": created_at,
            "matched_discount_count": len(matched_discounts),
            "actor_identity_source": "operator_supplied",
            "actor_authority_status": "not_independently_verified",
            "note_classification": "professional_workflow_metadata",
            "decision_effect": "none",
            "evidence_snapshot": evidence_snapshot,
        }
        return PricingNoteRecord(
            **self._notes_repository.create_note(record)
        )


pricing_contracts_service = PricingContractsService()
