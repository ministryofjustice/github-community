"""One-off import of the old visibility audit spreadsheets into Repository Stats.

Run as:
  python3 -m app.projects.repository_stats.jobs.import_visibility_audit_reports DIR [--dry-run]

DIR holds the baseline (list_repos_17aug2026.xlsx), historical-YYYY-MM-DD.xlsx and
Visibility-YYYY-MM-DD.xlsx files. The baseline becomes the first snapshot, every other
file a snapshot for its date, and the differences between consecutive files become events
with source "import". Other files in DIR are ignored.

GitHub ids: the spreadsheets don't have them, so the import lists the organisation's
repositories once (the same call as the visibility job) and matches them by full name.
Repositories GitHub no longer has under that name get a stable negative id, so they never
clash with real ids and the scan job records them as deleted.

The visibility job owns every date from its first successful run onwards: import files
for those dates are skipped. The import adds the events between its last file and that
first run's snapshot, dropping any that run (or a later one the same day) already wrote,
so nothing is lost and nothing is duplicated.

Safe to re-run: each run replaces the organisation's earlier import (its snapshots before
the first scan date and its "import" events) in one transaction. Any error rolls back the
whole run. --dry-run does all the reading and checking and prints counts, but writes
nothing.
"""

import argparse
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from app.app import create_app
from app.projects.repository_stats.clients.github_client import GitHubAppClient
from app.projects.repository_stats.config.collection_config import (
    RECORD_VISIBILITY_JOB_NAME,
    OrgInstallation,
    org_installations,
)
from app.projects.repository_stats.db_models import RepositoryStatsJobRun
from app.projects.repository_stats.repositories.visibility_repository import (
    VisibilityRepository,
)
from app.projects.repository_stats.services.audit_import import (
    IMPORT_SOURCE,
    AuditFile,
    AuditImportError,
    build_plan,
    diff_records,
    event_counts,
    full_name_key,
    read_directory,
)
from app.projects.repository_stats.services.github_inventory import (
    GitHubGetter,
    RepositoryRecord,
    fetch_org_repositories,
)
from app.projects.repository_stats.services.uk_time import london_date
from app.shared.config.app_config import app_config
from app.shared.config.logging_config import configure_logging

logger = logging.getLogger(__name__)

IMPORT_JOB_NAME = "import_visibility_audit_reports"


@dataclass
class OrgImportSummary:
    org: str
    snapshot_rows: dict[date, int] = field(default_factory=dict)
    events: dict[str, int] = field(default_factory=dict)
    bridge_events: dict[str, int] = field(default_factory=dict)
    unresolved_ids: int = 0


@dataclass
class ImportSummary:
    dry_run: bool
    first_scan_date: date | None
    skipped_dates: list[date]
    ignored_files: int
    orgs: list[OrgImportSummary]


def _now() -> datetime:
    return datetime.now(UTC)


def import_visibility_audit_reports(
    repository: VisibilityRepository,
    files: Sequence[AuditFile],
    orgs: Sequence[OrgInstallation],
    client_for: Callable[[int], GitHubGetter],
    dry_run: bool = False,
    ignored_files: int = 0,
    now: Callable[[], datetime] = _now,
) -> ImportSummary:
    session = repository.db_session
    started_at = now()
    installations = {org.org: org.installation_id for org in orgs}
    try:
        first_scan = repository.find_first_successful_run_started_at(
            RECORD_VISIBILITY_JOB_NAME
        )
        first_scan_date = london_date(first_scan) if first_scan else None
        usable = [
            f
            for f in files
            if first_scan_date is None or f.captured_on < first_scan_date
        ]
        skipped = [
            f.captured_on
            for f in files
            if first_scan_date is not None and f.captured_on >= first_scan_date
        ]
        file_orgs = sorted({row.org for f in usable for row in f.rows})
        unknown = [org for org in file_orgs if org not in installations]
        if unknown:
            raise AuditImportError(
                f"No GitHub App installation configured for {', '.join(unknown)}"
            )

        # Everything that can fail (GitHub, the data) happens before any write.
        summaries, writes = [], []
        for org in file_orgs:
            inventory = {
                full_name_key(record.org, record.name): record
                for record in fetch_org_repositories(
                    client_for(installations[org]), org
                )
            }
            plan = build_plan(org, usable, inventory)
            bridge = _bridge_events(repository, org, plan, first_scan_date)
            summaries.append(
                OrgImportSummary(
                    org=org,
                    snapshot_rows={d: len(r) for d, r in plan.snapshots.items()},
                    events=event_counts(plan.events),
                    bridge_events=event_counts(bridge or []),
                    unresolved_ids=plan.unresolved_ids,
                )
            )
            writes.append((plan, bridge))

        if not dry_run:
            for plan, bridge in writes:
                repository.delete_snapshots_for_org(plan.org, before=first_scan_date)
                repository.delete_events_for_org(
                    plan.org,
                    IMPORT_SOURCE,
                    before=first_scan_date,
                    also_on=first_scan_date if bridge is not None else None,
                )
                for captured_on, records in sorted(plan.snapshots.items()):
                    repository.insert_snapshots(captured_on, records)
                repository.add_events(plan.events + (bridge or []))
            session.add(
                RepositoryStatsJobRun(
                    job_name=IMPORT_JOB_NAME,
                    started_at=started_at,
                    finished_at=now(),
                    status="success",
                )
            )
            session.commit()
        else:
            session.rollback()
    except Exception:
        session.rollback()
        raise

    summary = ImportSummary(dry_run, first_scan_date, skipped, ignored_files, summaries)
    _log_summary(summary)
    return summary


