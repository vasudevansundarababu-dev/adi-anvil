# Model configuration and Harbor run workspace

Status: **design proposal for review; no implementation authorized by this document**.
Date: 30 October 2026. Product: ADI Anvil — Frontier Evaluation & Diagnostics Platform.

User request: Admin configures OpenAI, Claude and Gemini models and their keys; Harbor
offers those configured models and shows runs, failures and trajectories. Prepare screens,
journeys and this specification before building. The separate Admin-only simplification
request applies to Praxis; it does not silently change Anvil's existing paid-run controls.

## 1. Outcome and scope

An Admin can manage multiple named model profiles per provider, configure a credential
securely, and enable qualified profiles for selection in a project. A Researcher can import
a Praxis task, select one or several eligible profiles, set explicit limits, inspect
readiness, launch an authorized run and examine each model's observable execution.

V1 covers official OpenAI, Anthropic Claude and Google Gemini APIs, one trial per selected
profile, existing structured-decision/staged-decision task adapters, and sequential model
execution by default. Each model gets a separate child run with independent output and
grading; a parent group shares the exact task version and cumulative spending ceiling.
V2 may add repetitions, more providers, controlled parallelism and qualified tool agents.

Not included: arbitrary user endpoints, generic shell agents, hidden chain-of-thought,
automatic model discovery/pricing claims, training, automatic spending activation or
automatic re-dispatch after an ambiguous request. No keys or actual provider calls belong
in the design prototype. Example model names, states and results are simulated.

## 2. Current implementation versus proposed behavior

| Area                | Deployed v0.2.1                                                                                | Proposed increment                                                                          |
| ------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Providers           | Official SDK mock contracts for several providers; latest configuration per provider displayed | Multiple versioned profiles per provider, with project scope and explicit readiness         |
| Keys                | Operator-managed private files; empty read-only cloud mounts; no key-entry API                 | Admin write-only credential workflow through an approved server secret store                |
| Harbor paid adapter | Bounded OpenAI JSON mediator; actual paid qualification not performed                          | Separately qualify OpenAI, Claude and Gemini for the supported Harbor task modes            |
| Model selection     | One exact OpenAI connection per plan                                                           | One or more enabled, compatible model-profile versions per run group                        |
| Observability       | Check histories, artifacts, stage diagnostics, durable call records                            | Unified run group, model comparison and observable event/trajectory viewer                  |
| Live admission      | Legacy and Harbor switches disabled; key/authority absent                                      | Remains disabled until separately authorized; configuration does not grant launch authority |

Relevant source: `provider_api.py`, `providers.py`, `harbor_agents.py`, `harbor_api.py`,
`harbor_worker.py`, existing connections/approvals/spend tables and artifact storage.
Extend those boundaries; do not introduce a second execution engine or billing ledger.

## 3. Screens

### S1 — Settings → Models & keys (Admin)

One row per profile: friendly name, provider, exact model ID, version, credential status,
Harbor compatibility, enabled-for-selection status and last configuration check. Support
several profiles using the same provider and an explicitly shared credential reference.
Actions: Add model, Edit as new version, Manage key, Disable, inspect configuration history.
Show empty/not configured, missing key, unsupported adapter, pricing expired, disabled,
configuration checked and available-for-planning states explicitly. No fabricated healthy
status or current model/price defaults.

Saving does not send a generation request. A local configuration check validates fields,
references and qualified capabilities. A separate non-inference access check is offered
only where the provider has a documented supported endpoint; otherwise label it unavailable.
Any generation test is an explicitly priced authorized run, never a silent credential ping.

### S2 — Model and credential editor (Admin)

- Provider: OpenAI / Anthropic Claude / Google Gemini; provider controls the allowed endpoint.
- Friendly profile name and exact provider model ID, entered explicitly.
- Credential: choose an existing permitted reference or Add new key in a masked, write-only
  field. Rotation creates a new secret version. Show Present/Missing and version metadata,
  never the key, a reveal action, a key prefix/suffix or a browser-accessible secret URL.
- Project scope, enabled-for-selection toggle, tested output mode, output-token/time limits.
- Reviewed pricing reference/source, input/output rates in integer micro-USD per million
  tokens, expiry and processing-terms evidence. No prefilled paid ceiling or stale rates.
