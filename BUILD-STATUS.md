# Build status

Status: **RESUMED — VERIFICATION AND REMAINING ACCEPTANCE WORK IN PROGRESS**

New authorization: user instructed “ok continue the work” after the proposed additional eight-hour window. Resumed 2026-09-28 11:24 UTC; new stop deadline 2026-09-28 19:24 UTC. Single writer; no live inference or external publication authority. First action: repair lint and verify the final prior-session changes, preserving all data and source.

Stop audit: clock checked at 2026-09-28 10:52:30 UTC, after the 10:43 UTC deadline. Implementation stopped on detection. Read [morning report](docs/generated/morning-report.md) and its JSON companion. Final working tree is not fully verified; last lint check failed with 56 findings. No Git commit exists; preserve all untracked source and supplied files.

Latest verified results: 77 unit tests, 3 database integration tests, expanded 1-test real-OIDC E2E including worker restart and downloads; webpack production build; Alembic adoption; private backup/restore. Later automatic kit/provider/maintenance changes are partially untested. No live calls. Anvil web/API/worker stopped for handoff; infrastructure/volumes retained.

- Authorized launch: 2026-09-28 02:43 UTC; stop deadline: 2026-09-28 10:43 UTC.
- Single writer; no remote or live inference authorized.
- Tools: Node 24.21.0, pnpm 10.34.5, Python 3.14.6, uv 0.12.19, Docker 29.8.0, Compose 5.5.1, arm64 macOS.
- Docker verified with authorized sandbox escalation. Existing Git identity available.
- Web ports 3200 and 3201 occupied: use 3202, preserving unrelated processes.
- Live verification blocked: no keys, exact models, budget or independent paid approvals.
- Next: resolve independent dependencies, infrastructure and root launcher.

Resume evidence (11:34 UTC): `pnpm setup:local` passed idempotently; `pnpm dev` running; `pnpm check` passed lint, TypeScript, production webpack build and contract generation. `pnpm test:e2e` passed the complete six-episode existing fixture journey after automatic-kit changes. New request-byte limit and API create idempotency fixes verified by `pnpm test:unit` (83 passed) and `pnpm test:integration` (21 passed). Actual generated A4 PDF rendered with sips and visually inspected: legible single-page white background. Latest security changes still require browser regression. No live inference. Next: dispute/cancellation and graph outage/rebuild verification, remaining intake/release requirements.

Resume evidence (11:42 UTC): additive Alembic 003 import batch/receipt schema applied. Partner manifest dry-run/atomic commit/deduplication/quarantine tests pass. Integration suite now 23 passed, including real Neo4j rebuild/replay and simulated outage fallback. Expanded E2E passed automatic provisional/approved kits, deliberate dispute with third-identity adjudication, cancellation, and invocation counts. Intake and provider configuration UI added; TypeScript passed. Findings now validate finalized episode, bound criterion/capability and verbatim evidence before submission. Latest UI/graph/finding changes await full regression. Source/credential scan reported zero known local-secret matches. Preparing first local checkpoint; all functionality remains partial against the full P0 matrix.

Resume evidence (12:14 UTC): checkpoint `7377af7` created locally, no remote. `pnpm test:unit`: 83 passed; `pnpm test:integration`: 31 passed (signed OIDC claim negatives, successor history, withdrawals included). Expanded E2E passed rights revocation and successor download invalidation. `services/backend/.venv/bin/python tests/graph_outage.py` now passed actual Neo4j stop/fallback/start/rebuild with unchanged episode checksum; first run caught startup timing in the test harness, fixed bounded retry and reran successfully. Persisted evidence ZIPs and rights-review UI added. New isolated-project/mobile browser run in progress. Next: finish remaining findings/release/fixture delivery/operational requirements and acceptance evidence. Deadline remains 19:24 UTC.

