# ADI Anvil morning handoff

**Overall: partial. Live verification: blocked. Not accepted as a complete local MVP.**

Authorized launch: 2026-09-28 02:43 UTC. Deadline: 10:43 UTC. Deadline overrun detected at 10:52 UTC; implementation stopped immediately on detection. This handoff records the partial state, not a completion claim.

## What was verified

- Independent pnpm workspace and Python 3.12 virtualenv/uv lock; PostgreSQL, Neo4j and Keycloak Compose services under project `adi-anvil`.
- Real browser OIDC login for nine distinct local identities. Session-backed API calls, objective recommendations and separate scope approval.
- Hash-pinned import of MKT-001, FIN-001 and STR-001; repeated import does not duplicate cases. Explicit local rights review, rubric/content/calibration reviews, task publication, reviewed/frozen suite and reviewed protocol.
- Six illustrative episodes through PostgreSQL queue and LangGraph/PostgresSaver. Duplicate launch replay preserved six invocations. Worker restart while review was pending preserved output and reviews; independent double grading resumed without another candidate invocation.
- Scripted synthetic judgments produced three passes, three critical failures, six valid episodes, mean score 85. These are application fixture assertions, not measured model performance or expert validation.
- Actual authenticated PDF, HTML, ZIP and email-draft downloads. PDF page count was one. ZIP contained an explicit aggregate-file allowlist. Initial PDF visual inspection found transparent page background; renderer was corrected to paint white, but the corrected renderer was not regenerated/reinspected before deadline.
- Six official-SDK/compatible adapters: 73 transport-contract tests passed. Success, missing usage, refusal, truncation, malformed/empty output, authentication/model/rate/server errors and ambiguous timeout covered; one inference request maximum asserted. No real provider calls.
- Four additional scoring/rubric/fixture/PDF tests passed, for 77 unit tests total.
- Three database integration tests passed: runtime nonowner/RLS isolation and immutable revisions; concurrent shared spending ceiling; retained unknown-cost reservation and idempotent settlement.
- Consistent private PostgreSQL/artifact backup restored successfully into a new database. Counts verified: 22 resources, 18 episodes, 30 assessments, 102 checkpoints; 3 pending reviews and 31 artifact checksums preserved. Test history includes an earlier interrupted E2E run, so the database intentionally contains more than one six-episode run.

## Latest state and limitations

The final working tree is **not fully verified**. Later changes added Alembic migration adoption, provider-readiness/configuration routes, designated rights assignments, automatic provisional/refreshed Sales Kit jobs and maintenance commands. Alembic and backup/restore passed; automatic kit jobs and the latest API/worker/UI combination were not rerun end to end.

The last lint invocation failed with 56 import/style/unused-import findings. `pnpm check` is not passing. Frontend typecheck and webpack production build passed before the latest changes. Turbopack production builds failed on subprocess port permission even with requested escalation; the build script now uses the supported webpack path.

Important missing or incomplete work:

- Complete F-ENG/F-SK negative/security matrix, including OIDC failure permutations, session expiry/revocation, assigned-review boundary hardening, stale lease/crash/cancellation cases and actual disagreement/adjudication tests.
- Public partner JSON import/validation/commit, gap editing, external-result import, invitations/member administration, structured draft/successor editing and full typed-detail/API baseline compatibility. General uploads remain quarantined; no scanner qualification.
- Findings UI and complete evidence-link validation; graph outage/rebuild/replay tests, full graph lineage coverage and generation validation. Diagnostics presently verifies projected node hashes against canonical records and returns canonical relationships.
- A fully usable provider configuration UI and integrated live authorization/dispatch path. Adapters are **network-free SDK contract implementations**, not live-ready providers. The paid-approval endpoint deliberately blocks seeded identities and absent user authority. Budget mechanics are tested separately; reservation does not grant dispatch.
- Final Sales Kit automation verification, immutable release/download artifact binding, complete revocation/correction tests, fixture mail-delivery mechanics and final one-page visual QA. Real sending is disabled.
- Dockerfiles, CI workflow/checks, generated API client, full OpenAPI schema fidelity, dependency/advisory/secret audit, fresh clean startup, 200-record load fixture/performance measurement and responsive/keyboard coverage at required sizes.
- Root scripts exist, but the entire root command contract is not verified; some implementations still need hardening (configurable ports, collision/ownership detection, startup failure detection, lock/cache behavior, backup permissions).
- No local Git commit was created. Branch `build/overnight-v1` exists; all supplied and authored files remain untracked. Do not blindly stage the workspace. Secret scan and explicit staging remain required.

## Tested commands and results

