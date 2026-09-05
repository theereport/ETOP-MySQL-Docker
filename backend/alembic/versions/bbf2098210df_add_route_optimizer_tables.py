"""add route optimizer tables

Revision ID: bbf2098210df
Revises: dffa4a3678d0
Create Date: 2026-09-04 20:15:01.548363

RI-4: three new tables for the manual-trigger route optimizer.
route_warehouse_locations is manual-entry depot coordinates (MaddenCo's
own warehouse master has no lat/lon column at all - confirmed live).
route_optimization_runs is one row per POST /optimize/compute call
(metadata: warehouse, target date, readiness counts, success/failure).
route_optimization_plans is one row per vehicle-slot route per scenario
(baseline vs. with_backup) within a run - see
route_intelligence/service.py's compute_route_optimization(). Plain
CREATE only, mirrors data/mysql.py 1:1 - no autogenerate trimming
needed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bbf2098210df'
down_revision: Union[str, Sequence[str], None] = 'dffa4a3678d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'route_warehouse_locations',
        sa.Column('warehouse_number', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('updated_at', sa.String(length=64), nullable=False),
        sa.Column('updated_by', sa.String(length=255), server_default='', nullable=False),
        sa.PrimaryKeyConstraint('warehouse_number'),
    )

    op.create_table(
        'route_optimization_runs',
        sa.Column('run_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('run_at', sa.String(length=64), nullable=False),
        sa.Column('warehouse_number', sa.Integer(), nullable=False),
        sa.Column('target_date', sa.String(length=32), nullable=False),
        sa.Column('customer_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('customers_with_location_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('vehicle_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('vehicles_with_capacity_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('status', sa.String(length=32), server_default='', nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('run_id'),
    )
    op.create_index(
        'idx_route_optimization_runs_warehouse', 'route_optimization_runs',
        ['warehouse_number'], unique=False,
    )

    op.create_table(
        'route_optimization_plans',
        sa.Column('plan_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.BigInteger(), nullable=False),
        sa.Column('scenario', sa.String(length=32), nullable=False),
        sa.Column('vehicle_slot', sa.Integer(), nullable=False),
        sa.Column('assigned_vehicle_id', sa.BigInteger(), nullable=True),
        sa.Column('stop_sequence_json', sa.Text(), nullable=False),
        sa.Column('stop_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('total_distance_miles', sa.Float(), nullable=True),
        sa.Column('total_time_minutes', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['route_optimization_runs.run_id']),
        sa.ForeignKeyConstraint(['assigned_vehicle_id'], ['route_vehicles.vehicle_id']),
        sa.PrimaryKeyConstraint('plan_id'),
    )
    op.create_index(
        'idx_route_optimization_plans_run', 'route_optimization_plans',
        ['run_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_route_optimization_plans_run', table_name='route_optimization_plans')
    op.drop_table('route_optimization_plans')
    op.drop_index('idx_route_optimization_runs_warehouse', table_name='route_optimization_runs')
    op.drop_table('route_optimization_runs')
    op.drop_table('route_warehouse_locations')
