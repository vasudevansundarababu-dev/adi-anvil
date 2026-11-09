# Project collection packaging and local Run contract

This supplements34/35. Praxis still has a **Project containing Tasks**, mapped to one versioned Anvil Task Group. It does not introduce a new Praxis Task Group entity, change the strict legacy `praxis.anvil.export.v1` Task envelope, or place evaluator engines/keys in Praxis. Praxis implementation remains with its independent team.

## ZIP collection wrapper

`project.json` uses `anvil.task-group-import.v1`. It names `source_project` (id/version/name), `environments` (id/name/version/kind and descriptive enforcement flag), `tasks`, and optional `policy_manifest_path`. The machine-readable schema and reproducible fictional ZIP are exported with the implementation handoff.

Each Task entry contains `path` to its existing exact-hash export.v1 envelope, `environment_ids`, optional `dimensions` mapping criterion IDs to correctness/evidence/constraints, and optional Task-authored `failure_modes` containing id/title/criterion_ids. Existing payload JSON and SHA256 remain byte-bound. The collection source Project ID must match every Task export. A Project/version with different Task content conflicts; export a new source version.

The optional policy sidecar remains `praxis.anvil.project_policy.v1`, with exact Task/version/payload references and original source bytes. Policy identity/version binds its source reference and rules. Different bytes under that policy identity/version conflict. Original documents are retained; bounded text extraction can report Needs text without inventing executable rules. Only explicit applicable `agent_instruction` clauses reach candidate custody. Evaluator-only rules, expectations, engine configuration and credentials do not.

The portable ZIP contains declared regular file entries only, with ASCII relative names and no directory records, symlinks, encryption, aliases, traversal, extra files or external URLs. Limits:26MiB ZIP,30MiB expanded,10MiB per source,1200 entries,1000 imported Tasks,30 environments. These are explicit intake limits, not benchmark capability claims. File hashes, sizes, Project/Task references and policy source references are validated before persistence. Raw import is authenticated before streaming; legacy body limits remain unchanged.

## Setup and execution

Administration → Benchmark methods / Evaluators: both Admin and RL Engineer configure once and test supported capabilities. Import the Project, map applicable rules to compatible Ready configurations and Task/environment scopes, then save a reusable Execution Group. Each Run freezes selected Task versions, agent/model identities, environments, repetitions, method versions, policy sources, evaluator configurations/runtime receipts and execution source. Config edits create new records; they do not rewrite historical results.

The shipped local business runner is deliberately restricted to the exact public fictional banking source and three transparently labelled software controls. It performs real in-memory business-tool effects, records injected-note responses and separate boundary probes, seals those observations, and evaluates them separately. It has no vendor inference, external egress, Harbor/native isolation or formal-proof claim. Other imported sources can be stored and configured; this local adapter cannot silently execute them as the known fixture. Real models and other execution frameworks retain their separate admission/runtime requirements.

At most120 cells execute in one bounded local Run. PostgreSQL owns plans/jobs/captures/scores and immutable result digests. LangGraph owns capture→assessment checkpoints containing IDs/state only. The worker does not automatically reclaim a running/ambiguous job. Stale sources, revoked verifiers or revoked execution membership block work; they cannot produce a Pass. Old source-bound plans are visibly non-runnable and need a newly saved version.

## Results and export

Overview, Evaluations, Tasks & rubrics, Failure modes, Safety, Remediation and Report preview use the same scoped stored projection. The URL preserves Run/Task Group/model/environment/period/method/task/execution selection, including Back/Forward and sidebar return. Rapid filter changes compose against the current URL. The first matching execution selects its own rubric; Task detail and observable output/trace remain accessible.

Policy adherence, injection resistance and simulated environment containment are separate. A prohibited attempt is a policy Fail even when containment blocks it. Missing mappings are Not evaluated, missing facts Unknown, out-of-scope checks N/A. No custom attachment means custom-policy N/A; document-only undefined rules remain Not evaluated. Quality points and safety denominators stay separate. Undefined radar axes are gaps.

PDF/JSON exports require a completed result, actual report-review readiness and the exact displayed view hash. An authenticated Admin Run is exempt; an RL Engineer does not inherit exemption from an Admin-authored plan. Report review count is Admin-configurable0–10 for future Runs, default1. No real source review, spending authority or provider qualification is created by this report exemption.

Remediation JSONL and saved draft packs contain Task input, observed failed rubric expectations, exact evidence IDs, version/environment binding and explicit unverified/rights status. They create neither purchased licenses nor human-verified golden answers. The PDF groups repeated failures without omitting cohort evidence, lists all Task rubrics and executable verifier methodology, and makes original-versus-Custom benchmark availability explicit.

## QA supplement

Add collection-wrapper validation to PRX-Q07–10/ANV-Q15–16, and cross-product tests preserving exact legacy payload bytes. Run UI-Q01 with rapid successive model/environment changes, Back/Forward, reload and sidebar return. Test actual Admin versus RL Engineer executing the **same Admin-authored** plan. Check PDF scope hash, grouped evidence IDs, all rubric rows and separate safety denominators. Never treat fictional software receipts, mocked HTTP contracts or disabled catalog entries as live model/native/vendor qualification.
