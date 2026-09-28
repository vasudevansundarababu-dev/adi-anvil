# ADI Anvil — Identity and User Journeys

Version: 0.7 · Review draft · 27 September 2026

## 1. Distinct identity

Selected name: **ADI Anvil**. Exact tagline: **Frontier Evaluation & Diagnostics Platform**. This supersedes the earlier working identity/descriptor. Never show an Enterprise/Frontier edition switch.

Use the inspected Praxis frontend family: Next.js, React, TypeScript, Tailwind; navy #0A2170, blue #2A80D0, teal #3FAC95, silver #8597A3 and charcoal #212227. This replaces the earlier alternate palette. See [brand/UI handoff](17-ANVIL-BRAND-AND-UI.md) for semantic accessibility colors, generated logo derivative and review mockup. Design reuse is Anvil-owned, not a dependency on Praxis packages.

Separate product wordmark, browser title, application identifier, login entry, navigation configuration, design-token file and empty-state copy. Color is never the sole indicator of evidence, failure or approval. Contrast, keyboard navigation and narrow-screen behavior require implementation tests.

Home asks: **Which capability are you investigating?** It shows research objectives, pack readiness, evaluation validity and review queues—not running enterprise business processes.

Vocabulary: objective, task family, scenario, pack, candidate system, harness, grader, diagnostic finding, study, delivery. “Train” appears as **Training Packs** with “Prepare assets for your training stack,” not “Launch model training.”

## 2. Screen map

Persistent project/objective context; Praxis-style top navigation shows scoped MVP areas, with broader F01–F10 navigation added only as implemented. This supersedes the earlier left-sidebar proposal. A shared evidence drawer resolves versioned references; header badges show execution location, evidence origin and permission scope. “Baseline pending,” “Illustrative” and “Customer-reported” remain visibly distinct.

Key workspaces: Objective Brief; Source/Ontology Review; Praxis/Partner Intake; Case Gaps and Enhancements; Capability/Family Mapping; Environment Qualification; Training Pack Builder; Protocol Builder; Run Inspection; Failure Analysis; Comparison; Report Review; Delivery Manifest. Commissioned SME authoring stays in Praxis where supported; partner case intake does not force a rewrite. Detailed layouts are not approved wireframes.

### 2.1 F01 objective-definition entry journey

Confirmed F-D06/F-D08: objectives can originate from a customer request or ADI research. ADI Researchers, Advisors, ADI Sales and selected customer researchers can collaborate on F01 briefs within authorized projects. Advisors do not replace ADI Researchers; no sole lead has been selected. ADI Sales captures customer/delivery context; technical contributors shape the research question and measurement; selected customer researchers contribute permitted requirements/evidence. These detailed responsibilities are proposed, and not every objective must involve all four groups. Customer login is not mandatory for every objective, and internal research needs no invented customer.

F-D09 confirms that ADI Researchers and Advisors recommend objective scope and an ADI Product Owner gives final scope approval. F-D12 supports either a named benchmark or a capability/failure problem, with measurement planning before evaluation. Detailed permissions and review mechanics are proposed in [F01](10-RESEARCH-OBJECTIVES-SPEC.md); they are not yet fully approved. Neither participation nor scope approval grants execution, budget, scientific-assessment approval or access to other projects.

## 3. Journey F-J01 — Diagnose a capability gap

Actors: authorized ADI Researchers, Advisors, ADI Sales and selected customer researchers contribute to the F01 brief; an evaluation researcher handles the separately authorized assessment, supported by domain expert and Admin roles.

1. Receive a collaboratively defined F01 objective with target capability, model/harness, data boundary, proposed metrics, technical recommendations and ADI Product Owner scope approval. Detailed readiness/review requirements and customer-acceptance assignments remain to be specified; scope approval does not authorize evaluation execution.
2. Receive Praxis-accepted tasks or authorized partner case/task packs through F03, identify missing reference/rubric/interface material, qualify enhancements for the research purpose, and select compatible task/execution/grader versions. Source acceptance or professor-review claims alone are insufficient.
3. Freeze protocol, scope permitted tool/model calls and obtain applicable approvals.
4. Explicitly launch ADI-authorized evaluation or hand the approved runner to a customer execution owner.
5. Review all outcomes: success, agent failure, invalid task, grader fault, infrastructure error and incomplete trace.
6. Inspect evidence and annotate failure hypotheses; domain expert adjudicates relevant meaning.
7. Produce reviewed diagnostic report with “Intervention not tested” where applicable.

