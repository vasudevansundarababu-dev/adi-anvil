# Fictional software rehearsal and report authorization

This is a separate software execution workflow. It never creates official benchmark comparisons, qualifications, source reviews, model bindings or evaluator approvals. Candidate functions receive only the public items. A separate function derives squares independently by repeated addition; private `eval_pack` inputs are never loaded.

## Availability

Rehearsal routes require current project Admin/Engineer access and all three explicit settings: `ANVIL_ENV=local`, `ANVIL_BENCHMARK_REHEARSAL_ENABLED=true`, `ANVIL_LOCAL_FIXTURE_ENABLED=true`. Provider/live/Vertex/email flags must remain false. These flags do not authorize paid calls or deployment. The execution environment is `local_builtin_trusted_functions`, not native container isolation.

## Routes

All routes use `/api/v1/projects/{project}/workspace/benchmarks` and the existing `{data,meta}` envelope and idempotency mechanism.

- `POST /rehearsals`: `{name}`. Creates an immutable source/profile/input manifest and snapshots the current report policy; does not execute.
- `GET /rehearsals?limit=25&after={uuid}`: `{items,next_cursor}` with bounded cursor pagination.
- `GET /rehearsals/{id}`: actual persisted draft, failed or completed record. Pending report authorization does not hide execution evidence.
- `POST /rehearsals/{id}/execute`: `{expected_manifest_sha256}`. A locked, synchronous bounded execution. Terminal results are immutable; repeated execution returns the existing result. Source changes before or during execution reject the transaction without recording a new result. Unexpected execution failures store a sanitized failed outcome.
- `GET /report-review-policy`: current project policy with `required_reviewers`, `revision`, `policy_sha256`. Safe default is one reviewer. This settings route requires the benchmark feature; it does not require the optional rehearsal feature.
- `POST /report-review-policy`: authenticated project Admin only; `{required_reviewers:0..10,rationale?:string}`. Appends a policy revision without altering existing snapshots.
- `POST /rehearsals/{id}/report-review`: `{expected_result_sha256,assignment_id,human_reviewed:true,rationale}`. Records one real current individual duty/actor per exact result, never an automatic approval.
- `POST /rehearsals/{id}/report-approval`: authenticated project Admin only; `{expected_result_sha256,rationale}`. Records explicit exact-result Admin authorization.
- `POST /comparisons/{run_id}/report-approval`: equivalent explicit authenticated Admin authorization for an exact official score projection; current source/export rights remain required.

## Stored execution

There are exactly three versioned scripted profiles: square every integer, square the first six public items then use identity, and square even integers then use identity. Each executes two repetitions of FX-001 (24 criteria), FX-002 (6) and FX-003 (51): 18 actual cells. Outputs, output hashes, per-criterion points, measured duration, declared arithmetic failure tags and observable steps are stored. No scores or ties are inserted by a fixture answer table.

`result.profiles` contains both full-suite repetition totals and their mean out of81. `result.ranking` contains separate observed wins/ties and Bradley–Terry estimates over matched scripted profiles. The algorithm may truthfully return an unavailable fitted estimate; no pseudocount repair is used. These are fictional-profile software metrics, never model rankings. Filtering trace inspection does not silently replace this full-suite ranking basis.

Every record has `origin=fictional_scripted_rehearsal`, `model_performance=false`, `provider_calls=0`, and `official_primary=null`. Completed results include their immutable `result_sha256`; failed results contain a safe failure code rather than invented cells or scores.

## Report authorization is not human verification

`report_authorization` includes `ready`, `state`, `required_reviewers`, `completed_reviewers`, `policy_sha256`, `admin_actor_id`, and `reviewer_verified`. States are `pending_review`, `reviewed`, `admin_run_exempt`, `admin_approved`, or `policy_no_review`. Only `reviewed` asserts human reviewer verification. An actual authenticated Admin execution is recorded independently from the draft creator. An Admin-created draft executed by an Engineer does not acquire an Admin-run exemption. An Engineer-created draft actually executed by an Admin does.

PDF generation calls `rehearsal.require_report(c,row)` and requires completed execution plus the stored authorization policy. Evidence remains inspectable while report authorization is pending. Report authorization does not alter source rights, qualifications, paid admission, deployment approval or official scoring criteria.

## Official protocol compatibility

Legacy version1 policy serialization and hashes are preserved; its immutable first/second/adjudicator records are not rewritten. Version2 uses a bounded list of distinct reviewer assignments and server-frozen project report policy, retaining exact task thresholds and calibration. Admin-run/no-review release produces explicit authorization provenance and `reviewer_verified=false`, with no fabricated legacy review rows. Complete official scores can be released under this authority; incomplete executions retain null primary values. Runtime changes require honest new source binding and qualification evidence; old native evidence is not relabelled.
