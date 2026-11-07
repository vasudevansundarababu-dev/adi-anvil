// Explanation copy is presentation only: the server's readiness response is the sole
// ready/blocked authority. All wording here is DRAFT pending Product Owner review (D-COPY).
// Keep this module import-free so `node --test` can load it with type stripping.

export type Fixer = 'engineer' | 'admin' | 'operator';
export type Layer = 'package' | 'setup' | 'admission';
// `models` and `frameworks` are Admin-only workspace sections; `run` is the Run button itself.
export type Action =
  | 'models'
  | 'frameworks'
  | 'configure'
  | 'groups'
  | 'tasks'
  | 'escalate'
  | 'run';
type Entry = {
  layer: Layer;
  fixer: Fixer;
  action: Action;
  engineerAction?: Action;
  text: string;
  engineerText?: string;
};

export const UNKNOWN_REASON_TEXT =
  "This run is blocked by a condition Anvil can't describe yet. Ask a project Admin to review it.";
export const CODE_FORMAT = /^[a-z][a-z0-9_]{0,63}$/;
const OPERATOR = ' Contact your Anvil administrator.';

export const reasonCatalog: Record<string, Entry> = {
  admin_run_authorization_required: {
    layer: 'admission',
    fixer: 'admin',
    action: 'run',
    text: 'Select Run to authorize this exact configuration and its budget.',
    engineerText: 'An Admin must start this run to authorize its budget.',
  },
  aggregate_api_cap_missing: {
    layer: 'admission',
    fixer: 'engineer',
    action: 'configure',
    text: 'No aggregate API budget is set. Create a run configuration with an explicit budget.',
  },
  group_cap_below_conservative_cost_or_above_authority: {
    layer: 'admission',
    fixer: 'engineer',
    action: 'configure',
    text: 'The budget is below the estimated cost ceiling or above the authorized limit. Create a run configuration with a budget inside that range.',
  },
  reserved_spend_window_inactive_or_insufficient: {
    layer: 'admission',
    fixer: 'admin',
    action: 'configure',
    text: 'The reserved budget for this run is no longer active or is too small. Authorize a new run before more models can start.',
    engineerText:
      'The reserved budget for this run is no longer active or is too small. Ask a project Admin to authorize a new run.',
  },
  live_dispatch_disabled_in_runtime: {
    layer: 'admission',
    fixer: 'operator',
    action: 'escalate',
    text: 'Model execution is turned off on this Anvil server, so no run can start.' + OPERATOR,
  },
  model_cost_support_unavailable: {
    layer: 'admission',
    fixer: 'operator',
    action: 'escalate',
    text: 'Anvil has no cost estimate for this model, so it cannot be budgeted.' + OPERATOR,
  },
  model_cost_support_expired: {
    layer: 'admission',
    fixer: 'operator',
    action: 'escalate',
    text: 'The cost estimate for this model is out of date.' + OPERATOR,
  },
  execution_cost_snapshot_changed: {
    layer: 'setup',
    fixer: 'engineer',
    action: 'configure',
    text: 'The cost estimate changed after this configuration was saved. Select Update configuration to use the current estimate.',
  },
  adapter_changed_create_new_execution_group: {
    layer: 'setup',
    fixer: 'engineer',
    action: 'configure',
    text: 'Anvil execution settings changed after this configuration was saved. Select Update configuration.',
  },
  execution_group_required: {
    layer: 'setup',
    fixer: 'engineer',
    action: 'configure',
    text: 'Create an execution group to review cost, authorization and launch readiness.',
  },
  execution_group_not_launched: {
    layer: 'setup',
    fixer: 'engineer',
    action: 'groups',
    text: 'This model run belongs to an execution group that has not started. Start it from the execution group dashboard.',
  },
  exact_package_binding_changed: {
    layer: 'package',
    fixer: 'engineer',
    action: 'configure',
    text: 'The executable package bound to this configuration is no longer available as saved. Create a new run from the current package.',
  },
  initiator_access_revoked: {
    layer: 'setup',
    fixer: 'admin',
    action: 'configure',
    engineerAction: 'configure',
    text: 'The person who created this configuration no longer has run access in this project. Create a new run configuration.',
    engineerText:
      'The person who created this configuration no longer has run access in this project. Create a new run configuration or ask a project Admin.',
  },
  credential_missing: {
    layer: 'setup',
    fixer: 'admin',
    action: 'models',
    text: 'This model has no saved API key. Link a key in Models & keys, then select the new model version in a new run.',
    engineerText:
      'This model has no saved API key. Ask a project Admin to link one in Models & keys.',
  },
  credential_revoked_or_unavailable: {
    layer: 'setup',
    fixer: 'admin',
    action: 'models',
    text: 'The saved API key is revoked or unavailable. Link an active key to a new model version.',
    engineerText:
      'The saved API key is revoked or unavailable. Ask a project Admin to link an active key.',
  },
  bound_credential_rotated: {
    layer: 'setup',
    fixer: 'admin',
    action: 'models',
    text: 'The API key was rotated. Select a model version linked to its current key version.',
    engineerText:
      'The API key was rotated. Ask a project Admin for a model version linked to the current key.',
  },
  model_profile_disabled: {
    layer: 'setup',
    fixer: 'admin',
    action: 'models',
    text: 'This model profile is disabled for new runs. An Admin must enable it or a different model must be selected.',
  },
  model_version_mapping_missing: {
    layer: 'setup',
    fixer: 'admin',
    action: 'models',
    text: 'This model version is not linked to a model profile. An Admin must select a current model version.',
  },
  model_version_superseded: {
    layer: 'setup',
    fixer: 'admin',
    action: 'frameworks',
    text: 'A newer version of this model exists. An Admin must create a preset with the current version.',
  },
  model_revoked_or_unavailable: {
    layer: 'setup',
    fixer: 'admin',
    action: 'configure',
    engineerAction: 'configure',
    text: 'This model profile is revoked or unavailable. Select a different model.',
    engineerText:
      'This model profile is revoked or unavailable. Select a different model or ask a project Admin.',
  },
  model_configuration_changed: {
    layer: 'setup',
    fixer: 'admin',
    action: 'frameworks',
    text: 'This model profile changed after the configuration was saved. Create a preset with its current version.',
    engineerText:
      'This model profile changed after the configuration was saved. Ask a project Admin for a preset with its current version.',
  },
  selected_output_limit_exceeds_profile: {
    layer: 'setup',
    fixer: 'engineer',
    action: 'configure',
    text: 'The output-token limit is higher than this model profile allows. Lower it in a new run configuration.',
  },
  candidate_runtime_not_qualified: {
    layer: 'setup',
    fixer: 'engineer',
    action: 'configure',
    text: 'The selected candidate runtime is not qualified for execution. Choose a preset with a qualified runtime.',
  },
  external_tracing_not_qualified_export_disabled: {
    layer: 'setup',
    fixer: 'engineer',
    action: 'configure',
    text: 'External tracing is not qualified and export stays off. Choose a preset without external tracing.',
  },
  framework_binding_changed_or_unavailable: {
    layer: 'setup',
    fixer: 'admin',
    action: 'frameworks',
    text: 'A framework bound to this preset changed or is unavailable. Create a preset with current frameworks.',
    engineerText:
      'A framework bound to this preset changed or is unavailable. Ask a project Admin for an updated preset.',
  },
  provider_task_adapter_not_supported: {
    layer: 'setup',
    fixer: 'operator',
    action: 'configure',
    text: "This model's provider is not supported for task execution. Select an OpenAI, Anthropic or Gemini model.",
  },
  task_binding_not_supported: {
    layer: 'package',
    fixer: 'operator',
    action: 'escalate',
    text: "This task's package format is not supported by the execution adapter." + OPERATOR,
  },
  package_runtime_not_supported: {
    layer: 'package',
    fixer: 'operator',
    action: 'escalate',
    text: "This package targets a Harbor version this server doesn't run." + OPERATOR,
  },
  package_agent_admission_missing: {
    layer: 'package',
    fixer: 'engineer',
    action: 'tasks',
    text: 'This package was built before current agent checks existed. Rebuild the package, then create a new run.',
  },
  // Retained for older saved records; not produced by current readiness code.
  workspace_dispatch_not_qualified: {
    layer: 'admission',
    fixer: 'operator',
    action: 'escalate',
    text: 'Live execution for workspace profiles is not available yet.' + OPERATOR,
  },
  current_pricing_not_bound: {
    layer: 'admission',
    fixer: 'engineer',
    action: 'configure',
    text: 'Current pricing was not bound to this configuration. Create a new run configuration.',
  },
  reviewed_pricing_admission_not_bound: {
    layer: 'admission',
    fixer: 'engineer',
    action: 'configure',
    text: 'Pricing has not been reviewed for this exact evaluation. Create a new run configuration.',
  },
  pricing_metadata_missing: {
    layer: 'admission',
    fixer: 'admin',
    action: 'models',
    text: 'Pricing details are missing for this model.',
    engineerText: 'Pricing details are missing for this model. Ask a project Admin.',
  },
  pricing_metadata_expired: {
    layer: 'admission',
    fixer: 'admin',
    action: 'models',
    text: 'Pricing details for this model have expired.',
    engineerText: 'Pricing details for this model have expired. Ask a project Admin.',
  },
  pricing_metadata_invalid: {
    layer: 'admission',
    fixer: 'admin',
    action: 'models',
    text: 'Pricing details for this model are invalid.',
    engineerText: 'Pricing details for this model are invalid. Ask a project Admin.',
  },
  exact_user_authority_not_bound: {
    layer: 'admission',
    fixer: 'admin',
    action: 'configure',
    text: 'No spending authorization is attached to this configuration.',
    engineerText: 'No spending authorization is attached. An Admin must start this run.',
  },
  processing_rights_not_bound: {
    layer: 'admission',
    fixer: 'admin',
    action: 'configure',
    text: 'No processing-rights decision is attached to this configuration.',
    engineerText: 'No processing-rights decision is attached. An Admin must start this run.',
  },
  required_run_decisions_not_bound: {
    layer: 'admission',
    fixer: 'admin',
    action: 'configure',
    text: 'Required run approvals are not attached to this configuration.',
    engineerText: 'Required run approvals are not attached. An Admin must start this run.',
  },
  shared_spending_admission_not_implemented: {
    layer: 'admission',
    fixer: 'operator',
    action: 'escalate',
    text: 'Shared spending controls are not ready for these models.' + OPERATOR,
  },
  provider_task_adapter_not_qualified: {
    layer: 'setup',
    fixer: 'operator',
    action: 'escalate',
    text: 'The provider/task adapter is not qualified for this model.' + OPERATOR,
  },
};