Finish: approved diagnostic evidence. No training job, model registry promotion or deployment is created. Block on missing rights or execution authorization; permit saving a draft. Missing private traces reduce diagnosis depth rather than forcing an upload.

## 4. Journey F-J02 — Supply targeted training assets

Actor: post-training researcher and task/data/environment contributors.

1. Name the development failure family or capability hypothesis and supported learning method.
2. Task Intelligence Studio sends an approved task/coverage brief to Praxis for SME authoring and business review; F03 qualifies the accepted outputs. Supporting records come from Data Preparation.
3. Assemble approved demonstrations, comparable preference pairs or an executable environment/reward package.
4. Run format, meaning, isolation, reward-exploit and contamination checks applicable to the selected asset.
5. Complete expert/technical qualification and immutable package approval.
6. Deliver through an approved destination; customer checks integration and separately accepts.
7. Customer trains independently. ADI receives results only if permitted and chosen.

Finish: rights-cleared qualified assets, not a trained ADI checkpoint. If only static data is delivered, never label it a runnable RL Gym. Invalid data returns to review; a failed delivery is not customer acceptance.

## 5. Journey F-J03 — Test an intervention

Actor: evaluation researcher with customer research owner.

1. Freeze baseline, intervention, comparator, budgets and independent test protocol before seeing outcomes.
2. Receive candidate endpoint/revision or permitted customer results; record what changed and who ran it.
3. Evaluate matched candidates with protected cases, or validate imported result manifests.
4. Account for related families/repeats, exclusions, uncertainty, costs and regressions.
5. Separately test external benchmark transfer if scoped and permitted.
6. Review the study; conclude positive, negative or inconclusive within the evidence.

A model plus harness change is a system-level intervention. An imported result is customer-reported, not independently reproduced. A score on an ADI suite is not a GDPval result.

## 6. Journey F-J04 — Sales to collaborative objective definition

Actors: ADI Sales, ADI Researchers, Advisors and selected customer researchers within their authorized scope.

Capture the research need, available baseline, existing generation approach, missing capability, permitted execution/evidence, proposed acceptance owner, budget owner and delivery constraints. ADI Researchers and Advisors recommend technical scope with ADI Sales and selected customer input; an ADI Product Owner gives final objective-scope approval (F-D09). The responsible implementation/evaluation owners must validate actual feasibility before a quote promises supported interfaces, schedules or results. Contributor input and scope approval are not proof of implementation, customer acceptance or spending authorization. Technical/day-to-day ownership and detailed review mechanics remain open.

Select Diagnostic Pack, Training Environment/Data Pack or Controlled Improvement Study. Use an audience-approved brief; cannot edit metrics or verdicts. Proposed feature availability remains “Specified” until implementation evidence changes. No automatic email, public publication or customer endorsement.

## 7. Journey F-J05 — Correct a delivered pack

Actor: pack owner and release authority (assignment TBD).

Record defect → block affected new deliveries → assess dependent findings/reports → create corrected version → requalify → obtain recipient-specific release approval → send an authorized correction notice → retain the old manifest and acceptance history. Do not silently edit previously delivered evidence or force-upgrade a customer's training assets.

## 8. Separation tests

Praxis owns SME editing, human business-content acceptance and optional human RL-result judgment. Frontier's research review and scientific assessment remain separate. The [integration specification](11-PRAXIS-FRONTIER-INTEGRATION-SPEC.md) defines the proposed handoff and limits.

- F-UX01: A researcher can diagnose and report without visiting Training Packs.
- F-UX02: Training Pack screens never request a training GPU, optimizer schedule or ADI weight upload.
- F-UX03: Hidden answers/reference graph paths are absent from the candidate agent's view.
- F-UX04: Sales sees only authorized evidence; navigating to a report cannot start a model call.
- F-UX05: Product navigation, login identity and configuration contain no edition toggle or Enterprise operating workflow.
- F-UX06: Illustrative, imported, measured and customer-reported results remain distinct in every relevant screen and export.

These are proposed UX acceptance tests, not results from an implemented UI.

First-SKU journey: inventory Bodhium's partial 200-case business collection → agree the lab's capability/evidence requirements → review task/reference/rubric enhancements → qualify harness and grading → freeze custom suite/protocol → explicitly authorize/run assessments → adjudicate failures and successes → release permitted diagnostic evidence. No mandatory standard benchmark, simulator, F05 step or source reauthoring. See [SKU 01](13-BUSINESS-CASE-DIAGNOSTICS-SKU.md).
