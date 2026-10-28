from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database import db


class FlowBoard(db.Model):
    __tablename__ = "flow_metrics_boards"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    chart_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    charts: Mapped[list] = mapped_column(JSON, nullable=False)
    field_mapping: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class FlowDataset(db.Model):
    """Immutable event contract; chart revisions live separately in FlowBoard."""

    __tablename__ = "flow_metrics_datasets"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    provenance: Mapped[str] = mapped_column(String(20), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class FlowEvidence(db.Model):
    """Append-only source documents, distinct from the daily published view."""

    __tablename__ = "flow_metrics_evidence"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("flow_metrics_datasets.id"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    document: Mapped[dict] = mapped_column(JSON, nullable=False)


class FlowDelivery(db.Model):
    __tablename__ = "flow_metrics_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))


class FlowEvent(db.Model):
    __tablename__ = "flow_metrics_events"

    id: Mapped[str] = mapped_column(
        ForeignKey("flow_metrics_deliveries.id"), primary_key=True,
    )
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("flow_metrics_datasets.id"), nullable=False,
    )
    item_id: Mapped[str | None] = mapped_column(String(150), index=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_basis: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    quality: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)


class FlowCollectionRun(db.Model):
    __tablename__ = "flow_metrics_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    board_id: Mapped[str] = mapped_column(
        ForeignKey("flow_metrics_boards.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))


class FlowSnapshot(db.Model):
    __tablename__ = "flow_metrics_snapshots"
    __table_args__ = (UniqueConstraint("board_id", "captured_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    board_id: Mapped[str] = mapped_column(
        ForeignKey("flow_metrics_boards.id"), nullable=False
    )
    captured_date: Mapped[date] = mapped_column(Date, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
