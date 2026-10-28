from typing import List
from datetime import datetime, timedelta, timezone

from app.projects.repository_standards.config import (
    repository_compliance_config as legacy,
)
from app.projects.repository_standards.models.technical_standard import (
    TechnicalStandardCheck,
)
from app.projects.repository_standards.repositories.asset_repository import (
    RepositoryView,
)

PASS = "pass"
FAIL = "fail"
NOT_CHECKED = "not_checked"

GUIDANCE_URL = "https://octo-documentation.justice.gov.uk/docs/standards/github-repository-technical-standard.html"


def _check(
    number: int, name: str, anchor: str, status: str, description: str,
    recommendations: list[str] | None = None,
) -> TechnicalStandardCheck:
    return TechnicalStandardCheck(
        number=number,
        name=name,
        status=status,
        description=description,
        link_to_guidance=f"{GUIDANCE_URL}#{anchor}",
        recommendations=(recommendations or []) if status == FAIL else [],
    )


def get_all_technical_standard_checks(
    repository: RepositoryView,
) -> List[TechnicalStandardCheck]:
    return [
        get_authoritative_owner_check(repository),
        get_pull_request_review_protection_check(repository),
        get_branch_protection_enforced_for_admins_check(repository),
        get_signed_commits_check(repository),
        get_no_high_critical_security_alerts_check(repository),
        get_code_owner_reviews_check(repository),
        get_main_default_branch_check(repository),
        get_stale_reviews_check(repository),
        get_mit_license_check(repository),
    ]


def _unverified_feedback(subject: str) -> str:
    return (
        f"{subject} could not be verified by GitHub Community. "
        "Check back after the next scheduled data collection. "
        "If this persists, contact #ask-developer-experience."
    )


def _review_recommendations(protection, rulesets, settings) -> list[str]:
    if protection.present is None or rulesets.enabled is None:
        return [_unverified_feedback("The required review protection")]
    if protection.present is True:
        source = protection
        prefix = "classic"
        recommendations = []
    elif rulesets.enabled is True:
        source = rulesets
        prefix = "ruleset"
        recommendations = []
        if rulesets.pull_request_enforcement != "active":
            if rulesets.pull_request_enforcement is None:
                recommendations.append(_unverified_feedback("Pull request ruleset enforcement"))
            else:
                recommendations.append("Verify that the pull request ruleset is active and applies to the default branch.")
        bypass_count = rulesets.pull_request_bypass_actors_length
        if bypass_count is None:
            recommendations.append(
                _unverified_feedback("The ruleset bypass settings")
            )
        elif bypass_count > 0:
            recommendations.append("Remove bypass actors from the pull request ruleset.")
    else:
        return [
            "Review the default branch protection settings or an active ruleset with no bypass actors. "
            + " ".join(action for classic, ruleset, action in settings)
        ]

    for classic, ruleset, action in settings:
        value = getattr(source, classic if prefix == "classic" else ruleset, None)
        if value is None:
            recommendations.append(
                _unverified_feedback("The required review setting")
            )
        elif value is False or value == 0:
            if (
                prefix == "classic"
                and rulesets.enabled is True
                and (
                    rulesets.pull_request_enforcement is None
                    or rulesets.pull_request_bypass_actors_length is None
                    or (
                        rulesets.pull_request_enforcement == "active"
                        and rulesets.pull_request_bypass_actors_length == 0
                        and getattr(rulesets, ruleset, None) is None
                    )
                )
            ):
                recommendations.append(_unverified_feedback("The required review protection across branch protection and rulesets"))
            else:
                recommendations.append(action)
    return recommendations


def get_authoritative_owner_check(
    repository: RepositoryView,
) -> TechnicalStandardCheck:
    custom_properties_available = getattr(
        repository.data.basic, "custom_properties_available", None
    )
    property_is_set = bool(
        (repository.data.basic.business_unit or "").strip()
    )
    has_admin_team_with_two_maintainers = any(
        (repository.data.access.team_admin_maintainer_counts.get(team, 0) or 0) >= 2
        for team in repository.data.access.teams_with_admin
    )

    status = (
        PASS
        if property_is_set and has_admin_team_with_two_maintainers
        and custom_properties_available is not False
        else FAIL
    )
    recommendations = []
    if custom_properties_available is False:
        recommendations.append(
            _unverified_feedback("The business-unit custom property")
        )
    elif not property_is_set:
        recommendations.append("Set the repository's business-unit custom property.")
    if not has_admin_team_with_two_maintainers:
        counts = repository.data.access.team_admin_maintainer_counts
        admin_teams = repository.data.access.teams_with_admin
        if any(team not in counts or counts[team] is None for team in admin_teams):
            recommendations.append(_unverified_feedback("Admin-team maintainer counts"))
        else:
            recommendations.append("Ensure a team has Admin access and at least two team maintainers.")

    return _check(
        1,
        "Must have an authoritative owner",
        "1-must-have-an-authoritative-owner",
        status,
        "The business-unit property is set, and a team with Admin access has at least two maintainers.",
        recommendations,
    )


