from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Callable, Sequence
from itertools import combinations
from typing import Any

from data.database import get_connection

from .schemas import SourceInvoiceProjection


class AccountsPayableRepository:
    """ETOP-local AP projection, immutable evidence revisions, and timeline."""

    def __init__(
        self,
        connection_factory: Callable[[], sqlite3.Connection] = get_connection,
    ) -> None:
        self._connection_factory = connection_factory
        self._initialization_lock = threading.Lock()

    def _connection(self) -> sqlite3.Connection:
        connection = self._connection_factory()
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        return connection

    def initialize(self) -> None:
        with self._initialization_lock:
            connection = self._connection()
            try:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS ap_invoices (
                        ap_invoice_id TEXT PRIMARY KEY,
                        source_key TEXT NOT NULL UNIQUE,
                        document_job_id TEXT NOT NULL,
                        document_result_id TEXT NOT NULL,
                        source_record_index INTEGER,
                        source_file_name TEXT NOT NULL,
                        content_type TEXT,
                        document_type TEXT NOT NULL
                            CHECK (document_type = 'vendor_invoice'),
                        document_status TEXT NOT NULL,
                        classifier TEXT,
                        classification_confidence REAL,
                        classification_evidence_json TEXT NOT NULL,
                        parser_name TEXT,
                        parser_version TEXT,
                        vendor_number TEXT,
                        vendor_name TEXT,
                        normalized_vendor_identity TEXT,
                        invoice_number TEXT,
                        normalized_invoice_number TEXT,
                        invoice_date TEXT,
                        due_date TEXT,
                        purchase_order_number TEXT,
                        subtotal TEXT,
                        tax TEXT,
                        freight TEXT,
                        discount TEXT,
                        total_amount TEXT,
                        currency TEXT,
                        terms TEXT,
                        ocr_confidence REAL,
                        field_evidence_json TEXT NOT NULL,
                        exceptions_json TEXT NOT NULL,
                        warnings_json TEXT NOT NULL,
                        base_review_required INTEGER NOT NULL
                            CHECK (base_review_required IN (0, 1)),
                        ocr_review_required INTEGER NOT NULL
                            CHECK (ocr_review_required IN (0, 1)),
                        received_at TEXT,
                        processed_at TEXT,
                        source_result_created_at TEXT,
                        source_result_updated_at TEXT,
                        source_as_of TEXT NOT NULL,
                        source_evidence_sha256 TEXT NOT NULL
                            CHECK (length(source_evidence_sha256) = 64),
                        imported_at TEXT NOT NULL,
                        last_synced_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_ap_invoices_vendor
                    ON ap_invoices(normalized_vendor_identity, vendor_name);

                    CREATE INDEX IF NOT EXISTS idx_ap_invoices_number
                    ON ap_invoices(normalized_invoice_number);

                    CREATE INDEX IF NOT EXISTS idx_ap_invoices_dates
                    ON ap_invoices(invoice_date, due_date);

                    CREATE INDEX IF NOT EXISTS idx_ap_invoices_review
                    ON ap_invoices(base_review_required, ocr_review_required);

                    CREATE TABLE IF NOT EXISTS ap_invoice_revisions (
                        revision_id TEXT PRIMARY KEY,
                        ap_invoice_id TEXT NOT NULL,
                        source_evidence_sha256 TEXT NOT NULL,
                        source_as_of TEXT NOT NULL,
                        snapshot_json TEXT NOT NULL,
                        recorded_at TEXT NOT NULL,
                        UNIQUE (ap_invoice_id, source_evidence_sha256),
                        FOREIGN KEY (ap_invoice_id)
                            REFERENCES ap_invoices(ap_invoice_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_ap_revisions_invoice
                    ON ap_invoice_revisions(ap_invoice_id, recorded_at DESC);

                    CREATE TRIGGER IF NOT EXISTS ap_revisions_no_update
                    BEFORE UPDATE ON ap_invoice_revisions
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'AP evidence revisions are append-only.'
                        );
                    END;

                    CREATE TRIGGER IF NOT EXISTS ap_revisions_no_delete
                    BEFORE DELETE ON ap_invoice_revisions
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'AP evidence revisions are append-only.'
                        );
                    END;

                    CREATE TABLE IF NOT EXISTS ap_invoice_events (
                        event_id TEXT PRIMARY KEY,
                        event_key TEXT NOT NULL UNIQUE,
                        ap_invoice_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        label TEXT NOT NULL,
                        occurred_at TEXT,
                        recorded_at TEXT NOT NULL,
                        source TEXT NOT NULL,
                        actor TEXT,
                        details TEXT NOT NULL,
                        source_evidence_sha256 TEXT,
                        FOREIGN KEY (ap_invoice_id)
                            REFERENCES ap_invoices(ap_invoice_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_ap_events_invoice
                    ON ap_invoice_events(ap_invoice_id, occurred_at, event_id);

                    CREATE TRIGGER IF NOT EXISTS ap_events_no_update
                    BEFORE UPDATE ON ap_invoice_events
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'AP invoice timeline events are append-only.'
                        );
                    END;

                    CREATE TRIGGER IF NOT EXISTS ap_events_no_delete
                    BEFORE DELETE ON ap_invoice_events
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'AP invoice timeline events are append-only.'
                        );
                    END;

                    CREATE TABLE IF NOT EXISTS ap_duplicate_candidates (
                        candidate_id TEXT PRIMARY KEY,
                        invoice_a_id TEXT NOT NULL,
                        invoice_b_id TEXT NOT NULL,
                        vendor_identity TEXT NOT NULL,
                        normalized_invoice_number TEXT NOT NULL,
                        amount_corroboration TEXT NOT NULL,
                        date_corroboration TEXT NOT NULL,
                        evidence_json TEXT NOT NULL,
                        detected_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE (invoice_a_id, invoice_b_id),
                        FOREIGN KEY (invoice_a_id)
                            REFERENCES ap_invoices(ap_invoice_id),
                        FOREIGN KEY (invoice_b_id)
                            REFERENCES ap_invoices(ap_invoice_id),
                        CHECK (invoice_a_id < invoice_b_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_ap_duplicates_a
                    ON ap_duplicate_candidates(invoice_a_id);

                    CREATE INDEX IF NOT EXISTS idx_ap_duplicates_b
                    ON ap_duplicate_candidates(invoice_b_id);

                    CREATE TABLE IF NOT EXISTS ap_control_cases (
                        control_case_id TEXT PRIMARY KEY,
                        ap_invoice_id TEXT NOT NULL,
                        intended_action TEXT NOT NULL CHECK (
                            intended_action IN (
                                'approval_review',
                                'payment_preparation'
                            )
                        ),
                        requested_by TEXT NOT NULL,
                        assigned_reviewer TEXT NOT NULL,
                        payment_preparer TEXT,
                        notes TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        source_evidence_sha256 TEXT NOT NULL
                            CHECK (length(source_evidence_sha256) = 64),
                        evidence_snapshot_json TEXT NOT NULL,
                        evidence_snapshot_sha256 TEXT NOT NULL
                            CHECK (length(evidence_snapshot_sha256) = 64),
                        actor_identity_source TEXT NOT NULL CHECK (
                            actor_identity_source = 'operator_supplied'
                        ),
                        actor_authority_status TEXT NOT NULL CHECK (
                            actor_authority_status =
                                'not_independently_verified'
                        ),
                        approval_effect TEXT NOT NULL
                            CHECK (approval_effect = 'none'),
                        payment_effect TEXT NOT NULL
                            CHECK (payment_effect = 'none'),
                        FOREIGN KEY (ap_invoice_id)
                            REFERENCES ap_invoices(ap_invoice_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_ap_control_cases_queue
                    ON ap_control_cases(
                        intended_action,
                        created_at DESC,
                        control_case_id DESC
                    );

                    CREATE TRIGGER IF NOT EXISTS ap_control_cases_no_update
                    BEFORE UPDATE ON ap_control_cases
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'AP control cases are append-only.'
                        );
                    END;

                    CREATE TRIGGER IF NOT EXISTS ap_control_cases_no_delete
                    BEFORE DELETE ON ap_control_cases
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'AP control cases are append-only.'
                        );
                    END;

                    CREATE TABLE IF NOT EXISTS ap_control_reviews (
                        review_id TEXT PRIMARY KEY,
                        control_case_id TEXT NOT NULL,
                        reviewer_identity TEXT NOT NULL,
                        disposition TEXT NOT NULL CHECK (
                            disposition IN (
                                'evidence_ready',
                                'needs_information',
                                'duplicate_review_required',
                                'not_ready'
                            )
                        ),
                        notes TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        actor_identity_source TEXT NOT NULL CHECK (
                            actor_identity_source = 'operator_supplied'
                        ),
                        actor_authority_status TEXT NOT NULL CHECK (
                            actor_authority_status =
                                'not_independently_verified'
                        ),
                        approval_effect TEXT NOT NULL
                            CHECK (approval_effect = 'none'),
                        payment_effect TEXT NOT NULL
                            CHECK (payment_effect = 'none'),
                        FOREIGN KEY (control_case_id)
                            REFERENCES ap_control_cases(control_case_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_ap_control_reviews_case
                    ON ap_control_reviews(
                        control_case_id,
                        created_at DESC,
                        review_id DESC
                    );

                    CREATE TRIGGER IF NOT EXISTS ap_control_reviews_no_update
                    BEFORE UPDATE ON ap_control_reviews
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'AP control reviews are append-only.'
                        );
                    END;

                    CREATE TRIGGER IF NOT EXISTS ap_control_reviews_no_delete
                    BEFORE DELETE ON ap_control_reviews
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'AP control reviews are append-only.'
                        );
                    END;

                    CREATE TABLE IF NOT EXISTS ap_cash_scenarios (
                        cash_scenario_id TEXT PRIMARY KEY,
                        as_of_date TEXT NOT NULL,
                        horizon_days INTEGER NOT NULL CHECK (
                            horizon_days IN (7, 14, 30, 60, 90)
                        ),
                        horizon_end_date TEXT NOT NULL,
                        include_review_required INTEGER NOT NULL CHECK (
                            include_review_required IN (0, 1)
                        ),
                        prepared_by TEXT NOT NULL,
                        rationale TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        included_invoice_count INTEGER NOT NULL CHECK (
                            included_invoice_count >= 0
                        ),
                        included_known_amount_count INTEGER NOT NULL CHECK (
                            included_known_amount_count >= 0
                        ),
                        extracted_amount REAL NOT NULL,
                        excluded_review_required_count INTEGER NOT NULL CHECK (
                            excluded_review_required_count >= 0
                        ),
                        excluded_missing_due_date_count INTEGER NOT NULL CHECK (
                            excluded_missing_due_date_count >= 0
                        ),
                        excluded_missing_amount_count INTEGER NOT NULL CHECK (
                            excluded_missing_amount_count >= 0
                        ),
                        actor_identity_source TEXT NOT NULL CHECK (
                            actor_identity_source = 'operator_supplied'
                        ),
                        actor_authority_status TEXT NOT NULL CHECK (
                            actor_authority_status =
                                'not_independently_verified'
                        ),
                        scenario_classification TEXT NOT NULL CHECK (
                            scenario_classification = 'analytical_scenario'
                        ),
                        current_payable_status_known INTEGER NOT NULL DEFAULT 0
                            CHECK (current_payable_status_known = 0),
                        approval_effect TEXT NOT NULL CHECK (
                            approval_effect = 'none'
                        ),
                        payment_effect TEXT NOT NULL CHECK (
                            payment_effect = 'none'
                        ),
                        erp_write INTEGER NOT NULL DEFAULT 0 CHECK (
                            erp_write = 0
                        ),
                        evidence_snapshot_json TEXT NOT NULL,
                        evidence_snapshot_sha256 TEXT NOT NULL CHECK (
                            length(evidence_snapshot_sha256) = 64
                        )
                    );

                    CREATE INDEX IF NOT EXISTS idx_ap_cash_scenarios_time
                    ON ap_cash_scenarios(
                        created_at DESC,
                        cash_scenario_id DESC
                    );

                    CREATE TRIGGER IF NOT EXISTS ap_cash_scenarios_no_update
                    BEFORE UPDATE ON ap_cash_scenarios
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'AP cash scenarios are append-only.'
                        );
                    END;

                    CREATE TRIGGER IF NOT EXISTS ap_cash_scenarios_no_delete
                    BEFORE DELETE ON ap_cash_scenarios
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'AP cash scenarios are append-only.'
                        );
                    END;

                    CREATE TABLE IF NOT EXISTS ap_exception_actions (
                        action_id TEXT PRIMARY KEY,
                        ap_invoice_id TEXT NOT NULL,
                        disposition TEXT NOT NULL CHECK (
                            disposition IN (
                                'investigating',
                                'information_requested',
                                'document_correction_needed',
                                'duplicate_review_complete',
                                'ready_for_control_case'
                            )
                        ),
                        owner_identity TEXT NOT NULL,
                        actor_identity TEXT NOT NULL,
                        notes TEXT NOT NULL,
                        follow_up_date TEXT,
                        created_at TEXT NOT NULL,
                        source_evidence_sha256 TEXT NOT NULL CHECK (
                            length(source_evidence_sha256) = 64
                        ),
                        actor_identity_source TEXT NOT NULL CHECK (
                            actor_identity_source = 'operator_supplied'
                        ),
                        owner_identity_source TEXT NOT NULL CHECK (
                            owner_identity_source = 'operator_supplied'
                        ),
                        authority_status TEXT NOT NULL CHECK (
                            authority_status = 'not_independently_verified'
                        ),
                        action_classification TEXT NOT NULL CHECK (
                            action_classification =
                                'professional_workflow_metadata'
                        ),
                        approval_effect TEXT NOT NULL CHECK (
                            approval_effect = 'none'
                        ),
                        payment_effect TEXT NOT NULL CHECK (
                            payment_effect = 'none'
                        ),
                        erp_write INTEGER NOT NULL DEFAULT 0 CHECK (
                            erp_write = 0
                        ),
                        evidence_snapshot_json TEXT NOT NULL,
                        evidence_snapshot_sha256 TEXT NOT NULL CHECK (
                            length(evidence_snapshot_sha256) = 64
                        ),
                        FOREIGN KEY (ap_invoice_id)
                            REFERENCES ap_invoices(ap_invoice_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_ap_exception_actions_invoice
                    ON ap_exception_actions(
                        ap_invoice_id,
                        created_at DESC,
                        action_id DESC
                    );

                    CREATE TRIGGER IF NOT EXISTS ap_exception_actions_no_update
                    BEFORE UPDATE ON ap_exception_actions
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'AP exception actions are append-only.'
                        );
                    END;

                    CREATE TRIGGER IF NOT EXISTS ap_exception_actions_no_delete
                    BEFORE DELETE ON ap_exception_actions
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'AP exception actions are append-only.'
                        );
                    END;
                    """
                )
                connection.commit()
            finally:
                connection.close()

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
    ) -> tuple[Any, ...]:
        return (
            projection.ap_invoice_id,
            projection.source_key,
            projection.document_job_id,
            projection.document_result_id,
            projection.source_record_index,
            projection.source_file_name,
            projection.content_type,
            projection.document_type,
            projection.document_status,
            projection.classifier,
            projection.classification_confidence,
            AccountsPayableRepository._json(
                projection.classification_evidence
            ),
            projection.parser_name,
            projection.parser_version,
            projection.vendor_number,
            projection.vendor_name,
            projection.normalized_vendor_identity,
            projection.invoice_number,
            projection.normalized_invoice_number,
            projection.invoice_date,
            projection.due_date,
            projection.purchase_order_number,
            projection.subtotal,
            projection.tax,
            projection.freight,
            projection.discount,
            projection.total_amount,
            projection.currency,
            projection.terms,
            projection.ocr_confidence,
            AccountsPayableRepository._json(projection.field_evidence),
            AccountsPayableRepository._json(projection.exceptions),
            AccountsPayableRepository._json(projection.warnings),
            int(projection.base_review_required),
            int(projection.ocr_review_required),
            projection.received_at,
            projection.processed_at,
            projection.source_result_created_at,
            projection.source_result_updated_at,
            projection.source_as_of,
            projection.source_evidence_sha256,
            imported_at,
            last_synced_at,
        )

    def _insert_projection(
        self,
        connection: sqlite3.Connection,
        projection: SourceInvoiceProjection,
        recorded_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO ap_invoices (
                ap_invoice_id, source_key, document_job_id,
                document_result_id, source_record_index, source_file_name,
                content_type, document_type, document_status, classifier,
                classification_confidence, classification_evidence_json,
                parser_name, parser_version, vendor_number, vendor_name,
                normalized_vendor_identity, invoice_number,
                normalized_invoice_number, invoice_date, due_date,
                purchase_order_number, subtotal, tax, freight, discount,
                total_amount, currency, terms, ocr_confidence,
                field_evidence_json, exceptions_json, warnings_json,
                base_review_required, ocr_review_required, received_at,
                processed_at, source_result_created_at,
                source_result_updated_at, source_as_of,
                source_evidence_sha256, imported_at, last_synced_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            );
            """,
            self._projection_values(projection, recorded_at, recorded_at),
        )

    def _update_projection(
        self,
        connection: sqlite3.Connection,
        projection: SourceInvoiceProjection,
        imported_at: str,
        recorded_at: str,
    ) -> None:
        values = self._projection_values(
            projection,
            imported_at,
            recorded_at,
        )
        connection.execute(
            """
            UPDATE ap_invoices SET
                source_key = ?, document_job_id = ?, document_result_id = ?,
                source_record_index = ?, source_file_name = ?, content_type = ?,
                document_type = ?, document_status = ?, classifier = ?,
                classification_confidence = ?, classification_evidence_json = ?,
                parser_name = ?, parser_version = ?, vendor_number = ?,
                vendor_name = ?, normalized_vendor_identity = ?,
                invoice_number = ?, normalized_invoice_number = ?,
                invoice_date = ?, due_date = ?, purchase_order_number = ?,
                subtotal = ?, tax = ?, freight = ?, discount = ?,
                total_amount = ?, currency = ?, terms = ?, ocr_confidence = ?,
                field_evidence_json = ?, exceptions_json = ?, warnings_json = ?,
                base_review_required = ?, ocr_review_required = ?,
                received_at = ?, processed_at = ?, source_result_created_at = ?,
                source_result_updated_at = ?, source_as_of = ?,
                source_evidence_sha256 = ?, imported_at = ?, last_synced_at = ?
            WHERE ap_invoice_id = ?;
            """,
            (*values[1:], projection.ap_invoice_id),
        )

    def _append_revision(
        self,
        connection: sqlite3.Connection,
        projection: SourceInvoiceProjection,
        recorded_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO ap_invoice_revisions (
                revision_id, ap_invoice_id, source_evidence_sha256,
                source_as_of, snapshot_json, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                self._revision_id(
                    projection.ap_invoice_id,
                    projection.source_evidence_sha256,
                ),
                projection.ap_invoice_id,
                projection.source_evidence_sha256,
                projection.source_as_of,
                self._json(projection.source_snapshot),
                recorded_at,
            ),
        )

    def _append_event(
        self,
        connection: sqlite3.Connection,
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
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO ap_invoice_events (
                event_id, event_key, ap_invoice_id, event_type, label,
                occurred_at, recorded_at, source, actor, details,
                source_evidence_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?);
            """,
            (
                self._event_id(event_key),
                event_key,
                ap_invoice_id,
                event_type,
                label,
                occurred_at,
                recorded_at,
                source,
                details,
                source_hash,
            ),
        )
        return max(cursor.rowcount, 0)

    def sync_projections(
        self,
        projections: Sequence[SourceInvoiceProjection],
        recorded_at: str,
    ) -> dict[str, int]:
        self.initialize()
        imported = 0
        updated = 0
        unchanged = 0
        event_count = 0
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            for projection in projections:
                existing = connection.execute(
                    """
                    SELECT ap_invoice_id, source_evidence_sha256, imported_at
                    FROM ap_invoices
                    WHERE source_key = ?;
                    """,
                    (projection.source_key,),
                ).fetchone()
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
            duplicate_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM ap_duplicate_candidates;"
                ).fetchone()[0]
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        return {
            "imported": imported,
            "updated": updated,
            "unchanged": unchanged,
            "events": event_count,
            "duplicate_candidates": duplicate_count,
        }

    def _synchronize_duplicate_candidates(
        self,
        connection: sqlite3.Connection,
        recorded_at: str,
    ) -> None:
        rows = connection.execute(
            """
            SELECT
                ap_invoice_id,
                normalized_vendor_identity,
                normalized_invoice_number,
                vendor_name,
                invoice_number,
                invoice_date,
                total_amount
            FROM ap_invoices
            WHERE normalized_vendor_identity IS NOT NULL
              AND normalized_invoice_number IS NOT NULL
            ORDER BY ap_invoice_id;
            """
        ).fetchall()
        groups: dict[tuple[str, str], list[sqlite3.Row]] = {}
        for row in rows:
            key = (
                str(row["normalized_vendor_identity"]),
                str(row["normalized_invoice_number"]),
            )
            groups.setdefault(key, []).append(row)

        desired: dict[str, dict[str, Any]] = {}
        for (vendor_identity, invoice_number), group in groups.items():
            for left, right in combinations(group, 2):
                amount_status = "unavailable"
                if left["total_amount"] is not None and right["total_amount"] is not None:
                    if str(left["total_amount"]) != str(right["total_amount"]):
                        continue
                    amount_status = "matched"
                date_status = "unavailable"
                if left["invoice_date"] is not None and right["invoice_date"] is not None:
                    if str(left["invoice_date"]) != str(right["invoice_date"]):
                        continue
                    date_status = "matched"
                invoice_a_id, invoice_b_id = sorted(
                    (str(left["ap_invoice_id"]), str(right["ap_invoice_id"]))
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
            "SELECT candidate_id, evidence_json FROM ap_duplicate_candidates;"
        ).fetchall()
        existing = {
            str(row["candidate_id"]): str(row["evidence_json"])
            for row in existing_rows
        }
        stale_ids = set(existing) - set(desired)
        for candidate_id in stale_ids:
            connection.execute(
                "DELETE FROM ap_duplicate_candidates WHERE candidate_id = ?;",
                (candidate_id,),
            )
        for candidate_id, candidate in desired.items():
            if candidate_id not in existing:
                connection.execute(
                    """
                    INSERT INTO ap_duplicate_candidates (
                        candidate_id, invoice_a_id, invoice_b_id,
                        vendor_identity, normalized_invoice_number,
                        amount_corroboration, date_corroboration,
                        evidence_json, detected_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        candidate["candidate_id"],
                        candidate["invoice_a_id"],
                        candidate["invoice_b_id"],
                        candidate["vendor_identity"],
                        candidate["normalized_invoice_number"],
                        candidate["amount_corroboration"],
                        candidate["date_corroboration"],
                        candidate["evidence_json"],
                        recorded_at,
                        recorded_at,
                    ),
                )
            elif existing[candidate_id] != candidate["evidence_json"]:
                connection.execute(
                    """
                    UPDATE ap_duplicate_candidates
                    SET evidence_json = ?, amount_corroboration = ?,
                        date_corroboration = ?, updated_at = ?
                    WHERE candidate_id = ?;
                    """,
                    (
                        candidate["evidence_json"],
                        candidate["amount_corroboration"],
                        candidate["date_corroboration"],
                        recorded_at,
                        candidate_id,
                    ),
                )

    @staticmethod
    def _decode_row(row: sqlite3.Row) -> dict[str, Any]:
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
        duplicate_expression = (
            "(SELECT COUNT(*) FROM ap_duplicate_candidates d "
            "WHERE d.invoice_a_id = i.ap_invoice_id "
            "OR d.invoice_b_id = i.ap_invoice_id)"
        )
        where: list[str] = []
        parameters: list[Any] = []
        if query:
            token = f"%{query.strip().lower()}%"
            where.append(
                "(LOWER(COALESCE(i.vendor_name, '')) LIKE ? "
                "OR LOWER(COALESCE(i.vendor_number, '')) LIKE ? "
                "OR LOWER(COALESCE(i.invoice_number, '')) LIKE ? "
                "OR LOWER(COALESCE(i.purchase_order_number, '')) LIKE ? "
                "OR LOWER(i.document_job_id) LIKE ? "
                "OR LOWER(i.source_file_name) LIKE ?)"
            )
            parameters.extend([token] * 6)
        if status == "review_required":
            where.append(
                f"(i.base_review_required = 1 OR {duplicate_expression} > 0)"
            )
        elif status == "evidence_available":
            where.append(
                f"(i.base_review_required = 0 AND {duplicate_expression} = 0)"
            )
        elif status == "ocr_review":
            where.append("i.ocr_review_required = 1")
        if exception is True:
            where.append("i.exceptions_json <> '[]'")
        elif exception is False:
            where.append("i.exceptions_json = '[]'")
        if duplicate is True:
            where.append(f"{duplicate_expression} > 0")
        elif duplicate is False:
            where.append(f"{duplicate_expression} = 0")
        if exception_code:
            where.append("i.exceptions_json LIKE ?")
            parameters.append(f'%"code":"{exception_code}"%')

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        sort_columns = {
            "received_at": "i.received_at",
            "invoice_date": "i.invoice_date",
            "due_date": "i.due_date",
            "total": "CAST(i.total_amount AS REAL)",
            "vendor_name": "i.vendor_name",
            "ocr_confidence": "i.ocr_confidence",
        }
        sort_column = sort_columns.get(sort_by, "i.received_at")
        direction = "ASC" if sort_order == "asc" else "DESC"
        connection = self._connection()
        try:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM ap_invoices i {where_sql};",
                    parameters,
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT i.*, {duplicate_expression} AS duplicate_candidate_count
                FROM ap_invoices i
                {where_sql}
                ORDER BY {sort_column} {direction}, i.ap_invoice_id ASC
                LIMIT ? OFFSET ?;
                """,
                (*parameters, limit, offset),
            ).fetchall()
        finally:
            connection.close()
        return [self._decode_row(row) for row in rows], total

    def get_invoice(self, ap_invoice_id: str) -> dict[str, Any] | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT i.*,
                    (SELECT COUNT(*) FROM ap_duplicate_candidates d
                     WHERE d.invoice_a_id = i.ap_invoice_id
                        OR d.invoice_b_id = i.ap_invoice_id)
                    AS duplicate_candidate_count
                FROM ap_invoices i
                WHERE i.ap_invoice_id = ?;
                """,
                (ap_invoice_id,),
            ).fetchone()
        finally:
            connection.close()
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
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT d.*,
                    CASE WHEN d.invoice_a_id = ?
                         THEN d.invoice_b_id ELSE d.invoice_a_id END
                    AS candidate_ap_invoice_id,
                    other.invoice_number AS candidate_invoice_number,
                    other.vendor_name AS candidate_vendor_name,
                    other.total_amount AS candidate_amount
                FROM ap_duplicate_candidates d
                JOIN ap_invoices other
                  ON other.ap_invoice_id = CASE
                      WHEN d.invoice_a_id = ?
                      THEN d.invoice_b_id ELSE d.invoice_a_id END
                WHERE d.invoice_a_id = ? OR d.invoice_b_id = ?
                ORDER BY d.candidate_id;
                """,
                (ap_invoice_id, ap_invoice_id, ap_invoice_id, ap_invoice_id),
            ).fetchall()
        finally:
            connection.close()
        results: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(item.pop("evidence_json"))
            results.append(item)
        return results

    def list_events(self, ap_invoice_id: str) -> list[dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT event_id, event_type, label, occurred_at, recorded_at,
                       source, actor, details, source_evidence_sha256
                FROM ap_invoice_events
                WHERE ap_invoice_id = ?
                ORDER BY COALESCE(occurred_at, recorded_at), event_id;
                """,
                (ap_invoice_id,),
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]

    def revision_count(self, ap_invoice_id: str) -> int:
        self.initialize()
        connection = self._connection()
        try:
            return int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM ap_invoice_revisions
                    WHERE ap_invoice_id = ?;
                    """,
                    (ap_invoice_id,),
                ).fetchone()[0]
            )
        finally:
            connection.close()

    def create_control_case(
        self,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        self.initialize()
        snapshot_json = self._json(record["evidence_snapshot"])
        snapshot_hash = hashlib.sha256(
            snapshot_json.encode("utf-8")
        ).hexdigest()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute(
                """
                INSERT INTO ap_control_cases (
                    control_case_id, ap_invoice_id, intended_action,
                    requested_by, assigned_reviewer, payment_preparer,
                    notes, created_at, source_evidence_sha256,
                    evidence_snapshot_json, evidence_snapshot_sha256,
                    actor_identity_source, actor_authority_status,
                    approval_effect, payment_effect
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record["control_case_id"],
                    record["ap_invoice_id"],
                    record["intended_action"],
                    record["requested_by"],
                    record["assigned_reviewer"],
                    record["payment_preparer"],
                    record["notes"],
                    record["created_at"],
                    record["source_evidence_sha256"],
                    snapshot_json,
                    snapshot_hash,
                    record["actor_identity_source"],
                    record["actor_authority_status"],
                    record["approval_effect"],
                    record["payment_effect"],
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        stored = self.get_control_case(record["control_case_id"])
        if stored is None:
            raise RuntimeError("The AP control case was not persisted.")
        return stored

    def create_control_review(
        self,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        self.initialize()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute(
                """
                INSERT INTO ap_control_reviews (
                    review_id, control_case_id, reviewer_identity,
                    disposition, notes, created_at, actor_identity_source,
                    actor_authority_status, approval_effect, payment_effect
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record["review_id"],
                    record["control_case_id"],
                    record["reviewer_identity"],
                    record["disposition"],
                    record["notes"],
                    record["created_at"],
                    record["actor_identity_source"],
                    record["actor_authority_status"],
                    record["approval_effect"],
                    record["payment_effect"],
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        stored = self.get_control_review(record["review_id"])
        if stored is None:
            raise RuntimeError("The AP control review was not persisted.")
        return stored

    def get_control_case(
        self,
        control_case_id: str,
    ) -> dict[str, Any] | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT * FROM ap_control_cases
                WHERE control_case_id = ?;
                """,
                (control_case_id,),
            ).fetchone()
        finally:
            connection.close()
        return self._control_case_from_row(row) if row is not None else None

    def list_control_cases(
        self,
        *,
        intended_action: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        self.initialize()
        where = "WHERE intended_action = ?" if intended_action else ""
        parameters: tuple[Any, ...] = (
            (intended_action,) if intended_action else ()
        )
        connection = self._connection()
        try:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM ap_control_cases {where};",
                    parameters,
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT * FROM ap_control_cases
                {where}
                ORDER BY created_at DESC, control_case_id DESC
                LIMIT ? OFFSET ?;
                """,
                (*parameters, limit, offset),
            ).fetchall()
        finally:
            connection.close()
        return [self._control_case_from_row(row) for row in rows], total

    def get_control_review(
        self,
        review_id: str,
    ) -> dict[str, Any] | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT * FROM ap_control_reviews
                WHERE review_id = ?;
                """,
                (review_id,),
            ).fetchone()
        finally:
            connection.close()
        return self._control_review_from_row(row) if row is not None else None

    def list_control_reviews(
        self,
        control_case_id: str,
    ) -> list[dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT * FROM ap_control_reviews
                WHERE control_case_id = ?
                ORDER BY created_at DESC, review_id DESC;
                """,
                (control_case_id,),
            ).fetchall()
        finally:
            connection.close()
        return [self._control_review_from_row(row) for row in rows]

    def approval_time_stats(self, intended_action: str) -> dict[str, Any]:
        """Average hours from a control case's creation to its first
        recorded review disposition, for cases opened with the given
        intended_action. Both tables are append-only local evidence, so
        this is a real, computable metric with no ERP dependency."""

        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS case_count,
                    AVG(
                        julianday(first_review.created_at)
                        - julianday(c.created_at)
                    ) * 24.0 AS avg_hours,
                    MAX(first_review.created_at) AS latest_reviewed_at
                FROM ap_control_cases c
                JOIN (
                    SELECT control_case_id, MIN(created_at) AS created_at
                    FROM ap_control_reviews
                    GROUP BY control_case_id
                ) first_review
                    ON first_review.control_case_id = c.control_case_id
                WHERE c.intended_action = ?;
                """,
                (intended_action,),
            ).fetchone()
        finally:
            connection.close()
        case_count = int(row["case_count"] or 0)
        return {
            "case_count": case_count,
            "average_hours": (
                float(row["avg_hours"]) if row["avg_hours"] is not None else None
            ),
            "latest_reviewed_at": row["latest_reviewed_at"],
        }

    def create_cash_scenario(
        self,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        self.initialize()
        snapshot_json = self._json(record["evidence_snapshot"])
        snapshot_hash = hashlib.sha256(
            snapshot_json.encode("utf-8")
        ).hexdigest()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute(
                """
                INSERT INTO ap_cash_scenarios (
                    cash_scenario_id, as_of_date, horizon_days,
                    horizon_end_date, include_review_required, prepared_by,
                    rationale, created_at, included_invoice_count,
                    included_known_amount_count, extracted_amount,
                    excluded_review_required_count,
                    excluded_missing_due_date_count,
                    excluded_missing_amount_count, actor_identity_source,
                    actor_authority_status, scenario_classification,
                    current_payable_status_known, approval_effect,
                    payment_effect, erp_write, evidence_snapshot_json,
                    evidence_snapshot_sha256
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0,
                    ?, ?, 0, ?, ?
                );
                """,
                (
                    record["cash_scenario_id"],
                    record["as_of_date"],
                    record["horizon_days"],
                    record["horizon_end_date"],
                    int(record["include_review_required"]),
                    record["prepared_by"],
                    record["rationale"],
                    record["created_at"],
                    record["included_invoice_count"],
                    record["included_known_amount_count"],
                    record["extracted_amount"],
                    record["excluded_review_required_count"],
                    record["excluded_missing_due_date_count"],
                    record["excluded_missing_amount_count"],
                    record["actor_identity_source"],
                    record["actor_authority_status"],
                    record["scenario_classification"],
                    record["approval_effect"],
                    record["payment_effect"],
                    snapshot_json,
                    snapshot_hash,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        stored = self.get_cash_scenario(record["cash_scenario_id"])
        if stored is None:
            raise RuntimeError("The AP cash scenario was not persisted.")
        return stored

    def get_cash_scenario(
        self,
        cash_scenario_id: str,
    ) -> dict[str, Any] | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT * FROM ap_cash_scenarios
                WHERE cash_scenario_id = ?;
                """,
                (cash_scenario_id,),
            ).fetchone()
        finally:
            connection.close()
        return self._cash_scenario_from_row(row) if row is not None else None

    def list_cash_scenarios(self) -> list[dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT * FROM ap_cash_scenarios
                ORDER BY created_at DESC, cash_scenario_id DESC;
                """
            ).fetchall()
        finally:
            connection.close()
        return [self._cash_scenario_from_row(row) for row in rows]

    def create_exception_action(
        self,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        self.initialize()
        snapshot_json = self._json(record["evidence_snapshot"])
        snapshot_hash = hashlib.sha256(
            snapshot_json.encode("utf-8")
        ).hexdigest()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute(
                """
                INSERT INTO ap_exception_actions (
                    action_id, ap_invoice_id, disposition, owner_identity,
                    actor_identity, notes, follow_up_date, created_at,
                    source_evidence_sha256, actor_identity_source,
                    owner_identity_source, authority_status,
                    action_classification, approval_effect, payment_effect,
                    erp_write, evidence_snapshot_json,
                    evidence_snapshot_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?);
                """,
                (
                    record["action_id"],
                    record["ap_invoice_id"],
                    record["disposition"],
                    record["owner_identity"],
                    record["actor_identity"],
                    record["notes"],
                    record["follow_up_date"],
                    record["created_at"],
                    record["source_evidence_sha256"],
                    record["actor_identity_source"],
                    record["owner_identity_source"],
                    record["authority_status"],
                    record["action_classification"],
                    record["approval_effect"],
                    record["payment_effect"],
                    snapshot_json,
                    snapshot_hash,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        stored = self.get_exception_action(record["action_id"])
        if stored is None:
            raise RuntimeError("The AP exception action was not persisted.")
        return stored

    def get_exception_action(
        self,
        action_id: str,
    ) -> dict[str, Any] | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                "SELECT * FROM ap_exception_actions WHERE action_id = ?;",
                (action_id,),
            ).fetchone()
        finally:
            connection.close()
        return self._exception_action_from_row(row) if row is not None else None

    def list_exception_actions(
        self,
        ap_invoice_id: str,
    ) -> list[dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT * FROM ap_exception_actions
                WHERE ap_invoice_id = ?
                ORDER BY created_at DESC, action_id DESC;
                """,
                (ap_invoice_id,),
            ).fetchall()
        finally:
            connection.close()
        return [self._exception_action_from_row(row) for row in rows]

    def list_latest_exception_actions(self) -> dict[str, dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                WITH ranked_actions AS (
                    SELECT ap_exception_actions.*,
                           ROW_NUMBER() OVER (
                               PARTITION BY ap_invoice_id
                               ORDER BY created_at DESC, action_id DESC
                           ) AS action_rank
                    FROM ap_exception_actions
                )
                SELECT * FROM ranked_actions WHERE action_rank = 1;
                """
            ).fetchall()
        finally:
            connection.close()
        return {
            str(row["ap_invoice_id"]): self._exception_action_from_row(row)
            for row in rows
        }

    @staticmethod
    def _control_case_from_row(row: sqlite3.Row) -> dict[str, Any]:
        snapshot_json = str(row["evidence_snapshot_json"])
        expected_hash = str(row["evidence_snapshot_sha256"])
        actual_hash = hashlib.sha256(
            snapshot_json.encode("utf-8")
        ).hexdigest()
        if actual_hash != expected_hash:
            raise RuntimeError(
                "Stored AP control-case evidence failed its SHA-256 "
                "integrity check."
            )
        result = dict(row)
        result["evidence_snapshot"] = json.loads(
            result.pop("evidence_snapshot_json")
        )
        result["evidence_snapshot_sha256"] = expected_hash
        return result

    @staticmethod
    def _control_review_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    @staticmethod
    def _cash_scenario_from_row(row: sqlite3.Row) -> dict[str, Any]:
        snapshot_json = str(row["evidence_snapshot_json"])
        expected_hash = str(row["evidence_snapshot_sha256"])
        actual_hash = hashlib.sha256(
            snapshot_json.encode("utf-8")
        ).hexdigest()
        if actual_hash != expected_hash:
            raise RuntimeError(
                "Stored AP cash-scenario evidence failed its SHA-256 "
                "integrity check."
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
    def _exception_action_from_row(row: sqlite3.Row) -> dict[str, Any]:
        snapshot_json = str(row["evidence_snapshot_json"])
        expected_hash = str(row["evidence_snapshot_sha256"])
        actual_hash = hashlib.sha256(
            snapshot_json.encode("utf-8")
        ).hexdigest()
        if actual_hash != expected_hash:
            raise RuntimeError(
                "Stored AP exception-action evidence failed its SHA-256 "
                "integrity check."
            )
        result = dict(row)
        result.pop("action_rank", None)
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
