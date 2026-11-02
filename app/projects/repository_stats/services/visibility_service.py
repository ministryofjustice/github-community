"""Framework-agnostic orchestration for the repository visibility page."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from typing import Protocol, TypedDict

from app.projects.repository_stats.config.collection_config import (
    DEFAULT_ORG,
    RECORD_VISIBILITY_JOB_NAME,
    SHOW_ALL_ORGANISATIONS_OPTION,
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
    ALL_ORGANISATIONS,
    PAGE_SIZE,
    SORT_COLUMNS,
    ActivityItem,
    ArchivedProgress,
    ArchivedRepository,
    DateRangeResult,
    OrganisationScanState,
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

    def find_snapshot_dates_by_organisation(self) -> dict[str, list[date]]: ...

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

    def find_organisation_scan_states(
        self, job_name: str
    ) -> dict[str, OrganisationScanState]: ...


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
    repository_page: Page
    repository_page_numbers: list[int | None]
    page_ids: frozenset[int]
    # Archived public repositories that match the filters, still public or not.
    matching: int = 0
    # Every tracked archived repository (all orgs, public or not), for client-side
    # filtering and pagination.
    tracked: list[ArchivedRepository] = field(default_factory=list)
    # Progress for each organisation and for ALL_ORGANISATIONS, so the page can switch
    # progress with the Organisation filter without reloading.
    progress_by_organisation: Mapping[str, ArchivedProgress] = field(
        default_factory=dict
    )

    def progress_data(self) -> dict[str, dict[str, int]]:
        return {
            org: {
                "total": progress.total,
                "made_internal": progress.made_internal,
                "percent": progress.percent,
            }
            for org, progress in self.progress_by_organisation.items()
        }


class OrganisationFreshness(TypedDict):
    last_updated: tuple[str, str] | None


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
    organisation_freshness: Mapping[str, OrganisationFreshness] = field(
        default_factory=dict
    )
    default_organisation: str = ""

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
    failed_organisation_updates: Mapping[str, str | None] = field(default_factory=dict)


@dataclass
class _Context:
    query: VisibilityQuery
    snapshot_dates: list[date]
    snapshot_dates_by_organisation: dict[str, list[date]]
    date_range: DateRangeResult
    business_units: BusinessUnitSource
    scan_states: Mapping[str, OrganisationScanState]
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

    def _last_updated(
        self,
        org: str | None = None,
        scan_states: Mapping[str, OrganisationScanState] | None = None,
    ) -> tuple[str, str] | None:
        if org:
            state = scan_states.get(org) if scan_states else None
            return format_last_updated(state.last_successful_at if state else None)
        return format_last_updated(
            self.repository.find_last_successful_run_finished_at(
                RECORD_VISIBILITY_JOB_NAME
            )
        )

    def _context(self, query: VisibilityQuery) -> _Context:
        dates_by_org = self.repository.find_snapshot_dates_by_organisation()
        all_dates = sorted({d for dates in dates_by_org.values() for d in dates})
        dates = (
            dates_by_org.get(query.filters.org, []) if query.filters.org else all_dates
        )
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
            snapshot_dates_by_organisation=dates_by_org,
            date_range=date_range,
            business_units=self.ownership.business_units_by_repository(),
            scan_states=self.repository.find_organisation_scan_states(
                RECORD_VISIBILITY_JOB_NAME
            ),
            organisation_names=self.repository.find_organisation_display_names(),
        )
        # Archived progress includes every org, each with its own history bounds.
        bounds = [*all_dates[:1], *all_dates[-1:]]
        if date_range.is_valid:
            bounds += [date_range.from_date, date_range.to_date]
        if bounds:
            context.events = self.repository.find_events_between(
                min(bounds), max(bounds)
            )
        return context

    def _current_snapshots(
        self, dates_by_org: Mapping[str, list[date]]
    ) -> list[VisibilitySnapshot]:
        """Each organisation's latest snapshot, even when its last scan failed. A
        repository in more than one (transferred while its old organisation's scan
        failed) is kept only from its newest observation."""
        latest_by_org = {org: dates[-1] for org, dates in dates_by_org.items() if dates}
        snapshots_by_date = self.repository.find_snapshots_on_dates(
            latest_by_org.values()
        )
        current: dict[int, tuple[date, VisibilitySnapshot]] = {}
        for captured_on in sorted(snapshots_by_date):
            for snapshot in snapshots_by_date[captured_on]:
                if latest_by_org.get(snapshot.org) == captured_on:
                    current[snapshot.github_id] = (captured_on, snapshot)
        return [snapshot for _, snapshot in current.values()]

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
        first_archived_on = self.repository.find_first_archived_dates()
        # A repository transferred while its old organisation's scan failed is in both
        # organisations' latest snapshots; it belongs to the newer one.
        owner: dict[int, str] = {}
        for org, dates in sorted(
            context.snapshot_dates_by_organisation.items(), key=lambda item: item[1][-1]
        ):
            for s in snapshots.get(dates[-1], []):
                if s.org == org:
                    owner[s.github_id] = org
        every_org = []
        for org, dates in context.snapshot_dates_by_organisation.items():
            earliest, latest = dates[0], dates[-1]
            every_org.extend(
                r
                for r in archived_public_repositories(
                    earliest=[s for s in snapshots.get(earliest, []) if s.org == org],
                    earliest_date=earliest,
                    events=[
                        e
                        for e in context.events
                        if e.org == org and earliest < e.occurred_on <= latest
                    ],
                    latest=[s for s in snapshots.get(latest, []) if s.org == org],
                    first_archived_on=first_archived_on,
                    business_units=context.business_units,
                )
                if owner.get(r.github_id, org) == org
            )
        matching = sort_archived(
            r for r in every_org if context.include(r.github_id, r.org, r.name)
        )
        shown = sort_archived(
            r for r in matching if r.still_public or not context.query.only_public
        )
        repository_page = paginate(shown, context.query.page, PAGE_SIZE)
        progress_by_organisation = {
            org: archived_progress(r for r in every_org if r.org == org)
            for org in context.snapshot_dates_by_organisation
        }
        progress_by_organisation[ALL_ORGANISATIONS] = archived_progress(every_org)
        selected_org = context.query.filters.org
        return ArchivedSection(
            # Progress follows the Organisation filter only; the other filters only
            # narrow the list.
            progress=progress_by_organisation.get(
                selected_org or ALL_ORGANISATIONS, archived_progress([])
            ),
            progress_by_organisation=progress_by_organisation,
            repositories=sort_archived(shown),
            repository_page=repository_page,
            repository_page_numbers=page_numbers(repository_page),
            page_ids=frozenset(r.github_id for r in repository_page.items),
            deadline=self.archived_deadline,
            matching=len(matching),
            tracked=sort_archived(every_org),
        )

    def _default_organisation(self, query: VisibilityQuery) -> VisibilityQuery:
        """When no organisation was requested, default it. An explicit organisation, or
        an explicit "All organisations" while SHOW_ALL_ORGANISATIONS_OPTION is on, is
        never overridden. Prefers DEFAULT_ORG when it has data, falling back to the
        first organisation with data so this still works if DEFAULT_ORG is ever renamed
        or unavailable."""
        if query.filters.org or (
            SHOW_ALL_ORGANISATIONS_OPTION and query.all_organisations
        ):
            return query
        query = replace(query, all_organisations=False)
        organisations = self.repository.find_organisations()
        if not organisations:
            return query
        default = DEFAULT_ORG if DEFAULT_ORG in organisations else organisations[0]
        return replace(query, filters=replace(query.filters, org=default))

    def get_changes_page(self, query: VisibilityQuery) -> VisibilityPage:
        """The visibility changes page: current totals, change counts and activity."""
        query = self._default_organisation(query)
        context = self._context(query)
        dates = context.snapshot_dates
        latest = dates[-1] if dates else None
        counts = count_snapshot(
            s
            for s in self._current_snapshots(context.snapshot_dates_by_organisation)
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
            last_updated=self._last_updated(query.filters.org, context.scan_states),
            today=self.today,
            earliest_captured_on=dates[0] if dates else None,
            organisation_names=context.organisation_names,
        )

    def get_overview_page(self) -> OverviewPage:
        """Totals from each organisation's latest successful snapshot."""
        dates_by_org = self.repository.find_snapshot_dates_by_organisation()
        latest = max(
            (dates[-1] for dates in dates_by_org.values() if dates), default=None
        )
        snapshots = self._current_snapshots(dates_by_org)
        scan_states = self.repository.find_organisation_scan_states(
            RECORD_VISIBILITY_JOB_NAME
        )
        failed_updates = {
            org: formatted[0] if formatted else None
            for org, state in scan_states.items()
            if state.latest_status == "failed"
            for formatted in [format_last_updated(state.last_successful_at)]
        }
        return OverviewPage(
            overview=build_overview(
                snapshots,
                self.ownership.business_units_by_repository(),
                self.ownership.teams_by_repository(),
                self.repository.find_organisation_display_names(),
            ),
            latest_captured_on=latest,
            last_updated=self._last_updated(),
            failed_organisation_updates=failed_updates,
        )

    def get_archived_page(self, query: VisibilityQuery) -> VisibilityPage:
        """The archived repositories page. Dates never apply, so they are dropped here."""
        query = VisibilityQuery(
            filters=query.filters,
            page=query.page,
            only_public=query.only_public,
            all_organisations=query.all_organisations,
        )
        query = self._default_organisation(query)
        context = self._context(query)
        dates = context.snapshot_dates
        latest = dates[-1] if dates else None
        snapshot_bounds = {
            d
            for org_dates in context.snapshot_dates_by_organisation.values()
            for d in (org_dates[0], org_dates[-1])
        }
        snapshots = self.repository.find_snapshots_on_dates(snapshot_bounds)
        counts = count_snapshot(
            s
            for s in self._current_snapshots(context.snapshot_dates_by_organisation)
            if context.include(s.github_id, s.org, s.name)
        )
        freshness: dict[str, OrganisationFreshness] = {
            org: {"last_updated": self._last_updated(org, context.scan_states)}
            for org in context.snapshot_dates_by_organisation
        }
        if SHOW_ALL_ORGANISATIONS_OPTION:
            freshness[ALL_ORGANISATIONS] = {"last_updated": self._last_updated()}

        archived = self._archived(context, snapshots)
        query = replace(query, page=archived.repository_page.page)
        return VisibilityPage(
            query=query,
            organisations=self.repository.find_organisations(),
            business_units=self.ownership.business_unit_names(),
            latest_captured_on=latest,
            counts=counts,
            date_range=context.date_range,
            archived=archived,
            last_updated=self._last_updated(query.filters.org, context.scan_states),
            earliest_captured_on=dates[0] if dates else None,
            organisation_names=context.organisation_names,
            organisation_freshness=freshness,
            default_organisation=self._default_organisation(
                VisibilityQuery()
            ).filters.org
            or "",
        )

    def get_activity_csv(self, query: VisibilityQuery) -> tuple[str, str] | None:
        """(filename, CSV text) for every matching activity row, or None for invalid dates."""
        query = self._default_organisation(query)
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