def _bridge_events(repository, org, plan, first_scan_date):
    """Events between the last imported file and the visibility job's first snapshot.
    The visibility job runs more than once a day, so a "scan" event already recorded on
    first_scan_date doesn't mean that first run wrote it - events only store a date, not
    which run produced them. So the bridge is always computed, then any event it would
    produce that's already recorded (by the same org/date/source/github_id/type/from/to)
    is dropped, leaving only what's genuinely missing. None when there's nothing left to
    bridge."""
    if first_scan_date is None or not plan.snapshots:
        return None
    scan = repository.find_snapshots_for_org_on(org, first_scan_date)
    if not scan:
        return None
    last_on = max(plan.snapshots)
    before = {r.github_id: r for r in plan.snapshots[last_on]}
    after = {
        s.github_id: RepositoryRecord(
            github_id=s.github_id,
            org=s.org,
            name=s.name,
            visibility=s.visibility,
            archived=s.archived,
            fork=s.fork,
            created_at=s.created_at,
            pushed_at=s.pushed_at,
        )
        for s in scan
    }
    events = diff_records(before, after, last_on, first_scan_date)
    already_recorded = repository.find_event_keys_on(org, first_scan_date, "scan")
    events = [
        e
        for e in events
        if (e.github_id, e.event_type, e.from_visibility, e.to_visibility)
        not in already_recorded
    ]
    return events or None


def _log_summary(summary: ImportSummary) -> None:
    mode = "Dry run, nothing written" if summary.dry_run else "Imported"
    logger.info("%s. Ignored files: %s", mode, summary.ignored_files)
    if summary.first_scan_date:
        logger.info(
            "Visibility job's first run: %s. Skipped file dates: %s",
            summary.first_scan_date.isoformat(),
            ", ".join(d.isoformat() for d in summary.skipped_dates) or "none",
        )
    for org in summary.orgs:
        for captured_on, rows in sorted(org.snapshot_rows.items()):
            logger.info("%s %s: %s repositories", org.org, captured_on, rows)
        logger.info("%s events: %s", org.org, org.events)
        if any(org.bridge_events.values()):
            logger.info(
                "%s events up to the first scan: %s", org.org, org.bridge_events
            )
        logger.info(
            "%s repositories without a current GitHub id: %s",
            org.org,
            org.unresolved_ids,
        )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("directory", type=Path)
    parser.add_argument(
        "--dry-run", action="store_true", help="check and print counts only"
    )
    args = parser.parse_args(argv)

    configure_logging(app_config.logging_level)
    logger.info("Running...")
    files, ignored = read_directory(args.directory)
    github_app = app_config.github.app

    def client_for(installation_id: int) -> GitHubAppClient:
        return GitHubAppClient(
            github_app.client_id, github_app.private_key, installation_id
        )

    import_visibility_audit_reports(
        VisibilityRepository(),
        files,
        org_installations(github_app.installation_id),
        client_for,
        dry_run=args.dry_run,
        ignored_files=len(ignored),
    )
    logger.info("Complete!")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        main()
