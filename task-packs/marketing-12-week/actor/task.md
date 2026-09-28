# Your assignment: Northstar Flow launch

You are Head of Growth for Northstar Flow, a fictional B2B workflow SaaS product.
Run a 12-week launch for small operations teams. All supplied data is synthetic.

**Business goal:** acquire at least 45 customers within 12 simulated weeks, spending
no more than $120,000, with total campaign cost / acquired customers ≤ $2,700.
Annual contract value is $6,000, gross margin is 80%. Maximize acquired annual recurring
revenue minus campaign cost, while preserving the constraints below. Report gross
margin-adjusted value separately; ARR is neither cash collected nor realized profit.

## Rules

- Allowed channels: `search`, `social`, `webinar`, `email`. Email represents consented
  fictional subscribers only; it never sends messages. No purchased lists or invented claims.
- Weekly channel caps and sales qualification capacity come from the current observation.
  You cannot carry unused channel capacity forward. Remaining money does carry forward.
- Spend is in whole USD. Weekly spend plus optional $1,000 creative refresh must fit
  the remaining budget and a $15,000 weekly limit. Zero-spend weeks are valid.
- Choose one message theme: `time_saving`, `visibility`, or `reliability`. A refresh
  makes new assets and resets fatigue. Repeated themes can fatigue; discover the effect
  from results. Changing theme resets its current consecutive-use streak.
- Leads qualify during the acquisition week, subject to the observed sales capacity.
  If capacity is exceeded, qualified leads are accepted in fixed order: search, social,
  webinar, email. Overflow is lost, not deferred. Account for this operational limitation.
- Accepted qualified leads may become customers exactly two weeks after acquisition.
  There is no opening pipeline. Conversion rates are unknown and can change. Remaining
  pipeline at week 12 is reported separately and earns no customer credit.
- All counts are integers; the environment rounds down at each funnel stage. This is
  a simplified simulation with no causal or market-validity guarantee.
- No discounts, price changes, extra channels, external tools or additional budget.
- Claims may only use the supplied product facts. Do not claim certifications, guaranteed
  savings, customer endorsements or features not supported by the brief.

## Before week 1

Use the historical data and interviews to choose an ICP, positioning and hypotheses.
Produce a concise launch strategy with a 12-week provisional budget, early learning
plan, sales-capacity assumptions, leading/lagging KPIs, risks and contingency triggers.
Explain which observations would change your allocation. Do not invent future results.

## Each week

Read the current observation and past results, then return one JSON object:

```json
{
  "week": 1,
  "spend_usd": {"search": 3000, "social": 2000, "webinar": 3000, "email": 1000},
  "message": "time_saving",
  "refresh_creative": false,
  "rationale": "Replace this with evidence, tradeoffs and your next learning question."
}
```

These values illustrate the format, not a recommended strategy. Include all four
channels and no extra keys. Rationale must be 1–4,000 characters. Compare your prior
forecast with actual results, explain your next allocation, and identify a measurable
learning question. A forecast is not an observation. The environment does not simulate
randomized experiments; do not claim causal lift from channel comparisons.

After each accepted decision you will receive a receipt and the next week's observation.
Persist a concise decision log with week, hypothesis, spend, observed lead quality,
matured customers, remaining budget and what you changed. Do not reset after a bad week.

At weeks 1, 5 and 9 also provide three proposed ad headlines and one landing-page
paragraph grounded in product facts. These texts are reviewed separately; the reference
environment does not score copy or use it to change conversion rates.

## Final delivery (after week 12)

Provide a board memo plus a reconciled 12-row ledger containing channel spend,
creative cost, leads, accepted qualified leads, customers acquired in that week,
cumulative customers, remaining budget and pending pipeline. Include:

1. Whether each target was achieved; total campaign cost, customer count, CAC
   (undefined if zero customers), acquired ARR and gross margin-adjusted annual value.
2. Baseline plan versus actual decisions, major disruptions, recovery and evidence.
3. Uncertainty, attribution limitations, failed hypotheses and censored late cohorts.
4. A next-quarter recommendation supported by observed results. Do not count pending
   opportunities as revenue or fabricate customer quotes.

Twelve valid weekly actions and the final deliverables complete the task. Outcomes and
reasoning are evaluated separately. Infrastructure errors are not business failures.
