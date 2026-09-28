# Acceptance evidence matrix

Updated 2026-09-28 13:38 UTC. **Partial build, not release complete.** Stable checkpoint `387648a`; review issues, external imports and pagination are subsequent verified working-tree changes. No live provider or real email test passed. Partial evidence does not waive the remaining criterion.

Latest checks: 88 unit tests, 42 integration tests; browser passed in34.7s including customer import and actual-versus-qualified inventory counts, pagination and search. Full `pnpm check` passed formatting, lint, TypeScript, production build and generated contracts. Occupied-port launcher test and actual HTTP readiness passed.

Evidence references: API = `services/backend/tests/integration/test_api_security.py`; DB = `test_isolation.py`; worker = `test_worker_failures.py`; science = `services/backend/tests/unit/test_science_exports.py`; SDK = `test_providers.py`; browser = `tests/e2e/journey.spec.ts`. Private evidence artifacts live under `artifacts/test-runs/`.

| Requirement | Actual status | Evidence / remaining gate |
| --- | --- | --- |
| F-ENG01 | Passed | API session expiry/idle/revocation; signed issuer/audience/nonce/expiry/signature/unsigned negatives; invalid/reused state; real OIDC browser logins. |
| F-ENG02 | Partial | Scoped list/detail/artifact/review/graph/export substitutions and DB RLS passed; exhaustive mutation/job/resume matrix remains. |
| F-ENG03 | Partial | Direct API Sales/Admin content denial and Sales import denial passed; exhaustive role/mutation matrix remains. |
| F-ENG04 | Partial | CSRF/Origin negatives passed; exhaustive authenticated GET side-effect audit remains. |
| F-ENG05 | Passed | Stale412, replay and changed-body conflict; browser duplicate launch and external receipt replay. |
| F-ENG06 | Partial | Immutable revisions, successor and old-report download invalidation passed; all source/rubric/model/prompt dependency permutations remain. |
| F-ENG07 | Partial | Distinct author/review/adjudicator/sender identities enforced; exhaustive multi-role negatives and real paid quorum absent. |
| F-ENG08 | Passed | Non-owner cross-project FKs, missing tenant context and same-connection context reset. |
| F-ENG09 | Passed | Case dry-run, row errors, atomic commit, repeat deduplication and quarantine rejection. |
| F-ENG10 | Passed for fail-closed intake | Executable/macro/MIME/path/bomb fixtures remain quarantined without parsing; oversized requests rejected before storage. General scanner unavailable. |
| F-ENG11 | Partial | Original hashes/immutable versions preserved; derivative/faculty-review workflow absent. |
| F-ENG12 | Partial / live blocked | Local rights revocation blocks exports; complete external processing/expiry/training/redistribution workflow absent. |
| F-ENG13 | Partial | Missing/duplicate/cross-source inputs and unsupported modes rejected; full missing rubric/calibration matrix remains. |
| F-ENG14 | Partial | Source/task/family/episode counts distinct; complete related-variant split fixture matrix remains. |
| F-ENG15 | Partial | Actor-only resolver, strict SDK schemas and minimal checkpoint state; exhaustive log/graph leakage audit remains. |
| F-ENG16 | Passed | Actual LangGraph fixture journey: 3 pass/3 fail, mean85, one invocation each; illustrative exports. |
| F-ENG17 | Blocked / implementation partial | Exact real models, keys, budget, rights and independent paid approvals absent. Seeded approvals denied; no live dispatch claimed. |
| F-ENG18 | Partial | Concurrent reservation ceiling, unknown retention and idempotent reconciliation passed; no live launch integration. |
| F-ENG19 | Partial | Actual review-time worker restart passed; full dispatch crash-window matrix absent. |
| F-ENG20 | Partial | Stale fencing token denied; expired-token race/provider reconciliation remain. |
| F-ENG21 | Partial | Durable normal/adjudicated/invalidity review resumes without reinvocation; exhaustive duplicate/stale/wrong-project resume negatives remain. |
| F-ENG22 | Partial | Strict review schemas and server-constructed resume state; adversarial checkpoint/cancelled-resume matrix remains. |
| F-ENG23 | Partial | Unsupported graph version produces operational invalidity/no invocation; full recursion/time/token exhaustion matrix remains. |
| F-ENG24 | Partial | Fixture cancellation and imported unknown/unscorable preservation passed; no live cancellation claim. |
| F-ENG25 | Passed for available adapters | SDK cost absent remains null; separate ledger amounts; external costs unverified. |
| F-ENG26 | Passed | Strict weights, five anchors, calibration and missing-dimension rejection. |
| F-ENG27 | Passed | 6000/4000 at4/2 gives80; critical override and threshold85 fail. |
| F-ENG28 | Passed locally | Blinded second review, deliberate dispute and third adjudicator; imported model/source scores omitted from review response. |
| F-ENG29 | Partial | Ambiguous-reference flag, return-to-review and independent invalid/null-score resolution passed; dedicated valid-alternative exercise remains. |
| F-ENG30 | Passed | Zero denominator, unknown/invalid/cancelled separation and real imported score0/unscorable/unknown rendered report. |
| F-ENG31 | Passed locally | Immutable import receipts, actual durable review, separate source scores, origin-preserving PDF/HTML/email/ZIP; no invented traces or invocations. General uploaded outputs scanner-blocked. |
| F-ENG32 | Partial | Deterministic caveats and renderer; comprehensive claim/evidence registry absent. |
| F-ENG33 | Partial | Snapshot/replay generation and acknowledge-after-success; explicit out-of-order/failed-gap stress test remains. |
| F-ENG34 | Partial | Bounded scoped neighborhood and immediate canonical withdrawal passed; exhaustive every-hop visibility remains. |
| F-ENG35 | Passed | Actual Neo4j stop/fallback/start/rebuild with unchanged canonical score checksum. |
| F-ENG36 | Passed | Rebuild/replay and expected node/edge/hash comparison; PostgreSQL canonical. |
| F-ENG37 | Partial | ZIP allowlist, no raw references/internal brief, escaped HTML and fixed safe paths; exhaustive formula/path/secret matrix remains. |
| F-ENG38 | Passed for report path | Sharing revocation and draft successor block old download; old revisions retained. |
| F-ENG39 | Passed | Schema007 backup restored664 checkpoints/373 artifact checksums/3 pending reviews. Copied review resumed without reinvocation or original mutation; isolated restored graph rebuilt61 nodes/39 edges with matching hashes. |
| F-ENG40 | Partial | Independent locks/build, no sibling dependencies; clean isolated checkout acceptance remains. |
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

P1 inventory test passed200 synthetic source records, zero published-task sources, cursor uniqueness and full-inventory search. Thirty sequential ASGI+PostgreSQL samples measured list/detail p95 about31/19ms on15 CPU cores/24GiB RAM. This excludes browser/network latency. Related source versions,400-episode batch and full restart-recovery performance remain **not run**. Evidence: `artifacts/test-runs/inventory-performance.json`. CI configuration is local source only, not remotely executed. Historical prior-window results remain in [morning-report.md](morning-report.md); the final continuation handoff will replace that report with a dated current result.
