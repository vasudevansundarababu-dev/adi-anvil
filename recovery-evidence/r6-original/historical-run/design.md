# Technical design — APPROVED by user on 2026-11-06 — task-readiness explanations

- Work ID: `anvil-task-readiness-explanations-2026-11-06`
- Repository / branch / source commit: `vasudevansundarababu-dev/adi-anvil` /
  `codex/anvil-agent-team-2026-11-06` / `8cdc8a84784c7ae52d7bbb88f36193b387aedb60`
- Approval: see `approvals.md`. The user approved this design, including recommended
  option A and the recommendations below, on 2026-11-06.
- Gates still open after approval:
  - Q2: the Product Owner must approve the catalog text before Coding is accepted.
  - Coding needs a separate human approval.

## Approved PRD revision and requirements

- Input: `prd.md` in this directory, approved 2026-11-06 together with the amended G2,
  REQ-TRX-005 and REQ-TRX-007.
- Scope: REQ-TRX-001…009 only.

## Current architecture and source evidence

- **Server decides readiness.**
  - Planning reasons come from `workspace_preparation.readiness`, including
    model-version reasons from `workspace_models.selection_issues` (`:64-72`).
  - Execution-group reasons come from `workspace_execution.readiness` (`:274-370`) and
    `plan_readiness` (`:372-382`).
  - Launch re-checks readiness while holding a lock and returns 409 if anything changed
    (`workspace_execution.py:836-857`).
  - The architecture rule is that hiding a control in the browser is never an
    authorization check (`docs/architecture/README.md:5-8`).
- **Responses aren't typed.** The OpenAPI response schemas for preparations and
  execution groups are empty (`{}`) in `contracts/openapi/anvil.json`.
- **Two separate message lists in the web app.**
  - `executionReadiness.ts:6-33` (15 entries) is used by
    `WorkspaceExecutionGroups.tsx:114,139,237-243`, `WorkspacePreparation.tsx:672` and
    `lib/workspace.ts:109-121`.
  - The local list in `WorkspacePreparation.tsx:429-464` (28 entries) is used at lines
    927-941.
- **Counts, from searching the source:**
  - The server produces 29 codes.
  - 14 have no message in `executionReadiness.ts` and 12 have none in the Preparation
    list.
  - 5 have no message in either list.
  - 8 have different text in the two lists.
- **Import states:** the approved scope covers `queued`, `generating`, `validating`,
  `needs_clarification`, `generation_failed`, `validation_failed` and `ready`. They're
  shown raw on the task list (`WorkspaceTasks.tsx:218-231`). The detail page has only
  two badge texts (`:320-323`).
- **Roles:** the server returns capabilities (`workspace_access.py:22-41`). The web app
  treats `models.manage` as Admin (`ModernWorkspace.tsx:79`).
- **Existing pattern to copy:** `providerFailure.ts` with its test
  `tests/provider_failure.mjs` (run by `test:ui-policy`). It turns server data into
  fixed text and never repeats untrusted text.

## Proposed components, APIs and versioned data contracts

Q1 decision (approved): **option A — one message catalog in the web app, plus a
checked-in list of server reason codes.**

1. **Catalog module.** Create `apps/web/src/lib/readinessCatalog.ts` (or extend
   `executionReadiness.ts`). It replaces both current lists. Each entry holds:
   - the reason code
   - which layer it belongs to: package readiness, run setup, or run admission
   - who can fix it: `engineer`, `admin` or `operator`
   - the main text, plus an Engineer version where the fixer is an Admin
   - an optional action link, marked Admin-only where relevant
2. **Import-state entries.** The same module covers the import states in scope, each
   with a label, a reason, the next step and a badge style.
3. **Rendering helper.** A shared helper builds what each item displays: the main text,
   then optionally `Diagnostic code: x` as a secondary line. Both
   `WorkspaceExecutionGroups` and `WorkspacePreparation` use it. `runBlockers` keeps its
   current behavior, including the Admin rule at `executionReadiness.ts:38`.
4. **Reason-code list.** Add `contracts/readiness/reason-codes.v1.json`, a sorted list
   of the codes the server produces. It's a test-time contract only; the server doesn't
   read it at runtime.

Explicit no-change decisions:

- No PostgreSQL migration and no change to Neo4j or LangGraph.
- No change to readiness logic, gates or the launch path.
- No change to API response shapes and no OpenAPI change.
- No change to Praxis contracts.

## PostgreSQL ownership, projections and durable orchestration

Nothing changes. Readiness is still calculated live from the frozen snapshot and
current database rows (`workspace_preparation.py:119-190`). Nothing new is stored.

## Auth, project isolation, hidden-reference boundaries and budgets

- **Role-aware text (REQ-TRX-002):**
  - When the fixer is an Admin, an Engineer sees "Ask a project Admin to…" and no
    Admin-only link. This keeps the existing condition at
    `WorkspaceExecutionGroups.tsx:244`.
  - Issues an operator must fix (`live_dispatch_disabled_in_runtime`,
    `model_cost_support_*`, `package_runtime_not_supported`) say "Contact your Anvil
    administrator". They don't reveal server configuration.
  - Showing a link never grants access; the server still enforces every permission.
- **Safe content (REQ-TRX-006):** explanations use only fixed catalog text, the matched
  code, and model IDs the screen already shows. Server error text and other free-form
  server values are never inserted into explanations. No credential values, hidden
  references, grader content, cost authority details or other projects' data are added.
