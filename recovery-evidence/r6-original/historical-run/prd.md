# PRD — APPROVED by Product Owner on 2026-11-06 — task-readiness explanations

- Work ID: `anvil-task-readiness-explanations-2026-11-06`
- Repository / branch / source commit: `vasudevansundarababu-dev/adi-anvil` /
  `codex/anvil-agent-team-2026-11-06` / `8cdc8a84784c7ae52d7bbb88f36193b387aedb60`
- Approval: see `approvals.md` (user approval of 2026-11-06, relayed in OpenHands
  conversation `fa695daa-3b1f-4e64-8229-f2fe070a0f1c`).
- This file is a saved copy of the PRD approved in that conversation, including the
  amended G2, REQ-TRX-005 and REQ-TRX-007. The approved revision existed only as chat
  text, so it had no prior file hash. Evidence corrections found during Architecture
  are marked **[Corrected during Architecture]**. They change evidence only, not
  requirement text.

## Problem, users and repository evidence

Users are RL Engineers and Admins in the modern workspace (`docs/product/MODULE-GUIDE.md:20,24`).
Package readiness, run admission and measured model performance are separate claims
(`MODULE-GUIDE.md:40-41`, `README.md:35-38`). Current explanations are incomplete:

- E1 **[Corrected during Architecture]** Two separate web message maps exist.
  - `apps/web/src/lib/executionReadiness.ts:6-30` maps **15** codes (the draft PRD said
    16). Unknown codes fall back to raw text with underscores replaced (`:32-33`).
  - `apps/web/src/components/WorkspacePreparation.tsx:429-464` maps 28 codes and falls
    back to the raw code (`:928`, `:940`).
  - The server produces **29** codes (the draft PRD said 26). They come from
    `services/backend/src/anvil/workspace_preparation.py:119-190`,
    `workspace_execution.py:274-382` and `workspace_models.py:64-72`.
  - **14** codes have no message in `executionReadiness.ts` (the draft PRD said 12).
    12 have none in the Preparation map, **5** have none in either, and **8** have
    different text in the two maps.
  - These counts come from searching the source at the commit above, not from running
    the application.
- E2: For a v3 task without a package, the task list shows the raw import state with
  underscores replaced (`apps/web/src/components/WorkspaceTasks.tsx:218-231`). It gives
  no reason and no next step.
- E3: Strengths to keep: the detail page shows the package badge separately
  (`WorkspaceTasks.tsx:320-323,370-375`), and the execution-group panel shows
  "Run cannot start yet" and "No model request has been sent"
  (`WorkspaceExecutionGroups.tsx:237-243`). Run re-checks readiness when clicked
  (`BUILD-STATUS.md:921-922`, `docs/product/23-TASK-LIBRARY-VIEW-AND-RUN-SCREENS.md:58-62`).
- E4 **[Resolved during Architecture]** The red `.failed` style exists
  (`WorkspaceTasks.module.css:77-80`) but only `ExecutableImport.tsx:158` uses it. The
  task list and detail badges use two styles, so `BUILD-STATUS.md:720-722` overstates
  the behavior.

## Goals and measurable success criteria

- G1: 100% of server-produced reason codes have an approved plain-language message,
  checked automatically.
- G2 (amended): In the tested readiness screens, every readiness condition has a
  plain-language explanation as its main text. A raw reason code, underscores or not,
  never appears as the main or only explanation. A code may appear only as a separate,
  visually secondary diagnostic label, such as "Diagnostic code: …", when REQ-TRX-005
  allows it.
- G3: Every explanation says what is blocked, why, which role can fix it, and the next
  action.
- G4: No change to which runs are admitted, and no new spending or model-provider calls.

## Scope and explicit exclusions

- In scope: explanation text and how it's shown for (a) task package and import states
  on the task list and detail pages, and (b) planning and execution-group run blockers.
- Excluded:
  - Changing gate logic, adding or removing gates, or loosening admission.
  - Automatic fixes or automatic retries.
  - Live or paid provider calls.
  - Praxis changes.
  - The Benchmarks mockup.
  - Translation into other languages.
  - Billing dashboards.
  - The older source readiness/gap ledger (`readiness.py`); see Q3.

## Current behavior versus proposed behavior

| Area | Current | Proposed |
| --- | --- | --- |
| Unknown or unmapped reason code | Raw text, underscores replaced | Approved message, or the safe generic fallback (REQ-TRX-005) |
| List badge for an import state | Raw state label | Label, a one-sentence reason, and the next step |
| Blocker item | Message only, sometimes with a model prefix | What is blocked, why, who can fix it, and a link to the action |
| Layer separation | Present but implicit | Package readiness, run admission and performance are labelled separately |

## Requirements

