# Frontier — Evaluate

Version: 0.3 · Review draft · 27 September 2026
Module: F06

## 1. Purpose and modes

Evaluate a **model plus its harness/tools/configuration** against a named research capability; establish valid baselines, inspect failures and test interventions. No prior ADI training, ADI model or learned TTM is required.

Modes: package/task/environment/grader qualification; diagnostic baseline; controlled intervention comparison; locked final assessment; independently measured external benchmark transfer. Enterprise production suitability, deployment approval and operational business monitoring are outside this module.

First-SKU profile: custom-suite diagnostics on 200 MBA-style business cases. Bodhium supplies partial inputs and ADI enhances for lab requirements. Use [SKU 01](13-BUSINESS-CASE-DIAGNOSTICS-SKU.md) for gap assessment, open-ended reference/rubric calibration, source-exposure controls and mode selection. Do not require a standard benchmark or simulator for static document-to-deliverable cases. Prior reported model failures are hypotheses/evidence to investigate, not a required new-study outcome.

Customer owns any weight optimization. Evaluate can use approved candidate endpoints/harnesses, an approved local runner or imported permitted customer results. No model weights or private traces must be uploaded to complete an aggregate-result workflow; missing evidence limits conclusions.

## 2. Roles and protocol

Proposed ownership: researcher configures/runs and investigates; expert reviews domain-dependent validity; designated assessment reviewer approves findings, preferably independent for locked tests where feasible. These roles and distinct-person requirements need assignment before live operation. Admin activation/paid-scope approval is separate; Sales cannot edit tests or verdicts.

Freeze EvaluationProtocol before launch: objective; population/slices; candidate and baseline identities; model requested/returned versions; harness/prompt/tools; task family/split; environment/grader; graph visibility; token/tool/time limits; repetitions; sampling/uncertainty method; primary metric/guardrails; exclusions/retries; intervention/comparator; exposure history; allowed data egress; cost authorization; intended report audience.

Free-planning tests cannot leak reference paths, hidden simulator truth or grading answers. Graph-assisted tests are a separately labeled condition. Mutable model aliases carry a reproducibility limitation.

## 3. Qualification before model scoring

- Task: coherent facts, feasible allowed actions, meaningful objective and reviewed references. Intentional impossibility has an expected abstention/escalation outcome; accidental impossibility is a defect.
- Environment: isolated reset, transitions, action permissions, injection handling, termination/truncation and no episode leakage.
- Grader: known pass/fail/exploit fixtures, expert calibration of learned judgments, disagreement and false-accept/reject evidence where available. Multiple judges are not independent truth by default.
- Coverage: dependency depth, state tracking, recovery and slices; distinguish families, instances, variants and repetitions.
- Integrity: rights, lineage, source/family near-duplicates, protected splits and no answers in prompts.
- Harness: correct tools, serialization, budgets and telemetry. Missing tools are not automatically foundation-model failures.

No universal agreement percentage, sample size or success threshold is selected. Contracted criteria and limitations must be visible; defects cannot simply be removed after seeing results.

## 4. Execution and validity

Draft → Protocol reviewed → Authorization pending → Ready → Queued → Running → Completed → Review pending → Reviewed.

Blocked, Failed operationally, Partial, Cancellation requested, Cancelled and Invalidated retain evidence. Completed is not a successful agent outcome. Configuration changes create a new version and affected approvals. Explicit authorized launch only; report generation is not an execution trigger.

Each episode separately records candidate outcome, expected perturbation, environment/tool/grader status, infrastructure failure, completeness and costs. Preserve retries rather than reporting only the last successful attempt. Predeclare handling of invalid/excluded/cancelled episodes.

Imported customer results pass schema/digest checks but stay **Customer-reported** until independently reproduced. Validation of a file is not reproduction of a study. Replay of recorded outputs is different from a fresh stochastic rerun.

## 5. Metrics and comparisons

