import {
  SEEDS, METRICS, LAYOUTS, FIELDS, GROUP_FIELDS, MEASURES, CUSTOM_DEFAULTS,
  TICKETS, buildResult, stateAt, validChart, upgradeChart, validateFilters, scopeLabels, resultCSV,
  SEARCH_FIELDS, HISTORY, configureLiveData, configureSampleData, captureLabel,
  ticketReference, ticketChartLabel, ticketText, pointTicket, itemCount,
  chartHasDateAxis, datePresetRange, withDateRange, resolveFilters,
  observationLoader, setRealObservation,
  usesObservedHistory, setObservedResult, resultTicket,
} from "./flow-metrics-model.mjs";
import { CALCULATIONS, CALCULATION_DEFAULTS, calculationSettings, builderError, editableRecipe } from "./flow-metrics-builder.mjs";
import { REQUEST_VERSION, REQUEST_LIMIT, requestDetails, requestKey, parseRequests } from "./flow-metrics-admin.mjs";

const $ = (id) => document.getElementById(id);
const STORAGE_KEY = "hub.flow-metrics.sample.three-sprints.v1";
const live = $("team-panel").dataset.live === "true";
let workspaceRevision;
let csrf;
let previewSequence = 0;
let saving = false;
let pendingPreview = false;
let loadObservation;
const ticketLabel = "items";
const colours = ["#1d70b8", "#b85900", "#4c2c92", "#505a5f", "#007c91", "#0b0c0c"];
const clone = (value) => structuredClone(value);
let charts = [];
let selected;
let draft;
let result;
let chart;
let tableVisible = false;
let invalidConfiguration = false;
let pendingDrillTrigger;
let activeSuggestion = -1;
let dateRangeMenu = false;
const PAGE_SIZE = 10;
let dataPage = 1;
let ticketPage = 1;
let drillPoint;
const calculationControls = {
  interval: "reporting-interval", aggregation: "aggregation", minDays: "min-days",
  bandWidth: "band-width", counting: "counting", value: "calculation-value", additional: "additional-measure",
};

function icon(paths) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "flow-symbol");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.6");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  paths.forEach((d) => {
    const path = document.createElementNS(svg.namespaceURI, "path");
    path.setAttribute("d", d);
    svg.append(path);
  });
  return svg;
}

function chartIcon(layout) {
  const axes = "M3 3v18h18";
  const paths = {
    bar: ["M7 5h12v3H7z M7 11h8v3H7z M7 17h14v3H7z"],
    column: [axes, "M7 17v-5h3v5 M13 17V7h3v10 M19 17V4h2v13"],
    line: [axes, "m6 15 4-5 4 3 6-8"],
    area: [axes, "M6 18v-5l4-5 4 3 6-6v13z", "m6 16 4-3 4 2 6-4"],
    scatter: [axes, "M7 15h.1 M10 9h.1 M13 13h.1 M16 6h.1 M20 10h.1"],
    histogram: [axes, "M6 20v-7h4v7 M10 20V6h4v14 M14 20V9h4v11 M18 20v-5h3"],
    "stacked-bar": ["M4 5h16v5H4z M4 14h12v5H4z M11 5v5 M9 14v5"],
    "stacked-column": [axes, "M7 20V9h5v11 M15 20V4h5v16 M7 14h5 M15 11h5"],
    flow: [axes, "M6 18V9l5 2 5-5 5-2v14z", "m6 14 5 1 5-4 5-2"],
    burnup: [axes, "M6 17h4v-4h4V9h6", "M6 6h14"],
  };
  return icon(paths[layout] || paths.column);
}

// Native selects cannot consistently render SVG options across supported browsers.
function enhanceIconSelect(id, symbol) {
  const select = $(id);
  select.hidden = true;
  select.tabIndex = -1;
  const wrapper = document.createElement("div");
  wrapper.className = "flow-select";
  const button = document.createElement("button");
  button.type = "button";
  button.id = `${id}-picker`;
  button.className = "flow-select-button";
  button.setAttribute("aria-haspopup", "listbox");
  button.setAttribute("aria-expanded", "false");
  const label = document.querySelector(`label[for="${id}"]`);
  label.htmlFor = button.id;
  const list = document.createElement("div");
  list.id = `${id}-options`;
  list.className = "flow-select-options";
  list.setAttribute("role", "listbox");
  list.setAttribute("aria-label", label.textContent);
  list.hidden = true;
  button.setAttribute("aria-controls", list.id);
  const close = (focus = false) => {
    list.hidden = true;
    button.setAttribute("aria-expanded", "false");
    if (focus) button.focus();
  };
  const sync = () => {
    const selected = select.selectedOptions[0];
    button.replaceChildren(symbol(select.value), document.createTextNode(selected?.textContent || ""));
    for (const option of list.children) option.setAttribute("aria-selected", String(option.dataset.value === select.value));
  };
  for (const option of select.options) {
    const row = document.createElement("div");
    row.className = "flow-search-option";
    row.setAttribute("role", "option");
    row.tabIndex = -1;
    row.dataset.value = option.value;
    row.append(symbol(option.value), document.createTextNode(option.textContent));
    row.addEventListener("click", () => {
      select.value = option.value;
      sync();
      close(true);
      select.dispatchEvent(new Event("input", { bubbles: true }));
    });
    row.addEventListener("keydown", (event) => {
      const rows = [...list.children];
      const index = rows.indexOf(row);
      if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
        event.preventDefault();
        const next = event.key === "Home" ? 0 : event.key === "End" ? rows.length - 1
          : (index + (event.key === "ArrowDown" ? 1 : -1) + rows.length) % rows.length;
        rows[next].focus();
      } else if (event.key === "Enter" || event.key === " ") { event.preventDefault(); row.click(); }
      else if (event.key === "Escape") { event.preventDefault(); close(true); }
      else if (event.key === "Tab") close();
    });
    list.append(row);
  }
  button.addEventListener("click", () => {
    if (!list.hidden) { close(); return; }
    list.hidden = false;
    button.setAttribute("aria-expanded", "true");
    [...list.children].find((option) => option.dataset.value === select.value)?.focus();
  });
  button.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); button.click(); }
  });
  document.addEventListener("click", (event) => { if (!wrapper.contains(event.target)) close(); });
  wrapper.append(button, list);
  select.after(wrapper);
  sync();
  return sync;
}
const syncPickers = [];

async function refreshCollectionHealth() {
  try {
    const health = await apiRequest("collection-health");
    const failed = health.status === "failed" || health.scheduledStatus === "failed";
    const freshness = health.capturedAt
      ? `${captureLabel(health.capturedAt)}${failed ? " Latest collection failed." : ""}`
      : failed ? "No complete capture yet. Latest collection failed." : "No complete capture yet.";
    if ($("live-freshness").textContent !== freshness) $("live-freshness").textContent = freshness;
    const run = health.latestRun;
    const outcome = { complete: "Succeeded", failed: "Failed", running: "Running" };
    const stamp = value => {
      const date = new Date(value);
      const day = new Intl.DateTimeFormat("en-GB", {
        timeZone: "Europe/London", day: "numeric", month: "short", year: "numeric",
      }).format(date);
      const time = new Intl.DateTimeFormat("en-GB", {
        timeZone: "Europe/London", hour: "numeric", minute: "2-digit", hour12: true,
      }).format(date).replace(/\s/g, "");
      return `${day}, ${time}`;
    };
    $("collection-status").textContent = run
      ? `${stamp(run.startedAt)} · ${outcome[run.status] || "Unknown outcome"}${run.failureReason ? ` — ${run.failureReason}` : ""}`
      : "No runs recorded";
  } catch (error) {
    $("live-freshness").textContent = `Last updated unavailable. ${error.message}`;
    $("collection-status").textContent = `Run status unavailable. ${error.message}`;
  }
}
refreshCollectionHealth();
setInterval(() => { if (!document.hidden) refreshCollectionHealth(); }, 60000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshCollectionHealth(); });

