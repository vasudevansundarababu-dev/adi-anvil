# Frontier — Administration and Data Preparation

Version: 0.3 · Review draft · 27 September 2026
Modules: F10 Administration; F02 Data Preparation

## 1. Administration scope

Admin registers research users/projects, permitted model endpoints and customer harness interfaces, evaluation/generation runners, graders, sources, secrets and budget constraints. Register closed/open models as evaluation targets or approved generators/judges; registration is not permission to train their weights or reuse outputs.

Every model/harness configuration records requested and returned version identity where available, supported operations, context/tool limits, connection, intended use, permission evidence and baseline reports. Label imported/published, ADI-executed and customer-reported reports separately. Development can show **Baseline pending** without waiving access, capability or cost checks.

Credentials stay server-side and out of exports. Saving a connection does not call a model, download weights or run a benchmark. The existing two-distinct-Admin rule carries forward for applicable activation and paid operations; a researcher explicitly starts an authorized assessment/generation operation. Budget approval binds a defined scope, not unlimited future jobs.

No student checkpoint registry, optimizer configuration, Tinker fine-tuning credentials or H100 training administration. A generic runner may need computation to simulate or evaluate; that is not a training cluster. Customer-owned execution can work through a manifest/interface without ADI obtaining weights or private credentials.

## 2. Proposed setup screens

Readiness; Models & Harnesses; Runners & Source Connections; Graders; Access & Approvals. The benchmark registry lives in Benchmarks, with links here rather than a second editable catalogue. Configuration states: Draft → Validation pending → Review pending → Active; additionally Blocked, Disabled and Retired. Exact activation/revalidation rules need review; changing secrets/capabilities invalidates affected readiness.

Checks at selected milestones and final outputs are configurable. Failed checks may stop, use bounded correction, escalate or warn where policy permits. A grader outage is not a candidate failure. Critical constraints require a reviewed blocking policy before use; unsupported deterministic guarantees are prohibited.

## 3. Data Preparation boundary

Prepare approved source records, ontologies, synthetic context and eligible existing trajectories for research. **No task import, task-bank creation or workflow-to-graph conversion here.** F03 Task Intelligence Studio receives authorized Praxis task snapshots and approved-partner case/task packs and qualifies them, not through a disguised F02 data connector. F02 may prepare permitted case exhibits/supporting records referenced by F03. Praxis owns commissioned SME authoring/content review; original educational cases cannot bypass its synthetic-only task policy.

Start with CSV, S3, GCS and bounded REST intake. Broader file/database formats remain a phased proposal. Read-only by default; no write-back or credential capture in records. Each manual or approved scheduled refresh creates a new draft, never silently replaces a published version. No schedule is actually created by this document.

Organize records by domain/ontology and research objective without making a domain-model trainer mandatory. Preserve source rights, retention, generated-vs-observed labels, locale, schema, lineage and unknown fields. Missing facts remain unknown.

## 4. Data journey and controls

1. Register source/provenance/allowed use and preview schema.
2. Import into a new versioned draft.
3. AI may suggest cleaning with before/after differences; Data Engineer approves before application. Original values remain recoverable.
4. AI may suggest ontology mappings; Data Engineer corrects and Domain Expert approves applicable mappings.
5. Generate optional synthetic domain records from approved datasets or ontology plus expert guidance; retain generator/model/configuration lineage. New task logic is requested from F03.
6. Automated checks cover every generated record; Domain Expert reviews flags and an agreed representative sample, then approves content.
7. Data Engineer publishes the reviewed version for its permitted research/learning uses. Publication never triggers export, evaluation or customer training.

One/multiple permitted teacher models can produce learning examples. Retain individual model attribution; verifier recommendations about conflicts are evidence, not consensus ground truth. Domain Expert reviews the comparison rubric and unresolved conflicts before content approval. This is source generation, not student training.

Researcher confirms family/source-related train/development/locked-test separation. Same-template variants and repeated attempts are not independent samples. Protected evaluation content and contributor identity records cannot be nominated for learning-data export. Retirement from a final-test claim never grants reuse rights.

## 5. Data states and outputs

Draft → Imported → Preparation → Review pending → Content approved → Published. Blocked and Changes requested paths preserve findings; material changes create a new version and re-open affected review. Detailed state/action ownership is a proposal.

Output: DataVersion manifest, schema, record artifacts/digests, source and generation lineage, ontology/mapping references, quality report, split/permission labels, approval evidence and intended recipients/uses. Publication is separate from pack release/disclosure.

## 6. Acceptance criteria

- F-D01: Registering a customer target does not require weights or optimizer access.
- F-D02: Same-Admin activation/paid-scope self-approval is rejected.
- F-D03: Task uploads/conversion are routed out of Data Preparation, not silently imported.
- F-D04: Cleaning preserves originals; unavailable facts are not fabricated.
- F-D05: Synthetic publication requires automated checks, applicable expert approvals and Data Engineer publication.
- F-D06: Protected tests cannot enter a learning-data export through trajectory nomination.
- F-D07: Refresh leaves existing published versions immutable.
- F-D08: A published dataset starts no evaluation, training or external delivery.

Exact parser formats, source limits, approval binding, sampling thresholds and retention remain open. No connectors or generation engines are implemented.
