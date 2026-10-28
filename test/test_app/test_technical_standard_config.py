import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.projects.repository_standards.models.repository_info import (
    BasicRepositoryInfo,
    RepositoryAccess,
    RepositoryInfo,
)
from app.projects.repository_standards.config.technical_standard_config import (
    _has_overdue_alerts,
    FAIL,
    PASS,
    get_authoritative_owner_check,
    get_all_technical_standard_checks,
    get_branch_protection_enforced_for_admins_check,
    get_code_owner_reviews_check,
    get_main_default_branch_check,
    get_mit_license_check,
    get_no_high_critical_security_alerts_check,
    get_pull_request_review_protection_check,
    get_signed_commits_check,
    get_stale_reviews_check,
)


def make_repository(business_unit, admin_teams, maintainer_counts):
    return SimpleNamespace(
        data=SimpleNamespace(
            basic=SimpleNamespace(business_unit=business_unit),
            access=SimpleNamespace(
                teams_with_admin=admin_teams,
                team_admin_maintainer_counts=maintainer_counts,
            ),
        )
    )


def make_review_repository(
    classic_present=True,
    classic_dismiss_stale_reviews=False,
    classic_count=0,
    classic_latest_push=False,
    ruleset_enabled=False,
    ruleset_enforcement=None,
    ruleset_bypass_actors=None,
    ruleset_count=None,
    ruleset_latest_push=None,
    ruleset_dismiss_stale_reviews=None,
):
    return SimpleNamespace(
        data=SimpleNamespace(
            default_branch_protection=SimpleNamespace(
                present=classic_present,
                dismiss_stale_reviews=classic_dismiss_stale_reviews,
                required_approving_review_count=classic_count,
                require_last_push_approval=classic_latest_push,
            ),
            default_branch_ruleset=SimpleNamespace(
                enabled=ruleset_enabled,
                pull_request_enforcement=ruleset_enforcement,
                pull_request_bypass_actors_length=ruleset_bypass_actors,
                pull_request_required_approving_review_count=ruleset_count,
                pull_request_require_last_push_approval=ruleset_latest_push,
                pull_request_dismiss_stale_reviews_on_push=(
                    ruleset_dismiss_stale_reviews
                ),
            ),
        )
    )


def make_admin_enforcement_repository(
    classic_present=None,
    classic_enforced=None,
    rulesets_enabled=None,
    rulesets_enforced_without_bypass=None,
):
    return SimpleNamespace(
        data=SimpleNamespace(
            default_branch_protection=SimpleNamespace(
                present=classic_present,
                enforce_admins_enabled=classic_enforced,
            ),
            default_branch_ruleset=SimpleNamespace(
                enabled=rulesets_enabled,
                all_rulesets_enforced_without_bypass=(
                    rulesets_enforced_without_bypass
                ),
                repository_branch_rulesets_enabled=rulesets_enabled,
                repository_branch_rulesets_enforced_without_bypass=rulesets_enforced_without_bypass,
            ),
        )
    )


def make_signed_commits_repository(
    classic_present=None,
    classic_signed=None,
    ruleset_signed=None,
):
    return SimpleNamespace(
        data=SimpleNamespace(
            default_branch_protection=SimpleNamespace(
                present=classic_present,
                required_signatures=classic_signed,
            ),
            default_branch_ruleset=SimpleNamespace(
                required_signatures_ruleset_enforced_without_bypass=ruleset_signed,
            ),
        )
    )


def make_security_alerts_repository(
    code_scanning_count, dependabot_count, code_scanning_not_applicable=None
):
    return SimpleNamespace(
        data=SimpleNamespace(
            security_alerts=SimpleNamespace(
                open_high_critical_code_scanning_count=code_scanning_count,
                open_high_critical_dependabot_count=dependabot_count,
                code_scanning_not_applicable=code_scanning_not_applicable,
                code_scanning_alerts=(
                    [{"state": "open", "severity": "high", "created_at": "2020-01-01T00:00:00Z"}] * code_scanning_count
                    if code_scanning_count is not None else None
                ),
                dependabot_alerts=(
                    [{"state": "open", "severity": "high", "created_at": "2020-01-01T00:00:00Z"}] * dependabot_count
                    if dependabot_count is not None else None
                ),
                open_secret_scanning_count=0,
            )
        )
    )


