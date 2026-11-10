# Finalization concurrency fix: implementation report

- Work ID: `anvil-task-readiness-explanations-2026-11-06`
- Authority: `approvals.md` §8 (fix the finalization concurrency bug, complete the security
  review, rerun QA, keep local changes untouched, stop before deployment).
- Defect: `correction-qa-report.md` Q1, run finalization race in `worker.py` `finalize`.
- Input: base `8cdc8a84784c7ae52d7bbb88f36193b387aedb60` plus the uncommitted tree bound by
  `correction-evidence/code-manifest-r2.sha256`
  (`378b350819aa58fcd5509e98f0f6fcfe10aa57ac4cfdfce8d41ca13a6a707747`).
- Output: the tree bound by `finalization-evidence/code-manifest-r6.sha256` (30 files). It
  differs from r2 in three files:
  - `services/backend/src/anvil/worker.py` (changed; the product fix);
  - `services/backend/tests/integration/test_finalization_concurrency.py` (new);
  - `tests/e2e/golden-executable-import.spec.ts` (one browser-test selector line, r5 → r6;
    see "Browser-test selector repair").

  The other 27 files, which include all earlier local changes, are byte-identical to r2.
- Nothing was committed or pushed.

## Defects found

All three defects are in `worker.py` at HEAD. The new tests reproduce each one
deterministically (`finalization-evidence/red-green-r5.tsv`).

1. **Lost run completion.** `finalize` locked the job and the episode, but not the run. It
   moved the run to `reviewed` or `execution_complete` only when its own count of unfinished
   sibling episodes was 0. Under READ COMMITTED, two concurrent finalizers (or a finalizer
   and an operational-failure path) each counted the other as unfinished. The run then
   stayed `review_pending` for good.
2. **Duplicate delivery re-ran side effects.** A second `resume` delivery for an episode
   that was already finalized still wrote `episode.finalized` to the audit log (2 events
   instead of 1). It also re-ran the run-state update.
3. **Deadlock with run cancellation.** The run-cancel API locks project, then run, then
   episodes, then jobs. The worker locked job, then episode, and only reached the run in
   its final `UPDATE anvil.runs`. The two orders formed a cycle (`DeadlockDetected`).

## Change

The full diff is in `finalization-evidence/finalization-fix.diff`. In summary:

- **New `lock_run(c, job)`.** It takes `project_fence` (project `FOR KEY SHARE`), then the
  episode's run `FOR UPDATE`. It is called:
  - at the start of `guard()`, so every guarded episode or resume transaction takes the
    locks in the order project → run → job → episode;
  - on the failure path for `episode` and `resume` jobs, before the lease-fenced job
    update. Marketing episodes are excluded because `marketing_runtime` has its own
    locking.
- **Global order.** All of these paths now take locks as project → run → episode → job
  (or project → run → job → episode). This matches cancel and the other API mutations,
  which take the project `FOR UPDATE` first through `idempotent`. `FOR KEY SHARE` conflicts
  with `FOR UPDATE`, so worker and API transactions on one project serialize at the project
  row. No worker episode transaction later upgrades to a project `FOR UPDATE`. I checked
  `artifacts.store/read`, `domain.get_revision/rights_ok`, `evaluation.enqueue` and
  `db.audit`. That keeps the warning in the `project_fence` docstring satisfied.
- **Idempotent finalize.** The `finalized` update now uses `RETURNING`. If the episode was
  already finalized, the transaction returns before the count, the run update and the
  audit write. The job still ends as `succeeded`.

### What is unchanged

- **Fencing.** The lease checks in `guard()` and the lease-fenced failure update are as
  before.
- **Authorization.** Run-author and current-authorization checks are as before.
- **Audits.** The action names, and the rule of one `episode.finalized` event per episode,
  are as before.
- **Codes-only error reporting.** Unchanged.
- **Spend and budget.** There are no changes to spend, budget or provider gates, and no
  new provider, network or I/O work runs while the run lock is held.

### Iteration history

- **r3.** Locked the run only. It passed 4/4 targeted tests, and full run `qa3` passed ×2.
- **r4.** Removed the run lock from the marketing failure path. Full run `qa4-full-2` then
  failed once with `DeadlockDetected` in the cancel test.
- **Cause of the r4 failure.** A third transaction held the project row (in production,
  for example, `sales_kit_prepare` or any idempotent API call). Cancel queued on the
  project, and the finalizer later needed `KEY SHARE` on the project for audit and job
  foreign-key checks while it held the run lock.
- **New test.** `test_cancel_queued_on_project_lock_racing_finalization_does_not_deadlock`
  reproduces that ordering deterministically. It failed on r4 in 2/2 runs
  (`finalization-evidence/three-party-deadlock-r4-vs-r5.tsv`).
- **r5.** Takes the project fence first. It is the final version.

