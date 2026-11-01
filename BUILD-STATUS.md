# Build status

Current local checkpoint — 31 October 2026: the two-role and separate execution-group
journey is implemented on `codex/anvil-modern-workspace`. **Admin and RL Engineer only**;
Admin includes engineering. Schema 033 archives old memberships and preserves identities;
schema 034 records one exact Admin Run authorization. No Product Owner, second Admin,
external group-authority file or separate modern approval forms. Historical decisions,
private-reference assignments, immutable versions, recent sign-in, real identity, runtime
controls and atomic budget reservation remain. Run authors cannot independently grade
or inspect their own private review. New private bindings require prior individual access
or source ownership; task self-assignment and hidden-as-actor relabeling cannot grant access. Admin software-check Run authorizes its exact scope.

Execution groups now has separate newest-first **List → Create → View/dashboard** pages.
Task Run links preselect the task. Create saves without spending and opens the dashboard;
model runs link to existing result/failure/trajectory/snapshot/usage dashboards. Saved
preparation URLs are read-only compatibility views. Classic routes/baseline remain.
[Current spec](docs/product/22-TWO-ROLES-AND-EXECUTION-GROUP-JOURNEY.md),
[walkthrough](docs/runbooks/workspace-execution.md), and
[verification report](docs/generated/two-role-execution-groups-2026-10-31.md).

Verification: final `pnpm check` passed; 242 unit tests passed. Full real-Harbor/mock-provider
integration: 173 passed, one retained-data pagination-test failure, two optional Praxis-export
skips (235.77s). Repaired that test; final workspace/access follow-up 8 passed (1.26s),
including new populated role-history immutability coverage. Full integration was not
repeated after that repair or the final private-binding API guard. The final privacy/editor/
evaluation integration follow-up passed 14 tests (6.83s); API security passed 49 (44.09s). Full browser 14 passed/two duplicate-heading failures;
corrected the heading, affected replay 2 passed; final Harbor/preparation suites 5 passed
(47.4s). All 16 browser scenarios have passed across these runs. Final screenshot inspected;
after the private-binding guard, the complete classic journey and preparation suites
passed again: 3 browser tests (49.0s). Final static check/build passed after that guard.
320/768/1440-width overflow checks pass. Backup/restore passed into retained
`anvil_restore_663b0942d410`: 1,236 pending reviews and 6,833 artifact checksums verified;
original DB unchanged. Schema 034/new-table hashes match, including 3,146 archived membership
rows. Canonical authorization tables were empty; populated paid-authority recovery and
credential files/wrap-key/environment/Keycloak recovery remain not run.

API/database healthy at http://127.0.0.1:3202/workspace; both live inference and Harbor live
dispatch disabled. Paid smoke NOT RUN; seeded identities remain synthetic. No cloud rollout,
push, real email, IAM change, paid call, dependency install or reset occurred. Unrelated
AGENTS.md/cloud-runbook edits and comparison branch 3a17429c are preserved. This interactive
slice is complete locally, not a completed production platform or live model qualification.
Next nightly: verify relevant regressions only unless new requirements arrive; do not add
unrequested features or restore superseded role/approval requirements. Preserve the fixed
22:00–06:00 nightly window. Broader partial areas: People management, managed cloud secrets,
qualified external framework adapters and explicit spend reconciliation.

## Earlier checkpoints (policy superseded by the current checkpoint where it differs)

