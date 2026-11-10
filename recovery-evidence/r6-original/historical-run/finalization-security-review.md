# Security review: readiness explanations and finalization fix (REQ-TRX-006)

- Work ID: `anvil-task-readiness-explanations-2026-11-06`
- Authority: `approvals.md` §8.
- Scope:
  - the cumulative readiness-explanation and per-blocker link changes (the frontend and
    contract files in `finalization-evidence/code-manifest-r5.sha256`, unchanged since r2);
  - the finalization diff (`finalization-evidence/finalization-fix.diff`);
  - the r6 browser-test selector diff (`finalization-evidence/e2e-selector-fix.diff`). It
    is test-only and has no security effect: the alert role and the expected error text
    are still asserted.
- Final tree: `finalization-evidence/code-manifest-r6.sha256`. It is identical to r5 except
  for that one spec line, so the r5 backend results below apply to r6 unchanged.
- Method:
  - code review of the changed files and the server routes they call;
  - a lock-order review of every `FOR UPDATE` and `project_fence` call that touches
    projects, runs, episodes and jobs;
  - targeted scans;
  - the existing authorization, isolation and spend tests from the r5 full runs, ×2
    (`finalization-evidence/qa5-full-*.status.tsv`).
- Not performed: dynamic or penetration testing, a dependency audit (no dependencies
  changed), an accessibility audit, and a review of code outside this scope.

## Findings

| ID | Severity | Area | Status |
| --- | --- | --- | --- |
| S1 | Medium | Integrity and availability of run finalization (lost completion, duplicate audit, deadlock) | Fixed in r5 |
| S2 | Low | Throughput risk if provider I/O is ever placed inside `guard()` | Open (design note) |
| S3 | Info | One group-ID path segment in a share link is not encoded | Accepted |

### S1: Run finalization concurrency (fixed)

- **Impact.** Concurrent finalization could leave a run in `review_pending` for good. That
  blocks the final report and sales kit, which need `reviewed`, `execution_complete` or
  `cancelled`.
- **Audit integrity.** Duplicate delivery wrote two `episode.finalized` audit events for
  one episode.
- **Deadlock.** Cancel racing the last finalization could deadlock. The worker then failed
  the job with `DeadlockDetected`, while the cancel itself survived.
- **Fix.** See `finalization-implementation-report.md`. The fix applies one global lock
  order (project → run → episode/job) and makes finalize idempotent.
- **Verification.** The 5 deterministic tests fail on HEAD and pass on r5 (3 runs each).

#### Lock-order review

| Path | Order after the fix |
| --- | --- |
| Worker `guard()` transactions (validate, invoke, await review, finalize, cancel check) | project `KEY SHARE` → run → job → episode |
| Worker failure path (`episode` / `resume`) | project `KEY SHARE` → run → job → episode |
| Run cancel (`/runs/{rid}/cancel`) | project `FOR UPDATE` (`idempotent`) → run → episodes → jobs |
| Review, resolve-issue, adjudicate | project `FOR UPDATE` (`idempotent`) → episode |
| `sales_kit_prepare`, `domain.create/move` | project `FOR UPDATE` only (no run or episode lock) |
| Marketing runtime | Own path: project `FOR UPDATE` → episode. `lock_run` is not used there |

- No worker transaction that holds the project `KEY SHARE` later asks for the project
  `FOR UPDATE`. That rules out the upgrade deadlock that the `project_fence` docstring
  warns about.
- **Fencing.** The lease token and expiry still guard every worker write. Cancel still
  wins over an in-flight finalizer: the finalizer sees `lease_lost` and writes nothing.

### S2: Lock scope (open, design note)

- **Current scope.** The run lock and project `KEY SHARE` are held for each guarded worker
  transaction. Today those transactions do only fixture reads and writes; live inference
  is disabled and does not run inside `guard()`.
- **Requirement for future live inference.** Any design that adds live inference must
  invoke the provider outside the locked transaction. Otherwise one slow provider call
  would block that run and its project's API mutations.

### S3: Share-link path segment (accepted)

- **Where.** In `WorkspaceExecutionGroups.tsx`, `share` is built as `href + '/' + selected.id`.
- **Why it is acceptable.** `selected.id` is a server-generated UUID from an authorized
  project query, and React escapes the attribute. The preparation link already uses
  `encodeURIComponent`.
- **Status.** No change is needed for safety. It is noted for consistency only.

## Checks with no finding

- **XSS and injection.**
  - `ReasonList` renders the subject, text, fixer label, diagnostic and link label as React
    text nodes.
  - The changed web files contain no `dangerouslySetInnerHTML`, `innerHTML`, `eval` or
    `new Function`, and no `javascript:` URLs.
  - The one `window.location.assign` is pre-existing and uses an internal path plus a
    server ID.
  - Unknown reason codes are not echoed back. Only a value that matches
    `^[a-z][a-z0-9_]{0,63}$` is shown, as a "Diagnostic code".
- **Link destinations.**
  - Every `href` is the workspace route base plus a fixed suffix (`/models`, `/frameworks`,
    `/execution-groups`, `/tasks`), or the current page, or `#execution-group-run`.
  - No link takes any part of its value from reason text or from user input.
- **Authorization.**
  - The rule that Engineers never see an Admin-only destination (`ADMIN_ONLY` → escalate)
    is a UI hint, not an authority. The server still enforces authorization on every
    destination.
  - These r5 tests passed ×2: `test_existing_admin_authority_requires_current_active_project_admin` (3 cases),
    `test_readiness_is_not_visible_outside_the_project`, `test_missing_context_and_cross_project_rls`,
    `test_cross_project_mutation_matrix_preserves_foreign_records`,
    `test_cross_project_endpoint_substitution` (7 cases) and
    `test_web_role_cannot_access_checkpoints_and_worker_cannot_read_private_references`.
- **New read call.**
  - `ImportStateNote` calls the existing `GET /tasks/{sid}/executable-import`. That route
    runs in the RLS project context, requires `admin` or `rl-engineer`, and returns 404 for
    a source outside the project.
  - The UI calls it only when `canPlan` is true, and it ignores errors silently.
- **Information disclosure.**
  - The catalog and contract text contain no hidden references, grader or rubric content,
    or credential values. The credential reason texts state only a status ("no saved API
    key", "revoked", "rotated").
  - The finalization change keeps worker errors as codes only.
- **Spend.**
  - No changed path calls a provider or reserves budget.
  - `test_readiness_reads_and_blocked_launches_have_no_provider_or_spend_effects` passed
    ×2.
  - Live inference and Harbor dispatch are `disabled` on the dev stack.
- **Secrets.**
  - A scan of the changed code, the new test, the finalization evidence and `approvals.md`
    found one false positive: `sk-readiness-…` inside the work ID
    `task-readiness-explanations`.
  - The evidence contains no UUIDs, environment values or home paths.

## Conclusion

- No High or Critical findings.
- S1 is fixed and covered by regression tests.
- S2 is a forward-looking design constraint.
- S3 is informational.
