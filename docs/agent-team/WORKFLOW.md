# Approval-gated engineering workflow

Read root AGENTS.md and current BUILD-STATUS.md. Respect current product decisions;
historical specifications are not evidence that a feature exists. Cite source paths.
Work only in Anvil and preserve unrelated edits. Do not read secrets or private
runtime data. No production changes, paid inference, push, external messages,
automatic issue creation, deployments, destructive resets or volume deletion.

PRD → Architect → Planner → Coding → QA → DevOps preparation → human release review.
Each role delivers a draft and stops. Do not launch or impersonate the next role.
User approval must identify the artifact revision and next allowed scope; pending
approval, an agent's recommendation and an agent-written approval record are not
authorization. User instructions in the active conversation remain authoritative.
Changed inputs invalidate downstream approvals. Rejected QA returns to Coding
within explicitly authorized scope; resubmit changed artifacts for review.

Use `templates/handoff.md` for every boundary and the role's template for output.
Keep artifacts under `docs/agent-team/runs/<work-id>/`, free of private data.
Use stable requirement IDs and immutable Git commit or content hashes for inputs.
Do not describe an artifact as approved until the actual user approval is recorded.

Before implementation, require approved PRD, design and task scope. QA reviews the
actual code revision and maps requirements to observed results. DevOps prepares
commands, rollback and verification only; a separate exact-target authorization is
required to execute a deployment. This setup does not grant that authorization.

Handoff enforcement is procedural: these files do not create an execution sandbox
or a cryptographic approval service. Keep OpenHands tool confirmation enabled;
do not rely on prompts to contain an agent with unrestricted filesystem/cloud access.