Interactive execution continuation — checkpoint `c3d2eb1`,31October2026. The missing
preparation→execution-group→Harbor→results path is implemented and software-verified locally.
Overall platform remains partial; this is not live provider/model qualification or a rollout.
Additive031/032 applied: immutable groups/children reuse existing plans/checks/jobs/calls
and the shared spend window. Exact-group operator authority, current frozen rates/terms,
real assigned PO rights/run review and distinct-real-Admin activation/paid decisions remain
required. Group launch reserves one aggregate cap atomically; database claim fencing runs
children sequentially and blocks successors after failed/cancelled/unknown predecessors.
Scoped OpenAI/Claude/Gemini native brokers have no global key fallback, retries or redirects;
provider keys never enter Harbor. Durable intents commit before network I/O. Current
binding/role/rights/authority/cost gates are rechecked; unknown/cancelled caps remain held.
Project KEY SHARE precedes worker/intention group/job/plan/check locks. State-only worker
visibility and conditional finish preserve raced terminal cancellations byte-for-byte,
without granting access to private result columns. Exact frozen settings, rubric labels/
weights, recorded request-context hashes/IDs/times, hash-verified actually revealed actor
contexts and terminal outputs feed existing dashboards and compatible metric comparison.
Private grading bindings/references and hidden reasoning remain excluded. Mock requests,
including unknown outcomes, retain software-only provenance; no model performance claim.
Final `pnpm check` passed; `pnpm test:unit`238 passed (4.10s), including DEBUG log/key scans.
Broad real-Harbor integration173 passed/2 optional Praxis-export skips (232.35s) before the
last narrow terminal-recovery/error-detail repair. Final schema032 execution suite12 passed
(51.90s), including concurrent/replayed launch, group cap, state-only permissions, revocation,
no retry, cancellation/worker recovery and real staged Harbor with all three mocked SDKs.
Full all-module integration was not repeated after that narrow repair; relevant final suite
and full browser16 passed (2.5m). Fresh/repeated001–032 migrations passed in isolated tests.
SQL/artifact backup `.local/backups/20261101T003814Z-462e688d` restored into retained
`anvil_restore_a8f35c1740c5`:1213 pending reviews and6580 artifact checksums verified; all
12 workspace-table digests match, including1 execution group/2 child bindings. Original DB
unchanged; state-only worker grants preserved. Credential files/wrap-key, environment and
Keycloak recovery remain not tested. [Current execution handoff](docs/generated/workspace-execution-build-2026-10-31.md)
and [walkthrough](docs/runbooks/workspace-execution.md) supersede prior planning-only status.
App restored at http://127.0.0.1:3202/workspace with synthetic-only worker and both live flags
disabled. No real provider key was used, paid call made, cloud deployed, GitHub pushed,
email sent or real identity/IAM changed. Fresh contract identities exist only in isolated
test databases; seeded identities were not promoted. Unrelated user edits/baseline preserved.
Next: review the completed execution flow locally. Actual paid validation still requires
explicit exact group/provider/model/budget authority, real reviewers and runtime activation;
do not infer it from this build request. Remaining broader platform work: full profile/
People management, managed cloud credentials, external LangSmith/Semantic Kernel adapters,
general non-synthetic qualification and explicit spend reconciliation. Nightly automation
remains active; resume durable state and honor its fixed22:00–06:00 local window.

Execution-preset runner refresh fix — 31 October2026. Runner choices accept project-scoped
Harbor framework profiles, not provider/model profiles. FrameworkProfiles and ExecutionPresets
previously loaded independently, so saving a framework left the adjacent runner list stale.
Framework saves now notify the parent, which refreshes preset framework choices without
remounting the form. Added runner help distinguishing models from frameworks and explicit
empty/loading/error-aware Harbor setup guidance, including pagination guidance when present.
Real local read-only inspection of the previously selected project found no framework rows;
no profile, credential or permission was created on the user's behalf. Deterministic browser
coverage isolates retained framework lists while saving via the real authorized API and
proves the runner appears without reload and the entered preset name remains. Both
`pnpm test:e2e tests/e2e/workspace-preparation.spec.ts` checks passed (8.5s), including the
existing exact multi-model planning/readiness journey. TypeScript and scoped formatting/
whitespace checks passed. Backend, whole-browser and production-build counts below remain
historical evidence, not rerun for this UI-only fix. No dispatch/gate/backend changes or
paid calls; unrelated user edits preserved.

User-reported Harbor build feedback fix — 31 October2026. Read-only inspection of the
user's local modern Runs view confirmed a persisted package/checksum despite the apparent
no-op. Building is idempotent and does not start a run; the old UI only displayed its
checksum/manifest, with no success state or next action. Shared workbench now shows
Building progress, a focused 'Harbor package ready' heading, explicit saved/reused-package
feedback and a modern Prepare evaluation link scoped to the source task. Modern task/run
lists refresh after success. Source selection is disabled during writes, and an older
package-list response cannot replace the build result. No approval, execution or budget
gate was changed; no provider call made. New deterministic browser test covers503/retry,
in-flight state, focused success, same-package rebuild and exact preparation binding with
blank cap. Targeted browser1 passed (3.5s); shared Harbor browser3 passed (44.3s), including
the classic real-OIDC staged synthetic-check journey and modern build feedback.
TypeScript and scoped Prettier/whitespace checks passed. Backend/unit/full-browser/nightly
production-build counts below remain earlier evidence and were not rerun for this UI fix.
Unrelated AGENTS.md and cloud-runbook edits preserved.

