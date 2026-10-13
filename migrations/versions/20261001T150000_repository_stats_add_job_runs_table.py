"""Repository Stats: job runs table, used for the pages' "Last updated" time."""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e2b7a6f41d03"
down_revision = "c5e81d4b9a27"


def upgrade():
    op.create_table(
        "repository_stats_job_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_name", sa.String(), nullable=False),
        sa.Column("org", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_repository_stats_job_runs_job_name_status_finished_at",
        "repository_stats_job_runs",
        ["job_name", "status", "finished_at"],
    )


def downgrade():
    op.drop_index(
        "ix_repository_stats_job_runs_job_name_status_finished_at",
        table_name="repository_stats_job_runs",
    )
    op.drop_table("repository_stats_job_runs")
