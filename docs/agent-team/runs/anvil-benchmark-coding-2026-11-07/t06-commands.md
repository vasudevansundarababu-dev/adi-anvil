# T06 actual local Coding commands and results

Source `ca8c2792e849ed2c7756a08e633a73a7a5832df2`, tree `2f4fc5f2416cc3e4649ebf4899507e29bbc1fea0`. Run in `/workspace/project/adi-anvil`; locked Python3.12.14/uv and pnpm10.34.5. Historical commands, NOT future authority to pull images/use shared services/advance roles.

```sh
export ANVIL_ENV=local WEB_ORIGIN=http://127.0.0.1:3202 ANVIL_LIVE_PROVIDERS_ENABLED=false ANVIL_REAL_EMAIL_ENABLED=false LANGSMITH_TRACING=false
export ANVIL_FIXTURE_MODE=true ANVIL_BENCHMARK_ENABLED=true ANVIL_BENCHMARK_EVALUATION_ENABLED=true ANVIL_TEST_HARBOR=1
export ANVIL_BENCHMARK_VAULT_ROOT="$PWD/.local/t06-vault"
export MIGRATION_DATABASE_URL="postgresql://anvil_migration@/anvil_benchmark?host=$PWD/.local/t06/pgsocket"
export ANVIL_BENCHMARK_TEST_DATABASE_URL="$MIGRATION_DATABASE_URL"
export DATABASE_URL="postgresql://anvil_app@/anvil_benchmark?host=$PWD/.local/t06/pgsocket"
export WORKER_DATABASE_URL="postgresql://anvil_worker@/anvil_benchmark?host=$PWD/.local/t06/pgsocket"
export ANVIL_HARBOR_DOCKER_HOST="unix://$PWD/.local/benchmark-docker/docker.sock"
services/backend/.venv/bin/alembic -c services/backend/alembic.ini upgrade head
services/backend/.venv/bin/python -m pytest services/backend/tests/unit/test_benchmark_evaluation_contracts.py services/backend/tests/benchmark/test_benchmark_evaluation.py -q
services/backend/.venv/bin/python -m pytest services/backend/tests/benchmark/test_private_storage.py services/backend/tests/benchmark/test_canonical_bindings.py services/backend/tests/benchmark/test_benchmark_imports.py services/backend/tests/benchmark/test_benchmark_pipeline.py services/backend/tests/benchmark/test_benchmark_evaluation.py services/backend/tests/unit/test_benchmark_evaluation_contracts.py -k 'not real_native and not native_actor' -q
services/backend/.venv/bin/python -m pytest services/backend/tests/unit -q
PYTHONPATH="$PWD/services/harbor/src" .local/harbor-venv/bin/python -m unittest discover -s services/harbor/tests -q
node --test tests/provider_failure.mjs tests/readiness_catalog.mjs
services/backend/.venv/bin/ruff check services/backend/src/anvil/benchmark_eval*.py services/backend/src/anvil/{benchmark_api,artifacts}.py services/backend/tests/unit/test_benchmark_evaluation_contracts.py services/backend/tests/benchmark/test_benchmark_evaluation.py services/backend/alembic/versions/04{7,8,9}_*.py
services/backend/.venv/bin/ruff format --check services/backend/src/anvil/benchmark_eval*.py services/backend/src/anvil/{benchmark_api,artifacts}.py services/backend/tests/unit/test_benchmark_evaluation_contracts.py services/backend/tests/benchmark/test_benchmark_evaluation.py services/backend/alembic/versions/04{7,8,9}_*.py
services/backend/.venv/bin/python -m anvil.cli contracts
sha256sum -c docs/agent-team/runs/anvil-benchmark-coding-2026-11-07/t06-source.sha256
python3 scripts/secret_scan.py
git diff --check
```

Observed:57 focused pass=33 contracts+24 SQL/API INCLUDING2 actual native tests.136 combined backend pass includes T06 non-native/contracts;3 native tests intentionally deselected (oldT04 one+newT06 two), not skipped/passed.7 adapter/12Node/Ruff11 Python files pass. Full units **689 passed/1 FAILED**, not green: workspace_costs test46 expects current rates past declared2026-11-08T02:47:35Z expiry. Source/test byte-identical to acceptedT05. No invented rates/expiry extension/clock freeze/policy change or skipped-test workaround. Initial2 fixture-mode setup failures corrected with required local fictional flag. Existing Authlib warning remains.

## Dedicated runtime/migrations actually used

Restarted dedicated VFS root with fresh empty owner-only config/client/exec, same explicit private socket; bridge/iptables/ip-forward/ip-masq disabled. No pulls/builds/new images/Alpine probes/default/shared socket. Only approved preloaded PostgreSQL17.6/Python3.12.14 digests. image-ls initially empty, exact-digest inspect/run succeeded; no downloads to resolve it.

```sh
sudo -n dockerd --config-file="$PWD/.local/t06/daemon.json" --data-root="$PWD/.local/benchmark-docker/data" --exec-root="$PWD/.local/t06/docker-exec" --pidfile="$PWD/.local/t06/dockerd.pid" --host="unix://$PWD/.local/benchmark-docker/docker.sock" --bridge=none --iptables=false --ip6tables=false --ip-forward=false --ip-masq=false --storage-driver=vfs
MIGRATION_DATABASE_URL="postgresql://anvil_migration@/anvil_benchmark?host=$PWD/.local/t06/pg-fresh-socket" services/backend/.venv/bin/alembic -c services/backend/alembic.ini upgrade head
```

Daemon actually started background/log-redirected. Fresh main and independent fresh049 PostgreSQL containers: pullnever/networknone/readonly/UID10001/capsALLdropped/no-new-privileges/1CPU/1GiB/128pids,512MiB PGDATA+32MiB tmp tmpfs, only respective fresh0700 Unix socket bind. No ports; listen_addresses empty/unix_socket_permissions0700; passwordless private local trust, no credentials copied. Test-only app/worker roles NOSUPERUSER/NOBYPASSRLS/NOCREATEROLE/NOCREATEDB, no passwords. Tests explicitly SETROLE existingNOLOGIN evaluator in this isolated database; no service credential bootstrap or deployed auth changes.

Actual046→047→048→049/repeat and independent fresh001→049/repeat verified in alembic_version and schema_versions. Independent freshDB stopped/retained; main remains running to retain ephemeral fictional SQL evidence. Startup shell soft timeouts are recorded; independent SQL heads/retained states verified before pass claim. No old database/trial reuse or vault permission changes.

Native adapter uses exact preloaded pinned Python/no build/delete; fresh root/name each time, UID10001/readonly/networknone/1CPU/256MiB/32pids, only installed code RO bind, job via bounded stdin. Actual probes deny actor/vault/socket/DB credentials/metadata egress/writable evaluator. Real actor5+5 output stopped before hash-equal seal and distinct evaluator; private report persisted.7 evaluator+3 actor containers stopped/retained. No provider/judge credentials or calls.

No mocks in new T06 tests; SQL/auth API/process/filesystem/Docker real. T05 vendor-boundary SDK mocks remain offline. Numeric/paraphrase calibration is NOT SME semantic agreement. SemanticBlocked, malformedReviewRequired/no candidate0. Private job report is NOT T08 suite score/T07 admission. Unreviewed arbitrary imported code inert.

STOP human review. T06 reviewable/focused passed; full units retain1 baseline failure. No T07 onward/QA/full acceptance/paid/merge/deploy/Praxis/Mac/shared/auth changes. Raw logs/private test inputs ignored; summaries/hash evidence only committed.
