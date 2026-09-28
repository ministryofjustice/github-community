import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.projects.repository_standards.models.technical_standard import (
    TechnicalStandardCheck,
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


if __name__ == "__main__":
    unittest.main()