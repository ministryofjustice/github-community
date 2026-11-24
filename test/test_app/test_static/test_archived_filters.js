const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(
  path.join(
    __dirname,
    "../../../app/static/projects/repository_stats/javascript/archived-filters.js"
  ),
  "utf8"
);
const visibilityScript = fs.readFileSync(
  path.join(
    __dirname,
    "../../../app/static/projects/repository_stats/javascript/visibility-filters.js"
  ),
  "utf8"
);
const announcementScript = fs.readFileSync(
  path.join(__dirname, "../../../app/static/projects/repository_stats/javascript/announcement-toggle.js"),
  "utf8"
);

function element(tagName, attributes = {}) {
  const node = {
    tagName: tagName.toUpperCase(),
    attributes: { ...attributes },
    children: [],
    listeners: {},
    parentNode: null,
    hidden: false,
    classList: { add() {} },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    getAttribute(name) { return this.attributes[name] ?? null; },
    hasAttribute(name) { return Object.hasOwn(this.attributes, name); },
    appendChild(child) {
      child.parentNode = this;
      this.children.push(child);
      return child;
    },
    removeChild(child) {
      this.children.splice(this.children.indexOf(child), 1);
      child.parentNode = null;
    },
    addEventListener(type, callback) { this.listeners[type] = callback; },
    contains(child) {
      for (let current = child; current; current = current.parentNode) {
        if (current === this) return true;
      }
      return false;
    },
    closest(selector) {
      if (selector === "a[data-page]" && this.tagName === "A" && this.hasAttribute("data-page")) {
        return this;
      }
      return this.parentNode ? this.parentNode.closest(selector) : null;
    },
    querySelector(selector) {
      return this.children.flatMap(function find(child) {
        if (selector === '[aria-current="page"]' && child.getAttribute("aria-current") === "page") {
          return [child];
        }
        return child.children.flatMap(find);
      })[0] || null;
    },
    querySelectorAll(selector) {
      return this.children.flatMap(function find(child) {
        const matches = selector === "a[data-page]" &&
          child.tagName === "A" && child.hasAttribute("data-page");
        return (matches ? [child] : []).concat(child.children.flatMap(find));
      });
    },
    focus() { this.focused = true; },
    scrollIntoView() { this.scrolled = true; }
  };
  Object.defineProperty(node, "firstChild", {
    get() { return this.children[0] || null; }
  });
  return node;
}

