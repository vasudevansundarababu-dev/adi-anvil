# KYC technical-probe permission layer — 18 November 2026

Local source candidate only. No live model/Authoring calls, new QA permission
records, actual native Trial or runtime qualification were created by this change.

## Implemented

TechnicalProbeStore is separate from the existing role/business/paid admissions.
It validates operator-private plan files pinned to one QA host/kernel domain,
exact source dependencies and asset bytes, the fixed two-read request, zero
authorized model calls, short expiry and bounded lifecycle/cleanup caps. No prior
passed-qualification claim is needed merely to describe a technical probe plan.

Actual QA permission requires physical root custody at the fixed QA proof path,
not a caller-controlled scope label. Local fixtures retain owned_test_NOT_QA and
cannot authorize execution. Runtime-seal/role/image/mount asset *semantics* still
require the future owner preflight; matching hashes alone do not establish those.

Entry no longer accepts a caller's framework UUID dictionary. It reads owner-only
framework entry and process records from the exact nonce-bound attempt directory,
checks the live kernel PID/start/domain, target PID/user namespaces, interpreter
bytes and exact command line, then writes a durable O_EXCL intent. Replayed entry
cannot overwrite an intent. This ledger itself starts no subprocess or business
factory. It must be integrated with the actual owned native Trial lifecycle.

Outcomes distinguish model_calls_authorized=0 from actual_model_calls=null.
An opaque evidence hash remains evidence_reference_verified=false; observed or
unknown is never passed qualification. Unknown outcome recording can survive
permit expiry without granting more time or replay. Fixtures are explicitly
labelled by custody scope. Neither entry nor outcome grants business dispatch,
paid authority or native_trial_qualified.

## Verification

- 15 focused manufactured-plan controls: local custody/changed scope label,
  future/expired plans, paid request, expanded actions/scope, foreign host,
  changed source/assets, predeclared qualification, caller framework dictionary,
  target namespace mismatch and one-shot unknown outcome/replay semantics.
- Full local units: 1097 passed, 1 Linux-specific skip, 10 subtests passed,
  133.06 seconds. Log .local/kyc-probe-plan-units.log.
- Fresh/repeated-schema SQL: 30 passed, 109.91 seconds, source unchanged at
  d5e5303a9ba6514439031037e94effff6f8c0f82220c9141f0e39832e3f41c60.
  Log .local/kyc-probe-plan-sql.log. Disposable database retained; container stopped.
- Scoped Ruff and whitespace checks passed. Read-only independent source review
  found no remaining material ledger defect within this preparation scope.
- Shared operator source pin:
  477361b506ac914daef4793638f09c11ad6d5232e907109e4e5a6fdc672c9b7d.

These are software regression controls. They are not installed native qualification
or positive physical validation of a completed probe owner.

## Still required

Integrate the permit with the root-owned native Trial owner and actual framework
process receipt producer; validate all semantic assets before effects; execute
actual normal/crash/reset/MCP/checkpoint/role/mount/scoring controls and independently
review their current-source/image evidence. Existing closed gates remain closed;
this class is not wired as an execution bypass.

Policy review resolution/provisioning and genuine domain/source/rights decisions
also remain unfinished. KYC v7 stays unchanged, registered and blocked. Captured
federal text and pending state/charter artifacts must not be bound to v7. Any new
execution binding belongs in an explicitly reviewed successor such as v8.

The handoff requirements and current/proposed APIs are documented in
docs/product/27-AUTHORING-FORGE-EXECUTION-HANDOFF.md. All 23 updated evidence-bundle
payload hashes verify; sorted-ID population hash c77748bc...e08aa now verifies
using Authoring's explicit RFC8785 definition. No approval status was changed.
