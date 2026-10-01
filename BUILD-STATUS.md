# Build status

2026-10-01 — **Cloud deployment path built and rehearsed locally; not yet deployed.** User
requested GCP deployment like Praxis and approved: create project `adi-anvil-mvp-2026`
(us-west1), single e2-standard-4 VM + compose, sslip.io hostnames from a static IP,
$150/month budget alert. Added explicit validated `ANVIL_ENV=cloud` (HTTPS origin/issuer,
live providers and real email forced off, Secure cookies; synthetic seeds, demo projects and
local backups refuse cloud; local guard unchanged), `anvil.cli invite` (real Keycloak identity,
temporary password, explicit roles), backend/web images, `infra/gcp/` compose stack
(Caddy TLS, production Keycloak on PostgreSQL, private PostgreSQL/Neo4j), startup script,
Cloud Build config and idempotent `deploy.sh`/`invite.sh`. Local production-mode rehearsal
(Caddy internal CA) passed: migrations001–018, realm import, OIDC health via public issuer
name, invite idempotency/conflict refusal, login with forced password change, Secure cookies,
`/me` roles, public Keycloak admin 404, cross-origin CSRF 403, logout. `pnpm check` passed;
146 units and67 integrations passed. E2E browser journeys not rerun. Cloud provisioning is
blocked on the billing account ID; the configured project was not accessible. No cloud
resources were created.

2026-09-29 — **Local provenance increment verified.** User authorized autonomous local
execution. Extended the existing importer with immutable source owner declarations,
schema018, exact-version provenance and row lineage. Legacy sources stay unclassified;
only explicitly declared ADI synthetic sources can publish pending reviewed rights/privacy
controls. No partner fixtures, paid calls or external actions. `pnpm check` passed;
130 units,67 integrations (final rerun39.55s) and4 browser journeys passed (45.6s).
Final web type check and formatting passed. Fresh/repeated001–018 passed in retained
`anvil_migrationcheck_446c2001b9f4`. See the provenance report for scope and limits.


2026-09-29 — **ANV-BF-001 scoped Factory path locally verified.** User confirmed
executing TaskProfile/recommendation first and extending the existing registry;
GEO/intent-gap specs remain undefined. Added immutable confirmed profiles, explicit
catalog metadata registration, deterministic weighted ranking with hard filters,
gaps/composition advice and exact-version Suite draft creation in the existing shell.
Migration017 applied; no new service/database/catalog, dependencies, live calls,
external sends, schedules or remote publication. All supported data is original ADI
synthetic; no Bodhium data fabricated. See `docs/generated/ANV-BF-001-report.md` and
`docs/runbooks/benchmark-factory.md` for exact paths, commands and limits.

Final source checks: `pnpm check` passed lint/format/types/production build/OpenAPI;
`pnpm test:unit`124 passed; `pnpm test:integration`67 passed (38.13s);
`pnpm test:e2e`4 passed (46.2s). Fresh/repeated001–017 passed in retained isolated
`anvil_migrationcheck_ef26060f5c00`. Factory screenshot visually inspected.
Initial new assertions and a preexisting repeat-run fixture-selection defect were
repaired without weakening security gates. Current app restarted at3202/API8200.

Full Benchmark Factory acceptance remains partial: registration is metadata only;
full manifest/adapter smoke release, TaskBank profiling, measured cost/runtime,
global optimal composition and100,000-task execution remain outstanding. Matching
is limited to current qualified synthetic static fixtures; interactive marketing is
explicitly excluded from this path. Paired benchmark/recommendation bindings and
their exact task union are checked even for generic Suite creation. No hidden
reference payloads are used for matching. Live verification remains blocked;
schema017 backup/restore and destructive rollback were not run. Next ordered slice:
Night2 provenance/owner-lineage alignment for the already-built CSV/JSONL importer;
do not rebuild its upload/jobs/versioning. Stop after this requested increment.

2026-09-28 20:20 UTC — **Registered 12-week marketing workflow verified locally;
paid launch remains blocked at the user's request.** User confirmed that the API key
is not configured and two real Admin approvers are unavailable. Implemented the
trusted draft importer, exact task/suite/protocol/connection bindings, external
processing rights scope, run readiness/approval UI, bounded OpenAI Responses adapter,
13-step LangGraph/PostgreSQL runtime, immutable dispatch intents, preserved usage,
review handoff and conservative $100 cumulative/$13 run reservations. No live calls,
real paid approvals, external sending or remote publication were made.

