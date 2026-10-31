# Admin workspace and framework configuration

Status: combined design approved; autonomous local implementation launched 30 October 2026.
Target specification, not a claim of full delivery. See [build status](../../BUILD-STATUS.md)
and the [nightly implementation plan](../build/08-MODERN-WORKSPACE-NIGHTLY.md).
Extends [model configuration/run observability](20-MODEL-CONFIGURATION-AND-HARBOR-OBSERVABILITY-SPEC.md).
This proposal supersedes its role/navigation layout: **Admin includes every RL Engineer
capability**, plus administration. There is no role switcher or requirement to sign in
again to move between administrative setup and engineering work.

## 1. Two product profiles

| Capability, within assigned projects                                     | RL Engineer | Admin |
| ------------------------------------------------------------------------ | ----------- | ----- |
| Import/create tasks and inspect permitted task evidence                  | Yes         | Yes   |
| Select available models and qualified framework combinations             | Yes         | Yes   |
| Prepare/launch/cancel evaluations within authorized limits               | Yes         | Yes   |
| Inspect results, failures, observable trajectories and permitted exports | Yes         | Yes   |
| Configure model profiles and credentials                                 | No          | Yes   |
| Configure framework profiles and workspace defaults                      | No          | Yes   |
| Manage people/project access and allowed-model policies                  | No          | Yes   |
| Manage spending limits, data-export policy and audit views               | No          | Yes   |

These are two proposed product profiles, not a current backend permission migration.
Implementation must map existing grants and historical approval evidence explicitly.
Admin's engineering capability does not disclose a model's hidden reasoning or override
project isolation, data-use restrictions, spending authority or ambiguity handling.
Where independent real-person decisions remain required, they use distinct identities
within the permitted profile; do not recreate PO/PM screens as extra navigation roles.
Any change to those policies is an explicit design/implementation decision, not implied
by a broader navigation menu. No current permission or spending gate changes in this draft.

## 2. One workspace, two navigation groups

Common workspace: **Overview · Tasks · Runs**. Results/comparison/trajectories are children
of Runs, not extra top-level modules. Praxis is an import source within Tasks. Harbor is
one configured execution option, not the product's only navigation identity.

Admin-only group: **Models & keys · Frameworks · People · Limits & usage**.
Audit/activity is contextual within these pages rather than another mandatory workflow.
Keep project context and account identity visible. Do not show single-choice pickers or
duplicate settings menus. Advanced fields remain collapsed until needed.

Admin's initial Overview is a short setup checklist: add models, configure frameworks,
add engineers and set limits. It also links directly to Tasks and Runs. After setup,
Overview can prioritize recent work and actionable failures instead of repeating setup.
No fabricated usage/performance counters or ornamental dashboard cards.

## 3. Models & keys

One row per friendly profile, provider/exact model ID, credential presence and availability.
Support multiple profiles per provider and deliberate sharing of a credential within its
permitted project. OpenAI, Anthropic Claude and Google Gemini are the initial provider
choices; actual model IDs, prices and credentials are entered explicitly later.

Primary action: Add model. Editor: provider, friendly name, exact model ID, choose/create
credential, project scope, supported limits and current pricing. Masked write-only key
entry, rotation/version metadata and server-managed secret references follow spec20.
No plaintext key read-back, reveal control, browser storage or key-in-log behavior.

States must distinguish Draft, Key missing, Configuration valid, Adapter not qualified,
Disabled and Available for planning. Run readiness remains a separate exact-run check.
Save does not invoke a model. The review prototype accepts no real key at all.

## 4. Frameworks are typed integrations

Frameworks do not all perform the same function. A profile can expose several separately
qualified capabilities; the run uses a compatible composition rather than one untyped
framework name that silently changes the entire execution path.

| Integration     | Proposed supported role                                                    | Anvil status at this design                                                                          |
| --------------- | -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Harbor          | Evaluation execution/sandbox runner                                        | Existing pinned0.25.0 structured/staged software-check path; paid model qualification still separate |
| LangSmith       | External tracing; optional evaluation backend in a later qualified adapter | Design candidate; no configured destination/key, no trace transmission                               |
| Semantic Kernel | Candidate-agent/runtime orchestration SDK                                  | Requested design candidate; no SDK installation, adapter or live compatibility claim                 |
| LangGraph       | Existing Anvil durable platform orchestration                              | Platform core; PostgreSQL/checkpoints/spending/audit remain owned by Anvil                           |

Source basis, checked for this design:

