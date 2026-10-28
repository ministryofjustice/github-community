// Generated fiction only. Never import captured board items into this dataset.
const DAY = 86400000;
const shiftDate = (date, days) => new Date(Date.parse(`${date}T00:00:00Z`) + days * DAY).toISOString().slice(0, 10);

export const SAMPLE_SPRINTS = [
  { id: "sample-a", name: "Sprint A", start: "2026-09-14", end: "2026-09-27" },
  { id: "sample-b", name: "Sprint B", start: "2026-09-28", end: "2026-10-11" },
  { id: "sample-firebreak", name: "Firebreak", start: "2026-10-12", end: "2026-10-25" },
];

const asOf = "2026-10-19";
const scenarios = [
  "normal completion", "same-day completion", "blocked then completed",
  "reopened then completed", "reopened and unfinished", "waiting for review",
  "long-running blocked work", "not started", "icebox with re-estimate",
  "removed then returned to scope", "added and completed", "added and unfinished",
];

const tickets = SAMPLE_SPRINTS.flatMap((sprint, sprintIndex) =>
  scenarios.map((scenario, index) => {
    const created = shiftDate(sprint.start, -2);
    const events = [];
    const add = (offset, type, value) => {
      const date = shiftDate(sprint.start, offset);
      if (date <= asOf) events.push({ date, type, value });
    };
    add(-2, "status", index === 8 ? "Icebox" : "TODO");
    add(-2, "points", [1, 2, 3, 5, 8][index % 5]);
    add(index < 10 ? 0 : 3, "scope", sprint.id);
    if (![7, 8, 9].includes(index)) add(index === 1 ? 2 : index >= 10 ? 3 : 0, "status", "In Progress");
    if (index === 0) {
      add(2, "status", "In Review");
      add(4, "status", "Done");
    } else if (index === 1) {
      add(2, "status", "Done");
    } else if (index === 2) {
      add(1, "status", "Blocked / On Hold");
      add(5, "status", "In Progress");
      add(7, "status", "In Review");
      add(8, "status", "Done");
    } else if (index === 3 || index === 4) {
      add(3, "status", "Done");
      add(6, "status", "In Progress");
      if (index === 3) {
        add(9, "status", "In Review");
        add(10, "status", "Done");
      }
    } else if (index === 5) {
      add(1, "status", "In Review");
    } else if (index === 6) {
      add(0, "status", "Blocked / On Hold");
    } else if (index === 8) {
      add(4, "points", 8);
    } else if (index === 9) {
      add(3, "scope", null);
      add(6, "scope", sprint.id);
      for (const nextSprint of SAMPLE_SPRINTS.slice(sprintIndex + 1)) {
        const offset = Math.round((Date.parse(`${nextSprint.start}T00:00:00Z`) - Date.parse(`${sprint.start}T00:00:00Z`)) / DAY);
        add(offset, "scope", nextSprint.id);
      }
    } else if (index === 10) {
      add(8, "status", "In Review");
      add(9, "status", "Done");
    }
    return {
      id: `SAMPLE-${sprintIndex + 1}-${String(index + 1).padStart(2, "0")}`,
      title: `Sample ${scenario} (${sprint.name})`,
      repository: `sample-repository-${index % 2 ? "beta" : "alpha"}`,
      team: ["DevX", "Blueprint", "Engineering Platform"][index % 3],
      type: ["Task", "Bug", "Feature"][index % 3],
      objective: ["Sample reliability", "Sample developer tooling", "Sample delivery"][Math.floor(index / 3) % 3],
      planned: index < 10 ? "Planned" : "Unplanned",
      assignee: index % 4 === 0 ? ["Not set"] : [`sample-contributor-${index % 3 + 1}`],
      label: [index % 2 ? "sample-maintenance" : "sample-improvement", "sample-data"],
      milestone: [`Sample ${sprint.name} milestone`],
      reviewers: index % 3 === 2 ? [`sample-reviewer-${index % 2 + 1}`] : ["Not set"],
      priority: ["High", "Medium", "Low"][index % 3],
      refined: index % 2 ? "Yes" : "No",
      "blocked-by": index === 6 ? [`SAMPLE-${sprintIndex + 1}-06`] : ["Not set"],
      blocking: index === 5 ? [`SAMPLE-${sprintIndex + 1}-07`] : ["Not set"],
      "relates-to": index < 2 ? [`SAMPLE-${sprintIndex + 1}-${index === 0 ? "02" : "01"}`] : ["Not set"],
      "parent-issue": [7, 8].includes(index) ? [`SAMPLE-${sprintIndex + 1}-01`] : ["Not set"],
      "sub-issues-progress": index === 0 ? ["0/2 (0%)"] : ["Not set"],
      created,
      events: events.sort((a, b) => a.date.localeCompare(b.date)),
    };
  }),
);

export const SAMPLE_DATA = {
  version: 1,
  id: "sample-three-sprints",
  label: "Sample data",
  provenance: "synthetic",
  history: { from: "2026-09-12", to: asOf },
  reviewWindow: { from: "2026-10-12", to: "2026-10-15" },
  sprints: SAMPLE_SPRINTS,
  teams: [...new Set(tickets.map((ticket) => ticket.team))].sort(),
  tickets,
};

export function sampleSnapshotAt(date) {
  if (typeof date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(date)
      || !Number.isFinite(Date.parse(`${date}T00:00:00Z`))
      || shiftDate(date, 0) !== date
      || date < SAMPLE_DATA.history.from || date > SAMPLE_DATA.history.to) {
    throw new RangeError("Choose a valid date within the sample history.");
  }
  return {
    date,
    provenance: SAMPLE_DATA.provenance,
    items: SAMPLE_DATA.tickets.filter((ticket) => ticket.created <= date).map((ticket) => {
      let status = null;
      let statusSince = null;
      let sprint = null;
      let points = null;
      for (const event of ticket.events) {
        if (event.date > date) break;
        if (event.type === "status") {
          status = event.value;
          statusSince = event.date;
        } else if (event.type === "scope") sprint = event.value;
        else if (event.type === "points") points = event.value;
      }
      return { id: ticket.id, team: ticket.team, status, statusSince, sprint, points };
    }),
  };
}
