"""Explicit dataset lifecycle and validated, lossless private source imports."""

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import click
from flask.cli import with_appcontext
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.projects.flow_metrics.db_models import FlowBoard, FlowDataset, FlowEvidence
from app.projects.flow_metrics.service import validate_chart
from app.shared.database import db

REAL_ID = "ministryofjustice/152"
SAMPLE_ID = "sample-three-sprints"


class ObservationConflict(ValueError):
    """Safe error for contradictory evidence at the same source and instant."""


def digest(document):
    return hashlib.sha256(
        json.dumps(
            document,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def sample_dataset():
    dataset = db.session.get(FlowDataset, SAMPLE_ID)
    if not dataset:
        raise ValueError(
            "Initialise the fictional dataset with flow-metrics init-sample."
        )
    if (
        dataset.provenance != "synthetic"
        or dataset.payload.get("id") != SAMPLE_ID
        or dataset.payload.get("provenance") != "synthetic"
        or digest(dataset.payload) != dataset.content_sha256
    ):
        raise ValueError("Fictional dataset integrity check failed.")
    return dataset


def initialise_sample(document):
    data = document["dataset"]
    charts = document["charts"]
    if data["id"] != SAMPLE_ID or data["provenance"] != "synthetic":
        raise ValueError(
            "Only the explicitly fictional dataset can be initialised here."
        )
    ids = {ticket["id"] for ticket in data["tickets"]}
    if len(ids) != len(data["tickets"]) or not all(
        key.startswith("SAMPLE-") for key in ids
    ):
        raise ValueError("Fictional ticket identifiers must be unique and namespaced.")
    for ticket in data["tickets"]:
        required = {
            "title",
            "repository",
            "team",
            "type",
            "objective",
            "planned",
            "created",
            "assignee",
            "label",
            "milestone",
            "reviewers",
            "priority",
            "refined",
            "blocked-by",
            "blocking",
            "relates-to",
            "parent-issue",
            "sub-issues-progress",
        }
        if not required <= ticket.keys() or ticket["team"] not in data["teams"]:
            raise ValueError("Fictional metadata is incomplete.")
        for field in ("blocked-by", "blocking", "relates-to", "parent-issue"):
            if any(key != "Not set" and key not in ids for key in ticket[field]):
                raise ValueError(
                    "Fictional relationships must stay within their dataset."
                )
        if not ticket["events"] or ticket["events"] != sorted(
            ticket["events"], key=lambda event: event["date"]
        ):
            raise ValueError("Fictional events must be chronological.")
        for event in ticket["events"]:
            date.fromisoformat(event["date"])
            if not ticket["created"] <= event["date"] <= data["history"]["to"]:
                raise ValueError("Fictional event falls outside its ticket history.")
            if event["type"] not in {"status", "scope", "points"}:
                raise ValueError("Unsupported fictional event.")
    for chart in charts:
        validate_chart(chart)
    checksum = digest(data)
    existing = db.session.get(FlowDataset, SAMPLE_ID)
    if existing and existing.content_sha256 != checksum:
        raise ValueError(
            "Dataset ID is immutable; use a new version for changed fiction."
        )
    if existing is None:
        db.session.add(
            FlowDataset(
                id=SAMPLE_ID,
                provenance="synthetic",
                content_sha256=checksum,
                payload=data,
            )
        )
    if db.session.get(FlowBoard, SAMPLE_ID) is None:
        db.session.add(FlowBoard(id=SAMPLE_ID, charts=charts, chart_revision=0))
    db.session.commit()


def validate_evidence(document):
    """Validate known source formats without normalising away their provenance."""
    if (
        not isinstance(document, dict)
        or type(document.get("schema_version")) is not int
        or document["schema_version"] != 1
    ):
        raise ValueError("Unsupported capture schema.")
    if document.get("kind") == "published_board_observation":
        if document.get("board_id") != REAL_ID or document.get("provenance") != "real":
            raise ValueError("Wrong board or provenance.")
        items = document["payload"]["items"]
        stamp = document["captured_at"]
        day = document["captured_date"]
        source = "app-published-observation"
        if not isinstance(document["payload"]["fields"], list):
            raise ValueError("App capture fields are missing.")
        if not isinstance(items, list) or any(
            not isinstance(item, dict)
            or not isinstance(item.get("fields"), list)
            or not isinstance(item.get("content"), dict)
            for item in items
        ):
            raise ValueError("Incomplete app item.")
    elif document.get("source") == "GitHub GraphQL API via local gh sign-in":
        if (
            document["project"]["url"]
            != "https://github.com/orgs/ministryofjustice/projects/152"
        ):
            raise ValueError("Wrong external project.")
        items = document["items"]
        stamp = document["collection_finished_at"]
        day = document["snapshot_date"]
        source = "external-gh-capture"
        started = datetime.fromisoformat(document["collection_started_at"])
        if started.tzinfo is None or started > datetime.fromisoformat(stamp):
            raise ValueError("Invalid external collection interval.")
        zone = ZoneInfo(document["snapshot_timezone"])
        if not isinstance(document["project"]["fields"], dict):
            raise ValueError("External fields connection is missing.")
        if not isinstance(items, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("fieldValues"), dict)
            for item in items
        ):
            raise ValueError("External item fields are missing.")
    else:
        raise ValueError("Unrecognised source; no implicit conversion is permitted.")
    observed = datetime.fromisoformat(stamp)
    valid_days = (
        {observed.date()}
        if source == "app-published-observation"
        else {
            started.astimezone(zone).date(),
            observed.astimezone(zone).date(),
        }
    )
    if observed.tzinfo is None or date.fromisoformat(day) not in valid_days:
        raise ValueError("Capture timestamp/date must be explicit and consistent.")
    if type(document["item_count"]) is not int or document["item_count"] != len(items):
        raise ValueError("Capture count does not match its payload.")
    if any(not isinstance(item.get("id"), str) or not item["id"] for item in items):
        raise ValueError("Capture item identifiers are missing.")
    if len({item["id"] for item in items}) != len(items):
        raise ValueError("Capture contains duplicate item IDs.")

    def verify_pages(value):
        if isinstance(value, dict):
            if isinstance(value.get("pageInfo"), dict) and value["pageInfo"].get(
                "hasNextPage"
            ):
                raise ValueError("Partial source connections cannot be imported.")
            for child in value.values():
                verify_pages(child)
        elif isinstance(value, list):
            for child in value:
                verify_pages(child)

    verify_pages(document)
    return digest(document), source, observed


def stored_evidence_identities():
    dataset = db.session.get(FlowDataset, REAL_ID)
    if dataset is not None and dataset.provenance != "real":
        raise ValueError("Real dataset provenance mismatch.")
    identities, checksums = {}, set()
    for row in db.session.scalars(
        select(FlowEvidence).where(FlowEvidence.dataset_id == REAL_ID)
    ):
        checksum, source, observed = validate_evidence(row.document)
        stored_at = row.observed_at
        if stored_at.tzinfo is None:
            stored_at = stored_at.replace(tzinfo=UTC)
        if checksum != row.id or source != row.source or stored_at != observed:
            raise ValueError("Stored evidence integrity failure.")
        check_observation_identity(identities, checksum, source, observed)
        identities[(source, observed.astimezone(UTC))] = checksum
        checksums.add(checksum)
    return identities, checksums


def check_observation_identity(identities, checksum, source, observed):
    identity = (source, observed.astimezone(UTC))
    if identity in identities and identities[identity] != checksum:
        raise ObservationConflict("Capture conflicts with stored observation; nothing imported.")


def retain_evidence(document):
    checksum, source, observed = validate_evidence(document)
    if db.session.get(FlowDataset, REAL_ID) is None:
        db.session.add(
            FlowDataset(id=REAL_ID, provenance="real", content_sha256="", payload={})
        )
        db.session.flush()
    existing = db.session.get(FlowEvidence, checksum)
    if existing and (
        existing.document != document
        or existing.dataset_id != REAL_ID
        or existing.source != source
    ):
        raise ValueError("Stored source evidence failed its integrity check.")
    if existing is None:
        db.session.add(
            FlowEvidence(
                id=checksum,
                dataset_id=REAL_ID,
                source=source,
                observed_at=observed,
                document=document,
            )
        )
    return checksum


@click.command("init-sample")
@with_appcontext
def init_sample_command():
    """Idempotently initialise packaged fiction; never replace shared charts."""
    path = Path(__file__).with_name("sample-seed.json")
    initialise_sample(json.loads(path.read_text()))
    dataset = sample_dataset()
    click.echo(
        f"Fictional dataset initialised: {len(dataset.payload['tickets'])} tickets; existing charts preserved."
    )


@click.command("import-capture")
@click.option(
    "--file", "filename", required=True, type=click.Path(exists=True, dir_okay=False)
)
@with_appcontext
def import_capture_command(filename):
    """Import a recognised private source document, preserving every version."""
    path = Path(filename).resolve()
    repository = Path(__file__).resolve().parents[3]
    if path == repository or repository in path.parents:
        raise click.ClickException(
            "Real source imports must be outside the repository."
        )
    try:
        from app.projects.flow_metrics.locking import lock_collection
        from app.projects.flow_metrics.workspace import validate_observation

        encoded = path.read_bytes()
        if path.name.startswith("project-152-") and not path.stem.endswith(
            hashlib.sha256(encoded).hexdigest()
        ):
            raise ValueError("Archive filename checksum does not match.")
        document = json.loads(encoded)
        checksum, source, observed = validate_evidence(document)
        lock_collection()
        board = db.session.get(FlowBoard, REAL_ID, populate_existing=True)
        identities, _ = stored_evidence_identities()
        check_observation_identity(identities, checksum, source, observed)
        validate_observation(
            document, source, observed, checksum, board.field_mapping if board else {},
        )
        checksum = retain_evidence(document)
        db.session.commit()
    except ObservationConflict as error:
        db.session.rollback()
        raise click.ClickException(str(error)) from None
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, OSError, SQLAlchemyError):
        db.session.rollback()
        raise click.ClickException(
            "Invalid/incomplete source document; nothing imported."
        ) from None
    click.echo(f"Verified source evidence: {checksum}")


@click.command("remove-sample")
@click.option("--confirm-dataset", required=True)
@with_appcontext
def remove_sample_command(confirm_dataset):
    """Explicitly remove only fictional data and its shared chart definitions."""
    if confirm_dataset != SAMPLE_ID:
        raise click.ClickException(f"Confirm the exact dataset ID: {SAMPLE_ID}")
    board = db.session.get(FlowBoard, SAMPLE_ID)
    dataset = db.session.get(FlowDataset, SAMPLE_ID)
    if db.session.execute(
        select(FlowEvidence.id).where(FlowEvidence.dataset_id == SAMPLE_ID)
    ).first():
        raise click.ClickException("Unexpected evidence references; refusing cleanup.")
    if board:
        db.session.delete(board)
        db.session.flush()
    if dataset:
        db.session.delete(dataset)
    db.session.commit()
    click.echo(
        "Only fictional dataset and its chart definitions removed; real evidence/charts preserved."
    )
