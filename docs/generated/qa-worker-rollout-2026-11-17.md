# QA worker rollout — 17 November 2026

User explicitly requested deployment to existing QA, continued Marketing/Open Weight
work, no live calls or Authoring integration, and completion/blocker email.

Deployed source `fc23fb8f1df8f2874129a328c39b4c28b68e967a`; exact Gym
source hash `c9caef76e0e0ad5891dac7a911928d94172db44e38a0899bdc26bcdaee741918`.
GCP build `20d9b55d-a81f-48c4-9201-0dbd310a95e2` SUCCESS. Before rollout:
1053 units + 10 subtests and 28 fresh/repeated PostgreSQL execution checks passed.
Actual-host installed source/OPA/CLI checks passed for both new serving images.

Existing QA `anvil-qa-v1/us-west1-b` only:

- API, ordinary and business workers:
  `backend@sha256:8bb93ec29f6ed6541507c19dcd769928200e0980680b162dbfc8605e0317159a`.
- Dedicated software scheduler and grader:
  `kyc-runtime@sha256:4f27972ad13fa56d73dc4f0512189f4993ae9b8401cb4863391511e257cf7077`.
- Real installed service entry replaces sleep placeholders; existing dedicated role
  credentials are unchanged. Removed PYTHONPATH and corrected wheel resource root.
  Explicit existing QA project only; no mounts, ports, Docker socket or privileges.
  Readonly/nonroot, caps dropped, no new privileges, bounded polling, no auto-restart.
- Canonical Compose and original role env backups retained root-only at
  `/var/lib/anvil-qa-v1/backups/gym-wiring-fc23fb8-20261117`.
- No database migrations or fixtures/imports submitted on QA in this rollout.
  Existing web, identity, data and production unchanged.

User separately approved boot disk expansion30→50GB. Existing disk/partition/ext4
grown online;19GB free after pull. Automatic review rejected removal of three
stopped test images/containers despite proposed archives. No deletion occurred.

Post-rollout PASS: exact image identities, running five services/zero restarts,
actual scheduler/grader polling, internal API/database health, public workspace200,
public health200, anonymous project models401, unchanged existing role credential
fields, live/Harbor flags off. Initial public health503 retained as startup failure;
subsequent read-only recheck passed. No operation replay or inference retry.

QA: https://anvil-qa.adi-labs.ai/workspace

Limits: empty queues prove polling/wiring, not authenticated new import-to-result
acceptance. Native Marketing still gated; no qualified capture/grade claim. No model
calls, Authoring integration or native admission. Open Weight successor remains
local work, not included in this serving build. Completion/blocker email pending.
