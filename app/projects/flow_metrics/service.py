"""Allowlisted chart definitions and results over complete board observations."""

import math
import re
from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy import select

from app.projects.flow_metrics.collector import BOARD_ID, ESTIMATION_FIELD_ID
from app.projects.flow_metrics.db_models import FlowCollectionRun, FlowSnapshot
from app.shared.database import db

STATUSES = ["Icebox", "TODO", "In Progress", "In Review", "Blocked / On Hold", "Done"]
LAYOUTS = {
    "bar",
    "column",
    "line",
    "area",
    "stacked-bar",
    "stacked-column",
    "scatter",
    "histogram",
    "flow",
    "burnup",
}
METRICS = {
    "custom",
    "cycle",
    "churn",
    "age",
    "status",
    "stuck",
    "throughput",
    "flow",
    "progress",
    "velocity",
}
FIELDS = {
    "status",
    "team",
    "sprint",
    "repository",
    "type",
    "planned",
    "objective",
    "created",
    "completed",
    "reporting", "completionDate", "statusBand", "durationBand", "ticket",
}
CALCULATED_MEASURES = {"cycleTime", "itemAge", "statusDays", "completions", "historicalCount",
    "committedScope", "addedScope", "removedScope", "sprintScope", "completedScope", "scopeChanges"}
CATEGORY_FIELDS = {"status", "team", "sprint", "repository", "type", "planned", "objective"}
MEASURES = {"count", "points", "averagePoints", "estimation", "averageEstimation", "averageCycle", "averageAge"} | CALCULATED_MEASURES
FILTERS = {"team", "sprint", "from", "to", "status", "type", "planned", "query"}
QUERY_FIELDS = {
    "source",
    "is",
    "repository",
    "title",
    "status",
    "sprint",
    "type",
    "team",
    "planned",
    "objective",
    "from",
    "to",
    "priority",
    "refined",
    "assignee",
    "label",
    "milestone",
    "reviewers",
    "blocked-by",
    "blocking",
    "relates-to",
    "parent-issue",
    "sub-issues-progress",
}
METADATA_FIELDS = {
    "assignee",
    "label",
    "milestone",
    "reviewers",
    "blocked-by",
    "blocking",
    "relates-to",
    "parent-issue",
    "sub-issues-progress",
}
QUERY = re.compile(
    r'\s*(?:([a-z][a-z-]*):("(?:[^"\\]|\\["\\])*"|[^\s"]+)|("(?:[^"\\]|\\["\\])*"|[^\s:"]+))\s*'
)
FIELD_NAMES = {
    "status": "Status",
    "team": "Team",
    "sprint": "Sprint",
    "type": "Type",
    "planned": "Planned",
    "objective": "Objective",
    "points": "Points",
    "priority": "Priority",
    "refined": "Refined",
}


def parse_query(query):
    import json

    if not isinstance(query, str) or len(query) > 1000:
        raise ValueError("Keep the filter under 1,000 characters.")
    position = 0
    clauses = []
    while position < len(query.rstrip()):
        match = QUERY.match(query, position)
        if not match:
            raise ValueError('Use field:value or field:"value with spaces".')
        position = match.end()
        field = match[1] or "keyword"
        raw = match[2] or match[3]
        value = json.loads(raw) if raw.startswith('"') else raw
        if not value.strip() or (field != "keyword" and field not in QUERY_FIELDS):
            raise ValueError("Choose a supported field and a non-empty value.")
        clauses.append((field, value))
    return clauses