Final nightly usability checkpoint — `740b3b2`, 31 October2026. Overall **partial local**.
Saved preparations open read-only, with explicit fresh creation/blank budget; sole complete
package/preset choices become version summaries. Model/history and readiness focus, task-scope
reset, loading and visible saved-list/detail retry states are browser-verified. Credential
write metadata stays visible when UUID pagination excludes it, prefers fresher GET metadata
and deduplicates later pages. No authentication, project/private-reference, version, review
or spending gate changed. Classic baseline remains `3a17429c3e7bfe0314361dda5209ce890d96c8e3`.
Final `pnpm check` passed. Units224 passed (3.74s). With all workers stopped,
`ANVIL_TEST_HARBOR=1 ANVIL_HARBOR_DOCKER_HOST=unix:///Users/vasudevansundarababu/.docker/run/docker.sock pnpm test:integration`
passed162/2 optional Praxis-export skips in177.40s; fresh/repeated001–030 migrations included.
Final full `pnpm test:e2e`14 passed (2.2m). First final browser run12/14 exposed a real
credential-page visibility issue plus a one-request outage fixture consumed by dev effect
remounts. Both repaired; targeted1/1 and complete14 then passed without weakening assertions.
Read-only final review found no material blocker; production check rerun on final source.
Staged whitespace/credential-pattern scans passed. No secret/private artifact committed.
`pnpm backup:local` / `pnpm restore:test` passed: private backup
`.local/backups/20261031T101237Z-5eac472a`, retained restore database `anvil_restore_a4bf4e87ad55`,
1194 pending reviews/6171 artifact checksums preserved, original unchanged. All row digests
across ten workspace tables match at schema030. Local credential files/wrap key, environment
and Keycloak recovery were not tested. See [current morning report](docs/generated/modern-workspace-morning-2026-10-31.md)
and machine-readable morning/nightly reports; prior entries below are historical checkpoints.
App restored at http://127.0.0.1:3202/workspace with classic comparison and synthetic-only
Harbor worker; live inference/dispatch disabled. No paid calls, external sending, deployment,
push, identity/IAM changes or installs. Unrelated AGENTS.md/cloud-runbook edits preserved.
Next window: check writers/health first, then finish atomic shared spending admission and
credential-mediated execution with mock transports and durable budget/access tests. That
software remains unfinished, as do full profile authorization/People actions, source authoring
and broader M5 acceptance. Native SDK mocks are not live/Harbor-task/structured-output
qualification. Continue nightly automation; this is not completion. Window deadline remains
06:00 Chicago/11:00 UTC, not reset on wake.

04:00 nightly resume — internal credential-bound SDK mock contract verified as `a092a7f`.
No HTTP route, job/ledger writer or
availability promotion was added. Helper requires exact MockTransport, scoped Admin,
current/enabled frozen model and exact current credential/provider binding before key
resolution. Profile/key locks serialize metadata changes; actor UTF-8/token limits are
checked before SDK construction. SDK request guard enforces official HTTPS host/native
endpoint, POST and the bound auth header. No global-key fallback; Gemini mock mode is
explicitly non-Vertex. Unsafe SDK environment overrides fail closed. Native exceptions
are sanitized before SDK logging; response headers/body and final results are inspected
for credential echoes, including escaped/URL-encoded material. Unscannable/oversized
responses fail closed. Invalid JSON output is retained verbatim, never repaired.
Evidence means credential-bound SDK mock contracts only — not live/model/Harbor-task or
structured-output qualification. Native text SDK mode is intentionally unchanged.
`pnpm check` passed; units224 passed; targeted scoped SDK integration57 passed (6.90s);
full isolated integration152 passed/12 opt-in skipped (70.50s). Read-only review found no
blocking issue. The first expanded run had3 test failures because Pydantic rejected an
unpaired surrogate before helper entry; the corrected test mutates an already validated
request and proves the helper's independent fail-closed check. No assertion was weakened.
Browser14 from the previous UI checkpoint remains historical evidence, not rerun for this
internal non-routed increment. No SDK install, external provider request, real key use, paid action,
identity/IAM change, cloud deployment or GitHub push. Deadline remains06:00 local/11:00 UTC.
Staged whitespace/credential-pattern scans passed. Comparison app and synthetic-only worker
restarted; both live switches remain disabled. Unrelated user edits remain excluded.
Next checkpoint should prioritize remaining M5 usability/regression and a candid final
morning report within the existing deadline. Shared spending admission, actual credential-
mediated dispatch, full profile authorization/People actions and source authoring remain
unfinished; do not label mock contracts as completing those features or enable launch.

03:00 nightly resume — model profile versions/disable/pricing verified as `62d9e60`.
Migration030 backfills stable profile headers and immutable connection
version mappings without changing existing connection/config hashes. Current-only CAS and
header locking serialize successors; disable is one-way for the entire profile. Existing
presets/preparations retain snapshots and report superseded/disabled versions separately.
Database guards now reject workspace configuration mutation (including destination drift);
legacy connections keep their existing rules. The earlier drift integration now proves
DB rejection, with a pure readiness test retaining defense-in-depth drift detection.
Admin's focused model editor supports explicit credential-version binding, version history,
optional declared pricing/expiry/source and processing-terms references. USD prices convert
exactly to integer micro-USD per million tokens, with no money defaults. Metadata never
grants pricing admission, rights, provider approval or paid authority; legacy fields remain
false/null and workspace dispatch rejection remains. Classic /providers now selects only
legacy configurations, preserving its response shape and avoiding workspace/global-key mixing.
Read-only review found no blocking issue. Unit221 passed; targeted version/preparation
integration3 and added classic-compatibility integration1 passed. Final `pnpm check` passed;
isolated `pnpm test:integration`95 passed/12 opt-in skipped (60.12s); full `pnpm test:e2e`
14 passed (2.1m), including classic, synthetic Harbor, model versioning/disable and preparations.
Staged whitespace/credential-pattern scans passed; comparison app is running with live flags
disabled. No model calls, identity changes, deployment or GitHub push performed.
First browser assertion used label text for a select; corrected to its exact accessible
combobox role/name. Targeted browser1 passed (3.9s), including320px and pricing conversion.
Screenshot review then moved editing above/hid the long list for a focused accessible form.
Nightly deadline remains06:00 local /11:00 UTC; classic baseline and user edits preserved.
Next safe slice: an internal credential-bound native SDK mock contract using installed
OpenAI/Claude/Gemini adapters. Require explicit scoped SecretStr and httpx.MockTransport;
no default transport or HTTP endpoint, no global key lookup and no change to live launch.
Validate current/enabled exact model/provider/destination/config/credential, actor bytes
and output ceilings. Cover one request/no retries, refusal/truncation/timeout/unknown usage,
invalid JSON without repair, rotation/revocation and secret leakage. Evidence label must
remain 'credential-bound SDK mock contract tested', never Harbor/live qualification.
Shared spending admission and qualified real dispatch, full profile authorization/People
actions, source authoring and M5 refinements remain incomplete. Continue safe local work;
missing real credentials/authority block paid calls only. Preserve the same nightly deadline.

