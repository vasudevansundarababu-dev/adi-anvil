# QA report — DRAFT / PENDING HUMAN APPROVAL — task-readiness explanations

Work ID: `anvil-task-readiness-explanations-2026-11-06`. Role: anvil-qa, under the coding
approval quoted in `approvals.md` §5. Recorded 2026-11-06 (UTC). Nothing was committed,
pushed or deployed. No issues were created and no product model provider was called.

Approval basis, as recorded in `approvals.md` §5: the user's broad coding approval ("I
approve the coding changes. Run the QA agent on the same Anvil branch and investigate the
failing integration tests. Keep my local changes untouched and stop for my approval before
deployment."). It approves proceeding with the current coding changes to QA. QA does not
read it as a waiver of any specific requirement, and it does not authorize deployment.

Per-test integration detail: `integration-failure-analysis.md`. Durable sanitized evidence:
`qa-evidence/`.

## Approved requirements, plan and exact code revision

- Requirements: `prd.md` (SHA-256 `eb6e8aac45d305063bf0966b7f7551cac71df6db2dd1ab19c0c0b94e00fbb9af`).
- Plan: `plan.md` (`8af2f4b48bbe1a8fac805b613b4b706ef2fb899371b8e9901e076af84543da89`).
- Code: base `8cdc8a84784c7ae52d7bbb88f36193b387aedb60` on `codex/anvil-agent-team-2026-11-06`,
  plus the uncommitted Coding increment. QA is bound to the 16 code, test and config files
  listed in `coding-handoff.md`. Their manifest digest is
  `28030dc2fa54b4c65a26986757a36b0285ee1102851ae4df6cd1c99ae7d27769`. QA rechecked it after
  every run, and it did not change. Backend source, migrations and lock files are
  identical to base (`git diff HEAD -- services/backend/src services/backend/migrations`
  is empty).
- Environment: provider and agent keys unset (`ANTHROPIC_API_KEY`, `OPENHANDS_API_KEY`,
  `GITHUB_TOKEN`, `OPENAI_API_KEY`). Every subprocess had `ANVIL_LIVE_PROVIDERS_ENABLED=false`
  and `ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED=false`. The local stack reported "Live inference
  disabled". Only local Postgres, Keycloak and Neo4j containers and synthetic fixtures were used.

