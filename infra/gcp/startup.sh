#!/bin/bash
# Compute Engine startup script for the ADI Anvil MVP v1 host. Runs at every boot and on redeploy
# (sudo google_metadata_script_runner startup). Idempotent: never formats a disk that has data,
# never deletes volumes. Configuration comes from instance metadata; secrets from Secret Manager.
set -euo pipefail
exec > >(logger -t anvil-startup) 2>&1

md() { curl -fsS -H 'Metadata-Flavor: Google' "http://metadata.google.internal/computeMetadata/v1/instance/attributes/$1"; }
PROJECT=$(curl -fsS -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/project/project-id)
REGISTRY=$(md anvil-registry)
WEB_HOST=$(md anvil-web-host)
AUTH_HOST=$(md anvil-auth-host)

echo "== Docker engine"
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  apt-get update -q
  apt-get install -yq ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $VERSION_CODENAME stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -yq docker-ce docker-ce-cli containerd.io docker-compose-plugin
  systemctl enable --now docker
fi

echo "== Data disk"
DEV=/dev/disk/by-id/google-anvil-data
DATA=/var/lib/anvil
mkdir -p "$DATA"
if ! blkid "$DEV" >/dev/null 2>&1; then
  mkfs.ext4 -m 0 -E lazy_itable_init=0,lazy_journal_init=0,discard "$DEV"
fi
mountpoint -q "$DATA" || mount -o discard,defaults "$DEV" "$DATA"
grep -q "$DEV" /etc/fstab || echo "$DEV $DATA ext4 discard,defaults,nofail 0 2" >> /etc/fstab
mkdir -p "$DATA"/{postgres,neo4j,artifacts,caddy,harbor-checks}
chmod 700 "$DATA"
chown 10001 "$DATA/artifacts" && chmod 700 "$DATA/artifacts"
install -d -o 10001 -g 0 -m 0700 "$DATA/secret-index" "$DATA/import-worker-home"
install -d -o 10001 -g 0 -m 0700 "$DATA/import-tmp"
# Prepare empty operator-managed locations only. Never create key/authority values.
for private_dir in "$DATA/harbor-private" "$DATA/harbor-authority"; do
  [ ! -L "$private_dir" ] || { echo "Refusing symlinked Harbor private directory" >&2; exit 1; }
  install -d -o 10001 -g 0 -m 0700 "$private_dir"
done

# The read-only authority mount must contain the nested worker-home mount point.
install -d -o 10001 -g 0 -m 0700 "$DATA/harbor-authority/import-worker-home"

echo "== Runtime configuration (secret values are never logged)"
secret() { gcloud secrets versions access latest --secret="$1" --project="$PROJECT" </dev/null; }
while read -r var name; do
  value=$(secret "$name")
  export "$var=$value"
done <<'MAP'
ANVIL_DB_OWNER_PASSWORD anvil-db-owner-password
ANVIL_DB_APP_PASSWORD anvil-db-app-password
ANVIL_DB_WORKER_PASSWORD anvil-db-worker-password
ANVIL_NEO4J_PASSWORD anvil-neo4j-password
ANVIL_SESSION_KEY anvil-session-key
OIDC_CLIENT_SECRET anvil-oidc-client-secret
ANVIL_OIDC_ADMIN_PASSWORD anvil-keycloak-admin-password
KEYCLOAK_DB_PASSWORD anvil-keycloak-db-password
MAP
mkdir -p /opt/anvil
md anvil-render-config > /opt/anvil/render_config.py
export ANVIL_IMPORT_GENERATION_ENABLED="$(md anvil-import-generation-enabled 2>/dev/null || echo false)"
export ANVIL_GENERATION_SECRET_RESOURCE="$(md anvil-generation-secret-resource 2>/dev/null || true)"
export ANVIL_INSTALLATION_ADMIN_IDS="$(md anvil-installation-admin-ids 2>/dev/null || true)"
if [ "$(md anvil-support-vertex 2>/dev/null || true)" = "true" ]; then
  export ANVIL_SUPPORT_VERTEX_PROJECT="$PROJECT"
fi
python3 /opt/anvil/render_config.py "$DATA/config" "$WEB_HOST" "$AUTH_HOST"
unset ANVIL_DB_OWNER_PASSWORD ANVIL_DB_APP_PASSWORD ANVIL_DB_WORKER_PASSWORD ANVIL_NEO4J_PASSWORD \
  ANVIL_SESSION_KEY OIDC_CLIENT_SECRET ANVIL_OIDC_ADMIN_PASSWORD KEYCLOAK_DB_PASSWORD

md anvil-compose > /opt/anvil/compose.yaml
md anvil-caddyfile > /opt/anvil/Caddyfile
md anvil-postgres-init > /opt/anvil/postgres-init.sh
chmod 755 /opt/anvil/postgres-init.sh
cat > /opt/anvil/.env <<ENV
ANVIL_BACKEND_IMAGE=$(md anvil-backend-image)
ANVIL_WEB_IMAGE=$(md anvil-web-image)
ANVIL_HARBOR_IMAGE=$(md anvil-harbor-image)
ANVIL_WEB_HOST=$WEB_HOST
ANVIL_AUTH_HOST=$AUTH_HOST
ENV

echo "== Containers"
gcloud auth configure-docker "${REGISTRY%%/*}" --quiet >/dev/null
GOLDEN_IMAGE=$(md anvil-golden-image 2>/dev/null || true)
if [ -n "$GOLDEN_IMAGE" ]; then
  docker pull "$GOLDEN_IMAGE" --quiet >/dev/null
fi
docker pull python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e --quiet >/dev/null
cd /opt/anvil
docker compose --profile harbor pull --quiet
docker compose --profile harbor up -d --remove-orphans
for _ in $(seq 1 90); do
  if docker compose exec -T api python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8200/api/v1/health',timeout=2)" 2>/dev/null; then
    echo "Anvil API ready"
    docker image prune -f >/dev/null
    exit 0
  fi
  sleep 5
done
echo "Anvil API did not become ready; inspect: docker compose -f /opt/anvil/compose.yaml logs"
docker compose ps
exit 1
