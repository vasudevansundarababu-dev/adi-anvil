# Anvil Benchmark Factory Nightly Build Contract

**Purpose:** Autonomous nightly delivery of small, tested, demonstrable Anvil product increments\
**Target duration per run:** Approximately 2–3 focused hours\
**Source of truth:** The active Anvil repository and its existing architecture\
**Companion specifications:** `Anvil_Benchmark_Factory_Product_Technical_Spec_v1.0.md` and `Anvil_12_Week_Synthetic_Marketing_RL_Benchmark_Spec_v1.0.md`\

## 1. Standing Codex instruction

Use the following as the nightly job request:

```text
Advance the active Anvil repository by delivering exactly one complete, working,
demonstrable vertical increment from the Anvil Benchmark Factory specifications.

Begin by inspecting the repository, AGENTS.md and local instructions, current branch,
uncommitted work, recent relevant changes, tests, architecture, existing Objective,
approval, benchmark catalog, Suite, Protocol and Run Console implementations. Treat
the repository as the source of truth. Preserve existing user work and do not create a
parallel application, second catalog, second server, replacement schema, or conflicting
design system.

Select the first incomplete vertical slice in the ordered backlog. Before editing,
write a concise implementation contract containing stable requirement IDs, scope,
non-goals, acceptance criteria, affected areas and definition of done. Then implement
the feature, add or update tests, run repository-native lint/typecheck/tests/production
build, and exercise a runnable demo path. Fix issues caused by the increment.

Anvil is an RL Gym benchmark and evidence platform for frontier labs. It may invoke
models for baseline runs, trajectories, evaluation and verifier calibration, but it
must not implement model training, distilled models, weights, enterprise-agent
deployment, production campaign execution or customer-specific training.

Bodhium case studies are the priority real evaluation target and must be treated as
restricted partner evidence with explicit rights, privacy and access controls. ADI
Praxis task banks are separate SME-authored ADI assets. Synthetic fixtures, including
the 12-week marketing launch, are ADI synthetic and must never be labeled or implied
to be Bodhium-derived. Until approved Bodhium data is present, implement only the
intake, mapping, governance and rights-clear test path; do not fabricate Bodhium cases.

Design for at least 100,000 tasks using asynchronous jobs, bounded shards, durable
checkpoints, idempotent result commits, retries, rate and budget limits, and incremental
aggregation. Do not load a full run or all trajectories into memory or one UI response.

Match the existing Anvil UI. Required fields must show accessible mandatory indicators.
Every screen must expose sanitized, read-only contextual Anvil Help. Preserve existing
Objective → Approval → Tasks & Data → Benchmark Factory → Suite → Protocol → Run Console
navigation and behavior.

At the end, report:
1. implementation contract and requirement IDs completed;
2. exact repository paths changed;
3. migrations or configuration changes;
4. exact commands run and pass/fail counts;
5. production build result;
6. demo steps and screenshots when useful;
7. remaining blockers and risks;
8. commit-ready change summary;
9. precise next incomplete vertical slice.

Never claim implementation, scale, data availability, test success or build success
without direct evidence from the active repository and executed commands.
```

## 2. Ordered nightly backlog

Codex selects the first incomplete increment after inspecting repository truth. If an item already exists, it verifies its acceptance criteria and moves to the next incomplete item rather than rebuilding it.

### Night 1 — Task Profile and deterministic recommendation

**Requirements:** ANV-TP-001 through ANV-TP-005; ANV-REC-001 through ANV-REC-008\
**Outcome:** Select existing tasks, confirm a versioned TaskProfile, see ranked catalog benchmarks with reasons/gaps, and create an Eval Suite draft from a selection.\
**Demo:** Existing task → Task Profile → recommendations → add to Suite.\

### Night 2 — CSV and JSONL import to DatasetVersion

**Requirements:** ANV-ING-001, ANV-ING-008, ANV-ING-010; ANV-GOV-001, ANV-GOV-002\
**Outcome:** Upload, map, preview, validate, reject bad rows, detect duplicates, record provenance/checksum, and publish an immutable DatasetVersion.\
**Demo:** Import a small ADI synthetic fixture with one invalid and one duplicate row.\

### Night 3 — Durable background import jobs

**Requirements:** ANV-ING-008, ANV-ING-009\
**Outcome:** Job progress, checkpoint, pause/resume/cancel, failed-record retry, and error export using existing job infrastructure.\
**Demo:** Interrupt an import, resume it, and retry only failed records.\

