# Native verification preparation — frozen e4bb2d5

Status: read-only preparation; host not yet ready and no native tests run. Parent relayed authorization for the published isolated host plan88bcb5d, ceilingUSD60; creation not before2026-11-08T19:30:00Z. Parent subsequently confirmed new explicit resource authorization accepted by automatic review and DevOps provisioning resumed. DevOps owns provisioning and host readiness. Testing owns execution/evidence only. This is fictional software conformance, not a real three-model benchmark or application deployment.

Exact source: `e4bb2d56800b6e2705b359724750c5702a003204`; git archiveSHA256 `68d37ec7191c64a592a9710bd592cb40e7c002a87ca7d73e88dc3f6279a3f325`; migrations001–058. No source edits or substituted stock Harbor environment. A discovered source defect stops the affected checks for parent review and a new checkpoint.

## Host readiness contract

- Short canonical source root, preferably `/opt/anvil`, all paths verified non-symlink. `ANVIL_ROOT` equals that root. Dedicated Docker daemon/data root/socket only; exact socket `unix://ROOT/.local/benchmark-docker/docker.sock`, `/usr/bin/docker`, reviewed noninteractive sudo policy. No shared socket, host credentials or external application containers.
- Linux/amd64 and cgroup resource limits available. Exact approved Python fixture and PostgreSQL OCI digests preloaded by DevOps into this daemon. Every test uses pullnever. Testing performs no image pull/build/load.
- Frozen Python3.12 backend environment and separately version-pinned Harbor0.25 environment at `ROOT/.local/harbor-venv/bin/python`. Source lock-file hashes match the published plan. Harbor's original requirements file has exact version pins but no distribution hashes: derive and verify an additional artifact-hash manifest against official PyPI without changing any name/version pair before installation. Record the derived manifest and actual installed packages separately. The backend build-system requirement for Hatchling is unversioned; capture its actual version/artifact provenance and retain that limitation. Do not describe either source file as a complete hash-locked build environment. No global Python or source lock changes.
- Fresh disposable PostgreSQL database with canonical migrations058, exact restricted application/worker/evaluator roles and credentials generated only on this host. Database URLs stay in owner-only runtime environment files and never in reports. `ANVIL_BENCHMARK_TEST_DATABASE_URL` is the isolated migration-test connection; `DATABASE_URL` is the restricted app connection. No old runtime database or credential copying. Native-only SQL fixtures create their own fictional organizations/duties/signing keys.
- Fresh owner-only0700 vault/work/artifact roots, private vault disjoint from generic artifacts. `ANVIL_BENCHMARK_ENABLED=true`, `ANVIL_BENCHMARK_EVALUATION_ENABLED=true`, `ANVIL_BENCHMARK_OFFLINE_ENABLED=true`, `ANVIL_TEST_HARBOR=1`. Local environment/web origin consistent; no public service required. All live candidate/Harbor provider, generation, email, tracing and Vertex support paths disabled; no provider credentials. Offline SDK adapters use test transports, not real provider HTTP calls.
- Read back daemon identity, image digests, host architecture/kernel/cgroup information, source/lock hashes and migration head before execution. Missing prerequisite is blocked, never replaced with fabricated qualification metadata.

The canonical local migration entrypoint is `python -m anvil.cli migrate`; it explicitly requires the fresh database name `anvil_local` when `ANVIL_ENV=local`. This is safe only on the new isolated host/daemon, not an existing application's database. It initializes the two restricted login roles, schema/migrations and library checkpoint tables. The selected evaluator tests use `SET ROLE anvil_benchmark_evaluator` from their disposable migration-test connection; no evaluator LOGIN grant/password is needed. These28 selectors do not require Keycloak, Neo4j, a running web server or seeded demo users. Do not add unrelated service prerequisites.

## Exact first native suite

Run from the pinned root using its locked backend Python and constructed allowlisted environment; capture command, UTC time, exit status, complete private stdout/stderr and SHA256. Use `--tb=short` to avoid connection-error rendering of generated database credentials. The explicit selectors expand to28 cases; no blanket native opt-in across unrelated integration modules.

