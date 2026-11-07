# Execution plan — DRAFT / PENDING HUMAN APPROVAL BEFORE CODING

- Work ID: `anvil-task-readiness-explanations-2026-11-06`
- Repository / branch / source commit: `vasudevansundarababu-dev/adi-anvil` /
  `codex/anvil-agent-team-2026-11-06` / `8cdc8a84784c7ae52d7bbb88f36193b387aedb60`
- Role: anvil-planner. Nothing in this plan authorizes coding, dependency installation,
  test execution, commits, pushes, deployment or issue creation.

## Approved PRD and design revisions

| Artifact | SHA-256 | Approval |
| --- | --- | --- |
| `prd.md` | `eb6e8aac45d305063bf0966b7f7551cac71df6db2dd1ab19c0c0b94e00fbb9af` | 2026-11-06, see `approvals.md` §1 |
| `design.md` (option A) | `b490d0d8f4d89bc25571519d98e7bb8d1f43054a9fcbb2575e5f6468733a42d4` | 2026-11-06, see `approvals.md` §2 |
| `approvals.md` | `20a44cc3c5cf558f057f0221b20dfa203667ccde9a94d381c5ee37047afe5ee2` | Approval record |

If any of these files changes, this plan is invalid until it is reviewed again.

## Guardrails for every task

- Don't change server readiness logic, gates, launch, authorization, budget, rights,
  isolation or hidden-reference code. Specifically:
  - `workspace_preparation.readiness`
  - `workspace_execution.readiness` / `plan_readiness` / `launch`
  - `workspace_models.selection_issues`
  - `auth`
- No API response or error-shape change. `contracts/openapi/anvil.json` must come out
  of contract regeneration byte-identical.
- No migration, no Neo4j or LangGraph change, no Praxis or `contracts/praxis` change,
  and no new dependencies.
- Explanations are fixed catalog text. Free-form server text is never inserted into a
  catalog explanation.
- Only an unknown code that passes the format check `^[a-z][a-z0-9_]{0,63}$` may appear,
  and only as a secondary "Diagnostic code" label.
- Keep these headline strings exactly as they are:
  - "Run cannot start yet"
  - "Not ready to run · Generation and validation required"
  - "Package built"
  - "No model request has been sent for this draft."
- No live or paid provider calls. Tests use the existing controlled provider doubles
  only.

## Pre-coding findings, recorded here for the Coding role to confirm

**F1 — the model-selection 409 path (called out by Architecture under Q5).**
- Where it comes from: `workspace_preparation.model()` (`workspace_preparation.py:84-93`)
  calls `selection_issues` (`workspace_models.py:64-72`). If that finds problems, it
  raises `HTTPException(409, "Select an enabled current model version: " + ", ".join(codes))`.
  The codes can be `model_version_mapping_missing`, `model_profile_disabled` or
  `model_version_superseded`.
- Who can reach it:
  - `POST /workspace/presets` (Admin only, `:259-281`)
  - `POST /workspace/preparations` (planning roles, `:343-359`)

  Execution-group creation doesn't call `model()`; it re-uses the frozen preparation
  snapshot (`workspace_execution.py:19`).
- How it reaches the user:
  1. `api.py:76-88` puts the detail string in `error.message`.
  2. `workspaceApi` (`apps/web/src/lib/workspace.ts:109-121`) turns string details into
     `Error.message` unchanged.
  3. That message is shown raw in `role="alert"` paragraphs:
     - the presets form, `WorkspacePreparation.tsx:289-292`
     - the run/preparation form, `:604-607`

  Users can therefore see raw codes, so G2 applies to this path.
- Existing test: `services/backend/tests/integration/test_workspace_models.py:149-150`
  checks the readiness code and expects the 409.
- Separate path: a structured launch 409 (`workspace_execution.py:836-840`, detail
  `{message, missing, models, …}`) already goes through `runBlockers(detail, false)` in
  `workspace.ts:111-112`. Its "Execution blocked; no model dispatched" headline must be
  kept.

**F2 — more import states exist than the approved scope covers.**
- `migrations/036_executable_imports.sql:23` allows 11 states.
- `import_worker.py:460-475` also produces `environment_unavailable`, `budget_paused`,
  `outcome_unknown` and `cancelled`.
