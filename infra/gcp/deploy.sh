#!/usr/bin/env bash
# Deploys ADI Anvil MVP v1 to a dedicated Google Cloud project as one Compute Engine VM.
#
#   infra/gcp/deploy.sh <billing-account-id>      first deployment (creates project and resources)
#   DEPLOY_ONLY=1 infra/gcp/deploy.sh             rebuild images and roll the VM forward
#
# Target values come from infra/gcp/deployment.json. Re-running is safe: existing resources are
# reused, secrets are created once and never printed, the data disk is never recreated.
# Uses only Anvil's own gcloud credential directory (.local/gcloud-anvil), never sibling ones.
#
# Stack on the VM: Caddy (HTTPS, Let's Encrypt) -> Next.js web + FastAPI API, LangGraph worker,
# PostgreSQL 17, Neo4j 5, Keycloak 26 (production mode). Only ports 80/443 are public; SSH is
# IAP-only. Live model dispatch and real email stay disabled (cloud mode refuses them).
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
CONFIG_JSON="$ROOT/infra/gcp/deployment.json"
export CLOUDSDK_CONFIG="$ROOT/.local/gcloud-anvil"
export CLOUDSDK_ACTIVE_CONFIG_NAME=anvil-mvp-v1
jq_() { python3 -c "import json,sys;print(json.load(open('$CONFIG_JSON'))$1)"; }
PROJECT_ID=$(jq_ "['project_id']")
REGION=$(jq_ "['region']")
ZONE=$(jq_ "['zone']")
BUDGET=$(jq_ "['monthly_infrastructure_budget_usd']")
MACHINE=$(jq_ "['architecture']['machine_type']")
DATA_GB=$(jq_ "['architecture']['persistent_disk_gb']")
BILLING=${1:-}
COMMIT=$(git -C "$ROOT" rev-parse --short HEAD)
TAG=$COMMIT-$(date +%s)
VM=anvil-mvp-v1
SA=anvil-vm@$PROJECT_ID.iam.gserviceaccount.com
REPO=$REGION-docker.pkg.dev/$PROJECT_ID/anvil
SECRETS=(anvil-db-owner-password anvil-db-app-password anvil-db-worker-password anvil-neo4j-password
  anvil-session-key anvil-oidc-client-secret anvil-keycloak-admin-password anvil-keycloak-db-password)

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
exists() { "$@" >/dev/null 2>&1; }
retry() { for _ in $(seq 1 12); do "$@" >/dev/null 2>&1 && return 0; sleep 10; done; "$@"; }
gcloud config set project "$PROJECT_ID" >/dev/null 2>&1 || true

if [ -n "$(git -C "$ROOT" status --porcelain -- services apps infra fixtures task-packs assets)" ]; then
  echo "Uncommitted application changes; commit first so the deployed revision is recorded." >&2
  exit 1
fi

