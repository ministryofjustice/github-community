"""Framework-agnostic business logic for repository visibility reporting.

This module must not import Flask or SQLAlchemy so it can be reused as-is
if the application moves to another framework.
"""

import csv
import io
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from urllib.parse import urlencode

from app.projects.repository_stats.services.business_units import (
    BusinessUnitSource,
    business_units_for,
)

VISIBILITIES = ("public", "internal", "private")
EVENT_TYPES = ("changed", "created", "deleted", "archived")
TRANSITIONS = tuple(
    (from_v, to_v) for from_v in VISIBILITIES for to_v in VISIBILITIES if from_v != to_v
)

PAGE_SIZE = 25
DEFAULT_ACTIVITY = "all"
DEFAULT_SORT = "date"

ACTIVITY_OPTIONS = (
    ("all", "All activity"),
    ("changes", "All visibility changes"),
    *(
        (f"{from_v}-to-{to_v}", f"{from_v.capitalize()} to {to_v}")
        for from_v, to_v in TRANSITIONS
    ),
    ("new", "New repositories"),
    ("deleted", "Deleted repositories"),
)
ACTIVITY_LABELS = dict(ACTIVITY_OPTIONS)

SORT_COLUMNS = (
    ("repository", "Repository"),
    ("organisation", "Organisation"),
    ("business_unit", "Business unit"),
    ("activity", "Activity"),
    ("date", "Date"),
    ("by", "By"),
)
SORT_KEYS = tuple(key for key, _ in SORT_COLUMNS)

CSV_HEADERS = ("repository", "organisation", "business_unit", "activity", "date", "by")
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

NOT_KNOWN = "Not known"
NO_BUSINESS_UNIT = "None"


@dataclass(frozen=True)
class VisibilitySnapshot:
    github_id: int
    org: str
    name: str
    visibility: str
    archived: bool
    captured_on: date
    fork: bool = False
    created_at: datetime | None = None
    pushed_at: datetime | None = None


@dataclass(frozen=True)
class VisibilityEvent:
    github_id: int
    org: str
    name: str
    event_type: str
    occurred_on: date
    source: str
    from_visibility: str | None = None
    to_visibility: str | None = None
    actor: str | None = None


@dataclass(frozen=True)
class SnapshotCounts:
    total: int = 0
    public: int = 0
    internal: int = 0
    private: int = 0


@dataclass(frozen=True)
class TransitionCount:
    from_visibility: str
    to_visibility: str
    count: int


@dataclass(frozen=True)
class DateRangeResult:
    from_value: str
    to_value: str
    from_date: date | None
    to_date: date | None
    errors: dict = field(default_factory=dict)
    from_entered: bool = False
    to_entered: bool = False

    @property
    def is_valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class Page:
    items: list
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        if self.total_items == 0:
            return 1
        return (self.total_items + self.page_size - 1) // self.page_size

    @property
    def first_item_number(self) -> int:
        return 0 if self.total_items == 0 else (self.page - 1) * self.page_size + 1

    @property
    def last_item_number(self) -> int:
        return min(self.page * self.page_size, self.total_items)


# Dates and formatting


def format_date(value: date | None) -> str:
    if value is None:
        return ""
    return f"{value.day} {value:%B %Y}"


def changes_heading(filter_applied: bool, date_range: DateRangeResult) -> str | None:
    """None without filters. Otherwise a summary worded from the dates the user entered,
    not the defaults filled in for them."""
    if not filter_applied:
        return None
    if not date_range.is_valid:
        return summary_heading(None, None)
    if date_range.from_entered or date_range.to_entered:
        # The counted period: a blank or too-early 'from' is the earliest snapshot.
        return summary_heading(date_range.from_date, date_range.to_date)
    return "Summary, all dates"


def archived_heading(
    estate_filter_applied: bool, latest_captured_on: date | None
) -> str | None:
    """ "Summary" when org, business unit or name filters are applied (dates don't apply
    to that page). None with no filters or no snapshots."""
    if latest_captured_on is None or not estate_filter_applied:
        return None
    return "Summary"


def summary_heading(from_date: date | None, to_date: date | None) -> str:
    """'Summary, 1 August to 25 September 2026', or with both years when they differ.
    A single day is 'Summary, 1 October 2026'."""
    if from_date is None or to_date is None:
        return "Summary"
    if from_date == to_date:
        return f"Summary, {format_date(to_date)}"
    start = f"{from_date.day} {from_date:%B}"
    if from_date.year != to_date.year:
        start += f" {from_date.year}"
    return f"Summary, {start} to {format_date(to_date)}"


