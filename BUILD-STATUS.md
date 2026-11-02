# Build status

## OpenAI usage accounting repair — 2 November 2026

All three cloud golden imports are Ready, but real evaluation comparisons are
NOT complete. Each task dispatched one Astra request and stopped with
`response_model_or_usage_not_admitted`; all three outcomes remain unknown.
Read-only cloud verification confirmed the other 15 trials cancelled, with no
Claude or Gemini dispatch. Original reservations remain intact; actual charges
and request IDs are unavailable. Scoped provider log inspection did not recover
the three responses. Do not retry or retroactively classify these calls.

The documented nested cache-write lifetime breakdown reproduced a parser
rejection. The repair validates exact counter types, totals and admitted 30-minute
pricing, rejects unadmitted lifetimes, and retains only safe response/model/token
metadata for future reconciliation failures. It does not relax exact model
binding, budget reservation or the unknown-outcome no-retry gate. This is
consistent with the observed failure, not proof of the lost original payloads.

Validation: 323 unit tests passed; 16 workspace execution integration tests
passed (53.88s), including unknown metadata privacy and no-retry regression;
`pnpm check` passed; Ruff check/format passed for all five changed Python files.
Evidence: `/private/tmp/anvil-usage-unit.log`,
`/private/tmp/anvil-usage-integration.log`, `/private/tmp/anvil-usage-check.log`,
and `/private/tmp/anvil-live-call-status.log` (local, not committed).
Repair is local pending rollout; cloud remains c2d9792. Next: deploy the reviewed
repair with no active requests, then resolve authorization/accounting for a new
diagnostic before any further paid dispatch. Never release unknown reservations
or substitute a successful fixture result for a real model result.

## Cloud native process tracking — 2 November 2026

Deployed c2d9792-1793644383; Cloud Build65946f59-c809-4980-8b4d-3a1792792c1e
and API/TLS/OIDC startup passed. Final-source import integration rerun:11 passed
in335.33s, including all3 goldens/18 controlled trials. Actual deployed native
tool-agent smoke passed Linux process identity, gateway callback, real container,
empty-output grading and a separate nonzero0.375 software grading wire witness.
Both standalone checks made0 provider calls and0 database writes, with
model_performance=false; no fake evaluation result persisted. Harbor-only gate
restored after no active generation; API/database ready, ordinary inference off.
Both prior failed trials have0 provider-call rows; remaining trials cancelled.
Current saved groups: Marketing30bbd998, KYCce3b108d, Fraud208d45b3, each16.66USD.
Run attempt blocked by automatic approval review because fresh sign-in after final
deployment was not confirmed and the600s authorization window may have expired.
No workaround/indirect dispatch attempted. Fresh user sign-in required; paid model
comparison remains incomplete. Do not redeploy/restart once requests are active.

Fresh sign-in admitted saved Marketing group5acd39e7. Native agent failed during
process tracking; workspace contains task/runtime.log but no process.json. Confirmed
cloud slim image has no ps utility, while /proc is available. Process identity now
uses Linux boot ID/PID/start tick without an external binary, retaining ps fallback
for local non-Linux hosts. PID-reuse regression,313 units and full production check
passed. A cloud native tool-agent/gateway/empty-output grading software smoke has been
prepared with a controlled done action, zero provider calls and no database writes;
must pass before requesting another live launch. This is not model performance.
No completed real evaluation claim. Source imports remain Ready. Latest failed
trial f7a223b7 is under read-only provider-ledger verification before recovery.

## Cloud live-trial work-volume repair — 2 November 2026

Deployed850c7a1-1793643419 after backup anvil-pre-workdir-20261102 completed.
Cloud Build d6d2704a-a25a-4c4e-b6da-f70ecced29db succeeded; API/web/Harbor worker
actual image tags verified running850c7a1. API/database/TLS/OIDC ready; ordinary live
inference disabled, Harbor-only gate restored after verifying no generation active.
All3 new comparison groups saved with exact approved3 models,2 repetitions,2048 output
tokens,10 steps,300s and16.66USD each (49.98USD combined). Marketing5acd39e7,
KYCce3b108d,Fraud208d45b3. Paid launch blocked by normal600s recent-sign-in check;
fresh user sign-in requested. No paid evaluation result is claimed. Do not create
replacement groups or reset caps; use these saved groups after actual reauthentication.
Earlier zero-provider-call failure/cancelled children and reservations remain retained.

All3 golden sources are now Ready in cloud with real generation; Marketing reused
retained code at0.071888USD, KYC generated/qualified, Fraud generated at0.052005USD
and qualified. Saved keys verified; Astra/Gemini immutable versions corrected to
the exact approved IDs. Harbor preset with all3 models saved. First Marketing group
fcb9472c failed on trial1 before any provider call (read-only ledger query returns
zero call rows). Other5 trials cancelled through normal UI; failed evidence retained.
Readiness and exact binding pass, but tool-agent execution hardcodes read-only
/app/.local/harbor-checks instead of configured /var/lib/anvil/harbor-checks.
Shared work-directory helper now used by both trial paths. Cloud read-only-authority
regression,312 units and full production check passed. Deployment and live recovery
pending; do not describe this as18 completed paid trials. No ambiguous dispatch retry.