if [ -z "${DEPLOY_ONLY:-}" ]; then
  : "${BILLING:?billing account id required for first deployment (gcloud billing accounts list)}"
  say "Project $PROJECT_ID"
  exists gcloud projects describe "$PROJECT_ID" || gcloud projects create "$PROJECT_ID" --name="ADI Anvil" \
    ${ANVIL_ORG_ID:+--organization="$ANVIL_ORG_ID"}
  [ "$(gcloud billing projects describe "$PROJECT_ID" --format='value(billingAccountName)')" = "billingAccounts/$BILLING" ] ||
    gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING" >/dev/null
  gcloud config set project "$PROJECT_ID" >/dev/null
  PNUM=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')

  say "Enabling APIs"
  gcloud services enable compute.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
    secretmanager.googleapis.com iam.googleapis.com iap.googleapis.com logging.googleapis.com \
    monitoring.googleapis.com billingbudgets.googleapis.com

  say "Budget alert (\$$BUDGET/month; alerts only, not a spending cap)"
  if [ -z "$(gcloud billing budgets list --billing-account="$BILLING" --filter="displayName='ADI Anvil MVP v1'" --format='value(name)')" ]; then
    gcloud billing budgets create --billing-account="$BILLING" --display-name="ADI Anvil MVP v1" \
      --budget-amount="${BUDGET}USD" --filter-projects="projects/$PROJECT_ID" \
      --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0 \
      --threshold-rule=percent=1.0,basis=forecasted-spend >/dev/null
  fi

  say "Network (dedicated VPC; HTTPS public, SSH via IAP only)"
  exists gcloud compute networks describe anvil-net || gcloud compute networks create anvil-net --subnet-mode=custom
  exists gcloud compute networks subnets describe anvil-subnet --region="$REGION" ||
    gcloud compute networks subnets create anvil-subnet --network=anvil-net --region="$REGION" --range=10.20.0.0/24
  exists gcloud compute firewall-rules describe anvil-allow-https || gcloud compute firewall-rules create anvil-allow-https \
    --network=anvil-net --allow=tcp:80,tcp:443 --target-tags=anvil-web --source-ranges=0.0.0.0/0
  exists gcloud compute firewall-rules describe anvil-allow-iap-ssh || gcloud compute firewall-rules create anvil-allow-iap-ssh \
    --network=anvil-net --allow=tcp:22 --target-tags=anvil-web --source-ranges=35.235.240.0/20
  exists gcloud compute addresses describe anvil-ip --region="$REGION" ||
    gcloud compute addresses create anvil-ip --region="$REGION" --network-tier=PREMIUM

  say "Runtime service account"
  exists gcloud iam service-accounts describe "$SA" ||
    gcloud iam service-accounts create anvil-vm --display-name="ADI Anvil VM runtime"
  for role in roles/logging.logWriter roles/monitoring.metricWriter; do
    retry gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" --role="$role" --condition=None
  done
  # Cloud Build pushes images with the default compute service account.
  for role in roles/artifactregistry.writer roles/logging.logWriter roles/storage.objectViewer; do
    retry gcloud projects add-iam-policy-binding "$PROJECT_ID" \
      --member="serviceAccount:$PNUM-compute@developer.gserviceaccount.com" --role="$role" --condition=None
  done

  say "Secrets (generated once in Secret Manager; readable only by the VM identity)"
  for name in "${SECRETS[@]}"; do
    if ! exists gcloud secrets describe "$name"; then
      openssl rand -hex 32 | tr -d '\n' |
        gcloud secrets create "$name" --data-file=- --replication-policy=user-managed --locations="$REGION" >/dev/null
    fi
    retry gcloud secrets add-iam-policy-binding "$name" --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor
  done

  say "Artifact Registry"
  exists gcloud artifacts repositories describe anvil --location="$REGION" ||
    gcloud artifacts repositories create anvil --repository-format=docker --location="$REGION"
  retry gcloud artifacts repositories add-iam-policy-binding anvil --location="$REGION" \
    --member="serviceAccount:$SA" --role=roles/artifactregistry.reader

  say "Data disk and daily snapshots (14-day retention)"
  exists gcloud compute disks describe anvil-data --zone="$ZONE" ||
    gcloud compute disks create anvil-data --zone="$ZONE" --size="${DATA_GB}GB" --type=pd-balanced
  exists gcloud compute resource-policies describe anvil-daily --region="$REGION" ||
    gcloud compute resource-policies create snapshot-schedule anvil-daily --region="$REGION" \
      --daily-schedule --start-time=10:00 --max-retention-days=14 --on-source-disk-delete=keep-auto-snapshots
  [ -n "$(gcloud compute disks describe anvil-data --zone="$ZONE" --format='value(resourcePolicies)')" ] ||
    gcloud compute disks add-resource-policies anvil-data --zone="$ZONE" --resource-policies=anvil-daily
else
  say "Redeploy only ($PROJECT_ID)"
fi

