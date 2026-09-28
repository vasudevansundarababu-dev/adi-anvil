# ADI Anvil — MVP Database, Graph and API Contracts

Version: 1.0 · 27 September 2026 · Normative engineering draft; no migrations executed

Companion to [the build specification](14-MVP-V1-ENGINEERING-BUILD-SPEC.md). Fields and transitions below are implementation defaults. Generate OpenAPI/JSON Schemas and migrations from these definitions during the build; this Markdown is not an executable migration or a completed API.

The [Sales Kit extension](18-AUTOMATED-SALES-KIT-SPEC.md) adds its resource kind, contact/delivery/revision tables, job kinds and APIs to this v1.0 contract. It separates automatic digest preparation from approved external sending.

## 1. Common physical conventions

PostgreSQL schema `anvil`; independent `anvil_checkpoints` for LangGraph library-managed state. UUID primary keys; UTC `timestamptz`; monetary amounts integer `bigint` micro-USD (1 USD = 1,000,000), never float; weights integer basis points. JSONB is for versioned bounded contracts, not unrestricted replacement for authorization relationships. SHA-256 digests are lowercase 64-character hex over canonical JSON plus referenced artifact digests; define canonical JSON as UTF-8, sorted object keys, normalized timestamps, no NaN/Infinity. Array order is significant unless a contract explicitly sorts it. Preserve original source bytes separately.

Unless noted, project tables include `id uuid PK, org_id uuid NOT NULL, project_id uuid NOT NULL, created_at timestamptz NOT NULL, created_by uuid NOT NULL`. Mutable headers additionally have `updated_at timestamptz, row_version integer NOT NULL DEFAULT 1`. Immutable revisions have `revision integer >0, schema_version text, content_hash char(64), supersedes_id uuid NULL`. All FKs on project objects must include `(org_id, project_id, id)` against a matching unique key, preventing cross-project references even with guessed IDs. `created_by` must belong to the organization; revoked identities remain as audit subjects. Do not cascade-delete evidence on user/project deletion.

Notation: `?` nullable; `[]` typed array; `json` means a separately validated JSONB contract; enum strings are CHECK-constrained text. All listed business fields are required unless marked `?`; timestamps such as `completed_at?` are nullable until their event. Typed revision detail tables use `revision_id` as PK instead of another `id`, retaining org/project scope via composite keys. Reject unknown input fields. Foreign keys use RESTRICT except disposable join rows removed from an unsubmitted draft by an explicit transaction. Every state-changing transaction appends an audit event.

Immutable published content cannot be updated through normal app credentials; correcting it creates another revision. A mutable header tracks lifecycle/current revision separately. Rights/revocation and tombstones can block use of old revisions without altering original contents. `row_version` + HTTP ETag guard mutable edits. Content digests bind approval scope; never trust client-computed hashes.

## 2. PostgreSQL table catalog

### 2.1 Identity and project control

These identity tables are organization-scoped, not project-scoped unless specified.

| Table | Additional columns / rules |
| --- | --- |
| `organizations` | `id, name text, status active/disabled, created_at`; no multi-tenant self-signup |
| `users` | `id, org_id, issuer text, subject text, email text, display_name text, status invited/active/disabled, created_at`; unique `(issuer,subject)`; email not identity key |
| `invitations` | `id, org_id, project_id?, email, token_hash, expires_at, consumed_at?, invited_by`; roles separately validated and granted on acceptance; no plaintext token |
| `projects` | `id, org_id, name, status active/archived, retention_policy json, created_at, created_by, row_version` |
| `memberships` | `id, org_id, project_id?, user_id, role, status active/revoked, granted_by, created_at`; unique active `(org_id,project_id,user_id,role)` with NULL-safe handling; only Admin is allowed as organization-wide role |
| `sessions` | `id, org_id, user_id, token_hash UNIQUE, csrf_hash, issued_at, last_seen_at, expires_at, auth_time, revoked_at?`; no refresh/access token in browser |
| `oidc_login_attempts` | `id, state_hash UNIQUE, nonce_hash, encrypted_pkce_verifier, redirect_key, expires_at, consumed_at?`; fixed allowlisted callback, single use |

Invitation delivery is manual/local test in v1.0, not an email service. First two Admins are provisioned by an explicit one-time bootstrap command that refuses repeat execution and is audited; not through a publicly accessible endpoint. Future grants/revocations require Admin audit and security policy; granting roles cannot satisfy an already pending approval retroactively.

