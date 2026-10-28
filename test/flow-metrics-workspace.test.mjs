import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { SAMPLE_DATA } from "../app/static/projects/flow_metrics/javascript/flow-metrics-sample-data.mjs";
import { configureSampleData, buildResult, CUSTOM_DEFAULTS, resultCSV, SEARCH_FIELDS, ticketChartLabel, ticketReference, ticketText, pointTicket, itemCount, datePresetRange, withDateRange, resolveFilters, chartHasDateAxis, HISTORY, validateFilters, validChart, scopeLabels } from "../app/static/projects/flow_metrics/javascript/flow-metrics-model.mjs";
import { editableRecipe, builderError } from "../app/static/projects/flow_metrics/javascript/flow-metrics-builder.mjs";
import { observationLoader, setRealObservation, usesObservedHistory, setObservedResult, resultTicket, mergeObservedResult, SEEDS } from "../app/static/projects/flow_metrics/javascript/flow-metrics-model.mjs";

const real = (id, status = "TODO", extra = {}) => ({
  id: `real:${id}`, sourceId: id, datasetId: "ministryofjustice/152", provenance: "real",
  reference: `synthetic/repository#${id}`, title: "Fictional test of genuine adapter",
  url: `https://github.com/synthetic/repository/issues/${id}`,
  createdDate: "2026-10-13", observedAt: "2026-10-19T12:00:00Z",
  observedStatus: status, status, team: "DevX", sprint: "Firebreak",
  actualSprint: "🔥 Firebreak", sprintId: "real:iteration-1",
  repository: "synthetic/repository", type: "Issue", state: "OPEN", points: null,
  availableFields: ["status", "team", "sprint", "repository", "type", "title", "is"],
  ...extra,
});
const dataset = () => ({
  ...structuredClone(SAMPLE_DATA), provenance: "mixed",
  realObservations: [
    { capturedAt: "2026-10-16T12:00:00Z", items: [real("1")] },
    { capturedAt: "2026-10-18T12:00:00Z", items: [real("1", "In Progress")] },
    { capturedAt: "2026-10-19T12:00:00Z", items: [real("1", "Done", { state: "CLOSED" }), real("2")] },
  ],
});
const chart = (metric = "status", query = "", layout = "column") => ({
  ...structuredClone(CUSTOM_DEFAULTS), metric, layout, name: "Union", filters: { ...CUSTOM_DEFAULTS.filters, query },
});
const total = result => result.rows.reduce((sum, row) => sum + row.value, 0);
const ids = result => [...new Set(result.rows.flatMap(row => row.ids))].sort();

const projection = (series = [], extra = {}) => ({
  series, rows: series.flatMap(group => group.points.map(row => ({ ...row, series: group.name }))),
  tickets: [], itemStates: {}, captures: ["2026-10-28T12:00:00Z"], unit: "Items",
  baselineComplete: false, unavailable: "Captured history is insufficient for this calculation.", note: "Observed between captures.",
  ...extra,
});

test("all default built-ins and editable charts keep sample history when genuine history is insufficient", () => {
  const data = dataset();
  data.fictionalHistory = { ...SAMPLE_DATA.history };
  data.history.to = "2026-10-28";
  configureSampleData(data);
  for (const definition of SEEDS) {
    setObservedResult(null);
    const sample = buildResult(definition);
    assert.equal(sample.unavailable, null, definition.metric);
    assert.ok(sample.sampleSize > 0, definition.metric);
    setObservedResult(projection());
    const combined = buildResult(definition);
    assert.equal(combined.unavailable, null, definition.metric);
    assert.deepEqual(combined.rows, sample.rows);
    assert.deepEqual(buildResult(editableRecipe(definition)).rows, combined.rows, `${definition.metric} editable`);
  }
  for (const metric of ["flow", "progress", "throughput", "churn", "velocity"]) {
    setObservedResult(null);
    const filtered = chart(metric, "source:Fictional from:2026-10-20 to:2026-10-28");
    const result = buildResult(filtered);
    assert.equal(result.rows.length, 0, `${metric}: no sample continuation after its last date`);
  }
  for (const measure of ["count", "averageCycle", "points"]) {
    const custom = { ...chart("custom", "source:Fictional from:2026-10-20 to:2026-10-28"), x: "completed", y: measure };
    assert.equal(buildResult(custom).rows.length, 0, `${measure}: no invented sample-only week`);
  }
});

test("observed projections preserve mixed series, null baselines, exact row states, CSV and real links", () => {
  const data = dataset();
  data.fictionalHistory = { ...SAMPLE_DATA.history };
  data.history.to = "2026-10-28";
  configureSampleData(data);
  const original = real("1", "TODO", { observedAt: "2026-10-18T12:00:00Z" });
  const latest = real("1", "Done", { observedAt: "2026-10-28T12:00:00Z" });
  const point = {
    key: "2026-10-18", label: "18 Oct", value: 1, ids: ["real:1"],
    stateIds: { "real:1": "real:1@earlier" }, observedAt: original.observedAt, timeBasis: "observation",
  };
  setObservedResult(projection([{ name: "TODO", points: [point] }], {
    tickets: [latest], itemStates: { "real:1@earlier": original }, unavailable: null,
  }));
  const definition = chart("flow");
  const result = buildResult(definition);
  assert.ok(ids(result).some(id => id.startsWith("SAMPLE-")));
  const row = result.rows.find(row => row.stateIds?.["real:1"]);
  assert.equal(resultTicket(result, row, "real:1"), original);
  assert.equal(resultTicket(result, row, "real:1").status, "TODO", "Not the final capture's status");
  assert.equal(resultTicket(result, row, "real:1").url, latest.url);
  assert.ok(resultCSV(definition, result).includes(original.observedAt));
  assert.deepEqual(buildResult(editableRecipe(definition)).rows, result.rows);
  const genuineOnly = buildResult(chart("flow", "source:Genuine"));
  assert.deepEqual(ids(genuineOnly), ["real:1"], "An explicit Genuine source never injects samples");
  setObservedResult(projection([], { captures: [], baselineComplete: null, unavailable: null }));
  const fictionalOnly = buildResult(chart("flow", "source:Fictional"));
  assert.ok(ids(fictionalOnly).every(id => id.startsWith("SAMPLE-")));
  assert.ok(fictionalOnly.rows.every(row => row.key <= SAMPLE_DATA.history.to));
  const sample = { ...result, series: [], rows: [], tickets: [], unavailable: "Missing baseline" };
  const observed = projection([
    { name: "Committed", points: [{ ...point, ids: [], stateIds: {}, value: null }] },
    { name: "Completed", points: [{ ...point, value: 1 }] },
  ], { tickets: [latest], unavailable: null });
  const merged = mergeObservedResult(sample, observed);
  assert.equal(merged.rows[0].value, null);
  assert.equal(merged.rows[1].value, 1);
  assert.equal(merged.unavailable, null, "Missing baseline doesn't suppress supported completed scope");
  const compressed = { ...merged, itemStates: { stable: { ...original, observedAt: undefined } } };
  const historicalRow = { ...point, stateIds: { "real:1": "stable" }, stateObservedAt: { "real:1": original.observedAt } };
  assert.equal(resultTicket(compressed, historicalRow, "real:1").observedAt, original.observedAt);
  setObservedResult(null);
});

