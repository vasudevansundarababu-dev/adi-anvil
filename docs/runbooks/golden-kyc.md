# Golden KYC Anvil pilot

Current integration and qualification supersede the historical local-only flow
below: see `docs/generated/golden-kyc-anvil-progress.md` and the exact operational
packet `docs/generated/golden-kyc-qa-handoff.md`. Apply migrations075 and076.
In Benchmarks → Golden Bank KYC, import the pack, bind200 tasks/50 tested evaluator
configurations, and queue the canonical Anvil software Run. Dedicated non-owner
scheduler/grader processes use `--mode capture`, `--mode grade`, then `--mode finish`.
Use canonical Run dashboard/PDF/JSON for results. The original `/runs` profile
preparation below remains a separate toolkit path; it is not the canonical Run.
Paid calls remain off. All200 cases remain unscored pending independent case and
legal review. QA deployment requires qualified OpenEnv/OPA runtime availability;
Staging is held until owner confirmation of QA acceptance. Praxis deliverables
are authoring references, not a native Praxis import or execution target.

The owner-approved bank choices and assignment are frozen in
`docs/generated/golden-kyc-progress.md` and the immutable-version policy module.
The generator creates exactly200 original linked case families with controlled
`.invalid` contacts. It makes no provider calls and imports no external assets.

## Boundaries

Migration075 adds `banking` and `banking_private`; it never truncates/replaces
shared data. New NOLOGIN scheduler/grader capability roles are disjoint. Existing
API and ordinary worker gain no Docker access and no private-answer privileges.
Deployments must provision separate non-owner logins, never reuse migration or
ordinary-worker credentials. This chat has not provisioned deployment credentials.

The dedicated scheduler can read service scenarios, not expectations/results.
The grader reads sealed observations and expectations, not service controls.
The agent accesses the authenticated project gateway, not SQL or either role.
Current membership and assignment are rechecked at execution. Trial token and
generation prevent replay across reset; reset retains events, recommendations,
results and failures. Commands are row-locked, idempotent and not auto-retried
after error. Reset and clock advancement are scheduler-only functions, not tools.

## User flow and execution

With migration075 applied and `ANVIL_GOLDEN_KYC_ENABLED=true`, open Benchmarks →
Golden Bank KYC pilot. An Admin can queue preparation of the frozen200 cases,
browse the inventory and start a clean assigned software trial. The investigation
toolkit submits bounded tool commands and reads their results. Retained trials
export recommendations without credentials or private expected outcomes.

`POST /runs` prepares a dedicated immutable200-cell software profile (up to10
repetitions), bound to the pack manifest and every application hash. It creates
fresh trial state for each cell, separate from the old120-cell business worker.
Preparation is not execution or model performance. Configured paid-model Run
admission is absent while no exact model/budget authority exists.

The gateway prefix is `/api/v1/projects/{project}/golden-banking/v1`. It uses
existing genuine session/CSRF/RBAC and PostgreSQL RLS. Seed/trial/actions return
202 with a command receipt; authenticated `GET /commands/{id}` returns its result.
Verification results distinguish command acceptance, operation acceptance and
completion. The current simulator represents HTTP503/429 and accepted-client-
timeout as structured service observations, not a claimed wire-failure test.
The proposed direct `/identity-checks` style HTTP contract is not yet implemented.

To drain queued commands, provision a reviewed non-owner scheduler login with
only membership in `anvil_golden_scheduler`; set its separate
`ANVIL_GOLDEN_SCHEDULER_DATABASE_URL`, the existing local Anvil settings and pinned
`ANVIL_OPA_BINARY`/`ANVIL_OPA_SHA256`, then use:

```
python -m anvil.golden_kyc_worker --project <project-uuid> --max-commands 100
```

Startup rejects superuser/BYPASSRLS and private-answer privilege. OPA1.22.2
unavailable/error denies actions. No provider settings are consumed. The worker
does not grant its own role, alter paid-call flags or schedule itself.

## Qualification status and remaining gates

The unit/API/SQL and installed OpenEnv0.12.0 checks are software evidence only.
`GoldenEnvironment` subclasses the actual SDK, implements reset/step/state and
has a bearer-gated SDK server. Each scheduler assignment binds a frozen snapshot;
new model/repetition gets fresh state/credentials. SDK reset advances generation
without deleting previous evidence. A candidate cannot call reset through its
tool vocabulary. No model adapter or paid run admission is implemented here.

The Golden Harbor adapter uses the existing Harbor0.25.0 static no-network,
cached-image-only runner, host-mediated tools, bounded collection and separate
verifier. It requires a qualified Linux process domain and dedicated native host.
MacOS source/SDK tests do not qualify Harbor containers. No fallback bypasses the
kernel-domain guard, and no image download/build or deployment was authorized.

Legal modules, charter applicability and independent expectations are pending;
the grader therefore retains unscored points rather than claiming a qualified
100point result. State-specific rule rows, full ten-table business semantics,
trace qualification, partial-credit calibration and negative rule mutations need
completion/review. Initial ten fixed business tables compile only to bounded ZEN
scalar assertions, not a fully reviewed legal decision-table library. Search is a closed in-process corpus with no
network fetch; HTTP gateway/DNS/redirect qualification is not claimed. The frozen
calendar currently uses weekdays only, not an independently reviewed holiday
calendar. Documents are original text representations, not qualified ID images.

No cloud activation is requested. Rollback disables the new feature and worker;
it does not downgrade/delete banking history. Existing schema074 workers do not
understand Golden commands. Preserve earlier release packets and paidOFF flags.
