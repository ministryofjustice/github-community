"""Isolated fictional event dataset and immutable real source evidence."""

import sqlalchemy as sa
from alembic import op

revision = "a716d39be205"
down_revision = "e1b6c4a93270"


def upgrade():
    op.create_table(
        "flow_metrics_datasets",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("provenance", sa.String(20), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "flow_metrics_evidence",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(100),
            sa.ForeignKey("flow_metrics_datasets.id"),
            nullable=False,
        ),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
    )
    # Real source identity exists even before any archives are imported.
    op.bulk_insert(
        sa.table(
            "flow_metrics_datasets",
            sa.column("id"),
            sa.column("provenance"),
            sa.column("content_sha256"),
            sa.column("payload", sa.JSON()),
        ),
        [
            {
                "id": "ministryofjustice/152",
                "provenance": "real",
                "content_sha256": "",
                "payload": {},
            }
        ],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
            CREATE FUNCTION flow_metrics_reject_evidence_update() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'Flow Metrics dataset/source evidence is immutable';
            END;
            $$ LANGUAGE plpgsql
        """)
        for table in ("flow_metrics_datasets", "flow_metrics_evidence"):
            op.execute(f"""
                CREATE TRIGGER immutable_flow_record BEFORE UPDATE ON {table}
                FOR EACH ROW EXECUTE FUNCTION flow_metrics_reject_evidence_update()
            """)


def downgrade():
    # This revision does not own flow_metrics_boards or its observations.
    op.drop_table("flow_metrics_evidence")
    op.drop_table("flow_metrics_datasets")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION flow_metrics_reject_evidence_update()")