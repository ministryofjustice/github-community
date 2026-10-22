"""Opt-in cross-process checks, always in a disposable PostgreSQL schema."""

import json
import multiprocessing
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from flask import Flask
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from app.projects.flow_metrics.archive import export_snapshot
from app.projects.flow_metrics.archive_import import ArchiveImportError, import_archives
from app.projects.flow_metrics.collector import (
    BOARD_ID,
    CollectionError,
    collect,
    publish,
)
from app.projects.flow_metrics.datasets import retain_evidence
from app.projects.flow_metrics.db_models import (
    FlowBoard,
    FlowCollectionRun,
    FlowDataset,
    FlowDelivery,
    FlowEvent,
    FlowEvidence,
    FlowSnapshot,
)
from app.projects.flow_metrics.webhooks import process_deliveries
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
            "archived": False,
            "content": {"__typename": "Issue", "title": "Generated concurrency test",
                        "createdAt": "1999-01-01T00:00:00Z", "state": "OPEN"},
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


def import_worker(uri, schema, name, directory, output, single=False, entered=None, release=None, fail=False):
    def retain(document):
        if entered is not None:
            entered.set()
            if not release.wait(15):
                raise SQLAlchemyError("generated_test_timeout")
        if fail:
            raise SQLAlchemyError("generated_import_failure")
        return retain_evidence(document)

    app = application(uri, schema, name)
    with app.app_context(), patch(
        "app.projects.flow_metrics.archive_import.retain_evidence", side_effect=retain,
    ), patch(
        "app.projects.flow_metrics.datasets.retain_evidence", side_effect=retain,
    ):
        if single:
            from app.projects.flow_metrics.datasets import import_capture_command
            result = app.test_cli_runner().invoke(
                import_capture_command, ["--file", str(next(Path(directory).glob("*.json")))],
            )
            assert result.exit_code == (1 if fail else 0), result.output
            output.put((name, "generated_import_failure" if fail else 1))
        else:
            try:
                summary = import_archives(directory, datetime(2000, 1, 1, tzinfo=UTC).date())
                output.put((name, summary["new"]))
            except ArchiveImportError:
                if not fail:
                    raise
                output.put((name, "generated_import_failure"))


def delivery_worker(uri, schema, name, entered, release, output):
    from app.projects.flow_metrics.webhooks import event_fragment

    def fragment(delivery):
        if entered is not None:
            entered.set()
            if not release.wait(15):
                raise ValueError("generated_test_timeout")
        return event_fragment(delivery)

    app = application(uri, schema, name)
    with app.app_context(), patch(
        "app.projects.flow_metrics.webhooks.event_fragment", side_effect=fragment,
    ):
        output.put((name, process_deliveries()))


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


@pytest.mark.parametrize("single", [False, True])
def test_private_import_waits_for_collector_lock_and_preserves_newer_capture(isolated_postgres, tmp_path, single):
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
            uri, schema, importer_name, str(tmp_path), output, single,
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
        assert blocked, "Importer must wait for the collector's advisory mutex."
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


@pytest.mark.parametrize("change_mapping", [False, True])
def test_chart_save_during_fetch_finishes_and_mapping_race_fails_explicitly(isolated_postgres, change_mapping):
    uri, schema, _engine, app = isolated_postgres
    context = multiprocessing.get_context("spawn")
    entered, release = context.Event(), context.Event()
    output = context.Queue()
    name = f"{schema}_slow"
    process = context.Process(target=worker, args=(uri, schema, name, entered, release, output, ""))
    try:
        process.start()
        assert entered.wait(10)
        # Independent DB connection with an actual server-side timeout: a chart-row
        # lock across fetching would fail here instead of hanging the test.
        with app.app_context():
            db.session.execute(text("SET LOCAL lock_timeout = '1500ms'"))
            changes = {"charts": [{"id": "generated-concurrent-chart"}], "chart_revision": 1}
            if change_mapping:
                changes["field_mapping"] = {"status": "generated-changed-mapping"}
            updated = db.session.execute(
                update(FlowBoard).where(FlowBoard.id == BOARD_ID, FlowBoard.chart_revision == 0)
                .values(**changes)
            )
            assert updated.rowcount == 1
            db.session.commit()
        release.set()
        assert output.get(timeout=15) == (
            name, "field_mapping_changed_during_collection" if change_mapping else 1,
        )
        process.join(10)
        assert process.exitcode == 0
        with app.app_context():
            board = db.session.get(FlowBoard, BOARD_ID)
            assert board.chart_revision == 1 and board.charts == [{"id": "generated-concurrent-chart"}]
            if change_mapping:
                assert board.field_mapping == {"status": "generated-changed-mapping"}
                assert len(db.session.scalars(select(FlowSnapshot)).all()) == 1
                with patch("app.projects.flow_metrics.collector.collect_payload",
                           return_value=generated_payload("mapping-retry")) as fetch:
                    assert collect(object()) == 1
                assert fetch.call_args.args[1] == {"status": "generated-changed-mapping"}
                latest = db.session.scalar(select(FlowSnapshot).order_by(FlowSnapshot.captured_at.desc()))
                assert latest.payload["mapping"]["status"] == "generated-changed-mapping"
            else:
                assert len(db.session.scalars(select(FlowSnapshot)).all()) == 2
    finally:
        release.set()
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(10)
        output.close()