def validate_chart(chart):
    if not isinstance(chart, dict) or set(chart) - {"calculation"} != {
        "id",
        "name",
        "metric",
        "layout",
        "threshold",
        "x",
        "y",
        "group",
        "filters",
    }:
        raise ValueError("Invalid chart definition.")
    if not isinstance(chart["id"], str) or not re.fullmatch(
        r"[a-zA-Z0-9_-]{1,100}", chart["id"]
    ):
        raise ValueError("Invalid chart ID.")
    if (
        not isinstance(chart["name"], str)
        or not chart["name"].strip()
        or len(chart["name"]) > 80
    ):
        raise ValueError("Enter a chart name of 1 to 80 characters.")
    for key, values in [
        ("metric", METRICS),
        ("layout", LAYOUTS),
        ("x", FIELDS),
        ("y", MEASURES),
        ("group", CATEGORY_FIELDS | {"", "scopeChange"}),
    ]:
        if not isinstance(chart[key], str) or chart[key] not in values:
            raise ValueError("Choose an available chart option.")
    if type(chart["threshold"]) is not int or not 1 <= chart["threshold"] <= 365:
        raise ValueError("Threshold must be a whole number from 1 to 365.")
    filters = chart["filters"]
    if (
        not isinstance(filters, dict)
        or set(filters) != FILTERS
        or any(
            not isinstance(value, str) or len(value) > 1000
            for value in filters.values()
        )
    ):
        raise ValueError("Invalid chart filters.")
    if chart["metric"] == "custom" and chart["layout"] in {"flow", "burnup"} and chart["y"] not in CALCULATED_MEASURES:
        raise ValueError("Choose the matching metric for this layout.")
    validate_calculation(chart)
    clauses = parse_query(filters["query"])
    if any(field == "source" and value not in {"Genuine", "Fictional"} for field, value in clauses):
        raise ValueError("Choose source:Genuine or source:Fictional.")
    dates = {key: filters[key] for key in ("from", "to")}
    for field, value in clauses:
        if field in dates:
            dates[field] = value
        if field == "is" and value not in {"open", "closed"}:
            raise ValueError("Choose open or closed.")
    for value in dates.values():
        if value:
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError()
            except ValueError:
                raise ValueError("Use a valid date in YYYY-MM-DD format.") from None
    if dates["from"] and dates["to"] and dates["from"] > dates["to"]:
        raise ValueError("The From date must be on or before the To date.")


