## Plan: Add Repository Standard Custom Property

Add repository standard as a derived value from existing maturity scoring, persist it internally with repository metadata, and write it back to GitHub custom properties in the same sync lifecycle. This reuses the current repository standards scoring logic and minimizes new decision points by mapping maturity levels directly to baseline/standard/exemplar.

**Steps**
1. Phase 1: Define derivation and payload contract.
2. Add a single mapping utility for maturity to property value in /workspaces/github-community/app/projects/repository_standards/config/repository_compliance_config.py or a small adjacent helper module so both internal persistence and GitHub write paths use the same source of truth.
3. Confirm behavior for maturity level 0: do not set property value (or explicitly clear), and document expected API behavior for unset state.
4. Define GitHub payload shape to send as a list of property objects containing property_name=repository-standard and value derived from maturity.
5. Phase 2: Add GitHub custom-property write capability.
6. Extend /workspaces/github-community/app/projects/repository_standards/clients/github_client.py with a repository custom property update method targeting the repository custom properties endpoint.
7. Extend /workspaces/github-community/app/projects/repository_standards/services/github_service.py with a service-level method that calls the new client method and isolates API payload construction from job orchestration.
8. Add error handling/logging strategy for write failures (continue processing next repository, emit actionable log context with repository name and status code text).
9. Phase 3: Add internal persistence of derived repository standard.
10. Extend repository metadata model in /workspaces/github-community/app/projects/repository_standards/models/repository_info.py to include a field for derived repository standard under basic metadata (or another stable top-level section), and ensure serialization/deserialization includes it.
11. Update the sync flow in /workspaces/github-community/app/projects/repository_standards/jobs/map_github_repositories_to_owners.py to compute derived standard per repository and persist it through existing update_asset_by_name calls.
12. Keep this derivation idempotent and deterministic so repeated runs do not cause divergent DB state.
13. Phase 4: Integrate compliance scoring with write-back.
14. In /workspaces/github-community/app/projects/repository_standards/jobs/map_github_repositories_to_owners.py, create or reuse RepositoryComplianceService within the job loop after asset update so maturity can be computed from stored repository view.
15. For each repository, map maturity to baseline/standard/exemplar and call GithubService custom-property setter.
16. Ensure ordering is: internal asset update first, then compliance lookup/derive, then GitHub property write, then relationship updates and stale cleanup.
17. Add guardrails for skipped repositories (archived/fork already filtered) and for missing compliance result.
18. Phase 5: Tests and regression coverage.
19. Extend /workspaces/github-community/test/test_app/test_jobs/test_map_github_repositories_to_owners.py to assert custom property write is invoked with expected value for admin and non-admin mapping scenarios.
20. Add unit tests for maturity mapping utility and edge case maturity 0 handling.
21. Add unit tests for GitHub client/service custom-property payload formatting and error propagation/handling.
22. Phase 6: Operational validation and rollout safety.
23. Validate in dev environment with a constrained repository subset (existing limit support) to observe GitHub API behavior and rate-limit impact.
24. Add logging counters (attempted updates, successful updates, failed updates, skipped updates) to make first rollout observable.
25. Verify repository standards pages continue rendering unchanged and no schema migration is needed because metadata is JSON-backed.

**Relevant files**
- /workspaces/github-community/app/projects/repository_standards/jobs/map_github_repositories_to_owners.py — orchestrator to compute and apply repository-standard per repository during sync.
- /workspaces/github-community/app/projects/repository_standards/services/repository_compliance_service.py — maturity computation source to reuse, avoid duplicate compliance logic.
- /workspaces/github-community/app/projects/repository_standards/config/repository_compliance_config.py — existing maturity constants and best location for shared maturity-to-standard mapping.
- /workspaces/github-community/app/projects/repository_standards/services/github_service.py — add service method for custom property updates and payload assembly.
- /workspaces/github-community/app/projects/repository_standards/clients/github_client.py — add low-level GitHub endpoint call for repository custom properties.
- /workspaces/github-community/app/projects/repository_standards/models/repository_info.py — add internal persisted field for derived repository standard and keep to_dict/from_dict consistent.
- /workspaces/github-community/test/test_app/test_jobs/test_map_github_repositories_to_owners.py — extend job behavior tests for write-back calls.

**Verification**
1. Run targeted job tests: pytest test/test_app/test_jobs/test_map_github_repositories_to_owners.py -v.
2. Run repository standards test subset (if present) to catch model/service regressions: pytest test/test_app -k repository_standards -v.
3. Execute dry run in dev with reduced repository limit and inspect logs for update counters and per-repo failures.
4. Validate at least one repo each for baseline, standard, exemplar gets expected payload and one failing repo (maturity 0) is skipped or cleared as designed.
5. Validate DB asset JSON now includes derived repository standard for processed repositories.

**Decisions**
- Included scope: write repository-standard to GitHub and persist derived value internally.
- Included scope: derive from existing maturity mapping 1 baseline, 2 standard, 3 exemplar.
- Excluded scope: UI changes to display property explicitly (unless later requested).
- Excluded scope: new relational schema/migration; use existing JSON metadata storage.

**Further Considerations**
1. GitHub API semantics for unsetting property at maturity 0: preferred approach is skip update unless explicit clearing is required by policy.
2. Write amplification risk for unchanged values: optional optimization is compare stored value before PATCH and skip if no change.
3. Retry strategy for transient GitHub write failures: follow existing rate-limit retry behavior and avoid duplicate writes where possible.
