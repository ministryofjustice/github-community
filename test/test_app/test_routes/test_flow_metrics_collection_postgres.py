"""Opt-in cross-process checks, always in a disposable PostgreSQL schema."""

import json
import multiprocessing
import os
import time
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from flask import Flask
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.projects.flow_metrics.archive import export_snapshot
from app.projects.flow_metrics.archive_import import import_archives
from app.projects.flow_metrics.collector import (
    BOARD_ID,
    CollectionError,
    collect,
    publish,
)
from app.projects.flow_metrics.db_models import (
    FlowBoard,
    FlowCollectionRun,
    FlowEvidence,
    FlowSnapshot,
)
from app.shared.database import db


def application(uri, schema, name):
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=uri,
        SQLALCHEMY_ENGINE_OPTIONS={
            "connect_args": {
                "options": f"-c search_path={schema}",
                "application_name": name,
            },
        },
    )
    db.init_app(app)
    return app


def generated_payload(name):
    return {
        "project_id": "generated-project",
        "fields": [{"id": "generated-status", "name": "Status"}],
        "items": [{
            "id": f"generated-{name}",
            "content": {"__typename": "Issue", "title": "Generated concurrency test"},
            "fields": [],
        }],
    }


def worker(uri, schema, name, entered, release, output, fail):
    app = application(uri, schema, name)

    def fetch(*args):
        entered.set()
        if not release.wait(15):
            raise CollectionError("generated_test_timeout")
        if fail == "collection":
            raise CollectionError("generated_collection_failure")
        return generated_payload(name)

    def publish_result(*args):
        if fail == "publication":
            raise SQLAlchemyError("generated_publication_failure")
        return publish(*args)

    try:
        with app.app_context(), patch(
            "app.projects.flow_metrics.collector.collect_payload", side_effect=fetch,
        ), patch(
            "app.projects.flow_metrics.collector.publish", side_effect=publish_result,
        ):
            output.put((name, collect(object())))
    except CollectionError as error:
        output.put((name, str(error)))


def import_worker(uri, schema, name, directory, output):
    app = application(uri, schema, name)
    with app.app_context():
        summary = import_archives(directory, datetime(2000, 1, 1, tzinfo=UTC).date())
        output.put((name, summary["new"]))


@pytest.fixture
def isolated_postgres():
    uri = os.environ.get("FLOW_METRICS_TEST_DATABASE_URL")
    if not uri:
        pytest.skip("Set FLOW_METRICS_TEST_DATABASE_URL for isolated PostgreSQL checks.")
    engine = create_engine(uri)
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.fail("Collection lock checks require PostgreSQL.")
    schema = f"flow_test_{uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    app = application(uri, schema, schema)
    try:
        with app.app_context():
            db.create_all()
            db.session.add(FlowBoard(id=BOARD_ID, charts=[], field_mapping={}))
            db.session.add(FlowSnapshot(
                id="generated-prior", board_id=BOARD_ID,
                captured_date=datetime(2000, 1, 1, tzinfo=UTC).date(),
                captured_at=datetime(2000, 1, 1, tzinfo=UTC),
                payload=generated_payload("prior"),
            ))
            db.session.commit()
        yield uri, schema, engine, app
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        with engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        engine.dispose()


