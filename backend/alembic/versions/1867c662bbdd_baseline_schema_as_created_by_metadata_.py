"""baseline: schema as created by metadata.create_all

Revision ID: 1867c662bbdd
Revises:
Create Date: 2026-09-01 11:28:58.867098

Intentionally empty. Every table in this schema was already created before
Alembic was adopted (via `metadata.create_all(checkfirst=True)`, called from
each module's own `initialize_database()`). This revision exists only so a
real database can be `alembic stamp head`-ed onto it - marking "everything
before this point is out of Alembic's hands" - without alembic trying to
recreate or alter anything that already exists.

Do NOT `alembic upgrade head` a brand-new/empty database expecting this to
create the schema - it won't. A fresh database still needs the app's own
`initialize_database()` calls (or `metadata.create_all`) to get the initial
87 tables; only schema *changes* from here forward go through Alembic.

Note for future `alembic revision --autogenerate` runs: many tables have
CheckConstraint objects defined without an explicit `name=`, so MySQL
auto-assigns names like `sometable_chk_3`. Alembic can't correlate those to
the unnamed Python-side constraint and will propose dropping/recreating
every one of them as noise on every autogenerate diff. Review generated
migrations for genuine, intended changes and discard the `chk_N`
drop/create pairs rather than committing them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1867c662bbdd'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
