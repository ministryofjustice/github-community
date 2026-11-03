"""Private, lossless exports of published observations for later migration."""

import hashlib
import json
from datetime import UTC
from pathlib import Path

import click
from sqlalchemy import select

from app.projects.flow_metrics.collector import BOARD_ID
from app.projects.flow_metrics.db_models import FlowSnapshot
from app.shared.database import db


def snapshot_document(snapshot):
    items = snapshot.payload["items"]
    if len({item["id"] for item in items}) != len(items):
        raise ValueError("Snapshot contains duplicate item IDs.")
    return {
        "schema_version": 1,
        "provenance": "real",
        "kind": "published_board_observation",
        "board_id": snapshot.board_id,
        "snapshot_id": snapshot.id,
        "captured_date": snapshot.captured_date.isoformat(),
        "captured_at": snapshot.captured_at.replace(tzinfo=UTC).isoformat()
        if snapshot.captured_at.tzinfo is None else snapshot.captured_at.isoformat(),
        "item_count": len(items),
        "payload": snapshot.payload,
    }


def export_snapshot(snapshot, directory):
    directory = Path(directory).resolve()
    repository = Path(__file__).resolve().parents[3]
    if directory == repository or repository in directory.parents:
        raise ValueError("Real observations must be exported outside the repository.")
    document = snapshot_document(snapshot)
    encoded = (json.dumps(document, sort_keys=True, ensure_ascii=True) + "\n").encode()
    digest = hashlib.sha256(encoded).hexdigest()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f"project-152-{document['captured_date']}-{digest}.json"
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError("Existing archive failed its integrity check.")
    else:
        with path.open("xb") as output:
            path.chmod(0o600)
            output.write(encoded)
    saved = json.loads(path.read_bytes())
    if saved != document or saved["item_count"] != len(saved["payload"]["items"]):
        raise ValueError("Saved archive did not match the complete observation.")
    return path


@click.command("export-snapshots")
@click.option("--directory", required=True, type=click.Path(file_okay=False))
def export_command(directory):
    """Archive complete DB observations outside the repository; never overwrite."""
    snapshots = db.session.execute(
        select(FlowSnapshot)
        .where(FlowSnapshot.board_id == BOARD_ID)
        .order_by(FlowSnapshot.captured_at)
    ).scalars()
    try:
        for snapshot in snapshots:
            path = export_snapshot(snapshot, directory)
            click.echo(f"Verified archive: {path}")
    except (OSError, ValueError) as error:
        raise click.ClickException(str(error)) from None
