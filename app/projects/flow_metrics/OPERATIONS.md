# Running Flow Metrics captures

DEV captures the full project board at **09:30, 11:30, 13:30, 15:30 and 17:30,
Monday to Friday**, in `Europe/London` time. The schedule follows GMT/BST.
Each successful capture keeps an observation; it does not reconstruct changes
between captures.

## Deploy

Use the normal DEV deployment process. The schedule is enabled in DEV values:

```yaml
app:
  jobs:
    flow_metrics_reconcile:
      enabled: true
```

The job uses the existing database and GitHub App credentials. It only runs with
development values in the DEV namespace. Production collection is disabled.

## Check a run

Use your approved DEV context and namespace:

```sh
kubectl --context <context> -n <namespace> get cronjobs,jobs
kubectl --context <context> -n <namespace> logs job/<job-name>
```

Check that the Job completed, then reload Flow Metrics. **Last updated** shows
the latest successful observation; Admin shows collection status. A handled
failure keeps the previous data and reports a failed collection. Pod startup
failures or missed runs also need checking in Kubernetes.

## Run a capture manually

```sh
kubectl --context <context> -n <namespace> create job \
  flow-metrics-manual-$(date -u +%Y%m%d%H%M%S) \
  --from=cronjob/github-community-flow-metrics-reconcile
```

Avoid an active capture or a scheduled slot. `Forbid` prevents scheduled Jobs
overlapping each other, but does not cover manually created Jobs.

## Private local capture and import

Use a separate, initialised local development database and read-only GitHub credentials.
For an interactive `GH_TOKEN`, the collector accepts `FLOW_METRICS_LOCAL_TOKEN`
only in the existing auth-disabled local development configuration; do not
change hosted authentication.

```sh
FLOW_METRICS_LOCAL_TOKEN="$GH_TOKEN" uv run --locked python -m flask \
  --app app.app flow-metrics collect
uv run --locked python -m flask --app app.app flow-metrics export-snapshots \
  --directory /private/path/outside-the-checkout
```

Keep archives and credentials outside Git. Transfer the reviewed archive through
the approved private route, then use the [existing importer](archive_import.py)
in the target environment:

```sh
python3 -m flask --app app.app flow-metrics import-archives \
  /private/archive --since YYYY-MM-DD --dry-run
```

Check the dry-run result. Import by repeating the command without `--dry-run`
only after approval. Do not reset existing data or change capture timestamps.

## Disable

Set `app.jobs.flow_metrics_reconcile.enabled=false` and redeploy through the
normal process. Check for Jobs already running. Keep observations and charts.

Webhooks are Phase 2. The receiver and inbox processor remain disabled.
