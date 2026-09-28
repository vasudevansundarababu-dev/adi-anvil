# ADI Anvil — current local handoff

## Marketing update — 28 September 2026, 20:20 UTC

The registered 12-week workflow is implemented and mock-verified. **Paid launch remains
blocked as the user requested:** no local API key and no two real Admin approvers are
ready. Follow [the marketing walkthrough](../runbooks/marketing-live.md) for task import,
qualification, provider configuration, local key setup and the exact-run approval controls.

- `pnpm check`: passed lint, types, production build and generated OpenAPI.
- `pnpm test:unit`:116 passed.
- `pnpm test:e2e`:3 passed,47.3s total, including marketing preparation and blocked launch.
- `pnpm test:integration`:66 passed,37.71s; includes full13-response mocked worker execution,
  independent review, preserved ambiguous dispatch and captured-response recovery.
- Fresh/repeated migrations001–016 passed within the isolated marketing integration test.
- Evidence: `artifacts/test-runs/marketing-mock.json`, `marketing-readiness.png` (inspected).
- No live inference, real paid approvals or real sending. Provider-account billing balance
  remains unknown; no paid model requests were made by this build.

The runtime bounds actor prompts, output tokens and call count; it never automatically
retries an uncertain generation. $1 reservations per call remain held, up to $13/run,
within the shared $100 authority. Operator references and future state stay out of actor
requests. Real identity onboarding, billing reconciliation, live verification and schema016
backup/restore remain outstanding. Other provider adapters and arbitrary imported-task
execution remain unavailable. This is not a complete-MVP or model-performance claim.

The new implementation session began19:38 UTC with a03:38 UTC outer deadline; it is
finishing early after verification. Prior diagnostic/recovery evidence below is historical.

## Earlier diagnostic handoff — 15:45 UTC

**The local synthetic diagnostic journey works end to end. Full MVP acceptance remains partial; live inference and real sending are unavailable.**

Verified source checkpoint: `0adfcd9` on `build/overnight-v1`, 28 September 2026. Local commits only. The user authorized continuation at11:24 UTC, with an outer deadline of19:24 UTC. This replaces the earlier10:52 handoff; its lint failures and missing local modules are no longer the current state.

## Open the working application

