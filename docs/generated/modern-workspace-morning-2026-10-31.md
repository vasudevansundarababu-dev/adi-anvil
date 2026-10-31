# Modern workspace morning handoff — 31 October 2026

**Status: partial local build.** The modern journey is available locally alongside classic.
This is a development checkpoint, not a deployed release or complete MVP acceptance.
The nightly window began 2026-10-31 03:08 UTC and ends at 11:00 UTC (06:00 Chicago).
Build branch: `codex/anvil-modern-workspace`. Source checkpoint: `740b3b2`.
Classic comparison remains pinned to `3a17429c3e7bfe0314361dda5209ce890d96c8e3`.

## What can be reviewed

- Authenticated modern project workspace, task-level Harbor and diagnostic histories,
  result/failure dashboards, safe observable evidence, frozen task/rubric/protocol/package
  snapshots and conservative metric comparisons. Unfinished diagnostic grading stays blinded.
- Persisted model and typed framework profiles; immutable model versions, disabling,
  explicit credential bindings and declared pricing metadata. Local credentials are
  encrypted and write-only, with save/rotate/revoke tests. Cloud credential writes stay disabled.
- Scoped Admin engineering actions, Admin/RL Engineer profile projection and read-only
  People. Existing role grants remain authoritative; no blanket promotion or identity changes.
- Separate constrained diagnostic successor editor for public task, rubric and protocol
  fields. Existing runs retain their versions; new drafts need the existing review path.
- Typed execution presets and exact-version multi-model preparation records. Saved records
  open read-only; creating another opens a fresh form with blank budget. Fully loaded sole
  package/preset choices use summaries. Model selection remains explicit. Keyboard focus,
  task-scope reset, loading and visible error/retry states were improved.
  Newly saved/rotated/revoked credential metadata stays visible even when its UUID lies
  outside the first list page; loading later pages does not duplicate that record.
- Internal credential-bound native SDK mock contracts for OpenAI, Claude and Gemini.
  These expose no route and create no job, reservation or live qualification.

## Verification

| Command | Result |
| --- | --- |
| `pnpm check` | Passed lint, formatting, types, production build and generated OpenAPI on final source |
| `pnpm test:unit` | 224 passed,3.74s |
| `ANVIL_TEST_HARBOR=1 ANVIL_HARBOR_DOCKER_HOST=unix:///Users/vasudevansundarababu/.docker/run/docker.sock pnpm test:integration` | 162 passed,2 optional skips,177.40s; all app workers stopped |
| `pnpm test:e2e` | Final full14 passed,2.2min |
| `pnpm test:e2e tests/e2e/modern-workspace.spec.ts --grep 'Admin modern workspace'` | Targeted credential-page omission1 passed,6.8s |
| `pnpm test:e2e tests/e2e/workspace-preparation.spec.ts` | Targeted readiness/list failure recovery1 passed,6.2s |
| `pnpm backup:local` / `pnpm restore:test` | Passed SQL/artifact restore and separate workspace row-digest comparison |
| `git diff --cached --check` / staged credential-pattern scan | Passed before source checkpoint; no private artifacts staged |

Fresh and repeated migrations001–030 are exercised by the isolated marketing integration.
The two optional integration skips require `ANVIL_PRAXIS_EXPORT_PATH`, which was not supplied.
All provider transport checks are mocked; Harbor checks use the pinned local Docker runner
and synthetic tasks. None measures real model performance. Authlib/Alembic deprecations
and the browser NO_COLOR/FORCE_COLOR notice did not cause test failures.

Earlier browser selector corrections and a malformed-Unicode mock-test setup correction
are documented in BUILD-STATUS.md. This final review found a hidden saved-list failure and
a stale history-pagination error; both were repaired, with saved-list error/retry coverage.
The first final full browser run passed12/14. It exposed a real credential-list regression:
the newly saved UUID could disappear outside page1. The UI now retains the exact safe write
response and deduplicates later pages; a deterministic omitted-first-page browser check passed.
The second failure was a one-request outage fixture consumed by development effect remounts;
the test now holds the outage until explicit retry. Its targeted browser check passed.
No assertion or access boundary was weakened. Broader M5 acceptance remains partial.

## Recovery and evidence