- The approved REQ-TRX-003 covers 7 states. Per the coordination note, the scope is
  **not** expanded; see decision D-STATE.

**F3 — older codes.** The Preparation list holds these 11 entries:
- `workspace_dispatch_not_qualified`
- `current_pricing_not_bound`
- `reviewed_pricing_admission_not_bound`
- `pricing_metadata_missing`, `pricing_metadata_expired`, `pricing_metadata_invalid`
- `exact_user_authority_not_bound`
- `processing_rights_not_bound`
- `required_run_decisions_not_bound`
- `shared_spending_admission_not_implemented`
- `provider_task_adapter_not_qualified`

None of them is produced by the 3 modules in scope. The ones that appear in
`workspace_execution.py` are only in the `obsolete` filter set (`:278-287`), or in the
`provider_task_adapter_not_qualified` filter (`:316`). Keep them in the catalog as older
entries, per the design. Don't add them to the produced-code list.

## Blocked decisions (each resolved by the user before the task it affects)

| ID | Decision | Blocks | Default if the user approves the plan without choosing |
| --- | --- | --- | --- |
| D-COPY (Q2) | Product Owner approves the catalog text. Explicit sign-off is needed for `admin_run_authorization_required`, `aggregate_api_cap_missing`, `group_cap_below_conservative_cost_or_above_authority`, `reserved_spend_window_inactive_or_insufficient` and `live_dispatch_disabled_in_runtime`. | Accepting T3 and everything after it; the QA handoff | None. The text stays DRAFT, and Coding may continue with drafts marked for review. |
| D-STATE | How to show the 4 import states outside the approved scope (F2). (a) Keep the 7-state scope; the other 4 get one generic plain-language fallback ("This import stopped in a state Anvil can't describe yet. Open the import report or ask a project Admin.") with no raw state as main text. (b) Expand REQ-TRX-003 to 11 states, which needs a PRD amendment and approval. | T7 | (a). No scope expansion. |
| D-409 | How to fix the raw codes in the model-selection 409 (F1). (i) In the web app only: when `error.message` exactly matches the prefix `Select an enabled current model version: ` followed by comma-separated codes that pass the format check, show the catalog text instead. Anything else is shown unchanged, as today. (ii) On the server: return structured detail. That changes the API error shape, which goes against design option A, so it would need a design amendment. | T6 | (i). No API change. |
| D-E2E-ID | Which seeded local identity to use as the RL Engineer (non-Admin) in browser tests. Evidence: `services/backend/src/anvil/cli.py:72` seeds every non-`admin-*` user in the main project as `rl-engineer`. `tests/e2e/modern-workspace.spec.ts:9` already signs in as `researcher` to check Engineer restrictions. | T9 | Use `researcher`, which is the existing pattern. Don't create users, change role mappings, or copy local credentials into the repository; tests read the ignored `.local/demo-accounts.md` at runtime, as they do today. |

## Task graph

