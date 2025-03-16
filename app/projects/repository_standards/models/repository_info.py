import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


class RepositoryInfoFactory:
    @staticmethod
    def from_github_repo(
        repo,
        teams_with_admin,
        teams_with_admin_parents,
        teams_with_any,
        teams_with_any_parents,
    ):
        basic_info = BasicRepositoryInfo(
            name=repo.name,
            visibility=repo.visibility,
            description=repo.description,
            license=repo.license.key if repo.license else None,
            delete_branch_on_merge=repo.delete_branch_on_merge,
        )

        security_and_analysis = repo.security_and_analysis
        security_analysis = SecurityAndAnalysisInfo(
            secret_scanning_status=getattr(
                security_and_analysis.secret_scanning, "status", None
            ),
            secret_scanning_validity_checks=getattr(
                security_and_analysis.secret_scanning_validity_checks, "status", None
            ),
            push_protection_status=getattr(
                security_and_analysis.secret_scanning_push_protection, "status", None
            ),
            advanced_security=getattr(
                security_and_analysis.advanced_security, "status", None
            ),
            non_provider_patterns=getattr(
                security_and_analysis.secret_scanning_non_provider_patterns,
                "status",
                None,
            ),
        )

        try:
            default_branch_protection = repo.get_branch(
                repo.default_branch
            ).get_protection()
            pr = (
                default_branch_protection.required_pull_request_reviews
                if default_branch_protection
                else None
            )
            default_branch_protection = BranchProtectionInfo(
                enabled=getattr(default_branch_protection, "enabled", False),
                allow_force_pushes=getattr(
                    default_branch_protection, "allow_force_pushes", False
                ),
                enforce_admins=getattr(
                    default_branch_protection, "enforce_admins", False
                ),
                required_signatures=getattr(
                    default_branch_protection, "required_signatures", False
                ),
                dismiss_stale_reviews=getattr(pr, "dismiss_stale_reviews", False),
                require_code_owner_reviews=getattr(
                    pr, "require_code_owner_reviews", False
                ),
                require_last_push_approval=getattr(
                    pr, "require_last_push_approval", False
                ),
                required_approving_review_count=getattr(
                    pr, "required_approving_review_count", 0
                ),
            )
        except Exception as e:
            default_branch_protection = None
            logger.error("Error getting default branch protection: %s", e)

        repository_access = RepositoryAccess(
            teams_with_admin=teams_with_admin,
            teams_with_admin_parents=teams_with_admin_parents,
            teams=teams_with_any,
            teams_parents=teams_with_any_parents,
        )

        return RepositoryInfo(
            basic=basic_info,
            access=repository_access,
            security_and_analysis=security_analysis,
            default_branch_protection=default_branch_protection,
        )


@dataclass
class BasicRepositoryInfo:
    name: str
    visibility: str
    description: Optional[str]
    license: Optional[str]
    delete_branch_on_merge: bool


@dataclass
class SecurityAndAnalysisInfo:
    secret_scanning_status: Optional[str] = None
    secret_scanning_validity_checks: Optional[str] = None
    push_protection_status: Optional[str] = None
    advanced_security: Optional[str] = None
    non_provider_patterns: Optional[str] = None


@dataclass
class BranchProtectionInfo:
    enabled: bool
    allow_force_pushes: bool
    enforce_admins: bool
    required_signatures: bool
    dismiss_stale_reviews: bool
    require_code_owner_reviews: bool
    require_last_push_approval: bool
    required_approving_review_count: int


@dataclass
class RepositoryAccess:
    teams_with_admin: List[str]
    teams_with_admin_parents: List[str]
    teams: List[str]
    teams_parents: List[str]


@dataclass
class RepositoryInfo:
    basic: BasicRepositoryInfo
    access: RepositoryAccess
    security_and_analysis: Optional[SecurityAndAnalysisInfo] = None
    default_branch_protection: Optional[BranchProtectionInfo] = None