class TestSecurityAlertDeadlines(unittest.TestCase):
    def test_check_five_guidance_link_uses_the_updated_heading(self):
        repository = make_security_alerts_repository(0, 0)

        check = get_no_high_critical_security_alerts_check(repository)

        self.assertEqual(
            check.link_to_guidance,
            "https://octo-documentation.justice.gov.uk/docs/standards/"
            "github-repository-technical-standard.html"
            "#5-must-resolve-security-alerts-within-required-timescales",
        )

    def test_check_five_uses_all_agreed_remediation_windows(self):
        now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
        for source, severity, window in (
            ("code_scanning_alerts", "high", timedelta(days=14)),
            ("code_scanning_alerts", "critical", timedelta(days=14)),
            ("dependabot_alerts", "critical", timedelta(hours=72)),
            ("dependabot_alerts", "high", timedelta(days=7)),
        ):
            for extra, expected in ((-1, PASS), (0, PASS), (1, FAIL)):
                with self.subTest(source=source, severity=severity, extra=extra):
                    repository = make_security_alerts_repository(0, 0)
                    setattr(repository.data.security_alerts, source, [{
                        "state": "open", "severity": severity,
                        "created_at": (now - window - timedelta(seconds=extra)).isoformat(),
                    }])
                    check = get_no_high_critical_security_alerts_check(repository, now=now)
                    self.assertEqual(check.status, expected)

    def test_low_medium_and_unclassified_code_scanning_alerts_do_not_affect_check(self):
        now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
        repository = make_security_alerts_repository(0, 0)
        repository.data.security_alerts.code_scanning_alerts = [
            {"state": "open", "severity": severity, "created_at": "2020-01-01T00:00:00Z"}
            for severity in ("low", "medium", None, "unknown")
        ]

        check = get_no_high_critical_security_alerts_check(repository, now=now)

        self.assertEqual(check.status, PASS)
        self.assertEqual(check.recommendations, [])

    def test_any_open_secret_fails_even_when_other_sources_pass(self):
        repository = make_security_alerts_repository(0, 0)
        repository.data.security_alerts.open_secret_scanning_count = 1
        check = get_no_high_critical_security_alerts_check(repository)
        self.assertEqual(check.status, FAIL)
        self.assertEqual(check.recommendations, ["Resolve open Secret Scanning alerts."])

    def test_old_counts_alone_cannot_pass_the_new_rules(self):
        repository = make_security_alerts_repository(0, 0)
        del repository.data.security_alerts.code_scanning_alerts
        del repository.data.security_alerts.dependabot_alerts
        del repository.data.security_alerts.open_secret_scanning_count
        check = get_no_high_critical_security_alerts_check(repository)
        self.assertEqual(check.status, FAIL)
        self.assertEqual(len(check.recommendations), 3)

    def test_no_languages_exception_does_not_exempt_secret_scanning(self):
        repository = make_security_alerts_repository(None, 0, code_scanning_not_applicable=True)
        repository.data.security_alerts.open_secret_scanning_count = 1
        self.assertEqual(get_no_high_critical_security_alerts_check(repository).status, FAIL)

    def test_deadlines_are_strict_and_use_creation_time(self):
        now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
        for window in (timedelta(hours=72), timedelta(days=7), timedelta(days=14)):
            for offset, expected in ((-1, False), (0, False), (1, True)):
                with self.subTest(window=window, offset=offset):
                    alert = {"state": "open", "created_at": (now - window - timedelta(seconds=offset)).isoformat(),
                             "updated_at": now.isoformat()}
                    self.assertIs(_has_overdue_alerts([alert], now, window), expected)

    def test_unknown_dates_and_missing_data_cannot_pass(self):
        now = datetime(2026, 10, 21, tzinfo=timezone.utc)
        for alerts in (None, [{"state": "open"}], [{"state": "open", "created_at": "invalid"}],
                       [{"state": "open", "created_at": "2026-10-22T00:00:00Z"}]):
            with self.subTest(alerts=alerts):
                self.assertIsNone(_has_overdue_alerts(alerts, now, timedelta(days=14)))

    def test_dependency_severities_and_closed_alerts(self):
        now = datetime(2026, 10, 21, tzinfo=timezone.utc)
        deadlines = {"critical": timedelta(hours=72), "high": timedelta(days=7)}
        for severity, expected in (("critical", True), ("high", False), ("medium", False), ("low", False)):
            alert = {"state": "open", "severity": severity, "created_at": "2026-10-17T00:00:00Z"}
            self.assertIs(_has_overdue_alerts([alert], now, deadlines), expected)
        self.assertIs(_has_overdue_alerts([{"state": "fixed"}], now, deadlines), False)