test("bounded observations preserve history, source filters, exact rows, CSV and contributors", async () => {
  const full = dataset();
  full.realObservations[0].items[0].team = "Historical team";
  const bounded = {
    ...structuredClone(full), realObservations: [],
    realCaptures: full.realObservations.map(({ capturedAt, items }, index) => ({ id: `${index}`, capturedAt, source: "generated" })),
    realOptions: { team: ["Historical team", "DevX"], status: ["TODO", "In Progress", "Done"], sprint: ["Firebreak"] },
  };
  for (const [metric, to] of [["status", "2026-10-19"], ["age", "2026-10-18"], ["cycle", "2026-10-19"], ["flow", "2026-10-19"]]) {
    for (const source of ["", " source:Fictional", " source:Genuine"]) {
      const definition = chart(metric, `to:${to}${source}`);
      configureSampleData(structuredClone(full));
      const expected = buildResult(definition);
      const csv = resultCSV(definition, expected);
      configureSampleData(structuredClone(bounded));
      const load = observationLoader(bounded.realCaptures, async date =>
        structuredClone(full.realObservations.filter(entry => entry.capturedAt.slice(0, 10) <= date).at(-1)));
      setRealObservation(await load(definition.filters));
      const actual = buildResult(definition);
      assert.deepEqual(actual, expected);
      assert.equal(resultCSV(definition, actual), csv);
      assert.ok(SEARCH_FIELDS.find(([key]) => key === "team")[2].includes("Historical team"));
      assert.deepEqual(SEARCH_FIELDS.find(([key]) => key === "source")[2], ["Fictional", "Genuine"]);
      if (metric === "cycle" && source.includes("Genuine")) assert.equal(actual.unavailable, "Not enough history to calculate cycle time yet.");
    }
  }
});

test("observation loader resolves query dates, predecessor, bounded cache and retry", async () => {
  configureSampleData(dataset());
  const captures = dataset().realObservations.map(({ capturedAt }, index) => ({ id: `${index}`, capturedAt, source: "generated" }));
  const calls = [];
  let fail = false;
  const load = observationLoader(captures, async to => {
    calls.push(to);
    if (fail) throw new Error("Observation unavailable");
    return { selected: to };
  });
  const filters = { ...CUSTOM_DEFAULTS.filters, to: "2026-10-19", query: "to:2026-10-18" };
  assert.deepEqual(await load(filters), { selected: "2026-10-18" });
  await load(filters);
  assert.equal(calls.length, 1, "same selected capture uses one cached request");
  await load({ ...filters, from: "2026-10-17", query: "to:2026-10-17" });
  assert.equal(calls.at(-1), "2026-10-17", "predecessor capture before lower date remains usable");
  assert.equal(await load({ ...filters, to: "2026-10-15", query: "" }), null);
  assert.equal(calls.length, 2, "no later capture is substituted before first observation");
  fail = true;
  await assert.rejects(load(filters), /Observation unavailable/);
  fail = false;
  await load(filters);
  assert.equal(calls.length, 4, "failed requests do not poison the cache");
  await load({ ...filters, query: "to:2026-10-19" });
  await load(filters);
  assert.equal(calls.length, 6, "only one capture request is cached");
});

for (const metric of ["status", "flow"]) test(`actual async ${metric} preview discards stale responses and disables stale exports`, async () => {
  configureSampleData(dataset());
  const source = readFileSync(new URL("../app/static/projects/flow_metrics/javascript/flow-metrics.js", import.meta.url), "utf8");
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, { hidden: false, disabled: false, replaceChildren() {} });
    return elements.get(id);
  };
  const pending = [];
  const projections = [];
  const context = {
    live: false, previewSequence: 0, pendingPreview: false, chart: null, result: { old: true },
    draft: chart(metric, "to:2026-10-18"), $: element, setRealObservation, buildResult,
    usesObservedHistory, resolveFilters, HISTORY, setObservedResult,
    apiRequest: (route, definition) => new Promise((resolve, reject) => {
      assert.equal(route, "observed-result");
      projections.push({ definition, resolve, reject });
    }),
    loadObservation: filters => new Promise((resolve, reject) => pending.push({ filters, resolve, reject })),
    dirty: () => false, chartIcon: () => ({}), document: { createTextNode: text => text },
    renderScope() {}, renderDateRanges() {}, renderTable() {}, renderList() {}, updateView() {},
    message(text) { context.error = text; }, window: { Chart: true }, setTimeout: resolve => resolve(),
  };
  runInNewContext(source.slice(source.indexOf("async function renderPreview()"), source.indexOf("\nfunction closeDateRange()")), context);
  const earlier = context.renderPreview();
  await Promise.resolve();
  assert.equal(element("export-csv").disabled, true);
  assert.equal(element("chart-view").hidden, true);
  assert.equal(context.result, null);
  context.draft = chart(metric, "to:2026-10-19");
  const newer = context.renderPreview();
  await Promise.resolve();
  pending[1].resolve(dataset().realObservations[2]);
  if (metric === "flow") {
    assert.equal(projections.length, 2, context.error || JSON.stringify(context.draft));
    assert.equal(projections[1].definition.filters.to, "2026-10-19");
    projections[1].resolve(projection());
  }
  await newer;
  const latest = context.result;
  assert.ok(latest.tickets.some(item => item.sourceId === "2"));
  pending[0].resolve(dataset().realObservations[1]);
  if (metric === "flow") projections[0].resolve(projection());
  await earlier;
  assert.equal(context.result, latest);
  const failed = context.renderPreview();
  await Promise.resolve();
  if (metric === "flow") {
    pending[2].resolve(dataset().realObservations[2]);
    projections[2].reject(new Error("Cannot read observation"));
  } else pending[2].reject(new Error("Cannot read observation"));
  await failed;
  assert.equal(context.result, null);
  assert.equal(element("export-csv").disabled, true);
  assert.equal(element("table-view").hidden, true);
  assert.equal(context.error, "Cannot read observation");
});

