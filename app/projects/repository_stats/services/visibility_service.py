"""Framework-agnostic orchestration for the repository visibility page."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from app.projects.repository_stats.config.collection_config import (
    RECORD_VISIBILITY_JOB_NAME,
)
from app.projects.repository_stats.services.business_units import (
    BusinessUnitSource,
    business_units_for,
)
from app.projects.repository_stats.services.overview_logic import (
    Overview,
    RepositoryTeams,
    build_overview,
)
from app.projects.repository_stats.services.uk_time import (
    format_last_updated,
    london_date,
)
from app.projects.repository_stats.services.visibility_logic import (
    ACTIVITY_LABELS,
    ACTIVITY_OPTIONS,
    PAGE_SIZE,
    SORT_COLUMNS,
    ActivityItem,
    ArchivedProgress,
    ArchivedRepository,
    DateRangeResult,
    Page,
    SnapshotCounts,
    TransitionCount,
    VisibilityEvent,
    VisibilityQuery,
    VisibilitySnapshot,
    activity_csv,
    activity_csv_filename,
    archived_heading,
    archived_progress,
    archived_public_repositories,
    build_activity_items,
    changes_heading,
    count_changes,
    count_event_type,
    count_snapshot,
    count_transitions,
    filter_activity,
    filter_events_in_range,
    page_numbers,
    paginate,
    sort_activity,
    sort_archived,
    validate_date_range,
)

DEFAULT_RANGE_DAYS = 30


class VisibilityDataSource(Protocol):
    def find_snapshot_dates(self) -> list[date]: ...

    def find_snapshots_on_dates(
        self, dates: Iterable[date]
    ) -> dict[date, list[VisibilitySnapshot]]: ...

    def find_events_between(
        self, from_date: date, to_date: date
    ) -> list[VisibilityEvent]: ...

    def find_first_archived_dates(self) -> dict[int, date]: ...

    def find_organisations(self) -> list[str]: ...

    def find_organisation_display_names(self) -> dict[str, str]: ...

    def find_last_successful_run_finished_at(
        self, job_name: str
    ) -> datetime | None: ...


class OwnershipSource(Protocol):
    def business_unit_names(self) -> list[str]: ...

    def business_units_by_repository(self) -> BusinessUnitSource: ...

    def teams_by_repository(self) -> RepositoryTeams: ...


@dataclass(frozen=True)
class ChangesSection:
    total_changes: int
    created_count: int
    deleted_count: int
    transitions: list[TransitionCount]
    activity_label: str
    activity_page: Page
    activity_page_numbers: list[int | None]


@dataclass(frozen=True)
class ArchivedSection:
    progress: ArchivedProgress
    repositories: list[ArchivedRepository]
    deadline: str
    # Archived public repositories that match the filters, still public or not.
    matching: int = 0
    # Every tracked archived repository (all orgs, public or not), for client-side
    # filtering. Rows not in shown_ids are rendered hidden.
    tracked: list[ArchivedRepository] = field(default_factory=list)
    shown_ids: frozenset[int] = frozenset()


@dataclass(frozen=True)
class VisibilityPage:
    query: VisibilityQuery
    organisations: list[str]
    business_units: list[str]
    latest_captured_on: date | None
    counts: SnapshotCounts
    date_range: DateRangeResult
    archived: ArchivedSection | None = None
    changes: ChangesSection | None = None
    activity_options: tuple = ACTIVITY_OPTIONS
    sort_columns: tuple = SORT_COLUMNS
    page_size: int = PAGE_SIZE
    # ("25 September 2026", "1:04pm") from the latest successful job run, if there is one.
    last_updated: tuple[str, str] | None = None
    today: date | None = None
    earliest_captured_on: date | None = None
    # Organisation display names by login, where GitHub has one.
    organisation_names: Mapping[str, str] = field(default_factory=dict)

    def organisation_name(self, login: str) -> str:
        """The organisation's display name, or its login if it has none."""
        return self.organisation_names.get(login) or login

    @property
    def archived_heading(self) -> str | None:
        return archived_heading(
            self.query.estate_filter_applied, self.latest_captured_on
        )

    @property
    def date_errors(self) -> dict:
        return self.date_range.errors

    @property
    def changes_heading(self) -> str | None:
        return changes_heading(self.query.filter_applied, self.date_range)


