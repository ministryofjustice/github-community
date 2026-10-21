"""Source-aware exploration contract; never turn observations into events."""

from copy import deepcopy
from datetime import UTC, date, timedelta
from types import SimpleNamespace

from sqlalchemy import select

from app.projects.flow_metrics.collector import BOARD_ID, ESTIMATION_FIELD_ID
from app.projects.flow_metrics.config import DEFAULT_SOURCE_URL, workspace_config
from app.projects.flow_metrics.datasets import sample_dataset
from app.projects.flow_metrics.db_models import (
    FlowBoard,
    FlowEvent,
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


def exploratory_dataset():
    dataset = deepcopy(sample_dataset().payload)
    board = db.session.get(FlowBoard, BOARD_ID)
    mapping = board.field_mapping if board else {}
    observations = {}
    for evidence in db.session.execute(
        select(FlowEvidence)
        .where(FlowEvidence.dataset_id == BOARD_ID)
        .order_by(FlowEvidence.observed_at)
    ).scalars():
        payload = evidence_payload(evidence.document, evidence.source, mapping)
        contract = observation_contract(
            payload,
            evidence.observed_at,
            evidence.source,
            evidence.id,
            payload.get("mapping", {}),
        )
        observations[contract["id"]] = contract
    # The daily published view remains supported even before a private import.
    for snapshot in db.session.execute(
        select(FlowSnapshot)
        .where(FlowSnapshot.board_id == BOARD_ID)
        .order_by(FlowSnapshot.captured_at)
    ).scalars():
        contract = observation_contract(
            snapshot.payload,
            snapshot.captured_at,
            "app-published-observation",
            snapshot.id,
            snapshot.payload.get("mapping", {}),
        )
        if not any(
            existing["capturedAt"] == contract["capturedAt"]
            and existing["source"] == contract["source"]
            for existing in observations.values()
        ):
            observations[contract["id"]] = contract
    ordered = sorted(
        observations.values(),
        key=lambda observation: (
            observation["capturedAt"],
            observation["source"] == "app-published-observation",
            observation["id"],
        ),
    )
    if ordered and workspace_config()["source_url"] != DEFAULT_SOURCE_URL:
        raise ValueError(
            "Combined exploration with genuine evidence supports only project 152."
        )
    dataset.update(
        provenance="mixed",
        fictionalDatasetId=dataset["id"],
        realDatasetId=BOARD_ID,
        realObservations=ordered,
        sprintAliases=[
            {
                "display": "Firebreak",
                "fictionalId": "sample-firebreak",
                "realIterationId": FIREBREAK_ITERATION,
            }
        ],
        verifiedRealEvents=[
            {
                "deliveryId": event.id,
                "itemId": f"real:{event.item_id}" if event.item_id else None,
                "occurredAt": event.occurred_at.isoformat()
                if event.occurred_at
                else None,
                "timeBasis": event.time_basis,
                "quality": event.quality,
                "reason": event.reason,
                "evidence": event.evidence,
            }
            for event in db.session.execute(
                select(FlowEvent)
                .where(FlowEvent.dataset_id == BOARD_ID)
                .order_by(FlowEvent.occurred_at, FlowEvent.id)
            ).scalars()
        ],
        realEventCoverage={
            "complete": False,
            "reason": "Webhook fragments do not establish an uninterrupted transition stream or sprint-start baseline.",
        },
    )
    if ordered:
        dataset["history"]["to"] = max(
            dataset["history"]["to"],
            ordered[-1]["capturedAt"][:10],
        )
    return dataset
