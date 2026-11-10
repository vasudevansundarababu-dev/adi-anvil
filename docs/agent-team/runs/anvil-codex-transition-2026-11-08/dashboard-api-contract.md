# Replacement dashboard API contract v1 (implementation contract)

Base: `/api/v1/projects/{project}/workspace/benchmarks`.

Query: repeated `model` exact opaque model keys; `task=all|<task UUID>|suite:<revision UUID>`; `period=all|7d|30d` (UTC sliding completion/record timestamp); `environment=all|<actual recorded key>`; optional UUID `run_id`, `score_revision_id`, `trace_id`; optional `cluster` categorical key. No prompts/secrets in URLs. `view` is pathname only: `/benchmarks`, `/benchmarks/trace`, `/benchmarks/failures`, `/benchmarks/remediation`. Preserve query across navigation, reload and exports.

`GET /dashboard` returns the normal `{data: ...}` wrapper:

```typescript
type Metric = {status: string; value: string | number | null; reason: string | null};
type Score = {earned_points: string; possible_points: string; percent: string};
type Trace = {
 id: string; kind: 'comparison_cell'|'historical_control'; label: string;
 task_key: string; task_label: string; model_key: string|null; model_label: string;
 run_id: string|null; state: string; validity: string|null; origin: string;
 environment: string; recorded_at: string; duration_ms: number|null;
 points: Score|null; official: boolean; review_state: string;
 failure_tags: string[]; severity: 'none'|'low'|'medium'|'high'|'critical';
 evidence_available: boolean; source_sha256: string|null;
};
type Dashboard = {
 schema_version: 'anvil-dashboard-v1'; generated_at: string; snapshot_sha256: string;
 context: {model: string[]; task: string; period: string; environment: string;
   run_id: string|null; score_revision_id: string|null; trace_id: string|null; cluster: string|null};
 options: {models: {key:string;label:string;provider:string}[];
   tasks: {key:string;label:string}[]; environments:{key:string;label:string}[]};
 origin_notice: string; limitations: string[];
 overview: {leader: {model_key:string;model_id:string;percent:string}|null;
   average_score_percent:string|null; total_traces:number; model_trace_count:number;
   control_trace_count:number; ranked_models:number;
   models:{key:string;model_key:string;provider:string;model_id:string;suite_key:string;
     primary:Score|null;diagnostic:Score|null;review_state:string;run_count:number;
     scored_cells:number;planned_cells:number;duration_ms:number|null;
     cost_micro_usd:number|null;judge:Metric;logprobs:Metric}[];
   ranking:{observed_win_rate:{status:string;method:string;pair_count:number;
      rows:{model_key:string;wins:number;losses:number;ties:number;matchups:number;percent:string}[]};
    bradley_terry:{status:string;method:string;tie_policy:string;pair_count:number;
      rows:{model_key:string;relative_strength:string;rank:number}[];iterations:number;reason:string|null}}};
 traces:Trace[];
 failures:{eligible_traces:number;failed_traces:number;error_rate_percent:string|null;
   control_traces:number;infrastructure_events:number;
   categories:{key:string;label:string;count:number;severity:string}[];
   heatmap:{model_key:string;task_key:string;count:number;severity:string}[];
   traces:Trace[]};
 availability:{judge:Metric;logprobs:Metric;retrieval_noise:Metric;multi_step_drift:Metric};
 report:{path:string;raw_prompts_included:false};
};
```

`GET /dashboard/traces/{trace_id}` returns `{trace:Trace, snapshot_sha256:string, steps:{id:string;kind:string;label:string;status:string;content:string}[], outputs:{path:string;sha256:string;byte_size:number;text:string|null}[], criteria:{criterion_id:string;earned_points:string;possible_points:string}[], judge:Metric, logprobs:Metric, limitations:string[]}`. Content is observable/supplied public text, never hidden reasoning/private evaluator data. Access is rechecked after bounded reads. Historical controls are explicit non-model/non-ranking records and never restore qualification currency.

`GET /dashboard/report` accepts the same query plus optional `snapshot_sha256`; a stale supplied snapshot yields409. Returns an actual PDF for the exact filtered redacted projection, fictional/control provenance and unavailable metrics included. No raw prompts by default. No paid calls or mutations from any read/export.

Task filter preserves existing scoring: suite primary uses stored reviewed81-point result; task slices use mean of the two original reviewed cell observations at that task's own denominator, explicitly selected-task observations. No best retries. Multiple incompatible suites have no aggregate leader/BT until narrowed. Unreviewed scores are diagnostics only. Controls never count as active model endpoints, reviewed models, model failures or matchups.

Golden/remediation routes are separately owned by Testing; no dashboard read creates a review, assignment, run or verified golden case. Primary/ranking unavailable when real review gates are pending.

The final DTO also includes `curation:{datasets,case_versions,verified_cases,proposals,blocked_intents,cases,proposal_refs}`. Case references contain only ID, case key, revision, content digest and current status; proposal references contain only ID/status. Reports exclude input text, expected answers and proposed prompts. `overview.models[].reviewed_run_count` is distinct from all stored runs. Trace `severity_basis` and failure `classification_basis`/`rate_basis` identify rule-derived priority rather than calibrated risk. Cluster focus narrows trace inspection and linked curation; overview and failure-rate denominators retain the base model/task/time/environment cohort.
