import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.projects.repository_standards.models.repository_info import (
    RepositoryInfoFactory,
)
from app.projects.repository_standards.models.repository_info import RepositoryInfo


class TestRepositoryInfoFactory(unittest.TestCase):
    def test_stores_business_unit_custom_property(self):
        empty_security_setting = SimpleNamespace(status=None)
        repo = SimpleNamespace(
            name="example-repo",
            visibility="public",
            description="Example",
            default_branch="main",
            license=SimpleNamespace(key="mit", path="LICENSE"),
            delete_branch_on_merge=True,
            security_and_analysis=SimpleNamespace(
                secret_scanning=empty_security_setting,
                secret_scanning_validity_checks=empty_security_setting,
                secret_scanning_push_protection=empty_security_setting,
                advanced_security=empty_security_setting,
                secret_scanning_non_provider_patterns=empty_security_setting,
            ),
            get_branch=lambda branch: SimpleNamespace(
                get_protection=lambda: None
            ),
        )
        repo.get_contents = Mock(
            side_effect=[
                type("NotFound", (Exception,), {"status": 404})(),
                SimpleNamespace(decoded_content=b"* @ministryofjustice/example-team\n"),
            ]
        )
        github_client = Mock()
        github_client.get_repository_custom_properties.return_value = {
            "business-unit": "Example Business Unit"
        }
        github_client.get_codeowners_errors.return_value = {"errors": []}
        github_client.get_open_code_scanning_alerts.return_value = [
            {"state": "open", "rule": {"security_severity_level": "high"}},
            {"state": "fixed", "rule": {"security_severity_level": "critical"}},
            {"state": "open", "rule": {"security_severity_level": "medium"}},
        ]
        github_client.get_open_dependabot_alerts.return_value = [
            {
                "state": "open",
                "security_advisory": {"severity": "critical"},
            },
            {"state": "dismissed", "security_advisory": {"severity": "high"}},
        ]
        github_client.get_branch_rulesets.return_value = [
            {
                "type": "pull_request",
                "ruleset_id": 123,
                "parameters": {
                    "required_approving_review_count": 1,
                    "require_last_push_approval": True,
                },
            },
            {"type": "required_signatures", "ruleset_id": 789},
            {"type": "required_status_checks", "ruleset_id": 456},
        ]
        github_client.get_repository_ruleset.return_value = {
            "enforcement": "active",
            "bypass_actors": [],
        }

        result = RepositoryInfoFactory.from_github_repo(
            repo,
            teams_with_admin=[],
            teams_with_admin_parents=[],
            teams_with_any=[],
            teams_with_any_parents=[],
            github_client=github_client,
            team_admin_maintainer_counts={"team-alpha": 2},
        )

        self.assertEqual(
            result.basic.business_unit,
            "Example Business Unit",
        )
        self.assertEqual(result.basic.license_path, "LICENSE")
        self.assertIs(result.codeowners_file_present, True)
        self.assertIs(result.codeowners_file_valid, True)
        self.assertEqual(
            [call.args[0] for call in repo.get_contents.call_args_list],
            [".github/CODEOWNERS", "CODEOWNERS"],
        )

        self.assertEqual(
            result.access.team_admin_maintainer_counts,
            {"team-alpha": 2},
        )
        self.assertEqual(
            result.security_alerts.open_high_critical_code_scanning_count,
            1,
        )
        self.assertEqual(
            result.security_alerts.open_high_critical_dependabot_count,
            1,
        )
        self.assertIs(
            result.default_branch_ruleset.pull_request_require_last_push_approval,
            True,
        )
        self.assertIs(
            result.default_branch_protection.present,
            False,
        )
        self.assertIs(
            result.default_branch_ruleset.all_rulesets_enforced_without_bypass,
            True,
        )
        self.assertIs(
            result.default_branch_ruleset.required_signatures_ruleset_enforced_without_bypass,
            True,
        )
        self.assertEqual(
            result.default_branch_ruleset.required_signatures_ruleset_bypass_actors_length,
            0,
        )
        self.assertEqual(
            result.default_branch_ruleset.pull_request_bypass_actors_length,
            0,
        )
        github_client.get_repository_ruleset.assert_any_call("example-repo", 456)

    def test_extra_ruleset_lookup_failure_does_not_discard_legacy_data(self):
        empty_security_setting = SimpleNamespace(status=None)
        repo = SimpleNamespace(
            name="example-repo",
            visibility="public",
            description="Example",
            default_branch="main",
            license=SimpleNamespace(key="mit"),
            delete_branch_on_merge=True,
            security_and_analysis=SimpleNamespace(
                secret_scanning=empty_security_setting,
                secret_scanning_validity_checks=empty_security_setting,
                secret_scanning_push_protection=empty_security_setting,
                advanced_security=empty_security_setting,
                secret_scanning_non_provider_patterns=empty_security_setting,
            ),
            get_branch=lambda branch: SimpleNamespace(
                get_protection=lambda: None
            ),
        )
        github_client = Mock()
        github_client.get_repository_custom_properties.return_value = {}
        github_client.get_open_code_scanning_alerts.side_effect = ValueError(
            "missing code scanning alert permission"
        )
        github_client.get_open_dependabot_alerts.return_value = []
        github_client.get_branch_rulesets.return_value = [
            {
                "type": "pull_request",
                "ruleset_id": 123,
                "parameters": {
                    "required_approving_review_count": 1,
                    "require_last_push_approval": True,
                },
            },
            {"type": "required_signatures", "ruleset_id": 789},
            {"type": "required_status_checks", "ruleset_id": 456},
        ]

        def get_ruleset(repository_name, ruleset_id):
            if ruleset_id == 456:
                raise ValueError("ruleset detail unavailable")
            return {"enforcement": "active", "bypass_actors": []}

        github_client.get_repository_ruleset.side_effect = get_ruleset

        result = RepositoryInfoFactory.from_github_repo(
            repo,
            teams_with_admin=[],
            teams_with_admin_parents=[],
            teams_with_any=[],
            teams_with_any_parents=[],
            github_client=github_client,
        )

        self.assertEqual(
            result.default_branch_ruleset.pull_request_required_approving_review_count,
            1,
        )
        self.assertIsNone(
            result.security_alerts.open_high_critical_code_scanning_count
        )
        self.assertEqual(
            result.security_alerts.open_high_critical_dependabot_count,
            0,
        )
        self.assertIsNone(
            result.default_branch_ruleset.all_rulesets_enforced_without_bypass
        )
        self.assertIs(
            result.default_branch_ruleset.required_signatures_ruleset_enforced_without_bypass,
            True,
        )

class TestRepositoryInfoDeserialization(unittest.TestCase):
    def test_old_snapshot_defaults_business_unit_to_none(self):
        result = RepositoryInfo.from_dict(
            {
                "basic": {
                    "name": "example-repo",
                    "visibility": "public",
                    "delete_branch_on_merge": True,
                    "default_branch_name": "main",
                },
                "access": {
                    "teams_with_admin": [],
                    "teams_with_admin_parents": [],
                    "teams": [],
                    "teams_parents": [],
                },
            }
        )

        self.assertIsNone(result.basic.business_unit)
        self.assertIsNone(result.codeowners_file_present)
        self.assertIsNone(result.codeowners_file_valid)
        self.assertIsNone(
            result.security_alerts.open_high_critical_code_scanning_count
        )

        self.assertEqual(result.access.team_admin_maintainer_counts, {})
        
        self.assertIsNone(
            result.default_branch_ruleset.pull_request_require_last_push_approval
        )