02:00 nightly resume — typed presets and planning-only preparations verified as `b8d65a0`.
Migration029 adds immutable, project-scoped presets, model
allowlists, preparations and exact credential-version child bindings; repeated migration
passed. Admin configures typed Harbor runner, built-in/optional unqualified Semantic Kernel
candidate and optional export-disabled LangSmith tracing. Existing scoped planners/Admins save exact
multi-model/package preparations with one optional aggregate cap, blank by default. UI uses
USD with exact integer conversion; no silent rounding or copied per-model cap. Preset and
preparation saves create no jobs, calls, approvals, agent plans or reservations. All launch
paths remain unavailable. Readiness rechecks current model/provider/destination/config,
credential rotation/revocation, framework bindings and package compatibility without
reading keys, archive contents, private grading or future observations. Review caught a
destination-drift gap; corrected. Workspace model rows no longer inherit global-key presence.
`pnpm test:unit`213 passed; `pnpm check` passed; isolated integration94 passed/12 opt-in
skipped in57.32s. Full `pnpm test:e2e`13 passed (2.0m), including Admin preset/two-model
planning,320px dark layout, refresh, exact $0.012345 conversion and prior blank-budget
snapshot preservation. First targeted browser timed out after its pagination loop clicked
a disappearing final-page button; it now waits for completed responses and explicit busy
states (targeted1 passed in3.9s, followed by full13). Final `pnpm check` passed after UI
changes; staged whitespace and credential-pattern checks passed. Local app and dedicated
synthetic worker restarted. Both live switches remain disabled; classic branch unchanged.
Combined unit/integration invocation initially hit pytest's duplicate module-name collector;
standard separate suites passed without deleting caches or changing tests. No source/data
reset. Nightly deadline remains06:00 local /11:00 UTC. Preserve classic baseline/user edits.
Next incomplete work: model-profile versioning/revocation and explicit configuration/pricing
metadata, followed by separately tested credential mediation/provider qualification and
atomic shared multi-model spending admission. Existing workspace-profile rejection by the
legacy agent path stays enforced. Do not rebuild the completed preparation slice or label
it executable. Full profile authorization migration, People/Limits mutations, source
instruction authoring and M5 keyboard/loading/single-choice UX refinements remain partial.
Missing real keys/authority block live qualification only; continue safe local implementation.

01:00 nightly resume — profile mapping / People read transition verified as `6d272cd`.
Migration028 records immutable, audited Admin/RL Engineer mapping evidence from existing
active engineering/Admin grants; repeated migration passed. No identity or membership
changes. Current-grant capabilities drive modern navigation/editor/preparation controls;
historical snapshots never grant access. Other review/business identities show Legacy
access instead of incorrectly being labeled RL Engineers. People now has one paginated
row per person, with preserved duties in details and explicit unavailable management.
Do not call this a full authorization migration: invitation, promotion and project revocation,
full two-profile engineering permissions and review-policy consolidation remain unfinished.
Admin is not globally assigned legacy Researcher/Data Engineer roles (hidden-reference leak).
Read-only review found no privilege bypass. Targeted integration2 passed including actual
hidden-reference content denial, unchanged memberships/reviews, RLS, pagination and read-only
mapping storage. Initial test used the wrong artifact path; corrected to /content.
`pnpm test:unit`210 passed; `pnpm check` passed; isolated `pnpm test:integration`92 passed/
12 opt-in skipped in57.41s. Full `pnpm test:e2e`12 passed (2.0m), including genuine OIDC
Admin/Engineer boundaries, People390px, classic provider save and staged synthetic Harbor.
Final production check repeated after guarding canceled account-load responses in classic
and modern shells. First browser attempt matched Next's route-announcer as well as the
app denial; selector scoped to main content. Second attempt exposed the provider-save
message disappearing after a late account load; canceled-load guards added. Standalone
marketing retry correctly rejected resubmitting an already-reviewed fixture; dependency-
ordered full suite then passed on a fresh retained journey. No data or approval reset.
Next M4 work: typed presets and planning-only profile preparations, then complete
the explicit profile authorization migration and People/Limits mutations under reviewed
boundaries. No credentials or real paid authority are available; these block live dispatch
only. Classic baseline and unrelated edits preserved. Nightly deadline remains06:00 local.
Read-only next-step review: preserve existing harbor_agents rejection of workspace profiles
(it uses the legacy credential path). Add immutable, project-scoped exact-version preset/
preparation records with typed runner/runtime/tracing roles and one explicit optional group
cap. Save must create no jobs, agent plans, calls, approvals or reservations. All unqualified
adapters remain blocked with consolidated readiness reasons; unknown cost stays null and
budgets start blank. Recheck rotation/revocation without rewriting snapshots. No launch
endpoint or legacy key fallback in that bounded preparation slice.
Local app and dedicated synthetic worker restarted; both live switches remain disabled.

