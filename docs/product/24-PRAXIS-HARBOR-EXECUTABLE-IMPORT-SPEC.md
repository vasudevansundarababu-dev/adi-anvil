# Praxis → executable Harbor import

Version: 1.0 · Date: 1 November 2026

Status: consolidated product/design specification. Functional decisions below were
confirmed in chat. Technical mechanisms are the proposed implementation contract.
This document is not an implementation or deployment claim. The user requested a final
specification before implementation; prior nightly authority does not launch this new
code-generation, tool-agent or notebook-runtime increment.

Reference: user-supplied `harbor_task_import_specification.md`. The user's subsequent
decisions supersede its Dockerfile-build, human-approval and training assumptions.

## 1. Outcome and agreed scope

An imported Praxis task becomes a reproducible, executable Harbor package: agent
instructions, inputs, working tool bindings, generated Python verifiers, runtime
guardrails, rubric scoring, validation fixtures and a bound supplied Docker image.
Import succeeds only when required automated checks establish that the package can
execute and grade its declared test cases. A JSON preview or existing container alone
is not executable-task readiness.
Ready means ready for testing under this contract, not human-certified business correctness.

Confirmed decisions:

| Area | Decision |
| --- | --- |
| Framework | Harbor only in this increment; an adapter boundary permits later frameworks. |
| Source rules | Praxis currently supplies written descriptions. A generation model translates applicable descriptions into executable definitions/code. |
| Constraints | Both runtime guardrails and final-output checks. |
| Environment | Supplied Docker image. Environment generation and tool-implementation design are deferred. |
| Environment validation | Verify required tools/MCP servers exist, start and expose compatible interfaces; perform safe test calls. |
| Candidate | Multi-step agent able to call validated tools and write allowed output files, bounded by steps, time, output limits and budget. |
| Generated test cases | Generate known-good and known-bad cases, with their declared expected scores/violations. |
| Generation model | One standard configured model for the entire Anvil installation, independent of evaluation models. |
| Generation budget | Admin-configured default cap, copied to one import ledger covering initial generation and every regeneration. |
| Users | Admin and RL Engineer; both can inspect, edit, regenerate, test and save permitted project artifacts. |
| Notebook editing | Google Colab preferred; JupyterLab also supported as an alternative. |
| Save semantics | Edits create a new draft version and automatically rerun validation; existing runnable versions/runs are preserved. |
| Testing readiness | No human approval or Mark ready ceremony in this increment. Required automated validation passing makes the version Ready. Human approval can be added later. |

Generation settings authorize configured import-generation operations within their cap;
they do not grant evaluation spending authority. Existing authentication, project/data
rights, private-reference isolation, exact version binding and spending reservation remain.
The specification grants no actual paid-call, notebook provisioning or GCP deployment action.

## 2. Roles and model configuration

Models has two clearly separated areas:

1. **Standard import generation model — installation-wide**, editable by an Admin with
   installation-settings access. Provider, exact model version, centrally scoped saved
   credential and default whole-import cap. There is no default numerical cap or invented
   model selection. Missing configuration blocks generation with a setup explanation.
2. **Evaluation models — current project**, preserving existing model/key profiles and
   the task Run selection. These models execute tasks, not generate their grading code.

Installation-settings access is an authorization scope for the existing Admin role, not
a third role. Implementation must explicitly map that scope; a project grant must not
silently promote someone to global credential administration. Project users can invoke
the configured generation service under policy without receiving its secret value.
Existing project credentials are not automatically copied to the installation store.

Each import freezes the generation configuration version, provider/model, credential
version, prompt/generator version and cap. Later default-setting changes do not silently
rebind in-progress imports or reset their spending. Revocation/unavailability pauses work;
any authorized rebind is explicit, versioned and uses the same cumulative import ledger.
Task content, requests and generated artifacts remain project-scoped despite the shared
generation model. Notebook, candidate and tool containers never receive provider keys.

## 3. Import inputs and executable contract

UI accepts a Praxis JSON export plus referenced input assets, or a supported bundle
containing those assets. A bundle is a delivery envelope, not permission to execute its
scripts. Raw bytes/checksums and source lineage are retained. Imported code/assets remain
subject to scanning and isolation qualification before execution.