class TestCheckRecommendations(unittest.TestCase):
    def test_unknown_data_feedback_signposts_support_without_configuration_claims(self):
        repository = SimpleNamespace(data=RepositoryInfo(
            basic=BasicRepositoryInfo("repo", "public", True, "main"),
            access=RepositoryAccess([], [], [], []),
        ))
        for check in get_all_technical_standard_checks(repository):
            if check.number not in {2, 3, 4, 6, 8}:
                continue
            with self.subTest(check=check.number):
                self.assertEqual(check.status, FAIL)
                self.assertTrue(check.recommendations)
                for advice in check.recommendations:
                    self.assertIn("#ask-developer-experience", advice)
                    self.assertIn("next scheduled data collection", advice)
                    self.assertNotIn("Check access", advice)
                    self.assertNotIn("Enable ", advice)
                    self.assertNotIn("Add one", advice)

    def test_unknown_maintainer_count_does_not_claim_team_needs_more_maintainers(self):
        repository = make_repository("OCTO", ["team"], {})
        check = get_authoritative_owner_check(repository)
        self.assertEqual(check.status, FAIL)
        self.assertEqual(len(check.recommendations), 1)
        self.assertIn("#ask-developer-experience", check.recommendations[0])
        self.assertNotIn("Ensure a team", check.recommendations[0])

    def test_all_failed_requirements_have_recommendations(self):
        repository = SimpleNamespace(data=RepositoryInfo(
            basic=BasicRepositoryInfo("repo", "public", True, "master"),
            access=RepositoryAccess([], [], [], []),
        ))
        checks = get_all_technical_standard_checks(repository)
        self.assertEqual(len(checks), 9)
        for check in checks:
            with self.subTest(number=check.number):
                self.assertEqual(check.status, FAIL)
                self.assertTrue(check.recommendations)

    def test_owner_advice_only_lists_missing_requirements(self):
        check = get_authoritative_owner_check(
            make_repository(None, ["team"], {"team": 2})
        )
        self.assertEqual(check.recommendations, [
            "Set the repository's business-unit custom property."
        ])

    def test_latest_push_disabled_does_not_produce_recommendations(self):
        check = get_pull_request_review_protection_check(
            make_review_repository(classic_count=1, classic_latest_push=False)
        )
        self.assertEqual(check.status, PASS)
        self.assertEqual(check.recommendations, [])

    def test_ruleset_bypass_advice_does_not_request_enabled_settings(self):
        check = get_pull_request_review_protection_check(
            make_review_repository(
                classic_present=False,
                ruleset_enabled=True,
                ruleset_enforcement="active",
                ruleset_bypass_actors=1,
                ruleset_count=1,
                ruleset_latest_push=True,
            )
        )
        self.assertEqual(check.recommendations, [
            "Remove bypass actors from the pull request ruleset."
        ])

    def test_unknown_review_setting_is_not_reported_as_disabled(self):
        check = get_pull_request_review_protection_check(
            make_review_repository(classic_count=None, classic_latest_push=None)
        )
        self.assertEqual(len(check.recommendations), 1)
        self.assertIn("could not be verified", check.recommendations[0])

    def test_passing_ruleset_has_no_classic_protection_advice(self):
        check = get_pull_request_review_protection_check(
            make_review_repository(
                ruleset_enabled=True,
                ruleset_enforcement="active",
                ruleset_bypass_actors=0,
                ruleset_count=1,
                ruleset_latest_push=True,
            )
        )
        self.assertEqual(check.status, PASS)
        self.assertEqual(check.recommendations, [])

    def test_unknown_protection_does_not_claim_bypass_is_enabled(self):
        check = get_branch_protection_enforced_for_admins_check(
            make_admin_enforcement_repository()
        )
        self.assertEqual(len(check.recommendations), 2)
        self.assertTrue(all("could not be verified" in item for item in check.recommendations))

    def test_codeowners_advice_only_requests_missing_file(self):
        check = get_code_owner_reviews_check(
            make_code_owner_reviews_repository(
                codeowners_present=False,
                classic_present=True,
                classic_requires_codeowners=True,
            )
        )
        self.assertEqual(len(check.recommendations), 1)
        self.assertIn("Add a CODEOWNERS file on the default branch", check.recommendations[0])

    def test_stale_review_advice_is_separate_from_latest_push(self):
        check = get_stale_reviews_check(
            make_review_repository(classic_latest_push=True)
        )
        self.assertEqual(check.recommendations, [
            "Enable Dismiss stale pull request approvals when new commits are pushed."
        ])

    def test_alert_recommendations_do_not_include_counts(self):
        check = get_no_high_critical_security_alerts_check(
            make_security_alerts_repository(12, 3)
        )
        self.assertEqual(check.recommendations, [
            "Resolve open High and Critical Code Scanning alerts older than 14 days.",
            "Resolve open Dependabot Critical alerts older than 72 hours and High alerts older than 7 days.",
        ])

    def test_unavailable_alerts_do_not_claim_scanning_is_disabled(self):
        check = get_no_high_critical_security_alerts_check(
            make_security_alerts_repository(None, 0)
        )
        self.assertEqual(check.recommendations, [
            "Code Scanning SLA data is unavailable or incomplete. Check that Code Scanning is enabled."
        ])

    def test_passing_security_check_has_no_recommendations(self):
        check = get_no_high_critical_security_alerts_check(
            make_security_alerts_repository(0, 0)
        )
        self.assertEqual(check.recommendations, [])

    def test_enabled_codeql_without_supported_languages_is_not_applicable(self):
        check = get_no_high_critical_security_alerts_check(
            make_security_alerts_repository(None, 0, code_scanning_not_applicable=True)
        )
        self.assertEqual(check.status, PASS)
        self.assertEqual(check.recommendations, [])

    def test_not_applicable_codeql_does_not_bypass_dependabot_alerts(self):
        check = get_no_high_critical_security_alerts_check(
            make_security_alerts_repository(None, None, code_scanning_not_applicable=True)
        )
        self.assertEqual(check.status, FAIL)
        self.assertEqual(len(check.recommendations), 1)
        self.assertIn("Dependabot SLA data is unavailable", check.recommendations[0])

    def test_mixed_alert_data_has_distinct_recommendations(self):
        check = get_no_high_critical_security_alerts_check(
            make_security_alerts_repository(10, None)
        )
        self.assertEqual(check.recommendations, [
            "Resolve open High and Critical Code Scanning alerts older than 14 days.",
            "Dependabot SLA data is unavailable or incomplete. Check that Dependabot alerts are enabled.",
        ])

    def test_unavailable_scanning_feedback_does_not_request_report_refresh(self):
        repository = make_security_alerts_repository(None, None)
        repository.data.security_alerts.open_secret_scanning_count = None

        check = get_no_high_critical_security_alerts_check(repository)

        self.assertEqual(check.status, FAIL)
        self.assertEqual(check.recommendations, [
            "Code Scanning SLA data is unavailable or incomplete. Check that Code Scanning is enabled.",
            "Dependabot SLA data is unavailable or incomplete. Check that Dependabot alerts are enabled.",
            "Secret Scanning data is unavailable. Check that Secret Scanning is enabled.",
        ])
        self.assertTrue(all("refresh" not in advice.lower() for advice in check.recommendations))