function fixture() {
  const form = element("form", { "data-default-org": "ministryofjustice" });
  const org = element("select");
  org.value = "ministryofjustice";
  org.options = [{ text: "Ministry of Justice" }];
  org.selectedIndex = 0;
  const businessUnit = element("select");
  businessUnit.value = "Unit A";
  const name = element("input");
  name.value = "repo";
  const onlyPublic = element("input");
  onlyPublic.checked = true;
  form.querySelector = (selector) => ({
    "#org": org,
    "#business_unit": businessUnit,
    "#q": name,
    'input[type="checkbox"][name="only_public"]': onlyPublic
  })[selector] || null;

  const rows = Array.from({ length: 30 }, (_, index) =>
    element("tr", {
      "data-org": "ministryofjustice",
      "data-business-units": '["Unit A"]',
      "data-name": "repo-" + index,
      "data-visibility": "public"
    })
  );
  const table = element("table");
  table.tBodies = [{ rows }];
  const sortLink = element("a", { "data-sort": "archived", "data-direction": "asc" });
  table.querySelectorAll = (selector) => selector === "a[data-sort]" ? [sortLink] : [];
  const pagination = element("div", { "data-page": "1" });
  const tableRegion = element("div");
  const showing = element("p");
  const nodes = {
    "visibility-filters": form,
    "archived-table": table,
    "archived-table-region": tableRegion,
    "archived-no-match": element("div"),
    "archived-all-internal": element("div"),
    "archived-count": element("span"),
    "archived-filter-status": element("p"),
    "archived-showing": showing,
    "archived-pagination": pagination
  };
  const location = {
    pathname: "/repository-stats/archived",
    search: "?org=ministryofjustice&business_unit=Unit+A&q=repo",
    hash: ""
  };
  const historyCalls = [];
  function updateHistory(method, url) {
    historyCalls.push({ method, url });
    const parsed = new URL(url, "http://example.test");
    location.pathname = parsed.pathname;
    location.search = parsed.search;
    location.hash = parsed.hash;
  }
  const window = {
    location,
    history: {
      state: null,
      pushState(_state, _title, url) { updateHistory("push", url); },
      replaceState(_state, _title, url) { updateHistory("replace", url); }
    },
    addEventListener() {},
    clearTimeout() {},
    setTimeout() {}
  };
  const document = {
    readyState: "complete",
    getElementById(id) { return nodes[id] || null; },
    createElement(tagName) { return element(tagName); },
    createTextNode(text) { return { textContent: text, parentNode: null }; }
  };
  vm.runInNewContext(script, { document, window, URLSearchParams });

  function findPage(page) {
    function find(node) {
      if (node.tagName === "A" && node.getAttribute("data-page") === String(page)) {
        return node;
      }
      return node.children.map(find).find(Boolean);
    }
    return find(pagination);
  }

  function click(options = {}) {
    const link = findPage(2);
    assert.ok(link);
    if (options.linkTarget) link.setAttribute("target", options.linkTarget);
    if (options.download) link.setAttribute("download", "");
    const event = {
      target: link,
      button: 0,
      defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; },
      ...options
    };
    pagination.listeners.click(event);
    return { event, link };
  }

  return {
    click, findPage, historyCalls, name, onlyPublic, pagination, rows, showing, sortLink, tableRegion
  };
}

test("sort links retain live filters even during the search debounce", () => {
  const page = fixture();
  page.name.value = "new search";
  page.onlyPublic.checked = false;
  page.name.listeners.input();
  const url = new URL(page.sortLink.href, "http://example.test");
  assert.equal(url.searchParams.get("q"), "new search");
  assert.equal(url.searchParams.get("only_public"), "0");
  assert.equal(url.searchParams.get("sort"), "archived");
  assert.equal(url.searchParams.get("dir"), "asc");
  assert.equal(url.searchParams.has("page"), false);
});