def validate_calculation(chart):
    settings = {"version": 1, "interval": "weekly", "bandWidth": 3, "counting": "events",
        "value": "count", "aggregation": "individual", "minDays": 0, "additional": ""}
    supplied = chart.get("calculation", {})
    if not isinstance(supplied, dict) or set(supplied) - set(settings):
        raise ValueError("Unsupported calculation settings.")
    settings.update(supplied)
    if any(not isinstance(settings[key], str) for key in ("interval", "counting", "value", "aggregation", "additional")):
        raise ValueError("Invalid calculation setting type.")
    if (
        type(settings["version"]) is not int or settings["version"] != 1
        or settings["interval"] not in {"daily", "weekly"}
        or type(settings["bandWidth"]) is not int or not 1 <= settings["bandWidth"] <= 365
        or type(settings["minDays"]) is not int or not 0 <= settings["minDays"] <= 365
        or settings["counting"] not in {"events", "tickets"}
        or settings["value"] not in {"count", "points"}
        or settings["aggregation"] not in {"individual", "count", "sum", "average"}
        or settings["additional"] not in CALCULATED_MEASURES | {""}
    ):
        raise ValueError("Invalid calculation settings.")
    if chart["metric"] != "custom":
        return
    x, y, group, layout = (chart[k] for k in ("x", "y", "group", "layout"))
    duration = y in {"cycleTime", "itemAge", "statusDays"}
    if group == "scopeChange" and y not in {"committedScope", "addedScope", "removedScope", "completedScope", "scopeChanges"}:
        raise ValueError("Scope change grouping requires a sprint scope measure.")
    if y not in CALCULATED_MEASURES:
        if settings["additional"]:
            raise ValueError("Additional measures require a sprint scope calculation.")
        if "calculation" in chart and layout in {"scatter", "histogram", "flow", "burnup"}:
            raise ValueError("Choose a matching calculated measure for this layout.")
        if x not in CATEGORY_FIELDS | {"created", "completed"} and (x, y) not in {("statusBand", "count"), ("completionDate", "count")}:
            raise ValueError("Choose a compatible calculated category and measure.")
        if "calculation" in chart and y.startswith("average") and layout in {"area", "stacked-bar", "stacked-column"}:
            raise ValueError("Averages cannot be stacked.")
        if x == "statusBand" and group:
            raise ValueError("Use Days in current status with Count tickets for grouped bands.")
        return
    if settings["value"] == "points" and (y not in {"committedScope", "completedScope"} or x != "sprint" or group):
        raise ValueError("Historical Points require sprint commitment/completion by Sprint without grouping.")
    if duration:
        if settings["additional"]:
            raise ValueError("Duration measures cannot have additional scope measures.")
        if layout == "scatter":
            if y != "cycleTime" or x != "completionDate" or group:
                raise ValueError("Scatter requires Completion date, Cycle time and no grouping.")
        elif layout == "histogram":
            if y != "cycleTime" or x != "durationBand" or group:
                raise ValueError("Histogram requires Cycle-time band, Cycle time and no grouping.")
        elif layout in {"flow", "burnup"}:
            raise ValueError("Choose bar, column or line for duration calculations.")
        elif x == "ticket":
            if group or settings["aggregation"] != "individual":
                raise ValueError("Ticket requires Individual tickets and no grouping.")
        elif x == "statusBand":
            if y != "statusDays" or settings["aggregation"] != "count":
                raise ValueError("Days-in-status band requires Days in current status and Count tickets.")
        elif x not in CATEGORY_FIELDS or settings["aggregation"] == "individual":
            raise ValueError("Choose a board field and aggregate, or individual Ticket.")
        if settings["aggregation"] == "average" and layout in {"area", "stacked-bar", "stacked-column"}:
            raise ValueError("Averages cannot be stacked.")
        return
    axes = {"completionDate", "reporting"} if y == "completions" else {"sprint"} if y in {"addedScope", "removedScope", "committedScope", "scopeChanges"} else {"sprint", "reporting"} if y == "completedScope" else {"reporting"}
    if x not in axes or layout in {"scatter", "histogram"}:
        raise ValueError("Choose a compatible reporting/sprint axis and layout.")
    if (layout == "flow" and y != "historicalCount") or (layout == "burnup" and y not in {"sprintScope", "completedScope"}):
        raise ValueError("Choose the matching calculated measure for this layout.")
    compatible = {"addedScope", "removedScope"} if y in {"addedScope", "removedScope"} else {"committedScope", "completedScope"} if y == "committedScope" or (y == "completedScope" and x == "sprint") else {"sprintScope", "completedScope"} if y in {"sprintScope", "completedScope"} else set()
    if settings["additional"] and (settings["additional"] not in compatible or settings["additional"] == y):
        raise ValueError("Additional measures must share the sprint baseline and unit.")


def seeds():
    names = [
        ("cycle", "scatter", "Cycle time"),
        ("churn", "stacked-column", "Sprint churn"),
        ("age", "bar", "Work item age"),
        ("status", "column", "Status / WIP"),
        ("stuck", "bar", "Stuck items"),
        ("throughput", "column", "Throughput"),
        ("flow", "flow", "Cumulative flow"),
        ("progress", "burnup", "Sprint progress"),
    ]
    return [
        {
            "id": f"seed-{key}",
            "name": name,
            "metric": key,
            "layout": layout,
            "threshold": 7,
            "x": "status",
            "y": "count",
            "group": "",
            "filters": dict.fromkeys(FILTERS, ""),
        }
        for key, layout, name in names
    ]


def first_observation():
    return db.session.execute(
        select(FlowSnapshot.captured_date)
        .where(FlowSnapshot.board_id == BOARD_ID)
        .order_by(FlowSnapshot.captured_date)
        .limit(1)
    ).scalar_one_or_none()


def observation_at(day=None):
    query = select(FlowSnapshot).where(FlowSnapshot.board_id == BOARD_ID)
    if day:
        query = query.where(FlowSnapshot.captured_date <= day)
    return db.session.execute(
        query.order_by(FlowSnapshot.captured_date.desc()).limit(1)
    ).scalar_one_or_none()