class TestAuthoritativeOwnerCheck(unittest.TestCase):
    def test_unavailable_properties_fail_without_claiming_the_property_is_missing(self):
        for business_unit in (None, "Previously recorded value"):
            with self.subTest(business_unit=business_unit):
                repository = make_repository(business_unit, ["team-alpha"], {"team-alpha": 2})
                repository.data.basic.custom_properties_available = False
                check = get_authoritative_owner_check(repository)
                self.assertEqual(check.status, FAIL)
                self.assertEqual(len(check.recommendations), 1)
                self.assertIn("could not be verified", check.recommendations[0])
                self.assertNotIn("Set the repository's", check.recommendations[0])

    def test_passes_when_property_and_admin_team_requirements_are_met(self):
        repository = make_repository(
            "Any non-empty value",
            ["team-alpha"],
            {"team-alpha": 2},
        )

        check = get_authoritative_owner_check(repository)

        self.assertEqual(check.status, PASS)

    def test_fails_when_business_unit_property_is_missing(self):
        repository = make_repository(None, ["team-alpha"], {"team-alpha": 2})

        check = get_authoritative_owner_check(repository)

        self.assertEqual(check.status, FAIL)

    def test_fails_when_admin_team_has_fewer_than_two_maintainers(self):
        repository = make_repository("Any value", ["team-alpha"], {"team-alpha": 1})

        check = get_authoritative_owner_check(repository)

        self.assertEqual(check.status, FAIL)

    def test_fails_when_maintainer_team_does_not_have_admin_access(self):
        repository = make_repository("Any value", ["team-alpha"], {"team-beta": 2})

        check = get_authoritative_owner_check(repository)

        self.assertEqual(check.status, FAIL)


