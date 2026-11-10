#!/bin/bash
# Bounded build on the single approved QA host, never production.
set -euo pipefail
umask 077
test "$(hostname)" = anvil-overnight-qa-20261110
test "$(id -u)" = 0
role=${1:?backend or web required}
case "$role" in backend|web|combined) ;; *) exit 2;; esac
root=/var/lib/anvil-overnight-qa/build
install -d -m 700 "$root"
exec 9>"$root/admission.lock"
flock 9
count=0
test ! -f "$root/count" || read -r count < "$root/count"
test "$count" -lt 3
printf '%s\n' "$((count+1))" > "$root/count"
printf '%s %s\n' "$(date -u +%FT%TZ)" "$role" >> "$root/dispatches.txt"
flock -u 9
exec >"$root/$role.log" 2>&1
cd /opt/anvil-overnight-qa/source
if test "$role" = combined; then
  bases=(ghcr.io/astral-sh/uv:0.12.19 python:3.12-slim-bookworm node:24.21.0-bookworm-slim)
elif test "$role" = backend; then
  bases=(ghcr.io/astral-sh/uv:0.12.19 python:3.12-slim-bookworm)
else
  bases=(node:24.21.0-bookworm-slim)
fi
for image in "${bases[@]}"; do
  docker pull --platform linux/amd64 "$image"
  docker image inspect "$image" --format '{{index .RepoDigests 0}}' >> "$root/$role-bases.txt"
done
# Build a separate reviewed recipe bound to just-read immutable base digests.
python3 - "$role" "$root" <<'PY'
import sys
from pathlib import Path
role,root=sys.argv[1],Path(sys.argv[2])
source=Path('infra/docker')/(role+'.Dockerfile')
if role=='combined':
 web=Path('infra/docker/web.Dockerfile').read_text().rsplit('\nFROM node:',1)[0]
 backend=Path('infra/docker/backend.Dockerfile').read_text()
 additions='''COPY --from=build /usr/local/bin/node /usr/local/bin/node
COPY --from=build /usr/lib/x86_64-linux-gnu/libstdc++.so.6* /usr/lib/x86_64-linux-gnu/
COPY --from=build /app/apps /app/apps
COPY --from=build /app/node_modules /app/node_modules
ENV NEXT_TELEMETRY_DISABLED=1 NODE_ENV=production
'''
 text=web+'\n'+backend.replace('USER anvil',additions+'USER anvil')
 tags=['ghcr.io/astral-sh/uv:0.12.19','python:3.12-slim-bookworm','node:24.21.0-bookworm-slim']
else:
 text=source.read_text()
 tags=['ghcr.io/astral-sh/uv:0.12.19','python:3.12-slim-bookworm'] if role=='backend' else ['node:24.21.0-bookworm-slim']
digests=(root/(role+'-bases.txt')).read_text().splitlines()
for tag,digest in zip(tags,digests):
 if '@sha256:' not in digest:raise ValueError('Base digest absent')
 text=text.replace('FROM '+tag,'FROM '+digest)
(root/(role+'.Dockerfile')).write_text(text)
PY
timeout --signal=TERM --kill-after=30s 2300 docker build --platform linux/amd64 --pull=false --network=host --file "$root/$role.Dockerfile" --tag "anvil-overnight-qa-$role:c08c168" .
docker image inspect "anvil-overnight-qa-$role:c08c168" --format '{{json .}}' > "$root/$role-image.json"
touch "$root/$role.complete"
