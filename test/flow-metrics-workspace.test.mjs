import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { SAMPLE_DATA } from "../app/static/projects/flow_metrics/javascript/flow-metrics-sample-data.mjs";
import { configureSampleData, buildResult, CUSTOM_DEFAULTS, resultCSV, SEARCH_FIELDS, ticketChartLabel, ticketReference, ticketText, pointTicket, itemCount, datePresetRange, withDateRange, resolveFilters, chartHasDateAxis, HISTORY, validateFilters, validChart, scopeLabels } from "../app/static/projects/flow_metrics/javascript/flow-metrics-model.mjs";
import { editableRecipe, builderError } from "../app/static/projects/flow_metrics/javascript/flow-metrics-builder.mjs";

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
    $: id => elements[id], result: { tickets, to: 0 },
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

test("Team freshness retains capture/failure/errors while routine staleness belongs in Admin", async () => {
  const source = readFileSync(new URL("../app/static/projects/flow_metrics/javascript/flow-metrics.js", import.meta.url), "utf8");
  const start = source.indexOf("async function refreshCollectionHealth()");
  const end = source.indexOf("\nrefreshCollectionHealth();", start);
  assert.ok(start >= 0 && end > start);
  const elements = Object.fromEntries(["live-freshness", "collection-status", "collection-attempt", "collection-success"]
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
  assert.equal(elements["collection-status"].textContent, "Data may be out of date.");
  assert.equal(elements["collection-attempt"].textContent, "No collection attempts recorded.");
  assert.match(elements["collection-success"].textContent, /generated-capture/);
  for (const [status, outcome] of [["complete", "Succeeded"], ["failed", "Failed"], ["running", "Running (completion not recorded)"]]) {
    health = { ...health, status, latestRun: {
      status, startedAt: "generated-start", completedAt: status === "running" ? null : "generated-finish",
      failureReason: status === "failed" ? "Could not connect to GitHub." : null,
    } };
    await refresh();
    assert.ok(elements["collection-attempt"].textContent.includes(outcome));
    assert.match(elements["collection-attempt"].textContent, /generated-start/);
    assert.equal(elements["collection-attempt"].textContent.includes("generated-finish"), status !== "running");
    assert.equal(elements["collection-attempt"].textContent.includes("Could not connect"), status === "failed");
    assert.ok(elements["live-freshness"].textContent.startsWith("Last updated: generated-capture"));
    assert.match(elements["collection-success"].textContent, /generated-capture/);
  }
  health = { ...health, status: "not_configured", latestRun: null };
  health = { ...health, capturedAt: null };
  await refresh();
  assert.equal(elements["collection-status"].textContent, "");
  health = { ...health, capturedAt: "generated-capture", status: "failed" };
  await refresh();
  assert.match(elements["collection-status"].textContent, /Latest collection failed/);
  health = { ...health, status: "complete", configured: true, scheduledStatus: "failed" };
  await refresh();
  assert.match(elements["live-freshness"].textContent, /Latest collection failed/);
  assert.match(elements["collection-status"].textContent, /Scheduled collection: failed.*Data may be out of date/);
  health = { capturedAt: null, stale: true, status: "failed" };
  await refresh();
  assert.equal(elements["live-freshness"].textContent, "No complete capture yet. Latest collection failed.");
  failure = new Error("Generated API error");
  await refresh();
  assert.equal(elements["live-freshness"].textContent, "Last updated unavailable. Generated API error");
  assert.equal(elements["collection-status"].textContent, "Collection status unavailable. Generated API error");
  assert.equal(elements["collection-attempt"].textContent, "Latest attempt unavailable.");
  assert.equal(elements["collection-success"].textContent, "Latest successful capture unavailable.");
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
  for (const metric of ["cycle", "churn", "stuck", "throughput", "flow", "progress", "velocity"]) {
    const result = buildResult(chart(metric, "sprint:Firebreak", metric === "cycle" ? "scatter" : "column"));
    assert.equal(result.coverage.genuine, 2);
    assert.equal(result.coverage.excluded, 2);
    assert.match(result.coverageText, /excluded/);
    assert.ok(ids(result).every(id => !id.startsWith("real:")));
    assert.match(buildResult(chart(metric, "source:Genuine")).unavailable, /Verified event history/);
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
