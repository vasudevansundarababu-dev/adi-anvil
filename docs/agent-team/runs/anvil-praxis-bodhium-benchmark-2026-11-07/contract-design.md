# Proposed contracts — design only, DRAFT v0.1

This non-executable contract sketch supports human review; it is not an implemented JSON Schema, exporter or Bodhium sample. Bindings and limits are in `architecture.md` and `recovery-report.md`. Exact model/judge IDs, budgets, exhibits and criterion semantics remain missing.

## Bundle contract

```text
manifest.json                     signed manifest; no self-hash
signature.json                    detached signature/profile/key ID; not a trust root
runtime_pack/<task-id>/...         only that task's actor material
eval_pack/<task-id>/...            private rubric/oracle/calibration/templates
```

Member names are canonical relative POSIX paths, without links, leading whitespace, aliases or auto-run hooks. Hash means 64 lowercase SHA-256 hex characters, not an accepted placeholder. Strict duplicate-key/nonfinite/unknown-version rejection applies.

Manifest required fields:
- `schema_version=praxis.anvil.benchmark_bundle.v1`, `signature_profile=ed25519-jcs-v1`, `exporter:{identity,version}`, `bank:{id,version,revision,title}`, `exported_at` UTC.
- `source:{owner,classification,rights_references[]}` preserves actual restricted origin; declarations do not create Anvil grants.
- `files[]:{path,byte_size,sha256,media_type,visibility,task_id}` lists each payload exactly once. Visibility actor/evaluation_private; task binding mandatory. Manifest and detached signature are excluded from their own payload hash list; all other members declared and hashed.
- `tasks[]:{id,version,revision,domain,prompt_path,actor_asset_paths[],outputs[],timeout_seconds,environment,tools,criteria[],constraints[],evaluator_requirement,calibration_paths[]}`. Actor dependencies cannot reach another task or private assets.
- `outputs[]:{path,media_type,required,max_bytes,schema_ref?}` retains original Markdown; any structured sidecar is separately declared/SME-approved. No output path from candidate text.
- `environment:{image_reference,oci_manifest_digest,cpus,memory_mb,pids_limit,network=none}`; tool server version/schema digests and reviewed stdio command declarations. Parsing never executes them.
- `criteria[]:{id,possible_points,evaluator_type,rule_ref,evidence_requirement,applicability_rule}`. Stable IDs are task-bound and unique in the bank by composite identity. Private deterministic rule definitions supply units, scale, rounding, absolute/relative tolerance composition and range endpoint semantics. Semantic rules bind reviewed templates/configurations; no guessed keyword oracle.
- `scoring:{policy_version,task_maxima,suite_maximum,hard_constraint_policy,valid_trial_policy,display_rounding}`. Bodhium acceptance requires explicit 24/6/51 and 81; another bank declares a compatible profile rather than inheriting a banking constant.
- `compiler_requirement:{profile,version}` and `evaluator_requirement:{registry_id,version,implementation_sha256,image_digest,policy_sha256}` are requirements, not permission to download/run imported code.

`signature.json:{profile,key_id,algorithm,signature_base64}` signs RFC8785 canonical manifest bytes with the proposed Ed25519 profile. Retain both raw and canonical bytes. Roots/key validity/revocations come from installation policy, never the bundle. Unknown signer/unsigned => quarantine, not Verified. A future explicitly approved unverified-source policy cannot waive data rights or qualification.

Idempotent source identity is project + exporter + bank ID/version + exact archive bytes. Same version with changed/repackaged bytes is 409; correction requires successor version. Canonical manifest hash and archive hash are both retained.

## Frozen protocol contract

Add a new discriminated revision `mode=sme_benchmark_v1`; legacy `schemas.Protocol` remains unchanged. Required:
- Exact benchmark/suite revision, ordered task/package/evaluator hashes, source receipt, score/review policies.
- Exactly three `candidate_slots[]:{slot,provider,connection_id,model_profile_version,model_id,config_hash,credential_version_ref,adapter_profile,adapter_hash,sampling,context_limit,output_limit,destination,unsupported_controls[]}`. Credential refs are server-only. Null selections can exist in a draft but cannot freeze/admit.
- Repetitions (pilot two); deterministic order/seed policy; 15 turns/task; all task/tool/resource/output limits; provider/concurrency quotas; valid-trial/retry/cancellation/replacement policy.
- `judge:{binding,template_version,calibration_approval_ref,review_policy}`. Missing judge blocks semantic scoring. Pure deterministic fictional fixture protocols explicitly declare no external judge and software-conformance origin.
- Separate candidate/judge integer micro-USD caps, currency, pricing revision/bounds/expiry, authority expiry and destination rights. Unsupported currency blocks admission; no inferred conversion.
- Subject hash covers complete protocol and every child subject. Changed model/key/policy creates a successor, not a silent rebinding.