Required logical inputs:

- Task identity/version, objective, agent-visible instructions and output/deliverable contract.
- Rubric descriptions, weights, thresholds, expected business outcomes and source evidence.
- Constraint descriptions with severity, applicable phase and prohibited/required behavior.
- Tool/MCP declarations, argument/result schemas, startup/connection information and dependencies.
- Input assets with visibility and intended mount paths.
- Supplied environment image reference and deterministic initialization/reset contract.
- Task horizon and resource bounds: steps, timeout, early completion and output limits.
- Provenance and the existing rights/processing declarations applicable to supplied material.

When required facts are absent, generation must surface **Needs clarification** rather
than invent expected identities, accounting rules, tool behavior or pass conditions.
Subjective criteria without an executable scoring definition are not silently replaced
with an unconfigured paid model judge. Tool schema definitions alone do not implement tools.
Missing tool implementations block environment validation; automatic tool/environment
implementation generation is outside this agreed increment.

Versions are stored as strings with original source values preserved. The example schema
URLs and CLI commands in the supplied reference are proposals until verified against the
pinned Harbor adapter; Anvil must not present invented commands as installed Harbor APIs.

## 4. Compilation and generation

The generation service produces a candidate artifact set; Anvil validates and packages
it through a deterministic Harbor adapter. The language model does not dispatch code
on the API host, choose unbounded dependencies, rewrite the image or grant privileges.

Logical artifact layout (adapter emits the exact files required by the pinned Harbor version):

```text
task-version/
  source/                         immutable source/export and asset manifest
  public/
    instruction.md               agent-visible task instructions
    inputs/                      declared actor-visible assets
    tools.json                   validated tool interfaces, without server secrets
    output.schema.json           expected deliverable structure
  evaluation/                    excluded from candidate environment
    verifiers/*.py               generated final-output checks
    constraints/*.py             generated guardrail/final-check implementations
    fixtures/good/               known-good cases and declared expectations
    fixtures/bad/                known-bad/adversarial cases and expectations
    rubric.json                  scoring definitions and verifier mappings
    traceability.json            requirement → rule → code → fixture links
  review/
    review.ipynb                 notebook source and safe review fixtures
    generation-report.json       assumptions, unresolved items, code provenance
  validation/
    environment-report.json
    tool-probe-report.json
    verifier-test-report.json
    package-smoke-report.json
  package-manifest.json           hashes, versions, image digest and execution bindings
```

This is Anvil's logical storage layout, not a claim that Harbor consumes these folder
names directly. The adapter produces Harbor task configuration, instructions, verifier
entry point/reward files and the required environment reference from this artifact set.

Every generated rule records: source requirement ID, readable interpretation, check type,
input/output path or observed event, parameters, expected result, severity, scoring effect
and tests. Examples include JSON/file assertions, numeric bounds/tolerances, required
evidence, state transitions and prohibited tool attempts. Arbitrary natural-language
criteria cannot be marked covered merely because a Python file exists.

Constraints declare enforcement phase:

- **Runtime:** validate/deny a tool action before its side effect, record the attempted
  action and enforce any declared stop/hard-fail policy.
- **Final:** inspect permitted outputs and final environment state after completion.
- **Both:** enforce during execution and verify corresponding final invariants.

The candidate cannot change guardrail policy or grading code. Final graders run separately
against a captured workspace with controlled access. Private expected answers, fixtures
and executable evaluation bindings are not included in the candidate prompt/image.

## 5. Automated readiness pipeline

