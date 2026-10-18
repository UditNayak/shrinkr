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
    # batch mode lets SQLite (used in tests) change the column type
    with op.batch_alter_table("links") as batch:
        batch.add_column(
            sa.Column("is_custom", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch.alter_column(
            "code",
            existing_type=sa.String(16),
            type_=sa.String(32),
            existing_nullable=False,
        )


def downgrade():
    # fails if any alias is longer than 16 characters
    with op.batch_alter_table("links") as batch:
        batch.alter_column(
            "code",
            existing_type=sa.String(32),
            type_=sa.String(16),
            existing_nullable=False,
        )
        batch.drop_column("is_custom")
