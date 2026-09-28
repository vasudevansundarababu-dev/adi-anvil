# Anvil specification: Advanced Ingestion, Task Generation and Privacy

Status: Draft implementation specification  
Product: Anvil benchmark and evidence platform  
Depends on: Research Objective, TaskSpec v1, DatasetVersion v1, Eval Suite, Protocol, Run Console

## 1. Outcome

Anvil authors can ingest authorized source material from files, websites, databases, APIs and cloud storage; process large sources asynchronously; detect and handle sensitive information; generate or augment candidate benchmark tasks with full provenance; review them; and publish an immutable DatasetVersion that can be attached to an Eval Suite and executed from the Run Console.

The end-to-end contract is:

```text
Approved Research Objective
  → Authorized Source
  → Background Ingestion Job
  → Raw Source Artifacts
  → Extracted Records
  → PII Scan and Policy Action
  → Mapping or Task Generation
  → Candidate Task Review
  → Validated TaskSpecs
  → Immutable DatasetVersion
  → Eval Suite / Protocol / Run Console
```

## 2. Product principles

1. **One ingestion pipeline, many connectors.** Every source uses the same job, provenance, validation and publication lifecycle.
2. **Raw source is not a benchmark task.** Extraction, privacy processing and task construction are explicit stages.
3. **Every output is reproducible.** Connector configuration, source version, mapping, extraction version, generation recipe, model identifier, seed and policy version are retained.
4. **No silent publication.** Generated or transformed tasks remain candidates until validation and approval gates pass.
5. **Published versions are immutable.** Refreshes create new DatasetVersions.
6. **Secrets are references, not payload fields.** Credentials must use the active repository's secret-management abstraction.
7. **Privacy precedes generation and publication.** Restricted raw data can be quarantined; unsafe data cannot reach a published task pack.

## 3. Shared domain model

### 3.1 ConnectorDefinition

```json
{
  "connector_id": "con_<id>",
  "objective_id": "obj_<id>",
  "type": "pdf|parquet|web|database|api|cloud_bucket",
  "name": "Authorized support corpus",
  "configuration": {},
  "credential_ref": "secret_<reference>",
  "status": "draft|verified|disabled",
  "created_by": "user_<id>",
  "created_at": "<timestamp>"
}
```

Connector responses and application logs must never expose credentials or secret values.

### 3.2 IngestionJob

```json
{
  "job_id": "ing_<id>",
  "connector_id": "con_<id>",
  "objective_id": "obj_<id>",
  "status": "queued|discovering|extracting|scanning|transforming|validating|ready|failed|cancelled",
  "progress": {
    "objects_discovered": 0,
    "objects_processed": 0,
    "records_extracted": 0,
    "bytes_processed": 0,
    "errors": 0
  },
  "checkpoint": {},
  "idempotency_key": "<key>",
  "started_at": "<timestamp>",
  "finished_at": null
}
```

### 3.3 SourceArtifact

```json
{
  "artifact_id": "src_<id>",
  "job_id": "ing_<id>",
  "source_uri": "<sanitized-location>",
  "media_type": "application/pdf",
  "content_sha256": "<checksum>",
  "source_version": "<etag/version-id/last-modified>",
  "retrieved_at": "<timestamp>",
  "authorization_basis": "customer_owned|licensed|public_authorized",
  "retention_class": "temporary|retained|restricted"
}
```

### 3.4 ExtractedRecord

Every extracted record contains:

- Stable internal record ID
- SourceArtifact ID
- Source locator such as page, URL fragment, database primary key, API cursor or object key
- Structured content
- Extraction method and version
- Content checksum
- Extraction warnings
- Privacy status

### 3.5 PrivacyFinding

```json
{
  "finding_id": "pii_<id>",
  "record_id": "rec_<id>",
  "category": "email|phone|address|person|financial|government_id|health|credential|custom",
  "location": {"field": "content", "start": 42, "end": 58},
  "confidence": 0.98,
  "policy_action": "allow|mask|hash|drop_field|quarantine|block",
  "detector_version": "<version>"
}
```

### 3.6 TransformationRun

