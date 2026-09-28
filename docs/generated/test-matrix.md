# Acceptance evidence matrix

Updated 2026-09-28 14:44 UTC. **Partial build, not release complete.** Stable checkpoint `21fd458`; readiness ledger and expanded isolation checks are subsequent verified working-tree work. No live provider or real email test passed. Partial evidence does not waive the remaining criterion.

Latest checks:89 unit tests,52 integration tests; browser passed25.9s test/46.5s total including gap creation/resolution, draft/successor editing, Sales-role PDF download, customer import, inventory pagination and graph keyboard/responsive checks. Full `pnpm check` passed formatting, lint, TypeScript, production build and generated contracts. Fresh/repeated migrations001–010 passed. Occupied-port launcher test and actual HTTP readiness passed.

Evidence references: API = `services/backend/tests/integration/test_api_security.py`; DB = `test_isolation.py`; worker = `test_worker_failures.py`; science = `services/backend/tests/unit/test_science_exports.py`; SDK = `test_providers.py`; browser = `tests/e2e/journey.spec.ts`. Private evidence artifacts live under `artifacts/test-runs/`.

| Requirement | Actual status | Evidence / remaining gate |
| --- | --- | --- |
| F-ENG01 | Passed | API session expiry/idle/revocation; signed issuer/audience/nonce/expiry/signature/unsigned negatives; invalid/reused state; real OIDC browser logins. |
| F-ENG02 | Partial | Cross-project list/detail/draft/successor/submit/review/publish/freeze/withdraw/run/assessment/issue/export/artifact substitutions passed with unchanged foreign revisions; DB RLS passed. Full delivery/provider command matrix remains. |
| F-ENG03 | Partial | Direct API Sales/Admin content denial and Sales import denial passed; exhaustive role/mutation matrix remains. |
| F-ENG04 | Partial | CSRF/Origin negatives passed; exhaustive authenticated GET side-effect audit remains. |
| F-ENG05 | Passed | Stale412, replay and changed-body conflict; browser duplicate launch and external receipt replay. |
| F-ENG06 | Partial | Source imports preserve one identity and exact immutable version receipts; no inherited rights; author draft/successor UI, replay, historical approvals and old-report invalidation passed. Database run/episode/thread/graph bindings immutable. Full dependency permutations remain. |
| F-ENG07 | Partial | Distinct author/review/adjudicator/sender identities enforced; exhaustive multi-role negatives and real paid quorum absent. |
| F-ENG08 | Passed | Non-owner cross-project FKs, missing tenant context and same-connection context reset. |
| F-ENG09 | Passed | Case dry-run, row errors, atomic commit, repeat deduplication and quarantine rejection. |
| F-ENG10 | Passed for fail-closed intake | Executable/macro/MIME/path/bomb fixtures remain quarantined without parsing; oversized requests rejected before storage. General scanner unavailable. |
| F-ENG11 | Partial | Original hashes/immutable versions and exact-version readiness/gap history preserved. Gap UI and missing-input launch block passed; derivative/faculty-review workflow absent. |
| F-ENG12 | Partial / live blocked | Local operation/destination rights, expiry and revocation tested; dispatch/resume rechecks active author and rights. External processing/training/redistribution workflow absent. |
| F-ENG13 | Partial | Missing/duplicate/cross-source inputs, unresolved gaps, mismatched source origin and unsupported modes rejected; readiness cannot grant rights or replace evidence. Full missing rubric/calibration permutations remain. |
| F-ENG14 | Partial | Source/task/family/episode counts distinct; complete related-variant split fixture matrix remains. |
| F-ENG15 | Partial | Actor-only resolver, strict SDK schemas and minimal checkpoint state; exhaustive log/graph leakage audit remains. |
| F-ENG16 | Passed | Actual LangGraph fixture journey: 3 pass/3 fail, mean85, one invocation each; illustrative exports. |
| F-ENG17 | Blocked / implementation partial | Exact real models, keys, budget, rights and independent paid approvals absent. Seeded approvals denied; no live dispatch claimed. |
| F-ENG18 | Partial | Concurrent reservation ceiling, unknown retention and idempotent reconciliation passed; no live launch integration. |
| F-ENG19 | Passed for fixtures | Actual SIGKILL before invocation and after persisted output recovers without duplicate capture; review-time and400-episode worker restart passed. Paid dispatch/reconciliation remains blocked. |
| F-ENG20 | Passed for fixture guards | Stale and expired matching lease tokens denied; immutable episode/thread/run bindings tested under non-owner role. No provider reconciliation claim. |
| F-ENG21 | Partial | Durable normal/adjudicated/invalidity review resumes without reinvocation; exhaustive duplicate/stale/wrong-project resume negatives remain. |
| F-ENG22 | Partial | Strict review schemas and server-constructed resume state; adversarial checkpoint/cancelled-resume matrix remains. |
| F-ENG23 | Partial | Unsupported graph version produces operational invalidity/no invocation; full recursion/time/token exhaustion matrix remains. |
| F-ENG24 | Partial | Fixture cancellation and imported unknown/unscorable preservation passed; no live cancellation claim. |
| F-ENG25 | Passed for available adapters | SDK cost absent remains null; separate ledger amounts; external costs unverified. |
| F-ENG26 | Passed | Strict weights, five anchors, calibration and missing-dimension rejection. |
| F-ENG27 | Passed | 6000/4000 at4/2 gives80; critical override and threshold85 fail. |
| F-ENG28 | Passed locally | Blinded second review, deliberate dispute and third adjudicator; imported model/source scores omitted from review response. |
| F-ENG29 | Passed for scripted calibration | Differently named and worded valid MKT answer receives100/pass through independent review APIs and durable finalization. Ambiguous reference returns to review or independent invalid/null-score resolution. No expert reliability claim. |
| F-ENG30 | Passed | Zero denominator, unknown/invalid/cancelled separation and real imported score0/unscorable/unknown rendered report. |
| F-ENG31 | Passed locally | Immutable import receipts, actual durable review, separate source scores, origin-preserving PDF/HTML/email/ZIP; no invented traces or invocations. General uploaded outputs scanner-blocked. |
| F-ENG32 | Partial | Deterministic caveats and renderer; comprehensive claim/evidence registry absent. |
| F-ENG33 | Partial | Snapshot/replay generation and acknowledge-after-success; explicit out-of-order/failed-gap stress test remains. |
| F-ENG34 | Partial | Bounded scoped neighborhood, immediate canonical withdrawal and501 historical-edge starvation regression passed; exhaustive every-hop visibility remains. |
| F-ENG35 | Passed | Actual Neo4j stop/fallback/start/rebuild with unchanged canonical score checksum. |
| F-ENG36 | Passed | Rebuild/replay and expected node/edge/hash comparison; PostgreSQL canonical. |
| F-ENG37 | Partial | ZIP allowlist, no raw references/internal brief, escaped HTML and fixed safe paths; exhaustive formula/path/secret matrix remains. |
| F-ENG38 | Passed for report path | Sharing revocation and draft successor block old download; old revisions retained. |
| F-ENG39 | Passed | Schema009 backup restored2636 checkpoints/1049 artifact checksums/420 pending reviews into a retained new database. Copied-review resume passed without reinvocation; isolated graph rebuilt81 nodes/39 edges with matching hashes and unchanged live evidence. |
| F-ENG40 | Partial | Clean664703a archive installed JS/Python locks offline into independent directories; production check and88 units passed after explicit fixture test environment. Newest source and fresh infrastructure acceptance remain. |
| F-ENG41 | Partial | 320/768/1440 overflow/theme/keyboard checks and visual inspection passed; full task-level accessibility audit remains. |
| F-ENG42 | Passed for local boundary | Nonlocal/staging/wrong-origin startup tests reject bootstrap; mock-only SDK contracts; health/seed use local dependencies without inference. Remote CI execution remains untested. |
| F-SK01 | Passed for fixture path | Automatic unique provisional kit; pending metrics unset and no release authority. |
| F-SK02 | Partial | Auto-approved kit/idempotent manual build and successor/rights invalidation passed; all correction types remain. |
| F-SK03 | Passed | One A4 page, overflow rejection, logo/tagline; fixture/import PDF render and visual inspection. |
| F-SK04 | Passed for available evidence | Reviewed findings, fixture metrics, imported valid/unscorable/unknown denominators. |
| F-SK05 | Passed | Illustrative and partner/customer reported labels survive review/export; Sales has no scientific fact editing route. |
| F-SK06 | Partial | Fixed copy/report binding and attachment allowlist; exhaustive adversarial copy/leakage matrix remains. |
| F-SK07 | Passed for simulation | Exact recipient/sender/report/artifact approvals, distinct Admins, .invalid-only recipient and suppression. Real sender absent. |
| F-SK08 | Passed for simulation | Known duplicate replays; unknown/failed terminal, never labeled delivered/read. |
| F-SK09 | Passed | Network-free fixture mail; real sender disabled. |
| F-SK10 | Partial | Worker binding/rights/suppression rechecks; queued suppression tested; full rights/supersession queue permutations remain. |
| F-SK11 | Passed for tested outcomes | Provisional and negative score0/unscorable/unknown summaries remain candid. |
| F-SK12 | Blocked for real delivery | No localhost draft links; actual prospective-recipient access not configured/tested. |

P1 inventory test passed200 synthetic case identities/400 immutable versions/100 families, zero published-task sources, cursor uniqueness and full-inventory search. Thirty sequential ASGI+PostgreSQL samples measured list/detail p95 under500ms (latest exact values in `artifacts/test-runs/inventory-performance.json`) on15 CPU cores/24GiB RAM. This excludes browser/network latency.

`node tests/load_fixture_batch.mjs` passed200 repeated task variants from only3 independent cases/families and400 episodes:31.07s execution,267.8ms table readiness,1.22s first progress after worker restart, zero duplicate invocations. All400 human reviews remain pending; no model performance was measured. Evidence: `artifacts/test-runs/load-fixture-performance.json`, `load-run-console.png`. Throughput after the latest additional authorization checks has not been remeasured. CI configuration is local source only, not remotely executed. The final continuation handoff will replace the historical [morning report](morning-report.md).
