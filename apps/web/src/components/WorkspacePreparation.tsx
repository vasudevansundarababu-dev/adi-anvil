'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Form from './Form';
import { shortId, workspaceApi as api } from '../lib/workspace';
import { runBlockers } from '../lib/executionReadiness';
import { describeReason } from '../lib/readinessCatalog';
import ReasonList from './ReasonList';
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
  group?: string;
  hub?: { repository: string; revision: string };
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
  manifest: {
    task_id: string;
    task_version: string;
    native_binding?: {
      task_mode?: string;
      template_sha256?: string;
      runtime_sha256?: string;
      import_sha256?: string;
      evaluator_sha256?: string;
      case_dataset?: { sha256: string; case_count: number };
      case_selector?: { value: string; case_count: number };
    };
  };
};
type Workflow = {
  id: string;
  package_id: string;
  subject_hash: string;
  revoked_at: string | null;
  definition: {
    binding: {
      graph: {
        nodes: { id: string; role: string; human_mode?: string }[];
        bounds: { calls: number };
      };
    };
  };
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
  base,
  models,
  selected,
  change,
  showKeys = false,
  allowedIds,
}: {
  base: string;
  models: Model[];
  selected: string[];
  change: (ids: string[]) => void;
  showKeys?: boolean;
  allowedIds?: string[];
}) {
  const [search, setSearch] = useState('');
  const [group, setGroup] = useState('all');
  const [versionChoice, setVersionChoice] = useState('');
  const [catalog, setCatalog] = useState<{ id: string; label: string }[]>([]);
  const [catalogError, setCatalogError] = useState('');
  useEffect(() => {
    let active = true;
    api(base + '/workspace/models/catalog')
      .then((result) => {
        if (active) setCatalog(result.items);
      })
      .catch((e) => {
        if (active) setCatalogError((e as Error).message);
      });
    return () => {
      active = false;
    };
  }, [base]);
  const visible = models.filter(
    (m) =>
      (group === 'all' || (m.group || 'provider-models') === group) &&
      (!showKeys ||
        [m.name, m.provider, m.model_id, m.credential_name]
          .join(' ')
          .toLowerCase()
          .includes(search.toLowerCase())),
  );
  return (
    <fieldset>
      <legend>{showKeys ? 'Available models & linked keys' : 'Model profiles for planning'}</legend>
      <p className={styles.muted}>
        Select exact saved versions. Execution requires current bindings and explicit authorization.
      </p>
      <label>
        Model group
        <select
          value={group}
          onChange={(e) => {
            setGroup(e.target.value);
            setVersionChoice('');
          }}
        >
          <option value="all">All models</option>
          <option value="open-weight-models">Open Weight Models</option>
          <option value="provider-models">Provider models</option>
        </select>
      </label>
      {group === 'open-weight-models' && (
        <>
          <p>
            Choose saved model revisions below. Hugging Face access and execution runtime setup are
            still required; live calls are disabled.
          </p>
          {catalogError && <p role="alert">{catalogError}</p>}
          <details>
            <summary>Workbook catalog · {catalog.length} model variants</summary>
            <ul>
              {catalog.map((item) => (
                <li key={item.id}>
                  {item.label}
                  {models.some(
                    (m) => m.hub && (m.hub as { catalog_id?: string }).catalog_id === item.id,
                  )
                    ? ' · Saved configuration available'
                    : ' · Configure repository and revision first'}
                </li>
              ))}
            </ul>
          <a href={base.replace('/projects/', '/workspace/') + '/admin'}>
              Configure Open Weight Models in Models &amp; Keys
            </a>
          </details>
        </>
      )}
      <label>
        Model and version
        <select value={versionChoice} onChange={(e) => setVersionChoice(e.target.value)}>
          <option value="">Choose an exact saved model version</option>
          {visible.map((m) => (
            <option
              key={m.id}
              value={m.id}
              disabled={
                m.status === 'revoked' ||
                m.status === 'disabled' ||
                (!!allowedIds && !allowedIds.includes(m.id))
              }
            >
              {m.name} · {m.model_id} ·{' '}
              {m.hub ? 'Hub revision ' + m.hub.revision : 'Configuration ' + shortId(m.id)}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        disabled={
          !visible.some(
            (m) =>
              m.id === versionChoice &&
              m.status !== 'revoked' &&
              m.status !== 'disabled' &&
              (!allowedIds || allowedIds.includes(m.id)),
          ) ||
          selected.includes(versionChoice) ||
          selected.length >= 8
        }
        onClick={() => change([...selected, versionChoice])}
      >
        Add model version
      </button>
      {selected.length > 0 && (
        <div aria-label="Selected model versions">
          <strong>Selected models and versions ({selected.length}/8)</strong>
          <ul>
            {selected.map((id) => {
              const m = models.find((item) => item.id === id);
              return (
                <li key={id}>
                  {m ? m.name + ' · ' + (m.hub?.revision || shortId(id)) : shortId(id)}
                  {!visible.some((item) => item.id === id) ? ' · Outside current filter' : ''}{' '}
                  <button
                    type="button"
                    onClick={() => change(selected.filter((value) => value !== id))}
                  >
                    Remove
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
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
              (!selected.includes(m.id) && selected.length >= 8) ||
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
          {m.hub && (
            <small style={{ display: 'block', marginLeft: 24 }}>
              Hub revision: {m.hub.revision}
            </small>
          )}
          {showKeys && (
            <small style={{ display: 'block', marginLeft: 24 }}>
              Key: {m.credential_name || 'No saved key linked'}
              {m.credential_state && m.credential_state !== 'configured'
                ? ' · ' + m.credential_state
                : ''}
              {allowedIds && !allowedIds.includes(m.id)
                ? ' · Not included in this authorized run configuration'
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
              candidate_profile_id: null,
              tracing_profile_id: null,
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
          <option value="anvil-structured-json-v1">Forge structured JSON agent</option>
          <option value="golden-kyc-openenv-tool-agent-v1">
            Golden KYC · Harbor and OpenEnv tool agent
          </option>
          <option value="marketing-task2-five-role-v1">
            Headphone launch · Harbor and LangGraph five-role campaign
          </option>
        </select>
        <ToggleModels
          base={base}
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
  projectBinding,
  allowedPackageIds,
  executionBudgetId,
  budgetModelIds,
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
  projectBinding?: { task_group_id: string; id: string; snapshot_sha256: string };
  allowedPackageIds?: string[];
  executionBudgetId?: string;
  budgetModelIds?: string[];
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
  const workflows = useList<Workflow>(base + '/workspace/workflows/definitions');
  const responders = useList<{ id: string; name: string }>(
    base + '/workspace/workflows/responders',
  );
  const [chosenPackage, setChosenPackage] = useState('');
  const [additionalStatePackages, setAdditionalStatePackages] = useState<string[]>([]);
  const [workflowId, setWorkflowId] = useState('');
  const [environmentChoice, setEnvironmentChoice] = useState<{
    packageId: string;
    value: string;
  } | null>(null);
  const [timeoutChoice, setTimeoutChoice] = useState<{ packageId: string; value: string } | null>(
    null,
  );
  const visiblePackages = packages.items.filter(
    (p) =>
      (!packageId || p.id === packageId) &&
      (!allowedPackageIds || allowedPackageIds.includes(p.id)),
  );
  const exactPackage =
    visiblePackages.length === 1 && !packages.more ? visiblePackages[0].id : chosenPackage;
  const primaryPackage = packages.items.find((p) => p.id === exactPackage);
  const nativeBinding = primaryPackage?.manifest.native_binding;
  const reusableKyc = nativeBinding?.task_mode === 'reusable_state_workflow';
  const reusableMarketing = nativeBinding?.task_mode === 'reusable_campaign_workflow';
  const environmentValue =
    environmentChoice?.packageId === exactPackage
      ? environmentChoice.value
      : reusableKyc
        ? 'golden-kyc-openenv-v2'
        : reusableMarketing
          ? 'marketing-task2-us-v1'
          : 'package-docker';
  const timeoutValue =
    timeoutChoice?.packageId === exactPackage
      ? timeoutChoice.value
      : reusableMarketing
        ? '600'
        : '300';
  const compatibleStatePackages = reusableKyc
    ? packages.items.filter((p) => {
        const binding = p.manifest.native_binding;
        return (
          p.id !== exactPackage &&
          (!allowedPackageIds || allowedPackageIds.includes(p.id)) &&
          binding?.task_mode === 'reusable_state_workflow' &&
          binding.case_selector?.value !== nativeBinding?.case_selector?.value &&
          ['template_sha256', 'runtime_sha256', 'import_sha256', 'evaluator_sha256'].every(
            (key) =>
              binding[key as keyof typeof binding] ===
              nativeBinding?.[key as keyof typeof nativeBinding],
          ) &&
          binding.case_dataset?.sha256 === nativeBinding?.case_dataset?.sha256
        );
      })
    : [];
  const availableWorkflows = workflows.items.filter(
    (w) => !w.revoked_at && w.package_id === exactPackage,
  );
  const workflow =
    reusableKyc || reusableMarketing
      ? undefined
      : availableWorkflows.find((w) => w.id === workflowId);
  const humanRoles = [
    ...new Set(
      workflow?.definition.binding.graph.nodes
        .filter((n) => n.human_mode === 'actual')
        .map((n) => n.role) || [],
    ),
  ];
  const drafts = useList<Draft>(runOnSave ? null : base + '/workspace/preparations');
  const [presetId, setPresetId] = useState(''),
    [composing, setComposing] = useState(!preparationId),
    [detailLoading, setDetailLoading] = useState(!!preparationId),
    [selected, setSelected] = useState<string[]>([]),
    [saved, setSaved] = useState<Draft | null>(null),
    [refreshKey, setRefreshKey] = useState(0),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const submitting = useRef(false);
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
  const workspace = base.replace('/projects/', '/workspace/');
  const destinations = saved && {
    workspace,
    configure: workspace + '/execution-groups/new',
    share: workspace + '/preparation?preparation=' + encodeURIComponent(saved.id),
  };
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
              'Select your configuration and Run. Forge starts execution when all requirements are met, or shows exactly what needs attention.'
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
              if (submitting.current) return;
              const data = new FormData(e.currentTarget);
              submitting.current = true;
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
                if (
                  allowedPackageIds &&
                  (!allowedPackageIds.includes(String(data.get('package'))) ||
                    additionalStatePackages.some((id) => !allowedPackageIds.includes(id)))
                )
                  throw new Error(
                    'Selected execution packages must belong to the frozen Project bindings.',
                  );
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
                  ...(projectBinding ? { project_binding: projectBinding } : {}),
                  ...(executionBudgetId ? { execution_budget_id: executionBudgetId } : {}),
                  preset_id: exactPresetId,
                  package_id: data.get('package'),
                  model_profile_ids: selected,
                  workflow_definition_id:
                    reusableKyc || reusableMarketing ? null : workflow?.id || null,
                  ...(reusableKyc
                    ? {
                        task_package_ids: [String(data.get('package')), ...additionalStatePackages],
                        ...(String(data.get('applicationCases') || '').trim()
                          ? {
                              case_ids: String(data.get('applicationCases'))
                                .split(/[\s,]+/)
                                .filter(Boolean),
                            }
                          : {}),
                      }
                    : {}),
                  human_assignments: Object.fromEntries(
                    humanRoles.map((role) => [role, data.get('human:' + role)]),
                  ),
                  max_output_tokens: Number(data.get('tokens')),
                  episode_timeout_seconds: Number(data.get('timeout')),
                  aggregate_cap_micro_usd: dollars
                    ? Number(whole) * 1000000 + Number(fraction.padEnd(6, '0'))
                    : null,
                  trials_per_model: Number(data.get('trials') || 1),
                  max_agent_steps: reusableKyc
                    ? Number(data.get('agentSteps'))
                    : reusableMarketing
                      ? data.get('steps')
                        ? Number(data.get('steps'))
                        : null
                      : workflow?.definition.binding.graph.bounds.calls ||
                        (data.get('steps') ? Number(data.get('steps')) : null),
                  environment: String(data.get('environment') || 'package-docker'),
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
                submitting.current = false;
                setBusy(false);
              }
            }}
          >
            <fieldset disabled={busy} aria-busy={busy} style={{ border: 0, padding: 0, margin: 0 }}>
              <VersionChoice
                id="preparation-package"
                name="package"
                label="Task package version"
                value={chosenPackage}
                change={(value) => {
                  setChosenPackage(value);
                  setAdditionalStatePackages([]);
                  setWorkflowId('');
                }}
                complete={!packages.more && !packages.error}
                loading={packages.loading}
                choices={visiblePackages.map((p) => ({
                  id: p.id,
                  label:
                    (p.title || p.manifest.task_id) +
                    ' · ' +
                    p.manifest.task_version +
                    ' · ' +
                    shortId(p.package_sha256),
                }))}
              />
              {reusableKyc && (
                <fieldset>
                  <legend>Shared KYC application cases</legend>
                  <p>
                    These state tasks share one dataset, environment and evaluator library.
                    Application cases do not create more authored tasks. Every selected case gets an
                    isolated episode; all selected tasks and models share this group’s spending cap.
                  </p>
                  <p>
                    Primary state: {nativeBinding?.case_selector?.value} ·{' '}
                    {nativeBinding?.case_selector?.case_count} cases in its partition.
                  </p>
                  {compatibleStatePackages.map((p) => (
                    <label key={p.id}>
                      <input
                        type="checkbox"
                        checked={additionalStatePackages.includes(p.id)}
                        onChange={(e) =>
                          setAdditionalStatePackages((current) =>
                            e.target.checked
                              ? [...current, p.id]
                              : current.filter((id) => id !== p.id),
                          )
                        }
                      />
                      Include {p.title || p.manifest.task_id} ·{' '}
                      {p.manifest.native_binding?.case_selector?.case_count} cases
                    </label>
                  ))}
                  <label htmlFor="application-cases">Application cases to run (optional)</label>
                  <textarea
                    id="application-cases"
                    name="applicationCases"
                    placeholder="Comma-separated application IDs; leave empty for all cases in the selected states"
                  />
                  <p>
                    Forge verifies case membership and prices the complete plan before admission. A
                    budget limit can block the plan; it does not silently reduce case coverage.
                  </p>
                  <label htmlFor="native-agent-steps">Maximum model turns per application</label>
                  <input
                    id="native-agent-steps"
                    name="agentSteps"
                    type="number"
                    min={1}
                    max={100}
                    defaultValue={3}
                    required
                  />
                </fieldset>
              )}
              {reusableMarketing && (
                <section aria-label="Marketing campaign execution scope">
                  <h3>Complete five-role campaign</h3>
                  <p>
                    Each selected model runs all five roles through all 12 reporting windows,
                    including parallel work, handoffs and revision loops in the published workflow.
                    Models are compared in separate campaigns. This is not a mixed-model team.
                  </p>
                  <p>
                    The default uses the bound campaign dataset. The server prices the full plan
                    before admission. A budget blocker never reduces the windows or case coverage.
                  </p>
                </section>
              )}
              {workflows.error && (
                <p role="alert">Workflow choices could not be loaded: {workflows.error}</p>
              )}
              <label htmlFor="preparation-workflow">Workflow</label>
              <select
                id="preparation-workflow"
                disabled={reusableKyc || reusableMarketing}
                value={workflow?.id || ''}
                onChange={(e) => setWorkflowId(e.target.value)}
              >
                <option value="">Task’s standard execution</option>
                {availableWorkflows.map((w) => (
                  <option key={w.id} value={w.id}>
                    Reviewed workflow · {shortId(w.subject_hash)}
                  </option>
                ))}
              </select>
              {workflow && (
                <p>
                  Uses the reviewed graph with at most{' '}
                  {workflow.definition.binding.graph.bounds.calls} model calls per trial. Human
                  responses do not approve spending.
                </p>
              )}
              {humanRoles.map((role) => (
                <div key={role}>
                  <label htmlFor={'human-' + role}>Responder for {role}</label>
                  <select id={'human-' + role} name={'human:' + role} required defaultValue="">
                    <option value="" disabled>
                      Select a project member
                    </option>
                    {responders.items.map((person) => (
                      <option key={person.id} value={person.id}>
                        {person.name}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
              {humanRoles.length > 0 && responders.error && (
                <p role="alert">Responders could not be loaded: {responders.error}</p>
              )}
              <label htmlFor="preparation-environment">Target environment</label>
              <select
                key={'environment:' + exactPackage}
                id="preparation-environment"
                name="environment"
                value={environmentValue}
                onChange={(e) =>
                  setEnvironmentChoice({ packageId: exactPackage, value: e.target.value })
                }
              >
                <option value="package-docker">Harbor isolated Docker · task-bound image</option>
                {reusableKyc && (
                  <option value="golden-kyc-openenv-v2">
                    Golden KYC · shared OpenEnv, isolated per application
                  </option>
                )}
                {reusableMarketing && (
                  <option value="marketing-task2-us-v1">
                    Headphone launch · shared campaign environment, isolated per model
                  </option>
                )}
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
                  base={base}
                  models={runOnSave ? availableModels : preset.snapshot.models}
                  selected={selected}
                  change={setSelected}
                  showKeys={runOnSave}
                  allowedIds={
                    budgetModelIds
                      ? budgetModelIds.filter(
                          (id) =>
                            canAuthorizeRun ||
                            preset.snapshot.models.some((model) => model.id === id),
                        )
                      : runOnSave && !canAuthorizeRun
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
              {!reusableKyc && (
                <>
                  <label htmlFor="preparation-steps">
                    {reusableMarketing
                      ? 'Maximum model calls per campaign (optional)'
                      : 'Maximum agent steps per trial'}
                  </label>
                  <input
                    id="preparation-steps"
                    name="steps"
                    type="number"
                    min={1}
                    max={reusableMarketing ? 1000 : 100}
                    placeholder={
                      reusableMarketing
                        ? 'Use the complete bound campaign plan'
                        : 'Use task horizon'
                    }
                    disabled={!reusableMarketing && !!workflow}
                  />
                </>
              )}
              <label htmlFor="preparation-timeout">
                {reusableMarketing
                  ? 'Campaign time limit (seconds)'
                  : 'Episode time limit (seconds)'}
              </label>
              <input
                id="preparation-timeout"
                key={'timeout:' + exactPackage}
                name="timeout"
                type="number"
                required
                min={1}
                max={600}
                value={timeoutValue}
                onChange={(e) =>
                  setTimeoutChoice({ packageId: exactPackage, value: e.target.value })
                }
              />
              {reusableMarketing && (
                <p>
                  All five roles and all 12 reporting windows share this time limit. If time runs
                  out, the execution remains incomplete and its recorded progress is retained.
                </p>
              )}
              <p>
                New Gemini 3.8 Flash groups allow up to 180 seconds per request; other models use 90
                seconds. Requests remain bounded by the episode time left. Existing saved groups
                retain their original limits. No automatic retry is performed.
              </p>
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
                Each repetition creates a separate trial, in sequence. The cap covers every model
                and trial. A blank cap grants no spending authority.
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
            </fieldset>
          </Form>
        </section>
      )}
      {saved && destinations && (
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
          <ReasonList
            items={saved.readiness.missing.map((reason) => describeReason(reason, canAuthorizeRun))}
            canAdmin={canAuthorizeRun}
            to={destinations}
          />
          {saved.snapshot.models.map((m) => (
            <div key={m.id}>
              <h3>
                {m.name} · {m.provider}/{m.model_id}
              </h3>
              <ReasonList
                items={(
                  saved.readiness.models.find((state) => state.model_profile_id === m.id)
                    ?.missing || []
                ).map((reason) => describeReason(reason, canAuthorizeRun))}
                canAdmin={canAuthorizeRun}
                to={destinations}
              />
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
