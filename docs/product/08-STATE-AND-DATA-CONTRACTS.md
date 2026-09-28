# Frontier — State and Data Contracts

Version: 0.3 · Proposed logical design · 27 September 2026

This is the Frontier team's own schema/API design baseline, not a database migration or an import from another product. No Enterprise entities, services or migrations are required.

## 1. Object ownership

| Object | Owner | Key content |
| --- | --- | --- |
| ResearchObjective | F01 | Capability, target system, scope, metric/guardrails, acceptance owner, permissions |
| ObjectiveRevision / Recommendation / ScopeDecision | F01 | Immutable submitted brief, required version-bound recommendations and Product Owner scope decision |
| Connection / CapabilityRecord | F10 | Secret reference, endpoint/runner/grader capabilities, validation, allowed use |
| DataVersion / OntologyMapping | F02 | Source/generator lineage, records/schema/digests, quality, expert/publication reviews |
| ProductionRequest / PraxisSourceSnapshot | F03 | Approved brief to Praxis, accepted source ID/digest, provenance and supersession; no shared source DB |
| PartnerCaseSourceVersion / CaseReadinessRecord | F03 | Immutable partner case/exhibit references, permissions, review evidence, available/partial/missing inputs and gap owners |
| LabRequirementProfile / EnhancementVersion | F01 research brief / F03 artifact | Lab capability/interface/evidence requirements; parent-case transformations, reference/rubric changes, expert review and separate validation scope |
| TaskFamily / TaskVersion / TaskQualification | F03 | Research mapping of accepted source content, visible inputs, constraints, solvability, scenario/graph bindings, family lineage and qualified purpose |
| EnvironmentVersion | F04 | Package digest, action/observation contract, hidden-state boundary, reset/errors, dependencies |
| GraderVersion / RewardPlan | F04/F06 by purpose | Reviewed verification criteria or reward mapping; separate versions and ownership |
| AssetRequest | F05 | Learning use, approved sources, qualification status and delivery request |
| LearningAssetSetVersion | F05 | Qualified optional demonstrations/preferences/environment-reward learning assets |
| CapabilityPackVersion | F09 assembly and release authority — proposed F-A05 | Bound tasks/data/environment/reward/grader/split references, optional learning assets, rights and qualification evidence |
| BenchmarkVersion / EvaluationProtocol | F07 / F06 | Source/version/license; frozen candidate/harness, budgets, repetitions, metrics and exclusions |
| AssessmentRun / Episode / Trajectory | F06 | Config, attempts/outcomes, observable evidence, completeness, costs and validity |
| FailureFinding / Assessment | F06 | Observations/hypotheses, review, metric counts, uncertainty and limitations |
| ReviewExchange / ImportedHumanVerdict | F06 adapter boundary | Praxis review request/result identity, original metrics, separate human judgment, evidence permission and adjudication |
| ReportVersion / ClaimRecord | F08 | Source-linked evidence, audience, exact wording, reviews and corrections |
| PackRelease / Delivery / CustomerAcceptance | F09 | Exact manifest/recipient/use, transfer status and independent acceptance |
| Approval / AuditEvent | Local cross-module services | Actor, role, action, exact version/scope, time, expiry/revocation and event provenance |

Exact grader registration/authoring roles need design; one registry per purpose, not independently editable copies. Data/object IDs are locally namespaced (proposed prefix F-); naming is not a security boundary.

Absent entities: student optimizer job, model training checkpoint, enterprise agent release/deployment and business incident/continuous-learning controller.

## 2. Universal version and authorization rules

Every scoped object has organization/project, stable ID, version, creator/timestamps, provenance, permitted uses, and review references; immutable artifacts also have digests. Server-side tenant/role checks apply on every read/write/export/run. Never trust client-supplied tenant, reviewer or approved status.

Bound approvals refer to exact versions and action/resource scope. Optimistic concurrency prevents stale reviews from approving edited artifacts. Changed source versions do not mutate old manifests; dependency changes mark affected validity/reviews explicitly.

Append audit events for approval, launch, import, annotation, export, invalidation and correction without secrets. Object identity, content approval, paid authorization, disclosure and release are separate concepts.

## 3. Lifecycle ownership and handoffs

- Data Preparation owns data review/publication, not task or package release.
- Praxis owns SME task authoring and business-content acceptance. F03 owns immutable intake snapshots and Frontier research-qualified versions; F04 owns environment-qualified versions. Source correction requests do not create a second editable source master.
- Proposed approved-partner intake allows case/task packs directly into F03. Original cases remain immutable; ADI enhancements have separate versions and reviews. Source faculty-review provenance never automatically validates a derivative or overrides rights. Praxis synthetic-only content restrictions are not bypassed.
- Training Packs owns AssetRequest and learning-asset assembly/qualification; it requests inclusion in a package but cannot impersonate the release authority.
- Pack Release owns generic manifest assembly, delivery authorization/status and customer acceptance. This proposed correction F-A05 permits diagnostic-only packages without F05.
- Evaluate owns execution validity and reviewed assessments; Reports consumes immutable snapshots.
- Reports cannot alter source metrics; corrections create successor assessments/reports.

Use module lifecycle definitions as authoritative for each object. Displayed downstream statuses are references, not a second writable state machine. No Published/Completed/Approved event is an implicit launch or public-send instruction.

## 4. Proposed service boundaries

Research brief; data intake/publication; task/environment registry; asset assembly; assessment runner; evidence/failure store; reporting; release/delivery; access/approval/audit.

Implementation may be a modular local codebase first; this is not a demand for nine deployed microservices. Each boundary needs versioned requests/responses, explicit errors, permitted actor/actions and idempotent create/submit/deliver semantics. Retried submission cannot duplicate paid calls or exports unnoticed.

Async jobs return operation IDs, retain progress/attempt records and distinguish requested cancellation from confirmed stop. Provider usage uncertainty remains visible. Store hidden grading material apart from candidate-visible observations. Redaction uses audience policy before constructing exports, not only UI hiding.

## 5. Customer-run evidence interchange

Manifest must identify schema version, objective/pack/protocol digests, candidate/harness identity, execution owner/location, episode counts, validity/exclusion policy, allowed metrics/traces and signatures/digests where supported.

Unknown schema/version or inconsistent counts blocks qualification pending review; do not silently coerce results. Verify artifact integrity where possible, not unsupported scientific authenticity. Customer-reported evidence remains labeled even after successful import.

No required access to private weights or traces. No automatic outbound telemetry. Export permission is scoped to recipient/use; withdrawing ADI access cannot erase copies already delivered.

## 6. Contract acceptance criteria

- F-C01: No sibling code/service/schema dependency is required for any object lifecycle.
- F-C02: Tenant/role/version authorization is enforced server-side, including exports and hidden evidence.
- F-C03: Stale approvals cannot authorize edited content or changed recipients.
- F-C04: Retry/idempotency preserves distinct attempts without silent duplicate spending/delivery.
- F-C05: Import schema/integrity errors and missing trace data stay explicit.
- F-C06: Source invalidation marks dependent assessments/claims for review.
- F-C07: Asset qualification, release approval, delivery and customer acceptance remain separate.
- F-C08: No event automatically starts customer training or external publication.

Exact database tables, API routes, authentication provider, storage engine and queue stack are implementation choices still to select.

Praxis adapter records and documented endpoints are detailed in [the integration specification](11-PRAXIS-FRONTIER-INTEGRATION-SPEC.md). New local logical records are proposals, not assertions about existing Praxis schemas. The adapter must preserve source acceptance, Frontier qualification, scientific assessment and delivery acceptance as distinct records.
