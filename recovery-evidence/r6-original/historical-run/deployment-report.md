# Deployment report: r6 deployed and verified on the existing Anvil GCP environment

- Work ID: `anvil-task-readiness-explanations-2026-11-06`
- Role: DevOps (`.agents/skills/anvil-devops/SKILL.md`)
- Authority: `approvals.md` §9, the user's QA approval and deployment authorization. It was
  relayed by the Codex coordinator on 2026-11-06.
- Operator account: `vasudevan.sundarababu@adi-labs.ai`. The user signed in in their own
  terminal, using the Anvil-only gcloud config `.local/gcloud-anvil`.
- **Result: deployed.** URL: **https://anvil-34-36-217-66.sslip.io/workspace**
- Release window (UTC):
  - 2026-11-07T02:10Z, attempt 1: failed, then rolled back;
  - 2026-11-07T02:22Z–02:27:58Z, attempt 2: succeeded.

The earlier blocked-preflight report and handoff are kept in
`deployment-evidence/deployment-{report,handoff}-blocked-preflight.md`.

## Approved source → deployed images

| Item | Value |
| --- | --- |
| Base / approved tree | `8cdc8a84784c7ae52d7bbb88f36193b387aedb60` plus `finalization-evidence/code-manifest-r6.sha256` (`5c15faf0…`); snapshot tree `18fca788310f91a35a54df39392a37c026ae16b1` |
| Release commit | `15e35f12725a89be6e507b2eb73d4433e666dd76`. It is **local only and was never pushed**, on branch `release/anvil-r6-local` in the ignored worktree `.local/release-r6`. Its parent is `8cdc8a8` and its tree is `18fca78…`, the same as approved. It was built from `deployment-evidence/release-r6.patch` |
| Cloud Build | `1f2b1a68-44d3-44b5-bdc7-8acdf0be710e`, region us-west1, SUCCESS, 02:22:52–02:25:20Z |
| Image tag | `15e35f1-1794018124` |
| backend (api, worker, migrate) | `us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil/backend@sha256:0becacc8551d6910757c32cd6594b7194e6855b5d1e93889f3fa4c4e75472c7b` |
| web | `…/web@sha256:80e0a269584abc35be799c9a0fbdd9a0557d6d09b71909a8b0ca8007f422da25` |
| harbor-worker | `…/harbor@sha256:efaa5c3da4c846a414e43d6c570270300f2a62de49d27b9c01888290c368a377` |
| golden-tools | `…/golden-tools@sha256:f5506d5224953e193f47146ff11fed36ae898fea1f49a50366455f994f0f37ff` |

**Source-to-image binding.**

- The running `adi-anvil-api-1` and `adi-anvil-worker-1` containers use image ID
  `sha256:0becacc8…`; web uses `80e0a269…`; harbor-worker uses `efaa5c3d…`. Each equals its
  registry digest.
- `/app/services/backend/src/anvil/worker.py` in the running API container hashes to
  `ec5afade0e41600fc3eb29d9a857d58887f94c7e49b5d9fc46979eef3c6ab113`, the same as the r6
  manifest.
- The live web bundle contains r6-only readiness strings, all absent before the release:
  - "Anvil has no cost estimate for this model";
  - "Create an execution group to authorize a run";
  - "Create an execution group to review cost, authorization and launch readiness."

## Target (unchanged; nothing was created or replaced)

- **Location:** project `adi-anvil-mvp-2026` (676933531888), `us-west1`, zone
  `us-west1-a`.
- **VM:** `anvil-mvp-v1` (id 1026934762328279181, e2-standard-4).
- **Edge:** global HTTPS load balancer `34.36.217.66` with a Google-managed certificate.
- **Infra files:** the infra files uploaded as VM metadata (`startup.sh`, `compose.yaml`,
  `Caddyfile`, `postgres-init.sh`, `render_config.py`) were byte-identical to the metadata
  already on the VM. There was no config drift (see `rollback-record.txt`).
- **Feature settings carried over unchanged:**
  - `anvil-import-generation-enabled=true`;
  - `anvil-generation-secret-resource`;
  - `anvil-installation-admin-ids`;
  - `anvil-support-vertex=true`;
  - `enable-oslogin=TRUE`.