## Live import coverage repair — 2 November 2026

927d82e coverage repair deployed as927d82e-1793641835; Cloud Build
d74a48a4-8d2f-4557-8995-254905b2eb8d succeeded, startup/API/TLS/OIDC checks passed.
Backup anvil-pre-coverage-20261102 completed. UI Test again exposed a separate
PermissionError: two root-worker artifacts were0600 UID0, API UID10001. Existing
project artifacts otherwise UID10001/0600. Root writer now preserves artifact-volume
owner, keeping files0600/folders0700; non-root writers never chown.311 units and full
production check passed. Narrow repair of the two existing root-owned project files
authorized; no content/hash/database modifications. Ownership rollout/retest pending.

User reported cloud generation failure for M-BUDGET after $0.071888 accounted cost.
Read-only inspection of retained revision8047a75d confirms its rule references
over_limits, whose expected_checks already contains M-BUDGET but documentary covers
omits it. Validation now reconciles that redundant omission only from an existing
explicit assertion; no expected outcome, fixture, code or business rule is invented.
Unknown test references and references with neither declared nor asserted coverage
remain rejected; positive/negative assertion and isolated execution checks remain.
Generation prompt explicitly explains fixture-ID/covers/assertion consistency.
Final309 units and full pnpm check/production build passed. All11 import-pipeline
integration checks passed in334.98s: all3 goldens generated,7+7 grading/withheld cases
each, native Harbor smokes,18 controlled-provider evaluation trials and3 notebook
successors. First integration attempt omitted Docker opt-in/socket and failed; rerun
used ANVIL_TEST_HARBOR=1 and the verified existing local Unix socket, with no security
control removed. Cloud rollout and real model evaluations remain pending. Do not call
this deployed or the golden live journey complete. Dockerfile/Compose already emitted
by the compiler; tests verify pinned image and isolation files explicitly.

## Gemini qualification follow-up — 2 November 2026

Official Gemini3.8 Flash supports LOW/MEDIUM/HIGH thinking levels; the existing
structured adapter's zero thinking-budget request was not an appropriate3.8 control.
For exact gemini-3.8-flash only, use SDK ThinkingLevel.LOW and retain2048 output ceiling,
thought-token accounting, exact returned-model binding and one-attempt transport.
Wire-contract regression accepts the SDK's protobuf field spelling and rejects any
thinking-budget override. First assertion expected camelCase while installed SDK
uses thinking_level; corrected the test, not the runtime security checks.
Passed305 units and full pnpm check/production build. No dependency or SDK install.
This is compatibility qualification, not a successful live Gemini call.

Anvil025cbff is deployed, protected snapshot anvil-pre-live-demo-20261102 READY,
generation key metadata probe200 confirms gpt-6.1-sol and gpt-6-astra available,
zero inference calls. On the new Harbor image all3 golden environments passed their
2/4/4 tool contracts,7 verifier fixtures and7 held-out QA cases each plus native nop
smokes, zero model calls. Harbor-only runtime is gated; ordinary inference/email off.
All3 attempted generation submissions were refused by the fresh-sign-in gate; no
import revision or paid request exists. All3 evaluation credentials remain absent.
User asked to sign in and save keys; actionable input email sent to admin@adi-labs.ai.
Gemini stable pin approval is separately pending. Do not weaken recent authentication,
admission or exact model binding to meet11:00CST (17:00UTC). Overall evaluation ceiling
is50USD across3 task groups,2 repetitions/model,18 trials; each agent run can contain
multiple provider calls, bounded by10 steps and the aggregate caps, not18 API requests.

## YC live-demo preparation — 2 November 2026

User authorized daytime work toward 11:00 America/Chicago, existing-target releases,
real golden evaluations with gpt-6-astra, claude-opus-5-5 and Gemini Flash latest,
two repetitions/model/task, one combined evaluation cap of $50 (18 planned runs).
Generation retains its separately authorized gpt-6.1-sol $10/whole-import cap.
Gemini alias must resolve and bind a concrete supported version before comparison;
do not silently admit an unknown price/version. No live evaluation has run yet.

Cloud project credential storage implemented using the existing fixed Secret Manager
resource and workload grants: exact disjoint generation/project binding shapes,
canonical project/credential/version IDs, provider checks, immutable private locators,
no plaintext index, readback binding checks; existing Admin/project/recent-signin gates
preserved. No new IAM or public credential endpoint. Added verified standard Opus5.5
and Gemini3.8 Flash cost support; aliases remain unpriced until resolved/pinned.
Sources: https://platform.claude.com/docs/en/about-claude/pricing and
https://ai.google.dev/gemini-api/docs/pricing (2 November); no cache/fast-mode controls
introduced. Existing cache/usage guards and budget reservation remain in effect.

Passed: 304 units, three credential API integration tests (including managed-cloud
write/readback metadata, rotation and access denial), production pnpm check/build.
First integration attempt could not reach DB under restricted execution; authorized
local-DB rerun passed. A renderer experiment failed its disabled-by-default regression
and was withdrawn; deploy still defaults all paid dispatch off, with separate explicit
runtime activation only after user-approved models/cap and application admission.
Formatting failures corrected before final check. Deployment and paid checks pending.
Preserved unrelated AGENTS/runbook edits, generated next-env and existing demo video.

