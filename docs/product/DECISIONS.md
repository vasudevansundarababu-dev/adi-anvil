# ADI Anvil — Decisions and Review Items

Version: 0.10 · 27 September 2026

## Confirmed direction

| ID | Direction | Consequence |
| --- | --- | --- |
| F-D01 | Create separate Enterprise and Frontier product specifications, skins and journeys for two teams. | This folder is the authoritative product-specific starting point; combined documents are historical. |
| F-D02 | Maintain two separate codebases and identities. | The user's final instruction governs despite an earlier mention of potentially common code. No monorepo edition switch, mandatory shared runtime or sibling build dependency. |
| F-D03 | Remove features/enhancements not needed by each product, including product-specific Train scope. | Exact retained/removed scope is documented locally; no wholesale copy of the other product's backlog. |
| F-D04 — name superseded by F-D16 | Earlier working identity: ADI-Core-Frontier. | Folder retained; customer-facing identity is now ADI Anvil. |
| F-D05 | Start F01 Research Objectives discovery after the Frontier completeness review. | Create the dedicated discovery draft and resolve decisions one at a time. This does not select objective origins, users, screens, approval roles or implementation. |
| F-D06 | F01 option C: support both customer-requested and ADI-initiated research objectives, with separately labeled origins. | ADI can pursue proactive capability research and customer-specific requests. Objective origin does not decide authoring rights, customer login, technical ownership, approval or customer acceptance. |
| F-D07 — superseded by F-D08 | Earlier F01 authoring option C amendment described Advisors instead of researchers. | Retained only as history. The user corrected the participant list in F-D08; do not remove ADI Researchers or impose Advisor-only leadership. |
| F-D08 | Corrected F01 participants: ADI Researchers, Advisors, ADI Sales and selected customer researchers. | All four groups are eligible collaborators; Advisors supplement rather than replace ADI Researchers. This does not require all four on every objective or settle sole ownership, final approval or detailed access. No downstream execution roles are replaced. |
| F-D09 | F01 scope-approval option B: ADI Researchers and Advisors recommend; an ADI Product Owner gives final objective-scope approval. | Separate scope approval from scientific assessment, customer acceptance, spending and execution. Technical/day-to-day ownership, actual Product Owner assignment, review requirements and detailed approval mechanics remain open. |
| F-D10 | The user reports ADI-Praxis has launched for testing and is where SMEs author tasks; the user supplied its specification/testing manuals. | Treat Praxis as an existing external product. Documentation is not live verification or permission to run its test/security/nightly procedures. |
| F-D11 | The user confirmed: SME authoring and business-content review stay in Praxis; Frontier checks accepted tasks for research suitability, builds environments, evaluates and packages results. | No duplicate SME workbench. Source acceptance, research qualification, scientific judgment and release/customer acceptance remain separate. |
| F-D12 | F01 can begin from either a named benchmark or a capability/failure problem, with a measurement plan required before evaluation. | Drafts may capture an untested hypothesis or pending baseline. No benchmark access, reuse rights, execution or uplift claim is implied. |
| F-D13 — first-SKU interpretation superseded by F-D14 | Earlier direction named Marketing/Bodhium as the first offering. | Retain partnership context, but do not constrain SKU 01 to marketing or a shopping assistant. F-D14 clarifies the actual collection. |
| F-D14 | First SKU: 200 MBA-style business cases spanning Marketing, Finance, Strategy, M&A and other supplied areas; ADI evaluates models/agents and delivers failure diagnostics using a custom suite, not necessarily a standard benchmark. | User reports professor curation/validation and prior Bodhium case-solving agents with model failures. Preserve those as reported evidence until reviewed/reproduced; no official school benchmark, institutional endorsement or general simulator is established. |
| F-D15 | Assume Bodhium supplies some inputs; ADI must enhance the cases/materials for frontier-lab requirements. | Per-case gap assessment, lab requirement profiles and reviewed enhancements are in scope for design. Exact supply, work allocation, professor review of derivatives, budget and customer acceptance are not yet commitments. |
| F-D16 | Name ADI Anvil, tagline Frontier Evaluation & Diagnostics Platform; extend ADI Labs logo and use the same frontend family. | Use inspected Praxis visual/technology reference independently; generated derivative/mockup for review, no trademark claim. |
| F-D17 | PostgreSQL for CRUD and a graph database for graph needs. | PostgreSQL canonical operational records; Neo4j recommendation recorded separately, not a user vendor selection. |
| F-D18 | Agent stack will be LangGraph. | Python LangGraph in worker, PostgreSQL-backed checkpoints; distinct from Neo4j. |
| F-D19 | User needs further reading before supplying the next-version specification. | Interpreted in context as deferring advanced TNG/TTM/learned planning; current LangGraph choice retained. Do not invent future design. |
| F-D20 | After a benchmark run, automatically prepare a one-page digest for Sales and a kit to send to labs; user acknowledged review/recipient approval before external sending. | Add Sales Kit to MVP: deterministic automatic drafts, refreshed approved evidence, one-page PDF/HTML, email draft, internal brief and version/recipient-gated dispatch. No email is sent by this spec task. |
| F-D21 | Provide a sample format for Bodhium to supply the case bank and begin testing hypotheses. | Add partner handoff guide and editable Excel template with an original fictional example. Pilot size, detailed fields and experiment designs are recommendations, not assertions about partner delivery or proof of the hypotheses. |