Operation assignments `rights_reviewer` and `release_owner` are project-scoped capabilities stored in `project_assignments(id,org_id,project_id,user_id,capability,status,assigned_by,created_at)`, with unique active user/capability. Admin grants these only to active project members; they do not create a blanket extra role. Rights reviewers must additionally be Data Engineers or Product Owners; release owners must be Product Owners or Sales. They cannot override scientific approval or separated review requirements.

### 2.2 Shared version and review registry

| Table | Additional columns / rules |
| --- | --- |
| `resources` | `kind objective/case_source/task/rubric/suite/protocol/assessment/finding/report/release/candidate/requirement/ontology, current_revision_id?, lifecycle, row_version`; target for typed references |
| `revisions` | `resource_id, revision, schema_version, content_hash, supersedes_id?, content json`; unique `(resource_id,revision)`; immutable after submission; only one matching typed detail per revision |
| `review_requests` | `subject_revision_id, review_type, assignee_id, author_id, status pending/submitted/cancelled, deadline?, decision_id?`; role/independence checked at assignment and decision |
| `review_decisions` | `request_id, subject_hash, decision approve/changes_requested/reject, rationale, evidence_ids uuid[], reviewer_id, decided_at`; unique request; immutable |
| `approvals` | `subject_revision_id, purpose scope/protocol/provider_activation/paid_scope/report_audience/release, approver_id, subject_hash, scope json, expires_at?, revoked_at?`; distinct users per required quorum; unique subject/purpose/approver/hash |
| `audit_events` | `event_seq bigint identity, actor_id?, service_actor?, action, target_id?, before_hash?, after_hash?, request_id, reason?, occurred_at`; append-only to app roles; redacted metadata; no claim of superuser-proof tamper resistance |

Typed details below reference a `revision_id` in this registry; do not make competing versions in multiple tables. Headers/current pointers are separate from immutable JSON content. Database checks plus domain service enforce kind matches. Audit is authoritative for actions, not a substitute for underlying evidence records.

### 2.3 Objectives, cases and rubric data

| Table | Additional columns / rules |
| --- | --- |
| `objective_revisions` | `revision_id PK/FK, origin adi_initiated/customer_requested, entry_type capability/benchmark, title varchar(200), hypothesis text, business_context text, benchmark_reference?, measurement_plan json, owner_user_id, visibility internal/collaborators` |
| `requirement_revisions` | `revision_id, objective_revision_id, target_capabilities text[], output_contract json, execution_boundary adi_managed/external_import, acceptance_plan json, customer_validated boolean` |
| `case_sources` | mutable header: `resource_id, partner_key text, external_case_id text, source_family_key text`; unique `(project_id,partner_key,external_case_id)` |
| `case_source_revisions` | `revision_id, source_resource_id, title, subjects text[], source_edition?, information_cutoff date?, original_manifest_artifact_id, provenance json, exposure known/unknown/controlled` |
| `readiness_items` | `source_revision_id, item_key, status available/partial/missing/not_applicable, explanation, owner_user_id?, evidence_ids uuid[], blocks_operations text[], row_version`; unique source/item_key |
| `rights_grants` | `source_revision_id, operation, destination_key?, recipient_key?, status unknown/pending/approved/revoked/expired, valid_from?, expires_at?, evidence_artifact_id?, reviewed_by?, row_version`; any wildcard scope must be explicit in reviewed evidence; no inherited permission from affiliation |
| `task_revisions` | `revision_id, source_revision_id, parent_task_revision_id?, requirement_revision_id, title, role, objective, constraints text[], mode static/tool_enabled/interactive, actor_artifact_ids uuid[], reference_artifact_ids uuid[], expected_output json, completion_rules json, rubric_revision_id, family_id, split development/calibration/protected_test, capabilities text[], enhancement_summary, validation_level original/adi_enhanced/expert_reviewed/faculty_reviewed` |
| `rubric_revisions` | `revision_id, criteria json, threshold numeric(5,2), critical_rules json, calibration_record json`; threshold 0..100, weights total 10000; criterion IDs unique; no source-code expressions |
| `capability_revisions` | `revision_id, taxonomy_key, terms json`; unique term IDs, labels/descriptions, allowed parent relations; not learned model ontology claims |
| `task_capabilities` | `task_revision_id, capability_revision_id, term_id, mapping_review_id`; unique task/ontology/term |
| `case_families` | `id, family_key, rationale, exposure, row_version`; groups near-duplicates/related cases, not just identical titles |
| `artifacts` | `object_key UNIQUE, sha256, byte_size bigint >=0, mime_type, original_filename, purpose source/actor_input/reference/candidate_output/trace/report/manifest/rights_evidence, classification actor/internal/hidden_reference/approved_delivery, scan_status quarantined/clean/rejected, status active/tombstoned, provenance json`; storage key assigned by server |
| `artifact_links` | `revision_id, artifact_id, use_role, ordinal`; unique revision/artifact/use_role; classification cannot be weakened by a link |
| `import_batches` | `manifest_hash, status validating/validated/committed/rejected, validation_errors json, committed_source_ids uuid[], idempotency_key`; same committed hash never creates a duplicate case version |