`pnpm check` passed lint/format, types, production webpack and OpenAPI generation.
`pnpm test:unit`: **116 passed**. `pnpm test:integration`: **66 passed**,37.71s.
`pnpm test:e2e`: **3 passed**,47.3s total (diagnostic26.8s, marketing6.9s,
CSV/JSONL import7.7s). Browser screenshot `artifacts/test-runs/marketing-readiness.png`
was visually inspected. Initial browser failures found an import-assignment timing
bug and new-test account-switching assumptions; readiness gating, automatic search
and isolated OIDC contexts resolved them. No final verification failure remains.

Migrations001–016 were applied and repeated from empty schema in the isolated mock
database `anvil_marketingtest_12df460a55ec`. The real worker dispatched all13 mocked
responses, persisted the review interrupt and resumed after two synthetic software-test
reviews. Committed-intent interruption becomes unknown without retry; captured-output
interruption applies once without another call; stale lease and changed environment
binding are denied. Actor prompts exclude private future state/references. Evidence:
`artifacts/test-runs/marketing-mock.json`. Mock outputs are isolated from the main app
database and are not model performance. Main-browser acceptance stops at a draft run.

Scope limits: real identity onboarding, actual model/account access, real paid approval
exercise, live verification and billing reconciliation are outstanding. All API reservations
are retained conservatively; reported usage is not a verified bill. Pricing expires
2026-10-05. Runtime hashes prevent resuming a changed harness. General imported tasks,
other live providers and later ingestion/privacy increments remain outside this slice.
Schema016 backup/restore was not rehearsed; earlier schema012 recovery evidence remains
historical. Follow [marketing setup](docs/runbooks/marketing-live.md); do not relabel
demo accounts or grant fabricated approvals. Anvil was restarted; web3202 and API8200
both returned HTTP200. Staged secret scan checked216 tracked files with zero findings;
`git diff --cached --check` passed. This entry is included in the local implementation checkpoint;
no remote publication. Work stops after verification of this requested workflow.

2026-09-28 19:38 UTC — User requested enabling execution and selected the full
12-week interactive marketing task. New bounded implementation session (eight-hour
maximum, stopping by 2026-09-29 03:38 UTC). Implement the interactive binding and
verify locally; exact selection remains OpenAI `gpt-6-sol`, cumulative $100 ceiling.
No paid launch or fabricated Admin approval. User subsequently confirmed missing keys
and real approvers, and explicitly requested leaving paid launch blocked.

Status: **LOCAL DIAGNOSTIC SLICE VERIFIED — FULL MVP ACCEPTANCE PARTIAL**

2026-09-28 19:16 UTC — **Task & Data Import and advanced-ingestion Increment 1 verified.**
The user resumed work with both ingestion specifications after the explicit halt. Per the
advanced spec's §14, this delivery implements the current daily increment, not all six.
CSV/JSONL upload → durable validation/mapping → immutable DatasetVersion → exact suite
attachment → Run Console configuration is working. A draft run snapshots the exact
dataset ID, TaskSpec version, source/content checksums and task count. Arbitrary imported
tasks remain blocked from fixture dispatch and external-result substitution. No live calls.

Schema013 was applied before the halt; schema014 adds durable ingestion. Original records
and volumes were retained. Raw sources stay quarantined; actor/reference records are
separated. Logical200-record chunks use the existing PostgreSQL job queue, scoped author
transactions, lease fencing, cancellation/retry and bounded local transient backoff.
Static read-only Anvil Help and shared required-field/error-summary forms are included.
Later connectors, generation and PII processing are explicitly not implemented. This is
not a qualified runtime for the separate 12-week marketing task.

Verification: `pnpm check` passed lint/format/typecheck/production build/OpenAPI;
`pnpm test:unit` **103 passed**; `pnpm test:integration` **65 passed**. Full
`pnpm test:e2e` **2 passed** on final source (44.8s); expanded CSV+JSONL/help/configuration test
`pnpm test:e2e -- task-import.spec.ts` **1 passed** (10.7s total). Import integration
verifies atomic rollback on an injected insert failure, publish replay, immutable v1/v2,
exact run pinning, reference isolation, SIGKILL after a committed chunk, stale-lease denial,
cancel/resume without duplicate chunks, and bounded transient retry. Fresh/repeated001–014
migrations passed in retained `anvil_migrationcheck_9ca8c2c0ab5a`. Screenshot
`artifacts/test-runs/task-import-config.png` inspected. Anvil is running at3202/API8200.
Initial publication row-lock permission failure and CSV mapping-order UI issue were fixed;
no unresolved verification failures. Existing Authlib deprecation warning remains nonfatal.
The current branch retains this verified addition; previous checkpoint/counts below are historical.
Next daily increment is PDF/Parquet extraction; read its specification before proceeding.
See [five-minute import demo](docs/runbooks/task-data-import.md) for limits and remaining gates.

