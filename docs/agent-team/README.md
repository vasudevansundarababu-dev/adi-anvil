# ADI Anvil engineering team

Six repository-scoped OpenHands skills: `anvil-prd`, `anvil-architect`,
`anvil-planner`, `anvil-coding`, `anvil-qa`, `anvil-devops`.
These are reusable role instructions, not autonomous background processes.

## Start in Agent Canvas

Open the Anvil repository and the intended branch in a new conversation. If using
a remote clone, transfer these local commits through your normal reviewed source
publication process first; local files are not automatically present in a GitHub clone.
Send: `Use anvil-prd. Read .agents/skills/anvil-prd/SKILL.md and
docs/agent-team/WORKFLOW.md. Draft a PRD for <requested feature>. Do not implement.`
Use the corresponding skill name for each later role, supplying the approved
artifact and explicit human approval. Verify the working directory before writing.

## Compatibility

Checked against the installed OpenHands Agent Server/SDK 1.60.1. Its actual
`load_project_skills` implementation discovers `.agents/skills/*/SKILL.md` and
loads root AGENTS.md. Skills are discovered at conversation start; restart with a
new conversation after adding them. Do not install Anvil skills globally.

Official reference: https://docs.openhands.dev/sdk/guides/skill

## Independent Praxis workspace

Use a separate Praxis checkout, conversation, branch and workspace. Never mount
the shared Code-Repo parent as either agent's workspace. Keep runtime directories,
Compose project names, ports, volumes and credentials separate. The two products
exchange versioned contracts in `contracts/praxis`, not sibling source imports.
Do not change Praxis as part of this setup. Role instructions alone are not an OS
security boundary; use isolated workspaces and restricted runtime permissions.

## Authentication blocker

An ACP `authentication_failed` response prevents a live model run. Repair the
profile used by the conversation in Customize/LLM settings, using the matching
provider's API key and endpoint. Never use the Canvas session key as a model key.
Do not copy secrets into this repository or reports. A configured profile or
completed onboarding checklist does not prove successful authentication.
