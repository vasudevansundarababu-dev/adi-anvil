# Coding handoff — Anvil transition to Codex, 8 November 2026

Status update: the user subsequently authorized remaining Anvil implementation, independent Testing and DevOps staging preparation, with approval required before deployment and no paid candidate/judge calls. OpenHands stopped as writer before Codex product changes. The assessment below is retained as historical cutover context.

## Current implementation and qualification boundary

Checkpoint `267c4b8951237bad2ac127c38782625b8ea1996f` is pushed on the same branch. It implements the offline operational benchmark lifecycle, durable fenced scheduling/recovery, immutable review-gated score revisions, authorized evidence/exports and the real API-backed benchmark UI. It is **not a qualified release**: self-audit identified actual-file citation and typed missing/empty-output gaps, addressed by migration 058 and its successor checkpoint.

The scoring repair preserves exact per-file hashes and spans. Missing or empty mapped `answers.json` gives zero only to its affected criteria, bound to an exact typed absence event. Missing or empty required `report.md` without a frozen scoring rule remains explicitly unresolved with primary score null. Whole-task zero requires an explicitly frozen hard safety constraint; raw diagnostic points remain available. No missing deliverable invents an undeclared safety policy.

At 267, independent verification recorded 776 offline units and 148 benchmark SQL checks passing, with 28 explicit native skips; TypeScript, 12 Node tests and 7 adapter tests passed. These are historical checkpoint results, not validation of the successor. The scoring repair's focused scoring/evaluation unit checks currently pass 50 tests. Independent SQL and fresh final-source verification follow the successor checkpoint.

Remaining release gates are explicit: actual native execution requires the isolated reviewed Linux operator environment; the Mac's Docker Desktop does not satisfy that contract. Nonzero live candidate/judge broker reservations and live dispatch are not implemented by the offline transport and must not be claimed ready merely by enabling flags. Authentic Praxis exports, approved model/judge configurations, rights, calibration, thresholds and paid budgets remain required for live evaluations. DevOps prepares staging only; no deployment is authorized yet.

## Exact cutover and source ownership

