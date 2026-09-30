# Anvil 12 Week Synthetic Marketing Launch RL Benchmark

**Benchmark ID:** `adi-marketing-launch-12w`\
**Version:** 1.0.0\
**Status:** Flagship synthetic acceptance benchmark\
**Provenance:** ADI synthetic only\
**Purpose:** Validate Anvil Benchmark Factory and RL Gym end to end before approved Bodhium source data is available\

## 1. Benchmark objective

Evaluate whether a model or agent can plan, execute, monitor, and adapt a fictional product launch over a 12-week simulated timeline while grounding decisions in evidence, using permitted tools, managing budget and operational constraints, responding to state changes, and producing verifiable terminal artifacts.

This benchmark is not a Bodhium case study, not customer evidence, and not proof of real-world causal lift. It is a deterministic, rights-clear ADI acceptance benchmark and learning asset.

## 2. Why this is the flagship test

The scenario exercises the complete Anvil product loop:

```text
Synthetic source data
  → generated TaskBank
  → Task Neural Graph
  → stateful environment
  → benchmark recommendation/creation
  → Suite and Protocol
  → trajectories and verifiers
  → model comparison and gap analysis
```

It tests long-horizon planning, evidence grounding, budget allocation, tool use, delayed outcomes, uncertainty, policy constraints, adversarial events, recovery, and final business artifacts without using protected customer information.

## 3. Scenario template

Each scenario defines a fictional organization, product, market, audience, launch objective, budget, capacity/inventory, channel availability, source evidence, policy constraints, competitors, and deterministic event schedule.

Required parameters:

- fictional brand and product;
- industry and market category;
- country, locale, and language;
- target launch week and 12-week planning horizon;
- audience candidates and evidence;
- approved channels and tool availability;
- total budget and category limits;
- inventory/capacity constraints;
- compliance and claim constraints;
- starting awareness, consideration, demand, and conversion signals;
- competitor conditions;
- event seed and difficulty;
- required terminal artifacts.

No real brand, customer, credential, campaign, proprietary text, or production data may be embedded in a synthetic scenario.

## 4. Task families

| Task family | Capability under test |
|---|---|
| Market diagnosis | Evidence retrieval, synthesis, uncertainty |
| Audience selection | Segmentation, trade-offs, exclusion reasoning |
| Positioning and offer | Grounded messaging, constraint compliance |
| Channel strategy | Planning, allocation, modality selection |
| Content and asset plan | Sequencing, dependencies, approval awareness |
| Budget allocation | Optimization under constraints |
| Launch execution | Tool use, state transitions, operational correctness |
| Monitoring and experimentation | Metric interpretation, experiment selection |
| Adaptation and recovery | Detect failure, revise plan, preserve constraints |
| Post-launch evaluation | Attribution caution, evidence-backed reporting |

The v1 TaskBank must cover all task families. Difficulty is varied using task depth, ambiguity, number of constraints, tool failures, delayed signals, conflicting evidence, and recovery requirements.

## 5. Twelve-week environment

| Weeks | Environment phase | Required model behavior |
|---|---|---|
| 1–2 | Diagnose | Inspect evidence, define objective, identify audience and risks |
| 3–4 | Design | Select positioning, offer, success measures and launch hypothesis |
| 5–6 | Prepare | Allocate budget, choose channels, plan content and dependencies |
| 7–8 | Validate | Run prelaunch tests, resolve approval or capacity blockers |
| 9–10 | Launch | Execute actions, observe state changes, respond to events |
| 11–12 | Optimize and close | Reallocate, recover, stop unsafe actions, report outcomes and uncertainty |

Weeks are simulated states, not wall-clock waits. A run advances only after a legal action or explicit advance action. Deterministic events occur from the scenario seed.

## 6. State model

The environment state contains:

- current week and phase;
- remaining and committed budget by category;
- selected audience, positioning, offer, and channels;
- available, drafted, approved, rejected, and published assets;
- inventory/capacity and fulfillment risk;
- approvals and compliance findings;
- observed market, brand, channel, and conversion signals;
- experiments and their maturity;
- competitor events and external shocks;
- tool availability and failure state;
- unresolved blockers;
- submitted terminal artifacts;
- cumulative cost, action count, invalid-action count, and recovery count.

`state()` returns an immutable sanitized snapshot. Private simulator truth is never exposed to the model.

## 7. Observation model

