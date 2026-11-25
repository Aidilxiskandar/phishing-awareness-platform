"""campaign email template fields

Adds the drill-template columns to the campaign table:
  template_slug, body, cta_label, red_flags_json.

Revision ID: 7b5fd8786c85
Revises: b7c1d2e3f4a5
Create Date: 2026-11-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7b5fd8786c85'
down_revision: Union[str, Sequence[str], None] = 'b7c1d2e3f4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # A legacy create_all database may already have some or all of these columns.
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("campaign")}
    wanted = [
        ("template_slug", ""),
        ("body", ""),
        ("cta_label", ""),
        ("red_flags_json", "[]"),
    ]
    missing = [(name, default) for name, default in wanted if name not in existing]
    if not missing:
        return
    with op.batch_alter_table('campaign', schema=None) as batch_op:
        for name, default in missing:
            batch_op.add_column(sa.Column(
                name, sqlmodel.sql.sqltypes.AutoString(),
                nullable=False, server_default=default))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('campaign', schema=None) as batch_op:
        batch_op.drop_column('red_flags_json')
        batch_op.drop_column('cta_label')
        batch_op.drop_column('body')
        batch_op.drop_column('template_slug')