- Repository: `vasudevansundarababu-dev/adi-anvil`.
- Branch: `codex/anvil-agent-team-2026-11-06`; existing draft PR: [#16](https://github.com/vasudevansundarababu-dev/adi-anvil/pull/16).
- Cutover publication: `fd48c278c267d550485d739e4b0a09f0c6d70d79`.
- Product repair source: `e0a7b5fb45dbc73c1e9d6248647a102387ea5cd8`; recovery tested source: `4e64f54c368d04afcde6faa8c41cdadd9529e0d9`.
- Clean Codex checkout: `/Users/vasudevansundarababu/Documents/Codex/anvil-codex-transition`.
- OpenHands must finish its final handoff and stop repository writes before Codex product work starts. Preserve its conversations and evidence. Verify the remote again at the actual transfer; a newer commit must be reconciled rather than overwritten.
- Once bounded continuation is authorized, Coding is the sole product-source writer. Testing owns independent verification; DevOps owns isolated environment and staging preparation. Coordinate shared migrations, API contracts and release inputs through one reviewed source commit.
- Do not touch Praxis, the original Mac Anvil checkout or its uncommitted files. No reset, stash, force push, copied sibling dependencies or borrowed credentials.

The latest recovery report records 729 full-unit checks, 46 gateway checks, 95 provider-loop checks, three predefined six-test diagnostic rounds, 96 pricing/capture checks and 33 T06 contract checks passing. Counts overlap. Fresh SQL/native/resource checks remain blocked in that replacement runtime; old successful summaries are historical evidence, not a newly qualified environment. This assessment ran no tests.

## Reuse the approved plan and implementation

Continue the existing approved inputs in `docs/agent-team/runs/anvil-praxis-bodhium-benchmark-2026-11-07/`: `implementation-plan.md`, `architecture.md`, `contract-design.md`, `threat-model.md` and `requirements-to-test.md`. Historical pending-approval wording in those originals is superseded only by actual append-only approvals; do not rewrite the originals. Preserve T00–T06 work and the T05 repair.

The user asked for a correct switch point, separate Coding/Testing/DevOps agents and a path to staging. That authorizes this transition assessment and role handoff. It is not blanket approval to implement every remaining task, bypass review gates or treat an unspecified cloud target as staging. Root should present the first concrete continuation boundary and the verified staging target for the user's decision.

## Verified implementation gaps

| Plan unit | Existing foundation | Missing deliverable |
| --- | --- | --- |
| T07 | Canonical comparison/cell/attempt/spend tables in migrations 041–042; existing legacy run/budget helpers | No `benchmark_protocol.py` or `benchmark_execution.py`; no benchmark protocol-freeze, atomic whole-comparison admission or durable 18-cell scheduler runtime |
| T08 | Criterion/report validation in the T06 fictional evaluator; canonical result/review tables | No `benchmark_scores.py`; official primary comparison score revisions, assigned review/adjudication and scorecards are not implemented |
| T09 | `benchmark_api.py` exposes import/status/errors, source review, build/readiness/qualification and evaluator review/job/status/cancel routes | Comparison/protocol/run/cell projections, authorized evidence and JSON/CSV/redacted report/ATIF exports; corresponding typed modern-workspace client integration |
| T10 | Existing modern workspace and legacy catalog/task-profile workflow | Operational benchmark library/import/version/protocol/matrix/results screens backed by the new APIs |

`apps/web/src/components/WorkspaceBenchmarks.tsx` currently renders an explicit **UI MOCKUP** banner and `BenchmarkPreview` on the default Benchmarks route. Its `catalog` path renders the older metadata/catalog workflow. Proposed operational `BenchmarkLibrary`, `BenchmarkImport`, `BenchmarkVersion`, `BenchmarkProtocol`, `BenchmarkMatrix` and `BenchmarkResults` components are absent. Deploying the current branch would not deliver the requested benchmark journey.

Tables, manufactured receipt validators and static mockups must not be counted as complete scheduler, scoring or UI behavior. T06 private evaluator reports are not T08 official comparison scorecards. Offline SDK conformance is not a live model-performance result.

## Actionable dependency sequence

### Entry gate: stable baseline and native/SQL qualification

Testing and DevOps first establish a stable, isolated Anvil environment and a revision-bound baseline. Resolve the missing dedicated Docker/PostgreSQL/native prerequisites without using deployed user data, shared sockets or changed global permissions. Re-run the required T04/T06 native, resource and SQL checks against the exact cutover source. Preserve the last resource-probe action as unknown until its result is observed or the necessary check is independently rerun. The T05 connection fix must remain strict about authorization, framing limits, deadlines, single-use attempts and no inference retry.

Coding may review the next contracts while that preparation proceeds. A blocked native environment is not permission to change product semantics or invent a passing receipt.

### First implementation boundary: T07 protocol and durable execution

After explicit bounded continuation authority:

1. Freeze the exact benchmark/task/environment/tool/evaluator/model-slot/configuration versions and two-repetition protocol. Reject missing or stale bindings with inspectable reasons.
2. Implement atomic parent admission for all three per-package groups and exactly 18 initial cells. Reserve candidate and judge windows separately; prevent independent child launch and double reservation.
3. Implement durable claim/capacity/checkpoint ownership, at most three active trials, provider limits, and fenced intent/send/capture transitions.
4. Preserve cancel/restart/reconcile/unknown-outcome semantics. No automatic inference retry after ambiguous dispatch. Existing legacy group/run behavior remains intact.
5. Use clearly fictional offline model transports for software verification. Missing actual models, judge, rights or budgets keep live execution blocked.

Exit evidence must include real isolated PostgreSQL concurrency, replay, cancellation, capacity and reservation tests; a unit-only table/schema test is insufficient. Publish the exact tested commit and hand the boundary to independent Testing before expanding it.

### T08 and T09: official results and application integration

- Add the approved 81-criterion, 24/6/51 point accounting with exact Decimal/tolerance/display rules; distinguish operational invalidity from a valid model zero; leave incomplete primary scores null; never choose the best retry.
- Bind score revisions to immutable cell/attempt/protocol/evaluator evidence. Preserve assigned independent review, adjudication and successor history; semantic judgments remain blocked without real authority/calibration.
- Complete protocol/comparison/cell/status/evidence APIs with project/role isolation, CSRF, idempotency, CAS and pagination/event behavior. Reuse existing envelopes and error conventions.
- Implement authorized versioned exports from stored raw results. Deny private benchmark classes through generic download/export paths; validate redacted ATIF with installed Harbor conventions.
- Add typed clients in the existing modern workspace. Do not introduce an alternative backend, database, auth stack or parallel API product.

### T10: operational application screens

- Reuse the approved design and existing workspace styling. Read `apps/web/AGENTS.md` and installed Next.js guidance before frontend edits.
- Implement real library/import/version/readiness/protocol/matrix/results/evidence screens against T09. Show loading, empty, validation, blocked, stale, partial, unknown, cancellation and reconnect states truthfully.
- Move illustrative preview content to a clearly separate preview route; operational screens must never display invented model scores or task counts.
- Keep existing Tasks, Preparation, execution groups, run history and catalog behavior working. Add role-safe links, keyboard/focus/alert behavior and accessible error recovery.

## First integrated runnable milestone

The first integrated benchmark milestone is a browser walkthrough in an isolated Anvil environment:

`signed-in project → import clearly fictional signed bundle → inspect receipt/errors → build and inspect actual qualification → freeze a three-slot/two-repetition offline protocol → observe durable matrix → inspect exact criterion evidence and complete/incomplete scorecard → export authorized results`.

The UI reads real API/database states; tools and the separate evaluator execute through the approved isolated native boundaries. Only the unavailable paid provider boundary uses controlled responses, with the origin displayed as fictional/offline software conformance. No actual Bodhium/model-performance claim follows.

Earlier browser demonstrations of implemented import/build/readiness states are useful progress previews, but must be labeled partial. They cannot be described as this completed integrated milestone. T07–T10 completion, independent Testing evidence and DevOps release preparation precede staging qualification. Authentic live comparison is the separate T13 gate.

## Handoff, ownership and stop conditions

- Coding records changed paths, rationale, exact commands/outcomes, source/tree hashes and remaining limitations; preserve the existing progress/approval history and push only the authorized explicit file set.
- Testing reviews the exact product commit independently and reports passed, failed, blocked and not-run gates. It does not silently fix product source or certify missing native/live checks.
- DevOps prepares a distinct Anvil staging target, dependency/image identities, migration/rollback rehearsal and health verification; it must not reuse the existing deployed application as staging by assumption or affect Praxis.
- Root coordinates approval of the bounded continuation and concrete release. No QA/staging/paid authority is fabricated in this document. Default-off benchmark/live flags, rights/private-data boundaries and spending controls remain enforced.
- Stop at a genuine authority/environment blocker after preserving all safe independent progress. No production rollout, paid model/judge call, invented source data or swallowed test failure to reach a date target.

No delivery-hour or completion-percentage estimate is asserted: remaining T07 concurrency/financial behavior, T08 result semantics and T09–T10 integration are substantive implementation work. Re-estimate from the verified baseline and first implemented T07 boundary rather than promise a deployment based on recovered unit-test counts.