## Inherited safeguards retained where applicable

Two-distinct-Admin activation/paid-scope approval; explicit authorized launch; expert content/mapping/reward review; Data Engineer publication; no publication-triggered training; task/graph authoring outside Prepare Data; protected test separation; no hidden chain-of-thought; provider permissions/readiness checks; no automatic learning, release or deployment.

These originated in the combined discovery. Local descriptions adapt their applicability without claiming the user separately approved every new screen, schema, role or state.

## New scoped proposals for review

| ID | Proposal | Status |
| --- | --- | --- |
| F-P01 | Frontier Train is Training Packs, not ADI weight optimization; improvement studies evaluate customer-trained candidates. | Product-specific scope baseline; detailed first recipe/format and implementation order need review. |
| F-P02 | Top-level Environment Studio and pack release/delivery; no Enterprise Deploy/Monitor modules. | Detailed UX/lifecycle/ownership are proposed. |
| F-P03 | Earlier Capability Research Workbench identity proposal. | Superseded by Anvil identity and Praxis-aligned brand/UI handoff; screen details remain for review. |
| F-P04 | Local logical objects, service boundaries and explicit downstream handoffs. | MVP contracts specified; PostgreSQL/LangGraph selected, Neo4j recommended; no API implementation or migrations executed. |

## Open review items

F01 origins, collaborators, scope-approval authority, either research starting point and the Praxis product division are answered. Detailed functional controls are now proposed in [F01](10-RESEARCH-OBJECTIVES-SPEC.md); the [review brief](12-REVIEW-BRIEF.md) consolidates remaining choices. No benchmark execution or performance claim is authorized.

1. SKU 01's actual 200-case inventory, partial partner deliverables, lab capability profile, target harness and diagnostic acceptance criteria; named owners and detailed review mechanics. Do not reopen the superseded shopping/KYC selection question.
2. Initial learning-asset format, environment/policy interface and private-execution evidence boundary.
3. Evaluation reviewer(s), technical/domain approval assignments and independent-review policy.
4. Pack release/disclosure authority, delivery method, customer acceptance and correction policy.
5. Quality thresholds, sample/uncertainty design, retention and data-destination controls.
6. Exact TNG/TTM versus legacy TTG/TTN relationship before dependent graph/runtime design.
7. Review generated Anvil logo/mockup and recommended backend/Neo4j details; resolve dependency patches/repository setup before coding. Name, frontend family, PostgreSQL and LangGraph are selected.

## MVP engineering defaults — recommendations, not all user-approved

F-E01: Python FastAPI API/worker and independent Next.js/React/TypeScript/Tailwind frontend aligned with Praxis; local-first setup, compatible version pinning during scaffold.

F-E02: Neo4j query projection fed from a PostgreSQL transactional outbox; approvals/scores/rights remain canonical in PostgreSQL. Community local baseline; production edition/cost decision later.

F-E03: Static-case diagnostics plus labeled external results import for v1.0; tool/interactive cases remain visible but blocked from incompatible execution. Fixtures first, optional authorized model adapter; no autonomous grading authority.

F-E04: Schemas, endpoints, leases, LangGraph checkpoints/resume, review separation, scoring and tests in [MVP specification](14-MVP-V1-ENGINEERING-BUILD-SPEC.md) and companions are proposed engineering defaults. Named owners and actual protocol calibration remain operational decisions.

F-E05: Anvil-owned copies of selected Praxis visual concepts/tokens; no sibling imports. Retain existing folder/historical documents; no repository rename.

These do not block drafting; resolve affected items before production operations or firm commitments.

## Provisional decisions during autonomous drafting

The user asked for continued specification work without waiting for input, with decisions/questions reported afterward. This permits reversible draft design, not implementation, spending or changes to Praxis/Enterprise. F-D11 and F-D12 were subsequently explicitly confirmed by the user; the following remain proposals.