- Save configuration; Check configuration; explicitly separate any authorized live test.

The prototype disables actual key entry and simulates saving metadata only. The eventual
real form clears the transient key field after submission and never persists it in browser
storage, analytics, URLs, widget state or diagnostic errors.

### S3 — Build → Praxis → Harbor → Prepare model run

Task summary shows source product, task/version, exact source/package hashes, binding and
stage count. Source draft status and source rights declarations remain distinct from Anvil
approval. Offer a separate synthetic harness-check action so reference/no-op/negative
verification is never presented as a model run.

Model picker lists enabled project profiles and their exact versions/provider/model IDs.
Ineligible profiles remain visible with disabled selection and a precise reason (missing
key, unsupported task adapter, expired price or revoked connection). No fallback provider
or substituted model. Support one or multiple compatible selections.

Run controls: one trial/profile in V1, explicit aggregate API cap (blank initially),
per-model token/time limits within service bounds, sequential execution and exact task
version. Show maximum call count and conservative group reservation before launch.
The task's fictional environment budget is never an API spending budget.

Check readiness is read-only and makes no inference request. It shows credential presence,
adapter qualification, model/parameter binding, current pricing, rights, runtime admission,
exact user authority, real approvals and shared budget. Launch is disabled while any gate
is missing. This spec adds no new approval roles and removes none of Anvil's existing gates.
Configuration Admin privileges do not imply access to private task references.

### S4 — Run group and model comparison

Each row shows profile/provider/exact model, execution state, task outcome, completed stages,
latency, model-reported usage and cost provenance. Distinguish Reserved / Estimated /
Known reported / Settled / Unknown. Unknown values are null, never zero.

Execution state: blocked, queued, running, completed, refused, truncated, failed-operational,
cancel-requested, cancelled, execution-unknown. Task outcome is separately pass/fail/unscored
or awaiting review. A task failure can be a successfully completed execution. An operational
failure is not a model score of zero. Partial groups display each child's actual state.

Select a model row to inspect its trajectory. Cancel is best effort and preserves any
ambiguous dispatch/reservation. A new attempt is an explicit new run with lineage, fresh
readiness and spending admission; no automatic retry button silently resends an unknown call.

### S5 — Model trajectory and evidence (detail of S4)

An ordered, timestamped event list: task context revealed → dispatch intent → provider
request sent → final output/refusal/error captured → constraint verification → state update
→ next stage or terminal outcome. Select an event to see permitted evidence:

- Actor-visible instruction, revealed evidence and state snapshot actually supplied.
- Exact sanitized request artifact/hash, model settings and bounded final-output text/JSON.
- Provider request ID, returned model ID, finish/refusal/error code, timing and usage.
- Stage diagnostics and evidence-linked task outcome, without exposing private references
  to roles that cannot already read them.
- Cancellation, unknown-dispatch and manual reconciliation events with cost provenance.

No hidden provider reasoning, private chain-of-thought or reconstructed explanation is
shown. Future-stage observations appear only after their actual reveal event. Actual final
output is not replaced with a repaired JSON object. Sanitization/preview truncation is labeled.
Exports: redacted JSON trajectory, CSV comparison and evidence ZIP/manifest, subject to
project/rights permissions. Credential material and authorization headers never enter them.

## 4. User journeys

### J1 — Admin configures models once

Sign in → Settings → Models & keys → Add model → select provider and exact model ID →
choose/create credential → set supported limits and current price metadata → Save →
Check configuration → enable for selection when qualified. Repeat for other profiles.
Same-provider profiles may reference one explicit credential; cross-project sharing is
never automatic. Changing model/settings/pricing/credential version creates a new revision.

### J2 — Praxis export to a model run

Praxis project → Tasks and invites → download its Anvil JSON (for current synthetic
examples: **Download synthetic draft for Anvil qualification**) → Anvil Build → Praxis →
Harbor → upload exact JSON → inspect actor view/source receipt → build package → select
configured models → set explicit API limits → Check readiness → resolve displayed gates →
explicit Launch → open per-model trajectory. Source review never becomes Anvil approval.

### J3 — Understand why a model failed

