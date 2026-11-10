# Independent regression and bootstrap verdict

Product/native source: `edcc0514c43ceb614b813566820ee0c2c7311463`. The reviewed integration fixture correction is test-only commit `f85b093065a17ba7481941aaec9977733e447e29`; product runtime is unchanged. All402 paths in `qa-f85b093-source.json` matched after verification; manifestSHA256 `dc1f6b553cab03abace58f60d20bbf5e9389adc2edfe59a1daf4eb02f2d8d4af`. Its only change from the edcc corpus is the ownership-correct integration test. No native rerun was needed for that unrelated test-only change.

| Actual verification | Result and binding |
| --- | --- |
| Full backend units, existing locked Python3.12 Mac environment | **793 passed**,33.17s, edcc; known Authlib warning |
| Full integration, newly migrated SQL database and empty owned graph | **190 passed,19 skipped**,101.69s, f85 tests/edcc runtime |
| Benchmark SQL/API/security, separate pristine database | **168 passed,28 skipped**,93.55s, f85 corpus/edcc runtime |
| Fresh full selected native suite, isolated Linux host | **28 passed,zero skips**,610.72s, edcc; see `native-edcc051-verdict.md` |
| Actual initial-admin bootstrap SQL contracts | **10 passed**,4.808s, frozen preparation helperSHA256 `c4d66a2a51d8bfee6c1b29ebdae0a43a8857239b7555ff211979cf9d5dc17369` |
| Separate actual evaluator-login SQL contract | **One passed**,0.252s; proposed SET-only login contract, no jobs |

The28 benchmark native skips were exercised separately by the selected Linux suite, not counted as Mac passes. The19 legacy integration skips include distinct opt-in Docker/Harbor and authentic Praxis cases; they remain explicitly unrun. Fictional software conformance is not authentic-data or model-performance acceptance. Earlier browser/build evidence belongs to the earlier source and is not relabeled as a fresh build or deployment here.

## Preserved initial failures and classification

| Initial finding | Classification and bounded resolution |
| --- | --- |
| e4 privileged Compose JSON file became root-owned0600 | Source integration defect; reviewed stdout capture fix |
|057 Compose diagnostics mixed with JSON | Source integration defect; confirmed unset PREBUILT_IMAGE_NAME warning, reviewed config-only separate streams |
|8e5 actor public inputs inherited0700/0600 from private umask | Source projection defect; reviewed exact-membership/hash validation then public leaf0555/files0444; private ancestors unchanged |
|549 evaluator work parent absent | Missing owned test-work-root prerequisite; only canonical0700 parent created |
|549 evaluator program directory0700 prevented UID10001 traversal | Confirmed targeted native source defect; reviewed immutable public program-leaf projection fix in edcc |
| Cloud full units:790 passed,three missing-Git failures | Environment prerequisite; preserved, no package install. All793 passed on existing supported Mac with Git |
| New SQL database reused older graph watermark4349 versus SQL1239 | Test-environment mismatch. Guard correctly rejected stale projection; new isolated empty graph used, old graph untouched |
| Task clone returned403 while test expected201 | Test ownership/order defect. Captured first template UUID `f7d4bb8c-8c67-4832-8314-d4d8f8398337` was the importer-owned MKT draft; unassigned researcher correctly lacked private-reference binding authority at failure time. Later tests added a link, explaining isolated rerun passes. f85 selects the exact fixture-bound draft and its importing owner, separately proves403 with a fresh synthetic unassigned identity, then preserves intended source-origin409. No product permission guard changed |
| Benchmark ordinary claim assertion saw a leftover sales_kit_prepare job | Test database contamination from legacy suite. Separate pristine benchmark database passed; ordinary-job claiming was not weakened |

All failed/diagnostic receipts remain separate. Temporary assertion-only diagnostics are explicitly distinct from exact-edcc corpus results. The fixture import creates a draft; no publishing approval was invented to satisfy the test. The fresh synthetic negative identity has no real OIDC account and is disabled after its assertion.

## Actual SQL identity proofs and limits

The ten bootstrap cases used canonical migrations001–058 on a newly owned PostgreSQL17.6 cluster. They verified exactly five intended organization/user/project/admin-membership/audit rows with bound hashes; rejection of repeated/global history and wrong schema; real app/worker privilege denial; migration-session wrapper rejection; runtime elevation/evaluator LOGIN rejection; transaction rollback after an injected SQL insert failure; and one atomic winner under concurrent bootstrap. The observer was **manufactured explicitly for SQL contracts**, not actual GCE metadata or invited identity proof. The migration wrapper case is not evaluator-login proof.

The separate evaluator-login case used actual `anvil_staging_benchmark_evaluator_login` with NOINHERIT/NOSUPER/NOBYPASS and only protected-group membership: SETtrue,INHERITfalse,ADMINfalse. Connecting with exact startup options `-c role=anvil_benchmark_evaluator` yielded CURRENT_USER `anvil_benchmark_evaluator` and SESSION_USER `anvil_staging_benchmark_evaluator_login`; the real evaluator `_identity` accepted it. Plain login did not inherit protected identity. Private-table reads, app/worker/migration role assumptions and app/worker assumption of either evaluator role were denied. Zero evaluator jobs were created. This validates the proposed SQL identity contract only, not actual operator dispatch, GCE attestation or qualification.

Exact commands, times, source/test hashes, raw-log hashes and safe observed metadata are in `qa-edcc051-units.json`, `qa-f85b093-integration-fresh.json`, `qa-f85b093-benchmark-pristine.json`, `bootstrap-sql-contract.json` and `evaluator-login-sql-contract.json`. Raw logs remain owner-only in ignored/private test directories; no credentials or private payloads are versioned.

## Cleanup and remaining gates

Both newly created bootstrap/evaluator-login SQL containers and their private volumes were removed after evidence export; absence was independently verified with a healthy Docker daemon. Their generated credential files were deleted. See `bootstrap-sql-cleanup.json` and `evaluator-login-sql-cleanup.json`. Existing local test PostgreSQL/role-probe/graph/auth/preview resources and prior failed-state databases were preserved; no Praxis, original checkout, deployed service or existing cluster global role was changed. Cloud-host/key cleanup is owned by DevOps.

No paid provider calls, authentic Praxis export, real OIDC account creation, GCE metadata proof or application deployment occurred in these SQL/regression checks. Actual new-staging identity/bootstrap observation, release/rollback and deployment authorization remain separate. Testing has finished this bounded verification and hands the evidence to root for checkpoint review.
