# KYC v7 benchmark readiness — 18 November 2026

## Actual QA result

Registered under the user's signed-in Admin session through the existing API.
Actual table and independent read-only SQL confirm template6d8f9cae-7c06-4c36-a207-522978d5486b,
version7, canonical SHA c8c4eddfed5d018f69a739bc0280538dd5011ce79d4e52ede77f6e101f248a8d.
Actual qualification POST returned blocked:
AV_ENVIRONMENT_PROVISIONING_REQUIRED, REVIEW_PRAXIS_PUBLICATION;
conformance origin installed_golden_qualification_missing with
independent_paid_runtime_qualification_required (legacy reader fallback label).
No paid call is authorized or needed merely to replace that fallback with genuine
non-spending component evidence. No bindings, fabricated approvals or runtime
qualification installed. Existing projects/model selections preserved.

QA frontend now e0ec104, image6c95aa0a933d13026279cd5f03464a55f9fbd5e671e99f0a9d6b0f15fd7700e6,
Cloud Build20506c05-d383-4da7-8a14-353886aadbb8 SUCCESS. Web-only rollback config
/var/lib/anvil-qa-v1/backups/template-ui-e0ec104-20261118 retained. Backend remains818afca.
Actual workspace/health200, correct dataset-exports/generic/templates anonymous401,
bundle markers and unchanged other-service config PASS. Earlier8ac1169 deployed
wrong route prefix; initial smoke422 retained as failure, fixed in e0ec104 after
confirming actual deployed OpenAPI. Corrected local browser journey PASS3.9s.
Screenshots .local/kyc-v7-qa-qualification-full.jpg. No live model/Authoring calls.

Status: template registration COMPLETE; runtime qualification BLOCKED; task import/
bindings/benchmark readiness NOT COMPLETE. Remaining code work is explicit below,
not represented as an external permission issue or a passed test.

User authorizes registration, non-spending runtime qualification and bindings;
model selection remains with the user. No live model or Authoring calls authorized.

## Verified input and installed state

Full KYC specification parses against current TemplateSpec. Canonical hash
c8c4eddfed5d018f69a739bc0280538dd5011ce79d4e52ede77f6e101f248a8d
matches the task ZIP and supplied publication record; authoring/execution/skills
part hashes match. Template6d8f9cae-7c06-4c36-a207-522978d5486b version7.
Offline publication JSON explicitly has no RL Gym qualification receipts and is
informational; it must not be recorded as authenticated publication evidence.

Actual QA read-only preflight: no registered rows for that template; installed
component reader ready=false, missing independent_paid_runtime_qualification_required
(legacy full-reader fallback; this does not authorize running a paid call).
Installed Golden source280e925c934303a541657829164948893f5312183cad209e9d9dcc59eddde3b7.
Generic export enabled, Authoring template calls disabled, live model calls disabled.

## Work required before genuine readiness

1. Register exact supplied spec via real signed-in Admin route. Additive UI now
   uses existing POST generic/templates and displays canonical registration hash.
2. Acquire authenticated publication provenance through the existing trusted
   server path; the offline information record cannot satisfy this.
3. Implement and physically verify actual Trial operation admission/lifecycle:
   environment_harbor.fixed_trial_gate unconditionally closes entry;
   OperatorProofStore derive/derive_operation return authorization=false.
4. Complete genuine anvil_kyc_qualifier-owned policy qualification/materialization
   provisioning; current production readers have no corresponding owner producer.
5. Earn ten exact-source/image component controls plus four product controls:
   kyc_product_routing, all_original_rows_conserved,
   per_application_policy_registry, shared_task_evaluator_binding. Unit fixtures
   and self-written status booleans cannot serve as installed evidence.
6. Resolve the approved pilot task coverage: supplied ZIP has one individual-product
   workflow; existing paid product-taskset path requires four distinct product
   packages. Do not fabricate tasks or silently change this coverage rule.
7. Only after qualification/import, bind exact source policies, input/environment,
   evaluators and safety references; complete actual required rights/review gates.
   Then user selects model/version/credential and an explicit spending ceiling.

No claim of Ready to Run. No missing evidence replaced by fabricated approval,
fixture performance, seeded-account switching or relaxed authorization.

## Local UI verification

New template registration/qualification controls: production build PASS; Chrome
synthetic journey PASS (1 test3.9s), including registration response, nested actual
qualification envelope and blocked requirements. Existing32-model bulk and desktop/
mobile search checks pass. QA frontend build292a696e-6dd5-4b73-bdb1-06e00532642d
submitted after user refreshed GCP authentication; deployment pending.
