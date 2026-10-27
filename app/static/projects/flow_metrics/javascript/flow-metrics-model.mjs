import { eventValueAt, eventSeries } from "./flow-metrics-events.mjs";
import { CALCULATIONS, CATEGORY_FIELDS, BUILDER_AXES, builderError, compileRecipe, projectRecipe, calculationSettings } from "./flow-metrics-builder.mjs";

export const HISTORY = { from: "2026-07-01", to: "2026-08-25" };
let liveData = false;
let liveOptions = {};
let eventData = null;
const SAMPLE_METADATA_FIELDS = [
  "assignee", "label", "milestone", "reviewers", "priority", "refined",
  "blocked-by", "blocking", "relates-to", "parent-issue", "sub-issues-progress",
];
export function configureSampleData(dataset) {
  liveData = false;
  eventData = dataset;
  Object.assign(HISTORY, dataset.history);
  const realItems = (dataset.realObservations || []).flatMap((observation) => observation.items);
  const realOptions = dataset.realOptions || {};
  TEAMS.splice(0, TEAMS.length, ...new Set([...dataset.teams, ...(realOptions.team || realItems.map((ticket) => ticket.team))]));
  const statuses = new Set(dataset.tickets.flatMap((ticket) =>
    ticket.events.filter((event) => event.type === "status").map((event) => event.value)));
  realItems.forEach((ticket) => statuses.add(ticket.status));
  (realOptions.status || []).forEach(status => statuses.add(status));
  STATUSES.splice(0, STATUSES.length, ...new Set([...["Icebox", "TODO", "In Progress", "In Review", "Blocked / On Hold", "Done"].filter((status) => statuses.has(status)), ...statuses]));
  TICKETS.splice(0, TICKETS.length, ...dataset.tickets.map((ticket) => ({
    ...ticket, created: dayNumber(ticket.created), provenance: "synthetic", sourceId: ticket.id,
    datasetId: dataset.fictionalDatasetId || dataset.id, source: "Fictional",
  })));
  SEARCH_FIELDS.forEach((field) => {
    const key = field[0];
    if (key === "team") field[2] = TEAMS;
    else if (key === "source") field[2] = ["Fictional", "Genuine"];
    else if (key === "sprint") field[2] = [...new Set([...dataset.sprints.map((sprint) => sprint.name), ...(realOptions.sprint || realItems.map((ticket) => ticket.sprint))])].sort();
    else if (["repository", "type", "planned", "objective", ...SAMPLE_METADATA_FIELDS].includes(key)) {
      field[2] = [...new Set([...TICKETS, ...realItems.filter((ticket) => ticket.availableFields?.includes(key))]
        .flatMap((ticket) => ticket[key]).filter((value) => value !== undefined).concat(realOptions[key] || []))].sort();
    }
    else if (!["status", "is", "title", "from", "to"].includes(key)) field[2] = undefined;
  });
}
export function setRealObservation(observation) {
  eventData.realObservations = observation ? [observation] : [];
}

export function observationLoader(captures, load) {
  let cachedKey;
  let cachedRequest;
  return async (filters) => {
    validateFilters(filters);
    const { resolved } = resolveFilters(filters);
    const to = resolved.to || HISTORY.to;
    const selected = captures.filter(capture => capture.capturedAt.slice(0, 10) <= to).at(-1);
    if (!selected) return null;
    const key = `${selected.source}:${selected.id}:${selected.capturedAt}`;
    if (cachedKey !== key) {
      cachedKey = key;
      const request = load(to).catch(error => {
        if (cachedRequest === request) {
          cachedKey = undefined;
          cachedRequest = undefined;
        }
        throw error;
      });
      cachedRequest = request;
    }
    return cachedRequest;
  };
}

