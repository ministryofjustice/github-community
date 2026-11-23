(function () {
  "use strict";

  function bindSelects(form) {
    if (!form) return;
    form.addEventListener("change", function (event) {
      if (event.target.matches("select")) form.requestSubmit();
    });
  }

  var form = document.getElementById("visibility-filters");
  bindSelects(form);
  bindSelects(document.getElementById("visibility-activity-filters"));

  var name = form && form.querySelector("#q");
  var results = document.getElementById("visibility-results");
  var error = document.getElementById("visibility-search-error");
  var status = document.getElementById("visibility-search-status");
  var dateForm = document.getElementById("visibility-date-filters");
  var clearDates = document.getElementById("clear-dates");
  if (name && results && error && status && dateForm && clearDates) {
    var timer;
    var pending;
    var version = 0;
    name.addEventListener("input", function () {
      window.clearTimeout(timer);
      if (pending) pending.abort();
      var current = ++version;
      error.hidden = true;
      status.textContent = "";
      timer = window.setTimeout(function () {
        var url = new URL(form.action, window.location.href);
        url.search = new URLSearchParams(new FormData(form)).toString();
        pending = new AbortController();
        fetch(url, { signal: pending.signal }).then(function (response) {
          if (current !== version) return null;
          if (response.redirected) {
            window.location.assign(response.url);
            return null;
          }
          if (!response.ok) throw new Error("Search request failed");
          return response.text();
        }).then(function (html) {
          if (html === null || current !== version) return;
          var page = new DOMParser().parseFromString(html, "text/html");
          var updated = page.getElementById("visibility-results");
          var updatedClear = page.getElementById("clear-dates");
          if (!updated || !updatedClear) throw new Error("Search response is incomplete");
          results.innerHTML = updated.innerHTML;
          dateForm.querySelector('input[name="q"]').value = name.value;
          clearDates.href = updatedClear.href;
          bindSelects(document.getElementById("visibility-activity-filters"));
          window.history.replaceState(window.history.state, "", url);
          status.textContent = "Results updated";
        }).catch(function (failure) {
          if (current !== version || failure.name === "AbortError") return;
          error.hidden = false;
        });
      }, 200);
    });
  }

  document.querySelectorAll(".app-date-picker").forEach(function (picker) {
    var input = picker.querySelector('input[type="date"]');
    var button = picker.querySelector(".app-date-picker__button");
    if (!input || !button || typeof input.showPicker !== "function") return;

    var control = document.createElement("div");
    control.className = "app-date-picker__control";
    input.before(control);
    control.append(input, button);
    button.hidden = false;
    button.addEventListener("click", function () {
      input.focus();
      input.showPicker();
    });
  });
})();
