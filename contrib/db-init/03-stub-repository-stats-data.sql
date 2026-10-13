-- Stub data for GitHub Repository Stats (local development only).
-- Same shape as 02-stub-repository-visibility-data.sql, but for the Repository Stats tables,
-- with repositories spread across several GitHub Enterprise organisations so the
-- Organisation filter can be demonstrated:
--   ministryofjustice, moj-analytical-services, CriminalInjuriesCompensationAuthority
-- Sample data only. Real dynamic organisation fetching from the GitHub Enterprise API is
-- deferred to M3, pending installation of the GitHub App on the other organisations.
-- Dates are relative to the day the database is created. The rows below are written for
-- snapshots on 2026-08-01 and 2026-09-25 with weekly clusters of events in between. The
-- block at the end of this file moves the earliest snapshot to 2026-08-17 (the real
-- baseline date) and the latest to today (CURRENT_DATE), and spreads the events between
-- them. For example, on a database created on 2026-10-01 the snapshots are on 2026-08-17
-- and 2026-10-01, with events from 2026-08-19 to 2026-09-29.
-- The assets and ADMIN_ACCESS relationships below are the same rows as in 02 (shared
-- ownership tables, ON CONFLICT DO NOTHING), so this file also works on its own. An
-- UPDATE after them gives the stub assets shared, made-up team slugs per business unit
-- (for example platform-team, service-team, operations-team) for the Repository overview,
-- and the last statement copies them into repository_stats_team_access, the table the
-- visibility job fills with team access for every repository. A few more team access
-- rows use team slugs from the shared owners.config, so business units also show for
-- repositories with no shared ownership relationship, and the organisations get display
-- names (repository_stats_organisations) for the Repository overview.
-- Safe to run more than once: a second run doesn't add rows or move the dates again.

-- Stub rows already loaded by an earlier run, so the block at the end can tell a first
-- load (move the dates) from a re-run (keep the dates, drop rows re-added on the
-- original dates).
CREATE TEMP TABLE stub_repository_stats_before AS
SELECT
  (SELECT max(id) FROM public.repository_stats_visibility_snapshots
   WHERE github_id BETWEEN 900000000 AND 900000999) AS last_snapshot_id,
  (SELECT max(id) FROM public.repository_stats_visibility_events
   WHERE github_id BETWEEN 900000000 AND 900000999) AS last_event_id;

