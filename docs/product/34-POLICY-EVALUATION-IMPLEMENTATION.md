# Praxis and Anvil policy evaluation implementation specification

Version 2.0 · 9 November 2026 · User-authorized implementation baseline

## Purpose and decisions

This specification supersedes the earlier design-only Praxis policy/evaluator handoff. Praxis uses **Project**, containing multiple Tasks. Anvil imports a Praxis Project as a Task Group while preserving its source Project ID and version. A Task Group has many Runs. An Execution Group is a reusable configuration, not a second source Project. Every Run freezes its source, model, environment, method, policy, rule and evaluator versions.

There are exactly two application roles: Admin and RL Engineer. Both configure, test and execute benchmark/evaluator configurations for Projects they can access. No policy approval queue, second approver, fixed-three-reviewer requirement or additional configuration role is introduced. Existing configurable report review and actual Admin exemptions remain distinct from policy configuration. Access boundaries, evidence integrity and paid-call spending controls remain enforced.

Custom policies are optional. Final custom-policy compliance is deterministic. AI may draft formal rules or suggest a compatible registered evaluator, but cannot supply the final compliance judgment. Semantic benchmark judges remain separate measurements. A policy document without executable rules is not a verified policy. Unknown evidence is not Pass, zero or silently excluded coverage.

## Responsibility boundary

Praxis owns Project/Task authoring, source policy documents or text, clause locations, rule intent, Task applicability and source versions. Praxis does **not** install OPA, ZEN or other evaluation engines; hold commercial evaluator API keys; select deployment runtimes; or manufacture Anvil readiness receipts.

Anvil owns engine/adaptor configuration, secrets, deterministic verifier mappings, compatibility and known-case tests, execution, recorded evidence, metrics and reports. Engine selection and rule completion can happen after import. Saved mappings are reused until source policy, environment, schema or evaluator version changes. Changed mappings require ordinary configuration testing, not another approval workflow.

## Praxis authoring screens

PRX-01: Add an optional Policies section to Project and Task editors. Accept pasted text, UTF-8 TXT/Markdown, PDF or DOCX. Preserve original bytes, normalized display text separately, filename, media type, SHA-256 and extraction status. Never run macros or embedded instructions. Text extraction failure does not erase the original; show the affected attachment as needing readable text.

PRX-02: A Project policy applies to all member Tasks by default. A Task can add a policy or explicitly select a narrower policy applicability list. Any exclusion is explicit, versioned and exported. Do not silently override a Project constraint with a Task-level contradiction. Display both clauses when they conflict.

PRX-03: Each policy has a stable ID, immutable version, title, description, source reference and clause/rule definitions. Rule fields are stable rule ID, requirement text, source location, severity, applicability, agent visibility, optional rubric criterion IDs and failure-mode IDs. An expected behavior or test hint is allowed; an evaluator engine is **not mandatory** in Praxis.

PRX-04: Pasted text creates an attachment with an exact UTF-8 content hash. New edits create a new version; an export pins the original version. Deleted or replaced policies remain resolvable for historical exports. Author identity is provenance only, not an approval decision.

PRX-05: Show effective Project/Task policy scope and missing fields inline. Save and export without custom policies is a normal path. No new approval state or Publish queue is introduced by this feature. Existing source-data rights declarations remain independent.

## Versioned export attachment

PRX-06: Preserve the existing `praxis.anvil.export.v1` task envelope and its exact `payload_json` hash. It currently forbids unknown fields. Do not append policy fields to that envelope or reinterpret old source hashes.

PRX-07: Export an additional `praxis.anvil.project_policy.v1` JSON manifest, shipped with the existing versioned Task exports and policy files. This is a proposed new integration contract to implement in both products, not an assertion that old consumers accept it. The manifest includes `source_project` (id/version/name), `task_bindings`, `sources`, `policies`, and source export references. All paths are relative to the package. No network URL, host path, credential, executable verifier, or engine configuration is accepted as policy content.

PRX-08: Source references carry path, media type, byte size and SHA-256. Policy references carry policy ID/version. Task bindings carry source Task ID/version and exact export payload SHA-256. Bindings must match the imported task bank; they do not create membership or authorize a run. Project default applicability is resolved explicitly and snapshotted. Source provenance remains unverified until the application's existing checks succeed.

