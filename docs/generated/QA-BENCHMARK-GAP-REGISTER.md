# QA benchmark exercise — living gap register

## Capture and catalogue acceptance — 19 November, after deployed08d45ff

CAPTURE-27 (CODE BUILT, actual qualification pending): capture configuration had
no target/driver runtime-qualification receipt contract; frontend and backend
therefore always reported not ready. QA PostgreSQL actually had SSL off and its
default connection profile permitted fallback. New code separates an API-only,
operator-owned read-only receipt from project/peer/registrar qualification. It
binds source, lock, actual capture image, driver/libpq, exact target and public
trust-file bytes; requires independent review, six actual controls and <=24h
expiry. The explicit operator probe requires read-only actual identity, actual
driver cancellation acknowledgement, exact backendPID+start disappearance and
observer closure. No inventory GET probe or automatic qualification producer.
TLS provisioning must use explicit trust and verify-full, never disable checks.
Studio must generate this target/probe/review/mount lifecycle and invalidate on
address, source, driver, trust rotation, expiry or revocation. Preserve unknown
cleanup and forbid replay. A generic software role receipt cannot substitute.

CATALOGUE-28 (CODE BUILT, deployment pending): four recorded Project observations
still described151d6fb after08d45ff was serving and independently qualified.
Three Project roles lacked observations. The UI conflated these with platform
installation/technical failure. New projection displays current platform technical
controls separately and labels the existing table Project readiness/recorded
Project check. This does not fabricate target/binding IDs or grant readiness.
Studio should retain per-image installed provenance plus distinct per-project
operation evidence and refresh measured observations after accepted deployment.

OPS-29 (DEPLOYED CONFIG FIX): continuous software scheduler/grader max-cycles300
could exhaust its600s poll window despite no jobs. One-cycle polling renewal
keeps the original600s window and native300s cutoff; no catch-and-ignore of real
failures. Software grader also rejected its custom-Python enabled flag; it is now
false while the separate private-scoring coordinator remains isolated. Future
rendered configuration must be checked by each actual service validator, not
only by Compose syntax or a copied feature flag.

## Physical integration findings — 19 November 2026

RUNTIME-21 (BUILT, actual verification pending): an untraced real4eb0c6c Trial
failed its separate verifier's hardcoded30second timeout.0102243 derives the
verifier allowance from the bounded task budget (maximum300), reduces the
gateway cap to that allowance, and keeps the original aggregate monotonic
cutoff. Ten layout/boundary regressions and an elapsed-time sharing control pass.
Studio must lint nested SDK/agent/verifier/socket/outer/cleanup budgets together;
changing an outer limit alone does not update an SDK's nested default.

OPS-22 (RETRY IN PROGRESS): corrected Evaluation buildf397ef22 expired in GCP's
300second queue without executed-step evidence; Core and Environments succeeded.
The one-call automatic retry budget was initially misread as a fresh-human-
approval gate. The user's original retry authorization was independently recovered
from the actual chat userMessage; no later owner restriction revoked it. After
normal approval review and duplicate/outcome reconciliation, one unchanged
Evaluation resubmission315db6a2 was accepted as ledger ordinal2. No loop, deadline
increase or counter reset. The redundant email request was corrected. Future
tooling must distinguish automatic invocation limits from existing owner-approved
terminal retries; separate queue expiry/source failure/execution timeout/lost ACK;
preserve counters, artifact reuse and original authority receipts without inventing
extra approval requirements or silently rebuilding all phases.

| ID | Status / owner | Observed gap | Prevention | Exit evidence |
|---|---|---|---|---|
| RUNTIME-17 | BUILT / Gym | Mediated Harbor imports a sealed backend module but the origin guard checks it against the Harbor-only source manifest. | Map every first-party namespace to its own exact sealed wheel inventory; retain full dependency/stdlib/RECORD validation and reject missing/frozen/foreign origins. Exercise real shared-interpreter imports before release. | Candidate4eb0c6c source02e005b4…,16focused source controls passed,1283units+93SQL+5privateSQL passed; fresh physical Trial pending. |
| QA-18 | CONTROL_FIXED / Gym | A 15-second cold-import intent wait obscured the original transport state; failure cleanup lost partial streams. | Separate startup from the original bounded candidate deadline, retain original-handle stdout/stderr and mark unknown without replay. Independently trace every original process from pre-entry through terminal markers; count IPv6 capability probes separately from outbound connections and reject every internet connect. | OPS21308cf,7classifier controls passed; actual current-image observation pending. No global zero-call claim. |
| FIXTURE-19 | CONTROL_FIXED / Gym | Registry tests manufactured four product references over a five-state import, proving reader selection but not real import assembly. | Use application_types=True, verify original four tasks,200immutable assignments,50shared evaluator configurations/four environment bindings, and20actual product/state application snapshots. | Keystone read-only review; fresh4eb0c6c/21308cf physical registry result pending. Publication/legal/domain/runtime prerequisites remain explicitly synthetic; full native materialization/report flow is separate. |
| OPS-20 | PREPARED / Gym | Restoring old Compose leaves newly introduced coordinators running as orphans; migration max-version alone is insufficient custody. | Require exact schema+Alembic132, explicitly target133 once, prove both133 afterward; preserve private backup/diagnostics, stop only new owned container IDs and independently restore all old services on failure. | Harbor reviewed rollout936a93…; final manifest retarget and actual rollout pending. |

