---
name: anvil-qa
description: Verify an ADI Anvil code revision against approved acceptance criteria.
---

# Anvil qa

Read `docs/agent-team/WORKFLOW.md` before starting. Follow root AGENTS.md.
Verify that the working directory is the Anvil checkout, not Praxis or a parent directory.

Require approved requirements and the exact code revision. Inspect tests before execution; use synthetic fixtures and isolated local resources. Do not run integration tests against deployed data or live providers. Cover acceptance criteria and relevant auth/project isolation, version binding, hidden references, rights, budgets and regression negatives. Never count a skipped check or fixture output as live model verification. Report findings with reproduction and source references; do not silently fix product code or approve release.

Use `docs/agent-team/templates/qa.md` for the deliverable and
`docs/agent-team/templates/handoff.md` for the proposed transition.
Drafts remain pending human approval. Do not start the next role automatically.