Records the mapping or generation recipe, input record checksums, prompt/template version, model/provider identifier when applicable, decoding parameters, random seed, output checksums and validation summary.

### 3.7 CandidateTask

A candidate wraps TaskSpec v1 plus:

- Source record IDs and locators
- TransformationRun ID
- Candidate status: `generated`, `needs_review`, `approved`, `rejected`
- Automated quality findings
- Reviewer decision and rationale
- Similarity/deduplication result

Only approved, valid candidates may be included in a published DatasetVersion.

## 4. Shared background-job requirements

### ANV-JOB-001 — Durable execution

- Imports exceeding synchronous limits run through the repository's durable job mechanism.
- Job state survives application restarts.
- Work is divided into bounded, retryable chunks.
- A worker crash must not duplicate published records.

### ANV-JOB-002 — Idempotency and checkpoints

- Starting a job requires an idempotency key.
- Connector-specific checkpoints support resumption: page token, object key, row group, primary key cursor or API cursor.
- Reprocessing unchanged source content reuses the source checksum and does not create duplicate records.

### ANV-JOB-003 — Progress and control

- UI and API expose phase, counts, processed bytes, start time, elapsed time and recent actionable errors.
- Users can cancel a running job.
- Retrying a failed job resumes from its last safe checkpoint.

### ANV-JOB-004 — Error handling

- Transient failures use capped exponential retry.
- Permanent record-level failures are isolated and do not necessarily fail the entire job.
- Job failure reports connector, stage, sanitized error code and remediation; secrets and raw sensitive payloads are excluded.

### ANV-JOB-005 — Resource controls

- Configure maximum object size, records per chunk, concurrency, timeout and retry ceiling.
- Enforce per-workspace quotas using existing repository conventions.
- Reject decompression bombs, unsafe archive paths and unsupported encodings.

### ANV-JOB-006 — Auditability

- Audit creation, start, retry, cancellation, completion and publication.
- Record actor, connector, configuration checksum and output DatasetVersion.

## 5. Connector specifications

### 5.1 PDF import

#### ANV-PDF-001 — Acquisition

- Accept uploaded PDFs and PDFs discovered through authorized web/cloud connectors.
- Retain source checksum, filename, page count and extraction version.
- Detect encrypted, corrupt and image-only PDFs.

#### ANV-PDF-002 — Extraction

- Extract text with page boundaries and reading order.
- Preserve page number, section heading and bounding reference when available.
- Invoke OCR only when native text is unavailable or below a configurable quality threshold.
- Extract tables into structured rows when confidence is sufficient; otherwise retain them as page blocks with a warning.

#### ANV-PDF-003 — Task provenance

- Every mapped or generated task cites its contributing PDF page(s) and SourceArtifact ID.
- A reviewer can open the source page from the candidate-task view.

#### Acceptance

- A ten-page native PDF produces page-addressable records.
- An image-only page follows the OCR path and records the OCR engine/version.
- An encrypted PDF fails with an actionable, non-secret error.

### 5.2 Parquet import

#### ANV-PAR-001 — Schema discovery

- Read schema and metadata before full ingestion.
- Display fields, logical types, row count when available, partitions and representative samples.
- Allow field mapping into TaskSpec or an intermediate record schema.

#### ANV-PAR-002 — Scalable reading

- Process row groups incrementally without loading the complete file into memory.
- Support selected columns and partition filters.
- Preserve object version, row-group number and row index as provenance.

#### Acceptance

- Import a partitioned Parquet dataset using selected columns.
- Resume after a worker failure at the next safe row-group checkpoint.
- Reject incompatible mapped types with field-level errors.

### 5.3 Web import

#### ANV-WEB-001 — Authorized scope

- Require one or more explicit start URLs and an allowed-domain list.
- Respect configured authorization, robots directives and source-use policy.
- Default to the same origin; external links are not followed unless explicitly allowed.

#### ANV-WEB-002 — Safe retrieval

- Allow only `http` and `https`.
- Block loopback, link-local, private-network and cloud-metadata destinations to prevent SSRF.
- Apply redirect limits, response-size limits, rate limits, timeouts and user-agent identification.