2026-09-28 marketing-task addition: user selected OpenAI, confirmed exact model `gpt-6-sol` and a $100 cumulative API ceiling. Created `task-packs/marketing-12-week/`: original synthetic Northstar Flow launch, 64 historical channel-week rows, 8 fictional interviews, actor instructions, input checksums and operator rubric. `scripts/marketing_task.py` provides a network-free 12-step development environment with budget carryover, delayed conversions, fatigue, capacity losses and disruptions. This is **not integrated with or qualified for Anvil live execution**. No existing user records, runtime services or approvals were changed. No model calls were made. Secret readiness has not been reconfirmed; rights, actual distinct-Admin approvals and live runtime implementation remain outstanding.

Task-pack checks: `python3 scripts/marketing_task.py generate` passed; `python3 -m unittest discover -s tests -p 'test_marketing_task.py' -v` **9 passed**; `python3 scripts/marketing_task.py rehearse` completed all12 steps with $106,000 simulated spend,47 simulated customers and $2,255.32 CAC. These are scripted software feasibility results, **not model performance**. Ruff check/format and `git diff --check` passed for the addition. Full application/browser/integration suites were not rerun for this isolated task pack; prior application results below remain historical. Next live work requires the qualified interactive binding, durable dispatch/step controls, actor isolation and real paid gates; the task pack does not bypass them.

New authorization: user instructed “ok continue the work” after the proposed additional eight-hour window. Resumed 2026-09-28 11:24 UTC; new stop deadline 2026-09-28 19:24 UTC. Single writer; no live inference or external publication authority. First action: repair lint and verify the final prior-session changes, preserving all data and source.

Current source checkpoint: `0adfcd9` on `build/overnight-v1`. No remote publication. Latest unit/integration totals: **89/64 passed**. Production check passed. Real-OIDC browser passed29.5s test/47.4s total. Schema012. Main web/API/worker and infrastructure are running; clean-test services are stopped with all volumes retained. The updated morning report and JSON record current evidence and remaining work.

15:46 UTC: Disabled-account assignment and same-person multi-role negatives passed. Authenticated reads leave business tables unchanged except exact append-only access auditing; the test freezes independent background jobs/projection during measurement. Export canary, ZIP paths/allowlist/hashes and CSV checks passed. Independent build/89 units and fresh startup/browser/62 integrations passed after two explicit fixture-prerequisite repairs. Final main suite64 passed; no unresolved final-check failures. Next development scope: scanner/partner qualification, structured editing and remaining baseline/security permutations, then separately authorized and qualified live integration. No paid authority or real sender configured.

Historical15:30 UTC rehearsal: temporarily stopped the main app/services while a fresh checkout used the same loopback ports under separate Compose project `adi-anvil-fresh-3e1ac27`. Rehearsal finished and original services/app were restored; both sets of volumes are retained. Never run the clean checkout's default setup against the main Compose project.

15:25 UTC: All latest checks passed. Expanded graph lineage/atomic ordering, descriptive claim registry, fixture capture bounds and role/project provider/delivery negatives verified. Repeated400-episode load:39.84s execution,232.4ms table readiness,1.18s first progress after worker restart, zero duplicate invocations; all400 reviews pending. `pnpm demo:walkthrough` prepared project `ea1cc06d-3ad8-4e9c-8e89-87f27b2d2d82`: three cases, reviewed6 with3 pass/3 fail/mean85, plus separate6 pending practice episodes. Actual PDF visually inspected. Current schema012 backup restored into `anvil_restore_2f647051f0bc`, verifying4,856 checkpoints/1,898 artifact checksums/846 pending reviews. Copied review resume, isolated restored graph174 nodes/169 edges and actual Neo4j outage/rebuild passed. Next: local checkpoint and restart, then remaining bounded security/accessibility checks and current clean-checkout verification. See `docs/runbooks/morning-walkthrough.md` for the usable UI map. No live calls or real mail.

