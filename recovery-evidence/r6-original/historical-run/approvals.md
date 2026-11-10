# Approval record — anvil-task-readiness-explanations-2026-11-06

This file records only approvals the user actually gave. Each was given in Codex and
relayed by the user into OpenHands conversation
`fa695daa-3b1f-4e64-8229-f2fe070a0f1c` (created 2026-11-06T15:23:35Z). The user gave
dates, but no exact approval timestamps or message IDs, so none are recorded here.

Repository / branch / source commit: `vasudevansundarababu-dev/adi-anvil` /
`codex/anvil-agent-team-2026-11-06` / `8cdc8a84784c7ae52d7bbb88f36193b387aedb60`.

## 1. PRD approval — 2026-11-06

> "I approve the PRD. Run the Architect agent next using the same Anvil branch, and
> stop for my approval before planning or coding."

- The relaying message says this approves the PRD, including the amended G2,
  REQ-TRX-005 and REQ-TRX-007.
- Authorized scope: Architecture design only, for REQ-TRX-001..009.
- Saved artifact: `prd.md`. When it was approved, the PRD existed only as chat text,
  with no file or hash. `prd.md` adds evidence corrections from Architecture, clearly
  marked; requirement text is unchanged.

## 2. Architecture approval — 2026-11-06

> "I approve the architecture design. Save the PRD and architecture documents in the
> Anvil repo, then run the Planner agent on the same branch. Stop for my approval
> before coding."

- The relaying message says this applies to the architecture draft, its recommended
  option A and its recommendations, and the previously approved PRD.
- Authorized scope:
  - Save `prd.md`, `design.md` and `approvals.md`.
  - Produce a Planner draft (`plan.md`, `handoff.md`).
- Not authorized:
  - Source implementation.
  - Running application tests.
  - Installing dependencies.
  - Product provider calls.
  - Commits or pushes.
  - Deployments or issues.
  - Starting the Coding agent.
- Saved artifact: `design.md`. When it was approved, the design existed only as chat
  text, with no file or hash.

## 3. Coordination note — 2026-11-06 (scope instruction, not an approval)

> "keep this increment bounded. Conclude source research with the evidence already
> gathered, preserve remaining uncertainties as explicit plan gates, and prioritize
> saving the approved PRD/design and the draft plan/handoff now. Do not expand the
> approved 7-state scope silently if additional historical states are found. No coding."

## 4. Plan approval and Coding authorization — 2026-11-06

> "I approve the plan. Run the Coding agent on the same Anvil branch using the proposed
> defaults. Keep my local changes untouched and stop for my review before QA or
> deployment."

- The user gave this approval in Codex, and the Codex coordinator relayed it into this
  OpenHands conversation on 2026-11-06. No exact approval timestamp or message ID was
  given, so none is recorded.
- It approves the saved plan revision `plan.md`, SHA-256
  `8af2f4b48bbe1a8fac805b613b4b706ef2fb899371b8e9901e076af84543da89`. That file is
  unchanged.
- Authorized scope: Coding on `codex/anvil-agent-team-2026-11-06`, using the plan's
  proposed defaults (D-STATE (a), D-E2E-ID and the others). The user's local changes
  stay untouched.
- Not authorized: QA, deployment, commits or pushes beyond what the plan states, and
  product provider calls or spend.
- This entry was recorded during the Coding handoff, on the coordinator's instruction to
  record this approval. It records an approval the user gave; it does not grant one.

## 5. Coding approval and QA authorization — 2026-11-06

> "I approve the coding changes. Run the QA agent on the same Anvil branch and
> investigate the failing integration tests. Keep my local changes untouched and stop
> for my approval before deployment."

- The user gave this approval, and the Codex coordinator relayed it into this OpenHands
  conversation on 2026-11-06. No exact timestamp or message ID was given, so none is
  recorded.
- It applies to the uncommitted Coding increment on `codex/anvil-agent-team-2026-11-06`
  (base `8cdc8a84784c7ae52d7bbb88f36193b387aedb60`), as described in
  `coding-handoff.md`. That file's SHA-256 at approval was
  `db52231545c89b031a862532f6c43cb7cf2317ed384edb0317d3d75723b10afc`.
- It is a broad approval of the coding changes. It does not separately approve any
  single item, including the D-COPY wording, or the REQ-TRX-002 per-blocker link
  decision. No separate item-specific approval is recorded or implied.
- Authorized scope: the QA role on the same branch, including investigation of the
  failing integration tests. The user's local changes stay untouched.
- Not authorized: deployment or the DevOps stage, commits or pushes, and product
  provider calls or spend.

## Pending

- D-COPY / Q2 catalog wording: no separate Product Owner sign-off has been recorded. The
  broad coding approval in §5 covers the coding changes as a whole.
- QA result review: **PENDING HUMAN REVIEW** after the QA deliverables are saved.
- Correction Coding and QA rerun (§6): deliverables **PENDING HUMAN REVIEW** when saved.
- Deployment / DevOps: **NOT AUTHORIZED**.

## 6. Correction Coding and QA rerun authorization — 2026-11-06

> "Fix the integration test setup and the per-blocker links on the same Anvil branch,
> then rerun QA. Keep my local changes untouched and stop for my approval before
> deployment."

