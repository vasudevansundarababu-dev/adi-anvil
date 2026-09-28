# SKU 01 — Business Case Diagnostics 200

Version: 0.1 · 27 September 2026  
Status: First-SKU direction confirmed; working name and detailed delivery/protocol proposed

## 1. What we are selling

A private, expert-grounded evaluation of how a lab's model or agent solves complex business cases, with reproducible evidence of strengths, failures and limitations. The initial collection is **200 cases across Marketing, Finance, Strategy, M&A and other supplied business areas**, not a 200-case marketing-only set or a shopping-assistant pilot. Domain distribution is unknown.

Working commercial name: **Business Case Diagnostics 200**. This is a Capability Diagnostic Pack, not yet an online RL environment, a training-data license or a recognized public benchmark. The lab uses its own models. ADI need not train a model or prove a learned TTM to deliver it.

Proposed buyer-facing description: “Evaluate your model or agent on an expert-reviewed business-case suite and receive case-level scores, observed failure evidence, capability diagnostics and a reproducible evaluation protocol.” Use “expert-reviewed” externally only when the review records support it.

## 2. Confirmed direction versus reported evidence

| Item | Current status | Consequence |
| --- | --- | --- |
| First SKU is the 200-case business-case collection | User-confirmed product direction, F-D14 | Replaces the marketing-only/shopping pilot interpretation |
| Cases resemble those MBA students solve at institutions such as Harvard and Wharton | User description | Do not assume all cases are authored, owned, licensed or endorsed by those institutions |
| Cases are curated/validated by leading professors associated with those institutions | User-reported provenance | Obtain case-level reviewer identity, role, review scope/date and permission for attribution before sales claims |
| Bodhium coded agent-based case solving and observed many model failures | User-reported prior experiment | Request code/configuration and results; preserve as partner-reported until reproducibly assessed |
| No standard benchmark was used | User-confirmed description of prior work | Register a custom suite; GDPval is not a prerequisite or the name of the resulting score |
| Bodhium is expected to supply case/task definitions | User expectation | Record as requested deliverables, not a signed commitment or completed transfer |
| Bodhium will supply some inputs; ADI must enhance them to fit frontier-lab requirements | User-confirmed planning assumption, F-D15; exact scope unknown | Plan a gap-assessment and enhancement stage rather than assuming a complete ready-to-run pack |
| Reference solutions, grading rubrics, exhibits, traces, execution harness and usage rights | Not yet supplied/verified for this specification | Track completeness per case; joint responsibilities/effort follow the gap review |

The reported collection and experiments are new information beyond the September 22 Bodhium workshop summary. Do not use that older summary to deny this reported asset. Conversely, an agent solver is not proof of a general-purpose interactive simulator.

## 3. Partner handoff requested from Bodhium — proposed checklist

| Deliverable | Minimum information requested | If missing |
| --- | --- | --- |
| Collection inventory | 200 stable case IDs; titles; subjects; source/edition/date; existing versions and related cases | Report received/qualified counts honestly; do not fabricate missing cases |
| Case materials | Permitted narrative/exhibits, datasets/spreadsheets, facts and assumptions, information cutoff | Block affected execution or label restricted-evidence scope |
| Task definition | Role, objective, decision question, available information, allowed tools, constraints, requested artifacts, completion criteria | Joint definition work before evaluation |
| Expert validation | Reviewer identity/qualification, actual scope reviewed, date, comments, revisions and conflict declarations | Mark provenance/validation pending; no school-endorsement claim |
| Reference analysis | Key calculations, evidence, assumptions, acceptable alternatives, trade-offs and critical errors | Develop/review reference basis before high-confidence grading |
| Rubric | Dimensions, weights where applicable, partial-credit rules, anchored examples, critical failures and ambiguity handling | Calibrate jointly; a model judge cannot invent the ground truth |
| Existing solver/harness | Code or documented runnable interface; prompts; dependencies; tools; model requested/returned versions; budgets; stopping rules | Do not claim reproduction of prior results or comparative model superiority |
| Prior runs | Per-case outputs, observable action/tool traces, scores, failed/completed attempts, exclusions, judge/version and run dates | Keep prior failures as reported observations only |
| Rights and restrictions | Evaluation, provider processing, derivative tasks, commercial reporting, redistribution, training, storage and faculty/institution attribution permissions | Block the unpermitted operation; managed testing and asset resale are separate permissions |

Request a representative onboarding sample before full integration. Suggested engineering sample: 10–20 cases across the supplied subject areas and execution modes, including clear successes and disputed/failing cases. This is a compatibility/calibration sample, not a statistically justified substitute for the 200-case scope. Exact sample and effort remain to agree.

## 4. Division of work and Praxis boundary

**Bodhium:** expected source of the collection and whatever task/reference/rubric/solver evidence is available. Partial supply is the agreed planning assumption (F-D15), not a commitment to every requested item. Faculty participation and further validation are to be confirmed through named commitments.

**ADI Frontier:** intake qualification; capability ontology; versioned custom suite; permitted runner/harness adapters; calibrated grading; controlled runs; failure attribution; reports and authorized delivery. Frontier can evaluate partner-supplied tasks without forcing every case to be reauthored.

ADI also owns turning the partial source pack into a lab-specific diagnostic: complete missing task specifications, commission appropriate expert reference/rubric work, adapt allowed tool interfaces, define evidence capture and align output formats with the selected lab's needs. These are proposed work responsibilities under the confirmed enhancement direction, not unlimited included services or an agreed budget.

**ADI-Praxis:** remains the SME authoring and business-content review system for new tasks, adaptations, commissioned references and later expansion where its supported schema and content policy fit. It is not a mandatory rewrite stage for already supplied cases. The initial SKU may use a proposed approved-partner intake route directly into F03, with all provenance, rights and research review gates preserved.

Do not silently upload original educational cases into Praxis's documented synthetic-only task workflow or relabel them synthetic. Any Praxis support for licensed case material or multi-domain expert review requires a separate policy/schema decision. No source-code change to Praxis is authorized here.

F02 handles permitted supporting records/exhibits through referenced data assets. F03 owns case/task registration, source snapshots, capability mapping and qualification. F06 owns runs, validity and assessment; F07 owns suite membership/versioning; F08 owns reports; F09 owns package delivery. F05 remains optional and is not a prerequisite for this SKU.

## 5. What constitutes a case, task and run

Keep distinct identities for `CaseSourceVersion`, `CaseTaskVersion`, `SuiteVersion`, `EvaluationProtocol`, `CaseAttempt`, `GradingDecision` and `FailureFinding`. These are proposed Frontier logical objects, not existing Bodhium schema claims.

Map these concepts to the existing local contracts rather than duplicate services: CaseSourceVersion uses PartnerCaseSourceVersion; CaseTaskVersion is a case-specific TaskVersion; SuiteVersion uses BenchmarkVersion with type Custom; CaseAttempt is an Episode under an AssessmentRun; GradingDecision is versioned assessment/review evidence. Exact implementation schemas remain to design.

One case may contain several questions, exhibits and deliverables. Subquestions, seeded variants, repeated runs and corrected editions are not additional independent cases. Source-related or same-company cases may also be dependent; retain family/group mappings.

Starting scale is 200 source cases, not proof of 200 runnable/qualified independent tasks. The delivery manifest separately states supplied, rights-cleared, task-defined, executable, calibrated and evaluated counts, with reasons for exclusions.

Task fields include actor-visible materials, expected artifacts, tools/actions, information cutoff, constraints, completion/stop rules, hidden reference material, reference alternatives, rubric version, subject labels, capability labels, source family and permitted uses. Source-defined reasoning steps are reference evidence, not mandatory hidden chain-of-thought from the tested model.

## 6. Evaluation modes and scientific controls

Do not assume every case is interactive or long-horizon. Select its supported mode:

| Mode | Example | Required infrastructure |
| --- | --- | --- |
| Document-to-deliverable | Analyze exhibits and produce a strategy memo or valuation model | Controlled material presentation, artifact capture and graders; no simulator required |
| Tool-enabled case solving | Query permitted tables, calculate in a sandbox, inspect evidence and produce a recommendation | Pinned tool contracts, isolated workspace, trace collection and explicit budgets |
| Staged/interactive case | New information becomes available after a decision; agent must revise a plan | Qualified state/observation/action/transition contract and controlled event model |

Register the collection as a **custom business-case evaluation suite**. It becomes a usable internal benchmark through stable definitions, consistent conditions and credible grading; it does not thereby become a recognized industry benchmark or an official school benchmark.

Before launch freeze suite, case/exhibit revisions, model/harness/tool/prompt versions, information access, token/time/tool budgets, retries, repetitions, scoring, exclusions, sampling and reporting rules. Evaluate only explicitly authorized systems and provider destinations.

Where practical compare models through the same harness and tool budget. If comparing different full agents, describe system performance rather than isolated model ability. If the Bodhium harness is reused, qualify its mechanics and report its version and limits; if replaced, distinguish the new study from reproduction of the earlier one.

