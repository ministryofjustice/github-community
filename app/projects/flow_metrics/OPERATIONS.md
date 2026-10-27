# Flow Metrics operations

DEV uses combined exploration (`FLOW_METRICS_DATA_MODE=sample`): labelled
fictional events and genuine observations, selectable through the Source filter.
Keep the sample dataset and charts until a later phase.
The workspace loads one genuine observation at the selected reporting cutoff;
saved captures remain intact. Enable the UI explicitly with
`FLOW_METRICS_ENABLED=true` for local use; disabled deployments hide it.

## Collection

Automatic DEV capture is enabled by these values **after deployment**. The schedule is
09:30, 11:30, 13:30, 15:30 and 17:30 on weekdays, in `Europe/London` time.
Snapshots record observations, not the transitions between them.

Use the normal deployment process to change
`app.jobs.flow_metrics_reconcile.enabled` in DEV values (`true` to enable,
`false` to disable). Collection records genuine observations regardless of the
combined workspace display mode.
Each collector initializes the real board if needed, without replacing charts.
Disabling the CronJob does not stop existing Jobs or prevent manual CLI captures.
Check for running Jobs when disabling; keep all saved data and charts.

## Check a run

```sh
kubectl --context <context> -n <namespace> get cronjobs,jobs
kubectl --context <context> -n <namespace> logs job/<job-name>
```

**Last updated** is the latest successful observation. Admin's **Last run** is
the latest recorded collection attempt; imports do not create run records.
Check Kubernetes for missed, failed-start or killed Jobs that the app cannot
reliably report.

## Import saved captures

Keep private archives and credentials outside Git. Back up the target database,
review the captures, then run the [existing importer](archive_import.py):

```sh
python3 -m flask --app app.app flow-metrics import-archives \
  /private/archive --since YYYY-MM-DD --dry-run
```

Check the result, then repeat without `--dry-run` only after approval.
Preserve original timestamps, existing charts and both datasets. Do not enable
collection to import archives.

Webhook receiver and processor wiring is deferred to Phase 3. Stored inbox
tables and evidence are retained.
