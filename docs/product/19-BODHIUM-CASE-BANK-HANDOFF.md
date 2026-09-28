# ADI Anvil — Bodhium Case Bank Handoff Format

Version: 1.0 · 27 September 2026 · Proposed partner submission format, not a claim about existing Bodhium data

## 1. What to ask Bodhium for first

Please provide **10–20 permitted pilot cases**, spanning the subjects and execution modes actually available, plus the inventory of the broader proposed 200-case collection. Include clear successes, failures and disputed examples if available. Explain how the sample was selected; a failure-enriched sample is not a representative estimate of general model performance.

Do not wait until every case has a perfect task/rubric pack. Supply available material and mark each gap **Available / Partial / Missing / Not applicable**, with an owner and explanation. Missing permission blocks the corresponding use; it cannot be fixed by an AI-generated replacement declaration.

For the first executable pilot, identify several cases that can be solved from fixed documents/exhibits without a simulator. Keep tool-enabled and interactive cases in the inventory with their requirements. We will not force them into an unsuitable static runner or call a compatibility problem a model failure.

### Minimum first delivery

1. Stable case ID/version, title, subject, source/edition and related-case family.
2. The actual case narrative and exhibits, with clear separation between candidate-visible input and hidden reference/grading material.
3. What the solver is asked to do, allowed information/tools, constraints and required deliverable.
4. Available reference analysis, calculations, acceptable alternatives and known ambiguity.
5. Available rubric/critical errors and any expert review evidence. If absent, state what ADI and Bodhium must create together.
6. Rights evidence for internal evaluation and any intended external-model processing. Separately state redistribution, derivatives, training and attribution permissions.
7. Any existing harness and prior attempts, including successes and failures, exact configurations and observable evidence—or explicitly “not available.”

The first testable unit is **one rights-cleared task + complete actor inputs + reviewed grading basis + supported execution contract**. Two hundred PDFs alone are not a qualified benchmark.

## 2. Files supplied with this handoff

The accompanying Excel template uses one stable case ID/version across inventory, task fields, files, rights, rubrics, reviews and prior attempts. It contains clearly flagged fictional example rows; delete/replace those before submission and keep real case records separate. Add rows as needed; blank reserved rows do not represent supplied cases. No secrets or unnecessary personal information belong in the workbook.

The separate fictional sample folder contains a small original promotion case, actor inputs, hidden reference and rubric. It demonstrates packaging and arithmetic only. It is **not a Bodhium case, a faculty-reviewed case, a measured model result or proof of long-horizon capability**. Real case complexity must be demonstrated separately.

Proposed delivery structure:

```text
bodhium-case-bank-v1/
  Case_Bank_Handoff.xlsx
  collection.json                      # optional machine-readable inventory
  cases/
    BOD-001/v1/
      case.json                        # source/task manifest
      actor/
        task.md
        case.pdf
        exhibits.csv                   # or original spreadsheet + reviewed rendering
      private/
        reference.md
        rubric.json
        review-records.json
      rights/
        permission-evidence.pdf        # only the relevant authorized evidence
      prior-runs/
        run-manifest.json
        outputs/
        traces/
      harness/
        README.md                      # interface, commit/digest, dependencies
```

This is a transfer layout, not permission to upload every file to an LLM. `actor/` and `private/` are mandatory logical separation. Source originals and permission documents remain private; actual access is enforced in Anvil, not by folder names alone. Provide via an agreed secure transfer channel. Do not email restricted teaching notes, API keys or unlicensed material. Include file SHA-256 checksums if available; ADI can compute them on receipt. Mark unknown values, never invent them.

Anvil's API requires uploaded artifact UUIDs. Bodhium does **not** need to create those. Its relative file paths and external case IDs are mapped by the intake adapter to Anvil artifact IDs after scanning and permission checks. The partner workbook/package is not directly executable API input.

## 3. Workbook tabs and exact meaning

| Tab | One row represents | Required for |
| --- | --- | --- |
| Start here | Submission instructions/checklist | Understanding what to send and what remains unknown |
| Case bank | One source case/version | Stable inventory; 200 target is not a delivered count |
| Task fields | One named task field for one case/version | Solver role/goal/constraints/artifacts/completion and missing-input status |
| Files | One file linked to a case/version | Actor/reference separation, content completeness and checksums |
| Rights | One permitted-use question for one case/version/destination | Blocking unpermitted evaluation, egress, resale, derivatives, training or attribution |
| Rubrics | One scoring criterion for a case/version | Anchored 0–4 scoring, weights and critical errors |
| Reviews | One actual review of an exact artifact/case version | Distinguish case, answer, rubric and grader validation |
| Prior runs | One attempt on a case/model/harness | Reproduction, failure selection and execution provenance |
| Hypotheses | One proposed test with evidence and falsification conditions | Joint experiment planning; not a prefilled success claim |
| Worked example | One explanatory field or calculation from the fictional case | Show the required depth without borrowing licensed case content |

Every data tab starts with `case_id`, `case_version` and `is_example` where applicable. Stable IDs must not change when a title changes. `case_version` is a string, not an Excel date or floating-point number. Related cases share `family_id`; separate questions/variants/repeats must not inflate independent-case counts. Dates use ISO YYYY-MM-DD where supplied; timestamps use UTC ISO strings with Z. Empty numeric fields mean unavailable, not zero. Use the explicit status/limitations fields to explain gaps.