| Measure | Required disclosure |
| --- | --- |
| Valid-attempt success | Successes / valid scored attempts, raw counts and exclusions |
| End-to-end completion | Successful completions / launched attempts, including operational/cancelled breakdown |
| Constraint adherence | Specific violations / assessed applicable attempts; unchecked is not passed |
| Recovery | Successful recoveries / attempts with the declared recoverable perturbation |
| Repeated reliability | Precisely defined per-task repeated-run measure; distinguish pass-at-k from all-k success |
| Efficiency | Tokens, calls, time and cost per attempt/success, with unknowns and estimates labeled |
| Grader quality | Reviewed-reference agreement/disagreement and false decisions where justified |
| Improvement | Matched candidate-minus-baseline with uncertainty, controls and regressions |
| Transfer | Separately measured held-out-family/domain or external-benchmark outcome |

Use prespecified paired/cluster-aware analysis where appropriate; variants and repeats are not independent tasks. Show uncertainty method, adequacy/limitations and relevant multiple-comparison handling. Do not create a silent composite intelligence score.

For model-adaptation claims hold harness/protocol stable and examine appropriate data/compute comparators. If model and harness change, describe a system-level intervention unless the effect is isolated. Reference-model results do not establish results on a private untested model.

## 6. Failure analysis

Attribution categories: candidate behavior; context/retrieval; harness/tool integration; task/environment; grader/reference; infrastructure/budget; mixed/unknown.

Finding records: actual event references, earliest observed divergence, downstream effects, evidence for/against, alternative explanations, uncertainty basis, reviewer disposition, proposed intervention and any tested outcome. Earliest visible error is not necessarily root cause; trace inspection does not reveal the model's internal mechanism.

Inspect successful and recovered trajectories as well as failures. Corrections are new annotations, not edited original events. Record only observable actions/results and exposed concise explanations—not hidden chain-of-thought. Missing events remain missing.

Praxis can provide human business judgment through its documented RL review-request/result interface. Send only permitted evidence with pinned run/task/source/grader references. Preserve original automated scores and imported human agreements/disagreements separately; a disagreement creates an adjudication item, not an automatic score change or learning trigger. Frontier owns scientific validity and the final assessment. See [Praxis integration](11-PRAXIS-FRONTIER-INTEGRATION-SPEC.md).

Praxis recorded replay rejects unrecorded arguments according to the manuals. Freeze how unsupported valid actions, invalid actions and fixture defects affect validity before scoring. Replay capability does not establish a stateful simulator or prove long-horizon recovery performance.

## 7. Improvement handoff and held-out discipline

Reviewed development findings can request tasks from Task Intelligence Studio, source/trajectory records from Data Preparation and assets from Training Packs. Other findings may require a harness, context, task or grader repair instead of model training.

Protected test content/traces cannot be nominated for learning export. Test feedback used for optimization loses untouched-test status for that study and requires fresh independent confirmation; rights restrictions persist. Checkpoint/candidate selection does not use the final test.

## 8. Screens and output

Objectives & Suites; Protocol & Baselines; Review & Run; Results & Reliability; Failure Analysis; Compare & Report Handoff.

Assessment contains frozen protocol, outcome counts, uncertainty, slice/regression evidence, failure findings, validity/limitations, costs, trace permissions and reviews. A diagnostic assessment can finish without intervention. A negative/inconclusive result remains a valid reportable outcome.

## 9. Acceptance criteria

- F-EV01: Run diagnostics without an ADI training job, model weights or learned navigator.
- F-EV02: Hidden solutions and privileged state cannot enter free-planning agent observations.
- F-EV03: Task/grader/infrastructure faults remain distinct from model failures.
- F-EV04: Repeats and retries preserve all attempts and do not inflate independent sample counts.
- F-EV05: Protocol changes invalidate unsupported direct comparisons/approval reuse.
- F-EV06: Protected test trajectories cannot enter Training Packs.
- F-EV07: Customer imports stay customer-reported; no fabricated missing traces.
- F-EV08: Findings distinguish observations, hypotheses and experimentally supported explanations.
- F-EV09: Changed model plus changed harness cannot produce an isolated training-gain claim.
- F-EV10: Completion starts neither weight training nor external publication.
- F-EV11: ADI/adapted suite outcomes cannot populate an official-comparable benchmark field.
- F-EV12: Reports retain uncertainty, invalid/excluded counts, costs and regressions.

No runner, evaluator or benchmark result is implemented. Role assignments, first protocols and thresholds remain review decisions.