| Stage | Required work | Failure shown to user |
| --- | --- | --- |
| Validate source | Schema, identities, asset hashes/visibility, safe paths, output contract and supported rule coverage. | Exact field/file/rule needing correction. |
| Generate | Produce verifiers, constraints, scoring mappings, fixtures and notebook under the frozen model/cap. | Generation failure, refusal, clarification or budget state. |
| Inspect code | Parse/compile, dependency allowlist, entry-point checks, prohibited operation/static scanning and artifact isolation. | Specific file and actionable diagnostic. |
| Validate environment | Resolve supplied image digest, enforce resources/network/mount policy and verify initialization/reset. | Image/dependency/reset/isolation failure. |
| Validate tools | Executable/module availability, MCP startup/handshake, advertised tool/schema compatibility and safe probes. | Tool-by-tool result, missing implementation or incompatible schema. |
| Validate grading | Good, bad, empty-output and hard-failure cases; scoring math, constraint behavior and deterministic replay. | Expected versus actual outcomes by rule/case. |
| Package smoke test | Exercise pinned Harbor adapter without paid candidate inference; verify output collection, grader isolation and reports. | Runner/package infrastructure error, not a fabricated task score. |
| Ready | Freeze all passing artifact/image/config hashes and publish a runnable version. | No manual approval gate in testing mode. |

Safe probes run only in disposable, resettable test instances with synthetic inputs and
no production side effects. Mutating probes require a defined reversible test behavior;
otherwise the tool is **Not safely testable** and cannot pass the required probe gate.
Reset and initial-state fingerprints must match before independent probes and trials.

Good/bad fixtures and verifier code generated by the same model are software consistency
checks, not independent proof of business correctness. Their assumptions and coverage
remain inspectable. The empty baseline must meet the task's declared expected result;
for the reference scenarios this is zero, with no fixture outputs pre-seeded into the
candidate workspace. A verifier crash is a validation error, not a valid zero score.

Scoring contract: positive weights normalize explicitly; dense awards cannot be repeatedly
earned beyond their criterion cap; terminal awards and penalties are separately recorded;
hard failures force the declared outcome. Report raw components, final bounded reward,
pass threshold and guardrail outcomes. Unsupported scoring semantics block readiness.

States: **Uploaded → Validating source → Generating → Validating environment/tools →
Testing → Ready**. Branches: **Needs clarification, Generation failed, Environment
unavailable, Validation failed, Budget paused, Outcome unknown, Cancelled**. A failure
retains source, audit and diagnostics; only disposable compute/staging is cleaned up.

## 6. Budget and retry behavior

The installation default initializes one cumulative cap for the entire import family.
Initial generation, regeneration, generated-fixture creation and model-assisted repairs
all charge that same ledger. Editing in a notebook does not create a new generation cap.
Changing the default, reopening a draft or replaying a request does not reset spend.
Manual editing and non-model validation can continue when generation is paused.

Reserve a conservative bounded amount before each generation request. Persist request
intent and usage/outcome, enforce maximum calls/tokens and reconcile actual cost. If
remaining capacity cannot cover the next request, stop before dispatch and show the
remaining cap. Ambiguous requests retain their reservation and are not automatically
retried. Retry/idempotency and cancellation must not duplicate model requests.

Evaluation has a separate explicit run budget covering selected models and repetitions.
Generation budget does not pay for evaluation or authorize it. Runtime/infrastructure
resource limits are separate from the model-token cap; GCP provisioning and quotas need
their own implementation/deployment configuration. No numerical budgets are selected here.

## 7. Colab and JupyterLab editing

Both roles can open permitted generated code and test cases, edit directly or request
regeneration. Notebook use is optional; it is not an approval or readiness gate.

