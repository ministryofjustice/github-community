// Instant filtering for the archived repositories page. Without JavaScript the form submits
// and the server hides rows that don't match, so this script only enhances that behaviour.
(function () {
  "use strict";

  var DEBOUNCE_MS = 200;
  var PAGE_SIZE = 25;
  var FILTER_PARAMS = ["org", "business_unit", "q", "only_public"];
  var ALL_ORGANISATIONS = "all";

  function init() {
    var form = document.getElementById("visibility-filters");
    var table = document.getElementById("archived-table");
    var tableRegion = document.getElementById("archived-table-region");
    var noMatch = document.getElementById("archived-no-match");
    var allInternal = document.getElementById("archived-all-internal");
    var count = document.getElementById("archived-count");
    var status = document.getElementById("archived-filter-status");
    var clear = document.getElementById("clear-filters");
    var showing = document.getElementById("archived-showing");
    var pagination = document.getElementById("archived-pagination");
    var freshnessElement = document.getElementById("archived-freshness");
    var lastUpdated = document.getElementById("archived-last-updated");
    if (!form || !noMatch || !allInternal || !status) return;

    var org = form.querySelector("#org");
    var businessUnit = form.querySelector("#business_unit");
    var name = form.querySelector("#q");
    var onlyPublic = form.querySelector('input[type="checkbox"][name="only_public"]');
    if (!org || !businessUnit || !name || !onlyPublic) return;

    var freshness = freshnessElement
      ? JSON.parse(freshnessElement.getAttribute("data-organisations") || "{}")
      : {};
    var freshnessOrg = null;
    var progressElement = document.getElementById("archived-progress");
    var progress = progressElement
      ? JSON.parse(progressElement.getAttribute("data-progress") || "{}")
      : {};
    var progressOrg = null;
    var currentPage = pagination
      ? parseInt(pagination.getAttribute("data-page"), 10) || 1
      : 1;
    var rows = table ? Array.prototype.slice.call(table.tBodies[0].rows) : [];
    rows.forEach(function (row) {
      try {
        row.businessUnits = JSON.parse(row.getAttribute("data-business-units") || "[]");
      } catch (e) {
        row.businessUnits = [];
      }
    });

    function state() {
      return {
        org: org.value,
        businessUnit: businessUnit.value,
        q: name.value.trim().toLowerCase(),
        onlyPublic: onlyPublic.checked
      };
    }

    function matches(row, s) {
      if (s.org && s.org !== ALL_ORGANISATIONS && row.getAttribute("data-org") !== s.org) return false;
      if (s.businessUnit && row.businessUnits.indexOf(s.businessUnit) === -1) return false;
      return !s.q || (row.getAttribute("data-name") || "").indexOf(s.q) !== -1;
    }

    function updateUrl(pushHistory, hash) {
      if (!window.history || !window.history.replaceState) return;
      var params = new URLSearchParams(window.location.search);
      FILTER_PARAMS.forEach(function (key) { params.delete(key); });
      params.delete("page");
      if (org.value) params.set("org", org.value);
      if (businessUnit.value) params.set("business_unit", businessUnit.value);
      if (name.value.trim()) params.set("q", name.value.trim());
      if (!onlyPublic.checked) params.set("only_public", "0");
      if (currentPage > 1) params.set("page", String(currentPage));
      var search = params.toString();
      var url =
        window.location.pathname +
        (search ? "?" + search : "") +
        (hash === undefined ? window.location.hash : hash);
      var method = pushHistory ? "pushState" : "replaceState";
      window.history[method](
        window.history.state,
        "",
        url
      );
    }

    function pageNumbers(totalPages) {
      var shown = [1, totalPages];
      for (var number = currentPage - 2; number <= currentPage + 2; number += 1) {
        if (number >= 1 && number <= totalPages) shown.push(number);
      }
      shown.sort(function (a, b) { return a - b; });
      var unique = shown.filter(function (number, index) {
        return index === 0 || number !== shown[index - 1];
      });
      var result = [];
      var previous = 0;
      unique.forEach(function (number) {
        if (number - previous > 1) result.push(null);
        result.push(number);
        previous = number;
      });
      return result;
    }

    function pageHref(page) {
      var params = new URLSearchParams(window.location.search);
      FILTER_PARAMS.forEach(function (key) { params.delete(key); });
      params.delete("page");
      if (org.value) params.set("org", org.value);
      if (businessUnit.value) params.set("business_unit", businessUnit.value);
      if (name.value.trim()) params.set("q", name.value.trim());
      if (!onlyPublic.checked) params.set("only_public", "0");
      if (page > 1) params.set("page", String(page));
      var search = params.toString();
      return window.location.pathname + (search ? "?" + search : "") + "#archived-table";
    }

    function syncPaginationHrefs() {
      if (!pagination) return;
      pagination.querySelectorAll("a[data-page]").forEach(function (link) {
        link.href = pageHref(parseInt(link.getAttribute("data-page"), 10) || 1);
      });
    }

    function addPageLink(parent, page, label, options) {
      var wrapper = document.createElement(options.wrapperTag || "li");
      wrapper.className = options.wrapperClass;
      var link = document.createElement("a");
      link.className = "govuk-link govuk-pagination__link";
      link.href = pageHref(page);
      link.setAttribute("data-page", String(page));
      if (options.rel) link.setAttribute("rel", options.rel);
      if (options.current) {
        link.setAttribute("aria-current", "page");
        link.setAttribute("aria-label", "Page " + page);
      } else if (options.ariaLabel) {
        link.setAttribute("aria-label", options.ariaLabel);
      }
      link.textContent = label;
      wrapper.appendChild(link);
      parent.appendChild(wrapper);
    }

    function renderPagination(totalItems) {
      if (showing) {
        showing.hidden = totalItems === 0;
        if (totalItems) {
          var first = (currentPage - 1) * PAGE_SIZE + 1;
          var last = Math.min(currentPage * PAGE_SIZE, totalItems);
          showing.textContent = "Showing " + first + " to " + last + " of " + totalItems;
        }
      }
      if (!pagination) return;

      while (pagination.firstChild) pagination.removeChild(pagination.firstChild);
      var totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE));
      pagination.setAttribute("data-page", String(currentPage));
      pagination.hidden = totalPages <= 1;
      if (totalPages <= 1) return;

      var navigation = document.createElement("nav");
      navigation.className = "govuk-pagination";
      navigation.setAttribute("aria-label", "Archived repository pages");
      pagination.appendChild(navigation);

      if (currentPage > 1) {
        addPageLink(navigation, currentPage - 1, "Previous", {
          wrapperTag: "div",
          wrapperClass: "govuk-pagination__prev",
          rel: "prev",
          ariaLabel: "Previous page"
        });
      }

      var list = document.createElement("ul");
      list.className = "govuk-pagination__list";
      pageNumbers(totalPages).forEach(function (number) {
        if (number === null) {
          var item = document.createElement("li");
          item.className = "govuk-pagination__item govuk-pagination__item--ellipses";
          item.textContent = "…";
          list.appendChild(item);
        } else {
          var itemClass = "govuk-pagination__item";
          if (number === currentPage) itemClass += " govuk-pagination__item--current";
          addPageLink(list, number, String(number), {
            wrapperTag: "li",
            wrapperClass: itemClass,
            current: number === currentPage
          });
        }
      });
      navigation.appendChild(list);

      if (currentPage < totalPages) {
        addPageLink(navigation, currentPage + 1, "Next", {
          wrapperTag: "div",
          wrapperClass: "govuk-pagination__next",
          rel: "next",
          ariaLabel: "Next page"
        });
      }
    }

    function updateFreshness(selectedOrg) {
      if (freshnessOrg === selectedOrg) return;
      freshnessOrg = selectedOrg;
      var details = freshness[selectedOrg];
      if (lastUpdated) {
        lastUpdated.textContent = "";
        if (details && details.last_updated) {
          var updateLine = document.createElement("p");
          var time = document.createElement("em");
          updateLine.className = "govuk-body-s";
          updateLine.appendChild(document.createTextNode("Last updated: " + details.last_updated[0] + " at "));
          time.textContent = details.last_updated[1];
          updateLine.appendChild(time);
          lastUpdated.appendChild(updateLine);
        }
      }
    }

    function setText(id, text) {
      var element = document.getElementById(id);
      if (element) element.textContent = text;
    }

    function updateProgress(selectedOrg) {
      if (!progressElement || progressOrg === selectedOrg) return;
      progressOrg = selectedOrg;
      var details = progress[selectedOrg || ALL_ORGANISATIONS] || { total: 0, made_internal: 0, percent: 0 };
      var summary = document.getElementById("archived-progress-summary");
      var empty = document.getElementById("archived-progress-empty");
      var bar = document.getElementById("archived-progress-bar");
      var option = org.options[org.selectedIndex];
      setText("archived-progress-organisation", option ? option.text : "All organisations");
      setText(
        "archived-progress-text",
        details.made_internal + " of " + details.total + " archived public repositories have been made internal"
      );
      setText("archived-progress-percent", details.percent + "% complete");
      if (bar) bar.style.width = details.percent + "%";
      if (summary) summary.hidden = !details.total;
      if (empty) empty.hidden = !!details.total;
    }

    function apply(announce, historyMode) {
      var s = state();
      updateFreshness(s.org);
      updateProgress(s.org);
      var matchingRows = [];
      var shownRows = [];
      rows.forEach(function (row) {
        if (matches(row, s)) {
          matchingRows.push(row);
          if (!s.onlyPublic || row.getAttribute("data-visibility") === "public") {
            shownRows.push(row);
          }
        }
      });
      var totalPages = Math.max(1, Math.ceil(shownRows.length / PAGE_SIZE));
      currentPage = Math.min(Math.max(currentPage, 1), totalPages);
      var firstIndex = (currentPage - 1) * PAGE_SIZE;
      var pageRows = shownRows.slice(firstIndex, firstIndex + PAGE_SIZE);
      rows.forEach(function (row) {
        row.hidden = pageRows.indexOf(row) === -1;
      });
      if (table) table.hidden = pageRows.length === 0;
      if (tableRegion) tableRegion.hidden = pageRows.length === 0;
      if (count) count.textContent = String(shownRows.length);
      noMatch.hidden = matchingRows.length !== 0;
      allInternal.hidden = matchingRows.length === 0 || shownRows.length !== 0;
      if (announce) {
        if (shownRows.length) {
          var first = (currentPage - 1) * PAGE_SIZE + 1;
          var last = Math.min(currentPage * PAGE_SIZE, shownRows.length);
          status.textContent =
            "Showing " + first + " to " + last + " of " + shownRows.length + " repositories";
        } else {
          status.textContent = "No repositories shown";
        }
        if (historyMode !== false) updateUrl(!!historyMode);
      }
      renderPagination(shownRows.length);
    }

    var timer = null;
    function onType() {
      window.clearTimeout(timer);
      currentPage = 1;
      syncPaginationHrefs();
      timer = window.setTimeout(function () { apply(true); }, DEBOUNCE_MS);
    }

    form.classList.add("app-visibility-filters--live");
    [org, businessUnit, onlyPublic].forEach(function (field) {
      field.addEventListener("change", function () {
        currentPage = 1;
        apply(true);
      });
    });
    name.addEventListener("input", onType);
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      window.clearTimeout(timer);
      currentPage = 1;
      apply(true);
    });
    if (clear) {
      clear.addEventListener("click", function (event) {
        event.preventDefault();
        window.clearTimeout(timer);
        org.value = form.getAttribute("data-default-org") || "";
        businessUnit.value = "";
        name.value = "";
        onlyPublic.checked = true;
        currentPage = 1;
        apply(true);
      });
    }

    if (pagination) {
      pagination.addEventListener("click", function (event) {
        if (
          event.defaultPrevented || event.button !== 0 ||
          event.ctrlKey || event.metaKey || event.shiftKey || event.altKey
        ) return;
        var link = event.target.closest("a[data-page]");
        if (
          !link || !pagination.contains(link) ||
          link.hasAttribute("target") || link.hasAttribute("download")
        ) return;
        event.preventDefault();
        currentPage = parseInt(link.getAttribute("data-page"), 10) || 1;
        apply(true, false);
        updateUrl(true, "#archived-table");
        var currentLink = pagination.querySelector('[aria-current="page"]');
        if (currentLink) currentLink.focus();
        if (tableRegion) tableRegion.scrollIntoView();
      });
    }

    function restoreFromUrl() {
      var params = new URLSearchParams(window.location.search);
      org.value = params.get("org") || form.getAttribute("data-default-org") || "";
      businessUnit.value = params.get("business_unit") || "";
      name.value = params.get("q") || "";
      // Same rule as the server: absent means checked, otherwise any "1" means checked.
      var onlyPublicValues = params.getAll("only_public");
      onlyPublic.checked =
        onlyPublicValues.length === 0 || onlyPublicValues.indexOf("1") !== -1;
      currentPage = parseInt(params.get("page") || "1", 10) || 1;
      apply(false);
    }
    window.addEventListener("popstate", restoreFromUrl);

    // Browsers can restore edited field values on back/forward, so match the table to them.
    apply(false);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
