# Gym offline-upload and privacy correction — 18 November 2026

Serving backend source780e447; web remains e0ec104. QA only:
https://anvil-qa.adi-labs.ai/workspace. Production untouched.

## Changes

External Authoring discovery no longer queries or returns private dataset inventory
for either workload identity or project export-client authentication. Authorized
Gym browser discovery is retained. This fixes one identified metadata response;
it is not a claim that every external response has been privacy-audited.

KYC input planning accepts actual stored Admin offline-upload provenance without
relabelling user_session as workload_identity. Project/package/receipt/source and
sponsor-created_by checks remain; offline sponsors must be active project Admins.
Later source-version, complete task/package membership, installed qualification,
policy and Run gates remain in place. This does not verify Authoring publication,
approve a policy or authorize model calls.

Ownership handoff corrected: Authoring owns policy/rule/task relationships; Gym
owns private data, expectations, data reviews, evaluator mappings and runtime.
The living gap register now has52 unique IDs and verified relative evidence links.
One-time migration exception preserves unchanged SME content/provenance; material
business changes and missing policy decisions are not automatically approved.

## Verification

Final exact checkpoint:1111 unit tests PASS,10 subtests PASS,1 Linux-specific skip,
124.48s. Focused privacy/provenance14 PASS and independent read-only review clear.
Whitespace and scoped test Ruff PASS. Local test command from engineering checkout:

```sh
ANVIL_ENV=local ANVIL_FIXTURE_MODE=true WEB_ORIGIN=http://127.0.0.1:3202 \
ANVIL_MARKETING_SOURCE_FIXTURE_ROOT=/Users/vasudevansundarababu/Code-Repo/ADI-Anvil/.local/runtime-correction-20261117/.local/marketing-source-control-20261117 \
PYTHONPATH=services/backend/src:services/harbor/src:. \
services/openenv/.venv/bin/python -m pytest services/backend/tests/unit -q --tb=short
```

Ignored log: .local/gym-offline-780e447-units.log. Earlier attempts used incomplete
test environments: backend venv lacked OpenEnv/MCP; runtime venv without the explicit
Marketing fixture root failed dependent fixtures. These were corrected, not waived.

Cloud Build92e9fff1-dc79-4df6-a318-a280805d9ac9 SUCCESS. Immutable backend image:
`us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-qa-v1/backend@sha256:5f70ee4ae17a558144b5ee4b17e0c6f6b3f637a24f4a9001f9a9ec505ecc21a1`.
Archive contained committed source only; no local credentials/private evidence.

QA API/worker/business-worker updated; all three expected image/revision, running,
zero restarts at rollout verification. Other service definitions unchanged. Previous
Compose retained at /var/lib/anvil-qa-v1/backups/offline-780e447-20261118.
No database migration, volume deletion or production change. QA health/workspace200;
anonymous generic contracts401. Installed-image projection controls passed both
external identity modes and proved the native gate remains closed. These controls
use manufactured access context; actual external-auth E2E was NOT RUN.
Live provider/Harbor/Authoring integration and real-mail flags remain disabled.

## Not complete

Actual native Trial owner, no-model lifecycle/role controls, evidence review and
policy qualification/materialization remain unfinished. The updated code is not
installed native qualification. KYC v7 remains immutable and blocked. Authoring's
successor has not arrived, so offline successor import, bindings and Run creation
have NOT RUN. No model calls or model-performance claim.

Legacy ReusableExport v2 requires a dataset reference; product CandidateExport v1
does not. Do not put protected data IDs in the successor product export. A reviewed
state-policy not-applicable decision also lacks an explicit supported PolicySet
representation today (state_refs minimum1); record as gap BIND-14, never manufacture
a state source or bypass applicability validation to make an upload pass.
