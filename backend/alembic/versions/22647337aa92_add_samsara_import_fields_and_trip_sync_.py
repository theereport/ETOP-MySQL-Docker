"""add samsara import fields and trip sync tables

Revision ID: 22647337aa92
Revises: 309f33cce883
Create Date: 2026-09-04 14:21:55.928850

RI-1: route_vehicles/route_drivers get samsara_vehicle_id/
samsara_driver_id + vin so they can be imported directly from the real
Samsara fleet (see route_intelligence/service.py's import_samsara_
vehicles/import_samsara_drivers). route_customer_profiles gets
samsara_address_id for the manual geofence-link action. Two new tables:
route_actual_runs (ingested Samsara trip history) and samsara_sync_state
(last-manual-sync record). Plain ALTER/CREATE only, mirrors data/mysql.py
1:1 - no autogenerate trimming needed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '22647337aa92'
down_revision: Union[str, Sequence[str], None] = '309f33cce883'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'route_customer_profiles',
        sa.Column('samsara_address_id', sa.String(length=64), nullable=True),
    )

    op.add_column(
        'route_vehicles',
        sa.Column('vin', sa.String(length=32), nullable=True),
    )
    op.add_column(
        'route_vehicles',
        sa.Column('samsara_vehicle_id', sa.String(length=64), nullable=True),
    )
    op.create_index(
        'idx_route_vehicles_samsara_id', 'route_vehicles',
        ['samsara_vehicle_id'], unique=False,
    )

    op.add_column(
        'route_drivers',
        sa.Column('samsara_driver_id', sa.String(length=64), nullable=True),
    )
    op.create_index(
        'idx_route_drivers_samsara_id', 'route_drivers',
        ['samsara_driver_id'], unique=False,
    )

    op.create_table(
        'route_actual_runs',
        sa.Column('run_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('samsara_trip_id', sa.String(length=64), nullable=False),
        sa.Column('vehicle_id', sa.BigInteger(), nullable=True),
        sa.Column('driver_id', sa.BigInteger(), nullable=True),
        sa.Column('start_time', sa.String(length=64), nullable=True),
        sa.Column('end_time', sa.String(length=64), nullable=True),
        sa.Column('start_latitude', sa.Float(), nullable=True),
        sa.Column('start_longitude', sa.Float(), nullable=True),
        sa.Column('end_latitude', sa.Float(), nullable=True),
        sa.Column('end_longitude', sa.Float(), nullable=True),
        sa.Column('distance_meters', sa.Float(), nullable=True),
        sa.Column('completion_status', sa.String(length=32), server_default='', nullable=False),
        sa.Column('ingested_at', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['vehicle_id'], ['route_vehicles.vehicle_id']),
        sa.ForeignKeyConstraint(['driver_id'], ['route_drivers.driver_id']),
        sa.PrimaryKeyConstraint('run_id'),
        sa.UniqueConstraint('samsara_trip_id'),
    )
    op.create_index(
        'idx_route_actual_runs_vehicle', 'route_actual_runs',
        ['vehicle_id'], unique=False,
    )
    op.create_index(
        'idx_route_actual_runs_start_time', 'route_actual_runs',
        ['start_time'], unique=False,
    )

    op.create_table(
        'samsara_sync_state',
        sa.Column('sync_key', sa.String(length=64), nullable=False),
        sa.Column('last_synced_through', sa.String(length=64), nullable=True),
        sa.Column('last_run_at', sa.String(length=64), nullable=True),
        sa.Column('last_run_status', sa.String(length=32), server_default='', nullable=False),
        sa.Column('last_run_message', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('sync_key'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('samsara_sync_state')
    op.drop_index('idx_route_actual_runs_start_time', table_name='route_actual_runs')
    op.drop_index('idx_route_actual_runs_vehicle', table_name='route_actual_runs')
    op.drop_table('route_actual_runs')
    op.drop_index('idx_route_drivers_samsara_id', table_name='route_drivers')
    op.drop_column('route_drivers', 'samsara_driver_id')
    op.drop_index('idx_route_vehicles_samsara_id', table_name='route_vehicles')
    op.drop_column('route_vehicles', 'samsara_vehicle_id')
    op.drop_column('route_vehicles', 'vin')
    op.drop_column('route_customer_profiles', 'samsara_address_id')
