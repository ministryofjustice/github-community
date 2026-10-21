export const CALCULATION_DEFAULTS = Object.freeze({
  version: 1, interval: "weekly", bandWidth: 3, counting: "events",
  value: "count", aggregation: "individual", minDays: 0, additional: "",
});
export const CALCULATIONS = {
  cycleTime: { name: "Cycle time", metric: "cycle", duration: true },
  itemAge: { name: "Unfinished work item age", metric: "age", duration: true },
  statusDays: { name: "Days in current status", metric: "stuck", duration: true },
  completions: { name: "Completed items", metric: "throughput" },
  historicalCount: { name: "Historical point-in-time count", metric: "flow" },
  committedScope: { name: "Sprint-start commitment", metric: "velocity", series: "Committed" },
  addedScope: { name: "Added sprint scope", metric: "churn", series: "Added" },
  removedScope: { name: "Removed sprint scope", metric: "churn", series: "Removed" },
  sprintScope: { name: "Sprint scope", metric: "progress", series: "Scope" },
  completedScope: { name: "Completed in sprint", metric: "progress", series: "Completed" },
  scopeChanges: { name: "Committed, added and removed scope", metric: "churn" },
};
export const CATEGORY_FIELDS = ["status", "team", "sprint", "repository", "type", "planned", "objective"];
export const BUILDER_AXES = ["reporting", "completionDate", "statusBand", "durationBand", "ticket"];
export function calculationSettings(chart) {
  return { ...CALCULATION_DEFAULTS, ...chart.calculation };
}
export function builderError(chart) {
  const settings = calculationSettings(chart);
  if (chart.calculation !== undefined && (!chart.calculation || Array.isArray(chart.calculation)
      || typeof chart.calculation !== "object"
      || Object.keys(chart.calculation).some(key => !Object.hasOwn(CALCULATION_DEFAULTS, key)))) return "Unsupported calculation settings.";
  if (settings.version !== 1 || !["daily", "weekly"].includes(settings.interval)
      || !Number.isInteger(settings.bandWidth) || settings.bandWidth < 1 || settings.bandWidth > 365
      || !Number.isInteger(settings.minDays) || settings.minDays < 0 || settings.minDays > 365
      || !["events", "tickets"].includes(settings.counting)
      || !["count", "points"].includes(settings.value)
      || !["individual", "count", "sum", "average"].includes(settings.aggregation)
      || (settings.additional !== "" && !Object.hasOwn(CALCULATIONS, settings.additional))) return "Choose valid calculation settings (whole days from 0 to 365; band width 1 to 365).";
  if (chart.metric !== "custom") return null;
  if (chart.group === "scopeChange" && !["committedScope", "addedScope", "removedScope", "completedScope", "scopeChanges"].includes(chart.y)) return "Scope change grouping requires a sprint commitment, addition, removal or completed-in-sprint measure.";
  const spec = CALCULATIONS[chart.y];
  if (!spec) {
    if (settings.additional) return "Additional measures require a sprint scope calculation.";
    if (BUILDER_AXES.includes(chart.x) && !(chart.x === "completionDate" && chart.y === "count")
        && !(chart.x === "statusBand" && chart.y === "count")) return "Choose a compatible calculated measure for this category.";
    if (BUILDER_AXES.includes(chart.group)) return "Group by a board field, not a calculated axis.";
    if (chart.x === "statusBand" && chart.group) return "Use Days in current status with Count items to group duration bands.";
    if (["scatter", "histogram", "flow", "burnup"].includes(chart.layout)) return "This layout needs a matching calculated measure.";
    if (chart.calculation && chart.y.startsWith("average") && ["area", "stacked-bar", "stacked-column"].includes(chart.layout)) return "Averages cannot be stacked. Choose line, bar or column.";
    return null;
  }
  if (settings.value === "points" && !["committedScope", "completedScope"].includes(chart.y)) return "Historical Points are supported only for sprint-start commitment and completed-in-sprint by Sprint.";
  if (spec.duration) {
    if (settings.additional) return "Duration measures cannot be combined with sprint scope series.";
    if (chart.layout === "scatter") return chart.y === "cycleTime" && chart.x === "completionDate" && !chart.group
      ? null : "Scatter requires Completion date, Cycle time and no grouping.";
    if (chart.layout === "histogram") return chart.y === "cycleTime" && chart.x === "durationBand" && !chart.group
      ? null : "Histogram requires Cycle-time band, Cycle time and no grouping.";
    if (["flow", "burnup"].includes(chart.layout)) return "Use bar, column or line for duration calculations.";
    if (chart.x === "ticket") return chart.group ? "Individual item views cannot be grouped."
      : settings.aggregation !== "individual" ? "Item requires Individual items; choose a board-field category for an aggregate." : null;
    if (chart.x === "statusBand") return chart.y === "statusDays" && settings.aggregation === "count"
      ? null : "Days-in-status band requires Days in current status and Count items.";
    if (!CATEGORY_FIELDS.includes(chart.x) || settings.aggregation === "individual") return "For a board-field category choose Count items, Sum or Average; use Item for individual values.";
    if (settings.aggregation === "average" && ["area", "stacked-bar", "stacked-column"].includes(chart.layout)) return "Averages cannot be stacked. Choose line, bar or column.";
  } else {
    const axes = chart.y === "completions" ? ["completionDate", "reporting"]
      : ["addedScope", "removedScope", "committedScope", "scopeChanges"].includes(chart.y) ? ["sprint"]
        : ["completedScope"].includes(chart.y) ? ["sprint", "reporting"] : ["reporting"];
    if (!axes.includes(chart.x)) return `Choose ${axes.map(x => x === "reporting" ? "Reporting date" : x === "completionDate" ? "Completion date" : "Sprint").join(" or ")} for this measure.`;
    if (["scatter", "histogram"].includes(chart.layout)) return "Scatter and histogram require item-level Cycle time.";
    if (chart.layout === "flow" && chart.y !== "historicalCount") return "Cumulative flow requires Historical point-in-time count.";
    if (chart.layout === "burnup" && !["sprintScope", "completedScope"].includes(chart.y)) return "Burn up requires Sprint scope or Completed in sprint.";
    if (settings.value === "points" && (chart.x !== "sprint" || chart.group)) return "Historical Points require Sprint with no additional grouping.";
    const compatible = ["addedScope", "removedScope"].includes(chart.y) ? ["addedScope", "removedScope"]
      : chart.y === "committedScope" || (chart.y === "completedScope" && chart.x === "sprint") ? ["committedScope", "completedScope"]
        : ["sprintScope", "completedScope"].includes(chart.y) ? ["sprintScope", "completedScope"] : [];
    if (settings.additional && (!compatible.includes(settings.additional) || settings.additional === chart.y)) return "Choose a different additional measure with the same sprint baseline and unit.";
  }
  return null;
}

