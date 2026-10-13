"""Record every repository's visibility for Repository Stats.

Run as: python3 -m app.projects.repository_stats.jobs.record_repository_visibility

For each configured organisation, the job lists every repository, compares the list with
the organisation's latest snapshot, writes the events (changed, created, deleted,
archived) and saves today's snapshot. A second run on the same day updates today's
snapshot rather than adding another one. The whole run is one transaction: if any
organisation's repository list fails, nothing is written apart from a "failed" job-run
row.

It also records which teams can access each repository and the organisation's display
name (for the Repository overview, and team access for business units). Both are best
effort: if they can't be fetched, the error is logged, the organisation's previous data
is kept, and the visibility snapshot is still saved.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.app import create_app
from app.projects.repository_stats.clients.github_client import GitHubAppClient
from app.projects.repository_stats.config.collection_config import (
    RECORD_VISIBILITY_JOB_NAME,
    OrgInstallation,
    org_installations,
)
from app.projects.repository_stats.repositories.visibility_repository import (
    VisibilityRepository,
)
from app.projects.repository_stats.services.github_inventory import (
    CountingGetter,
    GitHubGetter,
    GitHubInventoryError,
    OrganisationProfile,
    RepositoryRecord,
    fetch_org_profile,
    fetch_org_repositories,
)
from app.projects.repository_stats.services.github_teams import (
    TeamAccessRecord,
    fetch_org_team_access,
)
from app.projects.repository_stats.services.uk_time import london_date
from app.projects.repository_stats.services.visibility_scan import diff_scan
from app.shared.config.app_config import app_config
from app.shared.config.logging_config import configure_logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrgResult:
    org: str
    repositories: int
    events: int
    # None when the teams couldn't be fetched and the previous team data was kept.
    team_access: int | None
    api_calls: int


@dataclass(frozen=True)
class _OrgScan:
    records: list[RepositoryRecord]
    team_access: list[TeamAccessRecord] | None
    api_calls: int
    # None when the organisation couldn't be fetched; its previous row is kept.
    profile: OrganisationProfile | None = None


def _scan_org(client: GitHubGetter, org: str) -> _OrgScan:
    counting = CountingGetter(client)
    records = fetch_org_repositories(counting, org)
    try:
        team_access = fetch_org_team_access(counting, org)
    except Exception:
        logger.exception(
            "Couldn't fetch team access for %s; keeping the previous team data", org
        )
        team_access = None
    try:
        profile = fetch_org_profile(counting, org)
    except Exception:
        logger.exception(
            "Couldn't fetch the display name for %s; keeping the previous one", org
        )
        profile = None
    return _OrgScan(records, team_access, counting.calls, profile)


def _now() -> datetime:
    return datetime.now(UTC)


def record_repository_visibility(
    repository: VisibilityRepository,
    orgs: Sequence[OrgInstallation],
    client_for: Callable[[int], GitHubGetter],
    now: Callable[[], datetime] = _now,
) -> list[OrgResult]:
    session = repository.db_session
    started_at = now()
    captured_on = london_date(started_at)
    run = repository.start_job_run(RECORD_VISIBILITY_JOB_NAME, started_at)
    session.commit()

    try:
        # Fetch everything first, so a GitHub failure can't leave a half-written run.
        scans = {
            org.org: _scan_org(client_for(org.installation_id), org.org) for org in orgs
        }
        results = []
        for org, scan in scans.items():
            previous = repository.find_latest_snapshots_for_org(org)
            if previous and not scan.records:
                raise GitHubInventoryError(
                    f"GitHub returned no repositories for {org}, which had some before"
                )
            events = diff_scan(previous, scan.records, captured_on)
            repository.save_snapshots(org, captured_on, scan.records)
            repository.add_events(events)
            team_access = scan.team_access
            if team_access == [] and repository.count_team_access_for_org(org):
                # Same safeguard as for repositories: an empty list after a full one is
                # far more likely to be a GitHub or permissions problem than real.
                logger.error(
                    "GitHub returned no team access for %s, which had some before; "
                    "keeping the previous team data",
                    org,
                )
                team_access = None
            if team_access is not None:
                repository.replace_team_access(org, team_access, started_at)
            if scan.profile is not None:
                repository.save_organisation_profile(scan.profile, started_at)
            results.append(
                OrgResult(
                    org,
                    len(scan.records),
                    len(events),
                    None if team_access is None else len(team_access),
                    scan.api_calls,
                )
            )
        run.status = "success"
        run.finished_at = now()
        session.commit()
    except Exception:
        session.rollback()
        try:
            run.status = "failed"
            run.finished_at = now()
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Couldn't record the failed run")
        raise

    for result in results:
        logger.info(
            "Recorded %s repositories, %s events and %s team access rows for %s "
            "(%s GitHub API calls)",
            result.repositories,
            result.events,
            "no new" if result.team_access is None else result.team_access,
            result.org,
            result.api_calls,
        )
    return results


def main() -> None:
    configure_logging(app_config.logging_level)
    logger.info("Running...")
    github_app = app_config.github.app

    def client_for(installation_id: int) -> GitHubAppClient:
        return GitHubAppClient(
            github_app.client_id, github_app.private_key, installation_id
        )

    record_repository_visibility(
        VisibilityRepository(),
        org_installations(github_app.installation_id),
        client_for,
    )
    logger.info("Complete!")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        main()
