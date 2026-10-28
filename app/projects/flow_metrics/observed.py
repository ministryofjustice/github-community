"""Chart projections over observations, never inferred transition timestamps."""

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select

from app.projects.flow_metrics.service import STATUSES, parse_query, validate_chart
from app.projects.flow_metrics.workspace import (
    capture_index,
    capture_order,
    observation_for,
    read_contract,
    require_supported_source,
)
from app.shared.database import db

HISTORICAL = {"flow", "progress", "throughput", "churn", "velocity"}
RECIPES = {
    "historicalCount": "flow", "sprintScope": "progress", "completedScope": "progress",
    "completions": "throughput", "committedScope": "velocity",
    "addedScope": "churn", "removedScope": "churn", "scopeChanges": "churn",
}
SERIES = {
    "sprintScope": "Scope", "completedScope": "Completed", "committedScope": "Committed",
    "addedScope": "Added", "removedScope": "Removed",
}


def historical_metric(chart):
    if chart["metric"] != "custom":
        return chart["metric"] if chart["metric"] in HISTORICAL else None
    if chart["y"] == "completedScope" and chart["x"] == "sprint":
        return "velocity"
    if chart["x"] == "completionDate" and chart["y"] == "count":
        return "throughput"
    return RECIPES.get(chart["y"])


def resolved_filters(chart):
    filters = dict(chart["filters"])
    clauses = parse_query(filters["query"])
    for field, value in clauses:
        if field in filters and field != "query":
            filters[field] = value
    return filters, clauses


def matches(item, filters, clauses):
    available = item["availableFields"]
    for key in ("team", "sprint", "status", "type", "planned"):
        if filters[key] and (key not in available or item[key] != filters[key]):
            return False
    for field, value in clauses:
        if field in {"from", "to", "team", "sprint", "status", "type", "planned"}:
            continue
        if field == "source":
            if value != "Genuine":
                return False
        elif field == "keyword":
            if value.casefold() not in f"{item['id']} {item['reference']} {item['title']}".casefold():
                return False
        elif field not in available:
            return False
        elif field == "title":
            if value.casefold() not in item["title"].casefold():
                return False
        elif field == "is":
            closed = item["status"] == "Done" or item["state"] in {"CLOSED", "MERGED"}
            if closed != (value == "closed"):
                return False
        elif isinstance(item.get(field), list):
            if value not in item[field]:
                return False
        elif item.get(field) != value:
            return False
    return True


def active_items(contract):
    return {
        item["id"]: item for item in contract["items"]
        if not item["archived"] and item["createdDate"] <= contract["capturedAt"][:10]
    }


def history_index():
    index = capture_index()
    ranked = select(
        index,
        func.row_number().over(
            partition_by=index.c.captured_at,
            order_by=[column.desc() for column in capture_order(index)],
        ).label("position"),
    ).subquery()
    return select(
        ranked.c.kind, ranked.c.id, ranked.c.captured_at, ranked.c.source,
    ).where(ranked.c.position == 1).subquery()


def captured_history():
    index = capture_index()
    first, last = db.session.execute(
        select(func.min(index.c.captured_at), func.max(index.c.captured_at))
    ).one()
    return {"from": first.date().isoformat(), "to": last.date().isoformat()} if first else None


def capture_rows(start, end):
    """Include the predecessor, but never read its predecessors' documents."""
    index = history_index()
    lower = datetime.combine(start, time.min, tzinfo=UTC)
    upper = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)
    predecessor = db.session.execute(
        select(index).where(index.c.captured_at < lower)
        .order_by(*(column.desc() for column in capture_order(index))).limit(1)
    ).first()
    if predecessor:
        yield predecessor
    yield from db.session.execute(
        select(index).where(index.c.captured_at >= lower, index.c.captured_at < upper)
        .order_by(*capture_order(index)).execution_options(yield_per=1)
    )


def short_date(value):
    return f"{value.day} {value.strftime('%b')}"


