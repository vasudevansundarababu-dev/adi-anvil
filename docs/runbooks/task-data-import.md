# Task & Data Import — five-minute local demo

Delivered scope: the CSV/JSONL import contract and the **first daily increment** of
`advanced-ingestion-generation-privacy-spec.md`. Subsequent connectors, generation and
privacy policy processing are not implemented by this increment. No paid calls occur.

## Demo

1. Start `pnpm services:up` and `pnpm dev` if needed. Open http://127.0.0.1:3202 and
   sign in as the project's Researcher using the local account file.
2. In **Research objectives**, find an approved objective with an existing frozen suite
   and approved protocol. The prepared walkthrough project already has these. Click
   **Import tasks** on the objective card.
3. Download the **five-task synthetic example**, declare **ADI synthetic**, its original
   author/owner, authoring basis, generator/authoring version and seed or recipe identifier.
   Then select that JSONL file and click
   **Upload and preview**. The background worker reports queued/extracting progress.
   Wait for **5 received · 5 valid · 0 invalid · 0 duplicate rows**.
4. Inspect the preview. References are stored separately and never displayed as actor
   inputs. Click **Publish immutable dataset**. Publication freezes normalized data,
   source checksum, mapping, validation and version number.
5. Choose the existing suite, click **Attach exact version**, select its approved protocol
   and click **Configure run**. The Run Console preselects objective, suite, protocol and
   dataset, showing **5 imported tasks selected**. Click **Save configured run** to persist
   the immutable version binding.

This produces a **configured draft run**, not an executed evaluation. Existing fixture
answers cannot execute arbitrary imported tasks. Task/scoring qualification, reviewed
rights and an appropriate execution adapter remain required. Paid dispatch remains
unimplemented/disabled; adding an API key does not remove those gates.

## Correct a file or mapping

For CSV, map source columns into `external_id`, `instruction` and `input`, then click
**Revalidate mapping**. Input/reference cells contain JSON objects. Optional fields include
title and metadata; schema_version defaults to `1.0` for CSV. JSONL matching keys map
automatically. Both rows of a duplicate external ID are reported. Any validation error
blocks publication, including errors beyond the first 20 preview rows.

Upload a corrected file while the current import is selected to target the same dataset.
Publication creates version 2; version 1 and existing run snapshots remain unchanged.
**Start a separate dataset** creates a new identity instead. **Resume an import** retrieves
the saved state after navigating away. A suite attachment is tied to its precise revision;
a suite successor needs a new attachment. Attachment does not inherit scientific approval
for the new tasks.

## Durable processing and limits

The shared PostgreSQL `anvil.jobs` queue handles all CSV/JSONL imports through a bounded
local text adapter. It commits logical 200-record chunk receipts and checkpoints together.
Source and mapping are immutable during a job; revalidation creates a fresh job revision.
Cancellation stops further chunks. Explicit retry retains the committed checkpoint and
is capped at three retries. Stale leases cannot commit progress. Publication and its
idempotency response share a transaction; a failed task insert rolls back the version.

Limits: UTF-8, 25 MiB source, 10,000 records, JSON nesting 32, CSV cells 128 KiB,
ten unfinished jobs per project, existing single worker and 60-second lease per chunk.
The current adapter **reparses the bounded source at each checkpoint**, then materializes
normalized TaskSpecs atomically at completion. It is not a streaming engine for arbitrary
large sources. Byte progress is proportional to accepted record progress. Local transient
I/O/database failures use 2s/4s lease-based backoff, at most three attempts per chunk.
Remote Retry-After handling, record-level extraction recovery and connector-specific cursors
are later adapter work. Source files remain quarantined; bounded text parsing is not a malware scan.

Only local CSV/JSONL adapters are registered (`SUPPORTED_CONNECTORS`). Future adapters
must preserve these scoped jobs, artifacts, checkpoints and publication bindings. No
partially working remote connector controls are exposed.

## Privacy, references and Help

Every new upload requires an explicit source declaration. It is immutable for that artifact
and copied into published versions, row lineage and configured run snapshots. Historical
imports without declarations stay **unclassified** and cannot be newly published; reupload
with an explicit declaration instead. Source labels are author attestations, not reviewed
rights or privacy clearance. Only explicitly declared ADI synthetic sources can publish
through this development path. Bodhium, ADI Praxis, public and licensed declarations
remain blocked until reviewed rights/privacy controls exist. Never label fictional fixtures
as partner data.

Use authorized, non-sensitive data. **Automated PII discovery/redaction is not implemented
yet.** This is a development intake path, not a privacy clearance. The raw source is a
quarantined private artifact; reference answers are separated from published actor rows.
The candidate worker database role cannot query imports or the reference table. Ingestion
uses a separately scoped transaction for the submitting active author. Audit events record
IDs, checksums and counts, not source content.

**Anvil Help** is available throughout the console. It uses bundled TaskSpec/workflow
definitions and static error guidance, with optional free-text keyword lookup. It receives
only the screen identifier; it does not read fields, entity payloads or uploads. Questions
never leave browser component memory, and Reset clears them. It cannot perform actions.
There is no model-backed help service, server conversation store or telemetry in this
increment. Its static documentation remains available independently. Feedback is session
only. This shell does not claim the later assistant's full diagnostic/grounding metrics.

Shared forms mark native required controls, expose required/invalid state, validate on
blur and submit, and focus a linked error summary. Help collapse restores focus and
preserves unsaved form values. Further screen-specific requirements ship with their
respective daily increments.

The included five-task fixture is original synthetic marketing data, not a Bodhium case,
expert-qualified benchmark or a performance result. It is distinct from the separately
authored interactive 12-week marketing task, which still lacks an Anvil runtime binding.

## Verification commands

```sh
pnpm db:migrate
pnpm test:unit
pnpm check
pnpm dev
pnpm test:e2e
pnpm test:integration
```

Run browser tests before integration tests, sequentially: the browser journey supplies
the integration fixture protocol. Stop registered app processes before the production
build because it shares the local Next.js build directory. The isolated import integration
test also verifies publication rollback, version pinning, worker reference isolation and
SIGKILL after a committed chunk followed by checkpoint recovery.
