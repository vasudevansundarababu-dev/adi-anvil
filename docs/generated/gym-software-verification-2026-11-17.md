# RL Gym software verification — 17 November 2026

Status: software-control milestone verified; native/live readiness incomplete.

Source: isolated branch codex/runtime-correction-20261117, commit
38c398bdfffad1607598128704719b665ccf3af7. Root unrelated edits preserved.
Authoring integration and paid calls remain deferred by the user's direction.

Changes: pinned OPA1.22.2 added to the task image; bounded software-only service
with exact project UUIDs, disjoint roles, fixed nonpaid phases and no failure
restart. Active children and SIGTERM-resistant descendants are terminated; source
custody and no-replay stay intact. Standalone Compose uses distinct service names,
separate env files, no mounts/ports/privilege and the exact existing DB network.
Recovered current tests omitted from the release; repaired stale mocks and test
clocks. Actual prices and freshness gates remain unchanged. Development SDK uses
the editable checkout; production runtime remains frozen and wheel-only.

Results:1019 unit checks plus10 subtests passed;28 actual PostgreSQL/CLI checks
passed. Includes200 KYC cells through disjoint capture/grading and canonical
JSON/PDF, and all12 Marketing graph windows with PostgreSQL checkpoints. Effects
are software controls, provider_calls0, not model performance. Cloud Build
4200658b-fd60-425c-a781-cfa6c0a55da5 SUCCESS:452 installed source files matched;
source hash exactly matches the local SQL run; three actual OPA allow/deny/missing
policy controls passed; installed service child entry executed with no DB/network.
The result explicitly native_qualified=false. Image digests in the existing
Anvil QA registry: KYC4d17e62eb3fd2730360659c2443670071dc910cd4a3500800a5dcf3d4965a82b;
Marketingcd107345b096a9146c9d305021a3d809d7d1195daf995e2bcda3a82500ce7119;
common61529766c6cbcf5e6fc28384b5586ecb99c61fd78a7e836daa4604e8056e8b0b.

Both exact task-image digests pulled onto QA. Actual-host containers
forge-gym-kyc-installed-38c398b and forge-gym-marketing-installed-38c398b exited0;
each repeated the452-file source check, identical source hash, actual OPA controls
and installed child entry. No network, credentials or mounts; nonroot/read-only,
capabilities dropped, bounded CPU/memory/PIDs. These are not serving workers.

Commands, from .local/runtime-correction-20261117:

    ANVIL_ENV=local WEB_ORIGIN=http://127.0.0.1:3202 ANVIL_FIXTURE_MODE=true ANVIL_ROOT="$PWD" ANVIL_MARKETING_SOURCE_FIXTURE_ROOT="$PWD/.local/marketing-source-control-20261117" services/openenv/.venv/bin/python -m pytest services/backend/tests/unit -q --tb=short
    services/backend/.venv/bin/python scripts/verify_gym_software.py

Final SQL evidence: ignored .local/forge-gym-sql-20261117-586f04;
database anvil_golden_kyc_8fd2402b71; stopped container retained. Start/end hash
1dc0c3f7a90f26d4ef5e98aedb523266957c24fa38366e24c0a8f28ddd23386b.
Unit log: .local/gym-sdk-units-final-20261117.log. Private fixtures/logs/credentials
are ignored. Existing273-file control pack inventory hash
59539b978994b472495f46786cf5085eae553230d2d7a2356acb165dea9d539a;
this is not the user's three pending Authoring exports.

Retained failures: installed development source origin, omitted checkpoint setup
in first harness, stale mocks/clocks, and source changed during a concurrent SQL
run (correctly denied409; frozen rerun passed). Queued build176d8a96-39b8-41bc-88d9-6312861a507e
was cancelled before execution to correct its source-label typo. Existing Authlib
deprecation warning remains. Failed/cancelled runs are not counted as passed.

QA UI: actual login redirect renders ADI-Forge QA; operator comparison verified
all other realm fields unchanged. No internal identifiers or access policy changed.

Remaining: software-worker QA wiring/observations, complete Marketing native
operator/world/lifecycle and physical capture/finish integration, exact-image
native isolation/recovery qualification and authentic runtime admission. Existing
Marketing native gate remains closed. No fabricated Ready/approval records.
The nearest missing connection is the outer operator driver for
marketing_native_operator_bootstrap._original_operation: retain the operator
container, observe actual Docker/PID/network namespace identities, send the first
bounded frame, bind the returned original control/receiver PIDs in operator-owned
assets, call API prepare once, then send the prepared frame and retain cleanup.
No production frame producer exists in this source. Qualified operator recipe,
sealed proof mounts, cgroup termination, private API routing/auth and independent
exact-source admission are prerequisites; tests cannot manufacture those facts.
No whole-Gym stability or paid benchmark claim. Main service unchanged; no new
inference, Authoring integration or additional email.