| Requirement | Test / command | Expected | Observed | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| REQ-TRX-001 | `node --test tests/provider_failure.mjs tests/readiness_catalog.mjs`; `pytest services/backend/tests/unit/test_readiness_reason_codes.py` | Every server-produced code has a catalog entry, and drift fails | ui-policy 9/9 passed; readiness unit 2/2 passed (also included in the 350-test unit run); full unit suite 350 passed | PASSED | `qa-evidence/qa-checks-summary.md` (UI-policy, unit) |
| REQ-TRX-002 | Code review of `WorkspaceExecutionGroups.tsx:230-244`; browser `workspace-preparation.spec.ts:313` | Each blocker shows the cause, who can fix it, and **one next-action link** | Cause and fixer are shown on each item. Links are only at panel level: Admins get "Open Models & keys" and "Change run configuration", Engineers get only "Change run configuration". Engineers never see the Admin-only link. | **PARTIAL — acknowledged implementation gap** | F5 below |
| REQ-TRX-003 | Browser `workspace-task-pages.spec.ts:326`, `golden-executable-import.spec.ts:177`; catalog test "seven approved import states…" | The 7 states each show a label, reason and next step on list and detail | Passed. The detail page is checked in the browser only for the no-revision case; the other states use a fulfilled list response (see implementation-report.md). | PASSED (fixture coverage) | `qa-evidence/qa-checks-summary.md` (browser) |
| REQ-TRX-004 | Catalog test "readiness wording makes no score, quality or performance claims" | No admission or performance claim | Passed | PASSED | `qa-evidence/qa-checks-summary.md` |
| REQ-TRX-005 | Catalog test "unknown codes use the generic explanation with only a safe secondary diagnostic"; `CODE_FORMAT = /^[a-z][a-z0-9_]{0,63}$/` (`readinessCatalog.ts:11`) | Generic text; diagnostic only if it matches the format; unknown codes block | Passed. `runBlockerItems` (`readinessCatalog.ts:301-315`) keeps unknown codes as blockers. | PASSED | `qa-evidence/qa-checks-summary.md` |
| REQ-TRX-006 | `test_workspace_execution.py::test_readiness_is_not_visible_outside_the_project` | No readiness data for outsiders | Passed in 2 of 2 full current runs | PASSED in tests; **security review not done (release limitation)** | `qa-evidence/qa-cur-full-{1,2}.status.tsv` |
| REQ-TRX-007 | Code review: base `executionReadiness.ts:34-47` vs current `readinessCatalog.ts:301-324`; `WorkspaceExecutionGroups.tsx:102-117`; catalog test "blocker semantics are unchanged…" | Server is the only authority; same blocking set; Admin rule kept; Run rechecks readiness on click | Same filter and the same per-model reasons, with the Admin `admin_run_authorization_required` exception. Launch fetches fresh readiness before POST. The server still enforces the decision (409 in the T8 test). | PASSED | `qa-evidence/qa-checks-summary.md`; T8 rows in `qa-evidence/qa-cur-full-*.status.tsv` |
| REQ-TRX-008 | `test_workspace_execution.py::test_readiness_reads_and_blocked_launches_have_no_provider_or_spend_effects` | No provider dispatch; counts of spend windows, Harbor checks and jobs unchanged | Passed in 2 of 2 full current runs. `workspace_dispatch.execute` is patched to fail the test if called. | PASSED | `qa-evidence/qa-cur-full-{1,2}.status.tsv` |
| REQ-TRX-009 | Browser `workspace-preparation.spec.ts:313` | `role=alert`/`status`, focus after Run, descriptive link names | Passed for the tested panel only. No full accessibility audit was done. | PASSED (limited) | `qa-evidence/qa-checks-summary.md` (browser) |
| G4 / regression | Full backend integration suite on current code and on base | No change in admitted runs and no new failures | Current: 39 failed / 146 passed / 19 skipped (twice). Base: 39 / 144 / 19. **Identical per-test status for all 202 shared tests**; both new tests pass. | Suite **FAILED**. No new failing shared tests observed in matched runs; 39 failures mask some assertions, so regressions behind them cannot be excluded. | `integration-failure-analysis.md` |
| Browser regression (planned specs) | `playwright test -c /tmp/anvil-code/pw.local.config.ts` (3 planned specs) | All pass | 8/8 passed in 44.7s | PASSED | `qa-evidence/qa-checks-summary.md` (browser) |

## Isolation, auth, rights, hidden-reference and budget negatives

- Cross-project: the outsider receives 403/404, and the readiness payload is absent
  (T8 test, passed). Existing cross-project suites in `test_api_security.py` (for example
  `test_cross_project_mutation_matrix_preserves_foreign_records`) **could not run**. They
  fail on the missing `journey.json` prerequisite on both base and current, so they give no
  evidence either way.
- Role: Engineers get Admin-directed wording and no Admin-only link (catalog test, browser
  test). A forged Engineer launch with a cap and rights is rejected with 403/409 (T8 test).
- Hidden references and grader content: the catalog emits only fixed text and the
  format-checked code. The golden browser test confirms no private oracle is exposed.
- Budget: blocked launches and readiness reads create no spend windows, Harbor checks or
  jobs, and dispatch no provider request (T8 test).
- Not verified: the pre-existing role and project suites that are blocked by F1.

