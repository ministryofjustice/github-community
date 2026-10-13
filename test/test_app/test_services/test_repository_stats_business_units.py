import unittest

from app.projects.repository_stats.services.business_units import (
    BusinessUnitConfig,
    RepositoryBusinessUnits,
    TeamAccessRow,
    business_units_for,
    derive_business_units,
    parse_business_unit_config,
)

CONFIGS = (
    BusinessUnitConfig("Unit A", ("team-a",), "unit-a-"),
    BusinessUnitConfig("Unit B", ("Team B Display",)),
    BusinessUnitConfig("Unit C", ("parent-team",)),
)


def row(github_id, slug, permission="write", name=None, parent=None, org="org-a"):
    return TeamAccessRow(org, github_id, slug, name or slug, parent, permission)


class TestDeriveBusinessUnits(unittest.TestCase):
    def test_admin_and_other_access(self):
        admin, other = derive_business_units(
            CONFIGS, [row(1, "team-a", "admin"), row(2, "team-a", "read")]
        )
        self.assertEqual(admin, {1: ["Unit A"]})
        self.assertEqual(other, {2: ["Unit A"]})

    def test_matches_slug_or_display_name_ignoring_case(self):
        admin, other = derive_business_units(
            CONFIGS,
            [
                row(1, "TEAM-A", "admin"),
                row(2, "team-b", "write", name="team b display"),
                row(3, "unrelated", "admin", name="Unrelated"),
            ],
        )
        self.assertEqual(admin, {1: ["Unit A"]})
        self.assertEqual(other, {2: ["Unit B"]})

    def test_follows_parent_teams(self):
        admin, other = derive_business_units(
            CONFIGS,
            [
                row(1, "grandchild", "admin", parent="child"),
                row(2, "child", "read", parent="parent-team"),
                row(3, "parent-team", "read"),
            ],
        )
        self.assertEqual(admin, {1: ["Unit C"]})
        self.assertEqual(other, {2: ["Unit C"], 3: ["Unit C"]})

    def test_parents_are_per_organisation_and_cycles_stop(self):
        admin, other = derive_business_units(
            CONFIGS,
            [
                # The parent's display name is only known in another organisation.
                row(1, "child", "admin", parent="team-b", org="org-b"),
                row(2, "team-b", "read", name="Team B Display", org="org-a"),
                row(3, "loop-a", "admin", parent="loop-b"),
                row(4, "loop-b", "admin", parent="loop-a"),
            ],
        )
        self.assertEqual(admin, {})
        self.assertEqual(other, {2: ["Unit B"]})

    def test_recorded_parent_slug_matches_without_its_own_row(self):
        admin, _ = derive_business_units(
            CONFIGS, [row(1, "child", "admin", parent="parent-team")]
        )
        self.assertEqual(admin, {1: ["Unit C"]})


class TestRepositoryBusinessUnits(unittest.TestCase):
    source = RepositoryBusinessUnits(
        by_name={"named-repo": ["Shared Unit"], "empty-repo": []},
        admin_by_github_id={1: ["Unit A"], 3: ["Unit B"]},
        other_by_github_id={1: ["Unit C"], 2: ["Unit C"]},
        configs=CONFIGS,
    )

    def test_shared_relationships_win(self):
        self.assertEqual(self.source.for_repository(1, "named-repo"), ("Shared Unit",))

    def test_admin_wins_over_other_and_prefix(self):
        self.assertEqual(self.source.for_repository(1, "unit-a-repo"), ("Unit A",))
        self.assertEqual(self.source.for_repository(3, "empty-repo"), ("Unit B",))

    def test_other_access_and_prefix(self):
        self.assertEqual(
            self.source.for_repository(2, "unit-a-repo"), ("Unit C", "Unit A")
        )
        self.assertEqual(self.source.for_repository(9, "unit-a-api"), ("Unit A",))
        self.assertEqual(self.source.for_repository(9, "other"), ())

    def test_plain_mapping(self):
        self.assertEqual(
            business_units_for({"repo": ["Unit A", "Unit A"]}, 1, "repo"), ("Unit A",)
        )
        self.assertEqual(business_units_for({}, 1, "repo"), ())
        self.assertEqual(business_units_for(self.source, 2, "other"), ("Unit C",))


class TestParseBusinessUnitConfig(unittest.TestCase):
    def test_parses_teams_and_prefix(self):
        self.assertEqual(
            parse_business_unit_config(
                "Unit A", {"teams": ["team-a", "", 3], "prefix": "unit-a-"}
            ),
            BusinessUnitConfig("Unit A", ("team-a",), "unit-a-"),
        )

    def test_missing_or_invalid(self):
        for config in (None, "x", {}, {"teams": "team-a", "prefix": None}):
            with self.subTest(config=config):
                self.assertEqual(
                    parse_business_unit_config("Unit", config),
                    BusinessUnitConfig("Unit"),
                )


if __name__ == "__main__":
    unittest.main()