#### ANV-WEB-003 — Content extraction

- Capture final URL, canonical URL, retrieval time, response metadata and content checksum.
- Extract primary textual content, headings, tables and relevant metadata while removing navigation and scripts.
- Store an immutable source snapshot or snapshot reference consistent with retention policy.

#### ANV-WEB-004 — Refresh

- Conditional retrieval uses ETag or Last-Modified when available.
- Changed content creates new source artifacts and may create a new DatasetVersion after review; it never mutates the previous version.

#### Acceptance

- Import an allowed three-page site and preserve URL-level provenance.
- Block a private-IP redirect.
- Refresh unchanged content without creating duplicate records.

### 5.4 Database import

#### ANV-DB-001 — Connection safety

- Use a credential reference and TLS according to workspace policy.
- Verify connections without returning secret material.
- Require a read-only account; Anvil never issues data-definition or mutation statements.

#### ANV-DB-002 — Query definition

- Support an approved `SELECT` query or table/view selection with columns and filters.
- Block multiple statements and prohibited commands.
- Apply statement timeout and maximum rows/bytes per chunk.
- Display an estimated or sampled result before starting the full job.

#### ANV-DB-003 — Incremental import

- Support a stable cursor such as monotonically increasing primary key or timestamp plus tie-breaker.
- Save the cursor checkpoint only after a chunk commits successfully.
- Preserve source system, schema, relation and primary-key locator without logging record payloads.

#### Acceptance

- A read-only query imports data in chunks and resumes after failure.
- An `UPDATE`, multi-statement query or missing stable cursor for incremental mode is rejected.

### 5.5 API import

#### ANV-API-001 — Request template

- Configure base URL, allowed paths, method, headers, non-secret parameters and credential reference.
- Initial scope supports idempotent `GET`; other methods require a later security review.
- Support cursor, page-number and link-header pagination.

#### ANV-API-002 — Reliability

- Honor rate-limit and retry headers.
- Use bounded retries with jitter for transient failures.
- Save sanitized request metadata, response checksum and pagination cursor.
- Validate response type and optionally a user-supplied JSON schema.

#### ANV-API-003 — Safety

- Apply the same destination restrictions as web import.
- Redact configured secret fields from stored responses and logs.
- Enforce maximum response and total-job size.

#### Acceptance

- Import a three-page JSON API and resume from page two after a simulated failure.
- Handle a rate-limit response without duplicate records.
- Reject an unexpected content type and identify the failing page.

### 5.6 Cloud-bucket import

#### ANV-CLD-001 — Supported source abstraction

- Use the repository's object-storage abstraction and credential references.
- Connector configuration includes provider, bucket/container, prefix and optional object pattern.
- Never persist raw access keys in the ConnectorDefinition.

#### ANV-CLD-002 — Discovery and versioning

- Enumerate objects incrementally.
- Preserve provider object version or ETag, object key, size and last-modified time.
- Apply allowlisted media types and object-size limits.
- Changed object versions produce new SourceArtifacts.

#### ANV-CLD-003 — Composition

- Route discovered PDFs, Parquet, CSV and JSONL through their respective extractors.
- Unsupported objects are reported and skipped according to configured policy.

#### Acceptance

- Import an allowed prefix containing mixed supported files.
- Re-run after one object changes and process only the changed object.
- Prevent traversal outside the configured bucket and prefix.

## 6. Task generation and augmentation

### ANV-GEN-001 — Versioned generation recipe

A recipe defines:

- Input record selection
- Target TaskSpec schema version
- Prompt/template and version
- Model/provider and immutable model identifier
- Decoding parameters and random seed where supported
- Requested number of candidates per source record
- Required metadata and provenance fields
- Automated validation and quality gates

### ANV-GEN-002 — Supported generation modes

- **Extraction:** turn explicit source questions/examples into TaskSpecs.
- **Synthesis:** create new tasks grounded in one or more source records.
- **Augmentation:** produce controlled variants by difficulty, locale, paraphrase, distractor, constraint or edge case.
- Every output declares its generation mode and parent record/task IDs.

