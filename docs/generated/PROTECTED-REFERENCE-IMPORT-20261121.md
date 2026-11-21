# Protected reference import access

Authorized scope: the Product Owner requested fixing Gym protected-storage access,
finishing the supplied task import/bindings, QA deployment/testing and a completion
or blocker email on 21 November 2026. Live model calls remain prohibited.

The exact supplied package passes deployed read-only source validation, but its
Admin account has no protected-reference assignment. Existing PostgreSQL RLS
requires this assignment even for an Admin; the import must not bypass it.

The implementation adds authenticated project-scoped GET/POST
`/workspace/benchmark/reference-storage-access` and POST
`/workspace/benchmark/reference-storage-access/{assignment}/revoke`, beneath the
existing `/api/v1/projects/{project}` prefix. Creation requires explicit typed
consent, the real Admin identity, CSRF and existing idempotency handling. It can
assign only that same account the existing `source_review` scope, with no artifact
restriction, for eight hours measured by PostgreSQL. Thus it permits source/raw
and evaluation-reference custody within this project, but not judge assets.
It accepts no target account, role, scope or expiry override. An existing active
self-grant is returned without extension. Creation/revocation is audited;
revocation can target only that Admin's own source-review assignment. No schema
or RLS policy is changed. Review approval and paid dispatch authority stay false.

Projects → Import displays the exact permission scope and an unchecked consent
box before the grant action. Access status and revocation remain available after
reload. This security-sensitive grant requires the owner's explicit action or
action-time confirmation when operated on their behalf. Deployment alone grants
no access, and no database impersonation is used.

The workspace import route now returns actionable validation-report JSON too:
source validity, Gym-owned blockers, correlation ID and separate setup readiness.
A valid task with missing storage access remains source-valid, with HTTP 409 and
`AV_PRIVATE_STORAGE_ASSIGNMENT_REQUIRED`; it is not mislabeled an Authoring defect.
The UI displays the storage explanation and safe error code/request ID.

Validation before freeze: 14 focused API tests passed; the preceding combined
access/validation/privacy regression run passed 34 tests and 10 subtests.
TypeScript and Ruff checks passed. Actual QA grant/import/binding acceptance and
fresh source-bound runtime qualification remain pending until rollout.

Idempotent import replays retain the immutable receipt but recompute current Gym
readiness and request correlation outside the cached response. Grant replays
also recheck actual access, and the UI reconciles status with a fresh GET.

Remaining human policy, data-rights and case-expectation reviews are distinct.
No source acceptance, storage grant or synthetic runtime control approves them.
