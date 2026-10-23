# 🚀 GitHub Community

[![Ministry of Justice Repository Compliance Badge](https://github-community.service.justice.gov.uk/repository-standards/api/github-community/badge)](https://github-community.service.justice.gov.uk/repository-standards/github-community) [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/ministryofjustice/github-community/badge)](https://scorecard.dev/viewer/?uri=github.com/ministryofjustice/github-community)

[![Open in Dev Container](https://raw.githubusercontent.com/ministryofjustice/.devcontainer/refs/heads/main/contrib/badge.svg)](https://vscode.dev/redirect?url=vscode://ms-vscode-remote.remote-containers/cloneInVolume?url=https://github.com/ministryofjustice/github-community) [![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/ministryofjustice/github-community)

Welcome to the **GitHub Community**! This repository serves as a central hub for community-driven projects within the **Ministry of Justice** GitHub space.

## 📜 Table of Contents

- [📣 About GitHub Community](#-about-github-community)
- [📌 Projects](#-projects)
- [🏗️ github-community Repository](#-github-community-repository)
  - [🔑 Key Features](#-key-features)
  - [📂 Folder Structure](#-folder-structure)
  - [🌎 Hosted Services](#-hosted-services)
  - [✅ Benefits](#-benefits)
  - [❌ Challenges](#-challenges)
  - [🛠️ Development Setup](#-development-setup)
- [📄 License](#-license)

## 📣 About GitHub Community

The **GitHub Community** is a group of passionate engineers dedicated to building great services. It is run by volunteers and promotes an **engineer-first** approach, ensuring that projects remain in the hands of those who actively develop them. The community fosters innovation and collaboration by supporting multiple projects within the **Ministry of Justice** GitHub ecosystem.

## 📌 Projects

The community currently provides the following projects and services:

| Project Name              | Description                                                                                               |
| ------------------------- | --------------------------------------------------------------------------------------------------------- |
| **Repository Standards**  | Improving code quality and security by centralizing knowledge and best practices for GitHub repositories. |
| **Repository Stats** | Viewing repository visibility reports, new and deleted repositories, and archived public repositories across our GitHub organisations. See the [Repository Stats README](app/projects/repository_stats/README.md). |
| **Shared GitHub Actions** | Providing reusable GitHub Actions to reduce technical debt, improve maintainability, and enhance quality. |
| **...**                   | More projects to be added...                                                                              |

## 🏗️ github-community Repository

The **github-community repository** serves as the primary hub and a single pane of glass for all things **GitHub Community**. To help engineers quickly build and deploy their projects, this repository hosts a **modular monolithic Flask application**. Engineers can optionally choose to host their ideas here, minimizing maintenance burdens while gaining quick access to shared components.

### 🔑 Key Features

- **Single Flask Application:** A shared core framework hosting multiple projects.
- **Single Set of Dependencies:** Simplified dependency management.
- **Shared Database (Amazon RDS - PostgreSQL):** Minimal maintenance with easy access to data persistence.
- **Shared Authentication:** Quickly secure projects with a common authentication layer.
- **Modular Code Structure:** Projects are self-contained within the monolith.

### 📂 Folder Structure

```
/github-community/
├── app/                      # Core Flask application
│   └── projects/                 # Individual project modules
│       ├── repository_standards/     # Repository standards module
│       ├── shared_github_actions/    # GitHub Actions module
│       └── ...
│   └── shared/                   # Shared modules
│       ├── config/                   # Shared configuration settings
│       ├── middleware/               # Shared middleware functions
│       ├── routes/                   # Shared routes
│       ├── database.py               # Shared database connection
│       └── ...
├── tests/                    # Automated tests
└── ...
```

### 🌎 Hosted Services

This repository provides a set of services accessible at **[github-community.service.justice.gov.uk](https://github-community.service.justice.gov.uk)**, including:

- **✅ Repository Standards** – Automated reports on repository health and best practices.

### ✅ Benefits

- **Simplified Maintenance** – One codebase to manage.
- **Shared Components** – Reduces duplication of common functionality.
- **Easier Collaboration** – Community contributions are streamlined.
- **Scalable & Extensible** – New projects can be added with minimal setup.

### ❌ Challenges

- **Coupling** – Projects share infrastructure and dependencies.
- **Deployment Coordination** – Updates affect all projects simultaneously.
- **Performance Considerations** – Shared resources must be optimized.

### 🛠️ Development Setup

### Prerequisites

- [uv](https://docs.astral.sh/uv/)
- Docker (optional for local database setup)

### Setup Instructions

```sh
# Clone the repository
git clone https://github.com/ministryofjustice/github-community.git

cd github-community

# Install dependencies
make uv-activate

# Run the application
make app-start
```

## 🚀 Managing Deployments and CronJobs

### Check 5 Security Alert Remediation

Check 5 uses calendar time from each alert's GitHub `created_at` timestamp:

- Any open Secret Scanning alert fails immediately, regardless of validity or age.
- Open Dependabot Critical alerts fail after 72 hours; High alerts fail after
  7 days. Medium and Low dependency alerts do not affect this check.
- Open High and Critical Code Scanning alerts fail after 14 days. Low, Medium
  and alerts with no recognized severity do not affect this check.

Alerts within their remediation window pass that part of the check; an alert
becomes overdue strictly after its deadline. Acknowledgement, production status
and formal risk-acceptance evidence are not evaluated. Fixed, resolved and
dismissed alerts do not count as open findings.

CodeQL's confirmed configured/no-languages exception still applies only to Code
Scanning; Dependabot and Secret Scanning must be assessed independently. Missing
or malformed required alert metadata fails conservatively. Old snapshots need a
fresh collection after deployment because alert counts alone cannot prove SLA
compliance. Deadlines are evaluated when reports are generated, so an alert can
become overdue before the next scrape.

The GitHub App needs Secret scanning alerts read permission approved on its
installation. The collector requests hidden secret values and stores only the
open-secret count; no secret values or raw secret-alert responses are stored.
Code Scanning and Dependabot snapshots retain only state, creation time and
dependency severity for SLA evaluation. Recommendations do not display alert
counts.

### Repository Standards Collection Concurrency

The ownership-mapping CronJob uses `GITHUB_COLLECTION_WORKERS` (1 to 8,
default 1). Helm sets this from
`app.jobs.map_github_repositories_to_owners.workers`: dev uses 3 and production
uses 1. This controls threads inside a single Job, not Kubernetes Pod parallelism
or Gunicorn workers. Dev collects all accessible visibilities with a combined
10,000-repository cap and a four-hour deadline. Production retains public-only
collection, a 1,500-repository cap and a two-hour deadline. Archived repositories
and forks remain excluded.

Set `GITHUB_REPOSITORY_STANDARDS_ORGS` to a comma-separated list of organization
installation IDs, for example:

```text
ministryofjustice:12345,moj-analytical-services:67890
```

Each organization uses its own installation token from the same GitHub App.
If unset, collection uses `ministryofjustice` and `GITHUB_APP_INSTALLATION_ID`
as before. The dev workflow uses the `DEVX_GH_APP_CLIENT_ID`,
`DEVX_GH_APP_PRIVATE_KEY`, `DEVX_GH_APP_INSTALLATION_ID_MOJ` and
`DEVX_GH_APP_INSTALLATION_ID_MOJAS` Actions variables/secret. Production retains
its existing `GH_APP_*` configuration.

The asset migration backfills existing repositories to `ministryofjustice`.
Repository identity is organization plus name; reports can filter by organization
and visibility, and org-qualified report/badge URLs distinguish duplicate names.
Existing name-only URLs still refer to MOJ. Legacy maturity-level reports remain
MOJ-only; the current Technical Standard reports include all collected organizations.
Owner configurations default to MOJ; an explicit `organisation` in owner config
is needed for another organization. Newly collected MOJAS repositories remain
unowned until matching owner mappings are configured.

Workers have separate GitHub clients, HTTP sessions and team caches. They share
a rate-limit cooldown; custom REST requests and retries wait for it, and workers
check it before starting another repository. Requests retry rate limits and
transient server errors up to three times. Each organization is collected, saved
and ownership-mapped before the next organization starts. Database mapping remains
serial, and each repository is saved once before ownership mapping. A failure
collecting MOJAS therefore does not discard MOJ results already saved in that run.
Stale cleanup only runs for that organization after its uncapped collection,
saving and ownership mapping succeed. Capped or skipped organizations retain
their previous unseen records. The cap is shared across organizations in
configuration order.

If the custom-properties endpoint returns HTTP 403 with "Resource not accessible
by integration", collection continues with unavailable custom-property metadata.
The warning logs the organization/repository, status, accepted permissions and
GitHub request ID, without dumping response bodies or credentials. The ownership
check fails conservatively and explains that the business-unit property could
not be verified, rather than claiming it is missing. Other API errors are not
silently ignored, and security-alert checks retain their existing behaviour.

Compare `Collection phase complete` and `Mapping and cleanup complete` log lines
with the previous benchmark. `Organization save complete` confirms one organization's
database saving and mapping have finished before collection proceeds to the next.
`Collected repository` logs give individual timings;
`GitHub collection complete` includes custom REST request totals (not PyGithub
request totals). Custom REST endpoint timings and remaining quota are logged at
DEBUG level, and cooldowns at WARNING level.

After a PR deployment updates the dev CronJob, its next scheduled run uses these
settings unless another deployment replaces them. No manual trigger is required.
Checkpoint/resume is not included: a retry still starts collection from the first
configured organization. Already saved organization results survive, but a failure
during collection still loses the in-memory progress for that organization.
Saves are not an atomic organization-wide transaction: a database failure can
leave partially updated reports, but cleanup is not run after that save failure.

### Shared GitHub Collection Services

Reusable collection infrastructure lives under `app/shared/services`:

- `github_collection_config.py` provides `OrganisationInstallation` and
  `parse_organisation_installations`. Callers supply the configuration value,
  configuration name and fallback organization; it does not read project env vars.
- `github_app_client.py` provides installation-token creation/refresh, an isolated
  HTTP session with timeouts, and optional shared rate-limit coordination/retries.
  `get`/`request` return raw responses for project-specific status handling;
  `request_json` decodes JSON and raises `GitHubApiError` on unsuccessful responses.
  Absolute pagination URLs must match the API origin. Call `close` when finished.

Create a client per worker and a coordinator per installation, not a session
shared by threads or a cooldown shared across different installation quotas.
Repository Standards uses this infrastructure but owns its repository filters,
checks, ownership mapping and persistence. Its existing client/config imports
remain available as compatibility adapters.

Repository Stats has **not** been migrated. A future change can adapt its
`REPOSITORY_STATS_ORGS` value to the shared parser and replace its local REST
transport with `GitHubAppClient`, retaining its inventory policy, pagination,
response-status handling, schedules and data model. No Stats configuration or
behaviour is changed by the shared-service extraction.

Occasionally, you may need to debug a failed deployment or failing CronJob in the Cloud Platform Kubernetes cluster. Replace `github-community-dev` with the namespace you’re working in. Below are some commands to help you debug issues.
Before trying these commands, follow the [Connecting to the Cloud Platform’s Kubernetes cluster](https://user-guide.cloud-platform.service.justice.gov.uk/documentation/getting-started/kubectl-config.html) guide.

Get pods in the namespace, useful for seeing if pods are healthy and getting the name of a failing pod:

```bash
$ kubectl -n github-community-dev get pods
NAME                                                   READY   STATUS      RESTARTS   AGE
github-community-56b5c64d49-9x2rj                      1/1     Running     0          27h
map-github-repositories-to-owners-job-29778480-mvzc4   0/1     Completed   0          104m
```

Get the logs of a specific pod, useful for seeing why a pod may be failing to start:

```bash
$ kubectl -n github-community-dev logs github-community-56b5c64d49-9x2rj
2026-08-14T13:36:31 |     INFO | error_handler.py:14 | A request was made to a page that doesn't exist 404 Not Found: The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.
```

Get CronJobs, useful for seeing what exists and double checking the name for other commands:

```bash
$ kubectl -n github-community-dev get cronjobs
NAME                                    SCHEDULE    TIMEZONE   SUSPEND   ACTIVE   LAST SCHEDULE   AGE
map-github-repositories-to-owners-job   0 3 * * *   <none>     False     0        10h             508d
```

Create Jobs, useful for manually triggering the mapper job to debug fixes:

```bash
$ kubectl -n github-community-dev create job manual-mapper-job --from cronjob/map-github-repositories-to-owners-job
job.batch/manual-mapper-job created
```

Get Jobs, useful for seeing running and previous jobs:

```bash
$ kubectl -n github-community-dev get jobs
NAME                                             STATUS     COMPLETIONS   DURATION   AGE
manual-mapper-job                                Running    0/1                      25s
map-github-repositories-to-owners-job-29602260   Failed     0/1           122d       122d
map-github-repositories-to-owners-job-29603700   Failed     0/1           121d       121d
map-github-repositories-to-owners-job-29777940   Complete   1/1           52m        10h
```

---

## 📄 License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.