def get_branch_protection_enforced_for_admins_check(
    repository: RepositoryView,
) -> TechnicalStandardCheck:
    protection = repository.data.default_branch_protection
    rulesets = repository.data.default_branch_ruleset
    repository_rulesets_enabled = rulesets.repository_branch_rulesets_enabled

    classic_safe = (
        protection.present is False
        or (
            protection.present is True
            and protection.enforce_admins_enabled is True
        )
    )
    rulesets_safe = (
        repository_rulesets_enabled is False
        or (
            repository_rulesets_enabled is True
            and rulesets.repository_branch_rulesets_enforced_without_bypass is True
        )
    )
    has_protection = protection.present is True or repository_rulesets_enabled is True
    status = PASS if has_protection and classic_safe and rulesets_safe else FAIL
    recommendations = []
    if protection.present is False and repository_rulesets_enabled is False:
        recommendations.append("Protect the default branch using branch protection or an active ruleset.")
    if protection.present is None:
        recommendations.append(_unverified_feedback("Classic branch protection"))
    elif protection.present is True and not classic_safe:
        if protection.enforce_admins_enabled is None:
            recommendations.append(_unverified_feedback("Administrator enforcement for classic branch protection"))
        else:
            recommendations.append(
                "Verify that classic branch protection applies to administrators "
                "by enabling Do not allow bypassing the above settings."
            )
    if repository_rulesets_enabled is None:
        recommendations.append(_unverified_feedback("Repository branch rulesets"))
    elif repository_rulesets_enabled is True and not rulesets_safe:
        if rulesets.repository_branch_rulesets_enforced_without_bypass is None:
            recommendations.append(_unverified_feedback("Repository ruleset enforcement and bypass settings"))
        else:
            recommendations.append(
                "Verify that all applicable repository branch rulesets are active and their bypass lists are empty."
            )

    return _check(
        3,
        "Must have branch protection applied to administrators",
        "3-must-have-branch-protection-applied-to-administrators",
        status,
        "Classic default branch protection and repository-defined branch rulesets must apply to administrators, with no bypass actors. Inherited organisation and enterprise rulesets are not assessed by this check.",
        recommendations,
    )


def get_signed_commits_check(repository: RepositoryView) -> TechnicalStandardCheck:
    protection = repository.data.default_branch_protection
    rulesets = repository.data.default_branch_ruleset

    classic_signing_enforced = (
        protection.present is True and protection.required_signatures is True
    )
    ruleset_signing_enforced = (
        rulesets.required_signatures_ruleset_enforced_without_bypass is True
    )
    status = (
        PASS
        if classic_signing_enforced or ruleset_signing_enforced
        else FAIL
    )
    signing_unknown = (
        protection.present is None
        or (protection.present is True and protection.required_signatures is None)
        or rulesets.required_signatures_ruleset_enforced_without_bypass is None
    )

    return _check(
        4,
        "Must have signed commits",
        "4-must-have-signed-commits",
        status,
        "Only commits with a valid verified signature are permitted on the default branch.",
        [
            _unverified_feedback("Signed-commit enforcement") if signing_unknown else
            "Enable Require signed commits "
            "on the default branch using classic protection or an active ruleset with no bypass actors."
        ],
    )


def _has_overdue_alerts(alerts, now, deadlines):
    if alerts is None:
        return None
    unknown = False
    for alert in alerts:
        state = alert.get("state")
        if state in {"fixed", "dismissed", "resolved", "auto_dismissed"}:
            continue
        if state != "open":
            unknown = True
            continue
        if isinstance(deadlines, timedelta):
            deadline = deadlines
        else:
            severity = (alert.get("severity") or "").lower()
            if severity in {"low", "medium"}:
                continue
            deadline = deadlines.get(severity)
            if deadline is None:
                unknown = True
                continue
        try:
            created_at = datetime.fromisoformat(alert["created_at"].replace("Z", "+00:00"))
            if created_at.tzinfo is None or created_at > now:
                unknown = True
                continue
            if now - created_at > deadline:
                return True
        except (KeyError, TypeError, ValueError, AttributeError):
            unknown = True
    return None if unknown else False


