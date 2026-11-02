# Shared Praxis / Anvil executable-import golden set

Contract: `praxis.anvil.task.v3` inside the unchanged `praxis.anvil.export.v1` envelope.
All data is original, fictional synthetic software-test data. These files are not
real KYC/AML decisions, fraud findings, marketing forecasts or model-performance results.

## The three primary files

| Praxis export | Scenario | End-to-end coverage |
| --- | --- | --- |
| `01-marketing.export.json` | Budgeted campaign allocation | Integer money, total/concentration limits, forecast tolerance, evidence IDs, prohibited campaign launch, exact/over-limit cases. |
| `02-kyc_aml.export.json` | Multi-hop corporate ownership | Ownership arithmetic, strict >25% UBO threshold, screening-derived risk, SAR evidence, prohibited customer contact. |
| `03-fraud.export.json` | Windowed investigation | Half-open time window, account aggregation, ordered freeze/escalate actions, immutable audit and prohibited transfers. |

Each export has a readable `.task.json` companion containing the exact `payload_json`
bytes. Upload either one export envelope or its raw task payload, not both as different
tasks. The export is the preferred shared Praxis handoff. JSON Schema is
`../task-v3.schema.json`; the executable validator is `anvil.praxis_executable.TaskV3`.

## Contract boundaries

- `objective`, `instructions`, actor-visible input assets, output schema and written
  rubric/constraint descriptions define what the agent must do.
- Tool declarations define interfaces and safe disposable probes, not automatic tool
  implementations. Implementations must exist in the supplied image.
- The environment includes an actual inspected image digest **and digest kind**. The
  local fixture ID is not claimed to be a registry-pullable OCI digest or available in GCP.
- `evaluation_private` contains authoritative QA expectations for this golden set. It
  is optional for normal prose-only imports, where Anvil will generate test cases later.
  It must never enter candidate prompts, tools, actor files or notebook exports by default.
- Installation generation model/key/cap and evaluation model/budget selections are Anvil
  policy. A Praxis payload cannot override them. Source project/client/review IDs are
  unverified lineage metadata and never choose the destination project or grant approval.
- Anvil accepts these as validated, immutable sources now, with isolated actor projections.
  General description-to-code generation, global generation settings, production MCP agent
  qualification and notebook editing remain subsequent spec24 milestones. Upload does
  **not** falsely mark them Ready or create a paid request.

Every source has safe tool probes, output structure, written requirements, weights,
runtime/final constraints, source/input hashes, supplied image information and private
good/bad/empty/guardrail/boundary fixtures. All rubric/constraint IDs have independently
asserted passing and failing expectations:21 cases across the three files.

## Supplied reference environment

The common image is built from the existing pinned Python base using stdlib code only.
Its source is `fixtures/executable-import/environment/`. It contains public synthetic
inputs and a newline-delimited JSON-RPC MCP stdio server. It contains neither the private
reference evaluator nor the scripted solution/oracle expectations. Tools are documented
against the [MCP2025-06-18 stdio](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
and [tool interface](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) contracts.

The reference server denies forbidden actions before effects and records attempted
actions. Fraud escalation requires a preceding freeze. Campaign saving enforces monetary
limits. Tool probes are intended for disposable seeded workspaces, never real endpoints.

The companion image archive is produced under ignored
`artifacts/golden-harbor-imports/anvil-golden-tools-1.0.0.tar`. On another authorized
Docker host, load that supplied archive, inspect the resulting image ID and compare it
to each export before execution. No registry upload or GCP deployment is performed.
If rebuilding produces a different image ID, explicitly regenerate the source bindings;
do not silently replace an image behind an existing task version.

## Reproduce the files and tests

From the Anvil repository, with its existing virtual environment/dependencies:

```sh
services/backend/.venv/bin/python -c 'from scripts.build_golden_exports import prepare_image; prepare_image()'
docker build --network=none --pull=false -t anvil-golden-tools:1.0.0 fixtures/executable-import/environment
# Inspect the real image ID, then pass it explicitly; do not invent an OCI digest.
docker image inspect anvil-golden-tools:1.0.0 --format '{{.Id}}'
services/backend/.venv/bin/python scripts/build_golden_exports.py --image-id <actual-image-id>
services/backend/.venv/bin/python scripts/verify_golden_imports.py
ANVIL_TEST_HARBOR=1 ANVIL_HARBOR_DOCKER_HOST=<authorized-local-unix-socket> services/backend/.venv/bin/python scripts/verify_golden_imports.py --native
```

Native rehearsal uses Harbor0.25.0's real Docker/oracle/nop paths: full positive,
empty-zero and hard-guardrail-zero trials for each scenario (nine trials). The scripted
actor computes from **public tool observations only**; it never reads the private fixture
outputs or expected rewards. Actual advertised MCP schemas are compared with the export.
The trusted reference grader is injected after candidate execution. All21 authored
negative/boundary oracle cases are additionally checked independently of model inference.

The fixed golden reference package is a software fixture, not the general-purpose
model-generated package implementation. Native rehearsal uses a controlled fixture
initializer; generic image initialization, read-only input mounting and safe independent
probe qualification remain part of the new worker implementation. Passing this harness
does not authorize executing arbitrary uploaded code or certify business correctness.

Evidence is written to ignored `artifacts/test-runs/golden-v3-report.json` and native
logs under `artifacts/test-runs/golden-v3/`. Failures remain failures, not zero-cost or
successful model runs. No API keys or paid model calls are needed by this rehearsal.

## Praxis exporter checklist

1. Emit v3 source as UTF-8 JSON and preserve exact bytes inside export.v1.
2. Compute payload/input SHA-256 values over their actual bytes. Never reformat
   `payload_json` after computing `payload_sha256`.
3. Keep versions as strings and IDs stable; a changed source needs a new logical version.
4. Export complete written rules and tool/output schemas; omit unavailable semantics
   only with an explicit unresolved status, not invented executable bindings.
5. Supply the environment separately and bind its real digest/kind. All required tools
   must be available in it; no code generation for the environment is implied.
6. Preserve private QA fixtures as private. Do not flatten this envelope into an agent
   prompt or use the reference results as measured model outputs.
7. Use these three files and the shared validator/schema as conformance tests. Praxis
   repository changes are intentionally not made from this Anvil implementation.
