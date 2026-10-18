"""add link expiry

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    # Nullable columns: existing links get NULL, meaning "no limit". No table rewrite needed.
    with op.batch_alter_table("links") as batch:
        batch.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("max_clicks", sa.Integer(), nullable=True))
        # Blocks writes while it builds: fine for a small table. A large production table
        # would use CREATE INDEX CONCURRENTLY (outside a transaction) instead.
        batch.create_index("ix_links_expires_at", ["expires_at"])


def downgrade():
    with op.batch_alter_table("links") as batch:
        batch.drop_index("ix_links_expires_at")
        batch.drop_column("max_clicks")
        batch.drop_column("expires_at")