Task fields to fill: `solver_role`, `objective`, `decision_question`, `constraints`, `allowed_information`, `allowed_tools`, `required_deliverable`, `completion_rule`, `information_cutoff`, `reasoning_dependencies`, `state_changes`, `reference_path`, `acceptable_alternatives`, `known_ambiguity`, `estimated_expert_minutes`, `validation_status`. For static cases, mark state changes not applicable with a reason. Reasoning dependencies describe observable work/evidence dependencies; do not request a model's private chain-of-thought.

Files: `actor_input`, `hidden_reference`, `rubric`, `rights_evidence`, `review_record`, `candidate_output`, `observable_trace`, `harness_documentation`. No original solution should be mislabeled actor_input. Define extraction/rendering for spreadsheets, images and PDFs; simply supplying bytes does not prove the model received equivalent information.

Rights operations: `internal_evaluation`, `external_model_processing`, `commercial_reporting`, `source_redistribution`, `derivative_creation`, `training_use`, `faculty_attribution`, `institution_attribution`. A faculty member's involvement is not a license or institutional endorsement. Record the actual permission holder/document, scope/destination, reviewer and expiry. A “permitted” declaration remains subject to ADI verification before activation.

Rubrics: weights for a case/version sum to 100%; criterion anchors 0,1,2,3,4 are explicit; explain critical failure conditions and acceptable alternative answers. A missing rubric is a gap to fill, not justification for a model judge to invent ground truth. Review records distinguish author/reviewer, qualifications/affiliation as documented, reviewed object/version, review date and evidence; do not include unnecessary biographical/contact details.

Prior runs: requested/returned model, run date, harness version/commit, prompt/config path, tools, budgets, output, trace coverage, source grading method, reported score/outcome and limitations. Include omitted/aborted attempts and selection basis. Do not fabricate a trace from an answer. Preserve partner-reported origin even if ADI later reviews the output.

## 4. Readiness and responsibilities

| Stage | Bodhium provides | ADI adds / checks | Stop condition |
| --- | --- | --- | --- |
| Inventory | Source IDs, available files, gaps, source permissions | Receipt hashes, family/subject mapping, restrictions | Restricted source cannot be received through an unapproved channel |
| Task readiness | Classroom question and available context | Explicit task/output/action boundary, reviewed normalization | Missing exhibits/task ambiguity |
| Grading readiness | Reference/rubric/expert records where available | Commission gaps, calibrate alternatives and critical errors | No defensible reference/rubric basis |
| Execution readiness | Existing harness/run details or mode requirements | Qualify supported adapter, budgets, isolation and trace capture | Unsupported interactive/tool mode or external-processing rights absent |
| Diagnostic readiness | Available prior failures/successes with evidence | Controlled runs, independent review and attribution | Cannot distinguish system error from defective task/harness |
| Commercial readiness | Actual asset and disclosure permissions | Reviewed report and Sales Kit, permitted offer/recipient | No permission to disclose case/system/results |

No assignment here is a signed cost/staffing commitment. Agree gap owners and effort after sample review; do not silently reuse old per-task pricing or investment assumptions.

## 5. Hypotheses the pilot can test

| ID | Hypothesis | Required evidence / experiment | What would weaken it |
| --- | --- | --- | --- |
| H1 | Cases reveal reproducible capability gaps under a stated protocol | Complete inputs, frozen harness/budgets, repeated permitted attempts, successes as well as failures | Failures vanish when missing exhibits/harness defects are fixed, or results cannot be reproduced |
| H2 | Expert rubric can grade valid alternatives consistently | Blind independent grades, disagreement/adjudication records on varied answers | High disagreement, reference ambiguity or answer-style bias |
| H3 | Diagnostics separate candidate failures from harness/reference errors | Input-delivery checks, controlled harness changes and observable evidence | Attribution changes arbitrarily or evidence does not identify the source |
| H4 | The collection adds useful coverage beyond familiar/public cases | Provenance/exposure review, capability map, lab comparison against existing eval needs | Public-answer exposure or coverage duplicates the lab's existing tests |
| H5 | Evidence/graph views make research diagnosis more useful | Reviewer study of evidence-linked reports versus score-only reports, time/quality measures | No improvement in diagnosis quality or researcher actionability |
| H6 | A targeted intervention improves protected performance | Later separately authorized study with suitable holdout, customer-owned training/intervention and matched conditions | Improvement is confined to exposed cases or disappears on held-out families |
| H7 | Labs will purchase the diagnostic | Approved sample dossier, customer interviews, paid-pilot/PO evidence | Customers do not value or cannot use the outputs |

H1–H5 can begin with the pilot if prerequisites exist. H6 is not proved by case-bank delivery and does not add Anvil-managed training. H7 requires customer evidence, not more synthetic cases. None alone proves Domain AGI, a learned TTM, a scientific moat or $20M ARR.

### Recommended first experiment

Qualify a small disclosed subset from the 10–20-case sample. Pre-register one research question, two permitted candidate systems under comparable conditions, scoring/invalidity rules and an affordable repetition budget. Keep a separate family-level protected set when there are enough independent cases; disclose if the sample is too small for reliable inference. First reproduce a claimed failure and a success, audit grading disagreements, then expand. No numeric performance target or scientific conclusion is prefilled in the template.

## 6. Short request to send Bodhium

Please use the attached ADI Anvil case-bank template to share the inventory and a permitted 10–20-case pilot sample. For each case, provide the task, candidate-visible exhibits, separate reference/rubric material, review provenance, use permissions and any prior model/harness results you have. Mark unavailable items explicitly; we will jointly prioritize the enhancements needed. Please include successes and disputed cases as well as failures, and explain how the sample was selected. Our first goal is to establish task readiness, reproducible evaluation and useful diagnostics—not to assume all 200 cases are already a validated benchmark.
