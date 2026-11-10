# T04D actual isolated Coding command record

Run from `/workspace/project/adi-anvil`. Final tested source 38cc1513aaee1069b69392b80566d23cb45d216a, tree 0fe379b77c4168bb905a76d1d83f13c3faa7ca30. Native launched atd5a97b5; runtime/SQL/Harbor code and exercised test function are unchanged at final source (verified diff/AST/source hashes). Commands are historical evidence, NOT standing authority to create/reuse services, pull images, invoke QA or change targets.

## Dedicated daemon and exact operator preloads

```sh
sudo -n dockerd --config-file="$PWD/.local/benchmark-docker/daemon.json" --data-root="$PWD/.local/benchmark-docker/data" --exec-root="$PWD/.local/benchmark-docker/exec" --pidfile="$PWD/.local/benchmark-docker/dockerd.pid" --host="unix://$PWD/.local/benchmark-docker/docker.sock" --bridge=none --iptables=false --ip6tables=false --ip-forward=false --ip-masq=false --storage-driver=vfs > .local/t04d/dockerd.log 2>&1 &
sudo -n /usr/bin/docker --config "$PWD/.local/benchmark-docker/client" --host "unix://$PWD/.local/benchmark-docker/docker.sock" pull postgres:17.6-bookworm@sha256:f3bd19c606e442c3d7bdfa8002e03fe260a1023351e0ea4598032022b68dd6e3
sudo -n /usr/bin/docker --config "$PWD/.local/benchmark-docker/client" --host "unix://$PWD/.local/benchmark-docker/docker.sock" pull python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e
```

Only these2 exact Docker Hub digests were pulled under actual user approval. Daemon JSON `{}` and empty client folder are fresh owner-only installation-local files, no credentials. No default socket/global config used. PostgreSQL `run` used the approved preloaded digest with `--pull never --network none --read-only --user 10001:10001 --cap-drop ALL --security-opt no-new-privileges:true --pids-limit 128 --memory 1g --memory-swap 1g --cpus 1`, fresh512MiB PGDATA tmpfs/32MiB tmp tmpfs, and only the owned Unix-socket directory bind. `PGDATA=/var/lib/postgresql/data/pgdata`, `POSTGRES_USER=anvil_migration`, `POSTGRES_DB=anvil_benchmark`, `POSTGRES_HOST_AUTH_METHOD=trust`, `-c listen_addresses= -c unix_socket_permissions=0700`. No network/ports/passwords/shared service. Full observed safe control fields in `t04d-environment.json` and `t04d-checks.json`.

## Actual private SQL targets and migrations

```sh
export ANVIL_ENV=local WEB_ORIGIN=http://127.0.0.1:3202 ANVIL_LIVE_PROVIDERS_ENABLED=false ANVIL_REAL_EMAIL_ENABLED=false ANVIL_BENCHMARK_ENABLED=true
export ANVIL_BENCHMARK_VAULT_ROOT="$PWD/.local/t04d-vault"
export MIGRATION_DATABASE_URL="postgresql://anvil_migration@/anvil_benchmark?host=$PWD/.local/bm-pg-socket"
export ANVIL_BENCHMARK_TEST_DATABASE_URL="$MIGRATION_DATABASE_URL"
export DATABASE_URL="postgresql://anvil_app@/anvil_benchmark?host=$PWD/.local/bm-pg-socket"
export WORKER_DATABASE_URL="postgresql://anvil_worker@/anvil_benchmark?host=$PWD/.local/bm-pg-socket"
export ANVIL_HARBOR_DOCKER_HOST="unix://$PWD/.local/benchmark-docker/docker.sock"
services/backend/.venv/bin/alembic -c services/backend/alembic.ini upgrade head
```

Fresh private container roles `anvil_app`/`anvil_worker` created LOGIN/NOSUPERUSER/NOBYPASSRLS/NOCREATEDB/NOCREATEROLE, with no password, only private network-disabled Unix local trust. Created empty schema `anvil` before direct Alembic, no credential-driven CLI/bootstrap. Main fresh/repeat045 then upgrade/repeat046; second owned fresh container used `.local/bm-pg-fresh046`, same roles/schema and001-through046/repeat046, verified actual head046. Second container stopped/retained via exact name, not removed. Original044/045 unchanged.

## Native and focused checks actually run

```sh
ANVIL_TEST_HARBOR=1 services/backend/.venv/bin/python -m pytest services/backend/tests/benchmark/test_benchmark_pipeline.py -k real_native -q
ANVIL_TEST_HARBOR=1 services/backend/.venv/bin/python -m pytest services/backend/tests/benchmark/test_benchmark_qualification.py -k rejects_stale -q
services/backend/.venv/bin/python -m pytest services/backend/tests/benchmark/test_canonical_bindings.py services/backend/tests/benchmark/test_private_storage.py services/backend/tests/benchmark/test_benchmark_imports.py services/backend/tests/benchmark/test_benchmark_pipeline.py services/backend/tests/unit/test_checkpoint_secret_scan.py services/backend/tests/unit/test_benchmark_bundle.py services/backend/tests/unit/test_benchmark_archive.py services/backend/tests/unit/test_benchmark_stream_limits.py services/backend/tests/unit/test_benchmark_trust.py services/backend/tests/unit/test_praxis_harbor.py services/backend/tests/unit/test_praxis_executable.py services/backend/tests/unit/test_readiness_reason_codes.py services/backend/tests/unit/test_request_limits.py services/backend/tests/unit/test_benchmark_compiler.py services/backend/tests/unit/test_benchmark_qualification_capture.py -k 'not real_native' -q
PYTHONPATH="$PWD/services/harbor/src" .local/harbor-venv/bin/python -m unittest discover -s services/harbor/tests -q
node --test tests/provider_failure.mjs tests/readiness_catalog.mjs
services/backend/.venv/bin/ruff check services/backend/src/anvil/benchmark_*.py services/backend/tests/benchmark/test_benchmark_pipeline.py services/backend/tests/unit/test_benchmark_qualification_capture.py services/backend/alembic/versions/04{4,5,6}_*.py
services/backend/.venv/bin/ruff format --check services/backend/src/anvil/benchmark_*.py services/backend/tests/benchmark/test_benchmark_pipeline.py services/backend/tests/unit/test_benchmark_qualification_capture.py services/backend/alembic/versions/04{4,5,6}_*.py
python3 scripts/secret_scan.py
git diff --check
```

Results:314 combined backend/1 native durable testcase containing9 actual Harbor trials+4 resources/3 stale negatives/7 adapter/12 Node passed. Native selectively excluded from combined count, not skipped or double-counted. Earlier2 failed SQL image/tool checks fixed046; review-lock race fixed/rechecked. No mocks, provider calls or real partner data. Raw logs/events/private receipts stay ignored; sanitized counts/source/report hashes only in versioned evidence. Docker bounded256-event sample is not a full-window audit. Long setup/event-read shell calls hit tool soft timeout; follow-up DB head/receipts/process/container states verified, no daemon reset or native retry.

## Stop boundary

All22 native containers stopped/retained; separate fresh046 PostgreSQL stopped/retained. Main private test PostgreSQL/daemon left running for ephemeral SQL evidence (only fictional test rows), no app/ports/shared service. No removal/prune/global permission changes. Human Coding review before T05–T10/QA/paid/merge/deployment; no further autonomous scope. Fresh runtime needs explicit setup authority; don't reuse stale trial sessions or infer standing pulls from this command record.