15:10 UTC: Readiness checkpoint `b39b799` saved. Subsequent graph ordering, limits and claims work:89 units/58 integrations and production check passed; browser25.0s/47.0s passed. Neo4j actual rollback/out-of-order tests, checkpoint/private-reference isolation, cancelled durable resume, cooperative fixture byte/time limits and strict reviewer state-injection tests pass. Generated descriptive claim registry is included in evidence ZIP; report copy limits enforced; updated one-page PDF rendered and inspected. Latest expansion adds family/capability/episode/finding graph lineage and immutable source family/exposure guards;61 integrations and fresh/repeat migrations001–012 passed (`anvil_migrationcheck_7050227e489a`). App currently stopped for production check; restart and expanded graph-browser test next, then remeasure400-episode batch, prepare a clean three-case morning demo and current backup. All extra migrations and graph changes remain uncommitted.

14:41 UTC: Added a version-bound source readiness/gap ledger and case UI. Missing/partial annotations block qualification, launch/resume and release; resolving an annotation cannot replace actual evidence or rights. Data Engineer/assigned reviewer guards, stale version/ETag/replay, foreign evidence, source-version isolation and launch block tested. Partner source cannot qualify under a synthetic source label. Fresh/repeated010 passed in `anvil_migrationcheck_4c204bf144f6`. Browser initially raced the asynchronous search result; waiting for the actual new case heading fixed the test and it passed. Expanded cross-project command matrix passed with unchanged foreign resource versions. Next: final formatting/check and local checkpoint for this milestone, then remaining scientific/export and execution-boundary tests. Schema010 backup not yet rehearsed.

14:27 UTC: `pnpm check` passed; integration50 passed, including alternate valid answer credited100/pass, exact draft replay, immutable execution bindings and revoked-rights/author guards. Initial membership-revocation test incorrectly attempted a forbidden worker update; corrected to owner-only setup followed by non-owner guard and passed. Migration009 fresh/repeat passed in `anvil_migrationcheck_d16294d30e92`. Backup `.local/backups/20260928T142451Z-e43d0121` restored to `anvil_restore_9dec35627311` with2636 checkpoints,420 pending reviews,1049 artifact checksums; copied review resume and isolated graph81 nodes/39 edges passed. Main app running latest guards. Browser regression in progress; next checkpoint after that result, then source readiness/gap workflow.

14:17 UTC: The standalone `node tests/load_fixture_batch.mjs` rehearsal passed on a new isolated project: 200 repeated synthetic task variants from only three independent cases/families, 400 episodes, 400 pending human reviews, no duplicate invocations. Execution took31.07s; 400-row UI ready267.8ms; first progress after registered-worker restart1.22s. No model performance measured or live inference. Evidence: `artifacts/test-runs/load-fixture-performance.json` and `load-run-console.png`. Source-version migration008 is applied. Schema008 backup/restore remains to run; prior schema007 recovery evidence is historical. Next exact action: complete `pnpm check`, restart `pnpm dev`, run integration and browser regressions, then backup/restore and checkpoint.

Historical first-window stop audit: clock checked at10:52:30 UTC after the10:43 deadline, implementation stopped, and the user subsequently authorized this continuation. The earlier lint failures were repaired and verified. Prior-window [morning report](docs/generated/morning-report.md) will be replaced at this window's handoff; its old no-commit/test counts are not current.

- Authorized launch: 2026-09-28 02:43 UTC; stop deadline: 2026-09-28 10:43 UTC.
- Single writer; no remote or live inference authorized.
- Tools: Node 24.21.0, pnpm 10.34.5, Python 3.14.6, uv 0.12.19, Docker 29.8.0, Compose 5.5.1, arm64 macOS.
- Docker verified with authorized sandbox escalation. Existing Git identity available.
- Web ports 3200 and 3201 occupied: use 3202, preserving unrelated processes.
- Live verification blocked: no keys, exact models, budget or independent paid approvals.
- Next: resolve independent dependencies, infrastructure and root launcher.

Resume evidence (11:34 UTC): `pnpm setup:local` passed idempotently; `pnpm dev` running; `pnpm check` passed lint, TypeScript, production webpack build and contract generation. `pnpm test:e2e` passed the complete six-episode existing fixture journey after automatic-kit changes. New request-byte limit and API create idempotency fixes verified by `pnpm test:unit` (83 passed) and `pnpm test:integration` (21 passed). Actual generated A4 PDF rendered with sips and visually inspected: legible single-page white background. Latest security changes still require browser regression. No live inference. Next: dispute/cancellation and graph outage/rebuild verification, remaining intake/release requirements.

