"""Transaction-scoped writer coordination, independent of editable chart rows."""

from sqlalchemy import text

from app.shared.database import db


def lock_collection():
    """SQLite is supported only for single-process local/test workspaces."""
    dialect = db.session.get_bind().dialect.name
    if dialect == "postgresql":
        # Stable namespace/project pair, released on commit, rollback or disconnect.
        db.session.execute(text("SELECT pg_advisory_xact_lock(1718447981, 152)"))
    elif dialect != "sqlite":
        raise ValueError("Flow Metrics writers require PostgreSQL.")