def test_disconnected_collector_releases_mutex(isolated_postgres):
    uri, schema, _engine, _app = isolated_postgres
    context = multiprocessing.get_context("spawn")
    entered, release = context.Event(), context.Event()
    output = context.Queue()
    first = context.Process(target=worker, args=(uri, schema, "generated-crash", entered, release, output, ""))
    release_next = context.Event()
    entered_next = context.Event()
    release_next.set()
    second = context.Process(target=worker, args=(
        uri, schema, "generated-after-crash", entered_next, release_next, output, "",
    ))
    try:
        first.start()
        assert entered.wait(10)
        first.terminate()
        first.join(10)
        second.start()
        assert output.get(timeout=15) == ("generated-after-crash", 1)
        second.join(10)
        assert second.exitcode == 0
    finally:
        for process in (first, second):
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(10)
        output.close()


@pytest.mark.parametrize("single", [False, True])
@pytest.mark.parametrize("fail", [False, True])
def test_collector_waits_for_import_and_import_rollback_releases_mutex(isolated_postgres, tmp_path, single, fail):
    uri, schema, engine, app = isolated_postgres
    with app.app_context():
        prior = db.session.get(FlowSnapshot, "generated-prior")
        prior.payload = {
            "fields": [], "items": [{
                "id": "generated-valid-import", "archived": False, "fields": [],
                "content": {"__typename": "Issue", "title": "Generated",
                            "createdAt": "1999-01-01T00:00:00Z", "state": "OPEN"},
            }],
        }
        db.session.commit()
        export_snapshot(prior, tmp_path)
    context = multiprocessing.get_context("spawn")
    entered, release, fetched, fetch_release = [context.Event() for _ in range(4)]
    fetch_release.set()
    output = context.Queue()
    importer = context.Process(target=import_worker, args=(
        uri, schema, "generated-held-import", str(tmp_path), output, single, entered, release, fail,
    ))
    collector = context.Process(target=worker, args=(
        uri, schema, f"{schema}_waiting", fetched, fetch_release, output, "",
    ))
    try:
        importer.start()
        assert entered.wait(10)
        with app.app_context():
            db.session.execute(text("SET LOCAL lock_timeout = '1500ms'"))
            db.session.execute(update(FlowBoard).where(FlowBoard.id == BOARD_ID).values(chart_revision=1))
            db.session.commit()
        collector.start()
        deadline = time.monotonic() + 10
        blocked = False
        while time.monotonic() < deadline:
            with engine.connect() as connection:
                blocked = connection.scalar(text(
                    "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                    "WHERE application_name = :name AND wait_event_type = 'Lock')"
                ), {"name": f"{schema}_waiting"})
            if blocked:
                break
            time.sleep(0.02)
        assert blocked and not fetched.is_set()
        release.set()
        assert dict(output.get(timeout=15) for _ in range(2)) == {
            "generated-held-import": "generated_import_failure" if fail else 1,
            f"{schema}_waiting": 1,
        }
        for process in (importer, collector):
            process.join(10)
            assert process.exitcode == 0
        with app.app_context():
            assert len(db.session.scalars(select(FlowEvidence)).all()) == (1 if fail else 2)
            assert db.session.get(FlowBoard, BOARD_ID).chart_revision == 1
    finally:
        release.set()
        for process in (importer, collector):
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(10)
        output.close()


def test_delivery_workers_skip_locked_and_publish_each_delivery_once(isolated_postgres):
    uri, schema, _engine, app = isolated_postgres
    with app.app_context():
        db.session.add(FlowDataset(id=BOARD_ID, provenance="real", content_sha256="", payload={}))
        db.session.commit()
        db.session.add_all([
            FlowDelivery(
                id=f"generated-delivery-{index}", event="projects_v2_item",
                action="edited", body_sha256=f"{index:064x}", body=b"{}",
                received_at=datetime(2026, 10, 16, tzinfo=UTC),
                status="pending", attempts=0,
            )
            for index in range(2)
        ])
        db.session.commit()
    context = multiprocessing.get_context("spawn")
    entered, release = context.Event(), context.Event()
    output = context.Queue()
    first = context.Process(target=delivery_worker, args=(uri, schema, "generated-worker-a", entered, release, output))
    second = context.Process(target=delivery_worker, args=(uri, schema, "generated-worker-b", None, None, output))
    try:
        first.start()
        assert entered.wait(10)
        second.start()
        assert output.get(timeout=15) == ("generated-worker-b", {"processed": 1, "failed": 0})
        release.set()
        assert output.get(timeout=15) == ("generated-worker-a", {"processed": 1, "failed": 0})
        for process in (first, second):
            process.join(10)
            assert process.exitcode == 0
        with app.app_context():
            assert len(db.session.scalars(select(FlowEvent)).all()) == 2
            assert all(delivery.attempts == 1 and delivery.status == "processed"
                       for delivery in db.session.scalars(select(FlowDelivery)))
    finally:
        release.set()
        for process in (first, second):
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(10)
        output.close()
