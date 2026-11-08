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

- Benchmark raw intake is feature-disabled by default; only its exact project POST route streams without the legacy body buffer. Do not raise legacy limits. Complete originals/manifests live in benchmark_raw; source authenticity is never execution authority. Staging/hashing/quota checks precede SQL row locks.
- Stock Harbor0.25.0 DockerEnvironment probes Alpine with `--rm`, attempts destructive startup cleanup and has helpers that bypass custom runtimes. Never use it directly for SME qualification or loosen socket permissions. The human-approved `anvil_harbor.sme:SMEDocker` adapter is static no-network/preloaded-only/no-build/no-delete; its actual focused evidence is in `t04b-checks.json`. Preserve the original failed attempt record. Do not treat local qualification receipts as durable product admission or QA approval.
- In prebuilt Harbor tasks, `CONTEXT_DIR` is unset: use task-relative binds and validate resolved sources stay inside the owned trial before startup. Docker cp did not capture output tmpfs here; snapshot bounded regular files, stop the entire actor, then seal exact bytes for the separate evaluator. Never mount evaluator logs in the actor, even owner-only host directories.
- A resumed workspace may restore private directory modes as group-readable. Do not weaken vault/config checks or modify unrelated runtime state. Use fresh owner-only test roots and explicit isolated Unix-socket DSNs; no credential-driven bootstrap. Avoid top-level shell `exit`, which can terminate the terminal and its local daemon/test database.

- T04 restart history provenance is in the Coding run `t04-recovery.json`; recovered044/045 source is not proof of SQL/native qualification. Current environment blockers and exact resume are at the top of BENCHMARK-PROGRESS.md.
- Native gateway Unix socket paths must use fresh short owner-only directories; deep trial/vault paths can exceed Linux AF_UNIX limits. Capture-contract tests use manufactured documents, not native pass evidence.
