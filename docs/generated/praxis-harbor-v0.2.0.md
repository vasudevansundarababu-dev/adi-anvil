# Praxis / Harbor v0.2.0 verification

Date: 30 October 2026. Existing Anvil GCP host only. Release rollout pending.

The increment imports the agreed single-stage and staged Praxis contracts, preserves exact
source/envelope receipts, compiles immutable Harbor packages, and retains check histories,
criterion diagnostics and artifacts. A separate Docker-host worker runs fixed compiler
templates. The workbench also prepares guarded structured-JSON agent plans; paid dispatch
for these tasks has not been authorized or exercised. Synthetic results are machinery
verification, never measured model performance.

## Passed

- `python3 scripts/local.py check`: production build, TypeScript, lint, formatting and
  generated OpenAPI contract.
- `python3 scripts/local.py unit`:174 tests, one existing Authlib deprecation warning.
- Full integration with `ANVIL_TEST_HARBOR=1`, actual staged Praxis envelope and local
  authorized Docker socket:89 tests,177.39s. Includes real Harbor reference/no-op/hard-failure,
  staged future/private isolation, non-root state protection, replay/reset, running
  cancellation, invocation fencing and an explicit stub gateway. Provider transport mocks
  and durable ledger tests verify bounded calls, no retries and held unknown reservations.
- `pnpm exec playwright test --grep-invert 'Praxis export to staged Harbor'`:6 baseline
  real-OIDC journeys,55.5s.
- `pnpm exec playwright test tests/e2e/harbor.spec.ts`: import/build, two real OIDC test
  identities, Product Owner software approval, reference reward1, retained reload and
  hard-failure reward0 with stage/criterion diagnostics,30.4s final test time. History labels
  refresh to succeeded. An explicit
  accessible selector and exact immutable source ID avoid ambiguous label selection.
- Fresh and repeated migrations001–025 in retained isolated migration database.
- Backend and dedicated Harbor Docker builds; worker CLI reports0.25.0.
- Shell syntax, diff whitespace and repository credential scan (no findings).
- Read-only release review found no critical deployment or isolation blocker. Repeated
  immutable rights reviews now explicitly require a new plan rather than reporting a
  silently ignored replacement.

Run database integration sequentially with the registered ordinary worker stopped. Initial
runs exposed expired mock-only spending dates, a test UUID/string mismatch and concurrent
audit/graph changes from browser/worker activity. The mock fixture was repaired without
extending real authority; sequential verification passed unchanged product assertions.

## Deployment and account

Target: `adi-anvil-mvp-2026/us-west1-a/anvil-mvp-v1`.
Web: https://anvil-34-36-217-66.sslip.io.
The user refreshed default GCP credentials; commands pin the Anvil project explicitly and
never read sibling credentials. Existing retained data snapshot is ready. Before upgrade:
4 revisions,3 artifacts,0 episodes,0 assessments. Data disk and volumes are preserved.

First real invited account: `anvil-admin`, `admin@adi-labs.ai`, Admin/Product Owner/Researcher.
User completed the required password change; authenticated browser roles were verified.
No email was sent. Invitation credentials remain in ignored owner-only local storage.

## Pending or blocked

Release commit, cloud rollout and post-upgrade preservation/
authenticated smoke are pending. Full earlier Library-field reconciliation is unverified.
New-task paid execution is blocked on exact user provider/model/budget authority, pricing,
rights evidence, local secrets and real application approvals. Cloud live dispatch remains
disabled. No hidden references were supplied to candidate invocation; no SDK paid call or
real email was made.
