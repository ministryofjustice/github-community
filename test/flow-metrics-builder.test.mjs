import test from "node:test";
import assert from "node:assert/strict";
import { SAMPLE_DATA } from "../app/static/projects/flow_metrics/javascript/flow-metrics-sample-data.mjs";
import { buildResult, configureSampleData, CUSTOM_DEFAULTS, SEEDS, validChart, upgradeChart, resultCSV } from "../app/static/projects/flow_metrics/javascript/flow-metrics-model.mjs";
import { CALCULATION_DEFAULTS, editableRecipe, builderError } from "../app/static/projects/flow_metrics/javascript/flow-metrics-builder.mjs";

configureSampleData(SAMPLE_DATA);
const recipe = (y, x, settings = {}, rest = {}) => ({
  ...structuredClone(CUSTOM_DEFAULTS), id: "test-recipe", name: "Custom recipe",
  y, x, calculation: { ...CALCULATION_DEFAULTS, ...settings }, ...rest,
});
const query = value => ({ ...CUSTOM_DEFAULTS.filters, query: value });
const identity = result => result.rows.map(({ series, label, value, ids, x, completedDate, ticketId }) =>
  ({ series, label, value, ids, x, completedDate, ticketId }));

test("all nine built-ins compile into editable recipes with identical series, values and exact contributors", () => {
  for (const seed of SEEDS) {
    for (const filter of ["", 'sprint:"Sprint A"', 'sprint:Firebreak', 'team:Blueprint']) {
      const chart = { ...structuredClone(seed), filters: query(filter) };
      const before = structuredClone(chart);
      const custom = editableRecipe(chart);
      assert.equal(validChart(custom), true, `${seed.metric}: ${builderError(custom)}`);
      const builtin = buildResult(chart), calculated = buildResult(custom);
      assert.deepEqual(identity(calculated), identity(builtin), `${seed.metric}/${filter}`);
      assert.equal(calculated.unit, builtin.unit);
      assert.equal(calculated.sampleSize, builtin.sampleSize);
      assert.deepEqual(chart, before);
      const csv = resultCSV(custom, calculated);
      for (const row of calculated.rows) for (const id of row.ids) assert.ok(csv.includes(id));
      assert.deepEqual(upgradeChart(custom), custom);
    }
  }
});

test("ticket histogram/scatter share cycle known answers including same-day and latest reopened completion", () => {
  for (const [layout, x] of [["scatter", "completionDate"], ["histogram", "durationBand"]]) {
    const chart = recipe("cycleTime", x, {}, { layout, filters: query('sprint:"Sprint A" to:2026-09-27') });
    assert.equal(builderError(chart), null);
    assert.deepEqual(identity(buildResult(chart)), identity(buildResult({ ...chart, metric: "cycle" })));
  }
  const histogram = buildResult(recipe("cycleTime", "durationBand", { bandWidth: 2 }, { layout: "histogram", filters: query('sprint:"Sprint A" to:2026-09-27') }));
  assert.deepEqual(histogram.rows.map(row => row.value), [1, 0, 1, 1, 1, 1]);
  assert.equal(new Set(histogram.rows.flatMap(row => row.ids)).size, 5);
});

test("duration groups align across series and match exact built-in contributors, thresholds and status bands", () => {
  const individual = buildResult({ ...SEEDS.find(s => s.metric === "stuck") });
  const grouped = buildResult(recipe("statusDays", "team", { minDays: 7, aggregation: "count" }));
  assert.equal(grouped.rows.reduce((sum, row) => sum + row.value, 0), individual.sampleSize);
  assert.deepEqual(grouped.rows.flatMap(row => row.ids).sort(), individual.rows.flatMap(row => row.ids).sort());
  const average = buildResult(recipe("cycleTime", "team", { aggregation: "average" }, { group: "sprint" }));
  const labels = average.series[0].points.map(p => p.label);
  assert.ok(average.series.every(s => JSON.stringify(s.points.map(p => p.label)) === JSON.stringify(labels)));
  for (const row of average.rows.filter(r => r.ids.length)) {
    const durations = buildResult({ ...SEEDS[0], filters: query("") }).rows.filter(r => row.ids.includes(r.ids[0])).map(r => r.value);
    assert.equal(row.value, Number((durations.reduce((s, v) => s + v, 0) / durations.length).toFixed(2)));
  }
  const legacyAverage = buildResult(recipe("averageCycle", "team"));
  const calculatedAverage = buildResult(recipe("cycleTime", "team", { aggregation: "average" }));
  for (const row of calculatedAverage.rows) {
    const legacy = legacyAverage.rows.find(r => r.label === row.label);
    assert.equal(row.value, legacy.value);
    assert.deepEqual(row.ids, legacy.ids);
  }
  const bands = buildResult(recipe("statusDays", "statusBand", { minDays: 0, aggregation: "count", bandWidth: 3 }));
  const all = buildResult(recipe("statusDays", "ticket"));
  assert.equal(bands.rows.reduce((sum, r) => sum + r.value, 0), all.sampleSize);
  assert.equal(new Set(bands.rows.flatMap(r => r.ids)).size, all.sampleSize);
  for (const row of bands.rows) {
    const lower = Number(row.label.split("–")[0]);
    assert.ok(all.rows.filter(r => row.ids.includes(r.ids[0])).every(r => r.value >= lower && r.value < lower + 3));
  }
});