Template/Environment Studio must generate a deployment-contract preflight that
covers shared interpreter imports, actual UID/GID, exact mounts/capabilities,
namespace peers, restricted SQL rights, original deadlines and retained cleanup.
Successful package installation or a manufactured registry fixture is not runtime,
publication, policy, rights or benchmark qualification. No live calls authorized.

## Source-verification performance and storage — 19 November 2026

PERF-01: The installed SQL software control repeated about358 complete source,
RECORD and loader scans, exceeding both180s and300s. Checkpoint151d6fb changes
nonspending registration and explicit software validation to an owned SQL
savepoint with one immutable operation-local byte proof. Full entry and exit
checks precede release; current DB configuration/receipt/revocation queries and
actual known cases remain fresh. No ambient/global cache or paid-path reuse.
Installed build measured2full scans for50configuration byte checks in17.217s;
1,247units+10subtests/90SQL+2actual rollback-revocation tests passed. QA151d6fb
deployed: fresh SQLv5 all4groups passed in62.920s; nativeTrial observed_not_qualified
with completecleanup at189.851s, no fullqualification granted. Studio/runtime qualification must budget
and measure preparation work separately from candidate time and avoid unbounded
repeated physical scans without weakening authority or source checks.

OPS-02: User approved persistent QA boot disk120GB; actual root filesystem was
expanded online and verified118Gtotal/50Gfree. Existing120GBdata disk unchanged.
Baseline is recorded separately from production in deployment.json. Future
provisioning must use it; image/backup retention still needs a reviewed bounded
policy rather than repeated disk growth or unapproved evidence deletion.

As of 18 November 2026. Purpose: learn from the complete Authoring → Forge → real
QA benchmark exercise, then use evidence to write the Template and Environment
Studio specification. **This is not that Studio specification.** The user explicitly
deferred Studio design until more lessons are known. No claim of a gap-free system.

## Corrected ownership and privacy boundary — user decision, 18 November

Latest engineering checkpoint: `4be884c`, final combined source
`f616bfde87ffd8a7d4385076a045a5106d710e445ff8f4c66527f17031b8751a`:
1173 unit tests and10subtests passed,2platform/root skips;64 actual isolated SQL
tests passed including fresh/repeated130. UI types/build/browser passed. Cloud
build and actual installed Trial verification are separate pending evidence.

Authoring binds applicable policies and business rules to tasks. Gym binds those
rules to evaluators and owns private datasets, cohorts, hidden expectations, data
rights/case reviews and environment qualification. SMEs never write interfaces;
Authoring uses Gym's published abstract tool/input/output catalog. Live integration
must not expose private case IDs, population hashes, counts or expected answers.

| ID | Status / owner | Observed gap | Prevention | Exit evidence |
|---|---|---|---|---|
| SEC-01 | LOCAL_VERIFIED / Gym API | Generic contract discovery included dataset inventory for Authoring export clients. No live exposure is established. | Skip private inventory lookup entirely for project export-client and workload-identity callers. | Three route tests pass for both external modes and authorized internal discovery; candidate not deployed. Other response paths still require privacy review. |
| FLOW-11 | LOCAL_VERIFIED / Gym input binding | Stored Admin ZIP resolution uses user_session, but input binding required workload_identity. | Validate each genuine server-stored mode without relabelling identity; verify exact project/package/receipt/source/sponsor and current Admin membership for offline uploads. | Positive unchanged-identity and negative tamper/project/sponsor/revocation tests pass. Full offline package preparation awaits successor and runtime qualification. |
| BIND-14 | OPEN / Gym policy contract | PolicySet.state_refs requires at least one source; a reviewed not-applicable decision cannot currently replace a state source. | Negotiate explicit applicability decision schema and genuine review resolution; never invent a source to satisfy min_length. | Applicable and reviewed-not-applicable paths tested, including exact scope, expiry and revocation; no gate bypass or empty-source fallback. |

KYC product CandidateExport v1 has no private dataset reference requirement;
Gym's resolve_candidate receives that dataset separately. The legacy state-oriented
ReusableExport v2 does require case_dataset and must not define the new product
handoff. Abstract input-requirements schema negotiation remains a separate gap.

The user's one-time task migration exception permits preserving unchanged SME
content and original approval provenance in successor revisions. It does not
approve missing policy decisions or changed business outcomes. Authoring prepares
the successor offline; Gym will validate its actual schema, provenance and content
before declaring it compatible. No assumption that an unseen v8 package will pass.

Continue this register through the first genuinely authorized QA model benchmark,
its grading/reporting and recovery checks. A successful run does not automatically
close every gap. Do not close an item on a plan, passing mock, source commit,
package installation, transfer completion or UI badge alone.

## Current answer: can benchmarking start?

No. V7 is registered but not qualified for benchmarking. Owned native Trial
integration, actual installed controls, authenticated policy review/provisioning,
publication provenance and required domain/input approvals remain unresolved.
Live model and Authoring calls are disabled. Model selection stays with the user.
Latest QA known serving components: frontend e0ec104, backend/runtime818afca.
Local engineering checkpoint545a7cd is not deployed or native-qualified.

## Status and closure rules

