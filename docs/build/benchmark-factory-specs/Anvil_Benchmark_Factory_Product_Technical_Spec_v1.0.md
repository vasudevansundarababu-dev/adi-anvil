# Anvil Benchmark Factory Product and Technical Specification

**Version:** 1.0\
**Status:** Approved UX direction; implementation-ready after repository inspection\
**Product:** Anvil benchmark and evidence platform\
**Primary product boundary:** RL Gym for frontier-model evaluation\
**Scale target:** At least 100,000 versioned tasks in a benchmark run\

## 1. Purpose

Anvil Benchmark Factory enables a user to import task and source data, create or approve task banks, profile their domain and capability requirements, receive explainable benchmark recommendations, instantly register or create an executable benchmark, compose an evaluation suite, and run the suite at production scale.

The first commercial priority is benchmarking Bodhium case studies. Bodhium materials are treated as restricted partner evidence and must retain their original provenance, rights status, and access boundaries. ADI Praxis produces separate SME-authored task banks. Synthetic assets, including the 12-week marketing launch benchmark, are explicitly labeled ADI synthetic and are used for platform acceptance, learning, and regression testing.

Anvil does not train or deploy models. It may invoke model endpoints to generate baseline trajectories, evaluate model behavior, calibrate verifiers, and compare results. Model weights, distilled models, customer-specific training, enterprise-agent deployment, and production campaign operation are outside this specification.

## 2. Product decision

The approved workflow extends the existing Anvil product rather than creating a parallel application:

```text
Research Objective
  → Approval
  → Tasks and Data
  → Task Factory and Review
  → Task Profile
  → Benchmark Recommendation or Creation
  → Eval Suite
  → Protocol
  → Run Console
  → Gap and Evidence Report
```

The existing Objective, approval, Suite, Protocol, Run Console, benchmark catalog, authentication, design system, API conventions, storage abstractions, and repository structure remain the source of truth. Implementations must map this specification onto existing types and patterns.

## 3. Product principles

1. **Tasks determine benchmark selection.** Benchmark selection begins with domain, modality, task type, horizon, tools, environment, constraints, expected artifact, and evaluation objective.
2. **Benchmarks are executable and versioned.** A benchmark is more than a dataset. It includes tasks, dataset versions, runner/environment, evaluators, metrics, success rules, and evidence lineage.
3. **Provenance never collapses.** Bodhium, ADI Praxis, public, third-party licensed, and ADI synthetic sources retain distinct ownership and access labels at record and artifact level.
4. **Task quality and model performance are separate.** Anvil reports whether a task is valid and whether a model performs it successfully as different score families.
5. **Dynamic environments are first-class.** Long-horizon RL Gym tasks expose state, observations, typed actions, transition rules, tools, constraints, termination, rewards, and reproducible reset.
6. **Verifiers are transparent.** Scores include verifier identity, version, reason code, evidence references, thresholds, and disagreement status.
7. **Production scale is asynchronous.** No UI request or API worker may attempt to process 100,000 tasks synchronously or hold a complete run in memory.
8. **Human review is targeted.** Programmatic validation covers all records; SMEs review seed tasks, high-risk items, disagreement cases, and statistically representative samples.
9. **The product explains its recommendation.** Users see why a benchmark matches and what remains uncovered.
10. **A benchmark can be added without a product release.** Compatible manifests and adapters are registered through a validated extension contract.

## 4. Users and permissions

| Role | Primary permissions |
|---|---|
| Research Lead | Create objectives, approve task profiles, select benchmarks, approve releases |
| Benchmark Engineer | Create manifests, adapters, environments, verifiers, suites, protocols |
| Data Steward | Configure imports, mappings, rights, PII policy, dataset publication |
| ADI Praxis Author | Draft SME tasks, rubrics, edge cases, state/action definitions |
| ADI Praxis Reviewer | Review, reject, request changes, adjudicate task quality |
| Run Operator | Validate protocols, start/pause/resume/cancel runs, retry infrastructure failures |
| Auditor | Read immutable versions, evidence, scores, audit events, provenance |
| Viewer | Read approved assets and permitted run results |

Authorization must be enforced server-side. Restricted Bodhium assets require explicit project membership and may not be exported, shared, or used for training without recorded authorization.

## 5. Core domain model

### 5.1 Entities