- **Unknown codes (REQ-TRX-005):**
  - The main text is the fixed generic explanation.
  - The code is shown as a secondary `<small>` diagnostic only if it matches
    `^[a-z][a-z0-9_]{0,63}$`. The longest current code is 52 characters. Anything else
    is left out completely.
  - An unknown code still counts as a blocker in `runBlockers`, so the save-then-run
    shortcut at `WorkspacePreparation.tsx:672` won't fire.
- **Server stays in charge (REQ-TRX-007):** the server's `ready` flag and its reason
  lists remain the only decision. The client never adds or removes blocking reasons,
  apart from the existing Admin rule. Missing or broken text can't enable Run, because
  launch is re-checked on the server (`workspace_execution.py:836-857`).
- **No spending (REQ-TRX-008):** explanations are calculated purely in the browser.
  Refreshing uses the existing GET endpoints, which only read the database and
  configuration. No provider calls and no spend reservations. "No model request has
  been sent" stays (`WorkspaceExecutionGroups.tsx:243`).
- **Accessibility (REQ-TRX-009):** keep the existing `role=alert` / `status` and focus
  behavior (`WorkspaceExecutionGroups.tsx:231-236`,
  `WorkspacePreparation.tsx:527-544,900-902`). Action links get descriptive names.

## Alternatives and tradeoffs

| Option | Pros | Cons |
| --- | --- | --- |
| **A. Web catalog plus reason-code list (approved)** | Smallest change; no API or database change; copies an existing pattern; undo by revert | Copy lives in the web app; it stays in step with the server only through the parity test |
| B. Server returns explanation text | One source of truth; the server already knows the role | Changes the readiness responses on two endpoints; copy changes need a backend deploy; a larger review surface |
| C. Server returns structured details (layer, fixer), web app maps the text | Fixer role is decided on the server | Changes the API without removing the need for a web catalog |

## Migration, compatibility, rollback and independent Praxis operation

- **Compatibility:** keep the existing headline strings that browser tests check:
  - "Run cannot start yet" (`workspace-preparation.spec.ts:207`,
    `workspace-task-pages.spec.ts:188`)
  - "Not ready to run · Generation and validation required"
    (`golden-executable-import.spec.ts:52`)
  - "Package built" (`workspace-task-pages.spec.ts:114`)

  Explanations go on extra lines below these, so the current tests keep working.
- **Older codes:** keep the older entries from the second list (for example
  `pricing_metadata_*`, `workspace_dispatch_not_qualified`). The Planner should search
  the code to confirm before removing any.
- **Rollback:** revert the web, test and contract commits. There's no migration or data
  to undo.
- **Praxis:** no change.

## Verification strategy and unresolved decisions

| Requirement | Check |
| --- | --- |
| REQ-TRX-001 | Backend unit test: scan the 3 producing modules' source for reason-code strings and compare with `reason-codes.v1.json`. Node test: catalog codes cover that list. Both fail when a new code is added without a message. |
| REQ-TRX-002 | Browser test as Engineer and as Admin on the same blocked group: correct fixer text, no Admin link for the Engineer. |
| REQ-TRX-003 | Node test covering every import state in scope. Browser test on the golden fixtures for the list and detail pages. |
| REQ-TRX-004 | Snapshot test: ready text mentions the separate admission check and contains no score, quality, performance or benchmark wording. |
| REQ-TRX-005 | Node test cases: known code; unknown code in the allowed format; unknown code that breaks the format or contains injected text (left out); the code is always secondary. |
| REQ-TRX-006 | Node test: server free-form text never appears in the output. Existing cross-project and role integration tests. |
| REQ-TRX-007 | Integration test: launch returns 409 when the server says not ready, whatever the web app shows. Code review: no readiness calculated in the browser. |
| REQ-TRX-008 | Integration test: readiness GET makes zero provider calls, using the existing controlled provider test double. That double is justified here because real calls would spend money. |
| REQ-TRX-009 | Role and focus checks added to the browser tests. |

Browser tests should also check that no raw underscore code appears as the main text in
the screens tested (G2).

Decisions:

- **Q2 — wording approval (open gate):** the Product Owner approves the catalog text in
  the Coding review. The spending and authorization entries need explicit sign-off:
  `admin_run_authorization_required`, `aggregate_api_cap_missing`,
  `group_cap_below_conservative_cost_or_above_authority`,
  `reserved_spend_window_inactive_or_insufficient`, `live_dispatch_disabled_in_runtime`.
  Legal review only if the Product Owner asks for it.
- **Q3 — older source readiness/gap ledger:** out of scope. `readiness.py` and
  `CaseReadiness.tsx` belong to the older diagnostic path (`MODULE-GUIDE.md:27-34`), not
  the modern Run path.
- **Q4 — red badge:** apply `.failed` to `generation_failed` and `validation_failed`
  under REQ-TRX-003. Correct the `BUILD-STATUS.md:720-722` wording only in an authorized
  later change.
- **Q5 — `model_version_superseded`:** produced at `workspace_models.py:71`. It reaches
  three places:
  - the Preparation readiness panel (`WorkspacePreparation.tsx:937-941`)
  - execution-group blockers (`workspace_execution.py:315`)
  - a 409 error message when a model is selected (`workspace_preparation.py:90-92`),
    which embeds the raw code

  It becomes one catalog entry. The Planner investigates how the 409 message is shown.
  If it is shown to users, show the catalog text rather than the raw error text.
- **Q6 — usability measure:** no extra measure for this increment.

## Handoff awaiting human approval

Planning is drafted in `plan.md` and `handoff.md`. Coding is not authorized until the
user approves the plan.
