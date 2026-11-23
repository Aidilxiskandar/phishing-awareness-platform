"""training module sources (further reading / videos)

Revision ID: b7c1d2e3f4a5
Revises: 3e27f7f0caf8
Create Date: 2026-11-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c1d2e3f4a5'
down_revision: Union[str, Sequence[str], None] = '3e27f7f0caf8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # A legacy create_all database may already have this column.
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("trainingmodule")}
    if "sources_json" in columns:
        return
    with op.batch_alter_table('trainingmodule', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sources_json', sa.String(), nullable=False,
                                      server_default='[]'))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('trainingmodule', schema=None) as batch_op:
        batch_op.drop_column('sources_json')