- **OPEN:** implementation/process missing or not verified.
- **BLOCKED_INPUT:** exact source, review or decision is missing; record the owner.
- **LOCAL_VERIFIED:** correction has local evidence, not serving QA acceptance.
- **QA_SUBCHECK_VERIFIED:** a specific QA subcheck passed, not the entire journey.
- **MITIGATED:** workaround/recovery exists; permanent experience gap remains.
- **NOT_RUN:** required test has not run. Never count it as passed.
- **RESOLVED_INPUT:** an input ambiguity/integrity question has been verified;
  this does not approve its contents or qualify execution.

Each item keeps its ID, first observation, latest status, owner, evidence and
future prevention rule. Append superseding evidence; preserve failed attempts.
Separate implementation, deployment, verification and approval dates. Never treat
an informational JSON record as an authenticated approval.

## Evidence index

| Ref | Evidence |
|---|---|
| E01 | [KYC actual registration/readiness](kyc-v7-readiness-2026-11-18.md) |
| E02 | [KYC worker/cohort corrections](kyc-runtime-corrections-2026-11-18.md), source843bd45 |
| E03 | [Probe permission layer](kyc-probe-permission-2026-11-18.md), source545a7cd |
| E04 | [Authoring–Forge handoff requirements](../product/27-AUTHORING-FORGE-EXECUTION-HANDOFF.md) |
| E05 | [Open Weight QA rollout](open-weight-qa-rollout-2026-11-17.md) |
| E06 | [Shared-token relink correction](open-weight-relink-fix-2026-11-17.md) |
| E07 | [Reported UI defects](ui-defects-2026-11-18.md); QA frontend e0ec104 |
| E08 | [Marketing isolation findings](marketing-native-isolation-2026-11-17.md); additional unserved candidate evidence lives in marketing-native-next-20261117 |
| E09 | User policy-evidence bundle: all23 updated payload hashes verified, manifest0e39c75004630077df6ef2b74f4424981869d69f5b3d2412925dcd4ebeeb695a |
| E10 | Actual QA smoke: workspace/health200, anonymous mounted template route401; initial wrong-prefix422 retained in E01 |

Source files named below are under services/backend/src/anvil unless a different
path is given. Historical reports describe their dated revisions, not automatic
qualification of newer source. Tests with manufactured evidence remain labelled.

## Runtime and technical qualification

19 November measured follow-up: the old30s callback spent8.90s importing and
20.70s validating before SQL. The user approved wall300/lifecycle420 (cleanup6);
b508a0a deployed through three successful independent phase builds. The next
native attempt reached worker intent and exposed a missing project row-lock
capability. Additive132 supplies only a scoped scheduler lock function; no project
UPDATE grant. Actual SQL covers denied scopes, restricted identities, revocation
blocking and stale-isolation refusal. A separate installed SDK test found that
Beartype's path hook changes the loader class even for untransformed modules.
The narrow pinned-loader compatibility patch preserves actual/raw code equality;
post-SDK source validation is now an installed-image regression. Both corrections
passed independent review,1238units/10subtests(4skips),90fresh/repeatedSQL on
f9e5d504...d1e551; actual image/QA qualification remains pending.

Studio lesson: version inventory and source validation before framework imports
are insufficient. Qualification must exercise the installed SDK import lifecycle,
actual restricted database logins and lock/revocation behavior, and distinguish
build success, deployment health, observed software and qualified execution.

19 November continuation: QA 5b19a72 passed actual installed Harbor log-profile
parity but native attempt063a350f reached its original120-second limit during
repeated runtime admission checks. No worker intent/SQL effect was observed;
cleanup complete and unknown outcome retained. Candidate5b0ccfe deduplicates
common hashes only within one call and only after kernel-readonly inspection of
all closure files/directories, including nested mounts and resolved interpreter.
Original limits and every component source/mirror check remain. Independent review
clear;1203 units/10subtests passed,4skipped;77 fresh/repeated SQL checks passed.
Cloud build/actual native rerun remain pending. Private timeout prefixes now retained
with safe stack metadata; public evidence never contains raw private logs.

Custom Python physical core5controls passed on5b19a72. The combined7control
harness exhausted its own budget before resource controls; those two are NOT
passed. Fixed core/resources suites use separate original85-second budgets,
fresh intents and no execution retry; resource-only physical run in progress.

