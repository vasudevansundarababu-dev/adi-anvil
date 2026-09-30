# ANV-BF-001 handoff — 29 September 2026

The scoped TaskProfile → recommendation → Suite draft path is implemented and locally
verified. The overall Benchmark Factory specification remains partial. The user
explicitly chose this increment before the undefined GEO/intent-gap cases and
authorized catalog metadata in the existing resource/revision registry.

## Contract and requirement evidence

[Implementation contract](../build/ANV-BF-001-implementation-contract.md).

| Requirement | Evidence and limits |
| --- | --- |
| ANV-TP-001 | One or selected published task revisions under an approved objective. TaskBank entities remain later work. |
| ANV-TP-002–003 | Fourteen required dimensions, normalized values, inference confidence/evidence and explicit human confirmation. Defaults are provisional. |
| ANV-TP-004 | Immutable stored revisions; recommendations pin exact profile revisions. Database mutation negative passed. |
| ANV-TP-005 | Declared domain/environment/horizon/interaction heterogeneity and segmentation advice. Not semantic clustering. |
| ANV-REC-001–003 | Current catalog versions; hard interface/output/modality/environment/locale/access/source-rights gates; exact 20/20/20/15/10/10/5 weights. Synthetic static fixture scope only. |
| ANV-REC-004 | Scores, reasons, gaps, exact-ID task coverage, pinned revisions; runtime/cost estimates explicitly unknown, so measured-estimate acceptance remains outstanding. |
| ANV-REC-005 | Threshold controls direct/composition/extension/gap advice; gaps save a prefilled draft without publication. |
| ANV-REC-006 | Bounded deterministic greedy coverage with duplicate minimization and equal evaluator metadata. Global optimal/cost-aware composition remains outstanding. |
| ANV-REC-007 | Reordered inputs and repeated snapshots match deterministically; fixed policy and catalog revision list persisted. |
| ANV-REC-008 | Override/gap rationale recorded; direct and generic Suite paths enforce compatible versions, exact task union and paired recommendation binding. |

Catalog registration is metadata only. Full BenchmarkManifest release, executable
adapter qualification and three-case smoke validation are **not implemented** here.
Existing qualified fixture execution remains separate. Interactive marketing matching
is visibly excluded and its established guarded runtime is retained.

## Exact changed paths

- `services/backend/src/anvil/factory.py`
- `services/backend/src/anvil/api.py`
- `services/backend/src/anvil/domain.py`
- `services/backend/src/anvil/schemas.py`
- `services/backend/migrations/017_benchmark_factory.sql`
- `services/backend/alembic/versions/017_benchmark_factory.py`
- `services/backend/tests/unit/test_factory.py`
- `services/backend/tests/integration/test_factory.py`
- `services/backend/tests/integration/test_api_security.py`
- `tests/migration_smoke.py`
- `tests/e2e/factory.spec.ts`
- `apps/web/src/components/BenchmarkFactory.tsx`
- `apps/web/src/components/Console.tsx`
- `apps/web/src/components/AnvilHelp.tsx`
- `contracts/openapi/anvil.json` (generated)
- `BUILD-DECISIONS.json`, `BUILD-STATUS.md`, `README.md`
- `docs/build/ANV-BF-001-implementation-contract.md`
- `docs/build/benchmark-factory-specs/Anvil_Benchmark_Factory_Nightly_Build_Contract_v1.0.md`
- `docs/build/benchmark-factory-specs/Anvil_Benchmark_Factory_Product_Technical_Spec_v1.0.md`
- `docs/build/benchmark-factory-specs/Anvil_12_Week_Synthetic_Marketing_RL_Benchmark_Spec_v1.0.md`
- `docs/runbooks/benchmark-factory.md`
- `docs/generated/ANV-BF-001-report.md`
- `docs/generated/test-matrix.md`
- `docs/generated/morning-report.md`, `docs/generated/morning-report.json`

