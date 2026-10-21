import test from "node:test";
import assert from "node:assert/strict";
import { SEEDS, LAYOUTS, METRICS, TICKETS, STATUSES, HISTORY, CUSTOM_DEFAULTS, FIELDS, GROUP_FIELDS, MEASURES, TEAMS, parseQuery, buildResult, stateAt, dayNumber, dateAt, csvCell, resultCSV, validChart, upgradeChart, validateFilters } from "../app/static/projects/flow_metrics/javascript/flow-metrics-model.mjs";

test("nine ordinary editable seed charts and all ten layouts", () => {
  assert.equal(SEEDS.length, 9);
  assert.equal(Object.keys(LAYOUTS).length, 10);
  assert.ok(SEEDS.every(validChart));
  assert.equal(validChart({ ...SEEDS[0], metric: "__proto__" }), false);
  assert.equal(validChart({ ...SEEDS[0], name: " " }), false);
  assert.equal(validChart({ ...SEEDS[0], threshold: 0 }), false);
});

test("all metric/layout previews produce matching finite table data and known ticket references", () => {
  for (const metric of Object.keys(METRICS)) {
    for (const layout of Object.keys(LAYOUTS)) {
      const result = buildResult({ ...CUSTOM_DEFAULTS, metric, layout });
      assert.deepEqual(result.rows, result.series.flatMap((s) => s.points.map((p) => ({ ...p, series: s.name }))));
      assert.ok(result.rows.every((p) => Number.isFinite(p.value) && p.value >= 0));
      assert.ok(result.rows.every((p) => p.ids.every((id) => TICKETS.some((t) => t.id === id))));
      assert.equal(result.sampleSize, new Set(result.rows.flatMap((p) => p.ids)).size);
    }
  }
});

test("cycle time is exact calendar days with same-day zero and inclusive date window", () => {
  const chart = { metric: "cycle", layout: "scatter", threshold: 7 };
  const result = buildResult(chart);
  const sameDay = TICKETS.find((t) => t.done !== null && t.done === t.start);
  assert.equal(result.rows.find((p) => p.ids.includes(sameDay.id)).value, 0);
  const singleDay = buildResult(chart, { from: dateAt(sameDay.done), to: dateAt(sameDay.done) });
  assert.ok(singleDay.rows.some((p) => p.ids.includes(sameDay.id)));
  for (const row of result.rows) {
    const ticket = TICKETS.find((t) => row.ids.includes(t.id));
    assert.equal(row.value, ticket.done - ticket.start);
  }
});

test("throughput counts every filtered completion exactly once", () => {
  const result = buildResult({ metric: "throughput", layout: "column", threshold: 7 }, { team: "Blueprint", from: "2026-07-10", to: "2026-08-01" });
  const expected = TICKETS.filter((t) => t.team === "Blueprint" && t.done !== null && t.done >= 9 && t.done <= 31);
  assert.equal(result.rows.reduce((sum, p) => sum + p.value, 0), expected.length);
  assert.equal(result.sampleSize, expected.length);
});

test("status and cumulative flow conserve items present on each sample day", () => {
  const result = buildResult({ metric: "flow", layout: "flow", threshold: 7 });
  assert.deepEqual(result.series.map((s) => s.name), STATUSES);
  for (let day = 0; day <= dayNumber(HISTORY.to); day++) {
    assert.equal(result.series.reduce((sum, s) => sum + s.points[day].value, 0), TICKETS.filter((t) => t.created <= day).length);
  }
});

test("stuck threshold includes review and blocked work and filters at reporting end", () => {
  const result = buildResult({ metric: "stuck", layout: "bar", threshold: 7 });
  assert.ok(result.rows.length > 0);
  for (const row of result.rows) {
    const ticket = TICKETS.find((t) => t.id === row.ticketId);
    const state = stateAt(ticket, result.to);
    assert.ok(["In Progress", "In Review", "Blocked / On Hold"].includes(state.status));
    assert.equal(row.value, result.to - state.since);
    assert.ok(row.value >= 7);
  }
  assert.equal(buildResult({ metric: "stuck", layout: "bar", threshold: 365 }).sampleSize, 0);
});

test("team and sprint filters propagate to every contributing ticket", () => {
  for (const seed of SEEDS) {
    const result = buildResult(seed, { team: "Blueprint", sprint: "Sample sprint 2" });
    assert.ok(result.tickets.every((t) => t.team === "Blueprint" && t.sprint === "Sample sprint 2"));
    assert.ok(result.rows.every((p) => p.ids.every((id) => result.tickets.some((t) => t.id === id))));
  }
});

