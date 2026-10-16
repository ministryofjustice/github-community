import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.projects.repository_standards.models.technical_standard import (
    TechnicalStandardCheck,
)
from app.projects.repository_standards.repositories.asset_repository import (
    RepositoryView,
)
from app.projects.repository_standards.services.technical_standard_service import (
    TechnicalStandardService,
)

MODULE = "app.projects.repository_standards.services.technical_standard_service"


def _check(status):
    return TechnicalStandardCheck(1, "name", status, "desc", "/link")


def _repository():
    return SimpleNamespace(
        name="repo",
        business_unit_owners_names=[],
        team_owners_names=[],
        data=SimpleNamespace(basic=SimpleNamespace(description=None)),
    )


class TestTechnicalStandardService(unittest.TestCase):
    def setUp(self):
        asset_service = SimpleNamespace(
            get_repository_by_name=lambda name: _repository(),
            is_owner_authoritative_for_repository=lambda repo, owner: True,
        )
        self.service = TechnicalStandardService(asset_service)

    @patch(f"{MODULE}.get_all_technical_standard_checks")
    def test_compliant_when_no_checks_fail(self, mock_checks):
        mock_checks.return_value = [_check("pass"), _check("not_checked")]
        self.assertTrue(self.service.get_repository_by_name("repo").compliant)

    @patch(f"{MODULE}.get_all_technical_standard_checks")
    def test_not_compliant_when_any_check_fails(self, mock_checks):
        mock_checks.return_value = [_check("pass"), _check("fail")]
        self.assertFalse(self.service.get_repository_by_name("repo").compliant)

    @patch(f"{MODULE}.get_all_technical_standard_checks")
    def test_progress_counts_only_passed_checks(self, mock_checks):
        mock_checks.return_value = [_check("pass"), _check("not_checked"), _check("fail")]
        report = self.service.get_repository_by_name("repo")
        self.assertEqual(report.checks_passed, 1)
        self.assertAlmostEqual(report.compliance_percentage, 100 / 3)
        self.assertIsNone(report.last_updated)

    @patch(f"{MODULE}.get_all_technical_standard_checks")
    def test_progress_handles_empty_failed_and_complete_reports(self, mock_checks):
        for statuses, passed, percentage in (
            ([], 0, 0),
            (["fail"] * 9, 0, 0),
            (["pass"] * 9, 9, 100),
            (["pass"] * 8 + ["fail"], 8, 800 / 9),
        ):
            with self.subTest(statuses=statuses):
                mock_checks.return_value = [_check(status) for status in statuses]
                report = self.service.get_repository_by_name("repo")
                self.assertEqual(report.checks_passed, passed)
                self.assertAlmostEqual(report.compliance_percentage, percentage)

    def test_check_summaries_count_pass_fail_and_missing_results(self):
        first = SimpleNamespace(
            checks=[_check("pass"), _check("fail"), _check("pass")]
        )
        first.checks[0].number = 1
        first.checks[0].name = "Owner"
        first.checks[1].number = 2
        first.checks[1].name = "Reviews"
        first.checks[2].number = 3
        first.checks[2].name = "License"
        second = SimpleNamespace(
            checks=[_check("fail"), _check("pass")]
        )
        second.checks[0].number = 1
        second.checks[0].name = "Owner"
        second.checks[1].number = 2
        second.checks[1].name = "Reviews"

        summaries = self.service.get_check_summaries([first, second])

        self.assertEqual(
            summaries,
            [
                {
                    "number": 1,
                    "name": "Owner",
                    "link_to_guidance": "/link",
                    "pass_count": 1,
                    "fail_count": 1,
                    "not_checked_count": 0,
                    "pass_rate": 50,
                },
                {
                    "number": 2,
                    "name": "Reviews",
                    "link_to_guidance": "/link",
                    "pass_count": 1,
                    "fail_count": 1,
                    "not_checked_count": 0,
                    "pass_rate": 50,
                },
                {
                    "number": 3,
                    "name": "License",
                    "link_to_guidance": "/link",
                    "pass_count": 1,
                    "fail_count": 0,
                    "not_checked_count": 1,
                    "pass_rate": 50,
                },
            ],
        )

    @patch(f"{MODULE}.get_all_technical_standard_checks", return_value=[])
    def test_report_retains_repository_snapshot_timestamp(self, mock_checks):
        repository = _repository()
        repository.last_updated = datetime(2026, 10, 15, 3, 24)
        self.service = TechnicalStandardService(
            SimpleNamespace(
                get_repository_by_name=lambda name: repository,
                is_owner_authoritative_for_repository=lambda repo, owner: True,
            )
        )
        report = self.service.get_repository_by_name("repo")
        self.assertEqual(report.last_updated, repository.last_updated)

    @patch(
        "app.projects.repository_standards.repositories.asset_repository.RepositoryInfo.from_dict"
    )
    def test_repository_view_retains_asset_timestamp(self, mock_info):
        asset = SimpleNamespace(
            id=1,
            name="repo",
            relationships=[],
            data={},
            last_updated=datetime(2026, 10, 15, 3, 24),
        )
        self.assertEqual(
            RepositoryView.from_asset(asset).last_updated, asset.last_updated
        )


if __name__ == "__main__":
    unittest.main()