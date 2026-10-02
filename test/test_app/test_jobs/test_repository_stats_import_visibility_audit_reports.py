"""The one-off audit report import. Spreadsheets are made up and built in a temporary
directory; GitHub is faked and never called."""

import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

from app.projects.repository_stats.db_models import (
    RepositoryStatsJobRun,
    RepositoryStatsVisibilitySnapshot,
)
from app.projects.repository_stats.jobs.import_visibility_audit_reports import (
    IMPORT_JOB_NAME,
    import_visibility_audit_reports,
    main,
)
from app.projects.repository_stats.services.audit_import import (
    AuditImportError,
    read_directory,
    synthetic_github_id,
)
from app.projects.repository_stats.services.github_inventory import GitHubInventoryError
from test.test_app.test_jobs.test_repository_stats_record_repository_visibility import (
    MOJ,
    FakeGitHub,
    RecordRepositoryVisibilityTestCase,
    repo,
)
from test.test_app.test_services.test_repository_stats_audit_import import (
    write_baseline,
    write_daily,
    write_historical,
)

AUG_17, AUG_24 = date(2026, 8, 17), date(2026, 8, 24)
SEP_18, SEP_20 = date(2026, 9, 18), date(2026, 9, 20)
IMPORTED_AT = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)


class ImportTestCase(RecordRepositoryVisibilityTestCase):
    def setUp(self):
        super().setUp()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        # GitHub today: alpha (id 1), beta (id 2) and fresh (id 3, created 19 Sep).
        self.github_repos = [
            repo(1, "alpha", "internal"),
            repo(2, "beta"),
            {**repo(3, "fresh"), "created_at": "2026-09-19T08:00:00Z"},
        ]
        self.write_reports()

    def write_reports(self):
        three = [("alpha", "public"), ("beta", "public"), ("gone", "public")]
        write_baseline(self.dir, three, org=MOJ)
        write_historical(self.dir, AUG_24, three, org=MOJ)
        write_daily(
            self.dir, SEP_18, [("alpha", "internal"), ("beta", "public")], org=MOJ
        )
        write_daily(
            self.dir,
            SEP_20,
            [("alpha", "internal"), ("beta", "public"), ("fresh", "public")],
            org=MOJ,
        )

    def run_import(self, dry_run=False, github=None):
        files, _ = read_directory(self.dir)
        github = github or FakeGitHub({MOJ: self.github_repos})
        return import_visibility_audit_reports(
            self.repository,
            files,
            self.orgs,
            github.client_for,
            dry_run=dry_run,
            now=lambda: IMPORTED_AT,
        )

    def imported_events(self):
        return [e[:6] for e in self.events() if e[7] == "import"]


class TestImport(ImportTestCase):
    def test_writes_snapshots_events_and_a_job_run(self):
        summary = self.run_import()
        self.assertEqual(
            sorted({k[1] for k in self.snapshots()}),
            ["2026-08-17", "2026-08-24", "2026-09-18", "2026-09-20"],
        )
        gone = synthetic_github_id(MOJ, "gone")
        self.assertEqual(
            self.snapshots(AUG_17),
            {
                (1, "2026-08-17"): ("alpha", "public", False),
                (2, "2026-08-17"): ("beta", "public", False),
                (gone, "2026-08-17"): ("gone", "public", False),
            },
        )
        self.assertEqual(
            self.imported_events(),
            [
                (1, "alpha", "changed", "public", "internal", "2026-09-18"),
                (gone, "gone", "deleted", "public", None, "2026-09-18"),
                (3, "fresh", "created", None, "public", "2026-09-19"),
            ],
        )
        self.assertTrue(all(e[6] is None for e in self.events()))  # actor not known
        self.assertEqual(self.runs(), [("success", IMPORT_JOB_NAME, None)])
        self.assertEqual(summary.orgs[0].unresolved_ids, 1)
        self.assertEqual(
            summary.orgs[0].events,
            {"changed": 1, "created": 1, "deleted": 1, "archived": 0},
        )
        # The page's "Last updated" line only reads the visibility job.
        self.assertIsNone(
            self.repository.find_last_successful_run_finished_at(
                "record_repository_visibility"
            )
        )
        self.assertTrue(self.repository.has_events_from_source("import"))

    def test_re_running_gives_the_same_data(self):
        self.run_import()
        snapshots, events = self.snapshots(), self.imported_events()
        self.run_import()
        self.assertEqual(self.snapshots(), snapshots)
        self.assertEqual(self.imported_events(), events)

    def test_re_running_with_more_files_replaces_the_earlier_import(self):
        self.run_import()
        write_daily(
            self.dir,
            date(2026, 9, 21),
            [("alpha", "private"), ("beta", "public"), ("fresh", "public")],
            org=MOJ,
        )
        self.run_import()
        changed = [e for e in self.imported_events() if e[2] == "changed"]
        self.assertEqual(
            [(e[1], e[4], e[5]) for e in changed],
            [("alpha", "internal", "2026-09-18"), ("alpha", "private", "2026-09-21")],
        )

    def test_dry_run_writes_nothing(self):
        summary = self.run_import(dry_run=True)
        self.assertTrue(summary.dry_run)
        self.assertEqual(summary.orgs[0].snapshot_rows[SEP_20], 3)
        self.assertEqual((self.snapshots(), self.events(), self.runs()), ({}, [], []))

    def test_github_failure_writes_nothing(self):
        self.run_import()
        before = (self.snapshots(), self.events(), self.runs())
        with self.assertRaises(GitHubInventoryError):
            self.run_import(github=FakeGitHub({}, failing_orgs=[MOJ]))
        self.assertEqual((self.snapshots(), self.events(), self.runs()), before)

    def test_database_failure_rolls_back_everything(self):
        self.run_import()
        before = (self.snapshots(), self.events(), self.runs())

        def fail(events):
            raise RuntimeError("database went away")

        with (
            patch.object(self.repository, "add_events", side_effect=fail),
            self.assertRaises(RuntimeError),
        ):
            self.run_import()
        self.assertEqual((self.snapshots(), self.events(), self.runs()), before)

    def test_org_without_an_installation_fails(self):
        write_daily(self.dir, SEP_20, [("x", "public")], org="other-org")
        with self.assertRaises(AuditImportError):
            self.run_import()
        self.assertEqual(self.snapshots(), {})


