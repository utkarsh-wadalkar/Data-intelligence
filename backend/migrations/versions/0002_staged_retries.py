"""Persist collection progress and staged rate-limit retries.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Revision 0001 creates the current Base metadata on new databases.
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("runs")}
    columns = (
        sa.Column("checkpoint", sa.JSON(), nullable=True),
        sa.Column("retry_attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("recovery_count", sa.Integer(), nullable=False, server_default="0"),
    )
    for column in columns:
        if column.name not in existing:
            op.add_column("runs", column)
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("runs")}
    if "ix_runs_next_retry_at" not in indexes:
        op.create_index("ix_runs_next_retry_at", "runs", ["next_retry_at"])


def downgrade() -> None:
    op.drop_index("ix_runs_next_retry_at", table_name="runs")
    op.drop_column("runs", "recovery_count")
    op.drop_column("runs", "next_retry_at")
    op.drop_column("runs", "retry_attempt")
    op.drop_column("runs", "checkpoint")