PRX-09: Required versus optional: source Project identity and collection fields are required in this manifest; collections may be empty. Rules may be empty for a document-only policy. No engine or API key is required. Unknown schema versions, duplicate conflicting IDs, unresolved Task references, unexpected fields, unsafe paths and hash mismatches produce field-specific errors. Same identity/version and bytes is idempotent; different bytes under the same identity/version is a conflict.

PRX-10: Protected expected outcomes, hidden references and adversarial attack goals must not enter the candidate-visible policy projection. Files retain their classification and authorized audience. Import/export never grants new permissions. A candidate receives only applicable agent-visible instructions and permitted source content, never private evaluator programs or full test manifests.

## Anvil configuration and readiness

ANV-01: Administration contains Models and credentials, Frameworks and connections, Benchmark methods, and Evaluators and integrations. Admin and RL Engineer have the same new configuration capability within authorized Project scope. Do not broaden unrelated existing administration privileges as a side effect.

ANV-02: Separate the setup catalog from Installed and connected. A catalog entry is not a usable Run option. Readiness is per installed adapter version and capability: absent, installed, needs configuration, testing, ready, unhealthy, unsupported or archived. Expose concise user-facing status and a reason, not fabricated green checks.

ANV-03: Ready requires an actual installed compatible adapter, pinned package/binary and runtime versions, license compatibility, an available local runtime or authenticated service, validated request/result schemas, and known Pass/Fail/Unknown fixture tests. HTTP 200 or credential presence alone is insufficient. Save a source-bound validation receipt and timestamp. Rotation, version changes or health failure invalidate readiness for future Runs; historical evidence remains unchanged.

ANV-04: Base distribution contains maintained open-source adapter integrations for OPA, GoRules/ZEN, NeMo Guardrails, Promptfoo, Arthur Engine, Phoenix, TruLens and Fiddler Auditor where compatible. Runtime dependencies are independently locked and isolated where necessary. No installation from an imported document or arbitrary package command at Run time. Model artifacts are not implicitly downloaded by the API. Archived Protect AI/LLM Guard is unavailable for new activation. A source-available or commercial product is not falsely labelled permissive open source.

ANV-05: Classify each capability separately: deterministic rule evaluation, model-based guardrail, attack orchestration, trace capture, semantic quality judge or formal proof verification. Only verified deterministic capabilities can satisfy custom-policy compliance. Tracing does not produce a policy score. NeMo/Arthur/Promptfoo configurations that invoke models cannot be silently classified as deterministic.

ANV-06: Provide at least two documented commercial/API adapters with bounded request/response contract tests. Configuration includes adapter ID/version, allowed service endpoint, provider-specific resource IDs, authentication type, secret reference, allowed evidence projection, timeout, result schema and spending scope. A generic endpoint/key form does not count as an implemented vendor integration. Mark contract-tested separately from real-account/live-verified. No account or live result is fabricated.

ANV-07: Use existing encrypted/managed secret storage, project isolation and secret-free API responses/audit. Never export keys into Praxis, browser state, reports or test logs. API-key, bearer and service-identity handling is adapter-specific. Disable redirects, bound response sizes, redact failures, restrict destinations and do not automatically retry ambiguous billable dispatch. No paid tests are enabled by this specification without exact provider/resource/budget authority.

## Deterministic custom rule execution

ANV-08: Complete rules using supported structured templates or a registered verifier bundle. Initial templates cover thresholds, required fields/state, destination allowlists, action ordering and exact required content. Facts come from authenticated captured tool/state/network evidence, not an unverified candidate claim. Numeric units, currency, strict versus inclusive thresholds, nulls and time ordering are explicit.

ANV-09: The mapping stores policy/rule ID/version, evaluator/bundle version and digest, configuration, evidence schema, source clause references and known-case fixtures. Test allowed, forbidden, missing, boundary and contradictory inputs before Ready. AI suggestions are explanatory drafts; saving a mapping is normal configuration, not a separate approval request. Unsupported or vague requirements remain Needs definition.

