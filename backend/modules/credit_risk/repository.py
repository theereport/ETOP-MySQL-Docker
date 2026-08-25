from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from data.database import get_connection


BAND_SET_ID = "credit-risk-manual-rating"
BAND_SET_VERSION = "1.0.0-draft"
BAND_SET_STATUS = "product_owner_supplied_draft"
BAND_SET_TITLE = "Manual commercial credit risk rating bands"
BAND_SET_SOURCE = (
    "SRC-002 World-Class Credit Risk Module Source Record"
)

BAND_SEED: tuple[tuple[int, int, int, str, str], ...] = (
    (1, 1, 2, "Very low risk", "Normal terms"),
    (2, 3, 4, "Low risk", "Routine monitoring"),
    (3, 5, 5, "Moderate risk", "Watch for deterioration"),
    (4, 6, 6, "Elevated risk", "Analyst review"),
    (5, 7, 7, "High risk", "Restrict additional exposure"),
    (6, 8, 8, "Very high risk", "Hold or secured terms"),
    (7, 9, 9, "Default likely", "Executive decision"),
    (8, 10, 10, "Default or legal", "Collections/legal management"),
)


class RiskBandConfigurationConflict(RuntimeError):
    """Raised when an existing version disagrees with its governed seed."""


class AssessmentEvidenceIntegrityError(RuntimeError):
    """Raised when stored evidence no longer matches its integrity marker."""


