# Validation JSON and Anvil-owned setup — 21 November 2026

The owner directed Anvil to finish setup using the supplied approved tasks.
Missing Gym runtime/dataset/policy/evaluator bindings are not reasons to ask
Authoring to redesign a task or template. Approved task bytes remain immutable.
Pending-TIN verification remains outside the pilot scope; no TIN capability was
added, and no result may claim that verification was performed.

## Confirmed QA database diagnosis

KYC v8 is registered as `937a438d-aada-4f02-807f-d0a4ac36511b` with exact
template hash `8449adb0…34f7d5`. Its latest qualified receipt, created at
2026-11-21 03:36:06 UTC, records template source `8d06a090…c8a289`, Golden
source `4e53d1c1…f730f0`, runtime image `3640267a…71386` and review `234243b1…cf41de`.
The serving API reports template source `f77ee84c…d7b935`, Golden source
`c26a7965…01e4`, runtime image `cbd37c0a…4fe7c` and review `a94fa462…2a3bf`.
Installed component qualification is ready with no missing checks. The stored
template receipt is stale, so the registry rejects it and the validator returns
`AV_TEMPLATE_NOT_QUALIFIED`. This does not establish task conformance: content
checks behind this gate have not run. The four historical request IDs/bodies
were not recovered from this readback; do not invent their exact responses.

An initial unscoped API read could not see the row because engineer RLS requires
a user scope. The separate read-only operator registry query above confirmed the
row exists. An empty RLS result is not evidence that registration is absent.

## Candidate response contract

Existing fields and HTTP semantics remain unchanged. Additive fields include:

- `data.request_id`, matching `meta.request_id`.
- Exact original ZIP SHA-256 even when template qualification blocks decoding.
- `data.validation_report`: status, source verdict, task-conformance assessment,
  tri-state task-fix requirement, per-task Gym blockers, owner/message/fix,
  sanitized qualification reason codes, review gates and no paid authority.
- Separate `anvil_setup`: assessed via existing project-binding readiness when
  exactly one project-scoped imported group matches the exact package. It reports
  setup status/gap codes without dataset IDs, population counts, hidden cases,
  expected answers or private reference bodies.

`valid: null` means not assessed, never passed. `valid: true` reports source
conformance, not permission to run. Setup can be ready for Run configuration
while fresh model, rights, spending and dispatch controls still apply. All
responses retain `run_authority: not_granted` and `paid_calls: false`.

Example shape (request and package values are illustrative):

```json
{
  "data": {
    "valid": null,
    "status": "validation_blocked",
    "request_id": "request-id",
    "validation_report": {
      "verdict": "blocked",
      "task_conformance": "not_evaluated",
      "task_fix_required": null,
      "blocking_items": [{
        "code": "AV_TEMPLATE_NOT_QUALIFIED",
        "owner": "anvil",
        "stage": "template_qualification",
        "task_change_requested": false,
        "qualification": {
          "status": "blocked",
          "reason_codes": ["template_source_changed"]
        },
        "fix": "Gym must qualify this exact template against its currently installed runtime and project bindings."
      }],
      "anvil_setup": {"status": "not_assessed", "execution_setup_ready": false},
      "run_authority": "not_granted",
      "paid_calls": false
    }
  },
  "meta": {"request_id": "request-id"}
}
```

Praxis should retain and display the complete response (including HTTP status,
package identity and correlation ID), rather than replacing it with a generic
"Gym's own work" message. No new task content is requested by this reporting fix.

## Release boundary

Diagnostics code is part of the qualification source closure. New code must be
built and installed with matching images/source, genuinely requalified, and then
the exact template/project runtime import must be refreshed through supported
authenticated paths. Old receipts must not be edited or relabelled. No model
requests are needed or authorized for this work.