export function configureLiveData(metadata) {
  liveData = true;
  eventData = null;
  liveOptions = metadata.options;
  Object.assign(HISTORY, metadata.history);
  TEAMS.splice(0, TEAMS.length, ...(liveOptions.team || []));
  STATUSES.splice(0, STATUSES.length, ...(liveOptions.status || []));
  TICKETS.splice(0);
  SEARCH_FIELDS.forEach((field) => {
    if (Object.hasOwn(liveOptions, field[0])) field[2] = liveOptions[field[0]];
    else if (field[0] === "source") field[2] = ["Genuine"];
    else if (!["is", "title", "from", "to"].includes(field[0])) field[2] = undefined;
  });
}
export const DEPARTMENT = "Developer Experience";
export const TEAMS = ["Blueprint", "DevX", "Engineering Platform"];
export const STATUSES = ["Icebox", "TODO", "In Progress", "In Review", "Blocked / On Hold", "Done"];
export const FIELDS = {
  status: "Status", team: "Team", sprint: "Sprint", repository: "Repository",
  type: "Item type", planned: "Planned and unplanned work", objective: "Objective",
  created: "Created week", completed: "Completed week",
  reporting: "Reporting date", completionDate: "Completion date", statusBand: "Days-in-status band",
  durationBand: "Cycle-time band", ticket: "Item",
};
export const GROUP_FIELDS = { ...Object.fromEntries(Object.entries(FIELDS).filter(([key]) => CATEGORY_FIELDS.includes(key))), scopeChange: "Scope change (Committed / Added / Removed)" };
export const MEASURES = {
  count: { name: "Count of items", unit: "Items" },
  points: { name: "Sum of points", unit: "Points" },
  averagePoints: { name: "Average points", unit: "Points per item" },
  estimation: { name: "Sum of Estimation", unit: "Estimation" },
  averageEstimation: { name: "Average Estimation", unit: "Estimation per item" },
  averageCycle: { name: "Average cycle time", unit: "Calendar days" },
  averageAge: { name: "Average work item age", unit: "Calendar days" },
  ...Object.fromEntries(Object.entries(CALCULATIONS).map(([key, spec]) => [key, { name: spec.name, unit: spec.duration ? "Calendar days" : "Items" }])),
};
export const DEFAULT_FILTERS = { team: "", sprint: "", from: "", to: "", status: "", type: "", planned: "", query: "" };
export const SEARCH_FIELDS = [
  ["source", "Source", ["Fictional", "Genuine"]],
  ["is", "Is", ["open", "closed"]],
  ["assignee", "Assignee"], ["label", "Label"],
  ["repository", "Repository", ["sample-repository-alpha", "sample-repository-beta"]],
  ["blocked-by", "Blocked by"], ["blocking", "Blocking"], ["relates-to", "Relates to"],
  ["title", "Title", []], ["status", "Status", STATUSES],
  ["sprint", "Sprint", [1, 2, 3, 4].map((n) => `Sample sprint ${n}`)],
  ["milestone", "Milestone"], ["type", "Type", ["Task", "Bug", "Feature"]],
  ["reviewers", "Reviewers"], ["parent-issue", "Parent issue"], ["sub-issues-progress", "Sub-issues progress"],
  ["priority", "Priority"], ["refined", "Refined"],
  ["team", "Team", TEAMS], ["planned", "Planned", ["Planned", "Unplanned"]],
  ["objective", "Objective", ["Sample reliability", "Sample developer tooling", "Sample delivery"]],
  ["from", "From date", []], ["to", "To date", []],
];

export function parseQuery(query = "") {
  if (query.length > 1000) throw new Error("Keep the filter under 1,000 characters.");
  const clauses = [];
  const pattern = /\s*(?:([a-z][a-z-]*):("(?:[^"\\]|\\["\\])*"|[^\s"]+)|("(?:[^"\\]|\\["\\])*"|[^\s:"]+))\s*/gy;
  let position = 0;
  while (position < query.trimEnd().length) {
    pattern.lastIndex = position;
    const match = pattern.exec(query);
    if (!match) throw new Error('Use field:value or field:"value with spaces".');
    position = pattern.lastIndex;
    const field = match[1] || "keyword";
    const raw = match[2] || match[3];
    const value = raw.startsWith('"') ? JSON.parse(raw) : raw;
    if (!value.trim()) throw new Error("Enter a filter value.");
    if (field !== "keyword") {
      const definition = SEARCH_FIELDS.find(([key]) => key === field);
      if (!definition || !definition[2]) throw new Error(`${definition?.[1] || field} is unavailable in this prototype.`);
      if (definition[2].length && !definition[2].includes(value)) throw new Error(`Choose an available ${definition[1].toLowerCase()} value.`);
    }
    clauses.push({ field, value });
  }
  return clauses;
}

export function resolveFilters(filters = {}) {
  const resolved = { ...filters };
  const clauses = parseQuery(filters.query);
  for (const { field, value } of clauses) {
    if (["team", "sprint", "status", "type", "planned", "from", "to"].includes(field)) {
      resolved[field] = value;
    }
  }
  return { resolved, clauses };
}

export function chartHasDateAxis(chart) {
  return ["throughput", "flow", "progress"].includes(chart.metric)
    || (chart.metric === "cycle" && chart.layout === "scatter")
    || (chart.metric === "custom" && ["reporting", "completionDate", "created", "completed"].includes(chart.x));
}

export function datePresetRange(preset, history = HISTORY) {
  if (preset === "max") return { from: "", to: "" };
  if (!["2weeks", "1month", "3months"].includes(preset)) throw new Error("Choose an available date range.");
  const end = new Date(`${history.to}T00:00:00Z`);
  const start = new Date(end);
  if (preset === "2weeks") start.setUTCDate(start.getUTCDate() - 13);
  else {
    const day = start.getUTCDate();
    start.setUTCDate(1);
    start.setUTCMonth(start.getUTCMonth() - (preset === "1month" ? 1 : 3));
    const last = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 0)).getUTCDate();
    start.setUTCDate(Math.min(day, last));
    start.setUTCDate(start.getUTCDate() + 1);
  }
  return { from: [history.from, start.toISOString().slice(0, 10)].sort().at(-1), to: history.to };
}