test("daily completion buckets and weekly end-of-interval snapshots use the same engine", () => {
  const daily = buildResult(recipe("completions", "completionDate", { interval: "daily" }));
  const weekly = buildResult(recipe("completions", "completionDate", { interval: "weekly" }, { group: "team" }));
  assert.equal(daily.rows.reduce((s, r) => s + r.value, 0), weekly.rows.reduce((s, r) => s + r.value, 0));
  assert.deepEqual(daily.rows.flatMap(r => r.ids).sort(), weekly.rows.flatMap(r => r.ids).sort());
  const snapshots = buildResult(recipe("historicalCount", "reporting", { interval: "weekly" }));
  const dailySnapshots = buildResult(recipe("historicalCount", "reporting", { interval: "daily" }));
  for (const row of snapshots.rows) assert.deepEqual(row.ids, dailySnapshots.rows.find(r => r.label === row.label).ids);
});

test("days-in-status thresholds are inclusive and bands include same-day zero and empty integer bands", () => {
  const data = structuredClone(SAMPLE_DATA);
  data.tickets = [0, 6, 7, 8].map((days,index) => ({
    ...structuredClone(data.tickets[0]), id: `STATUS-BOUNDARY-${index}`, created: "2026-10-01",
    events: [{ type: "status", date: new Date(Date.parse("2026-10-19T00:00:00Z")-days*86400000).toISOString().slice(0,10), value: "In Progress" }],
  }));
  try {
    configureSampleData(data);
    const stuck=buildResult(recipe("statusDays","team",{minDays:7,aggregation:"count"}));
    assert.deepEqual(stuck.rows.flatMap(r=>r.ids).sort(),["STATUS-BOUNDARY-2","STATUS-BOUNDARY-3"]);
    const bands=buildResult(recipe("statusDays","statusBand",{aggregation:"count",bandWidth:3}));
    assert.deepEqual(bands.rows.map(r=>r.value),[1,0,3]);
    assert.equal(bands.rows.reduce((s,r)=>s+r.value,0),4);
    assert.equal(buildResult(recipe("statusDays","ticket")).rows.find(r=>r.ids[0]==="STATUS-BOUNDARY-0").value,0);
  } finally {configureSampleData(SAMPLE_DATA);}
});

test("scope returns count occurrences vs distinct tickets and grouping preserves occurrence totals", () => {
  const data = structuredClone(SAMPLE_DATA);
  const ticket = data.tickets[0];
  ticket.events.push({ date: "2026-09-20", type: "scope", value: null },
    { date: "2026-09-21", type: "scope", value: "sample-a" },
    { date: "2026-09-22", type: "scope", value: null },
    { date: "2026-09-23", type: "scope", value: "sample-a" });
  ticket.events.sort((a,b) => a.date.localeCompare(b.date));
  try {
    configureSampleData(data);
    const events = recipe("addedScope", "sprint", { counting: "events" }, { filters: query('sprint:"Sprint A"') });
    const occurrences = buildResult(events);
    const distinct = buildResult({ ...events, calculation: { ...events.calculation, counting: "tickets" } });
    assert.equal(occurrences.rows[0].value, distinct.rows[0].value + 1);
    assert.equal(new Set(occurrences.rows[0].ids).size, occurrences.rows[0].ids.length);
    const groups = buildResult({ ...events, group: "team" });
    assert.equal(groups.rows.reduce((s,r) => s+r.value, 0), occurrences.rows[0].value);
  } finally { configureSampleData(SAMPLE_DATA); }
});