Observations may contain structured metrics, short documents, search/query evidence, fictional customer research, channel reports, asset status, tool results, policy notices, and event notifications.

Every observation has stable ID, source type, provenance, availability week, visibility rule, and checksum. Evidence cited by an answer must have been observed by that trajectory.

## 8. Action space

Typed actions include:

- inspect evidence or metric;
- record or revise diagnosis;
- select/revise audience;
- select/revise positioning and offer;
- allocate/reallocate budget;
- request/create/revise an asset brief;
- request approval;
- schedule or activate a channel action;
- configure an experiment;
- call a permitted analysis or execution tool;
- pause, stop, or escalate an unsafe action;
- respond to a competitor or operational event;
- advance the simulated week when prerequisites are met;
- submit launch plan, change log, outcome report, and uncertainty statement.

All actions use versioned schemas. Free-form text is confined to declared fields and is never interpreted as an executable instruction.

## 9. Constraints

The environment enforces:

- total and category budget limits;
- inventory/capacity limits;
- audience and geography restrictions;
- content approval dependencies;
- claim, privacy, safety, and brand rules;
- channel prerequisites and scheduling windows;
- experiment validity requirements;
- tool permissions and rate limits;
- evidence citation requirements;
- terminal deliverable requirements.

Invalid actions return structured reason codes and do not mutate committed state. Recoverable rejection returns the agent to an appropriate decision state.

## 10. Task Neural Graph

Minimum states:

```text
start
→ inspect_context
→ diagnose_market
→ choose_audience
→ define_positioning
→ allocate_budget
→ prepare_assets
→ validate_launch
→ launch
→ monitor
→ adapt_or_recover
→ close_and_report
→ terminal_success | terminal_partial | terminal_failure
```

Required recovery edges include budget rejection, unsupported claim, missing approval, failed tool, insufficient evidence, invalid experiment, capacity shortfall, and weak launch signal.

Graph validation requires at least one success path, one failure path, one recovery path, termination for every cycle, and a verifier or explicit non-scored rationale for every decision-relevant action.

## 11. Deterministic event families

Scenario seeds select bounded events such as:

- competitor price or messaging change;
- channel cost increase;
- creative or compliance rejection;
- delayed asset production;
- inventory/capacity reduction;
- weak audience response;
- strong reach with poor conversion;
- tool/API failure;
- contradictory research evidence;
- late executive constraint.

Events must be fictional, rights-clear, versioned, and replayable. The model must not know the event schedule before it becomes observable.

## 12. Required terminal artifacts

1. Launch strategy and objective.
2. Audience and positioning decision with evidence.
3. Twelve-week action plan.
4. Budget allocation and revision history.
5. Channel and content plan.
6. Experiment/measurement plan.
7. Constraint and approval record.
8. Event response/change log.
9. Outcome report distinguishing observation, inference, and uncertainty.
10. Final state submission.

## 13. Verifiers

### 13.1 Programmatic verifiers

- schema validity;
- action legality;
- budget arithmetic;
- dependency completion;
- state-transition correctness;
- required artifact presence;
- evidence-ID existence and prior observation;
- experiment configuration validity;
- terminal-state consistency;
- deterministic replay.

### 13.2 Policy and provenance verifiers

- unsupported claim detection;
- privacy and audience restriction;
- prohibited action detection;
- provenance completeness;
- synthetic labeling;
- export/access compliance.

### 13.3 Rubric verifiers

- diagnosis quality;
- evidence grounding;
- coherence across 12 weeks;
- trade-off quality;
- adaptation and recovery quality;
- uncertainty calibration;
- final artifact quality.

Rubric verifiers require calibration against SME judgments. Model-based judging cannot be the only source of a critical pass/fail decision.

## 14. Scoring

Initial normalized reward:

| Dimension | Weight |
|---|---:|
| Objective and terminal completion | 25% |
| Constraint, policy, and budget compliance | 20% |
| Evidence-grounded diagnosis and decisions | 15% |
| State/action and tool correctness | 15% |
| Adaptation and recovery | 15% |
| Required artifacts and reporting quality | 10% |

Critical privacy, authorization, fabricated-evidence, or prohibited-action failures cap total reward at `0.20`. Infrastructure failures are excluded from model score and reported separately. Raw dimension scores and verifier evidence remain available alongside normalized reward.

No score is described as revenue, brand lift, or causal business value.

## 15. Trajectory requirements

Each step captures:

- sequence and simulated week;
- observation IDs available;
- model input/output references;
- parsed action and validation result;
- tool request/result;
- state before and after;
- state delta;
- verifier decisions and reason codes;
- latency, tokens, and estimated cost;
- error and retry classification;
- reward contribution;
- intervention or human adjudication;
- terminal outcome.

The release contains at least one reviewed success trajectory, one failure trajectory, and one recovery trajectory for every seed task family.

## 16. Task generation and scale

### 16.1 Seed layer

ADI researchers and ADI Praxis SMEs create and review canonical seed scenarios, ontology, state/action definitions, constraints, verifier rules, and rubrics.

### 16.2 Controlled variation

The generator produces variants across domain, audience, market, modality, budget pressure, constraints, evidence ambiguity, event schedule, tool availability, and difficulty. Generated tasks retain template version, seed scenario, generator version, seed, source references, and transformation log.

### 16.3 Quality plan

- validate 100% programmatically;
- reject graph/schema/provenance duplicates and inconsistencies;
- review 100% of seed scenarios;
- review 100% of high-risk and verifier-disagreement cases;
- review a statistically defined sample of ordinary variants;
- measure reviewer agreement and adjudicate below-threshold categories;
- freeze accepted TaskBank versions.

The platform is designed to execute 100,000 tasks, but initial benchmark releases may contain fewer accepted tasks. Scale claims must distinguish system capacity from available reviewed content.

## 17. Adversarial cases

The v1 benchmark includes:

1. Best-looking channel violates an audience policy.
2. Highest projected return exceeds budget or capacity.
3. Strong reach masks poor conversion.
4. Evidence is conflicting or incomplete.
5. Tool reports success but state did not change.
6. Model claims an unobserved metric or source.
7. Mid-launch event invalidates the original plan.
8. Recovery requires stopping rather than spending more.
9. Experiment is underpowered or causally invalid.
10. Terminal narrative conflicts with recorded actions/state.

## 18. Benchmark splits

- **Development:** visible tasks, schemas, example trajectories, and verifier explanations.
- **Validation:** restricted tasks used during benchmark authoring and calibration.
- **Hidden evaluation:** protected tasks and variations used for comparative scoring.
- **Rotating challenge:** newly generated and reviewed variants used to reduce contamination.

Splits may share ontology but must not share near-duplicate scenarios. Leakage checks and split lineage are part of release evidence.

## 19. UX journey

1. Open Tasks & Data.
2. Choose **Generate task bank**.
3. Select **12-Week Product Launch**.
4. Configure scenario count, markets, modalities, difficulty, seed policy, and review plan.
5. Preview generated examples and graph coverage.
6. Run validation and ADI Praxis review.
7. Publish TaskBank version.
8. Confirm TaskProfile.
9. Review benchmark recommendations and uncovered requirements.
10. Select **Create benchmark from gaps**.
11. Validate manifest, environment, verifiers, and three smoke cases.
12. Publish BenchmarkVersion, compose Suite, create Protocol, and run.
13. Inspect trajectories, verifier decisions, reward, model comparison, and failure taxonomy.

## 20. Acceptance criteria

- **MKT-AC-001:** Same scenario version and seed replay identically twice.
- **MKT-AC-002:** Every task has schema, graph, provenance, constraint, verifier, and terminal validation.
- **MKT-AC-003:** Invalid actions never mutate committed state.
- **MKT-AC-004:** At least one success, failure, and recovery trajectory is inspectable.
- **MKT-AC-005:** Evidence citations are limited to observations actually inspected.
- **MKT-AC-006:** Budget and dependency calculations are programmatically verified.
- **MKT-AC-007:** Critical policy failures cap reward.
- **MKT-AC-008:** Task defects, environment defects, verifier disagreement, infrastructure failures, and model failures are separable.
- **MKT-AC-009:** Synthetic provenance is visible in every UI and export.
- **MKT-AC-010:** The benchmark can run through existing Objective, Suite, Protocol, and Run Console flows.
- **MKT-AC-011:** No Bodhium or customer provenance is implied.
- **MKT-AC-012:** The benchmark package passes repository validation, tests, typecheck, lint, and production build.

## 21. Definition of done

The flagship benchmark is done when a user can generate a versioned 12-week TaskBank, review its Task Neural Graph, create and publish the benchmark from detected coverage gaps, run at least two model configurations, replay trajectories deterministically, inspect verifier evidence, compare success/failure/recovery behavior, and export a permitted gap report without any Bodhium or customer data.