def history_result(chart, history):
    validate_chart(chart)
    require_supported_source()
    metric = historical_metric(chart)
    if metric is None:
        raise ValueError("Choose an observed-history calculation.")
    filters, clauses = resolved_filters(chart)
    start = date.fromisoformat(filters["from"] or history["from"])
    end = date.fromisoformat(filters["to"] or history["to"])
    if start > end or start < date.fromisoformat(history["from"]) or end > date.fromisoformat(history["to"]):
        raise ValueError("Choose dates within the captured observation history.")
    if any(field == "source" and value == "Fictional" for field, value in clauses):
        return {
            "series": [], "rows": [], "tickets": [], "itemStates": {}, "unit": "Items",
            "sampleSize": 0, "unavailable": None, "timeBasis": "observation",
            "captures": [], "note": "", "baselineComplete": None,
        }
    settings = {
        "interval": "weekly", "counting": "events", "value": "count", "additional": "",
        **chart.get("calculation", {}),
    }
    if chart["metric"] in {"flow", "progress"}:
        settings["interval"] = "daily"
    wanted = None
    if chart["metric"] == "custom":
        names = [SERIES.get(chart["y"]), SERIES.get(settings["additional"])]
        wanted = set(filter(None, names)) or None
        if chart["y"] == "scopeChanges":
            wanted = {"Committed", "Added", "Removed"}
    group = chart["group"] if chart["metric"] == "custom" else ""
    category_group = group and group != "scopeChange" and not (metric == "flow" and group == "status")
    buckets = {}
    tickets = {}
    states = {}
    sprints = {}
    captures = []
    previous = None
    daily = None
    known_groups = set()
    known_statuses = set(STATUSES)
    zero_keys = set()

    def point(name, key, label, items, *, observed_at, missing=False, occurrences=False):
        if wanted and name not in wanted:
            return
        grouped = defaultdict(list)
        for item in items:
            if category_group and group not in item["availableFields"]:
                continue
            category = item.get(group, "Not set") if group and group != "scopeChange" else ""
            if metric == "flow":
                series_name = item["status"] if group == "status" or chart["metric"] != "custom" else category or "Historical point-in-time count"
            else:
                series_name = f"{name} · {category}" if category else name
            grouped[series_name].append(item)
        if not grouped:
            if category_group:
                for category in sorted(known_groups):
                    grouped[category if metric == "flow" else f"{name} · {category}"] = []
            else:
                grouped[name] = []
        for series_name, members in grouped.items():
            if missing:
                members = []
            identity = (series_name, key)
            entry = buckets.setdefault(identity, {
                "label": label, "key": key, "value": 0, "ids": [], "stateIds": {}, "stateObservedAt": {},
                "observedAt": observed_at, "timeBasis": "observation",
            })
            entry["observedAt"] = observed_at
            if missing:
                entry["value"] = None
                entry.update(ids=[], stateIds={}, stateObservedAt={})
            elif entry["value"] is not None:
                if settings["counting"] == "tickets" and metric in {"churn", "throughput"}:
                    entry["value"] = len(set(entry["ids"]) | {item["id"] for item in members})
                else:
                    entry["value"] += len(members)
            if entry["value"] is None:
                members = []
            if occurrences:
                entry.setdefault("occurrences", []).extend(item["id"] for item in members)
            for item in members:
                identity = item["id"]
                if identity not in entry["ids"]:
                    entry["ids"].append(identity)
                tickets[identity] = item
                # Only drill-down fields, not complete normalized captures.
                state = {key: item.get(key) for key in (
                    "id", "reference", "title", "url", "repository", "team", "sprint",
                    "actualSprint", "status", "observedStatus", "provenance",
                )}
                state_key = tuple(state.items())
                if state_key not in states:
                    states[state_key] = (str(len(states)), state)
                entry["stateIds"][identity] = states[state_key][0]
                entry["stateObservedAt"][identity] = item["observedAt"]

    def publish_daily(contract):
        observed_date = date.fromisoformat(contract["capturedAt"][:10])
        if not start <= observed_date <= end:
            return
        members = [item for item in active_items(contract).values() if matches(item, filters, clauses)]
        population = list(active_items(contract).values())
        status_known = all("status" in item["availableFields"] for item in population)
        sprint_known = all("sprint" in item["availableFields"] for item in population)
        if settings["interval"] == "weekly":
            endpoint = min(end, start + timedelta(days=((observed_date - start).days // 7 + 1) * 7 - 1))
        else:
            endpoint = observed_date
        key = endpoint.isoformat()
        label = short_date(endpoint)
        group_known = not group or group == "scopeChange" or all(group in item["availableFields"] for item in population)
        complete = group_known
        if metric == "flow" and (group == "status" or chart["metric"] != "custom"):
            complete = complete and status_known
        elif metric == "progress":
            complete = complete and sprint_known and status_known
        zero_keys.discard(key)
        if complete:
            zero_keys.add(key)
        # Point-in-time counts replace earlier observations in the same interval.
        for identity in [identity for identity in buckets if identity[1] == key]:
            del buckets[identity]
        if metric == "flow":
            if group == "status" or chart["metric"] != "custom":
                for status in sorted(known_statuses):
                    point(status, key, label, [item for item in members if item["status"] == status],
                          observed_at=contract["capturedAt"], missing=not status_known)
            else:
                point("Historical point-in-time count", key, label, members,
                      observed_at=contract["capturedAt"], missing=not group_known)
        elif metric == "progress":
            scoped = [item for item in members if item.get("sprintId")]
            point("Scope", key, label, scoped, observed_at=contract["capturedAt"], missing=not sprint_known or not group_known)
            point("Completed", key, label, [item for item in scoped if item["status"] == "Done"],
                  observed_at=contract["capturedAt"], missing=not sprint_known or not status_known or not group_known)

    # Sprint calendars determine supported comparison windows, not membership.
    latest = observation_for(end.isoformat()) if metric in {"churn", "velocity"} else None
    if latest:
        sprints.update({sprint["id"]: sprint for sprint in latest["sprints"]})
    selected_sprints = {
        identity: sprint for identity, sprint in sprints.items()
        if sprint.get("start") and sprint.get("end")
        and sprint["start"] <= end.isoformat() and sprint["end"] >= start.isoformat()
        and (not filters["sprint"] or sprint["name"] == filters["sprint"]
             or (filters["sprint"] == "Firebreak" and identity == "real:122ca265"))
    }
    # A same-day observation is not proof of midnight sprint-start membership.
    baselines = {}

    for row in capture_rows(start, end):
        contract = read_contract(*row)
        captured_date = date.fromisoformat(contract["capturedAt"][:10])
        current = active_items(contract)
        known_statuses.update(item["status"] for item in current.values() if "status" in item["availableFields"])
        if category_group:
            known_groups.update(
                item[group] for item in current.values()
                if group in item["availableFields"] and matches(item, filters, clauses)
            )
        captures.append(contract["capturedAt"])
        sprints.update({sprint["id"]: sprint for sprint in contract["sprints"]})
        selected_sprints.update({
            identity: sprint for identity, sprint in sprints.items()
            if sprint.get("start") and sprint.get("end")
            and sprint["start"] <= end.isoformat() and sprint["end"] >= start.isoformat()
            and (not filters["sprint"] or sprint["name"] == filters["sprint"]
                 or (filters["sprint"] == "Firebreak" and identity == "real:122ca265"))
        })
        if metric in {"flow", "progress"}:
            if daily and daily["capturedAt"][:10] != contract["capturedAt"][:10]:
                publish_daily(daily)
            daily = contract
        if previous is not None and start <= captured_date <= end:
            before = active_items(previous)
            if metric == "throughput":
                completed = [
                    item for identity, item in current.items()
                    if identity in before and before[identity]["status"] != "Done"
                    and item["status"] == "Done"
                    and "status" in before[identity]["availableFields"]
                    and "status" in item["availableFields"]
                    and matches(item, filters, clauses)
                ]
                interval = 1 if settings["interval"] == "daily" else 7
                bucket_start = start + timedelta(days=((captured_date - start).days // interval) * interval)
                bucket_end = min(end, bucket_start + timedelta(days=interval - 1))
                point("Completed", bucket_start.isoformat(),
                      f"{short_date(bucket_start)} to {short_date(bucket_end)}", completed,
                      observed_at=contract["capturedAt"], occurrences=True,
                      missing=any("status" not in item["availableFields"] for item in [*before.values(), *current.values()]))
            if metric == "churn":
                for identity, sprint in selected_sprints.items():
                    if not sprint["start"] <= captured_date.isoformat() <= sprint["end"]:
                        continue
                    for name in ("Added", "Removed"):
                        changes = []
                        for item_id in sorted(before.keys() | current.keys()):
                            old, new = before.get(item_id), current.get(item_id)
                            if any(item is not None and "sprint" not in item["availableFields"] for item in (old, new)):
                                continue
                            old_scope = old.get("sprintId") if old else None
                            new_scope = new.get("sprintId") if new else None
                            changed = old_scope != identity and new_scope == identity if name == "Added" else old_scope == identity and new_scope != identity
                            candidate = new if name == "Added" else old
                            if changed and matches(candidate, filters, clauses):
                                changes.append(candidate)
                        point(name, f"{sprint['start']}:{identity}", sprint["name"], changes,
                              observed_at=contract["capturedAt"], occurrences=True,
                              missing=any("sprint" not in item["availableFields"] for item in [*before.values(), *current.values()]))
        previous = contract
    if daily:
        publish_daily(daily)
    if metric == "velocity" or chart.get("y") == "scopeChanges":
        for identity, sprint in selected_sprints.items():
            baseline = None
            if not wanted or "Committed" in wanted:
                midnight = datetime.combine(date.fromisoformat(sprint["start"]), time.min, tzinfo=UTC)
                index = history_index()
                row = db.session.execute(
                    select(index).where(index.c.captured_at == midnight)
                    .order_by(*(column.desc() for column in capture_order(index))).limit(1)
                ).first()
                baseline = read_contract(*row) if row else None
                baselines[identity] = baseline is not None
            cutoff = min(end, date.fromisoformat(sprint["end"]))
            observed = observation_for(cutoff.isoformat())
            valid_cutoff = observed and observed["capturedAt"][:10] >= sprint["start"]
            label = sprint["name"] + (" (in progress)" if sprint["end"] > end.isoformat() else "")
            for name in ("Committed", "Completed"):
                contract = baseline if name == "Committed" else observed
                missing = contract is None or (name == "Completed" and not valid_cutoff)
                required = {"sprint", "status"} if name == "Completed" else {"sprint"}
                if contract and any(not required.issubset(item["availableFields"]) for item in active_items(contract).values()):
                    missing = True
                    if name == "Committed" and identity in baselines:
                        baselines[identity] = False
                members = [] if missing else [
                    item for item in active_items(contract).values()
                    if item.get("sprintId") == identity and matches(item, filters, clauses)
                    and (name == "Committed" or item["status"] == "Done")
                ]
                # Points and the verified unitless Estimation field are not interchangeable.
                points = settings["value"] == "points" or (chart["metric"] == "velocity" and "calculation" not in chart)
                point(name, f"{sprint['start']}:{identity}", label, [] if points else members,
                      observed_at=contract["capturedAt"] if contract else None,
                      missing=missing or points)
    labels = sorted({entry["key"]: entry["label"] for entry in buckets.values()}.items())
    series = []
    for name in dict.fromkeys(name for name, _ in buckets):
        points = []
        for key, label in labels:
            entry = buckets.get((name, key))
            points.append(entry if entry else {
                "label": label, "key": key, "value": 0 if metric in {"churn", "throughput"} or key in zero_keys else None, "ids": [],
                "timeBasis": "observation", "stateIds": {},
            })
        series.append({"name": name, "points": points})
    result_rows = [{**entry, "series": group["name"]} for group in series for entry in group["points"]]
    used = {identity for entry in result_rows for identity in entry["ids"]}
    state_ids = {state_id for entry in result_rows for state_id in entry["stateIds"].values()}
    unit = "Points" if settings["value"] == "points" or (chart["metric"] == "velocity" and "calculation" not in chart) else "Items completed" if chart["metric"] == "throughput" else "Items"
    has_values = any(entry["value"] is not None for entry in result_rows)
    baseline_complete = all(baselines.values()) if baselines else None
    note = "Points are sample-only." if unit == "Points" else "Observed between captures." if metric in {"churn", "throughput"} else "Observed at captures."
    if baseline_complete is False and unit != "Points":
        note += " Sprint-start baseline unavailable."
    return {
        "series": series, "rows": result_rows, "tickets": [tickets[identity] for identity in sorted(used)],
        "itemStates": {identity: value for identity, value in states.values() if identity in state_ids},
        "unit": unit,
        "sampleSize": len(used),
        "unavailable": None if has_values else "Captured history is insufficient for this calculation.",
        "timeBasis": "observation", "captures": captures, "note": note,
        "baselineComplete": baseline_complete,
    }
