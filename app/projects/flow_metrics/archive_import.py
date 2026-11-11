"""Private operator imports: validate first, append evidence in one transaction."""

import hashlib
import json
import logging
from datetime import UTC, date
from pathlib import Path

import click
from flask.cli import with_appcontext
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.projects.flow_metrics.collector import BOARD_ID, MAX_ITEMS
from app.projects.flow_metrics.datasets import (
    ObservationConflict,
    check_observation_identity,
    retain_evidence,
    stored_evidence_identities,
    validate_evidence,
)
from app.projects.flow_metrics.db_models import FlowBoard
from app.projects.flow_metrics.locking import lock_collection
from app.projects.flow_metrics.workspace import validate_observation
from app.shared.database import db

logger = logging.getLogger(__name__)


class ArchiveImportError(Exception):
    """Safe operator message; never includes source paths or record contents."""


def check_connections(value):
    if isinstance(value, dict):
        if "pageInfo" in value and (
            not isinstance(value["pageInfo"], dict)
            or type(value["pageInfo"].get("hasNextPage")) is not bool
        ):
            raise ValueError("Missing explicit pagination state.")
        if "totalCount" in value and "nodes" in value:
            count = value["totalCount"]
            if type(count) is not int or count != len(value["nodes"]):
                raise ValueError("Connection count mismatch.")
        for child in value.values():
            check_connections(child)
    elif isinstance(value, list):
        for child in value:
            check_connections(child)


def read_bundle(directory, since):
    directory = Path(directory).resolve()
    repository = Path(__file__).resolve().parents[3]
    if directory == repository or repository in directory.parents:
        raise ArchiveImportError("Private captures must be outside the repository.")
    if not directory.is_dir():
        raise ArchiveImportError("Private capture directory does not exist.")
    documents, ignored, seen, identities = [], 0, set(), {}
    try:
        for path in sorted(directory.iterdir()):
            if path.is_symlink() or path.is_dir():
                raise ArchiveImportError(
                    "Use a flat directory without links or subdirectories."
                )
            if path.suffix.lower() != ".json":
                ignored += 1
                continue
            encoded = path.read_bytes()
            document = json.loads(encoded)
            if not isinstance(document, dict):
                raise TypeError("Expected a document.")
            capture = (
                document.get("kind") == "published_board_observation"
                or document.get("source") == "GitHub GraphQL API via local gh sign-in"
            )
            if not capture:
                if {
                    "items",
                    "payload",
                    "captured_at",
                    "snapshot_date",
                    "item_count",
                } & document.keys():
                    raise ArchiveImportError(
                        "Unrecognised capture format; nothing imported."
                    )
                ignored += 1
                continue
            checksum, source, observed = validate_evidence(document)
            if (
                date.fromisoformat(
                    document.get("captured_date", document.get("snapshot_date"))
                )
                < since
            ):
                raise ArchiveImportError("Capture precedes --since; nothing imported.")
            if document["item_count"] > MAX_ITEMS:
                raise ArchiveImportError(
                    "Capture exceeds the supported item limit; nothing imported."
                )
            check_connections(document)
            if source == "app-published-observation" or path.name.startswith(
                "project-152-"
            ):
                expected = f"project-152-{document.get('captured_date', document.get('snapshot_date'))}-{hashlib.sha256(encoded).hexdigest()}.json"
                if path.name != expected:
                    raise ArchiveImportError(
                        "Archive filename checksum/date mismatch; nothing imported."
                    )
            if checksum in seen:
                raise ArchiveImportError(
                    "Duplicate capture document in bundle; nothing imported."
                )
            identity = (source, observed.astimezone(UTC))
            if identity in identities and identities[identity] != checksum:
                raise ArchiveImportError(
                    "Conflicting captures at the same observation time; nothing imported."
                )
            identities[identity] = checksum
            seen.add(checksum)
            documents.append((checksum, source, observed, document))
    except (OSError, ValueError, KeyError, TypeError, OverflowError, RecursionError):
        raise ArchiveImportError(
            "Invalid capture bundle: check schema, dates, identity, checksums, duplicates and completeness; nothing imported."
        ) from None
    if not documents:
        raise ArchiveImportError("No recognised captures in the private directory.")
    return sorted(documents, key=lambda entry: (entry[2], entry[0])), ignored


def import_archives(directory, since, dry_run=False):
    """Append atomically; collectors/importers share a separate writer mutex."""
    try:
        documents, ignored = read_bundle(directory, since)
        query = select(FlowBoard).where(FlowBoard.id == BOARD_ID)
        if not dry_run:
            lock_collection()
            query = query.execution_options(populate_existing=True)
        board = db.session.execute(query).scalar_one_or_none()
        if board is None and not dry_run:
            raise ArchiveImportError(
                "Run flow-metrics init before importing private captures."
            )
        mapping = board.field_mapping if board else {}
        identities, existing = stored_evidence_identities()
        for checksum, source, observed, document in documents:
            check_observation_identity(identities, checksum, source, observed)
            validate_observation(document, source, observed, checksum, mapping)
        added = sum(checksum not in existing for checksum, *_ in documents)
        if not dry_run:
            for _, _, _, document in documents:
                retain_evidence(document)
            db.session.commit()
        else:
            db.session.rollback()
    except ObservationConflict as error:
        db.session.rollback()
        raise ArchiveImportError(str(error)) from None
    except ArchiveImportError:
        db.session.rollback()
        raise
    except (
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        OverflowError,
        SQLAlchemyError,
    ):
        db.session.rollback()
        raise ArchiveImportError(
            "Capture validation or database import failed; the whole bundle was rolled back. No payload logged."
        ) from None
    summary = {
        "captures": len(documents),
        "items": sum(d[3]["item_count"] for d in documents),
        "new": added,
        "existing": len(documents) - added,
        "ignored": ignored,
        "dry_run": dry_run,
    }
    logger.info(
        "Flow Metrics archive bundle: captures=%s item_observations=%s new=%s existing=%s ignored=%s dry_run=%s",
        *summary.values(),
    )
    return summary


@click.command("import-archives")
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("--since", required=True, type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option("--dry-run", is_flag=True)
@with_appcontext
def import_archives_command(directory, since, dry_run):
    """Validate a private directory, then append all captures or none."""
    try:
        summary = import_archives(directory, since.date(), dry_run)
    except ArchiveImportError as error:
        raise click.ClickException(str(error)) from None
    click.echo(
        f"{'Dry run; nothing written' if dry_run else 'Imported atomically'}: "
        f"{summary['captures']} captures, {summary['items']} item observations, "
        f"{summary['new']} new, {summary['existing']} existing, "
        f"{summary['ignored']} unrelated files ignored. "
        "Archive consistency checked; legacy files do not prove API-total completeness."
    )
