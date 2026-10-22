"""Durable signed delivery inbox and source-aware event fragments."""

import sqlalchemy as sa
from alembic import op

revision = "b827e40cf316"
down_revision = "a716d39be205"


def upgrade():
    op.create_table(
        "flow_metrics_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event", sa.String(50), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("body_sha256", sa.String(64), nullable=False),
        sa.Column("body", sa.LargeBinary(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(100)),
    )
    op.create_table(
        "flow_metrics_events",
        sa.Column(
            "id",
            sa.String(36),
            sa.ForeignKey("flow_metrics_deliveries.id"),
            primary_key=True,
        ),
        sa.Column(
            "dataset_id",
            sa.String(100),
            sa.ForeignKey("flow_metrics_datasets.id"),
            nullable=False,
        ),
        sa.Column("item_id", sa.String(150)),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("time_basis", sa.String(40), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("quality", sa.String(30), nullable=False),
        sa.Column("reason", sa.String(100), nullable=False),
    )
    op.create_index(
        "ix_flow_metrics_events_item_id", "flow_metrics_events", ["item_id"]
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
            CREATE TRIGGER immutable_flow_event BEFORE UPDATE ON flow_metrics_events
            FOR EACH ROW EXECUTE FUNCTION flow_metrics_reject_evidence_update()
        """)
        op.execute("""
            CREATE FUNCTION flow_metrics_guard_delivery() RETURNS trigger AS $$
            BEGIN
                IF (OLD.id, OLD.event, OLD.action, OLD.body_sha256, OLD.body, OLD.received_at)
                   IS DISTINCT FROM
                   (NEW.id, NEW.event, NEW.action, NEW.body_sha256, NEW.body, NEW.received_at)
                THEN RAISE EXCEPTION 'Flow Metrics original delivery is immutable';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """)
        op.execute("""
            CREATE TRIGGER immutable_flow_delivery BEFORE UPDATE ON flow_metrics_deliveries
            FOR EACH ROW EXECUTE FUNCTION flow_metrics_guard_delivery()
        """)


def downgrade():
    op.drop_table("flow_metrics_events")
    op.drop_table("flow_metrics_deliveries")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION flow_metrics_guard_delivery()")
