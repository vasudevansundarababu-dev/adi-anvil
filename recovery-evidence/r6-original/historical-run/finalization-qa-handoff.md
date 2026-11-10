# Handoff: finalization fix, security review and QA rerun → human review (deployment not started)

- Work ID: `anvil-task-readiness-explanations-2026-11-06`
- Repository / branch / source commit: `vasudevansundarababu-dev/adi-anvil` /
  `codex/anvil-agent-team-2026-11-06` / `8cdc8a84784c7ae52d7bbb88f36193b387aedb60`, plus the
  uncommitted tree bound by `finalization-evidence/code-manifest-r6.sha256`
  (`5c15faf05331d58b26342ce7a40d8b0df5f4be62d2619a2840fbf0cdab3f7c7b`, 30 files). Nothing was
  committed or pushed.
- r6 vs r5: the only difference is one line in `tests/e2e/golden-executable-import.spec.ts`
  (the alert selector). The backend, unit, lint and type evidence measured on r5 therefore
  applies to r6 and was not repeated. The browser evidence was measured on r6.
- From role / proposed next role: Coding + security review + QA (finalization stage) → human
  review. DevOps is not started.
- Authority:
  - `approvals.md` §8 (verbatim user authorization relayed by the Codex coordinator on
    2026-11-06);
  - the coordinator's routine QA repair of the browser-test selector, within the §8
    verification scope. It is test-only and is not a new approval.

## Input artifacts (SHA-256)

- `prd.md` `eb6e8aac45d305063bf0966b7f7551cac71df6db2dd1ab19c0c0b94e00fbb9af`
- `design.md` `b490d0d8f4d89bc25571519d98e7bb8d1f43054a9fcbb2575e5f6468733a42d4`
- `plan.md` `8af2f4b48bbe1a8fac805b613b4b706ef2fb899371b8e9901e076af84543da89`
- `approvals.md`, with §8 appended `90feb4dc96b1534001a5f462b43f363871da6d3a0ceba5e5cd23bc792c99a783`
  - The content before §8 is unchanged. Hashing the lines before §8, without the separating
    blank line, gives `5e1250cc…`, which matches the `approvals.md` hash in
    `correction-qa-handoff.md`.
- `correction-qa-report.md` (Q1 source) `07482829d2e431139faffc82233461cd29e37bd38cb88eecde0b230f21f82057`
- `correction-qa-handoff.md` `c095908ad9abfdae248b9739c9a07c6a60a51e1233963d423a426d20a43f131c`
- `correction-evidence/code-manifest-r2.sha256` `378b350819aa58fcd5509e98f0f6fcfe10aa57ac4cfdfce8d41ca13a6a707747`
- `correction-evidence/race/competing_worker.py` `35b820e6bbbd28a5d4b7d553371d25d3ffeecf293033424059409c8be591fd24` (unchanged)
- `correction-evidence/race/with-competitor.sh` `2d0853a2697919bb8d218718abded6188e7a2b21b8cabb68f3caff838ed192cf` (unchanged)
- `qa-evidence/original-42-ids.txt` `36b4fdd4f58888619d010bf102f5048fb5733c1e2faf30a1ef1caf004f6f1277`

## Output artifacts (SHA-256)

- `finalization-implementation-report.md` `7f9506769dec645af40487b80383a9427988f9fc16b8f79144c19c70a8aadfb1`
- `finalization-security-review.md` `753e9739d2cf1e338565e70d55cac7de3d287fb64544d053f92a0838bf6570f5`
- `finalization-qa-report.md` `31be324c3848135a2038e67b9e7599dc12218fec70ea52ef0116e9eba2a6d4ad`
- `finalization-evidence/code-manifest-r6.sha256` `5c15faf05331d58b26342ce7a40d8b0df5f4be62d2619a2840fbf0cdab3f7c7b` (final)
- `finalization-evidence/e2e-selector-fix.diff` `5c113a4f2f41af08fe6a1a281635bcf32092452a2bb1f2397bdbf788550f02b4` (r5 → r6)
- `finalization-evidence/code-manifest-r5.sha256` `071b1733c2c165a0059d6a79a4559377cfd04379c0561a86b1ae6846bfb822dc` (the tree for the backend evidence)
- `finalization-evidence/code-manifest-r4.sha256` `d616153c66b390eeb866b0c4220743489ee0437548eaced8267593b016488225` (superseded; kept for the r4 deadlock record)
- `finalization-evidence/finalization-fix.diff` `f720fe0ea441977c5bafa4a3ece898b26e8cd3f8cced8d74c749dd26cbf874a2`
- `finalization-evidence/red-green-r5.tsv` `50b84ed8bd5f1a31de9a1a186a42a8bd48dd92a0ad8253f011b4e097c8b6ce63`
- `finalization-evidence/three-party-deadlock-r4-vs-r5.tsv` `ca3266d80c0c27885f4105cde166b6aaa622f600b73a2618bb3908393ee9ff70`
- `finalization-evidence/qa5-full-1.status.tsv` `6d4c8bb495d817d05b424452dd0cf363f932cd575af9f96a1cd5782a439d3d23`
- `finalization-evidence/qa5-full-2.status.tsv` `6d4c8bb495d817d05b424452dd0cf363f932cd575af9f96a1cd5782a439d3d23` (identical to run 1)
- `finalization-evidence/qa5-full-1.state` `4a097cf311db95cb36cb1b881684bbc96195e3bd18b2e0c43157f9ce75fe0a71`
- `finalization-evidence/qa5-full-2.state` `1b88e6d79ff7a9096258b2ac201a9c9c54c0a57aaef16e13ec5f9509690b619c`
- `finalization-evidence/resume-competing-worker.tsv` `36b061b8a74bd58ac79e1b35fa5da5972f0b89faeea08f6df434f8422f297b5f`
- `finalization-evidence/resume-with-competing-worker.tsv` `41e3a6d2f065305613f3b51a5e8d5294fddbf21b628770a54569ba3376e66989`
- `finalization-evidence/e2e-summary.txt` `0c86e3acaa9f409021737366634c03154c59fadad43784290f07ada004fbcbc5`

