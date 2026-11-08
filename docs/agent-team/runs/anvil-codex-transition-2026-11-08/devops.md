# Anvil Codex transition: DevOps handoff

Date: 2026-11-08. Inspected source and cutover checkpoint: `fd48c278c267d550485d739e4b0a09f0c6d70d79`, branch `codex/anvil-agent-team-2026-11-06`. This is a repository-backed preparation report, not a deployment or a claim of live cloud verification.

## Decision and current readiness

The existing Anvil application is identifiable, but the repository does not define an isolated staging environment or a staging deployment script. Do not execute the existing deployment script against the current environment to satisfy the staging request. The DevOps agent owns subsequent infrastructure work once the exact target and bounded implementation are authorized; this handoff changes no infrastructure.

The user has been asked to choose between a new Anvil staging project and separate resources in the existing Anvil project. That choice, the exact resource names and the staging budget remain pending. A dedicated staging project gives the clearest isolation. Separate resources in the existing project can also work if their identities, data, networking, storage, secrets and routing are independently scoped. Neither option permits borrowing Praxis resources or configuration.

The recorded $150 monthly infrastructure budget belongs to the existing environment. It is not an additional $150 authorization for staging, a hard spending cap, or approval for model calls. Record the incremental staging and build budget, duration and shutdown policy before provisioning.

## Existing target: historical repository evidence

`infra/gcp/deployment.json` records:

| Item | Recorded value |
| --- | --- |
| Project | `adi-anvil-mvp-2026` |
| Region / zone | `us-west1` / `us-west1-a` |
| VM | `anvil-mvp-v1` |
| Application | `https://anvil-34-36-217-66.sslip.io` |
| Identity issuer | `https://auth-34-36-217-66.sslip.io/realms/anvil` |
| Access | `public_invited_users` |
| Cloud configuration | `anvil-mvp-v1`, credentials directory `.local/gcloud-anvil` |
| Infrastructure | `e2-standard-4`, 50 GB persistent disk, daily snapshots with 14-day retention |
| Latest recorded web update | `185059c`, verified 2026-11-02 |

These identify the current invited-user application, not an approved staging target. Its present cloud state, application revision and availability have not been checked. Some older deployment prose contradicts this manifest; do not treat older statements that deployment has not occurred as authoritative current status.

## Why the existing deployment path cannot be reused unchanged

- `infra/gcp/deploy.sh` uses the existing deployment manifest and fixed VM, disk, network, registry, secret, load-balancer and identity names. `DEPLOY_ONLY=1` still builds images, updates the existing VM metadata and runs its startup procedure; it is not an isolation mode.
- `infra/gcp/startup.sh` mounts and can initialize the existing data disk, retrieves secrets, pulls images, runs Compose with migrations and legacy Harbor services, and prunes images. Running it would change the current application and its data environment.
- `infra/gcp/compose.yaml` wires the existing API, ordinary worker, legacy Harbor worker, PostgreSQL, Neo4j and Keycloak. It does not yet deploy the new benchmark qualification and separate evaluator workers or their disjoint private vault configuration.
- The configuration renderer includes import-generation and optional Vertex support paths. Keeping candidate inference disabled alone does not disable every potentially paid path.
- The current machine's `gcloud` executable resolves inside the Praxis checkout. Do not invoke it or reuse its account/configuration. Any later cloud discovery must use an independently installed CLI with an explicit Anvil-only configuration directory and verified account/project.

No cloud commands, credential reads, image operations, tests, builds, deployments or repository pushes were performed for this assessment.

## Concrete staging implementation sequence

1. **Bind the target.** Record approved project ID, region and zone, resource prefix, application and identity hostnames, access policy, Anvil deployment identity, incremental budget and lifetime. Verify existing resources read-only using isolated Anvil configuration. Treat proposed names as proposals until approved. Do not relabel the current VM or route its hostnames to staging.
2. **Add an explicit staging deployment path.** Parameterize or create reviewed staging configuration without changing the existing deployment defaults. Fail closed if staging names collide with the recorded VM, disk, databases, secret identities, OIDC issuer or load-balancer backend. Prepare a reviewable resource plan before creating resources.
3. **Create separate state and identities.** Use staging-only application and identity databases, graph data, service accounts, Secret Manager references, artifact storage and benchmark vault. Start with fictional data. Do not clone user data, authentic task banks, private references or production secrets without explicit authority. Preserve PostgreSQL role separation and project authorization.
4. **Package the actual application.** Bind backend, web and required worker artifacts to the reviewed source SHA. Record registry image digests, architecture, build provenance, dependency inputs and configuration hash. Build and release contexts must continue excluding local credentials, private data and raw logs. Publish no secret values. The existing build definitions need review; source SHA alone does not make unpinned base images reproducible.
5. **Wire the benchmark services safely.** Keep API and ordinary workers free of the Docker socket. Qualification must use the approved restricted operator and exact approved preloaded images, with no fallback build/pull or broad destructive cleanup. Deploy the evaluator as a separate process with the reviewed narrow inputs, SQL projection/role and isolation; do not grant it actor credentials, private vault mounts or the Docker socket. Preserve private `benchmark_sealed` versus legacy `benchmark_output` handling. Create fresh owner-only, non-symlink private roots with the benchmark vault disjoint from generic artifacts; do not weaken checks to accept inherited permissive roots.
6. **Keep every paid route off.** Candidate calls, judge calls, import generation and paid support/Vertex paths stay disabled. Keep outbound email off. No authentic/live benchmark readiness is implied by offline software checks. Exact models, judge, rights, calibration, credentials and budgets remain separate gates.
7. **Qualify before rollout.** Coordinate with the independent Testing agent on the exact committed release: fresh and upgrade migrations, integrated login/import/qualification/evaluation/results paths using permitted fictional inputs, durable restart behavior, tenant/role separation, private-data exposure checks, stale-source rejection and worker cancellation/fencing. Explicitly distinguish missing runtime prerequisites from a pass. Review rollback compatibility before proposing deployment.
8. **Deploy and verify only the reviewed target.** After required review, deploy immutable digests and the reviewed migration/configuration set to staging only. Verify HTTPS, OIDC redirects, assets, authenticated API access, persistence, worker ownership, disabled paid features and the actual source/artifact identity. Return the verified staging URL and evidence; a healthy old application is not evidence that the new release is running.

## Migration and rollback requirements

Before deployment, capture the exact migration ledger, source SHA, image digests, non-secret configuration hash and previous staging revision. Review any automatic migration startup behavior. A backup/restore rehearsal requires staging-specific authorization and must never target the current application's disk or database by default.

Rollback must first stop new benchmark admission and drain or fence only staging benchmark work. Preserve ambiguous-dispatch reservations and evidence; never replay unknown paid requests. Disable new UI/API features, then restore compatible prior image digests and configuration. Retain additive schema, row-level-security policies and private objects unless an independently reviewed migration procedure explicitly permits otherwise. Verify older workers cannot claim incompatible jobs before declaring rollback safe. Do not prune the rollback artifacts during rollout.

## Exit evidence and remaining blockers

DevOps readiness requires an approved exact target and incremental budget, reviewed isolated deployment code, independent test/security evidence, pinned artifact digests, migration/rollback evidence and a verified application journey. None is replaced by historical unit-test totals or a GitHub checkpoint.

Current blockers are the pending target/budget decision and the missing staging and new benchmark-worker deployment wiring. This report does not authorize cloud provisioning, further coding scope, paid calls, production changes or reuse of Praxis infrastructure. Praxis and the user's original local changes remain outside this work.
