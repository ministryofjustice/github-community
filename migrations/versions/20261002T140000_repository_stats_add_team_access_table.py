"""Repository Stats: team access per repository, collected by the visibility job."""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "7d3c9a51f2b8"
down_revision = "e2b7a6f41d03"


def upgrade():
    op.create_table(
        "repository_stats_team_access",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("org", sa.String(), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("team_slug", sa.String(), nullable=False),
        sa.Column("team_name", sa.String(), nullable=False),
        sa.Column("parent_team_slug", sa.String(), nullable=True),
        sa.Column("permission", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "org",
            "github_id",
            "team_slug",
            name="uq_repository_stats_team_access_org_github_id_team_slug",
        ),
    )
    op.create_index(
        "ix_repository_stats_team_access_github_id",
        "repository_stats_team_access",
        ["github_id"],
    )


def downgrade():
    op.drop_index(
        "ix_repository_stats_team_access_github_id",
        table_name="repository_stats_team_access",
    )
    op.drop_table("repository_stats_team_access")
