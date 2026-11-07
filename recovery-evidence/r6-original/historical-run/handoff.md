# Handoff — DRAFT / PENDING HUMAN APPROVAL BEFORE CODING

- Work ID: `anvil-task-readiness-explanations-2026-11-06`
- Repository / branch / source commit: `vasudevansundarababu-dev/adi-anvil` /
  `codex/anvil-agent-team-2026-11-06` / `8cdc8a84784c7ae52d7bbb88f36193b387aedb60`
  (the saved documents are new untracked files; nothing has been committed)
- From role / proposed next role: anvil-planner → anvil-coding (only after human approval)
- Input artifact paths and SHA-256 hashes, all under
  `docs/agent-team/runs/anvil-task-readiness-explanations-2026-11-06/`:
  - `prd.md` `eb6e8aac45d305063bf0966b7f7551cac71df6db2dd1ab19c0c0b94e00fbb9af` (approved 2026-11-06)
  - `design.md` `b490d0d8f4d89bc25571519d98e7bb8d1f43054a9fcbb2575e5f6468733a42d4` (approved 2026-11-06)
  - `approvals.md` `20a44cc3c5cf558f057f0221b20dfa203667ccde9a94d381c5ee37047afe5ee2`
  - Planner instructions read at commit `8cdc8a8`: `.agents/skills/anvil-planner/SKILL.md`,
    `docs/agent-team/WORKFLOW.md`, `docs/agent-team/templates/planner.md`,
    `docs/agent-team/templates/handoff.md`, `package.json`, `scripts/local.py`
- Output artifact paths and SHA-256 hashes:
  - `plan.md` (same directory). The hash is reported in the conversation, because a
    file can't contain its own hash.
  - `handoff.md` (this file). Its hash is reported in the conversation.
- Changes and requirement IDs covered:
  - Plan tasks T0–T10 cover REQ-TRX-001…009 and G2.
  - Documentation only. No source, test, contract or dependency changes.
- Evidence (passed / failed / blocked / not run):
  - Passed:
    - `origin`, branch, HEAD and the clean starting status were verified.
    - The saved documents were read back and hashed.
    - Source reading for F1 (the model-selection 409 path), F2 (11 import states vs 7
      in scope) and F3 (older codes).
  - Not run: all application tests, builds and contract regeneration.
  - Blocked: none.
- Open questions and material risks:
  - D-COPY (Q2 wording): Product Owner sign-off still needed.
  - D-STATE: default (a), keep the 7-state scope with a generic fallback.
  - D-409: default (i), fix in the web app only, no API change.
  - D-E2E-ID: default `researcher`.
  - Risks: blocker count drifting during display changes; prefix matching on the 409
    message; the parity scan only finds literal strings; raw codes remain in the
    out-of-scope Marketing/Harbor screens.
- Proposed next allowed scope:
  - Coding T0–T10 only, within the file scopes in `plan.md`.
  - Local tests with the listed commands, against isolated local databases and with no
    provider keys.
  - Dependency installation (`pnpm setup:local`) and local commits only if the user's
    approval explicitly allows them.
  - Stop before QA.
- Prohibited actions:
  - Changing server gates, authorization, rights, isolation, hidden-reference or budget
    code.
  - API or OpenAPI shape changes, migrations, Praxis changes.
  - Live or paid provider calls, `pnpm test:live`.
  - Push, deployment, creating issues.
  - Destructive resets or volume deletion.
  - Starting QA, DevOps or any other role automatically.
  - Treating this draft or an agent recommendation as approval.
- Decision: PENDING HUMAN APPROVAL
- Human approver / actual approval message reference / timestamp:

Leave approval fields empty until the user supplies approval. Stop here.
