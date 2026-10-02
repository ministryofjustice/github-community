# GitHub Repository Stats

## One-off import of the old visibility audit reports

`app/projects/repository_stats/jobs/import_visibility_audit_reports.py` loads the old
visibility audit spreadsheets into the Repository Stats tables:

- `list_repos_17aug2026.xlsx` (sheet `Repos`) becomes the baseline snapshot for 17 August 2026.
- `historical-YYYY-MM-DD.xlsx` and `Visibility-YYYY-MM-DD.xlsx` (sheet `Full Comparison`)
  each become a snapshot for their date.
- Differences between consecutive files become events (visibility changed, new
  repository, deleted repository) with source `import`. An event is dated to the first
  file that shows it, so dates between 24 August and 18 September 2026 are approximate
  (the Visibility changes page says so).

Any other file in the directory is ignored. Repositories are matched by full name, so a
rename shows as a delete and a create, and a change that was reversed between two files
isn't recorded. GitHub ids are looked up from the GitHub App's current list of the
organisation's repositories; repositories that no longer exist get a stable negative id.
Dates from the visibility job's first successful run onwards are left to that job.

The spreadsheets contain real repository names. This repository is public, so never
commit them (`*.xlsx` is in `.gitignore`).

The import is safe to re-run (it replaces its own earlier import) and all-or-nothing.
Avoid running it at the same time as the visibility job (04:00, and 13:00 in prod, UTC).

### Running it

Do dev first (`github-community-dev`), then prod (`github-community-prod`). The file
names below are placeholders.

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