## YC release complete — 1 November 2026 (America/Chicago)

Anvil application ec210a9 (`ec210a9-1793593400`) is deployed on the existing host;
API/web/Harbor images independently match the new tag and run. Modern-only root,
legacy redirects, TLS/OIDC/login-form checks passed. Managed generation credential
transferred by stdin directly to Secret Manager and bound readback verified; cloud
gpt-6.1-sol cap exactly$10/import. Local$20 setting unchanged. Runtime generation=true,
paid evaluation=false. All3 cloud v1.1.0 goldens passed actual MCP/tool contracts,
7 generated fixtures +7 held-out QA each and native Harbor nop smoke (zero model calls).
Final modern browser suite14 passed in1.0m after fixing two ambiguous test selectors;
301 units and production checks passed. See docs/generated/yc-release-2026-11-01.md.

Praxis ddc8446b /yc-ddc8446b-20261101 deployed to all four existing services, migration
praxis-migrate-2qpbs succeeded, existing users/data preserved with demo setup skipped.
Version, console/candidate availability and `/readyz` DB/Redis checks passed.121 shared,
452 API tests and typechecks passed. Both repositories PUBLIC; reviewed release branches
pushed explicitly, README/architecture/test docs updated. Praxis default main received
documentation only, without changing its default-branch setting or merging application
history. Backup receipts: SQL1793593073237 SUCCESSFUL; anvil-pre-yc-20261101 READY.
Classic Git comparison remains untouched; unrelated AGENTS/cloud-runbook edits and SDK/
video artifacts preserved. First Anvil startup/pull failed; retry and nested mount repair
succeeded, and image-identity checks now prevent falsely certifying an old healthy version.
No paid model smoke calls, email, data reset or volume deletion. Authenticated cloud user
workflow/live model quality remains not-run; use assigned account for sign-in.
Requested rollout is complete: future night checkpoints should not repeatedly redeploy.

## YC existing-target release underway — 1 November 2026

Both GCP authentications verified. User authorized public repositories and rollout;
only installation code generation may spend (gpt-6.1-sol,$10/import), evaluations off.
Modern-only entry/legacy redirects implemented; classic Git baseline preserved. Added
scope-bound Secret Manager generation storage with private locator indexes, workload
identity, fixed secret resource and per-secret version-add/access grants. Shared worker
temporary path supports host Docker bind mounts without granting API Docker access.
Verified301 units,4 focused real-browser journeys, web TypeScript, production pnpm check,
secret scan and shell syntax. Praxis121 shared +452 API tests and typechecks passed;
expired-session null guard and explicit skip-demo-setup added. Both pre-release backups
completed: Praxis SQL1793593073237 SUCCESSFUL; Anvil snapshot anvil-pre-yc-20261101 READY.
Cloud generation secret resource created, no key value logged/published. Rollout/key
transfer and final deployed verification remain pending. No paid smoke calls authorized.

## Next authorized scope: YC public release — 1 November 2026

User confirmed public Anvil/Praxis GitHub repositories, rollout to existing GCP targets
and budgets, modern-only Anvil journey, concise architecture/test READMEs, and generation
only (gpt-6.1-sol,$10/import) with secure cloud key transfer. Paid evaluation remains off.
See docs/build/09-YC-PUBLIC-RELEASE.md for exact decisions and release gates. Both GCP
logins require browser reauthentication; GitHub works. Nightly automation updated to
this scope. No repository visibility change, push or cloud mutation performed yet.

## Nightly regression checkpoint — 1 November 2026, 22:05 America/Chicago

Resumed completed modern-workspace scope at8f53891; no feature expansion. Tonight's
deadline remains2 November06:00 America/Chicago. Passed `pnpm test:unit` (299, one
existing Authlib warning), `pnpm --filter @anvil/web exec tsc --noEmit`, and
`pnpm exec playwright test tests/e2e/golden-executable-import.spec.ts tests/e2e/task-run-history-comparison.spec.ts`
(3 passed in17.0s). Classic comparison remains3a17429c3e7bfe0314361dda5209ce890d96c8e3.
Preserved unrelated AGENTS/cloud-runbook edits and untracked user-requested demo-video
artifacts. No paid dispatch, cloud change, push, service restart or new live-result claim.
Full production rebuild/native integration not repeated this checkpoint: native3-golden
acceptance just passed in291.81s; active local app and separately authorized user generation
settings were left intact. No new actionable failure or user action from this checkpoint.

## Live generation clarification repair — 1 November 2026

The Marketing live model requested tool-response semantics and harness responsibilities
missing from the prompt. Added isolated safe-tool preflight before paid dispatch: actual
MCP result shapes plus bounded operational status/path markers reach generation; business
response values, prohibited tools and private QA remain excluded. Prompt now specifies
parsed asset inputs, completed/denied events, result-vs-envelope, harness reset/persistence
and no invented scoring IDs. Missing business semantics still block; unresolved is never
silently cleared. Added privacy/prohibited-tool regression. Verified299 unit tests,
`test_import_pipeline.py::test_all_three_goldens_generate_validate_publish_and_notebook_roundtrip`
(1 passed in291.81s, covering all3 goldens,18 native Harbor trials and3 notebook successors,
controlled providers), web TypeScript, Ruff/format/Prettier/diff checks. Restarted only
idle import worker; app HTTP200. No live retry initiated or spending limit changed.
User's current binding allows20 calls,2 used; old clarification reports remain historical.

