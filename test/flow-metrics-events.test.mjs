import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { SAMPLE_DATA } from "../app/static/projects/flow_metrics/javascript/flow-metrics-sample-data.mjs";
import { configureSampleData, buildResult, CUSTOM_DEFAULTS, METRICS, LAYOUTS, dateAt, stateAt, scopeLabels, resultCSV, upgradeChart, configureLiveData, SEARCH_FIELDS, displayDate, captureLabel, SEEDS } from "../app/static/projects/flow_metrics/javascript/flow-metrics-model.mjs";

configureSampleData(SAMPLE_DATA);
const chart = (metric, query = "") => ({ ...structuredClone(CUSTOM_DEFAULTS), id: "test", name: metric, metric, filters: { ...CUSTOM_DEFAULTS.filters, query } });

test("packaged database seed exactly preserves the full current fictional contract and definitions", () => {
  const seed = JSON.parse(readFileSync(new URL("../app/projects/flow_metrics/sample-seed.json", import.meta.url)));
  assert.deepEqual(seed.dataset, SAMPLE_DATA);
  assert.deepEqual(seed.charts, SEEDS);
});

test("scatter maps one point per completed ticket to its latest date and calendar-day duration", () => {
  const definition = { ...chart("cycle", 'sprint:"Sprint A" to:2026-09-27'), layout: "scatter" };
  const result = buildResult(definition);
  assert.equal(result.rows.length, 5);
  const known = {
    "SAMPLE-1-01": ["2026-09-18", 4], "SAMPLE-1-02": ["2026-09-16", 0],
    "SAMPLE-1-03": ["2026-09-22", 8], "SAMPLE-1-04": ["2026-09-24", 10],
    "SAMPLE-1-11": ["2026-09-23", 6],
  };
  for (const row of result.rows) {
    assert.equal(row.ids.length, 1);
    assert.deepEqual([row.completedDate, row.value], known[row.ids[0]]);
    assert.equal(row.x, Date.parse(`${row.completedDate}T00:00:00Z`));
  }
  assert.equal(new Set(result.rows.flatMap((row) => row.ids)).size, 5);
  const csv = resultCSV(definition, result);
  for (const [id, [date]] of Object.entries(known)) {
    assert.ok(csv.includes(id));
    assert.ok(csv.includes(displayDate(date)));
  }
});

test("cycle histogram is exhaustive disjoint three-day ticket bands, not aggregate-point counts", () => {
  const definition = { ...chart("cycle", 'sprint:"Sprint A" to:2026-09-27'), layout: "histogram" };
  const result = buildResult(definition);
  assert.deepEqual(result.rows.map((row) => [row.label, row.value]), [
    ["0–2 days", 1], ["3–5 days", 1], ["6–8 days", 2], ["9–11 days", 1],
  ]);
  assert.equal(result.rows.reduce((sum, row) => sum + row.value, 0), 5);
  assert.ok(result.rows.every((row) => row.ids.length === row.value));
  assert.equal(new Set(result.rows.flatMap((row) => row.ids)).size, 5);
  assert.equal(resultCSV(definition, result).split("\r\n").length, 5);
  const filtered = buildResult({ ...definition, filters: { ...definition.filters, query: 'team:Blueprint sprint:"Sprint A" to:2026-09-27' } });
  assert.equal(filtered.rows.reduce((sum, row) => sum + row.value, 0), 2);
  assert.deepEqual(filtered.rows.flatMap((row) => row.ids).sort(), ["SAMPLE-1-02", "SAMPLE-1-11"]);
});

