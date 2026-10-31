# Praxis tasks in Harbor

Open **Build → Praxis → Harbor** in an authorized Anvil project. Import the exact JSON
export from Praxis, inspect the actor view and source receipt, then build the immutable
Harbor package. A source review in Praxis is provenance; it grants no Anvil approval.

Supported contracts are `praxis.anvil.task.v1` (`structured-decision-v1`) and
`praxis.anvil.task.v2` (`staged-decision-v1`, 2–12 ordered decisions). The optional
`praxis.anvil.export.v1` envelope retains the exact payload and verifies its SHA-256.
Unknown versions, unsupported execution semantics and conflicting revisions fail closed.
The schemas and original fictional examples are in `contracts/praxis/`.

A project Product Owner approves synthetic software checks against the exact package.
Run the reference, no-op and constraint-failure checks, then inspect retained rewards,
criterion diagnostics and artifacts. These predetermined candidates test the machinery;
their scores are never model-performance measurements. Reopening the workbench retains
source revisions, package history, checks and analysis.

Staged tasks reveal only the current actor observation and previously revealed evidence.
Private references remain outside the candidate environment. A trusted verifier grades
each output and applies only declared scalar state updates. Candidate processes run as a
non-root identity and cannot rewrite the authoritative state. Hard-constraint failures
score zero while preserving diagnostics. This adapter does not execute arbitrary prose,
shell commands supplied by authors, or general environment transitions.

## Dedicated worker

Harbor 0.25.0 has independently locked dependencies in `services/harbor/requirements.lock`.
Only the dedicated worker receives the Docker socket. It requires explicit
`ANVIL_HARBOR_WORKER_ENABLED=synthetic-checks-only`; the ordinary worker never claims
Harbor jobs. Cloud deployment enables the `harbor` Compose profile. Host and container
work-directory paths must match for Docker bind mounts. Recovery never automatically
dispatches an ambiguously started invocation again. Cancellation cleans up only the
check's own labeled containers, without deleting persistent volumes.

## Model runs

The workbench can prepare a bounded OpenAI structured-output agent plan. Launch requires
exact provider/model selection, current explicit user authority, locally supplied keys,
reviewed rights with expiration, Product Owner approval and the existing distinct real
Admin controls. The full ceiling is reserved before launch. One provider call is allowed
per stage; SDK retries are disabled. Ambiguous calls retain their reservation and require
reconciliation. Candidate prompts contain actor material only, not expected answers.
Reviews are immutable. Create a new plan to renew an expired review or replace a revoked
one; reusing a previous review never restores rights.

The server mediates provider calls through an ephemeral local gateway. The candidate
container receives neither provider keys nor database credentials. Mock transport and
stub agent tests qualify mechanics only. Cloud configuration currently disables live
dispatch. No new paid-model authority has been supplied for these imported tasks.

## Verification

Run `python3 scripts/local.py check`, `python3 scripts/local.py unit` and the integration
suite. Run database integration checks sequentially after the browser journeys; stop the
registered app/ordinary worker with `python3 scripts/local.py stop` first, preserving the
infrastructure. Independent background processing can invalidate exact event-count tests.
Set `ANVIL_TEST_HARBOR=1` and `ANVIL_HARBOR_DOCKER_HOST` to the authorized local
Docker socket to include real Harbor checks. `ANVIL_PRAXIS_EXPORT_PATH` optionally points
to an actual Praxis envelope for the authenticated import/build/check test. Run
`pnpm exec playwright test tests/e2e/harbor.spec.ts` with the local app and dedicated
worker running for the real-OIDC workbench journey.

Full Library field reconciliation and arbitrary Praxis-task execution are unverified.
Use BUILD-STATUS.md for the latest passed, failed, blocked and pending release checks.
