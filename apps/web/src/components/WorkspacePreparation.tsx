'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Form from './Form';
import { shortId, workspaceApi as api } from '../lib/workspace';
import { runBlockers } from '../lib/executionReadiness';
import styles from './ModernWorkspace.module.css';

type Model = {
  id: string;
  name: string;
  provider: string;
  model_id: string;
  config_hash: string;
  workspace_profile?: boolean;
  status?: string;
  max_output_tokens: number;
  credential_name?: string | null;
  credential_state?: string;
};
type Framework = { id: string; name: string; framework: string };
type Preset = {
  id: string;
  subject_hash: string;
  snapshot: {
    name: string;
    models: Model[];
    candidate_runtime: string;
    runner: Framework;
    candidate?: Framework | null;
    tracing: Framework | null;
  };
};
type Package = {
  id: string;
  title: string;
  package_sha256: string;
  manifest: { task_id: string; task_version: string };
};
type Draft = {
  id: string;
  subject_hash: string;
  snapshot: {
    models: Model[];
    package: Package;
    preset: Preset['snapshot'];
    aggregate_cap_micro_usd: number | null;
    max_output_tokens: number;
  };
  readiness: { missing: string[]; models: { model_profile_id: string; missing: string[] }[] };
};

function useList<T>(path: string | null, revision = 0, all = false) {
  const [items, setItems] = useState<T[]>([]),
    [cursor, setCursor] = useState<string | null>(null),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(true);
  const generation = useRef(0);
  const load = useCallback(
    async (after?: string) => {
      const current = ++generation.current;
      if (!path) {
        setLoading(false);
        return;
      }
      setLoading(true);
      setError('');
      try {
        let result = await api(
          path + (after ? (path.includes('?') ? '&' : '?') + 'after=' + after : ''),
        );
        const items = [...result.items];
        const seen = new Set<string>();
        while (all && result.next_cursor && current === generation.current) {
          if (seen.has(result.next_cursor)) throw new Error('Model pagination did not advance.');
          seen.add(result.next_cursor);
          result = await api(
            path +
              (path.includes('?') ? '&' : '?') +
              'after=' +
              encodeURIComponent(result.next_cursor),
          );
          items.push(...result.items);
        }
        if (current === generation.current) {
          setItems((old) => (after ? [...old, ...items] : items));
          setCursor(result.next_cursor);
        }
      } catch (e) {
        if (current === generation.current) setError((e as Error).message);
      } finally {
        if (current === generation.current) setLoading(false);
      }
    },
    [path, all],
  );
  useEffect(() => {
    setItems([]);
    void load();
    return () => {
      generation.current++;
    };
  }, [load, revision]);
  useEffect(() => {
    if (!all) return;
    const refresh = () => void load();
    window.addEventListener('focus', refresh);
    return () => window.removeEventListener('focus', refresh);
  }, [all, load]);
  return {
    items,
    error,
    loading,
    reload: () => load(),
    more: cursor ? () => load(cursor) : undefined,
  };
}

function VersionChoice({
  id,
  label,
  name,
  choices,
  complete,
  loading,
  value,
  change,
}: {
  id: string;
  label: string;
  name?: string;
  choices: { id: string; label: string }[];
  complete: boolean;
  loading: boolean;
  value?: string;
  change?: (value: string) => void;
}) {
  if (loading) return <p role="status">Loading {label.toLowerCase()}…</p>;
  if (complete && choices.length === 1)
    return (
      <div>
        <strong>{label}</strong>
        <p>{choices[0].label}</p>
        <input id={id} type="hidden" name={name} value={choices[0].id} />
      </div>
    );
  return (
    <>
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        name={name}
        required
        {...(value === undefined ? { defaultValue: '' } : { value })}
        onChange={change ? (e) => change(e.target.value) : undefined}
      >
        <option value="" disabled>
          Select a saved version
        </option>
        {choices.map((choice) => (
          <option key={choice.id} value={choice.id}>
            {choice.label}
          </option>
        ))}
      </select>
    </>
  );
}

