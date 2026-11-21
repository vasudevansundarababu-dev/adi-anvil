# KYC Gym context preparation — 20 November 2026

**21 November completion:** user-authorized installation succeeded after Google
sign-in. Separate QA readback verified all 11 installed files, exact manifest,
root ownership, 0700 directories and 0600 files at
`/var/lib/anvil-qa-v1/dataset-staging/kyc-context-fe9571ece2c3-v1`.
Offline acceptance passed again: 200 resets, 100 follow-ups, 200 unscored pending
expectations and 178 chunks across 20 policy cells. No database writes, service
configuration changes or live calls. This supersedes the historical staging
blockers below. Dataset registration and active bindings remain pending.

21 November retry: the user explicitly authorized private QA staging. The
reviewed installer was retried but GCP rejected expired authentication before
SSH connection; no remote installation occurred. Google sign-in was opened
with a local callback and is awaiting the user. All 18 preparation regression
tests passed again (1.10 seconds). Resume the same installer after sign-in,
then independently read back every installed hash and private permission.

Status: prepared and mechanically tested; not registered, approved, or admitted
for a model run. No live calls were made. Existing v7/v8 records were preserved.

## Completed independently of the corrected export

- Read back all 200 existing QA public cases and independently verified the
  private parent controls inside the scheduler and grader with read-only SQL.
- Prepared a separate 12 November national-bank/OCC/New York context containing
  200 cases: 50 per product and ten per state/product cell. Preserved private
  scenarios and future documents; expectation review remains pending.
- Prepared 20 policy cells with exact source bytes and hashes, including both
  federal references and all individual Illinois source files. Explicit
  non-applicability and national-bank limitations remain visible.
- Mapped seven bank rules onto the existing 50 evaluator requirements. This is
  a binding plan, not registered evaluator configuration IDs or runtime proof.
- Checked 3,850 party-age and 13,420 document-date comparisons: no category
  threshold crossed. Follow-up dates shift by one day; this mechanical result
  does not approve case expectations or legal applicability.

## Verification

61 related tests passed, including 18 preparation tests. Ruff passed for both
scripts and the preparation tests. The offline acceptance checker reset 200
cases, exercised 100 follow-ups, confirmed all 200 pending expectations remain
unscored, and reconstructed all 20 policy cells through 178 bounded chunks.
Database writes and model calls: zero.

Commands use the repository's locked backend-capable Python environment:

```sh
services/openenv/.venv/bin/python -B -m pytest tests/ops/test_prepare_kyc_context.py -q
services/openenv/.venv/bin/python -B scripts/prepare_kyc_context.py --help
services/openenv/.venv/bin/python -B scripts/check_kyc_context_bundle.py --help
```

Private evidence and generated assets are retained under
`.local/gym-context-setup-20261120/`; do not commit them. Final bundle manifest:
`108d8f17ad675fa37dcbc52c525166772fc6b5f147c6326a5cac7111eb3cefbe`.
Child population: `fe9571ece2c343a71e14b6f9f0d229f4638913d7a55b9e40e01fdfadb07ef43d`.
Qualified runtime source remains unchanged at `c26a7965…01e4`; these offline
helpers require no runtime image rebuild.

## Remaining finalization

1. Validate and resolve the corrected Authoring export. Its exact immutable task
   revisions and resolved input IDs must determine the binding subjects.
2. Product Owner reviews the context/date change, private case expectations,
   rights, policy intervals and rule-to-evaluator mapping. Existing source
   approvals are evidence, not fabricated Gym ledger decisions.
3. Register a new dataset/context pack through a path that preserves private
   controls. The generic public actor upload currently resets those controls;
   do not use it to replace this bundle or modify the old reference pack.
4. Create the exact task/input-scoped policy subjects and retain genuine owner
   decisions. Provision policy materializations with actual runtime binding
   control evidence; global software qualification alone is insufficient.
5. Register exact evaluator configuration versions, bind them to the resolved
   tasks and new context, and rerun no-model admission/qualification checks.
   Qualification receipts expire; renew against the installed exact images if
   needed. Only then may a separately authorized model run be considered.

## QA staging boundary

The archive reached a private QA temporary directory. Automatic approval review
rejected the subsequent sudo installation into the private dataset-staging
directory, citing the prior staging hold. The installer did not run. No dataset,
policy approval, evaluator binding, service configuration or mount was changed.
Do not describe the assets as registered or available in the UI. Obtain explicit
authorization for that private QA staging write before retrying; do not bypass
the rejected action.