export function compileRecipe(chart) {
  if (chart.metric !== "custom") return null;
  if (chart.x === "status" && chart.y === "count" && !chart.group && !["scatter", "histogram", "flow", "burnup"].includes(chart.layout)) return { ...chart, metric: "status" };
  const spec = CALCULATIONS[chart.y];
  if (!spec && chart.x !== "statusBand" && chart.x !== "completionDate") return null;
  const settings = calculationSettings(chart);
  const metric = spec?.metric || (chart.x === "statusBand" ? "stuck" : "throughput");
  return {
    ...chart, metric: chart.y === "completedScope" && chart.x === "sprint" ? "velocity" : metric,
    threshold: chart.y === "statusDays" || chart.x === "statusBand" ? settings.minDays : chart.threshold,
    recipeFields: [chart.x, chart.group].filter(field => CATEGORY_FIELDS.includes(field)),
  };
}

// Projection only: all eligibility, temporal evaluation and evidence gates run in
// the same built-in engine before a recipe groups its exact contributors.
export function projectRecipe(chart, result, { fieldValue, point }) {
  if (result.unavailable) return result;
  const spec = CALCULATIONS[chart.y];
  const settings = calculationSettings(chart);
  let series = result.series;
  const ticketById = new Map(result.tickets.map(ticket => [ticket.id, ticket]));
  const groupRows = (rows, category, aggregation) => {
    const groups = new Map();
    for (const row of rows) {
      for (const id of row.ids) {
        const ticket = ticketById.get(id);
        const key = category(ticket, row);
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push({ ticket, value: row.value });
      }
    }
    return [...groups].map(([label, values]) => point(String(label),
      aggregation === "count" ? values.length : aggregation === "average"
        ? Number((values.reduce((sum, v) => sum + v.value, 0) / values.length).toFixed(2))
        : values.reduce((sum, v) => sum + v.value, 0), values.map(v => v.ticket)));
  };
  const byField = (ticket, field) => fieldValue(ticket, field, result.to);
  if (spec?.duration && !["scatter", "histogram"].includes(chart.layout)) {
    if (chart.x !== "ticket") {
      const groups = chart.group ? [...new Set(series.flatMap(s => s.points).flatMap(row => row.ids.map(id => byField(ticketById.get(id), chart.group))))] : [""];
      series = groups.map(group => ({
        name: group || spec.name,
        points: groupRows(result.rows.filter(row => !chart.group || byField(ticketById.get(row.ids[0]), chart.group) === group),
          (ticket, row) => chart.x === "statusBand" ? `${Math.floor(row.value / settings.bandWidth) * settings.bandWidth}–${(Math.floor(row.value / settings.bandWidth) + 1) * settings.bandWidth - 1} days` : byField(ticket, chart.x),
          settings.aggregation),
      }));
      result.unit = settings.aggregation === "count" ? "Items" : "Calendar days";
      const labels = [...new Set(series.flatMap(s => s.points.map(p => p.label)))].sort((a, b) => String(a).localeCompare(String(b), "en-GB", { numeric: true }));
      series.forEach(s => {
        s.points = labels.map(label => s.points.find(p => p.label === label)
          || point(label, settings.aggregation === "average" ? null : 0, []));
      });
    }
  } else if (chart.x === "statusBand") {
    series = [{ name: "Items", points: groupRows(result.rows, (ticket, row) => `${Math.floor(row.value / settings.bandWidth) * settings.bandWidth}–${(Math.floor(row.value / settings.bandWidth) + 1) * settings.bandWidth - 1} days`, "count") }];
    result.unit = "Items";
  } else if (spec && !spec.duration) {
    const wanted = [spec.series, CALCULATIONS[settings.additional]?.series].filter(Boolean);
    if (wanted.length) series = series.filter(s => wanted.includes(s.name));
    if (chart.y === "historicalCount" && chart.group !== "status") {
      const labels = series[0]?.points.map(p => p.label) || [];
      const grouped = chart.group ? [...new Set(result.tickets.filter(t => t.provenance !== "real").map(t => byField(t, chart.group)))] : [""];
      series = grouped.map(group => ({
        name: group || spec.name,
        points: labels.map((label, index) => {
          const ids = new Set(result.series.flatMap(s => s.points[index]?.ids || []));
          const matches = result.tickets.filter(t => ids.has(t.id) && (!chart.group || byField(t, chart.group) === group));
          return point(label, matches.length, matches);
        }),
      }));
    } else if (chart.y !== "historicalCount" && chart.group && chart.group !== "scopeChange") {
      series = series.flatMap(s => {
        const groups = [...new Set(s.points.flatMap(row => row.ids.map(id => byField(ticketById.get(id), chart.group))))];
        return groups.map(group => ({
          name: `${s.name} · ${group}`,
          points: s.points.map(row => {
            const matches = row.ids.map(id => ticketById.get(id)).filter(t => byField(t, chart.group) === group);
            const count = settings.counting === "events" && row.occurrences
              ? row.occurrences.filter(id => matches.some(t => t.id === id)).length : matches.length;
            return point(row.label, count, matches);
          }),
        }));
      });
    }

  }
  if (chart.x === "statusBand" && series.some(s => s.points.length)) {
    const max = Math.max(...series.flatMap(s => s.points.map(p => Number(p.label.split("–")[0]))));
    const labels = Array.from({ length: Math.floor(max / settings.bandWidth) + 1 },
      (_, index) => `${index * settings.bandWidth}–${(index + 1) * settings.bandWidth - 1} days`);
    series.forEach(s => { s.points = labels.map(label => s.points.find(p => p.label === label) || point(label, 0, [])); });
  }
  const rows = series.flatMap(s => s.points.map(p => ({ ...p, series: s.name })));
  return { ...result, series, rows, axis: chart.x, sampleSize: new Set(rows.flatMap(row => row.ids)).size,
    note: `${result.note} Calculation settings v1: ${settings.interval}; ${settings.counting === "events" ? "scope change occurrences" : "distinct items per bucket"}; ${settings.value}; ${settings.aggregation}; minimum status days ${settings.minDays}; bands ${settings.bandWidth} days.` };
}

export function editableRecipe(chart) {
  const calculation = { ...CALCULATION_DEFAULTS };
  const fields = {
    cycle: { x: chart.layout === "histogram" ? "durationBand" : chart.layout === "scatter" ? "completionDate" : "ticket", y: "cycleTime" },
    age: { x: "ticket", y: "itemAge" },
    stuck: { x: "ticket", y: "statusDays" },
    status: { x: "status", y: "count" },
    throughput: { x: "completionDate", y: "completions" },
    churn: { x: "sprint", y: "addedScope" },
    flow: { x: "reporting", y: "historicalCount", group: "status" },
    progress: { x: "reporting", y: "sprintScope" },
    velocity: { x: "sprint", y: "committedScope" },
  }[chart.metric];
  if (!fields) return structuredClone(chart);
  if (chart.metric === "stuck") calculation.minDays = chart.threshold;
  if (chart.metric === "churn") calculation.additional = "removedScope";
  if (chart.metric === "progress" || chart.metric === "velocity") calculation.additional = "completedScope";
  if (chart.metric === "velocity") calculation.value = "points";
  if (["flow", "progress"].includes(chart.metric)) calculation.interval = "daily";
  return { ...structuredClone(chart), metric: "custom", group: "", ...fields, calculation };
}
