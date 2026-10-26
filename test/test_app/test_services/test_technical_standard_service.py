import unittest
from types import SimpleNamespace

from app.projects.repository_standards.services.technical_standard_service import (
    TechnicalStandardService,
)
from app.projects.repository_standards.models.owner import OwnerConfig


def make_owner(owner_id, name, owner_type, organisation="ministryofjustice"):
    return SimpleNamespace(
        id=owner_id,
        name=name,
        type=SimpleNamespace(name=owner_type),
        config={"organisation": organisation},
    )


def make_report(
    name, compliant, business_units=None, teams=None,
    organisation="ministryofjustice",
):
    return SimpleNamespace(
        name=name,
        compliant=compliant,
        authoritative_business_unit_owners=business_units or [],
        authoritative_team_owners=teams or [],
        organisation=organisation,
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
        def get_all_repositories(organisation=None, visibility=None):
            return [
                repository
                for repository in self.repositories
                if organisation is None
                or repository.organisation == organisation
            ]

        self.service.get_all_repositories = get_all_repositories

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

    def test_owner_counts_distinguish_same_name_across_organisations(self):
        owners = [
            make_owner(1, "Platform Team", "TEAM", "ministryofjustice"),
            make_owner(2, "Platform Team", "TEAM", "moj-analytical-services"),
        ]
        self.repositories.extend(
            [
                make_report(
                    "mojas-repo", False, teams=["Platform Team"],
                    organisation="moj-analytical-services",
                ),
            ]
        )

        counts = self.service.get_owner_counts(owners)

        self.assertEqual(
            counts,
            {
                1: {"repo_count": 2, "compliant_count": 1},
                2: {"repo_count": 1, "compliant_count": 0},
            },
        )

    def test_returns_repositories_for_owner_type(self):
        owner = SimpleNamespace(id=1, name="HMPPS", type="BUSINESS_UNIT")
        owner.config = OwnerConfig(name="HMPPS", teams=[], prefix="")

        repositories = self.service.get_repositories_for_owner(owner)

        self.assertEqual([repo.name for repo in repositories], ["repo-one", "repo-two"])

    def test_owner_detail_only_returns_repositories_from_configured_organisation(self):
        owner = SimpleNamespace(
            id=1,
            name="Platform Team",
            type="TEAM",
            config=OwnerConfig(
                name="Platform Team", teams=[], prefix="",
                organisation="ministryofjustice",
            ),
        )
        self.repositories.extend(
            [
                make_report(
                    "mojas-repo", True, teams=["Platform Team"],
                    organisation="moj-analytical-services",
                ),
            ]
        )

        repositories = self.service.get_repositories_for_owner(owner)

        self.assertEqual([repo.name for repo in repositories], ["repo-one", "repo-two"])

    def test_returns_repositories_without_authoritative_owner(self):
        repositories = self.service.get_unowned_repositories()

        self.assertEqual([repo.name for repo in repositories], ["repo-four"])