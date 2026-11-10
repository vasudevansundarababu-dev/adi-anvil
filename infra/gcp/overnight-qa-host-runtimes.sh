#!/bin/bash
set -euo pipefail
umask 077
test "$(hostname)" = anvil-overnight-qa-20261110
test "$(id -u)" = 0
root=/opt/anvil-overnight-qa
test -d "$root/source/services/backend"
test ! -e "$root/uv"
exporter=$(docker create --name anvil-qa-uv-export anvil-overnight-qa-combined:c08c168 true)
docker cp "$exporter:/usr/local/bin/uv" "$root/uv"
docker rm "$exporter"
chmod 755 "$root/uv"
chown -R anvilqa:anvilqa "$root"
runuser -u anvilqa -- env -i PATH=/usr/bin:/bin HOME=/home/anvilqa UV_CACHE_DIR="$root/uv-cache" UV_PYTHON_INSTALL_DIR="$root/python" "$root/uv" python install 3.12.14
python="$root/python/cpython-3.12.14-linux-x86_64-gnu/bin/python3.12"
test -x "$python"
runuser -u anvilqa -- env -i PATH=/usr/bin:/bin HOME=/home/anvilqa UV_CACHE_DIR="$root/uv-cache" "$root/uv" sync --frozen --no-dev --python "$python" --project "$root/source/services/backend"
runuser -u anvilqa -- env -i PATH=/usr/bin:/bin HOME=/home/anvilqa UV_CACHE_DIR="$root/uv-cache" "$root/uv" sync --frozen --python "$python" --project "$root/source/services/openenv"
runuser -u anvilqa -- "$root/uv" venv "$root/harbor" --python "$python"
runuser -u anvilqa -- env -i PATH=/usr/bin:/bin HOME=/home/anvilqa UV_CACHE_DIR="$root/uv-cache" "$root/uv" pip install --python "$root/harbor/bin/python" --requirement "$root/source/services/harbor/requirements.lock"
ln -s "$root/source/services/backend/.venv" "$root/backend"
ln -s "$root/source/services/openenv/.venv" "$root/openenv"
"$root/backend/bin/python" --version
"$root/openenv/bin/python" -c 'import importlib.metadata; assert importlib.metadata.version("openenv")=="0.12.0"'
"$root/harbor/bin/python" -c 'import importlib.metadata; assert importlib.metadata.version("harbor")=="0.25.0"'
echo QA_HOST_RUNTIMES_INSTALLED
