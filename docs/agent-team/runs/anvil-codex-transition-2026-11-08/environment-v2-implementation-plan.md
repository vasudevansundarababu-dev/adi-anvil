# Approved environment specification implementation plan

## Authority and baseline

Planning input: ADI Anvil Implementation Specification revision 2.0, 9 November 2026. Source: `/Users/vasudevansundarababu/Documents/Codex/2026-11-09/referenced-chatgpt-conversation-this-is-an/outputs/anvil-implementation-spec/ADI-Anvil-Implementation-Specification.docx`; SHA256 `20140f38d36db2bcad07f1d56223da2a08d296bb62f0b4486e76df9083d2f5f3`. Read the complete document, including S01–S28 and AC01–AC22. This plan records scope and dependencies; it is not implementation or acceptance evidence.

Current local product baseline: `420ed32e5b5eaa1177f40d879954a375df890dd7`, unpublished and undeployed. Existing fictional preview is retained unchanged. Its eighteen stored simulator cells are software evidence, not six-seed native/model qualification.

Current reusable foundation: frozen Project/Task imports, optional policy sources, deterministic evaluator configurations and receipts, reusable execution groups, durable Run/capture/assessment records, seven result tabs, filter persistence and scoped exports. `workspace_environments.py` currently quarantines uploaded Docker contexts; it does not build executable environments. Existing `harbor_worker.py` has a bounded gateway/host boundary, not the new six-template provisioning and evidence contract. Preserve those boundaries rather than enabling arbitrary uploaded Dockerfiles.

## Ownership and invariants

This isolated checkout owns Anvil implementation. The other chat titled “Anvil new version: Praxis import and…” was read on receipt of this handoff; its latest response says it currently owns Praxis monitoring and has not begun Anvil implementation. No other chat or agent was messaged or resumed. Do not edit the original dirty checkout or Praxis. Independent QA owns its test expectations and acceptance execution; local developer tests do not imply its acceptance.

Preserve existing model identity/settings/selectors, method availability, repetitions, shell/navigation, seven tabs, rubric definitions/formula and historical records. Add environment/data/binding details without replacing the benchmark dashboard. Preserve actual KYC-001; the prior fictional KYC-001 control is not the authentic source blueprint.

Praxis supplies published frozen task/rule/rubric/source snapshots. Anvil supplies technical bindings, not policy authoring or extraction. Existing optional-policy intake is retained for legacy compatibility; the new path imports published extracted snapshots and does not add a second OpenQuery extraction workflow. Both Admin and RL Engineer use existing configuration/execution permissions; no new approval queue or SME role.

## Delivery sequence and evidence gates

### E0 Contract reconciliation and baseline preservation

Inspect actual installed Harbor APIs and pinned adapter packages, existing importer/export schema, rubric representation, gateway, database migrations and UI routes before selecting concrete new interfaces. Reconcile the actual published Praxis contract read-only; document missing exports. Capture screen/control baselines and legacy fixtures. Preserve old simulator Runs and old immutable hashes.

Outputs: typed contract decisions; installed-version/interface inventory; AC traceability; migration and backwards-compatibility plan. Gate: AC01, AC02, AC13, AC20, AC21 baseline checks.

### E1 Versioned metadata and additive screens

Implement strict bounded schemas and transactional metadata for TemplateVersion, ComponentSpec, DataPackManifest, scenario, EnvironmentVersion, runtime profile, BuildRequest/Receipt, TaskBinding, EvidenceEnvelope and evaluation revision. Canonical semantic hashes and source-byte hashes remain distinct. Registered versions immutable; draft updates require expected revision. Reused idempotency key with different content is rejected.

Add S08–S17 environment/data pages and S26/S27 impact/readiness through existing components; extend S01/S03/S05–S07/S18–S25. S02/S04 retain current behavior. S28 remains an explicit engineering trial. No success state based on a UI label.

Gate: AC01, AC05, AC07, AC15, AC20, AC21. Exercise tenant isolation, stale drafts, duplicate requests and historical resolution.

### E2 Materialized seed packs and component implementations

Build a shared component runtime for database, software, stateful local API and files. Each component owns actual state, typed tools, loader, reset, health and trusted exporter. Generate deterministic synthetic fixture bytes without paid inference, retain seeds/clocks/source hashes and isolate private controls. Imports/hybrid packs require explicit schema mappings, provenance, coverage and materialized outputs. Partial packs stay visibly partial.

Implement the financial seed vertically first, then reuse proven interfaces for the remaining five; all six remain mandatory. Per-seed minimum scenario count is five, yielding thirty proposed software fixture scenarios, not thirty new Praxis tasks.

