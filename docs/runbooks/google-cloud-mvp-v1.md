# Anvil MVP v1 Google Cloud deployment readiness

Status: preparation only. User requested Anvil deployment on 30 September 2026,
superseding the earlier local-only deployment restriction. No cloud resources created.
The existing application is not yet a qualified cloud release.

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

Latest local evidence remains130 units,67 integrations and4 browser journeys.
Cloud-specific build, deployment, identity and smoke checks are not run.
The MVP remains a research prototype using synthetic fixtures, with no proven live-model
benchmark performance or complete long-horizon runtime acceptance.
