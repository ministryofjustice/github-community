import json
import os
import secrets
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path

import click
from flask import Blueprint, current_app, jsonify, render_template, request, session
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError

from app.projects.flow_metrics.archive import export_command
from app.projects.flow_metrics.archive_import import import_archives_command
from app.projects.flow_metrics.collector import BOARD_ID, collect_command
from app.projects.flow_metrics.config import workspace_config
from app.projects.flow_metrics.datasets import (
    SAMPLE_ID,
    import_capture_command,
    init_sample_command,
    remove_sample_command,
)
from app.projects.flow_metrics.db_models import (
    FlowBoard,
    FlowCollectionRun,
    FlowDelivery,
    FlowEvent,
)
from app.projects.flow_metrics.reconciliation import reconcile_command
from app.projects.flow_metrics.service import (
    metadata,
    observation_at,
    result,
    seeds,
    validate_chart,
)
from app.projects.flow_metrics.webhooks import process_command, receive
from app.projects.flow_metrics.workspace import exploratory_dataset
from app.shared.database import db
from app.shared.middleware.auth import requires_auth

flow_metrics_main = Blueprint("flow_metrics_main", __name__, cli_group=None)
flow_metrics_main.add_url_rule("/webhook", "webhook", receive, methods=["POST"])


@flow_metrics_main.get("/")
@requires_auth
def index():
    response = current_app.make_response(
        render_template("projects/flow_metrics/pages/main.html", **workspace_config())
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@flow_metrics_main.get("/api/collection-health")
@requires_auth
def collection_health():
    """Expose aggregate collection health, never real items, in either UI mode."""
    if os.getenv("FLOW_METRICS_ENABLED") != "true":
        response = jsonify(capturedAt=None, status="not_configured", stale=True)
    else:
        try:
            latest = observation_at()
            run = db.session.execute(
                select(FlowCollectionRun)
                .where(FlowCollectionRun.board_id == BOARD_ID)
                .order_by(FlowCollectionRun.started_at.desc()).limit(1)
            ).scalar_one_or_none()
            scheduled_status = None
            health_path = os.getenv("FLOW_METRICS_COLLECTION_HEALTH_FILE")
            if health_path:
                try:
                    health = json.loads(Path(health_path).read_text())
                    scheduled_status = health["status"]
                except FileNotFoundError:
                    scheduled_status = "not_run"
                except (OSError, ValueError, KeyError):
                    current_app.logger.error("Flow Metrics scheduler health could not be read.")
                    scheduled_status = "unavailable"
            response = jsonify(
                capturedAt=latest.captured_at.isoformat() if latest else None,
                status=run.status if run else "not_run",
                scheduledStatus=scheduled_status,
                stale=not latest or latest.captured_date < datetime.now(UTC).date(),
            )
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.error("Flow Metrics collection health database unavailable.")
            response = jsonify(error="Real board collection status is unavailable.")
            response.status_code = 503
    response.headers["Cache-Control"] = "no-store"
    return response


@flow_metrics_main.get("/api/webhook-health")
@requires_auth
def webhook_health():
    """Aggregate inbox states only; never expose delivery payloads."""
    try:
        response = jsonify(
            enabled=os.getenv("FLOW_METRICS_WEBHOOK_ENABLED") == "true",
            deliveries=dict(db.session.execute(
                select(FlowDelivery.status, func.count()).group_by(FlowDelivery.status)
            ).all()),
            evidence=dict(db.session.execute(
                select(FlowEvent.quality, func.count()).group_by(FlowEvent.quality)
            ).all()),
            historicalCoverageComplete=False,
        )
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Flow Metrics webhook health database unavailable.")
        response = jsonify(error="Webhook inbox status is unavailable.")
        response.status_code = 503
    response.headers["Cache-Control"] = "no-store"
    return response


def api(function):
    @wraps(function)
    @requires_auth
    def wrapped(*args, **kwargs):
        if request.method == "POST":
            supplied = request.headers.get("X-Flow-CSRF", "")
            expected = session.get("flow_csrf")
            if not expected or not secrets.compare_digest(expected, supplied):
                return jsonify(
                    error="Session verification failed. Reload the page."
                ), 403
            if request.content_length is None or request.content_length > 150000:
                return jsonify(error="Request exceeds the chart limit."), 413
        try:
            return function(*args, **kwargs)
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.error(
                "Flow Metrics database operation failed; no payload logged."
            )
            return jsonify(
                error="Flow Metrics database is unavailable. No sample fallback is shown."
            ), 503

    return wrapped


@flow_metrics_main.get("/api/workspace")
@api
def workspace():
    live = workspace_config()["live"]
    board = db.session.get(FlowBoard, BOARD_ID if live else SAMPLE_ID)
    if not board:
        return jsonify(error="Initialise the Flow Metrics database before use."), 503
    session.setdefault("flow_csrf", secrets.token_urlsafe(32))
    response = jsonify(
        charts=board.charts,
        revision=board.chart_revision,
        csrf=session["flow_csrf"],
        **({**metadata(), "datasetId": BOARD_ID, "provenance": "real"} if live else {
            "dataset": exploratory_dataset(),
            "datasetId": SAMPLE_ID,
            "provenance": "mixed",
        }),
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@flow_metrics_main.post("/api/charts")
@api
def save_charts():
    body = request.get_json()
    if not isinstance(body, dict) or set(body) != {"charts", "revision"}:
        raise ValueError("Invalid chart update.")
    charts = body["charts"]
    if (
        not isinstance(charts, list)
        or len(charts) > 100
        or type(body["revision"]) is not int
    ):
        raise ValueError("At most 100 shared charts are supported.")
    for chart in charts:
        validate_chart(chart)
    if len({chart["id"] for chart in charts}) != len(charts):
        raise ValueError("Chart IDs must be unique.")
    updated = db.session.execute(
        update(FlowBoard)
        .where(
            FlowBoard.id == (BOARD_ID if workspace_config()["live"] else SAMPLE_ID),
            FlowBoard.chart_revision == body["revision"],
        )
        .values(charts=charts, chart_revision=body["revision"] + 1)
    )
    if updated.rowcount != 1:
        db.session.rollback()
        return jsonify(
            error="Someone else changed the shared charts. Reload before saving; your draft has not been written."
        ), 409
    db.session.commit()
    return jsonify(revision=body["revision"] + 1)


@flow_metrics_main.post("/api/result")
@api
def chart_result():
    if not workspace_config()["live"]:
        return jsonify(error="Use the immutable event contract returned by the fictional workspace."), 400
    response = jsonify(result(request.get_json()))
    response.headers["Cache-Control"] = "no-store"
    return response


@flow_metrics_main.cli.group("flow-metrics")
def commands():
    """Flow Metrics database initialisation and daily collection."""


@commands.command("init")
def initialise():
    """Seed the configured board once, after applying migrations."""
    if db.session.get(FlowBoard, BOARD_ID) is None:
        db.session.add(FlowBoard(id=BOARD_ID, chart_revision=0, charts=seeds()))
        db.session.commit()
    click.echo("Flow Metrics board initialised; existing shared charts preserved.")


commands.add_command(import_archives_command)
commands.add_command(collect_command)
commands.add_command(export_command)
commands.add_command(reconcile_command)
commands.add_command(init_sample_command)
commands.add_command(import_capture_command)
commands.add_command(remove_sample_command)
commands.add_command(process_command)
