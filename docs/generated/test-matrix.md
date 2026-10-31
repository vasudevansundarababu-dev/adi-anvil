# Acceptance evidence matrix

30 October 2026 modern workspace build: scoped implementation on a separate branch.
Current feature evidence (full final counts in BUILD-STATUS.md):

| Requirement                                | Evidence                                                                     | Status / limit                                                          |
| ------------------------------------------ | ---------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| MOD-01 Preserve classic journey            | modern-workspace browser; baseline Git branch                                | Passed local comparison; no deployment                                  |
| MOD-02 Harbor and diagnostic task history | workspace and diagnostic integration; modern browser | Passed local all-version history, snapshots and finalized-only evidence |
| MOD-03 Honest run metrics / unknown cost | workspace and diagnostic units/integration | Finalized denominators, whole-run scope, frozen dataset counts; partial comparisons descriptive only |
| MOD-04 Bound evidence and project scope    | test_workspace integration                                                   | Passed RLS, role, bound artifact/classification/hash checks             |
| MOD-05 Multiple model/framework profiles   | test_workspace integration; modern-workspace browser                         | Persisted metadata passed; adapters/composition not all implemented     |
| MOD-06 Write-only local credentials        | test_workspace_secrets unit; test_workspace_credentials integration; browser | Local save/rotate/revoke passed; cloud writes disabled                  |
| MOD-07 No legacy key substitution          | test_workspace integration                                                   | New profiles blocked from unqualified legacy dispatch                   |
| MOD-08 Two-profile migration / full editor | No acceptance test yet                                                       | Not implemented; existing grants/history preserved                      |
| MOD-09 Paid live verification              | Not run                                                                      | No new paid authority or real keys supplied                             |

2026-09-29 ANV-BF-001 update:124 units,67 integrations and4 browser journeys pass;
production check and fresh/repeated001–017 migrations pass. See
[Factory report](ANV-BF-001-report.md) for requirement-specific limits. Task-profile
confirmation, exact deterministic ranking, visible hard exclusions, immutable
snapshot readback, access/rights rechecks, scope bounds, paired Suite version binding,
override rationale and gap drafts have direct test evidence in `test_factory.py`
(unit and integration) and `tests/e2e/factory.spec.ts`. This does not establish complete
ANV-REC-004 measured estimates, global cost-optimal ANV-REC-006, benchmark smoke release,
TaskBank profiling or100,000-task capacity. Prior matrices below are historical.

2026-09-28 20:20 UTC addition: `pnpm check`,116 units,66 integrations and3 browser
journeys pass. `test_marketing.py` uses an isolated mock database:13 dependent responses,
independent review/resume, durable intent/capture recovery, stale fencing, immutable
environment binding, actor/reference isolation and missing-paid-authority denial. The
browser verifies preparation through disabled paid launch. Fresh/repeated001–016 migrations
pass in that isolated test. No live provider or real Admin approval exercise passed;
real-person onboarding and billing reconciliation remain outstanding. The following
15:46 matrix retains earlier evidence and limitations; F-ENG12 now additionally has
an explicit OpenAI external-processing scope, and F-ENG17/18 have the guarded marketing
runtime and shared spending-window integration, verified only with a mock provider.

Updated 2026-09-28 15:46 UTC. **Local diagnostic slice verified; full acceptance partial, not release complete.** Verified source checkpoint `0adfcd9`. No live provider or real email test passed. Partial evidence does not waive the remaining criterion.

Latest checks:89 unit tests,64 integration tests; browser29.5s test/47.4s total including capability → task → episode → finding navigation, gaps, draft/successor editing, Sales PDF download, external import, pagination and responsive/keyboard checks. `pnpm check` passed. Fresh/repeated migrations001–012 passed. A separate fresh-service rehearsal passed startup, real-OIDC browser and62 integrations after explicit fixture-prerequisite repairs. `pnpm demo:walkthrough` prepared the clean three-case project and pending practice run.

Evidence references: API = `services/backend/tests/integration/test_api_security.py`; DB = `test_isolation.py`; worker = `test_worker_failures.py`; science = `services/backend/tests/unit/test_science_exports.py`; SDK = `test_providers.py`; browser = `tests/e2e/journey.spec.ts`. Private evidence artifacts live under `artifacts/test-runs/`.

