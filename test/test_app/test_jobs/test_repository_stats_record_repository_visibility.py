# ruff: noqa: DTZ001 - naive datetimes here are UTC, as stored by the database
import unittest
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
    def __init__(self, body, status_code=200):
        self.body = body
        self.status_code = status_code
        self.links = {}
        self.headers = {}

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
    ):
        self.repositories_by_org = repositories_by_org
        self.failing_orgs = set(failing_orgs)
        self.teams_by_org = teams_by_org or {}
        self.failing_team_orgs = set(failing_team_orgs)
        self.display_names = display_names or {}
        self.failing_profile_orgs = set(failing_profile_orgs)
        # {path: how many times it times out before answering}
        self.slow_paths = {}
        self.calls = []

    def client_for(self, installation_id):
        org = {1: MOJ, 2: MAS}[installation_id]
        github = self

        class Client:
            def get(self, path):
                github.calls.append(path)
                if github.slow_paths.get(path):
                    github.slow_paths[path] -= 1
                    raise requests.ReadTimeout("Read timed out. (read timeout=10)")
                teams = github.teams_by_org.get(org, [])
                if path == f"/orgs/{org}":
                    if org in github.failing_profile_orgs:
                        return Response({"message": "Server Error"}, 500)
                    return Response(
                        {"login": org, "name": github.display_names.get(org)}
                    )
                if path == f"/orgs/{org}/repos?type=all&per_page=100":
                    if org in github.failing_orgs:
                        return Response({"message": "Server Error"}, 500)
                    return Response(github.repositories_by_org.get(org, []))
                if path == f"/orgs/{org}/teams?per_page=100":
                    if org in github.failing_team_orgs:
                        return Response({"message": "Forbidden"}, 403)
                    return Response(
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
                        return Response(
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
    ):
        github = FakeGitHub(
            repositories if isinstance(repositories, dict) else {MOJ: repositories},
            failing_orgs,
            teams if teams is None or isinstance(teams, dict) else {MOJ: teams},
            failing_team_orgs,
            display_names,
            failing_profile_orgs,
        )
        github.slow_paths.update(slow_paths or {})
        self.github = github
        times = iter([at, at + timedelta(minutes=4)])
        return record_repository_visibility(
            self.repository,
            orgs or self.orgs,
            github.client_for,
            now=lambda: next(times),
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
            for r in self.session.query(RepositoryStatsJobRun).order_by(
                RepositoryStatsJobRun.id
            )
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

    def test_github_failure_writes_nothing(self):
        self.run_job([repo(1, "one")], DAY_1)
        before = (self.snapshots(), self.events())
        orgs = [OrgInstallation(MOJ, 1), OrgInstallation(MAS, 2)]
        with self.assertRaises(GitHubInventoryError):
            self.run_job(
                {MOJ: [repo(1, "one", "internal"), repo(2, "new")]},
                DAY_2,
                orgs,
                failing_orgs={MAS},
            )
        self.assertEqual((self.snapshots(), self.events()), before)
        self.assertEqual([r[0] for r in self.runs()], ["success", "failed"])

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
        with self.assertRaisesRegex(GitHubInventoryError, "no repositories"):
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
        self.assertIn(
            "Recorded 1 repositories, 0 events and 3 team access rows for "
            "ministryofjustice (5 GitHub API calls)",
            "\n".join(logs.output),
        )

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


if __name__ == "__main__":
    unittest.main()
