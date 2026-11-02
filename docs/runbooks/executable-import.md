# Description-first Praxis → Harbor import

This journey uses `praxis.anvil.task.v3` inside the existing exact-byte
`praxis.anvil.export.v1` envelope. The three shared goldens are in
`contracts/praxis/golden-v3`. Sources and generated artifacts are different immutable
records. Existing v1/v2 imports and the classic journey remain available.

## Installation setup

An operator assigns existing Admin user UUIDs through `ANVIL_INSTALLATION_ADMIN_IDS`.
This is an installation-settings scope of Admin; a project grant alone does not grant
access to the shared key. No third user role or review ceremony is introduced.

Models & keys → Standard import generation model → configure provider, exact model ID,
write-only key, whole-import cap and call/token bounds. Saving makes no request.
An explicit `ANVIL_IMPORT_GENERATION_ENABLED=true` server setting and enabled saved
configuration are both required for paid generation. This build does not enable them.
Keys use Anvil's encrypted local store. Cloud credential entry is blocked until its
managed secret-store adapter is configured; this is not a cloud deployment claim.

Known standard OpenAI models use the existing server-managed cost catalog. Other
models require operator-verified rate/expiry support. Prices are spending controls,
not another task-user form. Accounted generation cost uses configured conservative
rates; unknown usage retains its full reservation. Evaluation has its separate existing
Admin Run authorization and aggregate budget.

## Import and fix

Tasks → Import Task → upload a golden export → inspect source summary → Import & generate.
Before a generation request, Anvil runs declared safe probes in fresh supplied-image
containers and supplies observed response shapes and operational status/path markers to
the generator. It excludes response business values and never invokes prohibited tools.
The prompt explicitly assigns JSON parsing, disposable reset and output persistence to
the trusted harness; unscored workflow instructions do not create new rubric IDs.
The dedicated Docker worker generates artifacts, checks Python syntax/allowed operations,
tests every rubric/constraint, resolves the supplied image, handshakes MCP servers,
compares actual tool schemas, runs declared safe probes in fresh instances, and exercises
the pinned Harbor adapter. All required checks must pass before a Ready version exists.
There is no human testing approval or Mark ready action.

Each import freezes its generation configuration and cap. Regeneration uses that same
ledger, including unknown reservations. New installation defaults do not reset spending.
An Admin can explicitly select **Use updated generation configuration** after current
work finishes. This appends an audited binding; the original cap, spend/reservations,
Ready versions and old revision configurations are retained. Manual code edits retain
their original generation provenance. A changed model/key never silently rewrites history.
No model request is retried after ambiguous dispatch. Replaying a command returns the
existing work. Cancel accounts for in-flight requests before stopping. Manual editing
and validation do not consume model budget.

For paid generation, the Admin's Import & generate action confirms processing of the
exact source with the displayed configuration and cap. This source-bound permission
expires and can be revoked; an RL Engineer can use its current policy but cannot grant
it. This permission applies to external requests. Local editing/validation has no human
readiness approval. The server checks permission before reserving or sending a request.

Supported generated Python is deliberately restricted: no imports, host I/O, arbitrary
dependencies, classes, decorators or dunder access. `evaluate(inputs, output, events)`
returns boolean checks; `guard(tool, arguments, inputs, events)` returns allow/violation
decisions; `probe(tool, result)` checks declared safe-probe behavior. Rule mappings and
positive/negative fixtures are mandatory. The trusted server computes bounded scores,
penalties and hard failures. Generated code is executed only in a separate pinned,
credential-free container, not on the API/worker interpreter.
Supplied private QA cases are withheld from the generation prompt and additionally
check generated grading logic before Ready. Self-consistent generated tests cannot
override those independent source expectations. Packages contain actual private Python
modules, rubric/fixture definitions and traceability files outside the candidate image.

Only supplied synthetic environments are admitted in this increment. Tools must already
exist in the image. Missing tools, unsupported semantics or schemas, unsafe probes and
failed verifiers produce an actionable failed/clarification report. Anvil does not
generate a Dockerfile or invent tool implementations. OCI references must match the
locally available registry digest; Docker image IDs require the supplied local archive.

## Edit and test

View Task → Inspect / edit generated Python → Save new draft & test. Generated tests and
rule mappings can be edited as an artifact draft. Test again performs server validation
without a model call. Existing Ready packages and run bindings are retained.

Download review notebook → open in Colab using File → Upload notebook, or open in
JupyterLab. The notebook contains code and an optional empty-output smoke using permitted
actor inputs. Provider keys, private inputs and source QA oracles are excluded. Full
grading/probe checks remain on Anvil's isolated worker. Hosted notebook output is not
proof that the Docker environment works. No automatic Google Drive upload or GCP runtime
provisioning is performed.

Return the edited notebook through Anvil. The base version is checked; code creates a
successor draft and fresh server validation. Other cells, saved outputs and client pass
flags are ignored. Stale/cross-project returns fail. A failed draft does not revoke an
earlier Ready version.

## Run and diagnose

Run Task → choose evaluation models with linked keys, shared output-token/step/time
bounds, repetitions and aggregate budget → Run. The existing admission and reservation
controls apply. Generation configuration does not authorize evaluation.

The native Harbor tool agent delegates each bounded decision to the server broker.
Supplied containers have a read-only root, no network, dropped capabilities, PID/CPU/RAM
limits, read-only actor inputs and a fresh output workspace. The broker validates actions,
denies prohibited effects before dispatch and retains trusted observations. Final grading
runs separately, using captured outputs and private inputs unavailable to the candidate.
After actor completion, a fixed verifier entry point receives only the trusted numeric
grade receipt. Anvil checks that Harbor's recorded reward equals the isolated grader's
reward. No private reference data or generated grading code is injected into the actor.

Task → Run history → dashboard exposes outputs, per-rule scores, trusted violations,
observable tool trajectories, usage and exact source/code/image bindings. Compare remains
inside task history; changed package/scoring bindings do not claim comparable score deltas.

## Verification

The integration suite uses isolated retained databases and authored SDK mock responses.
It exercises all three imports, actual Docker/MCP validation, native Harbor trials,
two evaluation providers × three repetitions per task, and notebook successor validation.
These are software conformance results, not measured live model performance.

See `BUILD-STATUS.md` for the latest command results, failures and live-call limitations.