| ID | Status / owner | Observed gap and evidence | Prevention requirement | Closure evidence |
|---|---|---|---|---|
| RUN-01 | QA_SUBCHECK_VERIFIED / Forge operations | Scheduler/grader had sleep placeholders rather than real polling. Actual role polling was deployed; E05. | Inventory must test each real service operation, not process existence. | Exact serving image/source, live queue-poll observation and role separation. Full business execution remains separate. |
| RUN-02 | LOCAL_VERIFIED / Forge runtime | Fixed child did not enter scheduler NOLOGIN capability from its dedicated LOGIN. E02. | Share transaction-local role-entry checks; reject elevated/mixed logins. | Real isolated SQL proves effective role, private-answer denial and role reset after transaction. QA deployment still needed. |
| RUN-03 | LOCAL_VERIFIED / Forge runtime | Scrubbed child lacked verified OPA path/hash. E02. | Pass only sealed tool identity; fail closed on absence/tampering. | Pinned executable controls and actual allowed/denied actions on installed runtime. |
| RUN-04 | LOCAL_VERIFIED / Forge runtime | Denied actions could be counted as completion; first correction rolled back denial evidence. E02. | Commit actual denial before stopping; prevent next action and completed receipt. | Real SQL: one denial persists, no second action/recommendation; ambiguous operation cannot replay. |
| RUN-05 | LOCAL_VERIFIED / Forge runtime | Exited leader with closed-stream descendant could escape cleanup. E02. | Keep leader unreaped through group cleanup; bounded original cleanup allowance; no post-reap group signal. | Actual isolated Linux control passed; future native normal/crash tests must prove owned cleanup. |
| RUN-06 | OPEN / Forge runtime | Qualification was required before the first qualifying native trial, creating circular admission. E03. | Separate permission for a bounded no-model technical probe from measured qualification success. | Permit/ledger local controls pass; actual execution bridge still must consume it safely. |
| RUN-07 | OPEN / Forge runtime | Owned native Trial bridge and framework-process receipt producer are not integrated. E03; environment_harbor.py; Harbor environment.py. | Only trusted fixed owner launches exact interpreter/image/roles; no arbitrary callbacks or caller UUIDs. | Genuine Trial UUID/process receipts, paired role preflight/start snapshots and one-shot intent before effects. |
| RUN-08 | NOT_RUN / Forge QA | Full current-source/image component qualification not earned. SQL/unit counts are insufficient. E01–E03. | Explicit test matrix for actual Harbor, MCP, reset, checkpoint, actor/grader, role/mount, OPA/ZEN, private scoring and zero-provider controls. | Actual positive/negative/crash results with exact source/image/locks, reviewed evidence and expiry. |
| RUN-09 | OPEN / Forge QA/operations | Installed versions and observed polling could be mistaken for Ready. E01/E05. | Distinguish installed, observed, tested, reviewed, qualified and run-authorized states. | Every readiness claim links to current evidence; stale source/image invalidates it. |
| RUN-10 | OPEN / Forge runtime | An unknown result must not assert zero actual calls merely because zero were authorized. E03. | Separate authorized limits from measured usage; unresolved evidence stays unknown. | Ledger tests preserve null actual calls/unverified evidence; future collector verifies actual no-call evidence. |
| RUN-11 | LOCAL_VERIFIED / Forge runtime | Installed QA preparation failed actor-file hash comparison after canonical plan storage reordered JSON keys. No Trial launched. | Use one canonical actor-byte representation across preparation, persisted plan and validation. | Canonical-roundtrip regression passed; actual installed retry remains required. |
| RUN-12 | LOCAL_VERIFIED / Forge runtime | SQL checked physical framework liveness before work but lacked a check before commit. | Revalidate original plan and framework lease inside transaction after work; fail and roll back on detected loss. | Framework-death and permission-change rollback regressions passed; actual crash controls remain required. |
| RUN-13 | OPEN / Forge runtime | Gateway startup precedes configuration write and lifecycle cleanup protection. An intervening exception can retain its thread/socket until CLI exit. | Enclose startup and intervening operations in bounded cleanup ownership. | Injected configuration/write failure leaves no gateway thread/socket. |
| RUN-14 | QA_SUBCHECK_VERIFIED / Forge adapter | A -m launch defined a second adapter class under __main__, rejecting the factory's canonical class. | Delegate the entry point to the canonical installed module; test it in the installed Harbor image. | Installed entry regression passed and bf839a4 actual framework advanced beyond type validation; full Trial remains separate. |
| RUN-15 | LOCAL_VERIFIED / Forge adapter | Actual Harbor0.25 defaults automatic mounting off, while the preparer expected SDK log mounts. Actual startup failed exact profile hash. | Pin explicit role log mounts without enabling SDK-wide chmod; test actual factory/mount writer and exact effective Compose before effects. | Config-only actual comparison isolated missing logs;1186 units/71 SQL pass on correction; installed-image and physical Trial pending. |
| RUN-16 | OPEN / Forge operations | UI Refresh reloads observations; a new image deployment does not refresh measured installed metadata. | Observe actual serving image/source/lock/interpreter/versions during release and append unqualified observations automatically. | bf839a4 four actual serving observations appended from measured receipts; repeatable tracked release integration still missing. |
| RUN-17 | LOCAL_VERIFIED / Forge diagnostics | Rejected Compose stdout was discarded before its full-profile hash check, making diagnosis require a separate reproduction. | Retain bounded private rejected projections under distinct filenames that cannot satisfy admission. | Private/exclusive/bounded rejected snapshots tested; valid preflight filenames stay absent on rejection. |

## Templates, policies, inputs and bindings