```text
python -m pytest -q -p no:cacheprovider --tb=short -rs \
 services/backend/tests/benchmark/test_benchmark_qualification.py::test_real_native_harbor_trial \
 services/backend/tests/benchmark/test_benchmark_qualification.py::test_native_rejects_stale_package_or_evaluator_before_execution \
 services/backend/tests/benchmark/test_benchmark_native_limits.py \
 services/backend/tests/benchmark/test_benchmark_offline_native.py::test_real_native_offline_sdk_and_separate_evaluator \
 services/backend/tests/benchmark/test_benchmark_evaluation.py::test_real_native_separate_evaluator_captures_fenced_private_result \
 services/backend/tests/benchmark/test_benchmark_evaluation.py::test_native_actor_stops_before_its_bytes_enter_separate_evaluator \
 services/backend/tests/benchmark/test_benchmark_pipeline.py::test_real_native_receipts_persist_through_durable_pipeline
```

Coverage: nine positive/empty/guardrail fictional trials across24/6/51-point tasks; three stale-package/private-rule denials; four actual cgroup/PID/OOM/timeout/output bounds; nine offline provider SDK conversations through real isolated actors and separate evaluators; two fenced evaluator isolation/custody cases; one durable native qualification pipeline. SDK provider-call counters represent fixture transport calls and must never be reported as paid calls or measured model performance.

Preserve actual retained container identities/receipts, actor-stopped-before-evaluation checks and source/environment hashes. Tests stop only their owned containers and intentionally retain evidence; no broad removal/pruning. Any skip in these28 cases remains a missing native requirement. Parent decides bounded follow-up after real findings; no source patch or deployment is implied by passing this suite.

## First actual host execution — e4,2026-11-09 UTC

Independent preflight confirmed Python3.12.14, both exact lock hashes, migration058, restricted app/worker roles and NOLOGIN evaluator, the two approved Linux/amd64 image digests, exact dedicated socket and absent default socket. All400 operator-manifest paths matched; Testing also independently compared401 archived e4 Git-blob paths including the original e4 staging-plan. The earlier409 local manifest contains later plan preparation and was not used to misidentify archived source.

At01:08:25Z, the selected suite ran with failfast. **First positive FX-001 qualification failed; zero qualification passes.** The nonroot Harbor adapter asked privileged Docker Compose to write a JSON validation file using `config --output`, then attempted to read that file as the nonroot operator. Actual retained file mode/owner:0600 root:root,1236bytes. The read raised PermissionError at `services/harbor/src/anvil_harbor/sme.py:167`, before an actor container was created. Docker inventory contained only the owned PostgreSQL container. This is a confirmed source integration defect, not missing Docker/image/role readiness. Root and Coding were notified; affected cases stopped. No chmod, broader permission grant, host workaround or green-until-pass rerun occurred. Private log SHA256 `a1df897e0fe8eee66178fb6b6fedf234224c92edfdf0abb739cf5587f4fc1d10`; JUnit SHA256 `ce7f2ec1f0b83f076b643d6adad68ee3e620e7d308075158d8bda0ce11cb35f0`.

Separately at01:10:19Z, the four native resource probes, which do not use Compose, **passed4/4** in14.63seconds on unchanged e4. They exercised actual cgroup OOM/PID bounds and owned process/stdio timeout/overflow stopping. Private log SHA256 `68cc2084625760a68bcb3a358a109680376fe04670254a5efb722a42557a72a4`; JUnit SHA256 `1ece8fc37530fe6fb52751974843c2a2c8653cda3c8295de9dadb285182fcf5f`. This independent subset does not qualify the blocked actor/evaluator/SDK path.

Owned logs/JUnit/summary were exported only to ignored `.local/native-qa/results`; private environment/credentials were not copied. Sanitized versioned receipts are `native-e4-summary.json` and `native-limits-e4-summary.json`. Source-fix review, pushed successor binding and fresh affected checks remain required. No paid provider calls or application deployment occurred.
