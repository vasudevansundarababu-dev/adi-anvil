# ADI Anvil — Product Specification

Version: 0.10 · 27 September 2026
Authority: Separate product/codebase confirmed; the scoped baseline and detailed design below are for review

Product identity: **ADI Anvil — Frontier Evaluation & Diagnostics Platform**. The folder retains its earlier ADI-Core-Frontier name. [MVP v1.0 engineering baseline](14-MVP-V1-ENGINEERING-BUILD-SPEC.md) narrows this broader roadmap to the first diagnostic release. LangGraph is user-selected for orchestration; PostgreSQL for CRUD; Neo4j is the recommended graph layer. TNG/TTM learned-planning design is deferred pending the user's later specification.

## 1. Product promise

Help frontier research teams obtain qualified capability-focused tasks, environments, graders and learning assets; investigate observable failures; and measure whether a specified intervention generalizes. The lab's model and agent runtime are the objects being tested, not products the lab must replace.

The unit of work is a **Research Objective** and its versioned **Capability Pack**. Domain expertise supplies realistic constraints and discriminating scenarios. A domain label, synthetic volume or graph representation alone is not a demonstrated advantage.

## 2. Users and outcomes

| Persona | Primary job | Boundary |
| --- | --- | --- |
| Research lead / buyer | Define the capability gap, protocol and acceptance basis | Interest does not establish purchase authority or guaranteed improvement |
| ADI Researcher — F01 contributor | Shape the technical objective, propose measurement and recommend scope with Advisors | Final scope approval belongs to the ADI Product Owner; technical/day-to-day ownership remains open |
| Advisor / assigned Advisor group | Contribute specialist insight and help shape/review F01 briefs alongside ADI Researchers | No automatic sole ownership, evaluation, spending, release or cross-customer access |
| Selected customer researcher — F01 contributor | Supply permitted requirements, evidence and feedback in an authorized project | Explicit selection/invitation required; participation is not final customer acceptance |
| ADI Product Owner — F01 scope approver | Give final objective-scope approval after technical recommendations from ADI Researchers/Advisors | Not automatic spending, scientific-assessment, release or customer-acceptance authority; actual assignment and review mechanics remain open |
| Evaluation researcher | Configure assessments, compare systems and investigate failures | Cannot treat task, grader or infrastructure defects as model failures |
| Post-training researcher / RL engineer | Consume approved examples, environment interfaces and rewards in the lab's stack | ADI does not optimize the lab's weights in this product |
| Task designer / domain expert | Author and review business content in Praxis; advise Frontier on research suitability and environment/grader fidelity | Praxis acceptance is not Frontier qualification or permission to disclose customer data |
| Data engineer / environment engineer | Prepare source records, build isolated worlds and validate integrations | No implicit task authoring inside Data Preparation |
| ADI Sales | Participate in F01 briefs, capture customer/delivery context and explain approved evidence | Cannot change tests, scores or scientific verdicts |
| Platform Admin / approver | Manage access, secrets, external calls and bounded authorization | Different Admin required for applicable activation/paid approval |

F01 includes ADI Researchers, Advisors, ADI Sales and selected customer researchers (F-D08). Advisors supplement rather than replace ADI Researchers. F-D09 confirms technical recommendations from ADI Researchers/Advisors and final scope approval by an ADI Product Owner. Technical/day-to-day ownership, detailed permissions and approval mechanics remain open; this does not replace downstream evaluation or customer training roles. Evaluation, release and disclosure role assignments remain review items; these are specification personas, not already-created accounts.

## 3. Product modules and navigation

| ID | Navigation | Included | Explicitly absent |
| --- | --- | --- | --- |
| F01 | [Research Objectives](10-RESEARCH-OBJECTIVES-SPEC.md) | Both origins and four collaborator groups; Product Owner scope approval; benchmark-led or capability-led entry; proposed readiness/review controls | Enterprise workflow operating dashboard |
| F02 | Data Preparation | Approved source data, ontologies, synthetic records and eligible trajectories | Task import/graph authoring |
| F03 | Task Intelligence Studio | Praxis/approved-partner task intake, case enhancement qualification, capability/family mapping, scenarios, optional graph/environment bindings and coverage | Duplicate SME workbench; required learned transition-policy service |
| F04 | Environment Studio | Isolated executable worlds, action contracts, reset and qualification | Production business-system access |
| F05 | Training Packs | Qualified demonstrations, preferences, environments, rewards and delivery formats | Model optimizer, Tinker/H100 training orchestration |
| F06 | Evaluate | Qualification, baselines, failure analysis, intervention comparison | Enterprise release/deploy approval |
| F07 | Benchmarks | Versioned suites/protocols, comparable baselines and permitted external benchmarks | Public ranking without a valid comparable protocol |
| F08 | Reports | Data cards, diagnostics, studies and audience-controlled sales evidence | Enterprise compliance certification |
| F09 | Pack Releases | Immutable research package delivery, rights and acceptance | Model deployment or business-agent monitoring |
| F10 | Administration | Model/harness access, graders, runners, source connections, roles and approvals | Training hardware/model-weight lifecycle |

