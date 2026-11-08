# T05 recovery — exact Coding verification commands

Tested commit `4e64f54c368d04afcde6faa8c41cdadd9529e0d9`, whole tree `0c745b5b5f098f2f55ea066f8c4f8228913cfe6f`. Product/test/lock bytes equal repair `e0a7b5fb45dbc73c1e9d6248647a102387ea5cd8`, tree `d807b5ee4f17acdf1d8f582a356e731863ab0c66`. Recovery/publication are documentation-only, not equal whole Git trees.

## Independent locked setup actually run

```sh
umask 077
mkdir -p .local/t05-recovery
chmod 700 .local .local/t05-recovery
export UV_PYTHON_INSTALL_DIR="$PWD/.local/python" UV_CACHE_DIR="$PWD/.local/uv-cache"
uv python install 3.12.14
uv sync --project services/backend --frozen --python 3.12.14
uv venv .local/harbor-venv --python 3.12.14
uv pip sync --python .local/harbor-venv/bin/python services/harbor/requirements.lock --index-url https://pypi.org/simple
```

All installs succeeded. Both environments are workspace-local and independently locked. No global package/system interpreter/config changes. uv created an optional user-bin link; only that new exact-target link was removed. Setup log hashes in checks JSON; raw logs ignored.

## Exact environment

Each check ran with a newly constructed allowlist, without ambient credentials or external database URLs:

```text
PATH=/bin:/usr/bin:/usr/local/bin
HOME=/workspace/project/adi-anvil/.local/t05-recovery/home
TMPDIR=/workspace/project/adi-anvil/.local/t05-recovery/tmp
LANG=C.UTF-8
ANVIL_ENV=local
WEB_ORIGIN=http://127.0.0.1:3202
ANVIL_LIVE_PROVIDERS_ENABLED=false
ANVIL_REAL_EMAIL_ENABLED=false
ANVIL_FIXTURE_MODE=true
LANGSMITH_TRACING=false
ANVIL_BENCHMARK_VAULT_ROOT=/workspace/project/adi-anvil/.local/t05-recovery/vault
PYTHONDONTWRITEBYTECODE=1
```

Correct ANVIL_FIXTURE_MODE=true from first test. Fresh owner-only HOME/TMP/vault. Additional variables per command below.

## Commands actually run and outcomes

### gateway

```sh
services/backend/.venv/bin/python -m pytest services/backend/tests/unit/test_benchmark_tool_gateway.py -q
```

Exit 0: 46 passed, 1 warning in 32.30s.

Ignored raw log `.local/t05-recovery/gateway.log`, SHA256 `bc490a7fe293dc96f93b2e073471a5ac1e6aefc3b5e58a1254964a71e3ab43d2`.

### provider-loop

```sh
services/backend/.venv/bin/python -m pytest services/backend/tests/unit/test_benchmark_provider_loop.py -q
```

Exit 0: 95 passed, 1 warning in 7.19s.

Ignored raw log `.local/t05-recovery/provider-loop.log`, SHA256 `ec711bef4ce837336c9e3c2c2700c8c5a3754ed37f41e1cc46042fa64d4407d7`.

### diagnostic-1

```sh
services/backend/.venv/bin/python -m pytest services/backend/tests/unit/test_benchmark_tool_gateway.py -k 'real_unix_gateway_and_installed_harbor_host_agent_client or wrong_auth_waits_for_split_bounded_body or gateway_concurrent_duplicate or failed_unknown_gateway_response' -q
```

Exit 0: 6 passed, 40 deselected, 1 warning in 15.68s.

Ignored raw log `.local/t05-recovery/diagnostic-1.log`, SHA256 `7b14bd872041367a0d26a9183478057cda068dc452b3ed12cec0279a6d831879`.

### diagnostic-2

```sh
services/backend/.venv/bin/python -m pytest services/backend/tests/unit/test_benchmark_tool_gateway.py -k 'real_unix_gateway_and_installed_harbor_host_agent_client or wrong_auth_waits_for_split_bounded_body or gateway_concurrent_duplicate or failed_unknown_gateway_response' -q
```

Exit 0: 6 passed, 40 deselected, 1 warning in 15.92s.

Ignored raw log `.local/t05-recovery/diagnostic-2.log`, SHA256 `b2fa05afa2f7ecffe9420a6230487d6cc456538fb20ada56e27282d022774b6f`.

### diagnostic-3

```sh
services/backend/.venv/bin/python -m pytest services/backend/tests/unit/test_benchmark_tool_gateway.py -k 'real_unix_gateway_and_installed_harbor_host_agent_client or wrong_auth_waits_for_split_bounded_body or gateway_concurrent_duplicate or failed_unknown_gateway_response' -q
```

Exit 0: 6 passed, 40 deselected, 1 warning in 15.73s.

Ignored raw log `.local/t05-recovery/diagnostic-3.log`, SHA256 `52d928564923fa4ea7a1425cf0ae25e67aa2109248351723198608e4929503b1`.

### pricing-capture

```sh
services/backend/.venv/bin/python -m pytest services/backend/tests/unit/test_workspace_costs.py services/backend/tests/unit/test_benchmark_qualification_capture.py -q
```

Exit 0: 96 passed, 1 warning in 5.78s.

Ignored raw log `.local/t05-recovery/pricing-capture.log`, SHA256 `d4031aef043edb10181b6fcd7be11dce8e50960839331083f2451a7d820fe541`.

### t06-contracts

```sh
services/backend/.venv/bin/python -m pytest services/backend/tests/unit/test_benchmark_evaluation_contracts.py -q
```

