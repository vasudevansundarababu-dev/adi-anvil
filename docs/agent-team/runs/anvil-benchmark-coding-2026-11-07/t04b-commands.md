# T04B focused Coding command record

Commands actually run from `/workspace/anvil-recovered`; reference only, not standing authority to rerun. No app/QA/cloud or paid calls. Exact source: `t04b-source.sha256`, commit `fbfcbb868256b809bae252709dccb2eef3900e66`.

## Existing regressions — 217 passed

```sh
ANVIL_ENV=local WEB_ORIGIN=http://127.0.0.1:3202 ANVIL_LIVE_PROVIDERS_ENABLED=false ANVIL_REAL_EMAIL_ENABLED=false ANVIL_BENCHMARK_ENABLED=true ANVIL_BENCHMARK_VAULT_ROOT=/workspace/anvil-recovered/.local/t04b-fresh-regression-vault ANVIL_BENCHMARK_TEST_DATABASE_URL='postgresql://anvil_migration@/anvil_benchmark?host=%2Fworkspace%2Fanvil-recovered%2F.local%2Fbm-pg-socket' DATABASE_URL='postgresql://anvil_app@/anvil_benchmark?host=%2Fworkspace%2Fanvil-recovered%2F.local%2Fbm-pg-socket' WORKER_DATABASE_URL='postgresql://anvil_worker@/anvil_benchmark?host=%2Fworkspace%2Fanvil-recovered%2F.local%2Fbm-pg-socket' services/backend/.venv/bin/python -m pytest services/backend/tests/benchmark/test_canonical_bindings.py services/backend/tests/benchmark/test_private_storage.py services/backend/tests/benchmark/test_benchmark_imports.py services/backend/tests/unit/test_checkpoint_secret_scan.py services/backend/tests/unit/test_benchmark_bundle.py services/backend/tests/unit/test_benchmark_archive.py services/backend/tests/unit/test_benchmark_stream_limits.py services/backend/tests/unit/test_benchmark_trust.py services/backend/tests/unit/test_praxis_harbor.py services/backend/tests/unit/test_praxis_executable.py services/backend/tests/unit/test_readiness_reason_codes.py services/backend/tests/unit/test_request_limits.py services/backend/tests/unit/test_benchmark_compiler.py -q
```

## Native matrix plus negatives/resources — 16 passed

```sh
ANVIL_ENV=local WEB_ORIGIN=http://127.0.0.1:3202 ANVIL_LIVE_PROVIDERS_ENABLED=false ANVIL_REAL_EMAIL_ENABLED=false ANVIL_TEST_HARBOR=1 ANVIL_HARBOR_DOCKER_HOST=unix:///workspace/anvil-recovered/.local/benchmark-docker/docker.sock services/backend/.venv/bin/python -m pytest services/backend/tests/benchmark/test_benchmark_qualification.py services/backend/tests/benchmark/test_benchmark_native_limits.py -q
```

## Adapter guards — 7 passed; Node policies — 12 passed

```sh
PYTHONPATH=/workspace/anvil-recovered/services/harbor/src .local/harbor-venv/bin/python -m unittest discover -s services/harbor/tests -q
node --test tests/provider_failure.mjs tests/readiness_catalog.mjs
```

## Format/lint and source verification

```sh
services/backend/.venv/bin/ruff check services/backend/src/anvil/benchmark_compiler.py services/backend/src/anvil/benchmark_qualification.py services/backend/tests/benchmark/test_benchmark_qualification.py services/backend/tests/benchmark/test_benchmark_native_limits.py services/harbor/src/anvil_harbor/sme.py services/harbor/tests/test_sme.py
services/backend/.venv/bin/ruff format --check services/backend/src/anvil/benchmark_compiler.py services/backend/src/anvil/benchmark_qualification.py services/backend/tests/benchmark/test_benchmark_qualification.py services/backend/tests/benchmark/test_benchmark_native_limits.py services/harbor/src/anvil_harbor/sme.py services/harbor/tests/test_sme.py
sha256sum -c docs/agent-team/runs/anvil-benchmark-coding-2026-11-07/t04b-source.sha256
git diff --check
python3 scripts/secret_scan.py
```

## Ephemeral DB recovery — no product migration changes

A top-level shell exit killed the terminal/dedicated daemon; its owned PostgreSQL tmpfs state was lost. Only the same dedicated daemon/data path and existing test container were restarted, with bridge/iptables disabled. Its new test schema/roles were created locally (no password/secret bootstrap), then existing Alembic migrations replayed to head043:

```sh
ANVIL_ENV=local WEB_ORIGIN=http://127.0.0.1:3202 MIGRATION_DATABASE_URL="postgresql://anvil_migration@/anvil_benchmark?host=/workspace/anvil-recovered/.local/bm-pg-socket" services/backend/.venv/bin/alembic -c services/backend/alembic.ini upgrade head
```

The old restored test vault was mode2770 and correctly failed owner-only checks: 22 failed/195 passed on that first retry. It was not modified or copied. A fresh owner-only root produced217/217; no source security check was relaxed. Neither `.env` nor `.local/demo-accounts.md` existed before secret scanning, so scanner did not read credential files. Raw logs, input packages, gateway tokens and private runtime directories remain ignored/local.
