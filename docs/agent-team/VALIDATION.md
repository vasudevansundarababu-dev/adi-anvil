# Validation — 2026-11-06

- Installed Agent Server OpenAPI reports 1.60.1; Agent Canvas UI reports 1.37.0.
- Inspected the installed SDK `load_project_skills` implementation before choosing
  `.agents/skills/<role>/SKILL.md`.
- Actual installed SDK loader loaded all six Anvil roles successfully, including
  PRD name, description and body. No model key or provider call was needed.
- Root AGENTS.md and unrelated dirty files were preserved.
- Live PRD execution: BLOCKED / NOT VERIFIED. The existing Canvas conversation
  reports ACP `authentication_failed` / Invalid API key. Do not treat loader
  validation or a separate offline review as a successful OpenHands agent run.
- Canvas has ADI-Coding (Anthropic), ADI-Architecture (OpenAI, default), and Default
  (OpenHands) profiles. Which profile the failed conversation used still needs
  confirmation. The conversation returned 404 on the inspected local agent server;
  verify the selected backend before assuming a local repository is its workspace.
- No keys printed, changed or committed. No push, production changes or deployment.

After authentication repair, start a new Anvil conversation and ask it to use
`anvil-prd` to draft a task-readiness explanation PRD. Pass criteria: correct Anvil
workspace and branch, skill loaded, current source citations, requirement IDs and
testable acceptance criteria, DRAFT status, no source edits, and stop awaiting human
approval before Architecture. Record the actual response and revision here.