def parse_iso_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def validate_date_range(
    from_value: str | None,
    to_value: str | None,
    default_from: date,
    default_to: date,
    today: date | None = None,
    earliest: date | None = None,
) -> DateRangeResult:
    """Validate 'from'/'to' ISO date strings, falling back to defaults when blank.

    Dates the user enters must be real and not after today, and 'from' must not be after
    'to'. A blank 'from' never comes after an entered 'to': it is moved back to that date
    so a 'to' before the first snapshot gives an empty period, not an error. A valid
    'from' before the earliest snapshot is moved forward to it; from_value keeps what the
    user entered."""
    from_entered = (from_value or "").strip()
    to_entered = (to_value or "").strip()
    from_raw = from_entered or default_from.isoformat()
    to_raw = to_entered or default_to.isoformat()

    from_date = parse_iso_date(from_raw)
    to_date = parse_iso_date(to_raw)
    if not from_entered and from_date and to_date and from_date > to_date:
        from_date = to_date
        from_raw = to_date.isoformat()
    errors: dict = {}

    if from_date is None:
        errors["from"] = "Enter a real 'from' date in the format YYYY-MM-DD"
    elif today and from_date > today:
        errors["from"] = "The 'from' date must be today or in the past"
    if to_date is None:
        errors["to"] = "Enter a real 'to' date in the format YYYY-MM-DD"
    elif today and to_date > today:
        errors["to"] = "The 'to' date must be today or in the past"
    if not errors and from_date > to_date:
        errors["from"] = "The 'from' date must be the same as or before the 'to' date"
    if not errors and earliest and from_date < earliest <= to_date:
        from_date = earliest

    return DateRangeResult(
        from_value=from_raw,
        to_value=to_raw,
        from_date=from_date,
        to_date=to_date,
        errors=errors,
        from_entered=bool(from_entered),
        to_entered=bool(to_entered),
    )


# Query parameters


def parse_only_public(values: Sequence[str]) -> bool:
    """Checkbox with a hidden '0' fallback: absent means the default (checked)."""
    if not values:
        return True
    return "1" in values


def parse_page_number(value: str | None) -> int:
    try:
        return max(1, int(value or "1"))
    except ValueError:
        return 1


def default_direction(sort: str) -> str:
    return "desc" if sort == "date" else "asc"


@dataclass(frozen=True)
class VisibilityFilters:
    org: str = ""
    business_unit: str = ""
    q: str = ""

    @property
    def is_active(self) -> bool:
        return bool(self.org or self.business_unit or self.q)

    def matches(self, org: str, name: str, business_units: Sequence[str]) -> bool:
        if self.org and org != self.org:
            return False
        if self.business_unit and self.business_unit not in business_units:
            return False
        return not self.q or self.q.lower() in name.lower()


@dataclass(frozen=True)
class VisibilityQuery:
    filters: VisibilityFilters = field(default_factory=VisibilityFilters)
    from_value: str = ""
    to_value: str = ""
    activity: str = DEFAULT_ACTIVITY
    sort: str = DEFAULT_SORT
    direction: str = "desc"
    page: int = 1
    only_public: bool = True

    def to_params(self, **overrides) -> dict[str, str]:
        """Non-default parameters, in a stable order, for building links and hidden inputs."""
        query = replace(self, **overrides) if overrides else self
        params = {
            "org": query.filters.org,
            "business_unit": query.filters.business_unit,
            "q": query.filters.q,
            "from": query.from_value,
            "to": query.to_value,
            "activity": "" if query.activity == DEFAULT_ACTIVITY else query.activity,
            "sort": "",
            "dir": "",
            "page": "" if query.page <= 1 else str(query.page),
            "only_public": "" if query.only_public else "0",
        }
        if query.sort != DEFAULT_SORT or query.direction != default_direction(
            DEFAULT_SORT
        ):
            params["sort"] = query.sort
            params["dir"] = query.direction
        return {key: value for key, value in params.items() if value}

    def query_string(self, **overrides) -> str:
        params = self.to_params(**overrides)
        return "?" + urlencode(params) if params else ""

    @property
    def estate_filter_applied(self) -> bool:
        """Organisation, business unit or name set: the filters that apply to both pages."""
        return any((self.filters.org, self.filters.business_unit, self.filters.q))

    @property
    def filter_applied(self) -> bool:
        """Organisation, business unit, name or dates set. Activity, sort and page don't count."""
        return any(
            (
                self.filters.org,
                self.filters.business_unit,
                self.filters.q,
                self.from_value,
                self.to_value,
            )
        )

    def csv_query_string(self, from_value: str, to_value: str) -> str:
        """Every parameter that shapes the activity table, including defaults, so the CSV
        matches what is on screen."""
        params = {
            "org": self.filters.org,
            "business_unit": self.filters.business_unit,
            "q": self.filters.q,
            "from": from_value,
            "to": to_value,
            "activity": self.activity,
            "sort": self.sort,
            "dir": self.direction,
        }
        return "?" + urlencode(params)

    def sort_query_string(self, column: str) -> str:
        if column == self.sort:
            direction = "asc" if self.direction == "desc" else "desc"
        else:
            direction = default_direction(column)
        return self.query_string(sort=column, direction=direction, page=1)

    def aria_sort(self, column: str) -> str:
        if column != self.sort:
            return "none"
        return "ascending" if self.direction == "asc" else "descending"


