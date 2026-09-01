"""Shared SQLAlchemy Core engine/metadata for the app's own MySQL database
(the `etop` schema on mysql-dev.kmdevlab.com), as opposed to `core/database.py`
which is the separate, read-only connection to the MaddenCo ERP MySQL box.

Every module being converted off SQLite defines its tables against the one
`metadata` object here so that `metadata.create_all()` can create every
table in one pass, in foreign-key-safe order - this matters once modules
start taking real FKs into another module's tables (e.g. financial_close
into workflow_foundation's wf_user_accounts).
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Computed,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects.mysql import LONGBLOB, LONGTEXT
from sqlalchemy.engine import Engine

# MySQL's plain BLOB caps at 64KB - far too small for a scanned PDF credit
# application. LONGBLOB (up to 4GB) is used on MySQL; SQLite's BLOB affinity
# has no such size cap, so the generic type is fine there.
_DOCUMENT_BLOB_TYPE = LargeBinary().with_variant(LONGBLOB(), "mysql")

# MySQL's plain TEXT also caps at 64KB - too small for a Payment Notes run's
# full canonical payload (bank-statement rows plus ERP evidence can run into
# the megabytes). LONGTEXT (up to 4GB) is used on MySQL; SQLite's TEXT
# affinity has no such size cap, so the generic type is fine there.
_LARGE_JSON_TYPE = Text().with_variant(LONGTEXT(), "mysql")

load_dotenv()


metadata = MetaData()

# SQLite's rowid-alias autoincrement only activates for a column typed
# exactly INTEGER PRIMARY KEY - BIGINT (or any other affinity) makes it a
# regular column with no auto-generation, so these three "sequence"
# surrogate keys need INTEGER on SQLite and BIGINT (more headroom) on MySQL.
_SEQUENCE_TYPE = Integer().with_variant(BigInteger(), "mysql")


# --- automations module -----------------------------------------------

automations_table = Table(
    "automations",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("name", String(255), nullable=False),
    Column("status", String(32), nullable=False, server_default="draft"),
    Column("source_type", String(32), nullable=False),
    Column("frequency", String(32), nullable=False, server_default="manual"),
    Column(
        "timezone",
        String(64),
        nullable=False,
        server_default="America/New_York",
    ),
    Column("next_run_at", String(64), nullable=True),
    Column("last_run_at", String(64), nullable=True),
    Column("last_run_status", String(32), nullable=True),
    Column("definition_json", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    Index("idx_automations_due", "status", "next_run_at"),
    Index("idx_automations_updated", "updated_at"),
)

automation_executions_table = Table(
    "automation_executions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column(
        "automation_id",
        String(64),
        ForeignKey("automations.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("automation_name", String(255), nullable=False),
    Column("status", String(32), nullable=False),
    Column("started_at", String(64), nullable=False),
    Column("completed_at", String(64), nullable=True),
    Column("duration_ms", Integer, nullable=True),
    Column("row_count", Integer, nullable=True),
    Column(
        "output_file_name",
        String(512),
        nullable=False,
        server_default="",
    ),
    Column(
        "output_file_path",
        String(1024),
        nullable=False,
        server_default="",
    ),
    Column("message", Text, nullable=False),
    Column("error_details", Text, nullable=False),
    Column("triggered_by", String(64), nullable=False),
    Index("idx_automation_executions_recent", "started_at"),
    Index("idx_automation_executions_automation", "automation_id", "started_at"),
)


# --- job_queue module ----------------------------------------------------

job_queue_jobs_table = Table(
    "job_queue_jobs",
    metadata,
    Column("job_id", String(64), primary_key=True),
    Column("job_type", String(64), nullable=False),
    Column("title", String(255), nullable=False),
    Column("status", String(16), nullable=False),
    Column("created_by", String(64), nullable=True),
    Column("created_at", String(64), nullable=False),
    Column("started_at", String(64), nullable=True),
    Column("completed_at", String(64), nullable=True),
    Column("message", Text, nullable=True),
    Column("result_module", String(64), nullable=True),
    Column("result_reference", String(255), nullable=True),
    Column("acknowledged_at", String(64), nullable=True),
    CheckConstraint("status IN ('queued', 'running', 'completed', 'failed')"),
    Index("idx_job_queue_jobs_status", "status", "created_at"),
    Index("idx_job_queue_jobs_created_at", "created_at"),
)


# --- reports module --------------------------------------------------------

reports_table = Table(
    "reports",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("name", String(255), nullable=False),
    # MySQL rejects a literal DEFAULT on TEXT columns - the app always
    # supplies description/parameters_json explicitly on insert anyway.
    Column("description", Text, nullable=False),
    Column("category", String(64), nullable=False, server_default="General"),
    Column("sql_text", Text, nullable=False),
    Column("database_name", String(64), nullable=False, server_default="ERP"),
    Column("output_format", String(16), nullable=False, server_default="xlsx"),
    Column("parameters_json", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    Index("idx_reports_name", "name"),
    Index("idx_reports_updated_at", "updated_at"),
)


# --- notes modules (8 near-identical append-only evidence tables) ---------
#
# Same template repeated per module: one table scoped by that module's
# business key, `evidence_snapshot_json` + a sha256 integrity column,
# append-only (enforced in the repository layer - see the workflow_foundation
# comment above on why no DB trigger). CHECK constraints pinning the
# governance columns to fixed literal values carry over unchanged (MySQL 8
# enforces CHECK natively).

ar_collections_notes_table = Table(
    "ar_collections_notes",
    metadata,
    Column("note_id", String(64), primary_key=True),
    Column("customer_number", Integer, nullable=False),
    Column("customer_name", String(255), nullable=False),
    Column("author_identity", String(255), nullable=False),
    Column("note", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("source_as_of", String(64), nullable=False),
    Column("actor_identity_source", String(32), nullable=False),
    Column("actor_authority_status", String(64), nullable=False),
    Column("note_classification", String(64), nullable=False),
    Column("decision_effect", String(16), nullable=False),
    Column("erp_write", Integer, nullable=False, server_default="0"),
    Column("evidence_snapshot_json", Text, nullable=False),
    Column("evidence_snapshot_sha256", String(64), nullable=False),
    CheckConstraint("actor_identity_source = 'operator_supplied'"),
    CheckConstraint(
        "actor_authority_status = 'not_independently_verified'"
    ),
    CheckConstraint(
        "note_classification = 'professional_workflow_metadata'"
    ),
    CheckConstraint("decision_effect = 'none'"),
    CheckConstraint("erp_write = 0"),
    CheckConstraint("length(evidence_snapshot_sha256) = 64"),
    Index(
        "idx_ar_collections_notes_customer_time",
        "customer_number",
        "created_at",
        "note_id",
    ),
)

general_ledger_notes_table = Table(
    "general_ledger_notes",
    metadata,
    Column("note_id", String(64), primary_key=True),
    Column("account_number", Integer, nullable=False),
    Column("division", Integer, nullable=False),
    Column("department", Integer, nullable=False),
    Column("period", Integer, nullable=True),
    Column("year", Integer, nullable=True),
    Column("account_description", String(255), nullable=False),
    Column("author_identity", String(255), nullable=False),
    Column("note", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("source_as_of", String(64), nullable=False),
    Column("actor_identity_source", String(32), nullable=False),
    Column("actor_authority_status", String(64), nullable=False),
    Column("note_classification", String(64), nullable=False),
    Column("decision_effect", String(16), nullable=False),
    Column("erp_write", Integer, nullable=False, server_default="0"),
    Column("evidence_snapshot_json", Text, nullable=False),
    Column("evidence_snapshot_sha256", String(64), nullable=False),
    CheckConstraint("actor_identity_source = 'operator_supplied'"),
    CheckConstraint(
        "actor_authority_status = 'not_independently_verified'"
    ),
    CheckConstraint(
        "note_classification = 'professional_workflow_metadata'"
    ),
    CheckConstraint("decision_effect = 'none'"),
    CheckConstraint("erp_write = 0"),
    CheckConstraint("length(evidence_snapshot_sha256) = 64"),
    Index(
        "idx_gl_notes_account_time", "account_number", "created_at", "note_id"
    ),
)

tax_compliance_notes_table = Table(
    "tax_compliance_notes",
    metadata,
    Column("note_id", String(64), primary_key=True),
    Column("customer_number", Integer, nullable=False),
    Column("customer_name", String(255), nullable=False),
    Column("author_identity", String(255), nullable=False),
    Column("note", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("source_as_of", String(64), nullable=False),
    Column("actor_identity_source", String(32), nullable=False),
    Column("actor_authority_status", String(64), nullable=False),
    Column("note_classification", String(64), nullable=False),
    Column("decision_effect", String(16), nullable=False),
    Column("erp_write", Integer, nullable=False, server_default="0"),
    Column("evidence_snapshot_json", Text, nullable=False),
    Column("evidence_snapshot_sha256", String(64), nullable=False),
    CheckConstraint("actor_identity_source = 'operator_supplied'"),
    CheckConstraint(
        "actor_authority_status = 'not_independently_verified'"
    ),
    CheckConstraint(
        "note_classification = 'professional_workflow_metadata'"
    ),
    CheckConstraint("decision_effect = 'none'"),
    CheckConstraint("erp_write = 0"),
    CheckConstraint("length(evidence_snapshot_sha256) = 64"),
    Index(
        "idx_tax_compliance_notes_cust_time",
        "customer_number",
        "created_at",
        "note_id",
    ),
)

pricing_notes_table = Table(
    "pricing_notes",
    metadata,
    Column("note_id", String(64), primary_key=True),
    Column("customer_number", Integer, nullable=False),
    Column("vendor_code", String(64), nullable=True),
    Column("product_class", String(64), nullable=True),
    Column("product_number", String(64), nullable=True),
    Column("product_type", String(64), nullable=True),
    Column("author_identity", String(255), nullable=False),
    Column("note", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("source_as_of", String(64), nullable=False),
    Column("matched_discount_count", Integer, nullable=False),
    Column("actor_identity_source", String(32), nullable=False),
    Column("actor_authority_status", String(64), nullable=False),
    Column("note_classification", String(64), nullable=False),
    Column("decision_effect", String(16), nullable=False),
    Column("erp_write", Integer, nullable=False, server_default="0"),
    Column("evidence_snapshot_json", Text, nullable=False),
    Column("evidence_snapshot_sha256", String(64), nullable=False),
    CheckConstraint("actor_identity_source = 'operator_supplied'"),
    CheckConstraint(
        "actor_authority_status = 'not_independently_verified'"
    ),
    CheckConstraint(
        "note_classification = 'professional_workflow_metadata'"
    ),
    CheckConstraint("decision_effect = 'none'"),
    CheckConstraint("erp_write = 0"),
    CheckConstraint("length(evidence_snapshot_sha256) = 64"),
    Index(
        "idx_pricing_notes_customer_time",
        "customer_number",
        "created_at",
        "note_id",
    ),
)

order_notes_table = Table(
    "order_notes",
    metadata,
    Column("note_id", String(64), primary_key=True),
    Column("invoice_number", Integer, nullable=False),
    Column("customer_number", Integer, nullable=True),
    # MySQL rejects a literal DEFAULT on TEXT - use VARCHAR here since this
    # column is always a short name, matching the app's own '' default.
    Column("customer_name", String(255), nullable=False, server_default=""),
    Column("author_identity", String(255), nullable=False),
    Column("note", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("source_as_of", String(64), nullable=False),
    Column("actor_identity_source", String(32), nullable=False),
    Column("actor_authority_status", String(64), nullable=False),
    Column("note_classification", String(64), nullable=False),
    Column("decision_effect", String(16), nullable=False),
    Column("erp_write", Integer, nullable=False, server_default="0"),
    Column("evidence_snapshot_json", Text, nullable=False),
    Column("evidence_snapshot_sha256", String(64), nullable=False),
    CheckConstraint("actor_identity_source = 'operator_supplied'"),
    CheckConstraint(
        "actor_authority_status = 'not_independently_verified'"
    ),
    CheckConstraint(
        "note_classification = 'professional_workflow_metadata'"
    ),
    CheckConstraint("decision_effect = 'none'"),
    CheckConstraint("erp_write = 0"),
    CheckConstraint("length(evidence_snapshot_sha256) = 64"),
    Index(
        "idx_order_notes_invoice_time",
        "invoice_number",
        "created_at",
        "note_id",
    ),
)

logistics_notes_table = Table(
    "logistics_notes",
    metadata,
    Column("note_id", String(64), primary_key=True),
    Column("route_code", String(64), nullable=False),
    Column("warehouse_number", Integer, nullable=True),
    Column("author_identity", String(255), nullable=False),
    Column("note", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("source_as_of", String(64), nullable=False),
    Column("actor_identity_source", String(32), nullable=False),
    Column("actor_authority_status", String(64), nullable=False),
    Column("note_classification", String(64), nullable=False),
    Column("decision_effect", String(16), nullable=False),
    Column("erp_write", Integer, nullable=False, server_default="0"),
    Column("evidence_snapshot_json", Text, nullable=False),
    Column("evidence_snapshot_sha256", String(64), nullable=False),
    CheckConstraint("actor_identity_source = 'operator_supplied'"),
    CheckConstraint(
        "actor_authority_status = 'not_independently_verified'"
    ),
    CheckConstraint(
        "note_classification = 'professional_workflow_metadata'"
    ),
    CheckConstraint("decision_effect = 'none'"),
    CheckConstraint("erp_write = 0"),
    CheckConstraint("length(evidence_snapshot_sha256) = 64"),
    Index(
        "idx_logistics_notes_route_time", "route_code", "created_at", "note_id"
    ),
)

inventory_notes_table = Table(
    "inventory_notes",
    metadata,
    Column("note_id", String(64), primary_key=True),
    Column("product_number", String(64), nullable=False),
    Column("product_description", String(255), nullable=False),
    Column("author_identity", String(255), nullable=False),
    Column("note", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("source_as_of", String(64), nullable=False),
    Column("actor_identity_source", String(32), nullable=False),
    Column("actor_authority_status", String(64), nullable=False),
    Column("note_classification", String(64), nullable=False),
    Column("decision_effect", String(16), nullable=False),
    Column("erp_write", Integer, nullable=False, server_default="0"),
    Column("evidence_snapshot_json", Text, nullable=False),
    Column("evidence_snapshot_sha256", String(64), nullable=False),
    CheckConstraint("actor_identity_source = 'operator_supplied'"),
    CheckConstraint(
        "actor_authority_status = 'not_independently_verified'"
    ),
    CheckConstraint(
        "note_classification = 'professional_workflow_metadata'"
    ),
    CheckConstraint("decision_effect = 'none'"),
    CheckConstraint("erp_write = 0"),
    CheckConstraint("length(evidence_snapshot_sha256) = 64"),
    Index(
        "idx_inventory_notes_product_time",
        "product_number",
        "created_at",
        "note_id",
    ),
)

vendor_notes_table = Table(
    "vendor_notes",
    metadata,
    Column("note_id", String(64), primary_key=True),
    Column("vendor_number", Integer, nullable=False),
    Column("vendor_name", String(255), nullable=False),
    Column("author_identity", String(255), nullable=False),
    Column("note", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("source_as_of", String(64), nullable=False),
    Column("actor_identity_source", String(32), nullable=False),
    Column("actor_authority_status", String(64), nullable=False),
    Column("note_classification", String(64), nullable=False),
    Column("decision_effect", String(16), nullable=False),
    Column("erp_write", Integer, nullable=False, server_default="0"),
    Column("evidence_snapshot_json", Text, nullable=False),
    Column("evidence_snapshot_sha256", String(64), nullable=False),
    CheckConstraint("actor_identity_source = 'operator_supplied'"),
    CheckConstraint(
        "actor_authority_status = 'not_independently_verified'"
    ),
    CheckConstraint(
        "note_classification = 'professional_workflow_metadata'"
    ),
    CheckConstraint("decision_effect = 'none'"),
    CheckConstraint("erp_write = 0"),
    CheckConstraint("length(evidence_snapshot_sha256) = 64"),
    Index(
        "idx_vendor_notes_vendor_time", "vendor_number", "created_at", "note_id"
    ),
)


# --- cash_flow_forecasting module ------------------------------------------
#
# Three of these four tables are append-only (enforced by convention, same
# as elsewhere); `cash_flow_ap_due_date_cache` is a plain mutable cache with
# no evidentiary purpose of its own (refreshed via delete-then-reinsert).

cash_flow_forecast_snapshots_table = Table(
    "cash_flow_forecast_snapshots",
    metadata,
    Column("snapshot_id", String(64), primary_key=True),
    Column("as_of", String(64), nullable=False),
    Column("generated_at", String(64), nullable=False),
    Column("horizon_weeks", Integer, nullable=False),
    Column("starting_balance_business_day", String(64), nullable=True),
    Column("starting_balance_amount", Float, nullable=True),
    Column("loc_balance", Float, nullable=True),
    Column("loc_available", Float, nullable=True),
    Column("evidence_snapshot_json", Text, nullable=False),
    Column("evidence_snapshot_sha256", String(64), nullable=False),
    CheckConstraint("length(evidence_snapshot_sha256) = 64"),
    Index("idx_cff_snapshots_as_of", "as_of", "snapshot_id"),
)

cash_flow_forecast_weeks_table = Table(
    "cash_flow_forecast_weeks",
    metadata,
    Column("week_id", String(64), primary_key=True),
    Column(
        "snapshot_id",
        String(64),
        ForeignKey("cash_flow_forecast_snapshots.snapshot_id"),
        nullable=False,
    ),
    Column("week_index", Integer, nullable=False),
    Column("week_start", String(64), nullable=False),
    Column("week_end", String(64), nullable=False),
    Column("projected_ar", Float, nullable=False),
    Column("projected_ap", Float, nullable=True),
    Column("projected_ap_on_hold", Float, nullable=True),
    Column("projected_other", Float, nullable=False),
    Column("projected_ending_balance", Float, nullable=True),
    Index("idx_cff_weeks_snapshot", "snapshot_id", "week_index"),
)

cash_flow_forecast_actuals_table = Table(
    "cash_flow_forecast_actuals",
    metadata,
    Column("actual_id", String(64), primary_key=True),
    Column("week_start", String(64), nullable=False),
    Column("week_end", String(64), nullable=False),
    Column("actual_ar", Float, nullable=False),
    Column("actual_ap", Float, nullable=False),
    Column("actual_other", Float, nullable=False),
    Column("actual_ending_balance", Float, nullable=True),
    Column("projected_ar", Float, nullable=True),
    Column("projected_ap", Float, nullable=True),
    Column("projected_other", Float, nullable=True),
    Column("projected_ending_balance", Float, nullable=True),
    Column("recorded_at", String(64), nullable=False),
    Column("evidence_snapshot_json", Text, nullable=False),
    Column("evidence_snapshot_sha256", String(64), nullable=False),
    CheckConstraint("length(evidence_snapshot_sha256) = 64"),
    Index("idx_cff_actuals_week", "week_start", "week_end", "recorded_at"),
)

cash_flow_ap_due_date_cache_table = Table(
    "cash_flow_ap_due_date_cache",
    metadata,
    Column("week_start", String(64), primary_key=True),
    Column("week_end", String(64), nullable=False),
    Column("open_amount", Float, nullable=False),
    Column("open_on_hold_amount", Float, nullable=False),
    Column("refreshed_at", String(64), nullable=False),
)


# --- credit_risk module -----------------------------------------------
#
# `credit_risk_band_sets.is_current` had a SQLite partial unique index
# (`WHERE is_current = 1`) enforcing "at most one current band set across
# the whole table". Same generated-column technique as
# wf_user_invitations: a column that's only non-NULL when is_current=1,
# with a UNIQUE index on it.

credit_risk_band_sets_table = Table(
    "credit_risk_band_sets",
    metadata,
    Column("band_set_id", String(64), nullable=False),
    Column("version", String(32), nullable=False),
    Column("title", String(255), nullable=False),
    Column("status", String(64), nullable=False),
    Column("source_record", String(255), nullable=False),
    Column("seeded_at", String(64), nullable=False),
    Column("automated_policy", Integer, nullable=False, server_default="0"),
    Column(
        "promotion_authority",
        String(32),
        nullable=False,
        server_default="deferred",
    ),
    Column("is_current", Integer, nullable=False, server_default="0"),
    Column(
        "current_singleton",
        Integer,
        Computed("CASE WHEN is_current = 1 THEN 1 ELSE NULL END", persisted=True),
    ),
    PrimaryKeyConstraint("band_set_id", "version"),
    CheckConstraint("automated_policy = 0"),
    CheckConstraint("promotion_authority = 'deferred'"),
    CheckConstraint("is_current IN (0, 1)"),
    Index("idx_credit_risk_one_current_band_set", "current_singleton", unique=True),
)

credit_risk_bands_table = Table(
    "credit_risk_bands",
    metadata,
    Column("band_set_id", String(64), nullable=False),
    Column("band_set_version", String(32), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("rating_min", Integer, nullable=False),
    Column("rating_max", Integer, nullable=False),
    Column("meaning", String(255), nullable=False),
    Column("typical_response", String(255), nullable=False),
    PrimaryKeyConstraint("band_set_id", "band_set_version", "sequence"),
    ForeignKeyConstraint(
        ["band_set_id", "band_set_version"],
        ["credit_risk_band_sets.band_set_id", "credit_risk_band_sets.version"],
    ),
    CheckConstraint("rating_min BETWEEN 1 AND 10"),
    CheckConstraint("rating_max BETWEEN 1 AND 10"),
    Index(
        "idx_credit_risk_band_rating",
        "band_set_id",
        "band_set_version",
        "rating_min",
        "rating_max",
    ),
)

credit_risk_assessments_table = Table(
    "credit_risk_assessments",
    metadata,
    Column("assessment_id", String(64), primary_key=True),
    Column("customer_number", Integer, nullable=False),
    Column("customer_name", String(255), nullable=False),
    Column("manual_rating", Integer, nullable=False),
    Column("band_set_id", String(64), nullable=False),
    Column("band_set_version", String(32), nullable=False),
    Column("band_set_status", String(64), nullable=False),
    Column("band_sequence", Integer, nullable=False),
    Column("band_rating_min", Integer, nullable=False),
    Column("band_rating_max", Integer, nullable=False),
    Column("band_meaning", String(255), nullable=False),
    Column("band_typical_response", String(255), nullable=False),
    Column("review_date", String(64), nullable=False),
    Column("next_review_date", String(64), nullable=False),
    Column("analyst_identity", String(255), nullable=False),
    Column("rationale", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("source_as_of", String(64), nullable=False),
    Column("completeness_state", String(32), nullable=False),
    Column("actor_identity_source", String(32), nullable=False),
    Column("actor_authority_status", String(64), nullable=False),
    Column("assessment_classification", String(64), nullable=False),
    Column("decision_effect", String(16), nullable=False),
    Column("evidence_snapshot_json", Text, nullable=False),
    Column("evidence_snapshot_sha256", String(64), nullable=False),
    ForeignKeyConstraint(
        ["band_set_id", "band_set_version"],
        ["credit_risk_band_sets.band_set_id", "credit_risk_band_sets.version"],
    ),
    CheckConstraint("manual_rating BETWEEN 1 AND 10"),
    CheckConstraint("completeness_state = 'partial'"),
    CheckConstraint("actor_identity_source = 'operator_supplied'"),
    CheckConstraint("actor_authority_status = 'not_independently_verified'"),
    CheckConstraint("assessment_classification = 'professional_judgment'"),
    CheckConstraint("decision_effect = 'none'"),
    CheckConstraint("length(evidence_snapshot_sha256) = 64"),
    Index(
        "idx_credit_risk_assessments_customer_time",
        "customer_number",
        "created_at",
        "assessment_id",
    ),
)

credit_line_proposals_table = Table(
    "credit_line_proposals",
    metadata,
    Column("proposal_id", String(64), primary_key=True),
    Column("customer_number", Integer, nullable=False),
    Column("customer_name", String(255), nullable=False),
    Column("proposed_credit_line", Float, nullable=False),
    Column("current_credit_line", Float, nullable=False),
    Column("analytical_reference_line", Float, nullable=True),
    Column("review_date", String(64), nullable=False),
    Column("analyst_identity", String(255), nullable=False),
    Column("rationale", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("source_as_of", String(64), nullable=False),
    Column("actor_identity_source", String(32), nullable=False),
    Column("actor_authority_status", String(64), nullable=False),
    Column("proposal_classification", String(64), nullable=False),
    Column("approval_status", String(64), nullable=False),
    Column("decision_effect", String(16), nullable=False),
    Column("erp_write", Integer, nullable=False, server_default="0"),
    Column("evidence_snapshot_json", Text, nullable=False),
    Column("evidence_snapshot_sha256", String(64), nullable=False),
    CheckConstraint("proposed_credit_line >= 0"),
    CheckConstraint("actor_identity_source = 'operator_supplied'"),
    CheckConstraint("actor_authority_status = 'not_independently_verified'"),
    CheckConstraint(
        "proposal_classification = 'professional_recommendation'"
    ),
    CheckConstraint(
        "approval_status = 'not_submitted_to_governed_approval'"
    ),
    CheckConstraint("decision_effect = 'none'"),
    CheckConstraint("erp_write = 0"),
    CheckConstraint("length(evidence_snapshot_sha256) = 64"),
    Index(
        "idx_credit_line_proposals_customer_time",
        "customer_number",
        "created_at",
        "proposal_id",
    ),
)

credit_portfolio_reviews_table = Table(
    "credit_portfolio_reviews",
    metadata,
    Column("portfolio_review_id", String(64), primary_key=True),
    Column("customer_number", Integer, nullable=False),
    Column("customer_name", String(255), nullable=False),
    Column("disposition", String(64), nullable=False),
    Column("reviewer_identity", String(255), nullable=False),
    Column("notes", Text, nullable=False),
    Column("follow_up_date", String(64), nullable=True),
    Column("created_at", String(64), nullable=False),
    Column(
        "assessment_id",
        String(64),
        ForeignKey("credit_risk_assessments.assessment_id"),
        nullable=False,
    ),
    Column(
        "proposal_id",
        String(64),
        ForeignKey("credit_line_proposals.proposal_id"),
        nullable=True,
    ),
    Column("actor_identity_source", String(32), nullable=False),
    Column("actor_authority_status", String(64), nullable=False),
    Column("review_classification", String(64), nullable=False),
    Column("decision_effect", String(16), nullable=False),
    Column("erp_write", Integer, nullable=False, server_default="0"),
    Column("evidence_snapshot_json", Text, nullable=False),
    Column("evidence_snapshot_sha256", String(64), nullable=False),
    CheckConstraint(
        "disposition IN "
        "('reviewed_no_change', 'reassessment_needed', "
        "'credit_line_analysis_needed', 'information_requested')"
    ),
    CheckConstraint("actor_identity_source = 'operator_supplied'"),
    CheckConstraint("actor_authority_status = 'not_independently_verified'"),
    CheckConstraint(
        "review_classification = 'professional_workflow_metadata'"
    ),
    CheckConstraint("decision_effect = 'none'"),
    CheckConstraint("erp_write = 0"),
    CheckConstraint("length(evidence_snapshot_sha256) = 64"),
    Index(
        "idx_credit_portfolio_reviews_customer_time",
        "customer_number",
        "created_at",
        "portfolio_review_id",
    ),
)

credit_order_recommendations_table = Table(
    "credit_order_recommendations",
    metadata,
    Column("order_recommendation_id", String(64), primary_key=True),
    Column("customer_number", Integer, nullable=False),
    Column("customer_name", String(255), nullable=False),
    Column("contemplated_order_amount", Float, nullable=False),
    Column("order_reference", String(255), nullable=True),
    Column("disposition", String(64), nullable=False),
    Column("analyst_identity", String(255), nullable=False),
    Column("rationale", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("source_as_of", String(64), nullable=False),
    Column(
        "assessment_id",
        String(64),
        ForeignKey("credit_risk_assessments.assessment_id"),
        nullable=True,
    ),
    Column(
        "proposal_id",
        String(64),
        ForeignKey("credit_line_proposals.proposal_id"),
        nullable=True,
    ),
    Column("current_credit_line", Float, nullable=False),
    Column("current_partial_exposure", Float, nullable=False),
    Column("projected_partial_exposure", Float, nullable=False),
    Column("projected_partial_available_credit", Float, nullable=False),
    Column("projected_partial_over_line_amount", Float, nullable=False),
    Column("actor_identity_source", String(32), nullable=False),
    Column("actor_authority_status", String(64), nullable=False),
    Column("recommendation_classification", String(64), nullable=False),
    Column("decision_status", String(64), nullable=False),
    Column("decision_effect", String(16), nullable=False),
    Column("order_effect", String(16), nullable=False),
    Column("erp_write", Integer, nullable=False, server_default="0"),
    Column("evidence_snapshot_json", Text, nullable=False),
    Column("evidence_snapshot_sha256", String(64), nullable=False),
    CheckConstraint("contemplated_order_amount > 0"),
    CheckConstraint(
        "disposition IN "
        "('advance_to_authorized_review', 'request_additional_information', "
        "'escalate_for_credit_authority', 'do_not_advance')"
    ),
    CheckConstraint("projected_partial_over_line_amount >= 0"),
    CheckConstraint("actor_identity_source = 'operator_supplied'"),
    CheckConstraint("actor_authority_status = 'not_independently_verified'"),
    CheckConstraint(
        "recommendation_classification = 'professional_recommendation'"
    ),
    CheckConstraint(
        "decision_status = 'not_submitted_to_governed_decision'"
    ),
    CheckConstraint("decision_effect = 'none'"),
    CheckConstraint("order_effect = 'none'"),
    CheckConstraint("erp_write = 0"),
    CheckConstraint("length(evidence_snapshot_sha256) = 64"),
    Index(
        "idx_credit_order_recommendations_customer_time",
        "customer_number",
        "created_at",
        "order_recommendation_id",
    ),
)

credit_potential_customers_table = Table(
    "credit_potential_customers",
    metadata,
    Column("potential_customer_id", String(64), primary_key=True),
    Column("status", String(64), nullable=False),
    Column("source_file_name", String(255), nullable=False),
    Column("source_sha256", String(64), nullable=False),
    Column("parser_name", String(64), nullable=False),
    Column("parser_version", String(32), nullable=False),
    Column("classifier_confidence", Float, nullable=False),
    Column("received_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    Column("fields_json", Text, nullable=False),
    Column("evidence_json", Text, nullable=False),
    Column("km_setup_json", Text, nullable=False),
    Column("matched_customer_number", Integer, nullable=True),
    Column("match_disposition", String(64), nullable=True),
    Column("review_notes", Text, nullable=False),
    Column("erp_write", Integer, nullable=False, server_default="0"),
    CheckConstraint("erp_write = 0"),
    Index(
        "idx_credit_potential_customers_status_time", "status", "received_at"
    ),
)

credit_potential_customer_documents_table = Table(
    "credit_potential_customer_documents",
    metadata,
    Column(
        "potential_customer_id",
        String(64),
        ForeignKey("credit_potential_customers.potential_customer_id"),
        primary_key=True,
    ),
    Column("file_name", String(255), nullable=False),
    Column("content_type", String(64), nullable=False),
    Column("content", _DOCUMENT_BLOB_TYPE, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("created_at", String(64), nullable=False),
)


# --- accounts_payable module ------------------------------------------
#
# Money amounts on ap_invoices (subtotal/tax/freight/discount/total_amount)
# are stored as TEXT in the original design (OCR-extracted, not always a
# clean parseable number) - kept as VARCHAR here, not a numeric type.

ap_invoices_table = Table(
    "ap_invoices",
    metadata,
    Column("ap_invoice_id", String(64), primary_key=True),
    Column("source_key", String(255), nullable=False, unique=True),
    Column("document_job_id", String(64), nullable=False),
    Column("document_result_id", String(64), nullable=False),
    Column("source_record_index", Integer, nullable=True),
    Column("source_file_name", String(255), nullable=False),
    Column("content_type", String(64), nullable=True),
    Column("document_type", String(32), nullable=False),
    Column("document_status", String(32), nullable=False),
    Column("classifier", String(64), nullable=True),
    Column("classification_confidence", Float, nullable=True),
    Column("classification_evidence_json", Text, nullable=False),
    Column("parser_name", String(64), nullable=True),
    Column("parser_version", String(32), nullable=True),
    Column("vendor_number", String(64), nullable=True),
    Column("vendor_name", String(255), nullable=True),
    Column("normalized_vendor_identity", String(255), nullable=True),
    Column("invoice_number", String(64), nullable=True),
    Column("normalized_invoice_number", String(64), nullable=True),
    Column("invoice_date", String(64), nullable=True),
    Column("due_date", String(64), nullable=True),
    Column("purchase_order_number", String(64), nullable=True),
    Column("subtotal", String(64), nullable=True),
    Column("tax", String(64), nullable=True),
    Column("freight", String(64), nullable=True),
    Column("discount", String(64), nullable=True),
    Column("total_amount", String(64), nullable=True),
    Column("currency", String(16), nullable=True),
    Column("terms", String(64), nullable=True),
    Column("ocr_confidence", Float, nullable=True),
    Column("field_evidence_json", Text, nullable=False),
    Column("exceptions_json", Text, nullable=False),
    Column("warnings_json", Text, nullable=False),
    Column("base_review_required", Integer, nullable=False),
    Column("ocr_review_required", Integer, nullable=False),
    Column("received_at", String(64), nullable=True),
    Column("processed_at", String(64), nullable=True),
    Column("source_result_created_at", String(64), nullable=True),
    Column("source_result_updated_at", String(64), nullable=True),
    Column("source_as_of", String(64), nullable=False),
    Column("source_evidence_sha256", String(64), nullable=False),
    Column("imported_at", String(64), nullable=False),
    Column("last_synced_at", String(64), nullable=False),
    CheckConstraint("document_type = 'vendor_invoice'"),
    CheckConstraint("base_review_required IN (0, 1)"),
    CheckConstraint("ocr_review_required IN (0, 1)"),
    CheckConstraint("length(source_evidence_sha256) = 64"),
    Index("idx_ap_invoices_vendor", "normalized_vendor_identity", "vendor_name"),
    Index("idx_ap_invoices_number", "normalized_invoice_number"),
    Index("idx_ap_invoices_dates", "invoice_date", "due_date"),
    Index("idx_ap_invoices_review", "base_review_required", "ocr_review_required"),
)

ap_invoice_revisions_table = Table(
    "ap_invoice_revisions",
    metadata,
    Column("revision_id", String(64), primary_key=True),
    Column(
        "ap_invoice_id",
        String(64),
        ForeignKey("ap_invoices.ap_invoice_id"),
        nullable=False,
    ),
    Column("source_evidence_sha256", String(64), nullable=False),
    Column("source_as_of", String(64), nullable=False),
    Column("snapshot_json", Text, nullable=False),
    Column("recorded_at", String(64), nullable=False),
    UniqueConstraint("ap_invoice_id", "source_evidence_sha256"),
    Index("idx_ap_revisions_invoice", "ap_invoice_id", "recorded_at"),
)

ap_invoice_events_table = Table(
    "ap_invoice_events",
    metadata,
    Column("event_id", String(64), primary_key=True),
    Column("event_key", String(255), nullable=False, unique=True),
    Column(
        "ap_invoice_id",
        String(64),
        ForeignKey("ap_invoices.ap_invoice_id"),
        nullable=False,
    ),
    Column("event_type", String(64), nullable=False),
    Column("label", String(255), nullable=False),
    Column("occurred_at", String(64), nullable=True),
    Column("recorded_at", String(64), nullable=False),
    Column("source", String(64), nullable=False),
    Column("actor", String(255), nullable=True),
    Column("details", Text, nullable=False),
    Column("source_evidence_sha256", String(64), nullable=True),
    Index("idx_ap_events_invoice", "ap_invoice_id", "occurred_at", "event_id"),
)

ap_duplicate_candidates_table = Table(
    "ap_duplicate_candidates",
    metadata,
    Column("candidate_id", String(64), primary_key=True),
    Column(
        "invoice_a_id",
        String(64),
        ForeignKey("ap_invoices.ap_invoice_id"),
        nullable=False,
    ),
    Column(
        "invoice_b_id",
        String(64),
        ForeignKey("ap_invoices.ap_invoice_id"),
        nullable=False,
    ),
    Column("vendor_identity", String(255), nullable=False),
    Column("normalized_invoice_number", String(64), nullable=False),
    Column("amount_corroboration", String(16), nullable=False),
    Column("date_corroboration", String(16), nullable=False),
    Column("evidence_json", Text, nullable=False),
    Column("detected_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    UniqueConstraint("invoice_a_id", "invoice_b_id"),
    CheckConstraint("invoice_a_id < invoice_b_id"),
    Index("idx_ap_duplicates_a", "invoice_a_id"),
    Index("idx_ap_duplicates_b", "invoice_b_id"),
)

ap_control_cases_table = Table(
    "ap_control_cases",
    metadata,
    Column("control_case_id", String(64), primary_key=True),
    Column(
        "ap_invoice_id",
        String(64),
        ForeignKey("ap_invoices.ap_invoice_id"),
        nullable=False,
    ),
    Column("intended_action", String(32), nullable=False),
    Column("requested_by", String(255), nullable=False),
    Column("assigned_reviewer", String(255), nullable=False),
    Column("payment_preparer", String(255), nullable=True),
    Column("notes", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("source_evidence_sha256", String(64), nullable=False),
    Column("evidence_snapshot_json", Text, nullable=False),
    Column("evidence_snapshot_sha256", String(64), nullable=False),
    Column("actor_identity_source", String(32), nullable=False),
    Column("actor_authority_status", String(64), nullable=False),
    Column("approval_effect", String(16), nullable=False),
    Column("payment_effect", String(16), nullable=False),
    CheckConstraint(
        "intended_action IN ('approval_review', 'payment_preparation')"
    ),
    CheckConstraint("length(source_evidence_sha256) = 64"),
    CheckConstraint("length(evidence_snapshot_sha256) = 64"),
    CheckConstraint("actor_identity_source = 'operator_supplied'"),
    CheckConstraint("actor_authority_status = 'not_independently_verified'"),
    CheckConstraint("approval_effect = 'none'"),
    CheckConstraint("payment_effect = 'none'"),
    Index(
        "idx_ap_control_cases_queue",
        "intended_action",
        "created_at",
        "control_case_id",
    ),
)

ap_control_reviews_table = Table(
    "ap_control_reviews",
    metadata,
    Column("review_id", String(64), primary_key=True),
    Column(
        "control_case_id",
        String(64),
        ForeignKey("ap_control_cases.control_case_id"),
        nullable=False,
    ),
    Column("reviewer_identity", String(255), nullable=False),
    Column("disposition", String(32), nullable=False),
    Column("notes", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("actor_identity_source", String(32), nullable=False),
    Column("actor_authority_status", String(64), nullable=False),
    Column("approval_effect", String(16), nullable=False),
    Column("payment_effect", String(16), nullable=False),
    CheckConstraint(
        "disposition IN "
        "('evidence_ready', 'needs_information', "
        "'duplicate_review_required', 'not_ready')"
    ),
    CheckConstraint("actor_identity_source = 'operator_supplied'"),
    CheckConstraint("actor_authority_status = 'not_independently_verified'"),
    CheckConstraint("approval_effect = 'none'"),
    CheckConstraint("payment_effect = 'none'"),
    Index(
        "idx_ap_control_reviews_case", "control_case_id", "created_at", "review_id"
    ),
)

ap_cash_scenarios_table = Table(
    "ap_cash_scenarios",
    metadata,
    Column("cash_scenario_id", String(64), primary_key=True),
    Column("as_of_date", String(64), nullable=False),
    Column("horizon_days", Integer, nullable=False),
    Column("horizon_end_date", String(64), nullable=False),
    Column("include_review_required", Integer, nullable=False),
    Column("prepared_by", String(255), nullable=False),
    Column("rationale", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("included_invoice_count", Integer, nullable=False),
    Column("included_known_amount_count", Integer, nullable=False),
    Column("extracted_amount", Float, nullable=False),
    Column("excluded_review_required_count", Integer, nullable=False),
    Column("excluded_missing_due_date_count", Integer, nullable=False),
    Column("excluded_missing_amount_count", Integer, nullable=False),
    Column("actor_identity_source", String(32), nullable=False),
    Column("actor_authority_status", String(64), nullable=False),
    Column("scenario_classification", String(32), nullable=False),
    Column(
        "current_payable_status_known",
        Integer,
        nullable=False,
        server_default="0",
    ),
    Column("approval_effect", String(16), nullable=False),
    Column("payment_effect", String(16), nullable=False),
    Column("erp_write", Integer, nullable=False, server_default="0"),
    Column("evidence_snapshot_json", Text, nullable=False),
    Column("evidence_snapshot_sha256", String(64), nullable=False),
    CheckConstraint("horizon_days IN (7, 14, 30, 60, 90)"),
    CheckConstraint("include_review_required IN (0, 1)"),
    CheckConstraint("included_invoice_count >= 0"),
    CheckConstraint("included_known_amount_count >= 0"),
    CheckConstraint("excluded_review_required_count >= 0"),
    CheckConstraint("excluded_missing_due_date_count >= 0"),
    CheckConstraint("excluded_missing_amount_count >= 0"),
    CheckConstraint("actor_identity_source = 'operator_supplied'"),
    CheckConstraint("actor_authority_status = 'not_independently_verified'"),
    CheckConstraint("scenario_classification = 'analytical_scenario'"),
    CheckConstraint("current_payable_status_known = 0"),
    CheckConstraint("approval_effect = 'none'"),
    CheckConstraint("payment_effect = 'none'"),
    CheckConstraint("erp_write = 0"),
    CheckConstraint("length(evidence_snapshot_sha256) = 64"),
    Index("idx_ap_cash_scenarios_time", "created_at", "cash_scenario_id"),
)

ap_exception_actions_table = Table(
    "ap_exception_actions",
    metadata,
    Column("action_id", String(64), primary_key=True),
    Column(
        "ap_invoice_id",
        String(64),
        ForeignKey("ap_invoices.ap_invoice_id"),
        nullable=False,
    ),
    Column("disposition", String(32), nullable=False),
    Column("owner_identity", String(255), nullable=False),
    Column("actor_identity", String(255), nullable=False),
    Column("notes", Text, nullable=False),
    Column("follow_up_date", String(64), nullable=True),
    Column("created_at", String(64), nullable=False),
    Column("source_evidence_sha256", String(64), nullable=False),
    Column("actor_identity_source", String(32), nullable=False),
    Column("owner_identity_source", String(32), nullable=False),
    Column("authority_status", String(64), nullable=False),
    Column("action_classification", String(64), nullable=False),
    Column("approval_effect", String(16), nullable=False),
    Column("payment_effect", String(16), nullable=False),
    Column("erp_write", Integer, nullable=False, server_default="0"),
    Column("evidence_snapshot_json", Text, nullable=False),
    Column("evidence_snapshot_sha256", String(64), nullable=False),
    CheckConstraint(
        "disposition IN "
        "('investigating', 'information_requested', "
        "'document_correction_needed', 'duplicate_review_complete', "
        "'ready_for_control_case')"
    ),
    CheckConstraint("length(source_evidence_sha256) = 64"),
    CheckConstraint("actor_identity_source = 'operator_supplied'"),
    CheckConstraint("owner_identity_source = 'operator_supplied'"),
    CheckConstraint("authority_status = 'not_independently_verified'"),
    CheckConstraint(
        "action_classification = 'professional_workflow_metadata'"
    ),
    CheckConstraint("approval_effect = 'none'"),
    CheckConstraint("payment_effect = 'none'"),
    CheckConstraint("erp_write = 0"),
    CheckConstraint("length(evidence_snapshot_sha256) = 64"),
    Index(
        "idx_ap_exception_actions_invoice",
        "ap_invoice_id",
        "created_at",
        "action_id",
    ),
)

ap_erp_open_ledger_cache_table = Table(
    "ap_erp_open_ledger_cache",
    metadata,
    Column("vendor_number", String(64), primary_key=True),
    Column("invoice_number", String(64), primary_key=True),
    Column("invoice_date", String(64), nullable=True),
    Column("due_date", String(64), nullable=True),
    Column("amount_invoiced", Float, nullable=False),
    Column("amount_discount", Float, nullable=False),
    Column("on_hold", Integer, nullable=False, server_default="0"),
    Column("refreshed_at", String(64), nullable=False),
    Column("gl_division", String(64), nullable=True),
    Column("gl_department", String(64), nullable=True),
    Column("gl_account", String(64), nullable=True),
    Index("idx_ap_erp_open_ledger_due_date", "due_date"),
)

ap_erp_vendor_terms_cache_table = Table(
    "ap_erp_vendor_terms_cache",
    metadata,
    Column("vendor_number", String(64), primary_key=True),
    Column("terms_code", String(64), nullable=True),
    Column("refreshed_at", String(64), nullable=False),
    Column("vendor_name", String(255), nullable=True),
)

ap_vendor_terms_reference_table = Table(
    "ap_vendor_terms_reference",
    metadata,
    Column("terms_code", String(64), primary_key=True),
    Column("discount_percent", Float, nullable=False, server_default="0"),
    Column("num_periods", Integer, nullable=True),
    Column("num_months", Integer, nullable=True),
    Column("num_days", Integer, nullable=True),
    Column("second_period", Integer, nullable=True),
    Column("third_period", Integer, nullable=True),
    Column("next_period", Integer, nullable=True),
    Column("day_of_month", Integer, nullable=True),
    Column("cutoff_day", Integer, nullable=True),
    Column("description", String(255), nullable=False, server_default=""),
    Column("updated_at", String(64), nullable=False),
)

ap_warehouse_approval_actions_table = Table(
    "ap_warehouse_approval_actions",
    metadata,
    Column("action_id", String(64), primary_key=True),
    Column("vendor_number", String(64), nullable=False),
    Column("invoice_number", String(64), nullable=False),
    Column("from_status", String(64), nullable=False),
    Column("to_status", String(64), nullable=False),
    Column("actor_identity", String(255), nullable=False),
    Column(
        "actor_identity_source",
        String(32),
        nullable=False,
        server_default="operator_supplied",
    ),
    Column("notes", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    CheckConstraint(
        "to_status IN "
        "('needs_approval', 'approved_by_warehouse', "
        "'approved_and_entered_by_ap')"
    ),
    CheckConstraint("actor_identity_source IN ('operator_supplied', 'sso')"),
    Index(
        "idx_ap_warehouse_approval_actions_invoice",
        "vendor_number",
        "invoice_number",
        "created_at",
    ),
)


# --- workflow_foundation module ----------------------------------------
#
# Three tables (wf_audit_events, wf_task_assignments, wf_task_events) were
# originally ordered "most recent first" via SQLite's implicit `rowid`
# pseudo-column (`ORDER BY rowid DESC`). MySQL has no equivalent stable
# physical-order column, so each gets an explicit auto-increment `sequence`
# surrogate key instead, with the original TEXT id kept as a UNIQUE column
# (nothing else has a foreign key into these three tables' TEXT ids, so
# this is safe).
#
# `username` uniqueness/ordering was `COLLATE NOCASE` in SQLite. MySQL's
# standard utf8mb4 collations are already case-insensitive by default, so
# a plain UNIQUE constraint enforces the same guarantee against real
# MySQL without any special DDL. The SQLite test engine's default
# collation is case-sensitive, so case-insensitive *duplicate* detection
# isn't exercised under tests - production correctness (the actual
# target) doesn't depend on that gap. Query-level case-insensitive
# lookups/ordering (`get_account_credentials`, `list_users`, ...) use
# func.lower(...) instead of a per-dialect COLLATE string, which is
# portable across both engines.

wf_persons_table = Table(
    "wf_persons",
    metadata,
    Column("person_id", String(64), primary_key=True),
    Column("display_name", String(255), nullable=False),
    Column("status", String(16), nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("created_by_user_id", String(64), nullable=True),
    CheckConstraint("status IN ('active', 'inactive')"),
)

wf_user_accounts_table = Table(
    "wf_user_accounts",
    metadata,
    Column("user_id", String(64), primary_key=True),
    Column(
        "person_id",
        String(64),
        ForeignKey("wf_persons.person_id"),
        nullable=False,
        unique=True,
    ),
    Column("username", String(255), nullable=False, unique=True),
    Column("password_salt", Text, nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("password_algorithm", String(64), nullable=False),
    Column("status", String(16), nullable=False),
    Column(
        "status_version",
        Integer,
        nullable=False,
        server_default="1",
    ),
    Column(
        "credential_version",
        Integer,
        nullable=False,
        server_default="1",
    ),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    CheckConstraint("password_algorithm = 'scrypt-n16384-r8-p1-v1'"),
    CheckConstraint("status IN ('active', 'inactive')"),
    CheckConstraint("status_version >= 1"),
    CheckConstraint("credential_version >= 1"),
)

wf_roles_table = Table(
    "wf_roles",
    metadata,
    Column("role_id", String(64), primary_key=True),
    Column("name", String(255), nullable=False),
    Column("description", Text, nullable=False),
    Column("queue_scope", String(64), nullable=False),
    Column("authority_effect", String(16), nullable=False),
    Column("decision_authority", Integer, nullable=False),
    Column("created_at", String(64), nullable=False),
    CheckConstraint("authority_effect = 'none'"),
    CheckConstraint("decision_authority = 0"),
)

wf_role_assignments_table = Table(
    "wf_role_assignments",
    metadata,
    Column("role_assignment_id", String(64), primary_key=True),
    Column(
        "user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("role_id", String(64), ForeignKey("wf_roles.role_id"), nullable=False),
    Column("effective_from", String(64), nullable=False),
    Column("effective_to", String(64), nullable=True),
    Column("assignment_status", String(16), nullable=False),
    Column("assigned_by_user_id", String(64), nullable=True),
    Column("created_at", String(64), nullable=False),
    CheckConstraint("assignment_status = 'active'"),
    UniqueConstraint("user_id", "role_id", "effective_from"),
)

wf_sessions_table = Table(
    "wf_sessions",
    metadata,
    Column("session_id", String(64), primary_key=True),
    Column(
        "user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("token_hash", String(128), nullable=False, unique=True),
    Column("issued_at", String(64), nullable=False),
    Column("expires_at", String(64), nullable=False),
    Column("revoked_at", String(64), nullable=True),
    Column("last_seen_at", String(64), nullable=False),
    Index("idx_wf_sessions_token", "token_hash", "expires_at"),
)

wf_modules_table = Table(
    "wf_modules",
    metadata,
    Column("module_id", String(64), primary_key=True),
    Column("name", String(255), nullable=False),
    Column("description", Text, nullable=False),
    Column("module_group", String(32), nullable=False),
    Column("default_access", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("authority_effect", String(16), nullable=False),
    Column("created_at", String(64), nullable=False),
    CheckConstraint(
        "module_group IN ('Overview', 'Workspaces', 'Tools', 'System')"
    ),
    CheckConstraint("default_access = 0"),
    CheckConstraint("status = 'active'"),
    CheckConstraint("authority_effect = 'none'"),
)

wf_access_profiles_table = Table(
    "wf_access_profiles",
    metadata,
    Column(
        "user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        primary_key=True,
    ),
    Column("access_version", Integer, nullable=False),
    Column("updated_at", String(64), nullable=False),
    Column(
        "updated_by_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=True,
    ),
    CheckConstraint("access_version >= 1"),
)

wf_user_module_access_table = Table(
    "wf_user_module_access",
    metadata,
    Column("user_id", String(64), ForeignKey("wf_user_accounts.user_id")),
    Column("module_id", String(64), ForeignKey("wf_modules.module_id")),
    Column("allowed", Integer, nullable=False),
    Column("updated_at", String(64), nullable=False),
    Column(
        "updated_by_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=True,
    ),
    PrimaryKeyConstraint("user_id", "module_id"),
    CheckConstraint("allowed IN (0, 1)"),
)

wf_module_access_events_table = Table(
    "wf_module_access_events",
    metadata,
    Column("access_event_id", String(64), primary_key=True),
    Column(
        "user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column(
        "actor_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=True,
    ),
    Column("before_module_ids_json", Text, nullable=False),
    Column("after_module_ids_json", Text, nullable=False),
    Column("access_version", Integer, nullable=False),
    Column("reason", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    CheckConstraint("access_version >= 1"),
)

wf_user_invitations_table = Table(
    "wf_user_invitations",
    metadata,
    Column("invitation_id", String(64), primary_key=True),
    Column("username", String(255), nullable=False),
    Column("display_name", String(255), nullable=False),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("role_ids_json", Text, nullable=False),
    Column("module_ids_json", Text, nullable=False),
    Column("status", String(16), nullable=False),
    Column(
        "created_by_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("created_at", String(64), nullable=False),
    Column("expires_at", String(64), nullable=False),
    Column("activated_at", String(64), nullable=True),
    Column(
        "activated_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=True,
    ),
    # Replaces SQLite's partial unique index
    # (`... ON wf_user_invitations(username COLLATE NOCASE) WHERE status = 'pending'`)
    # - MySQL has no partial indexes, so a generated column that's only
    # non-NULL while the invitation is pending stands in: a UNIQUE index
    # on it enforces "at most one pending invitation per username"
    # exactly like the original, since NULLs never collide under UNIQUE.
    Column(
        "pending_username_key",
        String(255),
        Computed(
            "CASE WHEN status = 'pending' THEN LOWER(username) ELSE NULL END",
            persisted=True,
        ),
    ),
    CheckConstraint("length(token_hash) = 64"),
    CheckConstraint("status IN ('pending', 'activated', 'revoked', 'expired')"),
    Index("idx_wf_pending_invitation_username", "pending_username_key", unique=True),
)

wf_invitation_events_table = Table(
    "wf_invitation_events",
    metadata,
    Column("invitation_event_id", String(64), primary_key=True),
    Column(
        "invitation_id",
        String(64),
        ForeignKey("wf_user_invitations.invitation_id"),
        nullable=False,
    ),
    Column("event_type", String(16), nullable=False),
    Column(
        "actor_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=True,
    ),
    Column("created_at", String(64), nullable=False),
    Column("details_json", Text, nullable=False),
    CheckConstraint("event_type IN ('created', 'activated', 'revoked', 'expired')"),
)

wf_password_reset_tokens_table = Table(
    "wf_password_reset_tokens",
    metadata,
    Column("reset_id", String(64), primary_key=True),
    Column(
        "user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("status", String(16), nullable=False),
    Column(
        "created_by_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("created_at", String(64), nullable=False),
    Column("expires_at", String(64), nullable=False),
    Column("activated_at", String(64), nullable=True),
    CheckConstraint("length(token_hash) = 64"),
    CheckConstraint("status IN ('pending', 'activated', 'revoked', 'expired')"),
)

wf_password_reset_events_table = Table(
    "wf_password_reset_events",
    metadata,
    Column("reset_event_id", String(64), primary_key=True),
    Column(
        "reset_id",
        String(64),
        ForeignKey("wf_password_reset_tokens.reset_id"),
        nullable=False,
    ),
    Column("event_type", String(16), nullable=False),
    Column(
        "actor_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=True,
    ),
    Column("created_at", String(64), nullable=False),
    Column("details_json", Text, nullable=False),
    CheckConstraint("event_type IN ('created', 'activated', 'expired')"),
)

wf_definitions_table = Table(
    "wf_definitions",
    metadata,
    Column("definition_id", String(64), nullable=False),
    Column("version", String(32), nullable=False),
    Column("title", String(255), nullable=False),
    Column("description", Text, nullable=False),
    Column("states_json", Text, nullable=False),
    Column("transitions_json", Text, nullable=False),
    Column("status", String(16), nullable=False),
    Column("authority_effect", String(16), nullable=False),
    Column("created_at", String(64), nullable=False),
    PrimaryKeyConstraint("definition_id", "version"),
    CheckConstraint("status = 'active'"),
    CheckConstraint("authority_effect = 'none'"),
)

wf_tasks_table = Table(
    "wf_tasks",
    metadata,
    Column("task_id", String(64), primary_key=True),
    Column("definition_id", String(64), nullable=False),
    Column("definition_version", String(32), nullable=False),
    Column("title", String(255), nullable=False),
    Column("description", Text, nullable=False),
    Column("capability", String(32), nullable=False),
    Column("context_type", String(64), nullable=False),
    Column("context_id", String(64), nullable=False),
    Column("context_label", String(255), nullable=False),
    Column("queue_role_id", String(64), ForeignKey("wf_roles.role_id"), nullable=False),
    Column("priority", String(16), nullable=False),
    Column("state", String(16), nullable=False),
    Column("due_date", String(64), nullable=True),
    Column(
        "created_by_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("idempotency_key", String(255), nullable=False),
    Column("request_sha256", String(64), nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    Column("version", Integer, nullable=False),
    Column("assignment_effect", String(32), nullable=False),
    Column("authority_effect", String(16), nullable=False),
    Column("execution_effect", String(16), nullable=False),
    ForeignKeyConstraint(
        ["definition_id", "definition_version"],
        ["wf_definitions.definition_id", "wf_definitions.version"],
    ),
    UniqueConstraint("created_by_user_id", "idempotency_key"),
    CheckConstraint(
        "capability IN "
        "('credit_risk', 'accounts_payable', 'lockbox', 'reporting', 'platform')"
    ),
    CheckConstraint("priority IN ('low', 'medium', 'high', 'critical')"),
    CheckConstraint(
        "state IN "
        "('open', 'in_progress', 'deferred', 'completed', 'cancelled', 'reopened')"
    ),
    CheckConstraint("length(request_sha256) = 64"),
    CheckConstraint("version >= 1"),
    CheckConstraint("assignment_effect = 'work_ownership_only'"),
    CheckConstraint("authority_effect = 'none'"),
    CheckConstraint("execution_effect = 'none'"),
    Index("idx_wf_tasks_queue", "queue_role_id", "state", "due_date", "updated_at"),
    Index("idx_wf_tasks_context", "capability", "context_type", "context_id"),
)

wf_task_assignments_table = Table(
    "wf_task_assignments",
    metadata,
    Column("sequence", _SEQUENCE_TYPE, primary_key=True, autoincrement=True),
    Column("assignment_event_id", String(64), nullable=False, unique=True),
    Column("task_id", String(64), ForeignKey("wf_tasks.task_id"), nullable=False),
    Column(
        "assignee_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("prior_assignee_user_id", String(64), nullable=True),
    Column(
        "assigned_by_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("assignment_type", String(16), nullable=False),
    Column("note", Text, nullable=False),
    Column("idempotency_key", String(255), nullable=False, unique=True),
    Column("task_version", Integer, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("authority_effect", String(16), nullable=False),
    CheckConstraint("assignment_type IN ('initial', 'claim', 'reassign')"),
    CheckConstraint("authority_effect = 'none'"),
    Index("idx_wf_assignments_task", "task_id", "sequence"),
)

wf_task_events_table = Table(
    "wf_task_events",
    metadata,
    Column("sequence", _SEQUENCE_TYPE, primary_key=True, autoincrement=True),
    Column("event_id", String(64), nullable=False, unique=True),
    Column("task_id", String(64), ForeignKey("wf_tasks.task_id"), nullable=False),
    Column("event_type", String(32), nullable=False),
    Column("from_state", String(16), nullable=True),
    Column("to_state", String(16), nullable=False),
    Column(
        "actor_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("note", Text, nullable=False),
    Column("idempotency_key", String(255), nullable=False, unique=True),
    Column("task_version", Integer, nullable=False),
    Column("created_at", String(64), nullable=False),
    CheckConstraint("event_type IN ('task_created', 'task_state_changed')"),
    Index("idx_wf_task_events_task", "task_id", "sequence"),
)

wf_notifications_table = Table(
    "wf_notifications",
    metadata,
    Column("notification_id", String(64), primary_key=True),
    Column(
        "recipient_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("task_id", String(64), ForeignKey("wf_tasks.task_id"), nullable=True),
    Column("notification_type", String(64), nullable=False),
    Column("title", String(255), nullable=False),
    Column("message", Text, nullable=False),
    Column("severity", String(16), nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("read_at", String(64), nullable=True),
    CheckConstraint("severity IN ('info', 'success', 'warning', 'critical')"),
    Index(
        "idx_wf_notifications_recipient", "recipient_user_id", "read_at", "created_at"
    ),
)

wf_audit_events_table = Table(
    "wf_audit_events",
    metadata,
    Column("sequence", _SEQUENCE_TYPE, primary_key=True, autoincrement=True),
    Column("audit_id", String(64), nullable=False, unique=True),
    Column("event_type", String(128), nullable=False),
    Column("actor_user_id", String(64), nullable=True),
    Column("subject_type", String(64), nullable=False),
    Column("subject_id", String(64), nullable=False),
    Column("correlation_id", String(64), nullable=False),
    Column("occurred_at", String(64), nullable=False),
    Column("details_json", Text, nullable=False),
    Column("previous_hash", String(64), nullable=False),
    Column("record_hash", String(64), nullable=False, unique=True),
    Column("schema_version", String(8), nullable=False),
    CheckConstraint("schema_version = '1.0'"),
    Index("idx_wf_audit_subject", "subject_type", "subject_id", "sequence"),
)


# --- payment_notes module -----------------------------------------------
#
# pn_route_reference_activations was originally ordered "most recent first"
# via SQLite's implicit rowid (`ORDER BY rowid DESC`) to read the tail of its
# hash chain. Same fix as workflow_foundation: an explicit auto-increment
# `sequence` surrogate key, with the original TEXT id kept as a UNIQUE
# column (nothing has a foreign key into it).

pn_route_references_table = Table(
    "pn_route_references",
    metadata,
    Column("reference_id", String(64), primary_key=True),
    Column("version_label", String(64), nullable=False),
    Column("source_name", String(255), nullable=False),
    Column("source_sha256", String(64), nullable=False),
    Column("source_size", Integer, nullable=False),
    Column("parser_version", String(64), nullable=False),
    Column("payload_json", _LARGE_JSON_TYPE, nullable=False),
    Column("payload_sha256", String(64), nullable=False),
    Column("created_by", String(255), nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("request_sha256", String(64), nullable=False),
    CheckConstraint("length(source_sha256) = 64"),
    CheckConstraint("source_size > 0"),
    CheckConstraint("length(payload_sha256) = 64"),
    CheckConstraint("length(request_sha256) = 64"),
    UniqueConstraint("created_by", "idempotency_key"),
    UniqueConstraint("source_sha256", "version_label", name="uq_pn_route_content_version"),
)

pn_route_reference_activations_table = Table(
    "pn_route_reference_activations",
    metadata,
    Column("sequence", _SEQUENCE_TYPE, primary_key=True, autoincrement=True),
    Column("activation_id", String(64), nullable=False, unique=True),
    Column(
        "reference_id",
        String(64),
        ForeignKey("pn_route_references.reference_id"),
        nullable=False,
    ),
    Column("actor", String(255), nullable=False),
    Column("occurred_at", String(64), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("request_sha256", String(64), nullable=False),
    Column("previous_hash", String(64), nullable=False),
    Column("record_hash", String(64), nullable=False, unique=True),
    CheckConstraint("length(request_sha256) = 64"),
    CheckConstraint("length(previous_hash) = 64"),
    CheckConstraint("length(record_hash) = 64"),
    UniqueConstraint("actor", "idempotency_key"),
    Index(
        "idx_pn_route_activation_current", "occurred_at", "sequence"
    ),
)

pn_runs_table = Table(
    "pn_runs",
    metadata,
    Column("run_id", String(64), primary_key=True),
    Column("source_name", String(255), nullable=False),
    Column("source_sha256", String(64), nullable=False),
    Column("source_size", Integer, nullable=False),
    Column(
        "route_reference_id",
        String(64),
        ForeignKey("pn_route_references.reference_id"),
        nullable=False,
    ),
    Column("route_reference_sha256", String(64), nullable=False),
    Column("date_from", String(64), nullable=False),
    Column("date_to", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("deposit_count", Integer, nullable=False),
    Column("physical_item_count", Integer, nullable=False),
    Column("quarantined_row_count", Integer, nullable=False),
    Column("payload_json", _LARGE_JSON_TYPE, nullable=False),
    Column("payload_sha256", String(64), nullable=False),
    Column("created_by", String(255), nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("request_sha256", String(64), nullable=False),
    CheckConstraint("length(source_sha256) = 64"),
    CheckConstraint("source_size > 0"),
    CheckConstraint("length(route_reference_sha256) = 64"),
    CheckConstraint("deposit_count >= 0"),
    CheckConstraint("physical_item_count >= 0"),
    CheckConstraint("quarantined_row_count >= 0"),
    CheckConstraint("length(payload_sha256) = 64"),
    CheckConstraint("length(request_sha256) = 64"),
    UniqueConstraint("created_by", "idempotency_key"),
    UniqueConstraint(
        "source_sha256",
        "route_reference_id",
        "date_from",
        "date_to",
        name="uq_pn_run_content_scope",
    ),
    Index("idx_pn_runs_created", "created_at", "run_id"),
)

pn_review_events_table = Table(
    "pn_review_events",
    metadata,
    Column("event_id", String(64), primary_key=True),
    Column("run_id", String(64), ForeignKey("pn_runs.run_id"), nullable=False),
    Column("item_id", String(64), nullable=False),
    Column("decision", String(32), nullable=False),
    Column("selected_payment_id", String(255), nullable=True),
    Column("reason", Text, nullable=False),
    Column("actor", String(255), nullable=False),
    Column("occurred_at", String(64), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("request_sha256", String(64), nullable=False),
    Column("previous_hash", String(64), nullable=False),
    Column("record_hash", String(64), nullable=False, unique=True),
    CheckConstraint(
        "decision IN ('accept_candidate', 'leave_unmatched', 'hold')"
    ),
    CheckConstraint("length(request_sha256) = 64"),
    CheckConstraint("length(previous_hash) = 64"),
    CheckConstraint("length(record_hash) = 64"),
    UniqueConstraint("actor", "idempotency_key"),
    Index("idx_pn_review_item", "run_id", "item_id", "occurred_at", "event_id"),
)


# --- financial_close module ----------------------------------------------
#
# fc_control_events spans every control (plus the cycle itself) within a
# cycle, and list_events(cycle_id) reads across all of them ordered by
# occurred_at - a timestamp that is not guaranteed unique, so (like
# workflow_foundation's audit trail) it needs a real auto-increment
# `sequence` surrogate key as a tiebreaker; event_id becomes a UNIQUE
# column instead of the primary key (nothing has a foreign key into it).
# fc_template_events' own "sequence" column is already unique per
# template_id (every query filters to one template_id), so no surrogate
# is needed there.
#
# uq_fc_cycle_created_event was a SQLite partial unique index (one
# cycle_created event per cycle). MySQL has no partial indexes, so a
# STORED generated column - NULL unless this is the cycle-created row -
# takes its place; NULLs don't collide under a UNIQUE index.

fc_cycles_table = Table(
    "fc_cycles",
    metadata,
    Column("cycle_id", String(64), primary_key=True),
    Column("entity_label", String(160), nullable=False),
    Column("period_label", String(120), nullable=False),
    Column("period_start", String(64), nullable=False),
    Column("period_end", String(64), nullable=False),
    Column("target_completion_date", String(64), nullable=True),
    Column("description", Text, nullable=False),
    Column(
        "created_by_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("created_by_json", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("request_sha256", String(64), nullable=False),
    Column("definition_sha256", String(64), nullable=False),
    Column("authority_effect", String(16), nullable=False),
    Column("close_effect", String(16), nullable=False),
    Column("approval_effect", String(16), nullable=False),
    Column("posting_effect", String(16), nullable=False),
    Column("erp_write", Integer, nullable=False),
    CheckConstraint("length(request_sha256) = 64"),
    CheckConstraint("length(definition_sha256) = 64"),
    CheckConstraint("authority_effect = 'none'"),
    CheckConstraint("close_effect = 'none'"),
    CheckConstraint("approval_effect = 'none'"),
    CheckConstraint("posting_effect = 'none'"),
    CheckConstraint("erp_write = 0"),
    UniqueConstraint("created_by_user_id", "idempotency_key"),
    Index("idx_fc_cycles_period", "period_end", "period_start", "cycle_id"),
)

fc_control_items_table = Table(
    "fc_control_items",
    metadata,
    Column("control_id", String(64), primary_key=True),
    Column("cycle_id", String(64), ForeignKey("fc_cycles.cycle_id"), nullable=False),
    Column("title", String(255), nullable=False),
    Column("description", Text, nullable=False),
    Column("planned_date", String(64), nullable=True),
    Column(
        "preparer_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("preparer_json", Text, nullable=False),
    Column(
        "reviewer_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("reviewer_json", Text, nullable=False),
    Column(
        "created_by_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("created_by_json", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("request_sha256", String(64), nullable=False),
    Column("definition_sha256", String(64), nullable=False),
    Column("authority_effect", String(16), nullable=False),
    Column("close_effect", String(16), nullable=False),
    CheckConstraint("preparer_user_id <> reviewer_user_id"),
    CheckConstraint("length(request_sha256) = 64"),
    CheckConstraint("length(definition_sha256) = 64"),
    CheckConstraint("authority_effect = 'none'"),
    CheckConstraint("close_effect = 'none'"),
    UniqueConstraint("created_by_user_id", "idempotency_key"),
    Index(
        "idx_fc_controls_cycle", "cycle_id", "planned_date", "created_at", "control_id"
    ),
    Index(
        "idx_fc_controls_participants",
        "preparer_user_id",
        "reviewer_user_id",
        "cycle_id",
    ),
)

fc_control_events_table = Table(
    "fc_control_events",
    metadata,
    Column("sequence", _SEQUENCE_TYPE, primary_key=True, autoincrement=True),
    Column("event_id", String(64), nullable=False, unique=True),
    Column("cycle_id", String(64), ForeignKey("fc_cycles.cycle_id"), nullable=False),
    Column(
        "control_id",
        String(64),
        ForeignKey("fc_control_items.control_id"),
        nullable=True,
    ),
    Column("event_type", String(32), nullable=False),
    Column(
        "actor_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("actor_json", Text, nullable=False),
    Column("occurred_at", String(64), nullable=False),
    Column("details_json", _LARGE_JSON_TYPE, nullable=False),
    Column("subject_version", Integer, nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("request_sha256", String(64), nullable=False),
    Column("previous_hash", String(64), nullable=False),
    Column("record_hash", String(64), nullable=False, unique=True),
    Column("schema_version", String(8), nullable=False),
    Column("authority_effect", String(16), nullable=False),
    Column("close_effect", String(16), nullable=False),
    Column(
        "cycle_created_key",
        String(64),
        Computed(
            "CASE WHEN control_id IS NULL THEN cycle_id ELSE NULL END",
            persisted=True,
        ),
    ),
    CheckConstraint(
        "event_type IN "
        "('cycle_created', 'control_created', "
        "'preparation_recorded', 'review_recorded')"
    ),
    CheckConstraint("subject_version >= 1"),
    CheckConstraint("length(request_sha256) = 64"),
    CheckConstraint("length(previous_hash) = 64"),
    CheckConstraint("length(record_hash) = 64"),
    CheckConstraint("schema_version = '1.0'"),
    CheckConstraint("authority_effect = 'none'"),
    CheckConstraint("close_effect = 'none'"),
    CheckConstraint(
        "(event_type = 'cycle_created' AND control_id IS NULL) OR "
        "(event_type <> 'cycle_created' AND control_id IS NOT NULL)"
    ),
    UniqueConstraint("actor_user_id", "idempotency_key"),
    UniqueConstraint("control_id", "subject_version"),
    Index("idx_fc_events_cycle", "cycle_id", "occurred_at", "sequence"),
    Index("idx_fc_events_control", "control_id", "subject_version", "sequence"),
    Index("uq_fc_cycle_created_event", "cycle_created_key", unique=True),
)

fc_control_templates_table = Table(
    "fc_control_templates",
    metadata,
    Column("template_id", String(64), primary_key=True),
    Column(
        "created_by_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("created_by_json", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("request_sha256", String(64), nullable=False),
    Column("definition_sha256", String(64), nullable=False),
    Column("authority_effect", String(16), nullable=False),
    Column("policy_effect", String(16), nullable=False),
    Column("automation_effect", String(16), nullable=False),
    CheckConstraint("length(request_sha256) = 64"),
    CheckConstraint("length(definition_sha256) = 64"),
    CheckConstraint("authority_effect = 'none'"),
    CheckConstraint("policy_effect = 'none'"),
    CheckConstraint("automation_effect = 'none'"),
    UniqueConstraint("created_by_user_id", "idempotency_key"),
)

fc_template_versions_table = Table(
    "fc_template_versions",
    metadata,
    Column("template_id", String(64), ForeignKey("fc_control_templates.template_id"), primary_key=True),
    Column("version", Integer, primary_key=True),
    Column("title", String(255), nullable=False),
    Column("description", Text, nullable=False),
    Column("change_note", Text, nullable=False),
    Column("status", String(64), nullable=False),
    Column(
        "created_by_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("created_by_json", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("request_sha256", String(64), nullable=False),
    Column("previous_version_sha256", String(64), nullable=False),
    Column("version_sha256", String(64), nullable=False, unique=True),
    Column("policy_effect", String(16), nullable=False),
    Column("automation_effect", String(16), nullable=False),
    CheckConstraint("version >= 1"),
    CheckConstraint("status = 'local_user_authored_planning_draft'"),
    CheckConstraint("length(request_sha256) = 64"),
    CheckConstraint("length(previous_version_sha256) = 64"),
    CheckConstraint("length(version_sha256) = 64"),
    CheckConstraint("policy_effect = 'none'"),
    CheckConstraint("automation_effect = 'none'"),
    UniqueConstraint("created_by_user_id", "idempotency_key"),
    Index("idx_fc_template_versions_latest", "template_id", "version"),
)

fc_template_items_table = Table(
    "fc_template_items",
    metadata,
    Column("item_id", String(64), primary_key=True),
    Column("template_id", String(64), nullable=False),
    Column("template_version", Integer, nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("title", String(255), nullable=False),
    Column("description", Text, nullable=False),
    Column("planned_offset_days", Integer, nullable=False),
    Column(
        "preparer_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("preparer_json", Text, nullable=False),
    Column(
        "reviewer_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("reviewer_json", Text, nullable=False),
    Column("item_sha256", String(64), nullable=False),
    Column("authority_effect", String(16), nullable=False),
    Column("policy_effect", String(16), nullable=False),
    ForeignKeyConstraint(
        ["template_id", "template_version"],
        ["fc_template_versions.template_id", "fc_template_versions.version"],
    ),
    CheckConstraint("preparer_user_id <> reviewer_user_id"),
    CheckConstraint("ordinal >= 1"),
    CheckConstraint("template_version >= 1"),
    CheckConstraint("length(item_sha256) = 64"),
    CheckConstraint("authority_effect = 'none'"),
    CheckConstraint("policy_effect = 'none'"),
    UniqueConstraint("template_id", "template_version", "ordinal"),
    Index("idx_fc_template_items_version", "template_id", "template_version", "ordinal"),
)

fc_template_events_table = Table(
    "fc_template_events",
    metadata,
    Column("event_id", String(64), primary_key=True),
    Column(
        "template_id",
        String(64),
        ForeignKey("fc_control_templates.template_id"),
        nullable=False,
    ),
    Column("event_type", String(32), nullable=False),
    Column(
        "actor_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("actor_json", Text, nullable=False),
    Column("occurred_at", String(64), nullable=False),
    Column("details_json", _LARGE_JSON_TYPE, nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("request_sha256", String(64), nullable=False),
    Column("previous_hash", String(64), nullable=False),
    Column("record_hash", String(64), nullable=False, unique=True),
    Column("schema_version", String(8), nullable=False),
    Column("authority_effect", String(16), nullable=False),
    Column("policy_effect", String(16), nullable=False),
    Column("automation_effect", String(16), nullable=False),
    CheckConstraint(
        "event_type IN "
        "('template_created', 'template_version_created', 'cycle_instantiated')"
    ),
    CheckConstraint("sequence >= 1"),
    CheckConstraint("length(request_sha256) = 64"),
    CheckConstraint("length(previous_hash) = 64"),
    CheckConstraint("length(record_hash) = 64"),
    CheckConstraint("schema_version = '1.0'"),
    CheckConstraint("authority_effect = 'none'"),
    CheckConstraint("policy_effect = 'none'"),
    CheckConstraint("automation_effect = 'none'"),
    UniqueConstraint("template_id", "sequence"),
    UniqueConstraint("actor_user_id", "idempotency_key"),
    Index("idx_fc_template_events", "template_id", "sequence"),
)

fc_cycle_template_snapshots_table = Table(
    "fc_cycle_template_snapshots",
    metadata,
    Column("snapshot_id", String(64), primary_key=True),
    Column(
        "cycle_id",
        String(64),
        ForeignKey("fc_cycles.cycle_id"),
        nullable=False,
        unique=True,
    ),
    Column("template_id", String(64), nullable=False),
    Column("template_version", Integer, nullable=False),
    Column("template_version_sha256", String(64), nullable=False),
    Column("calendar_anchor_date", String(64), nullable=False),
    Column("snapshot_json", _LARGE_JSON_TYPE, nullable=False),
    Column(
        "created_by_user_id",
        String(64),
        ForeignKey("wf_user_accounts.user_id"),
        nullable=False,
    ),
    Column("created_by_json", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("request_sha256", String(64), nullable=False),
    Column("snapshot_sha256", String(64), nullable=False, unique=True),
    Column("authority_effect", String(16), nullable=False),
    Column("policy_effect", String(16), nullable=False),
    Column("automation_effect", String(16), nullable=False),
    Column("close_effect", String(16), nullable=False),
    Column("approval_effect", String(16), nullable=False),
    Column("posting_effect", String(16), nullable=False),
    Column("erp_write", Integer, nullable=False),
    ForeignKeyConstraint(
        ["template_id", "template_version"],
        ["fc_template_versions.template_id", "fc_template_versions.version"],
    ),
    CheckConstraint("template_version >= 1"),
    CheckConstraint("length(template_version_sha256) = 64"),
    CheckConstraint("length(request_sha256) = 64"),
    CheckConstraint("length(snapshot_sha256) = 64"),
    CheckConstraint("authority_effect = 'none'"),
    CheckConstraint("policy_effect = 'none'"),
    CheckConstraint("automation_effect = 'none'"),
    CheckConstraint("close_effect = 'none'"),
    CheckConstraint("approval_effect = 'none'"),
    CheckConstraint("posting_effect = 'none'"),
    CheckConstraint("erp_write = 0"),
    UniqueConstraint("created_by_user_id", "idempotency_key"),
)


# --- document_intelligence module (phase 2) -------------------------------
#
# document_intelligence.db was actually split across two physical SQLite
# files by a path-resolution bug (see the migration script for the full
# explanation) - doc_jobs/doc_results/doc_processing_runs lived in one file,
# payer_customer_mapping/manual_enterprise_groups/manual_enterprise_group_
# members in the other. Consolidating into one shared MySQL schema resolves
# that split as a side effect. extraction_json/parsed_json/comparison_json
# measured up to ~640KB in real data - well past MySQL's 64KB TEXT cap - so
# they use _LARGE_JSON_TYPE (LONGTEXT) like payment_notes/financial_close.

doc_jobs_table = Table(
    "doc_jobs",
    metadata,
    Column("job_id", String(64), primary_key=True),
    Column("original_file_name", String(255), nullable=False),
    Column("stored_file_name", String(255), nullable=False),
    Column("stored_path", String(1024), nullable=False),
    Column("content_type", String(64), nullable=False),
    Column("file_size_bytes", BigInteger, nullable=False),
    Column("document_type", String(64), nullable=False),
    Column("confidence", Float, nullable=False),
    Column("status", String(32), nullable=False),
    Column("message", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    Column("source_sha256", String(64), nullable=True),
    Column("intake_document_type", String(64), nullable=True),
    Column("intake_source", String(64), nullable=True),
    Column("duplicate_of_job_id", String(64), nullable=True),
    Index("idx_doc_jobs_type_status", "document_type", "status", "created_at"),
    Index("idx_doc_jobs_source_hash", "source_sha256", "created_at"),
)

doc_results_table = Table(
    "doc_results",
    metadata,
    Column("job_id", String(64), ForeignKey("doc_jobs.job_id"), primary_key=True),
    Column("classifier", String(64), nullable=False),
    Column("classification_evidence", Text, nullable=False),
    Column("extraction_json", _LARGE_JSON_TYPE, nullable=False),
    Column("parsed_json", _LARGE_JSON_TYPE, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    Column("processing_run_id", String(64), nullable=True),
    Column("processing_run_number", Integer, nullable=True),
    Column("processor_version", String(64), nullable=True),
    Column("source_sha256", String(64), nullable=True),
)

doc_processing_runs_table = Table(
    "doc_processing_runs",
    metadata,
    Column("processing_run_id", String(64), primary_key=True),
    Column("job_id", String(64), ForeignKey("doc_jobs.job_id"), nullable=False),
    Column("run_number", Integer, nullable=False),
    Column("processor_version", String(64), nullable=False),
    Column("source_sha256", String(64), nullable=True),
    Column("status", String(16), nullable=False),
    Column("classifier", String(64), nullable=True),
    Column("classification_evidence", Text, nullable=False),
    Column("extraction_json", _LARGE_JSON_TYPE, nullable=False),
    Column("parsed_json", _LARGE_JSON_TYPE, nullable=False),
    Column("message", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("completed_at", String(64), nullable=False),
    CheckConstraint("run_number > 0"),
    CheckConstraint("status IN ('completed', 'failed')"),
    UniqueConstraint("job_id", "run_number"),
    Index("idx_doc_runs_job", "job_id", "run_number"),
)

payer_customer_mapping_table = Table(
    "payer_customer_mapping",
    metadata,
    Column("mapping_id", _SEQUENCE_TYPE, primary_key=True, autoincrement=True),
    Column("routing_number", String(64), nullable=False, server_default=""),
    Column("bank_account_last4", String(16), nullable=False, server_default=""),
    Column("normalized_payer_name", String(255), nullable=False, server_default=""),
    Column("customer_number", String(64), nullable=False),
    Column("confidence", Float, nullable=False),
    Column("confirmed_by_user", Integer, nullable=False, server_default="0"),
    Column("first_seen_at", String(64), nullable=False),
    Column("last_seen_at", String(64), nullable=False),
    UniqueConstraint(
        "routing_number", "bank_account_last4", "normalized_payer_name"
    ),
)

manual_enterprise_groups_table = Table(
    "manual_enterprise_groups",
    metadata,
    Column("group_id", _SEQUENCE_TYPE, primary_key=True, autoincrement=True),
    Column("created_by", String(255), nullable=False, server_default=""),
    Column("created_at", String(64), nullable=False),
)

manual_enterprise_group_members_table = Table(
    "manual_enterprise_group_members",
    metadata,
    Column(
        "group_id",
        _SEQUENCE_TYPE,
        ForeignKey("manual_enterprise_groups.group_id"),
        nullable=False,
    ),
    Column("customer_number", String(64), nullable=False, unique=True),
    Column("added_by", String(255), nullable=False, server_default=""),
    Column("added_at", String(64), nullable=False),
)

customer_payment_behavior_table = Table(
    "customer_payment_behavior",
    metadata,
    Column("behavior_id", _SEQUENCE_TYPE, primary_key=True, autoincrement=True),
    Column("customer_number", String(64), nullable=False),
    Column("pattern_type", String(64), nullable=False),
    Column("pattern_key", String(255), nullable=False),
    Column("observation_count", Integer, nullable=False, server_default="0"),
    Column("success_count", Integer, nullable=False, server_default="0"),
    Column("first_observed_at", String(64), nullable=False),
    Column("last_observed_at", String(64), nullable=False),
    UniqueConstraint("customer_number", "pattern_type", "pattern_key"),
)

document_training_sessions_table = Table(
    "document_training_sessions",
    metadata,
    Column("session_id", String(64), primary_key=True),
    Column("job_id", String(64), nullable=False),
    Column("dataset_type", String(64), nullable=False),
    Column("source_pdf_name", String(255), nullable=False),
    Column("ground_truth_file_name", String(255), nullable=False),
    Column("ground_truth_path", String(1024), nullable=False),
    Column("status", String(32), nullable=False),
    Column("metrics_json", Text, nullable=False),
    Column("comparison_json", _LARGE_JSON_TYPE, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    Index("idx_training_job_id", "job_id"),
)

document_learning_examples_table = Table(
    "document_learning_examples",
    metadata,
    Column("id", _SEQUENCE_TYPE, primary_key=True, autoincrement=True),
    Column("job_id", String(64), nullable=False),
    Column("document_type", String(64), nullable=False),
    Column("field_name", String(64), nullable=False),
    Column("original_value_json", Text, nullable=False),
    Column("corrected_value_json", Text, nullable=False),
    Column("reviewer", String(255), nullable=False, server_default=""),
    Column("source_status", String(64), nullable=False),
    Column("fingerprint", String(64), nullable=False, unique=True),
    Column("created_at", String(64), nullable=False),
    Index("idx_learning_job", "job_id"),
    Index("idx_learning_field", "field_name"),
)

document_reviews_table = Table(
    "document_reviews",
    metadata,
    Column("job_id", String(64), ForeignKey("doc_jobs.job_id"), primary_key=True),
    Column("status", String(32), nullable=False, server_default="pending"),
    Column("reviewer", String(255), nullable=False, server_default=""),
    Column("notes", Text, nullable=False),
    Column("corrected_fields_json", Text, nullable=False),
    Column("processing_run_id", String(64), nullable=True),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
)

document_review_history_table = Table(
    "document_review_history",
    metadata,
    Column("id", _SEQUENCE_TYPE, primary_key=True, autoincrement=True),
    Column("job_id", String(64), ForeignKey("doc_jobs.job_id"), nullable=False),
    Column("status", String(32), nullable=False),
    Column("reviewer", String(255), nullable=False, server_default=""),
    Column("notes", Text, nullable=False),
    Column("corrected_fields_json", Text, nullable=False),
    Column("processing_run_id", String(64), nullable=True),
    Column("created_at", String(64), nullable=False),
    Index("idx_review_history_job_id", "job_id", "created_at"),
)

# --- legacy lockbox_learning.db (lockbox_service.py) ----------------------

lockbox_reviews_table = Table(
    "lockbox_reviews",
    metadata,
    Column("job_id", String(64), primary_key=True),
    Column("transaction_id", String(64), primary_key=True),
    Column("review_json", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
)

lockbox_customer_profiles_table = Table(
    "lockbox_customer_profiles",
    metadata,
    Column("profile_id", _SEQUENCE_TYPE, primary_key=True, autoincrement=True),
    Column("customer_name", String(255), nullable=False),
    Column("customer_phone", String(64), nullable=False, server_default=""),
    Column("customer_address_line_1", String(255), nullable=False, server_default=""),
    Column("customer_address_line_2", String(255), nullable=False, server_default=""),
    Column("customer_city", String(255), nullable=False, server_default=""),
    Column("customer_state", String(64), nullable=False, server_default=""),
    Column("customer_postal_code", String(32), nullable=False, server_default=""),
    Column("aba_routing", String(64), nullable=False, server_default=""),
    Column("account_number", String(64), nullable=False, server_default=""),
    Column("times_confirmed", Integer, nullable=False, server_default="1"),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    Index("idx_lockbox_customer_profiles_bank", "aba_routing", "account_number"),
)

# --- lockbox_review.db (lockbox_review/database.py) -----------------------
#
# original_allocations_json measured up to 64,187 bytes in real data - right
# at MySQL's 65,535-byte plain-TEXT edge - so both allocation JSON columns
# use _LARGE_JSON_TYPE for headroom.

lockbox_transaction_reviews_table = Table(
    "lockbox_transaction_reviews",
    metadata,
    Column("job_id", String(64), primary_key=True),
    Column("transaction_id", String(64), primary_key=True),
    Column("original_allocations_json", _LARGE_JSON_TYPE, nullable=False),
    Column("allocations_json", _LARGE_JSON_TYPE, nullable=False),
    Column("customer_json", Text, nullable=False),
    Column("status", String(32), nullable=False),
    Column("reviewer", String(255), nullable=False, server_default=""),
    Column("notes", Text, nullable=False),
    Column("override_reason", Text, nullable=False),
    Column("misc_gl_json", Text, nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    Index("idx_lockbox_transaction_reviews_job", "job_id"),
)

lockbox_customer_notes_table = Table(
    "lockbox_customer_notes",
    metadata,
    Column("note_id", _SEQUENCE_TYPE, primary_key=True, autoincrement=True),
    Column("customer_number", String(64), nullable=False),
    Column("customer_name", String(255), nullable=False, server_default=""),
    Column("body", Text, nullable=False),
    Column("author", String(255), nullable=False),
    Column("source_job_id", String(64), nullable=False),
    Column("source_transaction_id", String(64), nullable=False),
    Column("source_check_number", String(64), nullable=False, server_default=""),
    Column("created_at", String(64), nullable=False),
    Index(
        "idx_lockbox_customer_notes_customer_created",
        "customer_number",
        "created_at",
        "note_id",
    ),
)

# --- invoice_owner_cache.db (integrations/invoice_owner_cache.py) --------
#
# A plain wholesale-replaceable cache (~257k rows), not an append-only
# ledger - each refresh discards the prior snapshot entirely and bulk-
# inserts the new one, so the migration/refresh code uses batched
# executemany-style inserts rather than the row-by-row check-then-insert
# pattern used elsewhere in this schema.

invoice_owner_cache_table = Table(
    "invoice_owner_cache",
    metadata,
    Column("invoice_number", String(32), primary_key=True),
    Column("customer_numbers", String(255), nullable=False),
    Column("refreshed_at", String(64), nullable=False),
)

invoice_owner_cache_metadata_table = Table(
    "invoice_owner_cache_metadata",
    metadata,
    Column("meta_key", String(64), primary_key=True),
    Column("meta_value", Text, nullable=False),
)

# --- lockbox_preparation.db (lockbox_preparation/repository.py) -----------
#
# preparation_schema (a singleton row tracking an in-place SQLite schema
# version, used only to drive the old ALTER-TABLE-based v2->v3 migration)
# is omitted entirely - MySQL always gets the current schema directly, the
# same "moot" treatment as every other in-place SQLite migration in this
# project. result_json/payload_json measured up to ~7.25MB in real data,
# so those (and source_json, which measured up to ~263KB) use
# _LARGE_JSON_TYPE (LONGTEXT). preparation_events.event_id is a genuine
# ordering dependency (events are always read `ORDER BY event_id`), so it
# gets the usual auto-increment `sequence`-style treatment already used
# elsewhere for the same reason - just named event_id here directly since
# nothing else needs the raw TEXT id this table never had in the first
# place.

lockbox_preparation_jobs_table = Table(
    "lockbox_preparation_jobs",
    metadata,
    Column("job_id", String(64), primary_key=True),
    Column("source_job_id", String(64), nullable=False),
    Column("source_file_hash", String(64), nullable=False),
    Column("source_reference", String(255), nullable=False, server_default=""),
    Column("correlation_id", String(64), nullable=False),
    Column("idempotency_key", String(255), nullable=False, unique=True),
    Column("request_fingerprint", String(64), nullable=False, server_default=""),
    Column("preparation_generation", Integer, nullable=False, server_default="1"),
    Column("state", String(32), nullable=False),
    Column("expected_count", Integer, nullable=False),
    Column("terminal_count", Integer, nullable=False, server_default="0"),
    Column("balanced_count", Integer, nullable=False, server_default="0"),
    Column("exception_count", Integer, nullable=False, server_default="0"),
    Column("preserved_count", Integer, nullable=False, server_default="0"),
    Column("rule_version", String(128), nullable=False),
    Column("service_version", String(128), nullable=False),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    Column("started_at", String(64), nullable=True),
    Column("completed_at", String(64), nullable=True),
    UniqueConstraint("source_job_id", "source_file_hash", "rule_version"),
)

lockbox_preparation_transactions_table = Table(
    "lockbox_preparation_transactions",
    metadata,
    Column(
        "job_id",
        String(64),
        ForeignKey("lockbox_preparation_jobs.job_id"),
        primary_key=True,
    ),
    Column("transaction_id", String(64), primary_key=True),
    Column("ordinal", Integer, nullable=False),
    Column("state", String(32), nullable=False),
    Column("attempt_count", Integer, nullable=False, server_default="0"),
    Column("retry_eligible", Integer, nullable=False, server_default="0"),
    Column("source_json", _LARGE_JSON_TYPE, nullable=False),
    Column("source_hash", String(64), nullable=False, server_default=""),
    Column(
        "extraction_version", String(64), nullable=False, server_default="unknown"
    ),
    Column("result_json", _LARGE_JSON_TYPE, nullable=True),
    Column("error_json", Text, nullable=True),
    Column("created_at", String(64), nullable=False),
    Column("updated_at", String(64), nullable=False),
    Column("started_at", String(64), nullable=True),
    Column("completed_at", String(64), nullable=True),
    UniqueConstraint("job_id", "ordinal"),
    Index("idx_lockbox_preparation_transactions_state", "job_id", "state", "ordinal"),
)

lockbox_preparation_events_table = Table(
    "lockbox_preparation_events",
    metadata,
    Column("event_id", _SEQUENCE_TYPE, primary_key=True, autoincrement=True),
    Column(
        "job_id", String(64), ForeignKey("lockbox_preparation_jobs.job_id"), nullable=False
    ),
    Column("transaction_id", String(64), nullable=True),
    Column("event_type", String(64), nullable=False),
    Column("from_state", String(32), nullable=True),
    Column("to_state", String(32), nullable=True),
    Column("payload_json", _LARGE_JSON_TYPE, nullable=False),
    Column("occurred_at", String(64), nullable=False),
    Index("idx_lockbox_preparation_events_job", "job_id", "event_id"),
)


_engine: Engine | None = None
_engine_override: Engine | None = None


def _build_engine() -> Engine:
    required = {
        "host": os.getenv("ETOP_DB_HOST"),
        "database": os.getenv("ETOP_DB_NAME"),
        "user": os.getenv("ETOP_DB_USER"),
        "password": os.getenv("ETOP_DB_PASSWORD"),
    }

    missing = [
        key.upper()
        for key, value in required.items()
        if value is None or not value.strip()
    ]

    if missing:
        raise RuntimeError(
            "Missing ETOP_DB settings in backend/.env: "
            + ", ".join(f"ETOP_DB_{name}" for name in missing)
        )

    port = os.getenv("ETOP_DB_PORT", "3306")

    url = (
        "mysql+mysqlconnector://"
        f"{required['user']}:{required['password']}@"
        f"{required['host']}:{port}/{required['database']}"
        "?charset=utf8mb4"
    )

    return create_engine(url, pool_pre_ping=True, pool_recycle=1800)


def get_engine() -> Engine:
    """Returns the shared app-database engine, honoring a test override."""

    if _engine_override is not None:
        return _engine_override

    global _engine
    if _engine is None:
        _engine = _build_engine()

    return _engine


def _set_engine_override(engine: Engine) -> None:
    """Test hook: redirect the app database at a different engine."""

    global _engine_override
    _engine_override = engine


def _reset_engine_override() -> None:
    """Test hook: restore the real (MySQL) engine."""

    global _engine_override
    _engine_override = None


# --- append-only enforcement ---------------------------------------------
#
# SQLite originally enforced append-only tables (wf_role_assignments,
# wf_module_access_events, wf_invitation_events, wf_password_reset_events,
# wf_task_assignments, wf_task_events, wf_audit_events - and the same
# pattern in later-converted modules) with BEFORE UPDATE/DELETE triggers.
# MySQL triggers need SUPER or log_bin_trust_function_creators=1 to create
# under binary logging, and the etop DB account doesn't have that - so by
# explicit decision, append-only-ness is enforced by convention in the
# repository layer instead (these tables are only ever INSERTed into,
# never UPDATEd/DELETEd). This is a weaker guarantee than a DB trigger -
# it does not stop a direct SQL client or a future bug in this codebase -
# so any repository code touching these tables must not add UPDATE/DELETE
# statements against them.
