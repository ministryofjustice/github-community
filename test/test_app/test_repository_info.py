import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.projects.repository_standards.models.repository_info import (
    RepositoryInfoFactory,
)
from app.projects.repository_standards.models.repository_info import RepositoryInfo


class TestRepositoryInfoFactory(unittest.TestCase):
    def test_repository_branch_ruleset_scope_excludes_inherited_visibility_policy(self):
        client = Mock()
        rules = [
            {"type": "pull_request", "ruleset_id": 18430120,
             "ruleset_source_type": "Repository"},
            {"type": "repository_visibility", "ruleset_id": 25238409,
             "ruleset_source_type": "Organization"},
        ]
        details = {18430120: {
            "target": "branch", "enforcement": "active", "bypass_actors": [],
        }}
        result = RepositoryInfoFactory._get_repository_branch_ruleset_status(
            rules, details, ".github", client
        )
        self.assertEqual(result, (True, True))
        client.get_repository_ruleset.assert_not_called()

    def test_local_branch_rulesets_still_require_active_enforcement_without_bypasses(self):
        for enforcement, bypasses in (
            ("active", [{"actor_type": "Team"}]),
            ("evaluate", []),
            ("active", None),
        ):
            with self.subTest(enforcement=enforcement, bypasses=bypasses):
                result = RepositoryInfoFactory._get_repository_branch_ruleset_status(
                    [{"ruleset_id": 123, "ruleset_source_type": "Repository"}],
                    {123: {"target": "branch", "enforcement": enforcement,
                           "bypass_actors": bypasses}},
                    "repo", Mock(),
                )
                self.assertEqual(result, (True, False))

    def test_repository_branch_ruleset_scope_requires_verified_source_and_target(self):
        for source, target, raises, expected in (
            ("Repository", "branch", False, (True, True)),
            ("Repository", "repository", False, (False, True)),
            ("Organization", "branch", False, (False, True)),
            (None, "branch", True, None),
            ("Repository", None, True, None),
        ):
            with self.subTest(source=source, target=target):
                details = {123: {
                    "source_type": source, "target": target,
                    "enforcement": "active", "bypass_actors": [],
                }}
                arguments = ([{"ruleset_id": 123}], details, "repo", Mock())
                if raises:
                    with self.assertRaises(ValueError):
                        RepositoryInfoFactory._get_repository_branch_ruleset_status(*arguments)
                else:
                    self.assertEqual(
                        RepositoryInfoFactory._get_repository_branch_ruleset_status(*arguments),
                        expected,
                    )

    def test_stores_business_unit_custom_property(self):
        class NotFound(Exception):
            status = 404

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
                get_protection=Mock(side_effect=NotFound())
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
            {"type": "repository_visibility", "ruleset_id": 25238409,
             "ruleset_source_type": "Organization"},
        ]
        github_client.get_repository_ruleset.side_effect = lambda name, ruleset_id: {
            "enforcement": "active",
            "bypass_actors": [{"actor_type": "EnterpriseOwner"}]
            if ruleset_id == 25238409 else [],
            "source_type": "Organization" if ruleset_id == 25238409 else "Repository",
            "target": "repository" if ruleset_id == 25238409 else "branch",
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
            False,
        )
        self.assertIs(
            result.default_branch_ruleset.repository_branch_rulesets_enabled,
            True,
        )
        self.assertIs(
            result.default_branch_ruleset.repository_branch_rulesets_enforced_without_bypass,
            True,
        )
        roundtrip = RepositoryInfo.from_dict(result.to_dict())
        self.assertIs(roundtrip.default_branch_ruleset.repository_branch_rulesets_enabled, True)
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
        self.assertIsNone(result.default_branch_ruleset.repository_branch_rulesets_enabled)
        self.assertIsNone(
            result.default_branch_ruleset.repository_branch_rulesets_enforced_without_bypass
        )
        self.assertIsNone(
            result.security_alerts.open_high_critical_code_scanning_count
        )

        self.assertEqual(result.access.team_admin_maintainer_counts, {})
        
        self.assertIsNone(
            result.default_branch_ruleset.pull_request_require_last_push_approval
        )