Exit 0: 33 passed in 0.40s.

Ignored raw log `.local/t05-recovery/t06-contracts.log`, SHA256 `56969c1508f0e70ef82e4377fc8ecce1eaf30cf0eee2f8a9593a7705c4e00604`.

### full-unit

```sh
services/backend/.venv/bin/python -m pytest services/backend/tests/unit -q
```

Exit 0: 729 passed, 1 warning in 43.00s.

Ignored raw log `.local/t05-recovery/full-unit.log`, SHA256 `37aefacf06eeda42c9ab77d87effe40f3047cb9c22268b24bd1cc735ac48421d`.

### adapter

Additional environment: `{"PYTHONPATH": "/workspace/project/adi-anvil/services/harbor/src"}`.

```sh
.local/harbor-venv/bin/python -m unittest discover -s services/harbor/tests -q
```

Exit 0: Ran 7 tests in 0.006s; OK.

Ignored raw log `.local/t05-recovery/adapter.log`, SHA256 `5b87efe35b8cd83f177571b6bb70850542b15c4626430b4cd5a8dcb0bdb7d49e`.

### node

```sh
/usr/local/bin/node --test tests/provider_failure.mjs tests/readiness_catalog.mjs
```

Exit 0: ℹ tests 12; ℹ pass 12; ℹ fail 0; ℹ skipped 0.

Ignored raw log `.local/t05-recovery/node.log`, SHA256 `b05a5642f531a37a84d727a3031131badeeaea3b602f65dfe0fb70e08a893437`.

### ruff-check

```sh
services/backend/.venv/bin/ruff check services/backend/src/anvil/benchmark_qualification.py services/backend/tests/unit/test_benchmark_tool_gateway.py
```

Exit 0: All checks passed!.

Ignored raw log `.local/t05-recovery/ruff-check.log`, SHA256 `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18`.

### ruff-format

```sh
services/backend/.venv/bin/ruff format --check services/backend/src/anvil/benchmark_qualification.py services/backend/tests/unit/test_benchmark_tool_gateway.py
```

Exit 0: 2 files already formatted.

Ignored raw log `.local/t05-recovery/ruff-format.log`, SHA256 `3bc53bf3e981a98a34a852e175bf9b77af841edea74fca595d9aedcbaf9a4938`.

### secret-scan

```sh
services/backend/.venv/bin/python scripts/secret_scan.py
```

Exit 0: {"tracked_files_checked": 678, "findings": []}.

Ignored raw log `.local/t05-recovery/secret-scan.log`, SHA256 `410937e23300530fe77352512b744812e5833d1d73d51b27bf94f30bafb648d2`.

### diff-check

```sh
git diff --check
```

Exit 0: no output; success.

Ignored raw log `.local/t05-recovery/diff-check.log`, SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

### private-predispatch

Additional environment: `{"ANVIL_HARBOR_DOCKER_HOST": "unix:///workspace/project/adi-anvil/.local/benchmark-docker/docker.sock", "ANVIL_TEST_HARBOR": "1"}`.

```sh
services/backend/.venv/bin/python -m pytest services/backend/tests/benchmark/test_benchmark_qualification.py -k native_rejects_stale_package_or_evaluator_before_execution -q
```

Exit 0: 3 passed, 9 deselected, 1 warning in 4.23s.

Ignored raw log `.local/t05-recovery/private-predispatch.log`, SHA256 `1ef9857c169c4a6f9fecee0e7501ab9557bbadba636151f0f00852bfee116d77`.

Exactly3 predefined diagnostic rounds; every outcome retained, not retry-until-green. The40 deselected per round and9 native deselected for3negative tests are scoped selections, not skipped/passed qualification. Source inspection confirms the3 private negatives reject before any Docker command; the opt-in is not native/runtime qualification. Capture tests use manufactured receipts, not native evidence.

## Blocked/not-run commands

- T06 full57:33 contracts+24 SQL/API including2native; combinedSQL136: BLOCKED/NOT RUN as suites;33contracts separately passed. No authorized preloaded dedicated Docker/PostgreSQL runtime/image store/socket; no fresh image pull/build/load authority.
- T04 actual native9;4resource probes memory_pids/tree_timeout/stdio_overflow/stdio_timeout: BLOCKED/NOT RUN; old4resource result UNOBSERVED. Same missing prerequisite.3pre-dispatch negatives pass without Docker and are NOT native isolation.9native deselected only in that scoped command.

No native/SQL invocation, shared socket/SQLite/mock substitute, image download/build/load/substitution/Alpineprobe/delete or permission changes. No paid/provider/judge/production/QA/T07/merge/deployment. Counts overlap.

## Historical proof and interruptions

Sanitized platform excerpts with IDs/timestamps/commands are in t05-recovery-history.json. Expected old-code4failed/11passed/25deselected and separate absolute-deadline1failed/39deselected retained, plus combined-run KeyboardInterrupt and outer soft timeouts. Later3x6diagnostics/57T06/12T04/136combined/729full/96pricing-capture summaries are historical only; final full/combined observations showe0a7b5f directly. Initial working-tree results are not fresh proof. Historical shell exit0 after tail does not override failed pytest. Last4resource action has no observed result. No old raw-log hash/artifact byte-exact recovery invented. Earlier pricing/T06 failure reports remain unchanged.

## Publication

Source manifest binds tested product bytes; final documentation publication is checked for zero product diff. Portable current run SHA256SUMS covers available tracked artifacts. Missing historical local-only TAP digest stays in artifact-index as unavailable; no bytes invented. Staged secret scan and portable checksums are verified before push.