export function withDateRange(filters, from, to) {
  const { clauses } = resolveFilters(filters);
  const query = clauses.filter(({ field }) => !["from", "to"].includes(field))
    .map(({ field, value }) => `${field === "keyword" ? "" : `${field}:`}${JSON.stringify(value)}`).join(" ");
  const next = { ...filters, from: "", to: "", query: [query, from ? `from:${from}` : "", to ? `to:${to}` : ""].filter(Boolean).join(" ") };
  validateFilters(next);
  return next;
}
export const CUSTOM_DEFAULTS = { metric: "custom", layout: "column", threshold: 7, x: "status", y: "count", group: "", filters: DEFAULT_FILTERS };
export const LAYOUTS = {
  bar: "Bar", column: "Column", line: "Line", area: "Stacked area",
  "stacked-bar": "Stacked bar", "stacked-column": "Stacked column",
  scatter: "Scatter", histogram: "Histogram", flow: "Cumulative flow", burnup: "Burn up",
};
export const METRICS = {
  custom: { name: "Custom chart", unit: "Items", description: "Build a chart from sample board fields. Choose the category axis, measure and optional grouping; filters belong to this chart." },
  cycle: { name: "Cycle time", unit: "Calendar days", description: "Elapsed calendar days from start to latest completion, for sample items completed in the reporting window. Same-day completion is 0.", events: true },
  churn: { name: "Sprint churn", unit: "Items", description: "Sample scope additions and removals during each sprint. An item can contribute to both series. These are fabricated events, not inferred board history.", events: true },
  age: { name: "Work item age", unit: "Calendar days", description: "Elapsed calendar days since creation for unfinished sample items, as at the end of the reporting window." },
  status: { name: "Status / WIP", unit: "Items", description: "Sample status distribution at the end of the reporting window. WIP includes In Progress, In Review and Blocked / On Hold." },
  stuck: { name: "Stuck items", unit: "Calendar days", description: "Unfinished WIP items in their current sample status for at least the configured number of calendar days, as at the reporting end date.", events: true },
  throughput: { name: "Throughput", unit: "Items completed", description: "Sample completions per seven-day bucket in the reporting window. The final bucket may be shorter than seven days." },
  flow: { name: "Cumulative flow", unit: "Items", description: "Daily counts by sample status, including Done, from fictional status events. Band thickness shows the number of items in each status.", events: true },
  progress: { name: "Sprint progress", unit: "Items", description: "Burn up of sample completed work against sample sprint scope. Select a sprint to inspect its fictional scope changes; all sprints shows combined sample scope.", events: true },
  velocity: { name: "Velocity", unit: "Points", description: "Points committed at sprint start versus points completed by sprint end, or reporting date for an in-progress sprint.", events: true },
};
export const SEEDS = [
  ["cycle", "scatter"], ["churn", "stacked-column"], ["age", "bar"], ["status", "column"],
  ["stuck", "bar"], ["throughput", "column"], ["flow", "flow"], ["progress", "burnup"], ["velocity", "column"],
].map(([metric, layout]) => ({ ...structuredClone(CUSTOM_DEFAULTS), id: `seed-${metric}`, name: METRICS[metric].name, metric, layout }));

