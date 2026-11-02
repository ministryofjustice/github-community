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
    click, findPage, historyCalls, name, onlyPublic, pagination, rows, showing, tableRegion
  };
}

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
