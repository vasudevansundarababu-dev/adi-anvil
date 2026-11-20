# KYC v8 technical reference action — 20 November

Scope: explicit Admin UI access to the existing four-product software-reference
registration API. No TemplateSpec, authored ZIP, backend/runtime image, policy,
dataset context, approval or run contract changes. The local diagnostic backend
patch is separate and must NOT enter this web-only build or deployment.

## Diagnosis and measured baseline

Project `a7454c18-602e-4907-bdd9-277067c36233` has zero `banking.anvil_imports`.
The existing UI omits task_mode, which defaults to reusable_state_workflow;
KYC v8 needs reusable_application_workflow. Exact v8 tools (including complete
tool schemas), 20 criteria, seven rule hashes and product selector match the
implemented adapter. Its accepted offline PO attestation is not repeated.
The generic adapter_not_supported error masks the missing project import.

Existing control pack: `7e17aa6b-4a23-4abc-a28f-f4ba97186c2d`,
golden-kyc-1.0.0, seed20261111, original_constraint_generator,
synthetic_software_fixture_not_real_customers. Actual metadata query confirms
200 rows, four products, five states, all20 cells with10 members each.
Public population SHA `e8d5cb8b4c84ec58049bba9259a04662fef732b536d3663bcfdb425fb7f74653`;
bank policy SHA `2bcdb7b2656dea0840f5d862d9cd39d9ce3e63d8b29b59776483f803c114098d`;
canonical sorted id/snapshot-hash member-list SHA
`d0d4f74ee15cb1266cf19bf2fc5e833d3cceb88c583a37c752d603c23e714ec2`.
Resolved v8 input count0. Before-evidence local file:
`/private/tmp/forge-kyc-reference-before-20261120.json` (no private expectations).
Nov11 clock/context and every snapshot remain unchanged and unapproved for v8
benchmark execution. This is not the authored v8 project import.

## Existing serving pins, preserved by web-only rollout

Backend/runtime revision39cb2d96418fd029f7c87274941b00639d12d87a;
Golden source896b9c2b39b33ff45f75c989a73f11437abe0b00daa0932d0b639c5336a0e088.
Backend image41e94e67b009582338415f1f791655902f1fe42e2c97350b7faf7afb8083bf9c;
KYC image60c0e3298feccc3f87eb9ea0578b14c39633e4b0ed95640ca9e9fe254d70e2b6.
Current compose SHA2c2046ee44311b9478f008e5dbe75cbd1b6676082b386d9c6c11b761f9d1dcbc;
old web ID832c7a64b489e6765a3d681d322c8094a76f20540d66808fa394befc43d398f1,
imageb56385ca097d86e3413141465713d24d69deff5042acbdd3bac4a6b26b8a2b0c.
Component receipt3b2ae3bee8c472ec627a212c24350576ead069bbc09353c6d1106fb1bccbad0d
expires20Nov21:00UTC; capturebe7bb48642cb448877635a93d4900cd6e586fe3f0685877c142e20104203553a
expires21Nov01:13:03UTC. Recheck actual source, expiry and installed readiness
before qualification; never extend/reissue a review merely for the UI release.

Build immutable web image from a clean Git archive with the locked Dockerfile.
Pull/pin actual resulting digest, retain old config/identity, change only web
image and release label, recreate only web (--no-deps/--no-build), preserve all
other seven IDs/images/profiles, schema133 and qualification files. Confirm
HTTP/TLS and actual new UI. Roll back only owned web candidate to exact old
config/image if checks fail. No migration, runtime restart, prune or phase2/3.

## Explicit authenticated action and effects

Admin selects the displayed existing pack, then deliberately clicks
Register four-product software reference. Request:
`POST /api/v1/projects/a7454c18-602e-4907-bdd9-277067c36233/golden-banking/v1/anvil/import`
with `{pack_id: "7e17aa6b-4a23-4abc-a28f-f4ba97186c2d", task_mode: "reusable_application_workflow"}`.
Existing session, CSRF, Admin/RLS and Idempotency-Key controls remain unchanged.
No agent cookie extraction, seeded identity or direct-SQL impersonation. No
auto-register on render, refresh or qualify. No automatic retry after uncertain
mutation: reconcile the original idempotency receipt and registry records first.

Existing register uses a savepoint and before/after software-resource proof.
Expected writes: software task group/four product tasks, public environment
pack/version, four environment-task bindings, 50 deterministic evaluator
configurations+known-case receipts (20rubric/10business/10OPA/10trace), canonical
banking import and ordinary audit/idempotency records. Existing validated
evaluators can be reused; count/pin the actual references, not assumed inserts.
No pack/snapshot/private-expectation update, real v8 resolution/B0/input binding,
policy/legal/rights approval, command/job/run/plan/budget/provider operation.
No queue or model callback is invoked by register; software/model run controls
remain separate explicit actions. Paid/provider/Authoring flags remain false.

After one acknowledged registration, retain exact import/group/environment IDs,
source/mode/manifest/environment/population and50 evaluator+validation hashes.
Compare all200 before/after snapshot hashes and20 cell counts; ensure no commands,
execution jobs, v8 inputs or paid plans/runs were created. Then the real Admin
may check qualificationv8; pass must use actual current installed qualification,
exact reference import, evaluator integrity and existing PO publication basis.
Template qualification grants no run authority or data/legal approval.

## Explicit limits and deferred hardening

This existing contract has NO hard reference-purpose admission field. The UI
label and operational HOLD do not constitute such an enforcement mechanism.
Do not bind this control import as genuine v8 execution data or claim it is
qualified for that purpose. Real v8 dataset/context/private expectations,
policy/rights and run admission remain HOLD. Future durable purpose/provenance
fencing must cover same-pack aliases, SQL input insertion, historical/resumed
input readers and the early policy path; it is documented, not implemented here.
No re-authoring, template v9, changed v8 hashes or repeat PO attestation is needed.