const DAY = 86400000;
export const dayNumber = (value) => Math.round((Date.parse(`${value}T00:00:00Z`) - Date.parse(`${HISTORY.from}T00:00:00Z`)) / DAY);
export const dateAt = (day) => new Date(Date.parse(`${HISTORY.from}T00:00:00Z`) + day * DAY).toISOString().slice(0, 10);
export const displayDate = (value) => value.split("-").reverse().join("/");
export function captureLabel(timestamp) {
  const date = new Date(timestamp);
  const day = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London", day: "numeric", month: "long", year: "numeric",
  }).format(date);
  const time = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London", hour: "numeric", minute: "2-digit", hour12: true,
  }).format(date).replace(/\s/g, "");
  return `Last updated: ${day} at ${time}`;
}
export const shortDate = (day) => new Date(`${dateAt(day)}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });

// Fixed, generated fiction: no API calls, board snapshots or person-level fields.
export const TICKETS = Array.from({ length: 72 }, (_, i) => {
  const created = Math.floor(i / 3) * 2;
  const start = created + (i % 4);
  const duration = i % 13;
  const done = i % 5 === 0 ? null : start + duration;
  return {
    id: `DEMO-${String(i + 1).padStart(3, "0")}`,
    title: `Sample ${["workflow improvement", "service change", "documentation task", "platform maintenance"][i % 4]} ${i + 1}`,
    repository: `sample-repository-${i % 2 === 0 ? "alpha" : "beta"}`,
    team: TEAMS[Math.floor(i / 3) % TEAMS.length], sprint: `Sample sprint ${Math.min(4, Math.floor(created / 14) + 1)}`,
    type: ["Task", "Bug", "Feature"][i % 3],
    points: [1, 2, 3, 5, 8][i % 5],
    planned: i % 4 === 0 ? "Unplanned" : "Planned",
    objective: ["Sample reliability", "Sample developer tooling", "Sample delivery"][Math.floor(i / 2) % 3],
    created, start, done, review: done === null ? null : Math.max(start, done - 2),
    blocked: done === null && i % 2 === 0,
    // One synthetic scope-change event per item, with explicit event dates.
    scopeDay: Math.floor(created / 14) * 14 + 3 + (i % 8),
    scopeChange: i % 6 === 0 ? "Removed" : i % 3 === 0 ? "Added" : null,
  };
});

export function stateAt(ticket, day) {
  if (ticket.provenance === "real") return { status: ticket.observedStatus, since: null };
  if (liveData) return { status: ticket.observedStatus, since: null };
  if (ticket.events) {
    const event = ticket.events.filter((entry) => entry.type === "status" && entry.date <= dateAt(day)).at(-1);
    return event ? { status: event.value, since: dayNumber(event.date) } : null;
  }
  if (ticket.created > day) return null;
  if (ticket.done !== null && ticket.done <= day) return { status: "Done", since: ticket.done };
  if (ticket.start > day) return { status: ticket.id.endsWith("1") ? "Icebox" : "TODO", since: ticket.created };
  if (ticket.blocked && day >= ticket.start + 2) return { status: "Blocked / On Hold", since: ticket.start + 2 };
  if (ticket.review !== null && ticket.review <= day) return { status: "In Review", since: ticket.review };
  return { status: "In Progress", since: ticket.start };
}

export function validChart(chart) {
  const valid = chart && typeof chart.id === "string" && chart.id.length > 0 && chart.id.length <= 100
    && typeof chart.name === "string" && chart.name.trim().length > 0 && chart.name.length <= 80
    && Object.hasOwn(METRICS, chart.metric) && Object.hasOwn(LAYOUTS, chart.layout)
    && Number.isInteger(chart.threshold) && chart.threshold >= 1 && chart.threshold <= 365
    && Object.hasOwn(FIELDS, chart.x) && Object.hasOwn(MEASURES, chart.y)
    && (chart.group === "" || Object.hasOwn(GROUP_FIELDS, chart.group))
    && chart.filters && typeof chart.filters === "object" && !Array.isArray(chart.filters)
    && !builderError(chart);
  if (!valid) return false;
  try { validateFilters(chart.filters); }
  catch { return false; }
  return true;
}

export function upgradeChart(chart) {
  if (!chart || typeof chart !== "object" || Array.isArray(chart)) throw new Error("Invalid chart definition");
  if (chart.filters !== undefined && (!chart.filters || typeof chart.filters !== "object" || Array.isArray(chart.filters))) {
    throw new Error("Invalid chart filters");
  }
  const filters = { ...DEFAULT_FILTERS, ...chart.filters };
  // Only the old aggregate label migrates; DevX is an actual board Team value.
  if (filters.team === DEPARTMENT) filters.team = "";
  const upgraded = {
    id: chart.id, name: chart.name, metric: chart.metric, layout: chart.layout, threshold: chart.threshold,
    x: chart.x ?? "status", y: chart.y ?? "count", group: chart.group ?? "", filters,
    ...(chart.calculation !== undefined ? { calculation: structuredClone(chart.calculation) } : {}),
  };
  if (!validChart(upgraded)) throw new Error("Invalid chart definition");
  return upgraded;
}

export function validateFilters(filters) {
  if (!filters || typeof filters !== "object" || Array.isArray(filters)
      || Object.entries(filters).some(([key, value]) => !Object.hasOwn(DEFAULT_FILTERS, key) || typeof value !== "string")) {
    throw new Error("Chart filters must use the available fields and options.");
  }
  filters = resolveFilters(filters).resolved;
  if ((filters.team && !TEAMS.includes(filters.team))
      || (filters.sprint && !(liveData ? (liveOptions.sprint || []).includes(filters.sprint)
        : eventData ? SEARCH_FIELDS.find(([field]) => field === "sprint")[2].includes(filters.sprint)
          : [1, 2, 3, 4].some((n) => filters.sprint === `Sample sprint ${n}`)))) {
    throw new Error("Choose a team and sprint from the available options.");
  }
  if ((filters.status && !STATUSES.includes(filters.status))
      || (filters.type && !(liveData ? liveOptions.type || [] : eventData ? SEARCH_FIELDS.find(([field]) => field === "type")[2] : ["Task", "Bug", "Feature"]).includes(filters.type))
      || (filters.planned && !(liveData ? liveOptions.planned || [] : eventData ? SEARCH_FIELDS.find(([field]) => field === "planned")[2] : ["Planned", "Unplanned"]).includes(filters.planned))) {
    throw new Error("Choose a status, item type and planned-work option from the available values.");
  }
  for (const date of [filters.from, filters.to].filter(Boolean)) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(dayNumber(date))
        || dateAt(dayNumber(date)) !== date || date < HISTORY.from || date > HISTORY.to) {
      throw new Error(`Use dates within ${liveData ? "captured" : "sample"} history: ${HISTORY.from} to ${HISTORY.to}.`);
    }
  }
  if ((filters.from || HISTORY.from) > (filters.to || HISTORY.to)) {
    throw new Error("The From date must be on or before the To date.");
  }
}

const point = (label, value, tickets) => ({ label, value, ids: tickets.map((ticket) => ticket.id) });
export const ticketReference = (ticket) => ticket.provenance === "real"
  ? ticket.reference || "Draft item" : ticket.reference || ticket.id;
export const ticketChartLabel = (ticket, plottedItems = []) => {
  const reference = ticketReference(ticket);
  const number = reference.match(/#([1-9]\d*)$/)?.[1];
  if (!number) return reference;
  const clashes = plottedItems.some((other) => other.id !== ticket.id
    && ticketReference(other).match(/#([1-9]\d*)$/)?.[1] === number);
  const repository = reference.slice(0, reference.lastIndexOf("#")).split("/").at(-1);
  return clashes ? `${repository}#${number}` : `#${number}`;
};
export const itemCount = (count) => `${count} ${count === 1 ? "item" : "items"}`;
export const ticketText = (ticket) => `${ticket.title} (${ticketReference(ticket)})`;
export const pointTicket = (row, tickets) => row.ticketId
  ? tickets.find((ticket) => ticket.id === row.ticketId) : null;