- **ResearchObjective:** The approved model capability or business-workflow question.
- **SourceAsset:** Original file, URL snapshot, database extract, API response batch, or SME input.
- **ImportJob:** Durable asynchronous ingestion process with progress and checkpoints.
- **DatasetVersion:** Immutable, checksummed publication of normalized records.
- **TaskBank:** Versioned collection of reviewed TaskSpecs with declared coverage.
- **TaskSpec:** Goal, inputs, expected artifacts, states, tools, constraints, terminal conditions, provenance, difficulty, and evaluation requirements.
- **TaskGraph:** States, legal transitions, recovery paths, termination conditions, tools, constraints, and verifier attachment points.
- **TaskProfile:** Normalized representation of domain, modality, capability, interaction, environment, risk, language, horizon, and evaluation needs.
- **BenchmarkDefinition:** Stable benchmark identity and ownership metadata.
- **BenchmarkVersion:** Immutable manifest, task selection, runner, evaluator set, metrics, and release evidence.
- **BenchmarkAdapter:** Code or configuration implementing the standard benchmark lifecycle.
- **EvalSuite:** One or more benchmark versions with coverage, weights, gates, normalization, and sampling rules.
- **Protocol:** Frozen execution configuration: models, seeds, concurrency, retries, limits, budget, and environment versions.
- **Run:** Top-level execution lifecycle and frozen inputs.
- **RunShard:** Bounded task partition used for distributed scheduling and checkpointing.
- **TaskExecution:** One model-task attempt and its status.
- **Trajectory:** Ordered observations, actions, tool results, state deltas, verifier results, costs, errors, and terminal outcome.
- **VerifierResult:** Versioned decision with reason codes and evidence.
- **Score:** Raw and normalized metric values with aggregation lineage.
- **EvidenceArtifact:** Input, output, trace, generated artifact, or adjudication record supporting a score.
- **AuditEvent:** Immutable actor/action/target/time/outcome record.

### 5.2 Required relationships

```text
Objective → TaskBank → TaskSpec → TaskGraph
TaskSpec → SourceAsset and DatasetVersion
TaskProfile → BenchmarkRecommendation
BenchmarkDefinition → BenchmarkVersion → BenchmarkAdapter
EvalSuite → BenchmarkVersion
Protocol → EvalSuite + Models + Runtime Policy
Run → RunShard → TaskExecution → Trajectory
Trajectory → VerifierResult → Score → EvidenceArtifact
Every released score → exact task, dataset, benchmark, protocol, model and verifier versions
```

Graph validation must detect unreachable terminals, actions without constraints or evaluation, cycles without retry/termination policy, orphan verifiers, missing provenance, and scores that cannot be traced to evidence.

## 6. Functional requirements

### 6.1 Tasks and data ingestion

- **ANV-ING-001:** Import CSV and JSONL with column mapping, preview, row-level validation, duplicate detection, checksum, and provenance.
- **ANV-ING-002:** Import Parquet without expanding the full file in application memory.
- **ANV-ING-003:** Import PDF with text extraction, OCR when needed, page references, table extraction status, and source-page lineage.
- **ANV-ING-004:** Import permitted web content as timestamped snapshots with URL, retrieval time, content hash, and robots/license metadata where available.
- **ANV-ING-005:** Import from configured databases using read-only credentials, bounded queries, incremental cursors, and schema capture.
- **ANV-ING-006:** Import from cloud buckets using prefixes, object metadata, checksums, continuation tokens, and resumable processing.
- **ANV-ING-007:** Import from APIs using credential references, pagination, rate limits, checkpoints, and response-schema validation.
- **ANV-ING-008:** All imports execute as durable jobs with queued, running, paused, completed, completed-with-errors, failed, cancelled, and quarantined states.
- **ANV-ING-009:** Operators can retry only failed records, resume from the last durable checkpoint, and export an error report.
- **ANV-ING-010:** Publishing produces an immutable DatasetVersion; corrections create a new version.

### 6.2 Privacy, rights, and provenance

- **ANV-GOV-001:** Every source and derived record has a provenance class: `bodhium_restricted`, `adi_praxis_sme`, `adi_synthetic`, `public_permitted`, or `third_party_licensed`.
- **ANV-GOV-002:** Derived tasks preserve source-record references and may not overwrite source ownership.
- **ANV-GOV-003:** PII detection produces finding type, confidence, location, policy action, reviewer, and disposition.
- **ANV-GOV-004:** Policies support mask, redact, tokenize, quarantine, reject, and allow-with-approval.
- **ANV-GOV-005:** Dataset, task-bank, benchmark, and export publication is blocked by unresolved rights, PII, or licensing findings.
- **ANV-GOV-006:** Synthetic records contain generator version, seed, generated timestamp, checksum, and explicit synthetic label.
- **ANV-GOV-007:** The UI and API must never describe synthetic or ADI Praxis assets as Bodhium-derived.
- **ANV-GOV-008:** Every privileged read, export, approval, run, and deletion is audited.