Open [the prepared three-case project](http://127.0.0.1:3202/p/ea1cc06d-3ad8-4e9c-8e89-87f27b2d2d82/objectives). The web/API/worker and main infrastructure are running. Credentials are in owner-only `.local/demo-accounts.md`; no passwords are included here.

The [current walkthrough](../runbooks/morning-walkthrough.md) maps MORN-01–08 to the built UI. It contains3 original synthetic cases/families, a reviewed6-episode run with3 passes/3 critical failures and mean85, plus a separate6-episode run awaiting manual review. These are scripted fixture assertions, not measured model performance or expert validation.

- Web: http://127.0.0.1:3202
- API health: http://127.0.0.1:8200/api/v1/health
- Keycloak: http://127.0.0.1:8180/realms/anvil
- PostgreSQL: loopback5542; Neo4j: loopback7475/7688.
- Screenshots and actual PDF/HTML/ZIP/email-draft/internal-brief downloads: `artifacts/morning-demo/`. The actual PDF was rendered and visually inspected as one readable A4 page.
- Restart: `pnpm services:up`, then `pnpm dev`. Stop the registered app with `pnpm stop`; restart only its worker with `pnpm worker:restart`. Preserve existing volumes and records.

## What works

Real Keycloak OIDC with opaque sessions, CSRF/Origin checks, independent local identities and project isolation; reviewed objectives; immutable source versions/receipts; manifest dry-run/commit/deduplication; local rights and expiry; version-bound readiness gaps; task/rubric qualification; frozen suites/protocols; actual LangGraph/PostgreSQL checkpoints; double grading, disputes and independent adjudication; invalid-reference resolution; cancellation and crash/restart recovery.

Diagnostics includes bounded case-family/capability/task/episode/finding relationships, keyboard selection and linked-record navigation. PostgreSQL is canonical; Neo4j is a versioned rebuildable cache. Actual transaction rollback, out-of-order generation, service outage/rebuild and restored-namespace tests passed.

Reports preserve origin and honest valid/pending/invalid/unscorable/unknown/cancelled denominators. A generated descriptive claim registry binds metrics to exact evidence IDs. Independent approvals gate actual PDF/HTML/ZIP/email draft exports. Successor versions and revoked rights block stale downloads. Sales can download approved kits without changing scientific facts. Network-free mail fixtures require independent sender/recipient/release approvals and never claim real delivery.

External-result import preserves producer-reported origin and configuration uncertainty, separates source scores from Anvil review, and uses durable review without calling a candidate. Aggregate-only and unknown executions cannot invent output or traces. General uploaded evidence remains quarantined.

Six provider adapters have mock SDK transport contracts, actor-only inputs and no automatic inference retry. Provider configuration/status is visible. Integer spending reservations, concurrent ceilings and unknown-cost retention are tested separately. This is **not an enabled or end-to-end-qualified live execution path**.

## Verification

| Exact command | Latest result |
| --- | --- |
| `pnpm check` | Passed Ruff, formatting, TypeScript, production webpack build and generated API contract. |
| `pnpm test:unit` |89 passed. Includes73 provider transport-contract cases. |
| `pnpm test:e2e` |1 comprehensive real-OIDC journey passed29.5s test/47.4s total. Includes11 identities, reviews/dispute/invalidity, rights/version invalidation, exports, fixture mail, intake, graph and responsive/keyboard checks. |
| `pnpm test:integration` |64 passed35.66s. Run sequentially after E2E because it consumes the saved journey. |
| `pnpm test:load` |400 fixture episodes from200 repeated variants of only3 sources/families;39.84s execution,232.4ms table readiness,1.18s first progress after worker restart, zero duplicate invocations. All400 human reviews pending. |
| `pnpm demo:walkthrough` |Prepared the clean project linked above, verified real downloads and left a separate practice run pending. |
| `services/backend/.venv/bin/python tests/migration_smoke.py` |Fresh and repeated migrations001–012 passed; retained database `anvil_migrationcheck_7050227e489a`. |
| `services/backend/.venv/bin/python tests/launcher_smoke.py` |Occupied port rejected without touching its listener, including on the clean checkout. |
| `services/backend/.venv/bin/python tests/graph_outage.py` |Actual Neo4j stop/fallback/start/rebuild passed; canonical score checksum unchanged. |
| `pnpm backup:local`, then `pnpm restore:test` |Schema012 backup restored to a new retained database; counts/checksums passed. |
| `services/backend/.venv/bin/python tests/restore_resume.py` |Copied pending review finalized using copied artifacts; invocation count and original episode unchanged. |
| `services/backend/.venv/bin/python tests/restore_graph.py` |174 nodes/169 edges rebuilt in a separate namespace; canonical hashes matched and live evidence unchanged. |
| `python3 scripts/secret_scan.py` |176 tracked files checked; zero findings. |
| `pnpm audit --prod --json` |Earlier same-lockfile audit: zero advisories across102 production dependencies. Python audit:84 listed dependencies, zero advisories; unpublished local package skipped. |
| `pnpm test:live` |Live verification blocked, not passed. No real model request was made. |
| Remote CI, cloud deployment, real email |Not run; no publication or external sending authorized. |

P1 inventory verification used200 synthetic source identities/400 immutable versions/100 families, with zero published-task sources. Thirty sequential in-process ASGI+PostgreSQL/Neo4j samples met list/detail500ms and graph2s targets. Exact timings/hardware are in `artifacts/test-runs/inventory-performance.json`; this is not browser/network latency or an expert case bank.

The [acceptance matrix](test-matrix.md) records requirement-level partial/blocked coverage. Remaining permutations are not silently marked passed.

## Independent startup and recovery

Clean archive `.local/clean-checkout-3e1ac27` installed locked JS/Python dependencies into new directories using package caches, without copying node_modules, virtualenvs or credentials. Explicit nonsecret `ANVIL_ENV=local WEB_ORIGIN=http://127.0.0.1:3202 ANVIL_FIXTURE_MODE=true` made its check/89 units pass. Initial attempts used the wrong uv cache or omitted required local configuration; these were test setup failures, corrected before passing.

Fresh bootstrap created new credentials and separate Compose project `adi-anvil-fresh-3e1ac27`. Explicit `docker compose --env-file .env -f infra/local/compose.yaml -p adi-anvil-fresh-3e1ac27 up -d --wait --wait-timeout 180`, followed by `pnpm db:migrate`, `pnpm seed:demo` and `pnpm dev`, passed. Its real-OIDC browser journey passed25.3s/47.8s. The first integration run exposed two tests relying on historical default-project fixtures; explicit prerequisites fixed them, and62 integrations passed29.12s. Those fixes are in0adfcd9. Later main-workspace hardening adds two more passing integrations.

The isolated app/services are now stopped with their volumes retained. The original services/app were restarted. No database or volume was reset, overwritten or deleted.

Latest rehearsed backup: `.local/backups/20260928T151725Z-3e32989f`, retained restore `anvil_restore_2f647051f0bc`:5,684 resources,1,291 episodes,373 assessments,462 imports,24 review issues/resolutions,42 external receipts,13 readiness items,4,856 checkpoints,846 pending reviews and1,898 artifact checksums. Later tests add records; these counts describe the snapshot, not the current entire database.

## Remaining work and authority gates

- Live provider activation, paid-scope/run approval and dispatch/reconciliation integration remain unqualified. Exact provider/model IDs, local secrets, reviewed processing rights, budget and genuine distinct-Admin approvals are also absent. Adding a key alone does not enable execution. No seeded identity can grant real paid authority.
- General clean-file scanning, nonfixture partner task qualification, faculty/derivative review, production invitation/member administration, complete structured rubric/task editing and full typed-detail/API baseline compatibility remain incomplete. Existing text draft/successor editing preserves bindings; it is not a full structured editor.
- The descriptive claim registry does not semantically validate arbitrary free-text conclusions. Independent human review remains required; no benchmark comparison, endorsement, human baseline, causal diagnosis or improvement claim is established.
- Fixture capture bounds are conservative UTF-8 byte and cooperative elapsed-time checks, not a provider tokenizer or hard process deadline. Broader execution and security permutations remain in the matrix.
- Real email/recipient-access checks and production identity/deployment qualification are unavailable. CI is local source only. This is not a production/research release acceptance claim.

Observed model-inference requests: **0**. Real email sent: **false**. Provider billed spend: **unknown/not queried**, not a reconciled zero-dollar bill. Synthetic ledger amounts are not actual spending.

Continue from BUILD-STATUS.md and preserve the verified checkpoint, prepared demo and retained evidence. Do not reset the repository or use local test identities to manufacture live authority.