test("Admin Manage uses the configured rendered workspace identity", () => {
  const source = readFileSync(new URL("../app/static/projects/flow_metrics/javascript/flow-metrics.js", import.meta.url), "utf8");
  let handler;
  const context = {
    $: id => id === "manage-current-board"
      ? { addEventListener(_type, callback) { handler = callback; } }
      : { textContent: '<b>Team & "Platform"</b>' },
    openAdminPanel(...args) { context.opened = args; },
  };
  const listener = source.split("\n").find(line => line.startsWith('$("manage-current-board").addEventListener'));
  runInNewContext(listener, context);
  const trigger = {};
  handler({ currentTarget: trigger });
  assert.deepEqual(context.opened, ["admin-manage", trigger, "admin-dialog-title", '<b>Team & "Platform"</b>']);
  assert.match(source.slice(source.indexOf("function openAdminPanel("), source.indexOf("function openTeamSetup(")), /\$\("admin-dialog-title"\)\.textContent = title/);
});

test("date shortcuts use available history and preserve one canonical filter system", () => {
  configureSampleData(dataset());
  assert.deepEqual(datePresetRange("2weeks", { from: "2026-01-01", to: "2026-03-31" }), { from: "2026-03-18", to: "2026-03-31" });
  assert.deepEqual(datePresetRange("1month", { from: "2026-01-01", to: "2026-03-31" }), { from: "2026-03-01", to: "2026-03-31" });
  assert.deepEqual(datePresetRange("3months", { from: "2025-01-01", to: "2026-03-31" }), { from: "2026-01-01", to: "2026-03-31" });
  assert.deepEqual(datePresetRange("2weeks", { from: "2026-03-30", to: "2026-03-31" }), { from: "2026-03-30", to: "2026-03-31" });
  const original = { ...CUSTOM_DEFAULTS.filters, from: "2026-10-16", query: 'title:"Fictional test" #2 from:2026-10-17 to:2026-10-18' };
  const changed = withDateRange(original, "2026-10-18", "2026-10-19");
  const { resolved, clauses } = resolveFilters(changed);
  assert.equal(resolved.from, "2026-10-18");
  assert.equal(resolved.to, "2026-10-19");
  assert.equal(clauses.filter(c => c.field === "from").length, 1);
  assert.deepEqual(clauses.filter(c => !["from", "to"].includes(c.field)), [{field:"title",value:"Fictional test"},{field:"keyword",value:"#2"}]);
  const max = resolveFilters(withDateRange(changed, "", "")).resolved;
  assert.equal(max.from, ""); assert.equal(max.to, "");
  assert.throws(() => withDateRange(original, "2026-10-19", "2026-10-18"));
  assert.throws(() => withDateRange(original, "1900-01-01", "2026-10-19"));
  assert.equal(chartHasDateAxis(chart("status")), false);
  assert.equal(chartHasDateAxis(chart("age")), false);
  assert.equal(chartHasDateAxis(chart("throughput")), true);
  assert.equal(chartHasDateAxis({...chart("custom"),x:"reporting"}), true);
});

