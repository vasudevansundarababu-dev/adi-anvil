# Remaining exact-binding qualification work

Status: engineering inventory and proposed implementation sequence, not a
qualification receipt. User authorization: finish Gym setup and test QA without
model calls. Runtime dde352b and UI5bdfc5d are deployed. Current B1 is
4df5e92a-4815-4efb-9267-faf88c9e6990; it is preparation only.

## Evidence boundary

The installed component receipt proves generic no-model runtime controls.
`kyc_policy_provision.retain_runtime_review` consumes a passed control bound to
runtime source/image, environment manifest and evaluator inventory hashes.
`infra/gcp/qualify_native_components.py` does not currently produce that record.
Do not inject a new field into an existing trusted receipt or copy a synthetic
fixture's review row into this project.

An exact-binding producer must load the authoritative stored scope via
`golden_kyc_resolved_store.policy_scope`, derive `runtime_subject`, verify the
registered import with `golden_kyc_anvil.validate_software`, and inspect actual
saved configurations. It must check source membership, B0/input/B1 ancestry,
environment/tool/reset contracts, resource identities and all evaluator targets.
It may reuse independent physical evidence only when the actual implementation
and configuration are proved equivalent to those tested. Changed executable
code or behavior requires new physical controls.

Run pass/fail/missing observations through each exact supported saved evaluator
configuration. Retain immutable observations, artifact/validation identities,
component receipt hash and expiry. Publish only after independent verification.
Keep private expected outputs inaccessible to ordinary API/scheduler roles.

Important limitation: the current default `_evaluators()` registration uses a
generic `supported == True` rule. Adapter operation is not proof of substantive
KYC correctness. A binding-integrity control must not claim that80 task criteria
are meaningfully graded merely because their IDs and hashes match.

## Other exact-scope producers

* `task_capability_qualifications`: a reader/schema exists; no production Python
  producer was found in the reviewed source tree. Implement actual bounded
  method capability controls and immutable publication tied to task/source/release.
* `task_safety_source_qualifications`: same producer gap. Qualified source and
  exact category/prompt configuration remain required. Manual draft/import
  endpoints can stage prompts; a draft is not qualified safety evidence.
* Typed diagnostic configurations and `/test-diagnostic-runtime` already exist.
  These manufactured measurement controls are no-provider software evidence;
  they do not replace exact task capability or deployment qualification.

Tests for each producer must reject wrong hashes, cross-project artifacts,
changed selections, stale runtime image/source, expired or revoked evidence,
missing/ambiguous targets, unsupported configurations and partial observations.
No model call is needed or authorized for these controls.

## Configuration and review

Inspect actual public S5 step pointers/roles from `workflow_step_options`. The
design register's `design_step` is a descriptive label, not an exact pointer.
Prepare a justified mapping matrix; do not map every skill to every step or infer
associations from label equality. Fixing the v8 viewer makes the supplied steps
visible but creates no mappings or source changes.

Prepare all method/diagnostic/safety/policy selections before a new B0. Rebind
the existing input population and prepare packages, then append package-only B1.
Preserve all previous preparations and immutable task/template versions.

Policy provisioning additionally requires actual owner decisions for the20
staged subjects, plus real restricted qualifier enrollment (current count0).
The one-day interval decision is not approval of policy contents. Rights and
case-expectation reviews remain pending; the child dataset has0 installed
expectations. No supplied artifact or software result may approve itself.

Studio prevention: expose complete producer/configuration/review prerequisites
before a template can be advertised as execution-supported. Return structured
Gym-owned gaps separately from Authoring conformance and never ask for a task
re-export to compensate for an absent Gym qualification producer.