## Tests added

`services/backend/tests/integration/test_finalization_concurrency.py` has 5 tests. They
use real PostgreSQL transactions on the shared session journey. The same deterministic
setup applies to all of them:

- **Interleaving control.** A thread is held inside its open transaction until the
  competing transaction reaches the same point, or until `pg_blocking_pids` shows the
  competitor waiting on it.
- **Isolation from dev processes.** Only the test's own backends count, because each test
  tags its connections with a unique `application_name`. The live dev worker and API
  therefore cannot release a pause.
- **No timing decisions.** Sleeps are used only to poll, never to decide an outcome. Each
  thread joins with a timeout and fails the test if it hangs.
- **Job assignment.** A test seam patches `worker.one` so that `claim_job()` returns the
  assigned leased job. Real claim semantics stay covered by the existing worker tests.

| Test | Interleaving | Asserts |
| --- | --- | --- |
| `test_last_two_episodes_finalized_concurrently_mark_run_reviewed` | Both finalizers paused at the audit write | Both jobs succeed. Both episodes finalized, `invocation_count` 1. One audit event each. Run `reviewed` |
| `test_finalization_racing_operational_failure_completes_run` | Finalizer and `final_review_missing` failure both paused after their counts | Job codes. Episode states. Audits. Run `execution_complete` |
| `test_duplicate_resume_delivery_finalizes_once` | Two deliveries of one episode, then a late redelivery | One audit event. State unchanged by the redelivery. Run `reviewed` |
| `test_cancel_racing_last_finalization_does_not_deadlock` | Cancel holds the run until the finalizer waits on it | Cancel returns 200. Finalizer `lease_lost`. Episode `cancelled`. No finalize audit. Run `cancelled` |
| `test_cancel_queued_on_project_lock_racing_finalization_does_not_deadlock` | A third transaction holds the project; cancel queues, then the finalizer queues | Same as the previous row, with no `DeadlockDetected` |

## Red/green

| `worker.py` | Runs | Result |
| --- | --- | --- |
| HEAD (base) | 3 | 15/15 test executions failed: run stuck `review_pending` (×2 tests), audit count 2, `DeadlockDetected` (×2 tests) |
| r5 (final) | 3 | 15/15 passed |

To run the red cases, the tracked `worker.py` was temporarily replaced with its HEAD copy.
After those runs the r5 copy was restored, and `sha256sum -c code-manifest-r5.sha256`
passed. The dev worker loads its code at startup, so the swaps did not affect it.

## Browser-test selector repair (r5 → r6)

- **Authority.** The coordinator's routine QA repair within the §8 verification scope. It
  is test robustness only, with no production change.
- **Change.** One line in `tests/e2e/golden-executable-import.spec.ts:151`
  (`finalization-evidence/e2e-selector-fix.diff`):

  ```diff
  -  await expect(page.getByRole('alert')).toBeVisible();
  +  await expect(page.getByRole('alert').filter({ hasText: 'Failed to fetch' })).toBeVisible();
  ```

- **Reason.** The unfiltered locator also matched Next.js's `#__next-route-announcer__`
  (also `role="alert"`). That caused a strict-mode violation in 3 of 4 r5 runs.
- **What the new locator still checks.** It still requires an element with the `alert`
  role, and it still requires the expected text, "Failed to fetch". That text is the
  browser's network error after the first `generate` request is aborted.
- **Unchanged.** Every other assertion in the test stays as it was:
  - the button is re-enabled;
  - exactly two requests share one idempotency key;
  - the `source_sha256` binding;
  - the in-progress and complete states;
  - the notebook download filename `anvil-review.ipynb`.

  The test has no retries, skips, added timeouts or `.only`. The word "retries" in its
  title describes the product's behavior, not a Playwright retry. The Playwright config was
  not changed.
- **Manifest.** `code-manifest-r6.sha256` differs from r5 only in the hash of this spec
  file.

## Dev stack

- The registered worker was restarted three times with `scripts/local.py worker-restart`,
  to load r3, r4 and then r5. Final pid: 1097806.
- Live providers are off (`ANVIL_LIVE_PROVIDERS_ENABLED=false`,
  `ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED=false`), and no provider or GitHub keys are in the
  worker's environment.
- API pid 121952 and web pid 121956 were not touched. Health is `ready`, with
  `live_inference` and `harbor_live_dispatch` both `disabled`.

## Residual risks

1. **Throughput.** All guarded transactions of one run now serialize on the run row. This
   is cheap today because they do only fixture work. If live inference is ever placed
   inside a `guard()` transaction, it would serialize the episodes of a run and hold
   project `KEY SHARE` during network I/O. That design must keep provider calls outside
   the locked transaction.
2. **Failure path.** `lock_run` can raise `project_unavailable` only if the project row is
   gone. No code deletes projects.