const wip = (status) => ["In Progress", "In Review", "Blocked / On Hold"].includes(status);
const completedWithin = (ticket, from, to) => ticket.done !== null && ticket.start !== null
  && ticket.done >= ticket.start && ticket.done >= from && ticket.done <= to;

function fieldValue(ticket, field, to) {
  if (field === "status") return stateAt(ticket, to)?.status;
  if (field === "created" || field === "completed") {
    const day = field === "created" ? ticket.created : ticket.done;
    return day === null || day > to ? null : Math.floor(day / 7) * 7;
  }
  return ticket[field];
}

function customSeries(chart, tickets, from, to, population = tickets) {
  const timeAxis = ["created", "completed"].includes(chart.x);
  const items = tickets.filter((t) => {
    if (chart.y === "averageCycle" && !completedWithin(t, from, to)) return false;
    if (chart.y === "averageAge" && (stateAt(t, to)?.status === "Done"
      || (t.provenance === "real" && ["CLOSED", "MERGED"].includes(t.state)))) return false;
    if (timeAxis) {
      const day = chart.x === "created" ? t.created : t.done;
      return day !== null && day >= from && day <= to;
    }
    return true;
  });
  let categories = [...new Set(items.map((t) => fieldValue(t, chart.x, to)))];
  if (chart.x === "status") categories = STATUSES;
  else if (chart.x === "team") categories = TEAMS;
  else if (timeAxis) {
    categories = [];
    for (let day = Math.floor(from / 7) * 7; day <= to; day += 7) categories.push(day);
  } else categories.sort((a, b) => String(a).localeCompare(String(b), "en-GB", { numeric: true }));
  const groups = chart.group ? [...new Set(items.map((t) => fieldValue(t, chart.group, to)))].sort() : [""];
  const measure = (matches, candidates) => {
    if (chart.y === "count") return matches.length;
    if (!matches.length) return ["points", "estimation"].includes(chart.y) && !candidates.length ? 0 : null;
    const values = matches.map((t) => chart.y === "averageCycle" ? t.done - t.start
      : chart.y === "averageAge" ? to - t.created
        : ["estimation", "averageEstimation"].includes(chart.y) ? t.estimate : t.points);
    const sum = values.reduce((a, b) => a + b, 0);
    return ["points", "estimation"].includes(chart.y) ? sum : Number((sum / matches.length).toFixed(2));
  };
  return groups.map((group) => ({
    name: chart.group ? String(group) : MEASURES[chart.y].name,
    points: categories.map((category) => {
      const matches = items.filter((t) => fieldValue(t, chart.x, to) === category
        && (!chart.group || fieldValue(t, chart.group, to) === group));
      const label = timeAxis ? `${shortDate(Math.max(category, from))} to ${shortDate(Math.min(category + 6, to))}` : String(category);
      const candidates = population.filter((t) => fieldValue(t, chart.x, to) === category
        && (!chart.group || fieldValue(t, chart.group, to) === group));
      return point(label, measure(matches, candidates), matches);
    }),
  }));
}

export function scopeLabels(filters = {}) {
  const { resolved, clauses } = resolveFilters(filters);
  filters = resolved;
  return [
    filters.team || "All teams",
    filters.sprint || "All sprints",
    (filters.from || HISTORY.from) === (filters.to || HISTORY.to)
      ? displayDate(filters.from || HISTORY.from)
      : `${displayDate(filters.from || HISTORY.from)} to ${displayDate(filters.to || HISTORY.to)}`,
    ...[filters.status, filters.type, filters.planned].filter(Boolean),
    ...clauses.filter(({ field }) => !["team", "sprint", "status", "type", "planned", "from", "to"].includes(field)).map(({ field, value }) => `${field}: ${value}`),
  ];
}

export function buildResult(chart, filters = chart.filters || {}) {
  const recipe = compileRecipe(chart);
  if (recipe) {
    const error = builderError(chart);
    if (error) throw new Error(error);
    const calculated = buildResultCore({ ...recipe, calculation: calculationSettings(chart) }, filters);
    if (chart.y === "scopeChanges" && !calculated.unavailable) {
      const commitment = buildResultCore({ ...recipe, metric: "velocity", calculation: { ...calculationSettings(chart), value: "count" } }, filters);
      calculated.series.forEach(s => s.points.forEach((p, index) => { p.label = commitment.series[0].points[index].label; }));
      calculated.series.unshift(commitment.series[0]);
      calculated.rows = calculated.series.flatMap(s => s.points.map(p => ({ ...p, series: s.name })));
    }
    return { ...projectRecipe(chart, calculated, { fieldValue, point }), axis: FIELDS[chart.x] };
  }
  return buildResultCore(chart, filters);
}