### Night 4 — Provenance, PII and publication gates

**Requirements:** ANV-GOV-001 through ANV-GOV-008\
**Outcome:** Provenance badges, PII findings, quarantine, rights approval, publication blocking, audit events, and synthetic/ADI Praxis/Bodhium separation.\
**Demo:** Publication blocked by unresolved finding, then permitted after authorized disposition.\

### Night 5 — Benchmark manifest and catalog extension

**Requirements:** ANV-BM-001 through ANV-BM-008\
**Outcome:** Create/import a BenchmarkManifest, validate it, add a version to the existing catalog, and preserve immutable versions.\
**Demo:** Add a dataset benchmark and show readiness blockers.\

### Night 6 — Benchmark adapter and smoke validation

**Requirements:** Standard adapter contract; ANV-BM-004, ANV-BM-005\
**Outcome:** Implement repository-native dataset and rubric adapter paths plus three-case smoke validation.\
**Demo:** Validate, prepare, execute, score, normalize, and clean up three deterministic cases.\

### Night 7 — Create benchmark from uncovered requirements

**Requirements:** ANV-BM-007; ANV-REC-005, ANV-REC-006\
**Outcome:** Low coverage creates a prefilled benchmark draft from TaskProfile and selected tasks, requiring human confirmation before publication.\
**Demo:** Task bank with no full match → gaps → benchmark draft.\

### Night 8 — Suite Composer and gates

**Requirements:** ANV-SUITE-001 through ANV-SUITE-006\
**Outcome:** Compose benchmark versions, show capability coverage/overlap, configure weights and non-negotiable gates, and freeze a Suite version.\
**Demo:** Compose two benchmarks and show an uncovered capability and a safety gate.\

### Night 9 — Executable environment adapter and trajectories

**Requirements:** ANV-RUN-001, ANV-RUN-004, ANV-RUN-007; graph integrity requirements\
**Outcome:** Run a deterministic reset/step environment, record state deltas and tool results, reject invalid actions atomically, and inspect a trajectory.\
**Demo:** One success and one invalid-action path.\

### Night 10 — Protocol and distributed-run primitives

**Requirements:** ANV-RUN-001 through ANV-RUN-006\
**Outcome:** Freeze protocol versions, create bounded shards, enqueue work, enforce concurrency/rate/cost limits, checkpoint, pause/resume/cancel, and commit idempotently.\
**Demo:** Multi-shard local run with worker restart and no duplicate result.\

### Night 11 — Scale-aware Run Console

**Requirements:** ANV-RUN-008, ANV-RUN-009; UX Run Console requirements\
**Outcome:** Paginated/aggregated progress, shard and worker state, retry queue, cost, throughput, ETA, infrastructure failures, and task drill-down.\
**Demo:** Monitor an illustrative multi-shard run without fetching all executions.\

### Night 12 — Gap analysis and evidence lineage

**Requirements:** ANV-GAP-001 through ANV-GAP-006\
**Outcome:** Separate task/environment/verifier/infrastructure/model failures, compare trajectories, and trace aggregate scores to exact evidence.\
**Demo:** Success, failure, and recovery comparison with verifier reason codes.\

### Night 13 — Synthetic Task Generator

**Requirements:** ANV-TF-001 through ANV-TF-008; marketing benchmark generation requirements\
**Outcome:** Configure and asynchronously generate a deterministic 12-week marketing TaskBank with preview, validation, provenance, and review routing.\
**Demo:** Same template/version/seed generates identical task checksums twice.\

### Night 14 — Twelve-week Task Neural Graph

**Requirements:** Marketing benchmark state, observation, action, transition, constraint, event, and graph requirements\
**Outcome:** Inspect the 12-week graph, recovery edges, terminal states, attached verifiers, and environment preview.\
**Demo:** Step through a seed case including one recoverable rejection.\

### Night 15 — Twelve-week scoring and flagship run

**Requirements:** MKT-AC-001 through MKT-AC-012\
**Outcome:** Complete success, failure and recovery trajectories; score dimensions and gates; run two model configurations or deterministic test agents; compare gaps.\
**Demo:** Full flagship workflow through existing Run Console.\

### Night 16 — ADI Praxis review workflow integration

**Requirements:** ANV-TF-003 through ANV-TF-008\
**Outcome:** Author/reviewer states, structured review reasons, adjudication, agreement metrics, and immutable accepted TaskBank version.\
**Demo:** Draft → changes requested → resubmitted → approved → published.\