Google documents Colab connections to local runtimes, including a runtime on a GCP
machine using forwarding. It also notes that notebook contents/outputs may be saved or
shared. See [Colab runtime documentation](https://research.google.com/colaboratory/local-runtimes.html)
and [Colab FAQ](https://research.google.com/colaboratory/faq.html).

Proposed integration:

1. Anvil prepares a task-bound `.ipynb` with code modules, synthetic fixtures, rule mappings
   and commands to invoke authorized validation. No embedded provider key, browser cookie,
   database credential or restricted reference data.
2. **Open in Colab** guides opening the notebook. Authoritative environment tests use an
   Anvil-managed isolated verification runtime on GCP through a configured supported
   connection; setup may require an explicit connection/tunnel step. No automatic native
   Colab↔Anvil save integration is assumed to exist.
3. JupyterLab can use the same verification service as an alternative. A standard hosted
   Colab session can edit/test permitted standalone code, but its results do not certify
   the supplied Docker environment. Supplied image execution is done by Anvil's qualified
   worker, not assumed available inside consumer Colab.
4. A task-scoped, expiring save-back session or explicit edited-notebook/code-bundle upload
   returns only permitted artifacts. External notebook content uses sanitized data by
   default; restricted fixtures remain server-side and are accessed only by authorized
   project validation services. No automatic Google Drive export of private evaluation data.
5. **Save back to Anvil** checks project/actor access and the base version, creates a new
   immutable draft, scans changes and reruns all required tests in a fresh bound environment.
   Notebook-supplied pass flags, outputs or hashes are not trusted as server validation.

Code/results are saved with cell/module provenance and artifact hashes. Conflicting
edits show a base-version conflict instead of overwriting another draft. Existing Ready
versions stay usable; after successful server validation the successor is also Ready.
Existing runs keep their original bindings. A failed successor does not revoke unrelated
working history or silently replace a run's task version.

Private model reasoning is not required or reconstructed. Notebook/kernel access is
isolated from the API host, production credentials, other projects and unrestricted
Docker/host administration. Actual runtime provisioning is implementation work, not done
by this specification. Existing individual private-reference access rules remain in force.

## 8. End-to-end user journeys

### A. Admin setup — once per installation

Models → Standard import generation model → select provider/model and save its credential →
set whole-import default cap → Save configuration. Display configuration version and
availability. Project evaluation-model setup remains separate.

### B. Import and make executable

Tasks → Import Task → supply Praxis export/bundle/assets and supplied image → inspect
task summary, framework Harbor and inherited generation model/cap → **Import & generate** →
observe source/code/environment/tool/fixture/package checks → **Ready** when all required
checks pass. No separate code-review, PO, PM or Mark ready approval.

If anything fails, show the stage, file/rule/tool and reason. User can fix the input,
change a draft, test again or regenerate within remaining cap. Never show Ready solely
because upload succeeded. Identical request replay returns its existing job rather than
spending again.

### C. Optional edit/test journey

View Task → Verifiers / Constraints / Rubrics → inspect source requirement and generated
code → Edit inline or Open in Colab/JupyterLab → test synthetic cases → save back → new
draft → automatic server validation → Ready or detailed failure. Regeneration uses the
same import generation ledger and does not overwrite the previous version.

### D. Evaluate

View Task → Run → explicitly choose Ready task version, compatible supplied environment,
evaluation models with linked keys, shared output/time/step limits and repetitions,
plus aggregate evaluation budget → **Run**. Launch or show exact blockers.

Each trial starts with clean state, uses only validated tools/guardrails, and stops on
completion, declared hard failure, cancellation or limits. Paid model mediation remains
outside the candidate container. Capture observable action/observation and output events.

### E. Diagnose and compare

View Task → Run history → open a trial dashboard for scores, constraints, failure modes,
observed trajectories, usage, outputs and exact task/code/image snapshots. Select runs
within history → Compare. Code/image/scoring changes affect compatibility; descriptive
comparison remains possible but unsupported score deltas are labeled unavailable.

## 9. Modifications to existing screens

| Screen | Modification / primary actions |
| --- | --- |
| Sidebar | Preserve Tasks and Administration. No Runs entry. Run history/comparison are reached through a task. No extra role/approval navigation. |
| Models & keys | Add installation-wide Standard import generation model and whole-import cap section; clearly separate project Evaluation models. Saved-key status/error feedback remains visible; no plaintext keys. |
| Tasks list | Status: importing/generating/testing/ready/blocked/failed; show latest Ready version and any newer draft state. Keep Import Task, View and Run. No Refresh tasks or row-level Run history link. Run points to a known Ready version or explains blockers. |
| Import Task | Replace the mixed legacy workbench with focused source/assets/image intake, task summary, Harbor binding, inherited generation model/cap and Import & generate. Show resume-existing-import when applicable. |
| Import progress — task subpage | Stage progress, actual diagnostics, tool/check coverage, generation spend/remaining cap; Cancel, Resume where safe, Fix input, Edit, Regenerate. Show why resume is blocked. No synthetic progress messages. |
| View Task — summary | Source/version, generated artifact revision, supplied image digest, readiness report, import lineage, generation provenance/cost, Ready and draft versions. Run and Run history remain available. |
| Task tab | Agent instructions, declared outputs, horizon, environment contract and source-to-runtime mappings. |
| MCP / Tool calls tab | Required tools, schemas, actual advertised interfaces, startup/availability and safe-probe results; show missing/incompatible tools. Implementation provenance points to supplied image. |
| Input files tab | Agent-visible files and mount paths/read-only state; restricted fixtures are separate and permission-controlled. |
| Rubrics tab | Weights, thresholds, dense/terminal/penalty definitions, generated verifier links and fixture expected/observed scores. |
| Constraints tab — new | Runtime/final/both classification, severity, generated implementation, blocked-action behavior and test coverage. |
| Verifiers tab | Generated Python source, requirement mapping, dependencies, tests and last validation report. Edit, Regenerate, Test, Open in Colab, Open in JupyterLab, Save as new draft. |
| Notebook connection / return panel | Notebook readiness, selected draft/base version, controlled-runtime connection status, allowed artifact set, Return to Anvil/save result and conflict diagnostics. |
| Run Task | Ready package/version and supplied environment; current project evaluation models with linked keys; shared max output tokens, max agent steps, timeout, repetitions and aggregate API cap; Run starts or explains. No generation model chooser here. |
| Run dashboard | Real step/tool/guardrail events, final outputs, rubric breakdown, violations, execution errors/unknowns, usage and bound source/generated-code/image versions. |
| Run history | Retain version-aware rows and comparison inside this page; separate synthetic compiler checks from candidate model trials. |

Navigation subpages/panels are task children, not new top-level modules. Common empty,
loading, error, cancellation, retry and expired-session states must remain explicit.

## 10. Implementation boundary and acceptance

Existing functionality: authenticated task lists/viewers, versioned profiles and encrypted
project credentials, bounded structured/staged Harbor packages, task Run groups/history,
metrics/observable dashboards, repeated trials and shared reservations. Dockerfile intake
is currently inert/quarantined. This new specification does not claim that general
description-to-code generation, arbitrary supplied-image qualification, MCP agent loops,
global generation settings or notebook integration are already built.

Proposed build order: export/mapping contract and fixtures → installation generation
configuration/ledger → generated artifacts/compiler → supplied-image/tool qualification →
automatic validation/readiness → multi-step guarded agent → notebook round trip → screen
integration and access/budget/isolation regression. Every runnable slice needs actual tests.

Acceptance criteria:

1. Complete supported Praxis task + supplied image becomes a hashed executable Harbor
   package; each required verifier/constraint maps to executable code and tests.
2. Missing required tools, unsafe probes, incompatible schemas, unresolved rule semantics,
   failed fixtures or verifier crashes prevent Ready with an actionable report.
3. No human approval is required for testing readiness; both scoped roles can edit/test.
4. All generation attempts for one import obey one cap and pinned configuration; evaluation
   uses a different explicitly chosen model set/budget. Unknown calls are not retried for free.
5. Two evaluation models × three repetitions produce six distinct trials under the shared
   cap, with independently reset environments and bound task/code/image versions.
6. Runtime prohibited-action attempts are denied/recorded; final checks grade the permitted
   workspace; private references/verifiers never enter candidate prompts or tool responses.
7. Notebook edits round-trip into a successor draft; stale-base/cross-project saves fail;
   only fresh server validation can mark the successor Ready. Existing versions/runs persist.
8. Good/bad/empty fixtures behave as declared; step reward is capped and penalties/hard
   failures are traceable. Generated fixture success is labeled software validation.
9. Run launches or explains current blockers; history provides actual results, observable
   trajectories and compatible comparisons with truthful missing/unknown accounting.
10. Provider keys, global generation credentials, other projects, host credentials and
    restricted grading assets remain outside notebooks/candidates/exports as applicable.

Not in this increment: other framework execution adapters, automatic environment/tool
implementation generation, arbitrary multi-service infrastructure design, training/PPO/GRPO,
hidden chain-of-thought capture, real email, cloud deployment/IAM changes or publication.
Human readiness approval is deliberately deferred, not silently recreated under another role.
