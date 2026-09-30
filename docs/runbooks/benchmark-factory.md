# Five-minute Benchmark Factory walkthrough

ANV-BF-001 extends the existing Anvil shell and resource/revision registry. Catalog
registration is matching metadata, not a published executable benchmark or evidence
of model performance. All supported examples are original ADI synthetic fixtures.

1. Start the existing application with `pnpm dev`; sign in as Researcher through
   Keycloak. Use an existing project with an approved objective and published tasks,
   such as the diagnostic project in `artifacts/test-runs/journey.json`.
2. Open **Benchmark Factory** in project navigation. Select the approved objective
   revision and one or more published task revisions. Choose **Inspect Task Profile**.
3. Review the evidence/confidence and segmentation advice. Confirm all fourteen
   dimensions. For the built-in diagnostics, replace the unconfirmed subdomain with
   `business-diagnostics`; other defaults are provisional and require human judgment.
4. Choose **Confirm immutable profile**, then **Register selected tasks in catalog**.
   This explicit action creates metadata only; it grants no source rights or approvals.
5. Choose **Recommend benchmarks**. Inspect dimension scores, reasons, uncovered
   requirements, exact catalog versions and exclusions. Runtime/cost estimates are
   unknown. Deterministic ranking uses the weights in the supplied product spec.
6. Select a compatible catalog version, supply a rationale if overriding the top full
   match or accepting gaps, and choose **Create Suite draft**. Continue to **Suites**
   for the existing independent review/freeze flow; no protocol or run is launched.
7. To demonstrate a gap, change the profile's capabilities to `uncovered-capability`,
   reconfirm the profile and recompute recommendations. Choose **Create benchmark
   from gaps**. Inspect the saved catalog draft; it cannot be published in this increment.
8. Reload and select the saved confirmed profile to verify persistence. Open **Anvil
   Help** for static, read-only explanations; no model receives your questions or data.

Existing Suite creation still works without benchmark bindings. Factory-created
suites additionally bind exact recommendation and benchmark revisions. Server-side
qualification prevents replacing their task set with unrelated task IDs. Current
rights and source/task qualification are checked again before creating a suite.

## Verification

`pnpm db:migrate`, `pnpm check`, `pnpm test:unit`, `pnpm test:e2e`, and
`pnpm test:integration` are the native commands. Browser tests create retained
synthetic records. `pnpm test:e2e -- factory.spec.ts` tests only this path after the
existing diagnostic journey has prepared the project. Fresh schema verification:

```python
from scripts.local import env, run, PY
run([str(PY), "tests/migration_smoke.py"], env=env())
```

The migration test creates and retains a separate disposable database. It does not
reset the main database. Destructive migration downgrade remains unsupported, as in
the existing repository policy.

## Boundaries and next work

Selection and catalog scope are bounded at 100. Ranking refuses an oversized catalog;
the task/objective picker displays only its first 100 records. This is not the
100,000-task executor. Compatible static synthetic fixtures use existing execution
qualification; interactive marketing metadata is explicitly excluded from this
matching path and retains its separate approved runtime.

The composition suggestion is deterministic greedy capability coverage with duplicate
coverage minimization and identical evaluator metadata. It is not a globally optimal
cost solver; costs are unknown. Interfaces, output schema, modality, environment,
locale, access and local rights are hard compatibility gates. No hidden reference
payload is read for matching. Full BenchmarkManifest/adapter validation and three-case
smoke release, actual TaskBank entities, measured estimates and restricted partner
intake are later increments.

The imported specifications are preserved in `docs/build/benchmark-factory-specs/`.
Their embedded nightly-job prompt is source material, not a created automation or an
extension of paid/external authority. The current user authorized one ANV-BF-001
increment and extending the existing registry.