function buildResultCore(chart, filters = chart.filters || {}) {
  validateFilters(filters);
  const { resolved, clauses } = resolveFilters(filters);
  filters = resolved;
  const from = dayNumber(filters.from || HISTORY.from);
  const to = dayNumber(filters.to || HISTORY.to);
  if (["scatter", "histogram"].includes(chart.layout) && chart.metric !== "cycle") {
    return {
      series: [], rows: [], tickets: [], from, to, sampleSize: 0, unit: "Items", axis: "",
      provenance: liveData ? "observed" : "synthetic", definitionVersion: 2,
      unavailable: "Scatter and histogram require Cycle time chart data. Choose Cycle time or another layout.",
    };
  }
  const source = eventData ? TICKETS.filter((ticket) => ticket.provenance !== "real").map((ticket) => {
    const date = dateAt(to);
    const statuses = ticket.events.filter((event) => event.type === "status" && event.date <= date);
    const completion = statuses.at(-1)?.value === "Done" ? statuses.at(-1) : null;
    const start = statuses.find((event) => event.value === "In Progress");
    const sprintId = eventValueAt(ticket, "scope", date);
    return { ...ticket, start: start ? dayNumber(start.date) : null,
      done: completion ? dayNumber(completion.date) : null,
      points: eventValueAt(ticket, "points", date),
      sprint: eventData.sprints.find((sprint) => sprint.id === sprintId)?.name || "Not set" };
  }) : TICKETS;
  const observation = eventData?.realObservations?.filter((entry) => entry.capturedAt.slice(0, 10) <= dateAt(to)).at(-1);
  const genuine = observation ? observation.items.filter((ticket) => !ticket.archived).map((ticket) => ({
    ...ticket, created: dayNumber(ticket.createdDate), done: null, start: null,
    source: "Genuine", events: [],
  })) : [];
  const population = [...source, ...genuine];
  const historicalScope = eventData && ["velocity", "churn", "progress", "flow"].includes(chart.metric);
  let missingFilterEvidence = 0;
  const tickets = population.filter((ticket) => {
    if (clauses.some(({ field, value }) => field === "source"
        && (ticket.provenance === "real" ? "Genuine" : "Fictional") !== value)) return false;
    if (ticket.provenance === "real"
        && ["team", "sprint", "status", "type", "planned"].some((field) => filters[field]
          && !ticket.availableFields?.includes(field))) {
      missingFilterEvidence++;
      return false;
    }
    return (!filters.team || ticket.team === filters.team)
    && (!filters.sprint || (historicalScope && ticket.provenance !== "real" ? ticket.events.some((event) => event.type === "scope"
      && event.value === eventData.sprints.find((sprint) => sprint.name === filters.sprint)?.id && event.date <= dateAt(to))
      : ticket.sprint === filters.sprint)) && ticket.created <= to
    && (!filters.status || stateAt(ticket, to)?.status === filters.status)
    && (!filters.type || ticket.type === filters.type)
    && (!filters.planned || ticket.planned === filters.planned)
    && clauses.every(({ field, value }) => {
      if (field === "source") return (ticket.provenance === "real" ? "Genuine" : "Fictional") === value;
      if (ticket.provenance === "real" && !["keyword", "from", "to"].includes(field)
          && !ticket.availableFields?.includes(field)) {
        missingFilterEvidence++;
        return false;
      }
      if (eventData && SAMPLE_METADATA_FIELDS.includes(field)) {
        return Array.isArray(ticket[field]) ? ticket[field].includes(value) : ticket[field] === value;
      }
      if (field === "repository" || field === "objective") return ticket[field] === value;
      if (field === "title") return ticket.title.toLowerCase().includes(value.toLowerCase());
      if (field === "keyword") return `${ticket.id} ${ticket.title} ${ticketReference(ticket)}`.toLowerCase().includes(value.toLowerCase());
      if (field === "is") return (stateAt(ticket, to)?.status === "Done"
        || (ticket.provenance === "real" && ["CLOSED", "MERGED"].includes(ticket.state))) === (value === "closed");
      return true;
    });
  });
  const needsHistory = ["cycle", "churn", "stuck", "throughput", "flow", "progress", "velocity"].includes(chart.metric)
    || (chart.metric === "custom" && (chart.y === "averageCycle" || ["created", "completed"].includes(chart.x)));
  const requiresPoints = chart.metric === "custom" && ["points", "averagePoints"].includes(chart.y);
  const requiresEstimation = chart.metric === "custom" && ["estimation", "averageEstimation"].includes(chart.y);
  const categoryFields = chart.recipeFields || (chart.metric === "custom" ? [chart.x, chart.group].filter(Boolean) : chart.metric === "status" ? ["status"] : []);
  const eligible = tickets.filter((ticket) => {
    if (needsHistory && ticket.provenance === "real") return false;
    if (requiresPoints && ticket.provenance === "real") return false;
    if (requiresPoints && (typeof ticket.points !== "number" || !Number.isFinite(ticket.points))) return false;
    if (requiresEstimation && (ticket.provenance !== "real"
        || ticket.identities?.estimate?.fieldId !== "PVTF_lADOACGfts4BHZqSzg_lEkY"
        || typeof ticket.estimate !== "number" || !Number.isFinite(ticket.estimate))) return false;
    if (ticket.provenance === "real" && categoryFields.some((field) => !ticket.availableFields.includes(field))) return false;
    if ((chart.metric === "age" || (chart.metric === "custom" && chart.y === "averageAge"))
        && ticket.provenance === "real" && ticket.state === "DRAFT") return false;
    return true;
  });
  const coverage = {
    available: tickets.length, eligible: eligible.length, excluded: tickets.length - eligible.length,
    genuine: tickets.filter((ticket) => ticket.provenance === "real").length,
    fictional: tickets.filter((ticket) => ticket.provenance !== "real").length,
    missingFilterEvidence,
    realObservation: observation?.capturedAt || null,
  };
  const included = eligible;
  const series = [];
  const add = (name, points) => series.push({ name, points });
  let unit = METRICS[chart.metric].unit;
  if (chart.metric === "velocity" && chart.calculation?.value === "count") unit = "Items";
  let note = "";
  let axis = chart.metric === "status" ? "Status" : "Reporting point";
  if (eventData && ["velocity", "churn", "flow", "progress"].includes(chart.metric)) {
    const scopedChart = { ...chart, filters };
    const context = { sprints: eventData.sprints, statuses: STATUSES, dateAt, dayNumber, point, shortDate };
    series.push(...eventSeries(scopedChart, included, from, to, context));
    if (chart.metric === "velocity") note = chart.calculation?.value === "count"
      ? "Committed items use sprint-start membership. Completed items use sprint-end or reporting-cutoff scope and latest Done state, excluding reopened unfinished work. In-progress sprints are partial."
      : "Committed points use sprint-start estimates. Completed points include added work and exclude reopened unfinished work. Missing point estimates are excluded; a populated baseline with no estimates is a gap. In-progress sprints are partial.";
  } else if (chart.metric === "custom") {
    series.push(...customSeries(chart, included, from, to, tickets));
    unit = MEASURES[chart.y].unit;
    axis = FIELDS[chart.x];
    note = ["created", "completed"].includes(chart.x)
      ? `Items ${chart.x} within the date window, grouped in calendar weeks.`
      : "Board fields are evaluated at the reporting end date; the From date limits completion-based averages only.";
    if (chart.y.startsWith("average")) note += " Empty groups have no average (shown as a gap), not zero.";
    if (chart.y.startsWith("average") && ["area", "stacked-bar", "stacked-column"].includes(chart.layout)) {
      note += " Stacked averages are not additive; use line or grouped columns to compare averages.";
    }
  } else if (chart.metric === "cycle") {
    const completed = included.filter((t) => completedWithin(t, from, to));
    add("Cycle time", completed.map((t) => ({
      ...point(ticketText(t), t.done - t.start, [t]), ticketId: t.id,
      completedDate: dateAt(t.done), x: Date.parse(`${dateAt(t.done)}T00:00:00Z`),
    })));
    axis = chart.layout === "scatter" ? "Completion date" : "Completed item";
  } else if (chart.metric === "age" || chart.metric === "stuck") {
    const active = included.filter((t) => {
      const state = stateAt(t, to);
      return state && (chart.metric === "age" ? state.status !== "Done"
        && !(t.provenance === "real" && ["CLOSED", "MERGED"].includes(t.state)) : wip(state.status) && to - state.since >= chart.threshold);
    });
    add(METRICS[chart.metric].name, active.map((t) => ({
      ...point(ticketText(t), to - (chart.metric === "age" ? t.created : stateAt(t, to).since), [t]), ticketId: t.id,
    })));
  } else if (chart.metric === "status") {
    add("Status", STATUSES.map((status) => point(status, included.filter((t) => stateAt(t, to)?.status === status).length, included.filter((t) => stateAt(t, to)?.status === status))));
    note = `WIP: ${included.filter((t) => wip(stateAt(t, to)?.status)).length} items (active, in review or blocked).`;
  } else if (chart.metric === "throughput") {
    const points = [];
    const interval = chart.calculation?.interval === "daily" ? 1 : 7;
    for (let day = from; day <= to; day += interval) {
      const end = Math.min(to, day + interval - 1);
      const completed = included.filter((t) => t.done !== null && t.done >= day && t.done <= end);
      points.push(point(`${shortDate(day)} to ${shortDate(end)}`, completed.length, completed));
    }
    add("Completed", points);
  } else if (chart.metric === "churn") {
    for (const change of ["Added", "Removed"]) {
      const sprints = filters.sprint ? [filters.sprint] : [1, 2, 3, 4].map((n) => `Sample sprint ${n}`);
      add(change, sprints.map((sprint) => {
        const changed = tickets.filter((t) => t.sprint === sprint && t.scopeChange === change && t.scopeDay >= from && t.scopeDay <= to);
        return point(sprint, changed.length, changed);
      }));
    }
  } else if (chart.metric === "flow") {
    for (const status of STATUSES) {
      add(status, Array.from({ length: to - from + 1 }, (_, i) => {
        const matches = tickets.filter((t) => stateAt(t, from + i)?.status === status);
        return point(shortDate(from + i), matches.length, matches);
      }));
    }
  } else if (chart.metric === "progress") {
    for (const name of ["Scope", "Completed"]) {
      add(name, Array.from({ length: to - from + 1 }, (_, i) => {
        const day = from + i;
        const scope = tickets.filter((t) => {
          const sprintStart = (Number(t.sprint.slice(-1)) - 1) * 14;
          return day >= sprintStart && (t.scopeChange !== "Added" || day >= t.scopeDay)
            && (t.scopeChange !== "Removed" || day < t.scopeDay);
        });
        const matches = name === "Scope" ? scope : scope.filter((t) => t.done !== null && t.done <= day);
        return point(shortDate(day), matches.length, matches);
      }));
    }
  }
  if (chart.layout === "histogram") {
    const observations = series.flatMap((s) => s.points).filter((p) => p.value !== null);
    const max = Math.max(0, ...observations.map((p) => p.value));
    const width = chart.calculation?.bandWidth || 3;
    const bins = Array.from({ length: Math.floor(max / width) + 1 }, (_, i) => {
      const matches = observations.filter((p) => p.value >= i * width && p.value < (i + 1) * width);
      return { label: `${i * width}–${(i + 1) * width - 1} days`, value: matches.length, ids: matches.flatMap((p) => p.ids) };
    });
    note = "One completed item per duration band, using first In Progress to latest completion; reopened unfinished items are excluded.";
    series.splice(0, series.length, { name: "Completed items", points: bins });
    unit = "Items";
    axis = "Cycle time (calendar days)";
  }
  const rows = series.flatMap((s) => s.points.map((p) => ({ ...p, series: s.name })));
  const coverageText = coverage.excluded || missingFilterEvidence
    ? `${coverage.eligible} of ${coverage.available} matching items have the required evidence; ${coverage.excluded} excluded.${missingFilterEvidence ? ` ${missingFilterEvidence} excluded by filters with uncollected fields.` : ""}`
    : "";
  if (needsHistory && coverage.excluded) note += " Genuine items without verified event history are excluded; observations are not transitions.";
  if (requiresEstimation) note += " Unitless numeric Estimation uses genuine items only; fictional Points are separate. Missing estimates are excluded.";
  if (requiresPoints && eventData?.realObservations) note += " Points uses fictional estimates only, not genuine numeric Estimation.";
  const unavailable = needsHistory && !eligible.length && coverage.genuine
    ? chart.metric === "cycle"
      ? "Not enough history to calculate cycle time yet."
      : "Verified event history is unavailable for these genuine items."
    : requiresEstimation && !eligible.length
      ? "No matching items have a captured numeric Estimation value from the verified field."
      : requiresPoints && !eligible.length && coverage.genuine
        ? "Points measures use fictional points. Choose Sum of Estimation or Average Estimation for genuine numeric estimates."
        : null;
  return {
    series: unavailable ? [] : series, rows: unavailable ? [] : rows, unit, axis, note, from, to, coverage, coverageText,
    unavailable,
    definitionVersion: 2,
    provenance: eventData?.realObservations ? "mixed" : liveData ? "observed" : "synthetic",
    sampleSize: unavailable ? 0 : new Set(rows.flatMap((p) => p.ids)).size,
    tickets,
  };
}