class TestPassingRepositoryFixture(unittest.TestCase):
    def test_complete_hmpps_main_mit_fixture_passes_all_checks(self):
        repository = SimpleNamespace(
            data=SimpleNamespace(
                basic=SimpleNamespace(
                    business_unit="HMPPS",
                    default_branch_name="main",
                    license="mit",
                    license_path="LICENSE",
                ),
                access=SimpleNamespace(
                    teams_with_admin=["team-alpha"],
                    team_admin_maintainer_counts={"team-alpha": 2},
                ),
                default_branch_protection=SimpleNamespace(
                    present=True,
                    enforce_admins_enabled=True,
                    required_signatures=True,
                    required_approving_review_count=1,
                    require_last_push_approval=True,
                    require_code_owner_reviews=True,
                    dismiss_stale_reviews=True,
                ),
                default_branch_ruleset=SimpleNamespace(
                    enabled=False,
                    all_rulesets_enforced_without_bypass=False,
                    repository_branch_rulesets_enabled=False,
                    repository_branch_rulesets_enforced_without_bypass=True,
                    required_signatures_ruleset_enforced_without_bypass=None,
                    pull_request_enforcement=None,
                    pull_request_bypass_actors_length=None,
                    pull_request_required_approving_review_count=None,
                    pull_request_require_last_push_approval=None,
                    pull_request_require_code_owner_review=None,
                    pull_request_dismiss_stale_reviews_on_push=None,
                ),
                security_alerts=SimpleNamespace(
                    open_high_critical_code_scanning_count=0,
                    open_high_critical_dependabot_count=0,
                    code_scanning_alerts=[],
                    dependabot_alerts=[],
                    open_secret_scanning_count=0,
                ),
                codeowners_file_present=True,
                codeowners_file_valid=True,
            )
        )

        checks = get_all_technical_standard_checks(repository)

        self.assertEqual(len(checks), 9)
        self.assertTrue(all(check.status == PASS for check in checks))
        self.assertTrue(all(not check.recommendations for check in checks))


class TestBranchProtectionEnforcedForAdminsCheck(unittest.TestCase):
    def test_inherited_bypasses_do_not_override_verified_repository_branch_rulesets(self):
        repository = make_admin_enforcement_repository(
            classic_present=False, rulesets_enabled=True,
            rulesets_enforced_without_bypass=True,
        )
        repository.data.default_branch_ruleset.all_rulesets_enforced_without_bypass = False
        check = get_branch_protection_enforced_for_admins_check(repository)
        self.assertEqual(check.status, PASS)
        self.assertEqual(check.recommendations, [])

    def test_inherited_rulesets_alone_do_not_satisfy_repository_protection(self):
        repository = make_admin_enforcement_repository(
            classic_present=False, rulesets_enabled=True,
            rulesets_enforced_without_bypass=True,
        )
        repository.data.default_branch_ruleset.repository_branch_rulesets_enabled = False
        self.assertEqual(get_branch_protection_enforced_for_admins_check(repository).status, FAIL)

    def test_old_unscoped_snapshot_requires_refresh(self):
        repository = make_admin_enforcement_repository(
            classic_present=False, rulesets_enabled=True,
            rulesets_enforced_without_bypass=True,
        )
        repository.data.default_branch_ruleset.repository_branch_rulesets_enabled = None
        repository.data.default_branch_ruleset.repository_branch_rulesets_enforced_without_bypass = None
        check = get_branch_protection_enforced_for_admins_check(repository)
        self.assertEqual(check.status, FAIL)
        self.assertIn("Check back after the next scheduled data collection", check.recommendations[0])

    def test_passes_when_classic_protection_enforces_for_admins(self):
        repository = make_admin_enforcement_repository(
            classic_present=True,
            classic_enforced=True,
            rulesets_enabled=False,
        )

        check = get_branch_protection_enforced_for_admins_check(repository)

        self.assertEqual(check.status, PASS)

    def test_fails_when_classic_protection_does_not_enforce_for_admins(self):
        repository = make_admin_enforcement_repository(
            classic_present=True,
            classic_enforced=False,
            rulesets_enabled=False,
        )

        check = get_branch_protection_enforced_for_admins_check(repository)

        self.assertEqual(check.status, FAIL)

    def test_passes_when_rulesets_are_active_and_have_no_bypass(self):
        repository = make_admin_enforcement_repository(
            classic_present=False,
            rulesets_enabled=True,
            rulesets_enforced_without_bypass=True,
        )

        check = get_branch_protection_enforced_for_admins_check(repository)

        self.assertEqual(check.status, PASS)

    def test_fails_when_rulesets_have_bypass_or_unknown_state(self):
        for rulesets_enforced_without_bypass in (False, None):
            with self.subTest(
                rulesets_enforced_without_bypass=rulesets_enforced_without_bypass
            ):
                repository = make_admin_enforcement_repository(
                    classic_present=False,
                    rulesets_enabled=True,
                    rulesets_enforced_without_bypass=(
                        rulesets_enforced_without_bypass
                    ),
                )

                check = get_branch_protection_enforced_for_admins_check(repository)

                self.assertEqual(check.status, FAIL)

    def test_fails_when_no_protection_is_configured(self):
        repository = make_admin_enforcement_repository(
            classic_present=False,
            rulesets_enabled=False,
        )

        check = get_branch_protection_enforced_for_admins_check(repository)

        self.assertEqual(check.status, FAIL)


