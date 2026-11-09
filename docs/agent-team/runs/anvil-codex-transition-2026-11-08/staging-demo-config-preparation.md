# Fictional demo configuration preparation — no deployment

`infra/gcp/staging_demo_config.py` creates usable configuration artifacts in a **new0700 directory**, each file0600. It performs no cloud, Docker, SQL, ownership change, secret generation, user activation or approval. The default remains paid/email/native-off. Separate user approval of the architecture amendment and exact deployment is still required.

## Required explicit inputs

The public contract requires mode `fictional_demo_preparation`, project `adi-anvil-mvp-2026`, source/operator root `/opt/anvil`, no runtime cloud identity/credentials, distinct actual app/auth DNS names and exact issuer `https://AUTH/realms/anvil-staging-demo`. It binds source SHA/source-manifest hash, six immutable core image digests and the exact separately reviewed native fixture image. It also requires explicit initial invited user's application UUID, OIDC subject UUID, name/email, organization/project UUIDs and names, and reviewed invitation hash. No identity, fixture data, assignment or review authority is invented.

A separate owner-only non-symlink secret JSON supplies ten **distinct new staging-only** values: `db_owner`, `db_app`, `db_worker`, `db_identity`, `neo4j`, `session`, `oidc_client`, `keycloak_admin`, `invited_password`, `evaluator_login`. Matching contract references must name distinct `projects/adi-anvil-mvp-2026/secrets/anvil-staging-demo-*` resources. Reference validation does not prove material newness; trusted provisioning provenance is a release gate. No current application/QA/Praxis credential may be copied. Values are never included in stdout/status. Generated realm/env files contain credentials and must never be committed or uploaded as review artifacts.

Invocation after the inputs are explicitly reviewed:

```text
python3 infra/gcp/staging_demo_config.py --contract PUBLIC_CONTRACT.json --secrets-file PRIVATE_OWNER_ONLY.json --output FRESH_PRIVATE_DIRECTORY
```

The command writes16 files: standalone `compose.json`; actual `Caddyfile`; app/worker/migration/PostgreSQL/Neo4j/Keycloak/web/Caddy envs; private `operator.env`; Keycloak realm; identity database initialization script; blocked identity-bootstrap contract; public expected-not-observed deployment-identity proposal; and deployment guards. It does not run any of them. Existing output and symlink paths are refused.

The bootstrap JSON matches the actual helper's strict `anvil.staging.initial-admin.v1` schema: exactly schema/target/identity/organization/project/reviewed-invitation fields, explicit `origin=real_invited_oidc_identity`, and no approval/apply extras. Unknown VM/disk/cluster observations remain null, deliberately blocking the real validator until trusted deployment observations exist. Deployment approval is a separate receipt, not a field made true by this generator.

The imported invited Keycloak user is **disabled by default**, with a temporary password, `emailVerified=false` and no role grants. An enabled artifact requires explicit `activate_invited_user=true` plus a separate reviewed account-activation hash reference. That reference is not a trusted receipt verification or deployment authority. Real invitation/account verification, activation and exact issuer/subject linkage remain approval/operational gates; generating configuration cannot create a live account or SQL membership. No rights/reviewer/evaluator approval is seeded.

## Concrete bindings and ownership

The explicit `render_demo` binding uses Compose/network `adi-anvil-staging-demo`; old `render()` output remains unchanged. Caddy sends `/api/*` to `api:8200` before the web service3202; auth routes to Keycloak8080 and denies public admin/metrics/health. Load-balancer `/healthz` proxies the actual API/database health endpoint rather than a static success. Actual Caddy parser/Compose boot and HTTPS remain pending checks.

| Purpose | New app VM host path | Container/logical path |
| --- | --- | --- |
| Source/operator root | `/opt/anvil` | API image `/app` |
| Private vault | `/opt/anvil/.local/benchmark-vault` | API `/app/.data/benchmark-vault`; host operator uses exact host path |
| Generic artifacts | `/opt/anvil/.data/artifacts` | API/ordinary worker `/app/.data/artifacts`; operator uses exact host path |
| Core state/config/daemonA | `/var/lib/anvil-staging-demo` | Reviewed per-service state mounts only |
| Native daemonB | `/opt/anvil/.local/benchmark-docker` | Host coordinator only; no core container socket/config/data mount |

No symlink or extra bind alias is needed. Shared vault/artifact directories require ownerUID10001/mode0700, matching API and trusted host coordinator; ordinary worker/migration receive no vault. Keep code/operator secrets outside API-writable mounts. On the actual new host, verify image UIDs before assigning private bind-file ownership: expected Keycloak realm owner1000 and PostgreSQL initialization-script owner999, both0600; Docker-root reads per-service env files0600. The generator deliberately does not chown files locally. Do not make private files world/group-readable to work around a mismatch. API/worker get neither evaluator DSN, native socket nor sudo; `ANVIL_TEST_HARBOR=0` stays set even in the explicit API-only fictional profile.

