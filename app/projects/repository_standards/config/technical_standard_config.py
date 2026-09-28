from typing import List, Optional

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
    repository: RepositoryView, authoritative_owner: Optional[List[str]]
) -> List[TechnicalStandardCheck]:
    return [
        _check(
            1,
            "Must have an authoritative owner",
            "1-must-have-an-authoritative-owner",
            legacy.get_has_authoritative_owner_check(authoritative_owner).status,
            "A named business unit and admin team are accountable for the repository.",
        ),
        _check(
            2,
            "Must have pull request review protection",
            "2-must-have-pull-request-review-protection",
            legacy.get_default_branch_protection_requires_atleast_one_review_check(
                repository
            ).status,
            "Pull requests to the default branch require at least one approving review.",
        ),
        _check(
            3,
            "Must have branch protection applied to administrators",
            "3-must-have-branch-protection-applied-to-administrators",
            legacy.get_branch_protection_enforced_for_admins_check(repository).status,
            "Administrators cannot bypass branch protection.",
        ),
        _check(
            4,
            "Must have signed commits",
            "4-must-have-signed-commits",
            legacy.get_default_branch_protection_requires_signed_commits_check(
                repository
            ).status,
            "Only commits with a verified signature are permitted.",
        ),
        _check(
            5,
            "Must have no outstanding high or critical security alerts",
            "5-must-have-no-outstanding-high-or-critical-security-alerts",
            NOT_CHECKED,
            "No open High or Critical GHAS alerts.",
        ),
        _check(
            6,
            "Must have code owner reviews",
            "6-must-have-code-owner-reviews",
            legacy.get_default_branch_protection_requires_code_owner_reviews_check(
                repository
            ).status,
            "Changes require approval from a designated code owner.",
        ),
        _check(
            7,
            "Must use main as the default branch",
            "7-must-use-main-as-the-default-branch",
            legacy.get_default_branch_is_main_check(repository).status,
            "The default branch is named main.",
        ),
        _check(
            8,
            "Must dismiss stale reviews on new changes",
            "8-must-dismiss-stale-reviews-on-new-changes",
            legacy.get_default_branch_pull_requests_dismiss_stale_reviews_check(
                repository
            ).status,
            "Approvals are dismissed when new commits are pushed.",
        ),
        _check(
            9,
            "Must use MIT license",
            "9-must-use-mit-license",
            legacy.get_licence_is_mit_check(repository).status,
            "The repository is licensed under MIT.",
        ),
    ]