Generation-limit diagnosis: the user's Marketing import spent $0.066990 of $10 but
exhausted its configured one-call limit. Its first live response requested clarification
about tool response schemas; it did not produce a Ready package. Split future call-limit
errors from budget-limit errors; retained legacy reports explain both. No cap/call-limit
changes or retry made.298 unit checks, Ruff, scoped Prettier and diff checks passed.

Task readiness visibility: green badges now explicitly mean a validated executable is
available (Ready to run); ungenerated/active tasks use amber Not ready indicators and
failed generation uses red. Unprepared tasks use neutral Complete setup links instead
of green Run buttons. Detail/Run/import views expose readiness separately from progress.
Run admission still checks model credentials, server controls and budget; package
readiness does not bypass those checks. Verified web TypeScript, golden browser tests
(2 passed, all three ungenerated tasks), formatting and diff checks.

Live-progress visibility follow-up: the checklist is now visible before generation
starts, labelled Live import progress, and receives focus/scroll when submission starts.
Previously it appeared only once starting/active/revision state existed. Verified web
TypeScript and golden browser tests (2 passed); no model request was made.

## Live import progress — 1 November 2026

Import & generate now immediately displays submission activity, elapsed time, and an
automatically polled stage checklist. The worker persists safe stage names for source
validation, generation, isolated verifier/tool qualification and native Harbor smoke
checks; completion or failure remains explicit. No fabricated percentage or private
fixture values are streamed. Restarted only the idle registered Harbor/import worker.
Verified:298 unit tests,2 golden browser journeys including simulated live-stage polling
through completion, web TypeScript, scoped Prettier and Ruff passed. No paid calls.

## Run page generation handoff fix — 1 November 2026

Fixed misleading model/budget guidance on tasks without a validated package. The Run
page now shows the executable-generation report and actions directly, explains why no
execution group can yet be created, and reloads package choices when polling observes
a Ready revision. Existing task sources link to their own package builder. No run or
paid generation was started, and no execution admission controls changed. Verified:
`pnpm exec playwright test tests/e2e/golden-executable-import.spec.ts` (2 passed,
including all three golden imports/Run pages), web `tsc --noEmit`, scoped Prettier,
and `git diff --check` passed.

## Spec24 final local acceptance — 1 November 2026

The full local executable-import pipeline is implemented. All three golden files pass
the application path: API intake, installation-wide generation settings, cumulative
import charging, controlled provider SDK generation, isolated Python qualification,
withheld private QA, supplied-image MCP probes, native Harbor execution and notebook
successor validation. Final acceptance: **11 passed in326.40s**, including18 native
evaluation trials (2 models ×3 repetitions ×3 tasks). Raw Harbor rewards match trusted
grades. Also passed:298 units,49 related integration checks (2 external-file skips),
production checks/build,6 browser journeys and21 independent oracle cases/9 native trials.
See docs/generated/executable-import-build-report.md for commands and limitations.

These are software checks with controlled model responses, not live model performance.
No paid calls, deployment or push. Actual generation still needs installation Admin
scope, a real standard model/key/cap and exact live-processing authority. Notebook support
is download/manual Colab or Jupyter editing/validated return, without hosted provisioning.
The supplied image is local, not published. Cloud credentials still require the managed
secret-store adapter. Classic and unrelated edits are preserved.

Continuation and initial-slice entries below are historical and superseded by this entry.

Spec24 continuation — user requested a separate background implementation agent to
finish the pipeline and test all three goldens. One source writer is active. Installation
settings, cumulative generation ledger, restricted Python artifacts, supplied-image/MCP
qualification, native bounded tool-agent trials, notebook return and artifact editing
are implemented. Broad verification passed **49 integration /2 external-file skips**,
**5 real-browser journeys**, **291 unit checks**, production build, and the independent
**21 oracle cases /9 native reference trials**. The integration path includes all3
imports,18 native Harbor evaluation trials (2 SDK-mocked providers ×3 repetitions each),
and3 notebook-successor validations. These are software checks, not live model results.

The earlier verifier-staging failures were resolved without making the candidate root
writable: root-only executable verifier staging plus Harbor's supported automatic log
mounts. Private generated graders execute separately. Final exact-source Admin processing
permission and malformed-notebook checks are being rerun before the checkpoint. Testing
readiness has no human approval gate; paid external processing still needs exact current
Admin permission and the independent generation flag/config. No paid calls, remote push
or deployment; prior delivered checkpoint remains35f8b60 until final checks finish.

