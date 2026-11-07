# Benchmark Coding progress

Status: T00/T01/T02/T03 complete at the focused Coding-foundation level. T04 is pending its approved native-image/evaluator prerequisite; see next-gate section below. No full benchmark completion or QA/release approval. Coding only; stop for human review before QA or deployment.

## Revision and authority

Working branch: `codex/anvil-agent-team-2026-11-06` in `vasudevansundarababu-dev/adi-anvil`.
Current source baseline: recovered existing commit `15e35f12725a89be6e507b2eb73d4433e666dd76`, tree `18fca788310f91a35a54df39392a37c026ae16b1`. This initial checkpoint's commit ID is `git log -1 --format=%H -- BENCHMARK-PROGRESS.md`; a commit cannot embed its own ID. Later checkpoints record the preceding exact commit below.

Approved design inputs under `docs/agent-team/runs/anvil-praxis-bodhium-benchmark-2026-11-07/` remain byte-identical:
- architecture: `c200d135bd9dbe171b63e13833349a6486d09adff17c5c27daf870d46c6cf68a`
- implementation plan: `1cdf87e4d48bc483a2e5116509e83d07b35f2652b95c032635b98bbe0e3f9749`
- specification: `44196cae04b7a399fb70da8d4577345b2cf95ee6a14daa41f3d8c8f2b4921cbc`

Actual human Coding approval and later autonomous commit/push/draft-PR approval are appended to `docs/agent-team/runs/anvil-benchmark-coding-2026-11-07/approval-log.jsonl`. Approval supersedes older pending-approval wording without rewriting historical artifacts. Existing ADI-Architecture LLM connection is unchanged; current role is Coding.

## Source recovery — passed

Original patch SHA-256 `3e3552e21f37388aca0f7985c54e169f54ce02bc318b0368ec19e334b6389e66`, original commit object, and original r6 manifest SHA-256 `5c15faf05331d58b26342ce7a40d8b0df5f4be62d2619a2840fbf0cdab3f7c7b` recovered through old Anvil sandbox file GET only. Pristine base + original patch reproduces expected complete tree; 504 files/modes, 30 manifest entries and 264 build archive files match. Restored 21 omitted historical paths, including actual readiness and finalization-race regressions. No substitute historical tests were authored.

Hash-bound prior finalization implementation/security/QA/deployment reports and approvals are retained as historical evidence, not new acceptance. Local comparison repo, raw input archive, compressed commit-object copy, credentials and raw logs are excluded from Git. Some historical hash indexes reference those local-only inputs; they intentionally remain unchanged. The actual recovered release commit is an ancestor of this checkpoint.

## Push / automation safety

GitHub read-only checks: correct repository/branch; remote branch initially `8cdc8a8…`; no webhooks, deployments or existing PR for this branch. Only source workflow is fixture CI (push on main, PR events), not deployment. Cloud Build YAML builds images; deployment scripts require explicit invocation. No cloud commands executed. External cloud integration configuration is not claimed audited beyond these available repository/GitHub checks.

Draft progress PRs now skip the full fixture job; non-draft PR/main behavior is preserved. No QA role or full acceptance is authorized by opening the draft. Do not mark it ready, merge, force-push or deploy.

Previous pushed checkpoint: `ac5373bf0a6e52cae8ab8725072721fe96c3a4bd` (T03A inspector/staging). Complete T02: `b83ad212b697e50d9e9cb17a6528330552f408aa`. T02A: `a829c49d837ac3e412963c45a6d22c0e67389453`. Earlier publication/database checkpoint: `a6b415e89cfe3b438f8f80356b91fcfa89b2215f`. T01: `9a82eab7b88bea8d6b5da5d29da92dd7f7735daf`. Initial checkpoint: `5345518b49df01c7f10caf1b4fd696bd61b3141f`. Draft PR: https://github.com/vasudevansundarababu-dev/adi-anvil/pull/16. Current checkpoint ID: `git log -1 --format=%H -- BENCHMARK-PROGRESS.md`.

## Completed tasks and focused results