00:00 nightly resume — constrained M4 diagnostic successor editor verified as `9bddc3d`.
Separate screen supports task title/capabilities/rubric binding, rubric labels/weights/
threshold and evaluation protocol policies/limits. Save uses canonical immutable revisions,
current-base locking, If-Match and idempotency; prior approvals and frozen run snapshots
stay bound to their old versions. Current resource becomes an unapproved draft. Source
assets, private references, anchors, calibration and execution binding remain server-side;
instruction changes require a new source import. Revision author or scoped Admin may append;
Admin override is audited. Approval/recommendation self-authorship now follows the actual
current revision author. Historical versions are read-only, with mobile320px coverage.
Full browser11 passed (1.6m), unit202 passed, targeted editor/diagnostic integration5 passed.
Final `pnpm check` passed (format/lint/types/production/OpenAPI); isolated
`pnpm test:integration`90 passed/12 opt-in skipped (54.36s) with registered workers stopped.
Full `pnpm test:e2e`11 passed (1.6m); `pnpm test:unit`202 passed. Staged diff whitespace
and credential-pattern checks passed. Real Harbor full integration95/2 remains historical;
the full browser run did execute the real staged synthetic Harbor software check.
The first test SQL lineage-column assumption was corrected; retained-history coverage now
walks cursors instead of assuming the original run remains on page one. No database reset.
M4 remains partial: explicit two-profile migration, People/Limits actions, source authoring,
qualified model/preset admission and typed compositions remain. Next resume these after
this checkpoint; do not rebuild the completed editor/read slices. Deadline remains06:00 local.
Local app and synthetic-only dedicated worker restarted; classic comparison preserved.

23:00 nightly resume — diagnostic workspace increment verified as `a96af51`.
M2 diagnostic task/run history now joins immutable suite/task revisions (including prepared
runs), with cursor pagination, whole-run finalized-only metrics, exact safe task/rubric/
protocol snapshots and paginated results. Candidate identity, score and pass/fail stay
blinded until finalization. Only finalized, bound internal output is inspectable; raw private
references/checkpoints remain excluded. Comparisons require complete planned cohorts and
matching task/candidate/runtime/version signatures; partial cohorts are descriptive only.
Frozen dataset counts and identity own planning/compatibility when attached to a run.
Diagnostic source switch is available in Tasks/Runs. Mobile390px check caught a project
selector overflow; fixed without weakening the assertion. Targeted modern browsers2 passed
(7.6s), new API integration1 passed, full unit199 passed, production/type/lint/format/OpenAPI
check passed. Isolated normal integration86 passed/12 opt-in skips (54.82s); real Harbor
regression95/2 from the initial checkpoint remains historical evidence, not rerun this hour.
Next work: M4 separate successor editor, explicit two-profile capability migration and
qualified model/preset admission. Do not restart the completed diagnostic read milestone.

Verified initial modern-workspace code checkpoint: `d2dfe82`. Local API/database ready;
legacy and Harbor live inference disabled. Registered app, ordinary worker, web and
dedicated synthetic Harbor worker are running for comparison. Only unrelated AGENTS.md
and Google Cloud runbook edits remain outside the checkpoint. The initial checkpoint
was handed off to the23:00 resume recorded above; continue M4, not M0 again.

Modern workspace autonomous build launched 30 Oct 2026 at 03:08 UTC on 31 Oct
(22:08 America/Chicago). Initial window deadline 11:00 UTC (06:00 local). M0 branch preservation
complete: `codex/anvil-modern-workspace`; baseline `codex/anvil-classic-v021-comparison`.
Nightly thread automation `anvil-nightly-modern-workspace-build` active hourly during
22:00–06:00 local, including checkpoint resumes tonight. No deadline reset on wake.
Resume plan: `docs/build/08-MODERN-WORKSPACE-NIGHTLY.md`. Local preflight passed after
granting access to existing Docker; Anvil infrastructure ports occupied, app ports free.
Current next milestone: M4 full versioned editor,
two-profile migration and qualified multi-model admission/composition.
Unrelated user edits remain excluded. Deployment and paid inference are not authorized.