### ANV-GEN-003 — Grounding and evidence

- Generated tasks retain source locators sufficient for reviewer verification.
- The generator must not invent a citation or source locator.
- Claims requiring source support fail validation when their evidence references are absent.

### ANV-GEN-004 — Candidate quality gates

- Validate TaskSpec schema.
- Detect exact and near duplicates against the job and target dataset.
- Check required-answer consistency when a reference is generated.
- Apply configurable length, language, toxicity, leakage and answerability checks.
- Record each check, version, result and rationale.

### ANV-GEN-005 — Human review

- Generated tasks cannot publish automatically in the initial release.
- Reviewer sees task, source evidence, privacy findings, quality findings and generation recipe.
- Reviewer can approve, reject or edit; edits create a derived candidate with lineage.
- Bulk approval is allowed only after sampling and quality-threshold policy passes.

### ANV-GEN-006 — Augmentation lineage

- Augmented tasks retain `parent_task_id`, transformation type and changed dimensions.
- Dataset reports distinguish original, extracted, synthetic and augmented counts.
- Train/eval leakage controls can keep task families or parents within a single split.

#### Acceptance

- Generate two grounded candidates from a source record and preserve recipe/evidence.
- Reject an ungrounded candidate and a near duplicate.
- Augment an approved task into two difficulty variants without losing parent lineage.
- Publish only approved candidates and report their origin distribution.

## 7. PII detection and redaction

### ANV-PII-001 — Scan points

- Scan extracted records before generation.
- Scan generated/edited TaskSpecs before approval and again before publication.
- Record detector and policy versions so a dataset can be rescanned later.

### ANV-PII-002 — Categories

Initial categories:

- Email address and phone number
- Person name and physical address
- Government identifier
- Financial account/payment data
- Health information
- Authentication credential, token or secret
- Workspace-defined patterns and dictionaries

### ANV-PII-003 — Policy actions

Policies operate by category, confidence and source classification:

- `allow`
- `mask` with typed placeholders such as `[EMAIL_1]`
- `hash` for consistent matching without retaining clear text
- `drop_field`
- `quarantine` for reviewer decision
- `block` the record or publication

Original restricted values must not be included in ordinary application logs, search indexes, generated prompts or published DatasetVersions.

### ANV-PII-004 — Consistent redaction

- Repeated values within an approved scope receive stable typed placeholders so task coherence is preserved.
- Redaction retains span-level lineage without exposing the original value to unauthorized users.
- A redacted record receives a new checksum and retains a link to the restricted source artifact.

### ANV-PII-005 — Review and override

- Reviewers see category, confidence, location and proposed action, subject to authorization.
- Overrides require reason, actor and audit event.
- Secrets and authentication credentials are always blocked and cannot be overridden into published tasks.

### ANV-PII-006 — Publication gate

- A DatasetVersion cannot publish with unresolved `quarantine` or `block` findings.
- Publication stores aggregate finding counts and policy version, not raw sensitive values.
- Rescanning a published dataset produces a compliance result; remediation creates a new DatasetVersion.

#### Acceptance

- Detect and mask an email consistently across instruction, input and reference fields.
- Quarantine a government identifier and prevent publication.
- Block an API token even when a reviewer attempts an override.
- Publish a clean dataset with privacy-policy version and aggregate counts.

## 8. API capabilities

Adapt endpoints to the active repository's conventions while preserving behavior:

```text
POST   /api/connectors
POST   /api/connectors/:connectorId/verify
POST   /api/ingestion-jobs
GET    /api/ingestion-jobs/:jobId
POST   /api/ingestion-jobs/:jobId/cancel
POST   /api/ingestion-jobs/:jobId/retry
GET    /api/ingestion-jobs/:jobId/artifacts
GET    /api/ingestion-jobs/:jobId/records
POST   /api/ingestion-jobs/:jobId/privacy-scan
POST   /api/generation-runs
GET    /api/generation-runs/:runId/candidates
POST   /api/candidate-tasks/:candidateId/decision
POST   /api/generation-runs/:runId/publish
```