ANV-10: Evaluators receive bounded read-only evidence projections, private expectations and exact job/run bindings. They run outside candidate custody. They cannot mutate candidate outputs or gain Docker sockets, secrets or arbitrary network access. A verifier crash, timeout or malformed response is an infrastructure/evaluator error; it cannot become a model policy failure or Pass.

ANV-11: Per-rule outcomes are Pass, Fail, Unknown or Not applicable, plus execution state Not evaluated/Error. Preserve severity, reason, attempted/completed findings, evidence references and evaluator version. A blocked prohibited attempt remains an agent-policy Fail; environment containment may separately Pass. Missing evidence yields Unknown. No silent LLM judge fallback.

## Execution groups and Runs

ANV-12: Import source Project as Task Group, choose Tasks, candidate models, repetitions and declared environments, select benchmark methods and saved compatible policy mappings, save an Execution Group and Run. Each Run belongs to one Task Group and freezes the exact plan. Reuse the plan for later Runs. Environment memberships come from Task bindings; do not invent compatible environments.

ANV-13: Only Ready compatible integrations are offered in execution selections and AI matching. A requested but unavailable method remains visibly Not evaluated with a reason; unrelated methods may execute, but coverage is incomplete. Health changes block new affected work without erasing history. No auto-substitution of a model, key, engine or policy version.

ANV-14: Canonical configuration, mappings, tests, Run snapshots and outcomes persist in PostgreSQL with project access controls and auditable changes. Local component state is not product persistence. Historical records and old task exports remain valid. Schema migrations are additive and tested on a fresh isolated database.

## Dashboard and provider report

ANV-15: Global Task Group, Run, model, evaluation period, environment and method selections persist across Overview, Evaluations, Tasks and rubrics, Failure modes, Safety, Remediation and Report preview. Never drop result context when navigating. First matching execution/rubric is selected; rubric and Task detail links open the exact record. Empty, unavailable, error and unauthorized states are distinct.

ANV-16: Evaluations lists only methods/integrations selected or actually used by the Run: version, contribution, execution status, outcome and evidence. OPA returns rule findings; attack tools return case results; trace tools provide evidence, not an invented performance score. Original suites require their exact source/harness; adaptations retain Custom naming and methodology disclosure. Existing 81-point scoring remains separate from judge metrics.

ANV-17: Six-axis spider chart: correctness, evidence completeness, constraint adherence, policy adherence, injection resistance and environment containment. Declare the same Task/model/environment scope for plotted series. Quality axes normalize earned/possible rubric points. Policy axis uses Pass/(Pass+Fail) over decided checks, with explicit decided/planned coverage and Unknown count. Attack resistance counts observed agent resistance; absence of attacker success alone is insufficient. Containment counts forbidden effects actually blocked. Cohorts and denominators remain separate. Unknown/unrun axes are gaps, never zero or Pass. No composite safety/quality score or polygon-area ranking.

ANV-18: PDF and data exports are persistent on all result views and bind exact Run/result hashes and selected scope. Reports for frontier-model teams include visual model comparisons, six-axis profile, critical incidents, task-level rule/tool/state/network excerpts, evaluation coverage, unknowns, actual review facts, remediation recommendations, all included task rubrics and methodology/evaluator provenance. Never fabricate approvals, people/contact details, model measurements, logprobs, hidden chain-of-thought, pricing or catalog rights.

ANV-19: Remediation links task-defined failure modes to applicable versioned Tasks, environments and sample datasets. Clearly distinguish licensed catalog inventory from unverified generated drafts. Explain task/environment/dataset bundle value and show real availability/rights/pricing only when known. Before/after improvement requires matched held-out rerun evidence; preserve regressions and unknowns.

## Delivery and release boundary

The user authorized coding and QA changes on 9 November after review of the full journey and six-axis report. Preserve the independent Anvil checkout, original local changes and Praxis repository. Produce a Praxis coding handoff, not unsolicited changes to Praxis itself. Record working, contract-tested, live-verified, blocked and unimplemented separately. Do not claim every library is integrated because its name exists in a registry.

Local dependency installation, development and relevant tests are authorized. Live model or evaluator API calls need exact provider/resource/budget and locally supplied credentials. No deployment, merge, production mutation, external message, paid evaluation or account creation is authorized by this implementation launch.
