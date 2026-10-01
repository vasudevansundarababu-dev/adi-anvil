#!/usr/bin/env bash
# Invites one person to the deployed Anvil: creates their Keycloak identity (temporary password,
# forced change at first sign-in) and Anvil project roles. Runs on the VM over IAP SSH.
#
#   infra/gcp/invite.sh <username> <email> "<Full Name>" <role> [role...] [--capability rights_reviewer]
# Roles: researcher advisor product-owner data-engineer reviewer adjudicator sales admin
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
export CLOUDSDK_CONFIG="$ROOT/.local/gcloud-anvil"
export CLOUDSDK_ACTIVE_CONFIG_NAME=anvil-mvp-v1
ZONE=$(python3 -c "import json;print(json.load(open('$ROOT/infra/gcp/deployment.json'))['zone'])")
USERNAME=${1:?username}; EMAIL=${2:?email}; NAME=${3:?full name}; shift 3
ARGS=(--username "$USERNAME" --email "$EMAIL" --name "$NAME")
while [ $# -gt 0 ]; do
  if [ "$1" = --capability ]; then ARGS+=(--capability "$2"); shift 2; else ARGS+=(--role "$1"); shift; fi
done
REMOTE="sudo docker compose -f /opt/anvil/compose.yaml run --rm -T ops python -m anvil.cli invite $(printf '%q ' "${ARGS[@]}")"
gcloud compute ssh anvil-mvp-v1 --zone="$ZONE" --tunnel-through-iap --command="$REMOTE"
