"""target reported_at for first-class phish reporting

Revision ID: c41d5e7f9a20
Revises: 7b5fd8786c85
Create Date: 2026-11-25 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c41d5e7f9a20'
down_revision: Union[str, Sequence[str], None] = '7b5fd8786c85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # A legacy create_all database may already have this column.
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("target")}
    if "reported_at" not in columns:
        with op.batch_alter_table('target', schema=None) as batch_op:
            batch_op.add_column(sa.Column('reported_at', sa.DateTime(), nullable=True))
    # Backfill from existing human report events (first one per recipient).
    op.execute(
        "UPDATE target SET reported_at = ("
        " SELECT MIN(event.created_at) FROM event"
        " WHERE event.target_id = target.id"
        " AND event.type = 'REPORT' AND event.verdict = 'HUMAN')"
        " WHERE reported_at IS NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('target', schema=None) as batch_op:
        batch_op.drop_column('reported_at')