**Sanitization.** The evidence holds only statuses, counts, hashes, the product diff, and
worker pid and state lines. It contains no environment values, credentials, UUIDs, home
paths or raw tracebacks.

## Changes and requirement IDs covered

- **`services/backend/src/anvil/worker.py`:** the new `lock_run`. It takes the project
  fence, then the run, from `guard()` and from the episode/resume failure path. Finalize is
  now idempotent through `RETURNING`.
  - Fixes Q1: lost run completion, duplicate finalize audit, and deadlock with cancel.
- **`services/backend/tests/integration/test_finalization_concurrency.py`:** new, with 5
  deterministic concurrency tests.
- **`tests/e2e/golden-executable-import.spec.ts:151` (r6):** the alert locator is now
  `getByRole('alert').filter({ hasText: 'Failed to fetch' })`, so it no longer also matches
  the Next.js route announcer. The role, the expected error and all other assertions are
  kept. No retries or skips were added.
- **REQ-TRX-006:** security review completed (`finalization-security-review.md`).
- **REQ-TRX-001 to REQ-TRX-009:** re-verified unchanged. The frontend and contract files
  are byte-identical to r2.
- **Untouched:** no migrations changed, and none of the user's earlier local changes were
  modified.

## Evidence (passed / failed / blocked / not run)

- **Passed:**
  - regression tests: HEAD 0/15 → r5 15/15, 3 runs each;
  - three-party deadlock test: `DeadlockDetected` on base and r4, passes on r5;
  - full integration: 190 passed / 0 failed / 19 skipped, ×2, with the dev worker live;
  - the original 42 IDs: 42/42 ×2;
  - the resume test: 5/5 with the dev worker and 5/5 with the competing-worker harness;
  - unit 350; ui-policy 12/12; tsc; ruff; Prettier; `git diff --check`.
- **Browser (r6):** the 3 planned specs passed 8/8 in each of 3 runs, and the golden spec
  passed 3/3 in each of 5 runs. There were no retries and no flaky marks.
- **Failed:** none on r6. On r5, `golden-executable-import.spec.ts:70` failed in 3 of 4
  runs from the strict-mode selector flake; r6 repairs it.
- **Blocked:** the 19 Docker, Harbor and Praxis opt-in tests (no docker socket access).
- **Not run:** the full `pnpm test:e2e`, the `chrome` channel and cross-browser checks, an
  accessibility audit, and dynamic or penetration security testing.

## Open questions and material risks

1. **S2, design constraint.** Any future live-inference design must keep provider calls
   outside `guard()` transactions. Those transactions now hold the run lock and the
   project `KEY SHARE`.
2. **Carried over.** These are still open:
   - D-COPY: label wording;
   - C2: stub-only passes;
   - C4c: unproven root cause;
   - fixture-only verification, with no live-model check.
3. **Dev stack.**
   - The worker is pid 1097806, restarted three times to load r3, r4 and r5. It is healthy
     with live providers off.
   - It was not restarted for r6, because the worker code is unchanged.
   - API pid 121952 and web pid 121956 were not touched. Health is `ready`, and the web
     returns 200.

## Next steps

- **Current status:** stopped before deployment.
- **Proposed next allowed scope:** the user reviews this stage. Deployment and DevOps need
  the user's separate approval with an exact target.
- **Prohibited actions:**
  - deployment or DevOps execution;
  - commits or pushes;
  - product provider calls, spend or real email;
  - changing the user's local changes;
  - weakening permissions;
  - deleting volumes or containers.

## Approval

- Decision: PENDING HUMAN APPROVAL
- Human approver / actual approval message reference / timestamp:
