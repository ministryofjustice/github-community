from typing import List

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


def _review_recommendations(protection, rulesets, settings) -> list[str]:
    if protection.present is True:
        source = protection
        prefix = "classic"
        recommendations = []
    elif rulesets.enabled is True:
        source = rulesets
        prefix = "ruleset"
        recommendations = []
        if rulesets.pull_request_enforcement != "active":
            recommendations.append(
                "Verify that the pull request ruleset is active and applies to the default branch."
            )
        bypass_count = rulesets.pull_request_bypass_actors_length
        if bypass_count is None:
            recommendations.append(
                "The ruleset bypass list could not be verified. Check access and refresh the report."
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
                f"The setting could not be verified. Check access and refresh the report: {action}"
            )
        elif value is False or value == 0:
            recommendations.append(action)
    return recommendations


def get_authoritative_owner_check(
    repository: RepositoryView,
) -> TechnicalStandardCheck:
    property_is_set = bool(
        (repository.data.basic.business_unit or "").strip()
    )
    has_admin_team_with_two_maintainers = any(
        repository.data.access.team_admin_maintainer_counts.get(team, 0) >= 2
        for team in repository.data.access.teams_with_admin
    )

    status = (
        PASS
        if property_is_set and has_admin_team_with_two_maintainers
        else FAIL
    )
    recommendations = []
    if not property_is_set:
        recommendations.append("Set the repository's business-unit custom property.")
    if not has_admin_team_with_two_maintainers:
        recommendations.append(
            "Ensure a team has Admin access and at least two team maintainers; "
            "verify team membership access if maintainer data is unavailable."
        )

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
        recommendations.append("Classic branch protection data is unavailable. Check access and refresh the report.")
    elif protection.present is True and not classic_safe:
        recommendations.append(
            "Verify that classic branch protection applies to administrators "
            "by enabling Do not allow bypassing the above settings."
        )
    if repository_rulesets_enabled is None:
        recommendations.append("Repository branch ruleset data is unavailable. Refresh the report data to verify its scope.")
    elif repository_rulesets_enabled is True and not rulesets_safe:
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

    return _check(
        4,
        "Must have signed commits",
        "4-must-have-signed-commits",
        status,
        "Only commits with a valid verified signature are permitted on the default branch.",
        [
            "Signed-commit enforcement was not confirmed. Enable Require signed commits "
            "on the default branch using classic protection or an active ruleset with no bypass actors."
        ],
    )


def get_no_high_critical_security_alerts_check(
    repository: RepositoryView,
) -> TechnicalStandardCheck:
    alerts = repository.data.security_alerts
    code_scanning_count = alerts.open_high_critical_code_scanning_count
    dependabot_count = alerts.open_high_critical_dependabot_count
    code_scanning_not_applicable = (
        getattr(alerts, "code_scanning_not_applicable", None) is True
    )
    if code_scanning_not_applicable:
        code_scanning_count = 0

    status = (
        PASS
        if code_scanning_count == 0 and dependabot_count == 0
        else FAIL
    )
    recommendations = []
    for source, count, setting in (
        ("Code Scanning", code_scanning_count, "Code Scanning is enabled"),
        ("Dependabot", dependabot_count, "Dependabot alerts are enabled"),
    ):
        if source == "Code Scanning" and code_scanning_not_applicable:
            continue
        if count is None:
            recommendations.append(
                f"{source} data is unavailable. Check that {setting}."
            )
        elif count > 0:
            recommendations.append(f"Resolve High/Critical {source} alerts.")

    return _check(
        5,
        "Must have no outstanding high or critical security alerts",
        "5-must-have-no-outstanding-high-or-critical-security-alerts",
        status,
        "No open High or Critical Code Scanning or Dependabot alerts; configured CodeQL with no supported languages is not applicable, while unavailable alert data does not pass.",
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
    if repository.data.codeowners_file_present is not True:
        recommendations.append(
            "A CODEOWNERS file was not confirmed. Add one on the default branch "
            "in .github/CODEOWNERS, CODEOWNERS or docs/CODEOWNERS."
        )
    elif repository.data.codeowners_file_valid is not True:
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

    classic_protection_passes = (
        (protection.required_approving_review_count or 0) >= 1
        and protection.require_last_push_approval is True
    )

    ruleset_passes = (
        ruleset.enabled
        and ruleset.pull_request_enforcement == "active"
        and not ruleset.pull_request_bypass_actors_length
        and (ruleset.pull_request_required_approving_review_count or 0) >= 1
        and ruleset.pull_request_require_last_push_approval is True
    )

    status = PASS if classic_protection_passes or ruleset_passes else FAIL

    return _check(
        2,
        "Must have pull request review protection",
        "2-must-have-pull-request-review-protection",
        status,
        "The default branch requires at least one approval, including approval of the most recent reviewable push.",
        _review_recommendations(protection, ruleset, [
            ("required_approving_review_count", "pull_request_required_approving_review_count",
             "Require at least one approving pull request review."),
            ("require_last_push_approval", "pull_request_require_last_push_approval",
             "Enable Require approval of the most recent reviewable push."),
        ]) if status == FAIL else [],
    )