def parse_visibility_query(
    args: Mapping[str, str], only_public_values: Sequence[str] = ()
) -> VisibilityQuery:
    sort = args.get("sort", DEFAULT_SORT)
    if sort not in SORT_KEYS:
        sort = DEFAULT_SORT
    direction = args.get("dir", "")
    if direction not in ("asc", "desc"):
        direction = default_direction(sort)
    activity = args.get("activity", DEFAULT_ACTIVITY)
    if activity not in ACTIVITY_LABELS:
        activity = DEFAULT_ACTIVITY

    return VisibilityQuery(
        filters=VisibilityFilters(
            org=(args.get("org") or "").strip(),
            business_unit=(args.get("business_unit") or "").strip(),
            q=(args.get("q") or "").strip(),
        ),
        from_value=(args.get("from") or "").strip(),
        to_value=(args.get("to") or "").strip(),
        activity=activity,
        sort=sort,
        direction=direction,
        page=parse_page_number(args.get("page")),
        only_public=parse_only_public(only_public_values),
    )


def parse_archived_query(
    args: Mapping[str, str], only_public_values: Sequence[str] = ()
) -> VisibilityQuery:
    """The archived repositories page only uses organisation, business unit, name and
    the 'only still public' checkbox. Dates, activity, sort and page never apply."""
    query = parse_visibility_query(args, only_public_values)
    return VisibilityQuery(filters=query.filters, only_public=query.only_public)


# Snapshot and event counts


def count_snapshot(snapshots: Iterable[VisibilitySnapshot]) -> SnapshotCounts:
    counts = {visibility: 0 for visibility in VISIBILITIES}
    total = 0
    for snapshot in snapshots:
        total += 1
        if snapshot.visibility in counts:
            counts[snapshot.visibility] += 1
    return SnapshotCounts(total=total, **counts)


def filter_events_in_range(
    events: Iterable[VisibilityEvent], from_date: date, to_date: date
) -> list[VisibilityEvent]:
    return [event for event in events if from_date <= event.occurred_on <= to_date]


def count_transitions(events: Iterable[VisibilityEvent]) -> list[TransitionCount]:
    """Count 'changed' events for all six transitions, in a fixed order (zeros included)."""
    counts = dict.fromkeys(TRANSITIONS, 0)
    for event in events:
        key = (event.from_visibility, event.to_visibility)
        if event.event_type == "changed" and key in counts:
            counts[key] += 1
    return [
        TransitionCount(from_v, to_v, count) for (from_v, to_v), count in counts.items()
    ]


def count_event_type(events: Iterable[VisibilityEvent], event_type: str) -> int:
    return sum(1 for event in events if event.event_type == event_type)


def count_changes(events: Iterable[VisibilityEvent]) -> int:
    return count_event_type(events, "changed")


# Activity table


def business_unit_text(business_units: Sequence[str]) -> str:
    return ", ".join(business_units) or NO_BUSINESS_UNIT


