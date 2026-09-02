from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from itertools import combinations
from typing import Any

from sqlalchemy import case, cast, delete, func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.types import Float as SAFloat

from core.evidence_integrity import verify_snapshot_hash
from data.mysql import (
    ap_control_cases_table,
    ap_control_reviews_table,
    ap_duplicate_candidates_table,
    ap_cash_scenarios_table,
    ap_exception_actions_table,
    ap_invoice_events_table,
    ap_invoice_revisions_table,
    ap_invoices_table,
    get_engine,
    metadata,
)

from .schemas import SourceInvoiceProjection


_AP_TABLES = [
    ap_invoices_table,
    ap_invoice_revisions_table,
    ap_invoice_events_table,
    ap_duplicate_candidates_table,
    ap_control_cases_table,
    ap_control_reviews_table,
    ap_cash_scenarios_table,
    ap_exception_actions_table,
]


class AccountsPayableRepository:
    """ETOP-local AP projection, immutable evidence revisions, and timeline."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialization_lock = threading.Lock()

    def initialize(self) -> None:
        with self._initialization_lock:
            metadata.create_all(self._engine, checkfirst=True, tables=_AP_TABLES)

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

    @staticmethod
    def _event_id(event_key: str) -> str:
        return "ap-event-" + hashlib.sha256(
            event_key.encode("utf-8")
        ).hexdigest()[:24]

    @staticmethod
    def _revision_id(ap_invoice_id: str, evidence_hash: str) -> str:
        return "ap-revision-" + hashlib.sha256(
            f"{ap_invoice_id}:{evidence_hash}".encode("utf-8")
        ).hexdigest()[:24]

    @staticmethod
    def _candidate_id(invoice_a_id: str, invoice_b_id: str) -> str:
        return "ap-duplicate-" + hashlib.sha256(
            f"{invoice_a_id}:{invoice_b_id}".encode("utf-8")
        ).hexdigest()[:24]

    @staticmethod
    def _projection_values(
        projection: SourceInvoiceProjection,
        imported_at: str,
        last_synced_at: str,
    ) -> dict[str, Any]:
        return {
            "ap_invoice_id": projection.ap_invoice_id,
            "source_key": projection.source_key,
            "document_job_id": projection.document_job_id,
            "document_result_id": projection.document_result_id,
            "source_record_index": projection.source_record_index,
            "source_file_name": projection.source_file_name,
            "content_type": projection.content_type,
            "document_type": projection.document_type,
            "document_status": projection.document_status,
            "classifier": projection.classifier,
            "classification_confidence": projection.classification_confidence,
            "classification_evidence_json": AccountsPayableRepository._json(
                projection.classification_evidence
            ),
            "parser_name": projection.parser_name,
            "parser_version": projection.parser_version,
            "vendor_number": projection.vendor_number,
            "vendor_name": projection.vendor_name,
            "normalized_vendor_identity": projection.normalized_vendor_identity,
            "invoice_number": projection.invoice_number,
            "normalized_invoice_number": projection.normalized_invoice_number,
            "invoice_date": projection.invoice_date,
            "due_date": projection.due_date,
            "purchase_order_number": projection.purchase_order_number,
            "subtotal": projection.subtotal,
            "tax": projection.tax,
            "freight": projection.freight,
            "discount": projection.discount,
            "total_amount": projection.total_amount,
            "currency": projection.currency,
            "terms": projection.terms,
            "ocr_confidence": projection.ocr_confidence,
            "field_evidence_json": AccountsPayableRepository._json(
                projection.field_evidence
            ),
            "exceptions_json": AccountsPayableRepository._json(
                projection.exceptions
            ),
            "warnings_json": AccountsPayableRepository._json(
                projection.warnings
            ),
            "base_review_required": int(projection.base_review_required),
            "ocr_review_required": int(projection.ocr_review_required),
            "received_at": projection.received_at,
            "processed_at": projection.processed_at,
            "source_result_created_at": projection.source_result_created_at,
            "source_result_updated_at": projection.source_result_updated_at,
            "source_as_of": projection.source_as_of,
            "source_evidence_sha256": projection.source_evidence_sha256,
            "imported_at": imported_at,
            "last_synced_at": last_synced_at,
        }

    def _insert_projection(
        self,
        connection,
        projection: SourceInvoiceProjection,
        recorded_at: str,
    ) -> None:
        connection.execute(
            ap_invoices_table.insert().values(
                **self._projection_values(projection, recorded_at, recorded_at)
            )
        )

    def _update_projection(
        self,
        connection,
        projection: SourceInvoiceProjection,
        imported_at: str,
        recorded_at: str,
    ) -> None:
        values = self._projection_values(projection, imported_at, recorded_at)
        ap_invoice_id = values.pop("ap_invoice_id")
        connection.execute(
            ap_invoices_table.update()
            .where(ap_invoices_table.c.ap_invoice_id == ap_invoice_id)
            .values(**values)
        )

    def _append_revision(
        self,
        connection,
        projection: SourceInvoiceProjection,
        recorded_at: str,
    ) -> None:
        connection.execute(
            ap_invoice_revisions_table.insert().values(
                revision_id=self._revision_id(
                    projection.ap_invoice_id,
                    projection.source_evidence_sha256,
                ),
                ap_invoice_id=projection.ap_invoice_id,
                source_evidence_sha256=projection.source_evidence_sha256,
                source_as_of=projection.source_as_of,
                snapshot_json=self._json(projection.source_snapshot),
                recorded_at=recorded_at,
            )
        )

    def _append_event(
        self,
        connection,
        *,
        event_key: str,
        ap_invoice_id: str,
        event_type: str,
        label: str,
        occurred_at: str | None,
        recorded_at: str,
        source: str,
        details: str,
        source_hash: str | None,
    ) -> int:
        existing = connection.execute(
            select(ap_invoice_events_table.c.event_id).where(
                ap_invoice_events_table.c.event_key == event_key
            )
        ).first()
        if existing is not None:
            return 0
        connection.execute(
            ap_invoice_events_table.insert().values(
                event_id=self._event_id(event_key),
                event_key=event_key,
                ap_invoice_id=ap_invoice_id,
                event_type=event_type,
                label=label,
                occurred_at=occurred_at,
                recorded_at=recorded_at,
                source=source,
                actor=None,
                details=details,
                source_evidence_sha256=source_hash,
            )
        )
        return 1

    def sync_projections(
        self,
        projections,
        recorded_at: str,
    ) -> dict[str, int]:
        self.initialize()
        imported = 0
        updated = 0
        unchanged = 0
        event_count = 0
        with self._engine.begin() as connection:
            for projection in projections:
                existing = connection.execute(
                    select(
                        ap_invoices_table.c.ap_invoice_id,
                        ap_invoices_table.c.source_evidence_sha256,
                        ap_invoices_table.c.imported_at,
                    ).where(
                        ap_invoices_table.c.source_key == projection.source_key
                    )
                ).mappings().first()
                if existing is None:
                    self._insert_projection(connection, projection, recorded_at)
                    self._append_revision(connection, projection, recorded_at)
                    imported += 1
                    event_count += self._append_event(
                        connection,
                        event_key=f"{projection.source_key}:document_received",
                        ap_invoice_id=projection.ap_invoice_id,
                        event_type="document_received",
                        label="Document received",
                        occurred_at=projection.received_at,
                        recorded_at=recorded_at,
                        source="document_intelligence.doc_jobs",
                        details="Source document job was received by Document Intelligence.",
                        source_hash=None,
                    )
                    event_count += self._append_event(
                        connection,
                        event_key=(
                            f"{projection.source_key}:document_processed:"
                            f"{projection.source_evidence_sha256}"
                        ),
                        ap_invoice_id=projection.ap_invoice_id,
                        event_type="document_processed",
                        label="Document processing result saved",
                        occurred_at=projection.source_result_updated_at,
                        recorded_at=recorded_at,
                        source="document_intelligence.doc_results",
                        details="Saved Document Intelligence result became AP evidence.",
                        source_hash=projection.source_evidence_sha256,
                    )
                    event_count += self._append_event(
                        connection,
                        event_key=(
                            f"{projection.source_key}:ap_invoice_imported:"
                            f"{projection.source_evidence_sha256}"
                        ),
                        ap_invoice_id=projection.ap_invoice_id,
                        event_type="ap_invoice_imported",
                        label="AP invoice evidence imported",
                        occurred_at=recorded_at,
                        recorded_at=recorded_at,
                        source="accounts_payable.sync",
                        details="ETOP created a local read-only AP evidence projection.",
                        source_hash=projection.source_evidence_sha256,
                    )
                    continue

                if existing["source_evidence_sha256"] == projection.source_evidence_sha256:
                    unchanged += 1
                    continue

                self._update_projection(
                    connection,
                    projection,
                    str(existing["imported_at"]),
                    recorded_at,
                )
                self._append_revision(connection, projection, recorded_at)
                updated += 1
                event_count += self._append_event(
                    connection,
                    event_key=(
                        f"{projection.source_key}:document_processed:"
                        f"{projection.source_evidence_sha256}"
                    ),
                    ap_invoice_id=projection.ap_invoice_id,
                    event_type="document_processed",
                    label="Updated document processing evidence saved",
                    occurred_at=projection.source_result_updated_at,
                    recorded_at=recorded_at,
                    source="document_intelligence.doc_results",
                    details="A changed saved Document Intelligence result became a new immutable AP evidence revision.",
                    source_hash=projection.source_evidence_sha256,
                )
                event_count += self._append_event(
                    connection,
                    event_key=(
                        f"{projection.source_key}:ap_invoice_source_refreshed:"
                        f"{projection.source_evidence_sha256}"
                    ),
                    ap_invoice_id=projection.ap_invoice_id,
                    event_type="ap_invoice_source_refreshed",
                    label="AP invoice source evidence refreshed",
                    occurred_at=recorded_at,
                    recorded_at=recorded_at,
                    source="accounts_payable.sync",
                    details="The current AP projection advanced without overwriting its prior immutable evidence revision.",
                    source_hash=projection.source_evidence_sha256,
                )

            if imported or updated:
                self._synchronize_duplicate_candidates(connection, recorded_at)
            duplicate_count = connection.execute(
                select(func.count()).select_from(ap_duplicate_candidates_table)
            ).scalar_one()

        return {
            "imported": imported,
            "updated": updated,
            "unchanged": unchanged,
            "events": event_count,
            "duplicate_candidates": duplicate_count,
        }

    def _synchronize_duplicate_candidates(
        self,
        connection,
        recorded_at: str,
    ) -> None:
        rows = connection.execute(
            select(
                ap_invoices_table.c.ap_invoice_id,
                ap_invoices_table.c.normalized_vendor_identity,
                ap_invoices_table.c.normalized_invoice_number,
                ap_invoices_table.c.vendor_name,
                ap_invoices_table.c.invoice_number,
                ap_invoices_table.c.invoice_date,
                ap_invoices_table.c.total_amount,
            )
            .where(
                ap_invoices_table.c.normalized_vendor_identity.is_not(None),
                ap_invoices_table.c.normalized_invoice_number.is_not(None),
            )
            .order_by(ap_invoices_table.c.ap_invoice_id)
        ).all()
        groups: dict[tuple[str, str], list] = {}
        for row in rows:
            key = (
                str(row.normalized_vendor_identity),
                str(row.normalized_invoice_number),
            )
            groups.setdefault(key, []).append(row)

        desired: dict[str, dict[str, Any]] = {}
        for (vendor_identity, invoice_number), group in groups.items():
            for left, right in combinations(group, 2):
                amount_status = "unavailable"
                if left.total_amount is not None and right.total_amount is not None:
                    if str(left.total_amount) != str(right.total_amount):
                        continue
                    amount_status = "matched"
                date_status = "unavailable"
                if left.invoice_date is not None and right.invoice_date is not None:
                    if str(left.invoice_date) != str(right.invoice_date):
                        continue
                    date_status = "matched"
                invoice_a_id, invoice_b_id = sorted(
                    (str(left.ap_invoice_id), str(right.ap_invoice_id))
                )
                candidate_id = self._candidate_id(invoice_a_id, invoice_b_id)
                match_factors = [
                    "exact_normalized_vendor_identity",
                    "exact_normalized_invoice_number",
                ]
                if amount_status == "matched":
                    match_factors.append("exact_total_amount")
                if date_status == "matched":
                    match_factors.append("exact_invoice_date")
                desired[candidate_id] = {
                    "candidate_id": candidate_id,
                    "invoice_a_id": invoice_a_id,
                    "invoice_b_id": invoice_b_id,
                    "vendor_identity": vendor_identity,
                    "normalized_invoice_number": invoice_number,
                    "amount_corroboration": amount_status,
                    "date_corroboration": date_status,
                    "evidence_json": self._json(
                        {
                            "rule_version": "ap-duplicate-exact-identity.v1",
                            "match_factors": match_factors,
                            "amount_corroboration": amount_status,
                            "date_corroboration": date_status,
                            "action": "review_only",
                            "confidence": None,
                            "explanation": (
                                "Exact normalized vendor identity and invoice "
                                "number matched. Any source-present amount/date "
                                "also matched; contradictory pairs were excluded."
                            ),
                        }
                    ),
                }

        existing_rows = connection.execute(
            select(
                ap_duplicate_candidates_table.c.candidate_id,
                ap_duplicate_candidates_table.c.evidence_json,
            )
        ).all()
        existing = {
            str(row.candidate_id): str(row.evidence_json) for row in existing_rows
        }
        stale_ids = set(existing) - set(desired)
        for candidate_id in stale_ids:
            connection.execute(
                delete(ap_duplicate_candidates_table).where(
                    ap_duplicate_candidates_table.c.candidate_id == candidate_id
                )
            )
        for candidate_id, candidate in desired.items():
            if candidate_id not in existing:
                connection.execute(
                    ap_duplicate_candidates_table.insert().values(
                        candidate_id=candidate["candidate_id"],
                        invoice_a_id=candidate["invoice_a_id"],
                        invoice_b_id=candidate["invoice_b_id"],
                        vendor_identity=candidate["vendor_identity"],
                        normalized_invoice_number=candidate[
                            "normalized_invoice_number"
                        ],
                        amount_corroboration=candidate["amount_corroboration"],
                        date_corroboration=candidate["date_corroboration"],
                        evidence_json=candidate["evidence_json"],
                        detected_at=recorded_at,
                        updated_at=recorded_at,
                    )
                )
            elif existing[candidate_id] != candidate["evidence_json"]:
                connection.execute(
                    ap_duplicate_candidates_table.update()
                    .where(
                        ap_duplicate_candidates_table.c.candidate_id
                        == candidate_id
                    )
                    .values(
                        evidence_json=candidate["evidence_json"],
                        amount_corroboration=candidate["amount_corroboration"],
                        date_corroboration=candidate["date_corroboration"],
                        updated_at=recorded_at,
                    )
                )

    @staticmethod
    def _decode_row(row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        for key in (
            "classification_evidence_json",
            "field_evidence_json",
            "exceptions_json",
            "warnings_json",
        ):
            result[key.removesuffix("_json")] = json.loads(result.pop(key))
        result["base_review_required"] = bool(result["base_review_required"])
        result["ocr_review_required"] = bool(result["ocr_review_required"])
        result["duplicate_candidate_count"] = int(
            result.get("duplicate_candidate_count", 0)
        )
        return result

    def list_invoices(
        self,
        *,
        query: str | None,
        status: str | None,
        exception: bool | None,
        duplicate: bool | None,
        exception_code: str | None,
        limit: int,
        offset: int,
        sort_by: str,
        sort_order: str,
    ) -> tuple[list[dict[str, Any]], int]:
        self.initialize()
        i = ap_invoices_table
        d = ap_duplicate_candidates_table
        duplicate_count_expr = (
            select(func.count())
            .select_from(d)
            .where(or_(d.c.invoice_a_id == i.c.ap_invoice_id, d.c.invoice_b_id == i.c.ap_invoice_id))
            .scalar_subquery()
        )

        conditions = []
        if query:
            token = f"%{query.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(func.coalesce(i.c.vendor_name, "")).like(token),
                    func.lower(func.coalesce(i.c.vendor_number, "")).like(token),
                    func.lower(func.coalesce(i.c.invoice_number, "")).like(token),
                    func.lower(func.coalesce(i.c.purchase_order_number, "")).like(token),
                    func.lower(i.c.document_job_id).like(token),
                    func.lower(i.c.source_file_name).like(token),
                )
            )
        if status == "review_required":
            conditions.append(
                or_(i.c.base_review_required == 1, duplicate_count_expr > 0)
            )
        elif status == "evidence_available":
            conditions.append(
                (i.c.base_review_required == 0) & (duplicate_count_expr == 0)
            )
        elif status == "ocr_review":
            conditions.append(i.c.ocr_review_required == 1)
        if exception is True:
            conditions.append(i.c.exceptions_json != "[]")
        elif exception is False:
            conditions.append(i.c.exceptions_json == "[]")
        if duplicate is True:
            conditions.append(duplicate_count_expr > 0)
        elif duplicate is False:
            conditions.append(duplicate_count_expr == 0)
        if exception_code:
            conditions.append(
                i.c.exceptions_json.like(f'%"code":"{exception_code}"%')
            )

        sort_columns = {
            "received_at": i.c.received_at,
            "invoice_date": i.c.invoice_date,
            "due_date": i.c.due_date,
            "total": cast(i.c.total_amount, SAFloat),
            "vendor_name": i.c.vendor_name,
            "ocr_confidence": i.c.ocr_confidence,
        }
        sort_column = sort_columns.get(sort_by, i.c.received_at)
        order = sort_column.asc() if sort_order == "asc" else sort_column.desc()

        with self._engine.connect() as connection:
            total = connection.execute(
                select(func.count()).select_from(i).where(*conditions)
            ).scalar_one()
            rows = connection.execute(
                select(i, duplicate_count_expr.label("duplicate_candidate_count"))
                .where(*conditions)
                .order_by(order, i.c.ap_invoice_id.asc())
                .limit(limit)
                .offset(offset)
            ).mappings().all()
        return [self._decode_row(row) for row in rows], total

    def get_invoice(self, ap_invoice_id: str) -> dict[str, Any] | None:
        self.initialize()
        i = ap_invoices_table
        d = ap_duplicate_candidates_table
        duplicate_count_expr = (
            select(func.count())
            .select_from(d)
            .where(or_(d.c.invoice_a_id == i.c.ap_invoice_id, d.c.invoice_b_id == i.c.ap_invoice_id))
            .scalar_subquery()
        )
        with self._engine.connect() as connection:
            row = connection.execute(
                select(i, duplicate_count_expr.label("duplicate_candidate_count")).where(
                    i.c.ap_invoice_id == ap_invoice_id
                )
            ).mappings().first()
        return self._decode_row(row) if row is not None else None

    def list_all_invoices(self) -> list[dict[str, Any]]:
        rows, _ = self.list_invoices(
            query=None,
            status=None,
            exception=None,
            duplicate=None,
            exception_code=None,
            limit=2_147_483_647,
            offset=0,
            sort_by="received_at",
            sort_order="desc",
        )
        return rows

    def list_duplicates(self, ap_invoice_id: str) -> list[dict[str, Any]]:
        self.initialize()
        d = ap_duplicate_candidates_table
        other = ap_invoices_table.alias("other")
        candidate_invoice_id = case(
            (d.c.invoice_a_id == ap_invoice_id, d.c.invoice_b_id),
            else_=d.c.invoice_a_id,
        )
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    d,
                    candidate_invoice_id.label("candidate_ap_invoice_id"),
                    other.c.invoice_number.label("candidate_invoice_number"),
                    other.c.vendor_name.label("candidate_vendor_name"),
                    other.c.total_amount.label("candidate_amount"),
                )
                .select_from(
                    d.join(other, other.c.ap_invoice_id == candidate_invoice_id)
                )
                .where(or_(d.c.invoice_a_id == ap_invoice_id, d.c.invoice_b_id == ap_invoice_id))
                .order_by(d.c.candidate_id)
            ).mappings().all()
        results: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(item.pop("evidence_json"))
            results.append(item)
        return results

    def list_events(self, ap_invoice_id: str) -> list[dict[str, Any]]:
        self.initialize()
        e = ap_invoice_events_table
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    e.c.event_id,
                    e.c.event_type,
                    e.c.label,
                    e.c.occurred_at,
                    e.c.recorded_at,
                    e.c.source,
                    e.c.actor,
                    e.c.details,
                    e.c.source_evidence_sha256,
                )
                .where(e.c.ap_invoice_id == ap_invoice_id)
                .order_by(func.coalesce(e.c.occurred_at, e.c.recorded_at), e.c.event_id)
            ).mappings().all()
        return [dict(row) for row in rows]

    def revision_count(self, ap_invoice_id: str) -> int:
        self.initialize()
        with self._engine.connect() as connection:
            return connection.execute(
                select(func.count())
                .select_from(ap_invoice_revisions_table)
                .where(ap_invoice_revisions_table.c.ap_invoice_id == ap_invoice_id)
            ).scalar_one()

    def create_control_case(self, record: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        snapshot_json = self._json(record["evidence_snapshot"])
        snapshot_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
        with self._engine.begin() as connection:
            connection.execute(
                ap_control_cases_table.insert().values(
                    control_case_id=record["control_case_id"],
                    ap_invoice_id=record["ap_invoice_id"],
                    intended_action=record["intended_action"],
                    requested_by=record["requested_by"],
                    assigned_reviewer=record["assigned_reviewer"],
                    payment_preparer=record["payment_preparer"],
                    notes=record["notes"],
                    created_at=record["created_at"],
                    source_evidence_sha256=record["source_evidence_sha256"],
                    evidence_snapshot_json=snapshot_json,
                    evidence_snapshot_sha256=snapshot_hash,
                    actor_identity_source=record["actor_identity_source"],
                    actor_authority_status=record["actor_authority_status"],
                    approval_effect=record["approval_effect"],
                    payment_effect=record["payment_effect"],
                )
            )
        stored = self.get_control_case(record["control_case_id"])
        if stored is None:
            raise RuntimeError("The AP control case was not persisted.")
        return stored

    def create_control_review(self, record: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        with self._engine.begin() as connection:
            connection.execute(
                ap_control_reviews_table.insert().values(
                    review_id=record["review_id"],
                    control_case_id=record["control_case_id"],
                    reviewer_identity=record["reviewer_identity"],
                    disposition=record["disposition"],
                    notes=record["notes"],
                    created_at=record["created_at"],
                    actor_identity_source=record["actor_identity_source"],
                    actor_authority_status=record["actor_authority_status"],
                    approval_effect=record["approval_effect"],
                    payment_effect=record["payment_effect"],
                )
            )
        stored = self.get_control_review(record["review_id"])
        if stored is None:
            raise RuntimeError("The AP control review was not persisted.")
        return stored

    def get_control_case(self, control_case_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self._engine.connect() as connection:
            row = connection.execute(
                select(ap_control_cases_table).where(
                    ap_control_cases_table.c.control_case_id == control_case_id
                )
            ).mappings().first()
        return self._control_case_from_row(row) if row is not None else None

    def list_control_cases(
        self,
        *,
        intended_action: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        self.initialize()
        c = ap_control_cases_table
        conditions = [c.c.intended_action == intended_action] if intended_action else []
        with self._engine.connect() as connection:
            total = connection.execute(
                select(func.count()).select_from(c).where(*conditions)
            ).scalar_one()
            rows = connection.execute(
                select(c)
                .where(*conditions)
                .order_by(c.c.created_at.desc(), c.c.control_case_id.desc())
                .limit(limit)
                .offset(offset)
            ).mappings().all()
        return [self._control_case_from_row(row) for row in rows], total

    def get_control_review(self, review_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self._engine.connect() as connection:
            row = connection.execute(
                select(ap_control_reviews_table).where(
                    ap_control_reviews_table.c.review_id == review_id
                )
            ).mappings().first()
        return self._control_review_from_row(row) if row is not None else None

    def list_control_reviews(self, control_case_id: str) -> list[dict[str, Any]]:
        self.initialize()
        r = ap_control_reviews_table
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(r)
                .where(r.c.control_case_id == control_case_id)
                .order_by(r.c.created_at.desc(), r.c.review_id.desc())
            ).mappings().all()
        return [self._control_review_from_row(row) for row in rows]

    def approval_time_stats(self, intended_action: str) -> dict[str, Any]:
        """Average hours from a control case's creation to its first
        recorded review disposition, for cases opened with the given
        intended_action. Both tables are append-only local evidence, so
        this is a real, computable metric with no ERP dependency.

        Computed in Python (parsing ISO timestamps) rather than SQL
        (julianday() is SQLite-only and has no direct MySQL equivalent for
        arbitrary ISO-8601 text columns)."""

        self.initialize()
        c = ap_control_cases_table
        r = ap_control_reviews_table
        first_review = (
            select(
                r.c.control_case_id,
                func.min(r.c.created_at).label("first_created_at"),
            )
            .group_by(r.c.control_case_id)
            .subquery()
        )
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(c.c.created_at, first_review.c.first_created_at)
                .select_from(
                    c.join(
                        first_review,
                        first_review.c.control_case_id == c.c.control_case_id,
                    )
                )
                .where(c.c.intended_action == intended_action)
            ).all()

        case_count = len(rows)
        if case_count == 0:
            return {
                "case_count": 0,
                "average_hours": None,
                "latest_reviewed_at": None,
            }
        hours = [
            (
                datetime.fromisoformat(row.first_created_at)
                - datetime.fromisoformat(row.created_at)
            ).total_seconds()
            / 3600.0
            for row in rows
        ]
        return {
            "case_count": case_count,
            "average_hours": sum(hours) / case_count,
            "latest_reviewed_at": max(row.first_created_at for row in rows),
        }

    def create_cash_scenario(self, record: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        snapshot_json = self._json(record["evidence_snapshot"])
        snapshot_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
        with self._engine.begin() as connection:
            connection.execute(
                ap_cash_scenarios_table.insert().values(
                    cash_scenario_id=record["cash_scenario_id"],
                    as_of_date=record["as_of_date"],
                    horizon_days=record["horizon_days"],
                    horizon_end_date=record["horizon_end_date"],
                    include_review_required=int(record["include_review_required"]),
                    prepared_by=record["prepared_by"],
                    rationale=record["rationale"],
                    created_at=record["created_at"],
                    included_invoice_count=record["included_invoice_count"],
                    included_known_amount_count=record[
                        "included_known_amount_count"
                    ],
                    extracted_amount=record["extracted_amount"],
                    excluded_review_required_count=record[
                        "excluded_review_required_count"
                    ],
                    excluded_missing_due_date_count=record[
                        "excluded_missing_due_date_count"
                    ],
                    excluded_missing_amount_count=record[
                        "excluded_missing_amount_count"
                    ],
                    actor_identity_source=record["actor_identity_source"],
                    actor_authority_status=record["actor_authority_status"],
                    scenario_classification=record["scenario_classification"],
                    current_payable_status_known=0,
                    approval_effect=record["approval_effect"],
                    payment_effect=record["payment_effect"],
                    erp_write=0,
                    evidence_snapshot_json=snapshot_json,
                    evidence_snapshot_sha256=snapshot_hash,
                )
            )
        stored = self.get_cash_scenario(record["cash_scenario_id"])
        if stored is None:
            raise RuntimeError("The AP cash scenario was not persisted.")
        return stored

    def get_cash_scenario(self, cash_scenario_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self._engine.connect() as connection:
            row = connection.execute(
                select(ap_cash_scenarios_table).where(
                    ap_cash_scenarios_table.c.cash_scenario_id == cash_scenario_id
                )
            ).mappings().first()
        return self._cash_scenario_from_row(row) if row is not None else None

    def list_cash_scenarios(self) -> list[dict[str, Any]]:
        self.initialize()
        s = ap_cash_scenarios_table
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(s).order_by(s.c.created_at.desc(), s.c.cash_scenario_id.desc())
            ).mappings().all()
        return [self._cash_scenario_from_row(row) for row in rows]

    def create_exception_action(self, record: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        snapshot_json = self._json(record["evidence_snapshot"])
        snapshot_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
        with self._engine.begin() as connection:
            connection.execute(
                ap_exception_actions_table.insert().values(
                    action_id=record["action_id"],
                    ap_invoice_id=record["ap_invoice_id"],
                    disposition=record["disposition"],
                    owner_identity=record["owner_identity"],
                    actor_identity=record["actor_identity"],
                    notes=record["notes"],
                    follow_up_date=record["follow_up_date"],
                    created_at=record["created_at"],
                    source_evidence_sha256=record["source_evidence_sha256"],
                    actor_identity_source=record["actor_identity_source"],
                    owner_identity_source=record["owner_identity_source"],
                    authority_status=record["authority_status"],
                    action_classification=record["action_classification"],
                    approval_effect=record["approval_effect"],
                    payment_effect=record["payment_effect"],
                    erp_write=0,
                    evidence_snapshot_json=snapshot_json,
                    evidence_snapshot_sha256=snapshot_hash,
                )
            )
        stored = self.get_exception_action(record["action_id"])
        if stored is None:
            raise RuntimeError("The AP exception action was not persisted.")
        return stored

    def get_exception_action(self, action_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self._engine.connect() as connection:
            row = connection.execute(
                select(ap_exception_actions_table).where(
                    ap_exception_actions_table.c.action_id == action_id
                )
            ).mappings().first()
        return self._exception_action_from_row(row) if row is not None else None

    def list_exception_actions(self, ap_invoice_id: str) -> list[dict[str, Any]]:
        self.initialize()
        a = ap_exception_actions_table
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(a)
                .where(a.c.ap_invoice_id == ap_invoice_id)
                .order_by(a.c.created_at.desc(), a.c.action_id.desc())
            ).mappings().all()
        return [self._exception_action_from_row(row) for row in rows]

    def list_latest_exception_actions(self) -> dict[str, dict[str, Any]]:
        self.initialize()
        a = ap_exception_actions_table
        action_rank = (
            func.row_number()
            .over(
                partition_by=a.c.ap_invoice_id,
                order_by=(a.c.created_at.desc(), a.c.action_id.desc()),
            )
            .label("action_rank")
        )
        ranked = select(a, action_rank).subquery()
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(ranked).where(ranked.c.action_rank == 1)
            ).mappings().all()
        return {
            str(row["ap_invoice_id"]): self._exception_action_from_row(row)
            for row in rows
        }

    @staticmethod
    def _control_case_from_row(row) -> dict[str, Any]:
        snapshot_json = str(row["evidence_snapshot_json"])
        expected_hash = str(row["evidence_snapshot_sha256"])
        verify_snapshot_hash(
            snapshot_json,
            expected_hash,
            error=RuntimeError,
            message=(
                "Stored AP control-case evidence failed its SHA-256 "
                "integrity check."
            ),
        )
        result = dict(row)
        result["evidence_snapshot"] = json.loads(
            result.pop("evidence_snapshot_json")
        )
        result["evidence_snapshot_sha256"] = expected_hash
        return result

    @staticmethod
    def _control_review_from_row(row) -> dict[str, Any]:
        return dict(row)

    @staticmethod
    def _cash_scenario_from_row(row) -> dict[str, Any]:
        snapshot_json = str(row["evidence_snapshot_json"])
        expected_hash = str(row["evidence_snapshot_sha256"])
        verify_snapshot_hash(
            snapshot_json,
            expected_hash,
            error=RuntimeError,
            message=(
                "Stored AP cash-scenario evidence failed its SHA-256 "
                "integrity check."
            ),
        )
        result = dict(row)
        result["include_review_required"] = bool(
            result["include_review_required"]
        )
        result["current_payable_status_known"] = bool(
            result["current_payable_status_known"]
        )
        result["erp_write"] = bool(result["erp_write"])
        result["evidence_snapshot"] = json.loads(
            result.pop("evidence_snapshot_json")
        )
        result["evidence_snapshot_sha256"] = expected_hash
        return result

    @staticmethod
    def _exception_action_from_row(row) -> dict[str, Any]:
        snapshot_json = str(row["evidence_snapshot_json"])
        expected_hash = str(row["evidence_snapshot_sha256"])
        verify_snapshot_hash(
            snapshot_json,
            expected_hash,
            error=RuntimeError,
            message=(
                "Stored AP exception-action evidence failed its SHA-256 "
                "integrity check."
            ),
        )
        result = {k: v for k, v in dict(row).items() if k != "action_rank"}
        result["erp_write"] = bool(result["erp_write"])
        result["evidence_snapshot"] = json.loads(
            result.pop("evidence_snapshot_json")
        )
        result["evidence_snapshot_sha256"] = expected_hash
        return result

    def source_statistics(self) -> dict[str, Any]:
        invoices = self.list_all_invoices()
        if not invoices:
            return {
                "count": 0,
                "as_of": None,
                "ocr_count": 0,
                "structured_count": 0,
            }
        structured_count = 0
        for invoice in invoices:
            if any(
                field.get("authority") in {
                    "document_extraction",
                    "human_corrected_evidence",
                }
                and field.get("normalized_value") is not None
                for field in invoice["field_evidence"]
            ):
                structured_count += 1
        return {
            "count": len(invoices),
            "as_of": max(invoice["source_as_of"] for invoice in invoices),
            "ocr_count": sum(
                invoice["ocr_confidence"] is not None for invoice in invoices
            ),
            "structured_count": structured_count,
        }


accounts_payable_repository = AccountsPayableRepository()
