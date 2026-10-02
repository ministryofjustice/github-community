# ruff: noqa: DTZ001 - naive datetimes here are UTC, as stored by the database
"""The audit report import's parsing and diffing. Every spreadsheet here is made up and
built in a temporary directory; no real report or repository name is used."""

import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook

from app.projects.repository_stats.services.audit_import import (
    AuditImportError,
    build_plan,
    event_counts,
    full_name_key,
    read_baseline,
    read_comparison,
    read_directory,
    synthetic_github_id,
)
from app.projects.repository_stats.services.github_inventory import RepositoryRecord

ORG = "example-org"
BASELINE_HEADERS = [
    "org",
    "repo",
    "full_name",
    "visibility",
    "archived",
    "fork",
    "created_at",
    "last_pushed_at",
    "some_compliance_column",
]


def write_workbook(path, sheets):
    """sheets: {title: [header row, *rows]}"""
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, rows in sheets.items():
        sheet = workbook.create_sheet(title)
        for row in rows:
            sheet.append(row)
    workbook.save(path)


def write_baseline(directory, repos, name="list_repos_17aug2026.xlsx", org=ORG):
    """repos: (name, visibility[, archived[, fork[, created_at, pushed_at]]])"""
    rows = [BASELINE_HEADERS]
    for repo in repos:
        name_, visibility, archived, fork, created, pushed = (
            *repo,
            *(False, False, "2020-01-02T03:04:05Z", "2026-08-01T10:00:00Z")[
                len(repo) - 2 :
            ],
        )
        rows.append(
            [
                org,
                name_,
                f"{org}/{name_}",
                visibility,
                archived,
                fork,
                created,
                pushed,
                "x",
            ]
        )
    write_workbook(Path(directory) / name, {"Repos": rows, "Summary": [["total"], [1]]})


def write_daily(directory, captured_on, repos, archived_column=False, org=ORG):
    """repos: (name, visibility[, archived]). Uses the daily 'Visibility-' layout."""
    day = captured_on.isoformat()
    headers = [
        "repo",
        "visibility_baseline_2026-08-17",
        f"visibility_current_{day}",
        "changed",
        "last_checked",
    ]
    if archived_column:
        headers.append("archived")
    rows = [headers]
    for repo in repos:
        row = [f"{org}/{repo[0]}", "new repo since Aug_17", repo[1], "No", day]
        if archived_column:
            row.append(repo[2] if len(repo) > 2 else False)
        rows.append(row)
    write_workbook(
        Path(directory) / f"Visibility-{day}.xlsx",
        {"Changed Repos": [["repo"]], "Full Comparison": rows},
    )


def write_historical(directory, captured_on, repos, org=ORG):
    rows = [["repo", "visibility_aug17", "visibility_aug24", "changed", "change_type"]]
    rows += [[f"{org}/{n}", "public", v, "No", ""] for n, v in repos]
    write_workbook(
        Path(directory) / f"historical-{captured_on.isoformat()}.xlsx",
        {"Changed Repos": [["repo"]], "Full Comparison": rows},
    )


def record(github_id, name, visibility="public", created_at=None, archived=False):
    return RepositoryRecord(
        github_id=github_id,
        org=ORG,
        name=name,
        visibility=visibility,
        archived=archived,
        fork=False,
        created_at=created_at or datetime(2020, 1, 2, 3, 4, 5),
        pushed_at=datetime(2026, 9, 1, 10),
    )


def inventory(*records):
    return {full_name_key(r.org, r.name): r for r in records}


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)


