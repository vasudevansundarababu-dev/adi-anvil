# T04C focused Coding commands — 2026-11-08

Actually run from `/workspace/project/adi-anvil` on source `c0f98b24de4aaeb8ebc72cbd4e6f8ed3eb5d4534`. Reference only, not standing authority. SQL/native remains blocked. Raw logs ignored under `.local/t04-recovery/`; hashes in `t04c-checks.json`.

```sh
export ANVIL_ENV=local WEB_ORIGIN=http://127.0.0.1:3202 ANVIL_LIVE_PROVIDERS_ENABLED=false ANVIL_REAL_EMAIL_ENABLED=false
services/backend/.venv/bin/python -m pytest services/backend/tests/unit/test_checkpoint_secret_scan.py services/backend/tests/unit/test_benchmark_bundle.py services/backend/tests/unit/test_benchmark_archive.py services/backend/tests/unit/test_benchmark_stream_limits.py services/backend/tests/unit/test_benchmark_trust.py services/backend/tests/unit/test_praxis_harbor.py services/backend/tests/unit/test_praxis_executable.py services/backend/tests/unit/test_readiness_reason_codes.py services/backend/tests/unit/test_request_limits.py services/backend/tests/unit/test_benchmark_compiler.py services/backend/tests/unit/test_benchmark_qualification_capture.py -q
PYTHONPATH="$PWD/services/harbor/src" .local/harbor-venv/bin/python -m unittest discover -s services/harbor/tests -q
node --test tests/provider_failure.mjs tests/readiness_catalog.mjs
services/backend/.venv/bin/ruff check services/backend/src/anvil/benchmark_*.py services/backend/src/anvil/harbor_api.py services/backend/tests/unit/test_benchmark_qualification_capture.py services/backend/tests/benchmark/test_benchmark_pipeline.py services/backend/alembic/versions/04{4,5}_*.py
services/backend/.venv/bin/ruff format --check services/backend/src/anvil/benchmark_*.py services/backend/src/anvil/harbor_api.py services/backend/tests/unit/test_benchmark_qualification_capture.py services/backend/tests/benchmark/test_benchmark_pipeline.py services/backend/alembic/versions/04{4,5}_*.py
services/backend/.venv/bin/python -m anvil.cli contracts
python3 scripts/secret_scan.py
git diff --check
```

233 backend (173 existing+60 new),7 adapter,12 Node passed; no final failures/skips. Not native/SQL qualification. OpenAPI uses existing CLI JSON formatting.

## Collection only — NOT execution

```sh
ANVIL_ENV=local WEB_ORIGIN=http://127.0.0.1:3202 services/backend/.venv/bin/python -m pytest services/backend/tests/benchmark/test_benchmark_pipeline.py --collect-only -q
```

21 collected, not passed. No DB URLs supplied, migrations run or Docker commands dispatched. Empty Docker/containerd stores inspected read-only. Exact missing images and next isolated setup scope: BENCHMARK-PROGRESS.md. Do not run old absolute paths/DSNs blindly.

All15 tracked approved-original files byte-compared using `git show 1b4f412:<path>`; equal. Full historical SHA256SUMS exits1 for2 unavailable excluded local-only originals, deliberately not fetched/replaced/claimed reverified. Historical source indexes are task-bound, not expected to match new product code.