test("duration band boundaries include 0,2,3,5,6,8 and empty completion windows", () => {
  const data = structuredClone(SAMPLE_DATA);
  data.tickets = [0, 2, 3, 5, 6, 8].map((duration, index) => ({
    ...structuredClone(SAMPLE_DATA.tickets[0]), id: `SAMPLE-BOUNDARY-${index}`,
    events: [
      { date: "2026-09-14", type: "scope", value: "sample-a" },
      { date: "2026-09-14", type: "status", value: "In Progress" },
      { date: new Date(Date.parse("2026-09-14T00:00:00Z") + duration * 86400000).toISOString().slice(0, 10), type: "status", value: "Done" },
    ],
  }));
  try {
    configureSampleData(data);
    const definition = { ...chart("cycle"), layout: "histogram" };
    assert.deepEqual(buildResult(definition).rows.map((row) => row.value), [2, 2, 2]);
    assert.equal(buildResult({ ...definition, filters: { ...definition.filters, from: "2026-10-19" } }).sampleSize, 0);
  } finally { configureSampleData(SAMPLE_DATA); }
});

test("display dates use day/month/year without changing stored dates", () => {
  assert.equal(displayDate("2026-10-19"), "19/10/2026");
  assert.match(scopeLabels().join(" "), /12\/09\/2026 to 19\/10\/2026/);
  assert.equal(captureLabel("2026-10-19T16:37:00Z"), "Last updated: 19 October 2026 at 5:37pm");
  assert.equal(captureLabel("2026-12-19T16:37:00Z"), "Last updated: 19 December 2026 at 4:37pm");
  assert.equal(SAMPLE_DATA.history.to, "2026-10-19");
});
test("every sample filter has data and metadata clauses filter exact contributors", () => {
  assert.ok(SEARCH_FIELDS.every((field) => Array.isArray(field[2])));
  for (const key of ["assignee", "label", "milestone", "reviewers", "priority", "refined",
    "blocked-by", "blocking", "relates-to", "parent-issue", "sub-issues-progress"]) {
    const values = SEARCH_FIELDS.find(([field]) => field === key)[2];
    assert.ok(values.some((value) => value !== "Not set"), key);
    for (const value of values) {
      const definition = chart("status", `${key}:${JSON.stringify(value)}`);
      const result = buildResult(definition);
      const expected = SAMPLE_DATA.tickets.filter((ticket) =>
        Array.isArray(ticket[key]) ? ticket[key].includes(value) : ticket[key] === value);
      assert.deepEqual(result.tickets.map((ticket) => ticket.id).sort(), expected.map((ticket) => ticket.id).sort(), `${key}:${value}`);
      assert.equal(result.rows.reduce((sum, row) => sum + row.value, 0), expected.length);
      assert.ok(resultCSV(definition, result).includes(key));
    }
  }
  const combined = buildResult(chart("status", 'assignee:sample-contributor-2 label:sample-maintenance'));
  assert.ok(combined.tickets.length);
  assert.ok(combined.tickets.every((ticket) => ticket.assignee.includes("sample-contributor-2")
    && ticket.label.includes("sample-maintenance")));
});

test("all metrics and layouts match table rows and exact contributors", () => {
  for (const metric of Object.keys(METRICS)) {
    for (const layout of Object.keys(LAYOUTS)) {
      const result = buildResult({ ...chart(metric), layout });
      if (["scatter", "histogram"].includes(layout) && metric !== "cycle") {
        assert.match(result.unavailable, /require Cycle time/);
        assert.equal(result.rows.length, 0);
        continue;
      }
      assert.ok(result.rows.length > 0, `${metric}/${layout}`);
      assert.deepEqual(result.rows, result.series.flatMap((series) => series.points.map((point) => ({ ...point, series: series.name }))));
      assert.ok(result.rows.every((row) => row.value === null || Number.isFinite(row.value)));
      assert.ok(result.rows.every((row) => row.ids.every((id) => result.tickets.some((ticket) => ticket.id === id))));
    }
  }
});

test("velocity uses start commitments, end estimates and flags the partial Firebreak", () => {
  const result = buildResult(chart("velocity"));
  assert.deepEqual(result.series[0].points.map((point) => point.value), [38, 46, 54]);
  assert.deepEqual(result.series[1].points.map((point) => point.value), [12, 12, 3]);
  assert.match(result.series[1].points[2].label, /in progress/);
  assert.deepEqual(buildResult(chart("velocity", 'sprint:"Sprint B"')).series.map((series) => series.points.length), [1, 1]);
});

