# QA benchmark exercise — living gap register

## 21 November — authored product-profile input setup

GYM-INPUT-44: the real four-product v8 import succeeded, but structured input
upload was hidden when Authoring supplied no default dataset. Gym owns that
dataset; an absent authored default must expose Gym provisioning, not suppress
the input controls. Frontend fix is deployed in adcfbc9; actual QA navigation
exposed the next API defect below. No Authoring edit is needed.

GYM-PROFILE-45: the imported tasks correctly declare the already supported
`golden-kyc-application-type-v1` profile, but the input-family classifier listed
only the older reusable-state profile. Actual dataset GET returned409. Candidate
83baf21 recognizes the exact product profile; unknown/mixed families remain
blocked. Future Template/Environment Studio must register profile-to-input-schema
and native-adapter capabilities together and exercise an actual published task
through import, input catalogue, upload, binding and readiness. A successful ZIP
validation alone is inadequate evidence of this path. Native/read-only/software
qualification and real benchmark admission remain distinct.

GYM-LOAD-46: unbounded binding GETs locked navigation while the full options
catalogue loaded. Frontend now cancels obsolete reads and bounds the wait to60s,
without applying that rule to mutations. Backend candidate83baf21 reuses verified
resource bytes within the existing proof/savepoint and performs its final full
closure verification. Individual configuration/revocation/receipt checks remain;
uncovered adapters use their ordinary path. Future Studio needs latency budgets,
read-stage diagnostics and safe reload, with no global authority cache or blind
mutation retries. Actual backend latency improvement awaits candidate deployment.

POLICY-INTERVAL-47: all20 prepared policy cells retain explicit source decisions
and hashes, but lack concrete applicability intervals. A simulation assessment
date/capture date is not automatically a legal effective interval. Twenty draft
subjects (15 applicable and5 not-applicable) are prepared with a proposed one-day
pilot scope, pending the owner's interval choice. Staging is not approval. Domain
decisions, rights and private expectation reviews require their exact application
subjects; neither import success nor a technical receipt creates those decisions.

## 20 November late evening — release reuse and qualification evidence

The e49 correction passed all three exact-image builds and fresh physical
no-model controls before qualification review. The release used a clean committed
archive, immutable Environment digest for Evaluation, one submission per phase,
durable operation intents, independently reconciled artifacts, and the preserved
128 MiB API scratch mount. Existing serving data and receipt bytes stayed intact
during controls. These observations do not admit authored tasks or real runs.

Future Studio/release automation must address two remaining operational gaps:

- Artifact reuse must be based on each component's exact inputs, identity and
  compatible qualification dependencies. Separate build phases alone do not make
  a release assembler that requires one Git revision on every image safely accept
  mixed, unchanged component revisions. Test that reuse explicitly; do not remove
  immutable-image or source checks to obtain it. This e49 backend decoder change
  affects the shared runtime source, so fresh environment/evaluation evidence was
  required.
- Qualification should orchestrate fresh names, exact current baselines,
  cancellation/terminal cleanup, independent review, receipt staging, expiry and
  guarded cutover as durable stages. Current one-shot operators are retained as
  consumed evidence. Replacing their pins or replaying old intents is not a
  supported automated retry. Diagnostic-file failures must not skip known safe
  cleanup, while ambiguous execution must remain a visible hold.

The real-import blockers remain separately recorded: unsupported authored tool
references, exact Gym dataset/policy-context compatibility and required reviews,
and genuine Admin acceptance for changed qualification subjects. Live integration
would transport artifacts; it would not supply missing reviewed semantics.

## 20 November evening — exact exported-source coverage

EXPORT-OPTIONAL-42: generated SME forms can preserve an empty string for an
optional pick list. The published form/general field validator permits it, but
the product decoder treated an empty example-state string as a selected state
and demanded impossible coverage metadata. Gym's bounded fix projects only exact
string-empty example metadata to absence without rewriting approved source or
hashes. Missing/None/blank and all contradictory/type/whitespace cases now have
decoder tests. This is a Gym defect, not a requirement to re-author SME tasks or
invent a state. Studio must test the actual form's empty-value representations
through the full decoder before declaring an export compatible.

EXPORT-TOOLS-43: the final authored ZIP contains nine procedure tool names outside
the exact published V8 execution catalogue. A free-text tool field passed SME
approval but cannot select an executable capability. Authoring should generate
tool choices and exact ID/schema bindings from the template and validate them
before approval/export. Gym must reject unknown names rather than guess aliases.
Preserve approved originals and use reviewed successor corrections when bound
source bytes change. The consolidated nine-location request is in
`KYC-V8-AUTHORING-TOOL-BINDING-CORRECTION.md`; datasets/private expected answers
remain Gym-owned, not an extra Authoring responsibility.

QA-SUBJECT-44: 20 registry-reader software candidates are not 20 completed native
episodes, evaluator executions or reports. Evidence must join the actual current
four-product import, frozen data membership, task/environment/evaluator versions
and per-cell stage outcomes. Mark manufactured prerequisites and blocked/not-run
stages explicitly. Current reference registration conserves all 200 snapshots
(ten per product/state); authored import/execution is still blocked. A change to
hashed decoder code also requires new source-bound image qualification; old
platform or template receipts must not be silently carried forward.

