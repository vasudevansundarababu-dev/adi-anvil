# Workspace execution handoff — 31 October2026

**The gated preparation-to-results path is implemented locally.** Source checkpoint
`c3d2eb1` on `codex/anvil-modern-workspace`; schema032. Overall platform acceptance remains
partial. Real provider access, exact-model compatibility and paid performance were not tested.
Classic comparison remains available and its branch stays pinned to
`3a17429c3e7bfe0314361dda5209ce890d96c8e3`. Nothing was deployed or pushed.

## What changed

Saved preparations now lead to **Create execution group**, computed readiness, exact rights/
Admin decision forms, explicit launch, sequential per-model execution, cancellation and
linked run dashboards. Existing task-level histories show frozen model/settings, rubric
labels/weights, actual captured call usage/errors and compatible metric comparisons.
Stage events show recorded times, request IDs, actor-context hashes, verified context
actually revealed at that intent and terminal captured outputs. Private grading bindings,
reference outputs, unrevealed future observations and hidden reasoning are not projected.

Group admission reuses existing Harbor plans/checks/jobs/calls and spending windows. One
aggregate cap is reserved atomically before durable child jobs are queued; replay/concurrent
launch cannot duplicate the reservation. Database claims require successful predecessors.
Failed, unknown and cancelled predecessors block later dispatch. Native OpenAI, Claude and
Gemini calls use only exact scoped credential versions in a guarded server broker, with
fixed endpoints, explicit limits, no global-key fallback, retries or redirects. No provider
credential enters Harbor, source packages, outputs, audit metadata or UI snapshots.

Exact authority, active rights/roles, current frozen model/key versions, pricing and compiled
code are rechecked before each stage. Intent commits before network I/O. Unknown outcomes
are never automatically retried; reservations are retained, including after cancellation.
Billing capture survives review/access revocation. Project-first lock ordering avoids
cancellation/result-capture inversion; a cancelled leased job with revoked rights preserves
terminal evidence and closes cleanly. Migration032 grants workers state-only visibility,
not access to private result columns. Stable error codes explain authorization/model/rate/
transport failures without retaining raw SDK exception bodies. Mock origin survives failures.

## How to continue in the app

Refresh [the local workspace](http://127.0.0.1:3202/workspace), open the saved preparation
and select **Create execution group**. The user's imported staged launch-allocation task
already has a saved preparation. Its old cap is blank: create another preparation with an
explicit budget before paid admission. If rates/terms/key bindings need a model-version
change, create a new preset selecting that version, then a new preparation/group.

[Open the existing preparation](http://127.0.0.1:3202/workspace/ea1cc06d-3ad8-4e9c-8e89-87f27b2d2d82/preparation?preparation=cd790b4f-1aca-4357-bc95-b65aef82b896).
The [execution walkthrough](../runbooks/workspace-execution.md) explains exact setup and
operator authority. Creation/saving makes no model request or reservation. Launch is
implemented but remains disabled until real exact authority, rights/reviews and runtime
activation are present. This build grants none of those decisions or spending authority.
Synthetic local accounts cannot provide paid approvals; no seeded identity was promoted.

## Verification and scope

| Check | Actual result |
| --- | --- |
| `pnpm check` | Final lint, formatting, types, production build and generated OpenAPI passed |
| `pnpm test:unit` |238 passed,4.10s; native request limits/parameters, secret echo suppression and DEBUG-log checks included |
| `ANVIL_TEST_HARBOR=1 ANVIL_HARBOR_DOCKER_HOST=unix:///Users/vasudevansundarababu/.docker/run/docker.sock pnpm test:integration` | Broader regression173 passed,2 optional Praxis-export skips,232.35s, before final narrow recovery/error-detail repair |
| Same environment, `services/backend/.venv/bin/python -m pytest services/backend/tests/integration/test_workspace_execution.py -q -x` | Final schema032 execution suite12 passed,51.90s; real staged Harbor with three native mocked providers, exact scope, concurrency, budget, revocation, unknown/no-retry and terminal recovery |
| `pnpm test:e2e` | Full16 browser journeys passed,2.5min; real OIDC, classic/modern, model versions, preset refresh, immutable preparation and group-readiness UI |
| `pnpm backup:local` / `pnpm restore:test` | SQL/artifact recovery passed; extended workspace digests/permissions matched |
| Staged whitespace and credential-pattern scan | Passed before source checkpoint; private artifacts/secrets excluded |

The complete all-module integration suite was not rerun after the last narrow worker/error
repair; its final relevant execution suite passed. Fresh and repeated001–032 migrations
are exercised in the isolated contracts. Two broad-suite skips need an external Praxis
export path not supplied. Existing Authlib/Alembic deprecations and browser color notices
are non-failing. No unresolved final test failure is being counted as a pass.

Earlier failures were repaired and rerun: isolated test-schema bootstrap, a test mistaking
public environment binding for private grading, rubric bytes-versus-model parsing, a
missing test import, conservative500/unknown expectation and SDK thinking-field casing.
One in-progress Docker run correctly stopped when source changed its admitted digest;
stable-code reruns passed. Formatting checks caught two final test/label formatting edits;
both were formatted and the full check passed. Read-only review drove the usage, authority,
lock ordering, mock-provenance and terminal-recovery repairs; no requirement was removed.

All native provider responses in tests were MockTransport software fixtures, not model
performance. Staged gateway tests expose only actual revealed context and retain outputs/
diagnostics; mock results are `native_sdk_mock_verification`, `model_performance=false`.
No real provider request was made. Build-incurred inference spend:0; provider-account billing
is **unknown/not queried**. These tests do not establish independent expert scoring validity.

Private evidence: `artifacts/test-runs/playwright.json`, `modern-execution-group-mobile.png`,
`modern-preparation-mobile.png`, `harbor-workbench.png` and existing modern/classic screenshots.
Execution-group mobile screenshot was visually inspected. Original MKT-001, FIN-001 and
STR-001 fixtures remain software scoring cases, not real model benchmark outcomes.

## Recovery, safety and remaining platform scope

Private backup `.local/backups/20261101T003814Z-462e688d` restored into the new retained
database `anvil_restore_a8f35c1740c5`:1213 pending reviews and6580 artifact checksums verified.
All12 workspace-table row digests matched at schema032, including1 group and2 child
bindings. State-only worker visibility was preserved and original data stayed unchanged.
This covers SQL/artifacts/metadata; local credential ciphertext/wrap-key files, environment
and Keycloak recovery remain **not tested**. No data reset, volume deletion or overwritten DB.

No SDK installation, real identity promotion, IAM change, cloud rollout, GitHub push or
external sending occurred. New contract-only identities exist in isolated retained test
databases; production/local-user identity grants were untouched. Unrelated AGENTS.md and
Google Cloud runbook edits were excluded. The app is left running with both live flags off
and the dedicated synthetic-only Harbor worker. Accounts remain in ignored
`.local/demo-accounts.md`; no credentials are included here.

Broader unfinished platform work remains: full People/profile permission management,
managed cloud credential storage, qualified LangSmith/Semantic Kernel external adapters,
general non-synthetic intake and explicit spend reconciliation. Exact returned-model IDs
and conservative usage remain strict; unsupported aliases/account features fail closed.
There is no automatic refund or unknown retry. Nightly work must retain these boundaries,
read BUILD-STATUS.md first and honor its22:00–06:00 America/Chicago window.
