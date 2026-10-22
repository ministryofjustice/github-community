"""Generated webhook fixtures only: no real deliveries or board records."""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from flask import Flask
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.projects.flow_metrics.collector import BOARD_ID
from app.projects.flow_metrics.db_models import FlowDataset, FlowDelivery, FlowEvent
from app.projects.flow_metrics.routes.main import flow_metrics_main
from app.projects.flow_metrics.webhooks import (
    MAX_BODY,
    PROJECT_NODE_ID,
    process_deliveries,
)
from app.shared.database import db

SECRET = "synthetic-test-only-key-not-a-production-secret"
URL = "/flow-metrics/webhook"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("FLOW_METRICS_WEBHOOK_ENABLED", "true")
    monkeypatch.setenv("FLOW_METRICS_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("FLOW_METRICS_WEBHOOK_ORGANISATION_ID", "101")
    monkeypatch.setenv("FLOW_METRICS_WEBHOOK_INSTALLATION_ID", "202")
    application = Flask("app")
    application.config.update(TESTING=True, SECRET_KEY="test", SQLALCHEMY_DATABASE_URI="sqlite://")
    db.init_app(application)
    application.register_blueprint(flow_metrics_main, url_prefix="/flow-metrics/")
    with application.app_context():
        db.create_all()
        db.session.add(FlowDataset(id=BOARD_ID, provenance="real", content_sha256="", payload={}))
        db.session.commit()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


def payload(action="edited", **extra):
    return {
        "action": action,
        "organization": {"id": 101, "login": "ministryofjustice"},
        "installation": {"id": 202},
        "projects_v2_item": {
            "node_id": "synthetic-item", "project_node_id": PROJECT_NODE_ID,
            "content_node_id": "synthetic-issue", "content_type": "Issue",
            "created_at": "2026-10-16T12:00:00Z", "updated_at": "2026-10-19T12:00:00Z",
            "archived_at": None,
        },
        "changes": {"field_value": {"field_type": "single_select", "field_node_id": "synthetic-status-field"}},
        **extra,
    }


def send(client, document=None, *, identity=None, event="projects_v2_item", body=None, headers=None):
    raw = body if body is not None else json.dumps(document or payload(), ensure_ascii=False).encode()
    return client.post(URL, data=raw, content_type="application/json", headers={
        "X-GitHub-Delivery": identity or str(uuid4()), "X-GitHub-Event": event,
        "X-Hub-Signature-256": "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest(),
        **(headers or {}),
    })


def test_pending_deliveries_precede_failed_backlog_with_deterministic_ties(app):
    with app.app_context():
        old = datetime(2026, 10, 16, tzinfo=UTC)
        for index in range(105):
            db.session.add(FlowDelivery(
                id=f"generated-failed-{index:03}", event="projects_v2_item", action="edited",
                body_sha256=f"{index:064x}", body=b'{"changes":["generated-invalid"]}', received_at=old,
                status="failed", attempts=3,
            ))
        for identity in ["generated-pending-b", "generated-pending-a"]:
            encoded = json.dumps(payload()).encode()
            db.session.add(FlowDelivery(
                id=identity, event="projects_v2_item", action="edited",
                body_sha256=hashlib.sha256(encoded).hexdigest(), body=encoded,
                received_at=old + timedelta(days=1), status="pending", attempts=0,
            ))
        db.session.commit()
        assert process_deliveries(limit=1) == {"processed": 1, "failed": 0}
        assert db.session.get(FlowDelivery, "generated-pending-a").status == "processed"
        assert db.session.get(FlowDelivery, "generated-pending-b").status == "pending"
        assert process_deliveries(limit=1) == {"processed": 1, "failed": 0}
        assert db.session.get(FlowDelivery, "generated-pending-b").status == "processed"
        assert process_deliveries(limit=1) == {"processed": 0, "failed": 1}
        assert db.session.get(FlowDelivery, "generated-failed-000").attempts == 4
        assert db.session.get(FlowDelivery, "generated-failed-001").attempts == 3
        assert process_deliveries(limit=1, replay="generated-failed-104") == {"processed": 0, "failed": 1}
        assert db.session.get(FlowDelivery, "generated-failed-104").attempts == 4


def test_signature_disabled_misconfigured_content_size_and_login_boundary(app, monkeypatch):
    client = app.test_client()
    with patch("app.shared.middleware.auth.app_config.auth_enabled", True):
        assert send(client).status_code == 202  # Machine authentication, not Microsoft session.
        assert client.get("/flow-metrics/api/workspace").status_code == 302
        assert client.get("/flow-metrics/api/webhook-health").status_code == 302
    with patch("app.shared.middleware.auth.app_config.auth_enabled", False):
        health = client.get("/flow-metrics/api/webhook-health")
    assert health.json["deliveries"] == {"pending": 1}
    assert health.json["historicalCoverageComplete"] is False
    assert health.headers["Cache-Control"] == "no-store"
    assert send(client, headers={"X-Hub-Signature-256": "sha256=" + "0" * 64}).status_code == 401
    assert send(client, headers={"X-Hub-Signature": "sha1=fake", "X-Hub-Signature-256": ""}).status_code == 401
    assert client.post(URL, data="{}", content_type="text/plain").status_code == 415
    assert send(client, headers={"Content-Encoding": "gzip"}).status_code == 415
    assert send(client, body=b"x" * (MAX_BODY + 1)).status_code == 413
    assert send(client, body=b"[").status_code == 400
    assert send(client, body=b"[]").status_code == 400
    assert send(client, headers={"X-GitHub-Delivery": "not-a-uuid"}).status_code == 400
    monkeypatch.setenv("FLOW_METRICS_WEBHOOK_SECRET", "weak")
    assert send(client).status_code == 503
    monkeypatch.setenv("FLOW_METRICS_WEBHOOK_ENABLED", "false")
    assert send(client).status_code == 404


def test_raw_bytes_unicode_mutation_durable_dedup_and_conflict(app):
    client = app.test_client()
    identity = str(uuid4())
    document = payload(note="Generated unicode £ test")
    raw = json.dumps(document, ensure_ascii=False, indent=2).encode()
    assert send(client, body=raw, identity=identity).status_code == 202
    assert send(client, body=raw, identity=identity).json["status"] == "duplicate"
    assert send(client, document, identity=identity).status_code == 409
    signature = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    assert send(client, body=raw+b" ", headers={"X-Hub-Signature-256": signature}).status_code == 401
    assert send(client, body=raw, identity=identity, event="projects_v2").status_code == 409
    with app.app_context():
        delivery = db.session.get(FlowDelivery, identity)
        assert delivery.body == raw
        assert delivery.status == "pending"
        assert delivery.body_sha256 == hashlib.sha256(raw).hexdigest()
        assert db.session.scalar(select(func.count()).select_from(FlowDelivery)) == 1


@pytest.mark.parametrize("field,value", [
    ("organization", {"id": 999, "login": "ministryofjustice"}),
    ("organization", {"id": 101, "login": "wrong-org"}),
    ("organization", {"id": 101, "login": []}),
    ("installation", {"id": 999}), ("installation", None),
])
def test_scope_fails_closed(app, field, value):
    assert send(app.test_client(), payload(**{field: value})).status_code == 403
    with app.app_context():
        assert db.session.scalar(select(func.count()).select_from(FlowDelivery)) == 0


def test_irrelevant_scope_ping_and_unknown_action_states(app):
    client = app.test_client()
    other = payload()
    other["projects_v2_item"]["project_node_id"] = "synthetic-other-board"
    assert send(client, other).json["status"] == "ignored_out_of_scope"
    assert send(client, payload(), event="issues").json["status"] == "ignored_irrelevant_event"
    assert send(client, {"zen": "Generated ping", "hook": {}}, event="ping").status_code == 202
    assert send(client, payload(), event="ping").status_code == 400
    identity = str(uuid4())
    assert send(client, payload("future_action"), identity=identity).status_code == 202
    with app.app_context():
        assert process_deliveries() == {"processed": 1, "failed": 0}
        assert db.session.get(FlowEvent, identity).quality == "unsupported"


def test_database_failure_is_not_success_and_does_not_log_payload(app, caplog):
    raw = payload(note="PRIVATE-FIXTURE-CONTENT")
    with patch("app.projects.flow_metrics.webhooks.db.session.commit", side_effect=SQLAlchemyError("private-token")):
        assert send(app.test_client(), raw).status_code == 503
    assert "PRIVATE-FIXTURE-CONTENT" not in caplog.text
    assert "private-token" not in caplog.text
    assert "inbox database unavailable" in caplog.text
    with app.app_context():
        assert db.session.scalar(select(func.count()).select_from(FlowDelivery)) == 0


def test_changes_clears_out_of_order_replay_and_coverage_boundaries(app):
    client = app.test_client()
    edits = []
    for at, before, after in [
        ("2026-10-19T12:00:00Z", "synthetic-option-a", "synthetic-option-b"),
        ("2026-10-18T12:00:00Z", "synthetic-option-b", None),
    ]:
        identity = str(uuid4())
        document = payload()
        document["projects_v2_item"]["updated_at"] = at
        document["changes"]["field_value"].update({"from": before, "to": after})
        assert send(client, document, identity=identity).status_code == 202
        edits.append(identity)
    with app.app_context():
        assert process_deliveries() == {"processed": 2, "failed": 0}
        events = [db.session.get(FlowEvent, key) for key in edits]
        assert all(event.quality == "incomplete" for event in events)
        assert events[1].evidence["hasTo"] is True
        assert events[1].evidence["to"] is None
        assert events[1].occurred_at < events[0].occurred_at
        assert events[1].evidence["outOfOrder"] is True
        assert all(event.time_basis == "item_updated_at" and not event.evidence["historyEligible"] for event in events)
        assert process_deliveries(replay=edits[0]) == {"processed": 0, "failed": 0}
        assert db.session.scalar(select(func.count()).select_from(FlowEvent)) == 2
        assert db.session.get(FlowDelivery, edits[0]).attempts == 1
    repeated = str(uuid4())
    assert send(client, document, identity=repeated).status_code == 202
    with app.app_context():
        assert process_deliveries()["processed"] == 1
        fragment = db.session.get(FlowEvent, repeated)
        assert fragment.evidence["replayOf"] == edits[1]
        assert fragment.reason == "duplicate_signed_payload"


@pytest.mark.parametrize("action,quality", [
    ("created", "verified_fragment"), ("archived", "verified_fragment"),
    ("restored", "incomplete"), ("deleted", "incomplete"),
    ("converted", "incomplete"), ("reordered", "incomplete"),
])
def test_lifecycle_fragments_are_not_synthetic_status_events(app, action, quality):
    document = payload(action)
    if action == "archived":
        document["projects_v2_item"]["archived_at"] = "2026-10-19T12:00:00Z"
        document["changes"] = {"archived_at": {"from": None, "to": "2026-10-19T12:00:00Z"}}
    elif action == "restored":
        document["changes"] = {"archived_at": {"from": "2026-10-18T12:00:00Z", "to": None}}
    identity = str(uuid4())
    assert send(app.test_client(), document, identity=identity).status_code == 202
    with app.app_context():
        assert process_deliveries()["processed"] == 1
        event = db.session.get(FlowEvent, identity)
        assert event.quality == quality
        assert event.evidence["historyEligible"] is False
        assert event.dataset_id == BOARD_ID
        assert event.item_id == "synthetic-item"


def test_missing_inaccessible_content_invalid_time_and_malformed_changes_are_explicit(app):
    client = app.test_client()
    documents = []
    missing = payload()
    missing["projects_v2_item"]["content_node_id"] = None
    documents.append((missing, "content_identity_missing_or_inaccessible"))
    future = payload("created")
    future["projects_v2_item"]["created_at"] = "2999-01-01T00:00:00Z"
    documents.append((future, "source_time_after_receipt"))
    for document, reason in documents:
        identity = str(uuid4())
        assert send(client, document, identity=identity).status_code == 202
        with app.app_context():
            process_deliveries()
            event = db.session.get(FlowEvent, identity)
            assert event.quality == "incomplete"
            assert event.reason == reason
    broken_id = str(uuid4())
    assert send(client, payload(changes=[]), identity=broken_id).status_code == 202
    with app.app_context():
        # Empty changes are simply missing evidence, not invented old/new values.
        process_deliveries()
        assert db.session.get(FlowEvent, broken_id).quality == "incomplete"


def test_processing_failure_retries_durably_and_cli_reports_it(app):
    identity = str(uuid4())
    assert send(app.test_client(), payload(changes=["bad"]), identity=identity).status_code == 202
    with app.app_context():
        assert process_deliveries() == {"processed": 0, "failed": 1}
        assert db.session.get(FlowDelivery, identity).status == "failed"
        assert db.session.get(FlowDelivery, identity).attempts == 1
        assert db.session.get(FlowEvent, identity) is None
    outcome = app.test_cli_runner().invoke(args=["flow-metrics", "process-deliveries"])
    assert outcome.exit_code != 0
    with app.app_context():
        assert db.session.get(FlowDelivery, identity).attempts == 2


def test_project_field_rename_requires_reconcile_not_status_rewrite(app):
    identity = str(uuid4())
    document = payload(projects_v2={"node_id": PROJECT_NODE_ID}, changes={"name": {"from": "Old name"}})
    assert send(app.test_client(), document, identity=identity, event="projects_v2").status_code == 202
    with app.app_context():
        process_deliveries()
        event = db.session.get(FlowEvent, identity)
        assert event.quality == "unsupported"
        assert event.reason == "project_metadata_requires_reconciliation"