Nightly progress: M1 implemented modern /workspace routes alongside classic /p, scoped
Harbor task/run pagination, persisted history, reward/coverage/failure/accounting projection,
retained internal evidence inspection, actor/package snapshots and conservative comparison.
M2 initial metadata slice persists multiple named model and typed framework profiles in
PostgreSQL; additive migration026 applied locally. Admin Harbor engineering access added
explicitly; existing PO/software and real paid decisions are not bypassed. Stale-response
guards and project remount prevent cross-project display races. Live score deltas remain
descriptive-only until complete execution-settings compatibility exists.

M3 local slice built: encrypted credential save/rotate/revoke and exact-version model
binding; migration027 applied locally. Dedicated random wrapping key, authenticated
project/credential/version/provider envelope, owner-only descriptor-based filesystem access,
directory fsync and missing-key recovery fail-closed. No raw key read endpoint; cloud writes
blocked. Credential unit6 and integration2 passed with test-only values, including worst-case
escaped maximum input, scope-swapped envelope rejection and missing-wrap-key recovery.
New workspace profiles are explicitly blocked from legacy dispatch: no global key fallback.
Current final checks: pnpm check (lint/format/types/production/OpenAPI) passed; pnpm test:unit
195 passed. Full9-browser regression passed (1.5m), including classic, new profile/key UI,
run history/snapshot/evidence/usage and real staged Harbor synthetic execution. With app
and dedicated workers stopped, `ANVIL_TEST_HARBOR=1 ANVIL_HARBOR_DOCKER_HOST=<authorized
local Unix socket> pnpm test:integration`:95 passed,2 skipped,162.15s. The skips are the two
parameterizations requiring ANVIL_PRAXIS_EXPORT_PATH; no export path supplied. No paid
live qualification claimed. New optional dedicated-worker registration in the local launcher
passed startup against the existing pinned Harbor executable; no dependency installs.
Initial browser failures were test selector issues (required-label suffix, duplicate heading),
corrected without weakening product behavior. Retained-project security test now selects
an originally static task and a genuinely different source instead of whichever task sorts
first; targeted5 passed. Final regression and OpenAPI regeneration completed.
Remaining: complete editor/versioning and profile migration,
multi-model admission/composition, managed cloud credentials, qualified external framework
adapters and broader responsive/access regression. See docs/generated/modern-workspace-nightly-report.md.

Run-workspace design extension: task-level history, run dashboard, all-attempt results,
failure modes, observable trajectories, bound task/rubric/evaluation snapshots, usage
and baseline comparison are now included in the review prototype and spec21 section11.
Separate “Edit as new version” editor is proposed; no historical run inputs are edited.
Prototype syntax and browser checks passed for dashboard, version-editor preview and
metric comparison; no console errors. Synthetic examples only; no application changes.

Admin redesign proposal: see
`docs/product/21-ADMIN-WORKSPACE-AND-FRAMEWORKS-UX-SPEC.md`. Clickable review screens
cover Overview, Models & keys, Frameworks, People, Limits & usage, Tasks and Runs.
Admin includes all RL Engineer capabilities within assigned projects. Framework
configuration distinguishes Harbor execution, LangSmith tracing/evaluation and
Semantic Kernel agent orchestration; proposed adapters are not represented as live.
Browser checks passed for navigation, example model save, Admin capability display
and Tasks → Runs setup; no console errors or horizontal overflow at the preview width.
Design only: no application implementation, credentials, invitations, calls or deployment.

Design-only request: prepared product spec
`docs/product/20-MODEL-CONFIGURATION-AND-HARBOR-OBSERVABILITY-SPEC.md` and a separate
interactive review prototype for Admin Models & keys → Harbor model selection → run
comparison/observable trajectories → user journey. OpenAI/Claude/Gemini multiple profiles,
write-only credential-store proposal, exact-version multi-model groups, shared cap and
failure/unknown accounting are specified. No application code, credential provisioning,
IAM, live calls or deployment changes in this design increment. Current app remains0.2.1.
Prototype checked in a local browser: navigation, metadata-only save, disabled key entry,
missing-key selection, cap/readiness preview and task-failure/unknown trajectory details.
All profiles/results are simulated. Secret-store backend/IAM scope and Anvil policy changes
require review before implementation; existing Anvil paid gates are not implicitly removed
by the separate Praxis Admin-only request.

v0.2.1 disabled cloud preparation deployed and verified. User authorized code and existing-host
deployment preparation only; no key/authority values, paid activation/calls, new IAM,
credentials, identities or approvers. Separate Harbor cloud admission defaults false;
legacy cloud live/email remain forbidden. Read-only private directory mounts reach API
and dedicated Harbor worker only. Historical marketing model/price/cost defaults removed
from provider setup; explicit current values required. See
[secure later handoff](docs/runbooks/harbor-cloud-admission.md).