@dataclass(frozen=True)
class ActivityItem:
    github_id: int
    name: str
    org: str
    business_units: tuple[str, ...]
    kind: str
    occurred_on: date
    from_visibility: str | None = None
    to_visibility: str | None = None
    actor: str | None = None
    repository_deleted: bool = False

    @property
    def activity_key(self) -> str:
        if self.kind == "created":
            return "new"
        if self.kind == "deleted":
            return "deleted"
        return f"{self.from_visibility}-to-{self.to_visibility}"

    @property
    def label(self) -> str:
        if self.kind == "created":
            return f"New, created as {self.to_visibility}"
        if self.kind == "deleted":
            return f"Deleted, was {self.from_visibility}"
        return f"{(self.from_visibility or '').capitalize()} to {self.to_visibility}"

    @property
    def by(self) -> str:
        return self.actor or NOT_KNOWN

    @property
    def business_unit_text(self) -> str:
        return business_unit_text(self.business_units)

    @property
    def github_url(self) -> str:
        return f"https://github.com/{self.org}/{self.name}"


def _is_activity_event(event: VisibilityEvent) -> bool:
    if event.event_type == "changed":
        return (event.from_visibility, event.to_visibility) in TRANSITIONS
    if event.event_type == "created":
        return event.to_visibility in VISIBILITIES
    if event.event_type == "deleted":
        return event.from_visibility in VISIBILITIES
    return False


def build_activity_items(
    events: Iterable[VisibilityEvent],
    business_units: BusinessUnitSource,
) -> list[ActivityItem]:
    """Changes, creations and deletions as table rows ('archived' events are not activity)."""
    activity_events = [event for event in events if _is_activity_event(event)]
    deleted_ids = {e.github_id for e in activity_events if e.event_type == "deleted"}
    return [
        ActivityItem(
            github_id=event.github_id,
            name=event.name,
            org=event.org,
            business_units=business_units_for(
                business_units, event.github_id, event.name
            ),
            kind=event.event_type,
            occurred_on=event.occurred_on,
            from_visibility=event.from_visibility,
            to_visibility=event.to_visibility,
            actor=event.actor,
            repository_deleted=event.github_id in deleted_ids,
        )
        for event in activity_events
    ]


def filter_activity(items: Iterable[ActivityItem], activity: str) -> list[ActivityItem]:
    if activity == "changes":
        return [item for item in items if item.kind == "changed"]
    if activity == "all" or activity not in ACTIVITY_LABELS:
        return list(items)
    return [item for item in items if item.activity_key == activity]


_SORT_VALUE: dict[str, Callable[[ActivityItem], object]] = {
    "repository": lambda item: item.name.lower(),
    "organisation": lambda item: item.org.lower(),
    "business_unit": lambda item: item.business_unit_text.lower(),
    "activity": lambda item: item.label.lower(),
    "date": lambda item: item.occurred_on,
    "by": lambda item: item.by.lower(),
}


def sort_activity(
    items: Iterable[ActivityItem],
    sort: str = DEFAULT_SORT,
    direction: str = "desc",
    organisation_names: Mapping[str, str] | None = None,
) -> list[ActivityItem]:
    """Sort by the chosen column; ties fall back to newest first, then repository name.
    Organisations sort by the name shown (organisation_names by login, else the login)."""
    key = _SORT_VALUE.get(sort, _SORT_VALUE[DEFAULT_SORT])
    if sort == "organisation" and organisation_names:
        key = lambda item: (organisation_names.get(item.org) or item.org).lower()
    ordered = sorted(items, key=lambda item: item.name.lower())
    ordered.sort(key=lambda item: item.occurred_on, reverse=True)
    ordered.sort(key=key, reverse=direction == "desc")
    return ordered


def paginate(items: Sequence, page: int = 1, page_size: int = PAGE_SIZE) -> Page:
    """Slice one page, clamping the page number into the valid range."""
    if page_size < 1:
        raise ValueError("page_size must be at least 1")
    total_items = len(items)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    page = min(max(1, page), total_pages)
    start = (page - 1) * page_size
    return Page(
        items=list(items[start : start + page_size]),
        page=page,
        page_size=page_size,
        total_items=total_items,
    )


def page_numbers(page: Page, window: int = 2) -> list[int | None]:
    """Page numbers to show in pagination, with None for an ellipsis."""
    last = page.total_pages
    shown = {1, last, *range(page.page - window, page.page + window + 1)}
    numbers: list[int | None] = []
    previous = 0
    for number in sorted(n for n in shown if 1 <= n <= last):
        if number - previous > 1:
            numbers.append(None)
        numbers.append(number)
        previous = number
    return numbers


# CSV


def csv_safe(value: str) -> str:
    """Stop spreadsheet apps treating a cell as a formula."""
    if value and value.startswith(CSV_FORMULA_PREFIXES):
        return "'" + value
    return value


