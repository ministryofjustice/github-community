import unittest

from sqlalchemy import BigInteger, Boolean, Date, DateTime, String, UniqueConstraint

from app.projects.repository_stats.db_models import (
    RepositoryStatsOrganisation,
    RepositoryStatsTeamAccess,
    RepositoryStatsVisibilityEvent,
    RepositoryStatsVisibilitySnapshot,
)


class TestRepositoryStatsVisibilitySnapshotModel(unittest.TestCase):
    table = RepositoryStatsVisibilitySnapshot.__table__

    def test_table_name(self):
        self.assertEqual(self.table.name, "repository_stats_visibility_snapshots")

    def test_columns(self):
        columns = self.table.columns
        expected = {
            "github_id": (BigInteger, False),
            "org": (String, False),
            "name": (String, False),
            "visibility": (String, False),
            "archived": (Boolean, False),
            "fork": (Boolean, False),
            "created_at": (DateTime, True),
            "pushed_at": (DateTime, True),
            "captured_on": (Date, False),
        }
        self.assertEqual(set(columns.keys()), {"id", *expected})
        self.assertTrue(columns["id"].primary_key)
        for name, (column_type, nullable) in expected.items():
            with self.subTest(column=name):
                self.assertIsInstance(columns[name].type, column_type)
                self.assertEqual(columns[name].nullable, nullable)

    def test_unique_github_id_per_captured_on(self):
        unique_columns = [
            tuple(column.name for column in constraint.columns)
            for constraint in self.table.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        self.assertIn(("github_id", "captured_on"), unique_columns)

    def test_captured_on_index(self):
        indexed = [tuple(c.name for c in index.columns) for index in self.table.indexes]
        self.assertIn(("captured_on",), indexed)


class TestRepositoryStatsVisibilityEventModel(unittest.TestCase):
    table = RepositoryStatsVisibilityEvent.__table__

    def test_table_name(self):
        self.assertEqual(self.table.name, "repository_stats_visibility_events")

    def test_columns(self):
        columns = self.table.columns
        expected = {
            "github_id": (BigInteger, False),
            "org": (String, False),
            "name": (String, False),
            "event_type": (String, False),
            "from_visibility": (String, True),
            "to_visibility": (String, True),
            "occurred_on": (Date, False),
            "actor": (String, True),
            "source": (String, False),
        }
        self.assertEqual(set(columns.keys()), {"id", *expected})
        self.assertTrue(columns["id"].primary_key)
        for name, (column_type, nullable) in expected.items():
            with self.subTest(column=name):
                self.assertIsInstance(columns[name].type, column_type)
                self.assertEqual(columns[name].nullable, nullable)

    def test_indexes(self):
        indexed = {tuple(c.name for c in index.columns) for index in self.table.indexes}
        self.assertTrue({("occurred_on",), ("event_type",), ("name",)} <= indexed)


class TestRepositoryStatsTeamAccessModel(unittest.TestCase):
    table = RepositoryStatsTeamAccess.__table__

    def test_columns(self):
        self.assertEqual(self.table.name, "repository_stats_team_access")
        expected = {
            "org": (String, False),
            "github_id": (BigInteger, False),
            "team_slug": (String, False),
            "team_name": (String, False),
            "parent_team_slug": (String, True),
            "permission": (String, False),
            "recorded_at": (DateTime, False),
        }
        self.assertEqual(set(self.table.columns.keys()), {"id", *expected})
        for name, (type_, nullable) in expected.items():
            self.assertIsInstance(self.table.columns[name].type, type_, name)
            self.assertEqual(self.table.columns[name].nullable, nullable, name)

    def test_one_row_per_org_repository_and_team(self):
        unique = [
            tuple(c.name for c in constraint.columns)
            for constraint in self.table.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        self.assertEqual(unique, [("org", "github_id", "team_slug")])


class TestRepositoryStatsOrganisationModel(unittest.TestCase):
    table = RepositoryStatsOrganisation.__table__

    def test_columns(self):
        self.assertEqual(self.table.name, "repository_stats_organisations")
        self.assertEqual(
            set(self.table.columns.keys()), {"login", "display_name", "updated_at"}
        )
        self.assertEqual([c.name for c in self.table.primary_key], ["login"])
        self.assertIsInstance(self.table.columns["login"].type, String)
        self.assertTrue(self.table.columns["display_name"].nullable)
        self.assertIsInstance(self.table.columns["updated_at"].type, DateTime)
        self.assertFalse(self.table.columns["updated_at"].nullable)


if __name__ == "__main__":
    unittest.main()