| ID | Status / owner | Observed gap and evidence | Prevention requirement | Closure evidence |
|---|---|---|---|---|
| BIND-01 | QA_SUBCHECK_VERIFIED / Forge import | KYC v7 was not registered, blocking ZIP validation. E01. | Exact template registration and publication preflight before task export. | Actual Admin registration and persisted canonical SHA verified. Qualification is not implied. |
| BIND-02 | OPEN / both integration owners | Informational publication JSON cannot verify actual publication; integration is disabled. E01/E04. | Authenticated publication response or explicitly supported verifiable offline proof; status synchronization. | Exact published spec/part hashes and trusted provenance accepted without manual DB writes. |
| BIND-03 | BLOCKED_INPUT / Authoring + domain owner | V7 federal hash identifies reference-only descriptor, not policy text. E09. | Descriptor and normative artifact have separate identities and explicit relation. | Captured text received and hash-verified; applicable review and successor binding remain required. |
| BIND-04 | BLOCKED_INPUT / domain owner | CA/NY/TX/FL/IL policy artifacts and applicability reviews are pending. E09. | Require original versioned sources and product/state/charter/effective-interval decisions. | Actual scoped decisions/provenance; never substitute synthetic practice documents. |
| BIND-05 | BLOCKED_INPUT / domain owner + Project Owner | Every supplied case has charter applicability reviewed=false. E09. | Applicability must be explicit, not inferred from residence or workflow approval. | Exact case/policy/charter subject reviewed and bound; unresolved rows remain blocked. |
| BIND-06 | OPEN / Forge policy service | Receipt UUID/hash syntax does not resolve authenticated exact-scope review evidence. E02. | Dedicated immutable review resolution with current reviewer authority, subject hashes, expiry/revocation. | Forged, cross-project, wrong-scope, expired and revoked references rejected in actual SQL/API tests. |
| BIND-07 | OPEN / Forge policy service | Restricted policy qualification/materialization producer is missing. E02. | Derive scope from original task/input/binding; append under separate qualifier capability after real reviews. | Exact public policy bytes delivered; no API/scheduler/grader write capability; overlap/size/revocation/conservation controls. |
| BIND-08 | BLOCKED_INPUT / Gym data owner + Project Owner | Case-expectation review and separate rights decision absent; synthetic provenance alone is not that approval. E09. | Gym records exact private dataset/artifact scope; Authoring has no access to benchmark cases or expectations. | Actual Gym review/rights records and version-bound acceptance; no fixture response treated as performance. |
| BIND-09 | RESOLVED_INPUT / Gym input contract | Population hash target was unspecified. Updated definition is sorted case-ID array; c77748bc...e08aa verifies. E04/E09. | Declare private hash targets, ordering and canonicalization inside Gym, not the Authoring exchange. | Updated manifest verifies; dataset/per-case hashes preserve content identity alongside ID-set identity. |
| BIND-10 | LOCAL_VERIFIED / Forge preparation | Four-task assumptions blocked one approved individual workflow. E02. | Support exact approved cohorts with actual counts and immutable ancestry. | 1–4 product controls pass; homogeneous input works structurally; foreign unassigned rows remain blocked. Full QA path not verified. |
| BIND-11 | OPEN / Gym preparation | Authored workflow must be resolved against Gym-owned data and evaluators; expecting benchmark input files from Authoring was an ownership error. | Authoring declares abstract input/output and policy/rule/task requirements. Gym selects private data and evaluator/environment bindings. | Offline task package prepares without sending protected cases, fingerprints or expectations to Authoring. |
| BIND-12 | OPEN / both products | New artifacts cannot be retrofitted behind immutable v7 hashes. User explicitly holds v7. E04/E09. | Explicit successor/version negotiation and fresh affected reviews/qualification. | Reviewed successor such as v8 binds actual source identities; v7/task history unchanged. No successor created yet. |
| BIND-13 | OPEN / both products | Internal synthetic rule-set review was confused with domain/legal/runtime approval. E09. | Record distinct approval subjects and actual owner decisions; optional reviewers do not become invented gates. | UI/API explains each decision and its scope; unrelated approvals cannot satisfy it. |

## Handoff, authentication and user experience

| ID | Status / owner | Observed gap and evidence | Prevention requirement | Closure evidence |
|---|---|---|---|---|
| FLOW-01 | OPEN / both integration owners | Manual files/paths are carrying publication/dependency status while live export is off. E04. | Negotiated contract discovery, pre-export dependency preflight and durable export/import receipts. | Complete authenticated QA roundtrip without manual copying; same validator for ZIP/live paths. |
| FLOW-02 | OPEN / both products | Bundle README said unregistered after Forge had registered v7. E04/E09. | Time-stamped shared status and correlated receipts, not copied stale status strings. | Both products show same exact-version registration/qualification and revocation state. |
| FLOW-03 | OPEN / Forge API | Generic contracts do not yet provide the complete dependency/review/readiness discovery contract. E04. | Extend through negotiated versioned schemas; expose only abstract compatibility and Authoring-owned fixes, not private data inventory. | Authoring can identify its required fixes before export without discovering cases, cohorts, counts, fingerprints or hidden expectations. |
| FLOW-04 | QA_SUBCHECK_VERIFIED / Forge UI/API | New registration UI initially used wrong mounted route; mocks mirrored the mistake. Corrected in e0ec104. E01/E10. | Generate/check clients against mounted OpenAPI; test actual deployed route/auth boundary. | Correct route401 unauthenticated and actual signed-in Admin register/qualify flow verified. |
| FLOW-05 | OPEN / Forge UI | Upload100% was displayed alongside server failure/unknown validation. E07. | Separate transferred, validating, accepted, blocked and outcome-unknown states. | No stale success wording after failure; retry/reconciliation instructions preserve idempotency. |
| FLOW-06 | OPEN / both APIs | Incomplete package validation can return no package hash and unclear fix ownership. E01. | Structured blocker with stage, owner, artifact/template reference and exact action. | Missing template/source/review/runtime failures are understandable and machine-actionable. |
| FLOW-07 | MITIGATED / Forge auth | Old sign-in tab caused Invalid login state; fresh workspace sign-in recovered. | Friendly safe restart preserving login-state validation; no cookie/state checks weakened. | Stale, parallel and expired login journeys recover without raw JSON dead-end. |
| FLOW-08 | QA_SUBCHECK_VERIFIED / Forge UI | Open Weight list/editor were inconsistent and single-model setup obscured shared credentials. E07. | Reusable selectable table and shared credential selection; exact model versions remain separate. | QA source contains new table/bulk flow; local browser payload/replay checks passed. Real Admin acceptance still distinct. |
| FLOW-09 | QA_SUBCHECK_VERIFIED / Forge UI | Search/actions, headings/tabs/navigation and typography lacked consistency. E07. | Common alignment/type/spacing/navigation rules and responsive checks. | QA frontend includes changes; desktop/mobile local checks; broader user acceptance remains open. |
| FLOW-10 | OPEN / Forge UI/content | Legacy Anvil labels appear in branding/data contexts. User requests ADI-Forge UI names. | Separate display branding from immutable realm/service/data identities; avoid backend rename as cosmetic fix. | Inventory all visible labels; login brand verified; remaining contexts reviewed without changing stored data blindly. |

