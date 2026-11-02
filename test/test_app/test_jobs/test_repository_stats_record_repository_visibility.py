# ruff: noqa: DTZ001 - naive datetimes here are UTC, as stored by the database
import unittest
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.projects.repository_stats.config.collection_config import OrgInstallation
from app.projects.repository_stats.db_models import (
    RepositoryStatsJobRun,
    RepositoryStatsOrganisation,
    RepositoryStatsTeamAccess,
    RepositoryStatsVisibilityEvent,
    RepositoryStatsVisibilitySnapshot,
)
from app.projects.repository_stats.jobs.record_repository_visibility import (
    record_repository_visibility,
)
from app.projects.repository_stats.repositories.visibility_repository import (
    VisibilityRepository,
)
from app.projects.repository_stats.services.github_inventory import GitHubInventoryError
from app.projects.repository_stats.services.visibility_service import VisibilityService

MOJ = "ministryofjustice"
MAS = "moj-analytical-services"
DAY_1 = datetime(2026, 9, 24, 4, 0, tzinfo=UTC)
DAY_2 = datetime(2026, 9, 25, 4, 0, tzinfo=UTC)
DAY_2_PM = datetime(2026, 9, 25, 13, 0, tzinfo=UTC)


def repo(github_id, name, visibility="public", archived=False, fork=False):
    return {
        "id": github_id,
        "name": name,
        "visibility": visibility,
        "archived": archived,
        "fork": fork,
        "created_at": "2020-01-02T03:04:05Z",
        "pushed_at": "2026-09-01T10:00:00Z",
    }


class Response:
    def __init__(self, body, status_code=200, headers=None):
        self.body = body
        self.status_code = status_code
        self.links = {}
        self.headers = headers or {}

    def json(self):
        return self.body


def team(slug, repos, name=None, parent=None):
    """A team as the fake GitHub returns it. repos: {github_id: role_name}."""
    return {"slug": slug, "name": name or slug, "parent": parent, "repos": repos}


class FakeGitHub:
    """The repositories and teams GitHub would return, per organisation. Never calls
    the network."""

    def __init__(
        self,
        repositories_by_org,
        failing_orgs=(),
        teams_by_org=None,
        failing_team_orgs=(),
        display_names=None,
        failing_profile_orgs=(),
        rate_headers_by_org=None,
    ):
        self.repositories_by_org = repositories_by_org
        self.failing_orgs = set(failing_orgs)
        self.teams_by_org = teams_by_org or {}
        self.failing_team_orgs = set(failing_team_orgs)
        self.display_names = display_names or {}
        self.failing_profile_orgs = set(failing_profile_orgs)
        self.rate_headers_by_org = rate_headers_by_org or {}
        # {path: how many times it times out before answering}
        self.slow_paths = {}
        self.calls = []

    def client_for(self, installation_id, request_coordinator=None):
        org = {1: MOJ, 2: MAS}[installation_id]
        github = self

        class Client:
            def get(self, path):
                github.calls.append(path)

                def respond(body, status_code=200):
                    return Response(
                        body, status_code, github.rate_headers_by_org.get(org)
                    )

                if github.slow_paths.get(path):
                    github.slow_paths[path] -= 1
                    raise requests.ReadTimeout("Read timed out. (read timeout=10)")
                teams = github.teams_by_org.get(org, [])
                if path == f"/orgs/{org}":
                    if org in github.failing_profile_orgs:
                        return respond({"message": "Server Error"}, 500)
                    return respond(
                        {"login": org, "name": github.display_names.get(org)}
                    )
                if path == f"/orgs/{org}/repos?type=all&per_page=100":
                    if org in github.failing_orgs:
                        return respond({"message": "Server Error"}, 500)
                    return respond(github.repositories_by_org.get(org, []))
                if path == f"/orgs/{org}/teams?per_page=100":
                    if org in github.failing_team_orgs:
                        return respond({"message": "Forbidden"}, 403)
                    return respond(
                        [
                            {
                                "slug": t["slug"],
                                "name": t["name"],
                                "parent": t["parent"] and {"slug": t["parent"]},
                            }
                            for t in teams
                        ]
                    )
                for t in teams:
                    if path == f"/orgs/{org}/teams/{t['slug']}/repos?per_page=100":
                        if t["repos"] is None:
                            # Renamed or deleted since the team list was fetched.
                            return respond({"message": "Not Found"}, 404)
                        return respond(
                            [
                                {"id": github_id, "role_name": role}
                                for github_id, role in t["repos"].items()
                            ]
                        )
                raise AssertionError(path)

        return Client()


class RecordRepositoryVisibilityTestCase(unittest.TestCase):
    orgs = (OrgInstallation(MOJ, 1),)

    def setUp(self):
        engine = create_engine("sqlite://")
        RepositoryStatsVisibilitySnapshot.metadata.create_all(
            engine,
            tables=[
                RepositoryStatsVisibilitySnapshot.__table__,
                RepositoryStatsVisibilityEvent.__table__,
                RepositoryStatsJobRun.__table__,
                RepositoryStatsTeamAccess.__table__,
                RepositoryStatsOrganisation.__table__,
            ],
        )
        self.session = Session(engine)
        self.addCleanup(self.session.close)
        self.repository = VisibilityRepository(self.session)

    def run_job(
        self,
        repositories,
        at,
        orgs=None,
        failing_orgs=(),
        teams=None,
        failing_team_orgs=(),
        display_names=None,
        failing_profile_orgs=(),
        slow_paths=None,
        workers=1,
        rate_headers_by_org=None,
    ):
        github = FakeGitHub(
            repositories if isinstance(repositories, dict) else {MOJ: repositories},
            failing_orgs,
            teams if teams is None or isinstance(teams, dict) else {MOJ: teams},
            failing_team_orgs,
            display_names,
            failing_profile_orgs,
            rate_headers_by_org,
        )
        github.slow_paths.update(slow_paths or {})
        self.github = github
        orgs = orgs or self.orgs
        times = iter(
            [at]
            + [moment for _ in orgs for moment in (at, at + timedelta(minutes=4))]
            + [at + timedelta(minutes=4)]
        )
        return record_repository_visibility(
            self.repository,
            orgs,
            github.client_for,
            now=lambda: next(times),
            workers=workers,
        )

    def snapshots(self, captured_on=None):
        query = self.session.query(RepositoryStatsVisibilitySnapshot)
        if captured_on:
            query = query.filter_by(captured_on=captured_on)
        return {
            (row.github_id, row.captured_on.isoformat()): (
                row.name,
                row.visibility,
                row.archived,
            )
            for row in query.all()
        }

    def events(self):
        return [
            (
                e.github_id,
                e.name,
                e.event_type,
                e.from_visibility,
                e.to_visibility,
                e.occurred_on.isoformat(),
                e.actor,
                e.source,
            )
            for e in self.session.query(RepositoryStatsVisibilityEvent)
            .order_by(RepositoryStatsVisibilityEvent.id)
            .all()
        ]

    def team_access(self):
        return sorted(
            (
                r.org,
                r.github_id,
                r.team_slug,
                r.team_name,
                r.parent_team_slug,
                r.permission,
            )
            for r in self.session.query(RepositoryStatsTeamAccess)
        )

    def runs(self):
        return [
            (r.status, r.job_name, r.org)
            for r in self.session.query(RepositoryStatsJobRun)
            .filter(RepositoryStatsJobRun.org.is_(None))
            .order_by(RepositoryStatsJobRun.id)
        ]

    def organisation_runs(self):
        return [
            (r.org, r.status)
            for r in self.session.query(RepositoryStatsJobRun)
            .filter(RepositoryStatsJobRun.org.isnot(None))
            .order_by(RepositoryStatsJobRun.id)
        ]