**Release limitation: security review not done.** REQ-TRX-006 lists "security review" as
a verification method, and QA did not perform one. The review scope should cover:
- the catalog and diagnostic-label path (`readinessCatalog.ts`, `CODE_FORMAT`, `itemText`,
  `modelSelectionMessage`), to confirm no user-supplied text, IDs, credential detail,
  hidden-reference or grader content, or cost-authority detail can be rendered;
- role-specific wording and links for Engineer versus Admin, including the retained Admin
  rule for `admin_run_authorization_required`;
- the readiness endpoints' project scoping and outsider responses (T8 test), plus the
  cross-project and role assertions currently masked by F1;
- confirming that readiness reads and blocked launches cause no provider dispatch or
  spend (REQ-TRX-008);
- the import-state explanations on list and detail pages, for hidden-reference leakage.

## Regressions, severity and reproduction

**Integration result: FAILED (39 failures).** No new failing shared tests were observed in
matched runs. 39 failures mask some assertions, so regressions behind them cannot be
excluded. In the matched runs, the same command and environment, run on an unchanged
`git archive` copy of `8cdc8a8` (`/tmp/anvil-base`, confirmed by `diff -rq` to equal HEAD),
gave the same 39 failures with the same exception types. A row for each of the original 42
node IDs, with reproduction commands and qualifications, is in
`integration-failure-analysis.md`. Results:

| Run | Tree | Result | JUnit SHA-256 |
| --- | --- | --- | --- |
| cur-full-1 (dev stack running) | current | 39 F / 146 P / 19 S | `513ee99b7fe7cb067218fbb9f8b7437ffaacd16898de093a45b8842b68c7a276` |
| base-full-1 (dev stack stopped) | base `8cdc8a8` | 39 F / 144 P / 19 S | `62d2fd2a70cdf8f75bba1913207eea1cb56b7170b8b2c78bbd4585f76ab75d75` |
| cur-full-2 (dev stack stopped) | current | 39 F / 146 P / 19 S | `f7a05c5ae042a0c228405ccf5ff2898c5e03c046d8c1126a6a9ccf63a7959bfb` |

Runner: `/tmp/anvil-qa/run-integ.sh`. It uses the same shape as `pnpm test:integration`
(`.env` plus `ANVIL_ROOT`), with keys removed and live inference forced off. The equivalent
command is in `integration-failure-analysis.md` (Reproduction section).

**F1 — Medium, pre-existing test infrastructure (33 failures).** `FileNotFoundError:
artifacts/test-runs/journey.json`. The only producer is `tests/e2e/journey.spec.ts:426`,
which `playwright.config.ts:5-7` ignores as retired classic UI (commit `ec210a9`,
2026-11-01). QA ran that spec once through an untracked QA-only config to test whether the
prerequisite could be produced legitimately. It **FAILED** with a timeout at
`journey.spec.ts:305-306` (classic `/p/<project>/sales-kits` now redirects to the modern
workspace, `apps/web/src/app/p/[project]/[[...section]]/page.tsx`), so the file cannot be
produced from the current tree. Affected: test_api_security 12, test_worker_failures 11,
test_workspace_editor 4, test_workspace_access 2, test_factory 1, test_isolation 1,
test_task_imports 1, test_workspace_diagnostics 1.
Reproduce: on a checkout without `artifacts/test-runs/journey.json`, run `pnpm test:integration`.

**F2 — Medium, environment prerequisite (4 failures, `test_import_pipeline.py`).** The
import worker probes supplied tools in Docker before the mocked generation stage
(`import_worker.py:260-261` → `import_sandbox.py:189` `docker image inspect`). The required
local fixture image `anvil-golden-tools:1.0.0` (image ID
`sha256:df12b069…`, `contracts/praxis/golden-v3/01-marketing.task.json`) is not present
(`docker image ls`), and the test user is not in the `docker` group (socket `0660 root:docker`).
The failure becomes `validation_failed` or "Docker operation failed: image" instead of the
asserted states. Unlike their siblings, these 4 tests are not gated by
`ANVIL_TEST_HARBOR=1`. QA did not build or import the image: that would need a registry
pull or an archive that isn't available, and a rebuild may not reproduce the frozen image ID.
Tests: `test_installation_scope_project_boundaries_and_unknown_no_retry`,
`test_whole_import_cap_blocks_before_dispatch_and_default_change_does_not_reset`,
`test_usage_capture_survives_actor_revocation_after_dispatch`,
`test_paid_generation_requires_exact_admin_source_processing_permission`.