Canonical database name remains **anvil**, inside the new exclusive PostgreSQL instance, so existing cloud migration guards remain intact. The initial `POSTGRES_USER=anvil_staging_migration` is a privileged SUPERUSER cluster owner by PostgreSQL image behavior; its secret belongs only to one-off migrations/reviewed bootstrap and must never enter API/worker/evaluator. This trust/retention model requires explicit deployment review; non-super migration-owner compatibility or automatic hardening is not claimed. App/worker/evaluator must remain NOSUPERUSER/NOBYPASSRLS; protected evaluator stays NOLOGIN and its dedicated wrapper/SET ROLE path requires independent SQL proof.

Host operator DSNs use only127.0.0.1:5432; PostgreSQL is published only on that loopback address. API uses its `postgres` service network connection. Operator file remains inactive/offline-off until explicit manual activation, host lock, rights/identity and exact-source checks. Only one trial per invocation; no daemon, auto-drain or automatic approval. The bootstrap/deployment-identity files intentionally contain null observed VM/disk/cluster identifiers and cannot serve as trusted runtime proof. Coding's actual observer must independently verify creation records and SQL identity after deployment approval.

Vault/artifacts/native images are on the30GiB boot disk, core state on50GiB disk. Existing private cap1GiB is per-project, not a host capacity guarantee. A single fictional project, retained-evidence bounds and at least10GiB boot free space before native admission are required. Config records these checks but does not implement the host lock/free-space runtime enforcement. No QA host repurpose, application resource creation or native configuration change occurred.

## Validation and remaining gates

Focused local tests: **10 generator tests +11 Compose tests passed**, plus3 build-recipe checks and the separately reviewed operator/bootstrap checks. The coordinating agent's aggregate **57 preparation tests passed** snapshot preceded the final new-demo service-budget test; that additional focused test passes without claiming a new aggregate count. The locked `/private/tmp/anvil-testing-backend/bin/python` and required local socket permission were used for aggregate verification. The earlier aggregate47 was an intermediate snapshot. Coverage includes actual `anvil.config` cloud validation in isolated child processes using fake values/no network or SQL; strict bootstrap schema, disabled default invitation/separate activation binding, exact callback/subject; proxy ordering/ports; distinct per-service secrets and operator-only evaluator/socket settings; full default-off/API-only opt-in behavior; existing render compatibility; matched mount bytes;0600/0700 output; unsafe host/issuer/UUID/secret injection/image/overwrite/symlink denial; CLI non-disclosure/nonexecution; and new-demo memory/CPU quotas with migration-before-worker ordering and no native cap reduction.

Historical environment notes, resolved rather than hidden: an earlier broad42-test run encountered a local Unix-socket sandbox PermissionError; system Python also lacked psycopg for bootstrap tests. Neither was a product failure. The correctly permissioned locked interpreter run above passed; there is no remaining socket/dependency test blocker. No network/SQL service or application boot is inferred from preparation tests.

A reviewable **TEST-ONLY dummy-material** fixture with current standardized bindings, strict bootstrap schema and disabled invited user is at `.local/staging-demo-config-fixture-v4`. The actual generator return/file listing was checked: **16 files**, including8 core service envs and a separate host-only operator env. Earlier `.local/staging-demo-config-fixture` and `-v2` are preserved historical preparation output and must not be consumed. Values/UUIDs/hosts are manufactured test inputs, not a real invitation or release configuration. No real credentials were read.

The separately reviewed operator one-shot guard now provides a persistent exclusive lock/unknown sentinel and an exact boot-device plus10GiB free-space **admission** check. This is not continuous disk monitoring or an automatic stop of an already-running actor on low space; the config's storage intent must not be read as that capability. Source/SQL authorization and unknown-dispatch disposition remain intact. Actual target integration and deployed acceptance proof are still required.

Remaining release gates: actual user/reviewer invitation/activation, DNS/TLS, exact approved artifacts/config, trusted observed VM/disk/SQL materialization, migration-owner secret controls, evaluator-wrapper proof, UID/ownership/bootstrap and Caddy/Compose browser rehearsal, deployed operator/admission integration, resource cost/lifetime/rollback, and explicit architecture/deployment approval. Passing configuration tests is not a deployed application or complete acceptance result. The reviewed backend/web-only build recipe and its immutable output/provenance gates are in `staging-build-recipe.md`; no paid build has run.
