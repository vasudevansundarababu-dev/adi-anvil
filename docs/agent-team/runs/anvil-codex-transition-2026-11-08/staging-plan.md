# Isolated Anvil staging proposal

Current native-QA decision proposal: see `linux-test-host-plan.md` and `infra/gcp/staging-linux-test-host-plan.json` for the standalone disposable test host with fresh same-host PostgreSQL, no VM cloud identity/scopes and its own NAT. That test-only proposal supersedes the earlier extra staging-worker/shared-staging-database proposal below for the immediate native QA request. Both remain unprovisioned; the application staging plan is separate and still stops before deployment.

Prepared 2026-11-08 against checkpoint `adcc1d2`. The user selected the existing Anvil GCP project with separate staging resources and approved an additional USD 500 monthly staging infrastructure budget covering compute, storage and builds. This proposal does not itself execute provisioning, T07 implementation, paid model calls or release. The companion `infra/gcp/staging-plan.json` is a declarative proposal, deliberately not accepted by the existing deployment script.

## Target and resource inventory

Use project `adi-anvil-mvp-2026`, region `us-west1`, zone `us-west1-a`. Propose prefix `anvil-staging`; names below are prospective, not discovered or allocated resources. Hostnames, public address, OIDC issuer, deployment principal and subnet CIDR remain null until inventory and decisions resolve them. The current invited-user application and all Praxis resources remain unchanged.

| Component | Proposed isolated resource |
| --- | --- |
| Compute | `anvil-staging`, one amd64 `e2-standard-4` VM without a direct public IP |
| State | New 50 GB `pd-balanced` disk `anvil-staging-data`; daily staging snapshot policy with seven-day retention |
| Network | `anvil-staging-net`, `anvil-staging-subnet`, dedicated router/NAT; CIDR selected after collision check |
| Firewall | Separate load-balancer HTTP and IAP SSH rules; no database ingress or unrestricted SSH |
| Identities | `anvil-staging-vm` and `anvil-staging-build` service accounts; deployment principal pending; permissions scoped to staging resources |
| Image registry | `us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil-staging` |
| HTTPS ingress | Separate address, instance group, health check, backend, URL map, HTTPS proxy, certificate and forwarding rule, each named with `anvil-staging` prefix |
| Application state | Compose project `adi-anvil-staging`, root `/var/lib/anvil-staging`; fresh application and identity databases, separate roles, graph data and Keycloak realm `anvil-staging` |
| Private storage | Generic artifacts and owner-only benchmark vault are disjoint; dedicated qualification work root; no existing disk mounts |
| Secret references | Eight new staging-prefixed Secret Manager names enumerated in JSON; no current secret versions reused and no values in Git |

Match the approved application stack: Next.js web, FastAPI API, PostgreSQL 17 canonical state, Neo4j projection, Keycloak and background workers, behind the established HTTPS load-balancer/Caddy pattern. A single-host staging deployment limits initial operational scope but is not highly available; worker and database memory/concurrency limits must be reviewed before accepting the proposed VM size. The proposal does not assume a production-sized benchmark fleet.

## Isolation and configuration work required

The current `infra/gcp/deploy.sh`, `startup.sh` and Compose configuration target the current application. Do not run them as staging configuration. A later bounded implementation must introduce explicit staging inputs, collision guards and stage-only state paths without changing current deployment defaults. Fixed data paths, VM names, realm names and secret bindings must not leak through defaults.

Use fresh fictional fixtures and separate staging identities. Do not copy the current database, private task banks, vault, credentials or user accounts. Bind the OIDC issuer and redirects only after distinct application/auth hostnames and certificate ownership are confirmed. Access remains invited-user authentication, not an anonymous public demonstration. Graph storage is isolated and rebuildable; PostgreSQL remains authoritative.

Keep candidate dispatch, judge dispatch, import generation, paid support/Vertex and outbound email disabled. Do not provision model API keys as part of this staging baseline. Exact models, authentic inputs, rights, current pricing and budgets remain separate live-run gates.