| Requirement | Actual status | Evidence / remaining gate |
| --- | --- | --- |
| F-ENG01 | Passed | API session expiry/idle/revocation; signed issuer/audience/nonce/expiry/signature/unsigned negatives; invalid/reused state; real OIDC browser logins. |
| F-ENG02 | Passed for tested routes | Cross-project content commands, runs, reviews, exports, artifacts, provider approvals, contact decisions, sender activation, delivery approval/send/read substitutions passed with unchanged foreign records; DB RLS passed. |
| F-ENG03 | Partial | Content-role negatives and nine provider/delivery command classes across nine local identities passed; exhaustive content role/mutation permutations remain. |
| F-ENG04 | Passed for authenticated routes | CSRF/Origin negatives passed; list/detail/review/evidence/readiness/graph/provider/delivery/download GETs leave business tables unchanged. Exact access-audit append events are checked separately from session activity. |
| F-ENG05 | Passed | Stale412, replay and changed-body conflict; browser duplicate launch and external receipt replay. |
| F-ENG06 | Partial | Source imports preserve one identity and exact immutable version receipts; no inherited rights; author draft/successor UI, replay, historical approvals and old-report invalidation passed. Database run/episode/thread/graph bindings immutable. Full dependency permutations remain. |
| F-ENG07 | Passed locally / paid blocked | Disabled identities rejected; one synthetic identity with multiple content roles cannot fill separated objective/reviewer/adjudicator assignments. Distinct sender Admin required. Seeded paid approvals denied; real paid quorum absent. |
| F-ENG08 | Passed | Non-owner cross-project FKs, missing tenant context and same-connection context reset. |
| F-ENG09 | Passed | Case dry-run, row errors, atomic commit, repeat deduplication and quarantine rejection. |
| F-ENG10 | Passed for fail-closed intake | Executable/macro/MIME/path/bomb fixtures remain quarantined without parsing; oversized requests rejected before storage. General scanner unavailable. |
| F-ENG11 | Partial | Original hashes/immutable versions and exact-version readiness/gap history preserved. Gap UI and missing-input launch block passed; derivative/faculty-review workflow absent. |
| F-ENG12 | Partial / live blocked | Local operation/destination rights, expiry and revocation tested; dispatch/resume rechecks active author and rights. External processing/training/redistribution workflow absent. |
| F-ENG13 | Partial | Missing/duplicate/cross-source inputs, unresolved gaps, mismatched source origin and unsupported modes rejected; readiness cannot grant rights or replace evidence. Full missing rubric/calibration permutations remain. |
| F-ENG14 | Partial | Source/task/family/episode counts distinct; task cannot relabel source family or claim protected-test exposure for a known development fixture. Complete related-variant split matrix remains. |
| F-ENG15 | Partial | Actor-only resolver, strict SDK schemas and minimal checkpoint state; exhaustive log/graph leakage audit remains. |
| F-ENG16 | Passed | Actual LangGraph fixture journey: 3 pass/3 fail, mean85, one invocation each; illustrative exports. |
| F-ENG17 | Blocked / implementation partial | Exact real models, keys, budget, rights and independent paid approvals absent. Seeded approvals denied; no live dispatch claimed. |
| F-ENG18 | Partial | Concurrent reservation ceiling, unknown retention and idempotent reconciliation passed; no live launch integration. |
| F-ENG19 | Passed for fixtures | Actual SIGKILL before invocation and after persisted output recovers without duplicate capture; review-time and400-episode worker restart passed. Paid dispatch/reconciliation remains blocked. |
| F-ENG20 | Passed for fixture guards | Stale and expired matching lease tokens denied; immutable episode/thread/run bindings tested under non-owner role. No provider reconciliation claim. |
| F-ENG21 | Partial | Durable normal/adjudicated/invalidity review resumes without reinvocation; exhaustive duplicate/stale/wrong-project resume negatives remain. |
| F-ENG22 | Passed for tested boundaries | Injected thread/checkpoint/resume/command/goto/update fields return422 without state change or echo. Web DB identity cannot access durable checkpoint tables; worker cannot read hidden artifacts/rubrics. Cancelled checkpoint cannot resume grading. |
| F-ENG23 | Partial | Unsupported graph version and fixture byte/time exhaustion produce operational invalidity/null scores without counted capture. Time checks are cooperative; hard process deadlines, live token accounting and full recursion matrix remain. |
| F-ENG24 | Partial | Fixture cancellation and imported unknown/unscorable preservation passed; no live cancellation claim. |
| F-ENG25 | Passed for available adapters | SDK cost absent remains null; separate ledger amounts; external costs unverified. |
| F-ENG26 | Passed | Strict weights, five anchors, calibration and missing-dimension rejection. |
| F-ENG27 | Passed | 6000/4000 at4/2 gives80; critical override and threshold85 fail. |
| F-ENG28 | Passed locally | Blinded second review, deliberate dispute and third adjudicator; imported model/source scores omitted from review response. |
| F-ENG29 | Passed for scripted calibration | Differently named and worded valid MKT answer receives100/pass through independent review APIs and durable finalization. Ambiguous reference returns to review or independent invalid/null-score resolution. No expert reliability claim. |
| F-ENG30 | Passed | Zero denominator, unknown/invalid/cancelled separation and real imported score0/unscorable/unknown rendered report. |
| F-ENG31 | Passed locally | Immutable import receipts, actual durable review, separate source scores, origin-preserving PDF/HTML/email/ZIP; no invented traces or invocations. General uploaded outputs scanner-blocked. |
| F-ENG32 | Partial | Generated descriptive claim registry binds metrics/denominators/origin to exact evidence IDs; wider scope/caller registry injection denied. Free-text semantic validation still requires independent review. |
| F-ENG33 | Passed for tested failure cases | Atomic snapshot transaction rolls back on injected failure; a late older watermark cannot overwrite a newer generation. Outbox acknowledges only after success, and projection version changes force rebuild. |
| F-ENG34 | Partial | Bounded scoped neighborhood, immediate canonical withdrawal and501 historical-edge starvation regression passed; exhaustive every-hop visibility remains. |
| F-ENG35 | Passed | Actual Neo4j stop/fallback/start/rebuild with unchanged canonical score checksum. |
| F-ENG36 | Passed | Rebuild/replay and expected node/edge/hash comparison; PostgreSQL canonical. |
| F-ENG37 | Passed for current export schema | Exact ZIP allowlist/safe paths/hash manifest, private producer canary/hidden-reference exclusion, CSV enum/UUID/numeric cells and HTML escaping verified. Internal brief stays outside ZIP. Arbitrary reviewed text still requires human release review. |
| F-ENG38 | Passed for report path | Sharing revocation and draft successor block old download; old revisions retained. |
| F-ENG39 | Passed | Schema012 backup restored4,856 checkpoints/1,898 artifact checksums/846 pending reviews into retained `anvil_restore_2f647051f0bc`. Copied-review resume passed without reinvocation; isolated graph rebuilt174 nodes/169 edges with matching hashes and unchanged live evidence. |
| F-ENG40 | Passed for recorded checkout | Independent3e1ac27 archive installed locked dependencies without copied environments/credentials; build/89 units passed. Separate new volumes/credentials passed startup/browser/62 integrations after explicit fixture repairs included in0adfcd9. Later main hardening passes64 integrations. No sibling dependency. |
| F-ENG41 | Partial | 320/768/1440 overflow/theme/keyboard checks and visual inspection passed; full task-level accessibility audit remains. |
| F-ENG42 | Passed for local boundary | Nonlocal/staging/wrong-origin startup tests reject bootstrap; mock-only SDK contracts; health/seed use local dependencies without inference. Remote CI execution remains untested. |
| F-SK01 | Passed for fixture path | Automatic unique provisional kit; pending metrics unset and no release authority. |
| F-SK02 | Partial | Auto-approved kit/idempotent manual build and successor/rights invalidation passed; all correction types remain. |
| F-SK03 | Passed | One A4 page, per-section word limits, physical overflow rejection, logo/tagline; fixture/import PDF render and visual inspection, including the clean morning walkthrough. |
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

`pnpm test:load` passed200 repeated task variants from only3 independent cases/families and400 episodes after the latest guards:39.84s execution,232.4ms table readiness,1.18s first progress after worker restart, zero duplicate invocations. All400 human reviews remain pending; no model performance was measured. Evidence: `artifacts/test-runs/load-fixture-performance.json`, `load-run-console.png`. Thirty sequential graph queries also stayed below the two-second target with a bounded200-node snapshot. CI configuration is local source only, not remotely executed. The [current walkthrough](../runbooks/morning-walkthrough.md) maps MORN-01–08; the final continuation handoff will replace the historical [morning report](morning-report.md).
# Provenance continuation — 29 September 2026

Existing CSV/JSONL source declarations:130 unit tests,67 integration tests and4 browser
journeys passed. Missing declarations, immutable owner changes and retroactive source
relabeling are blocked; exact dataset/run provenance and bounded row lineage verified.
Non-synthetic policy permutations tested without storing fictional partner records.
Fresh/repeated migrations001–018 passed. Rights/privacy review and live dispatch not run.
