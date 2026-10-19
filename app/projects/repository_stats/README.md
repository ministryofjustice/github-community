# GitHub Repository Stats

Reports on repository visibility across the MOJ organisations.

Access is limited to the configured GitHub team.

## Pages

- **Repository overview** shows repository totals by organisation, business unit and
  team, including public, internal and private repositories. Organisation totals count
  each repository once; where an existing mapping assigns a repository to multiple
  business units, it appears under each of those units.
- **Repository visibility changes** shows visibility changes, new repositories and
  deleted repositories since 17 August 2026. The page supports filters and CSV export.
- **Archived public repositories** lists archived public repositories, with the configured
  deadline to change their visibility to internal.

## Data collection

The `record_repository_visibility` job saves a visibility snapshot and compares it with
the latest prior snapshot to record visibility changes, repository creation and deletion
events. If there is no earlier snapshot, that first snapshot is the baseline and creates
no comparison events. The historical baseline is 17 August 2026.

The job runs in Dev and Prod at 04:00 and 13:00 UTC. Each environment has a separate
database.

## One-off import of the old visibility audit reports

`app/projects/repository_stats/jobs/import_visibility_audit_reports.py` loads the old
visibility audit spreadsheets into the Repository Stats tables:

- `list_repos_17aug2026.xlsx` (sheet `Repos`) is the baseline snapshot for 17 August 2026.
- Each `Full Comparison` sheet in a `historical-YYYY-MM-DD.xlsx` or
  `Visibility-YYYY-MM-DD.xlsx` file is a snapshot for its date.
- Differences between consecutive snapshots become events with source `import`, dated
  to the first file that shows the change.

Other files are ignored. Repositories are matched by full name, so a rename appears as a
delete and a create. Changes reversed between files are not recorded. Repository IDs
come from the GitHub App's current repository list; repositories no longer present get
a stable negative ID. Dates from the visibility job's first successful run onwards are
left to that job.

The spreadsheets contain real repository names. This repository is public, so never
commit them (`*.xlsx` is in `.gitignore`).

The import is safe to re-run (it replaces its own earlier import) and all-or-nothing.
Avoid running it at the same time as the visibility job (04:00 and 13:00 UTC in both
Dev and Prod).

### Running it

Run it in Dev first (`github-community-dev`), then Prod (`github-community-prod`). The
file names below are placeholders.

```bash
NAMESPACE=github-community-dev
POD=$(kubectl -n "$NAMESPACE" get pods -o name | grep -v job | head -n 1 | cut -d/ -f2)

# 1. Copy the files into the pod
kubectl -n "$NAMESPACE" exec "$POD" -- mkdir -p /tmp/visibility-audit
for file in list_repos_17aug2026.xlsx historical-YYYY-MM-DD.xlsx Visibility-YYYY-MM-DD.xlsx; do
  kubectl -n "$NAMESPACE" cp "./$file" "$POD:/tmp/visibility-audit/$file"
done

# 2. Dry run: prints counts only and writes nothing
kubectl -n "$NAMESPACE" exec "$POD" -- \
  python3 -m app.projects.repository_stats.jobs.import_visibility_audit_reports /tmp/visibility-audit --dry-run

# 3. Import for real
kubectl -n "$NAMESPACE" exec "$POD" -- \
  python3 -m app.projects.repository_stats.jobs.import_visibility_audit_reports /tmp/visibility-audit

# 4. Delete the copied files
kubectl -n "$NAMESPACE" exec "$POD" -- rm -rf /tmp/visibility-audit
```