class TestParsing(TempDirTestCase):
    def test_baseline(self):
        write_baseline(
            self.dir, [("alpha", "Public", True, True), ("beta", "internal")]
        )
        result = read_baseline(self.dir / "list_repos_17aug2026.xlsx")
        self.assertEqual(result.captured_on, date(2026, 8, 17))
        alpha, beta = result.rows
        self.assertEqual(
            (alpha.org, alpha.name, alpha.visibility, alpha.archived, alpha.fork),
            (ORG, "alpha", "public", True, True),
        )
        self.assertEqual(alpha.created_at, datetime(2020, 1, 2, 3, 4, 5))
        self.assertEqual(alpha.pushed_at, datetime(2026, 8, 1, 10))
        self.assertEqual((beta.visibility, beta.archived), ("internal", False))

    def test_baseline_tolerates_header_case_and_spaces(self):
        rows = [
            [" Org ", "REPO", "Visibility", "Archived"],
            [ORG, "alpha", "private", "TRUE"],
        ]
        write_workbook(self.dir / "base.xlsx", {" repos ": rows})
        (row,) = read_baseline(self.dir / "base.xlsx").rows
        self.assertEqual(
            (row.name, row.visibility, row.archived), ("alpha", "private", True)
        )
        self.assertIsNone(row.fork)

    def test_baseline_missing_column_or_sheet(self):
        write_workbook(self.dir / "a.xlsx", {"Repos": [["org", "repo"], [ORG, "x"]]})
        write_workbook(self.dir / "b.xlsx", {"Other": [["org"]]})
        for name in ("a.xlsx", "b.xlsx"):
            with self.subTest(name=name), self.assertRaises(AuditImportError):
                read_baseline(self.dir / name)

    def test_daily_file(self):
        write_daily(self.dir, date(2026, 9, 18), [("alpha", "internal", True)], True)
        result = read_comparison(
            self.dir / "Visibility-2026-09-18.xlsx", date(2026, 9, 18)
        )
        (row,) = result.rows
        self.assertEqual(
            (row.org, row.name, row.visibility, row.archived),
            (ORG, "alpha", "internal", True),
        )

    def test_daily_file_with_a_different_baseline_header(self):
        rows = [
            [
                "repo",
                "visibility_baseline_2026-09-17 21:57:48 UTC",
                "visibility_current_2026-09-20",
            ],
            [f"{ORG}/alpha", "public", "private"],
        ]
        write_workbook(self.dir / "f.xlsx", {"Full Comparison": rows})
        (row,) = read_comparison(self.dir / "f.xlsx", date(2026, 9, 20)).rows
        self.assertEqual(row.visibility, "private")
        self.assertIsNone(row.archived)

    def test_historical_file(self):
        write_historical(self.dir, date(2026, 8, 24), [("alpha", "internal")])
        path = self.dir / "historical-2026-08-24.xlsx"
        (row,) = read_comparison(path, date(2026, 8, 24)).rows
        self.assertEqual(row.visibility, "internal")

    def test_current_column_must_match_the_file_date(self):
        write_daily(self.dir, date(2026, 9, 18), [("alpha", "public")])
        with self.assertRaises(AuditImportError):
            read_comparison(self.dir / "Visibility-2026-09-18.xlsx", date(2026, 9, 19))

    def test_bad_values(self):
        cases = {
            "bad_visibility": [["repo", "visibility_current"], [f"{ORG}/a", "secret"]],
            "no_slash": [["repo", "visibility_current"], ["a", "public"]],
        }
        for name, rows in cases.items():
            write_workbook(self.dir / f"{name}.xlsx", {"Full Comparison": rows})
            with self.subTest(name=name), self.assertRaises(AuditImportError):
                read_comparison(self.dir / f"{name}.xlsx", date(2026, 9, 18))

    def test_directory_orders_files_and_ignores_others(self):
        write_baseline(self.dir, [("alpha", "public")])
        write_daily(self.dir, date(2026, 9, 20), [("alpha", "public")])
        write_daily(self.dir, date(2026, 9, 18), [("alpha", "public")])
        write_historical(self.dir, date(2026, 8, 24), [("alpha", "public")])
        write_baseline(self.dir, [("alpha", "public")], name="baseline (1).xlsx")
        (self.dir / "notes.txt").write_text("ignore me")
        files, ignored = read_directory(self.dir)
        self.assertEqual(
            [f.captured_on for f in files],
            [
                date(2026, 8, 17),
                date(2026, 8, 24),
                date(2026, 9, 18),
                date(2026, 9, 20),
            ],
        )
        self.assertEqual(sorted(ignored), ["baseline (1).xlsx", "notes.txt"])

    def test_directory_errors(self):
        with self.assertRaises(AuditImportError):
            read_directory(self.dir)  # no baseline
        write_baseline(self.dir, [("alpha", "public")])
        write_daily(self.dir, date(2026, 9, 18), [("alpha", "public")])
        write_historical(self.dir, date(2026, 9, 18), [("alpha", "public")])
        with self.assertRaises(AuditImportError):
            read_directory(self.dir)  # two files for one date


