# MKT-LH-001 — Launch Northstar Flow in 12 weeks

**Original synthetic task, development version 1.0. Not expert validated.**
Northstar Flow is a fictional workflow SaaS company selling to small operations teams.
All companies, results, quotes and amounts are invented. No customer or personal data is used.

You are the interim Head of Growth. Turn a **$120,000 simulated marketing budget** into
at least **45 new customers by the end of week 12**, with blended acquisition cost at
most **$2,700 per customer**. Build a defensible campaign, learn from weekly results,
respond to disruptions and leave a reconciled board report. Targets are provisional
task-design thresholds, not industry benchmarks or a guarantee of feasibility for every policy.

The selected candidate is **OpenAI `gpt-6-sol`**. The user's **$100 total API ceiling** is
separate from the simulated marketing budget. This pack makes no API calls.

## Start here

Give the candidate only [actor/task.md](actor/task.md) and
[actor/initial-input.json](actor/initial-input.json), then the current observation returned
by the environment. Keep the candidate's prior decisions and observed results in context.
Do not attach this whole directory or the environment source to the candidate.

The task is **12 sequential decisions plus a final report**, not a request to predict all
12 weeks in one answer. A decision consumes budget and changes state. Customers mature
two weeks after lead creation; late spending can create pipeline without contributing
to the week-12 target. Creative fatigue persists; a refresh consumes money. Weekly
disruptions change available actions and results. Results are computed from actions,
not selected from predetermined model answers.

The local reference environment lives in `scripts/marketing_task.py`. It is an offline
authoring/rehearsal tool, **not an Anvil-qualified execution mode**. Current Anvil live
dispatch and interactive environment integration remain unavailable. Do not upload this
as a static case and claim a completed long-horizon execution.

## Local use (no model calls)

From the repository root:

```sh
python3 scripts/marketing_task.py generate
python3 scripts/marketing_task.py rehearse
python3 -m unittest discover -s tests -p 'test_marketing_task.py' -v
```

`generate` deterministically rebuilds the synthetic actor dataset and its checksum manifest.
`rehearse` runs one scripted feasibility policy and prints its final observation. That is
a software check, never model performance. The Python interface is `reset()`,
`observe(state)`, `step(state, action)`. Each successful step returns a new state;
invalid actions raise `ValueError` without changing the previous state.

An operator/harness must retain private state, call `step` once per accepted week, and
send only `observe` to the candidate. The local source and files are **not a sandbox**:
a candidate with repository access could read future events and response parameters.
They must be isolated by an approved harness before any protected evaluation.

## Readiness and provenance

- One task family, development exposure; no independent benchmark/generalization claim.
- Inputs: 16 historical weeks × 4 channels = 64 channel-week records; 8 fictional
  interview excerpts; product facts, constraints, definitions and opening state.
- History comes from a separate synthetic formula; the policy must learn current
  performance. Neither history nor scenario dynamics are market forecasts.
- No external research, ad buying, email sending, browsing or real campaign execution.
- Model, provider and API ceiling selected by user on 2026-09-28. Credentials, reviewed
  rights, real distinct-Admin approvals and integrated live/runtime gates remain pending.
- [Operator review guide](operator/review.md) describes evaluation and limitations.
  It must not be part of actor input.
