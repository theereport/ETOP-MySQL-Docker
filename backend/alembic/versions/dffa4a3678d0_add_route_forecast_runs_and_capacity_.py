"""add route forecast runs and capacity assessments tables

Revision ID: dffa4a3678d0
Revises: 22647337aa92
Create Date: 2026-09-04 19:20:23.472785

RI-3: two new tables for the manual-trigger capacity forecast. route_
forecast_runs is one row per POST /forecast/compute call (metadata only:
when, how many weeks of history, how many warehouses, success/failure).
route_capacity_assessments is the latest computed day-of-week demand
forecast vs. fleet weight capacity per warehouse, one row per
(warehouse_number, day_of_week), upserted on every run rather than
accumulating unbounded history - see route_intelligence/service.py's
compute_capacity_forecast(). Plain CREATE only, mirrors data/mysql.py
1:1 - no autogenerate trimming needed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dffa4a3678d0'
down_revision: Union[str, Sequence[str], None] = '22647337aa92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'route_forecast_runs',
        sa.Column('run_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('run_at', sa.String(length=64), nullable=False),
        sa.Column('weeks_of_history', sa.Integer(), nullable=False),
        sa.Column('warehouse_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('status', sa.String(length=32), server_default='', nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('run_id'),
    )

    op.create_table(
        'route_capacity_assessments',
        sa.Column('warehouse_number', sa.Integer(), nullable=False),
        sa.Column('day_of_week', sa.String(length=16), nullable=False),
        sa.Column('forecast_run_id', sa.BigInteger(), nullable=True),
        sa.Column('sample_size', sa.Integer(), server_default='0', nullable=False),
        sa.Column('expected_weight', sa.Float(), nullable=True),
        sa.Column('expected_quantity', sa.Float(), nullable=True),
        sa.Column('expected_stops', sa.Float(), nullable=True),
        sa.Column('p50_weight', sa.Float(), nullable=True),
        sa.Column('p80_weight', sa.Float(), nullable=True),
        sa.Column('p90_weight', sa.Float(), nullable=True),
        sa.Column('weight_capacity', sa.Float(), nullable=True),
        sa.Column('p90_utilization_pct', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=32), server_default='', nullable=False),
        sa.Column('structural_review', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('computed_at', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['forecast_run_id'], ['route_forecast_runs.run_id']),
        sa.PrimaryKeyConstraint('warehouse_number', 'day_of_week'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('route_capacity_assessments')
    op.drop_table('route_forecast_runs')