function fieldIcon(field) {
  const person = ["M8 8a4 4 0 1 0 8 0a4 4 0 1 0-8 0", "M4 21v-2a8 8 0 0 1 16 0v2"];
  const select = ["M4 4h16v16H4z", "m8 10 4 4 4-4"];
  const calendar = ["M4 5h16v16H4z M4 10h16 M8 3v4 M16 3v4", "M8 14h2 M14 14h2 M8 17h2"];
  const relationship = ["M7 4v12a4 4 0 0 0 4 4h6 M7 9h10", "m14 6 3 3-3 3 M14 17l3 3-3 3"];
  const paths = {
    is: ["M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0", "m8 12 3 3 5-6"],
    assignee: person, reviewers: person,
    label: ["M3 4h8l10 10-7 7L3 10z", "M7 8h.1"],
    repository: ["M5 3h14v18H5z M5 16h14 M9 3v10"],
    "blocked-by": relationship, blocking: relationship, "relates-to": relationship,
    title: ["M4 5h16 M12 5v15 M8 20h8"],
    status: select, priority: select, refined: select, planned: select,
    sprint: ["M6 7h12l-3-3 M18 17H6l3 3", "M20 8a8 8 0 0 1 0 8 M4 16a8 8 0 0 1 0-8"],
    milestone: ["M5 3v18 M5 6h12l4 4-4 4H5"],
    type: ["M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0", "M12 8v8 M8 12h8"],
    "parent-issue": ["M4 4h16v7H4z M12 11v5 M7 16h10 M7 16v5 M17 16v5"],
    "sub-issues-progress": ["M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0", "m7 12 3 3 6-6"],
    team: ["M5 7a3 3 0 1 0 6 0a3 3 0 1 0-6 0 M15 8a2 2 0 1 0 4 0a2 2 0 1 0-4 0", "M2 21v-3a6 6 0 0 1 12 0v3 M17 14a5 5 0 0 1 5 5v2"],
    objective: ["M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0 M7 12a5 5 0 1 0 10 0a5 5 0 1 0-10 0 M12 12h.1"],
    from: calendar, to: calendar,
  };
  return icon(paths[field] || select);
}

function message(text, error = false) {
  if ($("chart-workspace").hidden) document.querySelector(".flow-main").prepend($("flow-message"));
  else $("search-error").after($("flow-message"));
  $("flow-message").textContent = text;
  $("flow-message").dataset.error = String(error);
  $("flow-message").setAttribute("role", error ? "alert" : "status");
  $("flow-message").setAttribute("aria-live", error ? "assertive" : "polite");
}

function readStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw !== null) {
      const stored = JSON.parse(raw);
      if (!Array.isArray(stored) || stored.length > 100) {
        throw new Error("Invalid chart definitions");
      }
      const upgraded = stored.map(upgradeChart);
      if (new Set(upgraded.map((item) => item.id)).size !== upgraded.length) throw new Error("Duplicate chart identifiers");
      upgraded.forEach((item) => {
        const legacy = ["team", "sprint", "status", "from", "to"].filter((key) => item.filters[key])
          .map((key) => `${key}:${JSON.stringify(item.filters[key])}`);
        item.filters.query = [...legacy, item.filters.query].filter(Boolean).join(" ");
        ["team", "sprint", "status", "from", "to"].forEach((key) => { item.filters[key] = ""; });
      });
      return upgraded;
    }
  } catch (error) {
    console.warn("Flow Metrics prototype chart storage could not be read.", error);
    message("Browser chart storage could not be read. It has not been changed; shared database charts are shown.", true);
  }
  return [];
}

