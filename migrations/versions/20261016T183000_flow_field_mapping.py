"""Flow Metrics: pin collected field meanings to GitHub node IDs."""

import sqlalchemy as sa
from alembic import op

revision = "e1b6c4a93270"
down_revision = "c93f4a108d72"


def upgrade():
    op.add_column(
        "flow_metrics_boards",
        sa.Column("field_mapping", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.alter_column("flow_metrics_boards", "field_mapping", server_default=None)


def downgrade():
    op.drop_column("flow_metrics_boards", "field_mapping")
