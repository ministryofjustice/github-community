import copy
import hashlib
import json
import time
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Flask
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.projects.flow_metrics.archive import export_snapshot
from app.projects.flow_metrics.archive_import import (
    ArchiveImportError,
    import_archives,
)
from app.projects.flow_metrics.collector import (
    BOARD_ID,
    ESTIMATION_FIELD_ID,
    FIELD_QUERY,
    ITEM_PAGE_SIZE,
    ITEM_QUERY,
    MAX_ITEMS,
    CollectionError,
    collect,
    collect_payload,
    pages,
)
from app.projects.flow_metrics.datasets import (
    SAMPLE_ID,
    initialise_sample,
    retain_evidence,
    sample_dataset,
)
from app.projects.flow_metrics.db_models import (
    FlowBoard,
    FlowCollectionRun,
    FlowDataset,
    FlowEvidence,
    FlowSnapshot,
)
from app.projects.flow_metrics.reconciliation import reconcile
from app.projects.flow_metrics.routes.main import flow_metrics_main
from app.projects.flow_metrics.service import (
    metadata,
    normalise,
    result,
    seeds,
    validate_chart,
)
from app.shared.config.jinja_config import configure_jinja
from app.shared.database import db


def field(key, name):
    return {"id": key, "name": name}


def item(key, status="TODO", points=3, archived=False):
    return {
        "id": key,
        "archived": archived,
        "content": {
            "__typename": "Issue",
            "id": f"issue-{key}",
            "number": int(key[-1]),
            "title": f"Synthetic test item {key}",
            "createdAt": "2026-10-14T10:00:00Z",
            "state": "OPEN",
            "repository": {"nameWithOwner": "synthetic/repository"},
        },
        "fields": [
            {
                "field": field("status-id", "Renamed status"),
                "name": status,
                "optionId": status,
            },
            {
                "field": field("team-id", "Team"),
                "name": "Blueprint",
                "optionId": "team-option",
            },
            {
                "field": field("sprint-id", "Sprint"),
                "title": "Test sprint",
                "iterationId": "iteration-id",
            },
            {"field": field("points-id", "Points"), "number": points},
        ],
    }


def payload(items=None):
    return {
        "project_id": "test-project",
        "fields": [
            field("status-id", "Status"),
            field("team-id", "Team"),
            field("sprint-id", "Sprint"),
            field("points-id", "Points"),
        ],
        "mapping": {
            "status": "status-id",
            "team": "team-id",
            "sprint": "sprint-id",
            "points": "points-id",
        },
        "items": items
        if items is not None
        else [
            item("item-1"),
            item("item-2", "In Progress"),
            item("item-3", archived=True),
        ],
    }


def sample_seed():
    return json.loads(Path("app/projects/flow_metrics/sample-seed.json").read_text())


def write_import_archive(directory, document):
    encoded = (json.dumps(document, sort_keys=True) + "\n").encode()
    path = directory / f"project-152-{document['captured_date']}-{hashlib.sha256(encoded).hexdigest()}.json"
    path.write_bytes(encoded)
    return path


def import_document(day=18, hour=12):
    return {
        "schema_version": 1, "kind": "published_board_observation",
        "board_id": BOARD_ID, "provenance": "real",
        "snapshot_id": f"generated-{day}-{hour}",
        "captured_date": f"2026-10-{day}", "captured_at": f"2026-10-{day}T{hour:02}:00:00+00:00",
        "item_count": 3, "payload": payload(),
    }


def external_import_document():
    document = import_document()
    return {
        "schema_version": 1, "source": "GitHub GraphQL API via local gh sign-in",
        "project": {"url": "https://github.com/orgs/ministryofjustice/projects/152",
                    "fields": {"nodes": document["payload"]["fields"],
                               "pageInfo": {"hasNextPage": False}}},
        "collection_started_at": "2026-10-18T10:00:00+00:00",
        "collection_finished_at": "2026-10-18T10:02:00+00:00",
        "snapshot_date": "2026-10-18", "snapshot_timezone": "Europe/London",
        "item_count": 3,
        "items": [
            {"id": item["id"], "isArchived": item["archived"], "content": item["content"],
             "fieldValues": {"nodes": item["fields"], "pageInfo": {"hasNextPage": False}}}
            for item in document["payload"]["items"]
        ],
    }


def test_archive_bundle_dry_run_and_atomic_rerun_preserve_mixed_workspace(app, tmp_path, monkeypatch):
    from app.projects.flow_metrics.workspace import exploratory_dataset

    write_import_archive(tmp_path, import_document(20))
    write_import_archive(tmp_path, import_document(17))
    external = external_import_document()
    (tmp_path / "earlier-external.json").write_text(json.dumps(external))
    (tmp_path / "metadata.json").write_text('{"description":"Generated manifest metadata"}')
    with app.app_context():
        initialise_sample(sample_seed())
        board = db.session.get(FlowBoard, SAMPLE_ID)
        board.charts = []
        board.chart_revision = 6
        real = db.session.get(FlowBoard, BOARD_ID)
        real.field_mapping = {}
        db.session.commit()
        before = copy.deepcopy(exploratory_dataset())
        with patch("app.projects.flow_metrics.archive_import.retain_evidence") as writer:
            dry = import_archives(tmp_path, date(2026, 10, 16), dry_run=True)
            writer.assert_not_called()
        assert dry == {"captures": 3, "items": 9, "new": 3, "existing": 0, "ignored": 1, "dry_run": True}
        assert db.session.scalar(select(func.count()).select_from(FlowEvidence)) == 0
        assert db.session.get(FlowDataset, BOARD_ID) is None
        assert exploratory_dataset() == before
        result = import_archives(tmp_path, date(2026, 10, 16))
        assert result["new"] == 3
        monkeypatch.setenv("FLOW_METRICS_DATA_MODE", "sample")
        combined = exploratory_dataset()
        with patch("app.shared.middleware.auth.app_config.auth_enabled", False):
            response = app.test_client().get("/flow-metrics/api/workspace")
        assert response.status_code == 200
        assert response.json["provenance"] == "mixed"
        assert response.json["dataset"]["realObservations"] == combined["realObservations"]
        assert combined["tickets"] == before["tickets"]
        assert combined["realEventCoverage"]["complete"] is False
        assert combined["realObservations"][-1]["capturedAt"].startswith("2026-10-20")
        adapted = next(entry for entry in combined["realObservations"] if entry["source"] == "external-gh-capture")
        assert adapted["items"][0]["team"] == "Blueprint"
        assert db.session.get(FlowBoard, SAMPLE_ID).charts == []
        assert db.session.get(FlowBoard, SAMPLE_ID).chart_revision == 6
        assert db.session.get(FlowBoard, BOARD_ID).charts == seeds()
        assert db.session.get(FlowSnapshot, "snapshot-test").payload == payload()
        assert db.session.scalar(select(func.count()).select_from(FlowCollectionRun)) == 0
        rerun = import_archives(tmp_path, date(2026, 10, 16))
        assert rerun["new"] == 0 and rerun["existing"] == 3
        assert exploratory_dataset() == combined
        assert db.session.get(FlowDataset, BOARD_ID).provenance == "real"
        assert sample_dataset().provenance == "synthetic"
        assert db.session.scalar(select(func.count()).select_from(FlowEvidence)) == 3
        stale = tmp_path / "stale"
        stale.mkdir()
        write_import_archive(stale, import_document(16))
        import_archives(stale, date(2026, 10, 16))
        assert exploratory_dataset()["realObservations"][-1] == combined["realObservations"][-1]


@pytest.mark.parametrize("failure", [
    "count", "duplicate_items", "wrong_board", "partial", "total", "schema",
    "unrecognised", "old", "checksum", "duplicate_file", "conflict", "unusable",
])
@pytest.mark.parametrize("dry_run", [False, True])
def test_invalid_later_archive_never_publishes_bundle(app, tmp_path, failure, dry_run):
    write_import_archive(tmp_path, import_document(17))
    document = import_document(20)
    if failure == "count":
        document["item_count"] += 1
    elif failure == "duplicate_items":
        document["payload"]["items"][1] = document["payload"]["items"][0]
    elif failure == "wrong_board":
        document["board_id"] = "wrong-board"
    elif failure == "partial":
        document["payload"]["pageInfo"] = {"hasNextPage": True}
    elif failure == "total":
        document["payload"]["connection"] = {"nodes": [], "totalCount": 1}
    elif failure == "schema":
        document["schema_version"] = True
    elif failure == "unrecognised":
        document["kind"] = "not-a-capture"
    elif failure == "old":
        document["captured_date"] = "2026-10-15"
        document["captured_at"] = "2026-10-15T12:00:00+00:00"
    elif failure == "unusable":
        del document["payload"]["items"][0]["content"]["createdAt"]
    target = write_import_archive(tmp_path, document)
    if failure == "checksum":
        target.write_text(target.read_text() + " ")
    if failure == "duplicate_file":
        external = external_import_document()
        for name in ("external-a.json", "external-b.json"):
            (tmp_path / name).write_text(json.dumps(external))
    if failure == "conflict":
        other = copy.deepcopy(document)
        other["payload"]["items"][0]["content"]["title"] = "Generated conflicting observation"
        write_import_archive(tmp_path, other)
    with app.app_context():
        with pytest.raises(ArchiveImportError):
            import_archives(tmp_path, date(2026, 10, 16), dry_run=dry_run)
        assert db.session.scalar(select(func.count()).select_from(FlowEvidence)) == 0
        assert db.session.get(FlowDataset, BOARD_ID) is None
        assert db.session.get(FlowSnapshot, "snapshot-test").payload == payload()


