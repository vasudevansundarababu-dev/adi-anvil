# Fictional staging demo: single new host, two isolated daemons — option for review

**Assessment only. No execution, application release or architecture approval is implied.** Do not repurpose/reconfigure the current Linux QA VM or its database. Complete/export QA evidence and clean up that test host by exact IDs. This option proposes a fresh separate application VM and fictional-only data to avoid inventing unimplemented distributed vault/SQL transport.

Current proposed first invitation is **only the user's existing ADI account, `vasudevan.sundarababu@adi-labs.ai`**, following the user's choice to start with their own account. No application account, subject/application UUID, invitation approval or activation has been created. Proposed hostnames are `anvil-staging.adi-labs.ai` and `anvil-staging-auth.adi-labs.ai`; these remain proposals with no DNS-zone authority, record creation or TLS approval inferred.

The first demo may honestly show the **three-reviewer gate as pending**. One invited admin is not three human reviewers and must not seed substitute identities, grant reviewer assignments, copy fixture approvals or bypass policy. A visible/runnable application or native software-conformance result is not a complete human-approved benchmark. Actual additional reviewers, independent reviews/rights and their activation remain separately pending.

## Assessment against the approved boundaries

This can be a legitimate **bounded fictional-demo architecture amendment**, provided the controls below are implemented and independently verified. The [approved architecture](../anvil-praxis-bodhium-benchmark-2026-11-07/architecture.md) requires a dedicated Harbor runner and says “never give API/ordinary worker a Docker socket” (line20), separate candidate/evaluator execution (lines48–49), and that candidate worker/mount configuration must not gain evaluator-vault access (line73). It does not expressly require physically separate VMs. Two daemons on a dedicated fresh VM can preserve these process/container boundaries; they do **not** create a VM-level security boundary.

The host operator is a trusted coordinator that stages authorized inputs; it is not the actor/container. The actor receives only actor projections, the evaluator only its authorized per-case projection, and neither gets a vault, SQL DSN, cloud metadata credential, Docker socket or host operator environment. This distinction must remain explicit. API policy-gated raw intake/private storage access does not authorize candidate execution to read that storage.

The earlier general design also calls for a separate evaluator service/identity and verified isolation (architecture.md lines73/179). The current offline fixture evaluator and manual host coordinator are a deliberately limited conformance path; this option must not be marketed as completing the general T06 semantic judge, authentic-data processing or autonomous distributed execution architecture. Authentic imports, paid candidates/judges, real secret datasets, public untrusted uploads and multi-user production operations remain disabled/unsupported.

## Proposed fresh resources and scope

- New VM `anvil-staging-demo`, proposed E2standard4/16GiB, 30GiB balanced boot plus50GiB separate data disk. New staging network/subnet/router/NAT/IAP-only administrative access; distinct HTTPS backend/address/hostnames/certificate for app and Keycloak. Final names/CIDR/IAM/TLS/reviewer details require the concrete release plan.
- **No attached cloud service account/scopes or runtime cloud credentials.** No source-control private keys or provider keys. Deploy principal supplies only newly generated staging-specific configuration; no current environment's credentials/data/identities copied.
- No public VM IP or database ports. GCP HTTPS load balancer to Caddy; actual app/auth DNS and invited-user login only after review. No anonymous public demo.
- Fresh PostgreSQL17 with protected roles/schema, Keycloak identity database/realm, Neo4j projection and disjoint artifact/vault roots. No QA database/state reuse.
- Seven-day initial application-demo lifetime, explicitly reviewed fixed STOP and exact-ID cleanup; no automatic restart of a stopped release without renewed review. Persistent charges after STOP must be tracked separately.

This is a resource proposal, not an allocation or a runnable deployment. The current native QA source candidates and results must first be settled; bind the exact reviewed successor SHA, source manifest, images and config hash before release.

## Two-daemon and filesystem contract

