"""add daily clicks

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "daily_clicks",
        sa.Column("link_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["link_id"], ["links.id"], name="fk_daily_clicks_link_id_links", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("link_id", "day", name="pk_daily_clicks"),
    )


def downgrade():
    op.drop_table("daily_clicks")