### 6.3 Task Factory and ADI Praxis workflow

- **ANV-TF-001:** Create tasks manually, from approved templates, from imported records, or by deterministic/model-assisted augmentation.
- **ANV-TF-002:** Generated drafts remain non-published until validation and required review complete.
- **ANV-TF-003:** Task drafts include domain, modality, task family, goal, inputs, expected deliverable, states, actions, tools, constraints, termination, difficulty, rubric, provenance, and leakage risk.
- **ANV-TF-004:** Authors can create positive, failure, adversarial, counterfactual, and recovery variants.
- **ANV-TF-005:** Similarity checks flag likely duplicates without automatically deleting them.
- **ANV-TF-006:** Review supports approve, reject, changes requested, adjudication required, and superseded.
- **ANV-TF-007:** Bulk generation is deterministic when the same template, source version, generator version, and seed are used.
- **ANV-TF-008:** Quality reporting separates schema validity, SME acceptance, verifier coverage, graph integrity, novelty, and provenance completeness.

### 6.4 Task profiling

- **ANV-TP-001:** Generate a TaskProfile from one task, selected tasks, or a TaskBank version.
- **ANV-TP-002:** Required dimensions are domain, subdomain, modality, task type, agent type, horizon, interaction model, environment, tools, capabilities, output artifact, language/locale, risk, and evaluation target.
- **ANV-TP-003:** Inferred dimensions show confidence and evidence; users must confirm low-confidence required fields.
- **ANV-TP-004:** TaskProfile versions are immutable after use in a released benchmark recommendation.
- **ANV-TP-005:** The profile reports internal heterogeneity and recommends segmentation when one task bank contains incompatible task populations.

### 6.5 Benchmark recommendation

- **ANV-REC-001:** Recommend benchmark versions from the existing catalog using hard compatibility filters followed by explainable ranking.
- **ANV-REC-002:** Hard filters include runnable model interface, input/output schema, modality, environment availability, license, access, and data policy.
- **ANV-REC-003:** Initial deterministic score:

```text
20% domain
20% modality
20% task type
15% capability
10% interaction/horizon
10% evaluator compatibility
 5% constraints, license, and operational fit
```

- **ANV-REC-004:** Each recommendation shows total score, dimension scores, reasons, unsupported requirements, estimated task coverage, runtime, and cost range.
- **ANV-REC-005:** A configurable threshold determines whether the system recommends direct use, composition, extension, or creation of a new benchmark.
- **ANV-REC-006:** Composite recommendation maximizes required capability coverage while minimizing duplicate coverage, cost, and incompatible scoring.
- **ANV-REC-007:** Recommendation output is deterministic for the same TaskProfile, catalog versions, policy, and weights.
- **ANV-REC-008:** Users can override a recommendation only with a recorded reason.

### 6.6 Instant benchmark creation and registration

- **ANV-BM-001:** Add a benchmark from an existing task bank, a manifest/package, a permitted repository/URL, or an external runner adapter.
- **ANV-BM-002:** Adding a benchmark extends the existing catalog; it must not create a second registry.
- **ANV-BM-003:** Every benchmark has stable ID, semantic version, owner, purpose, domains, modalities, capabilities, task schema, dataset versions, runner, environment, evaluators, metrics, normalization, success rules, access, license, provenance, runtime limits, and example case.
- **ANV-BM-004:** Supported execution classes are dataset, rubric, executable environment, and external runner.
- **ANV-BM-005:** A benchmark becomes Ready only after manifest validation, dependency validation, dataset access validation, evaluator validation, and three successful smoke cases.
- **ANV-BM-006:** Publishing freezes the manifest and referenced versions. Changes create a new benchmark version.
- **ANV-BM-007:** A benchmark created from uncovered requirements is prepopulated from TaskProfile and selected tasks, but requires human approval.
- **ANV-BM-008:** Benchmark deprecation preserves historical run reproducibility.

### 6.7 Standard adapter contract

Every runnable adapter must support the repository-equivalent of:

