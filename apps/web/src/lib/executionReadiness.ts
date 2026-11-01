export type RunReadiness = {
  missing: string[];
  models: { model_profile_id: string; model?: string; missing: string[] }[];
};

const messages: Record<string, string> = {
  admin_run_authorization_required: 'An Admin must start this run to authorize its budget.',
  credential_missing:
    'Select a saved API key for this model in Models & keys, then select the updated model version in a new run.',
  credential_revoked_or_unavailable:
    'The saved API key is revoked or unavailable. Link an active key to a new model version.',
  bound_credential_rotated:
    'The API key was rotated. Select a model version linked to its current key version.',
  live_dispatch_disabled_in_runtime: 'Live execution is disabled on this server.',
  model_cost_support_unavailable: 'This model is not supported by the current Anvil cost catalog.',
  model_cost_support_expired: 'Anvil’s cost catalog for this model needs an update.',
  execution_cost_snapshot_changed: 'Select Update configuration to bind the current cost estimate.',
  adapter_changed_create_new_execution_group:
    'Select Update configuration to use the current execution settings.',
  group_cap_below_conservative_cost_or_above_authority:
    'The budget is below the estimated ceiling or above the authorized limit. Create a run with a sufficient budget.',
  aggregate_api_cap_missing: 'Enter an aggregate API budget for the run.',
  selected_output_limit_exceeds_profile:
    'The selected output-token limit exceeds this model profile’s limit.',
  candidate_runtime_not_qualified: 'The selected candidate runtime is not qualified for execution.',
  external_tracing_not_qualified_export_disabled:
    'This tracing configuration is not qualified. Select a preset without external tracing.',
  model_version_superseded:
    'This model version has been superseded. Create a run using its current version.',
};

export const describeRunReason = (reason: string) =>
  messages[reason] || reason.replaceAll('_', ' ');
export function runBlockers(readiness: RunReadiness, canAdmin: boolean) {
  return [
    ...new Set([
      ...readiness.missing
        .filter((reason) => reason !== 'admin_run_authorization_required' || !canAdmin)
        .map(describeRunReason),
      ...readiness.models.flatMap((model) =>
        model.missing.map(
          (reason) => (model.model ? model.model + ': ' : '') + describeRunReason(reason),
        ),
      ),
    ]),
  ];
}
