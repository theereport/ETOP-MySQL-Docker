from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from .notes_repository import InventoryNotesRepository, inventory_notes_repository
from .repository import InventoryPurchasingRepository, inventory_purchasing_repository
from .schemas import (
    InventoryNoteCreate,
    InventoryNoteHistoryResponse,
    InventoryNoteRecord,
    MonthEndInventoryEvidence,
    MonthEndInventoryPeriod,
    OpenPurchaseOrderLine,
    ProductCostingEvidence,
    ProductEvidenceGap,
    ProductEvidenceResponse,
    ProductIdentityEvidence,
    ProductInventoryPositionEvidence,
    ProductSearchResponse,
    ProductSearchResult,
    PurchaseExposureEvidence,
    ReceivingEvent,
    ReceivingEvidence,
    SourceEvidence,
)


class ProductNotFound(LookupError):
    """Raised when MaddenCo has no product matching the requested number."""


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
    ProductEvidenceGap(
        code="reorder_point_formula",
        label="Reorder point / safety stock formula",
        explanation=(
            "No approved reorder-point or safety-stock formula is "
            "configured. MaddenCo's own configured order-generation "
            "thresholds (TMPROD.PDMIN / PDMAX), when populated, are shown "
            "as-is under inventory position; ETOP computes no reorder "
            "point of its own."
        ),
    ),
    ProductEvidenceGap(
        code="real_time_onhand_by_warehouse",
        label="Real-time on-hand quantity by warehouse",
        explanation=(
            "The current MaddenCo schema exposes no verified live, "
            "real-time perpetual inventory feed broken out by warehouse. "
            "The only inventory-position history available for trending "
            "is the periodic month-end snapshot in EOMINV/INEOMINV. "
            "TMPROD's on-hand/on-order/allocated fields are MaddenCo's "
            "last-committed product-master values, not a live warehouse "
            "feed."
        ),
    ),
    ProductEvidenceGap(
        code="demand_forecast_turnover_rate",
        label="Demand forecast / turnover-rate calculation",
        explanation=(
            "ETOP computes no demand forecast or turnover-rate figure. "
            "TMPROD.PDINVTURNS, when populated, is shown as MaddenCo's own "
            "stored value, not an ETOP-derived calculation."
        ),
    ),
    ProductEvidenceGap(
        code="vendor_number_cross_reference",
        label="Product-master vendor code cross-reference",
        explanation=(
            "TMPROD.PDVENDOR is a short vendor code stored on the product "
            "master; no verified mapping to PMVEND's numeric vendor number "
            "(as used by the Vendor Intelligence module) is joined in this "
            "module, so the two vendor identifiers are not reconciled here."
        ),
    ),
    ProductEvidenceGap(
        code="extended_product_attributes",
        label="Price history and extended product attributes",
        explanation=(
            "MaddenCo's TMPDHS (product price history) and TMPDIF "
            "(extended product info: picture reference, warranty, UTQG "
            "grade) tables exist in the current schema but are out of "
            "scope for this increment."
        ),
    ),
]


