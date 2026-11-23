"""campaign email template fields

Adds the drill-template columns to the campaign table:
  template_slug, body, cta_label, red_flags_json.

Revision ID: 7b5fd8786c85
Revises: 3e27f7f0caf8
Create Date: 2026-11-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7b5fd8786c85'
down_revision: Union[str, Sequence[str], None] = '3e27f7f0caf8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('campaign', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'template_slug', sqlmodel.sql.sqltypes.AutoString(),
            nullable=False, server_default=''))
        batch_op.add_column(sa.Column(
            'body', sqlmodel.sql.sqltypes.AutoString(),
            nullable=False, server_default=''))
        batch_op.add_column(sa.Column(
            'cta_label', sqlmodel.sql.sqltypes.AutoString(),
            nullable=False, server_default=''))
        batch_op.add_column(sa.Column(
            'red_flags_json', sqlmodel.sql.sqltypes.AutoString(),
            nullable=False, server_default='[]'))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('campaign', schema=None) as batch_op:
        batch_op.drop_column('red_flags_json')
        batch_op.drop_column('cta_label')
        batch_op.drop_column('body')
        batch_op.drop_column('template_slug')