INSERT INTO public.repository_stats_visibility_snapshots
(github_id, org, name, visibility, archived, fork, created_at, pushed_at, captured_on) VALUES
(900000001, 'ministryofjustice', 'sample-prison-visits', 'public', false, false, '2022-02-01 10:00:00', '2026-06-02 12:00:00', '2026-08-01'),
(900000002, 'moj-analytical-services', 'sample-probation-search', 'private', true, false, '2019-09-16 10:00:00', '2023-09-23 12:00:00', '2026-08-01'),
(900000003, 'ministryofjustice', 'sample-offender-events', 'internal', false, false, '2022-01-26 10:00:00', '2026-07-14 12:00:00', '2026-08-01'),
(900000004, 'ministryofjustice', 'sample-custody-tracker', 'internal', false, false, '2022-03-22 10:00:00', '2026-06-26 12:00:00', '2026-08-01'),
(900000005, 'CriminalInjuriesCompensationAuthority', 'sample-parole-board', 'internal', false, false, '2018-11-10 10:00:00', '2026-07-21 12:00:00', '2026-08-01'),
(900000006, 'moj-analytical-services', 'sample-sentence-calc', 'internal', true, false, '2016-10-29 10:00:00', '2021-07-23 12:00:00', '2026-08-01'),
(900000007, 'ministryofjustice', 'sample-prisoner-money', 'public', false, false, '2016-04-05 10:00:00', '2026-06-02 12:00:00', '2026-08-01'),
(900000008, 'moj-analytical-services', 'sample-release-planner', 'internal', false, false, '2019-02-07 10:00:00', '2026-07-05 12:00:00', '2026-08-01'),
(900000009, 'CriminalInjuriesCompensationAuthority', 'sample-cell-allocation', 'private', false, false, '2021-05-15 10:00:00', '2026-06-27 12:00:00', '2026-08-01'),
(900000010, 'ministryofjustice', 'sample-prison-education', 'public', true, true, '2017-06-24 10:00:00', '2022-07-13 12:00:00', '2026-08-01'),
(900000011, 'CriminalInjuriesCompensationAuthority', 'sample-probation-api', 'public', false, false, '2017-07-21 10:00:00', '2026-07-31 12:00:00', '2026-08-01'),
(900000012, 'moj-analytical-services', 'sample-risk-assessment', 'internal', false, false, '2023-01-11 10:00:00', '2026-07-08 12:00:00', '2026-08-01'),
(900000013, 'ministryofjustice', 'sample-court-to-custody', 'internal', true, false, '2016-07-02 10:00:00', '2021-01-04 12:00:00', '2026-08-01'),
(900000014, 'moj-analytical-services', 'sample-resettlement-hub', 'public', false, false, '2022-03-15 10:00:00', '2026-06-03 12:00:00', '2026-08-01'),
(900000015, 'moj-analytical-services', 'sample-visits-booking', 'internal', false, false, '2023-04-17 10:00:00', '2026-07-26 12:00:00', '2026-08-01'),
(900000016, 'ministryofjustice', 'sample-incentives', 'public', true, false, '2020-08-14 10:00:00', '2023-07-02 12:00:00', '2026-08-01'),
(900000017, 'moj-analytical-services', 'sample-adjudications', 'public', true, false, '2020-08-06 10:00:00', '2022-01-31 12:00:00', '2026-08-01'),
(900000018, 'ministryofjustice', 'sample-keyworker-ui', 'public', false, false, '2019-10-27 10:00:00', '2026-07-11 12:00:00', '2026-08-01'),
(900000019, 'ministryofjustice', 'sample-case-insights', 'internal', true, false, '2018-12-01 10:00:00', '2022-07-24 12:00:00', '2026-08-01'),
(900000020, 'ministryofjustice', 'sample-prison-register', 'public', true, false, '2016-04-25 10:00:00', '2019-02-16 12:00:00', '2026-08-01'),
(900000021, 'CriminalInjuriesCompensationAuthority', 'sample-legal-aid-portal', 'private', true, false, '2019-07-09 10:00:00', '2020-11-17 12:00:00', '2026-08-01'),
(900000022, 'ministryofjustice', 'sample-civil-apply', 'internal', false, false, '2021-04-11 10:00:00', '2026-06-04 12:00:00', '2026-08-01'),
(900000023, 'moj-analytical-services', 'sample-crime-apply', 'private', false, false, '2018-06-27 10:00:00', '2026-07-14 12:00:00', '2026-08-01'),
(900000024, 'ministryofjustice', 'sample-means-assessment', 'internal', false, false, '2021-09-14 10:00:00', '2026-07-26 12:00:00', '2026-08-01'),
(900000025, 'CriminalInjuriesCompensationAuthority', 'sample-provider-payments', 'internal', false, false, '2017-09-09 10:00:00', '2026-07-30 12:00:00', '2026-08-01'),
(900000026, 'moj-analytical-services', 'sample-fee-calculator', 'public', false, false, '2024-05-10 10:00:00', '2026-07-28 12:00:00', '2026-08-01'),
(900000027, 'moj-analytical-services', 'sample-laa-reporting', 'public', true, false, '2020-11-20 10:00:00', '2023-02-15 12:00:00', '2026-08-01'),
(900000028, 'ministryofjustice', 'sample-claims-api', 'public', false, true, '2023-12-06 10:00:00', '2026-06-24 12:00:00', '2026-08-01'),
(900000029, 'ministryofjustice', 'sample-eligibility-checker', 'internal', false, false, '2024-11-10 10:00:00', '2026-06-15 12:00:00', '2026-08-01'),
(900000030, 'ministryofjustice', 'sample-contract-work', 'internal', false, false, '2022-04-19 10:00:00', '2026-07-24 12:00:00', '2026-08-01'),
(900000031, 'moj-analytical-services', 'sample-laa-data-sync', 'public', false, false, '2019-02-03 10:00:00', '2026-06-22 12:00:00', '2026-08-01'),
(900000032, 'moj-analytical-services', 'sample-legal-adviser-search', 'private', false, false, '2018-04-03 10:00:00', '2026-06-24 12:00:00', '2026-08-01'),
(900000033, 'ministryofjustice', 'sample-lpa-frontend', 'private', false, false, '2020-01-10 10:00:00', '2026-06-30 12:00:00', '2026-08-01'),
(900000034, 'CriminalInjuriesCompensationAuthority', 'sample-lpa-api', 'private', true, false, '2019-07-28 10:00:00', '2022-02-19 12:00:00', '2026-08-01'),
(900000035, 'moj-analytical-services', 'sample-deputy-reporting', 'internal', false, false, '2022-02-25 10:00:00', '2026-07-22 12:00:00', '2026-08-01'),
(900000036, 'ministryofjustice', 'sample-sirius-ui', 'private', false, false, '2021-04-25 10:00:00', '2026-07-28 12:00:00', '2026-08-01'),
(900000037, 'moj-analytical-services', 'sample-opg-metrics', 'public', true, false, '2020-06-03 10:00:00', '2024-03-13 12:00:00', '2026-08-01'),
(900000038, 'ministryofjustice', 'sample-use-an-lpa', 'internal', true, false, '2019-04-04 10:00:00', '2022-10-03 12:00:00', '2026-08-01'),
(900000039, 'moj-analytical-services', 'sample-opg-data-export', 'public', false, true, '2018-02-08 10:00:00', '2026-06-11 12:00:00', '2026-08-01'),
(900000040, 'ministryofjustice', 'sample-modernising-lpa', 'public', false, false, '2023-01-16 10:00:00', '2026-06-27 12:00:00', '2026-08-01'),
(900000041, 'CriminalInjuriesCompensationAuthority', 'sample-refunds', 'public', true, false, '2016-11-10 10:00:00', '2024-06-08 12:00:00', '2026-08-01'),
(900000042, 'ministryofjustice', 'sample-court-listings', 'internal', false, false, '2016-01-22 10:00:00', '2026-07-31 12:00:00', '2026-08-01'),
(900000043, 'moj-analytical-services', 'sample-tribunal-forms', 'internal', false, false, '2019-12-22 10:00:00', '2026-07-23 12:00:00', '2026-08-01'),
(900000044, 'ministryofjustice', 'sample-hearing-scheduler', 'public', false, false, '2025-05-13 10:00:00', '2026-07-04 12:00:00', '2026-08-01'),
(900000045, 'ministryofjustice', 'sample-jury-summons', 'private', false, false, '2023-11-16 10:00:00', '2026-06-27 12:00:00', '2026-08-01'),
(900000046, 'moj-analytical-services', 'sample-fines-calculator', 'public', false, false, '2024-12-01 10:00:00', '2026-06-03 12:00:00', '2026-08-01'),
(900000047, 'ministryofjustice', 'sample-witness-portal', 'private', false, false, '2023-03-02 10:00:00', '2026-06-12 12:00:00', '2026-08-01'),
(900000048, 'moj-analytical-services', 'sample-court-store', 'public', true, false, '2016-06-21 10:00:00', '2022-05-09 12:00:00', '2026-08-01'),
(900000049, 'CriminalInjuriesCompensationAuthority', 'sample-family-mediation', 'internal', false, false, '2020-03-06 10:00:00', '2026-07-05 12:00:00', '2026-08-01'),
(900000050, 'ministryofjustice', 'sample-civil-money-claims', 'public', false, false, '2024-03-13 10:00:00', '2026-06-17 12:00:00', '2026-08-01'),
(900000051, 'ministryofjustice', 'sample-divorce-app', 'public', true, false, '2016-10-09 10:00:00', '2020-02-17 12:00:00', '2026-08-01'),
(900000052, 'CriminalInjuriesCompensationAuthority', 'sample-probate-frontend', 'private', true, false, '2016-02-07 10:00:00', '2024-12-24 12:00:00', '2026-08-01'),
(900000053, 'ministryofjustice', 'sample-design-system', 'public', false, true, '2018-06-08 10:00:00', '2026-07-25 12:00:00', '2026-08-01'),
(900000054, 'ministryofjustice', 'sample-docs-site', 'internal', false, false, '2023-10-20 10:00:00', '2026-07-08 12:00:00', '2026-08-01'),
(900000055, 'moj-analytical-services', 'sample-form-builder', 'public', true, false, '2017-09-20 10:00:00', '2019-07-02 12:00:00', '2026-08-01'),
(900000056, 'ministryofjustice', 'sample-status-page', 'internal', false, false, '2020-05-29 10:00:00', '2026-06-25 12:00:00', '2026-08-01'),
(900000057, 'ministryofjustice', 'sample-release-bot', 'internal', false, false, '2022-01-16 10:00:00', '2026-07-04 12:00:00', '2026-08-01'),
(900000058, 'ministryofjustice', 'sample-staff-directory', 'internal', false, true, '2025-02-08 10:00:00', '2026-07-12 12:00:00', '2026-08-01'),
(900000059, 'ministryofjustice', 'sample-intranet', 'public', true, false, '2019-09-17 10:00:00', '2020-08-05 12:00:00', '2026-08-01'),
(900000060, 'ministryofjustice', 'sample-prototype-kit', 'public', false, true, '2021-09-14 10:00:00', '2026-06-07 12:00:00', '2026-08-01'),
(900000061, 'moj-analytical-services', 'sample-analytics-dash', 'internal', false, false, '2016-12-16 10:00:00', '2026-06-10 12:00:00', '2026-08-01'),
(900000062, 'moj-analytical-services', 'sample-hale-platform', 'internal', false, false, '2024-03-19 10:00:00', '2026-06-25 12:00:00', '2026-08-01'),
(900000063, 'moj-analytical-services', 'sample-wiki-export', 'public', true, false, '2017-11-14 10:00:00', '2021-12-06 12:00:00', '2026-08-01'),
(900000064, 'ministryofjustice', 'sample-helm-charts', 'private', false, true, '2019-06-25 10:00:00', '2026-06-03 12:00:00', '2026-08-01'),
(900000065, 'ministryofjustice', 'sample-infra-terraform', 'public', false, false, '2024-04-08 10:00:00', '2026-07-08 12:00:00', '2026-08-01'),
(900000066, 'ministryofjustice', 'sample-log-shipper', 'public', false, false, '2023-06-05 10:00:00', '2026-07-21 12:00:00', '2026-08-01'),
(900000067, 'moj-analytical-services', 'sample-cloud-costs', 'public', false, false, '2018-02-16 10:00:00', '2026-06-11 12:00:00', '2026-08-01'),
(900000068, 'CriminalInjuriesCompensationAuthority', 'sample-security-scanner', 'public', false, false, '2019-04-14 10:00:00', '2026-06-19 12:00:00', '2026-08-01'),
(900000069, 'ministryofjustice', 'sample-ops-runbooks', 'internal', true, false, '2019-01-13 10:00:00', '2022-03-27 12:00:00', '2026-08-01'),
(900000070, 'moj-analytical-services', 'sample-temp-spike', 'internal', false, false, '2020-01-03 10:00:00', '2026-06-09 12:00:00', '2026-08-01'),
(900000071, 'ministryofjustice', 'sample-2019-hackday', 'public', true, false, '2018-03-06 10:00:00', '2021-02-11 12:00:00', '2026-08-01'),
(900000072, 'CriminalInjuriesCompensationAuthority', 'sample-old-case-viewer', 'public', true, false, '2020-03-09 10:00:00', '2023-09-19 12:00:00', '2026-08-01'),
(900000073, 'ministryofjustice', 'asset-alpha', 'public', false, false, '2016-02-08 10:00:00', '2026-07-25 12:00:00', '2026-08-01'),
(900000074, 'ministryofjustice', 'asset-bravo', 'public', false, false, '2022-10-17 10:00:00', '2026-07-12 12:00:00', '2026-08-01'),
(900000075, 'ministryofjustice', 'asset-charlie', 'public', false, false, '2021-05-20 10:00:00', '2026-07-31 12:00:00', '2026-08-01'),
(900000076, 'ministryofjustice', 'asset-delta', 'public', true, false, '2018-05-15 10:00:00', '2022-12-27 12:00:00', '2026-08-01'),
(900000077, 'ministryofjustice', 'asset-echo', 'public', true, false, '2020-07-21 10:00:00', '2024-11-18 12:00:00', '2026-08-01'),
(900000078, 'ministryofjustice', 'asset-foxtrot', 'public', false, false, '2024-09-15 10:00:00', '2026-07-27 12:00:00', '2026-08-01'),
(900000001, 'ministryofjustice', 'sample-prison-visits', 'public', false, false, '2022-02-01 10:00:00', '2026-08-11 12:00:00', '2026-09-25'),
(900000002, 'moj-analytical-services', 'sample-probation-search', 'private', true, false, '2019-09-16 10:00:00', '2023-09-23 12:00:00', '2026-09-25'),
(900000003, 'ministryofjustice', 'sample-offender-events', 'public', false, false, '2022-01-26 10:00:00', '2026-08-02 12:00:00', '2026-09-25'),
(900000004, 'ministryofjustice', 'sample-custody-tracker', 'internal', false, false, '2022-03-22 10:00:00', '2026-08-08 12:00:00', '2026-09-25'),
(900000005, 'CriminalInjuriesCompensationAuthority', 'sample-parole-board', 'private', false, false, '2018-11-10 10:00:00', '2026-09-02 12:00:00', '2026-09-25'),
(900000006, 'moj-analytical-services', 'sample-sentence-calc', 'internal', true, false, '2016-10-29 10:00:00', '2021-07-23 12:00:00', '2026-09-25'),
(900000007, 'ministryofjustice', 'sample-prisoner-money', 'internal', false, false, '2016-04-05 10:00:00', '2026-09-12 12:00:00', '2026-09-25'),
(900000008, 'moj-analytical-services', 'sample-release-planner', 'private', true, false, '2019-02-07 10:00:00', '2026-07-05 12:00:00', '2026-09-25'),
(900000009, 'CriminalInjuriesCompensationAuthority', 'sample-cell-allocation', 'internal', false, false, '2021-05-15 10:00:00', '2026-09-15 12:00:00', '2026-09-25'),
(900000010, 'ministryofjustice', 'sample-prison-education', 'public', true, true, '2017-06-24 10:00:00', '2022-07-13 12:00:00', '2026-09-25'),
(900000011, 'CriminalInjuriesCompensationAuthority', 'sample-probation-api', 'public', false, false, '2017-07-21 10:00:00', '2026-09-11 12:00:00', '2026-09-25'),
(900000012, 'moj-analytical-services', 'sample-risk-assessment', 'internal', false, false, '2023-01-11 10:00:00', '2026-09-19 12:00:00', '2026-09-25'),
(900000013, 'ministryofjustice', 'sample-court-to-custody', 'internal', true, false, '2016-07-02 10:00:00', '2021-01-04 12:00:00', '2026-09-25'),
(900000014, 'moj-analytical-services', 'sample-resettlement-hub', 'internal', false, false, '2022-03-15 10:00:00', '2026-08-01 12:00:00', '2026-09-25'),
(900000015, 'moj-analytical-services', 'sample-visits-booking', 'public', false, false, '2023-04-17 10:00:00', '2026-09-23 12:00:00', '2026-09-25'),
(900000016, 'ministryofjustice', 'sample-incentives', 'internal', true, false, '2020-08-14 10:00:00', '2023-07-02 12:00:00', '2026-09-25'),
(900000017, 'moj-analytical-services', 'sample-adjudications', 'internal', true, false, '2020-08-06 10:00:00', '2022-01-31 12:00:00', '2026-09-25'),
(900000018, 'ministryofjustice', 'sample-keyworker-ui', 'public', false, false, '2019-10-27 10:00:00', '2026-08-24 12:00:00', '2026-09-25'),
(900000019, 'ministryofjustice', 'sample-case-insights', 'internal', true, false, '2018-12-01 10:00:00', '2022-07-24 12:00:00', '2026-09-25'),
(900000021, 'CriminalInjuriesCompensationAuthority', 'sample-legal-aid-portal', 'private', true, false, '2019-07-09 10:00:00', '2020-11-17 12:00:00', '2026-09-25'),
(900000022, 'ministryofjustice', 'sample-civil-apply', 'public', false, false, '2021-04-11 10:00:00', '2026-08-05 12:00:00', '2026-09-25'),
(900000023, 'moj-analytical-services', 'sample-crime-apply', 'internal', false, false, '2018-06-27 10:00:00', '2026-08-24 12:00:00', '2026-09-25'),
(900000024, 'ministryofjustice', 'sample-means-assessment', 'internal', false, false, '2021-09-14 10:00:00', '2026-08-20 12:00:00', '2026-09-25'),
(900000025, 'CriminalInjuriesCompensationAuthority', 'sample-provider-payments', 'internal', false, false, '2017-09-09 10:00:00', '2026-08-14 12:00:00', '2026-09-25'),
(900000026, 'moj-analytical-services', 'sample-fee-calculator', 'public', false, false, '2024-05-10 10:00:00', '2026-09-04 12:00:00', '2026-09-25'),
(900000027, 'moj-analytical-services', 'sample-laa-reporting', 'internal', true, false, '2020-11-20 10:00:00', '2023-02-15 12:00:00', '2026-09-25'),
(900000028, 'ministryofjustice', 'sample-claims-api', 'internal', false, true, '2023-12-06 10:00:00', '2026-08-10 12:00:00', '2026-09-25'),
(900000029, 'ministryofjustice', 'sample-eligibility-checker', 'public', false, false, '2024-11-10 10:00:00', '2026-09-08 12:00:00', '2026-09-25'),
(900000030, 'ministryofjustice', 'sample-contract-work', 'internal', false, false, '2022-04-19 10:00:00', '2026-09-09 12:00:00', '2026-09-25'),
(900000032, 'moj-analytical-services', 'sample-legal-adviser-search', 'public', false, false, '2018-04-03 10:00:00', '2026-08-16 12:00:00', '2026-09-25'),
(900000033, 'ministryofjustice', 'sample-lpa-frontend', 'public', false, false, '2020-01-10 10:00:00', '2026-08-09 12:00:00', '2026-09-25'),
(900000034, 'CriminalInjuriesCompensationAuthority', 'sample-lpa-api', 'private', true, false, '2019-07-28 10:00:00', '2022-02-19 12:00:00', '2026-09-25'),
(900000035, 'moj-analytical-services', 'sample-deputy-reporting', 'internal', false, false, '2022-02-25 10:00:00', '2026-08-07 12:00:00', '2026-09-25'),
(900000036, 'ministryofjustice', 'sample-sirius-ui', 'internal', false, false, '2021-04-25 10:00:00', '2026-08-21 12:00:00', '2026-09-25'),
(900000037, 'moj-analytical-services', 'sample-opg-metrics', 'public', true, false, '2020-06-03 10:00:00', '2024-03-13 12:00:00', '2026-09-25'),
(900000038, 'ministryofjustice', 'sample-use-an-lpa', 'internal', true, false, '2019-04-04 10:00:00', '2022-10-03 12:00:00', '2026-09-25'),
(900000039, 'moj-analytical-services', 'sample-opg-data-export', 'public', false, true, '2018-02-08 10:00:00', '2026-09-01 12:00:00', '2026-09-25'),
(900000040, 'ministryofjustice', 'sample-modernising-lpa', 'public', false, false, '2023-01-16 10:00:00', '2026-08-07 12:00:00', '2026-09-25'),
(900000041, 'CriminalInjuriesCompensationAuthority', 'sample-refunds', 'public', true, false, '2016-11-10 10:00:00', '2024-06-08 12:00:00', '2026-09-25'),
(900000042, 'ministryofjustice', 'sample-court-listings', 'internal', false, false, '2016-01-22 10:00:00', '2026-09-23 12:00:00', '2026-09-25'),
(900000043, 'moj-analytical-services', 'sample-tribunal-forms', 'internal', false, false, '2019-12-22 10:00:00', '2026-09-16 12:00:00', '2026-09-25'),
(900000044, 'ministryofjustice', 'sample-hearing-scheduler', 'public', false, false, '2025-05-13 10:00:00', '2026-08-05 12:00:00', '2026-09-25'),
(900000045, 'ministryofjustice', 'sample-jury-summons', 'private', true, false, '2023-11-16 10:00:00', '2026-06-27 12:00:00', '2026-09-25'),
(900000046, 'moj-analytical-services', 'sample-fines-calculator', 'internal', false, false, '2024-12-01 10:00:00', '2026-08-25 12:00:00', '2026-09-25'),
(900000047, 'ministryofjustice', 'sample-witness-portal', 'private', false, false, '2023-03-02 10:00:00', '2026-08-17 12:00:00', '2026-09-25'),
(900000048, 'moj-analytical-services', 'sample-court-store', 'internal', true, false, '2016-06-21 10:00:00', '2022-05-09 12:00:00', '2026-09-25'),
(900000049, 'CriminalInjuriesCompensationAuthority', 'sample-family-mediation', 'private', false, false, '2020-03-06 10:00:00', '2026-09-09 12:00:00', '2026-09-25'),
(900000050, 'ministryofjustice', 'sample-civil-money-claims', 'private', false, false, '2024-03-13 10:00:00', '2026-08-20 12:00:00', '2026-09-25'),
(900000052, 'CriminalInjuriesCompensationAuthority', 'sample-probate-frontend', 'private', true, false, '2016-02-07 10:00:00', '2024-12-24 12:00:00', '2026-09-25'),
(900000053, 'ministryofjustice', 'sample-design-system', 'internal', false, true, '2018-06-08 10:00:00', '2026-09-11 12:00:00', '2026-09-25'),
(900000054, 'ministryofjustice', 'sample-docs-site', 'public', false, false, '2023-10-20 10:00:00', '2026-08-08 12:00:00', '2026-09-25'),
(900000055, 'moj-analytical-services', 'sample-form-builder', 'public', true, false, '2017-09-20 10:00:00', '2019-07-02 12:00:00', '2026-09-25'),
(900000056, 'ministryofjustice', 'sample-status-page', 'internal', true, false, '2020-05-29 10:00:00', '2026-06-25 12:00:00', '2026-09-25'),
(900000057, 'ministryofjustice', 'sample-release-bot', 'private', false, false, '2022-01-16 10:00:00', '2026-08-23 12:00:00', '2026-09-25'),
(900000058, 'ministryofjustice', 'sample-staff-directory', 'internal', false, true, '2025-02-08 10:00:00', '2026-08-31 12:00:00', '2026-09-25'),
(900000059, 'ministryofjustice', 'sample-intranet', 'internal', true, false, '2019-09-17 10:00:00', '2020-08-05 12:00:00', '2026-09-25'),
(900000060, 'ministryofjustice', 'sample-prototype-kit', 'public', false, true, '2021-09-14 10:00:00', '2026-09-01 12:00:00', '2026-09-25'),
(900000061, 'moj-analytical-services', 'sample-analytics-dash', 'private', false, false, '2016-12-16 10:00:00', '2026-08-08 12:00:00', '2026-09-25'),
(900000062, 'moj-analytical-services', 'sample-hale-platform', 'internal', false, false, '2024-03-19 10:00:00', '2026-09-05 12:00:00', '2026-09-25'),
(900000064, 'ministryofjustice', 'sample-helm-charts', 'public', false, true, '2019-06-25 10:00:00', '2026-09-03 12:00:00', '2026-09-25'),
(900000065, 'ministryofjustice', 'sample-infra-terraform', 'public', false, false, '2024-04-08 10:00:00', '2026-08-16 12:00:00', '2026-09-25'),
(900000066, 'ministryofjustice', 'sample-log-shipper', 'public', false, false, '2023-06-05 10:00:00', '2026-09-23 12:00:00', '2026-09-25'),
(900000067, 'moj-analytical-services', 'sample-cloud-costs', 'public', false, false, '2018-02-16 10:00:00', '2026-08-23 12:00:00', '2026-09-25'),
(900000068, 'CriminalInjuriesCompensationAuthority', 'sample-security-scanner', 'public', false, false, '2019-04-14 10:00:00', '2026-09-13 12:00:00', '2026-09-25'),
(900000069, 'ministryofjustice', 'sample-ops-runbooks', 'internal', true, false, '2019-01-13 10:00:00', '2022-03-27 12:00:00', '2026-09-25'),
(900000071, 'ministryofjustice', 'sample-2019-hackday', 'public', true, false, '2018-03-06 10:00:00', '2021-02-11 12:00:00', '2026-09-25'),
(900000072, 'CriminalInjuriesCompensationAuthority', 'sample-old-case-viewer', 'internal', true, false, '2020-03-09 10:00:00', '2023-09-19 12:00:00', '2026-09-25'),
(900000073, 'ministryofjustice', 'asset-alpha', 'public', false, false, '2016-02-08 10:00:00', '2026-09-22 12:00:00', '2026-09-25'),
(900000074, 'ministryofjustice', 'asset-bravo', 'public', false, false, '2022-10-17 10:00:00', '2026-08-30 12:00:00', '2026-09-25'),
(900000075, 'ministryofjustice', 'asset-charlie', 'public', false, false, '2021-05-20 10:00:00', '2026-09-07 12:00:00', '2026-09-25'),
(900000076, 'ministryofjustice', 'asset-delta', 'public', true, false, '2018-05-15 10:00:00', '2022-12-27 12:00:00', '2026-09-25'),
(900000077, 'ministryofjustice', 'asset-echo', 'public', true, false, '2020-07-21 10:00:00', '2024-11-18 12:00:00', '2026-09-25'),
(900000078, 'ministryofjustice', 'asset-foxtrot', 'private', false, false, '2024-09-15 10:00:00', '2026-08-23 12:00:00', '2026-09-25'),
(900000079, 'moj-analytical-services', 'sample-crime-apply-v2', 'public', false, false, '2026-08-05 10:00:00', '2026-09-08 12:00:00', '2026-09-25'),
(900000080, 'ministryofjustice', 'sample-prison-app-v2', 'public', false, false, '2026-08-11 10:00:00', '2026-08-21 12:00:00', '2026-09-25'),
(900000081, 'moj-analytical-services', 'sample-data-sharing-api', 'internal', false, false, '2026-08-18 10:00:00', '2026-09-20 12:00:00', '2026-09-25'),
(900000082, 'ministryofjustice', 'sample-probation-notes', 'public', false, false, '2026-08-26 10:00:00', '2026-08-26 12:00:00', '2026-09-25'),
(900000083, 'ministryofjustice', 'sample-tribunal-bundle', 'private', false, false, '2026-09-03 10:00:00', '2026-09-08 12:00:00', '2026-09-25'),
(900000084, 'ministryofjustice', 'sample-lpa-store', 'private', false, false, '2026-09-10 10:00:00', '2026-09-15 12:00:00', '2026-09-25'),
(900000085, 'moj-analytical-services', 'sample-open-data-export', 'public', false, false, '2026-09-16 10:00:00', '2026-09-24 12:00:00', '2026-09-25'),
(900000086, 'ministryofjustice', 'sample-court-api-v2', 'internal', false, false, '2026-09-22 10:00:00', '2026-09-22 12:00:00', '2026-09-25')
ON CONFLICT (github_id, captured_on) DO NOTHING;