test("churn counts scope events and keeps unique ticket contributors", () => {
  const result = buildResult(chart("churn", 'sprint:"Sprint A"'));
  assert.deepEqual(result.series.map((series) => series.points[0].value), [3, 1]);
  assert.equal(result.series[0].points[0].ids.length, 3);
});

test("latest completion, reopen and same-day cycle semantics", () => {
  const result = buildResult(chart("cycle", 'sprint:"Sprint A" to:2026-09-27'));
  assert.equal(result.rows.find((row) => row.ids.includes("SAMPLE-1-02")).value, 0);
  assert.equal(result.rows.find((row) => row.ids.includes("SAMPLE-1-04")).value, 10);
  assert.ok(!result.rows.some((row) => row.ids.includes("SAMPLE-1-05")));
  const throughput = buildResult(chart("throughput", "from:2026-09-14 to:2026-09-27"));
  assert.equal(throughput.rows.reduce((sum, row) => sum + row.value, 0), 5);
});

test("flow conserves each day's items and respects historical sprint scope", () => {
  const result = buildResult(chart("flow"));
  for (let i = 0; i <= result.to - result.from; i++) {
    const day = result.from + i;
    assert.equal(result.series.reduce((sum, series) => sum + series.points[i].value, 0),
      SAMPLE_DATA.tickets.filter((ticket) => ticket.created <= dateAt(day)).length);
  }
  const scoped = buildResult(chart("flow", 'sprint:"Sprint B" from:2026-09-28 to:2026-09-28'));
  assert.equal(scoped.rows.reduce((sum, row) => sum + row.value, 0), 11);
});

test("progress follows additions, removals, carryover and reopen events", () => {
  const result = buildResult(chart("progress", 'sprint:"Sprint A" from:2026-09-14 to:2026-09-27'));
  assert.equal(result.series[0].points[0].value, 10);
  assert.equal(result.series[0].points[3].value, 11);
  assert.equal(result.series[0].points[6].value, 12);
  assert.equal(result.series[1].points.at(-1).value, 5);
});

test("all metrics honour distinct DevX filters, saved definitions and CSV context", () => {
  for (const metric of Object.keys(METRICS)) {
    const definition = upgradeChart(chart(metric, "team:DevX"));
    const result = buildResult(definition);
    assert.ok(result.tickets.every((ticket) => ticket.team === "DevX"));
    assert.ok(resultCSV(definition, result).includes("DevX"));
  }
  assert.equal(upgradeChart({ ...chart("status"), filters: { team: "DevX" } }).filters.team, "DevX");
  assert.equal(scopeLabels()[0], "All teams");
});

test("age and stuck use creation and latest status entry, including review", () => {
  for (const metric of ["age", "stuck"]) {
    const result = buildResult(chart(metric));
    for (const row of result.rows) {
      const ticket = result.tickets.find((entry) => entry.id === row.ticketId);
      const state = stateAt(ticket, result.to);
      assert.notEqual(state.status, "Done");
      assert.equal(row.value, result.to - (metric === "age" ? ticket.created : state.since));
    }
    assert.ok(result.rows.length);
  }
});

test("live team options come only from data and never erase DevX", () => {
  configureLiveData({ history: { from: "2026-10-16", to: "2026-10-19" }, options: { team: ["DevX", "New team", "Not set"], status: ["TODO"] } });
  assert.deepEqual(SEARCH_FIELDS.find(([key]) => key === "team")[2], ["DevX", "New team", "Not set"]);
  assert.equal(upgradeChart({ ...chart("status"), filters: { team: "DevX" } }).filters.team, "DevX");
  configureSampleData(SAMPLE_DATA);
});