class TestRecordRepositoryVisibility(RecordRepositoryVisibilityTestCase):
    def test_first_run_is_a_baseline_without_events(self):
        results = self.run_job(
            [repo(1, "one"), repo(2, "two", "internal", archived=True)], DAY_1
        )
        self.assertEqual(
            self.snapshots(),
            {
                (1, "2026-09-24"): ("one", "public", False),
                (2, "2026-09-24"): ("two", "internal", True),
            },
        )
        self.assertEqual(self.events(), [])
        self.assertEqual(
            self.runs(), [("success", "record_repository_visibility", None)]
        )
        self.assertEqual(self.organisation_runs(), [(MOJ, "success")])
        self.assertEqual(
            [(r.org, r.repositories, r.events) for r in results], [(MOJ, 2, 0)]
        )

    def test_visibility_change(self):
        self.run_job([repo(1, "one")], DAY_1)
        self.run_job([repo(1, "one", "internal")], DAY_2)
        self.assertEqual(
            self.events(),
            [(1, "one", "changed", "public", "internal", "2026-09-25", None, "scan")],
        )

    def test_created_repository(self):
        self.run_job([repo(1, "one")], DAY_1)
        self.run_job([repo(1, "one"), repo(2, "new", "private")], DAY_2)
        self.assertEqual(
            self.events(),
            [(2, "new", "created", None, "private", "2026-09-25", None, "scan")],
        )

    def test_deleted_repository(self):
        self.run_job([repo(1, "one"), repo(2, "gone", "internal")], DAY_1)
        self.run_job([repo(1, "one")], DAY_2)
        self.assertEqual(
            self.events(),
            [(2, "gone", "deleted", "internal", None, "2026-09-25", None, "scan")],
        )
        self.assertEqual(set(self.snapshots(date(2026, 9, 25))), {(1, "2026-09-25")})

    def test_archived_repository(self):
        self.run_job([repo(1, "one"), repo(2, "already", archived=True)], DAY_1)
        self.run_job(
            [repo(1, "one", archived=True), repo(2, "already", archived=True)], DAY_2
        )
        self.assertEqual(
            self.events(),
            [(1, "one", "archived", None, None, "2026-09-25", None, "scan")],
        )

    def test_archived_and_made_internal_in_one_scan(self):
        self.run_job([repo(1, "one")], DAY_1)
        self.run_job([repo(1, "one", "internal", archived=True)], DAY_2)
        self.assertEqual(
            [e[2:5] for e in self.events()],
            [("changed", "public", "internal"), ("archived", None, None)],
        )

    def test_unarchiving_is_not_an_event(self):
        self.run_job([repo(1, "one", archived=True)], DAY_1)
        self.run_job([repo(1, "one")], DAY_2)
        self.assertEqual(self.events(), [])

    def test_rename_is_not_a_delete_and_create(self):
        self.run_job([repo(1, "old-name")], DAY_1)
        self.run_job([repo(1, "new-name")], DAY_2)
        self.assertEqual(self.events(), [])
        self.assertEqual(
            self.snapshots(date(2026, 9, 25)),
            {(1, "2026-09-25"): ("new-name", "public", False)},
        )

    def test_rename_and_change_uses_the_new_name(self):
        self.run_job([repo(1, "old-name")], DAY_1)
        self.run_job([repo(1, "new-name", "internal")], DAY_2)
        self.assertEqual([e[1:3] for e in self.events()], [("new-name", "changed")])

    def test_second_run_on_the_same_day_updates_todays_snapshot(self):
        self.run_job([repo(1, "one"), repo(2, "two")], DAY_1)
        self.run_job([repo(1, "one"), repo(2, "two")], DAY_2)
        self.run_job([repo(1, "one"), repo(2, "two")], DAY_2_PM)
        self.assertEqual(
            self.session.query(RepositoryStatsVisibilitySnapshot).count(), 4
        )
        self.assertEqual(self.events(), [])
        self.assertEqual([r[0] for r in self.runs()], ["success"] * 3)

    def test_changes_between_two_runs_on_the_same_day_are_recorded_once(self):
        self.run_job([repo(1, "one"), repo(2, "two"), repo(3, "three")], DAY_1)
        self.run_job(
            [repo(1, "one", "internal"), repo(2, "two"), repo(3, "three")], DAY_2
        )
        self.run_job(
            [repo(1, "one", "internal"), repo(2, "two", "private"), repo(4, "four")],
            DAY_2_PM,
        )
        self.run_job(
            [repo(1, "one", "internal"), repo(2, "two", "private"), repo(4, "four")],
            DAY_2_PM + timedelta(hours=1),
        )
        self.assertEqual(
            [e[:5] for e in self.events()],
            [
                (1, "one", "changed", "public", "internal"),
                (4, "four", "created", None, "public"),
                (2, "two", "changed", "public", "private"),
                (3, "three", "deleted", "public", None),
            ],
        )
        self.assertEqual(
            self.snapshots(date(2026, 9, 25)),
            {
                (1, "2026-09-25"): ("one", "internal", False),
                (2, "2026-09-25"): ("two", "private", False),
                (4, "2026-09-25"): ("four", "public", False),
            },
        )
        self.assertEqual(len(self.snapshots(date(2026, 9, 24))), 3)

    def test_later_organisation_failure_keeps_earlier_success(self):
        orgs = [OrgInstallation(MOJ, 1), OrgInstallation(MAS, 2)]
        self.run_job({MOJ: [repo(1, "one")], MAS: [repo(5, "five")]}, DAY_1, orgs)
        with self.assertRaises(GitHubInventoryError):
            self.run_job(
                {
                    MOJ: [repo(1, "one", "internal"), repo(2, "new")],
                    MAS: [repo(5, "five", "private")],
                },
                DAY_2,
                orgs,
                failing_orgs={MAS},
            )
        self.assertEqual(
            self.snapshots(DAY_2.date()),
            {
                (1, "2026-09-25"): ("one", "internal", False),
                (2, "2026-09-25"): ("new", "public", False),
            },
        )
        self.assertCountEqual([event[0] for event in self.events()], [1, 2])
        self.assertEqual([r[0] for r in self.runs()], ["success", "failed"])
        self.assertEqual(
            self.organisation_runs(),
            [(MOJ, "success"), (MAS, "success"), (MOJ, "success"), (MAS, "failed")],
        )
        states = self.repository.find_organisation_scan_states(
            "record_repository_visibility"
        )
        self.assertEqual(states[MAS].latest_status, "failed")
        self.assertEqual(
            states[MAS].last_successful_at.replace(tzinfo=UTC),
            DAY_1 + timedelta(minutes=4),
        )
        self.assertEqual(
            states[MOJ].last_successful_at.replace(tzinfo=UTC),
            DAY_2 + timedelta(minutes=4),
        )

        self.run_job(
            {
                MOJ: [repo(1, "one", "internal"), repo(2, "new")],
                MAS: [repo(5, "five", "private")],
            },
            DAY_2_PM,
            orgs,
        )
        recovered = self.repository.find_organisation_scan_states(
            "record_repository_visibility"
        )[MAS]
        self.assertEqual(recovered.latest_status, "success")
        self.assertEqual(
            recovered.last_successful_at.replace(tzinfo=UTC),
            DAY_2_PM + timedelta(minutes=4),
        )

    def test_earlier_organisation_failure_does_not_stop_later_scan(self):
        orgs = [OrgInstallation(MOJ, 1), OrgInstallation(MAS, 2)]
        self.run_job({MOJ: [repo(1, "one")], MAS: [repo(5, "five")]}, DAY_1, orgs)
        with self.assertRaises(GitHubInventoryError):
            self.run_job(
                {MOJ: [repo(1, "one")], MAS: [repo(5, "five", "internal")]},
                DAY_2,
                orgs,
                failing_orgs={MOJ},
            )
        self.assertEqual(
            self.snapshots(DAY_2.date()),
            {(5, "2026-09-25"): ("five", "internal", False)},
        )
        self.assertEqual([event[0] for event in self.events()], [5])
        self.assertEqual(
            self.organisation_runs()[-2:], [(MOJ, "failed"), (MAS, "success")]
        )

    def test_database_failure_rolls_back_only_the_affected_organisation(self):
        orgs = [OrgInstallation(MOJ, 1), OrgInstallation(MAS, 2)]
        self.run_job({MOJ: [repo(1, "one")], MAS: [repo(5, "five")]}, DAY_1, orgs)
        original = self.repository.add_events

        def fail_for_mas(events):
            original(events)
            if any(event.org == MAS for event in events):
                self.session.flush()
                raise RuntimeError("simulated database failure")

        self.repository.add_events = fail_for_mas
        with self.assertRaises(RuntimeError):
            self.run_job(
                {MOJ: [repo(1, "one", "internal")], MAS: [repo(5, "five", "private")]},
                DAY_2,
                orgs,
            )
        self.assertEqual(
            self.snapshots(DAY_2.date()),
            {(1, "2026-09-25"): ("one", "internal", False)},
        )
        self.assertEqual([event[0] for event in self.events()], [1])
        self.assertEqual(
            self.organisation_runs()[-2:], [(MOJ, "success"), (MAS, "failed")]
        )

    def test_database_failure_does_not_stop_a_later_organisation(self):
        orgs = [OrgInstallation(MOJ, 1), OrgInstallation(MAS, 2)]
        self.run_job({MOJ: [repo(1, "one")], MAS: [repo(5, "five")]}, DAY_1, orgs)
        original = self.repository.add_events

        def fail_for_moj(events):
            original(events)
            if any(event.org == MOJ for event in events):
                self.session.flush()
                raise RuntimeError("simulated database failure")

        self.repository.add_events = fail_for_moj
        with self.assertRaises(RuntimeError):
            self.run_job(
                {MOJ: [repo(1, "one", "internal")], MAS: [repo(5, "five", "private")]},
                DAY_2,
                orgs,
            )
        self.assertEqual(
            self.snapshots(DAY_2.date()),
            {(5, "2026-09-25"): ("five", "private", False)},
        )
        self.assertEqual([event[0] for event in self.events()], [5])
        self.assertEqual(
            self.organisation_runs()[-2:], [(MOJ, "failed"), (MAS, "success")]
        )

    def test_running_and_legacy_rows_do_not_invent_org_freshness(self):
        self.session.add_all(
            [
                RepositoryStatsJobRun(
                    job_name="record_repository_visibility",
                    started_at=DAY_1,
                    finished_at=DAY_1,
                    status="success",
                ),
                RepositoryStatsJobRun(
                    job_name="record_repository_visibility",
                    org=MAS,
                    started_at=DAY_2,
                    status="running",
                ),
            ]
        )
        self.session.commit()
        self.assertEqual(
            self.repository.find_organisation_scan_states(
                "record_repository_visibility"
            ),
            {},
        )

    def test_org_snapshot_dates_follow_each_scan_across_midnight(self):
        orgs = [OrgInstallation(MOJ, 1), OrgInstallation(MAS, 2)]
        github = FakeGitHub({MOJ: [repo(1, "one")], MAS: [repo(5, "five")]})
        moments = iter(
            [
                datetime(2026, 12, 31, 23, 59, tzinfo=UTC),
                datetime(2026, 12, 31, 23, 59, tzinfo=UTC),
                datetime(2027, 1, 1, 0, 1, tzinfo=UTC),
                datetime(2027, 1, 1, 0, 2, tzinfo=UTC),
                datetime(2027, 1, 1, 0, 3, tzinfo=UTC),
                datetime(2027, 1, 1, 0, 4, tzinfo=UTC),
            ]
        )

        record_repository_visibility(
            self.repository, orgs, github.client_for, now=lambda: next(moments)
        )

        self.assertEqual(
            self.snapshots(date(2026, 12, 31)),
            {(1, "2026-12-31"): ("one", "public", False)},
        )
        self.assertEqual(
            self.snapshots(date(2027, 1, 1)),
            {(5, "2027-01-01"): ("five", "public", False)},
        )
        first_mas_scan = self.repository.find_first_successful_run_started_at(
            "record_repository_visibility", MAS
        )
        self.assertEqual(first_mas_scan.date(), date(2027, 1, 1))

    def test_database_failure_rolls_back_everything(self):
        self.run_job([repo(1, "one")], DAY_1)
        before = (self.snapshots(), self.events())
        original = self.repository.add_events

        def add_then_fail(events):
            original(events)
            self.session.flush()
            raise RuntimeError("database went away")

        self.repository.add_events = add_then_fail
        with self.assertRaises(RuntimeError):
            self.run_job([repo(1, "one", "internal")], DAY_2)
        self.assertEqual((self.snapshots(), self.events()), before)
        self.assertEqual([r[0] for r in self.runs()], ["success", "failed"])

    def test_an_empty_list_after_a_full_one_is_treated_as_a_failure(self):
        self.run_job([repo(1, "one")], DAY_1)
        with self.assertRaisesRegex(GitHubInventoryError, "collection failed"):
            self.run_job([], DAY_2)
        self.assertEqual(self.events(), [])
        self.assertEqual([r[0] for r in self.runs()], ["success", "failed"])

    def test_several_organisations_in_one_run(self):
        orgs = [OrgInstallation(MOJ, 1), OrgInstallation(MAS, 2)]
        self.run_job({MOJ: [repo(1, "one")], MAS: [repo(2, "model")]}, DAY_1, orgs)
        self.run_job(
            {MOJ: [repo(1, "one")], MAS: [repo(2, "model", "internal")]}, DAY_2, orgs
        )
        rows = self.session.query(RepositoryStatsVisibilitySnapshot).filter_by(
            captured_on=date(2026, 9, 25)
        )
        self.assertEqual(
            sorted((r.org, r.name) for r in rows), [(MOJ, "one"), (MAS, "model")]
        )
        self.assertEqual(
            [
                (e.org, e.event_type)
                for e in self.session.query(RepositoryStatsVisibilityEvent)
            ],
            [(MAS, "changed")],
        )

    def test_a_new_organisation_starts_with_a_baseline(self):
        self.run_job({MOJ: [repo(1, "one")]}, DAY_1)
        orgs = [OrgInstallation(MOJ, 1), OrgInstallation(MAS, 2)]
        self.run_job(
            {MOJ: [repo(1, "one")], MAS: [repo(2, "model"), repo(3, "other")]},
            DAY_2,
            orgs,
        )
        self.assertEqual(self.events(), [])

    def test_captured_on_is_the_uk_date(self):
        self.run_job([repo(1, "one")], datetime(2026, 6, 30, 23, 30, tzinfo=UTC))
        self.assertEqual(set(self.snapshots()), {(1, "2026-07-01")})

    def test_last_updated_is_the_latest_successful_finish(self):
        self.assertIsNone(
            self.repository.find_last_successful_run_finished_at(
                "record_repository_visibility"
            )
        )
        self.run_job([repo(1, "one")], DAY_1)
        self.run_job([repo(1, "one")], DAY_2_PM)
        with self.assertRaises(GitHubInventoryError):
            self.run_job(
                [repo(1, "one")], DAY_2_PM + timedelta(hours=3), failing_orgs={MOJ}
            )
        finished = self.repository.find_last_successful_run_finished_at(
            "record_repository_visibility"
        )
        self.assertEqual(finished.replace(tzinfo=None), datetime(2026, 9, 25, 13, 4))
        self.assertIsNone(
            self.repository.find_last_successful_run_finished_at("another_job")
        )