def get_no_high_critical_security_alerts_check(
    repository: RepositoryView,
    now: datetime | None = None,
) -> TechnicalStandardCheck:
    alerts = repository.data.security_alerts
    now = now or datetime.now(timezone.utc)
    code_scanning_not_applicable = (
        getattr(alerts, "code_scanning_not_applicable", None) is True
    )
    code_scanning_alerts = getattr(alerts, "code_scanning_alerts", None)
    if code_scanning_alerts is not None:
        code_scanning_alerts = [
            alert
            for alert in code_scanning_alerts
            if (alert.get("severity") or "").lower() in {"high", "critical"}
        ]
    code_scanning_overdue = (
        False if code_scanning_not_applicable and code_scanning_alerts in (None, [])
        else _has_overdue_alerts(code_scanning_alerts, now, timedelta(days=14))
    )
    dependabot_overdue = _has_overdue_alerts(
        getattr(alerts, "dependabot_alerts", None), now,
        {"critical": timedelta(hours=72), "high": timedelta(days=7)},
    )
    secret_count = getattr(alerts, "open_secret_scanning_count", None)
    status = (
        PASS
        if code_scanning_overdue is False and dependabot_overdue is False
        and secret_count == 0
        else FAIL
    )
    recommendations = []
    for source, overdue, setting, action in (
        ("Code Scanning", code_scanning_overdue, "Code Scanning is enabled",
         "Resolve open High and Critical Code Scanning alerts older than 14 days."),
        ("Dependabot", dependabot_overdue, "Dependabot alerts are enabled",
         "Resolve open Dependabot Critical alerts older than 72 hours and High alerts older than 7 days."),
    ):
        if overdue is None:
            recommendations.append(
                f"{source} SLA data is unavailable or incomplete. Check that {setting}."
            )
        elif overdue:
            recommendations.append(action)
    if secret_count is None:
        recommendations.append(
            "Secret Scanning data is unavailable. Check that Secret Scanning is enabled."
        )
    elif secret_count > 0:
        recommendations.append("Resolve open Secret Scanning alerts.")

    return _check(
        5,
        "Must resolve security alerts within required timescales",
        "5-must-resolve-security-alerts-within-required-timescales",
        status,
        "No open Secret Scanning alerts or overdue Dependabot or Code Scanning alerts.",
        recommendations,
    )


def get_code_owner_reviews_check(
    repository: RepositoryView,
) -> TechnicalStandardCheck:
    protection = repository.data.default_branch_protection
    rulesets = repository.data.default_branch_ruleset
    business_unit = (repository.data.basic.business_unit or "").strip()
    belongs_to_hmpps = business_unit.casefold() == "hmpps"

    classic_enforces_code_owner_reviews = (
        protection.present is True
        and protection.require_code_owner_reviews is True
    )
    ruleset_enforces_code_owner_reviews = (
        rulesets.enabled is True
        and rulesets.pull_request_enforcement == "active"
        and rulesets.pull_request_require_code_owner_review is True
        and rulesets.pull_request_bypass_actors_length == 0
    )
    status = (
        PASS
        if belongs_to_hmpps
        or (
            repository.data.codeowners_file_present is True
            and repository.data.codeowners_file_valid is True
            and (
                classic_enforces_code_owner_reviews
                or ruleset_enforces_code_owner_reviews
            )
        )
        else FAIL
    )
    recommendations = []
    if repository.data.codeowners_file_present is None:
        recommendations.append(_unverified_feedback("The presence of a CODEOWNERS file"))
    elif repository.data.codeowners_file_present is False:
        recommendations.append(
            "Add a CODEOWNERS file on the default branch "
            "in .github/CODEOWNERS, CODEOWNERS or docs/CODEOWNERS."
        )
    elif repository.data.codeowners_file_valid is None:
        recommendations.append(_unverified_feedback("CODEOWNERS validation"))
    elif repository.data.codeowners_file_valid is False:
        recommendations.append(
            "Verify that CODEOWNERS contains ownership entries and has no GitHub validation errors."
        )
    if not (classic_enforces_code_owner_reviews or ruleset_enforces_code_owner_reviews):
        recommendations.extend(_review_recommendations(protection, rulesets, [
            ("require_code_owner_reviews", "pull_request_require_code_owner_review",
             "Enable Require review from Code Owners."),
        ]))

    return _check(
        6,
        "Must have code owner reviews",
        "6-must-have-code-owner-reviews",
        status,
        "Changes to the default branch must be reviewed and approved by the designated code owners for the affected areas of the repository.",
        recommendations,
    )


