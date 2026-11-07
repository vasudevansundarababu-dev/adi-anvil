# ADI Anvil build instructions

- This is an independent repository. Work only here; do not change Praxis, Enterprise or ADI-Core-Frontier. Preserve unrelated edits.
- Read README.md, BUILD-DECISIONS.json, docs/build/01-OVERNIGHT-BUILD-SPEC.md, docs/build/02-REPOSITORY-STRUCTURE.md and docs/build/03-EXECUTION-RUNBOOK.md before implementing. Read the relevant product/API/Sales Kit specifications before each milestone.
- This handoff is documentation until the user launches CODEX-OVERNIGHT-PROMPT.md. A pending answer does not grant permission. Local coding can use explicit safe defaults; missing paid-call authority blocks live dispatch, not unrelated local work.
- Product: ADI Anvil — Frontier Evaluation & Diagnostics Platform. User-approved Next.js/React/TypeScript/Tailwind, Python FastAPI, LangGraph, PostgreSQL, Neo4j and local Keycloak. Record changed choices instead of silently replacing them.
- PostgreSQL owns CRUD, scores, approvals, audit and durable checkpoints. Neo4j is a rebuildable evidence projection; LangGraph orchestrates runs. No learned TTM/TNG editor, optimizer, Tinker/H100 jobs or Enterprise runtime.
- Build and verify the complete local diagnostic slice, not only an HTML demo or phase 0–1. Use the dependency-ordered milestones; never claim unavailable functionality is implemented.
- Auth, role/project isolation, rights, immutable version binding, hidden-reference isolation and spending gates cannot be weakened to meet a time target. Local identity seeds are distinct identities, not a production role switcher.
- Synthetic fixtures and real executions are separately labeled. Predetermined fixture answers never count as model performance. Do not read expected answers from candidate invocation or train on them.
- Live calls require user-approved exact provider/model/budget, locally supplied secrets, reviewed data rights and the application's existing distinct-Admin activation/run controls. No automatic SDK inference retries after ambiguous dispatch. No auto-approval of live actions by switching seeded accounts.
- No GitHub creation/push, cloud deployment, real email, Notion update, sibling credentials, global installs, destructive resets or volume deletion. Local Git checkpoints are allowed after launch; do not fabricate a Git identity if absent.
- Use apply_patch for source edits. Lock dependencies independently; no sibling packages or copied node_modules. Never commit secrets, raw logs, private data or local credentials.
- After each milestone run relevant tests, repair regressions, update BUILD-STATUS.md and record evidence. Resume from that file after interruption; do not restart the repository.
- Do not spawn subagents or new user tasks unless explicitly authorized. One writer is the default.
- Stop on completion, a genuine authority/environment blocker with no safe independent work, or the approved work-window end. Leave a candid morning report with passed/failed/blocked/not-run tests, exact commands and remaining work. Never mark a blocked live smoke test as passed.

## Benchmark source conventions

- Resume active benchmark Coding from `BENCHMARK-PROGRESS.md`; approved originals and append-only approvals live in the dated agent-team runs. Progress authorization is session-specific, not a standing permission grant.
- SME bundle v1 is separate from legacy task/export validators. Fictional FX fixtures test software only; they are not Bodhium data or model performance.
- New benchmark-private classes must use the disjoint explicitly configured vault, never generic artifact storage/downloads. Dedicated SQL tests are under `services/backend/tests/benchmark/`; they require a real isolated PostgreSQL target and must not use shared/deployed services.
