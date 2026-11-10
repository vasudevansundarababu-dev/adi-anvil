# QA report: finalization fix and security review rerun

- Work ID: `anvil-task-readiness-explanations-2026-11-06`
- Authority:
  - `approvals.md` §8;
  - the coordinator's routine QA repair of the browser-test selector, within the §8
    verification scope.
- **Final tree under test.** Base `8cdc8a84784c7ae52d7bbb88f36193b387aedb60` plus the
  uncommitted tree bound by `finalization-evidence/code-manifest-r6.sha256`.
- **How r6 relates to r5.**
  - r6 differs from r5 only by one line in `tests/e2e/golden-executable-import.spec.ts`
    (`finalization-evidence/e2e-selector-fix.diff`). No product, backend, migration,
    contract or config file differs.
  - The backend, unit, lint and type results below were measured on r5, and they apply to
    r6 unchanged. They were not repeated.
  - The browser results were measured on r6.
  - Each full backend run checked the r5 manifest before and after (`manifest-r5 ok` in
    `finalization-evidence/qa5-full-*.state`). Each r6 browser run checked the r6 manifest
    first.
- **Environment.**
  - local dev stack with the registered `anvil.worker` running against the shared database
    (pid 1097806, restarted to load r5);
  - live inference and Harbor dispatch `disabled`;
  - provider and GitHub keys removed from every test process;
  - fixture data only.
- **Verdict: pass with release limitations.**
  - Q1 from `correction-qa-report.md` is fixed.
  - The browser selector flake from r5 is repaired in r6.

## Results

| Check | Tree | Result | Evidence |
| --- | --- | --- | --- |
| Finalization regression tests (5), HEAD `worker.py` | r5 | 3/3 runs failed; 15/15 executions failed | `finalization-evidence/red-green-r5.tsv` |
| Finalization regression tests (5) | r5 | 3/3 runs passed; 15/15 executions passed | `finalization-evidence/red-green-r5.tsv` |
| Three-party deadlock test, base / r4 / r5 | — | Base: 2/2 `DeadlockDetected`. r4: 2/2 `DeadlockDetected`. r5: 3/3 passed | `finalization-evidence/three-party-deadlock-r4-vs-r5.tsv` |
| Full integration suite, dev worker live, ×2 | r5 | 190 passed / 0 failed / 19 skipped, both runs; status files identical | `finalization-evidence/qa5-full-{1,2}.status.tsv`, `.state` |
| Originally failing 42 IDs (`qa-evidence/original-42-ids.txt`) | r5 | 42/42 passed in both full runs | the same status files |
| `test_import_publish_versions_run_and_resume`, dev worker live | r5 | 5/5 passed | `finalization-evidence/resume-competing-worker.tsv` |
| The same test with the QA competing-worker harness (`correction-evidence/race/`, unchanged) | r5 | 5/5 passed | `finalization-evidence/resume-with-competing-worker.tsv` |
| Backend unit tests | r5 | 350 passed | — |
| UI policy (`tests/provider_failure.mjs`, `tests/readiness_catalog.mjs`) | r5 | 12/12 passed | — |
| `tsc --noEmit` (apps/web) | r5 | Passed | — |
| `ruff check`, `ruff format --check` (services/backend) | r5 | Passed (163 files) | — |
| Prettier on changed and untracked web, test and package files | r5; repaired spec rechecked on r6 | Passed | — |
| `git diff --check` | r6 | Clean | — |
| Browser: 3 planned specs (8 tests), system Chromium | r5 | 7 passed, 1 failed (selector flake; see below) | `finalization-evidence/e2e-summary.txt` |
| Browser: golden spec only (3 tests) | r5 | 2 of 3 runs had 1 failure, from the same flake | `finalization-evidence/e2e-summary.txt` |
| Browser: 3 planned specs (8 tests) | r6 | 3/3 runs, 8 passed each; no retries, no flaky marks | `finalization-evidence/e2e-summary.txt` |
| Browser: golden spec only (3 tests) | r6 | 5/5 runs, 3 passed each | `finalization-evidence/e2e-summary.txt` |
| Security review | r5 + r6 diff | No High or Critical findings. S1 fixed | `finalization-security-review.md` |

The 19 skipped tests are the Docker, Harbor and Praxis opt-in tests. They skip because the
socket is `0660 root:docker` and the test process has no access. This is the same as in
earlier stages.

## Browser selector repair (resolved)

- **Failure on r5.** `golden-executable-import.spec.ts:70` failed in 3 of 4 r5 runs. The
  locator `getByRole('alert')` matched both the app's `<p role="alert">Failed to fetch</p>`
  and Next.js's `#__next-route-announcer__` (Playwright strict mode).
- **Origin.** The assertion comes from commit `20dae95`, which is an ancestor of HEAD. The
  app's alert markup is unchanged.
- **Repair (r6).** The locator is now
  `getByRole('alert').filter({ hasText: 'Failed to fetch' })`. It still asserts the alert
  role and the expected error, and every other assertion is unchanged.
- **Result.** 8 of 8 r6 runs passed, with no retries.

## Release limitations

**L1: Design constraint (Low).** Provider calls must stay outside `guard()` transactions
(`finalization-security-review.md` S2).

**L2: Carried over from `correction-qa-report.md`.**

- D-COPY: the next-action label wording is pending human review.
- C2: these tests pass with a container-free stub only.
- C4c: the root cause is unproven.
- Results are fixture-only; there is no live-model verification.

**L3: Not run.**

- the full `pnpm test:e2e`;
- the `chrome` channel and cross-browser checks;
- an accessibility audit;
- dynamic or penetration security testing;
- the 19 Docker-gated tests.

## Dev-stack state

- **Worker.** pid 1097806, healthy, live providers off, no provider or GitHub keys in its
  environment. The earlier worker pids (386427, then 908028 and 970640) were replaced only
  through `scripts/local.py worker-restart`.
- **No restart for r6.** The worker was not restarted for r6, because the worker code is
  unchanged.
- **API and web.** API pid 121952 and web pid 121956 were not touched. API health is
  `ready` with `live_inference` and `harbor_live_dispatch` both `disabled`, and the web
  returns 200.
- **Leftovers.** Test databases from the existing `owned_journey` and marketing tests are
  left as those tests' design leaves them.
