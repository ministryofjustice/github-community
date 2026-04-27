import unittest
from types import SimpleNamespace

from app.projects.repository_standards.routes.main import aggregate_owner_counts


class TestAggregateOwnerCounts(unittest.TestCase):
    def test_aggregates_counts_by_owner_and_maturity(self):
        entities = [
            SimpleNamespace(id="team-a", name="Team A"),
            SimpleNamespace(id="team-b", name="Team B"),
            SimpleNamespace(id="team-c", name="Team C"),
        ]

        repositories = [
            SimpleNamespace(
                maturity_level=1,
                authoritative_team_owners=["Team A", "Team B"],
            ),
            SimpleNamespace(
                maturity_level=2,
                authoritative_team_owners=["Team A", "Team A"],
            ),
            SimpleNamespace(
                maturity_level=3,
                authoritative_team_owners=["Team B", "Unknown Team"],
            ),
            SimpleNamespace(
                maturity_level=0,
                authoritative_team_owners=["Team A"],
            ),
        ]

        result = aggregate_owner_counts(
            entities,
            repositories,
            "authoritative_team_owners",
        )

        self.assertEqual(
            result["team-a"],
            {
                "repo_count": 3,
                "baseline_compliant_count": 2,
                "standard_compliant_count": 1,
                "exemplar_compliant_count": 0,
            },
        )
        self.assertEqual(
            result["team-b"],
            {
                "repo_count": 2,
                "baseline_compliant_count": 2,
                "standard_compliant_count": 1,
                "exemplar_compliant_count": 1,
            },
        )
        self.assertEqual(
            result["team-c"],
            {
                "repo_count": 0,
                "baseline_compliant_count": 0,
                "standard_compliant_count": 0,
                "exemplar_compliant_count": 0,
            },
        )

    def test_supports_different_owner_field_names(self):
        entities = [SimpleNamespace(id="bu-a", name="Business Unit A")]
        repositories = [
            SimpleNamespace(
                maturity_level=3,
                authoritative_business_unit_owners=["Business Unit A"],
            )
        ]

        result = aggregate_owner_counts(
            entities,
            repositories,
            "authoritative_business_unit_owners",
        )

        self.assertEqual(
            result["bu-a"],
            {
                "repo_count": 1,
                "baseline_compliant_count": 1,
                "standard_compliant_count": 1,
                "exemplar_compliant_count": 1,
            },
        )