Environment Studio is a first-class Frontier area. It is not nested inside a training-execution module. This is a product-specific replacement for the combined platform's Train placement, enabled by the user's separation request; exact screen layout remains proposed.

## 4. In-scope offers

1. **Capability Diagnostic Pack:** qualified cases, a supported runner, baseline evidence and reviewed failures.
2. **Training Environment and Data Pack:** reviewed learning data plus executable environment/reward interfaces where contracted; customer performs optimization.
3. **Controlled Improvement Study:** ADI assessment of baseline and intervention systems, with the customer conducting any weight training. ADI may retest supplied approved endpoints or import labeled customer results. ADI-run fine-tuning is not included.

Delivery acceptance concerns agreed validity, compatibility, rights and evidence quality. Positive improvement is a hypothesis, not a contractually implied scientific outcome. Counts distinguish families, instances, variants and attempts.

The first concrete SKU is [Business Case Diagnostics 200](13-BUSINESS-CASE-DIAGNOSTICS-SKU.md): qualify and enhance a partner-supplied business-case collection, evaluate lab models/agents and deliver evidence-backed failure diagnostics. It is a custom-suite diagnostic, not a required GDPval run or an online RL/training product by default.

## 5. Removed from this product

No ADI domain-model training service, teacher/student model registry for optimizer execution, model checkpoint selection/resume, H100 fleet administration, Tinker fine-tuning jobs, learned-TTM training, production agent deployment, enterprise business approvals or operational business-workflow monitoring.

Permitted teacher/example generation is a Data Preparation activity with rights, review and spending gates; it does not add student optimization. Assessment/generation/environment jobs still need execution status, costs, errors and internal service observability. Removing the enterprise Monitor module must not remove basic operational safety.

The product has no Enterprise mode, cross-product runtime dependency or shared customer database. A privately scoped internal research experiment outside this product must not quietly expand the sales contract or UI.

## 6. Success and MVP boundary

Measure: accepted valid/novel task coverage, grader quality, reproducible failures, integration effort, usable learning assets, research turnaround and interpretable held-out comparisons. Improvement metrics are study-specific with uncertainty; no universal uplift target is set.

Confirmed first SKU (F-D14): 200 MBA-style business cases from the Bodhium work spanning Marketing, Finance, Strategy, M&A and other supplied areas. The user reports professor curation/validation and prior agent experiments with many failures, without a standard benchmark. Treat these as reported assets/results until the actual evidence is reviewed. The precise subject split, source rights, professor-review scope and qualified case count remain unknown.

Confirmed planning assumption (F-D15): Bodhium supplies some inputs; ADI enhances them for lab requirements. Start with an inventory and per-case gap ledger, then task/reference/rubric enhancement, compatible execution, calibration and diagnostic reporting. A small onboarding sample validates the pipeline before full-suite assessment; it does not replace the 200-case scope. A simulator is needed only for cases requiring interactive state. No ADI model, learned TTM or training optimizer is required.

The older Bodhium question-mining/shopping proposal remains historical context, not the selected first SKU. The new case-solving claim does not prove simulator capability, general model failure or benchmark transfer. See [F01 pilot basis](10-RESEARCH-OBJECTIVES-SPEC.md#5-confirmed-first-sku--business-case-diagnostics-200).

Not a completion claim: no runner, simulator, data pack, buyer acceptance or benchmark uplift has been produced by this specification.

## 7. Product boundaries and independent ownership

Own frontend, backend, database, migrations, IAM configuration, secrets, queues/storage namespaces, telemetry, deployment manifests, release train and backlog. Never require the Enterprise repository to build, test or operate.

A common vendor library is allowed only as an independently pinned dependency. A future shared ADI package needs a separately approved contract, local ownership, compatibility policy and removal path; it is not part of this baseline. Optional file/API interchange is explicitly versioned and rights-checked, never an implicit shared database or release gate.

Praxis owns SME task authoring and business-content review (F-D11). Frontier consumes accepted task records and proposed approved-partner case submissions through explicit adapters/file handoffs; it owns research qualification, environment binding, evaluations and packages. Partner cases need not be rewritten in Praxis. Their source rights and content provenance still require review, and licensed educational cases cannot bypass Praxis's synthetic-only rule. No duplicated candidate flow, SME workbench, shared Praxis database or automatic Enterprise data access is required. See [Praxis integration](11-PRAXIS-FRONTIER-INTEGRATION-SPEC.md).

Proposed assembly correction F-A05: F09 owns the generic CapabilityPackVersion/manifest; F05 contributes qualified learning assets only when requested. Diagnostic packages do not depend on F05.

## 8. Acceptance boundaries

- F-P01: Diagnostic and package delivery journeys complete without model weights, an ADI planner, Tinker credentials or training GPUs.
- F-P02: Customer-hosted assessment can return permitted aggregates without uploading weights or private traces; limitations remain visible.
- F-P03: Navigation contains no enterprise model-training, deployment or business-monitoring workflow.
- F-P04: Independent build/test/release needs no sibling repository or service.
- F-P05: A negative/inconclusive study is reportable and does not become a fabricated success.
- F-P06: Declining optional graph assistance does not block an otherwise qualified free-planning assessment.

Read [local decisions](DECISIONS.md) before treating proposal details as approved.