All mutation endpoints use idempotency and repository-standard authorization/audit conventions.

## 9. User experience

### Platform-wide form behavior

The UI conventions in this section apply to Research Objectives, approval, Suites, Protocols, all ingestion screens, candidate review, privacy review and the Run Console.

#### ANV-UX-001 — Mandatory-field indicators

- Every mandatory field label displays `* Required` adjacent to the field name.
- Each form begins with the legend `* indicates a required field`.
- Color is supplemental and is never the only required-state indicator.
- Optional fields may display `Optional` when omission could otherwise be ambiguous.
- Dynamic required rules update the visible indicator and accessibility state immediately.

#### ANV-UX-002 — Accessible semantics

- Required controls expose native `required` where applicable and `aria-required="true"`.
- Error messages are programmatically associated with their controls.
- Invalid controls expose `aria-invalid="true"`.
- On failed submission, focus moves to an error summary that links to each invalid field; activating a link focuses the field.
- Keyboard order, focus visibility and screen-reader labels follow the active product design system.

#### ANV-UX-003 — Validation behavior

- Validate field format after blur and again on submission.
- Do not show a required error before the user has interacted with a field unless submission was attempted.
- Preserve valid user input after any validation or server error.
- Client validation mirrors the server contract, but server validation remains authoritative.
- Error copy states what is wrong and how to correct it; it does not expose implementation details.

#### ANV-UX-004 — Destructive and consequential actions

- Publish, approve, reject, cancel, retry and start-run actions have explicit labels and confirmation appropriate to consequence.
- Disabled actions show the unmet prerequisites nearby.
- The UI never relies on the help assistant to communicate a blocking requirement.

#### Required-field acceptance

- A keyboard-only user can identify all required fields, submit an incomplete form, navigate the error summary and correct the form.
- A screen reader announces the required and invalid state plus the associated correction message.
- A conditionally required database cursor field changes state visibly and programmatically when incremental mode is enabled.
- All existing Objective, Suite, Protocol and Run Console forms conform, not only new ingestion screens.

### Source setup

- Choose source type.
- Configure location and credential reference.
- Verify access.
- Preview schema/content and estimated scope.
- Confirm authorization basis and retention policy.

### Import monitor

- Current phase and progress
- Records/objects/bytes processed
- Validation, privacy and extraction warning counts
- Pause/cancel where supported
- Retry from checkpoint
- Actionable error details

### Candidate review

- Source evidence beside candidate TaskSpec
- Privacy and quality findings
- Generation lineage
- Approve, edit or reject
- Filters for unreviewed, blocked, duplicate and low-confidence candidates

### Publication

- Counts by source, origin and review status
- Unresolved-error and privacy gates
- Immutable DatasetVersion preview
- Attach to suite and configure run

### Screen-by-screen UI additions

| Screen | Required-field examples | Contextual help topics |
|---|---|---|
| Research Objective | Name, research question, success criteria | Writing measurable objectives; approval readiness |
| Objective Approval | Decision, rationale when rejected | Approval criteria; consequences of approval |
| Eval Suite | Name, DatasetVersion, evaluator selection | Dataset compatibility; evaluator coverage |
| Protocol | Sampling, repetitions, seed/model configuration | Reproducibility; protocol tradeoffs |
| Source Setup | Source type, location, authorization basis, retention class | Connector setup; credential-reference guidance |
| Field Mapping | External ID, instruction, input mapping | TaskSpec examples; mapping errors |
| Import Monitor | No editable mandatory fields | Job phases; retries; checkpoint diagnostics |
| Candidate Review | Decision; rationale for rejection/override | Evidence review; duplication; grounding |
| Privacy Review | Policy action; override reason when permitted | PII categories; masking and quarantine rules |
| Publication | Dataset name, version note where required | Readiness gates; immutability and lineage |
| Run Console | Suite, Protocol, DatasetVersion, model/provider | Compatibility, frozen versions and run failures |

## 10. Contextual Anvil Help assistant

