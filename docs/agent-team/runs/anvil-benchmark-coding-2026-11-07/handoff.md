# Coding recovery handoff — waiting for local environment confirmation

- Work ID: `anvil-benchmark-coding-2026-11-07`.
- Repository/workspace: `vasudevansundarababu-dev/adi-anvil`, `/workspace/anvil-recovered`.
- Existing branch: `codex/anvil-agent-team-2026-11-06`; branch HEAD remains base `8cdc8a84784c7ae52d7bbb88f36193b387aedb60`. No new commit created.
- Actual recovered baseline commit: **`15e35f12725a89be6e507b2eb73d4433e666dd76`**.
- Actual verified complete source tree: **`18fca788310f91a35a54df39392a37c026ae16b1`**, all 504 files/modes verified. The earlier partial overlay is superseded, not mislabeled.
- From role / next allowed party: anvil-coding → human environment confirmation. QA/DevOps are not started.

## Actual approval and input bindings

Human approval dated 2026-11-07, current conversation user message headed `USER APPROVAL 2026-11-07`, recorded verbatim in `approval-log.jsonl` with hashes:
- Approved architecture: `c200d135bd9dbe171b63e13833349a6486d09adff17c5c27daf870d46c6cf68a`.
- Approved implementation plan: `1cdf87e4d48bc483a2e5116509e83d07b35f2652b95c032635b98bbe0e3f9749`.
- Approved specification: `44196cae04b7a399fb70da8d4577345b2cf95ee6a14daa41f3d8c8f2b4921cbc`.

All original approved documents are unchanged. Approval remains valid; no new design approval is being fabricated or requested to replace it. Source gate T00 is now verifiably passed using original artifacts, not waived.

## Source provenance

Read-only GETs from the named old Anvil sandbox recovered:
- Original release patch SHA-256 `3e3552e21f37388aca0f7985c54e169f54ce02bc318b0368ec19e334b6389e66`.
- Original compressed commit object verified as release commit `15e35f1…`, with base parent `8cdc8a8…` and expected r6 tree.
- Original r6 manifest SHA-256 `5c15faf05331d58b26342ce7a40d8b0df5f4be62d2619a2840fbf0cdab3f7c7b`, all 30 entries matching.
- Hash-bound historical implementation/security/QA/deployment reports and handoffs/approvals. These retain their original dates and limitations, not current acceptance claims.

Artifacts remain at `recovery-evidence/r6-original/`. A pristine base comparison proves the complete source tree. Main isolated workspace recovery restores 21 previously missing historical paths; all 264 Cloud Build files match. No old runtime command/agent resume, cloud mutation, key/private credential file transfer or source reconstruction occurred.

## Changes / requirement coverage

- T00 source-integrity prerequisites for BM-02/06/12 resolved.
- Actual finalization-concurrency and readiness regression tests recovered.
- New Coding approval/provenance/environment/check/report documents only.
- **No benchmark feature implemented yet.** T01–T13 are incomplete.
- No source edit beyond restoring exact historical r6 bytes; no new migrations/lockfile/config changes.

## Evidence status

- **Passed:** complete r6 commit/tree/files/modes; 30-entry original manifest; 264 archive file matches; approved original document hashes unchanged.
- **Passed focused Coding check:** `node --test tests/provider_failure.mjs tests/readiness_catalog.mjs` → 12 passed / 0 failed / 0 skipped, exit 0. Evidence `focused-readiness-check.tap`, `focused-check-results.json`.
- **Blocked environment:** supported Python3.12/backend venv/dependencies and pnpm absent. Current Python3.13.15 is unsupported by backend. See `environment-preflight.json`.
- **Not run:** backend/finalization DB tests, types/build/browser/native Harbor/migrations/startup; full QA, deployment and live provider work. Historical reports are not a new QA invocation.

## Proposed next scope for confirmation

Confirm installation, confined to `/workspace/anvil-recovered`, of:
1. Supported Python3.12 and locked backend dependencies from `services/backend/uv.lock`.
2. pnpm10.34.5 and frontend dependencies from `pnpm-lock.yaml`.
3. Workspace-local tool/cache directories; only official sources; no global/config/credential changes and no sibling environment copies.

Initial setup must not start app/Docker/database/Keycloak services or change auth settings. Then continue the already-approved T01 onward with focused Coding checks. Later service needs must be isolated, not borrowed from the old/shared backend. Missing Bodhium/model/judge/rights/budget inputs stay blocked and fictional fixtures remain labeled. Stop for human code review before invoking QA/full acceptance or deployment.

## Prohibited

No QA/DevOps transition, deployed-cloud/IAM/auth changes, paid candidate/judge calls, invented inputs/criteria, Mac/Praxis operations, credential transfer, commits/pushes or destructive reset/volume deletion.

Decision: **CODING INCOMPLETE — ENVIRONMENT CONFIRMATION REQUESTED; NOT READY FOR QA.**

- Human approver of architecture/plan: current conversation user, actual 2026-11-07 approval recorded append-only.
- New local dependency-setup confirmation reference/time: pending.
- New human code-review / QA authorization reference/time: not supplied.

`implementation-report.md` provides the exact changed-file scope and checks. `SHA256SUMS`/`artifact-index.json` bind this handoff and current run evidence without modifying approved originals.