`criteria` schema: array length 1..30 of `{id:string,label:string,capability_term_ids:string[],weight_bps:int,anchors:{"0":string,"1":string,"2":string,"3":string,"4":string},evidence_required:boolean}`. Every score anchor is required and nonempty. `critical_rules` is an array of `{id,description,reference_artifact_id,validator_key?}`; validator keys come from an installed allowlist only. `calibration_record` contains reviewed example assessment IDs, agreement summary, limitations, reviewer IDs and approval reference; absent calibration blocks publication.

### 2.4 Suites, systems, runs and LangGraph

| Table | Additional columns / rules |
| --- | --- |
| `suite_revisions` | `revision_id, objective_revision_id, name, suite_type custom, planned_source_count integer, selection_method, exposure_note, membership_hash`; actual counts computed, not user entered |
| `suite_members` | `suite_revision_id, task_revision_id, ordinal`; unique suite/task; frozen revisions only; duplicate family split conflict blocks freeze |
| `candidate_revisions` | `revision_id, name, adapter_key, model_requested?, harness_version, graph_code_digest, settings json, connection_id?, provenance adi_configured/customer_supplied/partner_supplied` |
| `connections` | `id, provider_key, secret_reference?, allowed_destination_key, capabilities json, status draft/activation_pending/active/revoked, config_hash, pricing_revision?, row_version`; active requires applicable two-Admin approval; never raw key |
| `protocol_revisions` | `revision_id, objective_revision_id, suite_revision_id, candidate_revision_ids uuid[], specification json`; content binds all settings below |
| `runs` | `protocol_revision_id, origin adi_executed/customer_reported/partner_reported/illustrative, state, launch_key?, started_at?, completed_at?, cancel_requested_at?, authorization_hash?, max_cost_micro_usd, reserved_micro_usd, actual_cost_micro_usd?, cost_status not_applicable/estimated/reconciled/unknown, row_version` |
| `episodes` | `run_id, task_revision_id, candidate_revision_id, repetition int >=1, attempt int >=1, state, outcome pass/fail/invalid/unscorable/pending_review, reason_code?, started_at?, completed_at?, output_artifact_id?, trace_artifact_id?, row_version`; unique run/task/candidate/repetition/attempt |
| `provider_calls` | `episode_id, operation_key UNIQUE, dispatch_state prepared/dispatched/completed/unknown/reconciled, request_hash, provider_request_id?, model_returned?, usage json?, reserved_micro_usd, actual_micro_usd?, dispatched_at?, completed_at?, result_artifact_id?`; one submitted inference per allowed attempt |
| `agent_threads` | `episode_id UNIQUE, thread_id uuid UNIQUE, graph_version, graph_code_digest, checkpoint_namespace, last_checkpoint_id?, status active/interrupted/completed/blocked, pending_review_id?, row_version`; project authorization here precedes all saver access |
| `resume_requests` | `thread_id, review_decision_id, interrupt_key, status queued/consumed/rejected, idempotency_key`; unique thread/interrupt/decision; no arbitrary state injection |
| `jobs` | `kind import/episode/resume/project_graph/report/export, target_id, status queued/leased/succeeded/failed/cancelled/reconciliation_required, attempts, available_at, lease_owner?, lease_token uuid?, lease_until?, heartbeat_at?, error_code?, idempotency_key UNIQUE` |
| `run_events` | `run_id, episode_id?, seq bigint, kind, node_key?, payload json, occurred_at`; unique run/seq; public API gives sanitized subset only |

`protocol.specification`: `{schema_version:"1.0", task_input_hashes:object, rubric_hashes:object, model_parameters:object, harness_prompt_artifact_id:uuid, repetitions:int[1..10], step_limit:int[1..20], max_input_tokens:int>0, max_output_tokens:int>0, episode_timeout_seconds:int[1..600], concurrency:int[1..2], max_cost_micro_usd:int>=0, pricing_revision:string|null, exclusion_rules:array, reviewer_assignment:object, secondary_review_sample:{fraction:0.1,seed:string}, pass_policy:object, comparison_policy:object, exposure_policy:object, allowed_destination_key:string|null}`. Bounds are MVP engineering defaults, not scientific best practice. Static external imports declare unknown unsupported fields; they cannot pass as fully reproduced comparable runs.