class TestBuildPlan(TempDirTestCase):
    def plan(self, known=()):
        files, _ = read_directory(self.dir)
        return build_plan(ORG, files, inventory(*known))

    def events(self, plan):
        return [
            (
                e.name,
                e.event_type,
                e.from_visibility,
                e.to_visibility,
                e.occurred_on,
                e.source,
            )
            for e in plan.events
        ]

    def test_baseline_has_no_events(self):
        write_baseline(self.dir, [("alpha", "public"), ("beta", "internal")])
        plan = self.plan()
        self.assertEqual(plan.events, [])
        self.assertEqual(list(plan.snapshots), [date(2026, 8, 17)])
        self.assertEqual(len(plan.snapshots[date(2026, 8, 17)]), 2)

    def test_change_new_and_deleted(self):
        write_baseline(self.dir, [("alpha", "public"), ("gone", "public")])
        write_daily(
            self.dir, date(2026, 9, 20), [("alpha", "internal"), ("fresh", "public")]
        )
        sep_20 = date(2026, 9, 20)
        self.assertEqual(
            self.events(self.plan()),
            [
                ("alpha", "changed", "public", "internal", sep_20, "import"),
                ("fresh", "created", None, "public", sep_20, "import"),
                ("gone", "deleted", "public", None, sep_20, "import"),
            ],
        )

    def test_events_in_the_gap_are_dated_to_the_first_file_after_it(self):
        write_baseline(self.dir, [("alpha", "public"), ("beta", "public")])
        write_historical(
            self.dir, date(2026, 8, 24), [("alpha", "public"), ("beta", "public")]
        )
        write_daily(
            self.dir, date(2026, 9, 18), [("alpha", "internal"), ("beta", "public")]
        )
        write_daily(
            self.dir, date(2026, 9, 20), [("alpha", "internal"), ("beta", "private")]
        )
        self.assertEqual(
            [(n, t, on) for n, t, _, _, on, _ in self.events(self.plan())],
            [
                ("alpha", "changed", date(2026, 9, 18)),
                ("beta", "changed", date(2026, 9, 20)),
            ],
        )

    def test_created_uses_the_real_creation_date_when_it_fits(self):
        write_baseline(self.dir, [("alpha", "public")])
        write_historical(self.dir, date(2026, 8, 24), [("alpha", "public")])
        write_daily(
            self.dir,
            date(2026, 9, 18),
            [("alpha", "public"), ("fresh", "internal"), ("odd", "public")],
        )
        plan = self.plan(
            [
                record(1, "alpha"),
                # 23:30 UTC on 1 Sep is 2 Sep in London (BST)
                record(2, "fresh", "internal", datetime(2026, 9, 1, 23, 30)),
                # Created before the previous file (e.g. made visible to the app later)
                record(3, "odd", created_at=datetime(2026, 8, 1)),
            ]
        )
        self.assertEqual(
            [(e.name, e.occurred_on) for e in plan.events if e.event_type == "created"],
            [("fresh", date(2026, 9, 2)), ("odd", date(2026, 9, 18))],
        )

    def test_github_ids_come_from_the_inventory_by_full_name(self):
        write_baseline(self.dir, [("Alpha", "public"), ("gone", "public")])
        plan = self.plan([record(101, "alpha")])
        ids = {r.name: r.github_id for r in plan.snapshots[date(2026, 8, 17)]}
        self.assertEqual(ids["Alpha"], 101)
        self.assertEqual(ids["gone"], synthetic_github_id(ORG, "gone"))
        self.assertLess(ids["gone"], 0)
        self.assertEqual(plan.unresolved_ids, 1)

    def test_synthetic_ids_are_stable_and_case_insensitive(self):
        self.assertEqual(
            synthetic_github_id(ORG, "Gone"), synthetic_github_id(ORG, "gone")
        )
        self.assertNotEqual(
            synthetic_github_id(ORG, "a"), synthetic_github_id(ORG, "b")
        )

    def test_values_a_file_lacks_are_carried_forward(self):
        write_baseline(self.dir, [("alpha", "public", True, True)])
        write_daily(self.dir, date(2026, 9, 18), [("alpha", "public")])
        (alpha,) = self.plan().snapshots[date(2026, 9, 18)]
        self.assertEqual((alpha.archived, alpha.fork), (True, True))
        self.assertEqual(alpha.pushed_at, datetime(2026, 8, 1, 10))

    def test_newly_archived_when_the_file_says_so(self):
        write_baseline(self.dir, [("alpha", "public")])
        write_daily(self.dir, date(2026, 9, 18), [("alpha", "public", True)], True)
        self.assertEqual(
            [(n, t) for n, t, *_ in self.events(self.plan())], [("alpha", "archived")]
        )

    def test_newly_created_and_already_archived_both_get_events(self):
        write_baseline(self.dir, [("alpha", "public")])
        write_daily(
            self.dir,
            date(2026, 9, 18),
            [("alpha", "public"), ("fresh", "public", True)],
            True,
        )
        fresh_events = [
            (t, on)
            for n, t, *_rest, on, _src in self.events(self.plan())
            if n == "fresh"
        ]
        self.assertEqual(
            fresh_events,
            [("created", date(2026, 9, 18)), ("archived", date(2026, 9, 18))],
        )

    def test_pushed_at_old_none_falls_through_to_known_not_masked_forever(self):
        """A snapshot can legitimately carry pushed_at=None (GitHub's real value was later
        than that snapshot, see _not_after). A later file must still be able to pick up
        the real value from the inventory instead of being stuck with that old None."""
        write_workbook(
            self.dir / "list_repos_17aug2026.xlsx",
            {
                "Repos": [
                    BASELINE_HEADERS,
                    [
                        ORG,
                        "alpha",
                        f"{ORG}/alpha",
                        "public",
                        False,
                        False,
                        "2020-01-02T03:04:05Z",
                        "",
                        "x",
                    ],
                ],
                "Summary": [["total"], [1]],
            },
        )
        write_daily(self.dir, date(2026, 9, 27), [("alpha", "public")])
        known = RepositoryRecord(
            github_id=1,
            org=ORG,
            name="alpha",
            visibility="public",
            archived=False,
            fork=False,
            created_at=datetime(2020, 1, 2, 3, 4, 5),
            pushed_at=datetime(2026, 9, 25, 10, 0, 0),
        )
        plan = self.plan([known])
        baseline_alpha = plan.snapshots[date(2026, 8, 17)][0]
        self.assertIsNone(baseline_alpha.pushed_at)  # too recent for that snapshot

        daily_alpha = plan.snapshots[date(2026, 9, 27)][0]
        self.assertEqual(daily_alpha.pushed_at, datetime(2026, 9, 25, 10, 0, 0))

    def test_new_repositorys_later_push_is_not_put_on_an_older_snapshot(self):
        write_baseline(self.dir, [("alpha", "public")])
        write_daily(
            self.dir, date(2026, 8, 30), [("alpha", "public"), ("fresh", "public")]
        )
        plan = self.plan([record(2, "fresh", created_at=datetime(2026, 8, 20))])
        fresh = next(r for r in plan.snapshots[date(2026, 8, 30)] if r.name == "fresh")
        self.assertIsNone(fresh.pushed_at)  # GitHub's pushed_at is 1 September

    def test_duplicate_rows_fail(self):
        write_baseline(self.dir, [("alpha", "public"), ("ALPHA", "public")])
        with self.assertRaises(AuditImportError):
            self.plan()

    def test_event_counts(self):
        write_baseline(self.dir, [("alpha", "public"), ("gone", "public")])
        write_daily(
            self.dir, date(2026, 9, 20), [("alpha", "internal"), ("fresh", "public")]
        )
        self.assertEqual(
            event_counts(self.plan().events),
            {"changed": 1, "created": 1, "deleted": 1, "archived": 0},
        )


if __name__ == "__main__":
    unittest.main()
