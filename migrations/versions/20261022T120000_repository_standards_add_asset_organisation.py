"""Add organisation identity to repository-standard assets."""

import sqlalchemy as sa
from alembic import op


revision = "f91c2d7a6b40"
down_revision = "b41f0c7e9a26"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "assets",
        sa.Column(
            "organisation",
            sa.String(),
            nullable=False,
            server_default="ministryofjustice",
        ),
    )
    op.create_index(
        "ix_assets_organisation_name", "assets", ["organisation", "name"]
    )


def downgrade():
    op.drop_index("ix_assets_organisation_name", table_name="assets")
    op.drop_column("assets", "organisation")