# Actual authorization record

Work ID: anvil-praxis-bodhium-benchmark-2026-11-07. Conversation: fdd0cf03f01748698589fa2401680560. Recorded 2026-11-07 UTC. User identity is the Product Owner in this conversation; no separate named approver or message UUID was supplied. This file records messages, not an agent-granted approval.

## Product input approved

The original attachment begins with the actual relayed authorization dated 7 November 2026:

> I approve the benchmark spec. Hand it over to the existing Anvil OpenHands conversation to create the architecture and implementation plan. Keep Praxis and my local changes untouched, and stop for my approval before coding.

Approved specification v0.1 is saved byte-for-byte as `approved-specification.txt`, SHA-256 `44196cae04b7a399fb70da8d4577345b2cf95ee6a14daa41f3d8c8f2b4921cbc`. Its historical draft labels and section 16's narrower scope do not cancel this approval. Extracting the text between the markers, removing the separator blank line, and retaining exactly one terminal LF reproduces the attachment's stated approved hash. The complete original TXT, including its original separators, remains unchanged at `../../../../recovery-evidence/inputs/Anvil-Benchmark-Architecture-Planning-Handoff.txt` relative to this run folder (repository path: `recovery-evidence/inputs/Anvil-Benchmark-Architecture-Planning-Handoff.txt`).

## Current authorization supersedes old paths and stage pause

Initial current-conversation authorization relayed 2026-11-07:

> Start a new Anvil OpenHands conversation, recover the latest work from available release artifacts, and hand over the approved benchmark spec for architecture and planning. Keep Praxis and my local changes untouched; stop before coding.

The active request explicitly permits BOTH architecture and planning sequentially now, with the new isolated `/workspace/anvil-recovered` replacing old conversation/checkout assumptions. This permits drafting a plan from the unapproved design within this session; it does NOT claim the new design is human-approved or satisfy the future Coding gate.

Latest coordinator/user update supplied the archive and explicitly directed:

> Recover production source overlay onto isolated base checkout /workspace/anvil-recovered; retain base tests/docs labeled historical and record missing r6 test/evidence changes. Do not replace actual recorded tree/hash with invented reconstruction claims.

> No need GCP login/CLI inside runtime now, no credentials transfer. DO NOT switch LLM profile with a tool ... Work directly with the CURRENT runtime configuration.

> Continue recovery, source inspection, architecture and implementation plan based on approved full spec already attached ... Stop BEFORE benchmark coding, tests, model runs, commits/pushes/deploy. Praxis and Mac untouched.

The full archive/input bytes are preserved; this record quotes the operative human messages rather than fabricating a separate signed approval artifact. Historical r6 source approval and successful build/deployment are coordinator assertions, not newly reproduced acceptance evidence.

## Model transport workaround

The user reported Claude thinking-signature transport failures, then rebound the saved ADI-Architecture OpenAI profile and reported billing fixed. One profile-switch tool invocation occurred earlier in this conversation before the latest no-switch instruction. Recovery/design resumed using the current runtime configuration; no subsequent profile switch, key read/copy, product provider request or product fix was performed. No model ID, judge selection or spending authority for Anvil benchmarks follows from this agent-profile workaround.

## Gates still closed

- New architecture approval: **PENDING HUMAN APPROVAL**.
- New implementation plan approval: **PENDING HUMAN APPROVAL**.
- Benchmark coding/test execution: **NOT AUTHORIZED**.
- Product candidate/judge models, rights, paid budgets and live runs: **NOT AUTHORIZED / INPUTS MISSING**.
- Deployment, GCP writes, authentication/IAM changes, commits/pushes: **NOT AUTHORIZED**.
- Runtime gcloud/login helper: superseded by archive delivery; not installed, not prepared, no authentication attempted in this runtime.

Architecture/planning drafts cannot authorize their own execution. A future approval must identify their actual hashes and bounded task scope, and acknowledge the recovery evidence gap.