class TestRecordTeamAccess(RecordRepositoryVisibilityTestCase):
    TEAMS = (
        team("platform-team", {1: "admin", 2: "write"}, name="Platform team"),
        team("service-team", {1: "read"}, parent="platform-team"),
    )

    def test_records_team_access_for_every_repository(self):
        results = self.run_job(
            [repo(1, "one"), repo(2, "two", "private", archived=True)],
            DAY_1,
            teams=self.TEAMS,
        )
        self.assertEqual(
            self.team_access(),
            [
                (MOJ, 1, "platform-team", "Platform team", None, "admin"),
                (MOJ, 1, "service-team", "service-team", "platform-team", "read"),
                (MOJ, 2, "platform-team", "Platform team", None, "write"),
            ],
        )
        # One call for repositories, one for teams, one per team for its repositories
        # and one for the organisation's display name.
        self.assertEqual(len(self.github.calls), 5)
        self.assertEqual(results[0].api_calls, 5)
        self.assertEqual(results[0].team_access, 3)
        recorded = self.session.query(RepositoryStatsTeamAccess).first().recorded_at
        self.assertEqual(recorded.replace(tzinfo=None), DAY_1.replace(tzinfo=None))

    def test_api_calls_are_logged(self):
        with self.assertLogs(
            "app.projects.repository_stats.jobs.record_repository_visibility", "INFO"
        ) as logs:
            self.run_job([repo(1, "one")], DAY_1, teams=self.TEAMS)
        output = "\n".join(logs.output)
        self.assertIn("organisation=ministryofjustice status=success", output)
        self.assertIn("api_calls=5", output)
        self.assertIn("repositories=1 events=0 team_access_rows=3", output)

    def test_summary_logs_only_safe_rate_metrics_in_parallel(self):
        teams = [
            team("team-a", {1: "read"}),
            team("team-b", {1: "write"}),
            team("team-c", {1: "admin"}),
        ]
        with self.assertLogs(
            "app.projects.repository_stats.jobs.record_repository_visibility", "INFO"
        ) as logs:
            results = self.run_job(
                [repo(1, "sensitive-repository-marker")],
                DAY_1,
                teams=teams,
                workers=3,
                rate_headers_by_org={
                    MOJ: {
                        "x-ratelimit-remaining": "42",
                        "x-ratelimit-reset": "1790000000",
                        "authorization": "sensitive-header-marker",
                    }
                },
            )
        output = "\n".join(logs.output)
        self.assertEqual(results[0].api_calls, 6)
        self.assertIn("duration_seconds=", output)
        self.assertIn(
            "api_calls=6 rate_limit_remaining=42 rate_limit_reset=1790000000", output
        )
        self.assertNotIn("sensitive-repository-marker", output)
        self.assertNotIn("sensitive-header-marker", output)

    def test_failed_summary_does_not_log_untrusted_values(self):
        with (
            patch(
                "app.projects.repository_stats.jobs.record_repository_visibility."
                "fetch_org_repositories",
                side_effect=RuntimeError("sensitive-error-marker"),
            ),
            self.assertLogs(
                "app.projects.repository_stats.jobs.record_repository_visibility",
                "INFO",
            ) as logs,
            self.assertRaises(RuntimeError) as failure,
        ):
            self.run_job([repo(1, "sensitive-repository-marker")], DAY_1)
        output = "\n".join(logs.output)
        self.assertIn("status=failed", output)
        self.assertIn("error_type=RuntimeError", output)
        self.assertIn("rate_limit_remaining=unavailable", output)
        self.assertNotIn("sensitive-error-marker", output)
        self.assertNotIn("sensitive-repository-marker", output)
        self.assertNotIn("sensitive-error-marker", str(failure.exception))

    def test_invalid_rate_headers_are_not_logged(self):
        with self.assertLogs(
            "app.projects.repository_stats.jobs.record_repository_visibility", "INFO"
        ) as logs:
            self.run_job(
                [repo(1, "one")],
                DAY_1,
                rate_headers_by_org={
                    MOJ: {
                        "x-ratelimit-remaining": "sensitive-header-marker",
                        "x-ratelimit-reset": "-1",
                    }
                },
            )
        output = "\n".join(logs.output)
        self.assertIn("rate_limit_remaining=unavailable", output)
        self.assertIn("rate_limit_reset=unavailable", output)
        self.assertNotIn("sensitive-header-marker", output)

    def test_parallel_team_collection_logs_phase_timings_and_call_counts(self):
        teams = [
            team("team-a", {1: "read"}),
            team("team-b", {1: "write"}),
            team("team-c", {1: "admin"}),
        ]
        with self.assertLogs(
            "app.projects.repository_stats.jobs.record_repository_visibility", "INFO"
        ) as logs:
            results = self.run_job([repo(1, "one")], DAY_1, teams=teams, workers=3)
        self.assertEqual(results[0].api_calls, 6)
        self.assertIn(
            "repository inventory ",
            "\n".join(logs.output),
        )
        self.assertIn(
            "team access ",
            "\n".join(logs.output),
        )
        self.assertIn("(4 API calls, 3 workers)", "\n".join(logs.output))

    def test_team_access_worker_count_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "between 1 and 3"):
            self.run_job([repo(1, "one")], DAY_1, workers=4)

    def test_each_run_replaces_the_set(self):
        self.run_job([repo(1, "one")], DAY_1, teams=self.TEAMS)
        self.run_job([repo(1, "one")], DAY_2, teams=[team("ops-team", {1: "maintain"})])
        self.assertEqual(
            self.team_access(), [(MOJ, 1, "ops-team", "ops-team", None, "maintain")]
        )

    def test_team_failure_keeps_old_data_and_saves_the_snapshot(self):
        self.run_job([repo(1, "one")], DAY_1, teams=self.TEAMS)
        before = self.team_access()
        with self.assertLogs(
            "app.projects.repository_stats.jobs.record_repository_visibility", "ERROR"
        ) as logs:
            results = self.run_job(
                [repo(1, "one", "internal")], DAY_2, failing_team_orgs={MOJ}
            )
        self.assertIn(
            "Couldn't fetch team access for ministryofjustice", logs.output[0]
        )
        self.assertEqual(self.team_access(), before)
        self.assertEqual(
            self.snapshots(date(2026, 9, 25)),
            {(1, "2026-09-25"): ("one", "internal", False)},
        )
        self.assertEqual([e[2] for e in self.events()], ["changed"])
        self.assertEqual([r[0] for r in self.runs()], ["success", "success"])
        self.assertIsNone(results[0].team_access)

    @patch("app.projects.repository_stats.services.github_teams.time.sleep")
    def test_one_slow_team_call_is_retried_and_keeps_all_team_data(self, sleep):
        with self.assertLogs(
            "app.projects.repository_stats.services.github_teams", "WARNING"
        ) as logs:
            results = self.run_job(
                [repo(1, "one"), repo(2, "two")],
                DAY_1,
                teams=self.TEAMS,
                slow_paths={f"/orgs/{MOJ}/teams/service-team/repos?per_page=100": 1},
            )
        self.assertEqual(results[0].team_access, 3)
        self.assertEqual(len(self.team_access()), 3)
        self.assertIn("ReadTimeout", logs.output[0])
        sleep.assert_called_once_with(2)
        self.assertEqual(results[0].api_calls, 6)

    @patch("app.projects.repository_stats.services.github_teams.time.sleep")
    def test_team_call_that_keeps_timing_out_keeps_old_data(self, sleep):
        self.run_job([repo(1, "one")], DAY_1, teams=self.TEAMS)
        before = self.team_access()
        path = f"/orgs/{MOJ}/teams/service-team/repos?per_page=100"
        with self.assertLogs(
            "app.projects.repository_stats.jobs.record_repository_visibility", "ERROR"
        ):
            results = self.run_job(
                [repo(1, "one")], DAY_2, teams=self.TEAMS, slow_paths={path: 3}
            )
        self.assertIsNone(results[0].team_access)
        self.assertEqual(self.team_access(), before)
        self.assertEqual([call.args for call in sleep.call_args_list], [(2,), (5,)])

    def test_a_404_on_one_team_still_stores_the_other_teams(self):
        self.run_job([repo(1, "one")], DAY_1, teams=[team("old-team", {1: "read"})])
        with self.assertLogs(
            "app.projects.repository_stats.services.github_teams", "WARNING"
        ) as logs:
            results = self.run_job(
                [repo(1, "one"), repo(2, "two")],
                DAY_2,
                teams=[
                    team("platform-team", {1: "admin", 2: "write"}),
                    team("deleted-team", None),
                    team("service-team", {1: "read"}),
                ],
            )
        self.assertEqual(
            self.team_access(),
            [
                (MOJ, 1, "platform-team", "platform-team", None, "admin"),
                (MOJ, 1, "service-team", "service-team", None, "read"),
                (MOJ, 2, "platform-team", "platform-team", None, "write"),
            ],
        )
        self.assertEqual(results[0].team_access, 3)
        self.assertIn("deleted-team", "\n".join(logs.output))
        self.assertEqual([r[0] for r in self.runs()], ["success", "success"])

    def test_team_failure_in_one_org_keeps_other_orgs_teams(self):
        orgs = [OrgInstallation(MOJ, 1), OrgInstallation(MAS, 2)]
        teams = {MOJ: self.TEAMS, MAS: [team("analysts", {5: "write"})]}
        self.run_job(
            {MOJ: [repo(1, "one")], MAS: [repo(5, "five")]}, DAY_1, orgs, teams=teams
        )
        self.run_job(
            {MOJ: [repo(1, "one")], MAS: [repo(5, "five")]},
            DAY_2,
            orgs,
            teams={MOJ: [team("ops-team", {1: "read"})], MAS: []},
            failing_team_orgs={MAS},
        )
        self.assertEqual(
            self.team_access(),
            [
                (MOJ, 1, "ops-team", "ops-team", None, "read"),
                (MAS, 5, "analysts", "analysts", None, "write"),
            ],
        )

    def test_empty_team_list_after_a_full_one_keeps_old_data(self):
        self.run_job([repo(1, "one")], DAY_1, teams=self.TEAMS)
        before = self.team_access()
        with self.assertLogs(
            "app.projects.repository_stats.jobs.record_repository_visibility", "ERROR"
        ):
            self.run_job([repo(1, "one")], DAY_2, teams=[])
        self.assertEqual(self.team_access(), before)

    def test_repository_failure_writes_no_team_access(self):
        self.run_job([repo(1, "one")], DAY_1, teams=self.TEAMS)
        before = self.team_access()
        with self.assertRaises(GitHubInventoryError):
            self.run_job(
                [repo(1, "one")],
                DAY_2,
                failing_orgs={MOJ},
                teams=[team("ops-team", {1: "read"})],
            )
        self.assertEqual(self.team_access(), before)

    def test_database_failure_rolls_back_team_access(self):
        self.run_job([repo(1, "one")], DAY_1, teams=self.TEAMS)
        before = self.team_access()
        original = self.repository.replace_team_access

        def replace_then_fail(*args):
            original(*args)
            self.session.flush()
            raise RuntimeError("database went away")

        self.repository.replace_team_access = replace_then_fail
        with self.assertRaises(RuntimeError):
            self.run_job([repo(1, "one")], DAY_2, teams=[team("ops-team", {1: "read"})])
        self.assertEqual(self.team_access(), before)
        self.assertEqual([r[0] for r in self.runs()], ["success", "failed"])

    def test_overview_matches_teams_by_github_id(self):
        from app.projects.repository_stats.services.visibility_ownership import (
            OwnershipRepository,
        )

        self.run_job(
            [repo(1, "one"), repo(2, "two", "private", archived=True)],
            DAY_1,
            teams=self.TEAMS,
        )
        # Renamed on GitHub: still matched, because matching is by id.
        self.run_job(
            [repo(1, "one-renamed"), repo(2, "two", "private", archived=True)],
            DAY_2,
            teams=self.TEAMS,
        )

        class Ownership(OwnershipRepository):
            def business_units_by_repository(self):
                return {}

        service = VisibilityService(
            self.repository,
            Ownership(self.session),
            "23 October 2026",
            today=date(2026, 9, 25),
        )
        unknown = service.get_overview_page().overview.organisations[0].children[0]
        self.assertEqual(
            [(t.name, t.totals.total, t.totals.private) for t in unknown.children],
            [("Platform team", 2, 1), ("service-team", 1, 0)],
        )


