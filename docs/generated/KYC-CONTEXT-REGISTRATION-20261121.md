# KYC context registration checkpoint — 21 November2026

The runtime/protected-reference release `eeaf222` is deployed and technically
qualified. The real Admin imported the revised four-task ZIP successfully into
Project7. This does not establish full benchmark admission.

## Prepared data

Private ignored directory `.local/gym-context-setup-20261120/prepared-v5/` contains
the append-only normalized context. Manifest SHA:
`5c1f08e69ffcdd8e261e04e6f3ac036c6f2393c5a2d0689f0697a9bc0c80f9ae`.
Only missing document quality defaults are added. Source v4 and original pack are
unchanged. There are200 cases,100 withheld follow-ups and200 unapproved private
expectations; offline checks keep all200 unscored. Twenty policy cells reconstruct
178 bounded chunks. None of this grants policy, rights, case or run approval.

## Resume in order

1. Restore a responsive real Admin QA tab. Last native AX state shows bindings
   loading; its Reload action fails with no frame while its screenshot shows the
   earlier import receipt. Do not assume a submitted save or repeat the import.
2. Select Project7 / task group `1d2321f4-736f-4e5e-9e41-3cbaf454ee4a`.
   Upload only v5 `actor-input.json` through the existing data-input UI. Keep all
   `private/` files out of this upload and out of Authoring. Record its genuine
   queued input ID and content hash. Expected actor hash:
   `cb15e0b441157d2ea3675a6b772806f822ec8acb9f306b173c458dd291cd90bd`.
3. First run the same tool with `--check-bundle`, pinned manifest and `--output`
   in a credential-free, network-isolated validator. Keep the complete bundle,
   especially `private/expectations.json`, outside the scheduler container. The
   validator emits a canonical registration envelope containing only actor input,
   private service scenarios, lineage and context, cryptographically tied to the
   exact original manifest. Transfer only that envelope and the reviewed code.
   Run `scripts/register_kyc_context.py --registration-input <envelope>` inside
   the existing dedicated scheduler operational context, with exact
   project/group/input/source/manifest flags and its existing scheduler connection.
   Full-bundle verification is rejected when scheduler credentials are present;
   the writer rejects any fifth file or changed artifact bytes. Never supply an owner/app
   connection or set an Admin identity in SQL. The script rejects privileged or
   mixed logins, completed jobs, stale schema/source/input and changed private
   controls. It locks the same job as generic population. A failed/ambiguous
   operation requires readback, never blind replay. The group/source pairing is
   inherited from the authenticated immutable input; scheduler gets no new group
   read privilege. Downstream binding rechecks the source.
4. Read back the new child pack, standard provision manifest and completed job.
   The registration intentionally installs no private grading expectations.
   Their pending review remains visible; no qualification label is synthesized.
5. Use the existing Golden import route for the child pack in reusable application
   workflow mode. Save the preparatory binding for the actual imported group,
   then bind the exact resolution/application-input references. Prepare native
   packages and save their returned environment/evaluator references. Never use
   the old technical-reference pack as the child dataset or guess reference IDs.
6. Present concrete scoped policy, rights and expectation decisions to the real
   Product Owner under D-SIMPLE. Single-owner self-approval must be audited by
   the application. Independent/legal review is not silently fabricated. Then
   rerun readiness against the current technical receipts, renewing qualification
   if its earliest receipt expires22 November09:21:32 Chicago.

All provider/model calls remain disabled. No new Authoring change is requested
for this Gym-side context registration. No new backend migration or runtime build
is required for the standalone registration tool; its QA execution is pending.

## Verification

`tests/ops/test_prepare_kyc_context.py` and `test_register_kyc_context.py` verify
normalization, exact lineage, tamper rejection and authority preservation.
`test_register_kyc_context_sql.py` runs only with an explicitly supplied isolated
database and a synthetic cluster marker; it verifies actual scheduler privileges,
private-control preservation, no expectation access/insertion, replay refusal,
whole-transaction rollback and revoked-Admin/owner negatives. Initial fixture setup
failed the existing authenticated-engineer trigger; corrected the synthetic
fixture identity rather than changing any production guard.

Initial result:37 passed in4.49s. After separating validation from scheduler input,
40 passed in5.32s, including5 actual SQL tests. Ruff and `git diff --check` passed. Actual v5 bundle passes
registrar preflight; Golden source hash is unchanged. The isolated test container
is stopped and retained. Commands used the locked OpenEnv Python with
`ANVIL_ROOT=$PWD ANVIL_FIXTURE_MODE=true ANVIL_ENV=local
WEB_ORIGIN=http://127.0.0.1:3202`, all live flags false, and the explicit local
synthetic test DSN. Test command:

```sh
services/openenv/.venv/bin/python -B -m pytest \
  tests/ops/test_prepare_kyc_context.py \
  tests/ops/test_register_kyc_context.py \
  tests/ops/test_register_kyc_context_sql.py -q --tb=short
```

SQL tests are skipped when the isolated DSN is absent; a skipped run does not
replace the recorded actual PostgreSQL verification. No registrar QA execution,
final authenticated bindings save, human review approval or model trial passed.