- **Not changed:** secrets, IAM, firewall, network, load balancer, Keycloak, PostgreSQL,
  Neo4j and Caddy. The data-store and edge containers were not recreated: Caddy, Keycloak,
  Postgres and Neo4j all still show "Up 5 weeks".

## Commands and results

| Step | Command (summary) | Result |
| --- | --- | --- |
| Install the CLI | Official gcloud 592.0.0 and Debian `openssh-client`, installed into ignored `.local/` with checksums verified | `deployment-evidence/gcloud-setup.txt` |
| Sign-in | The user ran `.local/gcloud-anvil-login.sh` (`gcloud auth login --no-launch-browser`) in their own terminal | Account active; no code or token passed through the agent |
| Read-only access check | `testIamPermissions` on the project and the Cloud Build bucket | All required permissions present. No grants requested or made |
| Rollback record | Recorded VM metadata, rollback image digests, `deployment.json` blocks and running containers | `deployment-evidence/rollback-record.txt` |
| Pre-release backup | `gcloud compute disks snapshot anvil-data --snapshot-names=anvil-data-pre-r6-202611070208 --storage-location=us-west1` | READY, 50 GB |
| Release commit | `git worktree add -b release/anvil-r6-local .local/release-r6 8cdc8a8`, `git apply --index release-r6.patch`, commit | `15e35f1`, tree `18fca78…`, manifest verified inside the worktree |
| SSH access | Temporary OS Login key (`--ttl=1d`) in the ignored `.local/deploy-home` | Removed after release, and the local key deleted |
| Attempt 1 | `DEPLOY_ONLY=1 infra/gcp/deploy.sh` with the 3 feature settings carried over | **Failed** at VM startup (`migrate` exit 1). See below |
| Rollback | Set the 4 image metadata keys back to the recorded rollback tags and re-ran startup | startup exit 0; migrate exit 0; health ready. Outage window about 02:16–02:20Z |
| Fix | Release worktree file modes set to 644/755 (`umask 022`); exec bits match Git; tree unchanged | 0 upload files unreadable to others |
| Attempt 2 | Same command, `umask 022` (`deployment-evidence/deploy-attempt2-wrapper.sh`) | **Succeeded.** Image-tag assertion passed, startup OK, migrate exit 0 ("Alembic canonical migrations … ready"), smoke OK |

**Attempt 1 root cause.**

- **Cause:** the agent shell used `umask 077`, set for the credential directory. So
  `git worktree add` created the release files as 0600 and the directories as 0700.
- **Effect:** Docker `COPY` kept those modes in build `b835d1b1…` (tag
  `15e35f1-1794017439`). The backend image's non-root `anvil` user (uid 10001) could not
  read `src/anvil`, so the migration failed with `No module named anvil.cli`.
- **How it was handled:** `deploy.sh` stopped before its assertions, and the release was
  rolled back as above.
- **Why attempt 2 differs:** its image has `cli.py` at `644 root`.
- **Leftover:** the unused image tag `15e35f1-1794017439` remains in Artifact Registry. It
  was left there, because deleting it is not needed and is out of scope.

## Verification (attempt 2)

- **deploy.sh:** the api, web and harbor-worker images equal `…:15e35f1-1794018124`, and
  harbor-worker is `running`.
- **Health:** `GET /api/v1/health` →
  `{"api":"ready","database":"ready","live_inference":"disabled","harbor_live_dispatch":"disabled","version":"0.2.1"}`.
- **Routing:** `/` → 307 to `/workspace`, and `/workspace` → 200. An unauthenticated
  `/api/v1/projects` → 404, as before the release.
- **Edge security:**
  - OIDC issuer is `https://auth-34-36-217-66.sslip.io/realms/anvil`;
  - the public Keycloak `/admin/` → 404;
  - TLS uses Google Trust Services WR3, valid until 2026-12-30;
  - HSTS is present.
- **Runtime flags:** `ANVIL_LIVE_PROVIDERS_ENABLED=false` in the api and worker, and
  `ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED=false` in the api.