class TestRecordOrganisationNames(RecordRepositoryVisibilityTestCase):
    orgs = (OrgInstallation(MOJ, 1), OrgInstallation(MAS, 2))

    def names(self):
        return {
            row.login: row.display_name
            for row in self.session.query(RepositoryStatsOrganisation)
        }

    def test_records_display_names(self):
        self.run_job(
            {MOJ: [repo(1, "one")], MAS: [repo(5, "five")]},
            DAY_1,
            display_names={MOJ: "Example Justice", MAS: "  "},
        )
        self.assertEqual(self.names(), {MOJ: "Example Justice", MAS: None})
        self.assertEqual(
            self.repository.find_organisation_display_names(), {MOJ: "Example Justice"}
        )
        self.assertIn(f"/orgs/{MOJ}", self.github.calls)

    def test_a_later_run_updates_the_name(self):
        self.run_job({MOJ: [repo(1, "one")]}, DAY_1, display_names={MOJ: "Old name"})
        self.run_job({MOJ: [repo(1, "one")]}, DAY_2, display_names={MOJ: "New name"})
        self.assertEqual(self.names(), {MOJ: "New name", MAS: None})

    def test_failure_keeps_the_previous_name_and_still_records_the_snapshot(self):
        self.run_job({MOJ: [repo(1, "one")]}, DAY_1, display_names={MOJ: "Old name"})
        with self.assertLogs(
            "app.projects.repository_stats.jobs.record_repository_visibility", "ERROR"
        ) as logs:
            self.run_job(
                {MOJ: [repo(1, "one")]},
                DAY_2,
                display_names={MOJ: "New name"},
                failing_profile_orgs={MOJ},
            )
        self.assertIn("Couldn't fetch the display name for", "\n".join(logs.output))
        self.assertEqual(self.names(), {MOJ: "Old name", MAS: None})
        self.assertIn((1, DAY_2.date().isoformat()), self.snapshots())
        self.assertEqual(self.runs()[-1][0], "success")

    def test_overview_shows_display_name_and_keeps_login_keys(self):
        self.run_job(
            {MOJ: [repo(1, "one")], MAS: [repo(5, "five")]},
            DAY_1,
            display_names={MOJ: "Example Justice"},
        )
        service = VisibilityService(
            self.repository, FakeOwnership(), "", today=date(2026, 9, 25)
        )
        organisations = service.get_overview_page().overview.organisations
        self.assertEqual(
            [(o.name, o.key) for o in organisations],
            [("Example Justice", MOJ), (MAS, MAS)],
        )


