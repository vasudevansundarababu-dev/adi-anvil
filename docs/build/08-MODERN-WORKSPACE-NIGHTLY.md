# Modern workspace nightly implementation

User launched autonomous implementation on 30 October 2026, after approving the combined
Admin and task/run design. This is local build authority, not deployment or paid inference
authority. Nightly schedule: 22:00–06:00 America/Chicago, with hourly checkpoint resumes.
Initial window: 2026-10-31 03:08 UTC through 11:00 UTC (eight hours maximum, ending at
06:00 local); stop earlier on completion or a genuine blocker.

## Preservation and delivery

- Build branch: `codex/anvil-modern-workspace`.
- Preserved code baseline: `codex/anvil-classic-v021-comparison`, initially the same HEAD
  as `codex/praxis-harbor-v0-2`. Do not advance or rewrite the comparison branch.
- Preserve the classic `/p/{project}/...` routes and offer a separate `/workspace/...`
  modern journey with explicit links between both views of the same project data.
- Preserve uncommitted user edits in AGENTS.md and the Google Cloud runbook. Commit only
  enumerated implementation/design/checkpoint files; no credentials or private artifacts.
- Existing PostgreSQL records and evidence stay canonical. No resets or copied databases.
- The local launcher can register the dedicated Harbor worker when explicitly started
  with `ANVIL_HARBOR_WORKER_ENABLED=synthetic-checks-only` and the authorized local
  `ANVIL_HARBOR_DOCKER_HOST`. It requires the existing pinned executable; no install or
  paid activation is implied. Normal startup stays unchanged; `pnpm stop` owns the optional
  worker when registered this way. Stop all registered workers before isolated integration.

## Dependency-ordered milestones

1. M0: baseline branch, nightly automation, local preflight and durable plan.
2. M1: authenticated responsive modern shell, project selection and classic comparison;
   real task-level Harbor history, normalized result dashboard, failure categories, safe
   observable evidence, immutable actor/package snapshots and comparable metrics.
3. M2: persisted multiple model/framework profiles, versioned configuration, qualification
   states and project-scoped Admin CRUD. Registered adapter metadata must not imply a live
   implementation or enable a different runtime. Add diagnostic run coverage to M1.
4. M3: reviewed local credential-store boundary, write-only save/rotate/revoke, profile
   binding and secret leakage/access tests. No cloud IAM or secret provisioning. If the
   approved store cannot be provided locally, keep real-key entry disabled and report it.
5. M4: two product profiles with explicit scoped capabilities and historical identity
   preservation, Admin engineering actions, versioned task/rubric/evaluation editing,
   compatible run preparation and typed framework compositions. Preserve all real paid
   authorization, reviewed data rights, separation and ledger controls.
6. M5: complete browser journeys and failure/empty/loading/cancellation states, comparison
   eligibility, pagination, accessible responsive light/dark UI, regression/secret checks,
   local walkthrough URLs and candid morning report. Unqualified live adapters stay blocked.

Read product specs20/21 and applicable API contracts at each milestone. No mockup results
may appear in the real application as measured data. Do not install arbitrary SDKs, access
sibling credentials, push GitHub, deploy, send messages/email or make model calls under this
build authority. User requests no routine input: choose reversible local defaults, record
them and continue safe independent work when one integration is blocked.

Every window resumes BUILD-STATUS.md on the build branch and records its 06:00 local deadline.
Do not reset the nightly deadline on each hourly wake.
Do not run concurrently with another writer on this checkout. Keep the machine/app running
for scheduled execution; an automation is not a guarantee against sleep or service limits.
After the requested scope is complete, nightly work is relevant regression verification,
not unsolicited feature expansion. Report only meaningful completion, failures or blockers.