| ID | Proposal | Status |
| --- | --- | --- |
| F-A01 | An assigned ADI Researcher coordinates F01; require one assigned Researcher and one Advisor recommendation; a distinct Product Owner approves scope. | Review staffing, quorum and separation before implementation. |
| F-A02 | Submit immutable revisions, bind reviews to exact contents and require affected reapproval for material changes. | Proposed workflow/concurrency policy. |
| F-A03 | Start Praxis integration with accepted-record polling and pull-only human review results; authorized JSONL import is the fallback. | Documented endpoints exist in the supplied reference; schema/deployed compatibility unverified. |
| F-A04 | Use a PM-managed approved production brief to map Frontier work to a Praxis project before automating project creation. | Avoid assuming RL_GYM keys have PM privileges. |
| F-A05 | F09 owns generic CapabilityPackVersion assembly/manifest; F05 owns optional LearningAssetSetVersion preparation/qualification. | Explicit correction to the v0.1 ownership proposal; diagnostic-only work bypasses F05. |
| F-A06 | Praxis-accepted tasks enter Frontier research review, with source snapshots, purpose-specific qualification and successor lineage. | Proposed operational implementation of confirmed F-D11. |
| F-A07 | Accept authorized partner case/task packs directly into F03 with source/content/research gates, rather than require all 200 cases to be reauthored in Praxis. | Proposed intake design under F-D14/F-D15; preserve Praxis ownership for commissioned SME authoring and its synthetic-only policy. |
| F-A08 | First commercial form is a private diagnostic engagement; case/runner redistribution and training licenses are separately scoped. | Recommendation, not selected contract/pricing or execution location. |
| F-A09 | Track per-case completeness and versioned lab-specific enhancements, then calibrate before full-suite evaluation. | Proposed operational design for confirmed partial-input/enhancement direction. |

## Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.1 | 2026-09-27 | Created independent product baseline, scope exclusions, identity/journeys, module specifications and team handoff from combined v0.48 history. No application code, Git repository, external publication, spend or execution created. |
| 0.2 | 2026-09-27 | Started F01 v0.1 discovery draft with inherited boundaries, proposed brief fields, an illustrative objective and one unanswered origin question. Updated current-work pointers only; no other module ownership, Enterprise scope or implementation changed. |
| 0.3 | 2026-09-27 | Recorded F01 option C for both objective origins (F-D06); updated F01 to v0.2 and current-work pointers. Authoring/access options remain unanswered; no external portal, role assignment, Enterprise change or implementation authorized. |
| 0.4 | 2026-09-27 | Recorded collaborative F01 authoring with Advisors replacing ADI researchers (F-D07). F01 v0.3, product/current-work pointers and journeys now reflect Advisor-led briefs. Objective approval remains unanswered; no accounts, invitations, broader execution-role changes or implementation created. |
| 0.5 | 2026-09-27 | Applied the user's correction: F01 includes ADI Researchers, Advisors, ADI Sales and selected customer researchers (F-D08 supersedes F-D07). F01 v0.4 and journeys v0.3 remove Advisor-only leadership. Ownership/approval/access details remain open; no accounts, invitations or implementation created. |
| 0.6 | 2026-09-27 | Recorded F01 approval option B (F-D09): technical recommendations followed by ADI Product Owner scope approval. Updated F01 to v0.5, journeys to v0.4 and product pointers. Next starting-point question remains unanswered; no execution/spend, account assignment or implementation authorized. |
| 0.7 | 2026-09-27 | Incorporated supplied Praxis manuals and confirmed F-D10–F-D12; F01 v0.6 functional draft; new Praxis integration and review brief; affected scope/journeys/contracts updated. Recorded F-A01–F-A06 as provisional. Generic pack assembly proposed under F09 to remove diagnostic F05 dependency. No Praxis/Enterprise/source-file change, code, live test, external publication or deployment. |
| 0.8 | 2026-09-27 | Confirmed Marketing/Bodhium as first Frontier offering (F-D13); superseded suggested KYC pilot, updated F01 v0.7 and integration/review drafts, and linked the existing R03 master read-first. Flagged required marketing authoring/environment adaptation without assuming Bodhium supplies a simulator. Historical master/cash-flow files and Praxis remain unchanged. |
| 0.9 | 2026-09-27 | Clarified first SKU as 200 multi-domain MBA-style business cases (F-D14), with partial Bodhium inputs and ADI enhancement for lab requirements (F-D15). Added SKU definition, custom-suite diagnostics and enhancement workstream; proposed direct partner intake and private diagnostic packaging. Removed active shopping/marketing-only pilot assumptions while retaining historical sources. No source pack, model result, code, paid run, institutional endorsement or revised cash flow is claimed. |
| 0.10 | 2026-09-27 | Added MVP v1.0 engineering/data/API/build specifications; ADI Anvil brand and standalone UI review mockup; LangGraph orchestration and PostgreSQL authority with a recommended Neo4j projection. Deferred advanced TNG/TTM. Added reviewed automated Sales Kit design and Bodhium case-bank handoff guide, Excel template and fictional sample. No application backend, actual model run, external send or publication implemented. |
