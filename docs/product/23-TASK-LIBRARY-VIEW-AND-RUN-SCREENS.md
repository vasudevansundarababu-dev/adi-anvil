# Task library, task viewer and run workspace

User-approved reference: supplied three-panel Tasks / View Task / Run Task mockup,
1 November 2026. The design uses existing modern workspace navigation and light/dark
themes. The editor toolbar surrounding the reference image is not application UI.

## Journey and screens

- `/workspace/{project}/tasks`: server-side title/ID search, latest-version package
  status filter, ten-row cursor pages, last recorded execution timestamp, version/run
  counts, Import Task, Run, View and task-scoped run history. Package built describes
  packaging, not paid readiness or model qualification. Empty/error/loading states
  explain the next step without fabricated task rows or dates.
- `/tasks/import`: existing JSON task import and explicit package build, with optional
  environment-folder intake after selecting/importing an immutable task version.
- `/tasks/{sourceId}`: separate version viewer with title, import timestamp, historical
  version selection, run count, prompt/visible stage instructions and environment
  summary. Tabs: Task, MCP / Tool calls, Input files, Rubrics, Verifiers. Actions are
  declarations, not connected MCP servers. Rubric descriptions and weights are safe;
  executable private bindings/reference outputs remain excluded. Run/history actions
  retain the exact selected source version. Editing task content still requires a
  new immutable import; the viewer does not mutate history.
- `/tasks/{sourceId}/run`: configuration beside a recorded execution-events panel.
  Exact source package, configured framework preset, model selections, target
  environment, repetitions per model, output limit, time limit and explicit aggregate
  USD budget. Save creates an immutable group; Admin Run explicitly authorizes its
  bound rights and budget. Once launched, events show actual trial lifecycle, observed
  stage statuses, errors, terminal score and links to results/trajectories. No invented
  sandbox messages, token-stream simulation, hidden reasoning or raw container logs.

## Repetitions and accounting

The user explicitly requested repetitions now: 1–10 per selected model, at most eight
models and 80 sequential children. Each child has its own immutable plan, per-model trial
number, check/result and exact original task/model/key snapshot. The estimate sums all
children; one group cap is reserved atomically and applies cumulatively. Repetition is
explicit scope, not a retry after an ambiguous dispatch. Existing cancellation, revocation,
recent authentication, project/private-reference isolation and no-retry rules remain.
Migration035 expands the ordinal constraint without changing old groups. Missing trial
or environment fields on historical snapshots retain their original one-trial behavior.

## Dockerfile environments and current limitation

User supplied `/Users/vasudevansundarababu/Code-Repo/harbor-lab/marketing-budget/environment`
as a read-only example. It contains a Dockerfile using `python:3.12-slim`, apt-installed
tmux/CA certificates, a COPY of three input files, and `/app/output`. No sibling file
was changed and no image build or installation was run by this implementation.

Import accepts an environment folder: one root Dockerfile plus relative companion text
files, at most100 files/1MiB total/256KiB per file. Traversal, absolute/hidden/duplicate
paths are rejected. An immutable context hash, Dockerfile hash, author and source version
are persisted; artifact bytes are quarantined and cannot be read by the runtime.
Import is idempotent by exact context. Imported custom environments appear as Awaiting
qualification and cannot be selected for execution. Qualified package-bound Docker is
the currently executable environment. No custom Dockerfile is silently substituted into
it. The mock banking environment is not registered as real infrastructure.

**Incomplete:** building/executing uploaded Dockerfiles and arbitrary companion binaries
requires scanner and isolated-build qualification. The example's `/app` output convention
also needs an explicit adapter contract; the current structured adapter writes
`/workspace/output.json`. Uploading code must not silently change that contract, inherit
host credentials/network authority, or expose private verifier material to its build context.
The new screens and repeated trials do not claim this qualification is complete.
