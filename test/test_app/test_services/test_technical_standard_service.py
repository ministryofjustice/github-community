import unittest
from types import SimpleNamespace

from app.projects.repository_standards.services.technical_standard_service import (
    TechnicalStandardService,
)


def make_owner(owner_id, name, owner_type):
    return SimpleNamespace(
        id=owner_id,
        name=name,
        type=SimpleNamespace(name=owner_type),
    )


def make_report(name, compliant, business_units=None, teams=None):
    return SimpleNamespace(
        name=name,
        compliant=compliant,
        authoritative_business_unit_owners=business_units or [],
        authoritative_team_owners=teams or [],
    )


class TestTechnicalStandardServiceReports(unittest.TestCase):
    def setUp(self):
        self.service = TechnicalStandardService(asset_service=SimpleNamespace())
        self.repositories = [
            make_report(
                "repo-one",
                True,
                business_units=["HMPPS"],
                teams=["Platform Team"],
            ),
            make_report(
                "repo-two",
                False,
                business_units=["HMPPS"],
                teams=["Platform Team"],
            ),
            make_report("repo-three", True, teams=["Other Team"]),
            make_report("repo-four", False),
        ]
        self.service.get_all_repositories = (
            lambda organisation=None, visibility=None: self.repositories
        )

    def test_counts_business_unit_repositories_by_new_standard_compliance(self):
        owner = make_owner(1, "HMPPS", "BUSINESS_UNIT")

        counts = self.service.get_owner_counts([owner])

        self.assertEqual(
            counts,
            {1: {"repo_count": 2, "compliant_count": 1}},
        )

    def test_counts_team_repositories_by_new_standard_compliance(self):
        owner = make_owner(2, "Platform Team", "TEAM")

        counts = self.service.get_owner_counts([owner])

        self.assertEqual(
            counts,
            {2: {"repo_count": 2, "compliant_count": 1}},
        )

    def test_returns_repositories_for_owner_type(self):
        owner = SimpleNamespace(id=1, name="HMPPS", type="BUSINESS_UNIT")

        repositories = self.service.get_repositories_for_owner(owner)

        self.assertEqual([repo.name for repo in repositories], ["repo-one", "repo-two"])

    def test_returns_repositories_without_authoritative_owner(self):
        repositories = self.service.get_unowned_repositories()

        self.assertEqual([repo.name for repo in repositories], ["repo-four"])