@pytest.mark.parametrize("first_fails", ["", "collection", "publication"])
def test_processes_serialize_collection_and_recover_after_failure(isolated_postgres, first_fails):
    uri, schema, engine, app = isolated_postgres
    context = multiprocessing.get_context("spawn")
    entered_a, entered_b = context.Event(), context.Event()
    release_a, release_b = context.Event(), context.Event()
    release_b.set()
    output = context.Queue()
    names = [f"{schema}_a", f"{schema}_b"]
    processes = [
        context.Process(target=worker, args=(
            uri, schema, names[0], entered_a, release_a, output, first_fails,
        )),
        context.Process(target=worker, args=(
            uri, schema, names[1], entered_b, release_b, output, "",
        )),
    ]
    try:
        processes[0].start()
        assert entered_a.wait(10), "First collector did not start fetching."
        processes[1].start()
        deadline = time.monotonic() + 10
        blocked = False
        while time.monotonic() < deadline:
            with engine.connect() as connection:
                blocked = connection.scalar(text(
                    "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                    "WHERE application_name = :name AND wait_event_type = 'Lock')"
                ), {"name": names[1]})
            if blocked:
                break
            time.sleep(0.02)
        assert blocked, "Second process did not wait for the database lock."
        assert not entered_b.is_set(), "Overlapping collector fetched before the lock."
        release_a.set()
        outcomes = dict(output.get(timeout=15) for _ in processes)
        for process in processes:
            process.join(10)
            assert process.exitcode == 0
        assert outcomes[names[0]] == {
            "": 1, "collection": "generated_collection_failure",
            "publication": "snapshot_publication_failed",
        }[first_fails]
        assert outcomes[names[1]] == 1
        with app.app_context():
            snapshots = db.session.scalars(select(FlowSnapshot).order_by(
                FlowSnapshot.captured_at,
            )).all()
            assert snapshots[0].payload == generated_payload("prior")
            assert snapshots[-1].payload["items"][0]["id"] == f"generated-{names[1]}"
            evidence = db.session.scalars(select(FlowEvidence)).all()
            assert len(evidence) == (1 if first_fails else 2)
            if not first_fails:
                assert {row.document["payload"]["items"][0]["id"] for row in evidence} == {
                    f"generated-{name}" for name in names
                }
            runs = db.session.scalars(select(FlowCollectionRun).order_by(
                FlowCollectionRun.started_at,
            )).all()
            assert [run.status for run in runs] == [
                "failed" if first_fails else "complete", "complete",
            ]
            assert snapshots[-1].captured_at <= runs[-1].completed_at
    finally:
        release_a.set()
        for process in processes:
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(10)
        output.close()


def test_private_import_waits_for_collector_lock_and_preserves_newer_capture(isolated_postgres, tmp_path):
    uri, schema, engine, app = isolated_postgres
    with app.app_context():
        snapshot = FlowSnapshot(
            id="generated-import", board_id=BOARD_ID,
            captured_date=datetime(2001, 1, 1, tzinfo=UTC).date(),
            captured_at=datetime(2001, 1, 1, tzinfo=UTC),
            payload={
                "project_id": "generated-project", "fields": [],
                "items": [{
                    "id": "generated-imported-item", "archived": False, "fields": [],
                    "content": {
                        "__typename": "DraftIssue", "title": "Generated archive item",
                        "createdAt": "2000-01-01T00:00:00Z",
                    },
                }],
            },
        )
        exported = export_snapshot(snapshot, tmp_path)
        original = json.loads(exported.read_text())
    context = multiprocessing.get_context("spawn")
    entered, release = context.Event(), context.Event()
    output = context.Queue()
    collector_name, importer_name = f"{schema}_collector", f"{schema}_importer"
    processes = [
        context.Process(target=worker, args=(
            uri, schema, collector_name, entered, release, output, "",
        )),
        context.Process(target=import_worker, args=(
            uri, schema, importer_name, str(tmp_path), output,
        )),
    ]
    try:
        processes[0].start()
        assert entered.wait(10)
        processes[1].start()
        deadline = time.monotonic() + 10
        blocked = False
        while time.monotonic() < deadline:
            with engine.connect() as connection:
                blocked = connection.scalar(text(
                    "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                    "WHERE application_name = :name AND wait_event_type = 'Lock')"
                ), {"name": importer_name})
            if blocked:
                break
            time.sleep(0.02)
        assert blocked, "Importer must wait for collector's board row lock."
        with app.app_context():
            assert db.session.scalar(select(FlowEvidence.id).limit(1)) is None
        release.set()
        assert dict(output.get(timeout=15) for _ in processes) == {
            collector_name: 1, importer_name: 1,
        }
        for process in processes:
            process.join(10)
            assert process.exitcode == 0
        with app.app_context():
            evidence = db.session.scalars(select(FlowEvidence)).all()
            assert len(evidence) == 2
            assert any(row.document == original for row in evidence)
            latest = db.session.scalar(select(FlowSnapshot).order_by(FlowSnapshot.captured_at.desc()))
            assert latest.payload == {**generated_payload(collector_name), "mapping": db.session.get(FlowBoard, BOARD_ID).field_mapping}
            assert db.session.get(FlowBoard, BOARD_ID).charts == []
    finally:
        release.set()
        for process in processes:
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(10)
        output.close()
