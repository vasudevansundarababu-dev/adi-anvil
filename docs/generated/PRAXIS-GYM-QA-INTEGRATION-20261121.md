# Praxis–Gym QA connection — 21 November 2026

**Current update:** the owner provided action-time confirmation and the supported
adoption POST succeeded in the owner's real signed-in Admin browser session.
Request ID `2a9feebd-a955-4b84-8b3f-c89238e9a33b`, HTTP 200, existing grant
preserved, no credential issued. UI refresh displays Managed service identity /
Grant active. Separate read-only database readback confirms exactly the existing
grant now maps the account/subject/audience below, with scope and expiry unchanged.
This closes the historical Admin-mapping blocker below. End-to-end approved-task
delivery remains untested until Praxis sends the final scope-corrected export.
Health after adoption confirms API/database ready and both live dispatch flags
disabled. The related local suite passed 94 tests (one Authlib deprecation warning).

Praxis should initiate transfer using its own attached managed identity, obtaining
an audience-bound Google ID token for `https://anvil-qa.adi-labs.ai`. Use
`Content-Type: application/zip` with the original approved ZIP bytes at:

```text
POST https://anvil-qa.adi-labs.ai/api/v1/projects/a7454c18-602e-4907-bdd9-277067c36233/dataset-exports/generic/validate
POST https://anvil-qa.adi-labs.ai/api/v1/projects/a7454c18-602e-4907-bdd9-277067c36233/dataset-exports/generic/resolve
```

Validate first; resolve only when the response allows it. Retain a stable
Idempotency-Key for resolution and record request/package/receipt identities.
Do not blindly retry an ambiguous result. Do not send model/provider credentials,
Gym private cases or hidden expectations to Praxis. This connection does not
repair package conformance or bypass genuine Gym reviews.

User-authorized scope: published-template and approved-task transfer in QA only.
Provider/model calls remain disabled. No task transfer or binding completion is
claimed by a successful contract request.

## Installed and verified

Enabled on the existing API service only:

```text
ANVIL_PRAXIS_TEMPLATE_CALLS_ENABLED=true
ANVIL_PRAXIS_WORKLOAD_IDENTITY_ENABLED=true
ANVIL_PRAXIS_TEMPLATE_ORIGIN=https://praxis-api-742785092638.us-central1.run.app
```

The application/image is unchanged (`e49e149`, backend digest `71ac0ce3…7495f6b`).
Only API was recreated; other seven application container IDs are unchanged.
Current API ID: `729bf5b0e1454652eab0d55e84dcff4b8ed2a4d307e92a81e500ea720e741319`.
Current compose SHA-256:
`f199a2cdf22503b2a9596898690f6a1bf93c423548d12de57548950a8f27c925`.
Private rollback config is retained at
`/var/lib/anvil-qa-v1/config/praxis-enable-backup-20261121/compose-before.json`.

The first strict postcheck stopped because Docker reordered Binds. A separate
readback compared the accepted serving baseline: identical bind membership and
modes, identical effective mounts, all other HostConfig fields identical, and
unchanged user/entrypoint/command/image. No deployment retry was performed.

Actual installed API workload identity retrieved the authenticated Praxis
contract successfully. Praxis reports `paid_calls: false`; a cross-project
runtime client was rejected. Public health returns API/database ready and both
live inference and Harbor live dispatch disabled. Anonymous integration contract
request returns 401. Readback checked provider-disable flags across all running
QA containers. No model calls or database writes occurred in these operations.

## Required authenticated Admin mapping

The existing live QA grant is `39f85c78-9502-47f4-a505-381e7c0a6961`, project
`a7454c18-602e-4907-bdd9-277067c36233`, validate/resolve permission, expires
`2026-12-11T05:48:04Z`. It has no workload-principal mapping. In workload mode,
legacy static credentials are rejected. Do not issue a new key or impersonate
the sponsoring Admin through SQL.

Praxis QA's deployed managed identity was read from GCP, without accessing keys:

```json
{"subject":"101842014255515269117","account_email":"praxis-demo-run@adi-praxis-test-0928.iam.gserviceaccount.com"}
```

Use the real signed-in Admin session to POST that body to:

```text
/api/v1/projects/a7454c18-602e-4907-bdd9-277067c36233/dataset-exports/workload-clients/39f85c78-9502-47f4-a505-381e7c0a6961/adopt
```

The supported endpoint enforces project Admin, current sponsor, expiry,
revocation and immutable mapping. Incoming transfer remains blocked until this
succeeds. No mapping was inserted by the operator.

## Remaining transfer and binding tests

1. Attach the real managed identity through authenticated Admin adoption.
2. Praxis must send an audience-bound token for `https://anvil-qa.adi-labs.ai`,
   project scope above, and the final approved replacement package. Do not replay
   the superseded pending-TIN package as the new scope correction.
3. Validate, then resolve through existing generic endpoints with stable
   idempotency keys. Verify original bytes, exact task/template hashes, private
   isolation, duplicate replay, wrong-project rejection and approval provenance.
4. Published-template verification uses the existing authenticated proposal-ID
   read/publication acceptance contract. Obtain the genuine proposal reference
   where needed; do not invent one from a version ID or relabel offline evidence.
5. Bind the new immutable task revisions to the staged Gym context through actual
   dataset registration, reviewed policy subjects/intervals, evaluator config
   versions and exact runtime binding proof. Preserve the TIN scope exclusion and
   all pending case/rights/semantic reviews. Staging alone is not registration.

The earlier software qualification receipts are not reissued or extended by this
API configuration change. Recheck current eligibility before final preparation;
do not describe connection health as runtime/model qualification.

Private execution/readback evidence is under
`.local/gym-context-setup-20261120/`; credentials and raw case data are not included
in this document.
