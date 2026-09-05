"""add route plan decisions table

Revision ID: d9eded84a104
Revises: bbf2098210df
Create Date: 2026-09-05 08:20:34.521638

RI-5: dispatcher approval workflow over RI-4's optimization runs.
route_plan_decisions is append-only (every decision inserts a new row,
none are ever updated/deleted) - a run's current decision is just its
latest row. decided_by is free text, not a verified identity - see
route_intelligence/service.py's decide_optimization_run() docstring for
why. Plain CREATE only, mirrors data/mysql.py 1:1 - no autogenerate
trimming needed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9eded84a104'
down_revision: Union[str, Sequence[str], None] = 'bbf2098210df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'route_plan_decisions',
        sa.Column('decision_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.BigInteger(), nullable=False),
        sa.Column('decision', sa.String(length=32), nullable=False),
        sa.Column('decided_by', sa.String(length=200), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('modification_notes', sa.Text(), nullable=True),
        sa.Column('decided_at', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['route_optimization_runs.run_id']),
        sa.PrimaryKeyConstraint('decision_id'),
    )
    op.create_index(
        'idx_route_plan_decisions_run', 'route_plan_decisions',
        ['run_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_route_plan_decisions_run', table_name='route_plan_decisions')
    op.drop_table('route_plan_decisions')