export const safeDiagnostic = (code: unknown) =>
  typeof code === 'string' && CODE_FORMAT.test(code) ? code : null;

export type ReasonItem = {
  code: string | null;
  subject: string | null;
  text: string;
  diagnostic: string | null;
  known: boolean;
  layer: Layer | null;
  fixer: Fixer;
  fixerLabel: string;
  action: Action;
};

const fixerLabel = (fixer: Fixer, canAdmin: boolean) =>
  fixer === 'operator'
    ? 'Who can fix: your Anvil administrator'
    : fixer === 'admin'
      ? canAdmin
        ? 'Who can fix: you (Admin)'
        : 'Who can fix: a project Admin'
      : 'Who can fix: you';

export function describeReason(reason: unknown, canAdmin = false, subject?: string): ReasonItem {
  const entry =
    typeof reason === 'string' && Object.hasOwn(reasonCatalog, reason)
      ? reasonCatalog[reason]
      : undefined;
  if (!entry)
    return {
      code: null,
      subject: subject || null,
      text: UNKNOWN_REASON_TEXT,
      diagnostic: safeDiagnostic(reason),
      known: false,
      layer: null,
      fixer: 'admin',
      fixerLabel: fixerLabel('admin', canAdmin),
      action: 'escalate',
    };
  return {
    code: reason as string,
    subject: subject || null,
    text: canAdmin ? entry.text : entry.engineerText || entry.text,
    diagnostic: null,
    known: true,
    layer: entry.layer,
    fixer: entry.fixer,
    fixerLabel: fixerLabel(entry.fixer, canAdmin),
    action: viewerAction(entry, canAdmin),
  };
}