The assistant is a shared product capability embedded in every primary screen. Its purpose is to explain Anvil concepts, guide field completion, interpret validation/import/run errors, provide safe examples and link users to the relevant product documentation.

### ANV-HELP-001 — Availability and interaction

- A consistent **Anvil Help** launcher appears on every primary screen.
- Opening it creates a side panel that does not obscure the current form or discard unsaved work.
- The panel supports keyboard operation, accessible focus management, collapse/reopen and conversation reset.
- Each screen provides two to four context-specific starter questions; free-form questions remain available.

### ANV-HELP-002 — Safe screen context

The assistant may receive:

- Current route and screen identifier
- User-visible field names, descriptions and required rules
- Current workflow stage and entity IDs the user is authorized to access
- Validation error codes and sanitized messages
- Import-job stage, progress and sanitized failure codes
- Applicable schema, policy and documentation versions

The assistant must not receive by default:

- Credentials, tokens, connection strings or secret values
- Raw uploaded files, database rows or API responses
- Unredacted PII or quarantined values
- Data from another workspace, objective or unauthorized entity

Users may deliberately select non-sensitive field content to ask about it. The UI previews exactly what will be shared before sending when selected content can contain task data.

### ANV-HELP-003 — Grounded answers

- Answers are grounded in versioned Anvil documentation, field/schema definitions, error catalog and the safe screen-context contract.
- Answers distinguish product facts from suggestions.
- Provide links that navigate to the relevant field, validation error, job event or documentation section.
- When evidence is insufficient, state the limitation and recommend the next diagnostic action; do not invent configuration or job state.

### ANV-HELP-004 — Capabilities

Initial capabilities:

- Explain the purpose of the current screen and the next workflow step.
- Explain any visible field, required rule or validation message.
- Produce a synthetic example value or minimal example file.
- Explain TaskSpec, DatasetVersion, Suite and Protocol compatibility.
- Diagnose sanitized connector/import errors and recommend safe remediation.
- Explain candidate grounding, duplication and PII findings.
- Summarize why publication or run configuration is blocked.

### ANV-HELP-005 — Action boundary

- The assistant is read-only in the initial release.
- It may draft a proposed field value, mapping or remediation plan, but the user must explicitly apply it in the primary UI.
- It cannot approve objectives/tasks, override privacy findings, save credentials, publish DatasetVersions, attach suites, cancel imports or start runs.
- Later tool-enabled actions require a preview of exact changes, explicit confirmation, authorization checks, idempotency and audit events.

### ANV-HELP-006 — Privacy, security and retention

- Apply the same workspace and entity authorization as the host screen.
- Sanitize context server-side; never rely solely on the browser to remove secrets or PII.
- Treat user questions and retrieved content as untrusted input; ignore instructions attempting to bypass authorization or policy.
- Store conversation history according to workspace retention policy and provide a reset/delete control when supported.
- Assistant telemetry records latency, grounding source IDs, feedback and sanitized error categories—not source payloads, PII or secrets.

### ANV-HELP-007 — Failure and fallback

- A help-service outage never blocks the primary Anvil workflow.
- On failure, show links to the current screen's static help and error documentation.
- Preserve unsaved form state when the assistant fails, closes or reconnects.

### ANV-HELP-008 — Quality feedback

- Users can mark an answer helpful or unhelpful and optionally select a reason.
- Track grounded-answer rate, helpfulness, escalation-to-docs, unresolved questions and latency by screen.
- Feedback must not contain raw source content unless the user explicitly includes it.

### Help-assistant acceptance scenarios

1. From Field Mapping, ask “Why is input required?” and receive a TaskSpec-grounded answer with a link that focuses the input mapping control.
2. From an API job with a sanitized `RATE_LIMITED` error, receive retry guidance without exposing authorization headers or response payloads.
3. From Privacy Review, ask why publication is blocked and receive the unresolved finding counts and policy explanation without revealing redacted values.
4. Ask the assistant to publish a dataset; it refuses to perform the action and directs the user to the primary publication control.
5. A user without access to another objective cannot retrieve its entities through the assistant.
6. Disable the help service; every host screen remains functional and offers static help.

### Help-assistant tests

