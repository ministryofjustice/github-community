"""Compare a new repository scan with the previous snapshot and work out the events."""

from collections.abc import Iterable
from datetime import date

from app.projects.repository_stats.services.github_inventory import RepositoryRecord
from app.projects.repository_stats.services.visibility_logic import (
    VisibilityEvent,
    VisibilitySnapshot,
)

SCAN_SOURCE = "scan"


def diff_scan(
    previous: Iterable[VisibilitySnapshot],
    current: Iterable[RepositoryRecord],
    occurred_on: date,
) -> list[VisibilityEvent]:
    """Events between the previous snapshot and the current scan, matched on github_id.

    Matching on github_id means a rename is just a new name, not a delete and a create.
    With no previous snapshot (the first ever run) there is nothing to compare, so no
    events: the scan is only the baseline. Actor is never known from a scan.
    """
    before = {snapshot.github_id: snapshot for snapshot in previous}
    if not before:
        return []
    after = {record.github_id: record for record in current}

    def event(record, event_type, from_visibility=None, to_visibility=None):
        return VisibilityEvent(
            github_id=record.github_id,
            org=record.org,
            name=record.name,
            event_type=event_type,
            occurred_on=occurred_on,
            source=SCAN_SOURCE,
            from_visibility=from_visibility,
            to_visibility=to_visibility,
        )

    events: list[VisibilityEvent] = []
    for github_id, record in sorted(after.items(), key=lambda item: item[1].name):
        old = before.get(github_id)
        if old is None:
            events.append(event(record, "created", to_visibility=record.visibility))
            continue
        if old.visibility != record.visibility:
            events.append(event(record, "changed", old.visibility, record.visibility))
        if record.archived and not old.archived:
            events.append(event(record, "archived"))
    for github_id, old in sorted(before.items(), key=lambda item: item[1].name):
        if github_id not in after:
            events.append(event(old, "deleted", from_visibility=old.visibility))
    return events
