"""Record every repository's visibility for Repository Stats.

Run as: python3 -m app.projects.repository_stats.jobs.record_repository_visibility

For each configured organisation, the job lists every repository, compares the list with
the organisation's latest snapshot, writes the events (changed, created, deleted,
archived) and saves today's snapshot. A second run on the same day updates today's
snapshot rather than adding another one. Each organisation is saved in its own
transaction; a failure leaves its previous data intact without discarding other
organisations' successful scans. The overall job still fails if any organisation fails.

It also records which teams can access each repository and the organisation's display
name (for the Repository overview, and team access for business units). Both are best
effort: if they can't be fetched, the error is logged, the organisation's previous data
is kept, and the visibility snapshot is still saved.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter

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
    RequestCounter,
    fetch_org_profile,
    fetch_org_repositories,
)
from app.projects.repository_stats.services.github_teams import (
    MAX_TEAM_ACCESS_WORKERS,
    TeamAccessRecord,
    fetch_org_team_access,
)
from app.projects.repository_stats.services.uk_time import london_date
from app.projects.repository_stats.services.visibility_scan import diff_scan
from app.shared.config.app_config import app_config
from app.shared.config.logging_config import configure_logging
from app.shared.services.github_app_client import GitHubRequestCoordinator

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


def _scan_org(
    org_installation: OrgInstallation,
    client_for: Callable[[int, GitHubRequestCoordinator | None], GitHubGetter],
    workers: int,
    counter: RequestCounter,
) -> _OrgScan:
    coordinator = GitHubRequestCoordinator()
    client = client_for(org_installation.installation_id, coordinator)
    counting = CountingGetter(client, counter)
    try:
        repository_started = perf_counter()
        calls_before_inventory = counting.calls
        records = fetch_org_repositories(counting, org_installation.org)
        repository_seconds = perf_counter() - repository_started
        repository_calls = counting.calls - calls_before_inventory

        team_started = perf_counter()
        team_calls = counting.calls
        try:
            team_access = fetch_org_team_access(
                counting,
                org_installation.org,
                workers=workers,
                client_for_worker=lambda: CountingGetter(
                    client_for(org_installation.installation_id, coordinator),
                    counting.counter,
                ),
            )
        except Exception as error:  # noqa: BLE001 - team access is best effort.
            logger.error(
                "Couldn't fetch team access for %s (error_type=%s); "
                "keeping the previous team data",
                org_installation.org,
                type(error).__name__,
            )
            team_access = None
        team_access_seconds = perf_counter() - team_started
        team_access_calls = counting.calls - team_calls

        try:
            profile = fetch_org_profile(counting, org_installation.org)
        except Exception as error:  # noqa: BLE001 - the profile is best effort.
            logger.error(
                "Couldn't fetch the display name for %s (error_type=%s); "
                "keeping the previous one",
                org_installation.org,
                type(error).__name__,
            )
            profile = None
        logger.info(
            "GitHub collection for %s: repository inventory %.2fs (%s API calls); "
            "team access %.2fs (%s API calls, %s workers)",
            org_installation.org,
            repository_seconds,
            repository_calls,
            team_access_seconds,
            team_access_calls,
            workers,
        )
        return _OrgScan(
            records,
            team_access,
            counting.calls,
            profile,
        )
    finally:
        counting.close()


def _now() -> datetime:
    return datetime.now(UTC)


def record_repository_visibility(
    repository: VisibilityRepository,
    orgs: Sequence[OrgInstallation],
    client_for: Callable[[int, GitHubRequestCoordinator | None], GitHubGetter],
    now: Callable[[], datetime] = _now,
    workers: int = 1,
) -> list[OrgResult]:
    if not 1 <= workers <= MAX_TEAM_ACCESS_WORKERS:
        raise ValueError(
            "Repository Stats team access workers must be between 1 and "
            f"{MAX_TEAM_ACCESS_WORKERS}"
        )
    session = repository.db_session
    started_at = now()
    try:
        run = repository.start_job_run(RECORD_VISIBILITY_JOB_NAME, started_at)
        session.commit()
    except Exception as error:  # noqa: BLE001 - avoid exposing database errors.
        session.rollback()
        logger.error("Couldn't start collection (error_type=%s)", type(error).__name__)
        raise RuntimeError("Couldn't record the collection start") from None

    results: list[OrgResult] = []
    failures: list[tuple[str, bool]] = []
    try:
        for installation in orgs:
            org = installation.org
            counter = RequestCounter()
            org_started = perf_counter()
            outcome = "failed"
            result: OrgResult | None = None
            try:
                org_started_at = now()
                captured_on = london_date(org_started_at)
                org_run = repository.start_job_run(
                    RECORD_VISIBILITY_JOB_NAME, org_started_at, org=org
                )
                session.commit()
                try:
                    scan = _scan_org(installation, client_for, workers, counter)
                    previous = repository.find_latest_snapshots_for_org(org)
                    if previous and not scan.records:
                        logger.error(
                            "GitHub returned no repositories for %s; "
                            "keeping the previous data",
                            org,
                        )
                        raise GitHubInventoryError("Empty repository inventory")
                    events = diff_scan(previous, scan.records, captured_on)
                    repository.save_snapshots(org, captured_on, scan.records)
                    repository.add_events(events)
                    team_access = scan.team_access
                    if team_access == [] and repository.count_team_access_for_org(org):
                        logger.error(
                            "GitHub returned no team access for %s, which had some "
                            "before; keeping the previous team data",
                            org,
                        )
                        team_access = None
                    if team_access is not None:
                        repository.replace_team_access(org, team_access, org_started_at)
                    if scan.profile is not None:
                        repository.save_organisation_profile(
                            scan.profile, org_started_at
                        )
                    result = OrgResult(
                        org,
                        len(scan.records),
                        len(events),
                        None if team_access is None else len(team_access),
                        scan.api_calls,
                    )
                    org_run.status = "success"
                    org_run.finished_at = now()
                    session.commit()
                except Exception as error:  # noqa: BLE001 - continue with other orgs.
                    session.rollback()
                    status_code = getattr(error, "status_code", None)
                    if (
                        not isinstance(status_code, int)
                        or not 100 <= status_code <= 599
                    ):
                        status_code = None
                    logger.error(
                        "Repository Stats collection failed for %s "
                        "(error_type=%s, http_status=%s)",
                        org,
                        type(error).__name__,
                        status_code if status_code is not None else "unavailable",
                    )
                    org_run.status = "failed"
                    org_run.finished_at = now()
                    session.commit()
                    failures.append((org, isinstance(error, GitHubInventoryError)))
                    result = None
                else:
                    outcome = "success"
                    assert result is not None
                    results.append(result)
            finally:
                remaining, reset = counter.rate_limit
                logger.info(
                    "Repository Stats outcome organisation=%s status=%s "
                    "duration_seconds=%.2f api_calls=%s rate_limit_remaining=%s "
                    "rate_limit_reset=%s repositories=%s events=%s team_access_rows=%s",
                    org,
                    outcome,
                    perf_counter() - org_started,
                    counter.calls,
                    remaining if remaining is not None else "unavailable",
                    reset if reset is not None else "unavailable",
                    result.repositories if result else "unavailable",
                    result.events if result else "unavailable",
                    result.team_access
                    if result and result.team_access is not None
                    else "unavailable",
                )
        run.status = "failed" if failures else "success"
        run.finished_at = now()
        session.commit()
    except Exception as error:  # noqa: BLE001 - record an unexpected failure.
        session.rollback()
        logger.error(
            "Couldn't record a collection outcome (error_type=%s)",
            type(error).__name__,
        )
        try:
            run.status = "failed"
            run.finished_at = now()
            session.commit()
        except Exception as recording_error:  # noqa: BLE001 - report the failure safely.
            session.rollback()
            logger.error(
                "Couldn't record the failed run (error_type=%s)",
                type(recording_error).__name__,
            )
        raise RuntimeError("Couldn't record the collection outcome") from None

    if failures:
        failed_orgs = ", ".join(org for org, _ in failures)
        error_type = GitHubInventoryError if failures[0][1] else RuntimeError
        raise error_type(
            f"Repository Stats collection failed for: {failed_orgs}"
        ) from None
    return results


def main() -> None:
    configure_logging(app_config.logging_level)
    logger.info("Running...")
    github_app = app_config.github.app

    def client_for(
        installation_id: int, request_coordinator: GitHubRequestCoordinator | None
    ) -> GitHubAppClient:
        return GitHubAppClient(
            github_app.client_id,
            github_app.private_key,
            installation_id,
            request_coordinator=request_coordinator,
        )

    record_repository_visibility(
        VisibilityRepository(),
        org_installations(github_app.installation_id),
        client_for,
        workers=app_config.github.repository_stats_team_access_workers,
    )
    logger.info("Complete!")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        main()