test("invalid dates and selectors are rejected rather than silently defaulted", () => {
  for (const filters of [
    { from: "2026-08-20", to: "2026-07-01" }, { from: "2026-07-32" },
    { to: "2025-01-01" }, { from: "not a date" }, { team: "Unknown" }, { sprint: "Real sprint" },
    { type: "Secret" }, { status: "Invalid" }, { team: null }, { unknown: "filter" },
  ]) assert.throws(() => validateFilters(filters));
});

test("CSV is exact plotted rows, labelled synthetic, quoted and formula-neutralised", () => {
  const seed = SEEDS[5];
  const result = buildResult(seed, { team: "Blueprint" });
  const csv = resultCSV(seed, result, { team: "Blueprint" });
  assert.equal(csv.split("\r\n").length, result.rows.length + 1);
  assert.ok(csv.includes("Demonstration data only"));
  assert.ok(csv.includes("Blueprint"));
  assert.equal(csvCell('=SUM(1,2)'), '"\'=SUM(1,2)"');
  assert.equal(csvCell('  +formula'), '"\'  +formula"');
  assert.equal(csvCell('hello "world"'), '"hello ""world"""');
});

test("unfiltered charts combine the actual team values", () => {
  assert.deepEqual(TEAMS, ["Blueprint", "DevX", "Engineering Platform"]);
  const combined = buildResult(CUSTOM_DEFAULTS);
  const parts = TEAMS.map((team) => buildResult(CUSTOM_DEFAULTS, { team }));
  assert.equal(combined.sampleSize, 72);
  assert.equal(combined.sampleSize, parts.reduce((sum, p) => sum + p.sampleSize, 0));
  assert.ok(TICKETS.every((t) => TEAMS.includes(t.team)));
});

test("custom categories, grouping and all available measures produce aligned points with exact contributors", () => {
  for (const x of Object.keys(FIELDS).filter(key => !["reporting", "completionDate", "statusBand", "durationBand", "ticket"].includes(key))) {
    for (const group of ["", ...Object.keys(GROUP_FIELDS).filter(key => key !== "scopeChange")]) {
      for (const y of ["count", "points", "averagePoints", "averageCycle", "averageAge", "estimation", "averageEstimation"]) {
        const result = buildResult({ ...CUSTOM_DEFAULTS, x, y, group });
        const labels = result.series[0]?.points.map((p) => p.label);
        for (const series of result.series) {
          assert.deepEqual(series.points.map((p) => p.label), labels);
          for (const row of series.points) {
            const matches = TICKETS.filter((t) => row.ids.includes(t.id));
            if (group && group !== "status") assert.ok(matches.every((t) => String(t[group]) === series.name));
            const total = matches.reduce((sum, t) => sum + (y === "averageCycle" ? t.done - t.start
              : y === "averageAge" ? result.to - t.created : t.points), 0);
            const expected = y === "count" ? matches.length : y === "points" ? total
              : matches.length ? Number((total / matches.length).toFixed(2)) : null;
            assert.equal(row.value, expected, `${x}/${group}/${y}/${row.label}`);
          }
        }
      }
    }
  }
});

test("custom count and sum groupings conserve totals with known-answer values", () => {
  for (const x of ["status", "team", "type", "planned", "objective", "repository", "sprint"]) {
    const result = buildResult({ ...CUSTOM_DEFAULTS, x, group: "team" });
    assert.equal(result.rows.reduce((sum, p) => sum + p.value, 0), 72);
    const points = buildResult({ ...CUSTOM_DEFAULTS, x, group: "team", y: "points" });
    assert.equal(points.rows.reduce((sum, p) => sum + p.value, 0), TICKETS.reduce((sum, t) => sum + t.points, 0));
  }
});