Resume evidence (11:42 UTC): additive Alembic 003 import batch/receipt schema applied. Partner manifest dry-run/atomic commit/deduplication/quarantine tests pass. Integration suite now 23 passed, including real Neo4j rebuild/replay and simulated outage fallback. Expanded E2E passed automatic provisional/approved kits, deliberate dispute with third-identity adjudication, cancellation, and invocation counts. Intake and provider configuration UI added; TypeScript passed. Findings now validate finalized episode, bound criterion/capability and verbatim evidence before submission. Latest UI/graph/finding changes await full regression. Source/credential scan reported zero known local-secret matches. Preparing first local checkpoint; all functionality remains partial against the full P0 matrix.

Resume evidence (12:14 UTC): checkpoint `7377af7` created locally, no remote. `pnpm test:unit`: 83 passed; `pnpm test:integration`: 31 passed (signed OIDC claim negatives, successor history, withdrawals included). Expanded E2E passed rights revocation and successor download invalidation. `services/backend/.venv/bin/python tests/graph_outage.py` now passed actual Neo4j stop/fallback/start/rebuild with unchanged episode checksum; first run caught startup timing in the test harness, fixed bounded retry and reran successfully. Persisted evidence ZIPs and rights-review UI added. New isolated-project/mobile browser run in progress. Next: finish remaining findings/release/fixture delivery/operational requirements and acceptance evidence. Deadline remains 19:24 UTC.

Resume evidence (12:28 UTC): findings creation/review and actual queued network-free mail simulation passed in a fresh-project E2E (11 distinct OIDC accounts, 19.8s). Fixture mail API rejects non-.invalid addresses, requires distinct sender Admins and exact release-owner approval, rechecks suppression and evidence, and preserves terminal unknown acceptance without resending. 32 integration tests passed; 85 unit tests passed including zero-denominator/unknown/cancelled separation. `pnpm check` passed. Fresh Alembic 001–004 plus repeated upgrade passed on retained `anvil_migrationcheck_c8e3936a3f74`. `pnpm audit --prod --json`: zero advisories across 102 production dependencies. Worker operational-failure terminal handling was added after latest E2E and needs targeted verification. Python advisory audit running. No real email/model requests. Source changes after first checkpoint not yet committed.

Resume evidence (12:47 UTC): backup `.local/backups/20260928T123640Z-dd7587c3` restored to retained `anvil_restore_6f9904fd6b15`; 386 checkpoints, 3 pending reviews and 167 artifact checksums verified. `tests/restore_resume.py` finalized one copied pending episode using the copied artifact store, with unchanged invocation count and original episode. Python audit: 84 dependencies listed, zero advisories; local unpublished `adi-anvil` skipped. Immutable Compose image digests started successfully with retained volumes. CI/Dependabot/runbooks prepared locally, not executed remotely. Input qualification now rejects duplicate/cross-source actors; suspicious/oversized file fixtures remain quarantined/blocked. Latest integration: 40 passed; E2E passed 19.7s after correcting a repeat-import column typo. UI/test formatting and TypeScript passed. Next: ambiguous-reference resolution and external result import; no complete-MVP claim.

Evidence below reflects the prior session unless updated above.

Resume evidence (13:56 UTC): local checkpoint `664703a` saved the verified import/recovery slice. Clean archive `.local/clean-checkout-664703a` installed locked JS/Python dependencies offline into new directories with no copied credentials; production check passed. First clean unit run lacked `ANVIL_FIXTURE_MODE`, corrected the explicit test environment and88 tests passed. Main app running. Subsequent uncommitted work: abrupt SIGKILL fixture recovery before dispatch/after persisted output and matching-token expiry tests passed; interactive graph keyboard/320/768/1440 browser checks passed, and501 historical links cannot starve current edges. Migration008 applied and fresh/repeat upgrade passed in `anvil_migrationcheck_6a4a305ec580`. Source imports now append versions to one case and retain exact receipts; replay and expiry/no-rights-inheritance tests passed. Synthetic inventory now200 identities/400 versions/100 families. Last full integration46 passed before latest expiry/count additions; unit89 passed. Latest source needs formatting, full checks/browser rerun and new schema008 backup. No live inference or real sending.