test("an ordinary pagination click updates the page and keeps the filters", () => {
  const page = fixture();
  const { event, link } = page.click();

  assert.equal(event.defaultPrevented, true);
  assert.match(link.href, /org=ministryofjustice/);
  assert.match(link.href, /business_unit=Unit\+A/);
  assert.match(link.href, /q=repo/);
  assert.match(link.href, /page=2#archived-table$/);
  assert.equal(page.pagination.getAttribute("data-page"), "2");
  assert.equal(page.showing.textContent, "Showing 26 to 30 of 30");
  assert.equal(page.rows[0].hidden, true);
  assert.equal(page.rows[25].hidden, false);
  assert.equal(page.historyCalls.length, 1);
  assert.equal(page.historyCalls[0].method, "push");
  assert.equal(page.findPage(2).focused, true);
  assert.equal(page.tableRegion.scrolled, true);
});

test("a keyboard-activated pagination link updates the page", () => {
  const page = fixture();
  const { event } = page.click({ detail: 0 });
  assert.equal(event.defaultPrevented, true);
  assert.equal(page.pagination.getAttribute("data-page"), "2");
});

for (const [label, options] of [
  ["Ctrl-click", { ctrlKey: true }],
  ["Command-click", { metaKey: true }],
  ["Shift-click", { shiftKey: true }],
  ["Alt-click", { altKey: true }],
  ["middle-click", { button: 1 }],
  ["right-click", { button: 2 }],
  ["a link with a target", { linkTarget: "_blank" }],
  ["a download link", { download: true }]
]) {
  test(label + " is left to the browser", () => {
    const page = fixture();
    const { event } = page.click(options);
    assert.equal(event.defaultPrevented, false);
    assert.equal(page.pagination.getAttribute("data-page"), "1");
    assert.equal(page.historyCalls.length, 0);
    assert.equal(page.rows[0].hidden, false);
    assert.equal(page.rows[25].hidden, true);
  });
}

test("a modified click keeps recently changed filters in its link", () => {
  const page = fixture();
  page.onlyPublic.checked = false;
  page.onlyPublic.listeners.change();
  const previousHistoryCalls = page.historyCalls.length;
  const { event, link } = page.click({ metaKey: true });

  assert.equal(event.defaultPrevented, false);
  assert.match(link.href, /only_public=0/);
  assert.match(link.href, /page=2#archived-table$/);
  assert.equal(page.historyCalls.length, previousHistoryCalls);
  assert.equal(page.pagination.getAttribute("data-page"), "1");
});

test("a modified click during the search debounce uses the latest search text", () => {
  const page = fixture();
  page.name.value = "new-search";
  page.name.listeners.input();

  const { event, link } = page.click({ metaKey: true });

  assert.equal(event.defaultPrevented, false);
  assert.match(link.href, /q=new-search/);
  assert.doesNotMatch(link.href, /q=repo(?:&|$)/);
});

test("a click already prevented by another handler does not change the page", () => {
  const page = fixture();
  page.click({ defaultPrevented: true });
  assert.equal(page.pagination.getAttribute("data-page"), "1");
  assert.equal(page.historyCalls.length, 0);
});

test("visibility select changes submit their own form without applying dates", () => {
  const submitted = [];
  const ids = ["visibility-filters", "visibility-activity-filters", "visibility-date-filters"];
  const forms = Object.fromEntries(ids.map((id) => {
    const form = element("form");
    form.requestSubmit = () => submitted.push(id);
    return [id, form];
  }));
  vm.runInNewContext(visibilityScript, {
    document: { getElementById: (id) => forms[id], querySelectorAll: () => [] }
  });

  const event = (tagName) => ({ target: { matches: (selector) => selector === tagName } });
  forms[ids[0]].listeners.change(event("select"));
  forms[ids[1]].listeners.change(event("select"));
  forms[ids[0]].listeners.change(event("input"));

  assert.deepEqual(submitted, ids.slice(0, 2));
  assert.equal(forms[ids[2]].listeners.change, undefined);
});

test("visibility search updates results without applying draft dates and ignores stale responses", async () => {
  const name = element("input");
  name.value = "first";
  const form = element("form");
  form.action = "https://example.test/repository-stats/visibility";
  form.querySelector = () => name;
  const dateQuery = { value: "" };
  const dateForm = { querySelector: () => dateQuery };
  const activityQuery = { value: "" };
  const activityForm = element("form");
  activityForm.querySelector = () => activityQuery;
  const clearDates = { href: "https://example.test/visibility?q=old" };
  const sort = { href: "https://example.test/visibility?q=old&from=2026-08-05&sort=date#activity-table" };
  const pagination = { href: "https://example.test/visibility?q=old&from=2026-08-05&page=2#activity-table" };
  const csv = { href: "https://example.test/visibility/changes.csv?q=old&from=2026-08-05" };
  const results = { innerHTML: "initial", querySelectorAll: () => [sort, pagination, csv] };
  const error = { hidden: true };
  const status = { textContent: "" };
  const nodes = {
    "visibility-filters": form, "visibility-date-filters": dateForm,
    "visibility-activity-filters": activityForm,
    "visibility-results": results, "visibility-search-error": error,
    "visibility-search-status": status,
    "clear-dates": clearDates
  };
  const requests = [];
  let timer;
  let historyUrl;
  const document = {
    getElementById: (id) => nodes[id],
    querySelectorAll: () => []
  };
  const window = {
    location: { href: form.action },
    history: { replaceState(_state, _title, url) { historyUrl = url.toString(); } },
    clearTimeout() {},
    setTimeout(callback) { timer = callback; }
  };
  class FormData {
    constructor() { return [["q", name.value], ["from", "2026-08-05"]]; }
  }
  class DOMParser {
    parseFromString(html) {
      return { getElementById: (id) => id === "visibility-results"
        ? { innerHTML: html } : { href: "/clear?q=" + html } };
    }
  }
  vm.runInNewContext(visibilityScript, {
    document, window, URL, URLSearchParams, FormData, DOMParser, AbortController,
    fetch(url, options) {
      return new Promise((resolve, reject) => requests.push({ url, options, resolve, reject }));
    }
  });
  name.listeners.input();
  function assertQuery(expected) {
    assert.equal(dateQuery.value, expected);
    assert.equal(activityQuery.value, expected);
    for (const link of [clearDates, sort, pagination, csv]) {
      assert.equal(new URL(link.href).searchParams.get("q"), expected || null);
    }
    for (const link of [sort, pagination, csv]) {
      assert.equal(new URL(link.href).searchParams.get("from"), "2026-08-05");
    }
  }
  assertQuery("first");
  timer();
  name.value = "second";
  name.listeners.input();
  assert.equal(requests[0].options.signal.aborted, true);
  assertQuery("second");
  timer();
  assert.equal(requests[1].url.searchParams.get("from"), "2026-08-05");
  assert.equal(requests[1].url.searchParams.get("q"), "second");
  requests[1].resolve({ ok: true, text: () => Promise.resolve("second") });
  await new Promise(setImmediate);
  requests[0].resolve({ ok: true, text: () => Promise.resolve("first") });
  await new Promise(setImmediate);
  assert.equal(results.innerHTML, "second");
  assertQuery("second");
  assert.equal(status.textContent, "Results updated");
  assert.match(historyUrl, /q=second/);
  name.value = "third";
  name.listeners.input();
  timer();
  requests[2].reject(new Error("network"));
  await new Promise(setImmediate);
  assert.equal(error.hidden, false);
  assert.equal(results.innerHTML, "second");
  assertQuery("third");
  name.value = "";
  name.listeners.input();
  assertQuery("");
});

test("visibility calendar enhancement requires the native picker API", () => {
  for (const supported of [true, false]) {
    let opened = false;
    const input = {
      before() {},
      focus() {},
      showPicker: supported ? () => { opened = true; } : undefined
    };
    const button = element("button");
    button.hidden = true;
    const picker = { querySelector: (selector) => selector.startsWith("input") ? input : button };
    vm.runInNewContext(visibilityScript, {
      document: {
        getElementById: () => null,
        querySelectorAll: () => [picker],
        createElement: () => ({ append() {} })
      }
    });

    assert.equal(button.hidden, !supported);
    button.listeners.click?.();
    assert.equal(opened, supported);
  }
});

test("announcement starts collapsed and toggles accessibly", () => {
  const classes = new Set();
  const html = { classList: {
    add: (value) => classes.add(value),
    remove: (value) => classes.delete(value)
  } };
  const header = element("div");
  const banner = element("div");
  banner.classList.toggle = () => {};
  banner.querySelector = () => header;
  const content = element("div");
  content.id = "archived-announcement-content";
  let ready;
  const document = {
    readyState: "loading",
    documentElement: html,
    addEventListener(_type, callback) { ready = callback; },
    getElementById: (id) => id === "archived-announcement" ? banner : content,
    createElement: (tag) => element(tag)
  };
  vm.runInNewContext(announcementScript, { document });
  assert.equal(classes.has("app-announcement-pending"), true);
  ready();
  assert.equal(classes.has("app-announcement-pending"), false);
  const button = header.children[0];
  assert.equal(content.hidden, true);
  assert.equal(button.getAttribute("aria-controls"), content.id);
  assert.equal(button.getAttribute("aria-expanded"), "false");
  assert.equal(button.children[0].textContent, "Show");
  button.listeners.click();
  assert.equal(content.hidden, false);
  assert.equal(button.getAttribute("aria-expanded"), "true");
  assert.equal(button.children[0].textContent, "Hide");
  button.listeners.click();
  assert.equal(content.hidden, true);
  assert.equal(button.getAttribute("aria-expanded"), "false");
});
