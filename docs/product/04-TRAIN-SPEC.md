# Frontier — Training Packs

Version: 0.2 · Review draft · 27 September 2026
Module: F05 · Navigation label: Training Packs

## 1. Purpose and exclusions

Prepare **reviewed learning assets for the lab's own training stack**. This product does not train a domain model, optimize a customer model, select checkpoints or operate an ADI training cluster.

Excluded: Tinker/H100 training orchestration, student/base weight registry, optimizer scheduling, model checkpoint save/resume, ADI-run reference fine-tuning, transition-model training and production agent deployment. Evaluation/generation/environment workloads retain their own authorized execution controls; this exclusion does not remove essential runner administration.

A diagnostic-only engagement bypasses Training Packs. An intervention study can receive customer-trained candidates and return to Evaluate without any ADI weight update.

## 2. Personas and inputs

Post-training/RL researcher defines the requested asset and integration constraints. SMEs author tasks and domain reviewers accept business content in Praxis; Frontier F03 qualifies accepted versions for research. Data Engineer prepares approved records; environment engineer validates executable worlds. Pack qualification, release and disclosure authorities are proposed roles awaiting assignment.

Required request: ResearchObjective ID/version, capability hypothesis, reviewed development findings if available, intended learning method, target customer interface, permitted sources/uses, desired coverage, independent validation plan, acceptance criteria and recipient. Unknown requirements stay visible; a suspected failure cause is not proven by creating a request.

## 3. Asset types

| Asset | Minimum qualification | Never imply |
| --- | --- | --- |
| Demonstration / correction data | Reviewed successful or corrected observable actions/outputs, context, attribution, allowed use and format checks | A failed agent trace is an expert demonstration; hidden reasoning is available |
| Preference data | Meaningfully comparable alternatives, reviewed preference, evidence/rubric and compatible format | Unrelated starting states form valid pairs; teacher consensus is ground truth |
| RL environment and reward package | Reset/step/close, observations/actions, termination/errors, isolated scenarios, tested reward mapping and customer-policy interface | Static logs alone enable online RL |
| Scenario curriculum | Versioned families, capability/difficulty coverage, generation lineage and declared sampling controls | Automatic adaptive generation or guaranteed transfer |
| Permitted teacher examples | Model/version/rights attribution and expert-reviewed quality through Data Preparation | Access to closed weights or unrestricted reuse rights |

Provide only the formats/methods actually integration-tested for the contract. A pack can include one or several types. No universal SFT/preference/RL support is implied.

## 4. End-to-end preparation

1. **Scope:** research owner and customer agree objective, supported use, delivery boundary and acceptance criteria.
2. **Request:** new task logic/families go to F03 for a Praxis production brief, SME authoring/business review and subsequent Frontier qualification; supporting records and eligible trajectory transformations go through Data Preparation.
3. **Assemble:** bind immutable approved source versions, environment/reward/grader references and format adapters.
4. **Qualify:** check structural validity, semantics, permissions, contamination, supported integration, safety/isolation and reward behavior as applicable.
5. **Review:** technical/domain reviewers resolve findings; record remaining declared limitations. Qualification is not release.
6. **Approve delivery:** Pack Release authorizes exact version, recipient, allowed use, destination and redaction.
7. **Deliver:** export manifest and permitted artifacts; customer acceptance is separately recorded.
8. **Optional return:** receive permitted customer evidence; Evaluate labels origin and tests any new candidate under a separate approved protocol.

No publication or export launches customer training. No requirement to send private model weights, optimizer state or private traces back to ADI.

## 5. Synthetic generation and failure targeting

Use expert-grounded ontology/constraints plus capability and failure labels. Meaningful variation includes dependency structure, missing information, changing inventory/state, conflicting constraints, recovery and stopping—not just renaming entities.

Preserve source/generator/family lineage. Automated checks cover every generated record; experts review flags and an agreed representative sample. Review reference solvability or expected abstention/escalation; untested teacher answers are insufficient.

Task definitions and synthetic domain records have different owning modules. The Training Pack Builder assembles approved assets, not an unrestricted task authoring tool. Contributor onboarding/identity evidence is excluded.

## 6. Split and rights controls

Group related source cases/templates/near-duplicates before splitting into training, development and locked tests. Researcher reviews the proposal. Protect evaluation cases, reference solutions and test trajectories from learning exports.

Development failures can motivate new assets after permissions and review. If final-test feedback informs optimization, record exposure and obtain fresh independent confirmation; the old suite is no longer untouched final evidence for that study. This never grants rights to train on retired test material.

Manifest records allowed methods/use, recipients/destinations, source restrictions, retention and any redistribution limits. No blanket exclusivity or ownership claim is inferred from synthetic generation.

## 7. States, screens and handoffs

AssetRequest: Draft → Scope reviewed → In preparation → Qualification pending → Qualified → Delivery requested → Closed. Pack Release owns release/delivery states, which appear here only as linked status. Customer acceptance is a separate record, not a synonym for Delivered.

Blocked/Changes requested/Superseded/Withdrawn are explicit. Edits create a new version; dependent reviews are re-opened for changed scope. A failed transfer is Delivery failed with a retry history, not an accepted pack.

Screens: Requests; Configure Pack; Qualification & Findings; Review & Delivery Handoff; Asset/Trajectory Inspector; Version and Customer Feedback History. **No Launch Training screen.**

Outputs: qualified LearningAssetSetVersion with objective and contents, task/family counts, data/schema, environment/runner where contracted, reward/grader references, split restrictions, lineage, rights, qualification evidence, limitations and digests. Under proposed F-A05, F09 assembles the generic CapabilityPackVersion and owns release/delivery; this screen references those states. Diagnostic packages need no F05 asset set. Data-only exports explicitly say “Not a runnable RL environment.”

## 8. Runtime preparation and monitoring boundary

Environment qualification may run sandbox episodes or policy-interface tests; generation may call approved models. Each actual operation has actor, scope, cost/resource limit and authorization, retaining applicable two-distinct-Admin approval and explicit authorized launch. Package approval does not grant unrestricted calls or customer-side compute authority.

Track preparation jobs, validation errors, costs and delivery health. This is internal service/run observability, not an enterprise production-agent Monitor module.

## 9. Acceptance criteria

- F-TR01: Prepare and deliver a pack without an ADI model, learned TTM, Tinker account or training GPU.
- F-TR02: Diagnostic-only work never creates a training request automatically.
- F-TR03: Failed traces cannot be silently labeled successful expert demonstrations; corrections preserve original evidence.
- F-TR04: RL package qualification tests observation/action interfaces, reset, termination/errors, isolation and approved reward behavior.
- F-TR05: Data-only assets cannot be sold/exported as executable environments.
- F-TR06: Family overlap/protected-test findings block the relevant release until resolved under the agreed policy.
- F-TR07: New task logic routes to Task Intelligence Studio, not Data Preparation.
- F-TR08: Unsupported formats or unpermitted destinations block delivery; no implicit adapter fallback.
- F-TR09: A customer result stays customer-reported unless independently reproduced.
- F-TR10: Delivery triggers neither training nor an automatic model/evaluation call.
- F-TR11: Changing content, rights, reward or interface produces a new version and affected review.
- F-TR12: The module exposes no model optimizer, checkpoint selection/resume or production deployment action.

No execution service, asset package or integration has been implemented. First asset format, supported policy interface, exact thresholds and approver assignments remain open.