## 20 November, 9:34 PM Chicago — first-write filesystem parity

OPS-SCRATCH-40: the isolated HTTP test mounted `/tmp` as tmpfs while the serving
API wrote temporary OPA files into its image filesystem. A fresh controlled pair
showed the first image-filesystem write changed only the container root's ctime
and correctly tripped the complete ancestor witness. A dedicated bounded tmpfs
passed the unchanged guard; later tests in an already-written container had
missed the first-write condition. The API-only configuration correction and
actual real Admin registration succeeded without changing images or integrity
checks. Studio/environment contracts must declare scratch storage, mount flags,
capacity, UID/mode and memory accounting; test fresh first-use and repeated-use
conditions against the actual role profile, not just the same image. Do not
prewarm tempfile selection before measuring a first-write control. API and native
control profiles must not silently diverge in the test harness. The QA provisioner
now preserves this scratch contract and rejects destination aliases/overlap.

OPS-ACCEPTANCE-41: runtime deployment, platform qualification, software-reference
registration, exact template qualification, authored ZIP admission and model-run
admission are separate results. The corrected reference has four bindings and
50 evaluator configurations; this is not the authored task ZIP or a real model
benchmark. Browser actions refused before input are not submitted requests;
reconcile immutable receipts and pending transactions before a fresh visible
action. An inaccessible window is not an expired login or a server qualification
failure. Keep real policy/data/case reviews visible after technical acceptance.

## 20 November, 8:55 PM Chicago — rollout contract and authenticated acceptance

OPS-PROFILE-38: Docker Compose can reorder a bind list while preserving every
effective mount. Comparing serialized list order rejected the first cutover and
also obscured rollback acceptance. The corrected operator compares only unique
literal canonical source/destination/mode bindings without overlapping
destinations as an unordered set; effective mounts, mode, propagation, UID,
ordered commands and all other HostConfig fields remain exact. Twenty-six focused
guard tests passed. Automation should retain candidate profiles and safe field
diffs before enforcing guards, distinguish never-started preview defaults from
running-container state, and retain immutable executed-operator bytes. The single
corrected rollout succeeded with all eight qualified images and zero restarts;
no security-profile exception or image rebuild was needed.

OPS-AUTH-39: successful cloud deployment does not establish an authenticated
Forge Admin browser session. The actual QA tab shows Keycloak sign-in; no
registration was submitted. Release completion should report platform health,
authenticated application acceptance, reference provisioning, exact template
qualification and authored-package import admission separately. A different
Google OAuth window is not evidence that GCP or Forge authentication failed.
Continue independent checks and request only the actual missing sign-in.

RUNTIME-CONSUMER-34 follow-up: the reviewed exclusive-consumer corrective control
did run successfully. Both candidate worker and SDK exited naturally with zero;
the observer attributed actual transport to the candidate runtime and the exact
old coordinator was restored after terminal/quiescence checks. The original
shared-queue attempt remains nonqualifying and was not replayed. The accepted
component receipt now covers the corrected actual evidence and is consumed by
the deployed API/native readers. This closes the bounded technical control,
not the future automation gap or project/paid-run admission.

## 20 November evening — qualification consumer isolation and actual host evidence

RUNTIME-CONSUMER-34: a qualification request used the canonical native bridge
while the serving old coordinator was polling that same bridge. The old runtime
claimed and completed it; the new SDK's --once invocation skipped the consumed
request and exited0. The observer correctly refused candidate qualification
because there was no positive new-SDK connection evidence. Retained claim
a0e41fab83174973879ab5a76789299f records old60c, not candidate364. Process exit0
and a successful worker result are insufficient attribution. Studio/release
automation must reserve one consumer per qualification queue/generation, join
actual claimant SDK identity/image/source to every receipt, and distinguish a
no-op claim from executed work. Do not replay consumed attempts. Current bounded
remediation is an independently reviewed idle-coordinator pause with exact
ownership/quiescence/baseline guards, one fresh attempt and verified restoration;
its actual corrective outcome remains pending.

OBSERVER-SENSITIVITY-35: host security settings alone do not prove capture works.
Require a source-pinned physical known Unix connection from a descendant through
the same worker attachment and filtered SDK launch gates. Require actual ACK,
successful connect=0, exact peer, terminal original/descendant traces and PIDFD
closure. Separately require a successful controlled forbidden-peer connection
to be rejected; zero observations or failed connects cannot satisfy that test.
Actual candidate364 self-test passed both roles/cases and independent Aegis
review of29 safe files/inventory9f33fb56...64bfdd. This proves observer sensitivity,
not actual KYC transport, performance, policy/data rights or paid-run admission.
Keep classifier and container security restrictions unchanged.

