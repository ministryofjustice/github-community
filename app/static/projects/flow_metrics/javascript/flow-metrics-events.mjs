export function eventValueAt(ticket, type, date) {
  return ticket.events.filter((event) => event.type === type && event.date <= date).at(-1)?.value ?? null;
}

export function eventSeries(chart, tickets, from, to, { sprints, statuses, dateAt, dayNumber, point, shortDate }) {
  const series = [];
  const add = (name, points) => series.push({ name, points });
  const inScope = (ticket, date) => {
    const sprint = eventValueAt(ticket, "scope", date);
    return chart.filters.sprint
      ? sprints.some((entry) => entry.name === chart.filters.sprint && entry.id === sprint)
      : sprint !== null;
  };
  const selected = sprints.filter((sprint) => (!chart.filters.sprint || chart.filters.sprint === sprint.name)
    && sprint.start <= dateAt(to) && sprint.end >= dateAt(from));
  if (chart.metric === "velocity") {
    for (const name of ["Committed", "Completed"]) {
      add(name, selected.map((sprint) => {
        const date = name === "Committed" ? sprint.start : dateAt(Math.min(to, dayNumber(sprint.end)));
        const candidates = tickets.filter((ticket) => eventValueAt(ticket, "scope", date) === sprint.id
          && (name === "Committed" || eventValueAt(ticket, "status", date) === "Done"));
        const matches = candidates.filter(ticket => chart.calculation?.value === "count" || Number.isFinite(eventValueAt(ticket, "points", date)));
        return { ...point(`${sprint.name}${sprint.end > dateAt(to) ? " (in progress)" : ""}`,
          chart.calculation?.value === "count" ? matches.length
            : candidates.length && !matches.length ? null
              : matches.reduce((sum, ticket) => sum + eventValueAt(ticket, "points", date), 0), matches),
          missingEstimateCount: candidates.length - matches.length };
      }));
    }
  } else if (chart.metric === "churn") {
    for (const name of ["Added", "Removed"]) {
      add(name, selected.map((sprint) => {
        let count = 0;
        const occurrences = [];
        const matches = tickets.filter((ticket) => {
          let previous = null;
          let contributes = false;
          for (const event of ticket.events.filter((event) => event.type === "scope")) {
            const within = event.date > sprint.start && event.date <= sprint.end
              && event.date >= dateAt(from) && event.date <= dateAt(to);
            if (within && (name === "Added"
              ? event.value === sprint.id && previous !== sprint.id
              : previous === sprint.id && event.value !== sprint.id)) {
              count++;
              occurrences.push(ticket.id);
              contributes = true;
            }
            previous = event.value;
          }
          return contributes;
        });
        return { ...point(sprint.name, chart.calculation?.counting === "tickets" ? matches.length : count, matches), occurrences };
      }));
    }
  } else {
    const names = chart.metric === "flow" ? statuses : ["Scope", "Completed"];
    for (const name of names) {
      const interval = chart.calculation?.interval === "weekly" ? 7 : 1;
      add(name, Array.from({ length: Math.ceil((to - from + 1) / interval) }, (_, index) => {
        const day = Math.min(to, from + (index + 1) * interval - 1);
        const date = dateAt(day);
        const matches = tickets.filter((ticket) => ticket.created <= day
          && (chart.metric !== "flow" || !chart.filters.sprint || inScope(ticket, date))
          && (chart.metric !== "progress" || inScope(ticket, date))
          && (chart.metric === "flow" ? eventValueAt(ticket, "status", date) === name
            : name === "Scope" || eventValueAt(ticket, "status", date) === "Done"));
        return point(shortDate(day), matches.length, matches);
      }));
    }
  }
  return series;
}
