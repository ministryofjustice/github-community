import unittest
from datetime import UTC, datetime

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.projects.repository_stats.db_models import RepositoryStatsTeamAccess
from app.projects.repository_stats.services.overview_logic import Team
from app.projects.repository_stats.services.visibility_ownership import (
    OwnershipRepository,
    authoritative_business_units,
    teams_from_asset_data,
)


class TestAuthoritativeBusinessUnits(unittest.TestCase):
    def test_admin_business_unit_wins(self):
        rows = [
            ("repo", "HMPPS", "BUSINESS_UNIT", "ADMIN_ACCESS"),
            ("repo", "LAA", "BUSINESS_UNIT", "OTHER"),
        ]
        self.assertEqual(authoritative_business_units(rows), {"repo": ["HMPPS"]})

    def test_any_access_counts_when_there_are_no_admins(self):
        rows = [
            ("repo", "LAA", "BUSINESS_UNIT", "OTHER"),
            ("repo", "OPG", "BUSINESS_UNIT", None),
        ]
        self.assertEqual(authoritative_business_units(rows), {"repo": ["LAA", "OPG"]})

    def test_team_admin_blocks_non_admin_business_units(self):
        rows = [
            ("repo", "team-a", "TEAM", "ADMIN_ACCESS"),
            ("repo", "LAA", "BUSINESS_UNIT", "OTHER"),
        ]
        self.assertEqual(authoritative_business_units(rows), {"repo": []})

    def test_teams_are_not_business_units_and_duplicates_collapse(self):
        rows = [
            ("repo", "team-a", "TEAM", "OTHER"),
            ("repo", "HMPPS", "BUSINESS_UNIT", "ADMIN_ACCESS"),
            ("repo", "HMPPS", "BUSINESS_UNIT", "ADMIN_ACCESS"),
        ]
        self.assertEqual(authoritative_business_units(rows), {"repo": ["HMPPS"]})


