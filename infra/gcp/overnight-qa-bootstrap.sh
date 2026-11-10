#!/bin/bash
# Run only on the newly created, exact approved QA VM. No provider keys.
set -euo pipefail
umask 077
test "$(hostname)" = anvil-overnight-qa-20261110
test "$(id -u)" = 0
test "$(dpkg --print-architecture)" = amd64
. /etc/os-release
test "$VERSION_CODENAME" = bookworm
receipt=/var/lib/anvil-overnight-qa/bootstrap
install -d -m 700 "$receipt"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl gnupg
install -d -m 755 /etc/apt/keyrings
curl --fail --silent --show-error --proto '=https' --tlsv1.2 https://download.docker.com/linux/debian/gpg -o "$receipt/docker.asc"
gpg --show-keys --with-colons "$receipt/docker.asc" > "$receipt/docker-key.txt"
awk -F: '$1=="fpr" {print $10}' "$receipt/docker-key.txt" | grep -qx 9DC858229FC7DD38854AE2D88D81803C0EBFCD88
install -m 644 "$receipt/docker.asc" /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/anvil-qa-docker.sources <<'EOF'
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: bookworm
Components: stable
Architectures: amd64
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update
# Record exact signed repository candidates, then install those same versions.
packages=(docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin)
pins=()
for package in "${packages[@]}"; do
  candidate=$(apt-cache policy "$package" | awk '/Candidate:/ {print $2}')
  test -n "$candidate" && test "$candidate" != '(none)'
  printf '%s=%s\n' "$package" "$candidate" >> "$receipt/package-pins.txt"
  pins+=("$package=$candidate")
done
apt-get install -y --no-install-recommends "${pins[@]}"
systemctl enable --now docker
if ! id anvilqa >/dev/null 2>&1; then useradd --uid 10001 --create-home --shell /usr/sbin/nologin anvilqa; fi
test "$(id -u anvilqa)" = 10001
install -d -o anvilqa -g anvilqa -m 700 /opt/anvil-overnight-qa
cat > /etc/systemd/system/anvil-qa-actor-docker.service <<'EOF'
[Unit]
Description=Isolated Anvil QA actor daemon
After=network.target docker.service
[Service]
Type=notify
RuntimeDirectory=anvil-qa-docker
RuntimeDirectoryMode=0750
ExecStartPre=/bin/chown root:anvilqa /run/anvil-qa-docker
ExecStartPre=/bin/sh -c '/usr/sbin/ip link show anvilqaactor0 >/dev/null 2>&1 || /usr/sbin/ip link add name anvilqaactor0 type bridge'
ExecStartPre=/usr/sbin/ip address replace 172.30.90.1/24 dev anvilqaactor0
ExecStartPre=/usr/sbin/ip link set anvilqaactor0 up
ExecStart=/usr/bin/dockerd --host=unix:///run/anvil-qa-docker/docker.sock --group=anvilqa --data-root=/var/lib/anvil-qa-actor-docker --exec-root=/run/anvil-qa-docker/exec --pidfile=/run/anvil-qa-docker/pid --containerd-namespace=anvil-qa-actor --containerd-plugins-namespace=anvil-qa-actor-plugins --bridge=anvilqaactor0 --iptables=false --ip-forward=false --ip-masq=false
Restart=no
TimeoutStartSec=90
TimeoutStopSec=120
KillMode=process
Delegate=yes
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now anvil-qa-actor-docker
docker --version > "$receipt/docker-version.txt"
docker compose version > "$receipt/compose-version.txt"
docker --host unix:///run/anvil-qa-docker/docker.sock info --format '{{json .ServerVersion}}' > "$receipt/actor-version.json"
dpkg-query -W -f='${Package}=${Version}\n' "${packages[@]}" > "$receipt/installed-packages.txt"
echo 'QA_DOCKER_BOOTSTRAP_COMPLETE'
