# Current local walkthrough

Verified 28 September 2026, schema012. This is a working local synthetic diagnostic slice; live providers and real sending remain unavailable. The full acceptance matrix is still partial.

Open [the prepared project](http://127.0.0.1:3202/p/ea1cc06d-3ad8-4e9c-8e89-87f27b2d2d82/objectives). Sign in using the corresponding distinct local account from `.local/demo-accounts.md`; do not paste its password into chat. Switch identities by signing out and signing in. The prepared project contains three original synthetic cases, one reviewed six-episode run and a separate six-episode practice run awaiting human review.

If stopped, run `pnpm services:up` followed by `pnpm dev` from this repository. `pnpm stop` stops only the registered Anvil application processes. API health is at `http://127.0.0.1:8200/api/v1/health`; Keycloak is at `http://127.0.0.1:8180`. No inference is needed for this walkthrough.

| Acceptance step | Built UI and evidence |
| --- | --- |
| MORN-01 | Researcher → Research objectives. Inspect the approved objective and review history, or create a new one. Advisor and Product Owner use separate identities for their approvals. |
| MORN-02 | Data Engineer → Case bank, Rubrics and Qualification. Actual counts are 3 cases/3 families; target200 is only a plan. Expand readiness on a source to inspect evidence and gaps. Existing tasks are published against approved rubrics and local-only rights. |
| MORN-03 | Researcher → Suites, Protocols, Run console. The reviewed run is `4498686f-cb5c-4c80-bd4f-ba3e5f9b9eb3`. Both deterministic candidates ran through actual LangGraph checkpoints; this is not model performance. |
| MORN-04 | Reviewer1/Reviewer2 → review queue. Practice run `443273c5-1a18-4253-8c02-b76ad9aa1992` has six ungraded episodes. Read the bound rubric/reference and submit independent grades with literal output evidence. `pnpm worker:restart` preserves pending reviews. Disagreement requires the separate adjudicator. |
| MORN-05 | Researcher → Diagnostics. Search `constraint_preservation`, select the capability, then use the inspector's linked-record buttons to follow task → episode → finding. Clear the search to see the wider graph; it scrolls horizontally. Exact IDs, hashes and review state appear in the inspector. Actual outage and restored-projection tests passed separately. |
| MORN-06 | Reports shows 6 valid episodes, 3 passes/3 failures and mean85 from scripted fixture grades. Sales → Sales Kit provides approved PDF/HTML/ZIP/email-draft downloads. These are internal illustrative artifacts, not customer delivery approval. The separate practice run does not alter the reviewed report. |
| MORN-07 | Automated real-OIDC and API negatives cover role/project isolation, rights, stale versions, missing evidence, duplicate commands, review disputes and blocked providers. See the test matrix; untested permutations are not represented as passed. Use a new project for destructive-to-workflow negative exercises. |
| MORN-08 | Blocked. Adapters are mock-contract-tested, but live dispatch is not qualified or implemented end to end. Exact models, secrets, budget, data rights and genuine independent paid approvals are also absent. Adding a key alone does not enable execution. |

Screenshots and actual downloads are in `artifacts/morning-demo/`: `cases.png`, `runs.png`, `diagnostics.png`, `reports.png`, `sales-kit.pdf`, `sales-kit.png`, `sales-kit.html`, `evidence.zip`, `email-draft.txt` and `internal-brief.txt`. The PDF was rendered and visually inspected as one readable page. All results are illustrative; the mean85 is a fixture assertion, not a frontier-model measurement.

`pnpm demo:walkthrough` creates another isolated project through real local OIDC and API calls, applies explicitly scripted fixture reviews through separate test identities, verifies downloads, and leaves a new practice run pending. It retains earlier projects. It makes no model calls and sends no email. The latest project IDs are written to ignored `.local/morning-demo.json` and `artifacts/morning-demo/walkthrough.json`.