- **Harbor dispatch status.** Before the release, health reported
  `harbor_live_dispatch:"gated"`; after the release it reports `"disabled"`. This is the
  documented behavior: `infra/gcp/render_config.py` always writes the Harbor flag as false,
  and `docs/runbooks/harbor-cloud-admission.md` says "every standard redeployment therefore
  returns admission to disabled". Someone had switched it on by hand on the VM since the
  last release.
  - **Effect:** turning admission on again requires the runbook's separate
    activation/launch authorization, step 5. I did not change it back.
  - **Effect on attempt 1's rollback:** the rollback re-ran the same renderer, so it also
    returned the flag to false.
- **Praxis (read-only GETs only):** `praxis-web` → 307 and `praxis-candidate /sign-in` →
  200, unchanged from before the release.

**Not verified:** an authenticated UI walkthrough. No invited reviewer session was used,
and seeded or demo accounts are not deployed in cloud. Readiness behavior was verified by
the shipped bundle content plus r6 QA, not by signing in.

## Rollback

**Code rollback:** set the VM image metadata back, then re-run the startup script:

```sh
. .local/gcloud-anvil.env
R=us-west1-docker.pkg.dev/adi-anvil-mvp-2026/anvil
gcloud compute instances add-metadata anvil-mvp-v1 --project adi-anvil-mvp-2026 --zone us-west1-a \
  --metadata="anvil-backend-image=$R/backend:b0eec40-1793655919,anvil-harbor-image=$R/harbor:b0eec40-1793655919,anvil-golden-image=$R/golden-tools:b0eec40-1793655919,anvil-web-image=$R/web:185059c-1793661384"
gcloud compute ssh anvil-mvp-v1 --project adi-anvil-mvp-2026 --zone us-west1-a --tunnel-through-iap \
  --command='sudo google_metadata_script_runner startup'
```

- **Tested:** this exact procedure was exercised during attempt 1 (02:19–02:20Z), with
  startup exit 0 and health ready afterwards.
- **Rollback digests:**
  - backend `756413ce…`;
  - web `e1e53a2b…`;
  - harbor `865aa0b3…`;
  - golden-tools `539e63df…`.
- **Database:** r6 has no migrations, so the database needs no rollback.
- **Data safety net:** `anvil-data-pre-r6-202611070208`, plus the daily schedule
  `anvil-daily`. Restoring it would discard data written after 02:08Z, so use it only for
  data loss.

## Repository state

- **Approved checkout:** `/workspace/anvil-prd-validation` is unchanged:
  - HEAD `8cdc8a8`;
  - the same 30-file working-tree changes, and the r6 manifest still verifies;
  - `git status` lists the same paths. The new run artifacts are inside the already
    untracked `docs/agent-team/runs/`.
- **Release worktree:**
  - **Location:** the local branch `release/anvil-r6-local` and its worktree
    `.local/release-r6` (ignored) are kept as the exact deployed source.
  - **Uncommitted change:** after a successful run, `deploy.sh` rewrote
    `infra/gcp/deployment.json` there: `last_deployment` is now `15e35f1` /
    `15e35f1-1794018124` / `2026-11-07T02:27:58+00:00`. It also reordered or rewrote the
    `anvil-import-generation` secret reference. That reference now points to the project-ID
    form of the same secret instead of the project-number form; both name the same secret
    in project 676933531888. The change is recorded in
    `deployment-evidence/deployment-json-after-deploy.diff` and left uncommitted.
- **Not done:** pushes, changes to `main` or other branches, Praxis operations, Mac
  checkout operations, IAM grants, secret reads, database resets and product provider calls.

## Residual risks and QA limits

- **No authenticated UI smoke on the deployed host:** see "Not verified" above.
- **Harbor admission is now disabled**, as documented. Re-enabling it needs the runbook's
  separate authorization.
- **Outage:** attempt 1 caused about 4 minutes of API and worker unavailability (about
  02:16–02:20Z) before the rollback finished. The web stayed up throughout.
- **Carried over from QA:**
  - fixture-only verification;
  - the full `pnpm test:e2e`, cross-browser runs and accessibility audit were not run;
  - the 19 Docker-gated tests were not run;
  - D-COPY wording review, the C2 stub and the C4c root cause remain open;
  - S2 design constraint: provider calls must stay outside `guard()`;
  - no restore rehearsal on GCP.
- **Credentials left on this runtime:** the gcloud credentials remain in
  `.local/gcloud-anvil`. To remove them:

  ```sh
  . .local/gcloud-anvil.env && gcloud auth revoke --all
  ```