### Night 17 — Bodhium case-study intake readiness

**Requirements:** ANV-GOV requirements plus source mapping and benchmark-readiness reporting\
**Outcome:** Restricted intake template for task, inputs, expected outcome, scoring criteria, and known model results/failures; rights/privacy gate; no fabricated partner data.\
**Demo:** Rights-clear placeholder structure passes schema while publication stays blocked without approval.\

### Night 18 — Parquet and large-object ingestion

**Requirements:** ANV-ING-002, ANV-ING-006\
**Outcome:** Streaming/chunked Parquet and cloud-object import with continuation and checkpointing.\
**Demo:** Restartable large fixture import with bounded memory.\

### Night 19 — PDF, web, database and API connectors

**Requirements:** ANV-ING-003 through ANV-ING-007\
**Outcome:** Implement repository-standard connector interfaces and at least one rights-clear fixture per connector, with unavailable external dependencies mocked only at defined boundaries.\
**Demo:** Connector validation and provenance capture; no unapproved live scraping or credentials.\

### Night 20 — 100,000-task production hardening

**Requirements:** Scale acceptance and all NFR requirements\
**Outcome:** Non-billable 100,000-task load harness, bounded memory, failure injection, restart recovery, duplicate prevention, incremental aggregation, access tests, and production build.\
**Demo:** Scale report with exact environment, configuration, throughput, failures, recovery, memory, and limitations.

## 3. Rules for every increment

### 3.1 Scope control

- Complete one vertical slice; do not leave disconnected schemas or UI-only placeholders.
- Prefer the smallest end-to-end path that can be demonstrated.
- Keep migrations backward compatible where possible.
- Feature-flag unfinished production behavior.
- Preserve unrelated work and do not rewrite architecture without evidence.

### 3.2 Data safety

- Use only ADI synthetic fixtures in automated tests unless the repository already contains explicitly approved data.
- Never copy Bodhium source content into logs, snapshots, screenshots, prompts, or fixtures.
- Never invent Bodhium case studies or label synthetic cases as partner evidence.
- Do not transmit restricted content to an external model without explicit recorded authorization and configured policy.

### 3.3 Testing

Each increment includes:

- unit tests for new logic;
- integration test for the vertical path;
- regression coverage for affected existing behavior;
- negative tests for permissions, validation, and failure states;
- repository-native lint, typecheck, tests, and production build;
- repeatable demo fixture and commands.

Scale-related increments additionally record concurrency, task count, duration, throughput, memory, queue depth, retry count, duplicate count, and cost-model assumptions.

### 3.4 Reporting

The nightly report must distinguish:

- implemented and directly verified;
- implemented but not production-validated;
- specified only;
- blocked by unavailable data, credentials, approvals, infrastructure, or repository access.

No green status may be inferred from an unexecuted command.

## 4. First nightly implementation contract

### Increment

**ANV-BF-001 — Task Profile and Benchmark Recommendation**

### Scope

- Extend the current benchmark catalog model with matching metadata using existing migration conventions.
- Create TaskProfile from selected existing tasks.
- Add deterministic recommendation service and explanation.
- Add Task Profile and Recommendations states to the approved Anvil UI.
- Add selected benchmark version to an Eval Suite draft.
- Offer Create benchmark from gaps when no candidate clears the configured threshold.

### Non-goals

- No benchmark execution adapter.
- No 100,000-task queue.
- No advanced connector.
- No Bodhium content.
- No LLM-based semantic recommendation in the first version.

### Acceptance criteria

1. Same input profile and catalog versions return the same ordering and scores.
2. Hard-incompatible benchmarks are excluded with a visible reason.
3. Every recommendation includes total score, dimension scores, explanation, uncovered requirements, and benchmark version.
4. A selected recommendation creates or updates a Suite draft using existing flows.
5. Low coverage offers a prefilled benchmark draft without publishing it.
6. Required-field and accessibility behavior matches the approved UX.
7. Authorization is enforced server-side.
8. Unit, integration, regression, typecheck, lint, and production build pass.

### Definition of done

A permitted user can select existing tasks, confirm their TaskProfile, receive explainable deterministic benchmark recommendations, add one to a Suite draft, and see a create-new-benchmark path when coverage is insufficient, with all repository-native validation passing and a five-minute demo documented.