| Seed | Required working state | Required evidence and reset scope |
|---|---|---|
| BOD-FIN | Company/period/statement/source tables, financial research workspace, bounded read-only query tools, statement files and saved analysis | Query/result snapshots, decimal calculations, units/currency/revision and source locators; clear sessions/outputs and restore exact statements |
| MKT-PHONE | Product facts, audiences, campaign/budget/approval state, campaign application and stateful placement stub | Actual creative bytes, fact references, aggregate budget and event order; restore database/stub/queues/assets/clock |
| MKT-LOCALE | Channel/locale requirements, asset versions, review workflow, actual render/export/inspection and submission stub | File dimensions/format/text/coverage and approval sequence; restore assets/rows/cache/submissions |
| BNK-KYC | Customer/case/document/check/request/decision/refresh state and readable fictional evidence | Case-linked documents, scenario dates, actual information requests and decision transitions; restore all state owners |
| BNK-KYB | Dated ownership/control graph, source documents, screening stub and investigation workflow | Exact decimal path arithmetic, parallel paths/cycles, edge source evidence and decisions; restore graph/stub/reports/cache |
| BNK-AML | Customer/account/transaction/alert/case/disposition state and investigation tools | Query windows/returned transaction IDs, steps, evidence, escalation/order; restore ledger/cases/queues/clock |

Gate: AC04–AC07, AC10, AC11. Mutate every state owner, reset, compare declared logical digests and run simultaneous isolation probes. Unsupported semantic evaluators stay unavailable; exact file metadata is not a translation/claim-quality verdict.

### E3 Automatic GCP build and lifecycle orchestration

Implement a versioned runtime profile and durable idempotent phase jobs: preflight → content-addressed build/publish → provision/connect → load/read-back → behavioral/reset/isolation/evidence validation → registrable version → explicit registration. Record operation/resource/image identities before dependent work. Handle operation polling, timeouts, quota errors, crash recovery and partial load. Cancellation and cleanup have separate durable states.

Use the documented Compute-worker/inner-Harbor split only after installed Compose/collection capability is proven. App/API/general workers receive no Docker socket, private evaluator references or broad cloud credentials. Secret references resolve only through the scoped execution identity. No deprecated container startup agent.

Local implementation and contract tests may proceed without provisioning. Actual GCP testing needs a reviewed profile with exact project/resource/IAM/cost/lifetime/cleanup scope. Existing obsolete $5 build authority and monthly allowance are not a new runtime authorization. Gate AC03, AC16–AC18 requires real resource/build/load/delete receipts; mocks cannot satisfy it.

### E4 Task bindings and trusted evaluation

Import actual published snapshots, preserve rule applicability/precedence and bind exact task/rubric/source versions to registered environment/pack/scenario. Resolve each criterion and rule to a real compatible evaluator, field-level trusted evidence mapping and known-case receipt. Domain meaning cannot be rewritten in Anvil.

Persist separate agent outputs, trusted service events, consistent database/API exports and private references. Check hashes/trust/source-attempt ownership before evaluating. Missing evidence → Unknown/unresolved as declared; evaluator failure → Error; no silent zero/Pass/fallback. Shared policy/criterion findings receive no duplicate weight. Regrades create new revisions over preserved evidence.

Gate: AC02, AC08, AC11–AC15. Test valid, violating, absent, corrupt, out-of-scope and execution-error evidence.

### E5 Harbor Run lifecycle and existing reports

Freeze model/settings/harness, task/rule/rubric/source, environment/image/pack/scenario, runtime, collector and evaluator tuples at Run creation. Persist independent attempt rows before dispatch. Exact selected model × task × scenario × repetition × existing environment conditions produce the attempt matrix. Initialize/reset before candidate start; preserve multi-stage state within its authored attempt.

Use the bounded provider gateway and one execution owner. Trusted collectors flush/export before destruction; separate verifier consumes explicitly declared artifacts. Inspect Harbor collection statuses even when a trial reports completion. Uncertain mutating calls require deduplication/read-back or explicit uncertain termination, never blind replay. Cancellation retains available evidence; retries use linked fresh attempts and retain failures.

Extend existing seven views/PDF with version and criterion evidence drill-down. Preserve original scoring and separate safety/infrastructure metrics. Gate: AC09–AC17, AC20–AC22. Real provider/model/budget/data-rights authority remains required for live model validation; current paid-call-off policy is not changed by a specification describing that target.

### E6 Six-seed acceptance and optional OpenEnv comparison

Complete a separate readiness matrix for each seed: actual source/task mapping, materialized pack, component load, reset/isolation, evaluator fixtures, actual model attempt and report. A synthetic fixture never fills an authentic source receipt. Execute AC01–AC22 with inspectable evidence. Record failed/skipped/not-run checks independently.

Only then compare direct Harbor with an explicit pinned OpenEnv route using equivalent inputs/evaluators and selected action/reset contract. Verify collection/cleanup before latency/cost. Native reward remains diagnostic. AC19 requires actual installed-route verification, not source documentation alone.

## Dependencies that remain explicit

- Published authentic six-seed task/rule/rubric/source snapshots; exact KYC-001 and financial-versus-marketing mapping.
- Authorized and versioned source packs/assets or deliberately labeled synthetic inputs.
- Exact selected model identities/configuration, provider access, data rights and bounded live-test budget.
- Approved GCP runtime identity/resources/network/registry/storage/cost/lifetime and cleanup scope for actual provisioning.
- Appropriate configured subjective evaluators for translation/creative semantics; deterministic checks cannot certify these.
- Independent QA update from its current older cases to revision 2.0 and actual execution against the matching build. Its latest reported 212 local checks and 228 blocked/skipped product cases are not current Anvil acceptance.

No cloud resources, deployments, paid calls, source imports, model executions, new permissions or agent restarts were performed to create this plan. The current local preview remains on the completed earlier runtime. All six seeds are planned, not implemented by this document.