Resume evidence (13:35 UTC): `pnpm check` passed production build, types, lint and regenerated external/review/pagination contracts. Unit88/integration42 passed. Expanded real-OIDC browser journey passed (20.9s test,34.7s total), including customer-reported aggregate import and paginated case-bank search with29 actual sources versus3 published-task sources. External import integration passed actual durable review, separate producer scores, immutable execution binding and origin-preserving approved PDF/email/ZIP; rendered PDF visually verified. Fresh/repeated migrations001–007 passed in `anvil_migrationcheck_90a3bf87ef41`. Synthetic200-source list/detail p95 measured31/19ms through ASGI+PostgreSQL, concurrency1;400-episode capacity not tested. New launcher collision/readiness and nonlocal-config guards passed. Schema007 backup restored to `anvil_restore_5f1ed4794b68`:664 checkpoints,3 pending reviews,373 artifact checksums; restored worker resume and isolated graph rebuild passed. Next: complete source formatting/checkpoint, clean independent install, remaining security/operational criteria. Live calls still blocked.

Resume evidence (12:57 UTC): checkpoint `387648a` contains the verified continuation through fixture delivery, restoration and security work. Additive migration 005 adds assigned-reviewer issue flags and independent adjudicator resolutions. Expanded browser journey passed (19.0s): return-to-review and invalid-evidence resolution both exercised; invalid episode finalized with null score and invocation count one. `pnpm test:unit`: 85 passed; `pnpm test:integration`: 40 passed. `tests/migration_smoke.py` passed fresh/repeated migrations 001–005 in retained `anvil_migrationcheck_a9e959d63133`. New source formatting applied. Next: external-result import with preserved origin and no fabricated trajectories.

| Milestone | State | Evidence |
| --- | --- | --- |
| M0 Preflight, locks, isolated scaffold | Verified local path | Independent locked offline clean-checkout install/build, named services, pinned images and safe launcher |
| M1 Identity, API/DB, shell | Core path verified; security matrix incomplete | Real OIDC11 identities, CSRF/role/project negatives, RLS; no production identity readiness claim |
| M2 Intake, qualification, suite/protocol | Core path verified; baseline gaps remain | Source versions/receipts, rights expiry, rubric/task reviews, frozen bindings; general uploads quarantined |
| M3 Durable fixture evaluation + review | Core path and400-episode processing verified | Blinded double grading, dispute/invalidity, SIGKILL recovery, cancelled/unknown states;400 human reviews intentionally pending |
| M4 Diagnostics and graph | Core bounded local path verified | Family/capability/task/episode/finding links, atomic ordering, actual outage/rebuild, restored graph and keyboard navigation |
| M5 Report, release, Sales Kit | Core local path verified; semantic claims remain human-reviewed | Descriptive claim registry, real downloads, one-page visual QA, rights invalidation and network-free mail simulation |
| M6 Provider adapters and authorized smoke | Mock contracts passed; live blocked/unqualified | 73 SDK transport contracts; no inference; paid gate integration incomplete |
| M7 Verification and morning handoff | Current local evidence recorded; full acceptance partial |89 unit/64 integration, production/browser/load, independent startup and schema012 recovery passed; live/remote CI not passed |

Build agent maintains below: start/deadline, current commit, versions, last passing command, failures, pending questions, next exact action, local URLs/processes and safe resume instructions. Keep secrets and raw candidate/source content out of this file.

Latest evidence (03:16 UTC): `python3 scripts/local.py migrate && python3 scripts/local.py seed` passed; `python3 scripts/local.py integration` passed 2 tests; `pnpm exec playwright test` passed 1 real-login journey in 10.3s. Fixture expected numeric outcomes verified. Initial E2E failed on a too-short test evidence quote; corrected to full JSON field span, preserving product validation.

Runtime URLs: web http://127.0.0.1:3202; API http://127.0.0.1:8200; Keycloak http://127.0.0.1:8180. Credentials: `.local/demo-accounts.md` (owner-only). Logs and process registry in `.local/`. No model calls made.

Environment issues: optional Playwright Chromium download failed (network timeout/DNS); tests use installed Chrome with isolated profiles. Turbopack production build failed on subprocess port permission; supported webpack build being tested. Resume: review restart/dispute tests, graph projection/fallback, report/downloads, provider mocks, remaining P0 hardening.