- T00 complete, fully verified above.
- T01 complete: strict SME v1 metadata/schema, actor/private dependency closure, exact points, RFC8785 + real Ed25519 external trust/expiry/revocation/quarantine checks; original fictional 24/6/51 fixtures and private test oracles. At T01 no intake/execution/qualification API existed; T03 now adds intake only.
- Focused backend new/legacy checks: 105 passed (65 new T01 tests), including private projection, malformed inputs, actual oracle and stdio subprocess. Ruff/format and versioned JSON Prettier pass. Full deterministic fixture/schema two-step recipe reproduces all recorded hashes. See `t01-checks.json`.
- Focused existing tests: `node --test tests/provider_failure.mjs tests/readiness_catalog.mjs` → 12 passed, 0 failed, 0 skipped.
- Original approved run's 15 files remain unchanged; source whitespace/integrity checks pass.
- Historical recovery/Coding report and source-bound handoff saved in the new Coding run.

## Work in progress / remaining

- Completed workspace-local Python3.12.15 + locked backend environment, pnpm10.34.5 + locked frontend environment. Added and locked only RFC8785 canonicalization dependency0.1.4; no global/source/config changes. Earlier setup-confirmation blocker is superseded.
- T02 environment prerequisite resolved after initial preflight: dedicated Docker daemon under `.local/benchmark-docker/` and source-pinned PostgreSQL17.6 container `anvil-benchmark-postgres-20261107`, no network/ports, fresh tmpfs data, private Unix socket `.local/bm-pg-socket`. No shared backend/socket/volume/credentials or cloud resource used. API/worker still have no Docker socket. Container remains isolated; no deletion performed. Real SQL connection/version verified. Run dedicated Docker client with sudo against this exact socket only, not global Docker config or socket permission changes.
- Publication guard completed: one-line token-boundary correction avoids `task-readiness` false positives; actual scanner CLI in real temporary Git repositories still detects token shapes/forbidden private paths without printing values. New scanner tests3/3; combined focused backend set108/108; repository scan no findings. No mocks.
- T02A complete: additive039/040 + wrappers; private receipt/append-only assignments/revocations/evaluator bindings/fenced-job inputs; separate owner-only content-addressed vault; generic store/read/HTTP deny private classes; ordinary worker excludes benchmark job kinds. All18 real SQL/HTTP/concurrency/filesystem checks pass; combined focused backend126/126. Migration repeat pass. Source hashes/commands and limits in `t02a-checks.json` / `t02a-source.sha256`.
- T02B complete: exact typed membership/qualification/comparison/cell/attempt/evaluator-call/criterion/score/review/spend/capacity/dispatch relationships in041. Separate immutable window ownership042 prevents legacy/benchmark reuse in both orders and actual simultaneous transactions without late finance row-lock inversion. New9 real DB tests pass; real DB total27; focused backend135/135; migration repeat at042 passes. See `t02b-checks.json` and source hashes. These are persistence foundations, not implemented scheduling/grading/admission.
- T03A verified: new gzip/canonical USTAR regular-only incremental inspector, no extraction/execution; strict member/hash/size/header/alias/trailer checks, bounded gzip metadata complexity. Explicit conservative new format policy (GNU/PAX/directory headers unsupported) recorded in `t03a-checks.json`, not a partner compatibility claim. Private vault stage accepts streams in64KiB chunks. New26 archive tests pass; combined focused167 including old6 middleware checks and27 DB tests.
- T03 complete: exact raw streaming HTTP route, CSRF/Idempotency-Key/current assignment controls, owner-only spool/quota/disconnect cleanup; private malformed originals with audit; immutable exact-byte receipt conflicts/reuse; separate original/canonical metadata, safe project/role status/error routes, migration043 and generated OpenAPI. Archive hash must match immutable staged original before manifest binding. Original archives remain benchmark_raw and generic-download denied. Feature defaults disabled. Real SQL/HTTP/filesystem/concurrency44 checks, archive26, streaming7, public-trust9, legacy limits6 plus historical/core checks =>200 focused backend passed; exact Node policy suite12 passed. No failed/skipped final checks. See `t03-checks.json` / `t03-source.sha256`.
- Evaluator DB role is NOLOGIN/no bypass/no memberships. A later approved service identity/login/credential/mount scope remains unprovisioned; job-scoped SQL tests do not prove container G2 qualification. No private root mounted to an application/ordinary worker in this runtime. Stage/hashes precede DB row locks; binding phase is SQL-only. Private root must be explicitly configured and disjoint from generic artifact root; no default/fallback.
- Routine contract choices: ASCII canonical payload paths (Unicode content is supported), bounded integer point profile, UTC export seconds, no implied signature-to-execution/rights authority. Unsigned fixtures stay quarantined; image/evaluator metadata stays unqualified/unreviewed.
- T04–T10 follow dependency/qualification gates. Do not claim native/Docker/provider behavior without observing it.
- T11 independent QA, T12 release preparation and T13 live acceptance remain separately gated; no auto-transition.
- Authentic Bodhium cases, exhibits, 81 actual criteria/oracles/tolerances, rights, exact models/judge and budgets remain absent. Do not invent them; fictional fixtures demonstrate software behavior only.