INSERT INTO public.repository_stats_visibility_events
(github_id, org, name, event_type, from_visibility, to_visibility, occurred_on, actor, source)
SELECT v.* FROM (VALUES
(900000016, 'ministryofjustice', 'sample-incentives', 'changed', 'public', 'internal', DATE '2026-08-03', NULL::varchar, 'scan'),
(900000078, 'ministryofjustice', 'asset-foxtrot', 'changed', 'public', 'internal', DATE '2026-08-05', NULL::varchar, 'scan'),
(900000079, 'moj-analytical-services', 'sample-crime-apply-v2', 'created', NULL::varchar, 'public', DATE '2026-08-05', NULL::varchar, 'scan'),
(900000054, 'ministryofjustice', 'sample-docs-site', 'changed', 'internal', 'private', DATE '2026-08-05', NULL::varchar, 'scan'),
(900000046, 'moj-analytical-services', 'sample-fines-calculator', 'changed', 'public', 'private', DATE '2026-08-05', NULL::varchar, 'scan'),
(900000032, 'moj-analytical-services', 'sample-legal-adviser-search', 'changed', 'private', 'public', DATE '2026-08-05', NULL::varchar, 'scan'),
(900000056, 'ministryofjustice', 'sample-status-page', 'changed', 'internal', 'public', DATE '2026-08-05', NULL::varchar, 'scan'),
(900000070, 'moj-analytical-services', 'sample-temp-spike', 'deleted', 'internal', NULL::varchar, DATE '2026-08-06', NULL::varchar, 'scan'),
(900000049, 'CriminalInjuriesCompensationAuthority', 'sample-family-mediation', 'changed', 'internal', 'public', DATE '2026-08-10', NULL::varchar, 'scan'),
(900000057, 'ministryofjustice', 'sample-release-bot', 'changed', 'internal', 'private', DATE '2026-08-10', NULL::varchar, 'scan'),
(900000056, 'ministryofjustice', 'sample-status-page', 'changed', 'public', 'internal', DATE '2026-08-10', NULL::varchar, 'scan'),
(900000017, 'moj-analytical-services', 'sample-adjudications', 'changed', 'public', 'internal', DATE '2026-08-11', NULL::varchar, 'scan'),
(900000009, 'CriminalInjuriesCompensationAuthority', 'sample-cell-allocation', 'changed', 'private', 'internal', DATE '2026-08-11', NULL::varchar, 'scan'),
(900000080, 'ministryofjustice', 'sample-prison-app-v2', 'created', NULL::varchar, 'internal', DATE '2026-08-11', NULL::varchar, 'scan'),
(900000023, 'moj-analytical-services', 'sample-crime-apply', 'changed', 'private', 'public', DATE '2026-08-12', NULL::varchar, 'scan'),
(900000060, 'ministryofjustice', 'sample-prototype-kit', 'changed', 'public', 'private', DATE '2026-08-12', NULL::varchar, 'scan'),
(900000045, 'ministryofjustice', 'sample-jury-summons', 'archived', NULL::varchar, NULL::varchar, DATE '2026-08-13', NULL::varchar, 'scan'),
(900000020, 'ministryofjustice', 'sample-prison-register', 'deleted', 'public', NULL::varchar, DATE '2026-08-14', NULL::varchar, 'scan'),
(900000078, 'ministryofjustice', 'asset-foxtrot', 'changed', 'internal', 'private', DATE '2026-08-17', NULL::varchar, 'scan'),
(900000053, 'ministryofjustice', 'sample-design-system', 'changed', 'public', 'internal', DATE '2026-08-17', NULL::varchar, 'scan'),
(900000054, 'ministryofjustice', 'sample-docs-site', 'changed', 'private', 'public', DATE '2026-08-17', NULL::varchar, 'scan'),
(900000027, 'moj-analytical-services', 'sample-laa-reporting', 'changed', 'public', 'internal', DATE '2026-08-17', NULL::varchar, 'scan'),
(900000073, 'ministryofjustice', 'asset-alpha', 'changed', 'public', 'private', DATE '2026-08-18', NULL::varchar, 'scan'),
(900000081, 'moj-analytical-services', 'sample-data-sharing-api', 'created', NULL::varchar, 'private', DATE '2026-08-18', NULL::varchar, 'scan'),
(900000029, 'ministryofjustice', 'sample-eligibility-checker', 'changed', 'internal', 'public', DATE '2026-08-18', NULL::varchar, 'scan'),
(900000046, 'moj-analytical-services', 'sample-fines-calculator', 'changed', 'private', 'internal', DATE '2026-08-18', NULL::varchar, 'scan'),
(900000060, 'ministryofjustice', 'sample-prototype-kit', 'changed', 'private', 'public', DATE '2026-08-18', NULL::varchar, 'scan'),
(900000031, 'moj-analytical-services', 'sample-laa-data-sync', 'deleted', 'public', NULL::varchar, DATE '2026-08-21', NULL::varchar, 'scan'),
(900000073, 'ministryofjustice', 'asset-alpha', 'changed', 'private', 'public', DATE '2026-08-25', NULL::varchar, 'scan'),
(900000003, 'ministryofjustice', 'sample-offender-events', 'changed', 'internal', 'public', DATE '2026-08-25', NULL::varchar, 'scan'),
(900000028, 'ministryofjustice', 'sample-claims-api', 'changed', 'public', 'internal', DATE '2026-08-26', NULL::varchar, 'scan'),
(900000048, 'moj-analytical-services', 'sample-court-store', 'changed', 'public', 'internal', DATE '2026-08-26', NULL::varchar, 'scan'),
(900000001, 'ministryofjustice', 'sample-prison-visits', 'changed', 'public', 'private', DATE '2026-08-26', NULL::varchar, 'scan'),
(900000082, 'ministryofjustice', 'sample-probation-notes', 'created', NULL::varchar, 'public', DATE '2026-08-26', NULL::varchar, 'scan'),
(900000008, 'moj-analytical-services', 'sample-release-planner', 'changed', 'internal', 'private', DATE '2026-08-26', NULL::varchar, 'scan'),
(900000063, 'moj-analytical-services', 'sample-wiki-export', 'deleted', 'public', NULL::varchar, DATE '2026-08-27', NULL::varchar, 'scan'),
(900000008, 'moj-analytical-services', 'sample-release-planner', 'archived', NULL::varchar, NULL::varchar, DATE '2026-08-28', NULL::varchar, 'scan'),
(900000044, 'ministryofjustice', 'sample-hearing-scheduler', 'changed', 'public', 'private', DATE '2026-08-31', NULL::varchar, 'scan'),
(900000059, 'ministryofjustice', 'sample-intranet', 'changed', 'public', 'internal', DATE '2026-08-31', NULL::varchar, 'scan'),
(900000065, 'ministryofjustice', 'sample-infra-terraform', 'changed', 'public', 'internal', DATE '2026-09-01', NULL::varchar, 'scan'),
(900000036, 'ministryofjustice', 'sample-sirius-ui', 'changed', 'private', 'internal', DATE '2026-09-01', NULL::varchar, 'scan'),
(900000028, 'ministryofjustice', 'sample-claims-api', 'changed', 'internal', 'private', DATE '2026-09-02', NULL::varchar, 'scan'),
(900000080, 'ministryofjustice', 'sample-prison-app-v2', 'changed', 'internal', 'public', DATE '2026-09-02', NULL::varchar, 'scan'),
(900000057, 'ministryofjustice', 'sample-release-bot', 'changed', 'private', 'public', DATE '2026-09-02', NULL::varchar, 'scan'),
(900000083, 'ministryofjustice', 'sample-tribunal-bundle', 'created', NULL::varchar, 'internal', DATE '2026-09-03', NULL::varchar, 'scan'),
(900000051, 'ministryofjustice', 'sample-divorce-app', 'deleted', 'public', NULL::varchar, DATE '2026-09-04', NULL::varchar, 'scan'),
(900000044, 'ministryofjustice', 'sample-hearing-scheduler', 'changed', 'private', 'public', DATE '2026-09-07', NULL::varchar, 'scan'),
(900000072, 'CriminalInjuriesCompensationAuthority', 'sample-old-case-viewer', 'changed', 'public', 'internal', DATE '2026-09-07', NULL::varchar, 'scan'),
(900000014, 'moj-analytical-services', 'sample-resettlement-hub', 'changed', 'public', 'internal', DATE '2026-09-07', NULL::varchar, 'scan'),
(900000081, 'moj-analytical-services', 'sample-data-sharing-api', 'changed', 'private', 'internal', DATE '2026-09-08', NULL::varchar, 'scan'),
(900000049, 'CriminalInjuriesCompensationAuthority', 'sample-family-mediation', 'changed', 'public', 'private', DATE '2026-09-08', NULL::varchar, 'scan'),
(900000061, 'moj-analytical-services', 'sample-analytics-dash', 'changed', 'internal', 'private', DATE '2026-09-09', NULL::varchar, 'scan'),
(900000064, 'ministryofjustice', 'sample-helm-charts', 'changed', 'private', 'public', DATE '2026-09-09', NULL::varchar, 'scan'),
(900000065, 'ministryofjustice', 'sample-infra-terraform', 'changed', 'internal', 'public', DATE '2026-09-09', NULL::varchar, 'scan'),
(900000084, 'ministryofjustice', 'sample-lpa-store', 'created', NULL::varchar, 'private', DATE '2026-09-10', NULL::varchar, 'scan'),
(900000056, 'ministryofjustice', 'sample-status-page', 'archived', NULL::varchar, NULL::varchar, DATE '2026-09-10', NULL::varchar, 'scan'),
(900000022, 'ministryofjustice', 'sample-civil-apply', 'changed', 'internal', 'public', DATE '2026-09-14', NULL::varchar, 'scan'),
(900000050, 'ministryofjustice', 'sample-civil-money-claims', 'changed', 'public', 'private', DATE '2026-09-14', NULL::varchar, 'scan'),
(900000033, 'ministryofjustice', 'sample-lpa-frontend', 'changed', 'private', 'public', DATE '2026-09-14', NULL::varchar, 'scan'),
(900000083, 'ministryofjustice', 'sample-tribunal-bundle', 'changed', 'internal', 'private', DATE '2026-09-15', NULL::varchar, 'scan'),
(900000023, 'moj-analytical-services', 'sample-crime-apply', 'changed', 'public', 'internal', DATE '2026-09-16', NULL::varchar, 'scan'),
(900000085, 'moj-analytical-services', 'sample-open-data-export', 'created', NULL::varchar, 'public', DATE '2026-09-16', NULL::varchar, 'scan'),
(900000007, 'ministryofjustice', 'sample-prisoner-money', 'changed', 'public', 'internal', DATE '2026-09-21', NULL::varchar, 'scan'),
(900000057, 'ministryofjustice', 'sample-release-bot', 'changed', 'public', 'private', DATE '2026-09-21', NULL::varchar, 'scan'),
(900000015, 'moj-analytical-services', 'sample-visits-booking', 'changed', 'internal', 'public', DATE '2026-09-21', NULL::varchar, 'scan'),
(900000028, 'ministryofjustice', 'sample-claims-api', 'changed', 'private', 'internal', DATE '2026-09-22', NULL::varchar, 'scan'),
(900000086, 'ministryofjustice', 'sample-court-api-v2', 'created', NULL::varchar, 'internal', DATE '2026-09-22', NULL::varchar, 'scan'),
(900000005, 'CriminalInjuriesCompensationAuthority', 'sample-parole-board', 'changed', 'internal', 'private', DATE '2026-09-22', NULL::varchar, 'scan'),
(900000001, 'ministryofjustice', 'sample-prison-visits', 'changed', 'private', 'public', DATE '2026-09-22', NULL::varchar, 'scan')
) AS v(github_id, org, name, event_type, from_visibility, to_visibility, occurred_on, actor, source)
WHERE NOT EXISTS (
  SELECT 1 FROM public.repository_stats_visibility_events e
  WHERE e.github_id = v.github_id AND e.event_type = v.event_type AND e.occurred_on = v.occurred_on
);

