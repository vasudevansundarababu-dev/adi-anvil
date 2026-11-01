# Two roles and separate execution-group pages

Implemented locally on `codex/anvil-modern-workspace`, following the user's
31 October decisions in [spec22](../product/22-TWO-ROLES-AND-EXECUTION-GROUP-JOURNEY.md).
The broader platform remains partial and has not been deployed by this change.

## Delivered

- Only Admin and RL Engineer are active project roles. Admin includes engineering.
  Migration033 archives earlier memberships, retains existing Admins, migrates other
  members to RL Engineer, and enforces one active role per person/project. Users,
  passwords, synthetic provenance, historical decisions and immutable bindings survive.
- Modern Admin Run records one exact model/key/task/price/terms/rights/budget
  authorization. No Product Owner, second Admin, external authority file or separate
  approval forms are required. Recent authentication, real identity, runtime readiness,
  exact versions and one aggregate reservation remain enforced. RL Engineers can run
  an already authorized group but cannot authorize new budget or manage credentials.
  Migration034 authorization/revocation records are immutable and project scoped.
- Execution groups has a separate newest-first paginated list, separate Create page,
  and separate group dashboard. Creation saves preparation/group records without
  dispatch or reservation, then opens the dashboard. Task Run links preselect the task.
  Saved preparation compatibility views remain read-only. Each started model has a
  run-dashboard link; existing task history, comparisons and exact snapshots remain.
- Admin software-check Run records its own exact-package authorization atomically.
  Current UI/help uses the two roles; legacy schema field names remain compatibility
  details. Private references remain individually assigned/owned. Run authors cannot
  read/submit their own independent grading; distinct grading/adjudication duties stay.
  A final API guard prevents self-assignment or hidden-as-actor relabeling from minting
  access to another person's private reference; preserved successor bindings remain usable.

## Verification and limitations

- `pnpm db:migrate`: schema034 applied locally. Fresh/repeated migrations also exercised
  by isolated execution tests. No existing seeded identity was made a real identity.
- `pnpm test:unit`: **242 passed**, including two-role permissions, invitation validation,
  exact persisted authorization bindings and run-author grading isolation.
- `ANVIL_TEST_HARBOR=1 ANVIL_HARBOR_DOCKER_HOST=unix:///Users/vasudevansundarababu/.docker/run/docker.sock pnpm test:integration`:
  **173 passed, one failed, two optional Praxis-export skips**. Failure was a retained-data
  test assuming a newly saved framework appeared in the first 100 rows. Corrected it to
  follow pagination; no product code was relaxed.
- Targeted follow-up for `test_workspace.py` and `test_workspace_access.py`: **8 passed**,
  covering that repaired failure and the added populated role-history protection check.
  Full integration was not repeated after this correction or the final private-binding
  API guard. Final privacy/editor/evaluation suites: **14 passed (6.83s)**; final
  `test_api_security.py`: **49 passed (44.09s)**. Real staged Docker
  Harbor with all three native SDK MockTransports passed in the full run. Mock outputs
  are explicitly not model-performance evidence; no paid provider request was sent.
- Initial full `pnpm test:e2e`: **14 passed, two failed** on a duplicate Create-page heading.
  Corrected the page heading; `pnpm test:e2e --last-failed`: **2 passed**. Final affected
  `pnpm test:e2e tests/e2e/workspace-preparation.spec.ts tests/e2e/harbor.spec.ts`:
  **5 passed (47.4s)**. Final `pnpm check` passed (lint/format, TypeScript, production build,
  generated OpenAPI). Final viewport screenshot visually inspected.
  After the final private-binding guard, `pnpm test:e2e tests/e2e/journey.spec.ts tests/e2e/workspace-preparation.spec.ts`:
  **3 passed (49.0s)**; final static check/build also passed after that guard.
  Browser coverage includes real OIDC, classic journey, Admin/engineer boundaries,
  import/build feedback, separate list/create/view, mobile overflow checks and dashboards.
- `pnpm backup:local` / `pnpm restore:test`: passed. Backup
  `.local/backups/20261101T013330Z-7f91c07a` restored into retained
  `anvil_restore_663b0942d410`: 1,236 pending reviews and 6,833 artifact checksums verified;
  original database unchanged. Schema034 and hashes of all 3 new role/authority tables
  match. Role history is populated with 3,146 rows; canonical authorization/revocation
  tables were empty, so this recovery check does not prove populated paid-authorization
  recovery. Credential files/wrap key, environment and Keycloak recovery remain not run.
- Paid smoke: **not run**. Both live flags remain disabled. Seeded test accounts are
  still synthetic; this is a runtime/identity constraint, not another approver role.

Classic routes and `codex/anvil-classic-v021-comparison` remain available. The comparison
branch stays at `3a17429c3e7bfe0314361dda5209ce890d96c8e3`. Unrelated AGENTS.md/cloud-runbook
edits are preserved. No cloud deployment, GitHub push, real email, IAM change, paid call,
new SDK install, destructive reset or credential disclosure occurred.

Read-only reviews checked role migration, current permissions, private-reference access,
exact Admin authority and classic compatibility. Local follow-up is review through
**Execution groups → Create → group dashboard → Run / run dashboard**. Remaining broader
work includes People management, managed cloud secrets, qualified external framework
adapters and spend reconciliation; no claim is made that these are complete.
