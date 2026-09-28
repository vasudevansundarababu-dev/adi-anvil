# ADI-Praxis and Frontier — Integration Specification

Version: 0.3 · 27 September 2026
Status: Product division confirmed; interface design proposed; documentation review only

## 1. Confirmed division

The user reports that Praxis has launched for testing. F-D11 confirms that **Praxis owns SME task authoring and business-content review. Frontier qualifies accepted tasks for research, builds environments, runs evaluations and packages results.** Frontier does not recreate the SME onboarding, workbench or task-acceptance console.

F-D14/F-D15 subsequently define a partner-supplied 200-case business-diagnostics SKU with partial inputs and ADI enhancement. Proposed F-A07 allows those cases to enter F03 through approved partner intake with source/content/research gates, without mandatory reauthoring in Praxis. This document governs the Praxis integration when used; it is not a requirement that every source case originates there.

Praxis acceptance and Frontier qualification answer different questions. Praxis asks whether the expert-authored case is acceptable business content. Frontier asks whether that exact version is suitable for a specified research protocol, environment, split and permitted use. Neither decision proves a benchmark improvement.

Research objective in Frontier → production brief to Praxis PM → SME authors and Praxis Reviewer accepts → accepted-record intake in Frontier → research qualification and environment binding → authorized assessment → optional human RL-result review in Praxis → Frontier scientific assessment/report → approved package delivery.

These are independent products and data stores. Use a versioned adapter, not shared tables, cookies, migrations, runtime packages or automatic role inheritance. The first adapter can be tested with synthetic contract fixtures without a running Praxis instance.

## 2. What the supplied materials establish

Evidence labels: **User-confirmed**, **Documented**, **Proposed**, **Verified by test**. This review establishes no live-runtime verification. The API quick reference describes routes generated from source, but does not supply a complete integration schema or prove the deployed build matches it.

| Area | Documented Praxis behavior | Frontier implication |
| --- | --- | --- |
| Contributor lifecycle | Candidate sign-in, identity flow, profile conversation, human selection, onboarding, PM assignment and SME acceptance | Keep in Praxis; do not import identity evidence or duplicate the process |
| Task creation | KYC workbench W00–W06; manual, document, transcript or AI interview drafting; author confirmation; human accept/rework/reject | Reuse this production workflow; multi-domain support beyond the documented KYC path needs validation |
| Task payload | Scenario, evidence, recorded tool calls, reference trajectory, rubric, coverage and edge cases | Useful source assets, not automatically a complete executable environment or calibrated grader |
| Accepted dataset | Append-only records, lineage, corrections as successors, hashes and JSONL export | Pin source record and content digest; preserve supersession and audit references |
| Tool replay | MCP tool schemas and recorded arguments/results; unfamiliar arguments return an error | Qualify as recorded replay, not a general simulator |
| RL feedback | Gym submits run/task evaluation evidence; Reviewer claims and judges metrics; results can be pulled | Reuse for domain judgment; Frontier retains protocol, scientific validity and report ownership |
| Testing | Supplied tracker has 144 cases, all marked Not run; tester/build fields are empty | This copy is test coverage, not evidence of test passes; newer execution evidence may exist elsewhere |
| Test limits | Candidate sign-in, identity and email simulated; upload malware scanning is a placeholder; no blind solve in v1 | Test-only data cannot establish real identity verification or production readiness |

The reference materials distinguish decisions attributed to the owner, a specification or the implementation assistant. Do not elevate every implementation choice into an approved Frontier policy. In particular, source model identifiers and provider choices are unverified configuration descriptions, not recommended or confirmed available model products.

## 3. Ownership and records

| Object or action | Authoritative system | Frontier handling |
| --- | --- | --- |
| SME profile, identity status, source documents, transcript, terms, staffing | Praxis | Prefer opaque references and necessary scoped attestations only; no identity documents or profile-chat export |
| SME task draft, reference solution, business rubric and content acceptance | Praxis | Read accepted version; request content correction through Praxis, never overwrite locally |
| Research objective and production brief | Frontier F01/F03 | Immutable approved brief reference; PM maps it to Praxis project/template/coverage slots |
| Approved Task Record and its correction lineage | Praxis | Restricted immutable source snapshot with digest and source instance/build provenance |
| Capability mapping, family ancestry, research suitability and split allocation | Frontier F03 | Versioned research metadata referencing the source snapshot |
| Environment, executable grader and reward configuration | Frontier F04/F06 | Separate versioned artifacts derived from authorized accepted content; record transformations |
| Agent run, observable trajectory and automated score | Frontier F06 | Exact run/task/protocol/grader references; no hidden chain-of-thought |
| Human RL-review verdict | Praxis | Append imported review evidence without replacing original scores or traces |
| Scientific conclusion, customer claim and delivery manifest | Frontier F06/F08/F09 | Independently reviewed and audience-controlled |