Resume evidence (12:28 UTC): findings creation/review and actual queued network-free mail simulation passed in a fresh-project E2E (11 distinct OIDC accounts, 19.8s). Fixture mail API rejects non-.invalid addresses, requires distinct sender Admins and exact release-owner approval, rechecks suppression and evidence, and preserves terminal unknown acceptance without resending. 32 integration tests passed; 85 unit tests passed including zero-denominator/unknown/cancelled separation. `pnpm check` passed. Fresh Alembic 001–004 plus repeated upgrade passed on retained `anvil_migrationcheck_c8e3936a3f74`. `pnpm audit --prod --json`: zero advisories across 102 production dependencies. Worker operational-failure terminal handling was added after latest E2E and needs targeted verification. Python advisory audit running. No real email/model requests. Source changes after first checkpoint not yet committed.

Resume evidence (12:47 UTC): backup `.local/backups/20260928T123640Z-dd7587c3` restored to retained `anvil_restore_6f9904fd6b15`; 386 checkpoints, 3 pending reviews and 167 artifact checksums verified. `tests/restore_resume.py` finalized one copied pending episode using the copied artifact store, with unchanged invocation count and original episode. Python audit: 84 dependencies listed, zero advisories; local unpublished `adi-anvil` skipped. Immutable Compose image digests started successfully with retained volumes. CI/Dependabot/runbooks prepared locally, not executed remotely. Input qualification now rejects duplicate/cross-source actors; suspicious/oversized file fixtures remain quarantined/blocked. Latest integration: 40 passed; E2E passed 19.7s after correcting a repeat-import column typo. UI/test formatting and TypeScript passed. Next: ambiguous-reference resolution and external result import; no complete-MVP claim.

Evidence below reflects the prior session unless updated above.

| Milestone | State | Evidence |
| --- | --- | --- |
| M0 Preflight, locks, isolated scaffold | Infrastructure and locks ready; full command checks pending | Named Compose services running; independent pnpm/uv locks |
| M1 Identity, API/DB, shell | Core path verified; security matrix incomplete | Real OIDC for 9 identities, CSRF/role/project negatives; DB RLS tests |
| M2 Intake, qualification, suite/protocol | Core path verified; baseline gaps remain | Browser/API objective quorum, rights, rubric/task reviews, published cases, frozen suite/protocol |
| M3 Durable fixture evaluation + review | Six episodes verified; restart/dispute tests next | 1 E2E passed: 6 invocations, duplicate launch replay, blinded double grading, 3 pass/3 fail, mean 85 |
| M4 Diagnostics and graph | Partial | Projection/canonical response exercised; outage/rebuild tests missing |
| M5 Report, release, Sales Kit | Partial | Authenticated PDF/HTML/ZIP/draft downloads passed; one-page count passed; latest visual/automatic job changes unverified |
| M6 Provider adapters and authorized smoke | Mock contracts passed; live blocked/unqualified | 73 SDK transport contract tests; no inference; paid gate integration incomplete |
| M7 Full verification and morning handoff | Partial; window ended | Backup/restore passed; lint failed; full matrix, fresh startup, CI and audits incomplete |

Build agent maintains below: start/deadline, current commit, versions, last passing command, failures, pending questions, next exact action, local URLs/processes and safe resume instructions. Keep secrets and raw candidate/source content out of this file.

Latest evidence (03:16 UTC): `python3 scripts/local.py migrate && python3 scripts/local.py seed` passed; `python3 scripts/local.py integration` passed 2 tests; `pnpm exec playwright test` passed 1 real-login journey in 10.3s. Fixture expected numeric outcomes verified. Initial E2E failed on a too-short test evidence quote; corrected to full JSON field span, preserving product validation.

Runtime URLs: web http://127.0.0.1:3202; API http://127.0.0.1:8200; Keycloak http://127.0.0.1:8180. Credentials: `.local/demo-accounts.md` (owner-only). Logs and process registry in `.local/`. No model calls made.

Environment issues: optional Playwright Chromium download failed (network timeout/DNS); tests use installed Chrome with isolated profiles. Turbopack production build failed on subprocess port permission; supported webpack build being tested. Resume: review restart/dispute tests, graph projection/fallback, report/downloads, provider mocks, remaining P0 hardening.
