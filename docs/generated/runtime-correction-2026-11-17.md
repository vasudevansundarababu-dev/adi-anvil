# Required execution runtime correction — 17 November 2026

Status: incomplete mandatory-runtime acceptance. Previous release smoke checks
proved the app deployment, not operational KYC/Marketing execution.

After user-completed Google sign-in, inspected only project adi-anvil-mvp-2026,
QA host anvil-qa-v1/us-west1-b. Found zero runtime observations, allowlist rows,
QA admissions and update jobs. Golden scheduler/grader still use old images with
sleep commands. Existing cached combined runtime contains older first-party code.

Current isolated source revision: 6a3ee57ab256529e761127815262f74fe29fe7c2,
branch codex/runtime-correction-20261117. Recovered sealed current Forge source and
reviewed independently locked runtime packaging; preserved unrelated root edits.

Cloud Build b7f3a4bf-71c5-47af-b595-7af57b683ad3: SUCCESS. Tests included exact
locked versions, native package imports, byte matching installed first-party Python
files to current source, and network-disabled evaluator software controls. No model
calls, benchmark performance, source rights or independent QA approval asserted.

Registry prefix: us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-qa-v1.

| Image | SHA256 |
| --- | --- |
| task-runtime | b2371f2d4482fc0726fefd42b5ccb443c7495a3dbc64f19fc7d1241d4e0681d3 |
| kyc-runtime | 65dde47e0900306b2cefd18be6e2e747a9584ae7747a075af9d00a0fc473eebc |
| marketing-runtime | d3627cba4176633fb6f0263153552f7f28db77933ad0beddf699c1c2dddf2006 |
| private-evaluator | 09b7f6b8990e63d2464aca46f8a9217c02c34e4c3cb9f3d8cdb611f269d6f1bb |

KYC and Marketing images pulled successfully onto QA. KYC actual-host isolated
container forge-kyc-source-check-20261117 exited successfully: worker source hash
6391287f33e3e42a7c7df5f8ac0c70be65de3fc798784a0caaa1ece2b8de21c3,
Harbor0.25.0, OpenEnv0.12.0, MCP1.30.0, LangGraph1.2.14, PostgreSQL checkpoint3.1.3.
Container had no network, mounts or secrets; nonroot, read-only, no capabilities,
bounded memory/CPU/PIDs. This is an installed-image check, not a serving worker.

Private evaluator image also pulled onto QA. Actual-host network-disabled control
container forge-evaluator-controls-20261117 reported 14 checks passed: ZEN2.1.3,
OPA1.22.2, NeMo0.24.1, Promptfoo0.125.1; explicitly release_ready=false. Remaining
boot-disk free space3.5GB; data volume and existing services preserved.

Remaining blockers: current Marketing code unconditionally raises
marketing_native_operator_world_and_lifecycle_not_admitted. Native world/lifecycle
integration is unfinished, not a missing package toggle. KYC requires dedicated
worker credentials/wiring and genuine operation/admission evidence. Existing
runtime Update route stages requests and is not an installer. No readiness records,
signed receipts or human approvals have been fabricated; paid gates stay closed.

Main deployment unchanged during this correction. No paid inference or additional
email sent. QA: https://anvil-qa.adi-labs.ai/workspace.