test("chart ticket labels are short without losing repository identity elsewhere", () => {
  const ticket = real("511");
  assert.equal(ticketChartLabel(ticket), "#511");
  assert.equal(ticketReference(ticket), "synthetic/repository#511");
  assert.match(ticketText(ticket), /synthetic\/repository#511/);
  assert.equal(ticketChartLabel(real("511", "TODO", { reference: "another/repository#511" })), "#511");
  assert.equal(ticketChartLabel({ id: "SAMPLE-1-05" }), "SAMPLE-1-05");
  assert.equal(ticketChartLabel({ provenance: "real", id: "real:draft" }), "Draft item");
});

test("actual chart configuration prefixes only plotted number clashes and preserves full tooltips", () => {
  const source = readFileSync(new URL("../app/static/projects/flow_metrics/javascript/flow-metrics.js", import.meta.url), "utf8");
  const config = runInNewContext(`${source.slice(source.indexOf("function chartConfig()"), source.indexOf("\nfunction table("))}\nchartConfig`, {
    draft: chart("age", "", "bar"), ticketChartLabel, pointTicket, ticketText,
    ticketLabel: "items", colours: ["#1d70b8"],
    result: {
      unit: "Calendar days", axis: "Item",
      tickets: [
        real("115", "TODO", { id: "real:a", reference: "synthetic/developer-experience#115" }),
        real("115", "TODO", { id: "real:b", reference: "synthetic/platform#115" }),
        real("511", "TODO", { id: "real:c" }),
        real("511", "TODO", { id: "real:not-plotted", reference: "synthetic/elsewhere#511" }),
      ],
      series: [{ name: "Age", points: [
        { ticketId: "real:a", ids: ["real:a"], value: 1 },
        { ticketId: "real:b", ids: ["real:b"], value: 2 },
        { ticketId: "real:c", ids: ["real:c"], value: 3 },
      ] }],
    },
  })();
  assert.deepEqual(Array.from(config.data.labels), ["developer-experience#115", "platform#115", "#511"]);
  assert.match(config.options.plugins.tooltip.callbacks.title([{ datasetIndex: 0, dataIndex: 0 }]), /synthetic\/developer-experience#115/);
  assert.match(config.options.plugins.tooltip.callbacks.title([{ datasetIndex: 0, dataIndex: 2 }]), /synthetic\/repository#511/);
  assert.equal(ticketChartLabel(real("115"), [real("115")]), "#115", "Repeated same item is not a clash");
});

test("bundled Chart.js preserves numeric values and orientation across layouts", () => {
  const vendor = readFileSync(new URL("../app/static/projects/flow_metrics/vendor/chart.umd.js", import.meta.url), "utf8");
  const Chart = runInNewContext(`${vendor}\nChart`);
  const source = readFileSync(new URL("../app/static/projects/flow_metrics/javascript/flow-metrics.js", import.meta.url), "utf8");
  for (const layout of ["bar", "stacked-bar", "column", "stacked-column", "histogram", "line", "area", "flow", "burnup", "scatter"]) {
    const horizontal = ["bar", "stacked-bar"].includes(layout);
    const scatter = layout === "scatter";
    const values = [1, 100, 1];
    const config = runInNewContext(`${source.slice(source.indexOf("function chartConfig()"), source.indexOf("\nfunction table("))}\nchartConfig`, {
      draft: chart("status", "", layout), ticketChartLabel, pointTicket, ticketText,
      ticketLabel: "items", colours: ["#1d70b8", "#b85900"],
      result: {
        unit: "Items", axis: "Status", tickets: [],
        series: ["First", "Second"].map(name => ({
          name, points: values.map((value, i) => ({ label: `Status ${i}`, value, x: Date.UTC(2026, 9, 16 + i) })),
        })),
      },
    })();
    config.options.responsive = false;
    config.options.events = [];
    const canvas = { width: 800, height: 400 };
    const context = new Proxy({
      canvas,
      measureText: text => ({ width: String(text).length * 7 }),
      getLineDash: () => [],
    }, { get: (target, key) => key in target ? target[key] : () => {} });
    canvas.getContext = () => context;
    const rendered = new Chart(canvas, config);
    try {
      for (let datasetIndex = 0; datasetIndex < 2; datasetIndex++) {
        const meta = rendered.getDatasetMeta(datasetIndex);
        assert.deepEqual(Array.from(meta._parsed, point => point[horizontal ? "x" : "y"]), values, layout);
        if (horizontal) {
          assert.equal(rendered.scales.x.min, 0, layout);
          assert.ok(meta.data[1].width > meta.data[0].width * 50, `${layout}: 100 must render much longer than 1`);
        }
        assert.equal(rendered.scales.x.type, horizontal || scatter ? "linear" : "category", layout);
        assert.equal(rendered.scales.y.type, horizontal ? "category" : "linear", layout);
        if (scatter) {
          assert.deepEqual(Array.from(meta._parsed, point => point.x), values.map((_, i) => Date.UTC(2026, 9, 16 + i)));
        }
      }
      assert.equal(rendered.scales.x.options.title.text, horizontal ? "Items" : "Status");
      assert.equal(rendered.scales.y.options.title.text, horizontal ? "Status" : "Items");
      assert.equal(rendered.scales.x.options.stacked, ["area", "stacked-bar", "stacked-column", "flow"].includes(layout));
    } finally {
      rendered.destroy();
    }
  }
});

test("actual drill-down uses item wording and singular/plural without shortening references", () => {
  assert.equal(itemCount(0), "0 items");
  assert.equal(itemCount(1), "1 item");
  assert.equal(itemCount(2), "2 items");
  const source = readFileSync(new URL("../app/static/projects/flow_metrics/javascript/flow-metrics.js", import.meta.url), "utf8");
  const elements = {
    "drill-title": {},
    "ticket-table": { replaceChildren(value) { this.table = value; }, append(value) { this.pagination = value; } },
  };
  const tickets = [real("511"), real("512")];
  const context = {
    $: id => elements[id], result: { tickets, to: 0 }, resultTicket,
    drillPoint: { label: ticketText(tickets[0]), ids: [tickets[0].id] },
    ticketPage: 1, PAGE_SIZE: 10, live: false, ticketReference, itemCount,
    document: { createElement: () => ({}) },
    stateAt: () => ({ status: "TODO" }), captureLabel: () => "Last updated: generated",
    table: (headers, rows, caption) => ({ headers, rows, caption }),
    pagination: (count, page, callback, label) => ({ count, label }),
  };
  runInNewContext(source.slice(source.indexOf("function renderTickets()"), source.indexOf("\nfunction download(")), context);
  context.renderTickets();
  assert.equal(elements["drill-title"].textContent, `${ticketText(tickets[0])}: 1 item`);
  assert.equal(elements["ticket-table"].table.caption, "Item drill-down");
  assert.equal(elements["ticket-table"].table.rows[0][0].textContent, ticketReference(tickets[0]));
  context.drillPoint = { label: "All items", ids: tickets.map(ticket => ticket.id) };
  context.renderTickets();
  assert.equal(elements["drill-title"].textContent, "All items: 2 items");
  assert.equal(elements["ticket-table"].pagination.label, "Items");
});

for (const recovery of ["preset", "custom"]) {
  test(`date ${recovery} handler clears invalid search state only after successful validation`, () => {
    configureSampleData(dataset());
    const source = readFileSync(new URL("../app/static/projects/flow_metrics/javascript/flow-metrics.js", import.meta.url), "utf8");
    const section = (start, end) => {
      const first = source.indexOf(start);
      const last = source.indexOf(end, first);
      assert.ok(first >= 0 && last > first);
      return source.slice(first, last);
    };
    const elements = new Map();
    const element = id => {
      if (!elements.has(id)) elements.set(id, {
        value: "", hidden: true, disabled: false, textContent: "", attributes: {}, handlers: {}, children: [], dataset: {},
        setAttribute(name, value) { this.attributes[name] = value; },
        removeAttribute(name) { delete this.attributes[name]; },
        addEventListener(name, handler) { this.handlers[name] = handler; },
        focus() { this.focused = true; },
        append(...children) { this.children.push(...children); },
        replaceChildren(...children) { this.children = children; },
        querySelectorAll() { return this.children.filter(child => child.attributes["aria-disabled"] === "false"); },
        scrollIntoView() {},
        click() { this.handlers.click?.(); },
        contains(target) { return this.children.includes(target); },
      });
      return elements.get(id);
    };
    const saved = { ...chart("throughput", 'team:DevX title:"Fictional test"'), id: "date-recovery" };
    assert.equal(validChart(saved), true);
    const original = structuredClone(saved);
    for (const [id, key] of Object.entries({
      "chart-name": "name", metric: "metric", layout: "layout", "x-axis": "x", "y-axis": "y", "group-by": "group",
    })) element(id).value = saved[key];
    element("filter-query").value = `${saved.filters.query} from:2026-10-19 to:2026-10-12`;
    let node = 0;
    const context = {
      $: element, document: { createElement: () => element(`generated-${node++}`) },
      draft: structuredClone(saved), saving: false, invalidConfiguration: false,
      previewSequence: 0, pendingPreview: false, syncPickers: [], dateRangeMenu: false, activeSuggestion: -1,
      HISTORY, validateFilters, validChart, builderError, withDateRange, datePresetRange, chartHasDateAxis,
      resolveFilters, SEARCH_FIELDS, live: false, fieldIcon: () => element("icon"), icon: () => element("icon"),
      renderList() {}, syncFieldVisibility() {},
      renderPreview() {
        context.preview = buildResult(context.draft);
        context.scope = scopeLabels(context.draft.filters);
      },
    };
    runInNewContext([
      section("function closeDateRange()", "\nfunction renderScope()"),
      section("function previewConfiguration(", '\n$("configuration").addEventListener'),
      section("function closeSuggestions()", "\nlet dateFilter;"),
      section("function showSuggestions()", "\nfunction applySearch()"),
      section("function applySearch()", '\n$("filter-query").addEventListener'),
      section('$("filter-query").addEventListener("focus"', '\n$("show-chart").addEventListener'),
    ].join("\n"), context);
    context.applySearch();
    assert.equal(element("search-error").hidden, false);
    assert.equal(element("filter-query").attributes["aria-invalid"], "true");
    assert.equal(context.invalidConfiguration, true);
    assert.equal(element("search-save").disabled, true);
    assert.equal(context.preview, undefined);
    assert.deepEqual(context.draft, original);

    element("range-from").value = "2026-10-19";
    element("range-to").value = "2026-10-12";
    element("custom-date-fields").handlers.submit({ preventDefault() {} });
    assert.equal(element("date-range-error").hidden, false);
    assert.equal(element("search-error").hidden, false);
    assert.equal(element("filter-query").attributes["aria-invalid"], "true");
    assert.deepEqual(context.draft, original);

    const range = recovery === "preset" ? datePresetRange("2weeks") : { from: "2026-10-16", to: "2026-10-19" };
    element("filter-query").value += " ";
    context.showSuggestions();
    const options = () => element("filter-suggestions").children;
    assert.equal(options()[0].children[1].textContent, "Date range");
    options()[0].click();
    assert.deepEqual(options().map(option => option.children[1].textContent), ["2 weeks", "1 month", "3 months", "Max", "Custom range"]);
    if (recovery === "preset") options()[0].click();
    else {
      options().at(-1).click();
      assert.equal(element("date-range-panel").hidden, false);
      assert.equal(element("range-from").focused, true);
      element("range-from").value = range.from;
      element("range-to").value = range.to;
      element("custom-date-fields").handlers.submit({ preventDefault() {} });
      assert.equal(element("filter-query").focused, true);
    }
    assert.equal(element("search-error").hidden, true);
    assert.equal(element("filter-query").attributes["aria-invalid"], undefined);
    assert.equal(context.invalidConfiguration, false, element("config-error").textContent);
    assert.equal(element("date-range-panel").hidden, true);
    assert.equal(element("filter-query").attributes["aria-expanded"], "false");
    const { resolved, clauses } = resolveFilters(context.draft.filters);
    assert.equal(resolved.from, range.from);
    assert.equal(resolved.to, range.to);
    assert.deepEqual(clauses.filter(c => !["from", "to"].includes(c.field)), resolveFilters(saved.filters).clauses);
    assert.deepEqual(context.scope, scopeLabels(context.draft.filters));
    assert.deepEqual(context.preview.rows, buildResult(context.draft).rows);
    assert.deepEqual(saved, original, "The saved chart remains unchanged for Save/Discard");
    assert.notEqual(JSON.stringify(context.draft), JSON.stringify(saved), "Corrected range remains an unsaved change");

    element("filter-query").value += " ";
    context.showSuggestions();
    options()[0].click();
    if (recovery === "preset") assert.equal(options()[0].dataset.current, "true");
    context.closeSuggestions();
    context.draft = { ...saved, name: "User-created time chart", metric: "custom", x: "reporting" };
    element("filter-query").handlers.focus();
    assert.equal(options()[0].children[1].textContent, "Date range");
    const key = key => element("filter-query").handlers.keydown({ key, preventDefault() {} });
    key("ArrowDown"); key("Enter");
    assert.equal(options()[0].children[1].textContent, "2 weeks");
    key("Escape");
    assert.equal(element("filter-suggestions").hidden, true);
    if (recovery === "preset") {
      context.SEARCH_FIELDS = SEARCH_FIELDS.map(([field, label, values]) => [
        field, label,
        ({ label: ["example-label"], source: ["Sample", "Genuine"], blocking: ["example/repo#11"], "blocked-by": ["example/repo#12"] })[field] ?? values,
      ]);
      const labels = () => options().map(option => option.children[1].textContent);
      for (const [field, label, values] of context.SEARCH_FIELDS) {
        context.closeSuggestions();
        element("filter-query").value = "";
        element("filter-query").handlers.focus();
        assert.equal(labels()[0], "Date range", field);
        if (values?.length && !["from", "to"].includes(field)) {
          options().find(option => option.children[1].textContent === label).click();
          assert.deepEqual(labels(), values, `${field} offers only its values`);
          assert.equal(context.dateRangeMenu, false);
        }
        for (const suffix of ["", "no-matching-value"]) {
          element("filter-query").value = `${field}:${suffix}`;
          context.dateRangeMenu = true;
          element("filter-query").handlers.input();
          const expected = (values || []).filter(value => value.toLowerCase().includes(suffix));
          assert.deepEqual(labels(), expected, `${field}:${suffix} excludes date range and other fields`);
          assert.equal(context.dateRangeMenu, false);
          assert.equal(element("filter-suggestions").hidden, expected.length === 0);
        }
      }
      context.SEARCH_FIELDS.push(["empty", "Empty", []]);
      element("filter-query").value = "empty:";
      element("filter-query").handlers.input();
      assert.deepEqual(labels(), []);
      assert.equal(element("filter-suggestions").hidden, true);
      context.SEARCH_FIELDS = SEARCH_FIELDS;
    }
    context.draft = { ...saved, metric: "age", x: "ticket" };
    element("filter-query").value = "";
    context.renderDateRanges();
    context.showSuggestions();
    assert.ok(options().every(option => option.children[1].textContent !== "Date range"));
    assert.equal(element("date-range-panel").hidden, true);
  });
}

test("board Last run cell shows attempt outcome without changing Team successful freshness", async () => {
  const source = readFileSync(new URL("../app/static/projects/flow_metrics/javascript/flow-metrics.js", import.meta.url), "utf8");
  const start = source.indexOf("async function refreshCollectionHealth()");
  const end = source.indexOf("\nrefreshCollectionHealth();", start);
  assert.ok(start >= 0 && end > start);
  const elements = Object.fromEntries(["live-freshness", "collection-status"]
    .map(id => [id, { textContent: "" }]));
  let health = { capturedAt: "generated-capture", stale: true, status: "not_configured", configured: false };
  let failure;
  const refresh = runInNewContext(`${source.slice(start, end)}\nrefreshCollectionHealth`, {
    $: id => elements[id],
    apiRequest: async () => { if (failure) throw failure; return health; },
    captureLabel: stamp => `Last updated: ${stamp}`,
  });
  await refresh();
  assert.equal(elements["live-freshness"].textContent, "Last updated: generated-capture");
  assert.equal(elements["collection-status"].textContent, "No runs recorded");
  for (const [status, outcome] of [["complete", "Succeeded"], ["failed", "Failed"], ["running", "Running"]]) {
    health = { ...health, status, latestRun: {
      status, startedAt: "2026-10-22T08:30:00Z", completedAt: status === "running" ? null : "2026-10-22T08:31:00Z",
      failureReason: status === "failed" ? "Could not connect to GitHub." : null,
    } };
    await refresh();
    assert.ok(elements["collection-status"].textContent.startsWith(`22 Oct 2026, 9:30am · ${outcome}`));
    assert.equal(elements["collection-status"].textContent.includes("Could not connect"), status === "failed");
    assert.ok(elements["live-freshness"].textContent.startsWith("Last updated: generated-capture"));
  }
  health = { ...health, status: "not_configured", latestRun: null };
  health = { ...health, capturedAt: null };
  await refresh();
  assert.equal(elements["collection-status"].textContent, "No runs recorded");
  health = { ...health, capturedAt: "generated-capture", status: "failed" };
  await refresh();
  assert.equal(elements["collection-status"].textContent, "No runs recorded");
  health = { ...health, status: "complete", configured: true, scheduledStatus: "failed" };
  await refresh();
  assert.match(elements["live-freshness"].textContent, /Latest collection failed/);
  assert.equal(elements["collection-status"].textContent, "No runs recorded");
  health = { capturedAt: null, stale: true, status: "failed" };
  await refresh();
  assert.equal(elements["live-freshness"].textContent, "No complete capture yet. Latest collection failed.");
  failure = new Error("Generated API error");
  await refresh();
  assert.equal(elements["live-freshness"].textContent, "Last updated unavailable. Generated API error");
  assert.equal(elements["collection-status"].textContent, "Run status unavailable. Generated API error");
});

test("actual tab and chart navigation preserve URL selection with safe fallback and accessible tabs", () => {
  const source = readFileSync(new URL("../app/static/projects/flow_metrics/javascript/flow-metrics.js", import.meta.url), "utf8");
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {
      hidden: false, attributes: {}, handlers: {},
      setAttribute(key, value) { this.attributes[key] = value; },
      getAttribute(key) { return this.attributes[key]; },
      addEventListener(key, handler) { this.handlers[key] = handler; },
      after() {}, focus() { this.focused = true; },
    });
    return elements.get(id);
  };
  const tabs = ["team-tab", "admin-tab"].map(element);
  tabs[0].attributes["aria-controls"] = "team-panel";
  tabs[1].attributes["aria-controls"] = "admin-panel";
  const location = { href: "https://example.test/flow-metrics/?view=admin&chart=planned&other=kept#anchor" };
  const context = {
    $: element, tabs, URL, window: { location, history: { replaceState(_state, _title, url) { location.href = String(url); } } },
    charts: [{ id: "cycle", metric: "cycle", filters: { query: "" } }, { id: "planned", metric: "status", filters: { query: "planned:Planned" } }],
    live: false, selected: undefined, draft: null, chart: null,
    clone: structuredClone, syncControls() {}, renderList() {}, renderPreview() {},
  };
  context.currentSaved = () => context.charts.find(item => item.id === context.selected);
  runInNewContext(source.slice(source.indexOf("function updateWorkspaceURL("), source.indexOf("\nfunction chartConfig()")), context);
  runInNewContext(source.slice(source.indexOf("function activateTab("), source.indexOf('window.addEventListener("beforeunload"')), context);
  assert.equal(element("admin-panel").hidden, false);
  assert.equal(tabs[1].attributes["aria-selected"], "true");
  context.select("planned");
  assert.equal(context.selected, "planned");
  assert.equal(context.draft.filters.query, "planned:Planned");
  assert.equal(new URL(location.href).searchParams.get("view"), "admin");
  tabs[0].handlers.click();
  assert.equal(new URL(location.href).searchParams.get("view"), null);
  assert.equal(element("team-panel").hidden, false);
  tabs[0].handlers.keydown({ key: "ArrowRight", preventDefault() {} });
  assert.equal(new URL(location.href).searchParams.get("view"), "admin");
  assert.equal(tabs[1].focused, true);
  assert.equal(tabs[0].tabIndex, -1);
  context.select("deleted-or-invalid");
  assert.equal(context.selected, "cycle");
  assert.equal(new URL(location.href).searchParams.get("chart"), "cycle");
  context.live = true;
  context.select(null);
  assert.equal(context.selected, "planned", "Real mode retains its status-chart default");
  context.charts = [];
  context.select("missing");
  assert.equal(context.draft, null);
  assert.equal(new URL(location.href).searchParams.get("chart"), null);
  assert.equal(new URL(location.href).searchParams.get("other"), "kept");
  assert.equal(new URL(location.href).hash, "#anchor");
});

test("keywords find readable genuine references without changing explicit title filters", () => {
  configureSampleData(dataset());
  for (const keyword of ["synthetic/repository#2", "#2", "Fictional"]) {
    const result = buildResult(chart("status", `source:Genuine ${keyword}`));
    assert.ok(ids(result).includes("real:2"), keyword);
  }
  assert.equal(buildResult(chart("status", 'source:Genuine title:"synthetic/repository#2"')).sampleSize, 0);
  assert.equal(buildResult(chart("status", 'source:Genuine title:"real:2"')).sampleSize, 0);
  assert.deepEqual(ids(buildResult(chart("status", 'source:Genuine title:"FICTIONAL TEST" "#2"'))), ["real:2"]);
  assert.equal(buildResult(chart("status", 'source:Genuine title:"unmatched" "#2"')).sampleSize, 0);
  assert.deepEqual(ids(buildResult(chart("status", 'source:Genuine "real:2"'))), ["real:2"]);
  assert.deepEqual(ids(buildResult(chart("status", 'source:Genuine synthetic/repository#2 team:DevX'))), ["real:2"]);
  assert.equal(buildResult(chart("status", 'source:Genuine #2 status:Done')).sampleSize, 0);
});

test("genuine draft identity stays independent of editable Type for builtin and editable age", () => {
  const data = dataset();
  data.realObservations.at(-1).items = [
    real("1", "TODO", { type: "Task", state: "DRAFT" }),
    real("2", "TODO", { type: "Issue", state: "DRAFT" }),
    real("3", "TODO", { type: "DraftIssue" }),
    real("4", "TODO", { type: "Not set", createdDate: "2026-10-19" }),
    real("5", "TODO", { archived: true }),
    real("6", "TODO", { createdDate: "2026-10-20" }),
  ];
  configureSampleData(data);
  for (const layout of ["bar", "column", "line", "area", "stacked-bar", "stacked-column"]) {
    const builtin = chart("age", "source:Genuine", layout);
    const original = buildResult(builtin);
    assert.deepEqual(ids(original), ["real:3", "real:4"]);
    assert.equal(original.rows.find(row => row.ids.includes("real:4")).value, 0);
    assert.deepEqual(buildResult(editableRecipe(builtin)).rows, original.rows);
    assert.equal(original.coverage.excluded, 2);
  }
});

test("custom recipes retain all built-in mixed-source coverage, cutoff and missing-history gates", () => {
  configureSampleData(dataset());
  for (const metric of ["cycle", "age", "status", "stuck", "throughput", "churn", "flow", "progress", "velocity"]) {
    for (const query of ["", "source:Genuine", "source:Genuine to:2026-10-15", "sprint:Firebreak"]) {
      const builtin = chart(metric, query, metric === "cycle" ? "scatter" : "column");
      const original = buildResult(builtin);
      const custom = buildResult(editableRecipe(builtin));
      assert.deepEqual(custom.rows, original.rows, `${metric}/${query}`);
      assert.deepEqual(custom.coverage, original.coverage);
      assert.equal(custom.unavailable, original.unavailable);
    }
  }
});

test("union selects the latest observation, never repeats captured items or backfills membership", () => {
  configureSampleData(dataset());
  assert.equal(total(buildResult(chart())), 38);
  assert.equal(total(buildResult(chart("status", "to:2026-10-18"))), 37);
  assert.equal(total(buildResult(chart("status", "to:2026-10-15"))), 36);
  assert.equal(total(buildResult(chart("status", 'source:Genuine to:2026-10-15'))), 0);
  assert.deepEqual(ids(buildResult(chart("status", "source:Genuine"))), ["real:1", "real:2"]);
  assert.equal(total(buildResult(chart("status", 'sprint:"Sprint A"'))), 11);
  assert.ok(ids(buildResult(chart("status", 'sprint:"Sprint B"'))).every(id => id.startsWith("SAMPLE-")));
  assert.equal(total(buildResult(chart("status", "sprint:Firebreak"))), 16);
  assert.equal(total(buildResult(chart("status", "sprint:Firebreak source:Genuine"))), 2);
  assert.ok(SEARCH_FIELDS.find(([field]) => field === "team")[2].includes("DevX"));
});

test("real historical evidence gaps exclude genuine tickets explicitly and preserve scatter/hist totals", () => {
  configureSampleData(dataset());
  const fictionalCycle = buildResult(chart("cycle", "source:Fictional", "scatter"));
  assert.equal(fictionalCycle.unavailable, null);
  assert.ok(fictionalCycle.sampleSize > 0);
  assert.ok(ids(fictionalCycle).every(id => id.startsWith("SAMPLE-")));
  for (const metric of ["cycle", "churn", "stuck", "throughput", "flow", "progress", "velocity"]) {
    const result = buildResult(chart(metric, "sprint:Firebreak", metric === "cycle" ? "scatter" : "column"));
    assert.equal(result.coverage.genuine, 2);
    assert.equal(result.coverage.excluded, 2);
    assert.match(result.coverageText, /excluded/);
    assert.ok(ids(result).every(id => !id.startsWith("real:")));
    const unavailable = buildResult(chart(metric, "source:Genuine")).unavailable;
    if (metric === "cycle") {
      assert.equal(unavailable, "Not enough history to calculate cycle time yet.");
    } else {
      assert.match(unavailable, /Verified event history/);
    }
  }
  const scatter = buildResult(chart("cycle", "", "scatter"));
  const histogram = buildResult(chart("cycle", "", "histogram"));
  assert.equal(total(histogram), scatter.rows.length);
  assert.deepEqual(ids(histogram), ids(scatter));
  const csv = resultCSV(chart("cycle", "", "scatter"), scatter);
  assert.match(csv, /Combined exploration/);
  assert.match(csv, /synthetic/);
  assert.match(csv, /Contributor provenance/);
});

test("unknown metadata isn't explicit empty, estimate absence isn't zero, genuine unfinished age is usable", () => {
  const data = dataset();
  data.realObservations.at(-1).items.push(real("3", "TODO", {
    availableFields: [...real("3").availableFields, "label"], label: ["Not set"],
  }));
  configureSampleData(data);
  const empty = buildResult(chart("status", 'source:Genuine label:"Not set"'));
  assert.deepEqual(ids(empty), ["real:3"]);
  assert.equal(empty.coverage.missingFilterEvidence, 2);
  const points = buildResult({ ...chart("custom", "source:Genuine"), y: "points" });
  assert.equal(points.coverage.excluded, 3);
  assert.match(points.coverageText, /0 of 3/);
  const age = buildResult(chart("age", "source:Genuine"));
  assert.deepEqual(ids(age), ["real:2", "real:3"]);
  assert.deepEqual(age.rows.map(row => row.value), [6, 6]);
  const csv = resultCSV(chart("age", "source:Genuine"), age);
  assert.match(csv, /synthetic\/repository#2:real/);
  assert.doesNotMatch(csv, /real:2/);
  assert.match(csv, /synthetic\/repository#2/);
});

test("numeric Estimation uses only the verified real binding at cutoff; missing is not zero and Points stay separate", () => {
  const data = dataset();
  const identity = { estimate: { fieldId: "PVTF_lADOACGfts4BHZqSzg_lEkY" } };
  data.realObservations[1].items = [
    real("1", "TODO", { estimate: 0, identities: identity }),
    real("2", "TODO", { estimate: 8, identities: identity }),
    real("3", "In Review", { estimate: null, identities: identity }),
    real("4", "TODO", { estimate: 100, identities: { estimate: {fieldId:"wrong-field"} } }),
  ];
  data.realObservations[2].items = [
    real("1", "TODO", { estimate: 2.5, identities: identity }),
    real("2", "TODO", { estimate: 7.5, identities: identity }),
  ];
  configureSampleData(data);
  const sum = { ...chart("custom", "source:Genuine to:2026-10-18"), y: "estimation" };
  const result = buildResult(sum);
  assert.equal(total(result), 8);
  assert.equal(result.coverage.excluded, 2);
  assert.deepEqual(ids(result), ["real:1", "real:2"]);
  assert.equal(result.rows.find(row=>row.label==="In Review").value,null);
  assert.equal(result.rows.find(row=>row.label==="Icebox").value,0); // Empty countable category, not missing estimates.
  const average = buildResult({ ...sum, y:"averageEstimation" });
  assert.equal(average.rows.find(row=>row.label==="TODO").value,4); // The genuine numeric zero contributes.
  assert.deepEqual(ids(average),ids(result));
  const csv = resultCSV(sum,result);
  assert.match(csv,/Sum of Estimation/);
  assert.doesNotMatch(csv,/real:1|real:2|#3|#4/);
  assert.match(csv,/synthetic\/repository#1; synthetic\/repository#2/);
  assert.equal(total(buildResult({...sum, filters:{query:"source:Genuine"}})),10);
  assert.match(buildResult({...sum,filters:{query:"source:Genuine to:2026-10-16"}}).unavailable,/numeric Estimation/);
  assert.match(buildResult({...sum,filters:{query:"source:Fictional"}}).unavailable,/numeric Estimation/);
  const mixed = buildResult({...sum,filters:{query:""}});
  assert.deepEqual(ids(mixed),["real:1","real:2"]);
  assert.equal(mixed.coverage.excluded,36);
  const points = buildResult({...sum,y:"points",filters:{query:""}});
  assert.ok(ids(points).every(id=>id.startsWith("SAMPLE-")));
  assert.equal(points.coverage.excluded,2);
});

test("ticket points expose readable identity while preserving stable contributors and legitimate same-day zero", () => {
  configureSampleData(dataset());
  const age = buildResult(chart("age","source:Genuine"));
  assert.equal(age.rows[0].ticketId,"real:2");
  assert.equal(age.rows[0].label,"Fictional test of genuine adapter (synthetic/repository#2)");
  assert.deepEqual(age.rows[0].ids,["real:2"]);
  const scatter = buildResult(chart("cycle",'sprint:"Sprint A"',"scatter"));
  assert.ok(scatter.rows.some(row=>row.value===0 && row.ids.length===1));
  assert.ok(scatter.rows.every(row=>row.ticketId===row.ids[0] && row.label.includes(row.ids[0])));
});