```text
metadata()
validate(context)
prepare(dataset_version, protocol)
reset(task, seed)
execute(task, model, runtime_context)
capture_trajectory()
score(trajectory, artifacts)
normalize(raw_scores)
cleanup()
```

Adapters must be sandboxed according to existing platform policy, receive secrets by reference, enforce timeouts and resource limits, emit structured events, and be idempotent for the same execution key.

### 6.8 Suite composition

- **ANV-SUITE-001:** Compose one or more benchmark versions into a Suite.
- **ANV-SUITE-002:** Display coverage by domain, modality, capability, task family, difficulty, risk, language, and environment.
- **ANV-SUITE-003:** Detect overlapping tasks and metrics.
- **ANV-SUITE-004:** Support weighted metrics and non-negotiable gates. Critical safety, policy, privacy, or authorization failure cannot be hidden by a high aggregate score.
- **ANV-SUITE-005:** Sampling policies include all tasks, stratified, fixed-size deterministic sample, failure replay, and incremental regression.
- **ANV-SUITE-006:** Normalization retains raw scores and transformation details.

### 6.9 Protocol and execution

- **ANV-RUN-001:** A Protocol pins Suite, benchmark, task-bank, dataset, environment, verifier, model, prompt/scaffold, seed, runtime, and policy versions.
- **ANV-RUN-002:** Runs are asynchronous and partitioned into bounded shards.
- **ANV-RUN-003:** The scheduler supports priority, concurrency, model rate limits, cost ceiling, maximum wall time, pause, resume, cancel, retry, and stop conditions.
- **ANV-RUN-004:** Each task execution has a deterministic idempotency key and may commit at most one canonical result per attempt.
- **ANV-RUN-005:** Infrastructure retries are separated from model/task failures and do not alter model-performance scores.
- **ANV-RUN-006:** The system checkpoints shard progress and can recover after worker or orchestrator restart.
- **ANV-RUN-007:** Every step captures observation reference, action, tool call, tool result, state delta, verifier decision, latency, tokens/cost, error, and terminal outcome.
- **ANV-RUN-008:** Run Console supports aggregate progress and drill-down without loading every task execution.
- **ANV-RUN-009:** Results can be compared across models and benchmark versions only when comparability checks pass; otherwise the UI explains the mismatch.

### 6.10 Gap analysis and evidence

- **ANV-GAP-001:** Group failures by task family, capability, state, action, tool, constraint, verifier, modality, domain, and model.
- **ANV-GAP-002:** Distinguish task defects, environment defects, evaluator disagreement, infrastructure failure, and model failure.
- **ANV-GAP-003:** Support success, failure, and recovery trajectory comparison.
- **ANV-GAP-004:** Every aggregate score links to task executions, trajectories, verifier decisions, and source evidence.
- **ANV-GAP-005:** Exported evidence respects source access and redaction policy.
- **ANV-GAP-006:** The platform may recommend missing task categories or benchmark coverage; it must not claim that a synthetic reward equals real business impact.

## 7. Benchmark manifest minimum contract

```yaml
schema_version: anvil.benchmark/v1
benchmark_id: string
version: semver
name: string
owner:
  organization: string
  contact_ref: string
purpose: string
domains: [string]
modalities: [text|web|audio|voice|image|video|multimodal]
task_types: [string]
capabilities: [string]
interaction_model: string
horizon: string
input_schema_ref: string
output_schema_ref: string
task_bank_versions: [string]
dataset_versions: [string]
runner:
  adapter_type: dataset|rubric|environment|external
  adapter_ref: string
  timeout_seconds: integer
environment_ref: string|null
evaluators:
  - verifier_ref: string
    required: boolean
metrics:
  - metric_id: string
    direction: maximize|minimize
    normalization_ref: string
gates: [object]
sampling_policy: object
runtime_requirements: object
license: object
provenance_policy: object
access_policy: object
example_case_ref: string
```

Unknown fields must be preserved for forward compatibility where safe. Unsupported schema versions fail clearly rather than being silently coerced.

## 8. Production architecture for 100,000 tasks

### 8.1 Logical components

- Existing Anvil API and UI.
- Metadata database for versioned entities and operational state.
- Object storage for source files, datasets, artifacts, and trajectories.
- Durable job queue for imports, generation, validation, execution, and aggregation.
- Run orchestrator that creates shards and enforces limits.
- Horizontally scalable stateless workers grouped by adapter/runtime capability.
- Event stream or append-only event table for run progress and audit.
- Score aggregation workers that operate incrementally.
- Observability stack for metrics, logs, traces, alerts, and cost.

