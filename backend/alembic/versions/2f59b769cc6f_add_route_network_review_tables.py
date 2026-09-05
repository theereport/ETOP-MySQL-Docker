"""add route network review tables

Revision ID: 2f59b769cc6f
Revises: d9eded84a104
Create Date: 2026-09-05 09:04:39.082761

RI-8: permanent-route candidate detection over RI-3's already-stored
route_capacity_assessments - no new external calls. route_network_reviews
is one row per POST /network-review/compute call (metadata: how many
warehouses scanned, how many candidates found, success/failure).
route_permanent_route_candidates is one row per warehouse that triggered
a structural-review condition in a given run - see
route_intelligence/service.py's compute_network_review(). Plain CREATE
only, mirrors data/mysql.py 1:1 - no autogenerate trimming needed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2f59b769cc6f'
down_revision: Union[str, Sequence[str], None] = 'd9eded84a104'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'route_network_reviews',
        sa.Column('run_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('run_at', sa.String(length=64), nullable=False),
        sa.Column('warehouse_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('candidate_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('status', sa.String(length=32), server_default='', nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('run_id'),
    )

    op.create_table(
        'route_permanent_route_candidates',
        sa.Column('candidate_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.BigInteger(), nullable=False),
        sa.Column('warehouse_number', sa.Integer(), nullable=False),
        sa.Column('trigger_reasons_json', sa.Text(), nullable=False),
        sa.Column('median_utilization_pct', sa.Float(), nullable=True),
        sa.Column('days_over_median_threshold', sa.Integer(), server_default='0', nullable=False),
        sa.Column('days_over_p90_threshold', sa.Integer(), server_default='0', nullable=False),
        sa.Column('forecasted_weekly_weight_demand', sa.Float(), nullable=True),
        sa.Column('current_weight_capacity', sa.Float(), nullable=True),
        sa.Column('capacity_gap', sa.Float(), nullable=True),
        sa.Column('confidence', sa.String(length=16), server_default='', nullable=False),
        sa.Column('unavailable_fields_json', sa.Text(), nullable=False),
        sa.Column('computed_at', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['route_network_reviews.run_id']),
        sa.PrimaryKeyConstraint('candidate_id'),
    )
    op.create_index(
        'idx_route_permanent_route_candidates_run', 'route_permanent_route_candidates',
        ['run_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'idx_route_permanent_route_candidates_run',
        table_name='route_permanent_route_candidates',
    )
    op.drop_table('route_permanent_route_candidates')
    op.drop_table('route_network_reviews')
