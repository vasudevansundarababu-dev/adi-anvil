# Independent security successor verification

Candidate: `aad39e35ace64c55476f5e29400287a71e99d92a`. Executed November 9, 2026 UTC (November 8 Central), using isolated patched backend/Harbor/web environments. No product changes, paid calls, cloud actions or deployment were performed by Testing. Root and isolated backend source hashes remained unchanged throughout all captured commands; see `qa-aad39e3-source.json` and individual JSON receipts.

| Check | Actual result |
| --- | --- |
| Backend unit suite | 793 passed, 1 warning |
| Fresh separate benchmark SQL suite, schema058 | 168 passed, 28 explicitly skipped native cases |
| Fresh SQL/graph integration suite | Initial 189 passed, 1 failed, 19 explicitly skipped cases; failure was missing macOS `sysctl` in the private test PATH |
| Exact affected integration test after setup correction | 1 passed after adding `/usr/sbin` to private runner PATH; no product correction or full-suite repeat |
| Patched frontend production build | Passed, built against new local API port55202 |
| Real authenticated browser journeys | 2 passed against fresh synthetic realm/data: quarantined import persistence, cross-project isolation, reload/retry token retention and changed-body/project token separation |
| Harbor adapter contract suite | 9 unittest cases passed using the patched91-package Harbor environment; mocked adapter contracts, not native qualification |
| Production dependency advisory queries | npm102 reported production nodes: zero advisories; Linux CPython3.12 backend78 pins: zero OSV matches; separate Harbor91 pins: zero OSV matches; no query errors |

The combined integration evidence covers all190 non-skipped cases, but **the initial full command did not pass**. Its failure and corrected single-test result remain separate receipts. Nineteen integration and28 benchmark skips are not passes. The previous edcc native28-pass result is historical and is not qualification of this dependency successor. Fresh Linux native qualification still requires its separate approved runtime and execution.

## Preserved setup failures and limitations

- Private PATH initially omitted `/usr/sbin`; the inventory test raised `FileNotFoundError: sysctl`. The first correction attempt ran without local TCP permission and failed before application assertions; the authorized local TCP repeat passed. No test guard was weakened.
- Fresh graph readiness initially used malformed diagnostic Cypher (`RETURN count(n) n`); corrected only the private setup script to `RETURN count(n) AS n`, then verified the new graph empty. No product or old graph changes.
- A closed loopback connection initially prevented the private socket availability probe; no listener existed. Normal socket reuse enabled the availability check. Services subsequently listened only on their new loopback ports.
- The preview launcher incorrectly checked `/health`; actual endpoint is `/api/v1/health`. Services had already started normally, and the real browser tests passed against them. The launcher timeout is retained as setup evidence; it did not justify another service start.
- Harbor environment intentionally has no pytest. The first optional adapter invocation therefore failed before collection. Standard-library unittest then needed the explicit adapter source `PYTHONPATH`; after that private runner setup correction, all9 cases passed. No installation was made.
- During old realm shape inspection, a single-line old **synthetic test** realm JSON was accidentally included in tool output and therefore entered the tool/model conversation context. Root was informed. These were generated test credentials, not real account credentials; all new services use unrelated fresh synthetic credentials. The values are not repeated here, and private secrets are excluded from versioned evidence.
- The earlier baseline advisory check unexpectedly downloaded Corepack's pinned pnpm into its fresh private cache. That deviation remains documented in the historical report. This successor check reused that already present direct executable; no tool/dependency download or installation occurred during the advisory queries.

Advisories are version/database observations, not proof of runtime exploitability or blanket security. No container image/OS vulnerability scan ran; no scanning API was enabled. Authlib deprecation and expected database notifications remain warnings, not hidden failures.

## Actual new local preview

URL: `http://127.0.0.1:55203`; API: `http://127.0.0.1:55202`. This is an isolated **local synthetic test preview**, not staging or a deployment. New Keycloak realm, PostgreSQL databases, graph, volumes and private artifact/vault roots were created independently. All images were exact already-loaded reviewed pins with `--pull=never`, all network bindings loopback-only. No historical preview, Praxis service, global role, watermark or original checkout was changed.

Owned containers: `anvil-codex-aad-pg-20261109`(55197), `anvil-codex-aad-roleprobe-20261109`(55198), `anvil-codex-aad-graph-20261109`(55199/55200), `anvil-codex-aad-oidc-20261109`(55201). Each has its own data volume; Keycloak has a separate owned config volume. New API/web PIDs are48975/48976. Generated credentials and exact runtime state remain private under `/private/tmp/anvil-aad-runtime-e2ff0994be1f476f8059b3600e27e38d`, never in these receipts. Source-review duties were synthetic browser prerequisites; no source-rights approval, evaluator qualification, comparison admission or paid execution was invented.

Fresh authenticated screenshot: `artifacts/test-runs/benchmark-workspace-aad39e3.png`, captured `2026-11-09T03:24:17Z`, SHA256 `eb8231d42bcb85b96478678c84f0043ac2326f9f4432eac9f0766db3027e1fae`,173908bytes. Visually inspected: actual Anvil Benchmarks workspace, clearly fictional3-task quarantine, unsigned receipt, disabled build and explicit paid-call restriction; no passwords/tokens visible. Historical screenshot remains untouched.

Root will decide whether to retain this clearly labeled preview or stop/remove **only** these owned new processes, containers and volumes after evidence export. No cleanup of old services is authorized or necessary.

## Evidence

`qa-aad39e3-{units,integration,integration-sysctl-correction,integration-sysctl-correction-tcp,benchmark,web-build,browser,harbor-adapter,harbor-adapter-unittest,harbor-adapter-configured,advisories,source}.json` preserve command/source binding, timestamps, actual exits, raw private log hashes and explicit skips. Advisory receipt records all reviewed lock hashes and public-query provenance. Raw logs remain owner-only outside Git.