def normalise(snapshot):
    items = []
    for item in snapshot.payload["items"]:
        content = item["content"]
        values = {}
        for field in item["fields"]:
            field_id = field["field"]["id"]
            value = next(
                (
                    field[key]
                    for key in ("name", "title", "text", "number", "date")
                    if key in field
                ),
                None,
            )
            values[field_id] = value
        mapping = snapshot.payload.get("mapping", {})
        mapped = {key: values.get(field_id) for key, field_id in mapping.items()}
        estimate_field = next(
            (field for field in snapshot.payload.get("fields", [])
             if field["id"] == ESTIMATION_FIELD_ID and field.get("dataType") == "NUMBER"),
            None,
        )
        mapped["estimate"] = values.get(ESTIMATION_FIELD_ID) if estimate_field else None
        repository = content.get("repository", {}).get("nameWithOwner", "")
        created = date.fromisoformat(content["createdAt"][:10])
        parent = content.get("parent")
        summary = content.get("subIssuesSummary") or {}
        metadata_values = {
            "assignee": content.get("assignees", []),
            "label": content.get("labels", []),
            "milestone": [(content.get("milestone") or {}).get("title")]
            if content.get("milestone")
            else [],
            "reviewers": sorted(
                set(content.get("reviewRequests", []) + content.get("reviews", []))
            ),
            "blocked-by": content.get("blockedBy", []),
            "blocking": content.get("blocking", []),
            "relates-to": content.get("relatesTo", []),
            "parent-issue": [
                f"{parent['repository']['nameWithOwner']}#{parent['number']}"
            ]
            if parent
            else [],
            "sub-issues-progress": [
                f"{summary['completed']}/{summary['total']} ({summary['percentCompleted']}%)"
            ]
            if summary.get("total")
            else [],
        }
        items.append(
            {
                "id": item["id"],
                "reference": f"{repository}#{content['number']}"
                if content.get("number")
                else "Draft item",
                "url": (
                    f"https://github.com/{repository}/"
                    f"{'pull' if content['__typename'] == 'PullRequest' else 'issues'}/"
                    f"{content['number']}"
                    if content["__typename"] in {"Issue", "PullRequest"}
                    and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
                    and type(content.get("number")) is int
                    and content["number"] > 0
                    else None
                ),
                "title": content["title"],
                "repository": repository or "Draft item",
                "type": mapped.get("type")
                or (content.get("issueType") or {}).get("name")
                or content["__typename"],
                **{
                    key: mapped.get(key) or "Not set"
                    for key, name in FIELD_NAMES.items()
                    if key not in {"points", "type"}
                },
                "points": mapped.get("points"),
                "estimate": mapped.get("estimate"),
                "createdDate": created.isoformat(),
                "state": content.get("state", "DRAFT"),
                "archived": item["archived"],
                **{
                    key: values or ["Not set"]
                    for key, values in metadata_values.items()
                },
            }
        )
    return items