const ADMIN_ONLY: ReadonlySet<Action> = new Set(['models', 'frameworks', 'run']);

// Engineers never get an Admin-only destination: Admin-fixed blockers escalate instead.
function viewerAction(entry: Entry, canAdmin: boolean): Action {
  if (canAdmin) return entry.action;
  const action = entry.fixer === 'admin' ? entry.engineerAction || 'escalate' : entry.action;
  return ADMIN_ONLY.has(action) ? 'escalate' : action;
}

export type ActionDestinations = {
  workspace: string;
  configure: string;
  share: string;
  run?: string;
};

export type ActionLink = { label: string; href: string };

// One link per blocker. `share` is the current page, so an escalation link never
// points an Engineer at a page they cannot use.
export function actionLink(
  item: ReasonItem,
  canAdmin: boolean,
  to: ActionDestinations,
): ActionLink {
  const action = !canAdmin && ADMIN_ONLY.has(item.action) ? 'escalate' : item.action;
  switch (action) {
    case 'run':
      return to.run
        ? { label: 'Go to Run to authorize this run', href: to.run }
        : { label: 'Create an execution group to authorize a run', href: to.configure };
    case 'models':
      return { label: 'Open Models & keys', href: to.workspace + '/models' };
    case 'frameworks':
      return { label: 'Open Frameworks & presets', href: to.workspace + '/frameworks' };
    case 'configure':
      return { label: 'Change run configuration', href: to.configure };
    case 'groups':
      return { label: 'Open Execution groups', href: to.workspace + '/execution-groups' };
    case 'tasks':
      return { label: 'Open Tasks to rebuild the package', href: to.workspace + '/tasks' };
  }
  return {
    label:
      item.fixer === 'operator' || (canAdmin && !item.known)
        ? 'Link to this page for your Anvil administrator'
        : 'Link to this page for a project Admin',
    href: to.share,
  };
}

