# Anvil MVP v1 Google Cloud deployment readiness

Status: deployed 1 October 2026 at https://anvil-34-36-217-66.sslip.io (commit `401f98e`);
see `last_deployment` in `infra/gcp/deployment.json`. The VM is private (org policy forbids
external IPs) behind a global HTTPS load balancer with a Google-managed certificate. User requested Anvil deployment
on 30 September 2026, superseding the earlier local-only deployment restriction, and on
1 October approved the target below.

## Deploy

```sh
git commit ...                                  # deploy.sh refuses uncommitted app changes
infra/gcp/deploy.sh <BILLING_ACCOUNT_ID>        # first time: project, budget, VPC, VM, ...
DEPLOY_ONLY=1 infra/gcp/deploy.sh               # later: rebuild images and roll forward
infra/gcp/invite.sh <username> <email> "<Full Name>" admin researcher
```

Approved target (`infra/gcp/deployment.json`): project `adi-anvil-mvp-2026`, us-west1-a,
one e2-standard-4 VM (Debian 12, Shielded VM), 50 GB pd-balanced data disk with daily
snapshots (14 days), global load balancer IP, hostnames `anvil-<ip>.sslip.io` and
`auth-<ip>.sslip.io`, $150/month budget alert at 50/90/100% and forecast 100%.

| Piece | Implementation |
| --- | --- |
| Edge | Global external Application Load Balancer (Google-managed certificate, HTTP->HTTPS redirect) -> Caddy host router on port 80 (load balancer ranges only); `/api/*` to FastAPI, rest to Next.js |
| Identity | Keycloak 26 `start` (production) on its own PostgreSQL database; admin console only via IAP tunnel to 127.0.0.1:8180 |
| Data | PostgreSQL 17 and Neo4j 5 on the data disk, no published ports; artifacts on the data disk |
| Secrets | Eight generated Secret Manager secrets, readable only by `anvil-vm@`; rendered to owner-only env files at boot |
| Network | Dedicated `anvil-net`; VM has no external IP, Cloud NAT egress, SSH only from the IAP range |
| Images | Cloud Build to Artifact Registry `us-west1-docker.pkg.dev/<project>/anvil` |

Keycloak administration: `gcloud compute ssh anvil-mvp-v1 --zone us-west1-a --tunnel-through-iap -- -L 8180:127.0.0.1:8180`
then open http://127.0.0.1:8180/admin; the bootstrap password is secret `anvil-keycloak-admin-password`.

Backups are crash-consistent disk snapshots. Restore = create a disk from a snapshot and
attach it as `anvil-data`. A restore rehearsal on GCP has not been run.

Reusable target configuration: `infra/gcp/deployment.json`.
Setup and credential isolation: `docs/runbooks/google-cloud-configuration.md`.
Read both before every deployment; missing values block cloud provisioning.

## Repository checkpoint

Application source is committed through `79b8422` on `build/overnight-v1`.
No Git remote is configured. Local check-in does not constitute remote publication.
Advisor brief and five-slide deck are original pitch artifacts, not measured model results.

## Required deployment inputs

- Explicit Google Cloud project ID and region.
- Infrastructure budget and intended availability period.
- HTTPS hostname/domain and public sign-in versus private advisor access.
- Anvil-scoped cloud authentication available to the deployment process.
- Initial invited identities and their intended project roles; do not deploy local demo credentials.

The discovered gcloud executable is inside a sibling Praxis checkout. This workflow
does not inspect or reuse sibling credentials or mutate that product's cloud resources.

## Smallest proposed deployment

A dedicated Compute Engine VM with pinned application containers and persistent storage
is a candidate for the first bounded research MVP. It preserves the existing always-on
worker, PostgreSQL canonical state, Neo4j projection, Keycloak and artifact filesystem.
It is a single-host availability tradeoff, not a highly available production architecture.
Select machine/disk sizes only after approving the target and budget.

Use a supported startup-script or cloud-init container workflow, not the deprecated
Compute Engine container deployment shortcut. Reference:
https://docs.cloud.google.com/compute/docs/containers

## Required application work before release

1. Add a validated cloud environment configuration. The import-time local-only guard in
   `services/backend/src/anvil/config.py` must remain effective for local identity seeds;
   do not simply remove it or disguise a public deployment as local.
2. Containerize the existing web, API and worker using independent locked dependencies.
   Configure the API upstream instead of the hardcoded localhost rewrite.
3. Configure HTTPS, secure session/login/CSRF cookies, explicit OIDC issuer/callback URLs
   and trusted reverse-proxy behavior. Keep authorization, CSRF, RLS and reference isolation.
4. Run Keycloak in production mode with persistent database storage and reviewed hostname
   and proxy configuration. Keep its administrative surface private. Reference:
   https://www.keycloak.org/server/configuration-production
5. Create new Anvil-only secrets and invited accounts. Never ship `.env`, local realm exports,
   demo passwords, private logs, database dumps or synthetic test sessions in build contexts.
6. Keep PostgreSQL, Neo4j and worker endpoints private. Persist canonical data and artifacts,
   establish backup/restore and migration ownership, and retain deployment rollback evidence.
7. Keep paid inference and external sending disabled. Cloud hosting does not grant their
   separate provider/model/budget, rights, activation or independent approval requirements.

## Release checks

Required before claiming deployed: locked builds, cloud-config negatives, HTTPS login/logout,
invitation and role/project negatives, source/reference isolation, migration001–018,
durable worker restart, upload/artifact persistence and backup recovery. Then exercise
the existing objective, Factory, Suite, Protocol, fixture run/review/report and import paths
on the deployed host. Record the actual endpoint and deployment revision.

Latest local evidence: 146 units, 67 integrations; production-mode compose rehearsal passed
(see BUILD-STATUS 2026-10-01). Done in code: items 1-5 above and the private-endpoint part of 6.
Not yet run on GCP: deployment, TLS issuance, deployed smoke checks, worker restart, upload
persistence, snapshot restore and the fixture run/review/report paths on the deployed host.
The MVP remains a research prototype using synthetic fixtures, with no proven live-model
benchmark performance or complete long-horizon runtime acceptance.
