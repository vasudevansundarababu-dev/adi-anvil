# Current Codex implementation authority — 8 November 2026

This append-only session record supersedes historical pending-authority wording for this session only. Approved architecture and originals remain unchanged.

The user instructed: “Continue the remaining Anvil implementation with the Coding agent, then have Testing and DevOps prepare it for staging within $500/month. Keep Praxis and my local changes untouched, and stop for my approval before deployment. STop Anvil in OpenHands”. The user subsequently selected an independent code/security review as the use of remaining OpenHands credits. The existing coding session must not resume as a second writer.

## Ownership and boundaries

- Clean checkout: `/Users/vasudevansundarababu/Documents/Codex/anvil-codex-transition`, existing branch `codex/anvil-agent-team-2026-11-06`, draft PR16.
- OpenHands session `b59115d76f8b427baccc1382eeb0426e` was freshly inspected: **Done**, final publication `fd48c278c267d550485d739e4b0a09f0c6d70d79`, explicitly stopped as writer, no owned tests. No new execution message was sent.
- Coding agent owns backend benchmark implementation and development tests. Root owns frontend and narrowly scoped local loopback-port configuration. These are disjoint source assignments.
- Testing agent owns independent verification and fresh isolated local test services. Development passes on a changing tree are not immutable final QA evidence.
- DevOps owns separate staging configuration, resource-plan validation, pricing and operational preparation. No cloud provisioning or deployment is authorized in this execution.
- Normal checkpoint pushes on the existing branch remain authorized. No force push, merge, production changes, paid candidate/judge calls or outbound email.
- Praxis, the original Anvil checkout, its uncommitted edits and existing application processes are outside this work. New loopback ports and fresh test services are used rather than taking occupied ports.

## Staging preparation

Target is separate `anvil-staging` resources in project `adi-anvil-mvp-2026`, `us-west1`, with an additional USD500 monthly infrastructure allowance. This is not a technical billing hard cap or model-run authority. The current invited-user application is not staging.

The user completed sign-in with the existing ADI Labs account using the independently installed Cloud CLI and fresh Anvil-only configuration under `Documents/Codex/anvil-tools`. Only project resource metadata was queried; no secret payloads were accessed and no cloud resources changed. Sanitized observed metadata remains in ignored owner-only `.local/staging-inventory-observed.json`; versioned summaries omit credentials.

## Known verification limits

The Mac has pinned images available, but the existing native operator requires its dedicated Linux runtime, socket and executable contract. Neither shared socket access nor a path/symlink workaround is permitted. Native qualification remains blocked until that actual environment is available and the changed source is requalified. SQL, contract, unit and browser work proceed independently. Historical OpenHands passes are not fresh native evidence.

The remaining T07–T10 implementation is in progress. Source presence, types passing and a UI screen do not establish a complete benchmark workflow. Final handoff must map requirements, exact source, commands, passed/failed/blocked/skipped checks, provenance and remaining release gates. Deployment remains stopped for user approval.