class CreditRiskRepository:
    """Local append-only persistence for Credit Risk assessments."""

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
        """Create schema and seed the initial governed draft idempotently."""

        with self._initialization_lock:
            connection = self._connection()
            try:
                connection.execute("BEGIN IMMEDIATE;")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS credit_risk_band_sets (
                        band_set_id TEXT NOT NULL,
                        version TEXT NOT NULL,
                        title TEXT NOT NULL,
                        status TEXT NOT NULL,
                        source_record TEXT NOT NULL,
                        seeded_at TEXT NOT NULL,
                        automated_policy INTEGER NOT NULL DEFAULT 0
                            CHECK (automated_policy = 0),
                        promotion_authority TEXT NOT NULL DEFAULT 'deferred'
                            CHECK (promotion_authority = 'deferred'),
                        is_current INTEGER NOT NULL DEFAULT 0
                            CHECK (is_current IN (0, 1)),
                        PRIMARY KEY (band_set_id, version)
                    );
                    """
                )
                connection.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS
                        idx_credit_risk_one_current_band_set
                    ON credit_risk_band_sets(is_current)
                    WHERE is_current = 1;
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS credit_risk_bands (
                        band_set_id TEXT NOT NULL,
                        band_set_version TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        rating_min INTEGER NOT NULL
                            CHECK (rating_min BETWEEN 1 AND 10),
                        rating_max INTEGER NOT NULL
                            CHECK (rating_max BETWEEN 1 AND 10),
                        meaning TEXT NOT NULL,
                        typical_response TEXT NOT NULL,
                        PRIMARY KEY (
                            band_set_id,
                            band_set_version,
                            sequence
                        ),
                        FOREIGN KEY (band_set_id, band_set_version)
                            REFERENCES credit_risk_band_sets(
                                band_set_id,
                                version
                            )
                    );
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_credit_risk_band_rating
                    ON credit_risk_bands(
                        band_set_id,
                        band_set_version,
                        rating_min,
                        rating_max
                    );
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS credit_risk_assessments (
                        assessment_id TEXT PRIMARY KEY,
                        customer_number INTEGER NOT NULL,
                        customer_name TEXT NOT NULL,
                        manual_rating INTEGER NOT NULL
                            CHECK (manual_rating BETWEEN 1 AND 10),
                        band_set_id TEXT NOT NULL,
                        band_set_version TEXT NOT NULL,
                        band_set_status TEXT NOT NULL,
                        band_sequence INTEGER NOT NULL,
                        band_rating_min INTEGER NOT NULL,
                        band_rating_max INTEGER NOT NULL,
                        band_meaning TEXT NOT NULL,
                        band_typical_response TEXT NOT NULL,
                        review_date TEXT NOT NULL,
                        next_review_date TEXT NOT NULL,
                        analyst_identity TEXT NOT NULL,
                        rationale TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        source_as_of TEXT NOT NULL,
                        completeness_state TEXT NOT NULL
                            CHECK (completeness_state = 'partial'),
                        actor_identity_source TEXT NOT NULL
                            CHECK (
                                actor_identity_source = 'operator_supplied'
                            ),
                        actor_authority_status TEXT NOT NULL
                            CHECK (
                                actor_authority_status =
                                    'not_independently_verified'
                            ),
                        assessment_classification TEXT NOT NULL
                            CHECK (
                                assessment_classification =
                                    'professional_judgment'
                            ),
                        decision_effect TEXT NOT NULL
                            CHECK (decision_effect = 'none'),
                        evidence_snapshot_json TEXT NOT NULL,
                        evidence_snapshot_sha256 TEXT NOT NULL
                            CHECK (length(evidence_snapshot_sha256) = 64),
                        FOREIGN KEY (band_set_id, band_set_version)
                            REFERENCES credit_risk_band_sets(
                                band_set_id,
                                version
                            )
                    );
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_credit_risk_assessments_customer_time
                    ON credit_risk_assessments(
                        customer_number,
                        created_at DESC,
                        assessment_id DESC
                    );
                    """
                )
                connection.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS
                        credit_risk_assessments_no_update
                    BEFORE UPDATE ON credit_risk_assessments
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'Credit Risk assessments are append-only.'
                        );
                    END;
                    """
                )
                connection.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS
                        credit_risk_assessments_no_delete
                    BEFORE DELETE ON credit_risk_assessments
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'Credit Risk assessments are append-only.'
                        );
                    END;
                    """
                )

                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS credit_line_proposals (
                        proposal_id TEXT PRIMARY KEY,
                        customer_number INTEGER NOT NULL,
                        customer_name TEXT NOT NULL,
                        proposed_credit_line REAL NOT NULL
                            CHECK (proposed_credit_line >= 0),
                        current_credit_line REAL NOT NULL,
                        analytical_reference_line REAL,
                        review_date TEXT NOT NULL,
                        analyst_identity TEXT NOT NULL,
                        rationale TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        source_as_of TEXT NOT NULL,
                        actor_identity_source TEXT NOT NULL
                            CHECK (
                                actor_identity_source = 'operator_supplied'
                            ),
                        actor_authority_status TEXT NOT NULL
                            CHECK (
                                actor_authority_status =
                                    'not_independently_verified'
                            ),
                        proposal_classification TEXT NOT NULL
                            CHECK (
                                proposal_classification =
                                    'professional_recommendation'
                            ),
                        approval_status TEXT NOT NULL
                            CHECK (
                                approval_status =
                                    'not_submitted_to_governed_approval'
                            ),
                        decision_effect TEXT NOT NULL
                            CHECK (decision_effect = 'none'),
                        erp_write INTEGER NOT NULL DEFAULT 0
                            CHECK (erp_write = 0),
                        evidence_snapshot_json TEXT NOT NULL,
                        evidence_snapshot_sha256 TEXT NOT NULL
                            CHECK (length(evidence_snapshot_sha256) = 64)
                    );
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_credit_line_proposals_customer_time
                    ON credit_line_proposals(
                        customer_number,
                        created_at DESC,
                        proposal_id DESC
                    );
                    """
                )
                connection.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS
                        credit_line_proposals_no_update
                    BEFORE UPDATE ON credit_line_proposals
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'Credit-line proposals are append-only.'
                        );
                    END;
                    """
                )
                connection.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS
                        credit_line_proposals_no_delete
                    BEFORE DELETE ON credit_line_proposals
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'Credit-line proposals are append-only.'
                        );
                    END;
                    """
                )

                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS credit_portfolio_reviews (
                        portfolio_review_id TEXT PRIMARY KEY,
                        customer_number INTEGER NOT NULL,
                        customer_name TEXT NOT NULL,
                        disposition TEXT NOT NULL CHECK (
                            disposition IN (
                                'reviewed_no_change',
                                'reassessment_needed',
                                'credit_line_analysis_needed',
                                'information_requested'
                            )
                        ),
                        reviewer_identity TEXT NOT NULL,
                        notes TEXT NOT NULL,
                        follow_up_date TEXT,
                        created_at TEXT NOT NULL,
                        assessment_id TEXT NOT NULL,
                        proposal_id TEXT,
                        actor_identity_source TEXT NOT NULL CHECK (
                            actor_identity_source = 'operator_supplied'
                        ),
                        actor_authority_status TEXT NOT NULL CHECK (
                            actor_authority_status =
                                'not_independently_verified'
                        ),
                        review_classification TEXT NOT NULL CHECK (
                            review_classification =
                                'professional_workflow_metadata'
                        ),
                        decision_effect TEXT NOT NULL CHECK (
                            decision_effect = 'none'
                        ),
                        erp_write INTEGER NOT NULL DEFAULT 0 CHECK (
                            erp_write = 0
                        ),
                        evidence_snapshot_json TEXT NOT NULL,
                        evidence_snapshot_sha256 TEXT NOT NULL CHECK (
                            length(evidence_snapshot_sha256) = 64
                        ),
                        FOREIGN KEY (assessment_id)
                            REFERENCES credit_risk_assessments(assessment_id),
                        FOREIGN KEY (proposal_id)
                            REFERENCES credit_line_proposals(proposal_id)
                    );
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_credit_portfolio_reviews_customer_time
                    ON credit_portfolio_reviews(
                        customer_number,
                        created_at DESC,
                        portfolio_review_id DESC
                    );
                    """
                )
                connection.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS
                        credit_portfolio_reviews_no_update
                    BEFORE UPDATE ON credit_portfolio_reviews
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'Credit portfolio reviews are append-only.'
                        );
                    END;
                    """
                )
                connection.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS
                        credit_portfolio_reviews_no_delete
                    BEFORE DELETE ON credit_portfolio_reviews
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'Credit portfolio reviews are append-only.'
                        );
                    END;
                    """
                )

                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS credit_order_recommendations (
                        order_recommendation_id TEXT PRIMARY KEY,
                        customer_number INTEGER NOT NULL,
                        customer_name TEXT NOT NULL,
                        contemplated_order_amount REAL NOT NULL CHECK (
                            contemplated_order_amount > 0
                        ),
                        order_reference TEXT,
                        disposition TEXT NOT NULL CHECK (
                            disposition IN (
                                'advance_to_authorized_review',
                                'request_additional_information',
                                'escalate_for_credit_authority',
                                'do_not_advance'
                            )
                        ),
                        analyst_identity TEXT NOT NULL,
                        rationale TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        source_as_of TEXT NOT NULL,
                        assessment_id TEXT,
                        proposal_id TEXT,
                        current_credit_line REAL NOT NULL,
                        current_partial_exposure REAL NOT NULL,
                        projected_partial_exposure REAL NOT NULL,
                        projected_partial_available_credit REAL NOT NULL,
                        projected_partial_over_line_amount REAL NOT NULL CHECK (
                            projected_partial_over_line_amount >= 0
                        ),
                        actor_identity_source TEXT NOT NULL CHECK (
                            actor_identity_source = 'operator_supplied'
                        ),
                        actor_authority_status TEXT NOT NULL CHECK (
                            actor_authority_status =
                                'not_independently_verified'
                        ),
                        recommendation_classification TEXT NOT NULL CHECK (
                            recommendation_classification =
                                'professional_recommendation'
                        ),
                        decision_status TEXT NOT NULL CHECK (
                            decision_status =
                                'not_submitted_to_governed_decision'
                        ),
                        decision_effect TEXT NOT NULL CHECK (
                            decision_effect = 'none'
                        ),
                        order_effect TEXT NOT NULL CHECK (
                            order_effect = 'none'
                        ),
                        erp_write INTEGER NOT NULL DEFAULT 0 CHECK (
                            erp_write = 0
                        ),
                        evidence_snapshot_json TEXT NOT NULL,
                        evidence_snapshot_sha256 TEXT NOT NULL CHECK (
                            length(evidence_snapshot_sha256) = 64
                        ),
                        FOREIGN KEY (assessment_id)
                            REFERENCES credit_risk_assessments(assessment_id),
                        FOREIGN KEY (proposal_id)
                            REFERENCES credit_line_proposals(proposal_id)
                    );
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_credit_order_recommendations_customer_time
                    ON credit_order_recommendations(
                        customer_number,
                        created_at DESC,
                        order_recommendation_id DESC
                    );
                    """
                )
                connection.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS
                        credit_order_recommendations_no_update
                    BEFORE UPDATE ON credit_order_recommendations
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'Credit order recommendations are append-only.'
                        );
                    END;
                    """
                )
                connection.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS
                        credit_order_recommendations_no_delete
                    BEFORE DELETE ON credit_order_recommendations
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'Credit order recommendations are append-only.'
                        );
                    END;
                    """
                )

                seeded_at = datetime.now(UTC).isoformat()
                connection.execute(
                    """
                    INSERT OR IGNORE INTO credit_risk_band_sets (
                        band_set_id,
                        version,
                        title,
                        status,
                        source_record,
                        seeded_at,
                        automated_policy,
                        promotion_authority,
                        is_current
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 0, 'deferred', 1);
                    """,
                    (
                        BAND_SET_ID,
                        BAND_SET_VERSION,
                        BAND_SET_TITLE,
                        BAND_SET_STATUS,
                        BAND_SET_SOURCE,
                        seeded_at,
                    ),
                )

                for band in BAND_SEED:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO credit_risk_bands (
                            band_set_id,
                            band_set_version,
                            sequence,
                            rating_min,
                            rating_max,
                            meaning,
                            typical_response
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            BAND_SET_ID,
                            BAND_SET_VERSION,
                            *band,
                        ),
                    )

                self._verify_seed(connection)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    @staticmethod
    def _verify_seed(connection: sqlite3.Connection) -> None:
        metadata = connection.execute(
            """
            SELECT
                band_set_id,
                version,
                title,
                status,
                source_record,
                automated_policy,
                promotion_authority,
                is_current
            FROM credit_risk_band_sets
            WHERE band_set_id = ? AND version = ?;
            """,
            (BAND_SET_ID, BAND_SET_VERSION),
        ).fetchone()

        expected_metadata = (
            BAND_SET_ID,
            BAND_SET_VERSION,
            BAND_SET_TITLE,
            BAND_SET_STATUS,
            BAND_SET_SOURCE,
            0,
            "deferred",
            1,
        )
        if metadata is None or tuple(metadata) != expected_metadata:
            raise RiskBandConfigurationConflict(
                "Existing Credit Risk band-set version conflicts with the "
                "Product Owner supplied draft. No seed data was overwritten."
            )

        rows = connection.execute(
            """
            SELECT
                sequence,
                rating_min,
                rating_max,
                meaning,
                typical_response
            FROM credit_risk_bands
            WHERE band_set_id = ? AND band_set_version = ?
            ORDER BY sequence;
            """,
            (BAND_SET_ID, BAND_SET_VERSION),
        ).fetchall()

        if tuple(tuple(row) for row in rows) != BAND_SEED:
            raise RiskBandConfigurationConflict(
                "Existing Credit Risk band rows conflict with the Product "
                "Owner supplied draft. No configuration was overwritten."
            )

    def get_current_band_set(self) -> dict[str, Any]:
        self.initialize()
        connection = self._connection()
        try:
            metadata = connection.execute(
                """
                SELECT
                    band_set_id,
                    version,
                    title,
                    status,
                    source_record,
                    seeded_at,
                    automated_policy,
                    promotion_authority
                FROM credit_risk_band_sets
                WHERE is_current = 1
                LIMIT 1;
                """
            ).fetchone()
            if metadata is None:
                raise RuntimeError(
                    "No current Credit Risk band set is configured."
                )

            bands = connection.execute(
                """
                SELECT
                    sequence,
                    rating_min,
                    rating_max,
                    meaning,
                    typical_response
                FROM credit_risk_bands
                WHERE band_set_id = ? AND band_set_version = ?
                ORDER BY sequence;
                """,
                (metadata["band_set_id"], metadata["version"]),
            ).fetchall()
        finally:
            connection.close()

        band_set = dict(metadata)
        band_set["automated_policy"] = bool(
            band_set["automated_policy"]
        )
        return {
            "band_set": band_set,
            "bands": [dict(row) for row in bands],
        }

    def create_assessment(self, record: dict[str, Any]) -> dict[str, Any]:
        self.initialize()
        band = record["band"]
        snapshot_json = json.dumps(
            record["evidence_snapshot"],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        snapshot_sha256 = hashlib.sha256(
            snapshot_json.encode("utf-8")
        ).hexdigest()

        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute(
                """
                INSERT INTO credit_risk_assessments (
                    assessment_id,
                    customer_number,
                    customer_name,
                    manual_rating,
                    band_set_id,
                    band_set_version,
                    band_set_status,
                    band_sequence,
                    band_rating_min,
                    band_rating_max,
                    band_meaning,
                    band_typical_response,
                    review_date,
                    next_review_date,
                    analyst_identity,
                    rationale,
                    created_at,
                    source_as_of,
                    completeness_state,
                    actor_identity_source,
                    actor_authority_status,
                    assessment_classification,
                    decision_effect,
                    evidence_snapshot_json,
                    evidence_snapshot_sha256
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?
                );
                """,
                (
                    record["assessment_id"],
                    record["customer_number"],
                    record["customer_name"],
                    record["manual_rating"],
                    record["band_set_id"],
                    record["band_set_version"],
                    record["band_set_status"],
                    band["sequence"],
                    band["rating_min"],
                    band["rating_max"],
                    band["meaning"],
                    band["typical_response"],
                    record["review_date"],
                    record["next_review_date"],
                    record["analyst_identity"],
                    record["rationale"],
                    record["created_at"],
                    record["source_as_of"],
                    record["completeness_state"],
                    record["actor_identity_source"],
                    record["actor_authority_status"],
                    record["assessment_classification"],
                    record["decision_effect"],
                    snapshot_json,
                    snapshot_sha256,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        stored = self.get_assessment(record["assessment_id"])
        if stored is None:
            raise RuntimeError("The Credit Risk assessment was not persisted.")
        return stored

    def get_assessment(self, assessment_id: str) -> dict[str, Any] | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT *
                FROM credit_risk_assessments
                WHERE assessment_id = ?;
                """,
                (assessment_id,),
            ).fetchone()
        finally:
            connection.close()
        return self._assessment_from_row(row) if row is not None else None

    def create_credit_line_proposal(
        self,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        self.initialize()
        snapshot_json = json.dumps(
            record["evidence_snapshot"],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        snapshot_sha256 = hashlib.sha256(
            snapshot_json.encode("utf-8")
        ).hexdigest()

        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute(
                """
                INSERT INTO credit_line_proposals (
                    proposal_id, customer_number, customer_name,
                    proposed_credit_line, current_credit_line,
                    analytical_reference_line, review_date,
                    analyst_identity, rationale, created_at, source_as_of,
                    actor_identity_source, actor_authority_status,
                    proposal_classification, approval_status,
                    decision_effect, erp_write, evidence_snapshot_json,
                    evidence_snapshot_sha256
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0,
                    ?, ?
                );
                """,
                (
                    record["proposal_id"],
                    record["customer_number"],
                    record["customer_name"],
                    record["proposed_credit_line"],
                    record["current_credit_line"],
                    record["analytical_reference_line"],
                    record["review_date"],
                    record["analyst_identity"],
                    record["rationale"],
                    record["created_at"],
                    record["source_as_of"],
                    record["actor_identity_source"],
                    record["actor_authority_status"],
                    record["proposal_classification"],
                    record["approval_status"],
                    record["decision_effect"],
                    snapshot_json,
                    snapshot_sha256,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        stored = self.get_credit_line_proposal(record["proposal_id"])
        if stored is None:
            raise RuntimeError("The credit-line proposal was not persisted.")
        return stored

    def get_credit_line_proposal(
        self,
        proposal_id: str,
    ) -> dict[str, Any] | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT * FROM credit_line_proposals
                WHERE proposal_id = ?;
                """,
                (proposal_id,),
            ).fetchone()
        finally:
            connection.close()
        return self._proposal_from_row(row) if row is not None else None

    def list_credit_line_proposals(
        self,
        customer_number: int,
    ) -> list[dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT * FROM credit_line_proposals
                WHERE customer_number = ?
                ORDER BY created_at DESC, proposal_id DESC;
                """,
                (customer_number,),
            ).fetchall()
        finally:
            connection.close()
        return [self._proposal_from_row(row) for row in rows]

    def get_latest_credit_line_proposal(
        self,
        customer_number: int,
    ) -> dict[str, Any] | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT * FROM credit_line_proposals
                WHERE customer_number = ?
                ORDER BY created_at DESC, proposal_id DESC
                LIMIT 1;
                """,
                (customer_number,),
            ).fetchone()
        finally:
            connection.close()
        return self._proposal_from_row(row) if row is not None else None

    def create_portfolio_review(
        self,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        self.initialize()
        snapshot_json = json.dumps(
            record["evidence_snapshot"],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        snapshot_sha256 = hashlib.sha256(
            snapshot_json.encode("utf-8")
        ).hexdigest()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute(
                """
                INSERT INTO credit_portfolio_reviews (
                    portfolio_review_id, customer_number, customer_name,
                    disposition, reviewer_identity, notes, follow_up_date,
                    created_at, assessment_id, proposal_id,
                    actor_identity_source, actor_authority_status,
                    review_classification, decision_effect, erp_write,
                    evidence_snapshot_json, evidence_snapshot_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?);
                """,
                (
                    record["portfolio_review_id"],
                    record["customer_number"],
                    record["customer_name"],
                    record["disposition"],
                    record["reviewer_identity"],
                    record["notes"],
                    record["follow_up_date"],
                    record["created_at"],
                    record["assessment_id"],
                    record["proposal_id"],
                    record["actor_identity_source"],
                    record["actor_authority_status"],
                    record["review_classification"],
                    record["decision_effect"],
                    snapshot_json,
                    snapshot_sha256,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        stored = self.get_portfolio_review(record["portfolio_review_id"])
        if stored is None:
            raise RuntimeError("The credit portfolio review was not persisted.")
        return stored

    def get_portfolio_review(
        self,
        portfolio_review_id: str,
    ) -> dict[str, Any] | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT * FROM credit_portfolio_reviews
                WHERE portfolio_review_id = ?;
                """,
                (portfolio_review_id,),
            ).fetchone()
        finally:
            connection.close()
        return self._portfolio_review_from_row(row) if row is not None else None

    def list_portfolio_reviews(
        self,
        customer_number: int,
    ) -> list[dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT * FROM credit_portfolio_reviews
                WHERE customer_number = ?
                ORDER BY created_at DESC, portfolio_review_id DESC;
                """,
                (customer_number,),
            ).fetchall()
        finally:
            connection.close()
        return [self._portfolio_review_from_row(row) for row in rows]

    def get_latest_portfolio_review(
        self,
        customer_number: int,
    ) -> dict[str, Any] | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT * FROM credit_portfolio_reviews
                WHERE customer_number = ?
                ORDER BY created_at DESC, portfolio_review_id DESC
                LIMIT 1;
                """,
                (customer_number,),
            ).fetchone()
        finally:
            connection.close()
        return self._portfolio_review_from_row(row) if row is not None else None

    def create_order_recommendation(
        self,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        self.initialize()
        snapshot_json = json.dumps(
            record["evidence_snapshot"],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        snapshot_sha256 = hashlib.sha256(
            snapshot_json.encode("utf-8")
        ).hexdigest()
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute(
                """
                INSERT INTO credit_order_recommendations (
                    order_recommendation_id, customer_number, customer_name,
                    contemplated_order_amount, order_reference, disposition,
                    analyst_identity, rationale, created_at, source_as_of,
                    assessment_id, proposal_id, current_credit_line,
                    current_partial_exposure, projected_partial_exposure,
                    projected_partial_available_credit,
                    projected_partial_over_line_amount,
                    actor_identity_source, actor_authority_status,
                    recommendation_classification, decision_status,
                    decision_effect, order_effect, erp_write,
                    evidence_snapshot_json, evidence_snapshot_sha256
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, 0, ?, ?
                );
                """,
                (
                    record["order_recommendation_id"],
                    record["customer_number"],
                    record["customer_name"],
                    record["contemplated_order_amount"],
                    record["order_reference"],
                    record["disposition"],
                    record["analyst_identity"],
                    record["rationale"],
                    record["created_at"],
                    record["source_as_of"],
                    record["assessment_id"],
                    record["proposal_id"],
                    record["current_credit_line"],
                    record["current_partial_exposure"],
                    record["projected_partial_exposure"],
                    record["projected_partial_available_credit"],
                    record["projected_partial_over_line_amount"],
                    record["actor_identity_source"],
                    record["actor_authority_status"],
                    record["recommendation_classification"],
                    record["decision_status"],
                    record["decision_effect"],
                    record["order_effect"],
                    snapshot_json,
                    snapshot_sha256,
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        stored = self.get_order_recommendation(
            record["order_recommendation_id"]
        )
        if stored is None:
            raise RuntimeError("The credit order recommendation was not persisted.")
        return stored

    def get_order_recommendation(
        self,
        order_recommendation_id: str,
    ) -> dict[str, Any] | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT * FROM credit_order_recommendations
                WHERE order_recommendation_id = ?;
                """,
                (order_recommendation_id,),
            ).fetchone()
        finally:
            connection.close()
        return self._order_recommendation_from_row(row) if row else None

    def list_order_recommendations(
        self,
        customer_number: int,
    ) -> list[dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT * FROM credit_order_recommendations
                WHERE customer_number = ?
                ORDER BY created_at DESC, order_recommendation_id DESC;
                """,
                (customer_number,),
            ).fetchall()
        finally:
            connection.close()
        return [self._order_recommendation_from_row(row) for row in rows]

    def list_assessments(self, customer_number: int) -> list[dict[str, Any]]:
        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                SELECT *
                FROM credit_risk_assessments
                WHERE customer_number = ?
                ORDER BY created_at DESC, assessment_id DESC;
                """,
                (customer_number,),
            ).fetchall()
        finally:
            connection.close()
        return [self._assessment_from_row(row) for row in rows]

    def get_latest_assessment(
        self,
        customer_number: int,
    ) -> dict[str, Any] | None:
        self.initialize()
        connection = self._connection()
        try:
            row = connection.execute(
                """
                SELECT *
                FROM credit_risk_assessments
                WHERE customer_number = ?
                ORDER BY created_at DESC, assessment_id DESC
                LIMIT 1;
                """,
                (customer_number,),
            ).fetchone()
        finally:
            connection.close()
        return self._assessment_from_row(row) if row is not None else None

    def list_latest_assessments_by_customer(
        self,
        limit_per_customer: int = 2,
    ) -> list[dict[str, Any]]:
        """Return bounded assessment history for every assessed customer.

        The query intentionally starts from ETOP's local append-only
        assessments. It does not scan the ERP customer universe, so customers
        without a saved manual Credit Risk assessment are excluded by design.
        """

        if limit_per_customer < 1:
            raise ValueError("limit_per_customer must be at least 1.")

        self.initialize()
        connection = self._connection()
        try:
            rows = connection.execute(
                """
                WITH ranked_assessments AS (
                    SELECT
                        credit_risk_assessments.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY customer_number
                            ORDER BY created_at DESC, assessment_id DESC
                        ) AS assessment_rank
                    FROM credit_risk_assessments
                )
                SELECT *
                FROM ranked_assessments
                WHERE assessment_rank <= ?
                ORDER BY
                    customer_number ASC,
                    assessment_rank ASC;
                """,
                (limit_per_customer,),
            ).fetchall()
        finally:
            connection.close()

        return [self._assessment_from_row(row) for row in rows]

    @staticmethod
    def _assessment_from_row(row: sqlite3.Row) -> dict[str, Any]:
        snapshot_json = row["evidence_snapshot_json"]
        expected_hash = row["evidence_snapshot_sha256"]
        actual_hash = hashlib.sha256(
            snapshot_json.encode("utf-8")
        ).hexdigest()
        if actual_hash != expected_hash:
            raise AssessmentEvidenceIntegrityError(
                "Stored Credit Risk assessment evidence failed its "
                "SHA-256 integrity check."
            )

        return {
            "assessment_id": row["assessment_id"],
            "customer_number": row["customer_number"],
            "customer_name": row["customer_name"],
            "manual_rating": row["manual_rating"],
            "band_set_id": row["band_set_id"],
            "band_set_version": row["band_set_version"],
            "band_set_status": row["band_set_status"],
            "band": {
                "sequence": row["band_sequence"],
                "rating_min": row["band_rating_min"],
                "rating_max": row["band_rating_max"],
                "meaning": row["band_meaning"],
                "typical_response": row[
                    "band_typical_response"
                ],
            },
            "review_date": row["review_date"],
            "next_review_date": row["next_review_date"],
            "analyst_identity": row["analyst_identity"],
            "rationale": row["rationale"],
            "created_at": row["created_at"],
            "source_as_of": row["source_as_of"],
            "completeness_state": row["completeness_state"],
            "actor_identity_source": row["actor_identity_source"],
            "actor_authority_status": row["actor_authority_status"],
            "assessment_classification": row[
                "assessment_classification"
            ],
            "decision_effect": row["decision_effect"],
            "evidence_snapshot": json.loads(snapshot_json),
            "evidence_snapshot_sha256": expected_hash,
        }

    @staticmethod
    def _proposal_from_row(row: sqlite3.Row) -> dict[str, Any]:
        snapshot_json = row["evidence_snapshot_json"]
        expected_hash = row["evidence_snapshot_sha256"]
        actual_hash = hashlib.sha256(
            snapshot_json.encode("utf-8")
        ).hexdigest()
        if actual_hash != expected_hash:
            raise AssessmentEvidenceIntegrityError(
                "Stored credit-line proposal evidence failed its SHA-256 "
                "integrity check."
            )
        return {
            "proposal_id": row["proposal_id"],
            "customer_number": row["customer_number"],
            "customer_name": row["customer_name"],
            "proposed_credit_line": row["proposed_credit_line"],
            "current_credit_line": row["current_credit_line"],
            "analytical_reference_line": row[
                "analytical_reference_line"
            ],
            "review_date": row["review_date"],
            "analyst_identity": row["analyst_identity"],
            "rationale": row["rationale"],
            "created_at": row["created_at"],
            "source_as_of": row["source_as_of"],
            "actor_identity_source": row["actor_identity_source"],
            "actor_authority_status": row["actor_authority_status"],
            "proposal_classification": row[
                "proposal_classification"
            ],
            "approval_status": row["approval_status"],
            "decision_effect": row["decision_effect"],
            "erp_write": bool(row["erp_write"]),
            "evidence_snapshot": json.loads(snapshot_json),
            "evidence_snapshot_sha256": expected_hash,
        }

    @staticmethod
    def _portfolio_review_from_row(row: sqlite3.Row) -> dict[str, Any]:
        snapshot_json = row["evidence_snapshot_json"]
        expected_hash = row["evidence_snapshot_sha256"]
        actual_hash = hashlib.sha256(
            snapshot_json.encode("utf-8")
        ).hexdigest()
        if actual_hash != expected_hash:
            raise AssessmentEvidenceIntegrityError(
                "Stored credit portfolio review evidence failed its SHA-256 "
                "integrity check."
            )
        return {
            "portfolio_review_id": row["portfolio_review_id"],
            "customer_number": row["customer_number"],
            "customer_name": row["customer_name"],
            "disposition": row["disposition"],
            "reviewer_identity": row["reviewer_identity"],
            "notes": row["notes"],
            "follow_up_date": row["follow_up_date"],
            "created_at": row["created_at"],
            "assessment_id": row["assessment_id"],
            "proposal_id": row["proposal_id"],
            "actor_identity_source": row["actor_identity_source"],
            "actor_authority_status": row["actor_authority_status"],
            "review_classification": row["review_classification"],
            "decision_effect": row["decision_effect"],
            "erp_write": bool(row["erp_write"]),
            "evidence_snapshot": json.loads(snapshot_json),
            "evidence_snapshot_sha256": expected_hash,
        }

    @staticmethod
    def _order_recommendation_from_row(
        row: sqlite3.Row,
    ) -> dict[str, Any]:
        snapshot_json = row["evidence_snapshot_json"]
        expected_hash = row["evidence_snapshot_sha256"]
        actual_hash = hashlib.sha256(
            snapshot_json.encode("utf-8")
        ).hexdigest()
        if actual_hash != expected_hash:
            raise AssessmentEvidenceIntegrityError(
                "Stored credit order recommendation evidence failed its "
                "SHA-256 integrity check."
            )
        result = dict(row)
        result["erp_write"] = bool(result["erp_write"])
        result["evidence_snapshot"] = json.loads(
            result.pop("evidence_snapshot_json")
        )
        result["evidence_snapshot_sha256"] = expected_hash
        return result


credit_risk_repository = CreditRiskRepository()


def initialize_credit_risk_database() -> None:
    """Startup migration hook for the shared SQLite initialization boundary."""

    credit_risk_repository.initialize()