LangGraph saver internal tables are owned by its pinned library and isolated in `anvil_checkpoints`; do not duplicate them in Alembic models or add guessed columns. Startup checks expected checkpoint migration version with read-only credentials; setup is a controlled migration step. Store only validated serializable state; reject arbitrary pickle or user-supplied serialized checkpoints. Anvil wrapper scopes every read/resume/delete to the `agent_threads` registry, with no user-facing generic checkpoint API.

### 2.5 Assessments, findings and release

| Table | Additional columns / rules |
| --- | --- |
| `assessment_revisions` | `revision_id, episode_id, rubric_revision_id, reviewer_user_id, dimension_scores json, critical_violations json, evidence_refs json, outcome, score numeric(5,2)?, review_round int, blinded boolean`; score computed by server; all required dimensions |
| `adjudications` | `episode_id, assessment_revision_ids uuid[], final_assessment_revision_id, adjudicator_id, rationale, decided_at`; no adjudication by either disputed reviewer; final revision is immutable |
| `finding_revisions` | `revision_id, episode_id, assessment_revision_id, category, observation text, hypothesis text?, alternatives text[], confidence low/medium/high/unknown, evidence_refs json, capability_terms text[], status draft/reviewed/disputed` |
| `report_revisions` | `revision_id, objective_revision_id, run_ids uuid[], assessment_revision_ids uuid[], finding_revision_ids uuid[], audience internal/sales/customer, recipient_key?, content json, evidence_manifest_hash, rendered_artifact_ids uuid[]`; no client-provided recomputed score |
| `release_revisions` | `revision_id, report_revision_id, recipient_key, permitted_use text, artifact_allowlist uuid[], manifest json, manifest_hash, expires_at?`; exact recipient/use and content bind approval |
| `release_downloads` | `release_revision_id, user_id, downloaded_at, request_id`; records local authorized access, not proof customer accepted it |
| `budget_reservations` | `run_id, provider_call_id?, limit_micro_usd, reserved_micro_usd, settled_micro_usd?, status reserved/settled/unknown/released, row_version`; no negative balances; unknown retains conservative reservation |

`evidence_refs`: array of `{artifact_id:uuid, locator:{type:"text_lines"|"page"|"json_pointer",start?:int,end?:int,pointer?:string},claim:string}` with type-dependent fields, in-bounds validation and authorized project artifacts. Do not accept live URLs as evidence access instructions. Span/reference checks validate existence, not factual truth.

Indexes: every project table `(org_id,project_id)`; resources `(project_id,kind,lifecycle,updated_at)`; revisions unique resource/revision and index content_hash; jobs `(status,available_at,lease_until)` partial for queued/leased; episodes `(run_id,state)`; calls `(episode_id,dispatch_state)`; audits `(project_id,event_seq)`; rights `(source_revision_id,operation,status)`; pending reviews `(assignee_id,status)`; graph outbox `(status,sequence)`; run events `(run_id,seq)`. Add migration tests for uniqueness/FKs/checks and explain plans for inventory/run pagination.

## 3. State transitions and invalidation

Status cannot be assigned through generic PATCH; transitions are service commands with role/guard/audit checks. `blocked` is a readiness reason overlay unless specifically a terminal execution state; do not hide the underlying lifecycle.

| Object | Normal path | Other paths / guard |
| --- | --- | --- |
| Objective revision | draft → submitted → recommended → approved | changes_requested/rejected → new draft revision; distinct review quorum |
| Source/task | draft → content_review → research_review → qualified → published | changes_requested; withdrawn; source rights unresolved keeps qualification blocked |
| Rubric | draft → expert_review → calibration_review → approved | changes_requested; withdrawn; no unreviewed 0–4 anchors |
| Suite | draft → review → frozen | new revision for membership/rubric change; frozen suite never edited in place |
| Protocol | draft → review → approved | affected material changes require new revision; run authorization separate |
| Run | draft → authorization_pending → ready → queued → running → review_pending → reviewed | fixture skips paid auth only; partial, cancellation_requested → cancelled; invalidated; reconciliation_required |
| Episode | planned → queued → running → output_captured → awaiting_review → finalized | pre-dispatch blocked; failed_operational; execution_unknown; cancelled; invalidated; no automatic return from unknown to queued |
| Report | draft → evidence_checked → technical_reviewed → domain_reviewed → audience_approved → approved | changes_requested; invalidated; domain-reviewed waiver only with documented no-domain-judgment rationale |
| Release | draft → reviewed → approved → building → ready | build_failed, revoked, expired; download is an audit event, not acceptance |