| Task | Requirement IDs | Dependencies | Files/scope | Acceptance check | Risk |
| --- | --- | --- | --- | --- | --- |
| T0 Preflight | — | Plan approval | No source edits | `origin`, branch and HEAD (or an approved descendant) match; `git status --short` shows only this run directory's files; artifact hashes match the table above; tool versions match `.node-version` 24.21.0, `.python-version` 3.12, pnpm 10.34.5 | Starting from the wrong checkout or a changed input |
| T1 Confirm findings F1–F3 | REQ-TRX-001, -005, -006, -007 | T0 | Read-only; record notes in the run directory only if the user authorizes it | F1 paths, F2 states and F3 older codes confirmed against current source. Any difference stops the work for re-planning. | Findings out of date |
| T2 Reason-code list and backend parity test | REQ-TRX-001 | T1 | New `contracts/readiness/reason-codes.v1.json`; new `services/backend/tests/unit/test_readiness_reason_codes.py` | The test parses the code (AST) of `workspace_preparation.py`, `workspace_execution.py` and `workspace_models.py`. It collects the string literals added to `missing`/`issues`/`reasons` or returned as lists, excluding the `obsolete` set and the `provider_task_adapter_not_qualified` filter. It checks they equal the sorted JSON list (29 codes at `8cdc8a8`). Adding a fake code to a temporary copy makes the test fail. | Codes built dynamically are missed; documented as a limitation |
| T3 Catalog module and Node policy test | REQ-TRX-001, -002, -004, -005, -006 | T2; D-COPY drafts | New `apps/web/src/lib/readinessCatalog.ts`; new `tests/readiness_catalog.mjs`; `package.json` `test:ui-policy` adds the new test file | Every code in `reason-codes.v1.json` and every F3 older code has an entry with layer, fixer, main text and an Engineer version when the fixer is an Admin. The fallback works as specified: known code; unknown code in the allowed format shows a secondary label; an unknown code with a bad format or injected text such as `x<script>`, `a b`, a 65-character code, or uppercase is left out. The fallback is always blocking. Ready text says admission is checked separately and matches no `/score|quality|perform|benchmark/i`. The output never contains supplied free-form text. The module uses only TypeScript syntax Node can strip (no `enum` or `namespace`), as the existing `providerFailure.ts` test does. | Text that suggests authority (D-COPY) |
| T4 Run-blocker integration | REQ-TRX-002, -005, -007, -009 | T3 | `apps/web/src/lib/executionReadiness.ts`; `apps/web/src/components/WorkspaceExecutionGroups.tsx` | `runBlockers` returns the same set of blocking reasons as today: the same codes and the same `admin_run_authorization_required` rule for Admins (`:38`). Unknown codes still count. Each item shows the main text, then an optional secondary diagnostic. The Engineer never sees an Admin-only link (the condition at `:244` is kept). `role`/focus/`tabIndex` behavior and the headline strings are unchanged. `describeRunReason` either stays as a compatible wrapper or every caller is updated, including `workspace.ts:112`. | Display changes accidentally changing the blocker count, so Run is enabled |
| T5 Preparation panel integration | REQ-TRX-001, -002, -005 | T3 | `apps/web/src/components/WorkspacePreparation.tsx` (remove the local list at `:429-464`; render at `:927-941` through the catalog helper) | No local message list remains. Planning and model reasons render as main text with an optional secondary diagnostic. The save-then-run shortcut (`:672`) still depends on `runBlockers(...).length`. | Losing text for older codes; mitigated by F3 |
| T6 Model-selection 409 text | REQ-TRX-005, -006, -007 | T3, T5, D-409 | Under default (i): `apps/web/src/lib/workspace.ts` (or a small helper in the catalog module) and `tests/readiness_catalog.mjs` | An exact prefix with valid codes shows catalog text for each code, plus a secondary diagnostic for unknown codes in the allowed format. A prefix followed by injected or badly formatted content shows only the generic fallback, never the raw tail. Any other error message is shown exactly as it is today. The backend 409 is unchanged; `test_workspace_models.py:150` still passes. | Brittle matching on the error-text prefix; covered by tests, with D-409 (ii) as the alternative |
| T7 Task list and detail import states | REQ-TRX-003, -004 | T3, D-STATE | `apps/web/src/components/WorkspaceTasks.tsx` (`:218-231`, `:320-323`, `:370-375`); `WorkspaceTasks.module.css` (re-use `.failed`, no new tokens) | Each of the 7 approved states shows a label, a reason and the next step on the list and detail pages. `generation_failed` and `validation_failed` use `.failed`. Those two and `needs_clarification` point to the import validation report or editor. The other states follow D-STATE. "Package built" and the existing detail headline strings stay. No raw underscore state is shown as main text. | Golden browser-test text coupling (`golden-executable-import.spec.ts:52`) |
| T8 Backend integration guards | REQ-TRX-006, -007, -008 | T2 | New tests in `services/backend/tests/integration/test_workspace_execution.py` and/or `test_workspace_preparation.py`; no source edits | (a) `GET /preparations/{pid}` and `GET /execution-groups/{gid}` call no provider: the provider entry point is replaced with a stub that fails the test if called, the same pattern as the existing `httpx.MockTransport(lambda r: pytest.fail(...))` at `test_workspace_execution.py:253`. They also create no spend window or reservation rows. (b) Launch of a not-ready group returns 409 "Execution blocked; no model dispatched", whatever the client sends. (c) A foreign project or role sees no readiness, through the existing isolation patterns. | A stub instead of a real provider; justified because a real call would spend money |
| T9 Browser tests | REQ-TRX-002, -003, -005, -009, G2 | T4–T7, D-E2E-ID | `tests/e2e/workspace-preparation.spec.ts`, `workspace-task-pages.spec.ts`, `golden-executable-import.spec.ts` (additions only) | On the same blocked group, Admin and Engineer each see the correct fixer text, and the Engineer sees no "Open Models & keys". The blocker list has no main text matching `/\b[a-z]+(_[a-z]+)+\b/`. The panel keeps `role` and focus. Task list and detail show import explanations for the golden ungenerated tasks. Existing assertions are unchanged. | Flaky timing; follow the existing wait-for-heading patterns |
| T10 Verification, evidence and status | All | T2–T9 | `BUILD-STATUS.md` (a dated entry, as AGENTS.md requires); QA evidence under the run directory | Commands below run with outcomes recorded as passed / failed / blocked / not run. The contract regeneration leaves `contracts/openapi/anvil.json` unchanged. `git diff --stat` touches only planned files. D-COPY sign-off recorded only from an actual user message. | Claiming checks passed that weren't run |

