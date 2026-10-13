# ruff: noqa: DTZ001 - naive datetimes here are UTC, as stored by the database
"""Diffing a new repository scan against the previous snapshot."""

import unittest
from datetime import date, datetime

from app.projects.repository_stats.services.github_inventory import RepositoryRecord
from app.projects.repository_stats.services.visibility_logic import VisibilitySnapshot
from app.projects.repository_stats.services.visibility_scan import diff_scan

ORG = "ministryofjustice"
OCCURRED_ON = date(2026, 9, 25)


def snapshot(github_id, name, visibility, archived=False):
    return VisibilitySnapshot(
        github_id=github_id,
        org=ORG,
        name=name,
        visibility=visibility,
        archived=archived,
        captured_on=date(2026, 9, 1),
    )


def record(github_id, name, visibility="public", archived=False):
    return RepositoryRecord(
        github_id=github_id,
        org=ORG,
        name=name,
        visibility=visibility,
        archived=archived,
        fork=False,
        created_at=datetime(2020, 1, 2, 3, 4, 5),
        pushed_at=datetime(2026, 8, 1, 10),
    )


class TestDiffScan(unittest.TestCase):
    def test_no_previous_snapshot_means_no_events(self):
        self.assertEqual(diff_scan([], [record(1, "alpha")], OCCURRED_ON), [])

    def test_changed_created_and_deleted(self):
        previous = [snapshot(1, "alpha", "public"), snapshot(2, "gone", "public")]
        current = [record(1, "alpha", "internal"), record(3, "fresh", "public")]
        events = diff_scan(previous, current, OCCURRED_ON)
        self.assertEqual(
            [(e.name, e.event_type) for e in events],
            [("alpha", "changed"), ("fresh", "created"), ("gone", "deleted")],
        )

    def test_newly_created_and_already_archived_both_get_events(self):
        """A repo that's brand new to the scan (no previous snapshot) but already
        archived must not lose its "archived" event: it feeds the archived-public
        cohort, same as the one-off import does."""
        current = [
            record(1, "alpha", "public"),
            record(5, "fresh", "public", archived=True),
        ]
        events = diff_scan([snapshot(1, "alpha", "public")], current, OCCURRED_ON)
        self.assertEqual(
            [(e.name, e.event_type, e.occurred_on) for e in events],
            [
                ("fresh", "created", OCCURRED_ON),
                ("fresh", "archived", OCCURRED_ON),
            ],
        )

    def test_newly_created_not_archived_gets_only_a_created_event(self):
        current = [
            record(1, "alpha", "public"),
            record(5, "fresh", "public", archived=False),
        ]
        events = diff_scan([snapshot(1, "alpha", "public")], current, OCCURRED_ON)
        self.assertEqual(
            [(e.name, e.event_type) for e in events], [("fresh", "created")]
        )


if __name__ == "__main__":
    unittest.main()
