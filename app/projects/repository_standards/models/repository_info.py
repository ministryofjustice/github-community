import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from app.projects.repository_standards.clients.github_client import (
    GitHubApiError,
    GitHubClient,
)

logger = logging.getLogger(__name__)


class RepositoryInfoFactory:
    @staticmethod
    def _get_code_scanning_alert_result(repo, github_client):
        try:
            alerts = github_client.get_open_code_scanning_alerts(repo.name)
            count = sum(
                1
                for alert in alerts
                if alert.get("state") == "open"
                and (
                    ((alert.get("rule") or {}).get("security_severity_level") or "")
                    .lower()
                    in {"high", "critical"}
                )
            )
            metadata = [
                {"state": alert.get("state"), "created_at": alert.get("created_at")}
                for alert in alerts
            ]
            return count, False, metadata
        except Exception as error:
            no_analysis_found = (
                isinstance(error, GitHubApiError)
                and error.status_code == 404
                and error.message.strip().casefold() == "no analysis found"
            )
            if no_analysis_found and RepositoryInfoFactory._code_scanning_is_not_applicable(
                repo, github_client
            ):
                return 0, True, []
            logger.debug("Error getting Code Scanning alerts: %s", error)
            return None, False, None

    @staticmethod
    def _code_scanning_is_not_applicable(repo, github_client) -> bool:
        try:
            default_setup = github_client.get_code_scanning_default_setup(repo.name)
            return (
                default_setup.get("state") == "configured"
                and default_setup.get("languages") == []
                and github_client.get_repository_languages(repo.name) == {}
            )
        except Exception as error:
            logger.debug("Unable to confirm Code Scanning is not applicable: %s", error)
            return False

    @staticmethod
    def _get_effective_branch_rulesets(rules, details_by_id, repo_name, github_client):
        qualifying = {"pull_request": [], "required_signatures": []}
        unknown = {"pull_request": False, "required_signatures": False}
        failed_ids = set()
        for rule in rules:
            rule_type = rule.get("type")
            if rule_type not in qualifying:
                continue
            ruleset_id = rule.get("ruleset_id")
            if ruleset_id is None or ruleset_id in failed_ids:
                unknown[rule_type] = True
                continue
            try:
                if ruleset_id not in details_by_id:
                    details_by_id[ruleset_id] = github_client.get_repository_ruleset(
                        repo_name, ruleset_id
                    )
                details = details_by_id[ruleset_id]
                if details.get("target") in {"repository", "tag", "push"}:
                    continue
                if details.get("target") != "branch":
                    unknown[rule_type] = True
                    continue
                if details.get("enforcement") is None or details.get("bypass_actors") is None:
                    unknown[rule_type] = True
                    continue
                if details.get("enforcement") == "active" and details.get("bypass_actors") == []:
                    qualifying[rule_type].append(rule.get("parameters", {}))
            except Exception as error:
                failed_ids.add(ruleset_id)
                unknown[rule_type] = True
                logger.debug("Error getting branch ruleset %s: %s", ruleset_id, error)

        result = BranchRulesetInfo(enabled=bool(rules))
        reviews = qualifying["pull_request"]
        if reviews:
            result.pull_request_enforcement = "active"
            result.pull_request_bypass_actors_length = 0

        counts = [
            parameters["required_approving_review_count"]
            for parameters in reviews
            if parameters.get("required_approving_review_count") is not None
        ]
        result.pull_request_required_approving_review_count = max(counts) if counts else None
        for parameter, field_name in (
            ("require_last_push_approval", "pull_request_require_last_push_approval"),
            ("require_code_owner_review", "pull_request_require_code_owner_review"),
            ("dismiss_stale_reviews_on_push", "pull_request_dismiss_stale_reviews_on_push"),
        ):
            values = [parameters.get(parameter) for parameters in reviews]
            value = (
                True if True in values
                else None if unknown["pull_request"] or None in values
                else False
            )
            setattr(result, field_name, value)

        signing_enforced = (
            True if qualifying["required_signatures"]
            else None if unknown["required_signatures"]
            else False
        )
        result.required_signatures_ruleset_enforced_without_bypass = signing_enforced
        if signing_enforced:
            result.required_signatures_enforcement = "active"
            result.required_signatures_ruleset_bypass_actors_length = 0
        return result

    @staticmethod
    def _get_repository_branch_ruleset_status(
        rules, details_by_id, repo_name, github_client
    ) -> tuple[bool, bool]:
        repository_branch_rulesets = []
        for ruleset_id in {rule.get("ruleset_id") for rule in rules}:
            if ruleset_id is None:
                raise ValueError("Applicable rule has no ruleset ID")
            sources = {
                rule.get("ruleset_source_type")
                for rule in rules
                if rule.get("ruleset_id") == ruleset_id
            }
            if len(sources) == 1 and sources <= {"Organization", "Enterprise"}:
                continue
            details = details_by_id.get(ruleset_id)
            if details is None:
                details = github_client.get_repository_ruleset(repo_name, ruleset_id)
                details_by_id[ruleset_id] = details
            source = details.get("source_type")
            if source is None and len(sources) == 1:
                source = next(iter(sources))
            if source in {"Organization", "Enterprise"}:
                continue
            if source != "Repository":
                raise ValueError("Ruleset source could not be verified")
            target = details.get("target")
            if target in {"repository", "tag", "push"}:
                continue
            if target != "branch":
                raise ValueError("Ruleset target could not be verified")
            repository_branch_rulesets.append(details)

        return bool(repository_branch_rulesets), all(
            details.get("enforcement") == "active"
            and details.get("bypass_actors") == []
            for details in repository_branch_rulesets
        )

    @staticmethod
    def from_github_repo(
        repo,
        teams_with_admin,
        teams_with_admin_parents,
        teams_with_any,
        teams_with_any_parents,
        github_client: GitHubClient,
        team_admin_maintainer_counts: Optional[dict[str, int]] = None,
        organisation: str = "ministryofjustice",
    ):
        custom_properties = github_client.get_repository_custom_properties(repo.name)

        basic_info = BasicRepositoryInfo(
            name=repo.name,
            organisation=organisation,
            visibility=repo.visibility,
            description=repo.description,
            default_branch_name=repo.default_branch,
            license=repo.license.key if repo.license else None,
            license_path=getattr(repo.license, "path", None)
            if repo.license
            else None,
            delete_branch_on_merge=repo.delete_branch_on_merge,
            business_unit=custom_properties.get("business-unit"),
        )

        codeowners_file_present = None
        codeowners_file_valid = None
        for codeowners_path in (
            ".github/CODEOWNERS",
            "CODEOWNERS",
            "docs/CODEOWNERS",
        ):
            try:
                codeowners_file = repo.get_contents(
                    codeowners_path, ref=repo.default_branch
                )
                codeowners_file_present = True
                content = getattr(codeowners_file, "decoded_content", None)
                if content is not None:
                    if isinstance(content, bytes):
                        content = content.decode("utf-8", errors="replace")
                    has_owner_rules = any(
                        line.strip() and not line.lstrip().startswith("#")
                        for line in content.splitlines()
                    )
                    try:
                        codeowners_errors = github_client.get_codeowners_errors(
                            repo.name
                        )
                        codeowners_file_valid = (
                            has_owner_rules
                            and codeowners_errors.get("errors") == []
                        )
                    except Exception as e:
                        logger.debug("Error validating CODEOWNERS file: %s", e)
                break
            except Exception as e:
                if getattr(e, "status", None) == 404:
                    codeowners_file_present = False
                    continue
                logger.debug("Error getting CODEOWNERS file: %s", e)
                break
        if codeowners_file_present is False:
            codeowners_file_valid = False

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

        (
            open_high_critical_code_scanning_alerts,
            code_scanning_not_applicable,
            code_scanning_metadata,
        ) = RepositoryInfoFactory._get_code_scanning_alert_result(repo, github_client)

        open_high_critical_dependabot_alerts = None
        dependabot_metadata = None
        try:
            dependabot_alerts = github_client.get_open_dependabot_alerts(repo.name)
            open_high_critical_dependabot_alerts = sum(
                1
                for alert in dependabot_alerts
                if alert.get("state") == "open"
                and (
                    (
                        (alert.get("security_advisory") or {}).get("severity")
                        or ""
                    ).lower()
                    in {"high", "critical"}
                )
            )
            dependabot_metadata = [
                {
                    "state": alert.get("state"),
                    "created_at": alert.get("created_at"),
                    "severity": (
                        (alert.get("security_advisory") or {}).get("severity")
                        or (alert.get("security_vulnerability") or {}).get("severity")
                    ),
                }
                for alert in dependabot_alerts
            ]
        except Exception as e:
            logger.debug("Error getting Dependabot alerts: %s", e)

        open_secret_scanning_count = None
        try:
            secret_alerts = github_client.get_open_secret_scanning_alerts(repo.name)
            open_secret_scanning_count = sum(
                alert["state"] == "open" for alert in secret_alerts
            )
        except Exception as error:
            logger.debug("Secret Scanning collection failed (%s)", type(error).__name__)

        security_alerts = SecurityAlertsInfo(
            open_high_critical_code_scanning_count=(
                open_high_critical_code_scanning_alerts
            ),
            open_high_critical_dependabot_count=(
                open_high_critical_dependabot_alerts
            ),
            code_scanning_not_applicable=code_scanning_not_applicable,
            code_scanning_alerts=code_scanning_metadata,
            dependabot_alerts=dependabot_metadata,
            open_secret_scanning_count=open_secret_scanning_count,
        )

        try:
            raw_protection = repo.get_branch(repo.default_branch).get_protection()
            protection_present = raw_protection is not None
            raw_enforce_admins = getattr(raw_protection, "enforce_admins", None)
            enforce_admins_enabled = (
                raw_enforce_admins
                if isinstance(raw_enforce_admins, bool)
                else getattr(raw_enforce_admins, "enabled", None)
            )
            pr = (
                raw_protection.required_pull_request_reviews
                if raw_protection
                else None
            )
            default_branch_protection = BranchProtectionInfo(
                present=protection_present,
                enforce_admins_enabled=enforce_admins_enabled,
                enabled=getattr(raw_protection, "enabled", False),
                allow_force_pushes=getattr(
                    raw_protection, "allow_force_pushes", False
                ),
                enforce_admins=getattr(raw_protection, "enforce_admins", False),
                required_signatures=getattr(
                    raw_protection, "required_signatures", False
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
            if getattr(e, "status", None) == 404:
                default_branch_protection = BranchProtectionInfo(present=False)
            else:
                default_branch_protection = None
            logger.debug("Error getting default branch protection: %s", e)

        ruleset_details_by_id = {}
        rulesets_response = None
        all_rulesets_enforced_without_bypass = None
        try:
            rulesets_response = github_client.get_branch_rulesets(
                repo.name, repo.default_branch
            )
            default_branch_ruleset = RepositoryInfoFactory._get_effective_branch_rulesets(
                rulesets_response, ruleset_details_by_id, repo.name, github_client
            )
        except Exception as e:
            default_branch_ruleset = None
            logger.debug("Error getting default branch rules: %s", e)

        if rulesets_response is not None:
            try:
                ruleset_ids = {
                    rule.get("ruleset_id")
                    for rule in rulesets_response
                    if rule.get("ruleset_id") is not None
                }
                if not ruleset_ids:
                    all_rulesets_enforced_without_bypass = False
                else:
                    for ruleset_id in ruleset_ids.difference(
                        ruleset_details_by_id
                    ):
                        ruleset_details_by_id[
                            ruleset_id
                        ] = github_client.get_repository_ruleset(
                            repo.name, ruleset_id
                        )

                    all_rulesets_enforced_without_bypass = all(
                        ruleset_details_by_id[ruleset_id].get("enforcement")
                        == "active"
                        and ruleset_details_by_id[ruleset_id].get(
                            "bypass_actors"
                        )
                        == []
                        for ruleset_id in ruleset_ids
                    )
            except Exception as e:
                logger.debug(
                    "Error checking all ruleset enforcement and bypasses: %s", e
                )

        if default_branch_ruleset is not None:
            default_branch_ruleset.all_rulesets_enforced_without_bypass = (
                all_rulesets_enforced_without_bypass
            )
            if rulesets_response is not None:
                try:
                    enabled, enforced = RepositoryInfoFactory._get_repository_branch_ruleset_status(
                        rulesets_response, ruleset_details_by_id, repo.name, github_client
                    )
                    default_branch_ruleset.repository_branch_rulesets_enabled = enabled
                    default_branch_ruleset.repository_branch_rulesets_enforced_without_bypass = enforced
                except Exception as error:
                    logger.debug("Error checking repository branch rulesets: %s", error)

        repository_access = RepositoryAccess(
            teams_with_admin=teams_with_admin,
            teams_with_admin_parents=teams_with_admin_parents,
            teams=teams_with_any,
            teams_parents=teams_with_any_parents,
            team_admin_maintainer_counts=team_admin_maintainer_counts or {},
        )

        return RepositoryInfo(
            basic=basic_info,
            access=repository_access,
            codeowners_file_present=codeowners_file_present,
            codeowners_file_valid=codeowners_file_valid,
            security_and_analysis=security_analysis,
            security_alerts=security_alerts,
            default_branch_protection=default_branch_protection
            or BranchProtectionInfo(),
            default_branch_ruleset=default_branch_ruleset or BranchRulesetInfo(),
        )


@dataclass
class BasicRepositoryInfo:
    name: str
    visibility: str
    delete_branch_on_merge: bool
    default_branch_name: str
    description: Optional[str] = None
    license: Optional[str] = None
    license_path: Optional[str] = None
    business_unit: Optional[str] = None
    organisation: str = "ministryofjustice"


@dataclass
class SecurityAndAnalysisInfo:
    secret_scanning_status: Optional[str] = None
    secret_scanning_validity_checks: Optional[str] = None
    push_protection_status: Optional[str] = None
    advanced_security: Optional[str] = None
    non_provider_patterns: Optional[str] = None


@dataclass
class SecurityAlertsInfo:
    open_high_critical_code_scanning_count: Optional[int] = None
    open_high_critical_dependabot_count: Optional[int] = None
    code_scanning_not_applicable: Optional[bool] = None
    code_scanning_alerts: Optional[list[dict]] = None
    dependabot_alerts: Optional[list[dict]] = None
    open_secret_scanning_count: Optional[int] = None


@dataclass
class BranchProtectionInfo:
    present: Optional[bool] = None
    enforce_admins_enabled: Optional[bool] = None
    enabled: Optional[bool] = None
    allow_force_pushes: Optional[bool] = None
    enforce_admins: Optional[bool] = None
    required_signatures: Optional[bool] = None
    dismiss_stale_reviews: Optional[bool] = None
    require_code_owner_reviews: Optional[bool] = None
    require_last_push_approval: Optional[bool] = None
    required_approving_review_count: Optional[int] = None


@dataclass
class BranchRulesetInfo:
    repository_branch_rulesets_enabled: Optional[bool] = None
    repository_branch_rulesets_enforced_without_bypass: Optional[bool] = None
    all_rulesets_enforced_without_bypass: Optional[bool] = None
    required_signatures_ruleset_enforced_without_bypass: Optional[bool] = None
    enabled: Optional[bool] = None
    pull_request_enforcement: Optional[str] = None
    pull_request_bypass_actors_length: Optional[int] = None
    pull_request_required_approving_review_count: Optional[int] = None
    pull_request_dismiss_stale_reviews_on_push: Optional[bool] = None
    pull_request_require_code_owner_review: Optional[bool] = None
    pull_request_require_last_push_approval: Optional[bool] = None
    required_signatures_enforcement: Optional[str] = None
    required_signatures_ruleset_bypass_actors_length: Optional[int] = None


@dataclass
class RepositoryAccess:
    teams_with_admin: List[str]
    teams_with_admin_parents: List[str]
    teams: List[str]
    teams_parents: List[str]
    team_admin_maintainer_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class RepositoryInfo:
    basic: BasicRepositoryInfo
    access: RepositoryAccess
    codeowners_file_present: Optional[bool] = None
    codeowners_file_valid: Optional[bool] = None
    security_and_analysis: SecurityAndAnalysisInfo = field(
        default_factory=SecurityAndAnalysisInfo
    )
    security_alerts: SecurityAlertsInfo = field(default_factory=SecurityAlertsInfo)
    default_branch_protection: BranchProtectionInfo = field(
        default_factory=BranchProtectionInfo
    )
    default_branch_ruleset: BranchRulesetInfo = field(default_factory=BranchRulesetInfo)

    def to_dict(self):
        return json.loads(json.dumps(self, default=lambda o: o.__dict__))

    @classmethod
    def from_dict(cls, data: dict) -> "RepositoryInfo":
        return cls(
            basic=BasicRepositoryInfo(**data["basic"]),
            access=RepositoryAccess(**data["access"]),
            codeowners_file_present=data.get("codeowners_file_present"),
            codeowners_file_valid=data.get("codeowners_file_valid"),
            security_and_analysis=SecurityAndAnalysisInfo(
                **data.get("security_and_analysis", {})
            ),
            security_alerts=SecurityAlertsInfo(**data.get("security_alerts", {})),
            default_branch_protection=BranchProtectionInfo(
                **data.get("default_branch_protection", {})
            ),
            default_branch_ruleset=BranchRulesetInfo(
                **data.get("default_branch_ruleset", {})
            ),
        )