Passed so far:181 unit,90 isolated integration (188.66s), production/type/lint/contracts,
API UID10001/root-worker empty read-only mount rehearsal and Compose mount isolation.
Full8-browser regression passed (1.4m); final production/type/lint/contract check passed.
Disabled existing-host rollout passed API/database/TLS/OIDC/web/private-admin smoke.
Release code checkpoint `4693f00f0aec1eb54bd212ac27a658f918ec0867`; authorized existing-host
rollout completed as `4693f00-1793412536`, Cloud Build
`3c163d82-a103-4757-9683-7b1166c9734e` SUCCESS (us-west1). No paid activation or inputs supplied.
Post-upgrade evidence `artifacts/test-runs/cloud-v021-disabled.json`: version0.2.1,
legacy live=false, Harbor live=false, absent key/authority, API UID10001/root Harbor UID0,
private directories UID10001/mode0700 and read-only mounts on API/Harbor only. Normal
worker/web have neither private mount; API has no Docker socket. Historical, approval and
paid-ledger fingerprints all match before; paid-call records0. Verification command:
`python3 /private/tmp/anvil-v021-verify.py` (read-only metadata/fingerprint checks, retained
sanitized output above). Local Python's missing CA store failed the first final HTTPS
probe; system curl with certificate validation passed. No TLS checks were disabled.
Saved historical/paid-ledger pre-upgrade fingerprints in ignored
`artifacts/test-runs/cloud-before-v021-fingerprints.json`. No paid calls made.
First browser attempt caught a legacy test expecting an auto-filled historical model; the
test now explicitly selects its fixture model while leaving current pricing/cost empty.

Actual Praxis cloud exports (7230978b) now qualified in local real Harbor, exact bytes:
single SHA `15538a0c8a3f041a0fe46685f2c770b05e3cbcbf3f8b2c71a63f103f02133945`,
package `263cd426a57b6f9290c3920a2ee15a605903c9cc7985b1f91a373fd82a6ec13f`;
staged SHA `557cf87b43ba4dd6c3bb2bac6e7c558021abbf1908803bb1380f2e77015d43d4`,
package `5900ac88e97357fd2771e5a5bc1bc8528352bdd120bb68e5c48df6eac4c8007c`.
Each passed reference reward1 and deliberate constraint-failure reward0:2 tests/21.56s
single and2 tests/23.49s staged. Evidence: ignored
`artifacts/test-runs/praxis-harbor-<source SHA prefix>-<candidate>.json`.
Automated local test identities only; no human approval/model performance/paid-call claim.
User restored sign-in. Both exact cloud files imported/built/inspected in deployed Anvil;
both source/package hashes match local execution. Single package ID
`a5c31954-d9a4-4116-a629-86975952d4d3`, staged `e9e77084-4216-44de-a22b-28cbcafe6357`.
Read-only deployed verification: both unapproved,2 active POs,0 checks. Execution still
needs independent PO approval. No self-approval attempt was repeated. Staged actor view
shows only stage-commit and its revealed evidence. Screenshot evidence:
`artifacts/test-runs/cloud-imports-built.png` and cloud-single/staged-package.png.

Release checkpoint: `bae6260fe7995a080674125bcd65512b61148f94`, branch
`codex/praxis-harbor-v0-2`. Final Harbor browser test passed30.4s; final production check
passed. Automatic approval review rejected the cloud rollout because AGENTS.md says
"No cloud deployment" and it could not verify a direct override. No release cloud mutation
occurred on that attempt. User then explicitly authorized this existing-host rollout and
overrode AGENTS.md's cloud-deployment prohibition for release bae6260. Rollout completed;
API/database ready, version0.2.0, TLS/OIDC/web/private-admin smoke passed. Paid inference remains disabled.
Cloud Build: `6b53ac74-fb9b-435f-bb7d-5a34dda45600`, region us-west1;
release tag `bae6260-1793406451`. Existing VM only; schema025 verified. Historical counts
unchanged immediately after upgrade:4 revisions,3 artifacts,0 episodes,0 assessments.
User's first real sign-in and deployed roles verified in IAB.

Resumed acceptance: coordinator completed exact-byte authenticated staged envelope import,
payloadSHA `a16412f2d137022b996cbd1be6d6d23664f4eb360b7a0be368579d5001067b30`,
packageSHA `79a039d66422c0ef5fd917f21eaa9b3be5e6984acf48a7acc830e8e9df2b285b`.
Deployed reference/negative/results acceptance is BLOCKED: creator cannot approve their own
package when multiple active Product Owners exist. Do not impersonate, create an approver,
alter membership or bypass the gate. Corrected cloud imports/builds passed as above;
independent Product Owner approval is the remaining deployed-execution gate.

