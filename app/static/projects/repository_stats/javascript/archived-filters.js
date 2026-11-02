// Instant filtering for the archived repositories page. Without JavaScript the form submits
// and the server hides rows that don't match, so this script only enhances that behaviour.
(function () {
  "use strict";

  var DEBOUNCE_MS = 200;
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

    function updateUrl() {
      if (!window.history || !window.history.replaceState) return;
      var params = new URLSearchParams(window.location.search);
      FILTER_PARAMS.forEach(function (key) { params.delete(key); });
      if (org.value) params.set("org", org.value);
      if (businessUnit.value) params.set("business_unit", businessUnit.value);
      if (name.value.trim()) params.set("q", name.value.trim());
      if (!onlyPublic.checked) params.set("only_public", "0");
      var search = params.toString();
      window.history.replaceState(
        window.history.state,
        "",
        window.location.pathname + (search ? "?" + search : "") + window.location.hash
      );
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

    function apply(announce) {
      var s = state();
      updateFreshness(s.org);
      updateProgress(s.org);
      var matching = 0;
      var shown = 0;
      rows.forEach(function (row) {
        var visible = false;
        if (matches(row, s)) {
          matching += 1;
          visible = !s.onlyPublic || row.getAttribute("data-visibility") === "public";
        }
        row.hidden = !visible;
        if (visible) shown += 1;
      });
      if (table) table.hidden = shown === 0;
      if (tableRegion) tableRegion.hidden = shown === 0;
      if (count) count.textContent = String(shown);
      noMatch.hidden = matching !== 0;
      allInternal.hidden = matching === 0 || shown !== 0;
      if (announce) {
        status.textContent = shown + (shown === 1 ? " repository" : " repositories") + " shown";
        updateUrl();
      }
    }

    var timer = null;
    function onType() {
      window.clearTimeout(timer);
      timer = window.setTimeout(function () { apply(true); }, DEBOUNCE_MS);
    }

    form.classList.add("app-visibility-filters--live");
    [org, businessUnit, onlyPublic].forEach(function (field) {
      field.addEventListener("change", function () { apply(true); });
    });
    name.addEventListener("input", onType);
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      window.clearTimeout(timer);
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
        apply(true);
      });
    }

    // Browsers can restore edited field values on back/forward, so match the table to them.
    apply(false);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
