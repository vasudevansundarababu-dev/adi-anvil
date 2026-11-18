# Scoped KYC policy provisioning

The policy-review ledger separates a real project Product Owner decision from
installed technical evidence. It does not approve a run or grant spending.
Synthetic SQL and HTTP controls are software checks only; no policy decision or
runtime qualification is seeded by migration129.

The application stages exact subjects and records an authenticated PO decision.
With two active POs the subject creator cannot self-approve; with exactly one,
self-approval is explicit in the immutable receipt and audit. Subject hashes,
task/template versions, policy references, runtime/image/environment/evaluator
hashes and expiry remain exact. Readers recheck receipt revocation and current
reviewer authority. Application, worker, scheduler and grader cannot insert
runtime receipts or policy qualifications.

A separately provisioned restricted database login must be enrolled in
`kyc_policy_operator_principals` for its actual project/user and belong only to
`anvil_kyc_qualifier`. SQL binds this enrollment to `session_user`; changing GUCs
cannot impersonate another operator. Provisioning credentials are operator
inputs and are never supplied by the application.

Operator commands, using locally supplied `ANVIL_KYC_QUALIFIER_DATABASE_URL`:

```
python -m anvil.kyc_policy_provision --project PROJECT_UUID \
  --retain-runtime-review RESOLVED_INPUT_UUID --task TASK_ID --revision REVISION_ID
python -m anvil.kyc_policy_provision --project PROJECT_UUID --request REQUEST_JSON
```

The request contains exactly `qualification` and `materialization`. Runtime
retention requires real installed evidence with passed controls for the exact
runtime subject. Provisioning derives original stored scope, checks exact
template federal-policy references and both current ledger receipts, validates
complete materialization, then appends qualification and materialization in one
transaction. Receipt/qualification revocation is fail-closed. The command emits
`commit_observed: true` only after the database transaction commits. Failure
prints a fixed safe error without payload or connection credentials.

## Complete original source text: bounded v2 contract

The existing v1 contract supports complete raw UTF8 only when delivered text is
identical to source bytes, or exact existing JSON-pointer text. It deliberately
does not truncate, parse XML/HTML, select excerpts or relabel source hashes.
Explicit state-not-applicable policy records require a reviewed rationale and
empty state references; legacy empty-reference records remain invalid.

Real official sources of 13216, 71638 and 69622 bytes exceed v1 limits. The new
v2 materialization retains complete original UTF8 source bytes, without XML/HTML
parsing, excerpt selection or changed source hashes. Its bounded storage limits are
131072 bytes per artifact, 262144 aggregate public text, 1048576 materialization
and 524288 intermediate public JSON, retaining the existing 50MiB project quota.
Existing v1 limits remain unchanged.

The v2 policy tool returns a compact manifest reference. Existing `document.read`
retrieves manifest pages and exact UTF8 chunks through reserved IDs, bound to the
current authenticated product trial and original policy materialization. Each
document is bounded by both canonical and ordinary escaped JSON size8192. Sources
remain complete in immutable storage; chunk byte ranges and hashes permit exact
reconstruction without selecting excerpts. No filesystem path or hidden-reference
lookup is accepted. Every read repeats the current policy/review/scope checks.

The provider input32768, MCP65536 and engine100-call limits remain unchanged.
Sources whose complete reads exceed those episode limits cannot be declared
executable merely because they fit storage. Root manifest delivery does not mark
all source chunks read. State evaluation reconstructs actually delivered manifest
pages and chunks, checks full original source and policy-binding hashes, then
compares source metadata against the separate reviewed reference. Incomplete
delivery remains unknown. No v2 live admission or real
policy qualification is claimed by software fixtures.

The traced limits governing qualification of a v2 episode are:

* `golden_kyc_policy_delivery.py`: distinct materialization/public schema versions,
  exact full raw byte identity, version-dependent byte and JSON bounds.
* Migration129: version-dependent table CHECK and `exact_parent`
  validation, while retaining v1 bounds, RLS, immutable custody and quota.
* `kyc_policy_provision.py`: bounded1179648-byte CLI request, accommodating the
  bounded materialization plus qualification; each inner contract remains bounded.
* `golden_mcp_server.py`: tool response/line bounds currently65536. A negotiated
  v2 tool capability must account for JSON escaping and envelope overhead.
* `golden_kyc_paid_session.py`: prompt cap32768; deterministic public observation
  projection must preserve current exact chunk and manifest binding without
  pretending earlier source content remains in model context.
* `golden_kyc_paid_budget.py`: input allowance32768+1024 remains unchanged; reserve
  the bounded prompt cost before any dispatch.
* `golden_kyc_harbor.py`: actor/context byte caps8192 must remain valid for legacy
  execution; a successor must declare and enforce its own bounded capability.
* Provider dispatch (`workspace_dispatch.py`, `workspace_adapter_contracts.py`):
  normal actor input capped32768. Provider-specific model context, cost and
  exact payload bounds must agree with the negotiated successor.

An existing template is not silently upgraded by introducing a materialization
class. Its published `policy.read` / `document.read` schemas, complete document
coverage, deterministic transcript bounds and corresponding qualification/tests
must be verified before declaring the complete real-source workflow ready.