**F3 — Low, environment and data history (2 failures, `test_workspace_access.py`).**
`test_current_roles_are_exactly_two_and_historical_memberships_are_read_only` (`:20`,
`assert 0 > 0`) and `test_recorded_mapping_is_read_only_scoped_and_audited` (`:147`,
`assert []`) expect rows that migrations `028_workspace_profile_mapping.sql` and
`033_two_roles.sql` copy from memberships that existed **when they ran**. The local DB was
migrated before seeding. A read-only query shows `membership_role_history`,
`workspace_profile_mappings` and the matching audit events all at 0, with 101 memberships.

**F4 — Low, test hygiene: 3 first-run and order-dependent failures in the earlier 42.**
These failed in the Coding run but passed in all three QA runs, on base and on current:
- `test_200_synthetic_source_inventory_pagination_and_search` writes into
  `artifacts/test-runs/` (`test_api_security.py:642`) without creating it. Only
  `test_marketing.py:397`, which runs later, calls `mkdir`. **Reproduced** in a clean
  `git archive` root (sanitized excerpt in `qa-evidence/qa-checks-summary.md`).
- `test_concurrent_shared_ceiling_and_unknown_reservation` requires an approved protocol
  left by earlier runs (`test_budget.py:29-30`). On the fresh database none existed yet; the
  first appeared at 16:29:05Z.
- `test_manifest_dryrun_atomic_commit_dedup_and_quarantine` raised `KeyError: 'data'`
  (traceback line 1691; the researcher's `/tasks?limit=100` read is at
  `test_api_security.py:1690`) on the fresh database. **Root cause not proven.** It is
  consistent with first-run state. It was not among the base failures in the earlier
  isolated run, and it passed in base-full-1 and in both current full runs. The root cause
  remains UNRESOLVED.

**F5 — Acknowledged implementation gap, REQ-TRX-002 (severity: Medium, requirement not
fully met).** The PRD requires one next-action link per blocker. The implementation
provides panel-level links. Coding disclosed this as Partial in `implementation-report.md`.
The broad coding approval (§5) approved proceeding with the current coding changes to QA.
QA records the gap as open; it is not treated as waived.

## Fixture verification versus live model verification

Every result above is a software conformance result from synthetic fixtures, mocked
provider transports and browser `page.route` fixtures. None is a live model or provider
verification: 19 integration tests were **skipped** (Docker/Harbor opt-in), and these are
not counted as passed. The browser blocker test uses an injected draft group and a
representative set of codes, not every code. The full `pnpm test:e2e` suite was not run.

## Recommendation and handoff awaiting human approval

**QA recommendation: HOLD.** QA does not recommend approving deployment now.

- Requirements: 8 of 9 pass on fixture evidence. REQ-TRX-002 remains an acknowledged
  implementation gap (F5).
- Release limitation: the REQ-TRX-006 security review has not been done (scope above).
- Integration: **FAILED (39)**. No new failing shared tests were observed in matched runs.
  39 failures mask some assertions, so regressions behind them cannot be excluded. F1–F3
  block a green gate and hide the pre-existing cross-project and role assertions. The
  `KeyError: 'data'` root cause (row 12 in `integration-failure-analysis.md`) is unresolved.
- Conditions that would support lifting HOLD (each needs separate human approval): a
  decision on the REQ-TRX-002 gap; the security review; and remediation or an explicit
  acceptance of the masked integration coverage.
- QA does **not** approve release. Deployment is not authorized. See `qa-handoff.md`.