export function csvCell(value) {
  const text = String(value);
  const safe = /^[\s]*[=+\-@]/.test(text) || /^[\t\r\n]/.test(text) ? `'${text}` : text;
  return `"${safe.replaceAll('"', '""')}"`;
}

export function resultCSV(chart, result, filters = chart.filters || {}) {
  const mixed = result.provenance === "mixed";
  const context = `${mixed ? "Combined exploration: fictional events and genuine observations" : liveData ? "Captured board observation; definition v1" : "Demonstration data only"}; ${chart.name}; ${scopeLabels(filters).join("; ")}; ${chart.metric === "custom" ? `${FIELDS[chart.x]}; ${MEASURES[chart.y].name}; Group: ${GROUP_FIELDS[chart.group] || "None"}` : METRICS[chart.metric].name}; ${result.note}; ${result.coverageText || ""}`;
  return [
    ["Context", "Series", "Point", ...(chart.layout === "scatter" ? ["Completion date"] : []), result.unit, mixed ? "Item references" : liveData ? "Board item references" : "Sample item references", ...(mixed ? ["Contributor provenance", "Genuine observation at"] : [])],
    ...result.rows.map((row) => [context, row.series, row.label,
      ...(chart.layout === "scatter" ? [displayDate(row.completedDate)] : []),
      row.value ?? "", row.ids.map((id) => {
        const ticket = result.tickets.find((ticket) => ticket.id === id);
        return ticket ? ticketReference(ticket) : "Unavailable item reference";
      }).join("; "),
      ...(mixed ? [row.ids.map((id) => {
        const ticket = result.tickets.find((ticket) => ticket.id === id);
        return `${ticket ? ticketReference(ticket) : "Unavailable item reference"}:${ticket?.provenance || "synthetic"}`;
      }).join("; "), result.coverage.realObservation || ""] : [])]),
  ].map((row) => row.map(csvCell).join(",")).join("\r\n");
}