async function apiRequest(path, body) {
  const response = await fetch(`./api/${path}`, {
    method: body === undefined ? "GET" : "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(body === undefined ? {} : { "X-Flow-CSRF": csrf }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (response.status === 429) throw new Error("Too many requests. Wait a minute, then change the filter or reload to retry.");
  if (response.redirected || !response.headers.get("content-type")?.includes("application/json")) {
    throw new Error("Your session expired or the service is unavailable. Reload and sign in again.");
  }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Flow Metrics request failed (${response.status}).`);
  return data;
}

async function persist(next) {
    if (saving) { message("A save is already in progress. Wait before making another change.", true); return false; }
    saving = true;
    $("chart-workspace").inert = true;
    $("chart-sidebar").inert = true;
    try {
      const saved = await apiRequest("charts", { charts: next, revision: workspaceRevision });
      workspaceRevision = saved.revision;
      charts = next;
      return true;
    } catch (error) {
      message(error.message, true);
      return false;
    } finally {
      saving = false;
      $("chart-workspace").inert = false;
      $("chart-sidebar").inert = false;
    }
}

function currentSaved() { return charts.find((item) => item.id === selected); }
function dirty() { return Boolean(draft) && (invalidConfiguration || JSON.stringify(draft) !== JSON.stringify(currentSaved())); }
function mayLeave() { return !saving && (!dirty() || window.confirm("Discard the unsaved chart changes?")); }

function openConfiguration() {
  if (!draft || saving) return;
  $("configuration").hidden = false;
  $("configure-toggle").setAttribute("aria-expanded", "true");
  $("chart-name").focus();
}

function discardChanges() {
  select(currentSaved() ? selected : charts[0]?.id);
  message("Unsaved changes discarded.");
  retainActionFocus();
}

function retainActionFocus() {
  if (document.activeElement === document.body || document.activeElement.disabled) {
    (draft ? $("configure-toggle") : $("new-chart")).focus();
  }
}

let openChartMenu;
function closeChartMenu(returnFocus = false) {
  if (!openChartMenu) return;
  const menu = openChartMenu;
  openChartMenu = null;
  menu.open = false;
  menu.querySelector("summary").setAttribute("aria-expanded", "false");
  if (returnFocus) menu.querySelector("summary").focus();
}
function positionChartMenu() {
  if (!openChartMenu) return;
  const trigger = openChartMenu.querySelector("summary").getBoundingClientRect();
  const panel = openChartMenu.querySelector(".flow-menu-panel");
  const width = panel.offsetWidth;
  const height = panel.offsetHeight;
  const beside = trigger.right + 8 + width <= innerWidth - 12;
  panel.style.left = `${Math.max(12, Math.min(beside ? trigger.right + 8 : trigger.right - width, innerWidth - width - 12))}px`;
  panel.style.top = `${Math.max(12, Math.min(beside ? trigger.top : trigger.bottom + 4, innerHeight - height - 12))}px`;
}
document.addEventListener("click", (event) => {
  if (openChartMenu && !openChartMenu.contains(event.target)) closeChartMenu();
});
document.addEventListener("keydown", (event) => {
  if (openChartMenu && event.key === "Escape") {
    event.preventDefault();
    closeChartMenu(true);
  }
});
window.addEventListener("resize", positionChartMenu);
window.addEventListener("scroll", positionChartMenu, true);

function renderList() {
  closeChartMenu();
  const list = $("chart-list");
  list.replaceChildren();
  charts.forEach((item) => {
    const row = document.createElement("div");
    row.className = "flow-chart-row";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "flow-chart-link";
    const label = document.createElement("span");
    label.className = "flow-chart-label";
    label.textContent = item.name;
    button.append(chartIcon(item.id === selected && draft ? draft.layout : item.layout), label);
    button.setAttribute("aria-current", String(item.id === selected));
    button.addEventListener("click", () => {
      if (mayLeave()) select(item.id);
    });
    const actions = document.createElement("details");
    actions.className = "flow-chart-menu";
    const toggle = document.createElement("summary");
    toggle.className = "flow-icon-button";
    toggle.textContent = "\u22ef";
    toggle.setAttribute("aria-label", `Actions for ${item.name}`);
    toggle.setAttribute("aria-expanded", "false");
    toggle.dataset.chartId = item.id;
    const panel = document.createElement("div");
    panel.className = "flow-menu-panel";
    panel.id = `chart-actions-${item.id}`;
    panel.setAttribute("role", "group");
    panel.setAttribute("aria-label", `Actions for ${item.name}`);
    toggle.setAttribute("aria-controls", panel.id);
    actions.append(toggle, panel);
    const action = (label, handler, paths, { disabled = false, footer = false } = {}) => {
      const control = document.createElement("button");
      control.type = "button";
      control.className = footer ? `govuk-button${label === "Discard" ? " govuk-button--secondary" : ""}` : "flow-menu-action";
      if (label === "Delete chart") control.classList.add("flow-menu-delete");
      if (paths) control.append(icon(paths));
      control.append(document.createTextNode(label));
      control.disabled = disabled;
      control.addEventListener("click", async () => {
        closeChartMenu(true);
        if (item.id !== selected) {
          if (!mayLeave()) return;
          select(item.id);
        }
        await handler();
        if (label !== "Configure" && label !== "Delete chart") {
          document.querySelector(`summary[data-chart-id="${CSS.escape(selected)}"]`)?.focus();
        }
      });
      (footer ? panel.querySelector(".flow-menu-footer") : panel).append(control);
    };
    const isSelected = item.id === selected;
    action("Configure", openConfiguration, ["M4 7h16 M4 17h16 M8 4v6 M16 14v6"]);
    action("Save as new", () => save(true), ["M9 9h12v12H9z M15 5V3H3v12h2"], { disabled: isSelected && invalidConfiguration });
    action("Delete chart", openDeleteDialog, ["M4 6h16 M9 6V3h6v3 M6 6l1 15h10l1-15 M10 10v7 M14 10v7"]);
    const footer = document.createElement("div");
    footer.className = "flow-menu-footer";
    panel.append(footer);
    action("Discard", discardChanges, null, { footer: true, disabled: !isSelected || !dirty() });
    action("Save", () => save(), null, { footer: true, disabled: !isSelected || !dirty() || invalidConfiguration });
    const openActions = () => {
      if (openChartMenu !== actions) closeChartMenu();
      actions.open = true;
      openChartMenu = actions;
      toggle.setAttribute("aria-expanded", "true");
      positionChartMenu();
    };
    toggle.addEventListener("click", (event) => {
      event.preventDefault();
      if (actions.open) closeChartMenu();
      else openActions();
    });
    actions.addEventListener("toggle", () => {
      if (actions.open) {
        if (openChartMenu !== actions) closeChartMenu();
        openChartMenu = actions;
        toggle.setAttribute("aria-expanded", "true");
        positionChartMenu();
      } else {
        toggle.setAttribute("aria-expanded", "false");
        if (openChartMenu === actions) openChartMenu = null;
      }
    });
    actions.addEventListener("keydown", (event) => {
      if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
        event.preventDefault();
        openActions();
        const controls = [...panel.querySelectorAll("button:not(:disabled)")];
        const index = controls.indexOf(document.activeElement);
        const target = event.key === "Home" ? 0 : event.key === "End" ? controls.length - 1
          : index < 0 ? event.key === "ArrowUp" ? controls.length - 1 : 0
          : (index + (event.key === "ArrowDown" ? 1 : -1) + controls.length) % controls.length;
        controls[target]?.focus();
      }
    });
    actions.addEventListener("focusout", (event) => {
      if (!actions.contains(event.relatedTarget) && openChartMenu === actions) closeChartMenu();
    });
    row.append(button, actions);
    list.append(row);
  });
}

function syncControls() {
  closeDateRange();
  invalidConfiguration = false;
  $("config-error").hidden = true;
  $("chart-workspace").hidden = !draft;
  $("empty-state").hidden = Boolean(draft);
  if (!draft) return;
  $("chart-name").value = draft.name;
  $("metric").value = draft.metric;
  $("layout").value = draft.layout;
  $("threshold").value = draft.threshold;
  $("x-axis").value = draft.x;
  $("y-axis").value = draft.y;
  $("group-by").value = draft.group;
  const settings = calculationSettings(draft);
  for (const [key, id] of Object.entries(calculationControls)) $(id).value = settings[key];
  syncPickers.forEach((sync) => sync());
  $("filter-query").value = draft.filters.query || "";
  $("search-error").hidden = true;
  $("filter-query").removeAttribute("aria-invalid");
  closeSuggestions();
  syncFieldVisibility();
  $("delete-chart").disabled = !currentSaved();
}

function syncFieldVisibility() {
  $("threshold-field").hidden = draft.metric !== "stuck";
  $("threshold").disabled = draft.metric !== "stuck";
  if (draft.metric !== "stuck") $("threshold").value = draft.threshold;
  $("custom-fields").hidden = draft.metric !== "custom";
  $("custom-fields").disabled = draft.metric !== "custom";
  $("edit-recipe").hidden = draft.metric === "custom";
  $("x-label").textContent = "Category / axis";
  $("y-label").textContent = "Measure";
  const spec = CALCULATIONS[draft.y];
  const custom = draft.metric === "custom";
  const conditions = {
    "interval-field": custom && ["reporting", "completionDate"].includes(draft.x) && !spec?.duration,
    "aggregation-field": custom && spec?.duration && !["scatter", "histogram"].includes(draft.layout),
    "min-days-field": custom && (draft.y === "statusDays" || draft.x === "statusBand"),
    "bands-field": custom && (draft.layout === "histogram" || draft.x === "statusBand"),
    "counting-field": custom && ["addedScope", "removedScope", "scopeChanges"].includes(draft.y),
    "value-field": custom && ["committedScope", "completedScope"].includes(draft.y) && draft.x === "sprint",
    "additional-field": custom && ["committedScope", "addedScope", "removedScope", "sprintScope", "completedScope"].includes(draft.y),
  };
  for (const [id, visible] of Object.entries(conditions)) {
    $(id).hidden = !visible;
    $(id).querySelectorAll("input, select").forEach(control => { control.disabled = !visible; });
  }
  for (const option of $("additional-measure").options) {
    option.disabled = Boolean(builderError({ ...draft, calculation: { ...calculationSettings(draft), additional: option.value } }));
  }
}

function updateWorkspaceURL(view) {
  const url = new URL(window.location.href);
  if (view === "admin") url.searchParams.set("view", "admin");
  else if (view === "team") url.searchParams.delete("view");
  if (charts.some(item => item.id === selected)) url.searchParams.set("chart", selected);
  else url.searchParams.delete("chart");
  window.history.replaceState(null, "", url);
}

function select(id) {
  selected = charts.some(item => item.id === id) ? id
    : (live ? charts.find(item => item.metric === "status")?.id : null) || charts[0]?.id;
  draft = currentSaved() ? clone(currentSaved()) : null;
  $("configuration").hidden = true;
  $("configure-toggle").setAttribute("aria-expanded", "false");
  $("drill-down").hidden = true;
  syncControls();
  if (draft) $("search-error").after($("flow-message"));
  renderList();
  renderPreview();
  updateWorkspaceURL();
}

function chartConfig() {
  const horizontal = ["bar", "stacked-bar"].includes(draft.layout);
  const stacked = ["area", "stacked-bar", "stacked-column", "flow"].includes(draft.layout);
  const scatter = draft.layout === "scatter";
  const line = ["line", "area", "flow", "burnup"].includes(draft.layout);
  const numericPrecision = draft.metric === "custom" && (draft.y.startsWith("average") || draft.calculation?.aggregation === "average") ? 2 : 0;
  const plottedIds = new Set(result.series.flatMap((series) => series.points.map((point) => point.ticketId)).filter(Boolean));
  const plottedItems = result.tickets.filter((ticket) => plottedIds.has(ticket.id));
  const labels = result.series[0]?.points.map((p) => {
    const ticket = pointTicket(p, result.tickets);
    return ticket ? ticketChartLabel(ticket, plottedItems) : p.label;
  }) || [];
  return {
    type: scatter ? "scatter" : line ? "line" : "bar",
    data: {
      labels,
      datasets: result.series.map((series, i) => ({
        label: series.name,
        data: series.points.map((point) => scatter ? { x: point.x, y: point.value } : point.value),
        backgroundColor: `${colours[i % colours.length]}${line && stacked ? "55" : ""}`,
        borderColor: colours[i % colours.length],
        borderWidth: line ? 2 : 1,
        borderDash: i % 2 ? [6, 3] : [],
        pointStyle: i % 2 ? "rect" : "circle",
        pointRadius: scatter ? 5 : labels.length > 30 ? 0 : 3,
        pointHitRadius: 10,
        fill: line && stacked ? (i === 0 ? "origin" : "-1") : false,
        tension: 0,
      })),
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      indexAxis: horizontal ? "y" : "x",
      interaction: { mode: "nearest", intersect: true },
      scales: {
        x: {
          type: scatter || horizontal ? "linear" : "category", stacked, beginAtZero: !scatter,
          title: { display: true, text: horizontal ? result.unit : result.axis },
          ticks: { maxTicksLimit: 9, precision: horizontal ? numericPrecision : 0, ...(scatter ? {
            stepSize: 86400000,
            callback: (value) => new Date(value).toLocaleDateString("en-GB", { timeZone: "UTC" }),
          } : {}) },
        },
        y: { type: horizontal ? "category" : "linear", stacked, beginAtZero: true, title: { display: true, text: horizontal ? result.axis : result.unit }, ticks: { precision: horizontal ? 0 : numericPrecision } },
      },
      plugins: {
        title: { display: true, text: draft.name || "Untitled chart", color: "#0b0c0c", font: { size: 18 }, padding: 12 },
        legend: { display: true, position: "bottom", labels: { usePointStyle: true, color: "#0b0c0c", padding: 16 } },
        tooltip: { callbacks: {
          title: (items) => {
            const point = result.series[items[0].datasetIndex].points[items[0].dataIndex];
            const ticket = pointTicket(point, result.tickets);
            const label = ticket ? ticketText(ticket) : point.label;
            return scatter ? `${label} · ${point.completedDate.split("-").reverse().join("/")}` : label;
          },
          label: (item) => {
            const series = result.series[item.datasetIndex];
            const point = series.points[item.dataIndex];
            return `${series.name}: ${point.value === null ? "No observations" : `${point.value} ${result.unit.toLowerCase()}`}`;
          },
          footer: (items) => {
            const point = result.series[items[0].datasetIndex].points[items[0].dataIndex];
            const count = scatter ? result.rows.filter((other) => other.x === point.x && other.value === point.value).length : 0;
            return count > 1 ? `${count} overlapping items; select to inspect all` : `Select to inspect ${ticketLabel}`;
          },
        } },
      },
      onClick: (_event, elements) => {
        if (!elements.length) return;
        const { datasetIndex, index } = elements[0];
        const point = result.series[datasetIndex].points[index];
        if (scatter) {
          const overlaps = result.series.flatMap((series) => series.points)
            .filter((other) => other.x === point.x && other.value === point.value);
          showDrill({ ...point, ids: overlaps.flatMap((other) => other.ids) }, $("show-table"));
        } else showDrill(point, $("show-table"));
      },
    },
  };
}

function table(headers, rows, caption) {
  const element = document.createElement("table");
  element.className = "govuk-table";
  const title = element.createCaption();
  title.textContent = caption;
  title.className = "govuk-table__caption govuk-table__caption--s";
  const head = element.createTHead().insertRow();
  headers.forEach((label) => {
    const th = document.createElement("th");
    th.scope = "col";
    th.className = "govuk-table__header";
    th.textContent = label;
    head.append(th);
  });
  const body = element.createTBody();
  rows.forEach((cells) => {
    const row = body.insertRow();
    cells.forEach((content) => {
      const cell = row.insertCell();
      cell.className = "govuk-table__cell";
      if (content instanceof Node) cell.append(content);
      else cell.textContent = content === null ? "No observations" : String(content);
    });
  });
  return element;
}

function ticketCell(ticket) {
  const content = document.createElement("div");
  content.className = "flow-ticket-identity";
  const title = document.createElement("span");
  title.textContent = ticket.title;
  const reference = document.createElement((live || ticket.provenance === "real") && ticket.url ? "a" : "span");
  reference.textContent = ticketReference(ticket);
  if (reference.tagName === "A") {
    reference.className = "govuk-link";
    reference.href = ticket.url;
  }
  content.append(title, reference);
  return content;
}

function renderTable() {
  const total = result.rows.length;
  dataPage = Math.min(dataPage, Math.max(1, Math.ceil(total / PAGE_SIZE)));
  $("table-view").replaceChildren(table(
    ["Series", "Point", ...(draft.layout === "scatter" ? ["Completion date"] : []), result.unit, "Drill-down"],
    result.rows.slice((dataPage - 1) * PAGE_SIZE, dataPage * PAGE_SIZE).map((row) => {
      const button = document.createElement("button");
      button.className = "flow-link-button";
      button.type = "button";
      button.textContent = itemCount(row.ids.length);
      button.setAttribute("aria-label", `${itemCount(row.ids.length)} for ${row.series}, ${row.label}`);
      button.addEventListener("click", () => showDrill(row, button));
      const ticket = pointTicket(row, result.tickets);
      return [row.series, ticket ? ticketCell(ticket) : row.label, ...(draft.layout === "scatter" ? [row.completedDate.split("-").reverse().join("/")] : []), row.value, button];
    }),
    "Exact values",
  ));
  $("table-view").append(pagination(total, dataPage, (page) => {
    dataPage = page;
    renderTable();
    $("table-view").focus();
  }, "Data table"));
}

function pagination(total, page, onPage, label) {
  const container = document.createElement("div");
  const summary = document.createElement("p");
  summary.className = "govuk-body-s";
  summary.setAttribute("role", "status");
  summary.textContent = total ? `Showing ${(page - 1) * PAGE_SIZE + 1} to ${Math.min(page * PAGE_SIZE, total)} of ${total}` : "No rows";
  container.append(summary);
  const pages = Math.ceil(total / PAGE_SIZE);
  if (pages <= 1) return container;
  const nav = document.createElement("nav");
  nav.className = "flow-pagination";
  nav.setAttribute("aria-label", `${label} pages`);
  const add = (text, target, current = false) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "flow-page-button";
    button.textContent = text;
    if (current) button.setAttribute("aria-current", "page");
    button.setAttribute("aria-label", /^\d+$/.test(text) ? `Page ${text}` : text);
    if (text === "Previous" || text === "Next") {
      button.classList.add("flow-page-direction");
      const arrow = document.createElement("span");
      arrow.className = "flow-page-arrow";
      arrow.setAttribute("aria-hidden", "true");
      arrow.textContent = text === "Next" ? "\u2192" : "\u2190";
      if (text === "Next") button.append(arrow);
      else button.prepend(arrow);
    }
    button.addEventListener("click", () => onPage(target));
    nav.append(button);
  };
  if (page > 1) add("Previous", page - 1);
  const visible = new Set([1, pages, page - 1, page, page + 1].filter((n) => n >= 1 && n <= pages));
  let previous = 0;
  [...visible].sort((a, b) => a - b).forEach((n) => {
    if (previous && n > previous + 1) {
      const gap = document.createElement("span");
      gap.textContent = "\u2026";
      nav.append(gap);
    }
    add(String(n), n, n === page);
    previous = n;
  });
  if (page < pages) add("Next", page + 1);
  container.append(nav);
  return container;
}

async function renderPreview() {
  const sequence = ++previewSequence;
  if (chart) { chart.destroy(); chart = null; }
  if (!draft) return;
  if (live || loadObservation) {
    pendingPreview = true;
    result = null;
    $("export-csv").disabled = true;
    $("result-summary").textContent = "Loading...";
    $("chart-view").hidden = true;
    $("table-view").hidden = true;
    $("drill-down").hidden = true;
    await new Promise((resolve) => setTimeout(resolve, 350));
    if (sequence !== previewSequence) return;
    try {
      const historical = usesObservedHistory(draft);
      const { resolved } = resolveFilters(draft.filters);
      const observedChart = { ...draft, filters: { ...draft.filters,
        from: resolved.from || HISTORY.from, to: resolved.to || HISTORY.to } };
      const [response, observed] = await Promise.all([
        live ? apiRequest("result", draft) : loadObservation(draft.filters),
        historical && !live ? apiRequest("observed-result", observedChart) : null,
      ]);
      if (sequence !== previewSequence) return;
      if (live) result = response;
      else {
        setRealObservation(response);
        setObservedResult(observed);
        result = buildResult(draft);
      }
      pendingPreview = false;
      if (live) TICKETS.splice(0, TICKETS.length, ...result.tickets);
    } catch (error) {
      if (sequence !== previewSequence) return;
      result = null;
      pendingPreview = false;
      $("result-summary").textContent = error.message;
      message(error.message, true);
      return;
    }
  } else result = buildResult(draft);
  dataPage = 1;
  $("chart-title").replaceChildren(chartIcon(draft.layout), document.createTextNode(draft.name || "Untitled chart"));
  $("save-state").textContent = dirty() ? "Unsaved changes" : "";
  $("save-chart").disabled = !dirty();
  $("discard-chart").disabled = !dirty();
  $("search-save").disabled = !dirty();
  $("search-discard").disabled = !dirty();
  $("copy-chart").disabled = false;
  renderScope();
  renderDateRanges();
  $("result-summary").textContent = result.unavailable || (result.sampleSize
    ? ""
    : "No matching items. Change the filters.");
  if (live && !result.unavailable && !result.sampleSize) $("result-summary").textContent = "No matching board items at this observation.";
  $("drill-down").hidden = true;
  $("export-csv").disabled = !result.rows.length;
  renderTable();
  renderList();
  if (!window.Chart) {
    message("The chart library could not load. Use the data table and CSV export, or reload to retry.", true);
    tableVisible = true;
  }
  if (result.unavailable) {
    $("chart-view").hidden = true;
    $("table-view").hidden = true;
  } else updateView();
}

function closeDateRange() {
  $("date-range-panel").hidden = true;
  dateRangeMenu = false;
}

function renderDateRanges() {
  if (!chartHasDateAxis(draft)) closeSuggestions();
}

function selectedDateRange() {
  const { resolved } = resolveFilters(draft.filters);
  return !resolved.from && !resolved.to ? "max"
    : ["2weeks", "1month", "3months"].find((key) => {
      const range = datePresetRange(key);
      return resolved.from === range.from && resolved.to === range.to;
    });
}

function applyDateRange(from, to) {
  try {
    const filters = withDateRange({ ...draft.filters, query: $("filter-query").value }, from, to);
    $("search-error").hidden = true;
    $("filter-query").removeAttribute("aria-invalid");
    $("filter-query").value = filters.query;
    draft = { ...draft, filters };
    closeSuggestions();
    previewConfiguration();
    return true;
  } catch (error) {
    $("date-range-error").textContent = error.message;
    $("date-range-error").hidden = false;
    return false;
  }
}

function openCustomDateRange() {
  closeSuggestions();
  const { resolved } = resolveFilters(draft.filters);
  $("range-from").value = resolved.from || HISTORY.from;
  $("range-to").value = resolved.to || HISTORY.to;
  for (const id of ["range-from", "range-to"]) {
    $(id).min = HISTORY.from;
    $(id).max = HISTORY.to;
  }
  $("date-range-error").hidden = true;
  $("date-range-panel").hidden = false;
  $("range-from").focus();
}
function returnToFilter() {
  $("filter-query").focus();
  closeSuggestions();
}
$("custom-date-fields").addEventListener("submit", (event) => {
  event.preventDefault();
  if (saving) return;
  if (applyDateRange($("range-from").value, $("range-to").value)) returnToFilter();
});
$("cancel-date-range").addEventListener("click", returnToFilter);
$("custom-date-fields").addEventListener("keydown", (event) => {
  if (event.key === "Escape") { event.preventDefault(); returnToFilter(); }
});
$("date-range-panel").addEventListener("focusout", (event) => {
  if (!$("date-range-panel").contains(event.relatedTarget)) closeSuggestions();
});

function renderScope() {
  const labels = scopeLabels(draft.filters);
  const scope = $("chart-scope");
  if (scope.textContent === `Showing: ${labels.join(" · ")}`) return;
  const content = document.createDocumentFragment();
  content.append("Showing: ");
  labels.forEach((label, index) => {
    if (index) content.append(" · ");
    const value = document.createElement("strong");
    value.className = "govuk-!-font-weight-bold";
    value.textContent = label;
    content.append(value);
  });
  scope.replaceChildren(content);
}

function updateView() {
  if (!result || result.unavailable) return;
  $("chart-view").hidden = tableVisible;
  $("table-view").hidden = !tableVisible;
  $("show-chart").setAttribute("aria-pressed", String(!tableVisible));
  $("show-table").setAttribute("aria-pressed", String(tableVisible));
  if (draft && !tableVisible && window.Chart) {
    if (chart) chart.destroy();
    chart = new window.Chart($("chart"), chartConfig());
  }
}

function showDrill(point, trigger) {
  if (pendingPreview || !result) return;
  pendingDrillTrigger = trigger;
  drillPoint = point;
  ticketPage = 1;
  renderTickets();
  $("drill-down").hidden = false;
  $("drill-title").focus();
}

function renderTickets() {
  const tickets = result.tickets.filter((ticket) => drillPoint.ids.includes(ticket.id))
    .map(ticket => resultTicket(result, drillPoint, ticket.id));
  $("drill-title").textContent = `${drillPoint.label}: ${itemCount(tickets.length)}`;
  $("ticket-table").replaceChildren(table(
    ["Reference", "Title", "Repository", "Team", "Sprint", drillPoint.timeBasis === "observation" ? "Observed status" : "Status at reporting end", "Observed at"],
    tickets.slice((ticketPage - 1) * PAGE_SIZE, ticketPage * PAGE_SIZE).map((t) => {
      let reference = ticketReference(t);
      if ((live || t.provenance === "real") && t.url) {
        const link = document.createElement("a");
        link.className = "govuk-link";
        link.href = t.url;
        link.textContent = reference;
        reference = link;
      }
      return [reference, t.title, t.repository, t.team,
        t.actualSprint || t.sprint, stateAt(t, result.to)?.status || "Not created",
        t.observedAt ? captureLabel(t.observedAt).replace("Last updated: ", "") : "Explicit fictional events"];
    }),
    "Item drill-down",
  ));
  $("ticket-table").append(pagination(tickets.length, ticketPage, (page) => {
    ticketPage = page;
    renderTickets();
    $("ticket-table").focus();
  }, "Items"));
}

function download(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function save(asNew = false) {
  if (saving) return;
  if (!$("configuration").reportValidity()) return;
  if (invalidConfiguration) {
    $("config-error").focus();
    return;
  }
  if (!validChart(draft)) {
    message("Enter a chart name containing visible text and a whole-number threshold from 1 to 365.", true);
    return;
  }
  if (asNew && charts.length >= 100) {
    message("This workspace supports up to 100 charts. Delete a chart before creating another.", true);
    return;
  }
  const next = clone(draft);
  next.name = next.name.trim();
  if (asNew) {
    next.id = crypto.randomUUID();
    next.name = `${next.name.slice(0, 73)} (copy)`;
  }
  const updated = charts.some((item) => item.id === next.id)
    ? charts.map((item) => item.id === next.id ? next : item)
    : [...charts, next];
  if (!await persist(updated)) return;
  if (selected === next.id || asNew) select(next.id);
  retainActionFocus();
  message(asNew ? "Copy saved to the shared workspace." : "Chart saved to the shared workspace.");
}

Object.entries(METRICS).forEach(([value, item]) => $("metric").add(new Option(item.name, value)));
Object.entries(LAYOUTS).forEach(([value, label]) => $("layout").add(new Option(label, value)));
syncPickers.push(enhanceIconSelect("layout", chartIcon));
syncPickers.push(enhanceIconSelect("metric", (metric) => chartIcon(SEEDS.find((seed) => seed.metric === metric)?.layout || "column")));
Object.entries(FIELDS).forEach(([value, label]) => $("x-axis").add(new Option(label, value)));
Object.entries(GROUP_FIELDS).forEach(([value, label]) => $("group-by").add(new Option(label, value)));
Object.entries(MEASURES).forEach(([value, item]) => $("y-axis").add(new Option(item.name, value)));
Object.entries(CALCULATIONS).forEach(([value, item]) => $("additional-measure").add(new Option(item.name, value)));
syncPickers.push(enhanceIconSelect("x-axis", (field) => fieldIcon(["created", "completed"].includes(field) ? "from" : field)));
syncPickers.push(enhanceIconSelect("group-by", (field) => field ? fieldIcon(field) : icon(["M5 12h14"])));
syncPickers.push(enhanceIconSelect("y-axis", (measure) => chartIcon(measure.startsWith("average") ? "line" : "column")));
{
  charts = [];
  $("chart-workspace").hidden = true;
  $("new-chart").disabled = true;
  try {
    const workspace = await apiRequest("workspace");
    csrf = workspace.csrf;
    workspaceRevision = workspace.revision;
    if (live) configureLiveData(workspace);
    else {
      configureSampleData(workspace.dataset);
      loadObservation = observationLoader(workspace.dataset.realCaptures, async (to) => {
        const response = await apiRequest(`observation?to=${encodeURIComponent(to)}`);
        return response.observation;
      });
    }
    charts = workspace.charts;
    $("new-chart").disabled = false;
    select(new URL(window.location.href).searchParams.get("chart"));
    if (!live) {
      const local = readStorage();
      if (local.length) {
        const encoded = new TextEncoder().encode(JSON.stringify(local));
        const digest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", encoded))]
          .map((byte) => byte.toString(16).padStart(2, "0")).join("").slice(0, 32);
        const imported = local.map((item, index) => ({ ...item, id: `import-${digest}-${index}` }));
        const pending = () => imported.filter((item) => !charts.some((chart) => chart.id === item.id));
        if (pending().length) {
          $("import-browser-charts").hidden = false;
          $("import-browser-charts").textContent = `Import ${pending().length} browser charts`;
          $("import-browser-charts").addEventListener("click", async () => {
            if (!mayLeave() || !window.confirm("Copy these browser charts into the shared workspace? Existing shared charts and the browser originals will be kept.")) return;
            if (charts.length + pending().length > 100) { message("Import would exceed the 100-chart limit. Remove shared charts before importing.", true); return; }
            if (await persist([...charts, ...pending()])) {
              $("import-browser-charts").hidden = true;
              renderList();
              message("Browser charts imported. Original browser data has been kept.");
            }
          });
        }
      }
    }
  } catch (error) {
    message(error.message, true);
  }
}

function previewConfiguration(changedField) {
  if (!draft || saving) return;
  const next = {
    ...draft, name: $("chart-name").value, metric: $("metric").value, layout: $("layout").value,
    x: $("x-axis").value, y: $("y-axis").value, group: $("group-by").value,
    filters: { ...draft.filters, query: $("filter-query").value },
  };
  next.threshold = next.metric === "stuck" ? Number($("threshold").value) : draft.threshold;
  if (next.metric === "custom") {
    const settings = { ...CALCULATION_DEFAULTS };
    for (const [key, id] of Object.entries(calculationControls)) settings[key] = ["minDays", "bandWidth"].includes(key) ? Number($(id).value) : $(id).value;
    next.calculation = settings;
    if (changedField === "y-axis") {
      Object.assign(settings, CALCULATION_DEFAULTS);
      next.group = "";
      if (["cycleTime", "itemAge", "statusDays"].includes(next.y)) {
        next.x = "ticket"; settings.aggregation = "individual";
        if (["scatter", "histogram", "flow", "burnup"].includes(next.layout)) next.layout = "bar";
      } else if (next.y === "completions") next.x = "completionDate";
      else if (["committedScope", "addedScope", "removedScope", "scopeChanges"].includes(next.y)) next.x = "sprint";
      else if (["historicalCount", "sprintScope", "completedScope"].includes(next.y)) next.x = "reporting";
      else if (!Object.hasOwn(GROUP_FIELDS, next.x)) next.x = "status";
    }
    if (changedField === "layout" && ["scatter", "histogram"].includes(next.layout)) {
      next.y = "cycleTime"; next.x = next.layout === "scatter" ? "completionDate" : "durationBand";
      next.group = ""; settings.additional = ""; settings.aggregation = "individual";
    }
    if (changedField === "layout" && next.layout === "flow") {
      next.y = "historicalCount"; next.x = "reporting"; next.group = "status"; settings.additional = "";
    }
    if (changedField === "layout" && next.layout === "burnup") {
      next.y = "sprintScope"; next.x = "reporting"; next.group = ""; settings.additional = "completedScope";
    }
  } else {
    if (changedField === "layout" && next.layout === "flow") next.metric = "flow";
    if (changedField === "layout" && next.layout === "burnup") next.metric = "progress";
    if (changedField === "layout" && ["scatter", "histogram"].includes(next.layout)) next.metric = "cycle";
  }
  if (changedField === "metric") {
    if (next.metric === "flow") next.layout = "flow";
    else if (next.metric === "progress") next.layout = "burnup";
    else if (next.metric !== "custom" && ["flow", "burnup"].includes(next.layout)) next.layout = "column";
  }
  $("metric").value = next.metric;
  $("layout").value = next.layout;
  $("x-axis").value = next.x;
  $("y-axis").value = next.y;
  $("group-by").value = next.group;
  if (next.calculation) for (const [key, id] of Object.entries(calculationControls)) $(id).value = next.calculation[key];
  syncPickers.forEach((sync) => sync());
  try {
    validateFilters(next.filters);
    if (!next.name.trim()) throw new Error("Enter a chart name containing visible text.");
    if (!Number.isInteger(next.threshold) || next.threshold < 1 || next.threshold > 365) {
      throw new Error("Enter a whole-number threshold from 1 to 365.");
    }
    if (builderError(next)) throw new Error(builderError(next));
    if (!validChart(next)) throw new Error("Choose chart fields and a measure from the available options.");
  } catch (error) {
    previewSequence++;
    pendingPreview = false;
    invalidConfiguration = true;
    $("config-error").textContent = `${error.message} The chart still shows the last valid preview.`;
    $("config-error").hidden = false;
    $("save-state").textContent = "Unsaved changes";
    $("save-chart").disabled = true;
    $("discard-chart").disabled = false;
    $("search-save").disabled = true;
    $("search-discard").disabled = false;
    $("copy-chart").disabled = true;
    $("export-csv").disabled = true;
    renderList();
    return;
  }
  draft = next;
  invalidConfiguration = false;
  $("config-error").hidden = true;
  syncFieldVisibility();
  renderPreview();
}
$("configuration").addEventListener("input", (event) => previewConfiguration(event.target.id));
$("edit-recipe").addEventListener("click", () => {
  if (!draft || saving) return;
  draft = editableRecipe(draft);
  syncControls();
  renderPreview();
});
$("configuration").addEventListener("submit", (event) => { event.preventDefault(); save(); });
$("configure-toggle").addEventListener("click", () => {
  const open = $("configuration").hidden;
  if (open) openConfiguration();
  else {
    $("configuration").hidden = true;
    $("configure-toggle").setAttribute("aria-expanded", "false");
  }
});
$("close-configuration").addEventListener("click", () => {
  $("configuration").hidden = true;
  $("configure-toggle").setAttribute("aria-expanded", "false");
  $("configure-toggle").focus();
});
$("discard-chart").addEventListener("click", discardChanges);
$("copy-chart").addEventListener("click", () => save(true));
$("new-chart").addEventListener("click", () => {
  if (!mayLeave()) return;
  if (charts.length >= 100) { message("Delete a chart before creating another (100 chart limit).", true); return; }
  selected = crypto.randomUUID();
  draft = { ...clone(CUSTOM_DEFAULTS), id: selected, name: "New chart" };
  syncControls();
  renderList();
  renderPreview();
  $("configuration").hidden = false;
  $("configure-toggle").setAttribute("aria-expanded", "true");
  $("chart-name").focus();
  $("chart-name").select();
});
let deleteReturnFocus;
function openDeleteDialog() {
  const chart = currentSaved();
  if (!chart || saving) return;
  deleteReturnFocus = document.activeElement;
  $("delete-title").textContent = `Delete \u201c${chart.name}\u201d?`;
  $("delete-dialog").showModal();
  $("cancel-delete").focus();
}
$("delete-chart").addEventListener("click", openDeleteDialog);
$("close-delete").addEventListener("click", () => $("delete-dialog").close());
$("cancel-delete").addEventListener("click", () => $("delete-dialog").close());
$("delete-dialog").addEventListener("close", () => {
  if (deleteReturnFocus?.isConnected) deleteReturnFocus.focus();
  deleteReturnFocus = null;
});
$("delete-dialog").addEventListener("keydown", (event) => {
  if (event.key !== "Tab") return;
  const first = $("close-delete");
  const last = $("confirm-delete");
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
});
$("confirm-delete").addEventListener("click", async () => {
  if (saving || !await persist(charts.filter((item) => item.id !== selected))) return;
  deleteReturnFocus = null;
  $("delete-dialog").close();
  select(charts[0]?.id);
  message("Shared chart deleted from the database.");
  (draft ? $("chart-title") : $("new-chart")).focus();
});
$("open-guide").addEventListener("click", () => {
  closeChartMenu();
  $("how-to-dialog").showModal();
  $("close-guide").focus();
});
$("close-guide").addEventListener("click", () => $("how-to-dialog").close());
$("how-to-dialog").addEventListener("close", () => $("open-guide").focus());
$("how-to-dialog").addEventListener("keydown", (event) => {
  if (event.key !== "Tab") return;
  const controls = [...$("how-to-dialog").querySelectorAll('button, a[href], [tabindex="0"]')];
  const first = controls[0];
  const last = controls.at(-1);
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault(); last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault(); first.focus();
  }
});
$("how-to-dialog").querySelectorAll('a[href^="#"]').forEach(link => link.addEventListener("click", event => {
  event.preventDefault();
  const target = $(link.hash.slice(1));
  target.scrollIntoView({ block: "start" });
  target.focus({ preventScroll: true });
}));
$("search-save").addEventListener("click", () => save());
$("search-discard").addEventListener("click", discardChanges);

function closeSuggestions() {
  $("filter-suggestions").hidden = true;
  $("filter-date-panel").hidden = true;
  closeDateRange();
  $("filter-query").setAttribute("aria-expanded", "false");
  $("filter-query").removeAttribute("aria-activedescendant");
  activeSuggestion = -1;
}

let dateFilter;
function openDateFilter(key, prefix, value = "") {
  closeSuggestions();
  dateFilter = { key, prefix };
  $("filter-date-label").textContent = key === "from" ? "From date" : "To date";
  $("filter-date").value = value;
  $("filter-date").min = HISTORY.from;
  $("filter-date").max = HISTORY.to;
  $("filter-date-panel").hidden = false;
  $("filter-date").focus();
  if ($("filter-date").showPicker) $("filter-date").showPicker();
}

$("filter-date-apply").addEventListener("click", () => {
  const date = $("filter-date");
  if (!date.value) {
    date.setCustomValidity("Choose a date.");
    date.reportValidity();
    return;
  }
  $("filter-query").value = `${dateFilter.prefix}${dateFilter.key}:${date.value} `;
  $("filter-query").focus();
  applySearch();
  closeSuggestions();
});
$("filter-date").addEventListener("input", () => $("filter-date").setCustomValidity(""));
function cancelDateFilter() {
  $("filter-query").focus();
  closeSuggestions();
}
$("filter-date-cancel").addEventListener("click", cancelDateFilter);
$("filter-date-panel").addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    event.preventDefault();
    cancelDateFilter();
  }
});
document.addEventListener("pointerdown", (event) => {
  if (!event.target.closest(".flow-search")) closeSuggestions();
});

function showSuggestions() {
  if (!draft || saving) return;
  $("filter-date-panel").hidden = true;
  const input = $("filter-query");
  const text = input.value;
  const valueMatch = text.match(/(?:^|\s)([a-z-]+):("[^"]*|[^\s"]*)$/);
  const definition = valueMatch && SEARCH_FIELDS.find(([key]) => key === valueMatch[1]);
  if (valueMatch) dateRangeMenu = false;
  let options;
  if (dateRangeMenu && chartHasDateAxis(draft)) {
    const selected = selectedDateRange();
    options = [["2weeks", "2 weeks"], ["1month", "1 month"], ["3months", "3 months"], ["max", "Max"]].map(([key, label]) => ({
      label, field: "from", selected: key === selected,
      choose: () => {
        const range = datePresetRange(key);
        if (applyDateRange(range.from, range.to)) returnToFilter();
        else {
          const error = $("date-range-error").textContent;
          openCustomDateRange();
          $("date-range-error").textContent = error;
          $("date-range-error").hidden = false;
        }
      },
    }));
    options.push({ label: "Custom range", field: "from", choose: openCustomDateRange });
  } else if (definition?.[2]?.length) {
    const typed = valueMatch[2].replaceAll('"', "").toLowerCase();
    options = definition[2].filter((value) => value.toLowerCase().includes(typed)).map((value) => ({
      label: value, choose: () => {
        input.value = `${text.slice(0, valueMatch.index)}${valueMatch.index ? " " : ""}${definition[0]}:${JSON.stringify(value)} `;
        input.focus();
        applySearch();
        closeSuggestions();
      },
    }));
  } else if (definition) {
    options = [];
  } else {
    const fragment = text.match(/(?:^|\s)([a-z-]*)$/)?.[1] || "";
    options = SEARCH_FIELDS.filter(([, label, values]) => (!live || values) && label.toLowerCase().includes(fragment.toLowerCase())).map(([key, label, values]) => ({
      label, field: key, disabled: !values,
      choose: () => {
        if (key === "from" || key === "to") {
          openDateFilter(key, text.slice(0, text.length - fragment.length));
          return;
        }
        input.value = `${text.slice(0, text.length - fragment.length)}${key}:`;
        input.focus();
        showSuggestions();
      },
    }));
  }
  if (!valueMatch && !dateRangeMenu && chartHasDateAxis(draft)) options.unshift({
    label: "Date range", field: "from",
    choose: () => { dateRangeMenu = true; showSuggestions(); },
  });
  const list = $("filter-suggestions");
  list.replaceChildren();
  options.forEach((option, index) => {
    const row = document.createElement("div");
    row.id = `filter-option-${index}`;
    row.className = "flow-search-option";
    row.setAttribute("role", "option");
    row.setAttribute("aria-selected", "false");
    row.setAttribute("aria-disabled", String(Boolean(option.disabled)));
    const symbol = definition ? icon(["m5 12 4 4L19 6"]) : fieldIcon(option.field);
    const label = document.createElement("span");
    label.className = "flow-option-label";
    label.textContent = option.label;
    row.append(symbol, label);
    if (option.selected) {
      const note = document.createElement("small");
      note.textContent = "Selected";
      row.append(note);
      row.dataset.current = "true";
    }
    if (option.disabled) {
      const note = document.createElement("small");
      note.textContent = "Unavailable";
      row.append(note);
      row.title = live ? "This field is not collected" : "No sample data for this field";
    }
    row.addEventListener("mousedown", (event) => event.preventDefault());
    row.addEventListener("click", () => { if (!option.disabled) option.choose(); });
    list.append(row);
  });
  activeSuggestion = -1;
  input.removeAttribute("aria-activedescendant");
  list.hidden = !options.length;
  input.setAttribute("aria-expanded", String(Boolean(options.length)));
}

function applySearch() {
  if (!draft || saving) return;
  try {
    validateFilters({ ...draft.filters, query: $("filter-query").value });
  } catch (error) {
    previewSequence++;
    pendingPreview = false;
    invalidConfiguration = true;
    $("search-error").textContent = error.message;
    $("search-error").hidden = false;
    $("filter-query").setAttribute("aria-invalid", "true");
    $("save-state").textContent = "Unsaved changes";
    ["save-chart", "search-save", "copy-chart", "export-csv"].forEach((id) => { $(id).disabled = true; });
    ["discard-chart", "search-discard"].forEach((id) => { $(id).disabled = false; });
    renderList();
    return;
  }
  $("search-error").hidden = true;
  $("filter-query").removeAttribute("aria-invalid");
  previewConfiguration();
}
$("filter-query").addEventListener("focus", showSuggestions);
$("filter-query").addEventListener("click", showSuggestions);
$("filter-query").addEventListener("input", () => { applySearch(); showSuggestions(); });
$("filter-query").addEventListener("keydown", (event) => {
  if (event.key === "Escape") { closeSuggestions(); return; }
  if (["ArrowDown", "ArrowUp"].includes(event.key) && $("filter-suggestions").hidden) showSuggestions();
  const options = [...$("filter-suggestions").querySelectorAll('[role="option"][aria-disabled="false"]')];
  if (["ArrowDown", "ArrowUp"].includes(event.key)) {
    event.preventDefault();
    if (!options.length) return;
    activeSuggestion = (activeSuggestion + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
    options.forEach((option, index) => option.setAttribute("aria-selected", String(index === activeSuggestion)));
    $("filter-query").setAttribute("aria-activedescendant", options[activeSuggestion].id);
    options[activeSuggestion].scrollIntoView({ block: "nearest" });
  } else if (event.key === "Enter") {
    event.preventDefault();
    if (activeSuggestion >= 0 && options[activeSuggestion]) options[activeSuggestion].click();
    else { applySearch(); closeSuggestions(); }
  } else if (event.key === "Tab") closeSuggestions();
});
$("filter-query").addEventListener("blur", (event) => {
  if (!$("filter-date-panel").contains(event.relatedTarget)
      && !$("date-range-panel").contains(event.relatedTarget)) closeSuggestions();
});
$("show-chart").addEventListener("click", () => { tableVisible = false; updateView(); });
$("show-table").addEventListener("click", () => { tableVisible = true; updateView(); });
$("close-drill").addEventListener("click", () => {
  $("drill-down").hidden = true;
  pendingDrillTrigger?.focus();
});
$("export-csv").addEventListener("click", () => {
  if (!result || pendingPreview || result.unavailable) return;
  download(new Blob([resultCSV(draft, result)], { type: "text/csv;charset=utf-8" }), live ? "flow-metrics-board-observation.csv" : "flow-metrics-demonstration.csv");
  message("CSV exported with exact plotted values, active filters and contributor provenance.");
});
const tabs = [$("team-tab"), $("admin-tab")];
let adminTrigger;
const adminStorageKey = `hub.flow-metrics.admin.requests.v1:${$("admin-manage").querySelector("a").href}`;
function readAdminRequests() {
  return parseRequests(localStorage.getItem(adminStorageKey));
}
function renderAdminRequests(requests) {
  $("admin-requests").replaceChildren();
  $("admin-requests-empty").hidden = requests === null || requests.length > 0;
  if (!requests?.length) return;
  const overview = table(["Team", "GitHub project", "Status", "Action"], requests.map(request => {
    const project = document.createElement("a");
    project.className = "govuk-link";
    project.href = request.project;
    project.textContent = request.project;
    const review = document.createElement("button");
    review.type = "button";
    review.className = "flow-link-button";
    review.textContent = "Review request";
    review.dataset.requestId = request.id;
    review.setAttribute("aria-haspopup", "dialog");
    review.setAttribute("aria-controls", "admin-dialog");
    review.setAttribute("aria-label", `Review request for ${request.team}`);
    review.addEventListener("click", () => {
      $("admin-request-team").textContent = request.team;
      $("admin-request-project").textContent = request.project;
      $("admin-request-project").href = request.project;
      openAdminPanel("admin-request", review, "admin-dialog-title", request.team);
    });
    return [request.team, project, "Awaiting review", review];
  }), "Onboarding requests");
  overview.classList.add("flow-admin-table");
  [...overview.tBodies[0].rows].forEach(row => {
    [...row.cells].forEach((cell, i) => { cell.dataset.label = ["Team", "GitHub project", "Status", "Action"][i]; });
  });
  $("admin-requests").append(overview);
}
function loadAdminRequests() {
  try {
    renderAdminRequests(readAdminRequests());
    $("admin-storage-error").hidden = true;
  } catch {
    renderAdminRequests(null);
    $("admin-storage-error").textContent = "Requests could not be loaded from this browser. Existing storage has not been changed. Enable browser storage or correct stored data, then reload.";
    $("admin-storage-error").hidden = false;
  }
}
function closeAdminPanel(returnFocus = true) {
  $("admin-dialog").close();
  ["admin-manage", "admin-setup", "admin-request"].forEach(id => { $(id).hidden = true; });
  if (returnFocus) {
    if (adminTrigger?.isConnected) adminTrigger.focus();
    else $("add-team-board").focus();
  }
}
function openAdminPanel(id, trigger, focus, title) {
  ["admin-manage", "admin-setup", "admin-request"].forEach(panel => { $(panel).hidden = panel !== id; });
  adminTrigger = trigger;
  $("admin-dialog-title").textContent = title;
  if (!$("admin-dialog").open) $("admin-dialog").showModal();
  $("admin-dialog").querySelector(".flow-guide-content").scrollTop = 0;
  $(focus).focus();
}
function openTeamSetup(trigger, team = "") {
  $("admin-team-name").value = team;
  $("admin-project-url").value = "";
  $("admin-setup-form").hidden = false;
  $("admin-draft-review").hidden = true;
  $("admin-setup-error").hidden = true;
  $("admin-save-error").hidden = true;
  $("admin-project-url").removeAttribute("aria-invalid");
  $("admin-team-name").removeAttribute("aria-invalid");
  openAdminPanel("admin-setup", trigger, team ? "admin-project-url" : "admin-team-name", team ? `Set up ${team}` : "Add team board");
}
$("add-team-board").addEventListener("click", event => openTeamSetup(event.currentTarget));
$("manage-current-board").addEventListener("click", event => openAdminPanel("admin-manage", event.currentTarget, "admin-dialog-title", $("current-workspace-name").textContent));
document.querySelectorAll("[data-close-admin]").forEach(button => button.addEventListener("click", () => closeAdminPanel()));
$("close-admin-dialog").addEventListener("click", () => closeAdminPanel());
$("admin-dialog").addEventListener("cancel", event => {
  event.preventDefault();
  closeAdminPanel();
});
$("admin-dialog").addEventListener("keydown", event => {
  if (event.key !== "Tab") return;
  const controls = [...$("admin-dialog").querySelectorAll('button, input, a[href], [tabindex="0"]')]
    .filter(control => control.getClientRects().length && !control.disabled);
  const first = controls[0], last = controls.at(-1);
  if (event.shiftKey && (document.activeElement === first || !controls.includes(document.activeElement))) {
    event.preventDefault(); last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault(); first.focus();
  }
});
$("admin-open-workspace").addEventListener("click", () => {
  closeAdminPanel(false);
  activateTab(0);
  $("team-tab").focus();
});
$("admin-setup-form").addEventListener("submit", event => {
  event.preventDefault();
  let details;
  try {
    details = requestDetails($("admin-team-name").value, $("admin-project-url").value);
  } catch (error) {
    $("admin-setup-error").textContent = error.message;
    $("admin-setup-error").hidden = false;
    const control = !$("admin-team-name").value.trim() ? $("admin-team-name") : $("admin-project-url");
    control.setAttribute("aria-invalid", "true");
    control.focus();
    return;
  }
  $("admin-setup-error").hidden = true;
  $("admin-team-name").removeAttribute("aria-invalid");
  $("admin-project-url").removeAttribute("aria-invalid");
  $("admin-draft-team").textContent = details.team;
  $("admin-draft-project").textContent = details.project;
  $("admin-setup-form").hidden = true;
  $("admin-draft-review").hidden = false;
  $("admin-draft-title").focus();
});
$("admin-edit-draft").addEventListener("click", () => {
  $("admin-draft-review").hidden = true;
  $("admin-setup-form").hidden = false;
  $("admin-team-name").focus();
});
$("admin-save-request").addEventListener("click", () => {
  try {
    const details = requestDetails($("admin-team-name").value, $("admin-project-url").value);
    const requests = readAdminRequests();
    const duplicate = requests.some(request => requestKey(request) === requestKey(details));
    if (!duplicate) {
      if (requests.length >= REQUEST_LIMIT) throw new Error("This browser supports up to 100 requests.");
      requests.push({ id: crypto.randomUUID(), ...details });
      localStorage.setItem(adminStorageKey, JSON.stringify({ version: REQUEST_VERSION, requests }));
    }
    renderAdminRequests(requests);
    $("admin-storage-error").hidden = true;
    $("admin-request-feedback").textContent = duplicate
      ? "This request is already saved in this browser."
      : "Request saved in this browser. No board connected.";
    closeAdminPanel();
  } catch {
    $("admin-save-error").textContent = "Request could not be saved in this browser. Existing storage has not been changed. Check browser storage and try again.";
    $("admin-save-error").hidden = false;
  }
});
window.addEventListener("storage", event => {
  if (event.key === adminStorageKey || event.key === null) loadAdminRequests();
});
loadAdminRequests();
$("toggle-charts").addEventListener("click", () => {
  const collapsed = !$("chart-sidebar").hidden;
  $("chart-sidebar").hidden = collapsed;
  $("toggle-charts").setAttribute("aria-expanded", String(!collapsed));
  const label = collapsed ? "Show charts" : "Hide charts";
  $("toggle-charts").setAttribute("aria-label", label);
  $("toggle-charts-label").textContent = collapsed ? "Show charts" : "Hide";
  $("toggle-charts").closest(".flow-workspace").classList.toggle("flow-workspace--collapsed", collapsed);
  if (chart) chart.resize();
});
document.addEventListener("click", (event) => {
  document.querySelectorAll(".flow-chart-menu[open]").forEach((menu) => {
    if (!menu.contains(event.target)) menu.open = false;
  });
});
function activateTab(index) {
  $("open-guide").hidden = index !== 0;
  tabs.forEach((tab, i) => {
    tab.setAttribute("aria-selected", String(i === index));
    tab.tabIndex = i === index ? 0 : -1;
    $(tab.getAttribute("aria-controls")).hidden = i !== index;
  });
  if (index === 0 && chart) chart.resize();
  updateWorkspaceURL(index === 1 ? "admin" : "team");
}
activateTab(new URL(window.location.href).searchParams.get("view") === "admin" ? 1 : 0);
tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => activateTab(index));
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? 1 : 1 - index;
    activateTab(next);
    tabs[next].focus();
  });
});
window.addEventListener("beforeunload", (event) => {
  if (dirty()) { event.preventDefault(); event.returnValue = ""; }
});
