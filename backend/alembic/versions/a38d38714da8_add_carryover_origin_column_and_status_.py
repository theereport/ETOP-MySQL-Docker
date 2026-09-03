"""add carryover_origin column and status index to lockbox_transaction_reviews

Revision ID: a38d38714da8
Revises: 1867c662bbdd
Create Date: 2026-09-02 23:00:13.948385

Hand-trimmed: --autogenerate also proposed dropping and recreating ~150
CHECK constraints across unrelated tables (wf_*, *_notes, pn_*, fc_*,
ap_*, credit_*, etc.). Those are real, meaningful constraints enforced in
the live database (separation-of-duties, hash-length, enum-value checks)
that simply aren't represented in this codebase's SQLAlchemy metadata - a
known, pre-existing mismatch, not something this change should touch.
Only the two operations below are the actual intended change.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a38d38714da8'
down_revision: Union[str, Sequence[str], None] = '1867c662bbdd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'lockbox_transaction_reviews',
        sa.Column(
            'carryover_origin',
            sa.Boolean(),
            server_default='0',
            nullable=False,
        ),
    )
    op.create_index(
        'idx_lockbox_transaction_reviews_status',
        'lockbox_transaction_reviews',
        ['status'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'idx_lockbox_transaction_reviews_status',
        table_name='lockbox_transaction_reviews',
    )
    op.drop_column('lockbox_transaction_reviews', 'carryover_origin')
