# Benchmark Coding progress

Status: T00 complete; T01 next. Coding only; stop for human review before QA or deployment.

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

## Completed tasks and focused results

- T00 complete, fully verified above.
- Focused existing tests: `node --test tests/provider_failure.mjs tests/readiness_catalog.mjs` → 12 passed, 0 failed, 0 skipped.
- Original approved run's 15 files remain unchanged; source whitespace/integrity checks pass.
- Historical recovery/Coding report and source-bound handoff saved in the new Coding run.

## Work in progress / remaining

- Install workspace-local Python3.12 + locked backend environment and pnpm10.34.5 + locked frontend environment. Autonomous continuation now permits routine isolated setup; earlier setup-confirmation blocker is superseded.
- T01 strict SME bundle contract and original labeled fictional fixtures, then T02 private schema/access foundation and T03 streaming intake only once prerequisites/checks hold.
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