Source corrections go through Praxis's authorized Admin process. Frontier can flag a source as unsuitable/withdrawn for its own use and stop new deliveries without altering Praxis's record. Changing the task's business logic requires a new source version and content review. Binding accepted content to a simulator is a Frontier transformation with separate fidelity review, not a second SME authoring workflow.

## 4. Documented interface surface to reuse

All paths below are relative to `/api/v1`. Do not infer permissions beyond the source reference.

| Interface | Documented access | Proposed use |
| --- | --- | --- |
| `GET /dataset/records`, `GET /dataset/records/:id` | ADMIN or RL_GYM key | Accepted-task intake; record pagination checkpoint after durable ingest |
| `GET /dataset/export` | ADMIN or RL_GYM key | Approved JSONL file handoff where API integration is not yet ready |
| `GET /dataset/records/:id/lineage` | ADMIN or RL_GYM key | Source, project/template, author/reviewer and drafting provenance; minimize identity in downstream views |
| `GET /dataset/records/:id/replay` | ADMIN or RL_GYM key | Recorded replay bundle, restricted to environment packaging/authorized reference handling |
| `GET /mcp/kyc/tools` | ADMIN, PM, REVIEWER or RL_GYM key | Pin tool-catalog version and schemas |
| `POST /integrations/rl-gym/review-requests` | ADMIN or RL_GYM key | Request human interpretation of permitted run evidence |
| `GET /integrations/rl-gym/results` | ADMIN or RL_GYM key | Pull review results using documented sequence cursor behavior |
| `POST /dataset/records/:id/corrections` | ADMIN only | Existing source correction process; Frontier RL_GYM key must not perform this |
| `GET /dataset/verification` | ADMIN only | Request attestation from an authorized Praxis operator; no role escalation to obtain it |
| `POST /projects/:id/task-inputs` | ACCESS or CLIENT_API key in source table | Semantics and project authorization require confirmation; not presumed to accept Frontier production briefs |

The documented RL_GYM key is not a PM account. Project creation and staffing routes are not assumed available to it. For the first version, a human PM can receive the production brief and record the Praxis project reference. Automated project creation requires an explicitly approved contract later.

The docs describe a signed result webhook, but the test flow uses pull-only results. **Proposed initial transport: API polling, plus authorized JSONL import as a fallback.** Do not create a second synchronization mode until schema, signing, replay protection and reconciliation are tested.

## 5. Minimum Frontier adapter contract — proposed, not an existing Praxis API

Persist separate records rather than extending Praxis's database:

1. `PraxisConnection`: source instance, environment label, allowed project scope, pinned schema/build compatibility, secret reference and last compatibility check. Never store a bearer key in a task or manifest.
2. `ProductionRequest`: objective version, capability/behavior, domain/locale, coverage slots, requested family and instance counts, permitted sources, human gates, expected outputs, reviewer requirements, exclusions and external project reference. Requested budget is not authorized spend.
3. `PraxisSourceSnapshot`: source record ID, source version or supersession reference when available, source instance, capture time, canonicalization rule/content digest, permitted payload, provenance and rights evidence. Preserve unknown mandatory fields as incompatibilities rather than guessing.
4. `TaskQualification`: snapshot ID, capability/family mapping, purpose, constraints/ambiguities, reference visibility, grader/environment bindings, leakage checks, partition, reviewers, verdict and limitations.
5. `ReviewExchange`: local assessment/episode IDs, exact source-record IDs, externally compatible `rl_run_id` and `rl_task_id`, submitted payload digest, metric/grader mapping, disclosure approval, idempotency key, external request ID, delivery attempts, result sequence and imported verdict.
6. `SourceChangeEvent`: successor/withdrawal signal, affected versions and packs, disposition, review owner and audit time. It marks dependencies for review; it does not rewrite past results.

Actual request/response bodies, error codes, size limits, UUID formats, pagination guarantees, key project scope and schema compatibility must be verified against a supplied OpenAPI snapshot and build-specific examples before coding. No API calls were made during this review.

### Import behavior