export const describeRunReason = (reason: string, canAdmin = false) =>
  describeReason(reason, canAdmin).text;

export type RunReadiness = {
  missing: string[];
  models: { model_profile_id: string; model?: string; missing: string[] }[];
};

// The Admin exception mirrors existing behavior: an Admin's Run click is the authorization.
export function runBlockerItems(readiness: RunReadiness, canAdmin: boolean): ReasonItem[] {
  const seen = new Set<string>();
  const items: ReasonItem[] = [];
  const add = (reason: string, subject?: string) => {
    const key = (subject || '') + '\u0000' + reason;
    if (seen.has(key)) return;
    seen.add(key);
    items.push(describeReason(reason, canAdmin, subject));
  };
  readiness.missing
    .filter((reason) => reason !== 'admin_run_authorization_required' || !canAdmin)
    .forEach((reason) => add(reason));
  readiness.models.forEach((model) => model.missing.forEach((reason) => add(reason, model.model)));
  return items;
}

export const itemText = (item: ReasonItem) =>
  (item.subject ? item.subject + ': ' : '') +
  item.text +
  (item.diagnostic ? ' (Diagnostic code: ' + item.diagnostic + ')' : '');

export function runBlockers(readiness: RunReadiness, canAdmin: boolean) {
  return [...new Set(runBlockerItems(readiness, canAdmin).map(itemText))];
}

const MODEL_SELECTION_PREFIX = 'Select an enabled current model version: ';

// Replaces the raw codes in the model-selection 409 detail (workspace_preparation.model)
// with catalog text. Returns null for any other message so it is shown unchanged.
export function modelSelectionMessage(message: string): string | null {
  if (!message.startsWith(MODEL_SELECTION_PREFIX)) return null;
  const codes = message.slice(MODEL_SELECTION_PREFIX.length).split(', ');
  if (!codes.every((code) => CODE_FORMAT.test(code))) return UNKNOWN_REASON_TEXT;
  return (
    "This model selection can't be used. " +
    [...new Set(codes.map((code) => itemText(describeReason(code))))].join(' ')
  );
}

export type ImportStateExplanation = {
  label: string;
  reason: string;
  next: string;
  tone: 'ready' | 'draft' | 'failed';
  diagnostic: string | null;
};

const REPORT = 'Open the task and review the import validation report';
export const importStates: Record<string, Omit<ImportStateExplanation, 'diagnostic'>> = {
  queued: {
    label: 'Queued for generation',
    reason: 'Waiting for the generation worker to start.',
    next: 'Open the task to follow live progress.',
    tone: 'draft',
  },
  generating: {
    label: 'Generating checks',
    reason: 'The configured generation model is writing executable verifiers and constraints.',
    next: 'Open the task to follow live progress.',
    tone: 'draft',
  },
  validating: {
    label: 'Validating',
    reason: 'Generated checks are being tested against the supplied tools and fixtures.',
    next: 'Open the task to follow live progress.',
    tone: 'draft',
  },
  needs_clarification: {
    label: 'Needs clarification',
    reason: 'Generation stopped because part of the task needs clarification.',
    next: REPORT + ', then revise the task or edit the generated Python.',
    tone: 'draft',
  },
  generation_failed: {
    label: 'Generation failed',
    reason: 'Executable checks could not be generated.',
    next: REPORT + ' for details.',
    tone: 'failed',
  },
  validation_failed: {
    label: 'Validation failed',
    reason: 'Generated checks did not pass required validation.',
    next: REPORT + ', then inspect or edit the generated Python.',
    tone: 'failed',
  },
  ready: {
    label: 'Ready to run',
    reason:
      'A validated executable package exists. Models, keys, budget and authorization are checked separately when you run.',
    next: 'Select Run to choose models and a budget.',
    tone: 'ready',
  },
};

export function explainImportState(state: unknown): ImportStateExplanation {
  const entry =
    typeof state === 'string' && Object.hasOwn(importStates, state)
      ? importStates[state]
      : undefined;
  if (entry) return { ...entry, diagnostic: null };
  return {
    label: 'Needs attention',
    reason: "This import stopped in a state Anvil can't describe yet.",
    next: 'Open the import report or ask a project Admin.',
    tone: 'draft',
    diagnostic: safeDiagnostic(state),
  };
}
