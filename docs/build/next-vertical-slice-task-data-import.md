# Anvil implementation contract: Task & Data Import

Status: Ready for implementation in the active Anvil repository  
Scope: One demonstrable vertical slice, sized for 2–3 focused hours  
Depends on: Approved Research Objective, Eval Suite, Protocol, Run Console

## Outcome

An Anvil author can import a CSV or JSONL file containing benchmark tasks, correct row-level problems, publish an immutable dataset version, attach that exact version to a suite, and select it in the Run Console.

The slice is complete only when an imported task can reach the existing run configuration flow. Uploading a file without producing a runnable dataset version is not complete.

## Product boundary

Anvil remains the benchmark and evidence platform. This module imports benchmark tasks and associated task inputs/reference data. It does not train or fine-tune models, deploy enterprise agents, scrape websites, generate synthetic tasks, or implement the Enterprise Agent Platform control plane.

## Primary flow

1. From an approved Research Objective, select **Import tasks**.
2. Upload one `.csv` or `.jsonl` file.
3. Map source columns to the canonical TaskSpec fields.
4. Preview parsed tasks and validation results.
5. Correct the source file or mapping and revalidate.
6. Publish the valid import as an immutable DatasetVersion.
7. Attach that DatasetVersion to an existing Eval Suite.
8. Open the existing Run Console with the objective, suite, protocol, and dataset version preselected.

## Canonical contracts

### TaskSpec v1

```json
{
  "schema_version": "1.0",
  "external_id": "support-001",
  "title": "Resolve a duplicate charge",
  "instruction": "Investigate the account and propose the next compliant action.",
  "input": {
    "customer_message": "I was charged twice.",
    "account_tier": "gold"
  },
  "reference": {
    "answer": "Confirm both transactions before initiating a reversal."
  },
  "metadata": {
    "domain": "customer-support",
    "difficulty": "medium",
    "locale": "en-US",
    "tags": ["payments", "duplicate-charge"]
  }
}
```

Required fields:

- `schema_version`
- `external_id`
- `instruction`
- `input`

Optional fields:

- `title`
- `reference`
- `metadata.domain`
- `metadata.difficulty`
- `metadata.locale`
- `metadata.tags`

`reference` supplies task data only; scoring logic remains owned by the Eval Suite and Protocol.

### DatasetVersion v1

```json
{
  "dataset_id": "ds_<stable-id>",
  "version_id": "dsv_<immutable-id>",
  "version_number": 1,
  "objective_id": "obj_<id>",
  "schema_version": "1.0",
  "status": "published",
  "source": {
    "filename": "support-tasks.jsonl",
    "media_type": "application/x-ndjson",
    "sha256": "<content-checksum>"
  },
  "counts": {
    "received": 100,
    "valid": 98,
    "invalid": 2,
    "duplicates": 0
  },
  "created_at": "<timestamp>",
  "published_at": "<timestamp>"
}
```

Publishing freezes the source checksum, normalized TaskSpecs, validation result, and version number. Subsequent imports create new versions; they never mutate a published version.

## Requirements

### ANV-IMP-001 — Entry and authorization

- **Import tasks** is available only from an approved Research Objective.
- The new dataset is permanently linked to that objective.
- Existing repository authorization conventions must be reused.

### ANV-IMP-002 — Supported sources

- Accept `.csv` and `.jsonl`.
- Reject other extensions with an actionable message.
- Enforce the repository's upload-size convention; if none exists, use 25 MB for this slice.
- Retain filename, media type, byte size, and SHA-256 checksum.

### ANV-IMP-003 — Field mapping

- JSONL keys are mapped automatically when they match TaskSpec v1.
- CSV requires mappings for `external_id`, `instruction`, and `input`.
- A CSV `input` or `reference` cell may contain JSON.
- Mapping configuration is saved with the import record for reproducibility.

### ANV-IMP-004 — Deterministic normalization

- Normalize every accepted row to TaskSpec v1.
- Generate Anvil's internal immutable task ID without replacing `external_id`.
- Preserve the raw row number and source external ID as provenance.
- The same source bytes and mapping must produce the same normalized content checksum.

### ANV-IMP-005 — Validation

- Validate the complete file before publishing.
- Report errors using `row`, `field`, `code`, and `message`.
- Required error codes: `REQUIRED`, `INVALID_TYPE`, `INVALID_JSON`, `DUPLICATE_EXTERNAL_ID`, and `UNSUPPORTED_SCHEMA_VERSION`.
- Duplicate `external_id` values within the import are blocking errors.
- Show received, valid, invalid, and duplicate counts.
- Publishing is disabled while any blocking error exists.

