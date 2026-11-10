# T06 pricing maintenance — actual commands and results

Tested source `b97ac8d2949811d7ec06a00b43fdc8dc391e353e`, tree `1787c39dbd33ae733a775a413e5704afc8babf5f`. Same branch/draftPR16. Only source changes vs8854f71: workspace_costs.py and its unit tests. Actual authorization append-only atd7bc624. No T07/QA/paid/merge/deploy authority.

## Official sources actually retrieved

10 curl HTTPS GETs (no credentials/inference) allHTTP200 between2026-11-08T15:25:33.904130Z and15:25:35.450801Z. Full bodies ignored.local; dated relevant rows/model IDs/context/cache/tier quotes and SHA256 in t06-pricing-sources.json. Exact command pattern:

```sh
curl --fail --silent --show-error --location --max-time 25 --output .local/t06-pricing/openai-pricing.md --write-out '%{http_code}
%{url_effective}' https://developers.openai.com/api/docs/pricing.md
```

The same bounded pattern fetched the9 other exact URLs listed in evidence. Earlier urllib Anthropic403 -> curl alternative200; search-tool quota unavailable, no reliance on snippets. All6 old exact models verified; rates unchanged. No account availability/rights/paid authorization inferred. Existing7dayTTL: verified2026-11-08T15:25:35.450801Z, expiry2026-11-15T15:25:35.450801Z. Unknown/unlisted IDs remain unavailable. Old frozen group prices not rewritten/backfilled.

## Local test environment actually used

```sh
export ANVIL_ENV=local WEB_ORIGIN=http://127.0.0.1:3202 ANVIL_LIVE_PROVIDERS_ENABLED=false ANVIL_REAL_EMAIL_ENABLED=false LANGSMITH_TRACING=false ANVIL_FIXTURE_MODE=true
export ANVIL_BENCHMARK_ENABLED=true ANVIL_BENCHMARK_EVALUATION_ENABLED=true ANVIL_TEST_HARBOR=1
export ANVIL_BENCHMARK_VAULT_ROOT="$PWD/.local/t06-pricing/vault"
export MIGRATION_DATABASE_URL="postgresql://anvil_migration@/anvil_benchmark?host=$PWD/.local/t06/pgsocket"
export ANVIL_BENCHMARK_TEST_DATABASE_URL="$MIGRATION_DATABASE_URL"
export DATABASE_URL="postgresql://anvil_app@/anvil_benchmark?host=$PWD/.local/t06/pgsocket"
export WORKER_DATABASE_URL="postgresql://anvil_worker@/anvil_benchmark?host=$PWD/.local/t06/pgsocket"
export ANVIL_HARBOR_DOCKER_HOST="unix://$PWD/.local/benchmark-docker/docker.sock"
services/backend/.venv/bin/python -m pytest services/backend/tests/unit/test_workspace_costs.py -q
services/backend/.venv/bin/python -m pytest services/backend/tests/unit -q
services/backend/.venv/bin/python -m pytest services/backend/tests/unit/test_benchmark_evaluation_contracts.py services/backend/tests/benchmark/test_benchmark_evaluation.py -q
services/backend/.venv/bin/python -m pytest services/backend/tests/benchmark/test_private_storage.py services/backend/tests/benchmark/test_canonical_bindings.py services/backend/tests/benchmark/test_benchmark_imports.py services/backend/tests/benchmark/test_benchmark_pipeline.py services/backend/tests/benchmark/test_benchmark_evaluation.py services/backend/tests/unit/test_benchmark_evaluation_contracts.py -k 'not real_native and not native_actor' -q
PYTHONPATH="$PWD/services/harbor/src" .local/harbor-venv/bin/python -m unittest discover -s services/harbor/tests -q
node --test tests/provider_failure.mjs tests/readiness_catalog.mjs
services/backend/.venv/bin/ruff check services/backend/src/anvil/workspace_costs.py services/backend/tests/unit/test_workspace_costs.py
services/backend/.venv/bin/ruff format --check services/backend/src/anvil/workspace_costs.py services/backend/tests/unit/test_workspace_costs.py
sha256sum -c docs/agent-team/runs/anvil-benchmark-coding-2026-11-07/t06-pricing-source.sha256
python3 scripts/secret_scan.py
git diff --check
```

Existing exact pinned isolated PostgreSQL17.6 and Python3.12.14 image inspected before use; no daemon restart, pulls/builds/deletion/socket permission changes/role or credential bootstrap. Fresh owned0700 vault, fresh actor/evaluator roots/names. Only main approved test database reused, not stale actor sessions. No migrations changed; old fresh/upgrade049 evidence remains historical, not fabricated as a new check.

## Results and failure chronology

- Original price failure reproduced1failed/17passed. New test-first clock/verification checks15failed/21passed before implementation. Pricing final **36passed**; actual wall-clock expiry still enforced in production; deterministic explicit fixture clock for dated assertions.
- T06 final **57passed**, INCLUDING2 real native;33contracts+24SQL/API/filesystem. Combined backend **136passed/3deselected** (old native1+T06native2 separated, not skip/pass). Adapter7/Node12/Ruff2 pass. Counts overlap; do not sum as unique tests.
- Initial updated full units707passed/1FAILED unchanged T05 wrong-auth Unix BrokenPipe. Focused real-Unix3provider rerun passed/22deselected; one full workingtree rerun708passed. **Final exact committed source707passed/1FAILED same T05 test**. This is the latest result; full suite not reliably green. Earlier passes do not hide repeated failure.
- Trace fails at HTTPConnection sending unauthorized POST body before any provider callback; NativeGateway rejects wrong auth before reading body and can close first. Considered pricing/clock changes, SDK/model versions, network/daemon, stale socket path, process lifetime and request-body ordering: pricing/gateway source independent/unchanged, AF_UNIX uses fresh path, no provider callback; early rejection/body send ordering best matches actual trace/code.
- No changes to T05 gateway/test/SDK transport and no added retry/mock/skip or rerun-until-green. This is outside authorized pricing/T06 maintenance; stop for a separately approved bounded T05 fix if required. Existing Authlib deprecation remains.

Historical t06-checks/source/commands untouched, original pricing failure superseded only by actual36pricing pass and current rates verification. Full-unit gate remains failed/blocked. New maintenance4evaluator+2actor containers stopped/retained; main isolated PG running for ephemeral SQL evidence, independent fresh049 PG staysstopped. No real SME/Bodhium/model-performance/production-trust claim. Paid judgeBlocked. STOP human Coding review beforeQA/T07/paid/merge/deploy.