class TestOwnershipRepository(unittest.TestCase):
    """Runs the read-only queries against the shared ownership tables in SQLite."""

    def setUp(self):
        engine = create_engine("sqlite://")
        RepositoryStatsTeamAccess.metadata.create_all(
            engine, tables=[RepositoryStatsTeamAccess.__table__]
        )
        self.session = Session(engine)
        self.addCleanup(self.session.close)
        for statement in (
            "CREATE TABLE owner_types (id INTEGER PRIMARY KEY, name TEXT)",
            "CREATE TABLE owners (id INTEGER PRIMARY KEY, name TEXT, type_id INTEGER, config TEXT)",
            "CREATE TABLE assets (id INTEGER PRIMARY KEY, name TEXT, type TEXT, data TEXT)",
            "CREATE TABLE relationships (id INTEGER PRIMARY KEY, type TEXT, assets_id INTEGER, owners_id INTEGER)",
            "INSERT INTO owner_types VALUES (1, 'BUSINESS_UNIT'), (2, 'TEAM')",
            (
                "INSERT INTO owners VALUES"
                ' (1, \'HMPPS\', 1, \'{"name": "HMPPS", "teams": ["prisons-devs"], "prefix": "prisons-"}\'),'
                ' (2, \'LAA\', 1, \'{"name": "LAA", "teams": ["Legal Aid Team"], "prefix": ""}\'),'
                " (3, 'OPG', 1, NULL),"
                ' (4, \'team-a\', 2, \'{"name": "team-a", "teams": ["service-team"], "prefix": ""}\')'
            ),
            (
                "INSERT INTO assets VALUES"
                ' (1, \'repo-admin\', \'REPOSITORY\', \'{"access": {"teams_with_admin": ["platform-team"], "teams_with_admin_parents": ["parent-team"], "teams": ["platform-team", "service-team"]}}\'),'
                " (2, 'repo-other', 'REPOSITORY', '{\"access\": {\"teams_with_admin\": [], \"teams\": []}}'),"
                " (3, 'repo-none', 'REPOSITORY', '{}')"
            ),
            "INSERT INTO relationships VALUES (1, 'ADMIN_ACCESS', 1, 1), (2, 'OTHER', 1, 2), (3, 'OTHER', 2, 3), (4, 'OTHER', 2, 4)",
        ):
            self.session.execute(text(statement))

    def test_business_unit_names(self):
        self.assertEqual(
            OwnershipRepository(self.session).business_unit_names(),
            ["HMPPS", "LAA", "OPG"],
        )

    def add_team_access(self, *rows):
        self.session.add_all(
            RepositoryStatsTeamAccess(
                org="example-org",
                github_id=github_id,
                team_slug=slug,
                team_name=name,
                parent_team_slug=parent,
                permission=permission,
                recorded_at=datetime(2026, 10, 2, 4, 0, tzinfo=UTC),
            )
            for github_id, slug, name, parent, permission in rows
        )
        self.session.flush()

    def test_business_units_by_repository(self):
        units = OwnershipRepository(self.session).business_units_by_repository()
        self.assertEqual(
            units.by_name, {"repo-admin": ["HMPPS"], "repo-other": ["OPG"]}
        )
        self.assertEqual(units.for_repository(1, "repo-admin"), ("HMPPS",))
        self.assertEqual(units.for_repository(1, "repo-none"), ())

    def test_business_units_from_team_access_and_prefix(self):
        self.add_team_access(
            # Matched by slug, with admin access.
            (10, "prisons-devs", "Prisons developers", None, "admin"),
            # Matched by display name, case ignored.
            (11, "laa-team", "legal aid team", None, "write"),
            # Matched through the parent team.
            (12, "child-team", "Child team", "prisons-devs", "read"),
            # TEAM owners are not business units.
            (13, "service-team", "Service team", None, "admin"),
            # The shared relationships win where they give a business unit.
            (14, "laa-team", "legal aid team", None, "admin"),
        )
        units = OwnershipRepository(self.session).business_units_by_repository()
        self.assertEqual(units.for_repository(10, "internal-one"), ("HMPPS",))
        self.assertEqual(units.for_repository(11, "private-two"), ("LAA",))
        self.assertEqual(units.for_repository(12, "archived-three"), ("HMPPS",))
        self.assertEqual(units.for_repository(13, "other"), ())
        self.assertEqual(units.for_repository(14, "repo-other"), ("OPG",))
        # Name prefix, with no team access recorded.
        self.assertEqual(units.for_repository(99, "prisons-api"), ("HMPPS",))

    def test_teams_fall_back_to_assets_when_the_stats_table_is_empty(self):
        teams = OwnershipRepository(self.session).teams_by_repository()
        self.assertEqual(teams.by_github_id, {})
        self.assertEqual(
            teams.by_name,
            {
                "repo-admin": [
                    Team("platform-team", "platform-team"),
                    Team("service-team", "service-team"),
                ]
            },
        )
        self.assertEqual(
            list(teams.for_repository(99, "repo-admin")),
            [
                Team("platform-team", "platform-team"),
                Team("service-team", "service-team"),
            ],
        )

    def test_teams_come_from_the_stats_table_by_github_id(self):
        recorded_at = datetime(2026, 10, 2, 4, 0, tzinfo=UTC)
        self.session.add_all(
            RepositoryStatsTeamAccess(
                org="example-org",
                github_id=github_id,
                team_slug=slug,
                team_name=name,
                permission="write",
                recorded_at=recorded_at,
            )
            for github_id, slug, name in (
                (7, "ops-team", "Operations team"),
                (7, "data-team", "Data team"),
                (8, "ops-team", "Operations team"),
            )
        )
        self.session.flush()
        teams = OwnershipRepository(self.session).teams_by_repository()
        self.assertEqual(teams.by_name, {})
        self.assertEqual(
            teams.by_github_id,
            {
                7: [
                    Team("ops-team", "Operations team"),
                    Team("data-team", "Data team"),
                ],
                8: [Team("ops-team", "Operations team")],
            },
        )
        # Matched by id only: the name of a repository with asset teams doesn't count.
        self.assertEqual(list(teams.for_repository(1, "repo-admin")), [])


class TestTeamsFromAssetData(unittest.TestCase):
    def test_dict_and_json_text(self):
        data = {
            "access": {"teams_with_admin": ["a-team"], "teams": ["b-team", "a-team"]}
        }
        self.assertEqual(teams_from_asset_data(data), ["a-team", "b-team"])
        self.assertEqual(
            teams_from_asset_data('{"access": {"teams": ["b-team"]}}'), ["b-team"]
        )

    def test_missing_or_malformed_data(self):
        for data in (None, "", "not json", {}, {"access": None}, {"access": {}}, []):
            self.assertEqual(teams_from_asset_data(data), [])
        self.assertEqual(
            teams_from_asset_data({"access": {"teams": [None, "", "c-team"]}}),
            ["c-team"],
        )


if __name__ == "__main__":
    unittest.main()