class FakeOwnership:
    def business_unit_names(self):
        return []

    def business_units_by_repository(self):
        return {}

    def teams_by_repository(self):
        from app.projects.repository_stats.services.overview_logic import (
            RepositoryTeams,
        )

        return RepositoryTeams()


class TestPagesReadJobData(RecordRepositoryVisibilityTestCase):
    """Job-written rows work with the existing page service, ownership included."""

    def test_partial_run_keeps_freshness_and_progress_per_org(self):
        from app.projects.repository_stats.services.visibility_logic import (
            parse_visibility_query,
        )

        orgs = [OrgInstallation(MOJ, 1), OrgInstallation(MAS, 2)]
        baseline = {
            MOJ: [repo(1, "one", archived=True)],
            MAS: [repo(5, "five", archived=True)],
        }
        self.run_job(baseline, DAY_1, orgs)
        with self.assertRaises(GitHubInventoryError):
            self.run_job(
                {
                    MOJ: [repo(1, "one", "internal", archived=True)],
                    MAS: [repo(5, "five", archived=True)],
                },
                DAY_2,
                orgs,
                failing_orgs={MAS},
            )
        service = VisibilityService(
            self.repository, FakeOwnership(), today=DAY_2.date()
        )
        overview = service.get_overview_page()
        self.assertEqual(
            [(org.key, org.totals.total) for org in overview.overview.organisations],
            [(MOJ, 1), (MAS, 1)],
        )
        self.assertEqual(overview.last_updated, ("25 September 2026", "5:04am"))
        self.assertEqual(
            overview.failed_organisation_updates, {MAS: "24 September 2026"}
        )
        for org, updated, made_internal in (
            (MOJ, ("25 September 2026", "5:04am"), 1),
            (MAS, ("24 September 2026", "5:04am"), 0),
        ):
            with self.subTest(org=org):
                query = parse_visibility_query({"org": org})
                changes = service.get_changes_page(query)
                archived = service.get_archived_page(query)
                self.assertEqual(changes.last_updated, updated)
                self.assertEqual(archived.last_updated, updated)
                self.assertEqual(changes.earliest_captured_on, DAY_1.date())
                self.assertEqual(archived.earliest_captured_on, DAY_1.date())
                self.assertEqual(archived.archived.progress.total, 1)
                self.assertEqual(
                    archived.archived.progress.made_internal, made_internal
                )
        all_progress = service.get_archived_page(
            parse_visibility_query({"org": "all"})
        ).archived.progress
        self.assertEqual((all_progress.total, all_progress.made_internal), (2, 1))

        self.run_job(
            {
                MOJ: [repo(1, "one", "internal", archived=True)],
                MAS: [repo(5, "five", archived=True)],
            },
            DAY_2_PM,
            orgs,
        )
        self.assertEqual(service.get_overview_page().failed_organisation_updates, {})

    def test_dev_history_import_preserves_per_org_baselines_in_prod(self):
        from app.projects.repository_stats.services.visibility_logic import (
            parse_visibility_query,
        )

        moj_baseline = datetime(2026, 8, 17, 4, tzinfo=UTC)
        mas_baseline = datetime(2026, 10, 29, 4, tzinfo=UTC)
        later = datetime(2026, 10, 30, 4, tzinfo=UTC)
        self.run_job([repo(1, "moj-archived", archived=True)], moj_baseline)
        self.run_job(
            {
                MAS: [
                    repo(5, "mas-archived", archived=True),
                    repo(6, "mas-private", "private"),
                ]
            },
            mas_baseline,
            orgs=(OrgInstallation(MAS, 2),),
        )
        self.run_job([repo(1, "moj-archived", "internal", archived=True)], later)
        self.assertEqual(
            self.repository.find_snapshot_dates_by_organisation(),
            {MOJ: [moj_baseline.date(), later.date()], MAS: [mas_baseline.date()]},
        )
        self.assertEqual([e[0] for e in self.events()], [1])

        imported_engine = create_engine("sqlite://")
        self.addCleanup(imported_engine.dispose)
        RepositoryStatsVisibilitySnapshot.metadata.create_all(
            imported_engine,
            tables=[
                RepositoryStatsVisibilitySnapshot.__table__,
                RepositoryStatsVisibilityEvent.__table__,
                RepositoryStatsJobRun.__table__,
                RepositoryStatsOrganisation.__table__,
            ],
        )
        imported_session = Session(imported_engine)
        self.addCleanup(imported_session.close)
        snapshots = self.repository.find_snapshots_on_dates(
            self.repository.find_snapshot_dates()
        )
        imported_session.add_all(
            RepositoryStatsVisibilitySnapshot(**asdict(snapshot))
            for rows in snapshots.values()
            for snapshot in rows
        )
        imported_session.add_all(
            RepositoryStatsVisibilityEvent(**asdict(event))
            for event in self.repository.find_events_between(
                moj_baseline.date(), later.date()
            )
        )
        imported_session.commit()

        pages = {}
        for environment, repository, today in (
            ("dev", self.repository, later.date()),
            ("prod", VisibilityRepository(imported_session), date(2026, 11, 15)),
        ):
            service = VisibilityService(repository, FakeOwnership(), today=today)
            for org, baseline, latest, total, made_internal in (
                (MOJ, moj_baseline.date(), later.date(), 1, 1),
                (MAS, mas_baseline.date(), mas_baseline.date(), 2, 0),
            ):
                with self.subTest(environment=environment, org=org):
                    query = parse_visibility_query({"org": org})
                    page = service.get_changes_page(query)
                    self.assertEqual(page.earliest_captured_on, baseline)
                    self.assertEqual(page.latest_captured_on, latest)
                    self.assertEqual(page.date_range.from_date, baseline)
                    self.assertEqual(page.date_range.to_date, latest)
                    self.assertEqual(page.counts.total, total)
                    archived = service.get_archived_page(query).archived
                    self.assertEqual(archived.progress.total, 1)
                    self.assertEqual(archived.progress.made_internal, made_internal)
                    self.assertEqual(
                        [r.name for r in archived.repositories],
                        ["mas-archived"] if org == MAS else [],
                    )
                    pages[environment, org] = (
                        page.date_range,
                        page.counts,
                        page.changes,
                        archived,
                    )
            all_progress = service.get_archived_page(
                parse_visibility_query({"org": "all"})
            ).archived.progress
            self.assertEqual((all_progress.total, all_progress.made_internal), (2, 1))
        for org in (MOJ, MAS):
            self.assertEqual(pages["dev", org], pages["prod", org])

    def test_changes_and_archived_pages(self):
        from app.projects.repository_stats.services.visibility_logic import (
            NO_BUSINESS_UNIT,
            parse_visibility_query,
        )

        self.run_job([repo(1, "one"), repo(2, "two", archived=True)], DAY_1)
        self.run_job(
            [
                repo(1, "one", "internal"),
                repo(2, "two", archived=True),
                repo(3, "three"),
            ],
            DAY_2_PM,
        )
        service = VisibilityService(
            self.repository, FakeOwnership(), "23 October 2026", today=date(2026, 9, 25)
        )

        changes = service.get_changes_page(parse_visibility_query({}))
        self.assertEqual(changes.last_updated, ("25 September 2026", "2:04pm"))
        items = changes.changes.activity_page.items
        self.assertEqual(
            sorted((i.name, i.by, i.business_unit_text) for i in items),
            [
                ("one", "Not known", NO_BUSINESS_UNIT),
                ("three", "Not known", NO_BUSINESS_UNIT),
            ],
        )

        archived = service.get_archived_page(parse_visibility_query({}))
        self.assertEqual([r.name for r in archived.archived.repositories], ["two"])
        self.assertEqual(archived.last_updated, ("25 September 2026", "2:04pm"))