- [Harbor documentation](https://docs.harborframework.com/) describes running agents/models
  against tasks and datasets in sandboxes. This does not prove every task or model is
  supported by Anvil's narrower currently qualified adapters.
- [LangSmith documentation](https://docs.langchain.com/langsmith/observability) describes
  tracing, performance visibility and integrations, plus evaluation/platform capabilities.
- [Semantic Kernel's repository](https://github.com/microsoft/semantic-kernel) describes a
  model-agnostic agent orchestration SDK and now points to Microsoft Agent Framework as
  its successor. Keep Semantic Kernel as the user's explicit compatibility option; do not
  silently substitute the successor. Decide the desired SDK/migration target before coding.

## 5. Framework configuration screen

Primary list: friendly profile name, framework, role(s), deployment mode, pinned adapter/
runtime version, connection state, qualification and allowed-project scope. Configure
opens a focused side panel, with provider-specific inputs and a collapsed Advanced section.

**Harbor:** existing Anvil worker/local sandbox option, pinned runtime/adapter, supported
task bindings, allowed model profiles, concurrency/time bounds and artifact destination.
The existing local Harbor runner does not require a hosted Harbor API key. A hosted runner
would be a separate future profile with its own destination, credential and qualification.

**LangSmith:** approved service/deployment/region, workspace/project reference, separate
LangSmith credential reference, tracing policy and retention metadata. Default export off.
Metadata-only export is the initial proposed policy; sending prompts/outputs needs explicit
data-use authorization and redaction configuration. No key reuse from model providers.
Local Anvil trajectories remain available when an external tracing connection is absent.

**Semantic Kernel:** reviewed server-managed SDK and pinned version, registered agent
adapter, supported task modes, compatible model profiles and limits. It uses selected
model credentials through Anvil's trusted mediation boundary; there is no universal
"Semantic Kernel API key". Arbitrary plugins/code or repository URLs are not executable
configuration. Native SDK provider connectors cannot bypass Anvil's spending broker.

**Add framework:** choose from registered reviewed adapters, or record a request for a new
integration. Saving an entry never downloads/runs a package or grants an arbitrary endpoint
network access. Unknown adapters remain unavailable for engineering runs until qualified.

Local configuration validation is separate from explicitly requested external connectivity
checks. No automatic generation ping, test trace upload or trace-content export on Save.
Never label an uninstalled adapter Connected merely because its metadata was saved.

## 6. Compatible workspace defaults

Admin can prepare named execution presets containing model-profile allowlists, evaluation
runner, candidate-agent runtime and optional tracing/evaluator. Each component is optional
only if the qualified pipeline supports its absence.

Initial existing composition: Harbor evaluation runner and Anvil structured candidate agent,
with Anvil/LangGraph durable platform orchestration and local evidence. LangSmith tracing is a
separate opt-in integration. Semantic Kernel candidate orchestration is a proposed additional
agent adapter; it does not replace Anvil's durable authorization or ledger ownership.

Compatibility is versioned and checked by adapter, task binding, provider/model parameters,
data destination and resource limits. Harbor + Semantic Kernel, or a LangSmith evaluation
backend, are not promised merely by adding their names to this design. Show the missing
adapter/qualification reason. Record exact selected versions in each immutable run manifest.

RL Engineers and Admins use the same preset/model picker in Tasks → Run evaluation.
Incompatible or disabled options are visible with reasons. Readiness collects missing
configuration, data-use permissions, current cost/authority and applicable real decisions
in one place. Do not scatter the same requirements across repeated forms.

## 7. People and limits

People offers only Admin and RL Engineer product-profile choices, explicit project scope,
invite/disable actions and audit history. Admin already includes engineer work; do not
create duplicate accounts or assign a second visible role to achieve that. Existing user
history and grants require a reviewed migration; the prototype sends no invitations.

Limits & usage groups allowed models/presets, per-evaluation and workspace API caps,
concurrency and tracing/data-export policy. Money fields begin blank; examples are not
authority. Model generation, evaluator/judge calls and external service/storage fees must
have distinct cost provenance; external tracing is not assumed free. Preserve unknown
cost and held reservations. Policies describe permitted envelopes, not silent live launch.

## 8. Admin journeys

1. Sign in → Overview → Models & keys → configure model profile/credential → inspect
   local validation and qualification → enable a permitted profile for selection.
2. Frameworks → select registered integration → configure only its applicable inputs →
   inspect compatibility/privacy → prepare workspace defaults. No model request or trace
   upload is made just by saving configuration.
3. People → select RL Engineer or Admin → project scope → explicit invite through the
   real identity flow. No manufactured identities or automatic privilege promotion.
4. Limits & usage → explicit model/preset/cost/data-export policy → review effective limits.
5. Without switching roles, Tasks → import Praxis JSON → build/inspect task package → Run
   evaluation → select profiles/preset → check exact-run readiness → explicit authorized
   launch → Runs → outputs/failures/observable trajectories and permitted exports.

## 9. Architecture and safeguards for later implementation

Keep PostgreSQL canonical for profiles, versions, run manifests, audit and reservations.
Extend existing jobs/checks/calls/artifacts; no parallel unaccounted framework runner.
Framework credentials use the reviewed secret-store boundary in spec20. Candidate workers
receive scoped ephemeral mediation tokens, not raw provider/framework credentials.

Tracing exports use a redacted, versioned event schema, destination allowlist, project scope,
data-use permission and idempotent event IDs. Never export hidden references, future
observations, raw credentials or private model reasoning. External-tracing failures are
reported as degraded tracing and never retry a paid model call or lose local execution proof.
Evaluation services that issue model/judge calls must use an admitted spending adapter;
turning on a tracing profile must not implicitly turn on generation or online evaluations.

Framework updates create reviewed versions. Revocation blocks future dispatch; in-flight
requests preserve cancellation/unknown semantics. An Admin cannot install arbitrary SDKs
from the web UI. Preserve tenant/project isolation, no automatic inference retries and
atomic cumulative spending across all selected components.

## 10. Review and acceptance before implementation

- Approve Admin-superset/RL Engineer profile model and the shared/common navigation.
- Approve framework capability taxonomy and decide Semantic Kernel versus explicit
  Microsoft Agent Framework successor support; record both separately if both are wanted.
- Review secret backend/IAM, permitted destinations and tracing-content policy before
  provisioning. No new SDKs, secrets, identity grants, IAM, paid activation or deployments
  are authorized by a design checkbox.
- Test metadata save/reload, multiple models/framework profiles, missing credentials,
  incompatible versions, disabled selections and a clear first-run setup journey.
- Test role/project boundaries and Admin's complete engineering journey without role
  switching. Preserve meaningful historical identities and immutable run evidence.
- Confirm real connection/model qualification independently. Prototype statuses and
  simulated checks must never become live performance or compatibility claims.

At design delivery, the output was the clickable concept and specification only. The later
user launch authorizes local implementation on a separate branch; production remains
unchanged. Live switches and real spending controls remain enforced.

## 11. Task history, run diagnostics and comparison — design extension

User requested on 30 October 2026: each task has its own run history; each run exposes
results, failure modes, observable trajectories and its bound task/rubric/evaluations;
metrics can be compared across runs. This extends the shared Admin/RL Engineer workspace.

Journey: Tasks → task detail → Run history → run dashboard → result → trajectory/evidence.
Run history is attached to the stable task identity and includes all permitted versions.
Rows show run/model/configuration, task and rubric versions, start time, lifecycle state,
score and denominator, outcome counts, coverage and known/unknown cost. Project-wide Runs
is a second entry point to the same run details, not a separate result store.

Run detail tabs:

- Dashboard: score, pass rate, coverage, rubric aggregates, cost completeness and attention
  items. Every metric links to its contributing outputs and evaluation provenance.
- Results: all attempts, including unscored, canceled, errored and unknown outcomes;
  status filtering; output, grading evidence and trajectory drill-down.
- Failure modes: separate task failures, execution errors and unresolved dispatch.
  Deterministic findings, grader findings and hypothesized causes are explicitly distinct.
- Trajectories: ordered observable context, model/tool calls, outputs, runner events and
  evaluator evidence with timestamps, source and permitted artifacts. No hidden reasoning,
  hidden references, future-stage observations or secrets in unauthorized views.
- Task & evaluations: immutable task/package snapshot and content hashes, rubric weights
  and thresholds, checks, grader/agent configurations, protocol, sampling and exact model,
  adapter, runtime and dataset versions used by that run. Access restrictions still apply.
- Usage: candidate/judge/tool usage, durations, reservations, known charges, pricing
  provenance and unknown amounts. Missing usage is never displayed as zero cost.

Comparison starts by selecting two or more history rows and choosing a baseline. Show
scores, per-criterion metrics, pass rates with denominators, coverage, task failures,
execution errors, unknowns, latency, tokens and cost completeness side by side. Compare
matched attempts where meaningful; expose task/rubric/protocol/dataset, grader/model and
sampling differences. Different task/rubric/scoring versions are descriptive comparisons;
disable score deltas/rankings until comparability is established. Never imply significance
from a small sample; future confidence intervals require a specified method and sample.
Fixture and real performance cohorts cannot be pooled into a performance claim.

Recommended editing direction, still a design decision: keep run snapshots read-only;
an “Edit as new version” action opens a dedicated editor initialized from that snapshot.
Task, rubric and evaluation changes become linked drafts with a before/after diff. Saving
a draft does not change history, activate a configuration or dispatch a run. Re-run opens
preparation with the selected immutable versions; it is never an implicit retry.

Prototype uses fabricated, clearly labeled examples only. Production implementation,
pagination, cancellation/running/empty states, complete comparison eligibility checks and
the final editor design remain future work. The preview is not a performance report.