**Daemon A, core stack:** separate socket/data/exec/PID roots for app infrastructure. Only deployment administration can access it. API, ordinary worker, web and Keycloak receive no Docker socket or sudo capability. Core images run non-root where supported; PostgreSQL role credentials remain separated. This daemon's Compose lifecycle/rollback cannot issue commands against daemonB.

**Daemon B, native operator:** host-only trusted CLI uses the exact reviewed `ROOT/.local/benchmark-docker/docker.sock` and distinct data/exec/PID paths. No fallback to daemonA/default socket, no stock Harbor probes/cleanup, and only approved preloaded OCI digests. Every adapter/subprocess path must prove explicitB selection. No automatic image pull/build/load at runtime. Core containers must not mount daemonB's socket, config or data; an API compromise must not be able to invoke host sudo merely by sharing a numeric UID.

Use a reviewed dedicated local OS coordinator identity aligned with the backend UID10001 if necessary for owner-only vault semantics. Bind only the required vault to the API's container path; host and container must resolve the **same configured bytes** while ownership checks stay intact. Keep source/operator binaries/config outside API-writable mounts. Do not solve UID mismatch with world/group-readable vault permissions, shared writable source or symlink aliases. Actor/evaluator private projections are per-trial and never a broad mount of this shared vault.

Reviewed preparation path choice: on the **new** application VM, source/operator `ANVIL_ROOT=/opt/anvil`; private host vault `/opt/anvil/.local/benchmark-vault`; generic host artifacts `/opt/anvil/.data/artifacts`. API mounts those exact directories to `/app/.data/benchmark-vault` and `/app/.data/artifacts`, with API `ANVIL_ROOT=/app`. Both logical paths remain inside their installation roots, preserving the existing product guard without symlink/bind aliases. This identical path spelling does not authorize reusing the current QA VM. Native daemonB stays at `/opt/anvil/.local/benchmark-docker`; core daemonA/data/exec/PID/socket and PostgreSQL/Neo4j/Keycloak state use the separate50GiB disk at `/var/lib/anvil-staging-demo`.

Vault, generic artifacts, source/native environment and native retained images/trials occupy the30GiB boot disk. The product's default retained private cap is1GiB **per project**, not an unlimited host quota or permission to create more projects. This option is a single-project fictional demo. Require at least10GiB boot free space before native admission, stop on low space, and review retained trial/container/evidence totals before another invocation. The new config records this required admission check; an enforced runtime lock/free-space implementation and tests remain release gates, not a current capability claim. No shared cleanup/prune or permission loosening is allowed to recover space.

The trusted coordinator's `sudo /usr/bin/docker` is root-equivalent on this VM and could inspect the fresh core data/session secrets; restricted command spelling is not protection against the operator. This is the principal tradeoff requiring explicit acceptance. There are no production/cloud/provider secrets on the VM, but demo accounts/session keys still matter. Same kernel/host, resource contention, single-host outage and privileged-operator compromise remain shared risks. This option is unsuitable for hostile real uploads, confidential partners or production multi-tenancy without stronger reviewed isolation.

## Same-host SQL and evaluator custody

Core API uses the core Docker network PostgreSQL service; host coordinator uses **only a127.0.0.1 binding or owned Unix socket** to that same fresh staging database. No remote SQL listener, cross-host vault synchronization or inferred distributed filesystem is introduced. Keep app/RLS roles distinct from migration owner.

Evaluator connection requires the separately reviewed LOGIN wrapper `anvil_staging_benchmark_evaluator_login`, NOINHERIT/NOSUPERUSER/NOBYPASSRLS/NOCREATEDB/NOCREATEROLE, narrowly granted SET membership to protected NOLOGIN `anvil_benchmark_evaluator` without ADMIN/inherited-owner privileges. Exact startup role options must make current_user the protected role. Never turn the protected role into LOGIN or pass owner/app DSNs as evaluator authority. The coordinator receives these two restricted DSNs; actor/evaluator containers receive neither. Independent SQL proof must validate wrapper authentication, role transition, denial cases and exact job/fence/hash capture.