IP=$(gcloud compute addresses describe anvil-ip --region="$REGION" --format='value(address)')
WEB_HOST=anvil-${IP//./-}.sslip.io
AUTH_HOST=auth-${IP//./-}.sslip.io

say "Images (Cloud Build, $TAG)"
gcloud builds submit "$ROOT" --config="$ROOT/infra/gcp/cloudbuild.yaml" --region="$REGION" \
  --substitutions="_REPO=$REPO,_TAG=$TAG"

METADATA="anvil-registry=$REPO,anvil-backend-image=$REPO/backend:$TAG,anvil-web-image=$REPO/web:$TAG"
METADATA="$METADATA,anvil-web-host=$WEB_HOST,anvil-auth-host=$AUTH_HOST,enable-oslogin=TRUE"
FILES="startup-script=$ROOT/infra/gcp/startup.sh,anvil-compose=$ROOT/infra/gcp/compose.yaml"
FILES="$FILES,anvil-caddyfile=$ROOT/infra/gcp/Caddyfile,anvil-postgres-init=$ROOT/infra/gcp/postgres-init.sh"
FILES="$FILES,anvil-render-config=$ROOT/infra/gcp/render_config.py"

if ! exists gcloud compute instances describe "$VM" --zone="$ZONE"; then
  say "VM $VM ($MACHINE)"
  gcloud compute instances create "$VM" --zone="$ZONE" --machine-type="$MACHINE" \
    --network-interface=subnet=anvil-subnet,address=anvil-ip,network-tier=PREMIUM \
    --image-family=debian-12 --image-project=debian-cloud --boot-disk-size=30GB --boot-disk-type=pd-balanced \
    --disk=name=anvil-data,device-name=anvil-data,mode=rw,boot=no,auto-delete=no \
    --service-account="$SA" --scopes=cloud-platform --tags=anvil-web \
    --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring \
    --metadata="$METADATA" --metadata-from-file="$FILES"
  say "Waiting for first boot (Docker install, image pull, migrations; ~5-8 minutes)"
else
  say "Rolling VM forward to $TAG"
  gcloud compute instances add-metadata "$VM" --zone="$ZONE" --metadata="$METADATA" --metadata-from-file="$FILES"
  gcloud compute ssh "$VM" --zone="$ZONE" --tunnel-through-iap --command='sudo google_metadata_script_runner startup'
fi

say "Smoke checks"
for _ in $(seq 1 60); do
  if curl -fsS "https://$WEB_HOST/api/v1/health" 2>/dev/null | grep -q '"api":"ready"' &&
     curl -fsS "https://$AUTH_HOST/realms/anvil/.well-known/openid-configuration" 2>/dev/null | grep -q "\"issuer\":\"https://$AUTH_HOST/realms/anvil\""; then
    echo "API health, OIDC discovery and TLS: OK"
    curl -fsS -o /dev/null -w 'Web: HTTP %{http_code}\n' "https://$WEB_HOST/"
    code=$(curl -s -o /dev/null -w '%{http_code}' "https://$AUTH_HOST/admin/")
    echo "Public Keycloak admin path: HTTP $code (expected 404)"
    python3 - "$CONFIG_JSON" "$COMMIT" "$TAG" "$WEB_HOST" "$AUTH_HOST" "$IP" <<'PY'
import json, sys, datetime
path, commit, tag, web, auth, ip = sys.argv[1:]
d = json.load(open(path))
d["status"] = "deployed"
d["web_origin"] = f"https://{web}"
d["oidc_issuer"] = f"https://{auth}/realms/anvil"
d["architecture"]["selection_status"] = "provisioned"
d["architecture"]["service_account_email"] = f"anvil-vm@{d['project_id']}.iam.gserviceaccount.com"
d["secret_resource_references"] = {n: f"projects/{d['project_id']}/secrets/{n}" for n in [
    "anvil-db-owner-password", "anvil-db-app-password", "anvil-db-worker-password",
    "anvil-neo4j-password", "anvil-session-key", "anvil-oidc-client-secret",
    "anvil-keycloak-admin-password", "anvil-keycloak-db-password"]}
d["last_deployment"] = {
    "commit": commit, "image_tag": tag, "static_ip": ip,
    "web_origin": f"https://{web}", "oidc_issuer": f"https://{auth}/realms/anvil",
    "vm": "anvil-mvp-v1", "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "smoke": ["api_health", "oidc_discovery", "tls", "keycloak_admin_private"],
}
json.dump(d, open(path, "w"), indent=2); open(path, "a").write("\n")
PY
    echo
    echo "Anvil: https://$WEB_HOST"
    echo "Invite the first person (temporary password printed once; changed at first sign-in):"
    echo "  infra/gcp/invite.sh <username> <email> \"<Full Name>\" admin researcher"
    exit 0
  fi
  sleep 10
done
echo "Smoke checks did not pass. Inspect the VM: gcloud compute ssh $VM --zone=$ZONE --tunnel-through-iap" >&2
echo "  then: sudo journalctl -t anvil-startup; sudo docker compose -f /opt/anvil/compose.yaml logs --tail=100" >&2
exit 1