Protocol approval binds the set of material versions; payment approval binds run/candidate/destination/ceiling. A new rubric/source/model/prompt changes the protocol hash and requires new approvals; a typo in a nonsemantic display label does not alter frozen content but is audited on the mutable header. Withdrawal/rights revocation disables affected downloads and next provider dispatch; already completed measurements remain historical with an invalidation note. An in-flight external call may not be recallable—show that uncertainty. Never reset a consumed budget or delete findings to make a rerun look clean.

## 4. Neo4j graph contract

### 4.1 Why this recommendation

Neo4j is the proposed property-graph engine for multi-hop lineage and capability/failure exploration. This is a fit recommendation, not a benchmark claim that it is universally best. PostgreSQL alone could implement initial joins but does not meet the user's desired dedicated graph layer. Apache AGE is a PostgreSQL graph extension; it couples graph operations to the operational database and is not the chosen separation. [Neo4j driver](https://neo4j.com/docs/python-manual/current/), [Apache AGE overview](https://age.apache.org/overview/).

Defer Amazon Neptune because cloud vendor selection is not made and local development is a requirement. No need for vector search, graph neural training, GraphRAG, APOC or paid graph analytics libraries in this MVP. Before production, run Anvil-specific query/tenant/restore tests and review edition costs. Neo4j Community's one-standard-database constraint is reflected in the local design; no paid license economics are assumed.

### 4.2 Labels, keys and relationships

Every node has labels `AnvilEntity` plus a fixed typed label; `key` is the canonical UUID string, `org_id`, `project_id`, `revision_id?`, `content_hash?`, `visibility`, `projection_generation`, `source_sequence`. Create a unique constraint on `AnvilEntity.key` and indexes for `project_id` and `projection_generation`. `key` cannot be supplied arbitrarily by a client. All graph properties are an allowlisted metadata projection; **no original documents, hidden answers, credentials, personal SME profiles or raw output text**.

| From | Relationship | To | Canonical authority |
| --- | --- | --- | --- |
| TaskVersion | DERIVED_FROM | CaseSourceVersion | task source FK |
| TaskVersion | SUPERSEDES | TaskVersion | parent task/version lineage |
| TaskVersion | IN_FAMILY | CaseFamily | reviewed family mapping |
| TaskVersion | TESTS | Capability | task capability mapping |
| Criterion | MEASURES | Capability | rubric criterion mapping |
| TaskVersion | GRADED_BY | RubricVersion | pinned rubric FK |
| SuiteVersion | CONTAINS | TaskVersion | suite_members |
| Episode | ATTEMPTS | TaskVersion | episodes |
| Episode | USES_SYSTEM | CandidateVersion | episodes |
| Finding | OBSERVED_IN | Episode | finding evidence |
| Finding | CONCERNS | Capability | reviewed finding mapping |
| Finding | SUPPORTED_BY | EvidenceRef | artifact ID/span metadata only |
| ReportVersion | INCLUDES | Finding | approved report membership |

No `CAUSES` edge inferred by an LLM. Potential future TNG state/action/transition labels are a separate namespace and specification, not silently equated with this evidence graph. Graph-assistance to the candidate is off in v1.0.

### 4.3 Transactional outbox and reconstruction

Add `graph_outbox(id,event_id UNIQUE,org_id,project_id,sequence bigint,subject_id,subject_revision_id?,event_type upsert/tombstone,rebuild_generation?,status pending/leased/done/failed,attempts,available_at,lease_token?,lease_until?,created_at)` and `graph_projection_state(project_id UNIQUE,generation,contiguous_applied_sequence,last_success_at?,status current/lagging/rebuilding/failed)`.

In the same PostgreSQL transaction as a canonical mutation, append the event. Process serially per project using a lease/fencing token; parallelize different projects only. Project event sequence is allocated under a project lock so a lower number cannot commit after a higher event is applied. Read canonical authorized metadata, use parameterized Cypher MERGE keyed by UUID, replace that subject's outgoing relation set transactionally, then acknowledge PostgreSQL. Crash after graph commit before acknowledgement is safe to replay: same event/subject revision creates no duplicates. Ignore stale lower-version events only with a recorded supersession; never advance a contiguous watermark past a failed hole.

Deletion/revocation applies an immediate PostgreSQL visibility deny; graph tombstone follows asynchronously. A graph API read resolves returned canonical IDs against current PostgreSQL visibility and revocation before emitting nodes, edges or counts. Apply project filters at every traversal hop; never only filter the root. Do not send private candidate/model identities through blinded reviewer graph views.