The new qualification and evaluator services require deployment wiring that the existing Compose file lacks. API and ordinary workers receive no Docker socket. Qualification preserves the restricted preloaded-image operator and no-build/no-pull/no-delete controls; any image preload needs separate exact authority. Evaluator claims, private sealed inputs and narrow SQL access remain distinct from actor execution. Do not mount evaluator logs or private references into actors. Use fresh owner-only non-symlink roots and preserve legacy output versus private sealed artifact boundaries.

## Read-only verification without Praxis

It is possible to inventory this project independently: use a separately installed approved Cloud CLI, explicit Anvil-only configuration directory, explicit Anvil principal and project, then request only resource metadata. The currently resolved CLI lives inside Praxis and must not be invoked. Root installed official Google Cloud SDK 592.0.0 separately at `/Users/vasudevansundarababu/Documents/Codex/anvil-tools/google-cloud-sdk`, verified archive SHA256 `57553ae3c300f4ebaaa8fb4dee8d40c4d8c1141d84d266b41c1daf1669c4001a` against Google documentation, and checked its version with a new Anvil-only configuration directory. No credentials were read and no cloud inventory or mutation has run. Authentication remains required.

The future inventory must check proposed-name availability, network CIDRs, organization policies, quotas, enabled APIs, billing attachment, deploy-principal permissions and existing registry/resource ownership. Do not read secret payloads. Do not reuse project-wide default build/runtime identities with broad inherited access; review IAM changes for effects beyond staging. Existing project membership alone is not proof of appropriately limited permissions.

## Cost and budget gate

No prices or total have been invented. Before provisioning, obtain current official rates and a dated estimate for: VM running hours and disks/boot disk; snapshot growth and retention; external HTTPS load balancing and address charges; NAT hourly/data processing; network egress; Artifact Registry storage and transfer; Cloud Build machine/minutes and logs; Secret Manager versions/access; and monitoring/log retention. Specify expected uptime, lifetime, traffic, build frequency, image sizes and cleanup policy. Include whether startup needs package/image egress. Record taxes/credits separately where applicable.

The approved additional staging allowance is USD 500 per month for infrastructure including compute, storage and builds. The existing environment's $150 monthly budget is not duplicated or reassigned. Neither this approval nor a billing alert enforces a technical hard cap. Estimate all proposed resources against the $500 allowance before provisioning; define alert thresholds, lifetime, shutdown/retention responsibility and bounded build operations. Budget approval does not authorize model or judge calls. Resource validation, implementation and release gates still apply.

## Release, verification and rollback gates

1. Review exact staging inventory, incremental budget, hostnames, IAM and isolated deployment changes. Resolve JSON nulls before execution rather than silently selecting defaults.
2. Independent Testing agent verifies the exact source release, fresh/upgrade migrations, authorization/privacy boundaries and integrated fictional-data UI journey. Missing runtime prerequisites remain blocked, never passed. This planning artifact is not QA evidence.
3. Build once from reviewed source; record immutable web/backend/worker image digests, architecture, dependency inputs, provenance, configuration hash and migration ledger. Exclude credentials/private data from build contexts. Keep previous staging digests available.
4. Review the deploy plan and rollback compatibility before release. Startup must not format/reuse the current disk, prune shared images, modify current routing or apply migrations to the current database.
5. Verify deployed artifact identity, HTTPS/OIDC, authenticated UI/API journey, persistence/restart, worker ownership and every paid/email flag off. Return the actual verified staging URL; none exists from this proposal.

Rollback disables new staging admission and drains/fences only staging queues/processes, retaining ambiguous-dispatch reservations and evidence. Restore compatible previous staging images/configuration without dropping additive schema/RLS or replaying unknown calls. Test old-worker job compatibility. A first deployment needs a defined return-to-maintenance/offline procedure because no prior staging revision exists. Backup/restore rehearsal is staging-only and requires bounded execution authority; the existing application's snapshots are not staging rollback material.

## Current outcome