Migration017 only expands the existing resource-kind constraint. No new service,
database, queue, role, credential, dependency or infrastructure configuration.
Supplied specification copies normalize Markdown hard breaks from trailing spaces
to equivalent backslashes so the checkpoint whitespace check passes.
Existing source ownership, access, approvals and immutable evidence are retained.
The suite schema gains optional exact benchmark/recommendation IDs and override
rationale; existing unbound suites remain compatible.

## Commands and results

- `pnpm db:migrate`: passed with local-service permission; additive017 applied.
- `pnpm check`: passed Ruff, format, Prettier, TypeScript, production webpack build
  and OpenAPI generation on final source.
- `pnpm test:unit`: **124 passed**,2.98s; existing Authlib deprecation warning.
- `pnpm test:integration`: **67 passed**,38.13s on final source and a freshly prepared
  diagnostic project. Existing Authlib/Alembic warnings are nonfatal.
- `pnpm test:e2e -- factory.spec.ts`: **1 passed**,4.8s; scoped Factory acceptance.
- `pnpm test:e2e`: **4 passed**,46.2s on final restarted code; diagnostic, Factory,
  marketing and import. Earlier complete browser regression passed46.9s.
- Fresh/repeated migrations001–017: passed using the exact command below. Retained
  isolated database `anvil_migrationcheck_ef26060f5c00`.
- `git diff --check`: passed.
- `python3 scripts/secret_scan.py`: passed for tracked files; repeated after staging
  the explicit checkpoint file set so new files are included.
- `pnpm stop`, `pnpm dev`: restarted only registered Anvil processes; web3202/API8200
  ready. No volumes removed or other applications changed.

```sh
python3 - <<'PY'
from scripts.local import env, run, PY
run([str(PY), 'tests/migration_smoke.py'], env=env())
PY
```

Initial sandbox-denied DB/Neo4j commands were rerun with local-service permission.
A new unit assertion was corrected to expect canonical dimension order. The new
outsider assertion now expects the repository's existing404. An existing repeated-run
security test used the first task row, which could be an invalid draft from a prior
run; it now selects a published fixture and retains both strict negative assertions.
An intermediate toolbar JSX error was repaired before the final successful build.
No failing final source check remains.

## Demo and evidence

Follow [the five-minute walkthrough](../runbooks/benchmark-factory.md). Sign in as
Researcher, select an approved objective/published tasks, inspect and confirm the
profile, register metadata, recommend, select a version and create a Suite draft.
Add an uncovered capability to demonstrate draft creation from gaps. Read-only
Anvil Help uses local text only. The screenshot `artifacts/test-runs/benchmark-factory.png`
was visually inspected; shared styles, required indicators and disabled blockers are
visible. Synthetic test records are retained rather than deleted.

## Remaining gates and next increment

No live model calls, real paid approvals, partner-data access, real sending, remote
publication or schedules. Paid launch remains blocked. Not run:100,000-task load,
new performance/cost measurements, real SME calibration, schema017 backup/restore,
and destructive migration rollback (unsupported under repository policy).

Scope is bounded at100 selected tasks and100 catalog versions. Oversized catalog
ranking is rejected, rather than silently truncated. The task/objective picker shows
its first100 records. Claims of production scale, real benchmark performance, Bodhium
data availability or complete release acceptance would be unsupported.

The next ordered-backlog increment is **Night2 acceptance alignment of the existing
CSV/JSONL importer**, specifically ANV-GOV-001/002 provenance classes and source-owner
lineage. Upload/mapping/validation/version publication already exist and must be
reused. Night3's pause/resume, failed-record-only retry and error export remain later
gaps. The complete new flagship benchmark specification is not satisfied by the
older marketing task alone.

Commit-ready summary: add versioned Factory metadata and deterministic matching to
Anvil's existing shell, enforce pinned Suite provenance, and verify the local path.
The local checkpoint contains only the reviewed paths above, with no remote push.