def metadata():
    first = first_observation()
    latest = observation_at()
    items = normalise(latest) if latest else []
    options = {
        field: sorted({item[field] for item in items})
        for field in QUERY_FIELDS - {"is", "title", "from", "to"} - METADATA_FIELDS
        if field in {"repository", "type"}
        or (latest and latest.payload.get("mapping", {}).get(field))
    }
    if latest and latest.payload.get("metadataVersion") == 1:
        options.update(
            {
                field: sorted({value for item in items for value in item[field]})
                for field in METADATA_FIELDS
            }
        )
    run = db.session.execute(
        select(FlowCollectionRun)
        .where(FlowCollectionRun.board_id == BOARD_ID)
        .order_by(FlowCollectionRun.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return {
        "history": {
            "from": first.isoformat()
            if first
            else datetime.now(UTC).date().isoformat(),
            "to": latest.captured_date.isoformat()
            if latest
            else datetime.now(UTC).date().isoformat(),
        },
        "capturedAt": latest.captured_at.isoformat() if latest else None,
        "itemCount": len(items),
        "options": options,
        "lastRun": {"status": run.status, "error": run.error_code} if run else None,
        "stale": not latest or latest.captured_date < datetime.now(UTC).date(),
        "definitionVersion": 1,
    }


def result(chart):
    validate_chart(chart)
    first = first_observation()
    latest = observation_at()
    filters = {**chart["filters"]}
    clauses = parse_query(filters["query"])
    if any(field == "source" and value != "Genuine" for field, value in clauses):
        raise ValueError("Real mode supports only source:Genuine.")
    for field, value in clauses:
        if field in FILTERS and field != "query":
            filters[field] = value
    start = first if first else datetime.now(UTC).date()
    end = latest.captured_date if latest else start
    from_date = date.fromisoformat(filters["from"]) if filters["from"] else start
    to_date = date.fromisoformat(filters["to"]) if filters["to"] else end
    if from_date > to_date or from_date < start or to_date > end:
        raise ValueError("Choose dates within the captured observation history.")
    reporting = observation_at(to_date)
    empty = {
        "series": [],
        "rows": [],
        "unit": "Items",
        "axis": "Board item",
        "sampleSize": 0,
        "tickets": [],
        "from": (from_date - start).days,
        "to": (to_date - start).days,
        "note": "",
        "unavailable": None,
        "definitionVersion": 1,
    }
    if not reporting:
        return {
            **empty,
            "unavailable": "No complete board observation has been collected. Run the collector first.",
        }
    if chart["metric"] == "custom" and (chart["y"] in CALCULATED_MEASURES or chart["x"] in {"reporting", "completionDate", "statusBand", "durationBand", "ticket"}):
        return {**empty, "unavailable": "This calculated recipe requires the combined event workspace; genuine verified historical coverage is not established."}
    if chart["layout"] in {"scatter", "histogram"} and chart["metric"] != "cycle":
        return {
            **empty,
            "unavailable": "Scatter and histogram require Cycle time chart data. Choose Cycle time or another layout.",
        }
    if (
        any(field in METADATA_FIELDS for field, value in clauses)
        and reporting.payload.get("metadataVersion") != 1
    ):
        return {
            **empty,
            "unavailable": "These filters were not collected for this date. Choose a newer date or refresh the board data.",
        }
    if chart["metric"] in {
        "cycle",
        "churn",
        "stuck",
        "throughput",
        "flow",
        "progress",
        "velocity",
    } or (
        chart["metric"] == "custom"
        and (chart["x"] in {"created", "completed"} or chart["y"] == "averageCycle")
    ):
        return {
            **empty,
            "unavailable": "Reliable transition or sprint-start history is not available. Daily snapshots do not prove exact transition dates. No values have been inferred.",
        }
    items = []
    for item in normalise(reporting):
        if item["archived"]:
            continue
        if any(
            filters[key] and filters[key] != item[key]
            for key in ("team", "status", "sprint", "type", "planned")
        ):
            continue
        if any(
            (
                field in {"repository", "objective", "priority", "refined"}
                and item[field] != value
            )
            or (field in METADATA_FIELDS and value not in item[field])
            or (
                field in {"title", "keyword"}
                and value.casefold()
                not in f"{item['reference']} {item['title']}".casefold()
            )
            or (
                field == "is"
                and (item["state"] in {"CLOSED", "MERGED"}) != (value == "closed")
            )
            for field, value in clauses
        ):
            continue
        item["created"] = (date.fromisoformat(item["createdDate"]) - start).days
        item["observedStatus"] = item["status"]
        items.append(item)
    if chart["metric"] == "age" or (
        chart["metric"] == "custom" and chart["y"] == "averageAge"
    ):
        items = [
            item
            for item in items
            if item["state"] not in {"CLOSED", "MERGED"} and item["status"] != "Done"
        ]
        if any(item["type"] == "DraftIssue" for item in items):
            return {
                **empty,
                "unavailable": "Age includes draft items whose conversion history is not established. Filter to repository issues or pull requests.",
            }
    if (
        chart["metric"] == "custom"
        and chart["y"] in {"points", "averagePoints"}
        and any(
            type(item["points"]) not in {float, int}
            or not math.isfinite(item["points"])
            for item in items
        )
    ):
        return {
            **empty,
            "unavailable": "Some matching items have no numeric Points value. Missing estimates are not treated as zero.",
        }

    available_count = len(items)
    if chart["metric"] == "custom" and chart["y"] in {"estimation", "averageEstimation"}:
        items = [
            item for item in items
            if type(item["estimate"]) in {int, float} and math.isfinite(item["estimate"])
        ]
        if not items:
            return {**empty, "unavailable": "No matching tickets have a captured numeric Estimation value from the verified field."}

    def point(label, value, matches, ticket_id=None):
        return {
            "label": str(label),
            "value": value,
            "ids": [item["id"] for item in matches],
            **({"ticketId": ticket_id} if ticket_id else {}),
        }

    groups = defaultdict(list)
    if chart["metric"] == "age":
        series = [
            {
                "name": "Work item age",
                "points": [
                    point(
                        f"{item['title']} ({item['reference']})",
                        (
                            reporting.captured_date
                            - date.fromisoformat(item["createdDate"])
                        ).days,
                        [item],
                        ticket_id=item["id"],
                    )
                    for item in items
                ],
            }
        ]
        unit, axis = "Calendar days", "Board item"
    else:
        x = "status" if chart["metric"] == "status" else chart["x"]
        group = chart["group"] if chart["metric"] == "custom" else ""
        measure = chart["y"] if chart["metric"] == "custom" else "count"
        for item in items:
            groups[item[group] if group else ""].append(item)
        categories = sorted({item[x] for item in items})
        if (
            len(categories) > 200
            or len(groups) > 20
            or len(categories) * len(groups) > 2000
        ):
            raise ValueError(
                "Too many chart groups. Narrow the filters (200 categories, 20 series and 2,000 points maximum)."
            )
        series = []
        for name, members in sorted(groups.items()):
            points = []
            for category in categories:
                matches = [item for item in members if item[x] == category]
                value = len(matches)
                if measure in {"points", "averagePoints", "estimation", "averageEstimation"}:
                    field = "estimate" if measure in {"estimation", "averageEstimation"} else "points"
                    value = sum(item[field] for item in matches) if matches else None
                    if measure in {"averagePoints", "averageEstimation"}:
                        value = round(value / len(matches), 2) if matches else None
                if measure == "averageAge":
                    value = (
                        round(
                            sum(
                                (
                                    reporting.captured_date
                                    - date.fromisoformat(item["createdDate"])
                                ).days
                                for item in matches
                            )
                            / len(matches),
                            2,
                        )
                        if matches
                        else None
                    )
                points.append(point(category, value, matches))
            series.append(
                {
                    "name": str(name)
                    if group
                    else "Status"
                    if chart["metric"] == "status"
                    else "Sum of Estimation"
                    if measure == "estimation"
                    else "Average Estimation"
                    if measure == "averageEstimation"
                    else measure,
                    "points": points,
                }
            )
        unit = (
            "Calendar days"
            if measure == "averageAge"
            else "Points"
            if measure in {"points", "averagePoints"}
            else "Estimation"
            if measure == "estimation"
            else "Estimation per item"
            if measure == "averageEstimation"
            else "Items"
        )
        axis = x.capitalize()
    note = f"Observed {reporting.captured_at.isoformat()}. Current fields at that observation, not inferred transition history. Archived items retained in storage but excluded here."
    rows = [{**p, "series": s["name"]} for s in series for p in s["points"]]
    return {
        **empty,
        "series": series,
        "rows": rows,
        "tickets": items,
        "unit": unit,
        "axis": axis,
        "sampleSize": len({key for row in rows for key in row["ids"]}),
        "note": note,
        "coverageText": (
            f"{len(items)} of {available_count} matching tickets have numeric Estimation; {available_count - len(items)} excluded."
            if len(items) != available_count else ""
        ),
    }