def get_main_default_branch_check(
    repository: RepositoryView,
) -> TechnicalStandardCheck:
    status = (
        PASS
        if repository.data.basic.default_branch_name == "main"
        else FAIL
    )

    return _check(
        7,
        "Must use main as the default branch",
        "7-must-use-main-as-the-default-branch",
        status,
        "The default branch must be main; branch protection and governance checks are collected for the repository default branch.",
        ["Set main as the repository's default branch."],
    )


def get_stale_reviews_check(
    repository: RepositoryView,
) -> TechnicalStandardCheck:
    protection = repository.data.default_branch_protection
    rulesets = repository.data.default_branch_ruleset

    classic_enforces_stale_reviews = (
        protection.present is True
        and protection.dismiss_stale_reviews is True
    )
    ruleset_enforces_stale_reviews = (
        rulesets.enabled is True
        and rulesets.pull_request_enforcement == "active"
        and rulesets.pull_request_dismiss_stale_reviews_on_push is True
        and rulesets.pull_request_bypass_actors_length == 0
    )
    status = (
        PASS
        if classic_enforces_stale_reviews or ruleset_enforces_stale_reviews
        else FAIL
    )

    return _check(
        8,
        "Must dismiss stale reviews on new changes",
        "8-must-dismiss-stale-reviews-on-new-changes",
        status,
        "Default-branch protection must dismiss approvals when new commits are pushed.",
        _review_recommendations(protection, rulesets, [
            ("dismiss_stale_reviews", "pull_request_dismiss_stale_reviews_on_push",
             "Enable Dismiss stale pull request approvals when new commits are pushed."),
        ]) if status == FAIL else [],
    )


def get_mit_license_check(repository: RepositoryView) -> TechnicalStandardCheck:
    license_key = (repository.data.basic.license or "").strip().casefold()
    status = PASS if license_key == "mit" else FAIL

    return _check(
        9,
        "Must use MIT license",
        "9-must-use-mit-license",
        status,
        "GitHub must identify the repository's license as MIT.",
        ["Add or update the repository's license so GitHub recognises it as MIT."],
    )


def get_pull_request_review_protection_check(
    repository: RepositoryView,
) -> TechnicalStandardCheck:
    protection = repository.data.default_branch_protection
    ruleset = repository.data.default_branch_ruleset

    classic_approval_count = (
        protection.required_approving_review_count
        if protection.present is True
        else 0
        if protection.present is False
        else None
    )
    ruleset_state_unknown = (
        ruleset.enabled is None
        or (
            ruleset.enabled is True
            and (
                ruleset.pull_request_enforcement is None
                or ruleset.pull_request_bypass_actors_length is None
            )
        )
    )
    ruleset_is_effective = (
        ruleset.enabled is True
        and ruleset.pull_request_enforcement == "active"
        and ruleset.pull_request_bypass_actors_length == 0
    )
    if ruleset.enabled is False or (
        ruleset.enabled is True and not ruleset_state_unknown and not ruleset_is_effective
    ):
        ruleset_approval_count = 0
    elif ruleset_is_effective:
        ruleset_approval_count = ruleset.pull_request_required_approving_review_count
    else:
        ruleset_approval_count = None

    approval_count_passes = (
        (classic_approval_count or 0) >= 1
        or (ruleset_approval_count or 0) >= 1
    )
    status = PASS if approval_count_passes else FAIL

    recommendations = []
    if status == FAIL:
        ruleset_bypass_blocks_configured_requirement = (
            ruleset.enabled is True
            and ruleset.pull_request_enforcement == "active"
            and (ruleset.pull_request_bypass_actors_length or 0) > 0
            and (ruleset.pull_request_required_approving_review_count or 0) >= 1
        )
        if ruleset_bypass_blocks_configured_requirement:
            recommendations.append(
                "Remove bypass actors from the pull request ruleset."
            )
        else:
            approval_count_unknown = (
                (classic_approval_count is None)
                or (ruleset_approval_count is None)
            )
            if not approval_count_passes:
                recommendations.append(
                    _unverified_feedback("The required approval count")
                    if approval_count_unknown
                    else "Require at least one approving pull request review."
                )

    return _check(
        2,
        "Must have pull request review protection",
        "2-must-have-pull-request-review-protection",
        status,
        "Pull requests targeting the default branch require at least one approving review before merge.",
        recommendations,
    )