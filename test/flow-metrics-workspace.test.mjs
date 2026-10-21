import test from "node:test";
import assert from "node:assert/strict";
import { SAMPLE_DATA } from "../app/static/projects/flow_metrics/javascript/flow-metrics-sample-data.mjs";
import { configureSampleData, buildResult, CUSTOM_DEFAULTS, resultCSV, SEARCH_FIELDS } from "../app/static/projects/flow_metrics/javascript/flow-metrics-model.mjs";
import { editableRecipe } from "../app/static/projects/flow_metrics/javascript/flow-metrics-builder.mjs";

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

test("keywords find readable genuine references without changing explicit title filters", () => {
  configureSampleData(dataset());
  for (const keyword of ["synthetic/repository#2", "#2", "Fictional"]) {
    const result = buildResult(chart("status", `source:Genuine ${keyword}`));
    assert.ok(ids(result).includes("real:2"), keyword);
  }
  assert.equal(buildResult(chart("status", 'source:Genuine title:"synthetic/repository#2"')).sampleSize, 0);
  assert.deepEqual(ids(buildResult(chart("status", 'source:Genuine title:"real:2"'))), ["real:2"]);
  assert.deepEqual(ids(buildResult(chart("status", 'source:Genuine synthetic/repository#2 team:DevX'))), ["real:2"]);
  assert.equal(buildResult(chart("status", 'source:Genuine #2 status:Done')).sampleSize, 0);
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