def test_archive_bundle_database_failure_rolls_back_prior_insert(app, tmp_path):
    write_import_archive(tmp_path, import_document(17))
    write_import_archive(tmp_path, import_document(20))
    calls = 0

    def fail_second(document):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise SQLAlchemyError("generated failure; not an operator log message")
        return retain_evidence(document)

    with app.app_context(), patch(
        "app.projects.flow_metrics.archive_import.retain_evidence", side_effect=fail_second,
    ):
        with pytest.raises(ArchiveImportError, match="whole bundle"):
            import_archives(tmp_path, date(2026, 10, 16))
        assert calls == 2
        assert db.session.scalar(select(func.count()).select_from(FlowEvidence)) == 0
        assert db.session.get(FlowDataset, BOARD_ID) is None
    with app.app_context():
        assert import_archives(tmp_path, date(2026, 10, 16))["new"] == 2


def test_archive_bundle_cli_dry_run_missing_board_and_safe_errors(app, tmp_path):
    write_import_archive(tmp_path, import_document(20))
    runner = app.test_cli_runner()
    with app.app_context():
        db.session.delete(db.session.get(FlowSnapshot, "snapshot-test"))
        db.session.delete(db.session.get(FlowBoard, BOARD_ID))
        db.session.commit()
    dry = runner.invoke(args=["flow-metrics", "import-archives", str(tmp_path), "--since", "2026-10-16", "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert "nothing written" in dry.output and "legacy" in dry.output
    with app.app_context():
        assert db.session.get(FlowBoard, BOARD_ID) is None
        assert db.session.get(FlowDataset, BOARD_ID) is None
    failed = runner.invoke(args=["flow-metrics", "import-archives", str(tmp_path), "--since", "2026-10-16"])
    assert failed.exit_code != 0 and "flow-metrics init" in failed.output
    assert "Synthetic test item" not in failed.output
    assert runner.invoke(args=["flow-metrics", "init"]).exit_code == 0
    imported = runner.invoke(args=["flow-metrics", "import-archives", str(tmp_path), "--since", "2026-10-16"])
    assert imported.exit_code == 0 and "Imported atomically" in imported.output


def test_archive_bundle_rejects_conflict_with_stored_evidence(app, tmp_path):
    document = import_document(20)
    with app.app_context():
        retain_evidence(document)
        db.session.commit()
        document["payload"]["items"][0]["content"]["title"] = "Generated conflicting record"
        write_import_archive(tmp_path, document)
        with pytest.raises(ArchiveImportError):
            import_archives(tmp_path, date(2026, 10, 16), dry_run=True)
        assert db.session.scalar(select(func.count()).select_from(FlowEvidence)) == 1


@pytest.mark.parametrize("failure", ["empty", "malformed", "symlink", "nested", "inside_repository"])
def test_archive_bundle_input_boundary_is_explicit(app, tmp_path, failure):
    directory = tmp_path
    if failure == "malformed":
        (tmp_path / "generated.json").write_text('{"not valid')
    elif failure == "symlink":
        target = write_import_archive(tmp_path, import_document())
        (tmp_path / "linked.json").symlink_to(target)
    elif failure == "nested":
        (tmp_path / "nested").mkdir()
    elif failure == "inside_repository":
        directory = Path.cwd()
    with app.app_context():
        with pytest.raises(ArchiveImportError):
            import_archives(directory, date(2026, 10, 16), dry_run=True)
        assert db.session.scalar(select(func.count()).select_from(FlowEvidence)) == 0


def test_archive_bundle_success_and_failure_output_never_include_records(app, tmp_path, caplog):
    document = import_document()
    write_import_archive(tmp_path, document)
    runner = app.test_cli_runner()
    with caplog.at_level("INFO"):
        result = runner.invoke(args=["flow-metrics", "import-archives", str(tmp_path), "--since", "2026-10-16"])
    assert result.exit_code == 0
    assert "item observations" in result.output
    assert "Synthetic test item" not in result.output + caplog.text
    with patch("app.projects.flow_metrics.archive_import.retain_evidence",
               side_effect=SQLAlchemyError("generated secret-like payload must not be printed")):
        failed = runner.invoke(args=["flow-metrics", "import-archives", str(tmp_path), "--since", "2026-10-16"])
    assert failed.exit_code != 0 and "rolled back" in failed.output
    assert "secret-like" not in failed.output + caplog.text


@pytest.mark.parametrize("failure", ["project", "partial", "count", "pagination_state"])
def test_archive_bundle_external_completeness_checks(app, tmp_path, failure):
    document = external_import_document()
    if failure == "project":
        document["project"]["url"] = "https://github.com/orgs/example/projects/42"
    elif failure == "partial":
        document["items"][1]["fieldValues"]["pageInfo"]["hasNextPage"] = True
    elif failure == "count":
        document["project"]["fields"]["totalCount"] = 123
    elif failure == "pagination_state":
        document["items"][1]["fieldValues"]["pageInfo"]["hasNextPage"] = "false"
    (tmp_path / "external.json").write_text(json.dumps(document))
    with app.app_context():
        with pytest.raises(ArchiveImportError):
            import_archives(tmp_path, date(2026, 10, 16))
        assert db.session.scalar(select(func.count()).select_from(FlowEvidence)) == 0


@pytest.mark.parametrize("failure", ["empty_content", "missing_creation", "external_archived", "database"])
def test_single_capture_import_validates_readmodel_and_rolls_back(app, tmp_path, failure, monkeypatch):
    document = import_document(20)
    if failure == "empty_content":
        document["payload"]["items"][0]["content"] = {}
    elif failure == "missing_creation":
        del document["payload"]["items"][0]["content"]["createdAt"]
    elif failure == "external_archived":
        document = external_import_document()
        del document["items"][0]["isArchived"]
    path = tmp_path / "generated-external.json" if failure == "external_archived" else write_import_archive(tmp_path, document)
    if failure == "external_archived":
        path.write_text(json.dumps(document))
    with app.app_context():
        initialise_sample(sample_seed())
        from app.projects.flow_metrics.workspace import exploratory_dataset
        before = exploratory_dataset()
    if failure == "database":
        def fail_after_flush(document):
            retain_evidence(document)
            db.session.flush()
            raise SQLAlchemyError("private generated diagnostic")

        monkeypatch.setattr("app.projects.flow_metrics.datasets.retain_evidence", fail_after_flush)
    result = app.test_cli_runner().invoke(args=["flow-metrics", "import-capture", "--file", str(path)])
    assert result.exit_code != 0 and "nothing imported" in result.output
    assert "private generated diagnostic" not in result.output
    with app.app_context():
        assert db.session.get(FlowDataset, BOARD_ID) is None
        assert db.session.scalar(select(func.count()).select_from(FlowEvidence)) == 0
        assert exploratory_dataset() == before
        assert db.session.get(FlowBoard, BOARD_ID).charts == seeds()


def test_single_capture_valid_import_and_rerun_preserve_sources(app, tmp_path):
    path = write_import_archive(tmp_path, import_document(20))
    runner = app.test_cli_runner()
    for _ in range(2):
        result = runner.invoke(args=["flow-metrics", "import-capture", "--file", str(path)])
        assert result.exit_code == 0, result.output
    with app.app_context():
        assert db.session.scalar(select(func.count()).select_from(FlowEvidence)) == 1
        assert db.session.get(FlowSnapshot, "snapshot-test").payload == payload()


@pytest.mark.parametrize("offset", [False, True])
def test_single_capture_conflict_rejection_preserves_entire_workspace(app, tmp_path, offset):
    from app.projects.flow_metrics.workspace import exploratory_dataset

    original = import_document(20)
    runner = app.test_cli_runner()
    with app.app_context():
        initialise_sample(sample_seed())
    first_path = write_import_archive(tmp_path, original)
    assert runner.invoke(args=["flow-metrics", "import-capture", "--file", str(first_path)]).exit_code == 0
    with app.app_context():
        before = exploratory_dataset()
        before_metadata = metadata()
        before_charts = [(b.id, copy.deepcopy(b.charts), b.chart_revision, copy.deepcopy(b.field_mapping))
                         for b in db.session.scalars(select(FlowBoard))]
        before_evidence = [(e.id, copy.deepcopy(e.document)) for e in db.session.scalars(select(FlowEvidence))]
    changed = copy.deepcopy(original)
    changed["payload"]["items"][0]["content"]["title"] = "Generated contradictory observation"
    if offset:
        changed["captured_at"] = "2026-10-20T13:00:00+01:00"
    conflicting = write_import_archive(tmp_path, changed)
    rejected = runner.invoke(args=["flow-metrics", "import-capture", "--file", str(conflicting)])
    assert rejected.exit_code == 1
    assert "conflicts with stored observation; nothing imported" in rejected.output
    # Key order and whitespace do not change the canonical evidence checksum.
    reordered = tmp_path / "generated-reordered.json"
    reordered.write_text(json.dumps(dict(reversed(list(original.items()))), indent=3))
    assert runner.invoke(args=["flow-metrics", "import-capture", "--file", str(reordered)]).exit_code == 0
    with app.app_context():
        assert exploratory_dataset() == before
        assert metadata() == before_metadata
        assert [(b.id, b.charts, b.chart_revision, b.field_mapping)
                for b in db.session.scalars(select(FlowBoard))] == before_charts
        assert [(e.id, e.document) for e in db.session.scalars(select(FlowEvidence))] == before_evidence


def test_single_capture_distinct_source_or_time_remains_valid(app, tmp_path):
    runner = app.test_cli_runner()
    published = import_document(18)
    external = external_import_document()
    external["collection_finished_at"] = published["captured_at"]
    documents = [published, external, import_document(18, 13)]
    for index, document in enumerate(documents):
        path = tmp_path / f"generated-{index}.json"
        path.write_text(json.dumps(document))
        imported = runner.invoke(args=["flow-metrics", "import-capture", "--file", str(path)])
        assert imported.exit_code == 0, imported.output
    with app.app_context():
        assert db.session.scalar(select(func.count()).select_from(FlowEvidence)) == 3


def test_invalid_single_capture_preserves_preexisting_combined_workspace(app, tmp_path):
    from app.projects.flow_metrics.workspace import exploratory_dataset

    with app.app_context():
        initialise_sample(sample_seed())
        retain_evidence(import_document(18))
        db.session.commit()
        before = exploratory_dataset()
        charts = copy.deepcopy(db.session.get(FlowBoard, BOARD_ID).charts)
    broken = import_document(20)
    broken["payload"]["items"][-1]["content"] = {}
    path = write_import_archive(tmp_path, broken)
    imported = app.test_cli_runner().invoke(args=["flow-metrics", "import-capture", "--file", str(path)])
    assert imported.exit_code == 1
    with app.app_context():
        assert exploratory_dataset() == before
        assert db.session.get(FlowBoard, BOARD_ID).charts == charts
        assert db.session.scalar(select(func.count()).select_from(FlowEvidence)) == 1


@pytest.mark.parametrize("layout", ["bar", "column", "line", "stacked-bar", "stacked-column", "area"])
def test_real_editable_age_recipe_matches_builtin(app, layout):
    with app.app_context():
        snapshot = db.session.get(FlowSnapshot, "snapshot-test")
        data = payload()
        data["items"][0]["content"]["createdAt"] = "2026-10-16T00:00:00Z"
        snapshot.payload = data
        db.session.add(FlowSnapshot(
            id="generated-earlier-age", board_id=BOARD_ID,
            captured_date=date(2026, 10, 14), captured_at=datetime(2026, 10, 14, tzinfo=UTC),
            payload=payload(),
        ))
        db.session.commit()
        builtin = copy.deepcopy(next(chart for chart in seeds() if chart["metric"] == "age"))
        builtin["layout"] = layout
        custom = {**builtin, "metric": "custom", "x": "ticket", "y": "itemAge", "group": "",
                  "calculation": {"version": 1, "aggregation": "individual"}}
        expected = result(builtin)
        actual = result(custom)
        assert not actual["unavailable"]
        assert actual == expected
        assert actual["rows"][0]["value"] == 0
        custom["filters"]["query"] = 'title:"synthetic test item item-2"'
        assert result(custom)["sampleSize"] == 1
        custom["filters"]["query"] = 'title:"does not exist"'
        assert result(custom)["sampleSize"] == 0
        custom["filters"]["query"] = "to:2026-10-14"
        assert result(custom) == result({**builtin, "filters": custom["filters"]})
        assert [row["value"] for row in result(custom)["rows"]] == [0, 0]
        custom["filters"]["query"] = "to:2026-10-13"
        for definition in (custom, {**builtin, "filters": custom["filters"]}):
            with pytest.raises(ValueError, match="within the captured observation history"):
                result(definition)
        custom["y"] = "statusDays"
        custom["filters"]["query"] = ""
        assert result(custom)["unavailable"]


@pytest.mark.parametrize("custom_type", ["Task", "Issue", "Draft", "DraftIssue", None])
@pytest.mark.parametrize("kind", ["DraftIssue", "Issue"])
def test_age_draft_identity_not_project_type(app, custom_type, kind):
    with app.app_context():
        snapshot = db.session.get(FlowSnapshot, "snapshot-test")
        data = payload(items=[item("item-1")])
        data["mapping"]["type"] = "type-id"
        data["items"][0]["content"]["__typename"] = kind
        if kind == "DraftIssue":
            del data["items"][0]["content"]["state"]
        if custom_type is not None:
            data["items"][0]["fields"].append({"field": field("type-id", "Type"), "name": custom_type})
        snapshot.payload = data
        db.session.commit()
        age = copy.deepcopy(next(c for c in seeds() if c["metric"] == "age"))
        average = {**age, "metric": "custom", "x": "status", "y": "averageAge"}
        custom = {**age, "metric": "custom", "x": "ticket", "y": "itemAge", "group": ""}
        for chart in (age, average, custom):
            assert bool(result(chart)["unavailable"]) is (kind == "DraftIssue")


@pytest.mark.parametrize("query,expected", [
    ('title:"synthetic/repository#2"', 0), ('"SYNTHETIC/repository#2"', 1),
    ('#2', 1), ('title:"ITEM-2"', 1), ('title:"item-3"', 0),
    ('title:"item-1" #2', 0), ('title:"does not exist"', 0),
])
def test_real_title_only_and_keyword_reference_search(app, query, expected):
    with app.app_context():
        chart = copy.deepcopy(next(c for c in seeds() if c["metric"] == "status"))
        chart["filters"]["query"] = query
        data = result(chart)
        assert data["sampleSize"] == expected
        assert len(data["tickets"]) == expected


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("FLOW_METRICS_ENABLED", "true")
    monkeypatch.setenv("FLOW_METRICS_DATA_MODE", "real")
    application = Flask("app")
    application.config.update(
        TESTING=True,
        SECRET_KEY="synthetic-test-only",
        SQLALCHEMY_DATABASE_URI="sqlite://",
    )
    db.init_app(application)
    application.register_blueprint(flow_metrics_main, url_prefix="/flow-metrics/")
    configure_jinja(application)
    with application.app_context():
        db.create_all()
        db.session.add(
            FlowBoard(
                id=BOARD_ID,
                charts=seeds(),
                field_mapping=payload()["mapping"],
                chart_revision=0,
            )
        )
        db.session.add(
            FlowSnapshot(
                id="snapshot-test",
                board_id=BOARD_ID,
                captured_date=date(2026, 10, 16),
                captured_at=datetime(2026, 10, 16, 12, tzinfo=UTC),
                payload=payload(),
            )
        )
        db.session.commit()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user"] = {"expires_at": time.time() + 3600}
    return client


def csrf(client):
    response = client.get("/flow-metrics/api/workspace")
    assert response.status_code == 200
    return {"X-Flow-CSRF": response.json["csrf"]}


def test_sample_database_contract_shared_saving_and_real_isolation(app, client, monkeypatch):
    monkeypatch.setenv("FLOW_METRICS_DATA_MODE", "sample")
    seed = sample_seed()
    with app.app_context():
        initialise_sample(seed)
        initialise_sample(seed)
        data = sample_dataset()
        assert data.payload == seed["dataset"]
        assert len(data.payload["tickets"]) == 36
        assert all(ticket["events"] and ticket["label"] and ticket["reviewers"]
                   for ticket in data.payload["tickets"])
    headers = csrf(client)
    workspace = client.get("/flow-metrics/api/workspace").json
    assert workspace["provenance"] == "mixed"
    assert workspace["datasetId"] == SAMPLE_ID
    assert workspace["dataset"]["tickets"] == seed["dataset"]["tickets"]
    assert len(workspace["dataset"]["realObservations"]) == 1
    charts = copy.deepcopy(workspace["charts"])
    charts[0]["name"] = "Shared fictional cycle chart"
    assert client.post("/flow-metrics/api/charts", json={"charts": charts, "revision": 0}).status_code == 403
    assert client.post("/flow-metrics/api/charts", headers=headers,
                       json={"charts": charts, "revision": 0}).status_code == 200
    assert client.post("/flow-metrics/api/charts", headers=headers,
                       json={"charts": charts, "revision": 0}).status_code == 409
    other = app.test_client()
    with other.session_transaction() as session:
        session["user"] = {"expires_at": time.time() + 3600}
    assert other.get("/flow-metrics/api/workspace").json["charts"] == charts
    with monkeypatch.context() as changed_config:
        changed_config.setenv("FLOW_METRICS_SOURCE_URL", "https://github.com/orgs/synthetic/projects/999")
        refused = client.get("/flow-metrics/api/workspace")
        assert refused.status_code == 400
        assert "only project 152" in refused.json["error"]
    with app.app_context():
        initialise_sample(seed)
        assert db.session.get(FlowBoard, SAMPLE_ID).charts == charts
        assert db.session.get(FlowBoard, BOARD_ID).charts == seeds()
        assert db.session.get(FlowSnapshot, "snapshot-test").payload == payload()
        changed = copy.deepcopy(seed)
        changed["dataset"]["tickets"][0]["title"] = "Different fictional version"
        with pytest.raises(ValueError, match="immutable"):
            initialise_sample(changed)
    with patch("app.shared.middleware.auth.app_config.auth_enabled", True):
        assert app.test_client().get("/flow-metrics/api/workspace").status_code == 302


def test_sample_init_cli_preserves_existing_empty_workspace_and_real_data(app):
    runner = app.test_cli_runner()
    with app.app_context():
        prior = copy.deepcopy(db.session.get(FlowSnapshot, "snapshot-test").payload)
        real_charts = copy.deepcopy(db.session.get(FlowBoard, BOARD_ID).charts)
    first = runner.invoke(args=["flow-metrics", "init-sample"])
    assert first.exit_code == 0, first.output
    with app.app_context():
        board = db.session.get(FlowBoard, SAMPLE_ID)
        board.charts = []
        board.chart_revision = 7
        checksum = db.session.get(FlowDataset, SAMPLE_ID).content_sha256
        db.session.commit()
    with patch("app.projects.flow_metrics.collector.ProjectClient") as github:
        second = runner.invoke(args=["flow-metrics", "init-sample"])
        assert second.exit_code == 0, second.output
        github.assert_not_called()
    with app.app_context():
        board = db.session.get(FlowBoard, SAMPLE_ID)
        assert board.charts == []
        assert board.chart_revision == 7
        assert db.session.get(FlowDataset, SAMPLE_ID).content_sha256 == checksum
        assert db.session.get(FlowBoard, BOARD_ID).charts == real_charts
        assert db.session.get(FlowSnapshot, "snapshot-test").payload == prior
        assert db.session.scalar(select(func.count()).select_from(FlowEvidence)) == 0
        assert db.session.scalar(select(func.count()).select_from(FlowCollectionRun)) == 0


def test_versioned_builder_settings_shared_persistence_validation_and_conflicts(app, client, monkeypatch):
    monkeypatch.setenv("FLOW_METRICS_DATA_MODE", "sample")
    with app.app_context():
        initialise_sample(sample_seed())
    headers = csrf(client)
    workspace = client.get("/flow-metrics/api/workspace").json
    chart = {**copy.deepcopy(workspace["charts"][0]), "id": "custom-scope", "name": "Synthetic builder",
        "metric": "custom", "x": "reporting", "y": "sprintScope", "group": "", "layout": "burnup",
        "calculation": {"version": 1, "interval": "daily", "bandWidth": 3, "counting": "events",
            "value": "count", "aggregation": "individual", "minDays": 0, "additional": "completedScope"}}
    charts = workspace["charts"] + [chart]
    response = client.post("/flow-metrics/api/charts", headers=headers, json={"charts": charts, "revision": workspace["revision"]})
    assert response.status_code == 200
    assert client.get("/flow-metrics/api/workspace").json["charts"] == charts
    assert client.post("/flow-metrics/api/charts", headers=headers, json={"charts": charts, "revision": workspace["revision"]}).status_code == 409
    other = app.test_client()
    with other.session_transaction() as session:
        session["user"] = {"expires_at": time.time() + 3600}
    assert other.get("/flow-metrics/api/workspace").json["charts"] == charts
    for key, value in [("version", True), ("version", 2), ("bandWidth", 0), ("bandWidth", 366),
                       ("minDays", -1), ("counting", "records"), ("additional", ["completedScope"]),
                       ("value", "estimation"), ("interval", "hourly"), ("expression", "raw")]:
        invalid = copy.deepcopy(chart)
        invalid["calculation"][key] = value
        with pytest.raises(ValueError):
            validate_chart(invalid)
    for y, x in [("cycleTime", "team"), ("committedScope", "reporting"), ("completions", "sprint")]:
        invalid = {**chart, "y": y, "x": x}
        with pytest.raises(ValueError):
            validate_chart(invalid)
    with app.app_context():
        assert db.session.get(FlowBoard, BOARD_ID).charts == seeds()
        assert db.session.get(FlowSnapshot, "snapshot-test").payload == payload()


def test_source_import_is_lossless_idempotent_separate_and_strict(app):
    from app.projects.flow_metrics.archive import snapshot_document

    with app.app_context():
        document = snapshot_document(db.session.get(FlowSnapshot, "snapshot-test"))
        key = retain_evidence(document)
        db.session.commit()
        assert retain_evidence(document) == key
        db.session.commit()
        assert db.session.execute(select(func.count()).select_from(FlowEvidence)).scalar_one() == 1
        assert db.session.get(FlowEvidence, key).document == document
        newer = copy.deepcopy(document)
        newer["captured_at"] = "2026-10-16T13:00:00+00:00"
        key2 = retain_evidence(newer)
        db.session.commit()
        assert key != key2
        external = {
            "schema_version": 1, "source": "GitHub GraphQL API via local gh sign-in",
            "project": {"url": "https://github.com/orgs/ministryofjustice/projects/152",
                        "fields": {"nodes": [], "pageInfo": {"hasNextPage": False}}},
            "collection_started_at": "2026-10-18T10:00:00+00:00",
            "collection_finished_at": "2026-10-18T10:02:00+00:00",
            "snapshot_date": "2026-10-18", "snapshot_timezone": "Europe/London",
            "item_count": 1, "items": [{"id": "synthetic-test", "fieldValues": {"nodes": [], "pageInfo": {"hasNextPage": False}}}],
        }
        ext_key = retain_evidence(external)
        db.session.commit()
        evidence = db.session.get(FlowEvidence, ext_key)
        assert evidence.source == "external-gh-capture"
        assert evidence.document == external
        assert evidence.dataset_id == BOARD_ID
        assert db.session.get(FlowSnapshot, "snapshot-test").captured_date == date(2026, 10, 16)
        bad = copy.deepcopy(external)
        bad["item_count"] = 2
        with pytest.raises(ValueError, match="count"):
            retain_evidence(bad)
        bad = copy.deepcopy(document)
        bad["provenance"] = "synthetic"
        with pytest.raises(ValueError, match="provenance"):
            retain_evidence(bad)
        partial = copy.deepcopy(external)
        partial["project"]["fields"]["pageInfo"]["hasNextPage"] = True
        with pytest.raises(ValueError, match="Partial"):
            retain_evidence(partial)


@pytest.mark.parametrize("layout", ["scatter", "histogram"])
def test_real_specialised_layouts_never_fall_back_to_aggregate_points(app, layout):
    with app.app_context():
        cycle = {**seeds()[0], "layout": layout}
        assert "Reliable transition" in result(cycle)["unavailable"]
        incompatible = {**seeds()[3], "layout": layout}
        assert "require Cycle time" in result(incompatible)["unavailable"]


def test_scoped_cleanup_preserves_real_records_and_definitions(app):
    from app.projects.flow_metrics.archive import snapshot_document

    with app.app_context():
        initialise_sample(sample_seed())
        key = retain_evidence(snapshot_document(db.session.get(FlowSnapshot, "snapshot-test")))
        db.session.commit()
    runner = app.test_cli_runner()
    assert runner.invoke(args=["flow-metrics", "remove-sample", "--confirm-dataset", BOARD_ID]).exit_code != 0
    assert runner.invoke(args=["flow-metrics", "remove-sample", "--confirm-dataset", SAMPLE_ID]).exit_code == 0
    with app.app_context():
        assert db.session.get(FlowDataset, SAMPLE_ID) is None
        assert db.session.get(FlowBoard, SAMPLE_ID) is None
        assert db.session.get(FlowBoard, BOARD_ID).charts == seeds()
        assert db.session.get(FlowEvidence, key) is not None
        assert db.session.get(FlowSnapshot, "snapshot-test") is not None


def test_live_workspace_auth_and_no_cache(app, client):
    with patch("app.shared.middleware.auth.app_config.auth_enabled", True):
        assert app.test_client().get("/flow-metrics/api/workspace").status_code == 302
        response = client.get("/flow-metrics/api/workspace")
        assert response.json["itemCount"] == 3
        assert response.headers["Cache-Control"] == "no-store"
        assert response.json["options"]["status"] == ["In Progress", "TODO"]
        html = client.get("/flow-metrics/").get_data(as_text=True)
        assert ">Developer Experience board</a>" in html
        assert "About captured data" not in html
        assert "Charts are shared through this local database" not in html
        assert (
            "Every field, date, point estimate and ticket here is fictional" not in html
        )


def test_shared_crud_conflicts_and_csrf(client, app):
    headers = csrf(client)
    charts = seeds()
    assert (
        client.post(
            "/flow-metrics/api/charts", json={"charts": charts, "revision": 0}
        ).status_code
        == 403
    )
    charts[0]["name"] = "Shared synthetic chart"
    assert (
        client.post(
            "/flow-metrics/api/charts",
            headers=headers,
            json={"charts": charts, "revision": 0},
        ).json["revision"]
        == 1
    )
    assert (
        client.post(
            "/flow-metrics/api/charts",
            headers=headers,
            json={"charts": [], "revision": 0},
        ).status_code
        == 409
    )
    other = app.test_client()
    with other.session_transaction() as session:
        session["user"] = {"expires_at": time.time() + 3600}
    assert (
        other.get("/flow-metrics/api/workspace").json["charts"][0]["name"]
        == "Shared synthetic chart"
    )
    assert (
        client.post(
            "/flow-metrics/api/charts",
            headers=headers,
            json={"charts": [], "revision": 1},
        ).status_code
        == 200
    )
    assert client.get("/flow-metrics/api/workspace").json["charts"] == []


@pytest.mark.parametrize(
    "mutation",
    [
        lambda chart: chart.update(metric="raw-sql"),
        lambda chart: chart.update(threshold=True),
        lambda chart: chart.update(name=" "),
        lambda chart: chart.update(x="assignee"),
        lambda chart: chart["filters"].update(query="from:2026-02-30"),
        lambda chart: chart["filters"].update(query="unsupported:person"),
        lambda chart: chart["filters"].update(query='status:"'),
        lambda chart: chart.update(extra="not-allowed"),
    ],
)
def test_invalid_definitions_rejected(app, mutation):
    chart = seeds()[0]
    mutation(chart)
    with pytest.raises(ValueError):
        validate_chart(chart)


def test_real_result_is_exact_filtered_and_uses_field_ids(client):
    headers = csrf(client)
    chart = seeds()[3]
    response = client.post("/flow-metrics/api/result", headers=headers, json=chart)
    assert response.status_code == 200
    data = response.json
    assert sum(row["value"] for row in data["rows"]) == 2
    assert data["sampleSize"] == 2
    assert {key for row in data["rows"] for key in row["ids"]} == {"item-1", "item-2"}
    chart["filters"]["query"] = 'team:Blueprint status:"In Progress"'
    data = client.post("/flow-metrics/api/result", headers=headers, json=chart).json
    assert data["sampleSize"] == 1
    assert data["rows"][0]["ids"] == ["item-2"]


@pytest.mark.parametrize(
    ("kind", "repository", "number", "expected"),
    [
        (
            "Issue",
            "synthetic/repository",
            1,
            "https://github.com/synthetic/repository/issues/1",
        ),
        (
            "PullRequest",
            "synthetic/repository",
            2,
            "https://github.com/synthetic/repository/pull/2",
        ),
        ("DraftIssue", "", None, None),
        ("Issue", "unsafe/repository?query", 1, None),
        ("Issue", "synthetic/repository", -1, None),
    ],
)
def test_ticket_links_use_repository_and_content_kind(
    app, kind, repository, number, expected
):
    with app.app_context():
        snapshot = db.session.get(FlowSnapshot, "snapshot-test")
        observation = copy.deepcopy(snapshot.payload)
        content = observation["items"][0]["content"]
        content.update(__typename=kind, repository={"nameWithOwner": repository})
        content["number"] = number
        snapshot.payload = observation
        assert normalise(snapshot)[0]["url"] == expected


def test_unavailable_history_never_returns_fabricated_values(app):
    with app.app_context():
        for chart in seeds():
            if chart["metric"] in {"age", "status"}:
                continue
            data = result(chart)
            assert data["unavailable"]
            assert data["rows"] == []
            assert data["tickets"] == []
        chart = seeds()[3]
        chart["metric"] = "velocity"
        data = result(chart)
        assert data["unavailable"]
        assert data["rows"] == []


def test_devx_is_an_exact_team_not_an_all_team_alias(app):
    with app.app_context():
        snapshot = db.session.get(FlowSnapshot, "snapshot-test")
        observation = copy.deepcopy(snapshot.payload)
        observation["items"][0]["fields"][1]["name"] = "DevX"
        snapshot.payload = observation
        db.session.commit()
        chart = seeds()[3]
        chart["filters"]["query"] = "team:DevX"
        data = result(chart)
        assert data["sampleSize"] == 1
        assert {ticket["team"] for ticket in data["tickets"]} == {"DevX"}
        chart["filters"]["query"] = 'team:"Developer Experience"'
        assert result(chart)["sampleSize"] == 0


def test_private_snapshot_archive_is_lossless_immutable_and_verified(app, tmp_path):
    with app.app_context():
        snapshot = db.session.get(FlowSnapshot, "snapshot-test")
        path = export_snapshot(snapshot, tmp_path)
        saved = json.loads(path.read_text())
        assert saved["payload"] == snapshot.payload
        assert saved["provenance"] == "real"
        assert saved["schema_version"] == 1
        assert saved["item_count"] == len(snapshot.payload["items"])
        assert path.stat().st_mode & 0o777 == 0o600
        assert export_snapshot(snapshot, tmp_path) == path
        path.write_text("{}")
        with pytest.raises(ValueError, match="integrity"):
            export_snapshot(snapshot, tmp_path)
        with pytest.raises(ValueError, match="outside"):
            export_snapshot(snapshot, "app/projects/flow_metrics")


def test_reconciliation_archives_before_and_after_same_day_replacement(app, tmp_path):
    with app.app_context():
        snapshot = db.session.get(FlowSnapshot, "snapshot-test")
        before = copy.deepcopy(snapshot.payload)

        def replacement():
            snapshot.payload = payload([item("item-9", "Done")])
            snapshot.captured_at = datetime.now(UTC)
            db.session.commit()
            return 1

        with patch("app.projects.flow_metrics.reconciliation.collect", side_effect=replacement):
            count, paths = reconcile(tmp_path)
        assert count == 1
        assert len(paths) == 1
        archives = [json.loads(path.read_text()) for path in tmp_path.glob("*.json")]
        assert len(archives) == 2
        assert before in [archive["payload"] for archive in archives]
        assert snapshot.payload in [archive["payload"] for archive in archives]


def test_reconciliation_failure_preserves_existing_snapshot_and_archive(app, tmp_path):
    with app.app_context():
        snapshot = db.session.get(FlowSnapshot, "snapshot-test")
        before = copy.deepcopy(snapshot.payload)
        with (
            patch("app.projects.flow_metrics.reconciliation.collect", side_effect=CollectionError("test_failure")),
            pytest.raises(CollectionError, match="test_failure"),
        ):
            reconcile(tmp_path)
        assert db.session.get(FlowSnapshot, "snapshot-test").payload == before
        assert len(list(tmp_path.glob("*.json"))) == 1
        with (
            patch("app.projects.flow_metrics.reconciliation.export_snapshot", side_effect=OSError("archive unavailable")),
            patch("app.projects.flow_metrics.reconciliation.collect") as collector,
        ):
            with pytest.raises(OSError):
                reconcile(tmp_path)
            collector.assert_not_called()


def test_collection_health_in_sample_mode_is_real_capture_and_retains_failure(app, client, monkeypatch, tmp_path):
    monkeypatch.setenv("FLOW_METRICS_DATA_MODE", "sample")
    status_file = tmp_path / "health.json"
    status_file.write_text('{"status":"failed"}')
    monkeypatch.setenv("FLOW_METRICS_COLLECTION_HEALTH_FILE", str(status_file))
    response = client.get("/flow-metrics/api/collection-health")
    assert response.status_code == 200
    assert response.json["capturedAt"].startswith("2026-10-16T12:00:00")
    assert response.json["scheduledStatus"] == "failed"
    assert "no-store" in response.headers["Cache-Control"]
    assert "items" not in response.json
    with app.app_context():
        db.session.add(FlowCollectionRun(id="health-failed", board_id=BOARD_ID, started_at=datetime.now(UTC), status="failed"))
        db.session.commit()
    later = client.get("/flow-metrics/api/collection-health").json
    assert later["status"] == "failed"
    assert later["capturedAt"] == response.json["capturedAt"]


@pytest.mark.parametrize("enabled", ["true", "false"])
@pytest.mark.parametrize("mode", ["sample", "real"])
def test_health_latest_real_evidence_not_import_time_or_configuration(app, client, monkeypatch, enabled, mode):
    monkeypatch.setenv("FLOW_METRICS_ENABLED", enabled)
    monkeypatch.setenv("FLOW_METRICS_DATA_MODE", mode)
    with app.app_context():
        retain_evidence(import_document(20, 16))
        retain_evidence(import_document(17))
        db.session.commit()
    health = client.get("/flow-metrics/api/collection-health")
    assert health.status_code == 200
    assert health.json["capturedAt"].startswith("2026-10-20T16:00:00")
    assert health.json["configured"] is (enabled == "true")
    with app.app_context():
        snapshot = db.session.get(FlowSnapshot, "snapshot-test")
        snapshot.captured_at = datetime(2026, 10, 21, 12, tzinfo=UTC)
        snapshot.captured_date = date(2026, 10, 21)
        db.session.add(FlowCollectionRun(id="failed-latest", board_id=BOARD_ID, started_at=datetime.now(UTC), status="failed"))
        db.session.commit()
    later = client.get("/flow-metrics/api/collection-health").json
    assert later["capturedAt"].startswith("2026-10-21T12:00:00")
    assert later["status"] == "failed"


def test_health_imported_only_and_empty_never_use_fiction_timestamp(app, client, monkeypatch):
    monkeypatch.setenv("FLOW_METRICS_ENABLED", "false")
    with app.app_context():
        initialise_sample(sample_seed())
        db.session.delete(db.session.get(FlowSnapshot, "snapshot-test"))
        db.session.commit()
    empty = client.get("/flow-metrics/api/collection-health").json
    assert empty["capturedAt"] is None and empty["status"] == "not_configured" and empty["stale"]
    with app.app_context():
        retain_evidence(import_document(20))
        db.session.commit()
    imported = client.get("/flow-metrics/api/collection-health").json
    assert imported["capturedAt"].startswith("2026-10-20T12:00:00")
    assert imported["status"] == "not_configured"


@pytest.mark.parametrize("mode", ["sample", "real"])
def test_workspace_compact_only_exact_parsed_payload_and_csrf(app, client, monkeypatch, mode):
    from app.projects.flow_metrics.workspace import exploratory_dataset

    monkeypatch.setenv("FLOW_METRICS_DATA_MODE", mode)
    app.debug = True
    with app.app_context():
        initialise_sample(sample_seed())
        retain_evidence(import_document(20))
        db.session.commit()
        board = db.session.get(FlowBoard, SAMPLE_ID if mode == "sample" else BOARD_ID)
        expected = dict(charts=board.charts, revision=board.chart_revision,
                        **({"dataset": exploratory_dataset(), "datasetId": SAMPLE_ID, "provenance": "mixed"}
                           if mode == "sample" else {**metadata(), "datasetId": BOARD_ID, "provenance": "real"}))
    response = client.get("/flow-metrics/api/workspace")
    assert response.status_code == 200 and response.mimetype == "application/json"
    with client.session_transaction() as session:
        expected["csrf"] = session["flow_csrf"]
    assert response.json == expected
    assert response.data == (app.json.dumps(expected, separators=(",", ":")) + "\n").encode()
    assert len(response.data) < len(app.json.dumps(expected, indent=2).encode())
    assert app.debug is True and app.json.compact is None
    assert "no-store" in response.headers["Cache-Control"]
    assert client.post("/flow-metrics/api/charts", json={"charts": [], "revision": 0}).status_code == 403
    with patch("app.shared.middleware.auth.app_config.auth_enabled", True):
        assert app.test_client().get("/flow-metrics/api/workspace").status_code == 302


def test_known_answer_custom_points_and_calendar_age(app):
    with app.app_context():
        chart = seeds()[3]
        chart.update(metric="custom", y="points", x="team")
        data = result(chart)
        assert data["rows"][0]["value"] == 6
        chart.update(y="averageAge")
        assert result(chart)["rows"][0]["value"] == 2
        snapshot = db.session.get(FlowSnapshot, "snapshot-test")
        changed = copy.deepcopy(snapshot.payload)
        changed["items"][0]["fields"][-1]["number"] = None
        snapshot.payload = changed
        db.session.commit()
        chart["y"] = "points"
        assert "no numeric Points" in result(chart)["unavailable"]


def test_missing_observation_and_failed_run_are_honest(app):
    with app.app_context():
        snapshot = db.session.get(FlowSnapshot, "snapshot-test")
        db.session.delete(snapshot)
        db.session.commit()
        assert metadata()["capturedAt"] is None
        assert "No complete" in result(seeds()[3])["unavailable"]


def test_failed_collection_preserves_last_complete_snapshot(app):
    with (
        app.app_context(),
        patch(
            "app.projects.flow_metrics.collector.collect_payload",
            side_effect=CollectionError("github_query_incomplete"),
        ),
    ):
        before = db.session.get(FlowSnapshot, "snapshot-test").payload
        with pytest.raises(CollectionError):
            collect(object())
        assert db.session.get(FlowSnapshot, "snapshot-test").payload == before
        run = db.session.execute(select(FlowCollectionRun)).scalar_one()
        assert run.status == "failed"
        assert run.error_code == "github_query_incomplete"


def test_failed_publication_preserves_snapshot_and_records_failure(app):
    with (
        app.app_context(),
        patch(
            "app.projects.flow_metrics.collector.collect_payload",
            return_value=payload(),
        ),
        patch(
            "app.projects.flow_metrics.collector.publish", side_effect=SQLAlchemyError()
        ),
    ):
        before = db.session.get(FlowSnapshot, "snapshot-test").payload
        with pytest.raises(CollectionError, match="snapshot_publication_failed"):
            collect(object())
        assert db.session.get(FlowSnapshot, "snapshot-test").payload == before
        assert (
            db.session.execute(select(FlowCollectionRun)).scalar_one().status
            == "failed"
        )


def test_api_size_limits_and_cross_session_csrf(client, app):
    headers = csrf(client)
    other = app.test_client()
    with other.session_transaction() as session:
        session["user"] = {"expires_at": time.time() + 3600}
    assert (
        other.post(
            "/flow-metrics/api/charts",
            headers=headers,
            json={"charts": [], "revision": 0},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/flow-metrics/api/charts",
            headers=headers,
            data="x" * 150001,
            content_type="application/json",
        ).status_code
        == 413
    )


def test_idempotent_collection_retains_removed_item_history(app):
    with (
        app.app_context(),
        patch(
            "app.projects.flow_metrics.collector.collect_payload",
            return_value=payload([item("item-1")]),
        ),
    ):
        # Keep yesterday's full snapshot as evidence even when an item disappears.
        snapshot = db.session.get(FlowSnapshot, "snapshot-test")
        snapshot.captured_date = datetime.now(UTC).date().replace(day=1)
        db.session.commit()
        assert collect(object()) == 1
        assert collect(object()) == 1
        count = db.session.scalar(select(func.count()).select_from(FlowSnapshot))
        assert count == 2
        assert len(db.session.get(FlowSnapshot, "snapshot-test").payload["items"]) == 3
        evidence = db.session.execute(select(FlowEvidence)).scalars().all()
        assert len(evidence) == 2
        assert all(row.dataset_id == BOARD_ID and row.document["item_count"] == 1
                   for row in evidence)
        assert evidence[0].observed_at != evidence[1].observed_at


def test_five_unchanged_intraday_captures_retain_evidence_but_one_daily_snapshot(app):
    class CaptureClock:
        current = datetime(2026, 10, 21, 9, 30, tzinfo=UTC)

        @classmethod
        def now(cls, timezone):
            return cls.current.astimezone(timezone)

    with (
        app.app_context(),
        patch("app.projects.flow_metrics.collector.collect_payload", side_effect=lambda *_: payload()),
        patch("app.projects.flow_metrics.collector.datetime", CaptureClock),
    ):
        charts = copy.deepcopy(db.session.get(FlowBoard, BOARD_ID).charts)
        for hour in (9, 11, 13, 15, 17):
            CaptureClock.current = datetime(2026, 10, 21, hour, 30, tzinfo=UTC)
            assert collect(object()) == 3
        snapshots = db.session.scalars(select(FlowSnapshot).where(
            FlowSnapshot.captured_date == date(2026, 10, 21)
        )).all()
        assert len(snapshots) == 1
        assert snapshots[0].captured_at.replace(tzinfo=UTC) == CaptureClock.current
        evidence = db.session.scalars(select(FlowEvidence)).all()
        assert len(evidence) == 5
        assert len({row.observed_at for row in evidence}) == 5
        assert all(row.document["payload"] == evidence[0].document["payload"] for row in evidence)
        assert db.session.scalar(select(func.count()).select_from(FlowCollectionRun)) == 5
        assert db.session.get(FlowBoard, BOARD_ID).charts == charts
        before = {row.id for row in evidence}
        retain_evidence(evidence[-1].document)
        db.session.commit()
        assert set(db.session.scalars(select(FlowEvidence.id))) == before


def test_new_optional_fields_bind_without_changing_existing_ids(app):
    observation = payload([item("item-1"), item("item-2")])
    observation["fields"][0]["name"] = "Renamed status"
    observation["fields"].extend(
        [field("priority-id", "Priority"), field("refined-id", "Refined")]
    )
    observation["items"][0]["fields"].extend(
        [
            {"field": field("priority-id", "Priority"), "name": "High"},
            {"field": field("refined-id", "Refined"), "name": "Yes"},
        ]
    )
    with (
        app.app_context(),
        patch(
            "app.projects.flow_metrics.collector.collect_payload",
            return_value=observation,
        ),
    ):
        collect(object())
        assert (
            db.session.get(FlowBoard, BOARD_ID).field_mapping["status"] == "status-id"
        )
        assert metadata()["options"]["priority"] == ["High", "Not set"]
        assert "objective" not in metadata()["options"]
        chart = seeds()[3]
        chart["filters"]["query"] = "priority:High refined:Yes"
        assert result(chart)["sampleSize"] == 1
        chart["filters"]["query"] = "priority:High refined:No"
        assert result(chart)["sampleSize"] == 0


def connection(nodes, cursor=None, total=None):
    return {
        "nodes": nodes,
        "pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor},
        **({"totalCount": total} if total is not None else {}),
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("assignee", "synthetic-user"),
        ("label", "synthetic-label"),
        ("milestone", "Synthetic milestone"),
        ("reviewers", "synthetic-reviewer"),
        ("blocked-by", "synthetic/repository#7"),
        ("blocking", "synthetic/repository#8"),
        ("relates-to", "synthetic/repository#9"),
        ("parent-issue", "synthetic/repository#10"),
        ("sub-issues-progress", "1/2 (50%)"),
    ],
)
def test_metadata_filters_match_exact_items(app, field, value):
    with app.app_context():
        snapshot = db.session.get(FlowSnapshot, "snapshot-test")
        observation = copy.deepcopy(snapshot.payload)
        observation["metadataVersion"] = 1
        observation["items"][0]["content"].update(
            assignees=["synthetic-user"],
            labels=["synthetic-label"],
            milestone={"title": "Synthetic milestone"},
            reviewRequests=["synthetic-reviewer"],
            blockedBy=["synthetic/repository#7"],
            blocking=["synthetic/repository#8"],
            relatesTo=["synthetic/repository#9"],
            parent={
                "number": 10,
                "repository": {"nameWithOwner": "synthetic/repository"},
            },
            subIssuesSummary={"completed": 1, "total": 2, "percentCompleted": 50},
        )
        snapshot.payload = observation
        db.session.commit()
        assert value in metadata()["options"][field]
        chart = seeds()[3]
        chart["filters"]["query"] = f'{field}:"{value}"'
        data = result(chart)
        assert data["sampleSize"] == 1
        assert data["tickets"][0]["id"] == "item-1"
        chart["filters"]["query"] = f'{field}:"Not set"'
        assert result(chart)["sampleSize"] == 1


def test_old_observation_does_not_fabricate_metadata_filters(app):
    with app.app_context():
        chart = seeds()[3]
        chart["filters"]["query"] = "assignee:synthetic-user"
        assert "not collected" in result(chart)["unavailable"]


def test_metadata_connections_are_fully_paginated():
    from app.projects.flow_metrics.collector import collect_metadata

    content = {
        "__typename": "Issue",
        "id": "synthetic-id",
        "labels": connection([{"name": "First"}], cursor="next"),
    }

    class Client:
        def query(self, query, **variables):
            assert variables["cursor"] == "next"
            return {"node": {"labels": connection([{"name": "Second"}])}}

    collect_metadata(Client(), content)
    assert content["labels"] == ["First", "Second"]


def test_collector_paginates_items_and_nested_values_without_person_data():
    class Client:
        def query(self, query, **variables):
            if query == FIELD_QUERY:
                return {
                    "organization": {
                        "projectV2": {"fields": connection(payload()["fields"])}
                    }
                }
            if query == ITEM_QUERY:
                current = item("item-1" if variables["cursor"] is None else "item-2")
                current["isArchived"] = current.pop("archived")
                current["fieldValues"] = connection(
                    current.pop("fields"),
                    "values-next" if variables["cursor"] is None else None,
                )
                return {
                    "organization": {
                        "projectV2": {
                            "id": "project",
                            "items": connection(
                                [current],
                                "items-next" if variables["cursor"] is None else None,
                                2,
                            ),
                        }
                    }
                }
            return {
                "node": {
                    "fieldValues": connection(
                        [
                            {
                                "__typename": "ProjectV2ItemFieldUserValue",
                                "users": ["must-not-be-retained"],
                            },
                            {
                                "field": field("unneeded-text", "Private notes"),
                                "text": "must-not-be-retained",
                            },
                        ]
                    )
                }
            }

    data = collect_payload(Client())
    assert len(data["items"]) == 2
    assert "must-not-be-retained" not in str(data)


def test_repeated_cursor_rejected():
    with pytest.raises(CollectionError, match="pagination_invalid"):
        list(pages(lambda cursor: connection([], "repeated")))


class GeneratedBoardClient:
    def __init__(self, count, repeated=False, reported=None):
        self.count = count
        self.reported = count if reported is None else reported
        self.repeated = repeated
        self.item_calls = 0

    def query(self, query, **variables):
        if query == FIELD_QUERY:
            return {"organization": {"projectV2": {"fields": connection(payload()["fields"])}}}
        assert query == ITEM_QUERY
        self.item_calls += 1
        start = int(variables["cursor"] or 0)
        end = min(start + ITEM_PAGE_SIZE, self.count)
        nodes = []
        for index in range(start, end):
            current = item(f"generated-{index}")
            current["isArchived"] = current.pop("archived")
            current["fieldValues"] = connection(current.pop("fields"))
            nodes.append(current)
        cursor = ("20" if self.repeated else str(end)) if end < self.count else None
        return {"organization": {"projectV2": {
            "id": "generated-project", "items": connection(nodes, cursor, self.reported),
        }}}


@pytest.mark.parametrize("count", [2021, MAX_ITEMS])
def test_complete_board_pagination_reaches_supported_limit(count):
    client = GeneratedBoardClient(count)
    data = collect_payload(client)
    assert len(data["items"]) == count
    assert len({entry["id"] for entry in data["items"]}) == count
    assert client.item_calls == (count + ITEM_PAGE_SIZE - 1) // ITEM_PAGE_SIZE


def test_board_over_limit_fails_without_publication_or_history_changes(app):
    with app.app_context():
        before = copy.deepcopy(db.session.get(FlowSnapshot, "snapshot-test").payload)
        client = GeneratedBoardClient(MAX_ITEMS + 1)
        with pytest.raises(CollectionError, match="board_item_limit_exceeded"):
            collect(client)
        assert client.item_calls == 1
        assert db.session.get(FlowSnapshot, "snapshot-test").payload == before
        assert db.session.scalar(select(func.count()).select_from(FlowSnapshot)) == 1
        assert db.session.scalar(select(func.count()).select_from(FlowEvidence)) == 0
        assert db.session.scalar(select(FlowCollectionRun)).status == "failed"


def test_supported_item_limit_publishes_atomically_and_retains_prior_history(app):
    with app.app_context():
        before = copy.deepcopy(db.session.get(FlowSnapshot, "snapshot-test").payload)
        assert collect(GeneratedBoardClient(MAX_ITEMS)) == MAX_ITEMS
        latest = db.session.scalar(select(FlowSnapshot).order_by(
            FlowSnapshot.captured_at.desc()))
        assert len(latest.payload["items"]) == MAX_ITEMS
        assert db.session.get(FlowSnapshot, "snapshot-test").payload == before
        evidence = db.session.scalar(select(FlowEvidence))
        assert evidence.document["item_count"] == MAX_ITEMS
        assert evidence.document["payload"] == latest.payload


def test_item_pagination_rejects_repeated_cursor_and_unbounded_pages():
    with pytest.raises(CollectionError, match="github_pagination_invalid"):
        collect_payload(GeneratedBoardClient(60, repeated=True))
    with pytest.raises(CollectionError, match="github_pagination_invalid"):
        collect_payload(GeneratedBoardClient(MAX_ITEMS + 1, reported=MAX_ITEMS))


@pytest.mark.parametrize(("fault", "error_code"), [
    ("missing_item", "github_item_count_mismatch"),
    ("premature_end", "github_item_count_mismatch"),
    ("duplicate", "github_item_count_mismatch"),
    ("changed_total", "github_board_changed_during_collection"),
    ("inaccessible", "github_item_inaccessible"),
])
def test_incomplete_board_never_publishes_or_removes_prior_evidence(app, fault, error_code):
    from app.projects.flow_metrics.archive import snapshot_document

    class IncompleteClient(GeneratedBoardClient):
        def query(self, query, **variables):
            response = super().query(query, **variables)
            if query != ITEM_QUERY:
                return response
            page = response["organization"]["projectV2"]["items"]
            if fault == "missing_item":
                page["nodes"].pop()
            elif fault == "premature_end":
                page["pageInfo"] = {"hasNextPage": False, "endCursor": None}
            elif fault == "duplicate" and variables["cursor"] is not None:
                page["nodes"][0]["id"] = "generated-0"
            elif fault == "changed_total" and variables["cursor"] is not None:
                page["totalCount"] += 1
            elif fault == "inaccessible":
                page["nodes"][0]["content"] = None
            return response

    with app.app_context():
        prior = snapshot_document(db.session.get(FlowSnapshot, "snapshot-test"))
        evidence_id = retain_evidence(prior)
        db.session.commit()
        with pytest.raises(CollectionError, match=error_code):
            collect(IncompleteClient(21))
        assert snapshot_document(db.session.get(FlowSnapshot, "snapshot-test")) == prior
        assert db.session.get(FlowEvidence, evidence_id).document == prior
        assert db.session.scalar(select(func.count()).select_from(FlowSnapshot)) == 1
        assert db.session.scalar(select(func.count()).select_from(FlowEvidence)) == 1
        run = db.session.scalar(select(FlowCollectionRun))
        assert run.status == "failed"
        assert run.error_code == error_code


def test_collection_retains_archived_items_without_recent_date_or_sprint_scope():
    class ArchivedClient(GeneratedBoardClient):
        def query(self, query, **variables):
            response = super().query(query, **variables)
            if query == ITEM_QUERY:
                node = response["organization"]["projectV2"]["items"]["nodes"][0]
                node["isArchived"] = True
                node["content"]["createdAt"] = "2000-01-01T00:00:00Z"
                node["fieldValues"]["nodes"] = []
            return response

    data = collect_payload(ArchivedClient(1))
    assert len(data["items"]) == 1
    assert data["items"][0]["archived"] is True
    assert data["items"][0]["content"]["createdAt"] == "2000-01-01T00:00:00Z"
    assert data["items"][0]["fields"] == []


def test_collection_capture_time_precedes_publication_completion(app):
    from app.projects.flow_metrics.collector import publish

    captured = datetime.now(UTC)
    with app.app_context():
        run = FlowCollectionRun(id="generated-timing", board_id=BOARD_ID,
                                started_at=captured, status="running")
        db.session.add(run)
        db.session.commit()
        assert publish(run, payload(), captured) == 3
        snapshot = db.session.scalar(select(FlowSnapshot).where(
            FlowSnapshot.captured_date == captured.date()))
        assert snapshot.captured_at.replace(tzinfo=UTC) == captured
        assert snapshot.captured_date == captured.date()
        assert run.completed_at.replace(tzinfo=UTC) >= captured


def test_estimation_binding_is_stable_numeric_and_not_assumed_story_points(app):
    class Client:
        kind = "NUMBER"

        def query(self, query, **variables):
            if query == FIELD_QUERY:
                return {"organization": {"projectV2": {"fields": connection([
                    *payload()["fields"],
                    {"id": ESTIMATION_FIELD_ID, "name": "Renamed estimate", "dataType": self.kind},
                ])}}}
            current = item("item-1")
            current["isArchived"] = current.pop("archived")
            current["fields"].append({"field": field(ESTIMATION_FIELD_ID, "Renamed estimate"), "number": 8})
            current["fieldValues"] = connection(current.pop("fields"))
            return {"organization": {"projectV2": {"id": "generated-project", "items": connection([current], total=1)}}}

    client = Client()
    assert any(value.get("number") == 8 for value in collect_payload(client)["items"][0]["fields"])
    with app.app_context():
        original = copy.deepcopy(db.session.get(FlowSnapshot, "snapshot-test").payload)
        assert collect(client) == 1
        snapshot = db.session.scalar(select(FlowSnapshot).order_by(FlowSnapshot.captured_at.desc()))
        assert snapshot.payload["estimateBinding"] == {
            "fieldId": ESTIMATION_FIELD_ID, "name": "Renamed estimate", "dataType": "NUMBER", "unit": "number",
        }
        assert normalise(snapshot)[0]["estimate"] == 8
        assert normalise(snapshot)[0]["points"] == 3
        assert db.session.get(FlowSnapshot, "snapshot-test").payload == original
        preserved = copy.deepcopy(snapshot.payload)
        client.kind = "TEXT"
        with pytest.raises(CollectionError, match="estimation_field_type_changed"):
            collect(client)
        assert db.session.get(FlowSnapshot, snapshot.id).payload == preserved
        assert db.session.scalar(select(FlowCollectionRun).order_by(FlowCollectionRun.started_at.desc())).status == "failed"


def test_observation_contract_distinguishes_unavailable_fields_and_retains_ids():
    from app.projects.flow_metrics.workspace import (
        FIREBREAK_ITERATION,
        observation_contract,
    )

    generated = payload([item("item-1")])
    sprint = generated["items"][0]["fields"][2]
    sprint.update(iterationId=FIREBREAK_ITERATION, title="Generated Firebreak", startDate="2026-10-13", duration=14)
    original = copy.deepcopy(generated)
    data = observation_contract(generated, datetime(2026, 10, 19, tzinfo=UTC), "generated-ledger-hash", "generated-source", generated["mapping"])
    ticket = data["items"][0]
    assert ticket["id"] == "real:item-1" and ticket["sourceId"] == "item-1"
    assert ticket["sprint"] == "Firebreak" and ticket["actualSprint"] == "Generated Firebreak"
    assert data["sprints"][0]["start"] == "2026-10-13" and data["sprints"][0]["end"] == "2026-10-26"
    assert "label" not in ticket["availableFields"]
    assert ticket["points"] == 3 and ticket["provenance"] == "real"
    assert "events" not in ticket
    assert generated == original
    generated["metadataVersion"] = 1
    generated["items"][0]["content"].update(labels=[], reviewRequests=[], participants=[], subIssuesSummary=None)
    later = observation_contract(generated, datetime(2026, 10, 19, tzinfo=UTC), "generated-new-hash", "generated-source", generated["mapping"])
    assert later["items"][0]["label"] == ["Not set"]
    assert "label" in later["items"][0]["availableFields"]


def test_combined_external_adapter_is_lossless_handles_old_metadata_and_no_daily_duplicate(app):
    from app.projects.flow_metrics.archive import snapshot_document
    from app.projects.flow_metrics.workspace import exploratory_dataset

    with app.app_context():
        initialise_sample(sample_seed())
        published = snapshot_document(db.session.get(FlowSnapshot, "snapshot-test"))
        retain_evidence(published)
        alternate = copy.deepcopy(published)
        alternate["payload"]["items"][0]["content"]["title"] = "Generated simultaneous source version"
        retain_evidence(alternate)
        generated = item("item-1")
        generated["content"]["parent"] = {"id": "generated-parent", "number": 99, "url": "https://github.com/synthetic/repository/issues/99"}
        external = {
            "schema_version": 1, "source": "GitHub GraphQL API via local gh sign-in",
            "project": {"url": "https://github.com/orgs/ministryofjustice/projects/152",
                        "fields": {"nodes": payload()["fields"], "pageInfo": {"hasNextPage": False}}},
            "collection_started_at": "2026-10-18T10:00:00+00:00",
            "collection_finished_at": "2026-10-18T10:02:00+00:00",
            "snapshot_date": "2026-10-18", "snapshot_timezone": "Europe/London", "item_count": 1,
            "items": [{"id": generated["id"], "isArchived": False, "content": generated["content"],
                       "fieldValues": {"nodes": [*generated["fields"], {"__typename": "GeneratedUnknownValue"}],
                                       "pageInfo": {"hasNextPage": False}}}],
        }
        key = retain_evidence(external)
        db.session.commit()
        combined = exploratory_dataset()
        assert len(combined["realObservations"]) == 3
        assert len({entry["id"] for entry in combined["realObservations"]}) == 3
        latest = combined["realObservations"][-1]
        assert latest["items"][0]["sourceId"] == "item-1"
        assert "parent-issue" not in latest["items"][0]["availableFields"]
        assert latest["source"] == "external-gh-capture"
        assert db.session.get(FlowEvidence, key).document == external
        assert combined["tickets"] == sample_seed()["dataset"]["tickets"]
        assert combined["realEventCoverage"]["complete"] is False


def test_numeric_estimation_api_filter_identity_zero_missing_and_binding(app, client):
    with app.app_context():
        snapshot = db.session.get(FlowSnapshot, "snapshot-test")
        data = copy.deepcopy(snapshot.payload)
        data["fields"].append({"id": ESTIMATION_FIELD_ID, "name": "Estimation", "dataType": "NUMBER"})
        for ticket, value in zip(data["items"][:2], [0, 8], strict=True):
            ticket["fields"].append({"field": field(ESTIMATION_FIELD_ID, "Estimation"), "number": value})
        missing = item("item-4", "In Review")
        data["items"].append(missing)
        snapshot.payload = data
        db.session.commit()
        definition = {**seeds()[3], "metric": "custom", "y": "estimation", "x": "team"}
        measured = result(definition)
        assert measured["rows"][0]["value"] == 8
        assert measured["rows"][0]["ids"] == ["item-1", "item-2"]
        assert "2 of 3" in measured["coverageText"]
        assert result({**definition, "y": "averageEstimation"})["rows"][0]["value"] == 4
        assert result({**definition, "filters": {**definition["filters"], "query": "status:TODO"}})["rows"][0]["value"] == 0
        assert "No matching items" in result({**definition, "filters": {**definition["filters"], "query": 'status:"In Review"'}})["unavailable"]
        data = copy.deepcopy(snapshot.payload)
        data["fields"][-1]["dataType"] = "TEXT"
        snapshot.payload = data
        db.session.commit()
        assert "No matching items" in result(definition)["unavailable"]
    headers = csrf(client)
    chart = {**seeds()[3], "metric": "custom", "y": "averageEstimation"}
    charts = [chart]
    response = client.post("/flow-metrics/api/charts", headers=headers, json={"charts": charts, "revision": 0})
    assert response.status_code == 200
    assert client.get("/flow-metrics/api/workspace").json["charts"][0]["y"] == "averageEstimation"
