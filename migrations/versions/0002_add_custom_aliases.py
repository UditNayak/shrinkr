"""add custom aliases

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    # batch_alter_table: a plain ALTER on PostgreSQL; a table rebuild on SQLite (tests),
    # which cannot change a column's type in place.
    with op.batch_alter_table("links") as batch:
        # The server default fills existing rows, so adding a NOT NULL column is safe.
        batch.add_column(
            sa.Column("is_custom", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        # Aliases can be up to 32 characters (random codes are 7).
        batch.alter_column(
            "code",
            existing_type=sa.String(16),
            type_=sa.String(32),
            existing_nullable=False,
        )


def downgrade():
    # Fails if any alias is longer than 16 characters: delete or shorten those first.
    with op.batch_alter_table("links") as batch:
        batch.alter_column(
            "code",
            existing_type=sa.String(32),
            type_=sa.String(16),
            existing_nullable=False,
        )
        batch.drop_column("is_custom")