Run group → select a model → open failed stage → compare actual output against the visible
constraint diagnostic → inspect preceding revealed context/state → download permitted
evidence. For provider refusal/timeout/invalid configuration, show execution/error evidence
separately; do not fabricate task scores or causal claims. Unknown dispatch holds the cap.

### J4 — Rotate or disable a key

Admin → Manage key → supply replacement privately → create version → check configuration →
create a new profile revision. Existing run bindings remain immutable. Disabling a
credential blocks new dispatch and is rechecked between stages. An already dispatched call
cannot be recalled. Retain its accounting/history; secret cleanup does not erase run proof.
Revocation at the provider and snapshot-aware rotation remain explicit operator actions.

## 5. Secret storage proposal and decision boundary

**Proposed for review:** a server-side `CredentialStore` interface backed by Google Secret
Manager on the existing deployment. PostgreSQL stores project-scoped opaque references,
versions, owner/audit metadata and status, never plaintext API keys. A narrowly privileged
credential-writing boundary creates versions; the execution mediator reads only permitted
provider secrets. Do not grant project-wide access to unrelated database/identity secrets.
Exact service-account/resource permissions require an implementation security review and
separate authorization before creation. No new IAM/resources are authorized by this spec.

The current API's read-only file mounts cannot implement secure key entry by themselves.
Do not make those mounts writable to solve this, store plaintext keys in ordinary CRUD,
or claim the deployed file-based preparation already supports UI key management. Existing
operator-managed file credentials remain a clearly labeled compatibility mode with explicit
project mapping. A secret backend failure leaves the previous version untouched and the
new profile unavailable; never acknowledge a partially stored credential as usable.

Credential writes require Admin, project scope, recent real reauthentication, HTTPS, CSRF,
strict payload limits and no-store responses. Redact credential request bodies and headers
from access/error/validation/APM logs, traces and audit events. Validation errors must not
echo submitted key input. API responses return metadata only. Frontend refresh cannot
retrieve the submitted key. No key is passed into Harbor, candidate environment variables,
task packages, output artifacts or observable trajectories.

## 6. Proposed data and API contract

Reuse versioned `connections` for exact provider configurations. Add profile identity and
revision links rather than overwrite old rows. Add project-scoped credential metadata
(opaque secret-store version reference only), enable/revocation audit events and adapter
qualification records scoped to provider/model/parameters/task binding/adapter digest.
Existing `provider_approvals` continue to bind exact immutable subject hashes.

Add a lightweight `harbor_run_group` parent and model-profile-version bindings, each linked
to the existing Harbor plan/check/job/call/artifact records. Reuse the existing shared
spend window/reservation ledger. Add immutable observable call request/response/revealed-state
artifact references and ordered event records; PostgreSQL remains canonical. Neo4j remains
an optional rebuildable projection, not a log or secret store.

Proposed project-prefixed routes (names are design, not implemented endpoints):

| Operation              | Route                                                                          | Result                                                       |
| ---------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------ |
| List profiles          | `GET /model-profiles`                                                          | All visible profiles/versions, pagination, readiness reasons |
| Create/edit-as-version | `POST /model-profiles`, `POST /model-profiles/{id}/versions`                   | Immutable configuration digest                               |
| Save/rotate key        | `POST /provider-credentials`, `POST /provider-credentials/{id}/versions`       | Metadata only, write-only secret payload                     |
| Check configuration    | `POST /model-profiles/{id}/check`                                              | No automatic inference; explicit check type/provenance       |
| Disable profile/key    | `POST /model-profiles/{id}/disable`, `POST /provider-credentials/{id}/disable` | Audit event; no historical-row deletion                      |
| Prepare group          | `POST /harbor-run-groups`                                                      | Exact profile/task versions and conservative bounds          |
| Readiness/launch       | `GET /harbor-run-groups/{id}/readiness`, `POST /harbor-run-groups/{id}/launch` | No inference on GET; idempotent explicit launch              |
| Monitor/evidence       | `GET /harbor-run-groups/{id}`, `GET /harbor-checks/{id}/events`                | Paginated ordered events and permitted artifact references   |
| Cancel                 | `POST /harbor-run-groups/{id}/cancel`                                          | Best-effort, cost/unknown state preserved                    |