| ID | User story | Acceptance criteria | Verification method |
| --- | --- | --- | --- |
| REQ-TRX-001 | As an Engineer, I want every run blocker described in plain language. | Every code produced by `planning_readiness`, `readiness`, `plan_readiness` and `workspace_models` has an approved message. A test fails when a new code has no message. | Automated test comparing produced codes with the message list |
| REQ-TRX-002 | As a user, I want to know who can fix a blocker and how. | Each blocker shows the cause, the role that can fix it (Engineer or Admin), and one next-action link. Engineers are never pointed to Admin-only pages as if they can use them. | Component tests and browser tests for each role |
| REQ-TRX-003 | As a user, I want to understand a task's import state. | Each of the 7 import states (`queued`, `generating`, `validating`, `needs_clarification`, `generation_failed`, `validation_failed`, `ready`) shows a label, a reason and the next step on both the list and detail pages. `generation_failed`, `validation_failed` and `needs_clarification` point to the validation report or editor. | Component tests and browser tests using the golden synthetic fixtures |
| REQ-TRX-004 | As a reviewer, I don't want "Ready" to be mistaken for "admitted" or "performant". | The package-ready text says run admission is checked separately. No readiness text mentions model quality or scores. | Text review and a snapshot test |
| REQ-TRX-005 (amended) | As a user who sees a condition with no approved message, I want a safe, understandable fallback. | 1. An unrecognized code shows the generic plain-language explanation "This run is blocked by a condition Anvil can't describe yet. Ask a project Admin to review it." 2. The code may appear only as a secondary diagnostic label after that explanation. It is shown only if it matches the server's reason-code format: lowercase letters, digits and underscores, with a set maximum length. Anything else is left out completely. 3. The diagnostic label never contains user-supplied text, IDs, credential details, hidden-reference or grader content, cost authority details or other projects' data. 4. An unknown condition counts as blocking, and Run is not enabled. | Unit tests with a known code, an unknown code in the allowed format, and an unknown code that breaks the format or contains injected text. Snapshot test confirming the explanation comes first and the code is secondary. |
| REQ-TRX-006 | As a security owner, I want no leakage. | Explanations never include hidden reference answers, private grader content, credential values or IDs beyond the existing name, other projects' data, or more cost authority detail than the role can already see. | Security review and integration tests for cross-project and role negatives |
| REQ-TRX-007 (amended) | As an Admin, I want the server to stay the only authority on whether a run may start. | 1. The server's readiness responses are the only source of the ready-or-blocked decision and the reason codes. 2. The client never calculates readiness, adds or drops reasons that affect the decision, or enables Run on its own. 3. Explanation text is presentation only. Whether it's mapped in the web app or returned by the server was left open as Q1. Either way, the text is keyed to server reason codes. Missing, stale or failed text can't change the decision. 4. Existing safeguards stay: Run re-checks readiness when clicked, and drafts still say no model request was sent. 5. The current Admin presentation rule (`executionReadiness.ts:38`) stays. It hides `admin_run_authorization_required` from Admins because clicking Run is their authorization. Launch still goes through the server's authorization check. | Code review. Integration and browser tests confirming that a server "not ready" response blocks launch even when explanation text is missing or wrong. Existing Admin and Engineer Run-authorization tests. |
| REQ-TRX-008 | As a budget owner, I want explanations to cost nothing. | Showing or refreshing explanations makes no model or provider calls and creates no spend reservations. "No model request has been sent" stays for drafts. | Integration test confirming no provider calls (simulated responses) |
| REQ-TRX-009 | As an assistive-technology user, I want blockers announced. | The panel keeps `role=alert` or `status` and focus behavior. Each item is plain text, and links have descriptive names. | Accessibility checks in browser tests |

## Data, privacy, rights, access and spending constraints

- Explanations must keep project isolation and role scope as they are.
- Reasons stay tied to the exact frozen versions: `subject_hash`, package SHA, and the
  model/credential version bindings in `workspace_execution.py:289-310`.
- Rights checks and hidden-reference isolation must stay intact.
- No default spending authority is granted. Generation and evaluation budgets stay
  separate.
- Synthetic fixtures verify software behavior only. They are not model performance.
- No secrets go into code, logs or reports.

## Praxis interface and independent operation

None. There are no changes to the `contracts/praxis` contract or to Praxis.

## Dependencies, assumptions and open questions

- Assumption: the list of reason codes is fixed at commit `8cdc8a8`. Architecture
  re-counted it as 29 by searching the source.
- Q1 — **Resolved by design approval:** option A, a web-app message catalog plus a
  checked-in list of server reason codes (`design.md`).
- Q2 — **Open, kept as a gate:** the Product Owner approves the catalog text in the
  Coding review. The spending and authorization entries need explicit sign-off.
- Q3 — **Resolved by design approval:** the older source readiness/gap ledger is out
  of scope.
- Q4 — **Resolved from the code:** see E4.
- Q5 — **Resolved from the code:** `model_version_superseded` is produced at
  `workspace_models.py:71` and reaches the Preparation panel, execution-group blockers,
  and a 409 error message when a model is selected (`workspace_preparation.py:90-92`).
  How that error message is shown is investigated in the plan.
- Q6 — **Resolved by design approval:** no extra usability measure beyond G1–G3 and the
  Product Owner's wording review.

## Risks and rollout considerations

- Wording could suggest authority or a performance claim that doesn't exist. Requiring
  Product Owner wording review addresses this.
- The message list could fall behind new codes. The REQ-TRX-001 test addresses this.
- The change is UI-only, so it can be undone by reverting the change. No database
  migration is expected.

## Proposed handoff

The PRD is approved. Architecture is approved in `design.md`, and planning is in
`plan.md`. Coding has not started and needs separate human approval.
