"""Serialised collection with before/after immutable archives."""

import fcntl
from pathlib import Path

import click
from sqlalchemy import select

from app.projects.flow_metrics.archive import export_snapshot
from app.projects.flow_metrics.collector import BOARD_ID, CollectionError, collect
from app.projects.flow_metrics.db_models import FlowSnapshot
from app.shared.database import db


def reconcile(directory):
    directory = Path(directory).resolve()
    # Validate the destination before creating a lock or contacting GitHub.
    repository = Path(__file__).resolve().parents[3]
    if directory == repository or repository in directory.parents:
        raise ValueError("Real observations must be archived outside the repository.")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "reconciliation.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CollectionError("reconciliation_already_running") from None

        def archive_all():
            snapshots = db.session.execute(
                select(FlowSnapshot).where(FlowSnapshot.board_id == BOARD_ID)
            ).scalars()
            return [export_snapshot(snapshot, directory) for snapshot in snapshots]

        archive_all()
        count = collect()
        paths = archive_all()
        return count, paths


@click.command("reconcile")
@click.option("--directory", required=True, type=click.Path(file_okay=False))
def reconcile_command(directory):
    """Archive existing evidence, collect, then archive successful publication."""
    try:
        count, paths = reconcile(directory)
    except (OSError, ValueError, CollectionError) as error:
        raise click.ClickException(str(error)) from None
    click.echo(f"Complete: {count} items; {len(paths)} current snapshots archived.")
