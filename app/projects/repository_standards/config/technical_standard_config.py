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
    number: int, name: str, anchor: str, status: str, description: str
) -> TechnicalStandardCheck:
    return TechnicalStandardCheck(
        number=number,
        name=name,
        status=status,
        description=description,
        link_to_guidance=f"{GUIDANCE_URL}#{anchor}",
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

    return _check(
        1,
        "Must have an authoritative owner",
        "1-must-have-an-authoritative-owner",
        status,
        "The business-unit property is set, and a team with Admin access has at least two maintainers.",
    )


def get_branch_protection_enforced_for_admins_check(
    repository: RepositoryView,
) -> TechnicalStandardCheck:
    protection = repository.data.default_branch_protection
    rulesets = repository.data.default_branch_ruleset

    classic_safe = (
        protection.present is False
        or (
            protection.present is True
            and protection.enforce_admins_enabled is True
        )
    )
    rulesets_safe = (
        rulesets.enabled is False
        or (
            rulesets.enabled is True
            and rulesets.all_rulesets_enforced_without_bypass is True
        )
    )
    has_protection = protection.present is True or rulesets.enabled is True
    status = PASS if has_protection and classic_safe and rulesets_safe else FAIL

    return _check(
        3,
        "Must have branch protection applied to administrators",
        "3-must-have-branch-protection-applied-to-administrators",
        status,
        "Default branch protection must apply to administrators and maintainers, with no bypass actors unless an approved exception is documented.",
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
    )


def get_no_high_critical_security_alerts_check(
    repository: RepositoryView,
) -> TechnicalStandardCheck:
    alerts = repository.data.security_alerts
    code_scanning_count = alerts.open_high_critical_code_scanning_count
    dependabot_count = alerts.open_high_critical_dependabot_count

    status = (
        PASS
        if code_scanning_count == 0 and dependabot_count == 0
        else FAIL
    )

    return _check(
        5,
        "Must have no outstanding high or critical security alerts",
        "5-must-have-no-outstanding-high-or-critical-security-alerts",
        status,
        "No open High or Critical Code Scanning or Dependabot alerts; unavailable alert data does not pass.",
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

    return _check(
        6,
        "Must have code owner reviews",
        "6-must-have-code-owner-reviews",
        status,
        "Changes to the default branch must be reviewed and approved by the designated code owners for the affected areas of the repository.",
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
    )