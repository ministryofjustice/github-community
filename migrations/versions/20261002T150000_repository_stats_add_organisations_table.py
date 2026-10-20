"""Repository Stats: organisation display names, recorded by the visibility job."""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b41f0c7e9a26"
down_revision = "7d3c9a51f2b8"


def upgrade():
    op.create_table(
        "repository_stats_organisations",
        sa.Column("login", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("login"),
    )


def downgrade():
    op.drop_table("repository_stats_organisations")