Spec24 implementation launched, 1 November 2026 — user explicitly started implementation
and requested at least3 complete shared Praxis/Anvil golden export files. Initial contract /
import / conformance slice built; full spec24 remains partial. Added strict
`praxis.anvil.task.v3` under unchanged exact-byte `praxis.anvil.export.v1`, JSON Schema,
safe relative assets with byte hashes/strict embedded JSON, description-first rules,
supplied image digest/kind, MCP schemas/probes and optional private QA fixtures. Actual
prose-only sources need not provide fixtures: generating them is a later pipeline step.
Source payloads cannot choose generation credentials/caps or destination project scope.

Delivered contracts/praxis/golden-v3/{01-marketing,02-kyc_aml,03-fraud}.export.json and
readable .task.json companions, with original fictional inputs, public tool contracts,
runtime/final constraints, grading rules and21 private expected-outcome cases. Every
criterion/constraint has both passing and failing assertions. Explicit actor allowlist
excludes private oracles, expected rewards, probes and canaries. No reference answers
are supplied to the scripted candidate; its solutions compute from public MCP observations.
New v3 source intake persists/idempotently reloads real source/lineage records and renders
View Task safely. UI says Source validated / Needs generation, not Ready. Legacy Build
rejects v3 with an actionable409 until general generation/qualification exists. Existing
v1/v2 remain supported; no arbitrary source code executes on import.

Supplied local fixture image anvil-golden-tools:1.0.0 was built from the existing pinned
Python base with stdlib-only MCP services and public synthetic inputs. No dependency/SDK
installation, cloud push or host/provider secrets. Its actual Docker image ID is frozen
in the exports and distinguished from a pullable OCI digest. Native Harbor rehearsals
verify startup, actual advertised MCP schemas, tool observations, derived outputs and
guardrail denials, with grading injected after actor execution. Trusted reference
compiler/evaluator are explicitly software fixtures, NOT production model-generated code.
Generalized image initialization/read-only mounts/independent probes remain worker work.

Download artifacts: artifacts/golden-harbor-imports/praxis-anvil-golden-v3.zip (exports,
schema, reference sources, manifest and report) plus separate43MiB supplied-image tar.
Delivery artifacts are ignored; source fixtures/schema/scripts are versioned. No claim
that this local image has been published or is already available to GCP/Praxis runtime.
Praxis repository was not modified; the shared README/schema/goldens are the exporter target.

Verification: `pnpm test:unit`279 passed (4.49s). Real import/backward-compatibility suite
with ANVIL_TEST_HARBOR=1:18 passed/2 skipped (112.60s); two actual-Praxis-export-byte
fixtures require external files not supplied to that legacy test and are not passed.
An old negative test expected seeded Admin ineligibility403; updated it to assert409
and the exact missing-authority message under the user's already-approved Admin policy.
No application authorization logic was weakened. `scripts/verify_golden_imports.py --native`
with explicit Docker opt-in:3 tasks,21 oracle cases,9 actual Harbor trials passed
(positive1.0/empty0.0/guardrail0.0 per task). All are synthetic software checks, not model
performance. UI suites golden-executable-import/workspace-task-pages/workspace-preparation:
4 passed (48.1s), including all three real uploads, hidden-oracle exclusion, accurate
not-ready feedback and existing run journeys. Final `pnpm check` passed lint/format156
files, frontend formatting, types, production build and API contract. No paid call,
new schema migration, real-user key/budget change, deployment, email or GitHub push.

Next incomplete spec24 milestone: installation-wide generation model/credential and
whole-import ledger, then model-generated artifact validation and supplied-image/tool
qualification. Actual live generation requires an Admin-configured exact model/key/cap;
none is invented from this build authorization. Continue safe local/mock implementation,
then bounded multi-step candidate execution and Colab/Jupyter round trip. Source-validated
v3 imports must remain non-runnable until those requirements are implemented and pass.
Classic baseline and unrelated AGENTS/cloud-runbook edits remain preserved.

Executable-import design handoff, 1 November 2026 — user requested final specification,
journey and screen modifications after sequential clarification. Consolidated in
docs/product/24-PRAXIS-HARBOR-EXECUTABLE-IMPORT-SPEC.md. Confirmed Harbor-only execution,
model generation of verifiers/guardrails/fixtures from descriptions; supplied Docker
images and safe tool probes; multi-step tool agent; one installation-wide generation
model and one Admin-default cumulative cap per import including regenerations; separate
evaluation models/budgets; Admin/RL Engineer edit/test/regenerate; Colab preferred with
JupyterLab alternative; successor drafts with automatic revalidation; no human approval
or Mark ready gate for testing. Automatic Ready requires the required checks to pass.
Colab/runtime feasibility checked against Google's official runtime/FAQ documentation;
the spec distinguishes notebook editing from authoritative controlled-image validation.
No application implementation, model call, notebook/cloud provisioning, IAM change or
deployment was performed for this handoff. This new expansion remains documentation
until the user launches implementation; earlier nightly authority covers the existing
approved slice/regressions, not automatically this new generation/tool/notebook work.
Application limitations in earlier checkpoints remain accurate. Existing user edits
and classic comparison preserved. Documentation checks only; no runtime test claim.