Target choice and additional monthly budget are resolved. Exact inventory validation, hostnames/access details, cost estimate and lifetime, scoped principal/IAM, deployment implementation and independent release evidence remain pending. No resources were created or changed. Praxis and local uncommitted changes were not accessed or modified.

## Pricing worksheet — 2026-11-08, incomplete pending regional VM quote

Official public pricing pages were checked on 2026-11-08. USD list prices, 730 hours continuous uptime, no credits, commitments or free-tier offsets are assumed. Dynamic region selectors on public pages must be confirmed for Oregon in the final calculator/SKU quote. In particular, the official general-purpose VM page timed out twice: the `e2-standard-4` Oregon rate is **not verified**, and no third-party rate has been substituted. The following is a conservative planning worksheet, not a complete quoted bill or permission to provision.

| Component and explicit monthly usage | Official rate / calculation | Planning USD |
| --- | --- | ---: |
| VM, one `e2-standard-4`, 730 hours | Oregon on-demand rate still requires official confirmation | Unknown |
| Balanced disks: proposed 50 GiB data + explicit 30 GiB boot assumption | 80 × 730 × $0.000136986/GiB-hour | 8.00 |
| Regional snapshots incl. retained/deleted-chain allowance: 500 GiB-month | 500 × 730 × $0.000068493/GiB-hour; no preview discount assumed | 25.00 |
| One global HTTPS forwarding rule | 730 × $0.025/hour; conservatively no additional-rule discount | 18.25 |
| Load-balancer processing: 100 GiB ingress + 100 GiB egress | 200 × $0.008/GiB | 1.60 |
| Public NAT: one VM, one NAT IPv4, 100 GiB processed | 730 × ($0.0014 + $0.005)/hour + 100 × $0.045/GiB | 9.17 |
| Registry: 50 GiB stored for full month | 50 × 730 × $0.000136986/GiB-hour; same-region pulls assumed | 5.00 |
| Builds: 1,000 default-pool `e2-highcpu-8` build-minutes | 1,000 × $0.0156/minute; no free tier claimed | 15.60 |
| Logs: 50 GiB ingestion, 30-day retention | 50 × $0.50/GiB; shared project's free allotment not claimed | 25.00 |
| Monitoring allowance: 20 MiB chargeable metric ingestion | 20 × $0.258/MiB; no account free tier claimed | 5.16 |
| Secret Manager: 16 active versions, 100,000 accesses | 16 × 730 × $0.000082192 + 10 × $0.03; automatic single-location billing assumption | 1.26 |
| Optional DNS: one managed zone and 1 million ordinary queries | 730 × $0.000273973/hour + $0.40 | 0.60 |
| Internet egress / external address / certificate and related billing reserve | **$40 allocation, not a verified tariff calculation**; destination mix and exact ingress/address treatment pending | 40.00 |
| **Worksheet subtotal excluding VM** | Rounded line items | **154.64** |

