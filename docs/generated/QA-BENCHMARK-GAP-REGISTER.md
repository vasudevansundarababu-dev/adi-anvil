# QA benchmark exercise — living gap register

As of 18 November 2026. Purpose: learn from the complete Authoring → Forge → real
QA benchmark exercise, then use evidence to write the Template and Environment
Studio specification. **This is not that Studio specification.** The user explicitly
deferred Studio design until more lessons are known. No claim of a gap-free system.

## Corrected ownership and privacy boundary — user decision, 18 November

Authoring binds applicable policies and business rules to tasks. Gym binds those
rules to evaluators and owns private datasets, cohorts, hidden expectations, data
rights/case reviews and environment qualification. SMEs never write interfaces;
Authoring uses Gym's published abstract tool/input/output catalog. Live integration
must not expose private case IDs, population hashes, counts or expected answers.

| ID | Status / owner | Observed gap | Prevention | Exit evidence |
|---|---|---|---|---|
| SEC-01 | LOCAL_VERIFIED / Gym API | Generic contract discovery included dataset inventory for Authoring export clients. No live exposure is established. | Skip private inventory lookup entirely for project export-client and workload-identity callers. | Three route tests pass for both external modes and authorized internal discovery; candidate not deployed. Other response paths still require privacy review. |
| FLOW-11 | LOCAL_VERIFIED / Gym input binding | Stored Admin ZIP resolution uses user_session, but input binding required workload_identity. | Validate each genuine server-stored mode without relabelling identity; verify exact project/package/receipt/source/sponsor and current Admin membership for offline uploads. | Positive unchanged-identity and negative tamper/project/sponsor/revocation tests pass. Full offline package preparation awaits successor and runtime qualification. |

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
| FLOW-03 | OPEN / Forge API | Generic contracts do not yet provide the complete dependency/review/readiness discovery contract. E04. | Extend through negotiated versioned schemas; separate current from proposed APIs. | Authoring can enumerate exact requirements and fixes before export. |
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
