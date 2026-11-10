# Initial QA handoff — November 10

The owner-approved host window ends **November 11 noon Chicago (18:00 UTC)**, unchanged USD100 infrastructure cap. Exact VM9165875445833338817 is RUNNING with automatic STOP at that deadline. Cleanup follows48-hour retention, November13 at18:00UTC. Production/Praxis unchanged.

## Access

Private app: https://anvil-qa.127.0.0.1.sslip.io:8443/workspace/1c08f1bc-17ec-4480-9f56-b99ac2e22744/benchmarks?benchmark_run=6340fb00-5756-4a0e-bcff-d6784c29cf20

Open `scripts/Open Overnight QA.command` on the owner Mac. Use `node scripts/open-overnight-qa.mjs --engineer` for Engineer. This private tunnel address is not accessible from other computers without a separately agreed access path. The launcher checks the pinned root and current leaf keys in a separate browser, without global trust changes. Close/reopen the QA browser if its leaf certificate renews.

Accounts **qa-team-admin** and **qa-team-rl-engineer**; passwords only in owner-only `/private/tmp/anvil-overnight-qa-20261110-operator/QA-private-access.html`. Do not publish that file. Both actual Chrome OIDC sign-ins passed. Both accounts are restricted to acceptance project `1c08f1bc-17ec-4480-9f56-b99ac2e22744`. No provider credentials are present there; Engineer credential GET403 and cross-project GET404 were verified.

API docs: https://anvil-qa.127.0.0.1.sslip.io:8443/docs . OpenAPI `/openapi.json` SHA256 `824ad0dc5a7ed18aeabcfad45314674a50163be412804530c53577f9def5df83`.

## Stored records and expected calculations

| Case | Run | Verified outcome |
|---|---|---|
| Completed |6340fb00-5756-4a0e-bcff-d6784c29cf20|6 cells, each81/81, mean100%|
| Genuine zero |8344392d-c1b7-4957-9442-8c13fa30b8c0|6 cells, each0/81, mean0%|
| Intentional failure |69d14b02-378f-406a-9358-6db66c805235|Failed before capture; no score|
| Pending report review |9983295f-ef01-41aa-9775-fd913c06be5a|Engineer completed6 cells81/81; export409 until review|
| Six-world technical rehearsal |414e7313-07b9-4781-99ac-0a9a95945b58|Completed12 cells; Task score Not evaluated|

Pending means pending **report review**, not queued execution. No human decisions were fabricated. Earlier configuration failures are retained; replacement Runs are fresh, not patched. Software controls are fictional simulations, not vendor models. The zero control actually fails rubric criteria; missing/failed execution never becomes zero.

Original banking rubric: correctness4000bps=32.4 points, evidence3000bps=24.3, constraints3000bps=24.3; total81. Frozen rubrics, captured evidence, assessment hashes and graph-thread/result hashes are available in stored projections and exports. Both completed/zero PDFs were downloaded, rendered, and all7 pages each visually inspected. Public IDs and receipts are in `qa-team-evidence.json`.

## Source, bindings and reset

Praxis immutable export commit `bef6f49ebf1ad6c40f4fec0fea597cdc88c64743`:35files/156921bytes verified against manifest SHA256 `f557742a9700551e2423414a024d74b0a0e7c7849d16b756d2f9fb7e91b42d71`. Ten Tasks across5 workflows retain fictional/draft/no-human-review/no-rights-clearance labels. No authentic sixth financial workflow was supplied. READY does not activate rights.

Six synthetic packs were validated, registered, instantiated, exercised and reset; IDs/hashes/reset receipts appear in evidence JSON. **Reviewed Praxis Task/environment bindings remain blocked by draft source status.** No source approval was fabricated. Supplied rubrics are frozen draft rubrics, not published reviewed rubrics.

Reset an instance through `/api/v1/projects/{project}/workspace/environments/instances/{instance}/reset` with its current `expected_generation`; stale generations return409. Reset restores baseline and advances generation, retaining Runs/source/reviews/cost history. Reimport of identical export is idempotent. Use fresh Runs; do not truncate evidence or patch scores/states.

## Actual model smoke and initial QA limits

Separate smoke project `b3337332-aff7-4041-93f8-6adf9ca276d3` is available to the operator through launcher `--smoke-results`. Dedicated managed credentials were bound without key exposure. Four actual calls succeeded: gpt-6.1-sol, gpt-6-luna, claude-fable-5-2, claude-opus-5-5. Each passed one supplied fictional Phone Task's3 draft criteria, weights5000/3000/2000bps. This is not a model-quality ranking or official benchmark.

gemini-4-argon remains execution_unknown after rate limiting; gemini-3.8-flash remains execution_unknown after provider deadline/HTTP504. Neither retried or scored zero. Reservations retained. Known metered cost USD0.020075; total cost is unknown because those2 outcomes lack admitted usage. Four native captures were downloaded and SHA verified.

**Paid model/judge execution is OFF for initial QA**, verified by public activation receipt; no judge calls. App cloud provisioning disabled. USD75 total/initial USD10 model budgets remain unchanged. Three build attempts consumed; no fourth build authorized.

Runtime image baseline c08c168, DockerID `sha256:8844f7a2fc9dd6d90aeebd070c78b23d8655e3cc05f2aa75c4cd6bdf2b1af651`, plus explicit overlays; core source checkpoint75dd0fffc542e169e85b6baa5942d34e87af57fe. Later helper/docs commits do not imply an image rebuild. Actual Harbor0.25.0 / ATIF-v1.8 / OpenEnv0.12.0. Host-mediated business state is not native bank-service containment.

935 backend units,24 lifecycle/credential/worker checks and5 admission/control units passed. Actual role sign-ins, source idempotence,6 reset/stale-generation checks, state/score/API-doc/readback/export checks passed. Not independent QA or full authentic-source acceptance.

Automatic approval review rejected a proposed negative write test setting reviewers to zero. That request was removed and never sent; read-only role checks passed. Review settings remain unchanged.