Implement with the repository's existing technologies. Do not introduce a new database, queue, service boundary, or framework unless repository inspection proves the existing architecture cannot meet the requirements and the change is separately approved.

### 8.2 Partitioning

- Default shard size: configurable, initially 100–1,000 tasks depending on environment weight.
- Partition keys: run, benchmark version, model, task-family stratum, and shard number.
- Heavy executable environments may use smaller shards than dataset benchmarks.
- Shard creation is streaming and must not require materializing 100,000 payloads in application memory.
- Task bodies and artifacts are referenced by immutable IDs rather than copied into queue messages.

### 8.3 Delivery and consistency

- Queue delivery may be at least once.
- Result commits are idempotent and unique on execution key plus attempt.
- Progress is derived from committed task states, not untrusted worker counters.
- Cancelling prevents new dispatch and allows in-flight work to terminate or reach a safe checkpoint.
- Pausing preserves committed work and queue position.
- Retrying an infrastructure failure creates a new attempt linked to the original; model failure is not automatically retried unless the Protocol explicitly requests repeated trials.

### 8.4 Scale acceptance

Before GA, a non-billable load harness must demonstrate:

1. Creation and scheduling of 100,000 lightweight deterministic tasks.
2. Bounded memory in API, orchestrator, and workers.
3. Pause, resume, cancellation, worker restart, and orchestrator restart.
4. No duplicate canonical results under redelivery.
5. Incremental progress and aggregation.
6. Export and drill-down without full-run memory loading.
7. Budget and rate-limit enforcement.
8. Complete evidence lineage for sampled results.

## 9. Nonfunctional requirements

- **ANV-NFR-001:** Metadata read operations target p95 below 2 seconds under the tested production profile.
- **ANV-NFR-002:** Deterministic benchmark recommendation targets p95 below 3 seconds for the supported catalog size.
- **ANV-NFR-003:** Import/run creation acknowledges asynchronously; it does not wait for processing completion.
- **ANV-NFR-004:** No loss of committed results after process restart.
- **ANV-NFR-005:** All state transitions are auditable and timestamped.
- **ANV-NFR-006:** Secrets never appear in manifests, task payloads, logs, trajectories, exports, or help context.
- **ANV-NFR-007:** Tenant/project boundaries are enforced in storage queries, object paths, queues, and exports.
- **ANV-NFR-008:** Published artifacts are immutable and reproducible from pinned versions where external services remain available.
- **ANV-NFR-009:** Accessibility meets existing product standards; required fields are indicated visually and programmatically, errors are associated with fields, and keyboard workflows are supported.
- **ANV-NFR-010:** Contextual Anvil Help receives only sanitized screen metadata and cannot modify configuration or start runs.

## 10. UX specification

### 10.1 Navigation

Preserve the existing Anvil shell and add or extend:

```text
Objectives
Tasks & Data
Benchmark Factory
Suites
Protocols
Run Console
```

### 10.2 Tasks and Data screen

Shows source assets, provenance, readiness, latest DatasetVersion, import jobs, progress, failures, quarantine, and TaskBank routing. Primary action is **Import source**. The import wizard requires source type, source name, provenance class, rights basis, source configuration/file, and PII policy.

### 10.3 Synthetic Task Generator screen

Allows selection of an approved template such as **12-Week Product Launch**, scenario count, domain/industry, locale, modalities, difficulty distribution, variability controls, generator version, seed policy, source evidence, and review plan. It previews sample tasks before creating an asynchronous generation job.

### 10.4 Task Graph and Environment Preview

Displays states, legal actions, tools, constraints, recovery edges, terminal outcomes, attached verifiers, and a step-through deterministic preview. Users can compare success, failure, and recovery trajectories before publishing a TaskBank.

### 10.5 Benchmark Factory

Contains three stages:

1. **Task Profile:** required fields, inferred fields, confidence, source coverage, and blockers.
2. **Recommendations:** ranked benchmark versions, fit explanation, gaps, cost/runtime, and add-to-suite.
3. **Add Benchmark:** create from tasks, import manifest/package, or register adapter; show readiness checks and smoke tests.

### 10.6 Suite Composer

Shows selected benchmark versions, weights, mandatory gates, duplicate coverage, missing requirements, sampling policy, normalized score plan, and estimated execution cost.

### 10.7 Protocol

