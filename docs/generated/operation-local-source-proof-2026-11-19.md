# Operation-local source verification

User authority: 19 November 2026, fix repeated source verification without weaker
checks, continue testing and deploy to existing QA; no live calls. Coding, QA and
DevOps scope are explicitly authorized by that request.

The previous installed control exceeded both 180 and 300 seconds while repeating
roughly 358 complete qualification scans. This change does not increase trust in
paths, timestamps, dependency version strings, fixtures or supplied hashes.

Golden software registration owns a SQL savepoint and an explicit, immutable,
connection/PID/thread/deadline-bound byte proof inside it. Full source/RECORD and
actual loader validation run at entry and again before savepoint release. Watched
file identity, ownership, permissions, link count, size, mtime, ctime and content
are compared at exit, including installed/sealed packages and Beartype. Newly
loaded modules are checked by the final full scan. Exceptions close the proof and
roll back the savepoint. No global/TTL/ambient cache or caller-selected root,
resource inventory or hash is accepted. Trusted callers must not manually commit
or start a new SQL transaction inside the proof's lexical operation.

Only physical software byte measurements are reused. Every evaluator lookup
still queries its current configuration, receipt and revocation. Actual known
cases still execute. Run admission, public `validate()` and paid paths do not
inherit this proof. `validate_software()` is an explicit nonspending entry.

Local validation on source SHA-256
`4c439e71e914ac52d016a91def303e85446a8dba1f86303ed2b7584cce7ff357`:

- 1,247 unit tests and 10 subtests passed; 4 skipped. Focused proof tests cover
  repeated batches, tampering/restored mtime/replacement/symlinks, inactive,
  foreign connection/process/thread and expired proofs, and rollback ordering.
- 90 actual PostgreSQL regressions passed with fresh/repeated schema132.
- Two additional actual PostgreSQL tests passed: final-check failure leaves no
  registration/evaluator/binding rows, and new software validation observes a
  revocation while retaining all 50 configurations and 150 known-case results.
- Ruff and diff whitespace checks passed. Read-only independent review found no
  blocking issue.

QA deployment and installed verification:

- Release `151d6fbdea701be0d1f1c02bd869456c8dbad318` deployed to the existing QA VM;
  all six application services running, zero restarts; health/workspace HTTP200.
  Schema132 unchanged; no migration run. Rollback/config/DB backup retained in
  `/var/lib/anvil-qa-v1/backups/hashproof-151d6fb`.
- All three phases passed: Core `a74fcf6e-643c-4a54-a1e5-8af306a37ad9`,
  Environments `d498d54c-41f0-4788-a127-d3d8a6f64b9e`, Evaluation
  `514be781-e187-4cc7-9928-c6ce8cb183e5`.
- Actual installed post-SDK byte-proof control: two full scans per50configuration
  batch,17.217seconds. Actual sources/loader/RECORD verified, no verifier replaced.
- Fresh isolated QA SQLv5 control passed in62.920seconds (setup17.463seconds):
  restricted private/project isolation, actual OpenEnv/MCP SQL reset,
  four-product registration/conservation/shared bindings, and checkpoint
  interruption without replay. New SQL database retained stopped; old failed
  attempts were not replayed. Control SHA-256
  `37b1738c42b83a76769bfc3635f52c1aa5e6c75a6e59271912d9ef606a1d08cc`.
- Native attempt `aca17fb8-aab5-4e7e-b9b6-9da31472e154` completed exit0,
  `observed_not_qualified`; all intent/outcome records present, no exception
  frames, cleanup complete with zero failures at189.851seconds after launch.
  Evidence SHA-256 `2ed7033c1efc6e7eff959ac7cfecf296bced4e2bd169829098d4ea97d597869b`.
  No qualification granted. Model calls authorized0; actual call countnull.
- QA boot disk expanded to120GB and ext4 grown online;118Gusable/46Gfree after
  deployment/control artifacts (50Gfree immediately after expansion).
  Existing separate120GBdata disk unchanged; persistent baseline recorded.

Remaining overall benchmark gates are separate: per-application policy-registry
and private-scoring controls, independent request-absence evidence, qualification
producer and production worker-bridge wiring, plus actual applicable project
publication/policy/rights/case reviews. This release does not complete them.

Commands: unit pytest with local fixture flags and the explicitly configured
Marketing fixture root; `services/backend/.venv/bin/python scripts/verify_gym_software.py`;
same command with `--hash-proof-only`. Evidence: `.local/qa-hash-scope-units.log`,
`.local/qa-hash-scope-sql.log`, `.local/qa-hash-proof-rollback-sql.log`.

The first unit invocation omitted the required Marketing fixture-root variable;
those fixture setup failures were corrected and the complete suite rerun. An
initial Docker invocation lacked socket access; the authorized isolated suite
subsequently passed. Neither failed invocation is counted as a pass.

The installed build profiles the real verifier after the actual SDK import hook
and requires two full scans per 50-configuration byte-proof batch. This is not a
model benchmark, legal review, private-evaluator qualification or run authority.