test("each chart's saved filters feed result, exact rows and CSV without global overrides", () => {
  const chart = {
    ...CUSTOM_DEFAULTS, name: "Blueprint planned bug points", x: "status", y: "points", group: "type",
    filters: { team: "Blueprint", sprint: "Sample sprint 2", type: "Bug", planned: "Planned", to: "2026-08-05" },
  };
  const result = buildResult(chart);
  const expected = TICKETS.filter((t) => t.team === "Blueprint" && t.sprint === "Sample sprint 2"
    && t.type === "Bug" && t.planned === "Planned" && t.created <= dayNumber("2026-08-05"));
  assert.equal(result.sampleSize, expected.length);
  assert.equal(result.rows.reduce((sum, r) => sum + r.value, 0), expected.reduce((sum, t) => sum + t.points, 0));
  const csv = resultCSV(chart, result);
  for (const value of ["Blueprint", "Sample sprint 2", "Bug", "Planned", "05/08/2026", "Sum of points"]) assert.ok(csv.includes(value));
  assert.equal(buildResult(CUSTOM_DEFAULTS).sampleSize, 72);
});

test("created/completed week axes respect inclusive dates and exclude unfinished completions", () => {
  for (const x of ["created", "completed"]) {
    const filters = { from: "2026-07-10", to: "2026-07-20" };
    const result = buildResult({ ...CUSTOM_DEFAULTS, x, filters });
    const expected = TICKETS.filter((t) => {
      const day = x === "created" ? t.created : t.done;
      return day !== null && day >= 9 && day <= 19;
    });
    assert.equal(result.rows.reduce((sum, p) => sum + p.value, 0), expected.length);
    assert.equal(result.sampleSize, expected.length);
  }
});

test("legacy chart definitions keep IDs/names and acquire custom settings and per-chart defaults", () => {
  const legacy = { id: "old", name: "My chart", metric: "status", layout: "column", threshold: 7 };
  const upgraded = upgradeChart(legacy);
  assert.ok(validChart(upgraded));
  assert.equal(upgraded.id, "old");
  assert.equal(upgraded.filters.team, "");
  assert.equal(upgradeChart({ ...legacy, filters: { team: "DevX" } }).filters.team, "DevX");
  assert.equal(upgradeChart({ ...legacy, filters: { team: "Blueprint" } }).filters.team, "Blueprint");
  assert.throws(() => upgradeChart({ ...legacy, x: "__proto__" }));
  assert.throws(() => upgradeChart({ ...legacy, filters: null }));
  assert.equal(validChart({ ...upgraded, y: "SQL" }), false);
});

test("search filters parse quoted fields, keywords and exact sample values without evaluation", () => {
  assert.deepEqual(parseQuery('team:"Engineering Platform" status:Done workflow'), [
    { field: "team", value: "Engineering Platform" }, { field: "status", value: "Done" }, { field: "keyword", value: "workflow" },
  ]);
  assert.deepEqual(parseQuery("   "), []);
  for (const query of ["team:", 'status:"Done', "assignee:person", "label:bug", "status:Secret", "unknown:x", "x".repeat(1001)]) {
    assert.throws(() => parseQuery(query), query);
  }
  assert.throws(() => validateFilters({ query: "from:2026-08-20 to:2026-07-01" }));
});

test("search fields filter the same chart, rows, drill contributors and CSV scope", () => {
  const chart = {
    ...CUSTOM_DEFAULTS, name: "Filtered work", x: "status", group: "team",
    filters: { query: 'team:"Engineering Platform" status:Done repository:sample-repository-alpha title:"Sample" from:2026-07-01 to:2026-08-11' },
  };
  const result = buildResult(chart);
  const expected = TICKETS.filter((t) => t.team === "Engineering Platform" && t.repository === "sample-repository-alpha"
    && stateAt(t, dayNumber("2026-08-11"))?.status === "Done");
  assert.ok(expected.length > 0);
  assert.equal(result.sampleSize, expected.length);
  assert.equal(result.rows.reduce((sum, row) => sum + row.value, 0), expected.length);
  const csv = resultCSV(chart, result);
  for (const value of ["Engineering Platform", "11/08/2026", "Done", "sample-repository-alpha", "title: Sample"]) assert.ok(csv.includes(value));
  assert.throws(() => buildResult({ ...CUSTOM_DEFAULTS, filters: { query: 'team:"Developer Experience"' } }));
  const open = buildResult({ ...CUSTOM_DEFAULTS, filters: { query: "is:open" } });
  assert.ok(open.tickets.every((t) => stateAt(t, open.to)?.status !== "Done"));
  const keyword = buildResult({ ...CUSTOM_DEFAULTS, filters: { query: '"documentation task"' } });
  assert.ok(keyword.tickets.length > 0 && keyword.tickets.every((t) => t.title.includes("documentation task")));
});