## Models and Marketing

| ID | Status / owner | Observed gap and evidence | Prevention requirement | Closure evidence |
|---|---|---|---|---|
| MODEL-01 | QA_SUBCHECK_VERIFIED / Forge models | Linking/rotating shared HF token could duplicate profiles instead of versioning them. E06. | Stable profile identity, exact credential-version binding, atomic idempotent bulk action. | Real SQL link/rotate/revoke/RLS controls passed and fix deployed. |
| MODEL-02 | OPEN / operator + user | Hub catalogue/token access is not inference availability or terms acceptance. E05. | Expose repository/gated terms, exact revision, authorized access and actual inference adapter/runtime as separate prerequisites. | User accepts required terms; actual adapter qualified; no implicit live fallback. No model calls authorized now. |
| MODEL-03 | NOT_RUN / Forge execution + user | Exact evaluation model, credential, rate/terms, ceiling and first real run are not bound/authorized. | Freeze exact choices and reserve bounded spend only after preparation readiness. | User selection/approval, actual call evidence and cost reconciliation; no unknown dispatch retries. |
| MKT-01 | OPEN / Forge Marketing runtime | Native Marketing bridge/owner/capture/admission is unfinished. E08. | Qualify complete native lifecycle rather than configuration-only components. | Actual normal/crash/timeout/reset/separate grading evidence on exact image/source. |
| MKT-02 | OPEN / Forge isolation | Shared UID/helper proc-root access could expose authority. Diagnostic private-mount/MAC predicate passed, not native qualification. E08. | Per-attempt confinement, closed FD/filesystem projections, original process custody and scoped policy. | Actual actor cannot reach helper admin socket/proc/fds/signals; intended channels work; full business trial isolated. |
| MKT-03 | LOCAL_VERIFIED / Forge packaging | Runtime ENV/PATH/private source projection required separate minimal task image; earlier draft exposed private fixture material. E08. | Separate actor/verifier resources, minimal projection and measured interpreter/stdlib/ENV checks. | Candidate packaging/privacy checks; original private assets never actor-visible; current-source deployment admission still needed. |
| MKT-04 | OPEN / both template owners | Marketing authoring profile v2 is rejected by frozen v1 profile requirement. | Explicit profile/schema capability negotiation and tested successor; no silent aliasing. | Supported exact profile publishes and validates with hidden-reference separation. |

## Deployment, evidence and first real benchmark

| ID | Status / owner | Observed gap and evidence | Prevention requirement | Closure evidence |
|---|---|---|---|---|
| OPS-01 | OPEN / Forge release | Older/newer branches, local candidates and mixed component revisions made deployed behavior unclear. E01/E05. | Show actual web/API/worker/runtime/source/migration identities; compare against intended release. | Exact deployed digest/source manifests and browser smoke; local commit never presented as serving QA. |
| OPS-02 | QA_SUBCHECK_VERIFIED / Forge build | Frontend image initially omitted shared contract sources. E05. | Locked clean build-context closure; real production build before rollout. | Corrected image built and serving; no sibling node_modules or secret source inclusion. |
| OPS-03 | MITIGATED / Forge operations | GCP auth expired during deployment. E01. | Preflight required operator identity/access before build/rollout; safe sign-in handoff. | Reauthentication recovered; durable scoped deployment identity/process remains a design item. |
| OPS-04 | QA_SUBCHECK_VERIFIED / Forge operations | QA boot disk nearly full; approved30→50GB expansion recovered capacity. | Capacity preflight, layer-size budget and explicitly approved retention/cleanup policy. | Expansion verified; no unapproved image/container/volume deletion. Future capacity monitoring remains open. |
| OPS-05 | OPEN / Forge operations | Repeated attempts can lose custody or duplicate effects if blindly replayed. | One-shot rollout/control/import intents, rollback copies, explicit unknown reconciliation and stable idempotency. | Failure/restart tests and retained evidence; no automatic provider retry after uncertain dispatch. |
| QA-01 | NOT_RUN / Forge QA | Software fixtures/units/SQL and fake-socket probes do not prove complete native task execution. E01–E03/E08. | Evidence states must distinguish manufactured control, actual component, full native trial and real model performance. | Required actual current-source controls recorded independently, including failed/not-run cells. |
| QA-02 | NOT_RUN / Forge QA + user | First real QA benchmark has not run. | Predeclared exact cohort/protocol, qualified runtime/bindings, user model/budget and rights approval. | Actual provider request IDs, observable trajectory, separate grading, cost and completed/unknown outcomes. |
| QA-03 | NOT_RUN / Forge QA | First completed run still needs grading/report/reproducibility and recovery acceptance. | Treat execution, task score, validity, spending and report release as separate outcomes. | Frozen cohort/model/environment/criteria; repeat/recovery checks; private isolation; known/unknown spend reconciled. |
| QA-04 | OPEN / exercise owner | Findings have been scattered across sessions/reports. | Maintain this register as primary index; every new failure or manual step gets an ID and prevention lesson. | Dated updates through actual QA run; evidence-linked disposition and later Studio traceability. |

