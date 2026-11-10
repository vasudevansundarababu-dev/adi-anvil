# T05 actual offline Coding commands

Source `bb7713fdcee6a187a99daaa04b60c8f9f8afac63`, tree `1369a0254476b7dc64d107d7205527ef9addc2be`. Actually run from `/workspace/project/adi-anvil` with locked backend Python3.12.14 and independent locked Harbor environment. Historical evidence, NOT standing authority to run future services, live APIs or advance roles.

```sh
export ANVIL_ENV=local WEB_ORIGIN=http://127.0.0.1:3202 ANVIL_LIVE_PROVIDERS_ENABLED=false ANVIL_REAL_EMAIL_ENABLED=false
services/backend/.venv/bin/python -m pytest services/backend/tests/unit/test_benchmark_provider_loop.py services/backend/tests/unit/test_benchmark_tool_gateway.py -q
services/backend/.venv/bin/python -m pytest services/backend/tests/unit/test_benchmark_provider_loop.py services/backend/tests/unit/test_benchmark_tool_gateway.py services/backend/tests/unit/test_providers.py services/backend/tests/unit/test_workspace_adapter_contracts.py services/backend/tests/unit/test_checkpoint_secret_scan.py services/backend/tests/unit/test_benchmark_bundle.py services/backend/tests/unit/test_benchmark_archive.py services/backend/tests/unit/test_benchmark_stream_limits.py services/backend/tests/unit/test_benchmark_trust.py services/backend/tests/unit/test_praxis_harbor.py services/backend/tests/unit/test_praxis_executable.py services/backend/tests/unit/test_readiness_reason_codes.py services/backend/tests/unit/test_request_limits.py services/backend/tests/unit/test_benchmark_compiler.py services/backend/tests/unit/test_benchmark_qualification_capture.py services/backend/tests/unit/test_claude_json_format.py services/backend/tests/unit/test_gemini_failure_evidence.py services/backend/tests/unit/test_provider_reconciliation_metadata.py services/backend/tests/unit/test_harbor_agents.py services/backend/tests/unit/test_harbor_cloud.py services/backend/tests/unit/test_harbor_work_directory.py -q
PYTHONPATH="$PWD/services/harbor/src" .local/harbor-venv/bin/python -m unittest discover -s services/harbor/tests -q
node --test tests/provider_failure.mjs tests/readiness_catalog.mjs
services/backend/.venv/bin/ruff check services/backend/src/anvil/benchmark_{conversation,provider_wire,tool_gateway}.py services/backend/tests/unit/test_benchmark_{provider_loop,tool_gateway}.py
services/backend/.venv/bin/ruff format --check services/backend/src/anvil/benchmark_{conversation,provider_wire,tool_gateway}.py services/backend/tests/unit/test_benchmark_{provider_loop,tool_gateway}.py
sha256sum -c docs/agent-team/runs/anvil-benchmark-coding-2026-11-07/t05-source.sha256
python3 scripts/secret_scan.py
git diff --check
```

120 new tests pass (95 wire/loop+25 real bridge).467 combined backend pass INCLUDING those120 (not an additional467);7 adapter guards and12 Node pass. Ruff5 files pass. No final failed/skipped checks. Existing Authlib deprecation warning retained.

Only the unavailable paid vendor HTTP boundary uses exact-type `httpx.MockTransport`, required by approved BM05. All three installed SDKs build/parse real native tool requests/responses, one send per inference turn. Real fictional MCP processes use the hash-pinned repo tool script via locked Python, sanitized env and exact owned PID cleanup; no model-provided program/command is executed. Real owned files/pipes/Unix sockets and installed Harbor SMEAgent host client are exercised. The host-client test uses a host session descriptor, NOT a running Harbor Docker environment. No native trial or live performance claim.

Existing providers/dispatch/Harbor/SQL/OpenAPI/locks byte-compared against62ac0ff; original15 approved artifacts equal. T05 adds only3 focused backend modules and2 unit test files. No dependency installs or API/worker/live wiring; no Docker/database/shared service started, stopped, reused or reconfigured byT05. No secrets or production trust/authority read, copied or invented.

Earlier TDD/edge failures are recorded in t05-checks.json with raw log hashes; logs remain ignored under.local/t05. Direct stdio schema enforcement, bool RPC IDs, preflight schema rejection, ordered content and raw SDK token coercions repaired. Exact Gemini optional ID semantics taken from the installed locked SDK; missing native IDs normalize locally but are not invented on the native response-ID field. Opaque signatures replay privately, no hidden-thought request.

No T06–T10, QA/full acceptance, SQL/API/browser/native-T05 or live tests executed. No paid provider/judge calls, merge or deployment. Stop for human T05 Coding review.
