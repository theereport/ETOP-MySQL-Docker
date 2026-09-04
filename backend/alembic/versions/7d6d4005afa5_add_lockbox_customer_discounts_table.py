"""add lockbox_customer_discounts table

Revision ID: 7d6d4005afa5
Revises: a38d38714da8
Create Date: 2026-09-04 07:24:13.137081

Brand-new table backing the 2026-09-03 discount-customer rework (see
data/mysql.py's lockbox_customer_discounts_table) - unlike the previous
migration this needed no trimming, since a plain CREATE TABLE has nothing
for --autogenerate to confuse with an unrelated CHECK constraint.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d6d4005afa5'
down_revision: Union[str, Sequence[str], None] = 'a38d38714da8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'lockbox_customer_discounts',
        sa.Column('customer_number', sa.String(length=64), nullable=False),
        sa.Column(
            'is_discount_customer',
            sa.Boolean(),
            server_default='0',
            nullable=False,
        ),
        sa.Column(
            'discount_percent',
            sa.Float(),
            server_default='0',
            nullable=False,
        ),
        sa.Column(
            'updated_by',
            sa.String(length=255),
            server_default='',
            nullable=False,
        ),
        sa.Column('updated_at', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('customer_number'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('lockbox_customer_discounts')
