"""add management token

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("links") as batch:
        # The server default fills existing rows: every existing link starts enabled.
        batch.add_column(
            sa.Column("is_disabled", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        # Existing links get NULL: they have no token, so they can't be managed via the API.
        batch.add_column(sa.Column("token_hash", sa.String(64), nullable=True))


def downgrade():
    with op.batch_alter_table("links") as batch:
        batch.drop_column("token_hash")
        batch.drop_column("is_disabled")