Received → Schema/rights checks → Research review → Qualified for named use, or Blocked / Changes requested / Not suitable. Superseded and Withdrawn preserve lineage. These are Frontier states, not assumed Praxis enum values.

Persist snapshot and deduplication key transactionally before advancing the cursor. A repeated source record and digest is a no-op. The same immutable source ID with conflicting contents is an integrity exception, not a silent overwrite. An unknown schema or missing use permission blocks qualification. Failure after a partial page resumes without duplicating tasks. Imported counts distinguish records, successor versions, families, variants and usable tasks.

Imported `accepted` means accepted in Praxis only. It never sets Frontier `qualified`, `test_unexposed`, `rights_cleared` or `customer_accepted` automatically.

### Feedback behavior

Before posting, pin the run, source versions, observable trace, automated metrics and permitted audience. Submit only evidence the assigned Praxis reviewers are authorized to see. The source docs deduplicate by `(rl_run_id, rl_task_id)` even when a new Idempotency-Key is used. Reuse the original key for retrying an uncertain identical submission. Changed content needs a new explicitly versioned exchange, not reuse of the same semantic pair.

Pull results incrementally. Store the external verdict and its metric agreements/disagreements separately from computed scores. A human disagreement opens Frontier adjudication; it is not an automatic score overwrite, source correction, reward update or learning trigger. A model rerun or revised grading creates new local evidence and an explicitly mapped new external review identity.

The documented API lists a maximum of 100 evaluation results in a review request test. Confirm deployed limits and batch semantics rather than blindly splitting a scientific judgment. Review cancellation, reassignment, verdict correction and timeouts remain compatibility questions; do not invent existing endpoints.

## 6. Recorded replay versus an interactive environment

Praxis's documented replay returns a recorded result for matching tool arguments. TC-ADM-011 explicitly expects unfamiliar arguments to return `isError` with no recorded response. Treat this as `RECORDED_REPLAY` in Frontier metadata.

It can support scoped tool-use and evidence-synthesis checks if the task is actually solvable through those calls. It does not establish arbitrary alternative actions, changing inventories, simulated time, branch-dependent observations, repeatable side effects or recovery after unrecorded events.

For a dynamic environment, specify and test `STATEFUL_SIMULATION` separately: state representation, observation filtering, action validation, transitions, event/time model, side effects, reset isolation, termination, truncation and scoring evidence. A future generative tool-response fallback is a separate, unapproved mode requiring grounding and consistency checks; never add it silently to replay.

Distinguish an invalid action under a declared interface from a valid alternative action the replay fixture does not support. The latter is environment coverage uncertainty, not automatically a model reasoning failure. Freeze the treatment in the protocol before measurement.

Do not mark a case long-horizon merely because a KYC authoring test asks for at least six reference steps. Qualify dependency structure, partial information, decision consequences and recovery or escalation opportunities. An expert reference trajectory is one valid example, not the only accepted path or the agent's private reasoning.

## 7. Safety, rights and evaluation boundaries

- Synthetic-only task content is a documented Praxis rule. Synthetic does not establish permission to use employer procedures, customer documents or protected benchmark material. Check rights and provenance separately.
- Source uploads and author interview transcripts remain private in Praxis and are excluded from the dataset by the documented policy. Do not fetch them via a privileged workaround. Lineage may contain author/reviewer identifiers; replace these with approved references for customer delivery unless disclosure is authorized.
- No identity images/numbers, credentials, raw onboarding records or simulated verification presented as real credentials in Frontier packs.
- Source policy allows explaining scanner flags. An explanation is review evidence, not proof that a real identifier is permissible. Frontier must still block disallowed personal/customer information and quarantine the candidate asset.
- Actor views exclude reference answers, rubrics that expose answers, source provenance text revealing the solution and hidden future state. Keep full replay/reference payloads behind a trusted harness boundary rather than handing every field to the tested model.
- Assign family/source/near-duplicate groups before train/dev/test partitioning. Praxis's similarity warnings are an input, not a proven cross-pack contamination firewall.
- A protected evaluation trace sent for review remains protected. SME/advisor exposure is recorded; no automatic conversion to training data. Results-only private-customer evidence may be too limited for domain review; record that limitation.
- Use isolated credentials per environment and approved project scope. Documentation of role-level RL_GYM access does not prove per-project key isolation. Confirm least privilege before multi-customer data is connected.
- Do not embed private bearer-signed trace links in customer reports or logs. The manual says Praxis does not fetch the large-trajectory link server-side. Recipient scope, expiry and allowed hosts still need an integration design.

