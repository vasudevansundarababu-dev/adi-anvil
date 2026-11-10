# Anvil QA environment — next release plan

Status: preparation only; no provisioning, deployment, image build/upload or paid model call executed. Baseline source is a7b7fad1c11807d32e33d36e2e07b91965645324. Praxis and the existing Anvil deployment are excluded from changes.

## Current assessment

The local six-template component/runtime/dashboard integration is tested. This is not completion of the authentic-model/cloud specification. Current cloud Compose/operator recipes predate the new durable Run worker, six-world Harbor plugin and installed OpenEnv bridge. They must be amended and tested before using them as a release recipe. Existing model SDK tests use offline transports; a production live execution path for the new environments still needs integration and qualification. Exact source bindings depend on published Praxis contracts; unsupported contracts must remain blocked.

## Release sequence

1. Complete local deployment wiring: dedicated Run worker, independent pinned Harbor/OpenEnv runtimes, current migration069/checkpoints, stage-specific identities/paths, readiness, restart/recovery and paid-off configuration. API and ordinary workers receive no Docker socket, migration-owner DSN or provider keys. Verify Linux/amd64 compatibility; the Mac cached actor image is not automatically a Linux/amd64 qualification.
2. Prepare the exact public source/image-build package and manifest, current dependencies, operator/run instructions, rollback and cleanup plan. Old edcc/abb image-build packets are historical and cannot authorize this successor.
3. Reauthenticate the Anvil-only CLI and perform read-only inventory, quota/identity/network checks and fresh cost verification. The current read-only VM/registry inventory attempts failed because the saved account requires reauthentication. This is not evidence that resources disappeared. Do not inspect credential files or use Praxis's CLI/configuration.
4. Present a bounded cloud resource/build/lifetime plan for approval. Reuse the existing Anvil project and dedicated registry/build identity only after readback and scope verification. The USD500/month allowance is a planning ceiling, not a new deployment/model-call authorization.
5. After explicit cloud authorization, create an isolated Linux QA target and verify current-source build/load/tool/reset/collection, role boundaries, cancellation/restart and owned-resource cleanup. Actual resource IDs, image digests, receipts, charges/limits and deletion status must be recorded.
6. Import the authentic published six-task packages; implement and test the necessary field/schema/evaluator adapters without changing the source rubric. Do not substitute the fictional KYC example for financial/marketing/KYB/AML source qualification.
7. Connect selected real models through existing credential/budget/admission controls; exercise offline failure contracts first. Actual inference requires exact model IDs, securely saved credentials, permitted inputs and a separate spending cap. Zero paid calls until that authority exists.
8. Run the independently reviewed QA cases and retain per-requirement evidence. Prepare the QA application release, invited account/HTTPS/OIDC settings and migration/rollback record. Request deployment approval separately; a Linux QA host must not silently become the application deployment.

## Prospective infrastructure, not an execution request

- Target default: existing project `adi-anvil-mvp-2026`, region `us-west1`, zone `us-west1-a`.
- First cloud phase: one dedicated Linux/amd64 QA execution host, fresh test-only database/artifact roots and a dedicated Docker daemon. No current Anvil/Praxis database, disk, issuer, secrets or accounts copied.
- Proposed starting host class: e2-standard-4, concurrency1. Disk sizing, network path and lifecycle will be finalized after inventory and build-size checks. Do not assume a previously deleted host/network still exists.
- Default access proposal: private host plus authenticated operator access; no public database or anonymous demo. Public QA web ingress, hostnames and TLS belong to the later application release plan.
- Candidate existing build assets from historical receipts: `anvil-staging-demo` Artifact Registry, staging build service account and private source bucket. Existence and effective scopes are not freshly verified.
- Provider, judge, generation and email dispatch remain off. No exact resource cost or enforced shutdown mechanism is claimed from a schema or budget setting alone.

## Inputs needed from the owner

- Anvil Google account reauthentication through the normal sign-in flow, when cloud inventory resumes. Never send passwords or tokens in chat.
- Published Praxis Project/Task exports, reviewed rubric/constraints, permitted source datasets and pass/fail/Unknown evaluator fixtures for all six seeds; reviewed independent QA test package.
- Exact real provider/model IDs, repetitions and separately approved model-call cap; keys entered securely through Anvil settings when the live path is ready.
- Before provisioning: exact initial cloud build/host budget and lifetime/access scope. Before application rollout: explicit QA deployment approval and initial invited account.

Official pricing references for the future dated estimate: https://cloud.google.com/products/compute/pricing/general-purpose and https://cloud.google.com/build/pricing . Regional selection, disk/network/storage and retained-resource charges must be verified before giving a total. No provisional historical estimate is treated as a current bill guarantee.
