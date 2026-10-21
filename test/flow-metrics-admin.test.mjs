import test from "node:test";
import assert from "node:assert/strict";
import { requestDetails, requestKey, parseRequests, REQUEST_VERSION } from "../app/static/projects/flow_metrics/javascript/flow-metrics-admin.mjs";

const request = { id: "f7933177-581f-441f-a2bb-22637f67fe48", team: "Test team", project: "https://github.com/orgs/example/projects/42" };
const stored = requests => JSON.stringify({ version: REQUEST_VERSION, requests });

test("browser requests retain stable IDs and normalise details without claiming a board connection", () => {
  assert.deepEqual(parseRequests(null), []);
  assert.deepEqual(parseRequests(stored([request])), [request]);
  const details = requestDetails(" Test team ", "https://github.com/orgs/EXAMPLE/projects/42/");
  assert.deepEqual(details, { team: "Test team", project: request.project });
  assert.equal(requestKey(details), requestKey({ ...request, team: "TEST TEAM" }));
});

test("browser requests reject invalid links, empty and overlong teams", () => {
  for (const project of ["javascript:alert(1)", "https://example.com/orgs/example/projects/42",
    "https://github.com/orgs/example/projects/0", "https://github.com/orgs/example/projects/42?token=x",
    "https://github.com/orgs/example/projects/42#fragment"]) {
    assert.throws(() => requestDetails("Test", project));
  }
  for (const team of [" ", "a".repeat(81), null]) assert.throws(() => requestDetails(team, request.project));
});

test("invalid browser data is rejected rather than partially imported or silently replaced", () => {
  for (const raw of ["{", "null", "[]", JSON.stringify({ version: 2, requests: [] }),
    JSON.stringify({ version: 1, requests: [], unknown: true }), stored([null]),
    stored([{ ...request, id: 3 }]), stored([{ ...request, extra: true }]),
    stored([{ ...request, project: "https://example.com" }]), " ".repeat(100001),
    stored(Array.from({ length: 101 }, () => request))]) {
    assert.throws(() => parseRequests(raw));
  }
});

test("duplicate browser IDs and equivalent team/project requests are rejected", () => {
  assert.throws(() => parseRequests(stored([request, request])));
  assert.throws(() => parseRequests(stored([request, { ...request, id: "88d7ad16-3a57-4acb-9dfd-853a0665d1eb", team: "TEST TEAM", project: request.project + "/" }])));
});
