# DevOps preparation — current status

The user authorized Coding, independent Testing and separate staging preparation in existing project `adi-anvil-mvp-2026`, within an additional USD 500/month infrastructure allowance. **Stop before deployment.** No resources, builds, image pulls, secret payloads or deployments were performed by this agent. No application is qualified or running in staging; no staging URL exists.

Anvil authentication and read-only discovery were completed by the coordinating agent using an independent official CLI/configuration. Sanitized inventory observed 2026-11-08T17:50:08Z contains no staging-prefix names. Candidate subnet `10.21.0.0/24` overlaps none of 43 observed primary subnet ranges; it is proposed, not assigned. Endpoints, address, reviewed release, IAM and runtime evidence remain unresolved. See `staging-plan.md` for details. The provisional core envelope is USD 252.48/month, or USD 352.48 with contingency; not an enforced cap or final regional quote.

## Prepared source and actual checks

- `staging_prepare.py`: local non-secret validator/contract renderer; rejects unresolved/malformed plans, unsafe resource/identity/secret/path bindings, exact existing-name collisions and missing reviewed inventory bound to the plan. It never deploys.
- `staging_compose.py`: standalone eight-service **core** Compose renderer from six immutable image digests. Separate staging paths/env files; no Docker socket, native worker or evaluator daemon; restart disabled. API alone receives the gated benchmark vault. Ordinary worker and migration have no vault or vault setting; migration has no artifact mounts.
- Core explicitly disables live candidate, Harbor live, import generation, email, benchmark evaluation/offline/native activation and paid Vertex support. Actual support selector `ANVIL_SUPPORT_VERTEX_PROJECT` is empty, selecting the local assistant and overriding env-file values.
- `staging_startup.py`: prints a **planning checklist only**, not an executed rehearsal, installer or deployment. Runtime ownership/symlink checks, secret/config rendering and separate database initialization remain prerequisites.
- Actual backend Dockerfile runs API **8200**; web runs **3202**. Caddy must intercept `/api/*` to `api:8200` before other requests reach web. Next's compiled loopback rewrite cannot independently connect across containers.

`python3 -m unittest discover -s infra/gcp -p 'staging_*test.py'`: **8 passed** at this preparation checkpoint. Cases cover malformed/unresolved contracts, resource/secret/identity/path boundaries, inventory, private-worker mount denial, paid switches, distinct env files, actual ports and immutable images. These are offline configuration checks, not boot/application QA/native execution evidence. Current actual proposal fails closed on unresolved release inputs.

## Native worker environment decision

The new entrypoint is `python -m anvil.benchmark_offline_worker --project <UUID> --run <UUID> --operator <UUID> --max-trials 1`. It is an explicit bounded operator invocation, **not a daemon**. CLI allows 1–18, default 1; larger batches need the exact bounded test plan. It requires reviewed migrations through 052 or later exact source-defined head, frozen run/source/image bindings and current review-policy binding, active project admin/engineer and current individual evaluation assignment. It uses app-role SQL on the trusted coordinator host, exact controlled MockTransport and real actor/separate fixture evaluator. This is fictional software conformance, not model performance or T06 external judge activation.

Do **not** add it to the current backend container: `NativeDocker` requires `sudo -n /usr/bin/docker` and exact `ANVIL_HARBOR_DOCKER_HOST=unix://<ANVIL_ROOT>/.local/benchmark-docker/docker.sock`. The backend Dockerfile installs neither sudo nor Docker CLI and has no dedicated daemon. Mounting a shared socket, enabling privileged core containers or changing permissions would violate isolation.

Proposed test environment: a **separate disposable Linux operator host**, with dedicated Docker daemon/data root/socket and no current-application containers/images. Resource, lifetime, preload and narrow operator authority require review before provisioning; it is **not included** in the single-core-VM estimate. Prefer a bounded short test window, retaining only approved evidence afterward. A full-month second identical VM adds approximately USD 97.84 published-rate compute before disks/network/logs; do not claim remaining budget suffices without those costs and lifetime. No new host or image has been created.

Required native bindings:

1. Exact source SHA/source manifest, dependency locks, Harbor 0.25 adapter and reviewed migration ledger through 052 or later exact head. Runtime/review-policy source changes invalidate frozen protocol hashes.
2. Linux/amd64 operator OS/image, Python, locked backend environment and independently locked Harbor environment at `<ANVIL_ROOT>/.local/harbor-venv/bin/python`. Reviewed sudo policy and `/usr/bin/docker`; dedicated daemon configuration and matching host bind paths. No broad shared-host grants.
3. Exact preloaded fixture OCI digest/ownership. No implicit pull/build/load; old image-download permission is not inherited. Preflight verifies Linux and matching repository digest.
4. Fresh owner-only 0700 vault/work roots with every component non-symlink and benchmark vault under the reviewed root, disjoint from generic artifacts. Core storage is not automatically reused as native test state.
5. Isolated PostgreSQL test target with `DATABASE_URL` using the reviewed `anvil_app` role on trusted host, explicit project/run/operator UUIDs, frozen fictional records, current `evaluation_review` duty and active admin/RL-engineer role. `WORKER_DATABASE_URL` is not used. No current application data or provider credentials.
6. Process-scoped `ANVIL_BENCHMARK_OFFLINE_ENABLED=true`, `ANVIL_TEST_HARBOR=1`, exact Docker socket and `ANVIL_BENCHMARK_VAULT_ROOT`. API benchmark activation is separate. All live candidate/judge/generation/support/email paths remain off. Flags and seeded roles never grant source/rights approval.
7. Exact command/source/environment hashes and actual native/SQL evidence for cancellation, fences, resource bounds and unknown-dispatch retention. Missing native prerequisites remain blocked. Ambiguous intent is not replayed; captured evidence may finalize without redispatch only under existing fences.

Coding confirmed the ROOT/socket contract remains unchanged and CLI stops on error or no claim. `benchmark_pipeline_worker` is another explicit qualification CLI. `benchmark_evaluator_worker` is a functional library without an operational main/CLI: no invented evaluator daemon is deployed. The separate T06 external-judge service remains inactive.

## Remaining release gates

Resolve exact staging endpoint/DNS, IAM and source/digests; review stage-only database/Keycloak initialization; implement runtime root enforcement; complete independent Testing/security and migration/rollback evidence; separately review the native environment. Present the exact release and cost plan for deployment approval. Existing deployment scripts/defaults remain unchanged. Praxis and original local changes remain outside this work.

## Historical preparation evidence

Earlier dated proposal/pricing/inventory history remains in `devops.md` and `staging-plan.md`. Initial pending target/budget/login statements are superseded by the current status above. Earlier startup “rehearsal” wording described intended order only; no operational rehearsal was executed.