## Exact resume instructions

1. Use `/workspace/anvil-recovered`, verify `git remote -v`, current branch and clean/expected worktree; preserve original checkout and all unrelated edits.
2. Read this file, latest Coding run and approved architecture/plan/contract design/threat model. Check actual input hashes and latest source commit.
3. Use repository-local locked Python3.12/pnpm environments; never borrow credentials/environments/shared services from old sandbox, Praxis or Mac.
4. Implement the next ready plan task; focused tests only. Record commands/results/blocked prerequisites here and in a task-bound report. Push a normal checkpoint after a meaningful completed task and before stopping, after confirming draft PR is still open.
5. Stop for human code review before QA, merge, cloud/deployment or paid candidate/judge evaluation. If no safe independent task remains, checkpoint and report exact blocker.

Immutable release patch context whitespace is preserved to retain its approved SHA-256; new-source whitespace checks exclude only that historical patch. Raw check logs and original input archives stay local-only.

### Exact focused DB command environment (no credentials)

Use `ANVIL_ENV=local`, `WEB_ORIGIN=http://127.0.0.1:3202`, both live/email flags=false, `ANVIL_BENCHMARK_VAULT_ROOT=/workspace/anvil-recovered/.local/benchmark-vault`, `ANVIL_BENCHMARK_TEST_DATABASE_URL=postgresql://anvil_migration@/anvil_local?host=%2Fworkspace%2Fanvil-recovered%2F.local%2Fbm-pg-socket`, and `DATABASE_URL=postgresql://anvil_app@/anvil_local?host=%2Fworkspace%2Fanvil-recovered%2F.local%2Fbm-pg-socket`. Set `ANVIL_BENCHMARK_ENABLED=true` only in the isolated Coding test process for intake checks (default remains disabled). Run the exact combined200-check command in `t03-checks.json`; private-storage-only suite now19 checks. No real installation public trust file was created; signature tests use temporary public files and in-memory ephemeral signing keys. These DSNs use only the fresh network-disabled test container, not a shared/deployed database. Never replace them with production URLs. Migration command uses the migration DSN in `MIGRATION_DATABASE_URL` and `python -m anvil.cli migrate` (head043; repeated upgrade passed).


## Next gate — T04 native fixture/evaluator review

T03 is implemented and focused-verified, not the complete benchmark. Approved T04 explicitly requires an approved fictional environment/evaluator image before native qualification. `fixtures/benchmark-bundle/README.md` says current image metadata grants no pull/run/qualification authority; registry ID remains `fictional-arithmetic-unreviewed`. No imported evaluator is installed and no new test-image authority is inferred from Bodhium testing consent. The old dependency/DB blockers are resolved.

Proposed next action for PO confirmation: authorize a local-only native fictional qualification using the existing pinned Python fixture base `python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e` and a reviewed Anvil-authored evaluator binding from the source-hashed fictional oracle, or supply another reviewed exact binding. Build/run only in the dedicated isolated daemon, never the shared socket. Native image/runtime review and real G2 tests must still pass; approval itself does not certify isolation. No signature/rights/spending/run gate is waived, no paid model/judge dispatch is authorized, and no QA agent, merge or deployment follows automatically.

Until that prerequisite is resolved, T04 has not started and dependent T05–T10 are not claimed implemented. The next work is an explicit prerequisite review, not a request to invent Bodhium criteria/model IDs/budgets. All15 original approved artifacts were re-hashed unchanged at this checkpoint. Current Coding checkpoint source hash index: `t03-source.sha256`; recovered r6 baseline commit/tree above remain distinct from new code.

Initial local intake policy chosen explicitly for review: 4 simultaneous installation uploads, 2/project; 1GiB retained private objects/project and20,000 objects; gzip/canonical regular-only USTAR. Limits do not certify suitability for actual partner exhibits. Rejected complete originals are retained privately; incomplete owned staging is removed; no retention purge/deletion job is introduced. Public trust roots are external installation configuration, reloaded per inspection; no product secret reuse or trust root installation occurred. A verified receipt means source integrity at import, not rights/completeness/qualification/readiness.