## Proposed API payloads

Prefix `P=/api/v1/projects/{project}/workspace/benchmarks`. All commands require existing auth/CSRF/Idempotency-Key and bounded strict DTOs. Success `{data,meta:{request_id}}`; errors preserve current envelope with safe typed detail. These routes do not exist yet.

| Operation | Request fields | Response fields |
| --- | --- | --- |
| Stream `POST P/imports` | Raw archive body/type, filename for display only; project from authenticated URL | receipt_id, archive_sha256, parsed manifest_sha256, source_state, signature_status, task_count, validation operation; exact duplicate same receipt |
| Build/qualify | receipt URL ID, expected_manifest_sha256, adapter_profile, reviewed_evaluator_binding, explicit action | operation_id, package_ids, qualification_refs, state; no private bytes |
| Freeze benchmark | expected_revision/hash, ordered task/package/qualification refs, scoring_policy | immutable benchmark_revision/hash, suite_revision, task/points summary or typed blockers |
| Draft/freeze protocol | Frozen fields above + expected_current_revision for CAS | protocol revision/hash, state, planned_cell_count, redacted configurations |
| Readiness GET | Protocol ID only | ready, subject_hash, computed_at, gates, blockers, nullable candidate/judge/combined estimates and pricing status; no provider/job/reservation |
| Launch | subject_hash, exact candidate/judge caps, expiry, rights confirmations and current Admin scope | run_id, protocol_hash, cells_planned=18, admission/status refs; changed/expired scope => 409 without jobs/reservations |
| Progress/cells/events | cursor, limit (proposed default50/max100), after_event_seq | rows/next_cursor/event_seq, actual counters and distinct lifecycle dimensions |
| Cancel/resume | expected fence/state/hash, reason; checkpoint ref for resume | durable cutoff/transition or safe-resume blocker; ambiguous dispatch never retried |
| Reconcile | attempt/evaluator call, purpose, expected state/fence, provider evidence, actual charge or proven_not_dispatched, rationale | immutable reconciliation revision/reservation state; never a fabricated candidate result |
| Review | exact score revision/hash, assignment, criterion evidence/dispositions, decision/rationale | successor score revision/decision and review state; originals preserved |
| Export | exact scorecard revision, formats, redaction policy | export_id, content hashes/bytes/types and safe refs; rights/auth checked again at download |

Freeze/edit uses expected revision/hash CAS. 428 missing Idempotency-Key; 409 changed body/version/hash/not-ready; 413 size; 422 malformed/incomplete semantics; 202 queued; 404 cross-project/not-found uniformly; 403 same-project role/assignment denied. Typed blockers `{code,layer,fixer,task_id?,action}` never contain private filenames/oracles/key/provider exception dumps.

## Scorecard projection

Model row contains exact provider/model/version/protocol; planned/completed/valid/scored counts; completion status; nullable primary `{earned_points,possible_points,percent}`; diagnostic scores with included/excluded cells and denominators; task/repetition/criterion outcomes; observed range; candidate/judge/combined cost objects; measured median duration/sample count; evidence/review revisions and origin.

Unknown total cost is null/status unknown, even with a known subtotal. Primary score is null for incomplete required cells; no winner. Public criterion projection excludes private definitions, judge reasoning/prompts and credential refs; evidence points only to authorized sealed outputs. JSON/CSV/redacted report derive from the same immutable projection; CSV formula escaping and inert Markdown viewing required. Short-lived download refs never replace project/rights checks.

Illustrative blocker only, not a stored measurement: ready=false; source_exhibits_missing/package/engineer; judge_binding_missing/setup/admin; estimates unknown. No absent model, budget or score is filled in.
