import unittest
from datetime import date

from app.projects.repository_stats.services.business_units import (
    RepositoryBusinessUnits,
)
from app.projects.repository_stats.services.overview_logic import (
    NO_TEAM,
    UNKNOWN_BUSINESS_UNIT,
    RepositoryTeams,
    Team,
    build_overview,
    team_url,
)
from app.projects.repository_stats.services.visibility_logic import VisibilitySnapshot

DAY = date(2026, 10, 1)
SERVICE = Team("service-team", "Service team")


def snap(github_id, org, name, visibility, archived=False):
    return VisibilitySnapshot(github_id, org, name, visibility, archived, DAY)


def totals(row):
    t = row.totals
    return (t.total, t.public, t.internal, t.private)


class TestBuildOverview(unittest.TestCase):
    def test_counts_by_organisation_and_business_unit(self):
        overview = build_overview(
            [
                snap(1, "org-b", "repo-one", "public"),
                snap(2, "org-b", "repo-two", "internal", archived=True),
                snap(3, "org-b", "repo-three", "private"),
                snap(4, "org-a", "repo-four", "internal"),
            ],
            {"repo-one": ["Unit Z"], "repo-two": ["Unit A"], "repo-four": ["Unit A"]},
        )
        self.assertEqual(totals(overview.all_organisations), (4, 1, 2, 1))
        self.assertEqual([o.name for o in overview.organisations], ["org-a", "org-b"])
        org_b = overview.organisations[1]
        self.assertEqual(totals(org_b), (3, 1, 1, 1))
        self.assertEqual(
            [(bu.name, totals(bu)) for bu in org_b.children],
            [
                ("Unit A", (1, 0, 1, 0)),
                ("Unit Z", (1, 1, 0, 0)),
                (UNKNOWN_BUSINESS_UNIT, (1, 0, 0, 1)),
            ],
        )
        self.assertEqual(org_b.children[0].key, "org-b/Unit A")
        self.assertEqual(org_b.key, "org-b")

    def test_repository_with_several_business_units_counts_under_each(self):
        overview = build_overview(
            [snap(1, "org-a", "repo-one", "public")],
            {"repo-one": ["Unit A", "Unit B", "Unit A"]},
        )
        org = overview.organisations[0]
        self.assertEqual(totals(org), (1, 1, 0, 0))
        self.assertEqual(
            [(bu.name, totals(bu)) for bu in org.children],
            [("Unit A", (1, 1, 0, 0)), ("Unit B", (1, 1, 0, 0))],
        )

    def test_teams_within_business_units(self):
        overview = build_overview(
            [
                snap(1, "org-a", "repo-one", "public"),
                snap(2, "org-a", "repo-two", "internal"),
                snap(3, "org-a", "repo-three", "private"),
                snap(4, "org-a", "repo-four", "internal"),
                snap(5, "org-b", "repo-five", "public"),
            ],
            {
                "repo-one": ["Unit A"],
                "repo-two": ["Unit A"],
                "repo-three": ["Unit A", "Unit B"],
                "repo-five": ["Unit A"],
            },
            RepositoryTeams(
                by_github_id={
                    1: [SERVICE, Team("platform-team", "Platform-Team")],
                    2: [SERVICE, SERVICE],
                    3: [SERVICE],
                    4: [Team("ops-team", "ops-team")],
                    5: [SERVICE],
                }
            ),
        )
        org_a, org_b = overview.organisations
        unit_a, unit_b, unknown = org_a.children
        self.assertEqual(
            [(t.name, totals(t), t.url) for t in unit_a.children],
            [
                (
                    "Platform-Team",
                    (1, 1, 0, 0),
                    "https://github.com/orgs/org-a/teams/platform-team",
                ),
                (
                    "Service team",
                    (3, 1, 1, 1),
                    "https://github.com/orgs/org-a/teams/service-team",
                ),
            ],
        )
        self.assertEqual(
            [(t.name, totals(t)) for t in unit_b.children],
            [("Service team", (1, 0, 0, 1))],
        )
        self.assertEqual(
            [(t.name, totals(t)) for t in unknown.children],
            [("ops-team", (1, 0, 1, 0))],
        )
        # Team links use the repository's own organisation.
        self.assertEqual(
            org_b.children[0].children[0].url,
            "https://github.com/orgs/org-b/teams/service-team",
        )
        self.assertTrue(all(t.key is None for t in unit_a.children))

    def test_repositories_without_teams_count_under_no_team_last(self):
        overview = build_overview(
            [
                snap(1, "org-a", "repo-one", "public"),
                snap(2, "org-a", "repo-two", "internal"),
            ],
            {"repo-one": ["Unit A"], "repo-two": ["Unit A"]},
            RepositoryTeams(by_name={"repo-two": [Team("zeta-team", "zeta-team")]}),
        )
        teams = overview.organisations[0].children[0].children
        self.assertEqual(
            [(t.name, totals(t), t.url) for t in teams],
            [
                ("zeta-team", (1, 0, 1, 0), team_url("org-a", "zeta-team")),
                (NO_TEAM, (1, 1, 0, 0), None),
            ],
        )

    def test_github_id_match_ignores_names(self):
        overview = build_overview(
            [
                snap(1, "org-a", "repo-one", "public"),
                snap(2, "org-a", "repo-two", "public"),
            ],
            {},
            RepositoryTeams(by_github_id={2: [SERVICE]}),
        )
        teams = overview.organisations[0].children[0].children
        self.assertEqual(
            [(t.name, totals(t)) for t in teams],
            [("Service team", (1, 1, 0, 0)), (NO_TEAM, (1, 1, 0, 0))],
        )

    def test_team_url_is_quoted(self):
        self.assertEqual(
            team_url("org a", "team/b"),
            "https://github.com/orgs/org%20a/teams/team%2Fb",
        )

    def test_unexpected_visibility_counts_in_total_only(self):
        overview = build_overview([snap(1, "org-a", "repo-one", "unknown")], {})
        self.assertEqual(totals(overview.all_organisations), (1, 0, 0, 0))

    def test_organisation_display_names(self):
        overview = build_overview(
            [
                snap(1, "org-b", "repo-one", "public"),
                snap(2, "org-a", "repo-two", "public"),
            ],
            {},
            organisation_names={"org-b": "Alpha Example", "org-a": ""},
        )
        self.assertEqual(
            [(o.name, o.key) for o in overview.organisations],
            [("Alpha Example", "org-b"), ("org-a", "org-a")],
        )

    def test_business_units_from_team_access(self):
        source = RepositoryBusinessUnits(
            by_name={"repo-one": ["Unit A"]},
            admin_by_github_id={1: ["Unit B"], 2: ["Unit B"]},
            other_by_github_id={3: ["Unit C"]},
        )
        overview = build_overview(
            [
                snap(1, "org-a", "repo-one", "public"),
                snap(2, "org-a", "repo-two", "private"),
                snap(3, "org-a", "repo-three", "internal", archived=True),
                snap(4, "org-a", "repo-four", "internal"),
            ],
            source,
        )
        units = {u.name: totals(u) for u in overview.organisations[0].children}
        self.assertEqual(
            units,
            {
                "Unit A": (1, 1, 0, 0),
                "Unit B": (1, 0, 0, 1),
                "Unit C": (1, 0, 1, 0),
                "Unknown": (1, 0, 1, 0),
            },
        )

    def test_no_snapshots(self):
        overview = build_overview([], {})
        self.assertEqual(totals(overview.all_organisations), (0, 0, 0, 0))
        self.assertEqual(overview.organisations, [])


if __name__ == "__main__":
    unittest.main()
