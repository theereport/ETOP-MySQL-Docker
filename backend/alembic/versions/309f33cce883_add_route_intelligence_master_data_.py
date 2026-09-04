"""add route_intelligence master data tables

Revision ID: 309f33cce883
Revises: 7d6d4005afa5
Create Date: 2026-09-04 08:54:42.902558

Plain CREATE TABLE statements only (no autogenerate trimming needed - see
7d6d4005afa5's docstring for why autogenerate is otherwise avoided in this
repo). Mirrors data/mysql.py's route_intelligence table definitions 1:1.
Warehouses and routes themselves are NOT created here - they already live
in MaddenCo and are read through the freight_logistics module.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '309f33cce883'
down_revision: Union[str, Sequence[str], None] = '7d6d4005afa5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'route_customer_profiles',
        sa.Column('customer_number', sa.String(length=64), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('receiving_window_start', sa.String(length=16), server_default='', nullable=False),
        sa.Column('receiving_window_end', sa.String(length=16), server_default='', nullable=False),
        # MySQL rejects a server_default on TEXT/BLOB columns.
        sa.Column('closed_days_json', sa.Text(), nullable=False),
        sa.Column('preferred_delivery_days_json', sa.Text(), nullable=False),
        sa.Column('priority', sa.String(length=32), server_default='', nullable=False),
        sa.Column('normal_unloading_minutes', sa.Float(), nullable=True),
        sa.Column('vehicle_access_restrictions', sa.Text(), nullable=False),
        sa.Column('delivery_instructions', sa.Text(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.String(length=64), nullable=False),
        sa.Column('updated_by', sa.String(length=255), server_default='', nullable=False),
        sa.PrimaryKeyConstraint('customer_number'),
    )

    op.create_table(
        'route_vehicles',
        sa.Column('vehicle_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('unit_number', sa.String(length=64), nullable=False),
        sa.Column('vehicle_type', sa.String(length=64), server_default='', nullable=False),
        sa.Column('home_warehouse_number', sa.Integer(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('vehicle_id'),
    )
    op.create_index(
        'idx_route_vehicles_warehouse', 'route_vehicles',
        ['home_warehouse_number'], unique=False,
    )

    op.create_table(
        'route_vehicle_capacities',
        sa.Column('capacity_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('vehicle_id', sa.BigInteger(), nullable=False),
        sa.Column('weight_capacity', sa.Float(), nullable=True),
        sa.Column('cube_capacity', sa.Float(), nullable=True),
        sa.Column('tire_equivalent_capacity', sa.Float(), nullable=True),
        sa.Column('max_stops', sa.Integer(), nullable=True),
        sa.Column('effective_date', sa.String(length=32), server_default='', nullable=False),
        sa.ForeignKeyConstraint(['vehicle_id'], ['route_vehicles.vehicle_id']),
        sa.PrimaryKeyConstraint('capacity_id'),
    )
    op.create_index(
        'idx_route_vehicle_capacities_vehicle', 'route_vehicle_capacities',
        ['vehicle_id'], unique=False,
    )

    op.create_table(
        'route_drivers',
        sa.Column('driver_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('home_warehouse_number', sa.Integer(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('qualifications', sa.Text(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('driver_id'),
    )
    op.create_index(
        'idx_route_drivers_warehouse', 'route_drivers',
        ['home_warehouse_number'], unique=False,
    )

    op.create_table(
        'route_driver_availability',
        sa.Column('availability_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('driver_id', sa.BigInteger(), nullable=False),
        sa.Column('day_of_week', sa.String(length=16), nullable=False),
        sa.Column('available', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('shift_start', sa.String(length=16), server_default='', nullable=False),
        sa.Column('shift_end', sa.String(length=16), server_default='', nullable=False),
        sa.ForeignKeyConstraint(['driver_id'], ['route_drivers.driver_id']),
        sa.PrimaryKeyConstraint('availability_id'),
    )
    op.create_index(
        'idx_route_driver_availability_driver', 'route_driver_availability',
        ['driver_id'], unique=False,
    )

    op.create_table(
        'route_business_rules',
        sa.Column('rule_key', sa.String(length=128), nullable=False),
        sa.Column('rule_value', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.String(length=64), nullable=False),
        sa.Column('updated_by', sa.String(length=255), server_default='', nullable=False),
        sa.PrimaryKeyConstraint('rule_key'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('route_business_rules')
    op.drop_index('idx_route_driver_availability_driver', table_name='route_driver_availability')
    op.drop_table('route_driver_availability')
    op.drop_index('idx_route_drivers_warehouse', table_name='route_drivers')
    op.drop_table('route_drivers')
    op.drop_index('idx_route_vehicle_capacities_vehicle', table_name='route_vehicle_capacities')
    op.drop_table('route_vehicle_capacities')
    op.drop_index('idx_route_vehicles_warehouse', table_name='route_vehicles')
    op.drop_table('route_vehicles')
    op.drop_table('route_customer_profiles')