Official sources: [VM pricing — unavailable during this check](https://cloud.google.com/products/compute/pricing/general-purpose), [disk and regional snapshot rates](https://cloud.google.com/compute/disks-image-pricing), [load-balancer forwarding and processing](https://cloud.google.com/load-balancing/pricing), [Public NAT](https://cloud.google.com/nat/pricing), [registry storage and transfer](https://cloud.google.com/artifact-registry/pricing), [Cloud Build](https://cloud.google.com/build/pricing), [logs and monitoring](https://cloud.google.com/products/observability/pricing), [Secret Manager](https://cloud.google.com/secret-manager/pricing), [DNS](https://cloud.google.com/dns/pricing), and [network transfer/address pricing](https://cloud.google.com/vpc/network-pricing).

The worksheet leaves $345.36 of the approved $500 for the unverified VM and further uncertainty. Reserve a further $100 contingency: the VM and unresolved charges must fit within $245.36/month (equivalent to $0.3361/hour for the VM if there were no other unresolved charges). This is a budget constraint, **not** a claimed VM price. Do not conclude that staging is within budget until the official Oregon VM quote and transfer/address assumptions are resolved.

The network, subnet, router, firewall, instance group, health check, backend, URL map and service accounts are included in the architecture; this worksheet does not invent separate hourly fees for control-plane objects. Their traffic, IP, logging and attached compute costs are accounted for or explicitly unresolved above. No Cloud SQL, GKE, paid OS, premium identity subscription, Cloud Armor, vulnerability-scanning charges or extra worker VM is assumed. If required, add verified costs before execution. Domain registration, taxes, support plans and model/judge calls are excluded; the latter remain prohibited. Build output staging storage, scanner selection, snapshot churn, registry retention, log volume and cross-region transfers require final review. Usage allowances are planning assumptions rather than enforced quotas: traffic or failed builds can exceed them.

### Subsequent authorization and pricing update

The user subsequently authorized remaining Coding, independent Testing and DevOps preparation within the additional USD 500/month allowance, with an explicit stop before deployment. Earlier pending-budget wording is historical. No cloud provisioning/build/pull or runtime credentials are authorized by this preparation step.

A targeted search of the [official general-purpose VM pricing page](https://cloud.google.com/products/compute/pricing/general-purpose) now returned the E2 table with Oregon among supported regions: `e2-standard-4` on-demand USD 0.13402284/hour, or **USD 97.84 for 730 hours**. The dynamic page's regional selection still needs confirmation in the target-specific final quote; no discount is assumed. Adding that published rate gives a **planning total of USD 252.48/month**, including the explicit USD 40 unresolved-network allowance. With USD 100 contingency the envelope is **USD 352.48**, leaving **USD 147.52** against the approved allowance. This is a provisional planning estimate, not an enforced cap or bill guarantee; resolve regional selectors, transfer destinations, build staging storage, address/certificate treatment and lifetime before deployment.

`infra/gcp/staging_prepare.py` is a local, non-secret validator/contract renderer. It invokes no subprocesses, cloud CLI or deployment commands. Missing endpoints, subnet, deployment identity, source/images or outstanding decisions fail closed. Its successful output never grants deployment authority. Current unresolved values intentionally prevent readiness; existing deployment defaults and scripts remain unchanged.

### Read-only inventory update: 2026-11-08T17:50:08Z

The coordinating agent completed Anvil authentication using an independent official CLI and isolated configuration, then obtained project metadata read-only. Earlier login-pending statements are historical. This DevOps agent read only the sanitized local metadata, not credentials or secret payloads.

Observed counts: one VM, two disks, two networks, 43 subnets, one router, six firewall rules, two addresses, one instance group, one health check, one backend, two URL maps, one HTTPS proxy, one certificate, two forwarding rules, one snapshot policy, one registry repository, nine secret names and two service accounts. No observed names contain `anvil-staging`; the proposed prefix is not currently occupied in these categories. This does not assert future availability, NAT/IAM completeness or deploy readiness.

The existing Anvil subnet is `10.20.0.0/24`. Candidate staging subnet **`10.21.0.0/24`** does not overlap any of the 43 observed project subnet CIDRs. It is now recorded as a proposal, not an allocation; recheck secondary ranges, peering/VPN/on-prem routes and fresh inventory before assignment. No staging address was reserved or resource created. Application/auth hostnames, issuer and address remain null. Inventory observations alone cannot satisfy the validator's exact reviewed-plan binding or release gate.

### Bounded native Linux test-host proposal

Propose one additional **`anvil-staging-native`** Linux/amd64 `e2-standard-4` VM, 30 GiB balanced boot disk `anvil-staging-native-boot`, no public IP, and dedicated `anvil-staging-native@adi-anvil-mvp-2026.iam.gserviceaccount.com` identity. No source-control private keys or provider credentials; obtain reviewed source by a separately approved artifact delivery, not copied local credentials. The daemon/socket/data root belongs only to this disposable host. Do not share the core application's Docker daemon or expose its socket to application containers.

Proposed initial lifetime is **seven days (168 hours)**, with owner-reviewed stop/deletion policy and evidence retention. Automatic shutdown is not implemented and cannot be treated as a cap. Require explicit host/lifetime approval before provisioning; the existing testing/preparation request authorizes this proposal, not its deployment.

Incremental worksheet uses the same published rates and no credits. The full-month case is also shown so the proposal does not depend on timely shutdown. Existing NAT's single IP is reused by this second **staging-only** VM, with additional per-VM gateway cost; no new NAT/IP or load balancer is assumed. Existing core remains untouched.

| Increment | Seven-day test | 730-hour worst-case month |
| --- | ---: | ---: |
| E2 compute at $0.13402284/hour | $22.52 | $97.84 |
| 30 GiB balanced boot disk at $0.000136986/GiB-hour | $0.69 | $3.00 |
| Second NAT VM assignment at $0.0014/hour | $0.24 | $1.02 |
| Additional 10 GiB NAT processing at $0.045/GiB | $0.45 | $0.45 |
| Optional sanitized evidence disk-snapshot/archive allowance: 10 GiB-month regional standard snapshots at $0.000068493/GiB-hour | $0.50 | $0.50 |
| Extra network/log/build-staging allowance, **allocation not tariff claim** | $1.75 | $3.56 |
| **Additional planning amount** | **$26.15** | **$106.37** |
| Existing core including $100 contingency | $352.48 | $352.48 |
| **Combined envelope** | **$378.63** | **$458.85** |
| **Remaining against $500/month** | **$121.37** | **$41.15** |

Seven-day compute is rounded upward from $22.5158; boot/NAT values similarly round upward in the displayed allowance. Costs are planning assumptions, not verified consumption limits. The extra reserve does not duplicate the core $40 reserve: it is an explicit small allowance for operator-specific traffic/log/staging activity. Source artifacts and tests exceeding these bounds require re-estimation. Keep 30-day log retention/no optional paid metrics exporter; core's 50 GiB log and 50 GiB registry assumptions must include operator evidence/artifacts, or add usage. Do not preserve a whole private disk as evidence without reviewing content/retention; the 10 GiB snapshot allowance is an upper planning allocation, not approval to archive private inputs. No separate paid build is assumed; any new operator image build must fit the already budgeted 1,000 build-minutes or be re-estimated.

This combined figure is within $500 **only if** Oregon VM/disk selectors, shared staging NAT configuration and these traffic/storage assumptions are validated. Taxes, domain registration and paid model calls remain excluded. The narrower $41.15 full-month margin means a larger machine, second NAT IP/gateway, long-lived disk, repeated builds or higher data transfer cannot be silently added.

**Scoped SQL transport decision remains required.** Core PostgreSQL currently publishes no host port. For the operator to use a fresh staging database, prepare a dedicated staging-only private listener bound to the core VM's private address, TCP 5432, with host/container firewall and VPC ingress restricted to the reviewed operator's specific private source identity/address; no `0.0.0.0` public binding, no default-network ingress and no changes to the existing application's database. Require PostgreSQL TLS with verified server identity, a narrowly provisioned `anvil_app` database login with existing RLS/assignment checks, short-lived stage-only secret delivery and explicit database selection. Review container publishing/pg_hba/TLS configuration before opening anything. An alternative reviewed encrypted one-shot tunnel can avoid a durable database listener; select and test one approach rather than enabling both. Database credentials stay on the trusted operator coordinator, never in actor/evaluator containers. No connection path exists merely because both VMs are in one project.

Native execution additionally requires the reviewed migration ledger through **052 or later exact source-defined head**, current review-policy source binding, independently locked backend/Harbor runtime, exact preloaded fixture image and dedicated Docker/sudo contract described in `devops-preparation.md`. Source-policy changes require new frozen protocol/runtime bindings. Independent tests must prove SQL role/tenant isolation over the selected transport, native controls and restart/unknown-dispatch behavior before claiming qualification. The exact remaining decision is approval of this seven-day host and selected scoped SQL transport plus its reviewed release/artifact/image bindings—not authority to deploy now.
