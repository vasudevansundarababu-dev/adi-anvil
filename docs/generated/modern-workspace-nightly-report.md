# Modern workspace nightly checkpoint — 30 October 2026

00:00 continuation checkpoint `9bddc3d` adds a separate diagnostic successor editor. It edits public task,
rubric and protocol fields, shows a before/after review and paginated immutable version
history, and saves an unapproved draft through the canonical revision path. Prior approvals
and existing run snapshots remain unchanged. Private anchors/references/calibration and
actor assets stay server-side; changing source instructions requires a new import. Only
the scoped author or Admin may append, with audited Admin overrides and current-author
self-approval checks. Historical versions are read-only. Full browser11 passed (1.6m),
unit202 passed and targeted editor/diagnostic integration5 passed. Final `pnpm check`
passed; isolated `pnpm test:integration`90 passed/12 opt-in skipped in54.36s after stopping
registered workers. Staged whitespace/credential-pattern scan passed. The12 skips are
opt-in integration paths; the historical real Harbor full integration95/2 result below
was not rerun this hour. Full browser did rerun the real staged synthetic Harbor check.
Latest app and synthetic-only worker restarted for local classic/modern comparison.
This is a constrained editor slice, not completion of M4 or full source authoring.
The initial integration test used incorrect lineage column names; repaired. A retained
diagnostic history assertion now follows cursor pages rather than assuming page-one
membership; no data reset or weakened isolation assertion was used.

23:00 continuation checkpoint: `a96af51` adds diagnostic task/run history, prepared-run
membership, finalized-only result evidence, safe exact-version task/rubric/protocol snapshots
and complete-cohort comparison rules. Read-only routes retain project isolation and grading
blinding; unfinished pass/fail outcomes are masked, not just scores and candidate names.
Mobile390px overflow was repaired. Latest validation: production/type/lint/format/OpenAPI
passed,199 unit passed,86 normal isolated integration passed/12 opt-in skipped (54.82s),
targeted modern browsers2 passed (7.6s). Dataset-bound planned counts have additional
unit coverage. No paid calls, deployment or external credential transmission. Next: M4 editor,
profile migration and qualified model/preset execution preparation.

Status: **partial local implementation**. Autonomous build started22:08 America/Chicago;
verified code checkpoint `d2dfe82`.
this is the initial verified checkpoint, not a declaration that all approved screens and
runtime integrations are complete. Nightly continuation runs hourly22:00–06:00; the
calling Codex app and machine must be available. Each wake resumes BUILD-STATUS.md,
preserves unrelated edits and keeps the same06:00 nightly deadline.

## Delivered locally

- Branch `codex/anvil-modern-workspace`; preserved baseline `codex/anvil-classic-v021-comparison`.
- Separate modern `/workspace` shell and classic `/p/{project}/...` journey, with links
  between them. Both read canonical project data; the existing deployed site is unchanged.
- Project-scoped, paginated Harbor tasks and all-version run history; retained result,
  failure/unknown, criterion, snapshot, output and accounting views. Bound internal evidence
  is inspected through classification/hash/size checks. No fabricated trajectories.
- Side-by-side metrics with conservative signature checks; live comparisons remain
  descriptive until full execution-settings compatibility is implemented.
- Persisted multiple named model profiles and typed Harbor/LangSmith/Semantic Kernel
  metadata. Unimplemented adapters stay visibly unqualified; saving installs/calls nothing.
- Admin includes scoped Harbor engineering actions. Existing exact package, rights and
  real paid decisions remain required; no blanket role bypass or seeded-account promotion.
- Local write-only encrypted credential creation, rotation/revocation and exact-version
  profile binding. Scope-authenticated ciphertext and separate owner-only wrap key;
  cloud writes disabled. New profiles cannot use the legacy global key by substitution.
- Additive migrations026/027 applied to the local database. No resets or volume deletion.

## Verification

| Command                                                                                             | Result                                                             |
| --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `pnpm preflight`                                                                                    | Passed with local Docker access; existing infrastructure reused    |
| `pnpm db:migrate`                                                                                   | Passed through027; PostgreSQL/checkpoint setup retained            |
| `pnpm check`                                                                                        | Passed lint, format, types, production build and generated OpenAPI |
| `pnpm test:unit`                                                                                    | 195 passed                                                         |
| `pnpm test:e2e`                                                                                     | 9 passed in1.5m; real OIDC/classic/new/Harbor software journey     |
| `ANVIL_TEST_HARBOR=1 ANVIL_HARBOR_DOCKER_HOST=<authorized local Unix socket> pnpm test:integration` | 95 passed,2 skipped in162.15s with app workers stopped             |
| `git diff --check`                                                                                  | Passed                                                             |

The two integration skips require an external Praxis export path, not supplied in this
run. All Harbor and credential test inputs are synthetic/test-only. Real paid inference
was not run; no new paid-call authority or real model key was supplied. Existing Authlib
and Alembic deprecation notices remain; they did not fail checks.

The first browser attempt used an exact accessible label before the existing Form helper
added its required-field suffix; the next used an ambiguous classic heading. Both test
selectors were corrected and the complete suite passed. A retained-project negative
security test was repaired to select an originally static task and a different source,
instead of whichever published task sorts first. The unsupported-mode/source checks were
preserved. Async project/view races and incomplete live-comparison eligibility were found
in read-only review and corrected before final checks.

Evidence screenshots: `artifacts/test-runs/modern-workspace-admin.png` and
`artifacts/test-runs/harbor-workbench.png`; browser JSON at
`artifacts/test-runs/playwright.json`. These private test artifacts are ignored by Git.
No secrets or raw logs are committed. Existing AGENTS.md and Google Cloud runbook edits
remain excluded from this checkpoint.

## Next nightly work

1. Diagnostic task/run read integration is now verified; extend editing and preparation
   while preserving blinded unfinished grading and finalized-only general output evidence.
2. Finish source authoring beyond the constrained diagnostic successor editor and explicit two-profile
   capability migration without rewriting historical identities or paid decisions.
3. Qualify exact profile/credential bindings, atomic shared multi-model spending groups,
   run preparation and versioned framework compositions. No silent legacy key fallback.
4. Complete People/Limits actions, comparison/filter/error/cancellation states and responsive
   keyboard/light/dark coverage. Managed cloud credentials and external SDK adapters remain
   unimplemented until separately qualified; no arbitrary installs or deployment.

Open locally after startup: http://127.0.0.1:3202/workspace. Classic entry:
http://127.0.0.1:3202/. Local test account locations remain in ignored `.local/demo-accounts.md`;
no password is included in this report. The launcher can register the dedicated synthetic
Harbor worker when explicitly opted in; `pnpm stop` stops registered app/worker processes
while preserving infrastructure and all data.
