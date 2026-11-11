import test from "node:test";
import assert from "node:assert/strict";
import { SAMPLE_DATA, SAMPLE_SPRINTS, sampleSnapshotAt } from "../app/static/projects/flow_metrics/javascript/flow-metrics-sample-data.mjs";

const byId = (date, id) => sampleSnapshotAt(date).items.find((item) => item.id === id);

test("three named sprints, two complete and Firebreak in progress", () => {
  assert.deepEqual(SAMPLE_SPRINTS.map((sprint) => sprint.name), ["Sprint A", "Sprint B", "Firebreak"]);
  assert.equal(SAMPLE_SPRINTS.filter((sprint) => sprint.end < SAMPLE_DATA.history.to).length, 2);
  assert.deepEqual(SAMPLE_DATA.reviewWindow, { from: "2026-10-12", to: "2026-10-15" });
  assert.equal(SAMPLE_DATA.provenance, "synthetic");
  assert.equal(SAMPLE_DATA.label, "Sample data");
});

test("fictional identities, data-derived teams and reproducible chronological events", () => {
  assert.equal(SAMPLE_DATA.tickets.length, 36);
  assert.equal(new Set(SAMPLE_DATA.tickets.map((ticket) => ticket.id)).size, 36);
  assert.deepEqual(SAMPLE_DATA.teams, [...new Set(SAMPLE_DATA.tickets.map((ticket) => ticket.team))].sort());
  assert.deepEqual(SAMPLE_DATA.teams, ["Blueprint", "DevX", "Engineering Platform"]);
  for (const ticket of SAMPLE_DATA.tickets) {
    assert.match(ticket.id, /^SAMPLE-/);
    assert.match(ticket.repository, /^sample-repository-/);
    assert.ok(!Object.hasOwn(ticket, "url"));
    assert.ok(ticket.events.length >= 3);
    assert.deepEqual(ticket.events.map((event) => event.date), ticket.events.map((event) => event.date).sort());
    for (const event of ticket.events) {
      assert.ok(event.date >= ticket.created && event.date <= SAMPLE_DATA.history.to);
      assert.ok(["scope", "status", "points"].includes(event.type));
    }
  }
});

test("both completed sprints have exact commitment baselines, estimates and completed scope", () => {
  for (const [index, sprint] of SAMPLE_SPRINTS.slice(0, 2).entries()) {
    const baseline = sampleSnapshotAt(sprint.start).items.filter((item) => item.sprint === sprint.id);
    assert.equal(baseline.length, 10 + index);
    assert.equal(baseline.reduce((sum, item) => sum + item.points, 0), 38 + index * 8);
    const completed = sampleSnapshotAt(sprint.end).items.filter((item) => item.sprint === sprint.id && item.status === "Done");
    assert.equal(completed.length, 5);
    assert.equal(completed.reduce((sum, item) => sum + item.points, 0), 12);
    assert.equal(byId(sprint.end, `SAMPLE-${index + 1}-05`).status, "In Progress");
  }
});

test("scope additions, removals and returns are explicit, not inferred from planned labels", () => {
  assert.equal(byId("2026-09-14", "SAMPLE-1-11").sprint, null);
  assert.equal(byId("2026-09-17", "SAMPLE-1-11").sprint, "sample-a");
  assert.equal(byId("2026-09-17", "SAMPLE-1-10").sprint, null);
  assert.equal(byId("2026-09-20", "SAMPLE-1-10").sprint, "sample-a");
  assert.equal(byId("2026-09-28", "SAMPLE-1-10").sprint, "sample-b");
  assert.equal(byId("2026-10-12", "SAMPLE-1-10").sprint, "sample-firebreak");
  assert.equal(byId("2026-10-12", "SAMPLE-2-10").sprint, "sample-firebreak");
  const changes = SAMPLE_DATA.tickets.flatMap((ticket) => ticket.events.filter((event) =>
    event.type === "scope" && event.date > "2026-09-14" && event.date <= "2026-09-27"));
  assert.equal(changes.filter((event) => event.value === "sample-a").length, 3);
  assert.equal(changes.filter((event) => event.value === null).length, 1);
});

test("same-day, reopen, blocked and re-estimate scenarios retain their evidence", () => {
  const sameDay = SAMPLE_DATA.tickets.find((ticket) => ticket.id === "SAMPLE-1-02");
  const start = sameDay.events.find((event) => event.value === "In Progress");
  const done = sameDay.events.find((event) => event.value === "Done");
  assert.equal(start.date, done.date);
  assert.equal(byId("2026-09-17", "SAMPLE-1-04").status, "Done");
  assert.equal(byId("2026-09-20", "SAMPLE-1-04").status, "In Progress");
  assert.equal(byId("2026-09-24", "SAMPLE-1-04").status, "Done");
  assert.equal(byId("2026-09-27", "SAMPLE-1-07").statusSince, "2026-09-14");
  assert.equal(byId("2026-09-14", "SAMPLE-1-09").points, 5);
  assert.equal(byId("2026-09-18", "SAMPLE-1-09").points, 8);
});

test("four-day review window and current Firebreak include only events up to each date", () => {
  assert.equal(byId("2026-10-12", "SAMPLE-3-01").status, "In Progress");
  assert.equal(byId("2026-10-15", "SAMPLE-3-01").status, "In Review");
  assert.equal(byId("2026-10-16", "SAMPLE-3-01").status, "Done");
  assert.equal(byId("2026-10-19", "SAMPLE-3-04").status, "In Progress");
  const completed = sampleSnapshotAt("2026-10-19").items.filter((item) => item.sprint === "sample-firebreak" && item.status === "Done");
  assert.equal(completed.length, 2);
  assert.equal(completed.reduce((sum, item) => sum + item.points, 0), 3);
  assert.equal(sampleSnapshotAt("2026-09-14").items.length, 12);
});

test("daily observations conserve fictional items and cannot mutate source events", () => {
  for (let day = Date.parse(`${SAMPLE_DATA.history.from}T00:00:00Z`); day <= Date.parse(`${SAMPLE_DATA.history.to}T00:00:00Z`); day += 86400000) {
    const date = new Date(day).toISOString().slice(0, 10);
    const snapshot = sampleSnapshotAt(date);
    assert.equal(snapshot.items.length, SAMPLE_DATA.tickets.filter((ticket) => ticket.created <= date).length);
    assert.ok(snapshot.items.every((item) => item.status && Number.isInteger(item.points) && item.points > 0));
  }
  const snapshot = sampleSnapshotAt("2026-10-19");
  snapshot.items[0].status = "changed";
  assert.equal(sampleSnapshotAt("2026-10-19").items[0].status, "Done");
});

test("out-of-range and invalid sample dates fail explicitly", () => {
  for (const date of ["2026-09-11", "2026-10-20", "2026-09-31", "invalid", null]) {
    assert.throws(() => sampleSnapshotAt(date), RangeError);
  }
});
