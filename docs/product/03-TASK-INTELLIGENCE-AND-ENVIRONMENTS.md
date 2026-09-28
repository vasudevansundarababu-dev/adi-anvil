# Frontier — Task Intelligence and Environments

Version: 0.4 · Review draft · 27 September 2026

## 1. Terminology and ownership

Use the user's definitions: **TNG (Task Neural Graph)** represents possible work through states, transitions, specialists/agents, tools, constraints and completion conditions. **TTM (Task Transition Model)** selects a next transition given information, goal, history and available capabilities. Learning better navigation is a hypothesis, not a validated feature.

Earlier module drafts use TTG/TTN. Their equivalence to TNG/TTM is unresolved. Do not invent expansions, rename schemas or require a trainable graph model by inference. Frontier can qualify useful tasks and run free-planning assessments without a learned TTM or an ADI navigator.

The confirmed division (F-D11) places SME authoring and business-content review in Praxis. Frontier Task Intelligence Studio owns production briefs, task intake, research qualification, capability/family lineage, scenario variation specifications and procedural/environment bindings. Praxis source changes return to its source-review process; Frontier must not become a second editable master. Prepare Data handles source records/ontologies and existing eligible trajectory data, not task import or graph conversion. See [Praxis integration](11-PRAXIS-FRONTIER-INTEGRATION-SPEC.md).

The first SKU is now the 200-case multi-domain business diagnostic (F-D14/F-D15), superseding the marketing-only/shopping pilot. Proposed partner intake permits source case/task packs directly into F03 with provenance, rights and content/research qualification, without forced reauthoring in Praxis. Partial inputs create a case-level gap ledger. Version lab-specific task/reference/rubric enhancements separately from the immutable originals; use qualified expert review and do not inherit faculty validation automatically. See [SKU 01](13-BUSINESS-CASE-DIAGNOSTICS-SKU.md).

Praxis remains the commissioned SME production/review system where schema and content policy fit. Its documented synthetic-only policy and KYC fields do not establish support for original educational cases or multi-domain business rubrics. Any adaptation is separately specified and authorized. Partner solver code is not presumed to be a general simulator.

## 2. Task definition proposal

A versioned task contains objective, actor-visible starting information, allowed tools/actions, prerequisites/dependencies, constraints, permitted alternative completion paths, termination conditions, reference outcomes or expected escalation, difficulty axes, domain/locale, family/source/generator lineage and permitted use.

Capture long-horizon structure through dependent decisions, state changes, incomplete information, recovery and verifiable completion—not merely a large turn count. Synthetic variations must change meaningful conditions and retain ancestry; repeated names/numbers are not new independent families.

Expert reviews business meaning, ambiguity, solvability and edge cases; technical reviewer checks executable interfaces. AI suggestions are drafts. Hidden reference states, future events and privileged graph solutions stay separate from actor observations. Protocol states whether any graph assistance is visible; there is no single forced successful path.

Praxis owns its draft/submission/content-review states. Proposed Frontier states: Received → Schema/rights checks → Enhancement required when applicable → Research review → Qualified for named use → Published version. Blocked/Changes requested/Not suitable/Superseded/Withdrawn preserve source and review history. Imported source acceptance or faculty-review claims do not auto-qualify a task. Frontier domain experts review research meaning, new enhancement content and environment/grader fidelity without overwriting source approval history. Publication does not start execution. Detailed reviewer assignments and thresholds need confirmation.

## 3. Environment placement and responsibility

**Frontier Environment Studio is a top-level area.** It delivers controlled research environments independent of any ADI training service. A customer can connect its own policy/model to an agreed observation/action interface; no weight upload is required.

EnvironmentVersion includes package/image digest, observation/action schemas, reset/step/close behavior, initial-state source, tools, permissions, controllable injections, hidden-state isolation, limits, termination/truncation/error rules, reproducibility limits, dependency/license/egress manifest and qualification evidence. A record corpus or question library alone is not an executable environment.

Qualify ADI-built or approved partner environments; require actual tests rather than partner capability assumptions. Sandboxing, network allowlists, resource limits, secret isolation, per-episode state and cleanup are required design concerns. Simulated disruptions do not authorize live system disruption.

The supplied Praxis manuals describe recorded MCP replay that rejects unfamiliar arguments. Label this mode Recorded replay. It is not evidence of a stateful simulator. Dynamic actions, state changes, temporal events and alternative completion paths need separate Environment Studio contracts/tests. Do not count replay coverage defects as agent failures without the frozen protocol's explicit validity rules.

## 4. Lifecycle, interface and reward boundaries

Proposed lifecycle: Draft → Integration tests → Fidelity review → Approved for stated use → Active version; Blocked/Retired/Withdrawn retain history. Active means allowed for a declared purpose, not every workload. Pin versions to runs; changes cannot alter a running episode silently.

The conceptual runtime interface returns actor observations, observable action results, done/truncated/error status and allowed evidence references. Exact API/transport is not selected. Evaluation-hidden evidence uses a separate permission boundary. Seeded reset, recorded trace replay, fresh rerun and checkpoint resume are different capabilities; do not promise deterministic external-model responses.

Verifiers assess evidence. Rewards map approved verified milestones/final outcome to training signal. Evaluation scoring remains separately defined; optimizing the reward does not prove better evaluation quality. Check exploit cases, repeated credit, critical violations and grader unavailability. Expert reviews business meaning; researcher approves training-reward configuration independently of Admin spending approval.

## 5. Screens and handoffs

Task Studio: Production Briefs; Praxis/Partner Intake; Case Gap Ledger; Enhancement and Lab Requirements; Capability/Family Mapping; Research Constraints and Environment Binding; Optional Graph View; Variation/Coverage; Qualification Review; Source/Publish History. Link back to Praxis for its SME edits/content review; no duplicate workbench. Partner enhancement records preserve source and reviewer provenance.

Environment Studio: Environment Library; Interface/Tool Contract; Scenario Controls; Isolation/Fidelity Tests; Reward Evidence; Review/Versions. Hand off qualified task/environment/grader references to Training Packs or Evaluate, then Pack Release.

These are proposed screen responsibilities, not implemented or approved wireframes. No automatic task-to-graph converter or learned transition model is established.

## 6. Acceptance criteria

- F-TE01: Task authoring/conversion is absent from Data Preparation.
- F-TE02: The evaluated agent cannot access hidden solutions or future events unless explicitly part of the declared task observation.
- F-TE03: Reset isolates episodes; unintended state leakage blocks qualification.
- F-TE04: Planned perturbation, agent failure and infrastructure fault retain separate records.
- F-TE05: Invalid/ambiguous tasks and unsupported environments cannot be silently counted as model failures.
- F-TE06: Publishing a task/environment does not launch learning, assessment or deployment.
- F-TE07: A lab connects a supported policy interface without adopting an ADI model, TTM or training backend.
- F-TE08: A Praxis-accepted task may remain unqualified for a Frontier purpose without changing its source acceptance.
- F-TE09: Recorded replay and stateful simulation have distinct capability labels and qualification evidence.
- F-TE10: Task business-content corrections return to Praxis; Frontier preserves the original snapshot and successor lineage.

No environment, graph runtime or executable converter was created by this specification.