class InventoryPurchasingService:
    """Build source-grounded, evidence-only product intelligence responses."""

    def __init__(
        self,
        *,
        repository: InventoryPurchasingRepository = inventory_purchasing_repository,
        notes_repository: InventoryNotesRepository = inventory_notes_repository,
        clock: Callable[[], datetime] = _now,
        note_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._notes_repository = notes_repository
        self._clock = clock
        self._note_id_factory = note_id_factory or (
            lambda: f"inventory-note-{uuid4().hex}"
        )

    def search_products(
        self,
        *,
        search: str = "",
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> ProductSearchResponse:
        rows = self._repository.search_products(
            search=search,
            active_only=active_only,
            limit=limit,
            offset=offset,
        )
        retrieved_at = self._clock().astimezone(UTC).isoformat()
        results = [
            ProductSearchResult(
                product_number=_clean_text(row.get("PDNUMBER")),
                description=_clean_text(row.get("PDDESCRIP")),
                search_key=_clean_text(row.get("PDSEARCHKY")),
                product_class=_clean_text(row.get("PDCLASS")),
                product_type=_clean_text(row.get("PDTYPE")),
                brand=_clean_text(row.get("PDBRAND")),
                unit_of_measure=_clean_text(row.get("PDUNITMEAS")),
                vendor_code=_clean_text(row.get("PDVENDOR")),
                active=_clean_text(row.get("PDDELETE")) in ("", "A"),
                non_inventory=_clean_text(row.get("PDNONINV")).upper() == "Y",
            )
            for row in rows
        ]
        return ProductSearchResponse(
            source=SourceEvidence(retrieved_at=retrieved_at),
            count=len(results),
            products=results,
        )

    def get_product_evidence(self, product_number: str) -> ProductEvidenceResponse:
        row = self._repository.get_product(product_number)
        if row is None:
            raise ProductNotFound(
                f"Product {product_number} was not found in MaddenCo."
            )

        retrieved_at = self._clock().astimezone(UTC).isoformat()
        source = SourceEvidence(retrieved_at=retrieved_at)

        identity = ProductIdentityEvidence(
            product_number=_clean_text(row.get("PDNUMBER")),
            search_key=_clean_text(row.get("PDSEARCHKY")),
            description=_clean_text(row.get("PDDESCRIP")),
            product_class=_clean_text(row.get("PDCLASS")),
            product_type=_clean_text(row.get("PDTYPE")),
            brand=_clean_text(row.get("PDBRAND")),
            size=_clean_text(row.get("PDSIZE")),
            load_index=_clean_text(row.get("PDLOADINDX")),
            speed_rating=_clean_text(row.get("PDSPEEDRAT")),
            manufacturer_product_number=_clean_text(row.get("PDMFGPRDNO")),
            barcode=_clean_text(row.get("PDBARCODE")),
            unit_of_measure=_clean_text(row.get("PDUNITMEAS")),
            vendor_code=_clean_text(row.get("PDVENDOR")),
            store_number=_optional_int(row.get("PDSTORE")),
            warehouse_location=_clean_text(row.get("PDWAREHSE")),
            warehouse_alt_location=_clean_text(row.get("PDWAREHALT")),
            active=_clean_text(row.get("PDDELETE")) in ("", "A"),
            non_inventory=_clean_text(row.get("PDNONINV")).upper() == "Y",
            allow_po_creation=_clean_text(row.get("PDALLOWPO")).upper() == "Y",
            date_created=_parse_erp_date(row.get("PDDTECRT")),
            date_last_received=_parse_erp_date(row.get("PDRECVDATE")),
            date_last_sold=_parse_erp_date(row.get("PDSOLDDATE")),
        )

        costing = ProductCostingEvidence(
            vendor_cost=_optional_number(row.get("PDVENDCOST")),
            actual_cost=_optional_number(row.get("PDACTCOST")),
            replacement_cost=_optional_number(row.get("PDREPLCOST")),
            last_year_cost=_optional_number(row.get("PDLYRCOST")),
            price_1=_optional_number(row.get("PDPRICE1")),
            price_2=_optional_number(row.get("PDPRICE2")),
            price_3=_optional_number(row.get("PDPRICE3")),
            price_4=_optional_number(row.get("PDPRICE4")),
            price_5=_optional_number(row.get("PDPRICE5")),
            price_6=_optional_number(row.get("PDPRICE6")),
        )

        inventory_position = ProductInventoryPositionEvidence(
            on_hand=_optional_number(row.get("PDINVENTRY")),
            on_order=_optional_number(row.get("PDONORDER")),
            allocated=_optional_number(row.get("PDALLOCATD")),
            configured_minimum=_optional_number(row.get("PDMIN")),
            configured_maximum=_optional_number(row.get("PDMAX")),
            inventory_turns=_optional_number(row.get("PDINVTURNS")),
            ordering_lead_time_days=_optional_int(row.get("PDLEADTIM")),
        )

        month_end_inventory = self._build_month_end_inventory(product_number)
        purchase_exposure = self._build_purchase_exposure(product_number)
        receiving = self._build_receiving_evidence(product_number)

        return ProductEvidenceResponse(
            generated_at=retrieved_at,
            source=source,
            identity=identity,
            costing=costing,
            inventory_position=inventory_position,
            month_end_inventory=month_end_inventory,
            purchase_exposure=purchase_exposure,
            receiving=receiving,
            gaps=list(_GAPS),
        )

    def _build_month_end_inventory(
        self,
        product_number: str,
    ) -> MonthEndInventoryEvidence:
        try:
            rows = self._repository.get_month_end_inventory(product_number)
        except HTTPException:
            # EOMINV has ~48M rows and PARTNUM is the last column of its
            # composite primary key, so a PARTNUM-only filter cannot use an
            # index and forces a full-table scan that exceeds the
            # statement timeout for most products. This is a real MaddenCo
            # schema/indexing constraint ETOP cannot alter, not a missing
            # or zero value.
            return MonthEndInventoryEvidence(
                status="unavailable_source_capability",
                period_count=0,
                periods=[],
                latest_period_total_units=None,
                latest_period_total_cost=None,
                explanation=(
                    "Month-end inventory is unavailable for this product: "
                    "EOMINV has no index usable for a PARTNUM-only filter "
                    "(PARTNUM is the last column of its composite primary "
                    "key) and the query exceeded the source database's "
                    "statement timeout. This is a source-side indexing "
                    "constraint, not an absence of inventory data."
                ),
            )
        periods = [
            MonthEndInventoryPeriod(
                store_number=_optional_int(row.get("STORENUM")),
                month=_optional_int(row.get("MONTH")),
                year=_optional_int(row.get("YEAR")),
                vendor_number=_clean_text(row.get("VENDNUM")),
                class_number=_clean_text(row.get("CLASSNUM")),
                units=_number(row.get("UNITS")),
                total_cost=_number(row.get("TOTALCOST")),
                total_fet=_number(row.get("TOTALFET")),
            )
            for row in rows
        ]

        latest_units: float | None = None
        latest_cost: float | None = None
        if periods:
            latest_year = periods[0].year
            latest_month = periods[0].month
            latest_rows = [
                period
                for period in periods
                if period.year == latest_year and period.month == latest_month
            ]
            latest_units = round(sum(p.units for p in latest_rows), 2)
            latest_cost = round(sum(p.total_cost for p in latest_rows), 2)

        return MonthEndInventoryEvidence(
            period_count=len(periods),
            periods=periods,
            latest_period_total_units=latest_units,
            latest_period_total_cost=latest_cost,
        )

    def _build_purchase_exposure(
        self,
        product_number: str,
    ) -> PurchaseExposureEvidence:
        try:
            rows = self._repository.get_open_purchase_orders_for_product(
                product_number
            )
        except HTTPException:
            # TMPODT has ~6.2M rows and TPDPRD is never a leading column in
            # either of its two secondary indexes, so a TPDPRD-only filter
            # forces a full-table scan that exceeds the statement timeout
            # for most products. This is a source-side indexing constraint
            # ETOP cannot alter, not an absence of open purchase orders.
            return PurchaseExposureEvidence(
                status="unavailable_source_capability",
                open_order_count=0,
                open_order_total_cost=0.0,
                open_orders=[],
                explanation=(
                    "Open purchase order exposure is unavailable for this "
                    "product: TMPODT has no index usable for a TPDPRD-only "
                    "filter and the query exceeded the source database's "
                    "statement timeout. This is a source-side indexing "
                    "constraint, not an absence of open purchase orders."
                ),
            )
        orders = [
            OpenPurchaseOrderLine(
                po_number=int(row["TPHNB"]),
                vendor_number=_optional_int(row.get("TPHNBVND")),
                po_date=_parse_erp_date(row.get("TPHDTE")),
                date_required=_parse_erp_date(row.get("TPHDTEREQ")),
                status_code=_clean_text(row.get("TPHCDSTS")),
                complete=_clean_text(row.get("TPHFLGCMP")).upper() == "Y",
                ship_via=_clean_text(row.get("TPHVIA")),
                buyer_number=_optional_int(row.get("TPHBUYNUM")),
                ordered_quantity=_number(row.get("total_ordered")),
                received_quantity=_number(row.get("total_received")),
                backorder_quantity=_number(row.get("total_backorder")),
                average_unit_cost=_optional_number(
                    row.get("average_unit_cost")
                ),
                line_total_cost=_optional_number(row.get("line_total_cost")),
            )
            for row in rows
        ]
        return PurchaseExposureEvidence(
            open_order_count=len(orders),
            open_order_total_cost=round(
                sum(order.line_total_cost or 0.0 for order in orders), 2
            ),
            open_orders=orders,
        )

    def _build_receiving_evidence(
        self,
        product_number: str,
    ) -> ReceivingEvidence:
        rows = self._repository.get_receiving_history_for_product(
            product_number
        )
        events: list[ReceivingEvent] = []
        variances: list[float] = []
        missing_variance = 0
        for row in rows:
            variance = _optional_number(row.get("TRCDCOSDIF"))
            if variance is None:
                missing_variance += 1
            else:
                variances.append(variance)
            events.append(
                ReceivingEvent(
                    po_number=int(row["TRCDNUMPO"]),
                    vendor_number=_optional_int(row.get("TPHNBVND")),
                    quantity=_number(row.get("TRCDQTY")),
                    actual_cost=_optional_number(row.get("TRCDCOS")),
                    po_cost=_optional_number(row.get("TRCDCOSPO")),
                    cost_variance=variance,
                    dot_number=_clean_text(row.get("TRCDDOT")),
                    dot_date=_parse_erp_date(row.get("TRCDDOTDTE")),
                    received_date=_parse_erp_date(row.get("TRCDDTECRT")),
                )
            )

        if not events:
            completeness = "unavailable"
        elif missing_variance == 0:
            completeness = "complete"
        elif missing_variance == len(events):
            completeness = "unavailable"
        else:
            completeness = "partial"

        return ReceivingEvidence(
            receipt_count=len(events),
            total_cost_variance=(
                round(sum(variances), 2) if variances else None
            ),
            cost_variance_completeness=completeness,
            recent_receipts=events,
        )

    def list_notes(self, product_number: str) -> InventoryNoteHistoryResponse:
        records = [
            InventoryNoteRecord(**record)
            for record in self._notes_repository.list_notes(product_number)
        ]
        return InventoryNoteHistoryResponse(
            product_number=product_number,
            count=len(records),
            notes=records,
        )

    def create_note(
        self,
        product_number: str,
        payload: InventoryNoteCreate,
    ) -> InventoryNoteRecord:
        evidence = self.get_product_evidence(product_number)
        created_at = self._clock().astimezone(UTC).isoformat()
        record = {
            "note_id": self._note_id_factory(),
            "product_number": product_number,
            "product_description": evidence.identity.description,
            "author_identity": payload.author_identity,
            "note": payload.note,
            "created_at": created_at,
            "source_as_of": evidence.source.retrieved_at,
            "actor_identity_source": "operator_supplied",
            "actor_authority_status": "not_independently_verified",
            "note_classification": "professional_workflow_metadata",
            "decision_effect": "none",
            "evidence_snapshot": evidence.model_dump(mode="json"),
        }
        return InventoryNoteRecord(
            **self._notes_repository.create_note(record)
        )


inventory_purchasing_service = InventoryPurchasingService()