class TestImportAndScan(ImportTestCase):
    def scan(self, repositories, at):
        self.run_job(repositories, at)

    def test_a_later_scan_matches_imported_repositories(self):
        self.run_import()
        self.scan(self.github_repos, datetime(2026, 10, 3, 3, 0, tzinfo=UTC))
        oct_3 = self.snapshots(date(2026, 10, 3))
        self.assertEqual(sorted(k[0] for k in oct_3), [1, 2, 3])
        scan_events = [e for e in self.events() if e[7] == "scan"]
        self.assertEqual(scan_events, [])  # nothing changed, nothing duplicated

    def test_the_scan_records_a_repository_missed_by_the_import_once(self):
        self.run_import()
        self.scan(
            [*self.github_repos, repo(4, "newer")],
            datetime(2026, 10, 3, 3, 0, tzinfo=UTC),
        )
        self.assertEqual(
            [(e[1], e[2]) for e in self.events() if e[7] == "scan"],
            [("newer", "created")],
        )

    def test_files_on_or_after_the_first_scan_are_skipped(self):
        # The scan's first run (a baseline, so no events) is on 20 September.
        self.scan(
            [repo(1, "alpha", "private"), repo(2, "beta"), self.github_repos[2]],
            datetime(2026, 9, 20, 3, 0, tzinfo=UTC),
        )
        scan_snapshot = self.snapshots(SEP_20)
        summary = self.run_import()
        self.assertEqual(summary.skipped_dates, [SEP_20])
        self.assertEqual(summary.first_scan_date, SEP_20)
        self.assertEqual(self.snapshots(SEP_20), scan_snapshot)  # the scan's is kept
        self.assertEqual(
            sorted({k[1] for k in self.snapshots()}),
            ["2026-08-17", "2026-08-24", "2026-09-18", "2026-09-20"],
        )
        # The gap between the last imported file and the scan's baseline is bridged.
        self.assertEqual(
            [e[1:6] for e in self.imported_events() if e[5] >= "2026-09-19"],
            [
                ("fresh", "created", None, "public", "2026-09-19"),
                ("alpha", "changed", "internal", "private", "2026-09-20"),
            ],
        )
        # And re-running doesn't double the bridge.
        events = self.imported_events()
        self.run_import()
        self.assertEqual(self.imported_events(), events)

    def test_no_bridge_when_the_first_scan_already_wrote_events(self):
        self.scan(
            [repo(1, "alpha"), repo(2, "beta")], datetime(2026, 9, 19, 3, 0, tzinfo=UTC)
        )
        self.scan(
            [repo(1, "alpha", "private"), repo(2, "beta")],
            datetime(2026, 9, 20, 3, 0, tzinfo=UTC),
        )
        summary = self.run_import()
        self.assertEqual(summary.first_scan_date, date(2026, 9, 19))
        self.assertEqual(summary.skipped_dates, [SEP_20])
        self.assertEqual(
            [e[1:3] for e in self.events() if e[7] == "scan"], [("alpha", "changed")]
        )

    def test_scan_snapshots_of_other_dates_are_untouched(self):
        self.scan(self.github_repos, datetime(2026, 9, 25, 3, 0, tzinfo=UTC))
        scan_rows = self.session.query(RepositoryStatsVisibilitySnapshot).count()
        self.run_import()
        self.assertEqual(len(self.snapshots(date(2026, 9, 25))), scan_rows)


class TestMain(ImportTestCase):
    def test_cli_dry_run(self):
        with (
            patch(
                "app.projects.repository_stats.jobs.import_visibility_audit_reports.VisibilityRepository",
                return_value=self.repository,
            ),
            patch(
                "app.projects.repository_stats.jobs.import_visibility_audit_reports.GitHubAppClient",
                side_effect=lambda *_: FakeGitHub({MOJ: self.github_repos}).client_for(
                    1
                ),
            ),
            patch(
                "app.projects.repository_stats.jobs.import_visibility_audit_reports.configure_logging"
            ),
            patch(
                "app.projects.repository_stats.jobs.import_visibility_audit_reports.org_installations",
                return_value=self.orgs,
            ),
            self.assertLogs(
                "app.projects.repository_stats.jobs.import_visibility_audit_reports"
            ) as logs,
        ):
            main([str(self.dir), "--dry-run"])
        self.assertEqual((self.snapshots(), self.events()), ({}, []))
        output = "\n".join(logs.output)
        self.assertIn("Dry run, nothing written", output)
        self.assertIn("2026-09-20: 3 repositories", output)
        self.assertEqual(self.session.query(RepositoryStatsJobRun).count(), 0)
