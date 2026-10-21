"""Private durable inbox; verified fragments are not a promise of full history."""

import hashlib
import hmac
import json
import os
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

import click
from flask import current_app, jsonify, request
from flask.cli import with_appcontext
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.projects.flow_metrics.collector import BOARD_ID
from app.projects.flow_metrics.db_models import FlowDelivery, FlowEvent
from app.shared.database import db

MAX_BODY = 1024 * 1024
PROJECT_NODE_ID = "PVT_kwDOACGfts4BHZqS"
ITEM_ACTIONS = {
    "created",
    "edited",
    "deleted",
    "archived",
    "restored",
    "converted",
    "reordered",
}


def receiver_config():
    if os.getenv("FLOW_METRICS_WEBHOOK_ENABLED") != "true":
        return None
    secret = os.getenv("FLOW_METRICS_WEBHOOK_SECRET", "")
    org = os.getenv("FLOW_METRICS_WEBHOOK_ORGANISATION_ID", "")
    installation = os.getenv("FLOW_METRICS_WEBHOOK_INSTALLATION_ID", "")
    if (
        len(secret.encode()) < 32
        or len(set(secret)) < 12
        or secret.startswith(("ghp_", "github_pat_", "ghs_"))
        or not org.isdecimal()
        or not installation.isdecimal()
        or int(org) <= 0
        or int(installation) <= 0
    ):
        raise ValueError("webhook_configuration_missing")
    return secret.encode(), int(org), int(installation)