OPS-BASELINE-36: provisioning defaults and old deployment metadata are not actual
serving truth. QA-specific baseline must retain current OS/kernel/engine/cgroup,
CPU/memory/disk/inodes/time sync/security, effective UID/GID/caps/namespaces,
mount/socket custody and exact image/service identity. Actual baseline4011de5c...
68db8 plus supplement294ec849...be8a1 passed Harbor review; existing capacity and
profiles meet the reviewed QA requirements without VM rebuild or resource
increase. Old global/capture receipts are expired; healthy host/container state
does not extend qualification expiry. Keep host, image, observer, application
transport and genuine benchmark readiness as separate evidence layers.

OPS-DURABILITY-37: temporary local operational files disappeared during the pause.
Recover only exact tracked or hash-verified retained server operators, and retain
plans, intents, actual build receipts and sanitized review packets in durable
release evidence. Preserve source/version distinctions and never reconstruct
successful outcomes from a command template. Record executed guard versions:
the completed cache staging used its original300s pull guard; a later120s source
correction was not retroactively executed. No cosmetic replay or rewritten
historical evidence. Private configs, credentials and raw application data stay
outside Git and exported public evidence.

## 20 November — product-mode provisioning and diagnostic gap

KYC-REFERENCE-31: actual project canonical runtime import count0 caused v8
conformance failure despite installed platform qualification. Existing API
supports four-product reusable_application_workflow, but UI omitted task_mode
and defaulted to five-state mode. WEBONLY06fdab4 adds explicit Admin pack choice
and four-product software-reference registration, independently reviewed and
verified deployed. Registration is an explicit nonpaid engineering operation,
not authored-task import or real dataset approval. Verify4bindings/50evaluator
refs/population conservation and absence of queued jobs/real inputs afterward;
never auto-register during qualify. Current PO attestation is accepted.

KYC-DIAGNOSTIC-32: broad ValueError catch labels missing current project runtime
import adapter_not_supported. Safe local diagnostic patch returns a distinct
provisioning code/mode without implicit writes; it is tested but UNDEPLOYED to
preserve current qualified backend source. Studio should distinguish installed
runtime, canonical reference provisioning, template conformance, authenticated
or locally attested publication, and genuine run-data qualification.

KYC-PURPOSE-33 (BACKLOG, NOT IMPLEMENTED): existing imports have no hard
reference-only purpose/provenance admission fence. A software-reference UI label
is not enforcement. Future design must handle same-pack aliases/legacy imports,
exact selected import revalidation, durable SQL resolved-input guards, historical
and resumed input/package readers and early application-policy dispatch. Do not
alter published v8/task hashes or manufacture genuine dataset classification.
Current bounded reference registration has no automatic input binding/enqueue;
genuine v8 data/context/policy/private-expectation/rights/run gates remain HOLD.

## 19 November, deployed39cb2d9 — verified technical closure and remaining gates

CAPTURE-27/30: corrected restricted catalogue OID checks and API-only capture
qualification are deployed. Actual TLS verify-full probe passed all six
identity/read-only/cancellation/cleanup controls without granting private schema
access. Independent review and installed API receipt consumption passed.
Technical-component qualification passed14 controls, including actual native
Trial, worker/SDK transport, private scoring and SQL/registry controls. Receipts
are scoped and expiring; Studio must automate renewal/invalidation, not preserve
a permanent Ready flag. Failed62 candidate remains retained and unqualified.

CATALOGUE-28: current39 UI separates installed technical evidence from project
readiness; five actual measured observations refreshed. No project binding or
qualification was invented. Two roles without genuine measured observations
remain unobserved. Authenticated current39 visual acceptance is blocked by a
missing controllable Chrome window, not admitted as passed.

OFFLINE PUBLICATION: fresh database read still shows v8 publication/subject/PO
attestation counts0 and six historical blocked qualification rows. The exact
publication record exists in the owner package; it is not missing from Authoring.
The owner must stage it and attest locally using their real account. Studio
should show this precise next action, distinguish upload/registration/publication/
qualification and avoid demanding SME re-authoring or silently approving it.
Dataset/context review and actual Gym bindings remain distinct later run gates.
No live model calls or Authoring integration were performed.

## Capture and catalogue acceptance — 19 November, after deployed08d45ff

CAPTURE-30 (ACTUAL FAILURE REPRODUCED; corrected query verified read-only): all
three62abd00 image builds passed, but its real capture probe failed the identity
SELECT with PostgreSQL42501. Text relation privilege checks required private
schema USAGE; the query also named nonexistent campaign_private.expectations
instead of campaign_private.references. No private schema access was granted.
The corrected query resolves exactly both expected tables using catalogue OIDs,
requires forced RLS and denies table-wide OR any-column SELECT. A fresh scoped
metadata-only QA diagnostic returned restricted=true/read_only=true/ssl=true.
This is query evidence, not complete driver/cancellation qualification. Failed
probe container is retained terminal/PID0/exit1, with no cleanup failures and no
receipt/replay. Studio must test under actual restricted credentials, include
missing-relation/column-grant/RLS negatives and retain safe original error class/
SQLSTATE. Admin/owner success or mocked driver tests cannot prove this boundary.

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
