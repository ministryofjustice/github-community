(function () {
  "use strict";

  function initDatePickers() {
    Array.prototype.forEach.call(
      document.querySelectorAll(".app-date-picker"),
      function (picker) {
        var input = picker.querySelector('input[type="date"]');
        var button = picker.querySelector(".app-date-picker__button");
        if (!input || !button || !input.parentNode) return;

        var control = document.createElement("div");
        control.className = "app-date-picker__control";
        input.parentNode.insertBefore(control, input);
        control.appendChild(input);
        control.appendChild(button);
        button.hidden = false;
        button.addEventListener("click", function () {
          input.focus();
          if (typeof input.showPicker === "function") {
            input.showPicker();
          } else {
            input.click();
          }
        });
      }
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initDatePickers);
  } else {
    initDatePickers();
  }
})();
