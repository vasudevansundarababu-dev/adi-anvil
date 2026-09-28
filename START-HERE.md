# Start the ADI Anvil overnight build in VS Code

The specification, logo and sample data are ready. The application has not been built. All infrastructure/default questions are answered; API keys, exact model IDs, paid budget and real paid approvers remain outstanding. You can start coding now, but without those inputs real model testing will be reported blocked.

## Tonight

1. Open VS Code → **File → Open Folder** → `/Users/vasudevansundarababu/Code-Repo/ADI-Anvil`. Use a separate VS Code window; do not open the older ADI-Core-Frontier folder for this build.
2. Start Docker Desktop and keep the machine powered/awake. The build has an eight-hour work window, not a guarantee against sleep, rate limits or approval prompts.
3. Open the Codex sidebar and sign in. Use a local coding/editing session, not a read-only discussion. Keep your selected coding model; this spec does not require a model change. [Official IDE instructions](https://learn.chatgpt.com/docs/codex/ide)
4. Review [BUILD-DECISIONS.json](BUILD-DECISIONS.json) and [QUESTIONS.md](QUESTIONS.md). Keep live calls disabled until the missing prerequisites exist. Do not put API keys in those files.
5. Use the preflight prompt below first. Stay present to resolve legitimate workspace/dependency-network/Docker permissions. Scoped workspace access is recommended; do not disable all approval/security controls merely to avoid overnight pauses. [Official permissions guidance](https://learn.chatgpt.com/docs/agent-approvals-security)
6. Once preflight is clear, paste the complete contents of [CODEX-OVERNIGHT-PROMPT.md](CODEX-OVERNIGHT-PROMPT.md) into Codex. That prompt authorizes the local implementation across all milestones; it does not authorize GitHub publication or cloud/email actions.
7. In the morning, open `docs/generated/morning-report.md` and [the morning walkthrough](docs/build/04-MORNING-ACCEPTANCE.md). The build agent must supply tested startup commands and the local accounts-file path.

## Preflight prompt to paste first

```text
Read AGENTS.md, README.md, BUILD-DECISIONS.json, QUESTIONS.md and
docs/build/03-EXECUTION-RUNBOOK.md. Perform a read-only overnight-build preflight
in this ADI-Anvil folder: verify tools, Docker/Compose, disk/ports, workspace
and network/Docker access, and identify permissions that may interrupt work.
Do not start implementation, install globally, initialize/push Git, create
accounts, read secret values or call any model yet. Report exactly what I must
resolve before I paste the build prompt. No API keys exist yet, so live tests
must stay blocked while offline development can proceed.
```

## If the build stops

```text
Resume ADI Anvil from BUILD-STATUS.md and the existing Git state. Read AGENTS.md
and docs/build/03-EXECUTION-RUNBOOK.md first. Preserve finished work and unrelated
changes. Re-run the last relevant check, then continue the next incomplete
milestone within my previously authorized scope. Do not reset or regenerate
the repository. Do not infer paid-model or publication authorization. Tell me
if the original eight-hour window has expired before starting another work window.
```

No prompt can guarantee the process continues when the IDE closes or usage limits are reached. The saved milestone log makes resuming straightforward. No background automation or cloud task has been created here.
