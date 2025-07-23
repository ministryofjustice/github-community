document.addEventListener("DOMContentLoaded", function () {
  const input = document.getElementById('name');
  const resultsContainer = document.getElementById('results-container');

  if (!input || !resultsContainer) return;

  input.addEventListener('input', async () => {
    const query = input.value.trim();
    const rows = resultsContainer.querySelectorAll('tbody tr');

    rows.forEach(row => {
      const text = row.textContent.trim();
      
      if (text.includes(query)) {
        row.style.display = '';
      } else {
        row.style.display = 'none';
      }
    });
  });
});