`pnpm backup:local` and `pnpm restore:test` passed with app workers stopped. Private backup
`.local/backups/20261031T101237Z-5eac472a` restored into the new retained database
`anvil_restore_a4bf4e87ad55`: 1,194 pending reviews preserved, 6,171 artifact checksums
verified, original database unchanged. All row digests across ten workspace tables match
the restored database at schema030, including credential metadata and immutable bindings.
This tests SQL, artifacts and metadata recovery. Local credential ciphertext/wrap-key files,
environment configuration and Keycloak recovery were **not** recovery-tested by this backup.

Private browser evidence is under `artifacts/test-runs/`: `modern-workspace-admin.png`,
`modern-diagnostic-mobile.png`, `modern-version-editor.png`, `modern-people-mobile.png`,
`modern-model-version-editor.png`, `modern-preparation-mobile.png`, `harbor-workbench.png`
and `playwright.json`. Preparation coverage includes 320/768/1440px, keyboard activation,
dark readiness view and injected detail/list failures with retry. This is targeted coverage,
not a full accessibility audit. Older Sales Kit PDFs remain historical and were not
newly rendered or verified in this increment. No private artifacts or raw logs are committed.

Original synthetic demo cases are MKT-001 (promotion), FIN-001 (finance/debt choice) and
STR-001 (market entry). Scripted fixture-correct reviews expect100/pass; constraint-blind
reviews expect70/fail. Six such scripted reviews yield3 passes,3 failures and mean85.
These are scoring-software assertions, not independent expert validity or model performance.
Expected fixture answers are never candidate inputs.

## Remaining work

1. Implement atomic shared spending admission and credential-mediated workspace execution,
   with exact reviewed pricing, rights, model/budget authority, run decisions and durable
   dispatch uncertainty handling. This software path is unfinished, not merely missing keys.
2. Qualify exact provider/model/task/runtime combinations. Native SDK mocks do not establish
   live, Harbor-task or structured-output qualification. LangSmith/Semantic Kernel remain
   saved metadata; external tracing and their execution adapters are unavailable.
3. Finish the two-profile authorization migration and People invite/access actions while
   preserving existing identities and historical decisions. Current People is read-only.
4. Extend source/actor authoring beyond the constrained successor editor. Source instruction
   changes currently require a new import; private references/calibration are not exposed.
5. Complete broader accessibility, failure/empty/cancellation coverage and remaining MVP
   general-upload/non-synthetic qualification. Do not weaken existing isolation or gates.

Live verification was **not run**. No exact live provider/model/budget/rights/approval package
or real credential was used. External model requests by this build:0; inference spend
incurred by this build:0. Provider-account billing balance is **unknown/not queried**.
No deployment, GitHub push, real email, external sending, IAM change, global install or
identity grant occurred. Existing data/volumes, classic branch and unrelated user edits
in AGENTS.md and the Google Cloud runbook were preserved.

## Local review and safe resume

- Modern: http://127.0.0.1:3202/workspace
- Classic: http://127.0.0.1:3202/ (project routes remain `/p/{project}/...`)
- API health: http://127.0.0.1:8200/api/v1/health
- Local test account location: `.local/demo-accounts.md`; no credentials are in this report.

The comparison app is left running with the dedicated synthetic-only Harbor worker;
both live switches must remain disabled. `pnpm stop` stops registered app processes and
preserves infrastructure/data. Tested startup command:

```sh
ANVIL_HARBOR_WORKER_ENABLED=synthetic-checks-only ANVIL_HARBOR_DOCKER_HOST=unix:///Users/vasudevansundarababu/.docker/run/docker.sock pnpm dev
```

Installed versions: Node24.21.0, pnpm10.34.5, Python3.12.14, Next.js16.3.6,
FastAPI0.141.1, LangGraph1.2.12, OpenAI2.54.0, Anthropic0.125.0, google-genai1.75.0.
No dependency was installed for this final increment.

Next nightly window: read BUILD-STATUS.md and plan08 first, check for another writer,
confirm local health and resume the remaining admission design/implementation with mocked
transports and ledger/access-boundary tests. Preserve user edits. Stop by06:00 local;
never restart the eight-hour clock at a heartbeat. Nightly automation remains enabled.
