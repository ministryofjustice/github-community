from collections.abc import Iterable
from datetime import date, datetime

from sqlalchemy import func, insert
from sqlalchemy.orm import scoped_session

from app.projects.repository_stats.db_models import (
    RepositoryStatsJobRun,
    RepositoryStatsOrganisation,
    RepositoryStatsTeamAccess,
    RepositoryStatsVisibilityEvent,
    RepositoryStatsVisibilitySnapshot,
    db,
)
from app.projects.repository_stats.services.github_inventory import (
    OrganisationProfile,
    RepositoryRecord,
)
from app.projects.repository_stats.services.github_teams import TeamAccessRecord
from app.projects.repository_stats.services.visibility_logic import (
    VisibilityEvent,
    VisibilitySnapshot,
)


def _to_snapshot(row: RepositoryStatsVisibilitySnapshot) -> VisibilitySnapshot:
    return VisibilitySnapshot(
        github_id=row.github_id,
        org=row.org,
        name=row.name,
        visibility=row.visibility,
        archived=row.archived,
        captured_on=row.captured_on,
        fork=row.fork,
        created_at=row.created_at,
        pushed_at=row.pushed_at,
    )


def _to_event(row: RepositoryStatsVisibilityEvent) -> VisibilityEvent:
    return VisibilityEvent(
        github_id=row.github_id,
        org=row.org,
        name=row.name,
        event_type=row.event_type,
        occurred_on=row.occurred_on,
        source=row.source,
        from_visibility=row.from_visibility,
        to_visibility=row.to_visibility,
        actor=row.actor,
    )


