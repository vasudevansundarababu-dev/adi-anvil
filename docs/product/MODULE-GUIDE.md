# Anvil modules and distinctive features

Anvil is the execution and diagnostics half of the Praxis → Anvil workflow. Praxis
authors and exports tasks; Anvil validates, qualifies, executes and inspects them.
“Distinctive” describes concrete product behavior, not an unverified market comparison.
This guide covers the modern workspace; dated results belong in [BUILD-STATUS](../../BUILD-STATUS.md).

| Module | Definition and user outcome | Distinctive implemented features | Boundary |
| --- | --- | --- | --- |
| Overview | Project landing page for configuration readiness and recent evaluations. | Project-scoped records; Harbor and diagnostic-history sources; links to exact run dashboards. | Summary counts are operational records, not benchmark validity claims. |
| Tasks | Task library, source inspection and the entry point for evaluation preparation. | Exact Praxis payload/hash and lineage; separate actor/private material; immutable source and task versions; task-specific run history. | Supported contracts and qualified environments only; an import alone does not grant rights or authorize spending. |
| Benchmarks | UI mockup of a domain library and model comparison dashboard; existing diagnostic catalog is separate. | Domain links into comparison, protocol, coverage and failure previews; consistent light/dark colors and persistent UI MOCKUP disclosure. Existing catalog supports confirmed profiles and exact-version Suite drafts at `/benchmarks/catalog`. | Preview scores, trial counts, costs and durations are illustrative. No preview execution or SME API; GDPVal is Planned. Existing static synthetic catalog matching is limited to 100 tasks/catalog versions; full expert TaskBanks and release remain roadmap. |
| Import generation and qualification | Converts v3 task descriptions into executable grading/guardrail artifacts and checks whether they can run. | Installation-wide generation model; cumulative whole-import cap across regenerations; safe tool-schema probes; restricted generated Python; positive/negative fixtures and withheld source QA; automatic Ready only after required checks. | Supplied synthetic environments only; no arbitrary Dockerfile generation or invented tool implementation. Generation and evaluation budgets are separate. |
| Generated-code and notebook editing | Inspects and revises executable task artifacts. | Save a successor draft without altering earlier Ready packages; download a Colab/Jupyter notebook; return edits with base-version checks and independent server revalidation. | Manual notebook roundtrip; no hosted notebook provisioning. Notebook output or a client “pass” flag cannot grant readiness. |
| Execution groups | Freezes a task/package and selected model configurations into a bounded evaluation plan. | Exact model/key/framework/price/terms bindings; repetitions and per-run limits; readiness gates; explicit Admin Run authorization; atomic group reservation; sequential model execution and cancellation. | Failed/unknown/cancelled execution stops later models. New dispatch requires normal admission; no automatic retry of ambiguous calls. |
| Run dashboards and comparison | Explains what an execution did, how it scored and what it cost. | Separate execution state and task outcome; criterion diagnostics and hard failures; observable tool trajectories; retained output artifacts; version snapshots; known/unknown usage; comparisons from task history. | Unscored operational failures are not zero-scoring task answers. Incompatible versions do not produce comparable score deltas. No private chain-of-thought is inferred. |
| Models & keys | Admin configuration of model profiles, credentials and the standard import-generation model. | Exact model IDs; write-only credential entry; configuration history; edit as a new version; disabling profiles without rewriting old run bindings; scoped generation credentials. | Saving a key/model makes no inference call and grants no run authority. Live provider qualification is recorded separately. |
| Frameworks | Catalog and execution presets describing runner, agent and tracing capabilities. | Typed presets; separate metadata for runners/agents/tracing; readiness checks against the actual qualified adapter. | LangSmith/Semantic Kernel metadata is not a qualified external adapter. Harbor is the supported executable-import runner. |
| People | Displays project access and retained assignments. | Admin includes engineering; RL Engineer access remains project scoped; historical review duties remain traceable. | The page is not a production invitation/onboarding system or a role-switching shortcut. |
| Limits & usage | Explains operating boundaries and links to provider readiness. | Explicit notice that no default spending authority is granted; separate generation/evaluation controls and unknown-reservation policy. | This page is guidance, not a full billing dashboard. Actual per-run cost and unresolved usage are in run dashboards; cloud billing alerts are not application caps. |

## Retained diagnostic capabilities

The backend also retains source intake/gaps, versioned objectives/rubrics/suites/protocols,
rights and qualification, durable LangGraph fixture/reported-result workflows, blinded
human review, findings, graph projection and version-bound reports/Sales Kits. These
remain part of the evidence model and diagnostic-history compatibility path. The modern
workspace is the supported UI; this list does not claim that every former classic
authoring screen is exposed as a modern module.

## What ties the modules together

PostgreSQL owns canonical versions, audit, approvals, scores, jobs and budget ledgers.
Neo4j is rebuildable. Dedicated Harbor execution separates tools and private grading
from the ordinary API/worker. Source lineage, executable readiness, spending admission
and measured model performance are four separate claims.

The three golden tasks exercise marketing budgets, multi-hop KYC/AML ownership and
fraud investigation. Controlled responses qualify software mechanics. Actual model
results on those synthetic cases remain task-specific and unreviewed until reviewed;
they do not establish a broad intelligence benchmark.

The next cross-product increment sends eligible completed Anvil results into Praxis as
SME review tasks and logs the submitted review back into Anvil. This is a
[30-day roadmap item](../build/11-30-DAY-ROADMAP.md), not an implemented automatic API loop.

## Inspect implementation and evidence

- [Architecture](../architecture/README.md) and [executable-import runbook](../runbooks/executable-import.md).
- [Workspace UI](../../apps/web/src/components/ModernWorkspace.tsx), [task workflow](../../apps/web/src/components/WorkspaceTasks.tsx), [execution groups](../../apps/web/src/components/WorkspaceExecutionGroups.tsx).
- [Unit tests](../../services/backend/tests/unit/), [integration tests](../../services/backend/tests/integration/), [browser journeys](../../tests/e2e/).
- [Golden fixture contract](../../contracts/praxis/golden-v3/README.md) and [current build evidence](../../BUILD-STATUS.md).
