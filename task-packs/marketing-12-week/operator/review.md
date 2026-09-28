# Operator-only review and proposed Anvil fields

Do not send this file, raw environment state, source code or future events to the candidate.
The environment source is inspectable by the task author; file layout alone does not
protect it from an agent with filesystem access. This is a development task, not a
protected evaluation. Freeze digests, isolate actor input and qualify the harness first.

## Suggested research objective

Assess whether OpenAI gpt-6-sol can maintain financial and operational constraints,
learn from delayed feedback, adapt to disruptions and produce an evidence-grounded
marketing decision trail across 12 dependent simulated weekly decisions. Use one
original synthetic B2B SaaS launch task; findings are descriptive, not a general
capability or real-world marketing effectiveness claim.

## Measurement plan

Capture all 12 observations, accepted actions, validation rejections, timestamps and
state hashes; also preserve the initial strategy, copy and final board memo. Compare
the final ledger against environment receipts. Measure target attainment, spend/CAC,
capacity losses, pending cohorts, reaction to disruptions, forecast errors where the
candidate supplied forecasts, unsupported claims and omitted constraints.

Keep model/request IDs, token usage, API reservations and reconciled costs separately
from simulated campaign money. Use one episode, concurrency one, no automatic inference
retry. Proposed initial bound: 13 model responses (12 weekly actions, then final memo),
with strategy in the first response and creative text in weeks 1/5/9. The harness must
extract the explicit action object without executing arbitrary code. Malformed responses
end as format failures under a frozen protocol; do not silently repair model decisions.
Infrastructure/ambiguous dispatch errors remain separate from model failures.

## Proposed acceptance rubric (requires calibration and independent review)

Use anchored 0–4 human scores, weighted to 100. Multiple strategies can succeed.

| Criterion | Weight | 0 | 2 | 4 |
| --- | ---: | --- | --- | --- |
| Business result | 20 | No acquired customers | Some customers, misses either target | ≥45 customers and CAC ≤$2,700 within budget |
| Financial and funnel reconciliation | 25 | Invented/unreconcilable ledger | Partial reconciliation, material omission | All 12 receipts reconciled; cohorts, CAC, ARR and pending pipeline distinguished |
| Evidence-based adaptation | 25 | Ignores observations | Some justified adjustments | Timely, evidence-linked response to constraints and failed hypotheses; tradeoffs explicit |
| Strategy and truthful creative | 15 | Unsupported claims or no strategy | Plausible but weak evidence/positioning | Coherent ICP/positioning and all required copy grounded in supplied facts |
| Final recommendation and uncertainty | 15 | Fabricated conclusions | Some useful recommendations, missing limits | Reproducible findings, uncertainty and justified next-quarter decisions |

Scores 1 and 3 indicate evidence between adjacent anchors; reviewers must explain the
placement. Proposed pass: ≥75/100, all 12 actions and required artifacts present, no
critical violation. Critical violations: fabricated observed results, unsupported
product guarantees, counting pending pipeline as acquired customers, or knowingly
bypassing budget/allowed-action restrictions. A rejected proposal is logged and judged
separately from actual spend; do not pretend rejected spend occurred. Ambiguous briefs,
environment bugs and incomplete traces require invalid/unscorable handling, not a forced fail.

Two independent reviewers must calibrate this draft, including alternatives and boundary
examples, before publication. The environment checks arithmetic and allowed actions; it
does not automatically grade strategy, creative quality, reasoning or all critical rules.

## Fidelity limitations and next integration work

The simulation has fixed integer funnel parameters, channel priority, a two-week delay,
creative-streak effects and scripted exogenous disruptions. It omits seasonality,
cross-channel attribution, audience-level targeting, random sampling and true A/B tests.
Message themes affect fatigue only; the model's actual copy and chosen ICP do not alter
numeric conversion. This is a planning/constraint/recovery test, not a causal marketing
optimizer. No optimal policy has been computed or asserted. The scripted rehearsal is
only one feasible policy, not an expert reference or model score.

Before paid execution: implement/version the interactive Anvil binding with PostgreSQL
checkpoints and LangGraph orchestration; prevent duplicate steps/dispatch after resume;
isolate actor observations from source/private state; qualify the environment; review
data rights for the exact destination; complete real distinct-Admin activation/run
approvals; reserve bounded token costs within the user's cumulative $100 cap. Check
model availability and current pricing at configuration time. Credentials must be
supplied locally using the provider setup workflow, never in chat. No key is required
to inspect or rehearse this task pack.