def activity_csv(items: Iterable[ActivityItem]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADERS)
    for item in items:
        writer.writerow(
            csv_safe(value)
            for value in (
                item.name,
                item.org,
                item.business_unit_text,
                item.label,
                item.occurred_on.isoformat(),
                item.by,
            )
        )
    return buffer.getvalue()


def activity_csv_filename(from_date: date, to_date: date) -> str:
    return f"repository-activity-{from_date.isoformat()}-to-{to_date.isoformat()}.csv"


# Reconstructing visibility over time


@dataclass(frozen=True)
class RepositoryState:
    github_id: int
    org: str
    name: str
    visibility: str
    archived: bool


def _state_from_snapshot(snapshot: VisibilitySnapshot) -> RepositoryState:
    return RepositoryState(
        snapshot.github_id,
        snapshot.org,
        snapshot.name,
        snapshot.visibility,
        snapshot.archived,
    )


def apply_event(states: dict[int, RepositoryState], event: VisibilityEvent) -> None:
    current = states.get(event.github_id)
    if event.event_type in ("changed", "created") and event.to_visibility:
        if current is None:
            states[event.github_id] = RepositoryState(
                event.github_id, event.org, event.name, event.to_visibility, False
            )
        else:
            states[event.github_id] = replace(current, visibility=event.to_visibility)
    elif event.event_type == "deleted":
        states.pop(event.github_id, None)
    elif event.event_type == "archived" and current is not None:
        states[event.github_id] = replace(current, archived=True)


# Archived public repositories


@dataclass(frozen=True)
class ArchivedRepository:
    github_id: int
    name: str
    org: str
    business_units: tuple[str, ...]
    visibility: str
    first_archived_on: date | None
    pushed_at: datetime | None
    fork: bool = False

    @property
    def still_public(self) -> bool:
        return self.visibility == "public"

    @property
    def business_unit_text(self) -> str:
        return business_unit_text(self.business_units)

    @property
    def github_url(self) -> str:
        return f"https://github.com/{self.org}/{self.name}"


@dataclass(frozen=True)
class ArchivedProgress:
    total: int
    made_internal: int

    @property
    def percent(self) -> int:
        if self.total == 0:
            return 0
        return (self.made_internal * 100 + self.total // 2) // self.total


def archived_public_repositories(
    earliest: Sequence[VisibilitySnapshot],
    earliest_date: date,
    events: Sequence[VisibilityEvent],
    latest: Sequence[VisibilitySnapshot],
    first_archived_on: Mapping[int, date],
    business_units: BusinessUnitSource,
) -> list[ArchivedRepository]:
    """Repositories that were archived and public at the earliest snapshot, or were archived
    while public afterwards. Their current state comes from the latest snapshot; repositories
    missing from it (deleted) are left out."""
    in_scope = {
        s.github_id for s in earliest if s.archived and s.visibility == "public"
    }
    archived_on = {}
    states = {s.github_id: _state_from_snapshot(s) for s in earliest}
    for event in sorted(events, key=lambda e: e.occurred_on):
        if event.occurred_on <= earliest_date:
            continue
        apply_event(states, event)
        current = states.get(event.github_id)
        if current and current.archived and current.visibility == "public":
            in_scope.add(event.github_id)
            if event.event_type == "archived":
                archived_on.setdefault(event.github_id, event.occurred_on)

    return [
        ArchivedRepository(
            github_id=snapshot.github_id,
            name=snapshot.name,
            org=snapshot.org,
            business_units=business_units_for(
                business_units, snapshot.github_id, snapshot.name
            ),
            visibility=snapshot.visibility,
            first_archived_on=first_archived_on.get(snapshot.github_id)
            or archived_on.get(snapshot.github_id),
            pushed_at=snapshot.pushed_at,
            fork=snapshot.fork,
        )
        for snapshot in latest
        if snapshot.github_id in in_scope
    ]


def archived_progress(repositories: Iterable[ArchivedRepository]) -> ArchivedProgress:
    repositories = list(repositories)
    return ArchivedProgress(
        total=len(repositories),
        made_internal=sum(
            1 for repository in repositories if repository.visibility == "internal"
        ),
    )


def sort_archived(
    repositories: Iterable[ArchivedRepository],
) -> list[ArchivedRepository]:
    """Still-public first, then oldest archived date, then name."""
    return sorted(
        repositories,
        key=lambda r: (
            not r.still_public,
            r.first_archived_on is None,
            r.first_archived_on or date.max,
            r.name.lower(),
        ),
    )
