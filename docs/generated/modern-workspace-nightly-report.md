# Modern workspace nightly checkpoint — 30 October 2026

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

1. Integrate diagnostic tasks/runs and their exact safe snapshots into the modern journey.
   Preserve blinded unfinished grading; finalized output evidence only in general views.
2. Build the full separate task/rubric/evaluation successor editor and explicit two-profile
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
