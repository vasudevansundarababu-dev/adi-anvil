# Workflow sidecar v1 — Anvil/Praxis handoff

Current successor: schema074 supplies a separately registered structured-decision
native workflow adapter with durable parallel scheduling/joins, actual-human
wait/answer/cancel/expiry, API-mediated SDK/custody and original Task grading.
See `docs/generated/anvil-native-workflow-checkpoint.md` for its exact scope and
verification. It remains default-disabled and has not passed native/authentic
source acceptance. Tool-enabled graph roles and the older benchmark plan routes
remain blocked. The following original schema070 handoff records the historical
offline milestone; it must not be read as current native qualification evidence.

This is a separate declarative contract, **not task v4**, and is not a qualified
native execution adapter. Existing `praxis.anvil.task.v1/v2/v3` and
`praxis.anvil.export.v1` bytes remain unchanged.

In an `anvil.task-group-import.v1` `project.json`, an existing Task entry may add
`"workflow_path": "workflows/task-001.json"`. The archive must contain exactly
the declared files. The new file uses `praxis.anvil.workflow-binding.v1`:

```json
{
  "schema_version": "praxis.anvil.workflow-binding.v1",
  "task_id": "exact-task-id",
  "task_version": "exact-task-version",
  "revision_id": "exact-revision",
  "payload_sha256": "sha256 of the unchanged export payload_json UTF-8 bytes",
  "graph_sha256": "RFC8785 SHA256 of the fully normalized graph object",
  "graph": { "schema_version": "praxis.anvil.workflow-graph.v1" }
}
```

The abbreviated example is explanatory, not a valid package. The complete
machine schema is `workflow-binding.schema.json`; the three complete graph
fixtures are software tests, not SME source tasks or performance evidence.
The server materializes all schema defaults before hashing. An exporter must
materialize them too; use the complete fixture shape (including null/empty
optional fields) to avoid different hashes for default omission. RFC8785 is
already an independently locked Anvil dependency. No layout metadata is accepted
in this version; the viewer computes positions without changing semantics.

The importer verifies the exact task ID/version/revision/payload hash, graph hash
and tool IDs against the task's existing public action allowlist. Binding proves
byte identity, **not source authenticity, rights, source review or approval of a
newly attached graph**. No task review is inherited by the sidecar. The whole
import group hash also includes the graph and its capability diagnostics.

## Defined semantics and limits

- Stable role/node/edge/artifact IDs; typed scalar artifact fields; one producer
  per artifact and explicit allowed readers. No reference answer, evidence body,
  dynamic code, expression language, shell command or import path fields.
- Explicit input, agent step, decision, join, business human step, output and
  escalation nodes. Inputs on a node are required; absent inputs never become a
  fabricated output. Join inputs name explicitly required artifacts. Optional
  branch input merging is not an executable capability in this release.
- Decisions reference one upstream boolean field; `boolean_or_unknown` permits
  null as a captured domain-unknown result. True/false/unknown/error destinations
  are mandatory and unique. A dispatch uncertainty is retained Unknown, separate
  from a captured domain-unknown branch.
- Scripted and actual human modes are distinct. Human contracts require timeout
  and error destinations. The offline runner supports immediate scripted
  responses only; actual responders, waiting/timeouts, signatures and environment
  release/restore are not qualified by these fixtures.
- Every return edge identifies a bounded loop, a maximum number of **returns**,
  and an explicit exhausted destination outside the loop. Removing the declared
  returns must yield a reachable DAG. Undeclared cycles, irreducible entries,
  nested/overlapping loop regions and unreachable terminals are rejected. Nested
  loops are explicitly unsupported rather than being accepted without proof.
- Separate global transition/call/wall/token/cost bounds are declared. Offline
  persistence enforces wall expiry, transition and call bounds and requires cost
  zero. It invokes no models, so token/cost fields are not billing enforcement.

## Visibility and runtime boundary

The complete graph is an **operator definition**, returned as `task.workflow`,
not inserted into `task.actor`. Candidate role input is constructed separately by
`workflow_projection.role_input`: one node's instruction, tools, declared output
schema and declared already-produced input artifacts. Extra private/future data
is omitted, wrong roles/extra artifact fields are rejected. These checks are not
native role/process-isolation qualification.

The viewer displays actual declared edges and labels, decision diamonds, distinct
human nodes, join details and bounded returns, with an accessible connection list
and one self-contained escaped SVG export. It does not infer a graph from prose,
show a fabricated execution path, modify benchmark PDFs or support bulk export.

`workflow_fixture_runtime` compiles a deliberately bounded **sequential** offline
subset through installed Python LangGraph. It supports fixed roles, decisions,
linear correction loops and immediate scripted human responses. Logical parallel
graphs are inspectable but fixture execution explicitly rejects fan-out/joins;
tools and actual humans are also rejected. This is not the general multi-agent
runtime or a replacement for existing guarded Harbor dispatch.

Migration070 adds only project-scoped zero-cost fixture trials and an independent
PostgreSQL effect ledger. It does not add a public launch endpoint. PostgreSQL
checkpoints use the existing trusted checkpoint namespace. Claims commit before
the fixture effect; trial/node/visit/call-index keys bind a request hash. Re-entry
uses completed receipts; pending intent returns Unknown, never a fresh dispatch.
Cancellation/expiry/membership and immutable binding checks precede each step and
effect. Tests interrupt after intent and after receipt commits, then resume using
a new compiler/connection. These are controlled interruptions, not SIGKILL or
native-container recovery evidence. No paid reservation/exactly-once claim is made.

Both existing benchmark plan paths and worker validation reject graph-bearing
tasks until native qualification. Legacy scoring and Harbor reward paths are
unchanged. Existing Task rubric remains authoritative; no graph fixture score is
presented as a Task result or model performance.

## Exact next Praxis/Harbor handoff

Praxis must supply a canonical exporter for this sidecar, exact graph-bound review
and rights evidence and one genuinely authored supported-template package, with
unchanged legacy task bytes and independently computed graph hash. No graph may
be reverse-engineered from existing draft prose. Jointly review optional-input
join semantics and nested loops before extending this contract.

Then implement/qualify the graph-aware Harbor0.25.0 actor/broker/collector and
separate verifier against that exact template. Exercise oracle, invalid baseline,
tamper, role visibility, cancellation, Unknown custody and restart with the
existing durable paid admission. Preserve Task scoring and native reward
separately. Authentic export→import→native run→capture→verifier→stored results
is **blocked/not run**, not established by this offline milestone.