test("commitment is a baseline not Planned; count and Points units stay distinct, missing estimates never become zero", () => {
  const counts = buildResult(recipe("committedScope", "sprint", { additional: "completedScope" }));
  const velocity = buildResult(editableRecipe(SEEDS.find(s => s.metric === "velocity")));
  assert.equal(counts.unit, "Items");assert.equal(velocity.unit, "Points");
  assert.deepEqual(counts.series[0].points.map(p => p.value), [10, 11, 12]);
  const planned = buildResult({ ...CUSTOM_DEFAULTS, id: "planned", name: "Planned and unplanned work", x: "planned" });
  assert.notDeepEqual(planned.rows.map(r=>r.value), counts.series[0].points.map(p=>p.value));
  const changes = buildResult(recipe("scopeChanges", "sprint", {}, { group: "scopeChange" }));
  assert.deepEqual(changes.series[0].points, counts.series[0].points);
  const churn = buildResult(SEEDS.find(s => s.metric === "churn"));
  assert.deepEqual(changes.series.slice(1).map(s => s.points.map(({value,ids})=>({value,ids}))),
    churn.series.map(s => s.points.map(({value,ids})=>({value,ids}))));
  const data = structuredClone(SAMPLE_DATA);
  data.tickets.forEach(t => { t.events = t.events.filter(e => e.type !== "points"); });
  try {
    configureSampleData(data);
    const missing = buildResult(editableRecipe(SEEDS.find(s => s.metric === "velocity")));
    assert.ok(missing.rows.every(r => r.value === null || r.ids.length === 0));
    assert.ok(missing.rows.some(r => r.value === null));
  } finally { configureSampleData(SAMPLE_DATA); }
});

test("every guide recipe has compatible exact controls and aligned finite result rows", () => {
  const choices = [
    ...["status", "team", "sprint", "repository", "type"].map(x => ["count", x]),
    ["count", "status", {}, { group: "team", layout: "stacked-column" }],
    ["count", "planned", {}, { group: "team" }],
    ["estimation", "sprint", {}, { group: "planned" }],
    ...["estimation", "averageEstimation"].flatMap(y => ["team", "sprint"].map(x => [y, x])),
    ...["team", "status"].map(x => ["itemAge", x, { aggregation: "average" }]),
    ["itemAge", "ticket", {}, { layout: "bar" }],
    ...["team", "sprint"].map(x => ["cycleTime", x, { aggregation: "average" }]),
    ["completions", "completionDate", { interval: "weekly" }],
    ["completions", "completionDate", { interval: "daily" }, { group: "team" }],
    ["cycleTime", "completionDate", {}, { layout: "scatter" }],
    ["cycleTime", "durationBand", {}, { layout: "histogram" }],
    ["statusDays", "team", { aggregation: "count", minDays: 7 }],
    ["statusDays", "ticket", { minDays: 7 }, { layout: "bar" }],
    ["statusDays", "statusBand", { aggregation: "count", bandWidth: 3 }],
    ["addedScope", "sprint", { additional: "removedScope" }, { layout: "stacked-column" }],
    ["addedScope", "sprint", { additional: "removedScope", counting: "tickets" }],
    ["committedScope", "sprint"],
    ["scopeChanges", "sprint", {}, { group: "scopeChange" }],
    ["sprintScope", "reporting", { interval: "daily", additional: "completedScope" }, { layout: "burnup" }],
    ["historicalCount", "reporting", { interval: "daily" }, { group: "status", layout: "flow" }],
    ["historicalCount", "reporting", { interval: "weekly" }, { group: "team", layout: "line" }],
    ["completedScope", "sprint"],
  ];
  assert.equal(choices.length, 32);
  for (const [y, x, settings, rest] of choices) {
    const chart = recipe(y, x, settings, rest);
    assert.equal(builderError(chart), null, `${y}/${x}`);
    const result = buildResult(chart);
    if (result.unavailable) { assert.equal(result.rows.length, 0);continue; }
    assert.ok(result.rows.every(r => r.value === null || Number.isFinite(r.value)), `${y}/${x}`);
    assert.ok(result.rows.every(r => new Set(r.ids).size === r.ids.length));
    const labels = result.series[0]?.points.map(p => p.label);
    assert.ok(result.series.every(s => JSON.stringify(s.points.map(p => p.label)) === JSON.stringify(labels)), `${y}/${x}`);
    assert.equal(resultCSV(chart, result).split("\r\n").length, result.rows.length + 1);
  }
});

test("versioned settings reject incompatible units, layouts, axes, additional series and malicious keys", () => {
  for (const chart of [
    recipe("cycleTime", "team"), recipe("cycleTime", "team", {}, { layout: "scatter" }),
    recipe("statusDays", "statusBand"), recipe("historicalCount", "reporting", { additional: "cycleTime" }),
    recipe("addedScope", "sprint", { value: "points" }),
    recipe("committedScope", "sprint", { value: "estimation" }),
    recipe("cycleTime", "team", { aggregation: "average" }, { layout: "stacked-column" }),
    recipe("completions", "completionDate", { bandWidth: 0 }),
    recipe("completions", "completionDate", { version: 99 }),
    recipe("completions", "completionDate", { sql: "select" }),
  ]) {
    assert.ok(builderError(chart));assert.equal(validChart(chart), false);
  }
  for (const seed of SEEDS) assert.deepEqual(upgradeChart(seed), seed);
});