## How to fix the two immediate workstreams

### Runtime: Forge-owned implementation

1. Finish the trusted native Trial owner consuming the technical permit. Bind the
   actual cached image/interpreter/source/locks, root custody, private attempt path,
   process/kernel identity and finite resources. Hash custody alone is insufficient.
2. Validate semantic assets, actor and separate verifier roles before effects.
   Launch the pinned Harbor path; obtain the actual Trial UUID and parent-observed
   process receipt, not API/actor-supplied identities.
3. Persist the O_EXCL intent before creating the business trial/actions. Permit
   only the fixed read-only two-action control against an isolated synthetic fixture.
   No provider credentials, paid dispatch or arbitrary callback.
4. Capture/verify actor observations, separate verifier results and durable events.
   Exercise normal, denial, crash, timeout, reset, checkpoint and no-replay cases.
   Prove owned descendant/container cleanup without PID reuse hazards.
5. Run all required actual MCP/SQL/OPA/ZEN/private-grading/isolation controls, plus
   the four original product-routing/conservation/policy/evaluator controls.
6. Independently review exact current evidence; install a bounded, expiring
   technical qualification receipt only when checks really pass. Do not flip the
   existing source-only gate or set qualified=true to bootstrap a test.

This is engineering work, not something Authoring can fix by exporting more files.
The permit/ledger and regression fixes are local preparation, not completed native
execution. No new deadline or premature readiness promise is inferred.

### Authoring and policy: artifacts + decisions + Forge binding code

1. Preserve v7 and its approved task. Maintain the verified evidence bundle and
   explicitly label missing reviews; do not bind practice documents as public policy.
2. Obtain the actual missing state/applicability/charter sources and scope decisions.
   Preserve source versions, provenance and effective dates. Review scope/content;
   do not create approval markers merely to satisfy a validator.
3. Gym alone completes case-expectation and rights decisions for the intended exact50-case
   population (and private reference handling). Record actual identities, subject
   hashes, expiry/revocation as appropriate. Synthetic provenance alone is not a
   substitute for the application's required decision.
4. Prepare a successor draft such as v8 that references actual artifact identities
   and review subjects under a supported negotiated schema. Keep descriptor,
   normative text hashes distinct. Dataset/record/ID-set hashes stay in Gym's
   private preparation, outside the successor template and Authoring package.
5. Authoring completes its normal approval/publication path; Forge verifies the
   exact authenticated publication and qualifies its execution implementation.
6. Implement/use Forge's authenticated scoped review resolver and restricted
   qualifier/materialization producer. Bind exact task/input/policy/environment/
   evaluator/safety versions, preserving every original input row and pending gap.
7. Revalidate the import, full preparation and revocation/expiry behavior. Only then
   let the user select a model and approve a bounded QA benchmark.

No domain/legal decision is invented by this plan. Review ownership must be agreed;
Authoring transports authentic evidence, Forge verifies/enforces it, and the actual
responsible reviewer/Project Owner makes the decision. Live integration automates
the transport/status/preflight, not the approvals themselves.

## Lessons to carry into the later Studio specification

Capture design candidates, not approved feature promises:

- A template is an execution dependency graph, not just a form and task JSON.
- An environment is an actual qualified capability bundle, not an image/tag or
  installed package list. Its actor, tools, verifier, policy, data and recovery
  resources must be explicit and versioned.
- Publication, import, qualification, preparation readiness and run authority need
  separate visible states and synchronized receipts in both products.
- The normal happy path must discover dependencies and explain gaps before export;
  failure handling, expiry, successors, replay and recovery are first-class flows.
- Source identity and hash-target semantics must be machine-readable. A membership
  identity is not a content identity; a policy descriptor is not policy text.
- Isolation and original-input conservation must survive partial/singleton cohorts.
- Automated generation/provisioning must produce reviewable drafts and actual test
  evidence; it cannot invent law, rights, approvals, implementations or benchmark scores.
- One reusable UI/design language and actual API-derived clients should replace
  repeated ad-hoc controls and mock-only acceptance.
- Operator identity, resources, versions and rollback need preflight. Automation
  cannot quietly broaden privileges, spend or delete retained evidence.

## Update protocol through the first real QA benchmark

