from typing import List, Optional
from app.projects.repository_standards.models.repository_compliance import (
    RepositoryComplianceCheck,
)
from app.projects.repository_standards.repositories.asset_repository import (
    RepositoryView,
)

PASS = "pass"
FAIL = "fail"

BASELINE = 1
STANDARD = 2
EXEMPLAR = 3


def get_secret_scanning_enabled_check(
    repository: RepositoryView, required: bool = True
) -> RepositoryComplianceCheck:
    return RepositoryComplianceCheck(
        name="Secret Scanning Enabled",
        status=PASS
        if repository.data.security_and_analysis.secret_scanning_status == "enabled"
        else FAIL,
        required=required,
        maturity_level=BASELINE,
        description="Imporves organisational security by scanning and reporting secrets.",
        link_to_guidance="/repository-standards/guidance#secret-scanning-enabled",
    )


def get_secret_scanning_push_protection_enabled_check(
    repository: RepositoryView, required: bool = True
) -> RepositoryComplianceCheck:
    return RepositoryComplianceCheck(
        name="Secret Scanning Push Protection Enabled",
        status=PASS
        if repository.data.security_and_analysis.push_protection_status == "enabled"
        else FAIL,
        required=required,
        maturity_level=BASELINE,
        description="Prevents secrets from being pushed to the repository.",
        link_to_guidance="/repository-standards/guidance#secret-scanning-push-protection-enabled",
    )


def get_branch_protection_enforced_for_admins_check(
    repository: RepositoryView, required: bool = False
) -> RepositoryComplianceCheck:
    return RepositoryComplianceCheck(
        name="Default Branch Protection Enforced For Admins",
        status=PASS
        if repository.data.default_branch_protection.enforce_admins
        or (
            repository.data.default_branch_ruleset.enabled
            and not repository.data.default_branch_ruleset.pull_request_bypass_actors_length
            and not repository.data.default_branch_ruleset.required_signatures_ruleset_bypass_actors_length
        )
        else FAIL,
        required=required,
        maturity_level=STANDARD,
        description="Prevents admins from bypassing branch protection.",
        link_to_guidance="/repository-standards/guidance#default-branch-protection-enforced-for-admins",
    )


def get_default_branch_protection_requires_signed_commits_check(
    repository: RepositoryView, required: bool = False
) -> RepositoryComplianceCheck:
    return RepositoryComplianceCheck(
        name="Default Branch Protection Requires Signed Commits",
        status=PASS
        if repository.data.default_branch_protection.required_signatures
        or (
            repository.data.default_branch_ruleset.enabled
            and repository.data.default_branch_ruleset.required_signatures_enforcement
            == "active"
            and not repository.data.default_branch_ruleset.required_signatures_ruleset_bypass_actors_length
        )
        else FAIL,
        required=required,
        maturity_level=EXEMPLAR,
        description="Signed commits ensure that the commit author is verified, preventing impersonations.",
        link_to_guidance="/repository-standards/guidance#default-branch-protection-requires-signed-commits",
    )


def get_default_branch_protection_requires_code_owner_reviews_check(
    repository: RepositoryView, required: bool = False
) -> RepositoryComplianceCheck:
    return RepositoryComplianceCheck(
        name="Default Branch Protection Requires Code Owner Reviews",
        status=PASS
        if repository.data.default_branch_protection.require_code_owner_reviews
        or (
            repository.data.default_branch_ruleset.enabled
            and repository.data.default_branch_ruleset.pull_request_enforcement
            == "active"
            and not repository.data.default_branch_ruleset.required_signatures_ruleset_bypass_actors_length
            and repository.data.default_branch_ruleset.pull_request_require_code_owner_review
        )
        else FAIL,
        required=required,
        maturity_level=EXEMPLAR,
        description="Useful for delegating reviews of parts of the codebase to specific people.",
        link_to_guidance="/repository-standards/guidance#default-branch-protection-requires-code-owner-reviews",
    )