Credential-save feedback and history navigation, 1 November 2026 — read-only metadata
inspection confirmed the user's current project had no credential records and its
model versions were unlinked; no secret value was read or supplied. Found hidden save
feedback: errors above the credential table could be out of view when pressing Save.
The credential editor now opens with focused heading; rejected-save feedback is beside
Save, focused/scrolled into view, with Key not saved and an explicit sign-in link when
reauthentication is required. Entered password-field values remain available after
failure but are never put in local/session storage. Successful saves focus a named
Saved securely confirmation. Metadata reload failure explicitly distinguishes a saved
key from a list refresh failure and retains the returned metadata row.

Credential save/rotation now retains one idempotency key for retrying unchanged fields.
Editing fields or starting another editor resets it; success clears it. HTTP response
status is carried on workspace API errors without request data. Network/5xx/timeout
errors show Save could not be confirmed rather than asserting storage failed. A browser
regression commits a fake key through the real API, drops the response, retries the same
request and verifies the same credential ID, visible confirmation, hidden value and
persistence after reload. Auth/session freshness, encryption, project scoping and key
version binding are unchanged; no actual-user key was saved or model binding changed.

User's additional navigation request implemented: removed Runs from the modern sidebar.
Comparison is inside the task Run history panel with selection guidance. Closing remains
available after deselecting below two runs; no incompatible score deltas are enabled.
Task-view Run history links and historical run/dashboard URLs remain valid. Classic
comparison routes and baseline remain preserved.

Browser verification: credential refresh/lost-save/model-version suites3 passed (46.0s);
combined credential refresh/lost-save/history comparison/model-version suites4 passed
(47.1s). Admin/RL Engineer navigation plus retained Admin/classic journey2 passed (12.6s).
Initial lost-save replay found the retained fake record beyond the first metadata page;
the regression now follows visible pagination after reload instead of assuming page one.
History metric comparison uses explicitly labeled browser-only software fixtures, not
persisted model performance. No paid model calls, real-key changes, schema migrations,
deployment or push. Final `pnpm check` passed lint/format150 files, frontend formatting,
TypeScript, production build and generated API contract. `git diff --check` passed.
Classic comparison remains3a17429c; unrelated AGENTS and cloud-runbook edits preserved.

Direct Run and linked-model selection, 1 November 2026 — removed Refresh tasks and
row-level Run history from the task library beside Import Task; task-view history is
retained. Removed Refresh preparation choices. Task Run now loads every page of current
project models and displays each configured model with its linked key name and state,
with search. User explicitly chose linked model/key pairs rather than per-run key
overrides. No credential value or storage reference is exposed. One shared settings
section applies tokens, repetitions and episode timeout to every selected model; the
API budget remains one aggregate cap across all models/trials.

Task Run is one explicit action: validate fields, freeze the selected versions and budget,
create the group, and launch only if ready. Admin consent text remains beside Run.
When models fall outside an older preset, an Admin creates an exact-selection preset
using that preset's runner/integrations through the existing authorized API. Engineers
remain constrained to their preset scope. No key/model version is silently substituted.
Unavailable selections after a focus refresh are explicitly rejected and can be cleared.
Missing choices use visible focused validation messages. Unready groups show a named
Run cannot start yet panel; Run remains clickable and checks fresh readiness before
either launching or focusing the specific blockers. Structured server reasons display
readable messages. A failed/ambiguous launch response retains the same group; there is
no automatic paid retry or replacement group. Already-launched groups are not relaunched.

Testing found a real Form interaction issue: removing an invalid-field summary on blur
could shift a checkbox between pointer-down and click. Invalid fields now revalidate
while typing, clearing the summary before the next click; checkbox changes use the
actual checked value. This shared-form change is covered by the model/key regression
journeys. Initial test assertions also needed scoping away from Next's route announcer,
distinct fixture names and pagination over retained model metadata; no access or budget
assertions were removed.

Verification: final `pnpm check` passed lint/format150 files, frontend formatting,
TypeScript, production build and generated API contract. Credential/model integration:
`pytest services/backend/tests/integration/test_workspace_credentials.py
services/backend/tests/integration/test_workspace_models.py -q --tb=short`:3 passed
(1.61s), including project-scoped linked-key names without secret values/references.
Final `pnpm test:e2e tests/e2e/workspace-task-pages.spec.ts
tests/e2e/workspace-preparation.spec.ts tests/e2e/workspace-model-versions.spec.ts
tests/e2e/credential-refresh.spec.ts --timeout=45000`:5 passed (47.1s). Browser tests
cover all metadata pages, a model outside the old preset, shared limits for two models /
four trials, missing model/budget/key explanations and exactly one launch request. Ready
launch responses are browser-only fixtures: no launch reaches the real backend/provider;
persisted synthetic groups remain drafts. Backend dispatch/reservation logic unchanged.
Prior263 unit/22 guarded integration results are historical, not rerun for this UI change.
Local API restarted; runtime activation preserved. No migration, paid call, user-account
change, deployment, push or actual-user configuration edit. Classic baseline and
unrelated AGENTS/Google Cloud runbook edits preserved.