Use objective checks for supported facts/calculations, evidence-linked expert rubrics for open-ended judgment, and calibrated assisted judging where appropriate. Accept multiple defensible answers when supported by the facts. Strategy quality cannot be reduced to verbatim matching of a professor's answer. Reference calculations can also contain errors and remain reviewable.

Review judge disagreement, false pass/fail fixtures, alternative solutions and critical errors. Where feasible, blind reviewers to model identity. Distinguish expert validation of a case, validation of its reference answer, validation of the rubric and calibration of an automated grader; none substitutes for all the others.

Record prior public exposure and prior model access to cases/reference solutions. Published or repeatedly used educational cases may not be fresh holdouts; mark exposure Known / Unknown / Controlled rather than claim uncontaminated performance. Authorized new variants require renewed reference/rubric validation and do not automatically eliminate contamination. Do not use final-test feedback to construct learning assets while continuing to call that test untouched.

If the collection was selected because models failed it, describe results as performance on a failure-enriched set, not a representative estimate of all business reasoning. Document case selection and include permitted comparison/control cases where needed. Do not add out-of-scope cases to the claimed 200-case count without changing the manifest.

MBA curriculum relevance is context, not a measured human baseline. Claims such as “below MBA level” require comparable, permitted human work under a defensible protocol. Faculty affiliation is not institutional endorsement. No guarantee of frontier-model failure, novelty, improvement or eventual sales follows from the source description.

## 7. What labs receive — proposed diagnostic deliverables

1. **Suite/data card:** exact case coverage, subject/capability distribution, provenance, rights, qualification, public-exposure limitations and exclusions.
2. **Reproducible evaluation package or execution record:** pinned protocol/configuration and supported interfaces. Case files, code or rubric exports are included only when licensed and agreed; a managed assessment need not transfer the entire corpus.
3. **Case scorecards:** objective/rubric outcomes, critical violations, attempted/valid counts, costs/time where known, evidence and expert adjudication.
4. **Capability failure matrix:** failures grouped by observed capability—evidence extraction, quantitative reasoning, constraint handling, strategic trade-offs, tool use, planning, checking/revision—mapped back to case evidence.
5. **Failure dossiers:** visible error/omission, earliest observable divergence where traces permit, consequence, alternative explanations and confidence/limitations. Separate task, reference, grader, tool, harness and infrastructure defects from candidate errors.
6. **Prioritized research recommendations:** proposed data, model, harness, retrieval, tool or grading interventions, with suggested discriminating tests. These are hypotheses until tested, not claims to know a model's internal cause.
7. **Optional independent retest:** a separately scoped assessment after the lab changes its model/agent, with exposure and comparability disclosed. No optimizer or training-data license is included by default.

Example only, not a measured finding: a strategy case output omits a stated financing constraint. A valid diagnostic points to the omitted exhibit and affected recommendation, checks whether the harness supplied it, and tests the explanation. It does not simply label the model “bad at strategy.”

Report all valid successes as well as failures, invalid cases, incomplete attempts and disputed judgments. Missing traces limit trajectory-level diagnosis; final-answer evidence must not be converted into invented action history. Uncertainty accounts for related cases and repeated attempts, and small subject slices carry explicit limitations.

## 8. Commercial and release boundary

Proposed first commercial form: a private diagnostic engagement on agreed model/agent configurations, with an approved report and evidence bundle. Optional licensed case/runner access and later learning assets are separately scoped. Pricing, customer count, schedules, exact run repetitions, accepted-case commitment and service levels remain undecided.

Do not reuse the earlier per-task or 20,000-task economics automatically for expert-case licensing, professor review, harness integration, model runs and adjudication. No cash-flow workbook was changed by this SKU definition. Revenue ambition is not a forecast; this specification does not establish demand or a purchase order.

Release gates: source/use permission; intake schema/material completeness; reference/rubric calibration; supported harness/security qualification; agreed protocol; authorized execution; adjudicated report; approved recipient/use scope. A received professor-reviewed case is valuable input but not automatic release approval.

## 9. Acceptance criteria — proposed, not executed