Shows pinned versions, models, task count, shard size, concurrency, retries, timeouts, seeds, checkpoints, rate limits, budget ceiling, and preflight blockers.

### 10.8 Run Console

Shows total, queued, running, completed, retrying, failed, cancelled, and adjudication-required counts; throughput; workers; spend; ETA; shard progress; infrastructure-error rate; failure taxonomy; model comparison; and event timeline. Every aggregate supports drill-down.

### 10.9 Mandatory UI behavior

- Required fields show `*` and an accessible required state.
- Publish and run actions remain disabled with explicit blocker reasons.
- Bodhium, ADI Praxis, and synthetic badges remain visible wherever evidence is displayed.
- Empty states provide a direct next action.
- Destructive actions require confirmation and show scope.
- Anvil Help is present on every screen, read-only, contextual, and sanitized.

## 11. API and event behavior

Map routes to repository conventions. Required service capabilities are:

- create/read/list import jobs and retry/resume/cancel them;
- create/read/publish DatasetVersions and TaskBanks;
- generate/confirm TaskProfiles;
- request/read BenchmarkRecommendations;
- create/validate/publish BenchmarkVersions;
- validate adapters and run smoke cases;
- create/read/publish Suites and Protocols;
- create/pause/resume/cancel Runs;
- stream or poll progress events;
- query executions, trajectories, verifiers, scores, gaps, and evidence;
- export permitted evidence.

Long operations return an operation/run ID immediately. Events use stable types, schema versions, correlation IDs, actor IDs, entity IDs, and timestamps.

## 12. Validation and testing

### 12.1 Unit tests

- schema and manifest validation;
- recommendation scoring and explanations;
- provenance propagation;
- PII policy decisions;
- state machines;
- idempotency keys;
- score normalization and gates;
- graph integrity;
- deterministic generators and environments.

### 12.2 Integration tests

- import to DatasetVersion;
- TaskBank generation and approval;
- TaskProfile to recommendation;
- benchmark manifest to smoke run;
- Suite and Protocol creation;
- distributed execution and aggregation;
- restart, retry, pause, resume, cancel;
- evidence and audit lineage;
- access boundaries and export policy.

### 12.3 End-to-end tests

1. Synthetic 12-week marketing launch from generation through comparison.
2. Bodhium intake shell using rights-cleared sample records only until approved source data is available.
3. ADI Praxis SME task review and publication.
4. 100,000-task non-billable scale harness.

### 12.4 Release gates

- repository lint, format, typecheck, tests, and production build pass;
- migrations have forward and rollback validation;
- no critical security findings;
- no unresolved provenance or PII defects;
- accessibility checks pass;
- three benchmark smoke cases replay identically twice;
- scale harness meets acceptance criteria;
- UX matches the approved Anvil design and does not create a second shell.

## 13. Definition of done

The feature is complete when a permitted user can:

1. Import or generate a versioned TaskBank.
2. Confirm its TaskProfile.
3. Receive explainable benchmark recommendations.
4. Select, compose, extend, or create a benchmark.
5. Validate and publish a BenchmarkVersion.
6. Create a Suite and Protocol.
7. Execute and recover a 100,000-task run without duplicate canonical results.
8. Inspect every task trajectory, verifier result, score, and source lineage.
9. Compare models and identify capability gaps.
10. Keep Bodhium, ADI Praxis, and synthetic assets correctly separated.

## 14. Explicit exclusions

- Model training, fine-tuning, distillation, weights, or training recipes.
- Enterprise-agent runtime or deployment control plane.
- Real campaign execution or claims of causal commercial lift.
- Unapproved external sharing of Bodhium evidence.
- A second benchmark catalog, server, database, design system, or standalone UI.
- Treating LLM-judge output as unquestioned ground truth.
- Loading 100,000 tasks or complete trajectories into a single UI response or process memory.

## 15. Initial implementation priority

The first repository increment is **ANV-BF-001 Task-to-Benchmark Recommendation**:

1. inspect and extend the current benchmark-catalog metadata;
2. create a versioned TaskProfile using existing task types;
3. implement deterministic ranking and explanation;
4. add approved Task Profile and Recommendations UX inside Anvil;
5. allow a selected benchmark version to populate an Eval Suite draft;
6. offer **Create benchmark from gaps** when coverage is insufficient;
7. add tests and run all repository-native validation/build commands.

This increment must not invent the 100,000-task execution system prematurely; it establishes the product contract that later execution increments consume.