@dataclass(frozen=True)
class OverviewPage:
    overview: Overview
    latest_captured_on: date | None
    last_updated: tuple[str, str] | None = None


@dataclass
class _Context:
    query: VisibilityQuery
    snapshot_dates: list[date]
    date_range: DateRangeResult
    business_units: BusinessUnitSource
    events: list[VisibilityEvent] = field(default_factory=list)
    organisation_names: Mapping[str, str] = field(default_factory=dict)

    def include(self, github_id: int, org: str, name: str) -> bool:
        return self.query.filters.matches(
            org, name, business_units_for(self.business_units, github_id, name)
        )


class VisibilityService:
    def __init__(
        self,
        repository: VisibilityDataSource,
        ownership: OwnershipSource,
        archived_deadline: str = "",
        today: date | None = None,
    ):
        self.repository = repository
        self.ownership = ownership
        self.archived_deadline = archived_deadline
        self.today = today or london_date(datetime.now(tz=UTC))

    def _last_updated(self) -> tuple[str, str] | None:
        return format_last_updated(
            self.repository.find_last_successful_run_finished_at(
                RECORD_VISIBILITY_JOB_NAME
            )
        )

    def _context(self, query: VisibilityQuery) -> _Context:
        dates = self.repository.find_snapshot_dates()
        latest = dates[-1] if dates else self.today
        default_from = (
            dates[0] if dates else latest - timedelta(days=DEFAULT_RANGE_DAYS)
        )
        # From only: up to today. Otherwise a blank 'to' means the latest snapshot.
        default_to = self.today if query.from_value else latest
        date_range = validate_date_range(
            query.from_value,
            query.to_value,
            default_from,
            default_to,
            self.today,
            earliest=dates[0] if dates else None,
        )
        context = _Context(
            query=query,
            snapshot_dates=dates,
            date_range=date_range,
            business_units=self.ownership.business_units_by_repository(),
            organisation_names=self.repository.find_organisation_display_names(),
        )
        bounds = [*dates[:1], *dates[-1:]]
        if date_range.is_valid:
            bounds += [date_range.from_date, date_range.to_date]
        if bounds:
            context.events = self.repository.find_events_between(
                min(bounds), max(bounds)
            )
        return context

    def _activity_items(self, context: _Context) -> list[ActivityItem]:
        in_range = filter_events_in_range(
            context.events, context.date_range.from_date, context.date_range.to_date
        )
        items = build_activity_items(in_range, context.business_units)
        return [
            item
            for item in items
            if context.include(item.github_id, item.org, item.name)
        ]

    def _changes(self, context: _Context) -> ChangesSection:
        query = context.query
        items = self._activity_items(context)
        included_events = [
            e
            for e in filter_events_in_range(
                context.events, context.date_range.from_date, context.date_range.to_date
            )
            if context.include(e.github_id, e.org, e.name)
        ]

        shown = sort_activity(
            filter_activity(items, query.activity),
            query.sort,
            query.direction,
            context.organisation_names,
        )
        activity_page = paginate(shown, query.page, PAGE_SIZE)
        return ChangesSection(
            total_changes=count_changes(included_events),
            created_count=count_event_type(included_events, "created"),
            deleted_count=count_event_type(included_events, "deleted"),
            transitions=count_transitions(included_events),
            activity_label=ACTIVITY_LABELS[query.activity],
            activity_page=activity_page,
            activity_page_numbers=page_numbers(activity_page),
        )

    def _archived(
        self, context: _Context, snapshots: dict[date, list[VisibilitySnapshot]]
    ) -> ArchivedSection:
        dates = context.snapshot_dates
        if not dates:
            return ArchivedSection(ArchivedProgress(0, 0), [], self.archived_deadline)
        earliest, latest = dates[0], dates[-1]
        every_org = archived_public_repositories(
            earliest=snapshots.get(earliest, []),
            earliest_date=earliest,
            events=[e for e in context.events if earliest < e.occurred_on <= latest],
            latest=snapshots.get(latest, []),
            first_archived_on=self.repository.find_first_archived_dates(),
            business_units=context.business_units,
        )
        matching = [r for r in every_org if context.include(r.github_id, r.org, r.name)]
        shown = [r for r in matching if r.still_public or not context.query.only_public]
        return ArchivedSection(
            # Progress is for every organisation; filters only narrow the list.
            progress=archived_progress(every_org),
            repositories=sort_archived(shown),
            deadline=self.archived_deadline,
            matching=len(matching),
            tracked=sort_archived(every_org),
            shown_ids=frozenset(r.github_id for r in shown),
        )

    def get_changes_page(self, query: VisibilityQuery) -> VisibilityPage:
        """The visibility changes page: current totals, change counts and activity."""
        context = self._context(query)
        dates = context.snapshot_dates
        latest = dates[-1] if dates else None
        snapshots = self.repository.find_snapshots_on_dates(dates[-1:])
        counts = count_snapshot(
            s
            for s in snapshots.get(latest, [])
            if context.include(s.github_id, s.org, s.name)
        )
        changes = self._changes(context) if context.date_range.is_valid else None
        if changes is not None and changes.activity_page.page != query.page:
            query = replace(query, page=changes.activity_page.page)

        return VisibilityPage(
            query=query,
            organisations=self.repository.find_organisations(),
            business_units=self.ownership.business_unit_names(),
            latest_captured_on=latest,
            counts=counts,
            date_range=context.date_range,
            changes=changes,
            last_updated=self._last_updated(),
            today=self.today,
            earliest_captured_on=dates[0] if dates else None,
            organisation_names=context.organisation_names,
        )

    def get_overview_page(self) -> OverviewPage:
        """Totals from the latest snapshot, by organisation, business unit and team."""
        dates = self.repository.find_snapshot_dates()
        latest = dates[-1] if dates else None
        snapshots = (
            self.repository.find_snapshots_on_dates([latest]).get(latest, [])
            if latest
            else []
        )
        return OverviewPage(
            overview=build_overview(
                snapshots,
                self.ownership.business_units_by_repository(),
                self.ownership.teams_by_repository(),
                self.repository.find_organisation_display_names(),
            ),
            latest_captured_on=latest,
            last_updated=self._last_updated(),
        )

    def get_archived_page(self, query: VisibilityQuery) -> VisibilityPage:
        """The archived repositories page. Dates never apply, so they are dropped here."""
        query = VisibilityQuery(filters=query.filters, only_public=query.only_public)
        context = self._context(query)
        dates = context.snapshot_dates
        latest = dates[-1] if dates else None
        snapshots = self.repository.find_snapshots_on_dates(dates[:1] + dates[-1:])
        counts = count_snapshot(
            s
            for s in snapshots.get(latest, [])
            if context.include(s.github_id, s.org, s.name)
        )

        return VisibilityPage(
            query=query,
            organisations=self.repository.find_organisations(),
            business_units=self.ownership.business_unit_names(),
            latest_captured_on=latest,
            counts=counts,
            date_range=context.date_range,
            archived=self._archived(context, snapshots),
            last_updated=self._last_updated(),
            organisation_names=context.organisation_names,
        )

    def get_activity_csv(self, query: VisibilityQuery) -> tuple[str, str] | None:
        """(filename, CSV text) for every matching activity row, or None for invalid dates."""
        context = self._context(query)
        if not context.date_range.is_valid:
            return None
        items = sort_activity(
            filter_activity(self._activity_items(context), query.activity),
            query.sort,
            query.direction,
            context.organisation_names,
        )
        filename = activity_csv_filename(
            context.date_range.from_date, context.date_range.to_date
        )
        return filename, activity_csv(items)
