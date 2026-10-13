"""Repository Stats: visibility snapshot and event tables.

Independent copies of the Repository Standards visibility tables, which stay in place.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c5e81d4b9a27"
down_revision = "64b771c789c0"


def upgrade():
    op.create_table(
        "repository_stats_visibility_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("org", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("visibility", sa.String(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fork", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("pushed_at", sa.DateTime(), nullable=True),
        sa.Column("captured_on", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "github_id",
            "captured_on",
            name="uq_repository_stats_visibility_snapshots_github_id_captured_on",
        ),
    )
    op.create_index(
        "ix_repository_stats_visibility_snapshots_captured_on",
        "repository_stats_visibility_snapshots",
        ["captured_on"],
    )

    op.create_table(
        "repository_stats_visibility_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("org", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("from_visibility", sa.String(), nullable=True),
        sa.Column("to_visibility", sa.String(), nullable=True),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("actor", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_repository_stats_visibility_events_occurred_on",
        "repository_stats_visibility_events",
        ["occurred_on"],
    )
    op.create_index(
        "ix_repository_stats_visibility_events_event_type",
        "repository_stats_visibility_events",
        ["event_type"],
    )
    op.create_index(
        "ix_repository_stats_visibility_events_name",
        "repository_stats_visibility_events",
        ["name"],
    )


def downgrade():
    op.drop_index(
        "ix_repository_stats_visibility_events_name",
        table_name="repository_stats_visibility_events",
    )
    op.drop_index(
        "ix_repository_stats_visibility_events_event_type",
        table_name="repository_stats_visibility_events",
    )
    op.drop_index(
        "ix_repository_stats_visibility_events_occurred_on",
        table_name="repository_stats_visibility_events",
    )
    op.drop_table("repository_stats_visibility_events")

    op.drop_index(
        "ix_repository_stats_visibility_snapshots_captured_on",
        table_name="repository_stats_visibility_snapshots",
    )
    op.drop_table("repository_stats_visibility_snapshots")
