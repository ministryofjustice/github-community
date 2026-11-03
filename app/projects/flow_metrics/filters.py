"""Categorical query semantics shared by current and historical observations."""

CATEGORY_FIELDS = {"team", "sprint", "status", "type", "planned", "repository", "objective", "priority", "refined"}


def team_values(filters, clauses):
    values = [value for field, value in clauses if field == "team"]
    return list(dict.fromkeys(values or ([filters["team"]] if filters.get("team") else [])))


def category_matches(item, filters, clauses, available):
    teams = team_values(filters, clauses)
    if teams and ("team" not in available or item.get("team") not in teams):
        return False
    for field, value in clauses:
        if field in {"no", "has"}:
            if value not in available:
                return False
            missing = item.get(value) in (None, "", "Not set")
            if missing != (field == "no"):
                return False
        elif field.startswith("-"):
            key = field[1:]
            if key not in available or item.get(key) == value:
                return False
    return True