class VisibilityRepository:
    """The only visibility component that touches SQLAlchemy; returns plain dataclasses."""

    def __init__(self, db_session: scoped_session | None = None):
        self.db_session = db_session if db_session is not None else db.session

    def find_snapshot_dates(self) -> list[date]:
        rows = (
            self.db_session.query(RepositoryStatsVisibilitySnapshot.captured_on)
            .distinct()
            .order_by(RepositoryStatsVisibilitySnapshot.captured_on)
            .all()
        )
        return [row[0] for row in rows]

    def find_snapshots_on(self, captured_on: date) -> list[VisibilitySnapshot]:
        return self.find_snapshots_on_dates([captured_on]).get(captured_on, [])

    def find_snapshots_on_dates(
        self, dates: Iterable[date]
    ) -> dict[date, list[VisibilitySnapshot]]:
        dates = sorted(set(dates))
        if not dates:
            return {}
        rows = (
            self.db_session.query(RepositoryStatsVisibilitySnapshot)
            .filter(RepositoryStatsVisibilitySnapshot.captured_on.in_(dates))
            .order_by(RepositoryStatsVisibilitySnapshot.name)
            .all()
        )
        result: dict[date, list[VisibilitySnapshot]] = {d: [] for d in dates}
        for row in rows:
            result[row.captured_on].append(_to_snapshot(row))
        return result

    def find_events_between(
        self, from_date: date, to_date: date
    ) -> list[VisibilityEvent]:
        rows = (
            self.db_session.query(RepositoryStatsVisibilityEvent)
            .filter(RepositoryStatsVisibilityEvent.occurred_on >= from_date)
            .filter(RepositoryStatsVisibilityEvent.occurred_on <= to_date)
            .order_by(
                RepositoryStatsVisibilityEvent.occurred_on,
                RepositoryStatsVisibilityEvent.id,
            )
            .all()
        )
        return [_to_event(row) for row in rows]

    def find_first_archived_dates(self) -> dict[int, date]:
        rows = (
            self.db_session.query(
                RepositoryStatsVisibilitySnapshot.github_id,
                func.min(RepositoryStatsVisibilitySnapshot.captured_on),
            )
            .filter(RepositoryStatsVisibilitySnapshot.archived.is_(True))
            .group_by(RepositoryStatsVisibilitySnapshot.github_id)
            .all()
        )
        return {github_id: first_on for github_id, first_on in rows}

    def find_organisations(self) -> list[str]:
        rows = (
            self.db_session.query(RepositoryStatsVisibilitySnapshot.org)
            .distinct()
            .order_by(RepositoryStatsVisibilitySnapshot.org)
            .all()
        )
        return [row[0] for row in rows]

    def find_organisation_display_names(self) -> dict[str, str]:
        """Display names by login, for organisations that have one."""
        rows = self.db_session.query(
            RepositoryStatsOrganisation.login, RepositoryStatsOrganisation.display_name
        ).filter(RepositoryStatsOrganisation.display_name.isnot(None))
        return {login: name for login, name in rows if name}

    def save_organisation_profile(
        self, profile: OrganisationProfile, updated_at: datetime
    ) -> None:
        """Insert or update the organisation's row. The caller commits."""
        row = self.db_session.get(RepositoryStatsOrganisation, profile.login)
        if row is None:
            row = RepositoryStatsOrganisation(login=profile.login)
            self.db_session.add(row)
        row.display_name = profile.display_name
        row.updated_at = updated_at

    def find_last_successful_run_finished_at(self, job_name: str) -> datetime | None:
        return (
            self.db_session.query(func.max(RepositoryStatsJobRun.finished_at))
            .filter(RepositoryStatsJobRun.job_name == job_name)
            .filter(RepositoryStatsJobRun.status == "success")
            .scalar()
        )

    # Writes, used by the visibility job. They don't commit: the job owns the transaction.

    def find_latest_snapshots_for_org(self, org: str) -> list[VisibilitySnapshot]:
        latest = (
            self.db_session.query(
                func.max(RepositoryStatsVisibilitySnapshot.captured_on)
            )
            .filter(RepositoryStatsVisibilitySnapshot.org == org)
            .scalar()
        )
        if latest is None:
            return []
        rows = (
            self.db_session.query(RepositoryStatsVisibilitySnapshot)
            .filter(RepositoryStatsVisibilitySnapshot.org == org)
            .filter(RepositoryStatsVisibilitySnapshot.captured_on == latest)
            .all()
        )
        return [_to_snapshot(row) for row in rows]

    def save_snapshots(
        self, org: str, captured_on: date, records: Iterable[RepositoryRecord]
    ) -> None:
        """Make the org's snapshot for captured_on exactly match records.

        A second run on the same day updates that day's rows in place (the unique key is
        github_id + captured_on), adds new repositories and removes ones that have gone.
        """
        records = {record.github_id: record for record in records}
        existing = {
            row.github_id: row
            for row in self.db_session.query(RepositoryStatsVisibilitySnapshot)
            .filter(RepositoryStatsVisibilitySnapshot.captured_on == captured_on)
            .filter(
                (RepositoryStatsVisibilitySnapshot.org == org)
                | RepositoryStatsVisibilitySnapshot.github_id.in_(list(records))
            )
            .all()
        }
        for github_id, row in existing.items():
            if github_id not in records and row.org == org:
                self.db_session.delete(row)
        for github_id, record in records.items():
            row = existing.get(github_id)
            if row is None:
                row = RepositoryStatsVisibilitySnapshot(
                    github_id=github_id, captured_on=captured_on
                )
                self.db_session.add(row)
            row.org = record.org
            row.name = record.name
            row.visibility = record.visibility
            row.archived = record.archived
            row.fork = record.fork
            row.created_at = record.created_at
            row.pushed_at = record.pushed_at

    def add_events(self, events: Iterable[VisibilityEvent]) -> None:
        self.db_session.add_all(
            RepositoryStatsVisibilityEvent(
                github_id=event.github_id,
                org=event.org,
                name=event.name,
                event_type=event.event_type,
                from_visibility=event.from_visibility,
                to_visibility=event.to_visibility,
                occurred_on=event.occurred_on,
                actor=event.actor,
                source=event.source,
            )
            for event in events
        )

    def count_team_access_for_org(self, org: str) -> int:
        return (
            self.db_session.query(RepositoryStatsTeamAccess)
            .filter(RepositoryStatsTeamAccess.org == org)
            .count()
        )

    def replace_team_access(
        self, org: str, records: Iterable[TeamAccessRecord], recorded_at: datetime
    ) -> None:
        """Make the org's team access rows exactly match records. The caller commits."""
        self.db_session.query(RepositoryStatsTeamAccess).filter(
            RepositoryStatsTeamAccess.org == org
        ).delete(synchronize_session=False)
        self.db_session.add_all(
            RepositoryStatsTeamAccess(
                org=org,
                github_id=record.github_id,
                team_slug=record.team_slug,
                team_name=record.team_name,
                parent_team_slug=record.parent_team_slug,
                permission=record.permission,
                recorded_at=recorded_at,
            )
            for record in records
        )

    def start_job_run(
        self, job_name: str, started_at: datetime
    ) -> RepositoryStatsJobRun:
        run = RepositoryStatsJobRun(
            job_name=job_name, started_at=started_at, status="running"
        )
        self.db_session.add(run)
        return run

    def has_events_from_source(self, source: str) -> bool:
        return (
            self.db_session.query(RepositoryStatsVisibilityEvent.id)
            .filter(RepositoryStatsVisibilityEvent.source == source)
            .first()
            is not None
        )

    # Used by the one-off audit import. They don't commit: the import owns the transaction.

    def find_first_successful_run_started_at(self, job_name: str) -> datetime | None:
        return (
            self.db_session.query(func.min(RepositoryStatsJobRun.started_at))
            .filter(RepositoryStatsJobRun.job_name == job_name)
            .filter(RepositoryStatsJobRun.status == "success")
            .scalar()
        )

    def find_snapshots_for_org_on(
        self, org: str, captured_on: date
    ) -> list[VisibilitySnapshot]:
        rows = (
            self.db_session.query(RepositoryStatsVisibilitySnapshot)
            .filter(RepositoryStatsVisibilitySnapshot.org == org)
            .filter(RepositoryStatsVisibilitySnapshot.captured_on == captured_on)
            .all()
        )
        return [_to_snapshot(row) for row in rows]

    def has_events_on(self, org: str, occurred_on: date, source: str) -> bool:
        return (
            self.db_session.query(RepositoryStatsVisibilityEvent.id)
            .filter(RepositoryStatsVisibilityEvent.org == org)
            .filter(RepositoryStatsVisibilityEvent.occurred_on == occurred_on)
            .filter(RepositoryStatsVisibilityEvent.source == source)
            .first()
            is not None
        )

    def delete_snapshots_for_org(self, org: str, before: date | None) -> int:
        """The org's snapshots, all of them or only those captured before a date."""
        query = self.db_session.query(RepositoryStatsVisibilitySnapshot).filter(
            RepositoryStatsVisibilitySnapshot.org == org
        )
        if before is not None:
            query = query.filter(RepositoryStatsVisibilitySnapshot.captured_on < before)
        return query.delete(synchronize_session=False)

    def delete_events_for_org(
        self, org: str, source: str, before: date | None, also_on: date | None = None
    ) -> int:
        """The org's events from one source: all of them, or those before a date (plus,
        optionally, those on one more date)."""
        query = self.db_session.query(RepositoryStatsVisibilityEvent).filter(
            RepositoryStatsVisibilityEvent.org == org,
            RepositoryStatsVisibilityEvent.source == source,
        )
        if before is not None:
            occurred_on = RepositoryStatsVisibilityEvent.occurred_on
            condition = occurred_on < before
            if also_on is not None:
                condition = condition | (occurred_on == also_on)
            query = query.filter(condition)
        return query.delete(synchronize_session=False)

    def insert_snapshots(
        self, captured_on: date, records: Iterable[RepositoryRecord]
    ) -> None:
        rows = [
            {
                "github_id": record.github_id,
                "org": record.org,
                "name": record.name,
                "visibility": record.visibility,
                "archived": record.archived,
                "fork": record.fork,
                "created_at": record.created_at,
                "pushed_at": record.pushed_at,
                "captured_on": captured_on,
            }
            for record in records
        ]
        if rows:
            self.db_session.execute(insert(RepositoryStatsVisibilitySnapshot), rows)