After each material finding or milestone: add/extend a row with reproduction and
affected revision; classify defect vs missing input vs missing implementation vs
not-run check; record owner and immediate unblock; specify the future prevention
rule and actual closure evidence. Link its test/report without secrets/raw private
data. Record whether source is local, built, deployed or actually verified.

After the first real run: reconcile planned vs observed case/model/tool counts,
scoring/unknowns, actor/private separation, costs, retries/recovery and release
claims. Review every manual action and every new gap. Then derive the Studio
requirements with stable traceability back to these IDs. Do not freeze a purported
bulletproof spec before those observations or close items just to meet a date.

# Runtime 23 — repeated boundary integrity scans consume the original Trial

Observed on19November: current0102243 transport reached actor SDK entry145s
and verifier entry245s into the same300s allowance, then timed out. Cleanup was
complete; no technical qualification was issued. Complete parent runtime-seal
validation ran at both entry/exit for each of two peers, in addition to independent
SDK startup validation. Per-call common-closure deduplication did not prevent this
cross-boundary repetition.

Engineering correction under review: one nonserializable, exact-plan/PID/deadline
proof for the original Trial only. Reuse requires a fully readonly sealed closure,
including source mirrors and nested mounts; retain fresh process/profile/mount/
plan/deadline checks and full entry/final-exit hashes. Final hash failure or expiry
must discard success. No cross-Trial cache, writable skip, deadline reset or
qualification authority. Studio must estimate integrity/setup/actor/verifier/
finalization cost against the complete original budget and expose stage timings.
Acceptance requires fresh physical controls on the newly built exact image;
source review/unit tests alone do not close this gap.

Closure progress: frozen08d45ff, imagefeedc1a81…, actual filtered transport
completed139.075s within original300s. Full entry+final scan and4callback guards
confirmed; worker/SDK0exit, ownedcleanup complete, positiveUnix/0INETconnect
in observed trees. Evidence8359c921a497259d7fb40e8dec87dfc2e70de1fbd3bb0eceda7e8dc8b32e097c.
Separate fresh native SQL Trial passed. Full aggregation/rollout still pending;
this closes neither human/project binding gates nor model performance.

## Binding 24 — actual dataset context must match applicability evidence

Read-only final-v8 review verified all68 artifact hashes and authentic publication,
four accepted successor tasks and APR records. Those approvals exist; they are
not replaced by the manufactured isolated-registry software fixture.
Default Gym snapshots in golden_kyc_data.py retain assessment_date2026-11-11,
charter profile golden-pilot-pending-legal-review/reviewed=false; environment clock
also11November. Final applicability evidence covers national bank/OCC/homeNY as
of12November. Exact application-policy scope correctly refuses substituting that
different date/profile. Never relabel original snapshots or silently change their
hashes/ages/expectations to fit a receipt.

Before a real run, inspect the actual selected immutable dataset. Remedy requires
either reviewed applicability for its exact original context or an explicitly
versioned compatible Gym dataset/context with preserved source lineage and
revalidated private expectations/clock. Authoring does not own private case data.
Studio must compare task/policy/application charter and time scopes during
binding preview, explain the mismatch before provisioning, and retain exact
owner decisions. A passing synthetic20-cell registry test is not evidence that
the real imported project's dataset context or runtime bindings are qualified.

Local proposal `.local/kyc-v8-context-proposal/` retains exact200parent hashes
(populatione8d5cb8b…); proposed populationfe9571ec…, lineagef4462ae9….
Independent read-only review confirmed350party ages unchanged and all200initial
10-weekday deadlines25→26Nov; illustrative initial5-weekday dates18→19Nov.
The named golden-weekdays calendar excludes weekends, not bank holidays.
Documents unchanged does not prove document freshness or private expectation
no-impact; later-round clocks/responses/statutory scope still require impact
review. Actual selected serverpackID is deliberately null. Proposal is not a
dataset registration, ready flag, context approval or runtime binding receipt.

## Evidence 25 — producer/consumer contracts must cover real process layouts

Independent raw08 review verified8packet/56related hashes,23role inspections,
969terminal trace files and6private scoring/audit joins, then found two receipt
generation blockers. The parent component recorder omitted MCP server source
because that server actually ran in a child process. The role checker recognized
only Docker CLI's no-new-privileges spelling, not Compose's affirmative :true
encoding. Required source hashes and affirmative security enforcement remain
mandatory: recorder now hashes the fixed installed3module allowlist; parser
accepts exactly one of the two affirmative encodings and refuses false,
duplicates or contradictory forms. Fresh affected component control and new
curation/review are required; old evidence is never patched to appear complete.
Studio/release tooling must schema-check producer/consumer evidence on actual
installed process/engine output before a long qualification campaign. Missing
data is a reporting failure, not an excuse to synthesize a successful receipt.

## Operations 26 — validate existing mount encodings before service effects

The first08rollout migrated133, then its checker rejected legacy short binds that
the wiring producer had correctly preserved. Owned rollback restored old6services;
schema133 remains additive. Writer/validator must agree on both reviewed encodings
before mutation. Service-only retry admits only exact observed absolute short
binds, preserves defaultRW, keeps strict long-bind RO/type/path/duplicate checks,
and never replays migration. Local parser controls/source review pass; actual
retry awaits renewed GCP sign-in. Future deployment preflight must validate all
mount encodings before effects and checkpoint schema/config/service stages
independently. Technical qualification19ece… passed; deployment is still pending.