def receive():
    """Dedicated machine-auth endpoint. Never use Microsoft auth/CSRF here."""
    try:
        config = receiver_config()
    except ValueError:
        current_app.logger.error("Flow Metrics webhook configuration invalid.")
        return jsonify(error="Receiver is not configured."), 503
    if config is None:
        return jsonify(error="Receiver is disabled."), 404
    secret, org_id, installation_id = config
    if request.mimetype != "application/json" or request.headers.get(
        "Content-Encoding"
    ):
        return jsonify(error="Use uncompressed application/json."), 415
    if request.content_length is not None and request.content_length > MAX_BODY:
        return jsonify(error="Delivery exceeds the receiver limit."), 413
    body = request.stream.read(MAX_BODY + 1)
    if len(body) > MAX_BODY:
        return jsonify(error="Delivery exceeds the receiver limit."), 413
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not re.fullmatch(r"sha256=[0-9a-f]{64}", signature) or not hmac.compare_digest(
        expected, signature
    ):
        return jsonify(error="Signature verification failed."), 401
    try:
        delivery_id = str(UUID(request.headers.get("X-GitHub-Delivery", "")))
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise TypeError()
    except (ValueError, TypeError, UnicodeError):
        return jsonify(error="Invalid delivery identifier or JSON."), 400
    event = request.headers.get("X-GitHub-Event", "")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,49}", event):
        return jsonify(error="Invalid event header."), 400
    action = payload.get("action", "")
    if not isinstance(action, str) or len(action) > 40:
        return jsonify(error="Invalid action."), 400
    checksum = hashlib.sha256(body).hexdigest()
    try:
        existing = db.session.get(FlowDelivery, delivery_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Flow Metrics delivery lookup database unavailable.")
        return jsonify(error="Durable inbox unavailable; retry delivery."), 503
    if existing:
        if (
            existing.body_sha256 == checksum
            and existing.event == event
            and existing.action == action
        ):
            return jsonify(status="duplicate"), 200
        current_app.logger.error(
            "Flow Metrics conflicting webhook delivery identifier."
        )
        return jsonify(error="Conflicting delivery identifier."), 409
    if event == "ping":
        if not isinstance(payload.get("zen"), str) or not isinstance(
            payload.get("hook"), dict
        ):
            return jsonify(error="Invalid ping."), 400
        status = "ignored"
    else:
        organisation = payload.get("organization") or {}
        installation = payload.get("installation") or {}
        if (
            not isinstance(organisation, dict)
            or not isinstance(installation, dict)
            or type(organisation.get("id")) is not int
            or organisation["id"] != org_id
            or not isinstance(organisation.get("login"), str)
            or organisation["login"].lower() != "ministryofjustice"
            or type(installation.get("id")) is not int
            or installation["id"] != installation_id
        ):
            return jsonify(error="Delivery is outside the configured scope."), 403
        item = payload.get("projects_v2_item")
        project = payload.get("projects_v2")
        if event == "projects_v2_item":
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("node_id"), str)
                or not 1 <= len(item["node_id"]) <= 150
            ):
                return jsonify(error="Project item identity is missing."), 400
            if item.get("project_node_id") != PROJECT_NODE_ID:
                return jsonify(status="ignored_out_of_scope"), 202
            if not action:
                return jsonify(error="Project item action is missing."), 400
            status = "pending"
        elif (
            event == "projects_v2"
            and isinstance(project, dict)
            and project.get("node_id") == PROJECT_NODE_ID
        ):
            status = "pending"
        else:
            return jsonify(status="ignored_irrelevant_event"), 202
    try:
        db.session.add(
            FlowDelivery(
                id=delivery_id,
                event=event,
                action=action,
                body_sha256=checksum,
                body=body,
                received_at=datetime.now(UTC),
                status=status,
                attempts=0,
            )
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        try:
            existing = db.session.get(FlowDelivery, delivery_id)
            if (
                existing
                and existing.body_sha256 == checksum
                and existing.event == event
                and existing.action == action
            ):
                return jsonify(status="duplicate"), 200
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.error(
                "Flow Metrics delivery lookup database unavailable."
            )
            return jsonify(error="Durable inbox unavailable; retry delivery."), 503
        current_app.logger.error(
            "Flow Metrics conflicting webhook delivery identifier."
        )
        return jsonify(error="Conflicting delivery identifier."), 409
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Flow Metrics webhook inbox database unavailable.")
        return jsonify(error="Durable inbox unavailable; retry delivery."), 503
    return jsonify(status="accepted" if status == "pending" else "ignored"), 202


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    return stamp.astimezone(UTC) if stamp.tzinfo else None


def event_fragment(delivery):
    """Extract what the signed payload actually proves, including explicit nulls."""
    payload = json.loads(delivery.body)
    item = payload.get("projects_v2_item") or {}
    changes = payload.get("changes") or {}
    if not isinstance(item, dict) or not isinstance(changes, dict):
        raise TypeError("payload_schema_unprocessable")
    evidence = {
        "action": delivery.action,
        "projectNodeId": PROJECT_NODE_ID,
        "itemNodeId": item.get("node_id"),
        "contentNodeId": item.get("content_node_id"),
        "contentType": item.get("content_type"),
        "changes": payload.get("changes", {}),
        "createdAt": item.get("created_at"),
        "updatedAt": item.get("updated_at"),
        "archivedAt": item.get("archived_at"),
        "receivedAt": delivery.received_at.replace(tzinfo=UTC).isoformat()
        if delivery.received_at.tzinfo is None
        else delivery.received_at.isoformat(),
        "historyEligible": False,
    }
    occurred = None
    basis = "unknown"
    quality, reason = "incomplete", "exact_event_time_or_values_missing"
    if delivery.event == "projects_v2":
        quality, reason = "unsupported", "project_metadata_requires_reconciliation"
    elif delivery.action not in ITEM_ACTIONS:
        quality, reason = "unsupported", "unsupported_item_action"
    elif (
        not isinstance(item.get("content_node_id"), str)
        or not item["content_node_id"]
        or item.get("content_type")
        not in {
            "Issue",
            "PullRequest",
            "DraftIssue",
        }
    ):
        reason = "content_identity_missing_or_inaccessible"
    elif delivery.action == "created":
        occurred, basis = timestamp(item.get("created_at")), "item_created_at"
        if occurred:
            quality, reason = (
                "verified_fragment",
                "membership_creation_only_no_prior_baseline",
            )
    elif delivery.action in {"archived", "restored"}:
        change = changes.get("archived_at")
        if isinstance(change, dict) and "from" in change and "to" in change:
            evidence["from"] = change["from"]
            evidence["to"] = change["to"]
            if delivery.action == "archived" and change["from"] is None:
                occurred, basis = timestamp(change["to"]), "archived_at"
                if occurred and item.get("archived_at") == change["to"]:
                    quality, reason = (
                        "verified_fragment",
                        "archive_change_only_no_history_coverage",
                    )
            elif delivery.action == "restored" and change["to"] is None:
                occurred, basis = timestamp(item.get("updated_at")), "item_updated_at"
                reason = "restore_exact_action_time_unproven"
    elif delivery.action == "edited":
        change = changes.get("field_value")
        if isinstance(change, dict):
            evidence["fieldNodeId"] = change.get("field_node_id")
            evidence["fieldType"] = change.get("field_type")
            evidence["hasFrom"] = "from" in change
            evidence["hasTo"] = "to" in change
            if "from" in change:
                evidence["from"] = change["from"]
            if "to" in change:
                evidence["to"] = change["to"]
            occurred, basis = timestamp(item.get("updated_at")), "item_updated_at"
            reason = "field_change_values_or_transition_timestamp_unproven"
    elif delivery.action in {"deleted", "converted", "reordered"}:
        occurred, basis = timestamp(item.get("updated_at")), "item_updated_at"
        reason = "lifecycle_exact_action_time_or_semantics_unproven"
    # A future/invalid source time must never be made valid using receipt time.
    received = delivery.received_at
    if received.tzinfo is None:
        received = received.replace(tzinfo=UTC)
    if occurred and occurred > received + timedelta(minutes=5):
        quality, reason = "incomplete", "source_time_after_receipt"
    evidence["quality"] = quality
    return FlowEvent(
        id=delivery.id,
        dataset_id=BOARD_ID,
        item_id=item.get("node_id"),
        occurred_at=occurred,
        time_basis=basis,
        evidence=evidence,
        quality=quality,
        reason=reason,
    )


def process_deliveries(limit=100, replay=None):
    """Transactional per-delivery worker, safe to run concurrently or after crashes."""
    query = select(FlowDelivery.id).order_by(FlowDelivery.received_at, FlowDelivery.id)
    if replay:
        query = query.where(FlowDelivery.id == replay)
    else:
        query = query.where(FlowDelivery.status.in_(["pending", "failed"]))
    identities = db.session.execute(query.limit(limit)).scalars().all()
    count = 0
    failures = 0
    for identity in identities:
        db.session.rollback()
        delivery = db.session.execute(
            select(FlowDelivery)
            .where(FlowDelivery.id == identity)
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if not delivery or delivery.status == "ignored":
            db.session.rollback()
            continue
        if db.session.get(FlowEvent, identity) is not None:
            db.session.rollback()
            continue
        if delivery.status not in {"pending", "failed"} and not replay:
            db.session.rollback()
            continue
        delivery.attempts += 1
        try:
            fragment = event_fragment(delivery)
            prior_delivery = db.session.scalar(
                select(FlowDelivery)
                .where(
                    FlowDelivery.body_sha256 == delivery.body_sha256,
                    FlowDelivery.id != delivery.id,
                    FlowDelivery.received_at < delivery.received_at,
                )
                .order_by(FlowDelivery.received_at)
                .limit(1)
            )
            if prior_delivery:
                fragment.evidence["replayOf"] = prior_delivery.id
                fragment.quality = "incomplete"
                fragment.reason = "duplicate_signed_payload"
            if fragment.item_id and fragment.occurred_at:
                fragment.evidence["outOfOrder"] = (
                    db.session.scalar(
                        select(FlowEvent.id)
                        .where(
                            FlowEvent.item_id == fragment.item_id,
                            FlowEvent.occurred_at > fragment.occurred_at,
                        )
                        .limit(1)
                    )
                    is not None
                )
            fragment.evidence["quality"] = fragment.quality
        except (ValueError, KeyError, TypeError):
            delivery.status = "failed"
            delivery.error_code = "payload_schema_unprocessable"
            delivery.processed_at = datetime.now(UTC)
            db.session.commit()
            current_app.logger.error(
                "Flow Metrics delivery processing failed: payload_schema_unprocessable."
            )
            failures += 1
            continue
        db.session.add(fragment)
        delivery.status = "processed"
        delivery.error_code = (
            fragment.reason if fragment.quality != "verified_fragment" else None
        )
        delivery.processed_at = datetime.now(UTC)
        db.session.commit()
        count += 1
    return {"processed": count, "failed": failures}


@click.command("process-deliveries")
@click.option("--limit", type=click.IntRange(1, 500), default=100)
@click.option("--replay", type=click.UUID)
@with_appcontext
def process_command(limit, replay):
    """Drain/replay durable inbox; no network calls and no inferred history."""
    try:
        outcome = process_deliveries(limit, str(replay) if replay else None)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Flow Metrics delivery worker database unavailable.")
        raise click.ClickException(
            "Processing failed; retry after restoring database access."
        ) from None
    if outcome["failed"]:
        raise click.ClickException(
            f"{outcome['failed']} deliveries failed processing; inspect inbox states and retry after correcting the schema adapter."
        )
    click.echo(
        f"Processed {outcome['processed']} deliveries. Historical coverage is not implied."
    )
