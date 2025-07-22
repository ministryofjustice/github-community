document.addEventListener("DOMContentLoaded", function () {
  const input = document.getElementById('name');
  const resultsContainer = document.getElementById('results-container');

  if (!input || !resultsContainer) return;

  input.addEventListener('input', async () => {
    const query = input.value.trim();
    if (query === "") return;

    const response = await fetch(`/acronyms/live-search?q=${encodeURIComponent(query)}`);
    const data = await response.json();

    let html = `
      <table class="govuk-table">
        <thead class="govuk-table__head">
          <tr class="govuk-table__row">
            <th class="govuk-table__header">Acronym</th>
            <th class="govuk-table__header">Definition</th>
            <th class="govuk-table__header">Description</th>
          </tr>
        </thead>
        <tbody class="govuk-table__body">
    `;

    for (const item of data) {
      html += `
        <tr class="govuk-table__row">
          <td class="govuk-table__cell">${item.abbreviation}</td>
          <td class="govuk-table__cell">${item.definition}</td>
          <td class="govuk-table__cell">${item.description}</td>
        </tr>
      `;
    }

    html += `</tbody></table>`;
    resultsContainer.innerHTML = html;
  });
});