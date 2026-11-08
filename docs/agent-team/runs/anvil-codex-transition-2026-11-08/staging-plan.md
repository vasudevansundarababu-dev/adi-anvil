# Isolated Anvil staging proposal

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