class TestSignedCommitsCheck(unittest.TestCase):
    def test_passes_when_classic_protection_requires_signed_commits(self):
        repository = make_signed_commits_repository(
            classic_present=True,
            classic_signed=True,
        )

        check = get_signed_commits_check(repository)

        self.assertEqual(check.status, PASS)

    def test_passes_when_active_signature_ruleset_has_no_bypass_actors(self):
        repository = make_signed_commits_repository(
            classic_present=False,
            ruleset_signed=True,
        )

        check = get_signed_commits_check(repository)

        self.assertEqual(check.status, PASS)

    def test_fails_when_signing_is_disabled_or_ruleset_state_is_unknown(self):
        for ruleset_signed in (False, None):
            with self.subTest(ruleset_signed=ruleset_signed):
                repository = make_signed_commits_repository(
                    classic_present=True,
                    classic_signed=False,
                    ruleset_signed=ruleset_signed,
                )

                check = get_signed_commits_check(repository)

                self.assertEqual(check.status, FAIL)

    def test_fails_when_no_signing_protection_is_configured(self):
        repository = make_signed_commits_repository(
            classic_present=False,
            classic_signed=False,
            ruleset_signed=None,
        )

        check = get_signed_commits_check(repository)

        self.assertEqual(check.status, FAIL)


class TestNoHighCriticalSecurityAlertsCheck(unittest.TestCase):
    def test_passes_when_both_alert_counts_are_zero(self):
        repository = make_security_alerts_repository(0, 0)

        check = get_no_high_critical_security_alerts_check(repository)

        self.assertEqual(check.status, PASS)

    def test_fails_when_either_alert_category_has_open_high_critical_alerts(self):
        for code_scanning_count, dependabot_count in ((1, 0), (0, 2)):
            with self.subTest(
                code_scanning_count=code_scanning_count,
                dependabot_count=dependabot_count,
            ):
                repository = make_security_alerts_repository(
                    code_scanning_count, dependabot_count
                )

                check = get_no_high_critical_security_alerts_check(repository)

                self.assertEqual(check.status, FAIL)

    def test_fails_when_either_alert_count_is_unknown(self):
        repository = make_security_alerts_repository(None, 0)

        check = get_no_high_critical_security_alerts_check(repository)

        self.assertEqual(check.status, FAIL)


def make_code_owner_reviews_repository(
    codeowners_present,
    codeowners_valid=True,
    business_unit="OCTO",
    classic_present=False,
    classic_requires_codeowners=False,
    rulesets_enabled=False,
    ruleset_enforcement=None,
    ruleset_requires_codeowners=None,
    ruleset_bypass_actors=None,
):
    return SimpleNamespace(
        data=SimpleNamespace(
            basic=SimpleNamespace(business_unit=business_unit),
            codeowners_file_present=codeowners_present,
            codeowners_file_valid=codeowners_valid,
            default_branch_protection=SimpleNamespace(
                present=classic_present,
                require_code_owner_reviews=classic_requires_codeowners,
            ),
            default_branch_ruleset=SimpleNamespace(
                enabled=rulesets_enabled,
                pull_request_enforcement=ruleset_enforcement,
                pull_request_require_code_owner_review=ruleset_requires_codeowners,
                pull_request_bypass_actors_length=ruleset_bypass_actors,
            ),
        )
    )