class TestTransferredRepositoryHistory(RecordRepositoryVisibilityTestCase):
    orgs = (OrgInstallation(MOJ, 1), OrgInstallation(MAS, 2))
    day_3 = DAY_2 + timedelta(days=1)

    def assert_reports(self, today, expected_counts, expected_archived):
        from app.projects.repository_stats.services.visibility_logic import (
            parse_visibility_query,
        )

        service = VisibilityService(self.repository, FakeOwnership(), today=today)
        overview = service.get_overview_page().overview.organisations
        self.assertEqual(
            {org.key: org.totals.total for org in overview},
            {MOJ: expected_counts[MOJ], MAS: expected_counts[MAS]},
        )
        for org in (MOJ, MAS, "all"):
            with self.subTest(org=org):
                query = parse_visibility_query({"org": org}, only_public_values=["0"])
                changes = service.get_changes_page(query)
                archived_page = service.get_archived_page(query)
                archived = archived_page.archived
                self.assertEqual(changes.counts.total, expected_counts[org])
                self.assertEqual(archived_page.counts.total, expected_counts[org])
                self.assertEqual(
                    [repository.github_id for repository in archived.repositories],
                    expected_archived[org],
                )
                self.assertEqual(archived.progress.total, len(expected_archived[org]))
                self.assertEqual(
                    archived.progress.made_internal, len(expected_archived[org])
                )
                self.assertEqual(
                    [repository.github_id for repository in archived.tracked],
                    expected_archived["all"],
                )

    def baseline(self):
        self.run_job(
            {
                MOJ: [repo(1, "moj-keep", "private")],
                MAS: [
                    repo(5, "mas-archived", archived=True),
                    repo(6, "mas-keep", "internal"),
                ],
            },
            DAY_1,
        )

    def scan_with_failed_mas(self, moj_repositories, at):
        with self.assertRaises(GitHubInventoryError):
            self.run_job(
                {MOJ: moj_repositories},
                at,
                failing_orgs={MAS},
            )

    def test_transfer_then_deletion_does_not_restore_stale_copy(self):
        self.baseline()
        self.scan_with_failed_mas(
            [
                repo(1, "moj-keep", "private"),
                repo(5, "transferred", "internal", archived=True),
            ],
            DAY_2,
        )
        self.scan_with_failed_mas([repo(1, "moj-keep", "private")], self.day_3)
        self.assert_reports(
            self.day_3.date(),
            {MOJ: 1, MAS: 1, "all": 2},
            {MOJ: [], MAS: [], "all": []},
        )

        restored_on = self.day_3 + timedelta(days=1)
        self.scan_with_failed_mas(
            [
                repo(1, "moj-keep", "private"),
                repo(5, "transferred", "internal", archived=True),
            ],
            restored_on,
        )
        self.assert_reports(
            restored_on.date(),
            {MOJ: 2, MAS: 1, "all": 3},
            {MOJ: [5], MAS: [], "all": [5]},
        )

    def test_transfer_and_deletion_on_same_day_do_not_restore_stale_copy(self):
        self.baseline()
        self.scan_with_failed_mas(
            [
                repo(1, "moj-keep", "private"),
                repo(5, "transferred", "internal", archived=True),
            ],
            DAY_2,
        )
        self.scan_with_failed_mas([repo(1, "moj-keep", "private")], DAY_2_PM)
        self.assertNotIn((5, DAY_2.date().isoformat()), self.snapshots())
        self.assert_reports(
            DAY_2.date(),
            {MOJ: 1, MAS: 1, "all": 2},
            {MOJ: [], MAS: [], "all": []},
        )

    def assert_first_baseline_then_deletion(self, deleted_at):
        self.run_job(
            {
                MAS: [
                    repo(5, "mas-archived", archived=True),
                    repo(6, "mas-keep", "internal"),
                ]
            },
            DAY_1,
            orgs=(OrgInstallation(MAS, 2),),
        )
        moj_only = (OrgInstallation(MOJ, 1),)
        self.run_job(
            {
                MOJ: [
                    repo(1, "moj-keep", "private"),
                    repo(5, "transferred", "internal", archived=True),
                ]
            },
            DAY_2,
            orgs=moj_only,
        )
        self.assertFalse(
            self.session.query(RepositoryStatsVisibilityEvent)
            .filter_by(github_id=5, org=MOJ, event_type="created")
            .first()
        )
        self.run_job(
            {MOJ: [repo(1, "moj-keep", "private")]},
            deleted_at,
            orgs=moj_only,
        )
        self.assert_reports(
            deleted_at.date(),
            {MOJ: 1, MAS: 1, "all": 2},
            {MOJ: [], MAS: [], "all": []},
        )

    def test_transfer_at_first_baseline_then_deletion(self):
        self.assert_first_baseline_then_deletion(self.day_3)

    def test_transfer_at_first_baseline_then_same_day_deletion(self):
        self.assert_first_baseline_then_deletion(DAY_2_PM)

    def test_delayed_removal_from_old_org_does_not_hide_current_owner(self):
        self.baseline()
        self.scan_with_failed_mas(
            [
                repo(1, "moj-keep", "private"),
                repo(5, "transferred", "internal", archived=True),
            ],
            DAY_2,
        )
        with self.assertRaises(GitHubInventoryError):
            self.run_job(
                {MAS: [repo(6, "mas-keep", "internal")]},
                self.day_3,
                failing_orgs={MOJ},
            )
        self.assert_reports(
            self.day_3.date(),
            {MOJ: 2, MAS: 1, "all": 3},
            {MOJ: [5], MAS: [], "all": [5]},
        )

    def test_same_day_removal_from_old_org_keeps_current_owner(self):
        self.baseline()
        self.run_job(
            {
                MOJ: [
                    repo(1, "moj-keep", "private"),
                    repo(5, "transferred", "internal", archived=True),
                ],
                MAS: [repo(6, "mas-keep", "internal")],
            },
            DAY_2,
        )
        self.assert_reports(
            DAY_2.date(),
            {MOJ: 2, MAS: 1, "all": 3},
            {MOJ: [5], MAS: [], "all": [5]},
        )


if __name__ == "__main__":
    unittest.main()