| Exact command | Result |
| --- | --- |
| `python3 scripts/local.py preflight` | Passed tool/Docker checks; Anvil infrastructure ports occupied as expected after startup |
| `python3 scripts/local.py services-up` | Passed; isolated local infrastructure started |
| `python3 scripts/local.py migrate` | Passed SQL migration; later passed Alembic adoption and checkpoint setup |
| `python3 scripts/local.py seed` | Passed idempotent identity/project seed; no paid approvals or completed episodes seeded |
| `python3 scripts/local.py dev` | Started registered web/API/worker processes and verified DB/OIDC |
| `pnpm --filter @anvil/web check` | Passed before latest backend/automation edits |
| `pnpm --filter @anvil/web exec next build --webpack` | Passed production build |
| `pnpm exec playwright test` | Expanded real-OIDC journey passed, 1 test, 12.7 seconds; includes worker restart/downloads |
| `python3 scripts/local.py unit` | 77 passed, 2.53 seconds; Authlib deprecation warning |
| `python3 scripts/local.py integration` | 3 passed, 0.21 seconds |
| `python3 scripts/local.py backup` | Passed consistent database/artifact backup |
| `python3 scripts/local.py restore-test` | Passed into new retained `anvil_restore_64a52b7b141e` database |
| `services/backend/.venv/bin/ruff check --config ruff.toml services/backend scripts --output-format concise` | Failed: 56 style/import/unused-import findings at stop |
| `PLAYWRIGHT_BROWSERS_PATH=.local/browsers pnpm exec playwright install chromium` | Failed timeout/DNS; E2E used installed Chrome with fresh isolated profiles |

`pnpm setup:local`, the complete `pnpm check`, fresh-clone startup, `pnpm test:live -- --dry-run`, `pnpm demo:new`, and `pnpm graph:rebuild` were not fully exercised as root commands. Do not describe them as verified.

## Local locations and operating state

- Web: http://127.0.0.1:3202. Ports 3200/3201 were occupied; unrelated processes were preserved.
- API: http://127.0.0.1:8200. Identity: http://127.0.0.1:8180/realms/anvil.
- PostgreSQL: loopback 5542; Neo4j: loopback 7475/7688.
- Local credentials: `.local/demo-accounts.md`, generated owner-only. Secrets also in ignored `.env`/`.local/realm.json`. Do not copy values into chat, Git or reports.
- Web/API/worker stopped at handoff; Compose infrastructure and all volumes preserved. No background work scheduled, no remote created, no cloud/email/Notion action.
- Backup: `.local/backups/20260928T101755Z-b92c8a49/`; manifest and restore verification in that directory. Original database was not overwritten; restore target is retained for inspection.
- Evidence: `artifacts/test-runs/playwright.json`, `journey.json`, `objectives.png`, `sales-kit.pdf`, `sales-kit.png`, `sales-kit.html`, `evidence.zip`, `email-draft.txt`. These ignored artifacts contain local synthetic evidence. Existing PDF is the earlier rendered version; final white-background change is unverified.
- Runtime logs and former process registry: `.local/`. Raw local logs are never to be committed. API access logging was disabled in the latest launcher to avoid callback query tokens in future logs.

## Versions

Node 24.21.0; pnpm 10.34.5; Python 3.12.14 backend (system Python 3.14.6); uv 0.12.19. Next 16.3.6, React 19.3.0, Tailwind 4.3.3, TypeScript 5.9.3. FastAPI 0.141.1; LangGraph 1.2.12; checkpoint-postgres 3.1.2; psycopg 3.3.6; Neo4j driver 6.3.1; ReportLab 4.5.1. Images: postgres:17.6-bookworm, neo4j:5.26.12-community, keycloak:26.3.5. Exact dependencies in independent lockfiles; security/advisory qualification incomplete.

## Morning walkthrough mapping

| Walkthrough | Built route | Status |
| --- | --- | --- |
| MORN-01 objective | `/p/{project}/objectives` | Core API/browser path passed; full editing/negative matrix incomplete |
| MORN-02 cases/qualification | `/cases`, `/rubrics`, `/tasks` under project | Original fixture path passed; general partner import/gaps incomplete |
| MORN-03 run | `/suites`, `/protocols`, `/runs` | Six-episode fixture path passed; latest UI combination not rechecked |
| MORN-04 human review | `/reviews` | Double grading and actual worker restart passed; dispute/reconciliation matrix incomplete |
| MORN-05 diagnostics | `/diagnostics` | Graph metadata/table response exercised; outage/rebuild walkthrough not run |
| MORN-06 exports | `/reports`, `/sales-kits` | Downloads and one-page count passed; final visual/automation checks pending |
| MORN-07 negatives | Same routes/direct API | Selected CSRF/role/project/idempotency tests passed; full walkthrough not run |
| MORN-08 live | `/providers` | Blocked; no keys/models/budget/rights/real paid approvals, live dispatch not qualified |

## Spend and next action

Observed model-inference requests: **0**. No paid model credentials were used. Provider billed spend is **unknown/not queried**, not claimed to be a reconciled zero-dollar bill. Synthetic ledger test amounts are not real spending.

Resume with a new explicit work window. Read `BUILD-STATUS.md`, inspect the untracked working tree, fix lint, run compilation/unit/integration checks, restart only Anvil, then rerun E2E on the final sources. Verify automatic kit jobs and the corrected PDF visually. Finish missing security/P0 criteria before calling the local MVP complete. Preserve existing projects/volumes; use a new demo project rather than resetting test evidence.