class TestCodeOwnerReviewsCheck(unittest.TestCase):
    def test_passes_with_codeowners_file_and_classic_enforcement(self):
        repository = make_code_owner_reviews_repository(
            codeowners_present=True,
            business_unit="OCTO",
            classic_present=True,
            classic_requires_codeowners=True,
        )

        check = get_code_owner_reviews_check(repository)

        self.assertEqual(check.status, PASS)

    def test_passes_with_codeowners_file_and_active_ruleset_without_bypass(self):
        repository = make_code_owner_reviews_repository(
            codeowners_present=True,
            business_unit="OCTO",
            rulesets_enabled=True,
            ruleset_enforcement="active",
            ruleset_requires_codeowners=True,
            ruleset_bypass_actors=0,
        )

        check = get_code_owner_reviews_check(repository)

        self.assertEqual(check.status, PASS)

    def test_hmpps_is_exempt_without_codeowners_or_review_protection(self):
        repository = make_code_owner_reviews_repository(
            codeowners_present=False,
            codeowners_valid=False,
            business_unit=" hmpps ",
        )

        check = get_code_owner_reviews_check(repository)

        self.assertEqual(check.status, PASS)

    def test_fails_without_codeowners_file_or_enforced_review(self):
        cases = [
            make_code_owner_reviews_repository(
                codeowners_present=False,
                classic_present=True,
                classic_requires_codeowners=True,
            ),
            make_code_owner_reviews_repository(
                codeowners_present=None,
                classic_present=True,
                classic_requires_codeowners=True,
            ),
            make_code_owner_reviews_repository(
                codeowners_present=True,
                codeowners_valid=False,
                classic_present=True,
                classic_requires_codeowners=True,
            ),
            make_code_owner_reviews_repository(
                codeowners_present=True,
                classic_present=True,
                classic_requires_codeowners=False,
            ),
            make_code_owner_reviews_repository(
                codeowners_present=True,
                rulesets_enabled=True,
                ruleset_enforcement="evaluate",
                ruleset_requires_codeowners=True,
                ruleset_bypass_actors=0,
            ),
            make_code_owner_reviews_repository(
                codeowners_present=True,
                rulesets_enabled=True,
                ruleset_enforcement="active",
                ruleset_requires_codeowners=True,
                ruleset_bypass_actors=None,
            ),
        ]

        for repository in cases:
            with self.subTest(repository=repository):
                check = get_code_owner_reviews_check(repository)

                self.assertEqual(check.status, FAIL)


class TestMainDefaultBranchCheck(unittest.TestCase):
    def test_passes_when_default_branch_is_main(self):
        repository = SimpleNamespace(
            data=SimpleNamespace(
                basic=SimpleNamespace(default_branch_name="main")
            )
        )

        check = get_main_default_branch_check(repository)

        self.assertEqual(check.status, PASS)

    def test_fails_when_default_branch_is_not_main(self):
        repository = SimpleNamespace(
            data=SimpleNamespace(
                basic=SimpleNamespace(default_branch_name="master")
            )
        )

        check = get_main_default_branch_check(repository)

        self.assertEqual(check.status, FAIL)


class TestStaleReviewsCheck(unittest.TestCase):
    def test_passes_when_classic_protection_dismisses_stale_reviews(self):
        repository = make_review_repository(
            classic_present=True,
            classic_dismiss_stale_reviews=True,
        )

        check = get_stale_reviews_check(repository)

        self.assertEqual(check.status, PASS)

    def test_passes_when_active_ruleset_dismisses_reviews_without_bypass(self):
        repository = make_review_repository(
            classic_present=False,
            ruleset_enabled=True,
            ruleset_enforcement="active",
            ruleset_bypass_actors=0,
            ruleset_dismiss_stale_reviews=True,
        )

        check = get_stale_reviews_check(repository)

        self.assertEqual(check.status, PASS)

    def test_fails_when_stale_review_dismissal_is_missing_inactive_or_bypassable(self):
        cases = [
            make_review_repository(
                classic_present=True,
                classic_dismiss_stale_reviews=False,
            ),
            make_review_repository(
                classic_present=False,
                ruleset_enabled=True,
                ruleset_enforcement="evaluate",
                ruleset_bypass_actors=0,
            ),
            make_review_repository(
                classic_present=False,
                ruleset_enabled=True,
                ruleset_enforcement="active",
                ruleset_bypass_actors=None,
            ),
        ]

        for repository in cases:
            with self.subTest(repository=repository):
                check = get_stale_reviews_check(repository)

                self.assertEqual(check.status, FAIL)