## Execution order and bounded coding assignments

1. T0 → T1. Stop if F1–F3 differ from current source.
2. T2.
3. T3 (needs draft text for D-COPY).
4. In order, one writer: T4, then T5, then T6 (needs D-409), then T7 (needs D-STATE).
5. T8 can run after T2, independently of T3–T7.
6. T9 after T4–T7 (needs D-E2E-ID).
7. T10 last. Then stop and hand off to QA. Don't start QA automatically.

Rules for each step:

- One writer at a time (AGENTS.md).
- Each task leaves its tests passing before the next one starts.
- Create local checkpoints only if the coding approval allows commits.
- A task that hits an unresolved decision stops. It does not choose a wider option.

Estimates are planning guesses, not delivery commitments. Suggested batches:

- Batch 1: T0–T3.
- Batch 2: T4–T7.
- Batch 3: T8–T10.

## Local test prerequisites and commands

All commands come from the root `package.json` and `scripts/local.py`. None were run
for this plan.

Prerequisites:

- Docker, Node 24.21.0, pnpm 10.34.5, Python 3.12 and uv.
- Local services with Keycloak and the seeded identities.
- Integration tests use isolated test databases (`services/backend/tests/integration/conftest.py:31-54`).
- Never run against deployed or user data.
- No provider keys are needed.
- `pnpm setup:local` installs locked dependencies (`pnpm install --frozen-lockfile`,
  `uv sync --frozen`). It needs explicit authorization in the coding approval.

```sh
pnpm preflight
pnpm setup:local                 # dependency install: requires explicit authorization
pnpm services:up && pnpm db:migrate
pnpm test:ui-policy              # node --test tests/provider_failure.mjs (+ tests/readiness_catalog.mjs after T3)
pnpm test:unit                   # pytest services/backend/tests/unit -q   (T2)
pnpm test:integration            # pytest services/backend/tests/integration -q   (T8, regressions)
pnpm dev                         # app on http://127.0.0.1:3202 for e2e
pnpm test:e2e -- tests/e2e/workspace-preparation.spec.ts tests/e2e/workspace-task-pages.spec.ts tests/e2e/golden-executable-import.spec.ts
pnpm check                       # ruff, prettier, web tsc, production build, OpenAPI contract regeneration
git diff --exit-code contracts/openapi/anvil.json
git diff --check && git status --short
pnpm stop                        # stops app processes without deleting data
```

Not allowed for this work: `pnpm test:live`, `pnpm test:smoke` against live services,
deploy scripts, and any destructive reset or volume deletion.

## Risks

- Display refactoring could change which reasons count as blocking. T4's check compares
  the blocker set before and after; server launch re-checks remain the backstop.
- Wording could suggest spending authority or performance. Covered by D-COPY and the
  wording test in T3.
- Prefix matching on the 409 message is brittle (T6). Tests cover it; D-409 (ii) is the
  structural alternative.
- The parity scan only catches literal strings (T2). The limitation is documented, and
  future dynamic codes still get the safe fallback.
- Browser tests are coupled to the headline text. Headlines are kept and new text is
  added below them.
- Raw underscore codes remain in other screens (Marketing/Harbor `missing_gates`). They
  are out of scope for this increment and not claimed as fixed.

## Handoff awaiting human approval

See `handoff.md`. **DRAFT / PENDING HUMAN APPROVAL BEFORE CODING.**
