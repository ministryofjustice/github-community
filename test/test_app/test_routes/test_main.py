import unittest
from types import SimpleNamespace

from app.projects.repository_standards.services.repository_compliance_service import (
    RepositoryComplianceService,
)


class TestAggregateOwnerCounts(unittest.TestCase):
    def test_aggregates_counts_by_owner_and_maturity(self):
        service = RepositoryComplianceService(asset_service=SimpleNamespace())
        entities = [
            SimpleNamespace(id="team-a", name="Team A", type=SimpleNamespace(name="TEAM")),
            SimpleNamespace(id="team-b", name="Team B", type=SimpleNamespace(name="TEAM")),
            SimpleNamespace(id="team-c", name="Team C", type=SimpleNamespace(name="TEAM")),
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

        service.get_all_repositories = lambda: repositories

        result = service.aggregate_owner_counts(entities)

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
        service = RepositoryComplianceService(asset_service=SimpleNamespace())
        entities = [
            SimpleNamespace(
                id="bu-a",
                name="Business Unit A",
                type=SimpleNamespace(name="BUSINESS_UNIT"),
            )
        ]
        repositories = [
            SimpleNamespace(
                maturity_level=3,
                authoritative_business_unit_owners=["Business Unit A"],
            )
        ]

        service.get_all_repositories = lambda: repositories

        result = service.aggregate_owner_counts(entities)

        self.assertEqual(
            result["bu-a"],
            {
                "repo_count": 1,
                "baseline_compliant_count": 1,
                "standard_compliant_count": 1,
                "exemplar_compliant_count": 1,
            },
        )
