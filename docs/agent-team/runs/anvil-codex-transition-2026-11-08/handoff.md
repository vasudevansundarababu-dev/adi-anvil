# Anvil: OpenHands to Codex handoff

Date: 8 November 2026 (America/Chicago). Status: cutover identified; three Codex roles assessed; staging NOT deployed.

## Immutable cutover

- Repository: `vasudevansundarababu-dev/adi-anvil`.
- Continue branch `codex/anvil-agent-team-2026-11-06`, existing draft PR16.
- Final OpenHands publication: `fd48c278c267d550485d739e4b0a09f0c6d70d79`.
- Tested recovery source: `4e64f54c368d04afcde6faa8c41cdadd9529e0d9`.
- Product repair source: `e0a7b5fb45dbc73c1e9d6248647a102387ea5cd8`.
- Publication changes evidence/documentation; product/test/lock bytes remain bound to the recovery evidence. Do not equate whole Git trees.
- OpenHands was instructed to publish only its existing final handoff and stop writing. Its final task state reports publication complete, remote verified, clean workspace and no owned tests running. No further OpenHands product work is authorized by this transition.
- Clean Codex checkout: `/Users/vasudevansundarababu/Documents/Codex/anvil-codex-transition`. Original local checkout and uncommitted work were not used or modified. Praxis remains separate.

## What carries forward

Reuse the approved PRD, benchmark specification, architecture, implementation plan and original fifteen input artifacts. Preserve all append-only approvals and failure history. No rewrite or new product design is proposed.

OpenHands recovery reports passing offline checks: 46 gateway, 95 provider-loop, three fixed six-test diagnostic rounds, 96 pricing/capture, 33 evaluator contracts, 729 full units, three pre-dispatch negatives, seven adapter guards, twelve Node checks and focused lint/scanning. Counts overlap. These are source-bound OpenHands results, not independent Codex QA or model performance.

Fresh native Docker/resource and PostgreSQL checks remain blocked in the replacement OpenHands environment. Sanitized historical successes do not close that gate. Read `t05-recovery-checks.json` and `t05-recovery-commands.md` in the prior Coding run for exact evidence.

## Separate Codex roles

| Role | Ownership | Handoff |
|---|---|---|
| Coding | Product implementation, fixes, API/UI integration; one product writer | Exact commit plus requirements and developer verification |
| Testing | Independent requirements-based verification, isolation/concurrency/security and real browser journey | Passed/failed/blocked/not-run matrix on the exact commit; defects return to Coding |
| DevOps | Isolated staging configuration, reproducible artifact, migrations, rollback and deployment smoke | Exact target/source/image digests and observed deployment evidence |

The roles may assess and prepare independently in parallel. Product changes, tests and staging operations must use coordinated source revisions and isolated environments. Do not let agents concurrently change the same source or shared runtime. No agent approves its own output on the user's behalf.

Role assessments: `coding.md`, `testing.md`, `devops.md` in this directory. Initial work is assessment and transition preparation, not a claim that remaining implementation or QA has started.

## Path to a usable staging application

1. Close the fresh native/SQL environment gap with an Anvil-only test target and explicitly scoped prerequisites.
2. Continue the existing plan: T07 durable protocol/admission/execution; T08 official scoring/review; T09 comparison APIs/projections/exports; T10 operational UI backed by those APIs.
3. Coding demonstrates one genuine persisted user journey using clearly labeled fictional/offline materials. No mockup is called an implemented benchmark workflow and no fabricated live results are shown.
4. Testing independently verifies that exact integrated revision, including login, persistence, project/role isolation, private-reference separation, concurrency, cancellation/restart, truthful errors and regressions.
5. DevOps builds once, deploys immutable artifacts to the confirmed isolated staging target, then verifies health, login and the intended browser flow. Preserve the existing invited-user Anvil application.

Current Benchmarks screen is explicitly a UI mockup; T07–T10 are incomplete. Deploying the cutover revision alone will not deliver the requested new benchmark journey.

## Staging target and authority

The repository records an existing invited-user deployment in project `adi-anvil-mvp-2026`, VM `anvil-mvp-v1`, zone `us-west1-a`. It is not a separately configured staging environment. Existing deployment scripts hardcode current resources and mutate their data/services; do not use them as a staging shortcut.

Propose a dedicated staging project, or a separately named and isolated resource set in the Anvil project, with separate identity, data, disks, vault, secrets, service account and backend. Exact project/resources/hostnames/access and infrastructure spending limit remain user decisions. No cloud resources were provisioned by this assessment.

Keep paid candidate/judge/generation/support paths and real email disabled in staging unless independently authorized. New staging authorization never grants production, Praxis, private data, paid inference or credential-sharing authority. Do not use the `gcloud` executable currently found under the Praxis checkout or borrow its configuration.

## Review checkpoint

User requested the switch point, separate agents and staging. This document makes that transition concrete. It does not invent acceptance of the resulting T06 code, waive native/SQL checks, or authorize a guessed staging target. Confirm bounded continuation and exact staging target before those dependent actions. Preserve existing gates unless the user explicitly changes them.
