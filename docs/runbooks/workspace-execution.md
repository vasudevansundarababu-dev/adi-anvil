# Run a prepared Harbor task in the modern workspace

The local workspace now connects a saved preparation to an execution group, the existing
Harbor worker and per-model results. **Saving configuration is not authorization to spend.**
Real provider/model compatibility is not claimed from software tests. No cloud rollout is
included in this increment.

## User journey

1. In **Models & keys**, save each exact model version with its explicit credential version,
   output ceiling, current declared input/output prices, expiry and processing-terms reference.
   The reference records information; it does not grant data rights or pricing authority.
2. In **Frameworks**, configure a Harbor0.25.0 runner and an execution preset. Choose
   **Anvil structured JSON agent**, the model allowlist and **None** for external tracing.
   LangSmith/Semantic Kernel metadata still does not provide a qualified execution adapter.
3. Import the exact Praxis JSON and **Build Harbor package**. Rebuilding identical input
   reuses its immutable package. Obtain the existing exact-package software-check decision
   from the project Product Owner; this does not authorize a paid model call.
4. Open **Prepare evaluation**, select the package, preset and exact models, set explicit
   output/time limits and one aggregate API cap, and save. If an old preparation has a
   blank cap or obsolete model version, use **Create another preparation**; old snapshots
   and their existing runs are not edited.
5. In saved readiness, choose **Create execution group**. It freezes the preparation,
   ordered model/config/key versions, declared prices/terms and execution-code digest.
   Creating this draft makes no provider request and creates no spending reservation.
6. Review the group's displayed blockers and conservative cost. The assigned real Product
   Owner records a rights-document reference, then explicitly reviews the exact run and
   external processing rights. Existing single-PO self-approval rules and audit remain.
   Each of two distinct real Admins records activation and paid-scope decisions, with a
   recent sign-in and explicit expiry. Synthetic local test identities cannot supply these
   paid decisions. Nothing in this build changes identity grants or impersonates reviewers.
7. After the operator binds separately approved exact authority and runtime controls below,
   **Launch evaluation** becomes available only if every current gate passes. Launch
   reserves the group cap once and creates each child run durably in the existing ledger.
8. Follow **View run** for each model. Dashboard, Results, Failure modes, Trajectories,
   Task & evaluations and Usage show the retained outcome, exact safe snapshots and costs.
   Trajectories show recorded dispatch times/hashes/IDs, verified actor context and terminal
   captured output. Future stage data appears only for that stage's actual recorded intent.
   Private grading bindings/reference outputs and hidden reasoning are excluded.
9. In **Runs**, select matching completed runs to compare metrics. Matching package, origin,
   scoring, execution-code, output and timeout settings permit score deltas; incompatible
   runs remain descriptive. Automated scores are not human scientific review or significance.

## Operator authorization

The runtime remains off by default. The build does **not** create paid authority or change
the runtime flag. A separately approved operator records `.local/workspace-authority.json`
with owner-only mode0600, after the user approves the exact group/provider/model/prices and
budget. It must be a regular owner-controlled file, not a symlink. Do not include an API key.

| Field | Meaning |
| --- | --- |
| `reference` | Explicit `harbor:` budget-authority reference; an existing reference shares its existing spend window |
| `project_id` | Exact local project UUID displayed in the group's snapshot details |
| `group_subject_hash` | Exact group hash, covering task/package, ordered frozen model/config/key versions, prices, terms, limits and code |
| `total_cap_micro_usd` | Positive integer user-authorized cumulative cap;1 USD =1,000,000 micro-USD; no inferred/default budget |
| `expires_at` | Explicit future timestamp with timezone |

Use the existing independently gated Harbor live-runtime switch only with separate live
authorization. Do not reuse old marketing-only authority, silently fall back to a global
provider key, promote seeded accounts, or rewrite a group to match changed settings.
Changing a reference/cap invalidates matching Admin decisions. Changing code, model/key
version or price metadata requires a new preparation/group and appropriate fresh review.
The authority file currently admits one exact group at a time; replacing it revokes further
dispatch for older nonmatching groups. Coordinate this explicitly while runs are active.

Exact returned-model equality is deliberate. An alias resolving to a different returned
model identifier, missing/malformed usage, unadmitted Anthropic cache pricing, inconsistent
Gemini usage, a response above its admitted token/cost bound or uncertain transport becomes
an unresolved outcome. It is not retried or silently relabeled as a successful compatible
model. Use pinned exact model identifiers for approved validation.

## Budget, sequencing, cancellation and failure

- Launch serializes the exact group and shared authority window and reserves **one aggregate
  cap**. A replay or concurrent launch cannot enqueue duplicates or reserve twice. The sum
  of per-model/per-stage conservative bounds must fit both group and authority ceilings.
- Child jobs are durable together. The database only lets a child be claimed after all
  predecessors succeeded. A task failure with a valid retained grading result can continue;
  operational failure, unknown dispatch or cancellation stops later dispatch.
- Each stage rechecks current access, bindings, credential revocation/rotation, reviews,
  code, authority/expiry and reservation. Its dispatch intent commits before network I/O.
  Project/group/plan/check locks never span the provider request.
- Provider credentials are resolved only inside the trusted server boundary. Fixed native
  endpoints/auth and no-retry/redirect behavior are guarded; provider secrets never enter
  Harbor, task archives, trajectories, audit metadata or error text.
- **Cancel remaining runs** stops queued children and requests cancellation of active work.
  An already dispatched request cannot be recalled. Captured billing evidence is recorded
  even after rights/access revocation. Unknown and cancelled attempts retain their reserved
  ceiling. There is no automatic refund, settlement or ambiguous re-dispatch.
- The local encrypted credential files/wrap key remain separate from SQL/artifact backup.
  Missing/invalid secret material fails closed before a provider request. Restore those
  files securely before trying a fresh authorized operation; do not substitute another key.

## Software evidence versus live verification

The test path uses original synthetic tasks, fresh isolated contract databases, new
contract-only identities and explicit native SDK MockTransport responses. The real pinned
Harbor runner/sandbox/Gateway is exercised for staged OpenAI, Claude and Gemini paths.
Mock calls are labeled `native_sdk_mock_verification` and `model_performance=false`.
These tests establish software behavior, not real API access, provider availability,
model quality, real-person approvals or paid performance. No real model call is made by
the build. See BUILD-STATUS.md for exact final verification and remaining platform scope.