Rebuild creates a new projection generation from a consistent PostgreSQL snapshot at a project watermark, replays later events, validates counts/checksums and atomically switches the active generation. Old generation stays inaccessible, then is purged through an approved maintenance operation. No user action directly mutates Neo4j. When unavailable, CRUD/review/report generation remain operational; graph routes return typed degraded status with a canonical relationship-table fallback, not an empty success graph.

Graph query limits: allowed query names only; max depth 3, max nodes 200, edges 500, server timeout 2 seconds. Pagination by opaque continuation token; results declare `truncated`, `as_of_sequence`, `canonical_sequence`, `projection_status`. These are proposed bounds to performance-test, not measured throughput. API timeouts do not silently broaden queries. Expected initial graph is small; load tests—not total source case count—determine sizing.

## 5. Durable job and LangGraph boundaries

Claim jobs in a short PostgreSQL transaction using row locks with `SKIP LOCKED`; commit the lease before work. Default lease 60 seconds, heartbeat 15 seconds. Only a matching live lease token can commit completion. Lease loss fences internal commits but cannot retract an already dispatched external request. A sweeper requeues expired safe/idempotent jobs and sends paid dispatched episodes to reconciliation. Max 3 retries for safe local jobs, exponential 2/10/30 second backoff; no automatic paid inference retry. Queue claims use a dedicated narrow service permission; tenant-scoped execution revalidates target project/rights afterward. [PostgreSQL SELECT locking](https://www.postgresql.org/docs/17/sql-select.html).

The job queue schedules work; LangGraph manages resumable step state within an episode. Do not create competing schedulers that both invoke the candidate. `await_human_review` persists an interrupt and marks its job succeeded-as-paused; episode remains awaiting review. A canonical final review queues one unique `resume` job. Concurrent review/resume requests lock the thread and episode. Worker validates thread ownership, graph digest, pending interrupt, decision version and current rights before resuming. Code upgrades preserve the pinned graph implementation for old threads or require an explicit tested migration; no arbitrary checkpoint rewriting.

Cancellation is a request: stop future node dispatch and queued jobs, then record confirmed local stop. For an in-flight paid call, expose result/cost uncertainty. Reconciliation resolves ledger entries without fabricating output. A new attempt is a new episode attempt number with new explicit budget authority, never overwritten old evidence.

## 6. API conventions

Base `/api/v1`. All business routes below live under `/projects/{project_id}` (abbreviated `P`). JSON bodies; UTC ISO timestamps, UUIDs as strings, explicit null for unknown measurements. Response `{data,meta:{request_id,row_version?,content_hash?,next_cursor?}}`; error `{error:{code,message,field_errors?,retryable,request_id}}`. Avoid disclosing another project's ID existence: return 404. No secret/source content in errors.

List endpoints use `limit` 1..100 (default 25), stable `(created_at,id)` cursor, allowlisted filters and sort keys. Normal creates return 201; asynchronous jobs return 202 plus job ID; updates return 200; idempotent replay returns original status/body. Require `If-Match` for mutable PATCH and transition commands; missing =428, stale =412. Return 409 for invalid state, duplicate-key changed body, quorum failure or stale resumed decision; 422 for schema, 403 for known authorized-project role denial, 413 for upload cap, 429 for quotas, 503 for unavailable dependency. State is never client authoritative.

`Idempotency-Key` required for imports, launches, resume, approvals, report/export builds. Store `(org_id,project_id,user_id,route,key,body_hash,response_status,response_body,expires_at)` with unique route/key scope. Retain launch/release idempotency permanently with operation history; ordinary draft command records 24 hours. Same key/body returns original; changed body conflicts. Commit idempotency result and mutation/job transaction together.

### 6.1 Endpoint surface

| Method/path | Input / result | Required authority |
| --- | --- | --- |
| GET `/auth/login`; GET `/auth/callback`; POST `/auth/logout`; GET `/me` | OIDC flow; sanitized session identity/roles | State/nonce/session checks; logout CSRF |
| GET/POST `/projects` | Visible list / `{name,retention_policy}` | Member list; Admin create |
| POST `P/invitations`; PATCH `P/memberships/{id}` | `{email,roles}` / `{status}` | Admin, current reauthentication; audit |
| GET/POST `P/objectives` | List / `{title,origin,entry_type,hypothesis,business_context,measurement_plan,owner_user_id}` | Collaborator; field restrictions by role |
| GET/PATCH `P/objectives/{id}/draft` | Full authorized draft / changed draft fields | Assigned collaborator, ETag |
| POST `P/objectives/{id}/submit` | `{expected_revision}` → immutable review revision | Researcher |
| POST `P/review-requests/{id}/decisions` | `{decision,rationale,evidence_ids}` | Assigned role, independence, content hash |
| POST `P/approvals` | `{subject_revision_id,purpose,scope,expires_at}` | Purpose-specific role; quorum derived server-side |
| POST `P/artifacts` | Multipart file + purpose/classification → quarantined ID | Data Engineer or permitted evidence contributor |
| GET `P/artifacts/{id}/content` | Authorized stream; safe content-disposition | Separate role/use check on every request |
| POST `P/imports/validate` | Case manifest below → validation job/row errors | Data Engineer |
| POST `P/imports/{id}/commit` | `{manifest_hash}` → imported IDs | Data Engineer; validated unchanged batch |
| GET `P/cases`; GET `P/cases/{id}` | Inventory / permitted source, versions, gaps, rights | Authorized project content roles |
| PATCH `P/cases/{id}/readiness/{item}` | `{status,explanation,owner_user_id,evidence_ids}` | Data Engineer or assigned reviewer |
| POST `P/cases/{id}/rights` | `{source_revision_id,operation,destination_key,recipient_key,evidence_artifact_id,status}` | Admin-designated rights reviewer; cannot self-assert accepted permission without evidence |
| POST `P/tasks`; PATCH `P/tasks/{id}/draft` | Task definition including source/rubric/capabilities | Researcher; commissioned SME business authoring remains Praxis |
| POST `P/tasks/{id}/{submit|publish|withdraw}` | Revision/hash and reason where applicable | Researcher submit; Data Engineer publish after all reviews; authorized withdrawal |
| POST `P/rubrics`; PATCH `P/rubrics/{id}/draft` | Criteria/anchors/critical rules/calibration draft | Researcher/Domain Reviewer proposals |
| POST `P/rubrics/{id}/submit` | Exact revision → assigned review | Author; reviewer cannot be same person |
| POST `P/suites`; PATCH `P/suites/{id}/draft`; POST `P/suites/{id}/freeze` | Name/task revision IDs/selection/exposure | Researcher; validation/review before freeze |
| POST `P/candidates`; POST `P/connections`; POST `P/connections/{id}/activation-request` | Candidate definition / secret reference and fixed destination | Researcher candidate; Admin connection and activation request |
| POST `P/protocols`; PATCH `P/protocols/{id}/draft`; POST `P/protocols/{id}/submit` | Frozen-contract proposal → review | Researcher |
| POST `P/runs` | `{protocol_revision_id,origin}` → draft run | Researcher; origin computed/checked against adapter |
| POST `P/runs/{id}/authorization-request` | `{max_cost_micro_usd,destination_key}` → required approvals | Assigned Researcher/Admin; no launch |
| POST `P/runs/{id}/launch` | `{protocol_hash,authorization_hash}` → job/run | Researcher; reserved budget, rights, active quorum |
| GET `P/runs/{id}`; GET `P/runs/{id}/events?after_seq=` | Status/cost/counts; sanitized ordered events | Scoped research roles; no secret checkpoint dump |
| POST `P/runs/{id}/cancel` | `{reason}` → cancellation_requested | Assigned Researcher/Admin |
| POST `P/runs/{id}/external-results/validate`; POST `P/imports/{id}/commit-results` | Results manifest below; immutable accepted episodes | Data Engineer; correct external origin |
| POST `P/provider-calls/{id}/reconcile` | `{provider_status,evidence_artifact_id,actual_cost_micro_usd?,disposition}` | Admin; no automatic resend |
| POST `P/episodes/{id}/assessments` | Dimension scores/critical flags/evidence/rationale | Assigned Domain Reviewer, blind and independent |
| POST `P/episodes/{id}/adjudicate` | `{assessment_revision_ids,final_scores,critical_violations,evidence_refs,rationale}` | Third assigned reviewer if disputed |
| POST `P/episodes/{id}/resume-review` | `{final_assessment_revision_id,expected_pending_review_id}` → unique resume job | Authorized reviewer or coordinator after final decision; no raw Command/state |
| POST `P/findings`; PATCH `P/findings/{id}/draft`; POST `P/findings/{id}/submit` | Observation/hypothesis/evidence/capabilities | Researcher; independent finding review |
| GET `P/graph?root_id=&view=lineage|capability_failures&depth=` | Authorized nodes/edges + freshness | Researcher/assigned Advisor; allowed query only |
| POST `P/graph/rebuild` | `{reason}` → maintenance job | Admin; no arbitrary Cypher |
| POST `P/reports`; POST `P/reports/{id}/build`; POST `P/reports/{id}/submit` | Bound run/finding/assessment IDs; draft artifact | Researcher; builds don't approve |
| POST `P/releases`; POST `P/releases/{id}/build`; GET `P/releases/{id}/download` | Approved report/recipient/artifact allowlist; ZIP | Product Owner approval; scoped release owner download after rights recheck |
| GET `P/jobs/{id}`; GET `P/audit` | Redacted status/audit cursor | Job owner/scoped Admin; audit scopes enforced |

Generic GET by ID and list endpoints are required for each primary resource in this table, with the same visibility filtering. Unsupported DELETE returns 405; withdrawal/revocation is explicit. Dev documentation must include response models and examples generated from typed schemas, not hand-maintained routes diverging from implementation.

### 6.2 Partner case manifest — interchange v1

```json
{
  "schema_version": "anvil.case_import.v1",
  "partner_key": "synthetic-fixture",
  "cases": [{
    "external_case_id": "DEMO-001",
    "source_version": "1",
    "title": "Demand allocation under a margin constraint",
    "subjects": ["Marketing"],
    "source_family_key": "demo-demand-01",
    "exposure": "controlled",
    "information_cutoff": null,
    "artifact_ids": ["11111111-1111-4111-8111-111111111111"],
    "provenance": {"origin": "synthetic_fixture", "faculty_review_claim": null},
    "readiness": [
      {"item_key": "rubric", "status": "missing", "explanation": "Requires expert review", "evidence_ids": []}
    ],
    "rights_declarations": [{"operation": "external_processing", "status": "unknown", "evidence_artifact_id": null}]
  }]
}
```

The UUID is a format example, not an existing artifact. Validate every referenced ID against uploaded clean project files. Partner declarations are claims, not approved rights grants. Missing readiness items default to missing, not available. Empty cases/duplicate external IDs/repeated version with different content =422/conflict as appropriate. Exact repeated source version/hash is idempotent. A new source version creates a new immutable record. Validation dry-run writes only its batch/errors, not business cases. Commit locks the batch and rechecks file status/rights/configuration.

### 6.3 External results manifest — interchange v1

Required root fields: `schema_version="anvil.external_results.v1"`, `run_id`, `origin=customer_reported|partner_reported`, `producer`, `executed_at`, `protocol_hash` or explicit null with `incomparability_reasons`, `candidate_descriptor={model_requested,model_returned,harness_version,graph_version,tools,parameters}` (unknown values explicit), `attempts` array.

Each attempt: `{task_revision_id,repetition,attempt,execution_state,output_artifact_id?,trace_artifact_id?,usage?,reported_cost_micro_usd?,source_score?,source_rubric_version?,limitations:[]}`. Source scores are labeled reported and never overwrite Anvil reviewer scores. Partial traces carry coverage; lack of trace is not replaced with generated steps. Unknown task IDs/different project/exposure breaches reject the batch. External manifest ingestion never starts candidate execution. Preserve original manifest and producer-supplied hash; compute an Anvil receipt hash separately.

### 6.4 Candidate adapter contract

`execute(request, cancellation, authorized_artifact_reader) → result` is a server-only interface. Request: `{episode_id,operation_key,protocol_hash,candidate_version,actor_artifact_ids,prompt_version,budgets,allowed_destination}`. Reader only resolves actor-approved clean artifacts from the frozen manifest. Result: `{status:completed|failed_operational|execution_unknown,output_artifact_id?,provider_request_id?,model_returned?,usage?,cost_estimate_micro_usd?,observable_event_ids:[],error_code?}`. No raw credentials or hidden-reference IDs. Adapters publish a capability manifest and version; unsupported requirements block before dispatch. LangGraph owns orchestration, adapter owns provider translation, application services own authorization and ledger consistency.

### 6.5 Release bundle contract

ZIP built by the server from an explicit allowlist, no path traversal/symlinks. Files: `manifest.json`, `README.md` (how to read/limits), `suite-card.json`, `protocol.json` (redacted), `scorecards.csv`, `findings.jsonl`, `report.html`, `report.md`, and permitted evidence under safe hashed names. Manifest includes schema/product/build IDs, recipient, permitted use, evidence origins, all source/version hashes, artifact checksums, exclusions, reviewers and correction/supersession IDs. No secrets, private source files, hidden references, identities or protected learning content unless specifically permitted and approved. HTML is escaped with no executable embedded scripts; CSV strings beginning with formula-triggering characters are neutralized. Download approval is not proof of customer receipt/acceptance. Exporting a draft fixture is internal-only and prominently watermarked.