def get_default_branch_pull_requests_dismiss_stale_reviews_check(
    repository: RepositoryView, required: bool = False
) -> RepositoryComplianceCheck:
    return RepositoryComplianceCheck(
        name="Default Branch Pull Request Dismiss Stale Reviews",
        status=PASS
        if repository.data.default_branch_protection.dismiss_stale_reviews
        or (
            repository.data.default_branch_ruleset.enabled
            and repository.data.default_branch_ruleset.pull_request_enforcement
            == "active"
            and not repository.data.default_branch_ruleset.required_signatures_ruleset_bypass_actors_length
            and repository.data.default_branch_ruleset.pull_request_dismiss_stale_reviews_on_push
        )
        else FAIL,
        required=required,
        maturity_level=STANDARD,
        description="Ensures that the latest changes are reviewed before merging.",
        link_to_guidance="/repository-standards/guidance#default-branch-pull-request-dismiss-stale-reviews",
    )


def get_default_branch_protection_requires_atleast_one_review_check(
    repository: RepositoryView, required: bool = False
) -> RepositoryComplianceCheck:
    return RepositoryComplianceCheck(
        name="Default Branch Pull Request Requires Atleast One Review",
        status=PASS
        if repository.data.default_branch_protection.required_approving_review_count
        or (
            repository.data.default_branch_ruleset.enabled
            and repository.data.default_branch_ruleset.pull_request_enforcement
            == "active"
            and not repository.data.default_branch_ruleset.pull_request_bypass_actors_length
            and repository.data.default_branch_ruleset.pull_request_required_approving_review_count
        )
        else FAIL,
        required=required,
        maturity_level=STANDARD,
        description="Ensures that at least one person has reviewed the changes before merging.",
        link_to_guidance="/repository-standards/guidance#default-branch-pull-request-requires-atleast-one-review",
    )


def get_has_authorative_owner_check(
    authorative_owner: Optional[str], required: bool = False
) -> RepositoryComplianceCheck:
    return RepositoryComplianceCheck(
        name="Has an Authorative Owner",
        status=PASS if authorative_owner else FAIL,
        required=required,
        maturity_level=STANDARD,
        description="Prevents orphaned repositories by having an easily identifiable owner.",
        link_to_guidance="/repository-standards/guidance#has-an-authoritative-owner",
    )


def get_licence_is_mit_check(
    repository: RepositoryView, required: bool = False
) -> RepositoryComplianceCheck:
    return RepositoryComplianceCheck(
        name="License is MIT",
        status=PASS if repository.data.basic.license == "mit" else FAIL,
        required=required,
        maturity_level=STANDARD,
        description="MIT License is a permissive license that allows for reuse of the codebase.",
        link_to_guidance="/repository-standards/guidance#license-is-mit",
    )


def get_default_branch_is_main_check(
    repository: RepositoryView, required: bool = False
) -> RepositoryComplianceCheck:
    return RepositoryComplianceCheck(
        name="Default Branch is main",
        status=PASS if repository.data.basic.default_branch_name == "main" else FAIL,
        required=required,
        maturity_level=STANDARD,
        description="main is a more inclusive and modern term for the default branch.",
        link_to_guidance="/repository-standards/guidance#default-branch-is-main",
    )


def get_all_compliance_checks(
    repository: RepositoryView, authorative_owner: Optional[str]
) -> List[RepositoryComplianceCheck]:
    return [
        get_secret_scanning_enabled_check(repository),
        get_secret_scanning_push_protection_enabled_check(repository),
        get_branch_protection_enforced_for_admins_check(repository),
        get_default_branch_protection_requires_signed_commits_check(repository),
        get_default_branch_protection_requires_code_owner_reviews_check(repository),
        get_default_branch_pull_requests_dismiss_stale_reviews_check(repository),
        get_default_branch_protection_requires_atleast_one_review_check(repository),
        get_has_authorative_owner_check(authorative_owner),
        get_licence_is_mit_check(repository),
        get_default_branch_is_main_check(repository),
    ]
