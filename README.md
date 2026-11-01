# ADI Anvil

Frontier Evaluation & Diagnostics Platform

The modern workspace is being built on `codex/anvil-modern-workspace`. Open
http://127.0.0.1:3202/workspace after local startup; classic `/p/{project}/...` remains
available through **Compare classic journey**. The preserved baseline branch is
`codex/anvil-classic-v021-comparison`. Both journeys use the same canonical local data;
new schema changes are additive. This development branch has not been deployed.
Tasks and Runs offer a **Diagnostic evaluations** source switch for existing diagnostic
history, finalized result evidence and exact task/rubric/protocol snapshots. Unfinished
grading stays blinded, and diagnostic metrics explicitly cover the whole run.
Modern People groups each person once, with Admin/RL Engineer labels derived from current
grants and preserved review duties available in details. Historical mapping evidence is
recorded locally; this transition does not grant new access or implement invitations.
Frameworks also offers typed execution presets. From a Harbor task, **Prepare evaluation**
saves exact package/model/framework versions and shows missing readiness requirements.
These are planning records: saving makes no model request or spending reservation, and
does not launch a run. From saved readiness, **Create execution group** freezes the exact
models, prices, terms and limits, shows computed gates, and supports existing rights/Admin
decisions, atomic shared reservation, sequential Harbor execution, cancellation and per-model
results. OpenAI/Claude/Gemini native brokers are software-verified with mocked SDK responses;
live model access/compatibility is not claimed. Runtime dispatch stays off until separately
authorized. See the [execution walkthrough](docs/runbooks/workspace-execution.md).
Saved preparations open as read-only readiness summaries. **Create another preparation**
opens a fresh form with an empty budget; a sole fully loaded package or preset is shown
as a version summary instead of a dropdown. Model selections remain explicit.
Models & keys supports **Edit as new version**, configuration history and whole-profile
disabling. Existing preparations keep their original bindings; superseded/disabled versions
are blocked from new preparation. Optional pricing and terms are declared metadata, with
no automatic model request, rights approval or spending authority.
See the [nightly plan](docs/build/08-MODERN-WORKSPACE-NIGHTLY.md) and [current status](BUILD-STATUS.md)
for built versus remaining capabilities. Saved LangSmith/Semantic Kernel metadata is not a
qualified external adapter; saving a credential never enables inference.

The v0.2.0 increment adds the [Praxis → Harbor workbench](docs/runbooks/praxis-harbor.md),
immutable single-stage/staged task packages, retained software-check analysis and gated
model-run preparation. The workbench is deployed; authenticated import/build passed, while
deployed execution awaits independent Product Owner approval. See
[current build status](BUILD-STATUS.md). Synthetic check scores are not model performance.

The deployed v0.2.1 [cloud admission handoff](docs/runbooks/harbor-cloud-admission.md) prepares empty
private file mounts and a separate disabled Harbor admission flag. It supplies no keys,
paid authority or live activation; current model/pricing/budget and real approvals remain
separate requirements.

**Verified local diagnostic, Factory and provenance increments — 29 September 2026.** The real-OIDC diagnostic, task-import, marketing-preparation and Benchmark Factory journeys pass, along with the production build,130 unit tests and67 integration tests. Fresh migrations through018 pass. Uploaded sources carry immutable author declarations; non-synthetic publication awaits reviewed rights/privacy controls. Full MVP and Benchmark Factory acceptance remain partial; paid launch and external sending stay blocked. See [current build status](BUILD-STATUS.md) and the [handoff report](docs/generated/morning-report.md).

## Start

1. Run `pnpm setup:local` to install locked dependencies and start PostgreSQL, Neo4j and Keycloak. Docker, Node/pnpm, Python and uv must already be available.
2. Run `pnpm dev`, then open http://127.0.0.1:3202. Distinct local account credentials are in ignored, owner-only `.local/demo-accounts.md`.
3. Verify with `pnpm check`, `pnpm test:unit`, `pnpm test:e2e`, then `pnpm test:integration`. Integration budget tests require the qualified protocol produced by E2E.
4. `pnpm stop` stops registered app/worker processes while preserving infrastructure and data. `pnpm services:down` stops infrastructure without deleting volumes.