INSERT INTO public.assets (id, name, type, last_updated, data) VALUES
(2001, 'sample-2019-hackday', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-2019-hackday", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo 2019-hackday", "license": "mit"}, "access": {"teams_with_admin": ["team-2019-hackday"], "teams_with_admin_parents": [], "teams": ["team-2019-hackday"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2002, 'sample-adjudications', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-adjudications", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo adjudications", "license": "mit"}, "access": {"teams_with_admin": ["team-adjudications"], "teams_with_admin_parents": [], "teams": ["team-adjudications"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2003, 'sample-analytics-dash', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-analytics-dash", "visibility": "private", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo analytics-dash", "license": "mit"}, "access": {"teams_with_admin": ["team-analytics-dash"], "teams_with_admin_parents": [], "teams": ["team-analytics-dash"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2004, 'sample-cell-allocation', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-cell-allocation", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo cell-allocation", "license": "mit"}, "access": {"teams_with_admin": ["team-cell-allocation"], "teams_with_admin_parents": [], "teams": ["team-cell-allocation"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2005, 'sample-civil-apply', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-civil-apply", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo civil-apply", "license": "mit"}, "access": {"teams_with_admin": ["team-civil-apply"], "teams_with_admin_parents": [], "teams": ["team-civil-apply"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2006, 'sample-civil-money-claims', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-civil-money-claims", "visibility": "private", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo civil-money-claims", "license": "mit"}, "access": {"teams_with_admin": ["team-civil-money-claims"], "teams_with_admin_parents": [], "teams": ["team-civil-money-claims"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2007, 'sample-claims-api', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-claims-api", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo claims-api", "license": "mit"}, "access": {"teams_with_admin": ["team-claims-api"], "teams_with_admin_parents": [], "teams": ["team-claims-api"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2008, 'sample-cloud-costs', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-cloud-costs", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo cloud-costs", "license": "mit"}, "access": {"teams_with_admin": ["team-cloud-costs"], "teams_with_admin_parents": [], "teams": ["team-cloud-costs"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2009, 'sample-contract-work', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-contract-work", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo contract-work", "license": "mit"}, "access": {"teams_with_admin": ["team-contract-work"], "teams_with_admin_parents": [], "teams": ["team-contract-work"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2010, 'sample-court-api-v2', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-court-api-v2", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo court-api-v2", "license": "mit"}, "access": {"teams_with_admin": ["team-court-api-v2"], "teams_with_admin_parents": [], "teams": ["team-court-api-v2"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2011, 'sample-court-listings', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-court-listings", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo court-listings", "license": "mit"}, "access": {"teams_with_admin": ["team-court-listings"], "teams_with_admin_parents": [], "teams": ["team-court-listings"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2012, 'sample-court-store', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-court-store", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo court-store", "license": "mit"}, "access": {"teams_with_admin": ["team-court-store"], "teams_with_admin_parents": [], "teams": ["team-court-store"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2013, 'sample-court-to-custody', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-court-to-custody", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo court-to-custody", "license": "mit"}, "access": {"teams_with_admin": ["team-court-to-custody"], "teams_with_admin_parents": [], "teams": ["team-court-to-custody"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2014, 'sample-crime-apply', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-crime-apply", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo crime-apply", "license": "mit"}, "access": {"teams_with_admin": ["team-crime-apply"], "teams_with_admin_parents": [], "teams": ["team-crime-apply"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2015, 'sample-crime-apply-v2', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-crime-apply-v2", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo crime-apply-v2", "license": "mit"}, "access": {"teams_with_admin": ["team-crime-apply-v2"], "teams_with_admin_parents": [], "teams": ["team-crime-apply-v2"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2016, 'sample-custody-tracker', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-custody-tracker", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo custody-tracker", "license": "mit"}, "access": {"teams_with_admin": ["team-custody-tracker"], "teams_with_admin_parents": [], "teams": ["team-custody-tracker"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2017, 'sample-data-sharing-api', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-data-sharing-api", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo data-sharing-api", "license": "mit"}, "access": {"teams_with_admin": ["team-data-sharing-api"], "teams_with_admin_parents": [], "teams": ["team-data-sharing-api"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2018, 'sample-deputy-reporting', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-deputy-reporting", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo deputy-reporting", "license": "mit"}, "access": {"teams_with_admin": ["team-deputy-reporting"], "teams_with_admin_parents": [], "teams": ["team-deputy-reporting"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2019, 'sample-design-system', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-design-system", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo design-system", "license": "mit"}, "access": {"teams_with_admin": ["team-design-system"], "teams_with_admin_parents": [], "teams": ["team-design-system"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2020, 'sample-divorce-app', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-divorce-app", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo divorce-app", "license": "mit"}, "access": {"teams_with_admin": ["team-divorce-app"], "teams_with_admin_parents": [], "teams": ["team-divorce-app"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2021, 'sample-docs-site', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-docs-site", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo docs-site", "license": "mit"}, "access": {"teams_with_admin": ["team-docs-site"], "teams_with_admin_parents": [], "teams": ["team-docs-site"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2022, 'sample-eligibility-checker', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-eligibility-checker", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo eligibility-checker", "license": "mit"}, "access": {"teams_with_admin": ["team-eligibility-checker"], "teams_with_admin_parents": [], "teams": ["team-eligibility-checker"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2023, 'sample-family-mediation', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-family-mediation", "visibility": "private", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo family-mediation", "license": "mit"}, "access": {"teams_with_admin": ["team-family-mediation"], "teams_with_admin_parents": [], "teams": ["team-family-mediation"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2024, 'sample-fee-calculator', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-fee-calculator", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo fee-calculator", "license": "mit"}, "access": {"teams_with_admin": ["team-fee-calculator"], "teams_with_admin_parents": [], "teams": ["team-fee-calculator"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2025, 'sample-fines-calculator', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-fines-calculator", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo fines-calculator", "license": "mit"}, "access": {"teams_with_admin": ["team-fines-calculator"], "teams_with_admin_parents": [], "teams": ["team-fines-calculator"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2026, 'sample-form-builder', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-form-builder", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo form-builder", "license": "mit"}, "access": {"teams_with_admin": ["team-form-builder"], "teams_with_admin_parents": [], "teams": ["team-form-builder"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2027, 'sample-hale-platform', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-hale-platform", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo hale-platform", "license": "mit"}, "access": {"teams_with_admin": ["team-hale-platform"], "teams_with_admin_parents": [], "teams": ["team-hale-platform"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2028, 'sample-hearing-scheduler', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-hearing-scheduler", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo hearing-scheduler", "license": "mit"}, "access": {"teams_with_admin": ["team-hearing-scheduler"], "teams_with_admin_parents": [], "teams": ["team-hearing-scheduler"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2029, 'sample-helm-charts', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-helm-charts", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo helm-charts", "license": "mit"}, "access": {"teams_with_admin": ["team-helm-charts"], "teams_with_admin_parents": [], "teams": ["team-helm-charts"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2030, 'sample-incentives', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-incentives", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo incentives", "license": "mit"}, "access": {"teams_with_admin": ["team-incentives"], "teams_with_admin_parents": [], "teams": ["team-incentives"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2031, 'sample-infra-terraform', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-infra-terraform", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo infra-terraform", "license": "mit"}, "access": {"teams_with_admin": ["team-infra-terraform"], "teams_with_admin_parents": [], "teams": ["team-infra-terraform"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2032, 'sample-intranet', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-intranet", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo intranet", "license": "mit"}, "access": {"teams_with_admin": ["team-intranet"], "teams_with_admin_parents": [], "teams": ["team-intranet"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2033, 'sample-jury-summons', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-jury-summons", "visibility": "private", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo jury-summons", "license": "mit"}, "access": {"teams_with_admin": ["team-jury-summons"], "teams_with_admin_parents": [], "teams": ["team-jury-summons"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2034, 'sample-keyworker-ui', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-keyworker-ui", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo keyworker-ui", "license": "mit"}, "access": {"teams_with_admin": ["team-keyworker-ui"], "teams_with_admin_parents": [], "teams": ["team-keyworker-ui"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2035, 'sample-laa-data-sync', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-laa-data-sync", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo laa-data-sync", "license": "mit"}, "access": {"teams_with_admin": ["team-laa-data-sync"], "teams_with_admin_parents": [], "teams": ["team-laa-data-sync"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2036, 'sample-laa-reporting', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-laa-reporting", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo laa-reporting", "license": "mit"}, "access": {"teams_with_admin": ["team-laa-reporting"], "teams_with_admin_parents": [], "teams": ["team-laa-reporting"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2037, 'sample-legal-adviser-search', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-legal-adviser-search", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo legal-adviser-search", "license": "mit"}, "access": {"teams_with_admin": ["team-legal-adviser-search"], "teams_with_admin_parents": [], "teams": ["team-legal-adviser-search"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2038, 'sample-legal-aid-portal', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-legal-aid-portal", "visibility": "private", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo legal-aid-portal", "license": "mit"}, "access": {"teams_with_admin": ["team-legal-aid-portal"], "teams_with_admin_parents": [], "teams": ["team-legal-aid-portal"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2039, 'sample-log-shipper', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-log-shipper", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo log-shipper", "license": "mit"}, "access": {"teams_with_admin": ["team-log-shipper"], "teams_with_admin_parents": [], "teams": ["team-log-shipper"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2040, 'sample-lpa-api', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-lpa-api", "visibility": "private", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo lpa-api", "license": "mit"}, "access": {"teams_with_admin": ["team-lpa-api"], "teams_with_admin_parents": [], "teams": ["team-lpa-api"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2041, 'sample-lpa-frontend', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-lpa-frontend", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo lpa-frontend", "license": "mit"}, "access": {"teams_with_admin": ["team-lpa-frontend"], "teams_with_admin_parents": [], "teams": ["team-lpa-frontend"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2042, 'sample-lpa-store', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-lpa-store", "visibility": "private", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo lpa-store", "license": "mit"}, "access": {"teams_with_admin": ["team-lpa-store"], "teams_with_admin_parents": [], "teams": ["team-lpa-store"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2043, 'sample-case-insights', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-case-insights", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo case-insights", "license": "mit"}, "access": {"teams_with_admin": ["team-case-insights"], "teams_with_admin_parents": [], "teams": ["team-case-insights"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2044, 'sample-means-assessment', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-means-assessment", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo means-assessment", "license": "mit"}, "access": {"teams_with_admin": ["team-means-assessment"], "teams_with_admin_parents": [], "teams": ["team-means-assessment"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2045, 'sample-modernising-lpa', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-modernising-lpa", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo modernising-lpa", "license": "mit"}, "access": {"teams_with_admin": ["team-modernising-lpa"], "teams_with_admin_parents": [], "teams": ["team-modernising-lpa"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2046, 'sample-offender-events', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-offender-events", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo offender-events", "license": "mit"}, "access": {"teams_with_admin": ["team-offender-events"], "teams_with_admin_parents": [], "teams": ["team-offender-events"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2047, 'sample-old-case-viewer', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-old-case-viewer", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo old-case-viewer", "license": "mit"}, "access": {"teams_with_admin": ["team-old-case-viewer"], "teams_with_admin_parents": [], "teams": ["team-old-case-viewer"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2048, 'sample-open-data-export', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-open-data-export", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo open-data-export", "license": "mit"}, "access": {"teams_with_admin": ["team-open-data-export"], "teams_with_admin_parents": [], "teams": ["team-open-data-export"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2049, 'sample-opg-data-export', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-opg-data-export", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo opg-data-export", "license": "mit"}, "access": {"teams_with_admin": ["team-opg-data-export"], "teams_with_admin_parents": [], "teams": ["team-opg-data-export"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2050, 'sample-opg-metrics', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-opg-metrics", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo opg-metrics", "license": "mit"}, "access": {"teams_with_admin": ["team-opg-metrics"], "teams_with_admin_parents": [], "teams": ["team-opg-metrics"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2051, 'sample-ops-runbooks', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-ops-runbooks", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo ops-runbooks", "license": "mit"}, "access": {"teams_with_admin": ["team-ops-runbooks"], "teams_with_admin_parents": [], "teams": ["team-ops-runbooks"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2052, 'sample-parole-board', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-parole-board", "visibility": "private", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo parole-board", "license": "mit"}, "access": {"teams_with_admin": ["team-parole-board"], "teams_with_admin_parents": [], "teams": ["team-parole-board"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2053, 'sample-prison-app-v2', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-prison-app-v2", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo prison-app-v2", "license": "mit"}, "access": {"teams_with_admin": ["team-prison-app-v2"], "teams_with_admin_parents": [], "teams": ["team-prison-app-v2"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2054, 'sample-prison-education', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-prison-education", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo prison-education", "license": "mit"}, "access": {"teams_with_admin": ["team-prison-education"], "teams_with_admin_parents": [], "teams": ["team-prison-education"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2055, 'sample-prison-register', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-prison-register", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo prison-register", "license": "mit"}, "access": {"teams_with_admin": ["team-prison-register"], "teams_with_admin_parents": [], "teams": ["team-prison-register"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2056, 'sample-prison-visits', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-prison-visits", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo prison-visits", "license": "mit"}, "access": {"teams_with_admin": ["team-prison-visits"], "teams_with_admin_parents": [], "teams": ["team-prison-visits"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2057, 'sample-prisoner-money', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-prisoner-money", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo prisoner-money", "license": "mit"}, "access": {"teams_with_admin": ["team-prisoner-money"], "teams_with_admin_parents": [], "teams": ["team-prisoner-money"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2058, 'sample-probate-frontend', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-probate-frontend", "visibility": "private", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo probate-frontend", "license": "mit"}, "access": {"teams_with_admin": ["team-probate-frontend"], "teams_with_admin_parents": [], "teams": ["team-probate-frontend"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2059, 'sample-probation-api', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-probation-api", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo probation-api", "license": "mit"}, "access": {"teams_with_admin": ["team-probation-api"], "teams_with_admin_parents": [], "teams": ["team-probation-api"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2060, 'sample-probation-notes', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-probation-notes", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo probation-notes", "license": "mit"}, "access": {"teams_with_admin": ["team-probation-notes"], "teams_with_admin_parents": [], "teams": ["team-probation-notes"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2061, 'sample-probation-search', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-probation-search", "visibility": "private", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo probation-search", "license": "mit"}, "access": {"teams_with_admin": ["team-probation-search"], "teams_with_admin_parents": [], "teams": ["team-probation-search"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2062, 'sample-prototype-kit', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-prototype-kit", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo prototype-kit", "license": "mit"}, "access": {"teams_with_admin": ["team-prototype-kit"], "teams_with_admin_parents": [], "teams": ["team-prototype-kit"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2063, 'sample-provider-payments', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-provider-payments", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo provider-payments", "license": "mit"}, "access": {"teams_with_admin": ["team-provider-payments"], "teams_with_admin_parents": [], "teams": ["team-provider-payments"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2064, 'sample-refunds', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-refunds", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo refunds", "license": "mit"}, "access": {"teams_with_admin": ["team-refunds"], "teams_with_admin_parents": [], "teams": ["team-refunds"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2065, 'sample-release-bot', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-release-bot", "visibility": "private", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo release-bot", "license": "mit"}, "access": {"teams_with_admin": ["team-release-bot"], "teams_with_admin_parents": [], "teams": ["team-release-bot"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2066, 'sample-release-planner', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-release-planner", "visibility": "private", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo release-planner", "license": "mit"}, "access": {"teams_with_admin": ["team-release-planner"], "teams_with_admin_parents": [], "teams": ["team-release-planner"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2067, 'sample-resettlement-hub', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-resettlement-hub", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo resettlement-hub", "license": "mit"}, "access": {"teams_with_admin": ["team-resettlement-hub"], "teams_with_admin_parents": [], "teams": ["team-resettlement-hub"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2068, 'sample-risk-assessment', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-risk-assessment", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo risk-assessment", "license": "mit"}, "access": {"teams_with_admin": ["team-risk-assessment"], "teams_with_admin_parents": [], "teams": ["team-risk-assessment"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2069, 'sample-security-scanner', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-security-scanner", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo security-scanner", "license": "mit"}, "access": {"teams_with_admin": ["team-security-scanner"], "teams_with_admin_parents": [], "teams": ["team-security-scanner"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2070, 'sample-sentence-calc', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-sentence-calc", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo sentence-calc", "license": "mit"}, "access": {"teams_with_admin": ["team-sentence-calc"], "teams_with_admin_parents": [], "teams": ["team-sentence-calc"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2071, 'sample-sirius-ui', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-sirius-ui", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo sirius-ui", "license": "mit"}, "access": {"teams_with_admin": ["team-sirius-ui"], "teams_with_admin_parents": [], "teams": ["team-sirius-ui"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2072, 'sample-staff-directory', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-staff-directory", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo staff-directory", "license": "mit"}, "access": {"teams_with_admin": ["team-staff-directory"], "teams_with_admin_parents": [], "teams": ["team-staff-directory"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2073, 'sample-status-page', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-status-page", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo status-page", "license": "mit"}, "access": {"teams_with_admin": ["team-status-page"], "teams_with_admin_parents": [], "teams": ["team-status-page"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2074, 'sample-temp-spike', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-temp-spike", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo temp-spike", "license": "mit"}, "access": {"teams_with_admin": ["team-temp-spike"], "teams_with_admin_parents": [], "teams": ["team-temp-spike"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2075, 'sample-tribunal-bundle', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-tribunal-bundle", "visibility": "private", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo tribunal-bundle", "license": "mit"}, "access": {"teams_with_admin": ["team-tribunal-bundle"], "teams_with_admin_parents": [], "teams": ["team-tribunal-bundle"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2076, 'sample-tribunal-forms', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-tribunal-forms", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo tribunal-forms", "license": "mit"}, "access": {"teams_with_admin": ["team-tribunal-forms"], "teams_with_admin_parents": [], "teams": ["team-tribunal-forms"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2077, 'sample-use-an-lpa', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-use-an-lpa", "visibility": "internal", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo use-an-lpa", "license": "mit"}, "access": {"teams_with_admin": ["team-use-an-lpa"], "teams_with_admin_parents": [], "teams": ["team-use-an-lpa"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2078, 'sample-visits-booking', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-visits-booking", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo visits-booking", "license": "mit"}, "access": {"teams_with_admin": ["team-visits-booking"], "teams_with_admin_parents": [], "teams": ["team-visits-booking"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2079, 'sample-wiki-export', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-wiki-export", "visibility": "public", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo wiki-export", "license": "mit"}, "access": {"teams_with_admin": ["team-wiki-export"], "teams_with_admin_parents": [], "teams": ["team-wiki-export"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}'),
(2080, 'sample-witness-portal', 'REPOSITORY', NOW(), '{"basic": {"name": "sample-witness-portal", "visibility": "private", "delete_branch_on_merge": null, "default_branch_name": "main", "description": "Sample repo witness-portal", "license": "mit"}, "access": {"teams_with_admin": ["team-witness-portal"], "teams_with_admin_parents": [], "teams": ["team-witness-portal"], "teams_parents": []}, "security_and_analysis": {"secret_scanning_status": "enabled", "push_protection_status": "enabled", "non_provider_patterns": "enabled"}, "default_branch_protection": {"allow_force_pushes": false, "enforce_admins": true, "require_code_owner_reviews": true}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.relationships (id, type, assets_id, owners_id, last_updated)
SELECT v.id, 'ADMIN_ACCESS', v.assets_id, o.id, NOW()
FROM (VALUES
(2002, 2002, 'HMPPS'),
(2003, 2003, 'Central Digital'),
(2004, 2004, 'HMPPS'),
(2005, 2005, 'LAA'),
(2006, 2006, 'HMCTS'),
(2007, 2007, 'LAA'),
(2009, 2009, 'LAA'),
(2010, 2010, 'HMCTS'),
(2011, 2011, 'HMCTS'),
(2012, 2012, 'HMCTS'),
(2013, 2013, 'HMPPS'),
(2014, 2014, 'LAA'),
(2015, 2015, 'LAA'),
(2016, 2016, 'HMPPS'),
(2018, 2018, 'OPG'),
(2019, 2019, 'Central Digital'),
(2020, 2020, 'HMCTS'),
(2021, 2021, 'Central Digital'),
(2022, 2022, 'LAA'),
(2023, 2023, 'HMCTS'),
(2024, 2024, 'LAA'),
(2025, 2025, 'HMCTS'),
(2026, 2026, 'Central Digital'),
(2027, 2027, 'Central Digital'),
(2028, 2028, 'HMCTS'),
(2030, 2030, 'HMPPS'),
(2032, 2032, 'Central Digital'),
(2033, 2033, 'HMCTS'),
(2034, 2034, 'HMPPS'),
(2035, 2035, 'LAA'),
(2036, 2036, 'LAA'),
(2037, 2037, 'LAA'),
(2038, 2038, 'LAA'),
(2040, 2040, 'OPG'),
(2041, 2041, 'OPG'),
(2042, 2042, 'OPG'),
(2043, 2043, 'HMPPS'),
(2044, 2044, 'LAA'),
(2045, 2045, 'OPG'),
(2046, 2046, 'HMPPS'),
(2048, 2048, 'Central Digital'),
(2049, 2049, 'OPG'),
(2050, 2050, 'OPG'),
(2052, 2052, 'HMPPS'),
(2053, 2053, 'HMPPS'),
(2054, 2054, 'HMPPS'),
(2055, 2055, 'HMPPS'),
(2056, 2056, 'HMPPS'),
(2057, 2057, 'HMPPS'),
(2058, 2058, 'HMCTS'),
(2059, 2059, 'HMPPS'),
(2060, 2060, 'HMPPS'),
(2061, 2061, 'HMPPS'),
(2062, 2062, 'Central Digital'),
(2063, 2063, 'LAA'),
(2064, 2064, 'OPG'),
(2065, 2065, 'Central Digital'),
(2066, 2066, 'HMPPS'),
(2067, 2067, 'HMPPS'),
(2068, 2068, 'HMPPS'),
(2070, 2070, 'HMPPS'),
(2071, 2071, 'OPG'),
(2072, 2072, 'Central Digital'),
(2073, 2073, 'Central Digital'),
(2075, 2075, 'HMCTS'),
(2076, 2076, 'HMCTS'),
(2077, 2077, 'OPG'),
(2078, 2078, 'HMPPS'),
(2079, 2079, 'Central Digital'),
(2080, 2080, 'HMCTS')
) AS v(id, assets_id, owner_name)
JOIN public.owners o ON o.name = v.owner_name
ON CONFLICT (id) DO NOTHING;

-- Teams for the Repository overview page. Each business unit gets two or three made-up
-- team slugs, some repositories have two teams, and some repositories with no business
-- unit have no team (they show under "No team"). The overview reads these from
-- assets.data access.teams_with_admin and access.teams. Only the stub assets
-- (ids 2001 to 2080) are changed, always to the same values, so re-running is safe.
UPDATE public.assets a
SET data = jsonb_set(
  a.data::jsonb,
  '{access}',
  jsonb_build_object(
    'teams_with_admin', to_jsonb(v.teams_with_admin),
    'teams_with_admin_parents', '[]'::jsonb,
    'teams', to_jsonb(v.teams),
    'teams_parents', '[]'::jsonb
  )
)::json
FROM (VALUES
(2001, ARRAY['data-team']::text[], ARRAY['data-team']::text[]),
(2002, ARRAY['service-team']::text[], ARRAY['service-team']::text[]),
(2003, ARRAY['platform-team']::text[], ARRAY['platform-team']::text[]),
(2004, ARRAY['platform-team']::text[], ARRAY['platform-team']::text[]),
(2005, ARRAY['apply-service-team']::text[], ARRAY['apply-service-team']::text[]),
(2006, ARRAY['courts-service-team']::text[], ARRAY['courts-service-team']::text[]),
(2007, ARRAY['payments-team']::text[], ARRAY['payments-team']::text[]),
(2008, ARRAY[]::text[], ARRAY[]::text[]),
(2009, ARRAY['operations-team']::text[], ARRAY['operations-team']::text[]),
(2010, ARRAY['courts-platform-team']::text[], ARRAY['courts-platform-team']::text[]),
(2011, ARRAY['courts-service-team']::text[], ARRAY['courts-service-team']::text[]),
(2012, ARRAY['courts-platform-team']::text[], ARRAY['courts-platform-team', 'courts-service-team']::text[]),
(2013, ARRAY['operations-team']::text[], ARRAY['operations-team']::text[]),
(2014, ARRAY['apply-service-team']::text[], ARRAY['apply-service-team', 'payments-team']::text[]),
(2015, ARRAY['payments-team']::text[], ARRAY['payments-team']::text[]),
(2016, ARRAY['service-team']::text[], ARRAY['service-team', 'platform-team']::text[]),
(2017, ARRAY['data-team']::text[], ARRAY['data-team']::text[]),
(2018, ARRAY['lpa-service-team']::text[], ARRAY['lpa-service-team']::text[]),
(2019, ARRAY['data-team']::text[], ARRAY['data-team']::text[]),
(2020, ARRAY['courts-service-team']::text[], ARRAY['courts-service-team']::text[]),
(2021, ARRAY['operations-team']::text[], ARRAY['operations-team']::text[]),
(2022, ARRAY['operations-team']::text[], ARRAY['operations-team']::text[]),
(2023, ARRAY['courts-platform-team']::text[], ARRAY['courts-platform-team']::text[]),
(2024, ARRAY['apply-service-team']::text[], ARRAY['apply-service-team']::text[]),
(2025, ARRAY['courts-service-team']::text[], ARRAY['courts-service-team']::text[]),
(2026, ARRAY['platform-team']::text[], ARRAY['platform-team', 'data-team']::text[]),
(2027, ARRAY['data-team']::text[], ARRAY['data-team']::text[]),
(2028, ARRAY['courts-platform-team']::text[], ARRAY['courts-platform-team', 'courts-service-team']::text[]),
(2029, ARRAY[]::text[], ARRAY[]::text[]),
(2030, ARRAY['platform-team']::text[], ARRAY['platform-team']::text[]),
(2031, ARRAY['data-team']::text[], ARRAY['data-team']::text[]),
(2032, ARRAY['operations-team']::text[], ARRAY['operations-team']::text[]),
(2033, ARRAY['courts-service-team']::text[], ARRAY['courts-service-team']::text[]),
(2034, ARRAY['operations-team']::text[], ARRAY['operations-team']::text[]),
(2035, ARRAY['payments-team']::text[], ARRAY['payments-team', 'operations-team']::text[]),
(2036, ARRAY['operations-team']::text[], ARRAY['operations-team']::text[]),
(2037, ARRAY['apply-service-team']::text[], ARRAY['apply-service-team']::text[]),
(2038, ARRAY['payments-team']::text[], ARRAY['payments-team']::text[]),
(2039, ARRAY[]::text[], ARRAY[]::text[]),
(2040, ARRAY['opg-platform-team']::text[], ARRAY['opg-platform-team']::text[]),
(2041, ARRAY['lpa-service-team']::text[], ARRAY['lpa-service-team']::text[]),
(2042, ARRAY['opg-platform-team']::text[], ARRAY['opg-platform-team', 'lpa-service-team']::text[]),
(2043, ARRAY['service-team']::text[], ARRAY['service-team']::text[]),
(2044, ARRAY['operations-team']::text[], ARRAY['operations-team', 'apply-service-team']::text[]),
(2045, ARRAY['lpa-service-team']::text[], ARRAY['lpa-service-team']::text[]),
(2046, ARRAY['platform-team']::text[], ARRAY['platform-team', 'operations-team']::text[]),
(2047, ARRAY['data-team']::text[], ARRAY['data-team']::text[]),
(2048, ARRAY['platform-team']::text[], ARRAY['platform-team']::text[]),
(2049, ARRAY['opg-platform-team']::text[], ARRAY['opg-platform-team']::text[]),
(2050, ARRAY['lpa-service-team']::text[], ARRAY['lpa-service-team']::text[]),
(2051, ARRAY[]::text[], ARRAY[]::text[]),
(2052, ARRAY['operations-team']::text[], ARRAY['operations-team']::text[]),
(2053, ARRAY['service-team']::text[], ARRAY['service-team']::text[]),
(2054, ARRAY['platform-team']::text[], ARRAY['platform-team']::text[]),
(2055, ARRAY['operations-team']::text[], ARRAY['operations-team', 'service-team']::text[]),
(2056, ARRAY['service-team']::text[], ARRAY['service-team']::text[]),
(2057, ARRAY['platform-team']::text[], ARRAY['platform-team']::text[]),
(2058, ARRAY['courts-platform-team']::text[], ARRAY['courts-platform-team']::text[]),
(2059, ARRAY['operations-team']::text[], ARRAY['operations-team']::text[]),
(2060, ARRAY['service-team']::text[], ARRAY['service-team', 'platform-team']::text[]),
(2061, ARRAY['platform-team']::text[], ARRAY['platform-team']::text[]),
(2062, ARRAY['data-team']::text[], ARRAY['data-team', 'operations-team']::text[]),
(2063, ARRAY['apply-service-team']::text[], ARRAY['apply-service-team']::text[]),
(2064, ARRAY['opg-platform-team']::text[], ARRAY['opg-platform-team', 'lpa-service-team']::text[]),
(2065, ARRAY['operations-team']::text[], ARRAY['operations-team']::text[]),
(2066, ARRAY['operations-team']::text[], ARRAY['operations-team']::text[]),
(2067, ARRAY['service-team']::text[], ARRAY['service-team']::text[]),
(2068, ARRAY['platform-team']::text[], ARRAY['platform-team', 'operations-team']::text[]),
(2069, ARRAY['data-team']::text[], ARRAY['data-team']::text[]),
(2070, ARRAY['operations-team']::text[], ARRAY['operations-team']::text[]),
(2071, ARRAY['lpa-service-team']::text[], ARRAY['lpa-service-team']::text[]),
(2072, ARRAY['platform-team']::text[], ARRAY['platform-team']::text[]),
(2073, ARRAY['data-team']::text[], ARRAY['data-team']::text[]),
(2074, ARRAY[]::text[], ARRAY[]::text[]),
(2075, ARRAY['courts-service-team']::text[], ARRAY['courts-service-team']::text[]),
(2076, ARRAY['courts-platform-team']::text[], ARRAY['courts-platform-team', 'courts-service-team']::text[]),
(2077, ARRAY['opg-platform-team']::text[], ARRAY['opg-platform-team']::text[]),
(2078, ARRAY['service-team']::text[], ARRAY['service-team']::text[]),
(2079, ARRAY['operations-team']::text[], ARRAY['operations-team', 'platform-team']::text[]),
(2080, ARRAY['courts-service-team']::text[], ARRAY['courts-service-team']::text[])
) AS v(id, teams_with_admin, teams)
WHERE a.id = v.id AND a.id BETWEEN 2001 AND 2080;

-- One successful run of the visibility job, so the pages show "Last updated: <date> at
-- 1:04pm" (12:04 UTC is 1:04pm BST; 12:04pm in winter), on the day the database is created
-- once the dates are moved below. The real job adds a row each time it runs.
INSERT INTO public.repository_stats_job_runs (job_name, org, started_at, finished_at, status)
SELECT 'record_repository_visibility', NULL, TIMESTAMPTZ '2026-09-25 12:00:00+00', TIMESTAMPTZ '2026-09-25 12:04:00+00', 'success'
WHERE NOT EXISTS (
  SELECT 1 FROM public.repository_stats_job_runs WHERE job_name = 'record_repository_visibility'
);

-- Move the stub dates: the earliest snapshot goes to 2026-08-17 (the real baseline date,
-- from the visibility audit) and the latest to the day the database is created
-- (CURRENT_DATE). Dates between the two original snapshots (2026-08-01 to 2026-09-25) are
-- spread proportionally across the new window, so the weekly clusters keep their shape
-- and no event lands on or before 2026-08-17. Repository created_at and pushed_at use the
-- same mapping (time of day kept), so new-repository events still match created_at and
-- nothing is pushed after it was captured. Dates on or before 2026-08-01 (older
-- repositories, and every baseline pushed_at) stay as they are. Only stub rows
-- (github_id 900000000 to 900000999, and the stub job run above) are changed, and only on
-- the first load.
CREATE FUNCTION pg_temp.stub_repository_stats_move(d date) RETURNS date
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE
    WHEN d IS NULL OR d <= DATE '2026-08-01' THEN d
    WHEN d > DATE '2026-09-25' THEN d + (CURRENT_DATE - DATE '2026-09-25')
    ELSE DATE '2026-08-17' + greatest(
      1,
      round((d - DATE '2026-08-01') * (CURRENT_DATE - DATE '2026-08-17') / 55.0)::integer
    )
  END
$$;

DO $$
DECLARE
  v_last_snapshot_id integer;
  v_last_event_id integer;
BEGIN
  SELECT b.last_snapshot_id, b.last_event_id INTO v_last_snapshot_id, v_last_event_id
  FROM stub_repository_stats_before b;

  IF v_last_snapshot_id IS NOT NULL OR v_last_event_id IS NOT NULL THEN
    -- A re-run: the stub was loaded and moved before. The inserts above only add rows
    -- on the original dates, which no longer clash with the moved ones, so remove them.
    DELETE FROM public.repository_stats_visibility_snapshots
    WHERE github_id BETWEEN 900000000 AND 900000999 AND id > coalesce(v_last_snapshot_id, 0);
    DELETE FROM public.repository_stats_visibility_events
    WHERE github_id BETWEEN 900000000 AND 900000999 AND id > coalesce(v_last_event_id, 0);
    RETURN;
  END IF;

  IF CURRENT_DATE <= DATE '2026-08-17' THEN
    RAISE NOTICE 'Stub repository stats dates left as written: today is not after 2026-08-17';
    RETURN;
  END IF;

  -- Latest first: today is after 2026-08-17, so neither move clashes with
  -- (github_id, captured_on) rows that haven't moved yet.
  UPDATE public.repository_stats_visibility_snapshots
  SET captured_on = CURRENT_DATE
  WHERE github_id BETWEEN 900000000 AND 900000999 AND captured_on = DATE '2026-09-25';
  UPDATE public.repository_stats_visibility_snapshots
  SET captured_on = DATE '2026-08-17'
  WHERE github_id BETWEEN 900000000 AND 900000999 AND captured_on = DATE '2026-08-01';

  UPDATE public.repository_stats_visibility_snapshots
  SET created_at = pg_temp.stub_repository_stats_move(created_at::date) + created_at::time,
      pushed_at = pg_temp.stub_repository_stats_move(pushed_at::date) + pushed_at::time
  WHERE github_id BETWEEN 900000000 AND 900000999;

  UPDATE public.repository_stats_visibility_events
  SET occurred_on = pg_temp.stub_repository_stats_move(occurred_on)
  WHERE github_id BETWEEN 900000000 AND 900000999;

  UPDATE public.repository_stats_job_runs
  SET started_at = started_at + make_interval(days => CURRENT_DATE - DATE '2026-09-25'),
      finished_at = finished_at + make_interval(days => CURRENT_DATE - DATE '2026-09-25')
  WHERE job_name = 'record_repository_visibility'
    AND started_at = TIMESTAMPTZ '2026-09-25 12:00:00+00'
    AND finished_at = TIMESTAMPTZ '2026-09-25 12:04:00+00';
END
$$;

-- Team access as the visibility job records it (repository_stats_team_access), built from
-- the made-up team slugs given to the stub assets above, so the Repository overview shows
-- the same teams. Display names come from the slug (platform-team -> "Platform team").
-- Matched to each stub repository's github_id by name; admin where the team is in
-- teams_with_admin, otherwise write. Re-runs add nothing (unique org/github_id/team).
INSERT INTO public.repository_stats_team_access
(org, github_id, team_slug, team_name, parent_team_slug, permission, recorded_at)
SELECT DISTINCT ON (s.github_id, t.slug)
  s.org,
  s.github_id,
  t.slug,
  upper(left(t.slug, 1)) || replace(substr(t.slug, 2), '-', ' '),
  NULL,
  CASE WHEN a.data::jsonb -> 'access' -> 'teams_with_admin' ? t.slug THEN 'admin' ELSE 'write' END,
  (SELECT max(finished_at) FROM public.repository_stats_job_runs
   WHERE job_name = 'record_repository_visibility' AND status = 'success')
FROM public.repository_stats_visibility_snapshots s
JOIN public.assets a ON a.name = s.name AND a.id BETWEEN 2001 AND 2080
CROSS JOIN LATERAL jsonb_array_elements_text(a.data::jsonb -> 'access' -> 'teams') AS t(slug)
WHERE s.github_id BETWEEN 900000000 AND 900000999
ORDER BY s.github_id, t.slug, s.captured_on DESC
ON CONFLICT ON CONSTRAINT uq_repository_stats_team_access_org_github_id_team_slug DO NOTHING;

-- Team access that maps to business units through the shared owners.config (the team
-- slugs in the owners migrations), so the pages show business units for repositories
-- with no shared ownership relationship, including internal, private and archived ones:
--   sample-helm-charts (private)      platforms admin           -> Platforms
--   sample-infra-terraform            modernisation-platform    -> Modernisation Platform
--   sample-log-shipper                log-shipping-team, child of technology-services
--                                                               -> Technology Services
--   sample-ops-runbooks (archived)    hmpps-developers admin    -> HMPPS
--   sample-data-sharing-api           opg                       -> OPG
-- Re-runs add nothing (unique org/github_id/team).
INSERT INTO public.repository_stats_team_access
(org, github_id, team_slug, team_name, parent_team_slug, permission, recorded_at)
SELECT s.org, t.github_id, t.slug, t.team_name, t.parent_slug, t.permission,
  (SELECT max(finished_at) FROM public.repository_stats_job_runs
   WHERE job_name = 'record_repository_visibility' AND status = 'success')
FROM (VALUES
  (900000064, 'platforms', 'Platforms', NULL, 'admin'),
  (900000065, 'modernisation-platform', 'Modernisation Platform', NULL, 'write'),
  (900000066, 'log-shipping-team', 'Log shipping team', 'technology-services', 'write'),
  (900000066, 'technology-services', 'Technology Services', NULL, 'read'),
  (900000069, 'hmpps-developers', 'HMPPS Developers', NULL, 'admin'),
  (900000081, 'opg', 'OPG', NULL, 'write')
) AS t(github_id, slug, team_name, parent_slug, permission)
JOIN LATERAL (
  SELECT org FROM public.repository_stats_visibility_snapshots
  WHERE github_id = t.github_id ORDER BY captured_on DESC LIMIT 1
) s ON true
ON CONFLICT ON CONSTRAINT uq_repository_stats_team_access_org_github_id_team_slug DO NOTHING;

-- Organisation display names, as the visibility job records them from GET /orgs/{org}.
-- The Repository overview shows these instead of the login. Re-runs keep existing rows.
INSERT INTO public.repository_stats_organisations (login, display_name, updated_at) VALUES
('ministryofjustice', 'Ministry of Justice', NOW()),
('moj-analytical-services', 'MoJ Analytical Services', NOW()),
('CriminalInjuriesCompensationAuthority', 'Criminal Injuries Compensation Authority', NOW())
ON CONFLICT (login) DO NOTHING;