### ANV-IMP-006 — Preview

- Display the first 20 normalized tasks.
- Display validation errors beside their affected rows.
- Changing the mapping reruns normalization and validation without creating a DatasetVersion.

### ANV-IMP-007 — Publish immutable DatasetVersion

- Publishing creates one DatasetVersion and its TaskSpec records atomically.
- A repeated publish request with the same import idempotency key returns the original DatasetVersion.
- Store actor, timestamps, source checksum, mapping, validation summary, and objective linkage.

### ANV-IMP-008 — Suite attachment

- A published DatasetVersion can be attached to an existing Eval Suite.
- The attachment stores `version_id`, never only `dataset_id` or “latest.”
- Existing suite validation must reject draft, failed, or missing versions.

### ANV-IMP-009 — Run Console integration

- **Configure run** opens the existing Run Console with objective, suite, protocol, and DatasetVersion preselected.
- The run snapshot records the exact DatasetVersion ID and TaskSpec schema version.
- The run shows the imported task count before execution.

### ANV-IMP-010 — Auditability

- Emit repository-standard audit events for import creation, validation, publication, and suite attachment.
- Never log raw task payloads or uploaded file contents in application logs.

## Suggested API surface

Adapt names to existing repository routing conventions, but preserve these behaviors:

```text
POST   /api/research-objectives/:objectiveId/task-imports
POST   /api/task-imports/:importId/validate
GET    /api/task-imports/:importId
POST   /api/task-imports/:importId/publish
GET    /api/dataset-versions/:versionId/tasks
PUT    /api/eval-suites/:suiteId/dataset-version
```

The upload endpoint may be multipart or use the repository's existing object-storage flow. Do not introduce a second upload abstraction if one already exists.

## UI states

- Empty: accepted formats and a downloadable minimal example.
- Parsing: progress indicator and filename.
- Mapping: source column → TaskSpec field controls.
- Invalid: counts, row errors, and disabled publish action.
- Ready: valid count, checksum summary, and publish action.
- Published: immutable version number plus **Attach to suite** and **Configure run** actions.

## Acceptance scenarios

1. Import a valid five-row JSONL file, publish version 1, attach it to a suite, and reach Run Console with five tasks selected.
2. Import CSV with custom source column names, map them, and obtain the same canonical TaskSpec shape.
3. Import a file missing `instruction`; the affected row and field are identified and publishing is blocked.
4. Import duplicate `external_id` values; both row numbers are reported and publishing is blocked.
5. Publish and retry the same request; only one DatasetVersion exists.
6. Publish a corrected file to the same dataset; version 2 is created and version 1 remains unchanged.
7. Start a run with version 1 after version 2 exists; the run continues to reference version 1.

## Tests required

- Parser unit tests for valid and malformed CSV/JSONL.
- Normalization tests for mappings and nested JSON cells.
- Schema-validation tests for every required error code.
- Duplicate-detection and deterministic-checksum tests.
- Publish transaction and idempotency integration tests.
- Suite rejection test for unpublished DatasetVersions.
- Run-snapshot test proving exact-version pinning.
- One UI happy-path test from upload through Configure run.

## Definition of done

- All acceptance scenarios pass.
- Existing tests still pass.
- Typecheck, lint, test, and production build pass using repository-standard commands.
- No published object can be mutated.
- A five-task fixture is included for the demo, but it is clearly labeled synthetic and is not presented as a Bodhium case.
- The README or module documentation contains a five-minute demo path.
- No unrelated architecture or user work is rewritten.

## Explicitly out of scope

- PDF, web, database, Parquet, cloud-bucket, and API imports
- Background import jobs for very large datasets
- Task generation or augmentation
- Ontology/TNG authoring
- PII detection or redaction
- Evaluator authoring and scoring changes
- Model training or fine-tuning
- Enterprise-agent runtime, identity, RBAC, deployment, or rollback

## Implementation instruction for Codex

Before editing, inspect the active repository's domain models, persistence layer, routing, UI patterns, authorization, audit events, test conventions, and build commands. Reuse them. Treat the contracts and acceptance behavior above as normative, but adapt filenames and framework-specific structure to the repository. Implement the smallest complete vertical slice; do not create a parallel application or replace the existing Objective, Suite, Protocol, or Run Console modules.