function ToggleModels({
  models,
  selected,
  change,
  showKeys = false,
  allowedIds,
}: {
  models: Model[];
  selected: string[];
  change: (ids: string[]) => void;
  showKeys?: boolean;
  allowedIds?: string[];
}) {
  const [search, setSearch] = useState('');
  const visible = models.filter(
    (m) =>
      !showKeys ||
      [m.name, m.provider, m.model_id, m.credential_name]
        .join(' ')
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  return (
    <fieldset>
      <legend>{showKeys ? 'Available models & linked keys' : 'Model profiles for planning'}</legend>
      <p className={styles.muted}>
        Select exact saved versions. Execution requires current bindings and explicit authorization.
      </p>
      {showKeys && (
        <>
          <label>
            Search models and keys
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Model, provider or saved key name"
            />
          </label>
          <p>{selected.length} selected · Up to 8 models</p>
        </>
      )}
      {visible.map((m) => (
        <label key={m.id} style={{ display: 'block' }}>
          <input
            type="checkbox"
            checked={selected.includes(m.id)}
            disabled={
              m.status === 'revoked' ||
              m.status === 'disabled' ||
              (!!allowedIds && !allowedIds.includes(m.id))
            }
            onChange={(e) =>
              change(
                e.target.checked
                  ? Array.from(new Set([...selected, m.id]))
                  : selected.filter((id) => id !== m.id),
              )
            }
          />
          {m.name} · {m.provider}/{m.model_id} · {shortId(m.id)}
          {showKeys && (
            <small style={{ display: 'block', marginLeft: 24 }}>
              Key: {m.credential_name || 'No saved key linked'}
              {m.credential_state && m.credential_state !== 'configured'
                ? ' · ' + m.credential_state
                : ''}
              {allowedIds && !allowedIds.includes(m.id)
                ? ' · Ask an Admin to add this model to the preset'
                : ''}
            </small>
          )}
          {m.status === 'revoked' ? ' · Revoked' : m.status === 'disabled' ? ' · Disabled' : ''}
        </label>
      ))}
      {showKeys && !!models.length && !visible.length && <p>No matching models or linked keys.</p>}
      {!models.length && <p>No workspace model profiles loaded. Configure models first.</p>}
    </fieldset>
  );
}

export function ExecutionPresets({
  base,
  frameworkRevision = 0,
}: {
  base: string;
  frameworkRevision?: number;
}) {
  const models = useList<Model>(base + '/workspace/models?current_only=true');
  const frameworks = useList<Framework>(base + '/workspace/frameworks', frameworkRevision);
  const presets = useList<Preset>(base + '/workspace/presets');
  const [selected, setSelected] = useState<string[]>([]),
    [runtime, setRuntime] = useState('anvil-structured-json-v1'),
    [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [busy, setBusy] = useState(false);
  return (
    <section
      className={styles.panel}
      aria-label="Execution preset configuration"
      aria-busy={models.loading || frameworks.loading || presets.loading}
    >
      <h2>Execution presets</h2>
      {(models.loading || frameworks.loading || presets.loading) && (
        <p role="status">Loading preset choices…</p>
      )}
      <p>
        Save a reusable selection of models, runner and optional integrations. This saves a planning
        configuration; it does not install, connect or run anything.
      </p>
      <button
        onClick={() => {
          void models.reload();
          void frameworks.reload();
          void presets.reload();
        }}
      >
        Refresh preset choices
      </button>
      {[error, models.error, frameworks.error, presets.error].filter(Boolean).map((e, i) => (
        <p key={i} role="alert">
          {e}
        </p>
      ))}
      {message && <p role="status">{message}</p>}
      <Form
        onSubmit={async (e) => {
          e.preventDefault();
          const form = e.currentTarget,
            data = new FormData(form);
          setBusy(true);
          setError('');
          setMessage('');
          try {
            await api(base + '/workspace/presets', 'POST', {
              name: data.get('name'),
              runner_profile_id: data.get('runner'),
              candidate_runtime: runtime,
              candidate_profile_id: runtime === 'semantic_kernel' ? data.get('candidate') : null,
              tracing_profile_id: data.get('tracing') || null,
              model_profile_ids: selected,
            });
            setMessage('Preset saved. Prepare a task to review costs and launch requirements.');
            form.reset();
            setSelected([]);
            setRuntime('anvil-structured-json-v1');
            await presets.reload();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label htmlFor="preset-name">Preset name</label>
        <input id="preset-name" name="name" required maxLength={100} />
        <label htmlFor="preset-runner">Evaluation runner</label>
        <p id="preset-runner-help">
          Select a Harbor framework profile saved in this project. OpenAI, Claude and Gemini model
          profiles are selected below; they are not evaluation runners.
        </p>
        {!frameworks.loading &&
          !frameworks.error &&
          !frameworks.items.some((f) => f.framework === 'harbor') && (
            <p role="status">
              No Harbor runner profiles loaded. Above, choose Configure Harbor, enter a profile name
              and save it. {frameworks.more ? 'Or load more framework choices below.' : ''}
            </p>
          )}
        <select
          id="preset-runner"
          name="runner"
          aria-describedby="preset-runner-help"
          required
          defaultValue=""
        >
          <option value="" disabled>
            Select a Harbor profile
          </option>
          {frameworks.items
            .filter((f) => f.framework === 'harbor')
            .map((f) => (
              <option key={f.id} value={f.id}>
                {f.name} · Harbor 0.25.0
              </option>
            ))}
        </select>
        <label htmlFor="preset-runtime">Candidate runtime</label>
        <select id="preset-runtime" value={runtime} onChange={(e) => setRuntime(e.target.value)}>
          <option value="anvil-structured-json-v1">Anvil structured JSON agent</option>
          <option value="semantic_kernel">Semantic Kernel · adapter unavailable</option>
        </select>
        {runtime === 'semantic_kernel' && (
          <>
            <label htmlFor="preset-candidate">Semantic Kernel profile</label>
            <select id="preset-candidate" name="candidate" required defaultValue="">
              <option value="" disabled>
                Select a Semantic Kernel profile
              </option>
              {frameworks.items
                .filter((f) => f.framework === 'semantic_kernel')
                .map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
            </select>
          </>
        )}
        <label htmlFor="preset-tracing">External tracing</label>
        <select id="preset-tracing" name="tracing" defaultValue="">
          <option value="">None · keep evidence in Anvil</option>
          {frameworks.items
            .filter((f) => f.framework === 'langsmith')
            .map((f) => (
              <option key={f.id} value={f.id}>
                {f.name} · export disabled
              </option>
            ))}
        </select>
        <ToggleModels
          models={models.items.filter((m) => m.workspace_profile)}
          selected={selected}
          change={setSelected}
        />
        {models.more && (
          <button type="button" disabled={models.loading} onClick={() => void models.more?.()}>
            Load more model choices
          </button>
        )}
        {frameworks.more && (
          <button
            type="button"
            disabled={frameworks.loading}
            onClick={() => void frameworks.more?.()}
          >
            Load more framework choices
          </button>
        )}
        <button disabled={busy || !selected.length || selected.length > 8}>
          Save execution preset
        </button>
      </Form>
      <h3>Saved presets</h3>
      {presets.items.map((p) => (
        <details key={p.id}>
          <summary>
            {p.snapshot.name} · {p.snapshot.models.length} model profiles · planning only
          </summary>
          <pre>{JSON.stringify(p.snapshot, null, 2)}</pre>
          <small>Binding {p.subject_hash}</small>
        </details>
      ))}
      {!presets.items.length && <p>No saved execution presets.</p>}
      {presets.more && <button onClick={() => void presets.more?.()}>Load more presets</button>}
    </section>
  );
}

const messages: Record<string, string> = {
  execution_group_required:
    'Create an execution group below to review costs, authorization and launch readiness.',
  workspace_dispatch_not_qualified: 'Live execution for workspace profiles is not available yet.',
  current_pricing_not_bound: 'Current reviewed pricing has not been bound to this preparation.',
  reviewed_pricing_admission_not_bound: 'Pricing still needs review for this exact evaluation.',
  model_profile_disabled: 'This model profile is disabled for all new preparations.',
  model_version_superseded:
    'A newer model version exists. Create a preset with the current version.',
  model_version_mapping_missing: 'This model version has no valid profile mapping.',
  pricing_metadata_missing: 'Declared pricing metadata is missing.',
  pricing_metadata_expired: 'Declared pricing metadata has expired.',
  pricing_metadata_invalid: 'Declared pricing metadata is invalid.',
  exact_user_authority_not_bound: 'No spending authorization is attached to this preparation.',
  processing_rights_not_bound: 'No processing-rights decision is attached to this preparation.',
  required_run_decisions_not_bound: 'Required run approvals are not attached to this preparation.',
  shared_spending_admission_not_implemented:
    'Shared spending controls are not ready for these models.',
  aggregate_api_cap_missing: 'An explicit aggregate API cap is missing.',
  candidate_runtime_not_qualified: 'The selected candidate runtime is not qualified.',
  external_tracing_not_qualified_export_disabled:
    'External tracing is not qualified; export stays disabled.',
  credential_missing: 'Credential missing.',
  credential_revoked_or_unavailable: 'Credential revoked or unavailable.',
  bound_credential_rotated:
    'The bound credential was rotated. Create a new model version and preset.',
  provider_task_adapter_not_qualified: 'Provider/task adapter not qualified.',
  model_revoked_or_unavailable: 'Model profile revoked or unavailable.',
  model_configuration_changed: 'Model configuration changed.',
  selected_output_limit_exceeds_profile:
    'Selected output limit exceeds this model profile ceiling.',
  task_binding_not_supported: 'This task binding is not supported by the planned adapter.',
  package_runtime_not_supported: 'The package runtime does not match the pinned Harbor version.',
  package_agent_admission_missing:
    'Rebuild this package with the current agent admission compiler.',
  framework_binding_changed_or_unavailable: 'A bound framework version changed or is unavailable.',
};

export default function WorkspacePreparation({
  base,
  taskId,
  preparationId,
  open,
  createGroup = false,
  packageId,
  sourceId,
  environments = [],
  runOnSave = false,
  canAuthorizeRun = false,
}: {
  base: string;
  taskId?: string | null;
  preparationId?: string | null;
  open: (id: string, issue?: string) => void;
  createGroup?: boolean;
  packageId?: string;
  sourceId?: string;
  environments?: { id: string; name: string; status: string }[];
  runOnSave?: boolean;
  canAuthorizeRun?: boolean;
}) {
  const packages = useList<Package>(
    base +
      '/workspace/packages' +
      (sourceId
        ? '?source_id=' + encodeURIComponent(sourceId)
        : taskId
          ? '?task_id=' + encodeURIComponent(taskId)
          : ''),
  );
  const presets = useList<Preset>(base + '/workspace/presets');
  const allModels = useList<Model>(
    runOnSave ? base + '/workspace/models?current_only=true&limit=100' : null,
    0,
    true,
  );
  const drafts = useList<Draft>(runOnSave ? null : base + '/workspace/preparations');
  const [presetId, setPresetId] = useState(''),
    [composing, setComposing] = useState(!preparationId),
    [detailLoading, setDetailLoading] = useState(!!preparationId),
    [selected, setSelected] = useState<string[]>([]),
    [saved, setSaved] = useState<Draft | null>(null),
    [refreshKey, setRefreshKey] = useState(0),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const selectedPresetId =
    !presets.loading && !presets.error && !presets.more && presets.items.length === 1
      ? presets.items[0].id
      : presetId;
  const preset = presets.items.find((p) => p.id === selectedPresetId);
  const availableModels = allModels.items.filter(
    (m) => m.workspace_profile && m.status !== 'disabled' && m.status !== 'revoked',
  );
  const staleSelections =
    runOnSave && !allModels.loading
      ? selected.filter((id) => !availableModels.some((m) => m.id === id))
      : [];
  const composerHeading = useRef<HTMLHeadingElement>(null),
    readinessHeading = useRef<HTMLHeadingElement>(null);
  const formError = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (error || packages.error || presets.error || allModels.error) {
      formError.current?.focus();
      formError.current?.scrollIntoView({ block: 'nearest' });
    }
  }, [error, packages.error, presets.error, allModels.error]);
  useEffect(() => {
    setComposing(!preparationId);
  }, [preparationId]);
  useEffect(() => {
    if (composing) {
      composerHeading.current?.focus();
      composerHeading.current?.scrollIntoView({ block: 'start' });
    } else if (saved) {
      readinessHeading.current?.focus();
      readinessHeading.current?.scrollIntoView({ block: 'start' });
    }
  }, [composing, saved?.id]);
  useEffect(() => {
    let active = true;
    setSaved(null);
    setError('');
    setDetailLoading(!!preparationId);
    if (preparationId)
      api(base + '/workspace/preparations/' + preparationId)
        .then((value) => {
          if (active) setSaved(value);
        })
        .catch((e) => {
          if (active) setError(e.message);
        })
        .finally(() => {
          if (active) setDetailLoading(false);
        });
    return () => {
      active = false;
    };
  }, [base, preparationId, refreshKey]);
  return (
    <>
      {!composing && (
        <section className={styles.panel}>
          <h2>Saved preparation</h2>
          {detailLoading && <p role="status">Loading saved preparation…</p>}
          {error && <p role="alert">{error}</p>}
          <button onClick={() => setRefreshKey((old) => old + 1)} disabled={detailLoading}>
            Refresh readiness
          </button>
          <a href={base.replace('/projects/', '/workspace/') + '/execution-groups/new'}>
            Create execution group
          </a>
        </section>
      )}
      {composing && (
        <section
          className={styles.panel}
          aria-label="Evaluation preparation"
          aria-busy={packages.loading || presets.loading || drafts.loading || allModels.loading}
        >
          <h2 ref={composerHeading} tabIndex={-1}>
            Configure run
          </h2>
          {(packages.loading || presets.loading || drafts.loading) && (
            <p role="status">Loading preparation choices…</p>
          )}
          <p>
            {runOnSave ? (
              'Select your configuration and Run. Anvil starts execution when all requirements are met, or shows exactly what needs attention.'
            ) : (
              <>
                Choose the task package, preset, models and budget. Create saves the group and opens
                its dashboard. Run starts execution from that dashboard.
              </>
            )}
          </p>
          {[error, packages.error, presets.error, allModels.error].filter(Boolean).map((e, i) => (
            <p role="alert" key={i} ref={i === 0 ? formError : undefined} tabIndex={-1}>
              {e}
            </p>
          ))}
          <Form
            onSubmit={async (e) => {
              e.preventDefault();
              const data = new FormData(e.currentTarget);
              setBusy(true);
              setError('');
              try {
                if (packages.loading || presets.loading || allModels.loading)
                  throw new Error('Run cannot start yet: configuration choices are still loading.');
                if (packages.error || presets.error || allModels.error)
                  throw new Error(
                    'Run cannot start yet: reload the configuration choices that failed to load.',
                  );
                if (!selected.length)
                  throw new Error('Run cannot start yet: select at least one model.');
                if (selected.length > 8)
                  throw new Error('Select at most eight models for one run.');
                if (staleSelections.length)
                  throw new Error(
                    'A selected model version is no longer available. Clear unavailable selections and select its current version.',
                  );
                if (!preset) throw new Error('Run cannot start yet: select an execution preset.');
                const dollars = String(data.get('cap') || '');
                if (dollars && !/^\d+(\.\d{1,6})?$/.test(dollars))
                  throw new Error('Enter a USD amount with at most six decimal places.');
                const [whole, fraction = ''] = dollars.split('.');
                let exactPresetId = selectedPresetId;
                const frozen = new Map(preset.snapshot.models.map((m) => [m.id, m.config_hash]));
                if (
                  runOnSave &&
                  canAuthorizeRun &&
                  selected.some(
                    (id) =>
                      frozen.get(id) !== allModels.items.find((m) => m.id === id)?.config_hash,
                  )
                ) {
                  const exact = await api(base + '/workspace/presets', 'POST', {
                    name: ('Run selection · ' + preset.snapshot.name).slice(0, 100),
                    runner_profile_id: preset.snapshot.runner.id,
                    candidate_runtime: preset.snapshot.candidate_runtime,
                    candidate_profile_id: preset.snapshot.candidate?.id || null,
                    tracing_profile_id: preset.snapshot.tracing?.id || null,
                    model_profile_ids: selected,
                  });
                  exactPresetId = exact.id;
                }
                const result = await api(base + '/workspace/preparations', 'POST', {
                  preset_id: exactPresetId,
                  package_id: data.get('package'),
                  model_profile_ids: selected,
                  max_output_tokens: Number(data.get('tokens')),
                  episode_timeout_seconds: Number(data.get('timeout')),
                  aggregate_cap_micro_usd: dollars
                    ? Number(whole) * 1000000 + Number(fraction.padEnd(6, '0'))
                    : null,
                  trials_per_model: Number(data.get('trials') || 1),
                  environment: 'package-docker',
                });
                if (createGroup) {
                  const group = await api(base + '/workspace/execution-groups', 'POST', {
                    preparation_id: result.id,
                  });
                  if (runOnSave && !runBlockers(group.readiness, canAuthorizeRun).length) {
                    try {
                      await api(
                        base + '/workspace/execution-groups/' + group.id + '/launch',
                        'POST',
                        canAuthorizeRun
                          ? {
                              subject_hash: group.subject_hash,
                              aggregate_cap_micro_usd: group.readiness.aggregate_cap_micro_usd,
                              rights_confirmed: true,
                            }
                          : undefined,
                      );
                    } catch (e) {
                      open(
                        group.id,
                        'Run status could not be confirmed: ' +
                          (e as Error).message +
                          ' Review this saved run before retrying.',
                      );
                      return;
                    }
                  }
                  open(group.id);
                } else {
                  setSaved(result);
                  open(result.id);
                }
                await drafts.reload();
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <VersionChoice
              id="preparation-package"
              name="package"
              label="Task package version"
              complete={!packages.more && !packages.error}
              loading={packages.loading}
              choices={packages.items
                .filter((p) => !packageId || p.id === packageId)
                .map((p) => ({
                  id: p.id,
                  label:
                    (p.title || p.manifest.task_id) +
                    ' · ' +
                    p.manifest.task_version +
                    ' · ' +
                    shortId(p.package_sha256),
                }))}
            />
            <label htmlFor="preparation-environment">Target environment</label>
            <select id="preparation-environment" name="environment" defaultValue="package-docker">
              <option value="package-docker">Harbor isolated Docker · task-bound image</option>
              {environments.map((env) => (
                <option key={env.id} value={env.id} disabled>
                  {env.name} · Awaiting qualification
                </option>
              ))}
            </select>
            <p className={styles.muted}>
              Uses the selected package’s immutable environment. Additional environments require
              configuration.
            </p>
            {packages.more && (
              <button
                type="button"
                disabled={packages.loading}
                onClick={() => void packages.more?.()}
              >
                Load more package choices
              </button>
            )}
            {!packages.loading && !packages.items.length && (
              <p>No built packages in this view. Import and build a task package first.</p>
            )}
            <VersionChoice
              id="preparation-preset"
              label="Execution preset"
              complete={!presets.more && !presets.error}
              loading={presets.loading}
              value={presetId}
              change={(id) => {
                setPresetId(id);
                setSelected([]);
              }}
              choices={presets.items.map((p) => ({
                id: p.id,
                label: p.snapshot.name + ' · ' + shortId(p.subject_hash),
              }))}
            />
            {presets.more && (
              <button
                type="button"
                disabled={presets.loading}
                onClick={() => void presets.more?.()}
              >
                Load more preset choices
              </button>
            )}
            {!presets.loading && !presets.items.length && (
              <p>An Admin must save an execution preset in Frameworks first.</p>
            )}
            {preset && (
              <ToggleModels
                models={runOnSave ? availableModels : preset.snapshot.models}
                selected={selected}
                change={setSelected}
                showKeys={runOnSave}
                allowedIds={
                  runOnSave && !canAuthorizeRun
                    ? preset.snapshot.models.map((m) => m.id)
                    : undefined
                }
              />
            )}
            {!!staleSelections.length && (
              <p role="alert">
                A selected model changed or became unavailable.{' '}
                <button
                  type="button"
                  onClick={() =>
                    setSelected(selected.filter((id) => !staleSelections.includes(id)))
                  }
                >
                  Clear unavailable selections
                </button>
              </p>
            )}
            <h3>Settings for all selected models</h3>
            <p>
              The output-token limit, repetitions and episode time limit apply to every selected
              model. The API budget is one total cap across all models and repetitions.
            </p>
            <label htmlFor="preparation-tokens">Selected maximum output tokens</label>
            <input
              id="preparation-tokens"
              name="tokens"
              type="number"
              required
              min={1}
              max={2048}
              defaultValue={2048}
            />
            <label htmlFor="preparation-trials">Repetitions per model</label>
            <input
              id="preparation-trials"
              name="trials"
              type="number"
              required
              min={1}
              max={10}
              defaultValue={1}
            />
            <label htmlFor="preparation-timeout">Episode time limit (seconds)</label>
            <input
              id="preparation-timeout"
              name="timeout"
              type="number"
              required
              min={1}
              max={600}
              defaultValue={300}
            />
            <label htmlFor="preparation-cap">
              {createGroup
                ? 'Aggregate API budget (USD)'
                : 'Aggregate API budget (USD, optional while planning)'}
            </label>
            <input
              id="preparation-cap"
              name="cap"
              required={createGroup}
              type="number"
              min={0.000001}
              max={1000}
              step={0.000001}
            />
            <p>
              Each repetition creates a separate trial, in sequence. The cap covers every model and
              trial. A blank cap grants no spending authority.
            </p>
            {runOnSave && canAuthorizeRun && (
              <p>
                By selecting Run, you confirm permission to process this task with the selected
                models and authorize the budget entered above.
              </p>
            )}
            <button
              disabled={
                busy ||
                (!runOnSave &&
                  (!selected.length ||
                    packages.loading ||
                    presets.loading ||
                    !!packages.error ||
                    !!presets.error))
              }
            >
              {busy && runOnSave
                ? 'Starting run…'
                : runOnSave
                  ? 'Run'
                  : createGroup
                    ? 'Create execution group'
                    : 'Save preparation'}
            </button>
          </Form>
        </section>
      )}
      {saved && (
        <section className={styles.panel} aria-labelledby="preparation-readiness-heading">
          <h2 id="preparation-readiness-heading" ref={readinessHeading} tabIndex={-1}>
            Preparation readiness
          </h2>
          <p role="status">Preparation saved · planning only</p>
          <h3>Bound task and settings</h3>
          <p>
            {saved.snapshot.package.manifest.task_id} · version{' '}
            {saved.snapshot.package.manifest.task_version}
          </p>
          <p>
            Package {shortId(saved.snapshot.package.package_sha256)} · preset{' '}
            {saved.snapshot.preset.name}
          </p>
          <p>
            Output ceiling: {saved.snapshot.max_output_tokens} tokens. Aggregate budget:{' '}
            {saved.snapshot.aggregate_cap_micro_usd === null
              ? 'not set'
              : new Intl.NumberFormat('en-US', {
                  style: 'currency',
                  currency: 'USD',
                  maximumFractionDigits: 6,
                }).format(saved.snapshot.aggregate_cap_micro_usd / 1000000)}
            .
          </p>
          <p>Conservative cost: unknown. Reservation: not created. External tracing: disabled.</p>
          <ul>
            {saved.readiness.missing.map((reason) => (
              <li key={reason}>{messages[reason] || reason}</li>
            ))}
          </ul>
          {saved.snapshot.models.map((m) => (
            <div key={m.id}>
              <h3>
                {m.name} · {m.provider}/{m.model_id}
              </h3>
              <ul>
                {saved.readiness.models
                  .find((state) => state.model_profile_id === m.id)
                  ?.missing.map((reason) => (
                    <li key={reason}>{messages[reason] || reason}</li>
                  ))}
              </ul>
            </div>
          ))}
          <p>Use Create execution group to choose the configuration for a new run.</p>
          <details>
            <summary>Exact preparation snapshot</summary>
            <pre>{JSON.stringify(saved.snapshot, null, 2)}</pre>
            <small>Binding {saved.subject_hash}</small>
          </details>
        </section>
      )}
      {!createGroup && (
        <section className={styles.panel} aria-labelledby="saved-preparations-heading">
          <h2 id="saved-preparations-heading">Saved preparations</h2>
          {drafts.loading && <p role="status">Loading saved preparations…</p>}
          {drafts.error && (
            <>
              <p role="alert">{drafts.error}</p>
              <button onClick={() => void drafts.reload()} disabled={drafts.loading}>
                Refresh saved preparations
              </button>
            </>
          )}
          {drafts.items.map((draft) => (
            <p key={draft.id}>
              <button onClick={() => open(draft.id)}>
                {draft.snapshot.preset.name} · {shortId(draft.id)} · planning only
              </button>
            </p>
          ))}
          {!drafts.loading && !drafts.error && !drafts.items.length && (
            <p>No saved preparations.</p>
          )}
          {drafts.more && (
            <button disabled={drafts.loading} onClick={() => void drafts.more?.()}>
              Load more preparations
            </button>
          )}
        </section>
      )}
    </>
  );
}
