# Frontier specification — Review brief

Version: 0.3 · 27 September 2026
Status: Decisions and specification progress, not implementation completion

## What changed

1. The user confirmed Praxis owns SME authoring and business-content review. Frontier consumes accepted records, qualifies them for research, builds environments, evaluates agents and packages deliverables.
2. F01 can start from either a benchmark target or a capability/failure problem. Measurement planning is required before evaluation.
3. F01 now includes proposed fields by stage, permissions, version-bound review, handoffs and acceptance tests.
4. A dedicated Praxis integration specification maps documented dataset, replay and human-review APIs. It distinguishes existing documented behavior from proposed Frontier contracts.
5. The generic package manifest moves to F09 as a provisional design correction. F05 supplies learning assets only when requested, so diagnostic-only engagements can bypass training preparation.
6. The user clarified the first SKU: **200 MBA-style business cases across Marketing, Finance, Strategy, M&A and other supplied areas**, not a shopping assistant or marketing-only pilot. ADI will build a custom-suite diagnostic and advise labs on evidence-backed failures.
7. Assume Bodhium supplies partial materials and ADI enhances them for lab requirements. A new SKU specification defines case-level gaps, reference/rubric work, execution modes, grading calibration and diagnostic deliverables. Prior failures and faculty provenance remain user-reported until evidence is reviewed.

## What the Praxis materials tell us

Praxis already has a documented production workflow: SME qualification and staffing, KYC task creation, reference trajectories, rubrics, human review, append-only accepted records, tool replay and RL-result review. We should integrate these instead of rebuilding them.

The documents do not establish deployed correctness. The supplied spreadsheet contains 144 cases, all Not run, with no tester or build recorded. That may be a blank distribution copy, not the latest operational tracker. Ask for current execution evidence before claiming readiness.

Recorded tool replay is narrower than a stateful environment. The documented replay rejects unrecorded arguments. Frontier must make that limitation visible and separately qualify dynamic state, alternative paths and recovery behavior where a customer needs them.

Candidate sign-in, identity checks and email are simulated in test; malware scanning is a placeholder. No blind-solve workflow is built in Praxis v1 according to the guide. These are known documented limitations, not newly discovered security vulnerabilities.

## Confirmed decisions

- Separate Frontier and Enterprise products and codebases.
- Both customer-requested and ADI-initiated objectives.
- ADI Researchers, Advisors, ADI Sales and selected customer researchers can collaborate.
- ADI Researchers and Advisors recommend; an ADI Product Owner approves objective scope.
- Praxis authoring/content review and Frontier research qualification/environment/evaluation/delivery division.
- Either benchmark-led or capability/failure-led F01 entry, with measurement planning before evaluation.
- SKU 01 is the 200-case multi-domain Bodhium business-case diagnostic, superseding the earlier marketing-only interpretation.
- Partial partner inputs with ADI enhancement for frontier-lab requirements; unknown input completeness is not a drafting blocker.

## Provisional decisions made to keep drafting

These are reversible design proposals, not user-approved implementation or spending authority.

| ID | Proposed default | Reason / review condition |
| --- | --- | --- |
| F-A01 | One assigned ADI Researcher coordinates each objective, with named required Researcher/Advisor recommendations; a distinct Product Owner makes the scope decision | Clear accountability without requiring every contributor to approve; staffing and delegation need confirmation |
| F-A02 | Version-bound review, optimistic concurrency and material-change reapproval | Prevent approval of a stale brief or an edited scientific claim |
| F-A03 | Begin Praxis integration with accepted-record polling and pull-only review results; authorized JSONL fallback | Matches documented interfaces; no invented webhook or project-write privileges |
| F-A04 | PM-managed production-brief handoff before automated project creation | RL_GYM access does not include the documented PM project-creation route |
| F-A05 | F09 owns generic CapabilityPackVersion assembly; F05 owns optional learning-asset preparation/qualification | Removes the diagnostic-only dependency on Training Packs |
| F-A06 | Treat imported Praxis tasks as research-review candidates, not auto-qualified tasks | Business acceptance alone does not establish environment fitness, valid graders, rights or test isolation |
| F-A07 | Direct approved-partner intake for supplied business cases; use Praxis for commissioned authoring/enhancements where supported | Avoid reauthoring existing cases or bypassing Praxis's synthetic-only rule |
| F-A08 | Package SKU 01 first as a private diagnostic, with asset/training licenses separate | Distinguish selling evaluation evidence from rights to redistribute the full corpus |
| F-A09 | Maintain case-level gaps and versioned lab-specific enhancements before calibration/full evaluation | Partial references/rubrics must not become invented ground truth or inherited faculty endorsement |

## Decisions still needed from the user

| Priority | Decision | Recommendation | When needed |
| --- | --- | --- | --- |
| 1 | What can Bodhium supply for the 200-case collection, and what is the lab's diagnostic question? | Use the confirmed partial-input assumption; inspect a permitted sample and build a per-case gap ledger | Before effort/budget and acceptance commitments |
| 2 | Managed evaluation, customer-run evaluation or licensed case assets; which execution modes are actually needed? | Start with a private diagnostic; qualify the supplied harness or an adapter, adding stateful simulation only for interactive cases | Before integration and commercial scope commitments |
| 3 | Confirm F01 review staffing and separation | Assigned Researcher coordinator, required Researcher plus Advisor recommendations, distinct Product Owner | Before workflow implementation |
| 4 | Who can sign scientific assessment and customer release? | Separate named evaluation and release/disclosure owners; Sales contributes but does not approve results | Before evaluation/report release |
| 5 | First customer acceptance criteria and supported policy interface | Agree one interface, validity checks, coverage, grader-calibration evidence and evidence-sharing boundary; no guaranteed uplift | Before paid pilot commitments |

Technical evidence requests: permitted case/task/reference/rubric samples; case provenance and professor-review records; existing solver/run manifests; source-use permissions; then Praxis API/test evidence only for integrations actually used. No credentials or unrestricted teaching materials are needed in chat. Unknowns remain visible while drafting continues.

## Reading order

1. [Business Case Diagnostics 200](13-BUSINESS-CASE-DIAGNOSTICS-SKU.md): first SKU, partial-input enhancement plan, measurement and delivery.
2. [F01 Research Objectives](10-RESEARCH-OBJECTIVES-SPEC.md): confirmed direction and proposed operational details.
3. [Praxis–Frontier integration](11-PRAXIS-FRONTIER-INTEGRATION-SPEC.md) and [Task Intelligence](03-TASK-INTELLIGENCE-AND-ENVIRONMENTS.md): intake/authoring boundaries.
4. [Decisions](DECISIONS.md): confirmed choices versus proposals and release history.

## Completeness and next work

F01 is a functional draft for review, not fully approved or ready to build unchanged. Praxis integration now has a source-grounded contract proposal, but payload examples and deployed compatibility are unverified. F03/F04 still need deeper capability ontology, task qualification, simulator/action-state contracts and grader calibration design. F05–F10 remain earlier scoped drafts with the integration/ownership changes noted where relevant.

Next specification sequence: inspect representative supplied cases → case gap ledger and lab capability profile → task/reference/rubric enhancement → harness/grader calibration → freeze custom suite and assessment protocol → diagnostic reports and acceptance. The first SKU does not require a standard benchmark, dynamic simulator, model training or mandatory Praxis reauthoring. Those enter only if separately needed and qualified.

No application code, live test, provider call, security scan, external publication, Git commit or deployment was performed by this specification update. Praxis, Enterprise and the supplied manuals/tracker remain unchanged.