## Bounded operations and capacity

Only reviewed original fictional fixtures, exact signer/source/rights bindings and fresh test identities. User review/assignment gates remain real; no fixture key, seeded account or deploy flag manufactures an approval. Explicit API fictional-demo flags do not activate paid routes. Generation, live candidate/judge, Vertex support and outbound email remain off.

Manual host-only qualification/offline CLI, **one trial per invocation** (`--max-trials1`), no daemon/auto-drain/retry. At most one active native operation on the entire host, including qualification; operator lock plus SQL claim/fence checks required. Do not start another after ambiguous intent until disposition is reviewed. Cancel/lease/source-policy changes must stop admission without replay. Bound retained evidence/containers and perform exact owned cleanup only after evidence export; no shared `prune`.

Proposed core memory allocation ceiling6GiB total, native runtime budget4GiB with the reviewed per-container limits retained, host/OS+coordinator2GiB and4GiB headroom on16GiB. Native actor/evaluator are sequential under existing stop-before-evaluation semantics; the current evaluator limit is2GiB/1CPU/64PIDs. Do not silently reduce source-enforced native caps to fit a UI demo. Core CPU budget up to3vCPU and native1vCPU; prove memory/CPU pressure does not disrupt DB/auth or leak jobs before acceptance. No throughput or performance guarantee is inferred from these budgets. Disk admission/retention bounds and fresh failure behavior must be tested;50GiB is a proposal, not unlimited retained trials.

The new-demo Compose binding now enforces this **proposed** steady-core allocation, leaving the old renderer unchanged:

| Service | Memory MiB | CPU quota | PID limit |
| --- | ---: | ---: | ---: |
| PostgreSQL |1024|0.50|256|
| Neo4j |1536|0.75|256|
| Keycloak |1536|0.50|256|
| API |512|0.50|128|
| Ordinary worker |512|0.25|128|
| Web |512|0.40|128|
| Caddy |128|0.10|64|
| **Steady total** |**5760 (5.625GiB)**|**3.00**| |

One-off migration has512MiB/0.50CPU/128PIDs, restart disabled; API/worker admission depends on successful migration completion. On an upgrade, explicitly drain/stop prior API/workers before migration; dependencies do not automatically stop an existing old container. No Java/Neo4j heap tuning or native actor/evaluator cap change was introduced. These are hard container quotas but **not** pressure/boot/throughput evidence: JVM overhead, Node/auth/database behavior and memory-pressure recovery must pass actual integrated rehearsal before deployment acceptance.

## Cost comparison and approval gate

The previous core estimate was252.48USD/month plus100USD contingency; it includes one E2standard4,80GiB total balanced storage, NAT/LB/build/log/egress allowances. With both daemons on that same new VM, no second persistent operator VM/NAT is assumed. This estimate must be adjusted for registry/data/log retention and verified against actual image/native storage use; the single-host design does not make native work free.

The already-authorized QA host has a separate60USD operator ceiling, so a full proposed core month plus that QA allocation is **412.48USD**, leaving87.52USD of the additional500USD monthly allowance for unresolved overhead. These are allocations, not accrued bills or a hard cap. Clean QA resources after evidence; do not count uncreated staging resources as current spend or duplicate the old production150USD budget. A seven-day demo should be quoted with its actual fixed lifetime, build and residual costs before approval; no discount, free tier or proportional reduction of all fixed allowances is assumed here.

Separate approval must explicitly accept: fresh app resources/hostnames/reviewer/IAM, the privileged-operator same-host tradeoff, fictional-only scope, dual-daemon/UID/SQL-wrapper implementation, single-trial cap, exact source/artifacts/cost/lifetime, deployed validation/rollback and cleanup. If stronger VM-level evaluator isolation or real/private input processing is required, reject this option and complete the original cross-host custody architecture instead. Nothing in this assessment authorizes application deployment or changes the current QA host.
