"""Source-aware exploration contract; never turn observations into events."""

from copy import deepcopy
from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace

from sqlalchemy import case, exists, literal, select, union_all

from app.projects.flow_metrics.collector import BOARD_ID, ESTIMATION_FIELD_ID
from app.projects.flow_metrics.config import DEFAULT_SOURCE_URL, workspace_config
from app.projects.flow_metrics.datasets import sample_dataset
from app.projects.flow_metrics.db_models import (
    FlowBoard,
    FlowEvidence,
    FlowSnapshot,
)
from app.projects.flow_metrics.service import FIELD_NAMES, METADATA_FIELDS, normalise
from app.shared.database import db

# Deliberate exploration alias, not a change to either sprint's identity/calendar.
FIREBREAK_ITERATION = "122ca265"


def observation_contract(payload, observed_at, source, source_id, mapping):
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    mapping = dict(mapping)
    if any(
        field["id"] == ESTIMATION_FIELD_ID and field.get("dataType") == "NUMBER"
        for field in payload.get("fields", [])
    ):
        mapping["estimate"] = ESTIMATION_FIELD_ID
    items = normalise(SimpleNamespace(payload=payload))
    by_id = {item["id"]: item for item in payload["items"]}
    sprints = {}
    for item in items:
        original = by_id[item["id"]]
        fields = {field["field"]["id"]: field for field in original["fields"]}
        identities = {
            key: {
                "fieldId": field_id,
                "optionId": fields.get(field_id, {}).get("optionId"),
                "iterationId": fields.get(field_id, {}).get("iterationId"),
            }
            for key, field_id in mapping.items()
            if field_id
        }
        iteration = fields.get(mapping.get("sprint"), {})
        iteration_id = iteration.get("iterationId")
        if iteration_id:
            sprints[iteration_id] = {
                "id": f"real:{iteration_id}",
                "fieldId": mapping["sprint"],
                "iterationId": iteration_id,
                "name": iteration["title"],
                "start": iteration.get("startDate"),
                "end": (
                    date.fromisoformat(iteration["startDate"])
                    + timedelta(days=iteration["duration"] - 1)
                ).isoformat()
                if iteration.get("startDate") and iteration.get("duration")
                else None,
                "provenance": "real",
            }
        available = ["repository", "type", "title", "is"]
        available.extend(key for key, field_id in mapping.items() if field_id)
        if payload.get("metadataVersion") == 1:
            available.extend(METADATA_FIELDS)
        item.update(
            id=f"real:{item['id']}",
            sourceId=item["id"],
            datasetId=BOARD_ID,
            provenance="real",
            source=source,
            observedAt=observed_at.isoformat(),
            identities=identities,
            availableFields=sorted(set(available)),
            observedStatus=item["status"],
            actualSprint=item["sprint"],
            sprintId=f"real:{iteration_id}" if iteration_id else None,
        )
        if iteration_id == FIREBREAK_ITERATION:
            item["sprint"] = "Firebreak"
    return {
        "id": source_id,
        "capturedAt": observed_at.isoformat(),
        "source": source,
        "items": items,
        "sprints": list(sprints.values()),
    }


def evidence_payload(document, source, mapping):
    """Adapt the read model only; original evidence remains immutable."""
    if source == "app-published-observation":
        return document["payload"]
    if source == "external-gh-capture":
        # Keep the original document untouched; adapt only its read model.
        external_fields = document["project"]["fields"]["nodes"]
        available_ids = {field["id"] for field in external_fields}
        bound = {key: value for key, value in mapping.items() if value in available_ids}
        for key, name in FIELD_NAMES.items():
            if key not in bound:
                match = next(
                    (field["id"] for field in external_fields if field["name"] == name),
                    None,
                )
                if match:
                    bound[key] = match
        return {
            "fields": external_fields,
            "mapping": bound,
            "items": [
                {
                    "id": item["id"],
                    "archived": item["isArchived"],
                    "content": {
                        key: value
                        for key, value in item["content"].items()
                        if key != "parent"
                    },
                    "fields": [
                        value
                        for value in item["fieldValues"]["nodes"]
                        if value and value.get("field", {}).get("id") in available_ids
                    ],
                }
                for item in document["items"]
            ],
        }
    raise ValueError("Unsupported stored source evidence.")