- The Codex coordinator relayed this user authorization into this OpenHands
  conversation on 2026-11-06. It states that the user authorizes both stages: anvil-coding
  first, then anvil-qa. No exact timestamp or message ID was given, so none is recorded.
- Input revision: base `8cdc8a84784c7ae52d7bbb88f36193b387aedb60` plus the existing
  uncommitted increment (code manifest
  `28030dc2fa54b4c65a26986757a36b0285ee1102851ae4df6cd1c99ae7d27769`), and the prior QA
  deliverables `qa-report.md` (`1f10deb2726711d9ec158627454de02bb022222e0493739406cec4027411eab6`),
  `integration-failure-analysis.md` (`41628e0ac2727a4abaea482446d965546161359e87cad6db966476f87beebb6e`)
  and `qa-handoff.md` (`c2df2ebe12569df2e788a5cb7c95b12cf84ce068943752b9d548735d1bd29aa3`).
- Authorized scope: fix the integration test setup, and add per-blocker next-action
  links (REQ-TRX-002) on the same branch; then rerun QA.
- Not authorized: deployment or the DevOps stage, commits or pushes, and product provider
  calls or spend. The user's local changes stay untouched.

## 7. Coordinator clarification of the §6 authorization — 2026-11-06 (not a new approval)

- This section is **not** a new user quote and **not** a new approval. The governing user
  approval is §6, quoted there exactly:
  > "Fix the integration test setup and the per-blocker links on the same Anvil branch,
  > then rerun QA. Keep my local changes untouched and stop for my approval before
  > deployment."
- The Codex coordinator clarified in this OpenHands conversation on 2026-11-06 that the
  §6 approval covers the following work, already completed:
  - the integration test-setup fixes, including the test-isolation fix for
    `test_import_publish_versions_run_and_resume` (`owned_journey`, test code only);
  - the QA rerun.
  No retroactive approval is required for them.
- The coordinator also said the earlier PRD-only request is superseded.
- Dev worker restoration: the agent paused the dev `anvil.worker` itself, and it crashed.
  Restarting only that registered worker (pid 386427, live providers off, no provider
  keys, checkpoints preserved) returned the user's dev stack to its prior running state.
  This follows §6's instruction to keep the user's local environment untouched.
- Still not authorized: deployment or DevOps, commits or pushes, product provider calls,
  spend or real email. Stop for the user's approval before deployment.
- No exact timestamp or message ID was given for the clarification, so none is recorded.
- Record history (kept for audit):
  1. The first draft of §7, written by this agent, contained a quotation and an artifact
     hash that this agent made up. Both were removed before any later artifact cited
     them.
  2. The second draft described §7 as an unconfirmed interpretation of a truncated
     relay, needing user confirmation.
  3. This version replaces draft 2, following the coordinator's clarification that §6
     already governs.

## 8. Finalization fix, security review and QA rerun authorization — 2026-11-06

> "Fix the Anvil finalization concurrency bug and complete the security review in
> OpenHands. Rerun QA on the same branch, keep my local changes untouched, and stop for my
> approval before deployment."

- The Codex coordinator relayed this user authorization into this OpenHands conversation
  on 2026-11-06. No exact timestamp or message ID was given, so none is recorded.
- Input revision: base `8cdc8a84784c7ae52d7bbb88f36193b387aedb60` plus the uncommitted
  tree bound by `correction-evidence/code-manifest-r2.sha256`
  (`378b350819aa58fcd5509e98f0f6fcfe10aa57ac4cfdfce8d41ca13a6a707747`).
- Authorized scope, done in order with no approval needed between steps:
  1. a scoped product fix for the run finalization race (`correction-qa-report.md` Q1);
  2. the REQ-TRX-006 security review of the cumulative readiness and link changes plus
     the finalization diff, with safe fixes for findings in that scope;
  3. a QA rerun.
- Not authorized: deployment or DevOps, commits or pushes, production, product provider
  calls or spend, secrets, Mac or Praxis access, permission weakening, and container or
  volume deletion. The user's local changes stay untouched.

## 9. QA approval and deployment authorization — 2026-11-06

> "I approve the QA results. Run the DevOps agent in OpenHands to deploy the same Anvil
> branch to the existing GCP environment, verify it, and give me the URL. Keep Praxis and my
> local changes untouched."

- The Codex coordinator relayed this user authorization into this OpenHands conversation
  on 2026-11-06. No exact timestamp or message ID was given, so none is recorded.
- Approved artifact revision: base `8cdc8a84784c7ae52d7bbb88f36193b387aedb60` plus the
  uncommitted tree bound by `finalization-evidence/code-manifest-r6.sha256`
  (`5c15faf05331d58b26342ce7a40d8b0df5f4be62d2619a2840fbf0cdab3f7c7b`), as reported in
  `finalization-qa-handoff.md`.
- Authorized scope: deploy that snapshot to the existing Anvil GCP environment, verify it
  and report the URL.
- Not authorized: Praxis operations, changes to the user's local (Mac) checkout, pushes
  or other branches, `main`, new access grants or weakening security, destructive database
  resets, and product provider calls.