`pnpm test:load` runs a separate400-episode, network-free fixture rehearsal in a new retained project. It creates200 repeated task variants from three source cases, restarts only the registered worker and leaves400 human reviews pending. Its results measure local processing, not model performance or independent case coverage. Run it while `pnpm dev` is ready and no other test is restarting the worker.

The [current walkthrough](docs/runbooks/morning-walkthrough.md) links to the prepared three-case project and maps the built UI to MORN-01–08. `pnpm demo:walkthrough` creates a fresh retained copy with scripted fixture reviews and a separate pending practice run. The [acceptance specification](docs/build/04-MORNING-ACCEPTANCE.md) describes the target; consult the [test matrix](docs/generated/test-matrix.md) for remaining gates. No specification is evidence of a passed test.

## Engineering authority

The [Benchmark Factory walkthrough](docs/runbooks/benchmark-factory.md) describes the
TaskProfile → deterministic recommendations → exact-version Suite draft increment.
It extends the existing registry and shell; catalog registration is metadata only,
and full benchmark smoke release and 100,000-task execution remain later work.

The [12-week marketing walkthrough](docs/runbooks/marketing-live.md) covers the registered
interactive task, exact OpenAI connection, draft run, real paid approvals and local key setup.
The harness supports 12 dependent decisions plus a final memo, PostgreSQL checkpoints and
independent review. It has been exercised with a mocked provider, not a live model. The user
requested leaving paid launch blocked: no local key or real Admin approvers are ready.

The [Task & Data Import walkthrough](docs/runbooks/task-data-import.md) covers CSV/JSONL
upload, background validation, immutable dataset publication, suite attachment and exact
version selection in Run Console. This is the first daily ingestion increment; advanced
connectors, generation, privacy processing and arbitrary imported-task execution remain pending.

The latest user selected a new independent repository named **ADI-Anvil**, private, local build first and GitHub publication only after review. Infrastructure and the eight-hour/local-only build boundaries are confirmed. The requested morning target includes the diagnostic journey **and live model evaluations**. The first selected provider/model is OpenAI `gpt-6-sol`, with a $100 cumulative API ceiling. Credentials, reviewed rights and real paid approvals remain required; paid launch stays blocked. The [12-week synthetic marketing task](task-packs/marketing-12-week/README.md) now has a dedicated Anvil workflow alongside its offline development simulation.

Read [overnight build specification](docs/build/01-OVERNIGHT-BUILD-SPEC.md), [repository structure](docs/build/02-REPOSITORY-STRUCTURE.md), [runbook](docs/build/03-EXECUTION-RUNBOOK.md), [live evaluation gates](docs/build/05-LIVE-EVALUATION.md) and [fixture contract](docs/build/06-FIXTURE-CONTRACT.md).

The files in `docs/product/` preserve the detailed v1.0 product/contracts baseline. The new `docs/build/` instructions supersede only the old folder name, phase-0–1-only coding prompt, one-phase-per-request sequencing, and prohibition on local Git initialization once this build is launched. They do not remove security, rights, review, truthfulness or budget controls. The old ADI-Core-Frontier folder is not a runtime dependency and must remain unchanged.

## Target and current boundary

The local slice includes UI + API + PostgreSQL + LangGraph worker + Neo4j projection + OIDC, source intake/gaps, rights, qualification, versioned suites/protocols, fixture execution, reported-result import, human review, diagnostics and downloadable one-page Sales Kits. The registered marketing runtime adds guarded OpenAI dispatch, tested with a mock transport; actual model access, real-person Admin onboarding and live verification remain outstanding. Other provider adapters remain mock-contract only. General files stay quarantined without a qualified scanner. No enterprise training, TNG/TTM, simulator authoring, cloud deployment, real email, Notion publishing or live Praxis synchronization.

Original sample cases test application mechanics, not research novelty, long-horizon intelligence, university validation or commercial performance. All fixture outputs remain illustrative after review/export. No real Bodhium cases are included.