Task mockup implementation, 1 November 2026 — separate Tasks library, View Task and
Run Task pages are built on the modern branch. Library includes server search/status
filtering, ten-row pagination, latest version, last run timestamp, run count and Run /
View / history actions. Version viewer includes prompt/visible stages, declared tools,
actor inputs, safe rubric descriptions/weights, verifier descriptions and immutable
environment/package bindings. Run page keeps exact-source configuration beside real
sanitized lifecycle/stage events, trial progress and result/trajectory links. Theme
persists across pages. Desktop/mobile screenshots were visually inspected; fixed a
white global-navigation background in dark mode. Current source is always selectable
even beyond the latest100 version list. Task-context configuration refresh stays on
Run Task and preserves the original source. Classic comparison remains unchanged.

User explicitly requested repetitions now: 1–10 per model, up to80 sequential children.
Migration035 expands ordinals and adds immutable, scoped task-environment intake.
Each trial has a separate bound plan/check and per-model trial number; conservative
cost sums every trial, with one atomic aggregate reservation. Existing Admin Run,
recent-session, rights, secret revocation, private-reference and no-retry boundaries
remain. No actual-user group was launched or key/model binding silently changed.

Dockerfile folder intake is implemented for root Dockerfile plus relative companion
text files (100 files/1MiB total/256KiB per file). Context and Dockerfile hashes bind
the immutable source version. Uploaded bytes stay quarantined and runtime reads are
denied. **Custom Dockerfile build/execution remains incomplete** pending scanner and
isolated-build qualification; imported environments are labeled accordingly and cannot
be selected for dispatch. Package-bound Harbor Docker remains runnable. User's
harbor-lab marketing environment was inspected read-only; its apt instructions were
not executed, no sibling files changed, and no host/provider credentials inherited.
See docs/product/23-TASK-LIBRARY-VIEW-AND-RUN-SCREENS.md for the boundary and adapter gap.

Verified: `pnpm test:unit` 263 passed (4.31s); final `pnpm check` passed backend lint /
format150 files, frontend formatting, TypeScript, production build and generated API.
Guarded integration: `ANVIL_TEST_HARBOR=1` with the configured local Docker socket and
pytest test_workspace_task_pages.py, test_workspace_preparation.py,
test_workspace_execution.py, test_workspace_managed_costs.py: 22 passed (56.30s),
including native SDK mocks through Harbor, repetition cost multiplication, one-cap
reservation, per-trial projections, project denial and quarantined-artifact read denial.
Initial integration without the Docker opt-in:18 passed/1 explicitly skipped, superseded
by the fully enabled final run. Fresh isolated databases migrate through035; existing
local database was migrated additively without resets or volume deletion.

Browser: `pnpm test:e2e tests/e2e/workspace-task-pages.spec.ts
tests/e2e/workspace-preparation.spec.ts --timeout=45000`:3 passed (14.7s). Initial new
test timed out because Form appends Required to accessible labels; corrected the test
to match required-field names. Product fields were present. Screenshot evidence in
ignored artifacts/test-runs/task-{library,view,run-configuration,run-mobile}.png uses
explicit synthetic browser fixtures. No fake performance populated actual user data.
Read-only parallel review found four UI issues (trial label, terminal polling,
upload-selection remount and old version selector), all repaired. No paid calls,
custom-image builds, deployment, push or account changes. Full-platform regression,
backup/restore and live model qualification were not run for this increment.

Nightly checkpoint, 1 November 2026 00:09 America/Chicago (05:09 UTC):
`pnpm check` passed backend lint/format (146 files), frontend formatting, TypeScript,
production build (classic and modern routes) and generated API contract. Existing
Authlib deprecation warning only. No source changes, provider calls, user-configuration
changes or new blockers. The prior missing-key diagnosis remains unchanged. Unit
evidence from the preceding checkpoint: 250 passed; integration/browser tests were
not repeated on unchanged source. Unrelated edits remain preserved. Stop by 06:00
local and do not extend the authorized eight-hour work window for the DST extra hour.

Nightly checkpoint, 31 October 2026 23:11 America/Chicago (1 November 04:11 UTC):
`pnpm test:unit` passed 250 tests (9.71s); existing Authlib deprecation warning only.
`git diff --check` passed; classic comparison remains at 3a17429c. User edits in
AGENTS.md and the Google Cloud runbook remain untouched. No source expansion or paid
calls. Current user-facing Run diagnosis: group becf1a47 in project 2eb81cb7 binds a
model version without a saved credential. This differs from the previously checked
preparation in project ea1cc06d. Update configuration preserves model/key versions;
it cannot adopt a newly saved model version. User has been told to bind the saved key
and create a group selecting that version. No user configuration was silently changed.
Earlier integration/browser/build evidence below remains valid but was not rerun at
this checkpoint. Nightly deadline: 06:00 America/Chicago, including the DST transition.

