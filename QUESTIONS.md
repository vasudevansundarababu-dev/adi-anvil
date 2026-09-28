# Launch decisions

Version 1.1 — update answers from the user, not from agent inference.

| # | Question | Answer / safe handling |
| --- | --- | --- |
| 1 | Repository location, visibility and publication? | Confirmed: private ADI-Anvil at proposed local path; publish after review. GitHub owner can wait because no remote creation/push is permitted. |
| 2 | Morning outcome? | Confirmed: complete diagnostic journey plus live model evaluations. A fixture-only build is a partial outcome if live testing remains blocked. |
| 3 | May calls incur cost? | Conditional permission confirmed: after user specifies models and budget. User has no API keys. Requested Meta Muse, OpenAI, Claude, Gemini, Mistral and open models. Exact IDs/total USD ceiling pending. Never paste keys in chat/spec. |
| 4 | Proposed stack and Docker readiness? | Confirmed: Next.js/React/TypeScript/Tailwind, FastAPI, LangGraph, PostgreSQL, Neo4j and Keycloak. User reports Docker/Compose working; check the actual build shell before launch. |
| 5 | Local integrations, synthetic cases and drafts only? | Confirmed: no real source data, live Praxis/Bodhium connection, email or cloud. Live model calls governed separately by #3. |
| 6 | Work window and install scope? | Confirmed: 8 hours; repo-local dependencies and local Git checkpoints, no global install/reset/deployment. |

## Non-blocking choices with explicit defaults

- One local organization, two test projects for isolation tests; invitation-only identities, no real customer login service.
- Deterministic checks plus real human grading UI; no autonomous LLM judge as final authority.
- Three original synthetic static cases; no request to license or ingest copyrighted school cases overnight.
- Artifact storage on local private disk behind an interface; PostgreSQL queue, no Redis requirement.
- UI uses existing supplied Anvil logo and Praxis-aligned style; no redesign or shared package dependency.
- English UI; timestamps UTC in records and clearly labeled local display; example amounts USD.
- Local internal PDF/HTML/ZIP/email draft downloads; no automatic sharing links or sender setup.
- Production hosting, SSO provider, retention/legal policy, paid graph edition, customer support and licensing are later decisions, not night-one blockers.

## Live preflight requires a person

The existing product requires distinct Admins for paid provider activation and paid run scope. Seeded test identities validate mechanics, not real independent approval. Before a live run, designated people must record the required approvals for exact configuration/destination/budget. If no two approvers are available, finish the adapter and local E2E, leave live execution blocked, and report that limitation. Do not silently waive the product policy.

No more framework decisions are needed. Exact models, live budget, locally configured credentials and paid approvers remain outstanding. GitHub owner can wait until publication. See [provider setup](docs/build/07-PROVIDER-SETUP.md). If a new unresolved decision expands cost, exposure or scope, record it and continue only unaffected work.
