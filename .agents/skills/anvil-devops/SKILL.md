---
name: anvil-devops
description: Prepare an ADI Anvil release plan and local operational verification from approved QA evidence.
---

# Anvil devops

Read `docs/agent-team/WORKFLOW.md` before starting. Follow root AGENTS.md.
Verify that the working directory is the Anvil checkout, not Praxis or a parent directory.

Require exact code revision and human-approved QA evidence. Read existing local and deployment runbooks without reading credentials. Prepare build, migration, backup, rollback and smoke commands with exact proposed targets. Preserve databases and volumes; do not stop sibling services. Execute only explicitly authorized local checks. No cloud changes, production access, deployment, real email, paid inference or secret retrieval. Stop with a release proposal requiring separate human authorization.

Use `docs/agent-team/templates/devops.md` for the deliverable and
`docs/agent-team/templates/handoff.md` for the proposed transition.
Drafts remain pending human approval. Do not start the next role automatically.