def capture_index():
    """Select only identities/times, including non-duplicated snapshot fallback."""
    evidence = select(
        literal("evidence").label("kind"), FlowEvidence.id.label("id"),
        FlowEvidence.observed_at.label("captured_at"), FlowEvidence.source.label("source"),
    ).where(FlowEvidence.dataset_id == BOARD_ID)
    snapshots = select(
        literal("snapshot").label("kind"), FlowSnapshot.id.label("id"),
        FlowSnapshot.captured_at.label("captured_at"),
        literal("app-published-observation").label("source"),
    ).where(
        FlowSnapshot.board_id == BOARD_ID,
        ~exists(select(FlowEvidence.id).where(
            FlowEvidence.dataset_id == BOARD_ID,
            FlowEvidence.source == "app-published-observation",
            FlowEvidence.observed_at == FlowSnapshot.captured_at,
        )),
    )
    return union_all(evidence, snapshots).subquery()


def capture_order(index):
    return (
        index.c.captured_at,
        case((index.c.source == "app-published-observation", 1), else_=0),
        index.c.id,
    )


def require_supported_source():
    if workspace_config()["source_url"] != DEFAULT_SOURCE_URL:
        raise ValueError(
            "Combined exploration with genuine evidence supports only project 152."
        )


def read_contract(kind, identity, observed_at, source):
    board = db.session.get(FlowBoard, BOARD_ID)
    mapping = board.field_mapping if board else {}
    if kind == "evidence":
        document = db.session.scalar(select(FlowEvidence.document).where(FlowEvidence.id == identity))
        if document is None:
            raise ValueError("The saved observation is unavailable. Reload the workspace to retry.")
        payload = evidence_payload(document, source, mapping)
    else:
        payload = db.session.scalar(select(FlowSnapshot.payload).where(
            FlowSnapshot.id == identity, FlowSnapshot.captured_at == observed_at,
        ))
        if payload is None:
            raise ValueError("The capture changed while loading. Reload the workspace to retry.")
    return observation_contract(payload, observed_at, source, identity, payload.get("mapping", {}))


def observation_for(reporting_date):
    try:
        upper = date.fromisoformat(reporting_date)
    except (ValueError, TypeError):
        raise ValueError("Use a reporting date in YYYY-MM-DD format.") from None
    if upper.isoformat() != reporting_date or upper == date.max:
        raise ValueError("Use a reporting date in YYYY-MM-DD format.")
    require_supported_source()
    index = capture_index()
    row = db.session.execute(
        select(index).where(
            index.c.captured_at < datetime.combine(upper + timedelta(days=1), time.min, tzinfo=UTC)
        ).order_by(*(column.desc() for column in capture_order(index))).limit(1)
    ).first()
    return read_contract(*row) if row else None


def exploratory_dataset():
    dataset = deepcopy(sample_dataset().payload)
    index = capture_index()
    captures = []
    options = {key: set() for key in ["team", "status", "sprint", "repository", "type", "planned", "objective", *METADATA_FIELDS]}
    # Stream one document at a time; retain only small option unions and identities.
    for row in db.session.execute(
        select(index).order_by(*capture_order(index)).execution_options(yield_per=1)
    ):
        require_supported_source()
        contract = read_contract(*row)
        captures.append({key: contract[key] for key in ("id", "capturedAt", "source")})
        for item in contract["items"]:
            for key, values in options.items():
                if key in {"team", "status", "sprint"} or key in item["availableFields"]:
                    value = item.get(key)
                    if value is not None:
                        values.update(value if isinstance(value, list) else [value])
    dataset.update(
        provenance="mixed",
        fictionalHistory=dict(dataset["history"]),
        fictionalDatasetId=dataset["id"],
        realDatasetId=BOARD_ID,
        realObservations=[],
        realCaptures=captures,
        realOptions={key: sorted(values) for key, values in options.items()},
        sprintAliases=[
            {
                "display": "Firebreak",
                "fictionalId": "sample-firebreak",
                "realIterationId": FIREBREAK_ITERATION,
            }
        ],
        realEventCoverage={
            "complete": False,
            "reason": "Webhook fragments do not establish an uninterrupted transition stream or sprint-start baseline.",
        },
    )
    if captures:
        dataset["history"]["to"] = max(
            dataset["history"]["to"],
            captures[-1]["capturedAt"][:10],
        )
    return dataset


def validate_observation(document, source, observed, checksum, mapping):
    payload = evidence_payload(document, source, mapping)
    return observation_contract(
        payload, observed, source, checksum, payload.get("mapping", {})
    )