Simplified model setup, 31 October 2026 — manual pricing and processing-terms fields
are removed from the modern model editor. Existing model/key/preset bindings remain
usable. Anvil freezes server-managed cost estimates into new execution groups;
Admin Run still confirms processing rights and reserves the explicit aggregate budget.
Draft **Update configuration** creates a new group with the same immutable preparation
and cap, preserving the old group and making no authorization, reservation or model call.
Managed catalog covers exact OpenAI gpt-6-luna, gpt-6-astra, gpt-6.1-sol and
gpt-6.1-terra IDs, verified against official pricing on 1 November UTC and expiring
8 November 02:47:35 UTC. Unknown/expired support blocks dispatch; existing declared
rates remain compatible. This is not an automatically refreshed all-provider catalog.
Cache-aware accounting and a conservative reservation include 30-minute cache writes;
requests bind that TTL. Missing usage components fail closed. Historical metadata is
preserved without requiring the user to fill it in again.
Verification: `pnpm test:unit` 250 passed; guarded execution/managed-cost integration
18 passed with mocked providers and local Harbor; `pnpm check` passed. Initial affected
browser run: 3 passed, 1 test transport failure reading a response after full navigation;
the assertion now reads the persisted group after navigation. Follow-up
`pnpm test:e2e tests/e2e/workspace-preparation.spec.ts`: 2 passed (9.7s).
Read-only preflight of the existing user preparation passed model setup; conservative
estimate 5,248 microUSD is within its unchanged 90,000 microUSD cap. No real provider
request, paid smoke, deployment or actual-user authorization was performed.

Saved-key status clarification, 31 October 2026 — read-only inspection confirmed the user's
existing credential is persisted, decryptable by Anvil and bound to its model. No key
value was displayed, logged or sent to a provider. The disabled blank API-key input was
misleading: replaced it with a named **Saved securely** status and explicit saved-versus-
selected model-binding guidance. Model list now says **Saved key linked**; credential list
distinguishes saved/revoked/missing values. Saved values remain write-only and hidden.
Failed credential saves retain the newly entered password-field value until success;
expired-login failures show a Sign in again link and explain the old saved key is unchanged.
No authentication, key storage, provider or budget policy changed. Browser regression
now covers failed-save retry, key/model save, persistence after reload, clear saved status,
hidden values, refresh/rotation and revocation using fake test keys. Initial affected
browser run: 4 passed/two stale assertion failures (alert scope and updated confirmation);
fixed those assertions, final affected replay2 passed (12.0s). Final `pnpm check` passed.
No backend migration, paid call, actual provider validation, real-key replacement or account
change was performed. Existing user key did not need re-entry.

Credential picker refresh fix, 31 October 2026 — the model editor now has **Refresh
credential versions**, loading/error/retry feedback, and refresh on window focus.
Credential saves/rotation/revocation refresh the picker independently of the credential
table's current page; all paginated metadata is loaded and filtered to the selected
provider. Latest-request guards prevent stale responses overwriting newer choices or
updates after project unmount. Model draft fields and explicit key selection stay intact;
rotation/revocation warns and blocks stale binding rather than silently swapping keys.
No backend permission, credential storage or dispatch behavior changed. Verified
`pnpm check` (lint/format, TypeScript, production build, OpenAPI) and browser credential
refresh/model-version suites: 2 passed (9.5s). The new regression uses real authorized
create/rotate/revoke endpoints with fake keys and deterministic paginated metadata;
it covers save, pagination, provider filtering, rotation, focus, failed refresh/retry,
draft retention and revocation. No model calls, paid requests or real-key reads occurred.

Account eligibility update, 31 October 2026 — user explicitly rejected the extra
demo-versus-real-account requirement and authorized using the existing Admin account.
Active project Admin membership now determines eligibility regardless of seeded origin.
No new account/invitation, identity promotion or `is_synthetic` update is required or made.
Modern group authorization and legacy Admin checks/counts apply this policy consistently.
Audit records retain actor origin and `active-project-admin-v2`; output/fixture provenance
is unchanged. Active user/membership, project boundaries, recent sign-in, exact model/key/
version/rights/pricing/terms, explicit cap, reservation, revocation and no-retry checks remain.
This supersedes earlier real-account-only statements in historical checkpoints/specs.

Verification: 242 unit tests passed. Existing-admin execution plus marketing integration:
13 passed (48.83s), including actual staged Docker Harbor with all three provider SDKs
mocked; the group creator/authorizer is existing admin-1 and its origin flag stays true.
API security plus three Admin revocation cases: 50 passed/two fixture failures (42.38s).
Those two fixtures used an unassigned source actor after the private-binding guard;
changed only their fixture actor to the source owner. Follow-up of those cases plus
workspace/private-access tests: 6 passed (0.84s). The three disabled-user/membership/role
cases confirm authorization is invalidated before dispatch. Static check/build passed.
Full platform integration was not repeated; no real provider request was made.
Final existing-Admin browser/preparation follow-up: 2 passed (9.3s). Actual workspace
eligibility read check passed for admin-1 with its original origin flag unchanged;
API/database healthy, Harbor live dispatch enabled (`gated`). No model was launched.

Runtime update, 31 October 2026 — user explicitly requested enabling server live execution.
Local `.env` now sets `ANVIL_LIVE_PROVIDERS_ENABLED=true`; Anvil restarted successfully.
Health confirms API/database ready and Harbor live dispatch `gated` (enabled with per-run
checks retained). The legacy `live_inference` health field remains hardcoded disabled;
it does not describe Harbor's switch. No queued/leased jobs existed before activation;
no model run, paid request, account promotion, cloud change or email was initiated.
Exact Admin authorization, current model/key/pricing/terms, rights and
budget checks remain. Earlier disabled-runtime statements below describe prior checks.

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
