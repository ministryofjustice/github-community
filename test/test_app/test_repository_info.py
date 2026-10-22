import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from datetime import datetime, timezone

from app.projects.repository_standards.config.technical_standard_config import (
    get_all_technical_standard_checks,
    get_no_high_critical_security_alerts_check,
)
from app.projects.repository_standards.clients.github_client import GitHubApiError
from app.projects.repository_standards.models.repository_info import (
    RepositoryInfoFactory,
)
from app.projects.repository_standards.models.repository_info import RepositoryInfo


class TestRepositoryInfoFactory(unittest.TestCase):
    def test_configured_codeql_without_repository_languages_is_saved_as_not_applicable(self):
        class NotFound(Exception):
            status = 404

        setting = SimpleNamespace(status=None)
        repo = SimpleNamespace(
            name=".github", visibility="public", description=None,
            default_branch="main", license=None, delete_branch_on_merge=True,
            security_and_analysis=SimpleNamespace(**{
                name: setting for name in (
                    "secret_scanning", "secret_scanning_validity_checks",
                    "secret_scanning_push_protection", "advanced_security",
                    "secret_scanning_non_provider_patterns",
                )
            }),
            get_contents=Mock(side_effect=NotFound()),
            get_branch=Mock(return_value=SimpleNamespace(get_protection=lambda: None)),
            get_languages=Mock(return_value={}),
        )
        client = Mock()
        client.get_repository_custom_properties.return_value = {}
        client.get_open_code_scanning_alerts.side_effect = GitHubApiError(
            404, "no analysis found"
        )
        client.get_code_scanning_default_setup.return_value = {
            "state": "configured", "languages": [],
        }
        client.get_open_dependabot_alerts.return_value = []
        client.get_open_secret_scanning_alerts.return_value = []
        client.get_branch_rulesets.return_value = []

        result = RepositoryInfoFactory.from_github_repo(
            repo, [], [], [], [], client
        )

        self.assertEqual(
            result.security_alerts.open_high_critical_code_scanning_count, 0
        )
        self.assertIs(result.security_alerts.code_scanning_not_applicable, True)
        restored = RepositoryInfo.from_dict(result.to_dict())
        self.assertIs(restored.security_alerts.code_scanning_not_applicable, True)
        self.assertEqual(restored.security_alerts.code_scanning_alerts, [])
        self.assertEqual(restored.security_alerts.open_secret_scanning_count, 0)
        self.assertEqual(
            get_no_high_critical_security_alerts_check(SimpleNamespace(data=restored)).status,
            "pass",
        )

        client.get_open_code_scanning_alerts.side_effect = None
        client.get_open_code_scanning_alerts.return_value = [{
            "state": "open", "created_at": "2026-10-20T00:00:00Z",
            "rule": {"security_severity_level": "low", "description": "Do not store"},
        }]
        client.get_open_dependabot_alerts.return_value = [{
            "state": "open", "created_at": "2026-10-20T00:00:00Z",
            "security_advisory": {"severity": "critical", "description": "Do not store"},
        }]
        client.get_open_secret_scanning_alerts.return_value = [
            {"state": "open", "secret": "never-persist-this"}
        ]
        snapshot = RepositoryInfoFactory.from_github_repo(repo, [], [], [], [], client)
        self.assertEqual(snapshot.security_alerts.code_scanning_alerts, [
            {"state": "open", "created_at": "2026-10-20T00:00:00Z"}
        ])
        self.assertEqual(snapshot.security_alerts.dependabot_alerts, [
            {"state": "open", "created_at": "2026-10-20T00:00:00Z", "severity": "critical"}
        ])
        self.assertNotIn("never-persist-this", str(snapshot.to_dict()))
        self.assertNotIn("Do not store", str(snapshot.to_dict()))
        self.assertEqual(snapshot.security_alerts.open_secret_scanning_count, 1)
        check = get_no_high_critical_security_alerts_check(
            SimpleNamespace(data=snapshot), now=datetime(2026, 10, 21, tzinfo=timezone.utc)
        )
        self.assertEqual(check.status, "fail")
        self.assertEqual(check.recommendations, ["Resolve open Secret Scanning alerts."])

    def test_only_confirmed_no_analysis_with_no_languages_is_not_applicable(self):
        repo = SimpleNamespace(name=".github", get_languages=lambda: {})
        client = Mock()
        client.get_open_code_scanning_alerts.side_effect = GitHubApiError(
            404, "no analysis found"
        )
        client.get_code_scanning_default_setup.return_value = {
            "state": "configured", "languages": [],
        }
        result = RepositoryInfoFactory._get_code_scanning_alert_result(repo, client)
        self.assertEqual(result, (0, True, []))

    def test_other_alert_errors_remain_unavailable(self):
        repo = SimpleNamespace(name=".github", get_languages=Mock(return_value={}))
        for error in (
            GitHubApiError(404, "Not Found"),
            GitHubApiError(403, "Resource not accessible by integration"),
        ):
            with self.subTest(error=error):
                client = Mock()
                client.get_open_code_scanning_alerts.side_effect = error
                self.assertEqual(
                    RepositoryInfoFactory._get_code_scanning_alert_result(repo, client),
                    (None, False, None),
                )
                client.get_code_scanning_default_setup.assert_not_called()
                repo.get_languages.assert_not_called()

    def test_code_scanning_not_applicable_requires_configured_setup_and_no_languages(self):
        repo = SimpleNamespace(name=".github", get_languages=lambda: {})
        client = Mock()
        client.get_code_scanning_default_setup.return_value = {
            "state": "configured", "languages": [],
        }
        self.assertTrue(
            RepositoryInfoFactory._code_scanning_is_not_applicable(repo, client)
        )
        repo.get_languages = lambda: {"Python": 1200}
        self.assertFalse(
            RepositoryInfoFactory._code_scanning_is_not_applicable(repo, client)
        )
        repo.get_languages = lambda: {}
        client.get_code_scanning_default_setup.return_value = {
            "state": "not_configured", "languages": [],
        }
        self.assertFalse(
            RepositoryInfoFactory._code_scanning_is_not_applicable(repo, client)
        )
        client.get_code_scanning_default_setup.side_effect = ValueError("unavailable")
        self.assertFalse(
            RepositoryInfoFactory._code_scanning_is_not_applicable(repo, client)
        )

    def test_multiple_rulesets_collect_order_independent_compliance_results(self):
        rules = [
            {"type": "pull_request", "ruleset_id": 1, "ruleset_source_type": "Repository",
             "parameters": {"required_approving_review_count": 2}},
            {"type": "required_signatures", "ruleset_id": 1, "ruleset_source_type": "Repository"},
            {"type": "pull_request", "ruleset_id": 2, "ruleset_source_type": "Organization",
             "parameters": {"require_last_push_approval": True, "require_code_owner_review": True,
                            "dismiss_stale_reviews_on_push": True}},
            {"type": "pull_request", "ruleset_id": 3, "ruleset_source_type": "Repository",
             "parameters": {"required_approving_review_count": 0, "require_last_push_approval": False}},
            {"type": "required_signatures", "ruleset_id": 3, "ruleset_source_type": "Repository"},
        ]
        security_setting = SimpleNamespace(status=None)
        for ordered_rules in (rules, list(reversed(rules))):
            repo = SimpleNamespace(
                name="repo", visibility="public", description=None, default_branch="main",
                license=SimpleNamespace(key="mit"), delete_branch_on_merge=True,
                security_and_analysis=SimpleNamespace(**{
                    field: security_setting for field in (
                        "secret_scanning", "secret_scanning_validity_checks",
                        "secret_scanning_push_protection", "advanced_security",
                        "secret_scanning_non_provider_patterns",
                    )
                }),
                get_branch=Mock(return_value=SimpleNamespace(get_protection=lambda: None)),
                get_contents=Mock(return_value=SimpleNamespace(decoded_content=b"* @org/team")),
            )
            client = Mock()
            client.get_repository_custom_properties.return_value = {"business-unit": "OCTO"}
            client.get_codeowners_errors.return_value = {"errors": []}
            client.get_open_code_scanning_alerts.return_value = []
            client.get_open_dependabot_alerts.return_value = []
            client.get_branch_rulesets.return_value = ordered_rules
            client.get_repository_ruleset.side_effect = lambda name, ruleset_id: {
                "source_type": "Organization" if ruleset_id == 2 else "Repository",
                "target": "branch", "enforcement": "active",
                "bypass_actors": [{"actor_type": "Team"}] if ruleset_id == 3 else [],
            }
            snapshot = RepositoryInfoFactory.from_github_repo(
                repo, ["team"], [], ["team"], [], client, {"team": 2}
            )
            checks = {check.number: check for check in get_all_technical_standard_checks(
                SimpleNamespace(data=snapshot)
            )}
            for number in (2, 4, 6, 8):
                with self.subTest(number=number, first_ruleset=ordered_rules[0]["ruleset_id"]):
                    self.assertEqual(checks[number].status, "pass")
                    self.assertEqual(checks[number].recommendations, [])
            self.assertEqual(checks[3].status, "fail")
            self.assertEqual(client.get_repository_ruleset.call_count, 3)
            client.get_branch_rulesets.assert_called_once_with("repo", "main")

    def test_ruleset_lookup_failure_does_not_discard_other_verified_rules(self):
        rules = [
            {"type": "pull_request", "ruleset_id": ruleset_id,
             "parameters": {"required_approving_review_count": 1,
                            "require_last_push_approval": True}}
            for ruleset_id in (1, 2)
        ]
        client = Mock()
        client.get_repository_ruleset.side_effect = ValueError("Unavailable")
        for ordered_rules in (rules, list(reversed(rules))):
            result = RepositoryInfoFactory._get_effective_branch_rulesets(
                ordered_rules,
                {1: {"target": "branch", "enforcement": "active", "bypass_actors": []}},
                "repo", client,
            )
            self.assertEqual(result.pull_request_required_approving_review_count, 1)
            self.assertIs(result.pull_request_require_last_push_approval, True)
            self.assertEqual(result.pull_request_bypass_actors_length, 0)

    def test_effective_rulesets_combine_requirements_independently_of_order(self):
        rules = [
            {"type": "pull_request", "ruleset_id": 1,
             "parameters": {"required_approving_review_count": 2}},
            {"type": "pull_request", "ruleset_id": 2,
             "parameters": {"required_approving_review_count": 0,
                            "require_last_push_approval": True,
                            "require_code_owner_review": True,
                            "dismiss_stale_reviews_on_push": True}},
            {"type": "required_signatures", "ruleset_id": 1},
            {"type": "required_signatures", "ruleset_id": 3},
        ]
        details = {
            ruleset_id: {"target": "branch", "enforcement": "active",
                         "bypass_actors": [] if ruleset_id != 3 else [{"actor_type": "Team"}]}
            for ruleset_id in (1, 2, 3)
        }
        for ordered_rules in (rules, list(reversed(rules))):
            client = Mock()
            client.get_repository_ruleset.side_effect = lambda name, ruleset_id: details[ruleset_id]
            result = RepositoryInfoFactory._get_effective_branch_rulesets(
                ordered_rules, {}, "repo", client
            )
            self.assertEqual(result.pull_request_required_approving_review_count, 2)
            self.assertIs(result.pull_request_require_last_push_approval, True)
            self.assertIs(result.pull_request_require_code_owner_review, True)
            self.assertIs(result.pull_request_dismiss_stale_reviews_on_push, True)
            self.assertIs(result.required_signatures_ruleset_enforced_without_bypass, True)
            self.assertEqual(client.get_repository_ruleset.call_count, 3)

    def test_bypassable_or_unverified_rules_cannot_supply_review_requirements(self):
        rules = [
            {"type": "pull_request", "ruleset_id": 1,
             "parameters": {"required_approving_review_count": 1}},
            {"type": "pull_request", "ruleset_id": 2,
             "parameters": {"require_last_push_approval": True}},
        ]
        for enforcement, bypasses, target in (
            ("active", [{"actor_type": "Team"}], "branch"),
            ("evaluate", [], "branch"),
            ("active", None, "branch"),
            ("active", [], None),
            ("active", [], "repository"),
        ):
            with self.subTest(enforcement=enforcement, bypasses=bypasses, target=target):
                result = RepositoryInfoFactory._get_effective_branch_rulesets(
                    rules,
                    {1: {"target": "branch", "enforcement": "active", "bypass_actors": []},
                     2: {"target": target, "enforcement": enforcement, "bypass_actors": bypasses}},
                    "repo", Mock(),
                )
                self.assertEqual(result.pull_request_required_approving_review_count, 1)
                self.assertIsNot(result.pull_request_require_last_push_approval, True)

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
            return {"target": "branch", "enforcement": "active", "bypass_actors": []}

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