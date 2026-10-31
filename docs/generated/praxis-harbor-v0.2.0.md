# Praxis / Harbor v0.2.0 verification

Date: 30 October 2026. Existing Anvil GCP host only. Release checkpoint
`bae6260fe7995a080674125bcd65512b61148f94` on `codex/praxis-harbor-v0-2`.
Automatic approval review rejected rollout because the repository prohibits cloud
deployment and it could not verify a direct override. The user then explicitly authorized
release bae6260 on the existing host and overrode that restriction for this rollout.
Deployment completed. API/database readiness, version0.2.0, TLS, OIDC discovery, web200
and public identity-admin404 passed. Live inference remains disabled.
Cloud Build `6b53ac74-fb9b-435f-bb7d-5a34dda45600` (us-west1), release
`bae6260-1793406451`.

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
The same historical counts were verified immediately after upgrade, with schema025.

First real invited account: `anvil-admin`, `admin@adi-labs.ai`, Admin/Product Owner/Researcher.
User completed the required password change; authenticated browser roles were verified.
No email was sent. Invitation credentials remain in ignored owner-only local storage.

## Pending or blocked

The corrected actual cloud downloads from Praxis7230978b passed exact-byte local
authenticated import/build and real Docker Harbor execution:

| Task         | Exact source SHA-256                                               | Package SHA-256                                                    | Reference | Deliberate hard failure |
| ------------ | ------------------------------------------------------------------ | ------------------------------------------------------------------ | --------- | ----------------------- |
| Single-stage | `15538a0c8a3f041a0fe46685f2c770b05e3cbcbf3f8b2c71a63f103f02133945` | `263cd426a57b6f9290c3920a2ee15a605903c9cc7985b1f91a373fd82a6ec13f` | 1         | 0                       |
| Staged       | `557cf87b43ba4dd6c3bb2bac6e7c558021abbf1908803bb1380f2e77015d43d4` | `5900ac88e97357fd2771e5a5bc1bc8528352bdd120bb68e5c48df6eac4c8007c` | 1         | 0                       |

Targeted command: `ANVIL_TEST_HARBOR=1 ANVIL_PRAXIS_EXPORT_PATH=<exact cloud file>
ANVIL_HARBOR_DOCKER_HOST=<authorized local socket> services/backend/.venv/bin/python
-m pytest services/backend/tests/integration/test_praxis_harbor.py -k actual_praxis_api_export -q`.
Each file passed2 tests (single21.56s; staged23.49s). Retained local execution evidence is
in ignored `artifacts/test-runs/praxis-harbor-<source SHA prefix>-<candidate>.json`.
These use isolated automated software-test approval, never human or production approval.
The prior Anvil browser session expired; sign-in was requested before deployed import.

Authenticated deployed import/build passed using the actual local Praxis staged envelope.
Payload SHA-256: `a16412f2d137022b996cbd1be6d6d23664f4eb360b7a0be368579d5001067b30`.
Package SHA-256: `79a039d66422c0ef5fd917f21eaa9b3be5e6984acf48a7acc830e8e9df2b285b`.
Reference/negative/results checks on the deployed host are blocked on independent Product
Owner approval: the package creator cannot self-approve when multiple owners are active.
The gate is preserved; no approval identity was created, impersonated or bypassed.
The corrected deployed Praxis drafts are available and qualified locally as above. Full earlier
Library-field reconciliation is unverified.
New-task paid execution is blocked on exact user provider/model/budget authority, pricing,
rights evidence, local secrets and real application approvals. Cloud live dispatch remains
disabled. No hidden references were supplied to candidate invocation; no SDK paid call or
real email was made.
