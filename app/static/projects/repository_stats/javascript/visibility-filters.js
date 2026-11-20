(function () {
  "use strict";

  ["visibility-filters", "visibility-activity-filters"].forEach(function (id) {
    var form = document.getElementById(id);
    if (!form) return;

    form.addEventListener("change", function (event) {
      if (event.target.matches("select")) form.requestSubmit();
    });
  });

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
