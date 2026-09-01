from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from data.mysql import (
    credit_line_proposals_table,
    credit_order_recommendations_table,
    credit_portfolio_reviews_table,
    credit_risk_band_sets_table,
    credit_risk_bands_table,
    credit_risk_assessments_table,
    get_engine,
    metadata,
)


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

_CREDIT_RISK_TABLES = [
    credit_risk_band_sets_table,
    credit_risk_bands_table,
    credit_risk_assessments_table,
    credit_line_proposals_table,
    credit_portfolio_reviews_table,
    credit_order_recommendations_table,
]


class RiskBandConfigurationConflict(RuntimeError):
    """Raised when an existing version disagrees with its governed seed."""


class AssessmentEvidenceIntegrityError(RuntimeError):
    """Raised when stored evidence no longer matches its integrity marker."""


class CreditRiskRepository:
    """Local append-only persistence for Credit Risk assessments."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialization_lock = threading.Lock()

    def initialize(self) -> None:
        """Create schema and seed the initial governed draft idempotently."""

        with self._initialization_lock:
            metadata.create_all(
                self._engine, checkfirst=True, tables=_CREDIT_RISK_TABLES
            )

            with self._engine.begin() as connection:
                seeded_at = _now_iso()
                exists = connection.execute(
                    select(credit_risk_band_sets_table.c.band_set_id).where(
                        credit_risk_band_sets_table.c.band_set_id == BAND_SET_ID,
                        credit_risk_band_sets_table.c.version == BAND_SET_VERSION,
                    )
                ).first()
                if exists is None:
                    connection.execute(
                        credit_risk_band_sets_table.insert().values(
                            band_set_id=BAND_SET_ID,
                            version=BAND_SET_VERSION,
                            title=BAND_SET_TITLE,
                            status=BAND_SET_STATUS,
                            source_record=BAND_SET_SOURCE,
                            seeded_at=seeded_at,
                            automated_policy=0,
                            promotion_authority="deferred",
                            is_current=1,
                        )
                    )

                existing_sequences = {
                    row.sequence
                    for row in connection.execute(
                        select(credit_risk_bands_table.c.sequence).where(
                            credit_risk_bands_table.c.band_set_id == BAND_SET_ID,
                            credit_risk_bands_table.c.band_set_version
                            == BAND_SET_VERSION,
                        )
                    ).all()
                }
                for band in BAND_SEED:
                    sequence = band[0]
                    if sequence in existing_sequences:
                        continue
                    connection.execute(
                        credit_risk_bands_table.insert().values(
                            band_set_id=BAND_SET_ID,
                            band_set_version=BAND_SET_VERSION,
                            sequence=band[0],
                            rating_min=band[1],
                            rating_max=band[2],
                            meaning=band[3],
                            typical_response=band[4],
                        )
                    )

                self._verify_seed(connection)

    @staticmethod
    def _verify_seed(connection) -> None:
        metadata_row = connection.execute(
            select(
                credit_risk_band_sets_table.c.band_set_id,
                credit_risk_band_sets_table.c.version,
                credit_risk_band_sets_table.c.title,
                credit_risk_band_sets_table.c.status,
                credit_risk_band_sets_table.c.source_record,
                credit_risk_band_sets_table.c.automated_policy,
                credit_risk_band_sets_table.c.promotion_authority,
                credit_risk_band_sets_table.c.is_current,
            ).where(
                credit_risk_band_sets_table.c.band_set_id == BAND_SET_ID,
                credit_risk_band_sets_table.c.version == BAND_SET_VERSION,
            )
        ).first()

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
        if metadata_row is None or tuple(metadata_row) != expected_metadata:
            raise RiskBandConfigurationConflict(
                "Existing Credit Risk band-set version conflicts with the "
                "Product Owner supplied draft. No seed data was overwritten."
            )

        rows = connection.execute(
            select(
                credit_risk_bands_table.c.sequence,
                credit_risk_bands_table.c.rating_min,
                credit_risk_bands_table.c.rating_max,
                credit_risk_bands_table.c.meaning,
                credit_risk_bands_table.c.typical_response,
            )
            .where(
                credit_risk_bands_table.c.band_set_id == BAND_SET_ID,
                credit_risk_bands_table.c.band_set_version == BAND_SET_VERSION,
            )
            .order_by(credit_risk_bands_table.c.sequence)
        ).all()

        if tuple(tuple(row) for row in rows) != BAND_SEED:
            raise RiskBandConfigurationConflict(
                "Existing Credit Risk band rows conflict with the Product "
                "Owner supplied draft. No configuration was overwritten."
            )

    def get_current_band_set(self) -> dict[str, Any]:
        self.initialize()
        with self._engine.connect() as connection:
            metadata_row = connection.execute(
                select(
                    credit_risk_band_sets_table.c.band_set_id,
                    credit_risk_band_sets_table.c.version,
                    credit_risk_band_sets_table.c.title,
                    credit_risk_band_sets_table.c.status,
                    credit_risk_band_sets_table.c.source_record,
                    credit_risk_band_sets_table.c.seeded_at,
                    credit_risk_band_sets_table.c.automated_policy,
                    credit_risk_band_sets_table.c.promotion_authority,
                )
                .where(credit_risk_band_sets_table.c.is_current == 1)
                .limit(1)
            ).mappings().first()
            if metadata_row is None:
                raise RuntimeError(
                    "No current Credit Risk band set is configured."
                )

            bands = connection.execute(
                select(
                    credit_risk_bands_table.c.sequence,
                    credit_risk_bands_table.c.rating_min,
                    credit_risk_bands_table.c.rating_max,
                    credit_risk_bands_table.c.meaning,
                    credit_risk_bands_table.c.typical_response,
                )
                .where(
                    credit_risk_bands_table.c.band_set_id
                    == metadata_row["band_set_id"],
                    credit_risk_bands_table.c.band_set_version
                    == metadata_row["version"],
                )
                .order_by(credit_risk_bands_table.c.sequence)
            ).mappings().all()

        band_set = dict(metadata_row)
        band_set["automated_policy"] = bool(band_set["automated_policy"])
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

        with self._engine.begin() as connection:
            connection.execute(
                credit_risk_assessments_table.insert().values(
                    assessment_id=record["assessment_id"],
                    customer_number=record["customer_number"],
                    customer_name=record["customer_name"],
                    manual_rating=record["manual_rating"],
                    band_set_id=record["band_set_id"],
                    band_set_version=record["band_set_version"],
                    band_set_status=record["band_set_status"],
                    band_sequence=band["sequence"],
                    band_rating_min=band["rating_min"],
                    band_rating_max=band["rating_max"],
                    band_meaning=band["meaning"],
                    band_typical_response=band["typical_response"],
                    review_date=record["review_date"],
                    next_review_date=record["next_review_date"],
                    analyst_identity=record["analyst_identity"],
                    rationale=record["rationale"],
                    created_at=record["created_at"],
                    source_as_of=record["source_as_of"],
                    completeness_state=record["completeness_state"],
                    actor_identity_source=record["actor_identity_source"],
                    actor_authority_status=record["actor_authority_status"],
                    assessment_classification=record[
                        "assessment_classification"
                    ],
                    decision_effect=record["decision_effect"],
                    evidence_snapshot_json=snapshot_json,
                    evidence_snapshot_sha256=snapshot_sha256,
                )
            )

        stored = self.get_assessment(record["assessment_id"])
        if stored is None:
            raise RuntimeError("The Credit Risk assessment was not persisted.")
        return stored

    def get_assessment(self, assessment_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self._engine.connect() as connection:
            row = connection.execute(
                select(credit_risk_assessments_table).where(
                    credit_risk_assessments_table.c.assessment_id
                    == assessment_id
                )
            ).mappings().first()
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

        with self._engine.begin() as connection:
            connection.execute(
                credit_line_proposals_table.insert().values(
                    proposal_id=record["proposal_id"],
                    customer_number=record["customer_number"],
                    customer_name=record["customer_name"],
                    proposed_credit_line=record["proposed_credit_line"],
                    current_credit_line=record["current_credit_line"],
                    analytical_reference_line=record[
                        "analytical_reference_line"
                    ],
                    review_date=record["review_date"],
                    analyst_identity=record["analyst_identity"],
                    rationale=record["rationale"],
                    created_at=record["created_at"],
                    source_as_of=record["source_as_of"],
                    actor_identity_source=record["actor_identity_source"],
                    actor_authority_status=record["actor_authority_status"],
                    proposal_classification=record["proposal_classification"],
                    approval_status=record["approval_status"],
                    decision_effect=record["decision_effect"],
                    erp_write=0,
                    evidence_snapshot_json=snapshot_json,
                    evidence_snapshot_sha256=snapshot_sha256,
                )
            )

        stored = self.get_credit_line_proposal(record["proposal_id"])
        if stored is None:
            raise RuntimeError("The credit-line proposal was not persisted.")
        return stored

    def get_credit_line_proposal(
        self,
        proposal_id: str,
    ) -> dict[str, Any] | None:
        self.initialize()
        with self._engine.connect() as connection:
            row = connection.execute(
                select(credit_line_proposals_table).where(
                    credit_line_proposals_table.c.proposal_id == proposal_id
                )
            ).mappings().first()
        return self._proposal_from_row(row) if row is not None else None

    def list_credit_line_proposals(
        self,
        customer_number: int,
    ) -> list[dict[str, Any]]:
        self.initialize()
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(credit_line_proposals_table)
                .where(
                    credit_line_proposals_table.c.customer_number
                    == customer_number
                )
                .order_by(
                    credit_line_proposals_table.c.created_at.desc(),
                    credit_line_proposals_table.c.proposal_id.desc(),
                )
            ).mappings().all()
        return [self._proposal_from_row(row) for row in rows]

    def get_latest_credit_line_proposal(
        self,
        customer_number: int,
    ) -> dict[str, Any] | None:
        self.initialize()
        with self._engine.connect() as connection:
            row = connection.execute(
                select(credit_line_proposals_table)
                .where(
                    credit_line_proposals_table.c.customer_number
                    == customer_number
                )
                .order_by(
                    credit_line_proposals_table.c.created_at.desc(),
                    credit_line_proposals_table.c.proposal_id.desc(),
                )
                .limit(1)
            ).mappings().first()
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
        with self._engine.begin() as connection:
            connection.execute(
                credit_portfolio_reviews_table.insert().values(
                    portfolio_review_id=record["portfolio_review_id"],
                    customer_number=record["customer_number"],
                    customer_name=record["customer_name"],
                    disposition=record["disposition"],
                    reviewer_identity=record["reviewer_identity"],
                    notes=record["notes"],
                    follow_up_date=record["follow_up_date"],
                    created_at=record["created_at"],
                    assessment_id=record["assessment_id"],
                    proposal_id=record["proposal_id"],
                    actor_identity_source=record["actor_identity_source"],
                    actor_authority_status=record["actor_authority_status"],
                    review_classification=record["review_classification"],
                    decision_effect=record["decision_effect"],
                    erp_write=0,
                    evidence_snapshot_json=snapshot_json,
                    evidence_snapshot_sha256=snapshot_sha256,
                )
            )
        stored = self.get_portfolio_review(record["portfolio_review_id"])
        if stored is None:
            raise RuntimeError("The credit portfolio review was not persisted.")
        return stored

    def get_portfolio_review(
        self,
        portfolio_review_id: str,
    ) -> dict[str, Any] | None:
        self.initialize()
        with self._engine.connect() as connection:
            row = connection.execute(
                select(credit_portfolio_reviews_table).where(
                    credit_portfolio_reviews_table.c.portfolio_review_id
                    == portfolio_review_id
                )
            ).mappings().first()
        return self._portfolio_review_from_row(row) if row is not None else None

    def list_portfolio_reviews(
        self,
        customer_number: int,
    ) -> list[dict[str, Any]]:
        self.initialize()
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(credit_portfolio_reviews_table)
                .where(
                    credit_portfolio_reviews_table.c.customer_number
                    == customer_number
                )
                .order_by(
                    credit_portfolio_reviews_table.c.created_at.desc(),
                    credit_portfolio_reviews_table.c.portfolio_review_id.desc(),
                )
            ).mappings().all()
        return [self._portfolio_review_from_row(row) for row in rows]

    def get_latest_portfolio_review(
        self,
        customer_number: int,
    ) -> dict[str, Any] | None:
        self.initialize()
        with self._engine.connect() as connection:
            row = connection.execute(
                select(credit_portfolio_reviews_table)
                .where(
                    credit_portfolio_reviews_table.c.customer_number
                    == customer_number
                )
                .order_by(
                    credit_portfolio_reviews_table.c.created_at.desc(),
                    credit_portfolio_reviews_table.c.portfolio_review_id.desc(),
                )
                .limit(1)
            ).mappings().first()
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
        with self._engine.begin() as connection:
            connection.execute(
                credit_order_recommendations_table.insert().values(
                    order_recommendation_id=record["order_recommendation_id"],
                    customer_number=record["customer_number"],
                    customer_name=record["customer_name"],
                    contemplated_order_amount=record[
                        "contemplated_order_amount"
                    ],
                    order_reference=record["order_reference"],
                    disposition=record["disposition"],
                    analyst_identity=record["analyst_identity"],
                    rationale=record["rationale"],
                    created_at=record["created_at"],
                    source_as_of=record["source_as_of"],
                    assessment_id=record["assessment_id"],
                    proposal_id=record["proposal_id"],
                    current_credit_line=record["current_credit_line"],
                    current_partial_exposure=record[
                        "current_partial_exposure"
                    ],
                    projected_partial_exposure=record[
                        "projected_partial_exposure"
                    ],
                    projected_partial_available_credit=record[
                        "projected_partial_available_credit"
                    ],
                    projected_partial_over_line_amount=record[
                        "projected_partial_over_line_amount"
                    ],
                    actor_identity_source=record["actor_identity_source"],
                    actor_authority_status=record["actor_authority_status"],
                    recommendation_classification=record[
                        "recommendation_classification"
                    ],
                    decision_status=record["decision_status"],
                    decision_effect=record["decision_effect"],
                    order_effect=record["order_effect"],
                    erp_write=0,
                    evidence_snapshot_json=snapshot_json,
                    evidence_snapshot_sha256=snapshot_sha256,
                )
            )
        stored = self.get_order_recommendation(
            record["order_recommendation_id"]
        )
        if stored is None:
            raise RuntimeError(
                "The credit order recommendation was not persisted."
            )
        return stored

    def get_order_recommendation(
        self,
        order_recommendation_id: str,
    ) -> dict[str, Any] | None:
        self.initialize()
        with self._engine.connect() as connection:
            row = connection.execute(
                select(credit_order_recommendations_table).where(
                    credit_order_recommendations_table.c.order_recommendation_id
                    == order_recommendation_id
                )
            ).mappings().first()
        return self._order_recommendation_from_row(row) if row else None

    def list_order_recommendations(
        self,
        customer_number: int,
    ) -> list[dict[str, Any]]:
        self.initialize()
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(credit_order_recommendations_table)
                .where(
                    credit_order_recommendations_table.c.customer_number
                    == customer_number
                )
                .order_by(
                    credit_order_recommendations_table.c.created_at.desc(),
                    credit_order_recommendations_table.c.order_recommendation_id.desc(),
                )
            ).mappings().all()
        return [self._order_recommendation_from_row(row) for row in rows]

    def list_assessments(self, customer_number: int) -> list[dict[str, Any]]:
        self.initialize()
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(credit_risk_assessments_table)
                .where(
                    credit_risk_assessments_table.c.customer_number
                    == customer_number
                )
                .order_by(
                    credit_risk_assessments_table.c.created_at.desc(),
                    credit_risk_assessments_table.c.assessment_id.desc(),
                )
            ).mappings().all()
        return [self._assessment_from_row(row) for row in rows]

    def get_latest_assessment(
        self,
        customer_number: int,
    ) -> dict[str, Any] | None:
        self.initialize()
        with self._engine.connect() as connection:
            row = connection.execute(
                select(credit_risk_assessments_table)
                .where(
                    credit_risk_assessments_table.c.customer_number
                    == customer_number
                )
                .order_by(
                    credit_risk_assessments_table.c.created_at.desc(),
                    credit_risk_assessments_table.c.assessment_id.desc(),
                )
                .limit(1)
            ).mappings().first()
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
        table = credit_risk_assessments_table
        assessment_rank = (
            func.row_number()
            .over(
                partition_by=table.c.customer_number,
                order_by=(table.c.created_at.desc(), table.c.assessment_id.desc()),
            )
            .label("assessment_rank")
        )
        ranked = select(table, assessment_rank).subquery()
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(ranked)
                .where(ranked.c.assessment_rank <= limit_per_customer)
                .order_by(ranked.c.customer_number.asc(), ranked.c.assessment_rank.asc())
            ).mappings().all()

        return [self._assessment_from_row(row) for row in rows]

    @staticmethod
    def _assessment_from_row(row) -> dict[str, Any]:
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
                "typical_response": row["band_typical_response"],
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
            "assessment_classification": row["assessment_classification"],
            "decision_effect": row["decision_effect"],
            "evidence_snapshot": json.loads(snapshot_json),
            "evidence_snapshot_sha256": expected_hash,
        }

    @staticmethod
    def _proposal_from_row(row) -> dict[str, Any]:
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
            "analytical_reference_line": row["analytical_reference_line"],
            "review_date": row["review_date"],
            "analyst_identity": row["analyst_identity"],
            "rationale": row["rationale"],
            "created_at": row["created_at"],
            "source_as_of": row["source_as_of"],
            "actor_identity_source": row["actor_identity_source"],
            "actor_authority_status": row["actor_authority_status"],
            "proposal_classification": row["proposal_classification"],
            "approval_status": row["approval_status"],
            "decision_effect": row["decision_effect"],
            "erp_write": bool(row["erp_write"]),
            "evidence_snapshot": json.loads(snapshot_json),
            "evidence_snapshot_sha256": expected_hash,
        }

    @staticmethod
    def _portfolio_review_from_row(row) -> dict[str, Any]:
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
    def _order_recommendation_from_row(row) -> dict[str, Any]:
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
        result = {k: v for k, v in dict(row).items() if k != "assessment_rank"}
        result["erp_write"] = bool(result["erp_write"])
        result["evidence_snapshot"] = json.loads(
            result.pop("evidence_snapshot_json")
        )
        result["evidence_snapshot_sha256"] = expected_hash
        return result


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


credit_risk_repository = CreditRiskRepository()


def initialize_credit_risk_database() -> None:
    """Startup migration hook for the shared SQLite initialization boundary."""

    credit_risk_repository.initialize()