- F-BC01: Register the 200-case collection with received and qualified counts separated; never fabricate missing or invalid cases.
- F-BC02: Each reported result pins case, rubric, protocol and model/harness versions.
- F-BC03: Custom-suite results are not labeled GDPval, an official Harvard/Wharton benchmark or general business intelligence rankings.
- F-BC04: Prior Bodhium failures remain partner-reported until reproduced under stated conditions.
- F-BC05: An open-ended defensible alternative can earn credit under an expert-reviewed rubric without matching one reference wording.
- F-BC06: Case validation, solution validation, grader calibration and institutional attribution have distinct evidence.
- F-BC07: Source/exposure/selection limitations and invalid/disputed outcomes remain visible in reports.
- F-BC08: Partner-supplied case intake does not require a duplicate SME authoring UI, source rewrite or a synthetic-only policy bypass in Praxis.
- F-BC09: No simulator, ADI model, learned TTM or F05 training request is required for document-to-deliverable diagnostics.
- F-BC10: Model failure, harness/tool defect, case ambiguity, grader fault and incomplete evidence remain distinguishable.
- F-BC11: Recommendations identify evidence and alternatives; untested causal claims or invented private reasoning are prohibited.
- F-BC12: Case/answer redistribution, training use and faculty/institution marketing attribution require their own verified permission.

## 10. Immediate decisions and evidence requests

F-D15 answers the planning question: assume partial Bodhium inputs and enhance for frontier-lab requirements. Do not block specification work while the exact supply is unknown. Obtain a permitted sample, available reference/rubric material, existing harness/run manifests, professor review records and a rights summary before estimating full conversion effort or promising outcomes. No secrets or unrestricted teaching materials are requested in chat.

Also settle whether the initial product is managed evaluation, customer-run evaluation or licensed assets; choose the actual target model/agent interfaces; agree report acceptance and expert adjudication ownership. These can be resolved incrementally without reverting to the superseded shopping/KYC pilot question.

## 11. Case enhancement workstream — proposed operating design

Maintain one `CaseReadinessRecord` per source-case version. For task specification, exhibits, reference analysis, rubric, tooling, source rights and prior runs, record Available / Partial / Missing / Not applicable, evidence, gap owner, proposed effort and acceptance check. Not applicable needs a reason. Do not invent a single completeness score that hides a missing permission or grading basis.

Create an approved `LabRequirementProfile`: capability question, target system/interface, tools, budgets, required outputs, failure categories of interest, execution/data boundary and acceptance evidence. ADI Researchers and Advisors can propose a default profile before a customer is identified; label it an unvalidated ADI hypothesis until customer input supports it.

| Enhancement | ADI output | Review needed |
| --- | --- | --- |
| Turn a classroom prompt into a measurable task | Explicit role, input boundaries, constraints, artifacts and completion rules | Business expert plus research reviewer |
| Fill incomplete reference material | Evidence-linked calculations, alternatives and decision trade-offs | Qualified subject expert; do not label newly written material faculty-validated without its own review |
| Adapt grading for the lab's question | Anchored rubric, critical errors, partial credit, grading fixtures and adjudication rules | Calibration against reviewed examples, including plausible alternatives |
| Make execution comparable | Permitted tools, common harness where appropriate, fixed budgets and trace/artifact contract | Technical integration and isolation tests |
| Focus failure analysis | Capability-to-rubric mapping and evidence-linked findings | Research review distinguishing behavior from causal hypotheses |
| Add a new variant or staged decision | Versioned derivative case with fresh assumptions, reference analysis, rubric and source lineage | Source-use permission and new content/executable validation |

Keep the original partner case immutable. Store `EnhancementVersion` with parent case, requirement-profile version, changed fields, author/reviewer, rights, validation and digest. Distinguish Original supplied / ADI-enhanced / Expert-reviewed enhancement / Faculty-reviewed enhancement using actual evidence. The original case's professor review does not validate every derivative.

Preserve a stable base suite and publish customer-specific profiles/subsets as separately labeled versions. Scores across different customized case sets, tools, graders or budgets are not directly comparable. Any training-oriented enhancement remains outside protected test content and requires a separately approved learning use.

Proposed sequence: inventory/sample review → gap ledger and effort estimate → approved lab requirement profile → reference/task/grading enhancement → harness/grader calibration → freeze assessment suite/protocol → authorized runs → adjudicated diagnostics. Qualification is case-specific: some cases may be ready earlier; report deferred or blocked cases rather than claiming all 200 are ready.

- F-BC13: Partial Bodhium inputs remain visibly partial until each required enhancement is reviewed; blocked cases cannot inflate qualified counts.
- F-BC14: An ADI-enhanced case preserves its original source and cannot inherit unearned faculty validation or source-use rights.
- F-BC15: Customer customization records its protocol/suite differences and cannot silently replace the base comparison set.
