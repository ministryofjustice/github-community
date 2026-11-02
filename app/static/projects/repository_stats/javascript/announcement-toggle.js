// Adds a Show/Hide button to the archived page announcement. The deadline has passed, so
// the message starts collapsed; the choice applies only to the current page view.
// Without JavaScript the message always shows.
(function () {
  "use strict";

  function init() {
    var banner = document.getElementById("archived-announcement");
    if (!banner) return;
    var header = banner.querySelector(".app-announcement__header");
    var content = document.getElementById("archived-announcement-content");
    if (!header || !content) return;

    var button = document.createElement("button");
    button.type = "button";
    button.className = "app-announcement__toggle";
    button.setAttribute("aria-controls", content.id);

    var chevron = document.createElement("span");
    chevron.className = "app-announcement__chevron";
    chevron.setAttribute("aria-hidden", "true");
    var label = document.createElement("span");
    var hiddenLabel = document.createElement("span");
    hiddenLabel.className = "govuk-visually-hidden";
    hiddenLabel.textContent = " announcement";
    button.appendChild(chevron);
    button.appendChild(label);
    button.appendChild(hiddenLabel);

    function render(hidden) {
      content.hidden = hidden;
      banner.classList.toggle("app-announcement--collapsed", hidden);
      button.setAttribute("aria-expanded", hidden ? "false" : "true");
      label.textContent = hidden ? "Show" : "Hide";
    }

    button.addEventListener("click", function () {
      render(!content.hidden);
    });

    render(true);
    header.appendChild(button);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
