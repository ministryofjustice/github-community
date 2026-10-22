"""Flow Metrics: shared charts and complete daily observations."""

import sqlalchemy as sa
from alembic import op

revision = "c93f4a108d72"
down_revision = "b41f0c7e9a26"


def upgrade():
    op.create_table(
        "flow_metrics_boards",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("chart_revision", sa.Integer(), nullable=False),
        sa.Column("charts", sa.JSON(), nullable=False),
    )
    op.create_table(
        "flow_metrics_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "board_id",
            sa.String(100),
            sa.ForeignKey("flow_metrics_boards.id"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(100)),
    )
    op.create_table(
        "flow_metrics_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "board_id",
            sa.String(100),
            sa.ForeignKey("flow_metrics_boards.id"),
            nullable=False,
        ),
        sa.Column("captured_date", sa.Date(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("board_id", "captured_date"),
    )


def downgrade():
    op.drop_table("flow_metrics_snapshots")
    op.drop_table("flow_metrics_runs")
    op.drop_table("flow_metrics_boards")
