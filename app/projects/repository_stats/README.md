# GitHub Repository Stats

Reports on repository visibility across configured GitHub organisations. The same
Repository Stats viewers team controls access to all organisations, pages and CSV
exports.

## Pages

- **Repository overview:** Totals by organisation, business unit, team and visibility.
  A repository mapped to multiple units appears under each but is counted once in its
  organisation's total.
- **Repository visibility changes:** Visibility changes, new and deleted repositories,
  with filters and CSV export.
- **Archived public repositories:** Archived public repositories, with progress for the
  selected organisation or all organisations. Other filters narrow only the list,
  which is paginated in groups of 25.

The visibility and archived pages open on Ministry of Justice. Choosing another
organisation, or All organisations, is kept in the URL.

## Baselines and collection

Each organisation's baseline is its earliest stored snapshot, including previously
imported history:

- **Ministry of Justice:** 17 August 2026.
- **MOJ Analytical Services:** 29 October 2026.

When an organisation has no earlier snapshots, its first successful development
collection with repository data establishes the baseline without comparison events.
Use the same baseline in production. The visibility page shows the selected
organisation's baseline; both pages show its last successful collection when available.

Organisations are saved independently: a failed scan retains that organisation's
previous data without discarding other successful scans. The overall collection fails if
any organisation fails. Team access and organisation names are collected on a
best-effort basis.

Configure organisations per environment with `REPOSITORY_STATS_ORGS`, a comma-separated
list of `organisation:installation_id` entries. The GitHub App needs appropriate access
to each organisation.