The supplied security and nightly-process manuals are reference procedures only. This task does not authorize scans, account creation, uploads, nightly jobs, API calls, deployments or external issue reports.

## 8. Readiness gates and test mapping

| Gate | Source coverage to request evidence for | Additional Frontier contract check |
| --- | --- | --- |
| Accepted task intake | TC-E2E-001/002/003; TC-REV-012/013 | Exact accepted snapshot enters research review, never auto-qualification |
| Dataset and lineage | TC-ADM-009/010; TC-RLG-005 | Pagination retry, deduplication, successor import, digest mismatch and dependency invalidation |
| Replay | TC-ADM-011; TC-RLG-007; TC-SME-032/033 | Hidden-answer separation, unfamiliar valid arguments, reproducible recorded results and explicit mode labeling |
| Human feedback | TC-E2E-005; TC-RLG-001/002/003/004; TC-REV-020/021 | Stable run/task mapping, timeout retry, disagreement adjudication, protected-trace exposure and no automatic learning |
| Authorization/privacy | TC-ADM-007; TC-RLG-006; TC-SEC-005/006/014/015/018 | Cross-project/client key isolation, minimal provenance disclosure and test/production credential separation |
| Production onboarding/uploads | Guide known limitations; pen-test rules accepted items | Actual auth/identity/email activation and malware scanning require Praxis-owned production readiness evidence |

Frontier acceptance tests, not yet executed:

- F-PX01: No SME authoring, selection or source-content approval screen is duplicated in Frontier.
- F-PX02: A Praxis-accepted record can be blocked by Frontier for research unsuitability with both verdicts intact.
- F-PX03: Reimport/retry creates no duplicate task version or human-review request.
- F-PX04: Corrections append successor mappings and mark affected assessments/packs for review without erasing history.
- F-PX05: RL_GYM cannot correct source records or create projects using undocumented privileges.
- F-PX06: Recorded replay cannot be advertised as tested stateful simulation.
- F-PX07: Unfamiliar valid tool arguments are classified under the frozen environment policy, not silently counted as model failure.
- F-PX08: Identity/source-upload/hidden-answer material is absent from unauthorized actor and customer exports.
- F-PX09: Human verdict disagreement preserves original metrics and requires explicit adjudication.
- F-PX10: Missing rights, incompatible schema or unknown tenant scope blocks intake qualification.
- F-PX11: Test-only identity outcomes cannot produce a real-credential-verification claim.
- F-PX12: Diagnostic delivery works without F05, ADI weights, learned TTM or a live shared Praxis database.

## 9. First integration proposal and open items

Confirmed first SKU is **200 business cases across Marketing, Finance, Strategy, M&A and other supplied areas**, with partial Bodhium inputs and ADI enhancement for lab requirements (F-D14/F-D15). KYC and shopping are not the selected first SKU. See [the case diagnostics specification](13-BUSINESS-CASE-DIAGNOSTICS-SKU.md).

Proposed proof: a representative permitted case sample, source/version mapping, reviewed task/reference/rubric enhancements, one compatible model/agent interface and an evidence-backed diagnostic. Use partner intake without a compulsory Praxis project. If expert enhancements or human feedback are commissioned through Praxis, test that handoff on content its current policy and schema permit.

Required Praxis adaptation assessment when used: multi-domain template/ontology; task fields and artifacts; approved tools; reference alternatives and rubrics; appropriate expert/reviewer scope; rights and content policy; dataset/export compatibility. Preserve source provenance and the synthetic-only boundary. Do not upload original educational case packs into a synthetic-only task workflow or copy KYC rules into business-case judgments. Proposed enhancements require separate authorization before code changes.

The newer user-reported case-solving agents and faculty-reviewed collection extend the older Bodhium R03 context. Request actual harness, input and result evidence. Neither those reports nor the older question-mining assets establish an available general simulator; only interactive cases require a stateful environment contract.

Before implementation obtain: a build-specific OpenAPI snapshot, redacted accepted-record/replay/review payloads, executed test results, approved connection/project scope and a rights/terms summary. Before external promises also resolve: blind-solve/independent solvability evidence, grader calibration, family/split safeguards and the required environment mode.

Source details are in [the source register](SOURCE-MAP.md#praxis-reference-materials-received-27-september-2026). Outstanding product decisions are consolidated in [the review brief](12-REVIEW-BRIEF.md). No source files or live Praxis systems were changed.