- Unit tests for screen-context construction and secret/PII sanitization.
- Authorization tests for workspace and entity isolation.
- Prompt-injection tests using imported web, PDF and API content.
- Grounding tests for field definitions and error codes.
- Action-boundary tests for approval, publication, privacy override and run start.
- Accessibility tests for launcher, panel, focus restoration and keyboard navigation.
- End-to-end test on Objective, Import, Candidate Review, Privacy Review and Run Console screens.

## 11. Observability and evidence

Track per connector and job:

- Throughput, bytes and records processed
- Extraction and validation yield
- Retry/failure rate
- Duplicate rate
- PII finding and quarantine rate
- Generated candidate acceptance rate
- Cost and latency per accepted task when model generation is used
- Published DatasetVersion and downstream Run IDs
- Help usage, grounded-answer rate, user feedback and sanitized unresolved-question category

Metrics must not contain source payloads, PII or secrets.

## 12. Definition of done

- Every connector produces the shared SourceArtifact and ExtractedRecord contracts.
- Large imports resume without duplication after worker failure.
- Task generation is reproducible and fully lineage-linked.
- Privacy gates prevent restricted content from reaching published datasets.
- Published DatasetVersions remain immutable and are pinned by Suite and Run.
- Repository-standard typecheck, lint, tests and production build pass.
- Threat-focused tests cover SSRF, secret leakage, unsafe queries, path traversal and unauthorized source access.
- Every primary screen uses the shared mandatory-field and validation pattern.
- Every primary screen exposes the shared contextual Anvil Help assistant with a tested, sanitized context contract.
- The product includes a synthetic end-to-end demo; it is not represented as a Bodhium customer case.

## 13. Daily build sequence

Each increment must be independently demonstrable in roughly 2–3 focused hours.

### Increment 1 — Durable ingestion foundation

- IngestionJob state machine, idempotency and checkpoints
- Background worker adapter
- Progress API and minimal monitor
- Convert existing CSV/JSONL import to use the shared pipeline
- Add the shared required-field/error-summary components to the import flow
- Add the Anvil Help shell and screen-context interface with static grounded help

Demo: interrupt and resume a large JSONL import without duplication.

### Increment 2 — PDF and Parquet

- PDF extraction with page provenance
- Parquet schema preview and row-group processing
- Connector-specific validation and fixtures
- Add connector-specific required rules and contextual help topics

Demo: publish tasks mapped from one PDF and one Parquet source.

### Increment 3 — Web and API

- Safe HTTP retrieval foundation
- Allowed-domain policy, SSRF controls, pagination and rate-limit handling
- Immutable web/API source snapshots
- Add safe error-diagnostic context for the help assistant

Demo: refresh unchanged content without duplicate records.

### Increment 4 — Database and cloud bucket

- Read-only database query/cursor import
- Object listing/versioning and extractor routing
- Credential-reference integration
- Add conditional required fields and help for cursor/credential-reference setup

Demo: resume a database job and selectively reprocess one changed cloud object.

### Increment 5 — Task generation and augmentation

- Versioned generation recipes
- Candidate tasks, provenance, deduplication and review
- Original/synthetic/augmented lineage reporting
- Add candidate-review help grounded in evidence and quality findings

Demo: generate, review and approve grounded candidates without publishing rejected items.

### Increment 6 — Privacy and integrated publication

- PII scan stages and policy actions
- Quarantine/review/publication gates
- End-to-end hardening, audit and security tests
- Add privacy/publication help with strict redaction and action boundaries

Demo: mask allowed PII, block a secret, publish the clean version and open it in Run Console.

## 14. Implementation instruction for Codex

Use the active Anvil repository as the source of truth. Before editing, inspect its persistence, background-job, file/object storage, secrets, authorization, audit, UI, testing and deployment conventions. Extend those abstractions rather than introducing parallel infrastructure. Reuse the active design system for mandatory indicators, validation and the help panel. Implement only the current daily increment, satisfy its acceptance tests, run the repository-standard checks, and leave later connector adapters behind explicit interfaces rather than partially implemented UI.
