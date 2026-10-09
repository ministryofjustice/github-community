"""UK local time for Repository Stats: job dates and the pages' "Last updated" time."""

from datetime import UTC, date, datetime, timedelta, tzinfo

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover
    ZoneInfo = None
    ZoneInfoNotFoundError = Exception


def _last_sunday(year: int, month: int) -> datetime:
    day = datetime(year, month + 1, 1, 1, tzinfo=UTC) - timedelta(days=1)
    return day - timedelta(days=(day.weekday() + 1) % 7)


class _UkFallback(tzinfo):
    """The UK rule since 1996: BST from 01:00 UTC on the last Sunday of March until
    01:00 UTC on the last Sunday of October. Only used if the system has no tz database."""

    def utcoffset(self, dt):
        return self.dst(dt)

    def dst(self, dt):
        if dt is None:
            return timedelta(0)
        start, end = _last_sunday(dt.year, 3), _last_sunday(dt.year, 10)
        as_utc = dt.replace(tzinfo=UTC) if dt.tzinfo is self else dt.astimezone(UTC)
        return timedelta(hours=1) if start <= as_utc < end else timedelta(0)

    def fromutc(self, dt):
        return dt + self.dst(dt.replace(tzinfo=UTC))

    def tzname(self, dt):
        return "BST" if self.dst(dt) else "GMT"


def _london() -> tzinfo:
    try:
        return ZoneInfo("Europe/London")
    except (ZoneInfoNotFoundError, TypeError):
        return _UkFallback()


LONDON = _london()


def to_london(value: datetime) -> datetime:
    """Naive datetimes are treated as UTC (that's how the job stores them)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(LONDON)


def london_date(value: datetime) -> date:
    return to_london(value).date()


def format_last_updated(value: datetime | None) -> tuple[str, str] | None:
    """("25 September 2026", "1:04pm") in UK time, or None if there's no time."""
    if value is None:
        return None
    local = to_london(value)
    hour = local.hour % 12 or 12
    suffix = "am" if local.hour < 12 else "pm"
    return (
        f"{local.day} {local.strftime('%B')} {local.year}",
        f"{hour}:{local.minute:02d}{suffix}",
    )