Existing `/providers` and single-model Harbor routes need a documented compatibility path;
do not silently change their response shape. IDs are opaque and tenant-scoped. Cross-project
substitution returns denied/not found. Body secrets are never idempotency response content;
store only a keyed digest/operation reference for credential-write deduplication, not the
plaintext body. Same-key replay cannot create extra secret versions or paid requests.

## 7. Execution and spending behavior

Qualify each provider separately for these Harbor adapters. Existing SDK mocks are not
proof of Harbor live compatibility. Use native provider-specific output/usage/error mapping;
do not assume identical JSON/temperature/reasoning parameters. Unsupported capabilities
fail before reservation/dispatch, with a visible reason. V1 retains the service limits of
32768 actor-prompt UTF-8 bytes,2048 output tokens and one request per admitted stage unless
a separately reviewed adapter revision establishes different bounds.

At group launch, revalidate all model/task/credential/adapter/pricing/rights versions and
required real approvals. Atomically reserve the full conservative group ceiling within the
same global authority window; selected models cannot each obtain an independent copy of
the cap. Allocate per-child/per-call reservations without double counting. Queued runs
recheck current revocation/expiry before dispatch. Persist dispatch intent before network
I/O; configure SDK retries to zero. Capture usage conservatively, retain unknown reservations
and reconcile only with supported evidence. No silent model substitution or request retry.

Reference/no-op/negative checks are separately labeled synthetic verification and never
enter model comparisons as measured model performance. Failures, refusals, cancellations,
unknowns and ungraded outputs remain visible in denominators and exports.

## 8. Acceptance and implementation sequence

1. **Design review:** confirm screens, multi-model grouping, secret-store choice and V1
   provider scope. Current delivery ends here; no application implementation yet.
2. **Registry/secrets:** versioned metadata, write-only secret boundary, roles/isolation,
   rotation/revocation, no-secret-response/logging tests. Keep live switches off.
3. **Adapter qualification:** independent OpenAI/Claude/Gemini mock and sandbox contract
   tests for structured/staged tasks, bounds/refusal/usage/unknown/no-retry behavior.
4. **Harbor group/observability:** reuse worker/ledger; implement event and artifact binding,
   deterministic local stubs, explicit cancellation and evidence exports.
5. **Integrated release:** genuine OIDC browser journeys, unit/integration/build/restore and
   project-isolation tests; deploy disabled to existing target only if separately authorized.
6. **Optional live qualification:** later exact provider/model/budget/price/rights/keys and
   real application approvals, explicit bounded launch. Never infer this from design approval.

Required acceptance checks:

- Admin can create at least two profiles for one provider plus Claude and Gemini profiles;
  reload retains exact versions and project visibility. Existing rows remain intact.
- Save/rotate/revoke operations reveal no key in any response, error, log, trace, browser
  storage, package, trajectory or export; cross-project references and CSRF attacks fail.
- Only qualified, enabled, credential-present compatible profiles can be selected. Current
  pricing expiry and exact run readiness are separately visible; blank/default-free budgets.
- Select two profiles for one package; receive two child executions with the same task
  version and independent outputs, under one atomic cumulative cap. Concurrent launches
  cannot duplicate capacity. Replays do not duplicate requests or secret versions.
- Observable trajectory matches actually supplied actor context and raw final output;
  future/private evidence and hidden reasoning are absent from unauthorized views.
- Success, task failure, operational error, refusal, truncation, cancellation and ambiguous
  timeout produce distinct correct states. Unknown cost stays unknown and held; no retries.
- Key/profile/rights revocation between stages blocks the next dispatch. Rotation does not
  rewrite a previous run. Server restart recovers without re-invocation.
- Redacted JSON/CSV/ZIP downloads preserve source provenance, versions, partial/unknown
  outcomes and hashes. Keyboard,320/768/1440px and light/dark layouts remain usable.

## Review decisions

Proposed defaults: official APIs only; multiple profiles/provider; one or more selected
models with sequential child runs; one trial/profile; no API spending defaults; write-only
Admin key entry through the reviewed secret store; existing Anvil paid gates unchanged.
Provider model IDs, current rates/caps, credentials, new IAM and activation are intentionally
unselected. No design checkbox is evidence of real authority or live qualification.