class TestMitLicenseCheck(unittest.TestCase):
    def test_passes_when_github_detects_mit_license_without_a_path(self):
        repository = SimpleNamespace(
            data=SimpleNamespace(
                basic=SimpleNamespace(license="mit", license_path=None)
            )
        )

        check = get_mit_license_check(repository)

        self.assertEqual(check.status, PASS)

    def test_fails_for_non_mit_or_missing_license_metadata(self):
        cases = [
            SimpleNamespace(license="apache-2.0", license_path="LICENSE"),
            SimpleNamespace(license=None, license_path=None),
        ]

        for basic in cases:
            with self.subTest(basic=basic):
                repository = SimpleNamespace(data=SimpleNamespace(basic=basic))

                check = get_mit_license_check(repository)

                self.assertEqual(check.status, FAIL)


class TestPullRequestReviewProtectionCheck(unittest.TestCase):
    def test_approval_count_can_come_from_either_protection_source(self):
        configurations = (
            make_review_repository(
                classic_count=1,
                classic_latest_push=False,
                ruleset_enabled=True,
                ruleset_enforcement="active",
                ruleset_bypass_actors=0,
                ruleset_count=0,
                ruleset_latest_push=True,
            ),
            make_review_repository(
                classic_count=0,
                classic_latest_push=True,
                ruleset_enabled=True,
                ruleset_enforcement="active",
                ruleset_bypass_actors=0,
                ruleset_count=1,
                ruleset_latest_push=False,
            ),
        )
        for repository in configurations:
            with self.subTest(repository=repository):
                check = get_pull_request_review_protection_check(repository)
                self.assertEqual(check.status, PASS)
                self.assertEqual(check.recommendations, [])

    def test_passes_classic_protection_with_approval_and_latest_push_setting(self):
        repository = make_review_repository(
            classic_count=1,
            classic_latest_push=True,
        )

        check = get_pull_request_review_protection_check(repository)

        self.assertEqual(check.status, PASS)

    def test_passes_classic_protection_without_latest_push_setting(self):
        repository = make_review_repository(
            classic_count=1,
            classic_latest_push=False,
        )

        check = get_pull_request_review_protection_check(repository)

        self.assertEqual(check.status, PASS)

    def test_guidance_link_uses_the_standard_heading_anchor(self):
        repository = make_review_repository(
            classic_count=1,
            classic_latest_push=True,
        )

        check = get_pull_request_review_protection_check(repository)

        self.assertEqual(
            check.link_to_guidance,
            "https://octo-documentation.justice.gov.uk/docs/standards/"
            "github-repository-technical-standard.html"
            "#2-must-have-pull-request-review-protection",
        )

    def test_passes_active_ruleset_with_required_approval(self):
        repository = make_review_repository(
            ruleset_enabled=True,
            ruleset_enforcement="active",
            ruleset_bypass_actors=0,
            ruleset_count=1,
            ruleset_latest_push=True,
        )

        check = get_pull_request_review_protection_check(repository)

        self.assertEqual(check.status, PASS)

    def test_fails_ruleset_without_required_approval(self):
        repository = make_review_repository(
            ruleset_enabled=True,
            ruleset_enforcement="active",
            ruleset_bypass_actors=0,
            ruleset_count=0,
            ruleset_latest_push=True,
        )

        check = get_pull_request_review_protection_check(repository)

        self.assertEqual(check.status, FAIL)

    def test_passes_ruleset_when_latest_push_is_none(self):
        repository = make_review_repository(
            ruleset_enabled=True,
            ruleset_enforcement="active",
            ruleset_bypass_actors=0,
            ruleset_count=1,
            ruleset_latest_push=None,
        )

        check = get_pull_request_review_protection_check(repository)

        self.assertEqual(check.status, PASS)

    def test_latest_push_setting_does_not_affect_classic_or_ruleset_result(self):
        for source in ("classic", "ruleset"):
            for latest_push in (True, False, None):
                for approval_count, expected in ((0, FAIL), (None, FAIL), (1, PASS), (2, PASS)):
                    with self.subTest(source=source, latest_push=latest_push, count=approval_count):
                        repository = make_review_repository(
                            classic_present=source == "classic",
                            classic_count=approval_count,
                            classic_latest_push=latest_push,
                            ruleset_enabled=source == "ruleset",
                            ruleset_enforcement="active",
                            ruleset_bypass_actors=0,
                            ruleset_count=approval_count,
                            ruleset_latest_push=latest_push,
                        )

                        check = get_pull_request_review_protection_check(repository)

                        self.assertEqual(check.status, expected)
                        self.assertNotIn("most recent", check.description)
                        self.assertTrue(all("most recent" not in advice for advice in check.recommendations))