2026-10-30 — **v0.2.0 deployed; authenticated execution acceptance blocked.** Backend/web0.2.0,
additive migrations001–025 applied locally; fresh/repeated migration smoke passed.
Praxis v1/v2 import, immutable Harbor0.25 packages, staged evidence isolation,
reference/no-op/negative checks, retained analysis and guarded agent mediation implemented.
174 unit tests passed. Production/type/lint/format/API-contract check passed. Full isolated
integration:89 passed (177.39s). Six baseline real-OIDC browser journeys and the new Harbor
browser journey passed, including the history-label refresh (30.4s). Deployment checks pending. Earlier runs caught an expired historical
mock window, a test UUID/string mismatch in sampled second grading, and interference from
independent browser/worker activity in exact event-count tests. Repaired only the test
fixtures and ran sequentially with the app worker stopped. No paid calls made.

First real invitation created on existing GCP host: username `anvil-admin`, email
`admin@adi-labs.ai`, roles Admin/Product Owner/Researcher. Protected temporary credential:
`.local/invitations/anvil-admin.json`; first login forces password change. No email sent.
The reserved username `admin` was rejected without modifying its existing identity.
Full Library-field reconciliation and new-task paid execution remain unverified/blocked.
Resume from the active tests and [workbench runbook](docs/runbooks/praxis-harbor.md).

2026-10-01 — **Deployed to Google Cloud: https://anvil-34-36-217-66.sslip.io** (commit
`401f98e`, project `adi-anvil-mvp-2026`, us-west1-a). The org policy
`compute.vmExternalIpAccess` forbids VM external IPs, so per user choice the VM is private
(Cloud NAT egress, IAP SSH) behind a global external Application Load Balancer with a
Google-managed certificate for `anvil-` and `auth-34-36-217-66.sslip.io`; Caddy routes HTTP from
load balancer ranges only. Billing slot freed by the user unlinking empty `cs-project-kx8bsqkz`.
Deployed smoke passed: backend HEALTHY, API health, OIDC discovery issuer, TLS, web 200,
HTTP->HTTPS 301, login redirect 307, unauthenticated `/me` 401, public Keycloak admin 404.
Not yet run on GCP: first invitation and browser sign-in, fixture run/review/report journeys,
worker restart, upload persistence, snapshot restore. Live inference and email remain disabled.

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

| Milestone                                 | State                                                           | Evidence                                                                                                                       |
| ----------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| M0 Preflight, locks, isolated scaffold    | Verified local path                                             | Independent locked offline clean-checkout install/build, named services, pinned images and safe launcher                       |
| M1 Identity, API/DB, shell                | Core path verified; security matrix incomplete                  | Real OIDC11 identities, CSRF/role/project negatives, RLS; no production identity readiness claim                               |
| M2 Intake, qualification, suite/protocol  | Core path verified; baseline gaps remain                        | Source versions/receipts, rights expiry, rubric/task reviews, frozen bindings; general uploads quarantined                     |
| M3 Durable fixture evaluation + review    | Core path and400-episode processing verified                    | Blinded double grading, dispute/invalidity, SIGKILL recovery, cancelled/unknown states;400 human reviews intentionally pending |
| M4 Diagnostics and graph                  | Core bounded local path verified                                | Family/capability/task/episode/finding links, atomic ordering, actual outage/rebuild, restored graph and keyboard navigation   |
| M5 Report, release, Sales Kit             | Core local path verified; semantic claims remain human-reviewed | Descriptive claim registry, real downloads, one-page visual QA, rights invalidation and network-free mail simulation           |
| M6 Provider adapters and authorized smoke | Mock contracts passed; live blocked/unqualified                 | 73 SDK transport contracts; no inference; paid gate integration incomplete                                                     |
| M7 Verification and morning handoff       | Current local evidence recorded; full acceptance partial        | 89 unit/64 integration, production/browser/load, independent startup and schema012 recovery passed; live/remote CI not passed  |

Build agent maintains below: start/deadline, current commit, versions, last passing command, failures, pending questions, next exact action, local URLs/processes and safe resume instructions. Keep secrets and raw candidate/source content out of this file.

Latest evidence (03:16 UTC): `python3 scripts/local.py migrate && python3 scripts/local.py seed` passed; `python3 scripts/local.py integration` passed 2 tests; `pnpm exec playwright test` passed 1 real-login journey in 10.3s. Fixture expected numeric outcomes verified. Initial E2E failed on a too-short test evidence quote; corrected to full JSON field span, preserving product validation.

Runtime URLs: web http://127.0.0.1:3202; API http://127.0.0.1:8200; Keycloak http://127.0.0.1:8180. Credentials: `.local/demo-accounts.md` (owner-only). Logs and process registry in `.local/`. No model calls made.

Environment issues: optional Playwright Chromium download failed (network timeout/DNS); tests use installed Chrome with isolated profiles. Turbopack production build failed on subprocess port permission; supported webpack build being tested. Resume: review restart/dispute tests, graph projection/fallback, report/downloads, provider mocks, remaining P0 hardening.
