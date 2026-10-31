'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Form from './Form';
import { shortId, workspaceApi as api } from '../lib/workspace';
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

function useList<T>(path: string) {
  const [items, setItems] = useState<T[]>([]),
    [cursor, setCursor] = useState<string | null>(null),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(true);
  const generation = useRef(0);
  const load = useCallback(
    async (after?: string) => {
      const current = ++generation.current;
      setLoading(true);
      setError('');
      try {
        const result = await api(
          path + (after ? (path.includes('?') ? '&' : '?') + 'after=' + after : ''),
        );
        if (current === generation.current) {
          setItems((old) => (after ? [...old, ...result.items] : result.items));
          setCursor(result.next_cursor);
        }
      } catch (e) {
        if (current === generation.current) setError((e as Error).message);
      } finally {
        if (current === generation.current) setLoading(false);
      }
    },
    [path],
  );
  useEffect(() => {
    setItems([]);
    void load();
    return () => {
      generation.current++;
    };
  }, [load]);
  return {
    items,
    error,
    loading,
    reload: () => load(),
    more: cursor ? () => load(cursor) : undefined,
  };
}

function ToggleModels({
  models,
  selected,
  change,
}: {
  models: Model[];
  selected: string[];
  change: (ids: string[]) => void;
}) {
  return (
    <fieldset>
      <legend>Model profiles for planning</legend>
      <p className={styles.muted}>
        Select exact saved versions. All remain unavailable for dispatch until qualified.
      </p>
      {models.map((m) => (
        <label key={m.id} style={{ display: 'block' }}>
          <input
            type="checkbox"
            checked={selected.includes(m.id)}
            disabled={m.status === 'revoked'}
            onChange={() =>
              change(
                selected.includes(m.id)
                  ? selected.filter((id) => id !== m.id)
                  : [...selected, m.id],
              )
            }
          />
          {m.name} · {m.provider}/{m.model_id} · {shortId(m.id)}
          {m.status === 'revoked' ? ' · Revoked' : ''}
        </label>
      ))}
      {!models.length && <p>No workspace model profiles loaded. Configure models first.</p>}
    </fieldset>
  );
}

export function ExecutionPresets({ base }: { base: string }) {
  const models = useList<Model>(base + '/workspace/models');
  const frameworks = useList<Framework>(base + '/workspace/frameworks');
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
            setMessage('Preset saved. Model execution remains unavailable until qualified.');
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
        <select id="preset-runner" name="runner" required defaultValue="">
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
          <option value="anvil-structured-json-v1">
            Anvil structured agent · binding qualification pending
          </option>
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
  workspace_dispatch_not_qualified: 'Workspace model dispatch is not qualified.',
  current_pricing_not_bound: 'Current reviewed pricing has not been bound to this preparation.',
  exact_user_authority_not_bound: 'Exact user spending authority has not been bound.',
  processing_rights_not_bound: 'Reviewed processing rights have not been bound.',
  required_run_decisions_not_bound: 'Required real run decisions have not been bound.',
  shared_spending_admission_not_implemented:
    'Shared spending admission is not implemented for these profiles.',
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
}: {
  base: string;
  taskId?: string | null;
  preparationId?: string | null;
  open: (id: string) => void;
}) {
  const packages = useList<Package>(
    base + '/workspace/packages' + (taskId ? '?task_id=' + encodeURIComponent(taskId) : ''),
  );
  const presets = useList<Preset>(base + '/workspace/presets');
  const drafts = useList<Draft>(base + '/workspace/preparations');
  const [presetId, setPresetId] = useState(''),
    [selected, setSelected] = useState<string[]>([]),
    [saved, setSaved] = useState<Draft | null>(null),
    [refreshKey, setRefreshKey] = useState(0),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const preset = presets.items.find((p) => p.id === presetId);
  useEffect(() => {
    let active = true;
    setSaved(null);
    setError('');
    if (preparationId)
      api(base + '/workspace/preparations/' + preparationId)
        .then((value) => {
          if (active) setSaved(value);
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    return () => {
      active = false;
    };
  }, [base, preparationId, refreshKey]);
  return (
    <>
      <section
        className={styles.panel}
        aria-label="Evaluation preparation"
        aria-busy={packages.loading || presets.loading || drafts.loading}
      >
        <h2>Prepare model evaluation</h2>
        {(packages.loading || presets.loading || drafts.loading) && (
          <p role="status">Loading preparation choices…</p>
        )}
        <p>
          Choose exact saved versions and review what is missing. Saving creates a preparation, not
          a run. No model request, reservation or external trace is sent.
        </p>
        <button
          onClick={() => {
            void presets.reload();
            void packages.reload();
            void drafts.reload();
            setRefreshKey((old) => old + 1);
          }}
        >
          Refresh preparation choices
        </button>
        {[error, packages.error, presets.error, drafts.error].filter(Boolean).map((e, i) => (
          <p role="alert" key={i}>
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
              const dollars = String(data.get('cap') || '');
              if (dollars && !/^\d+(\.\d{1,6})?$/.test(dollars))
                throw new Error('Enter a USD amount with at most six decimal places.');
              const [whole, fraction = ''] = dollars.split('.');
              const result = await api(base + '/workspace/preparations', 'POST', {
                preset_id: presetId,
                package_id: data.get('package'),
                model_profile_ids: selected,
                max_output_tokens: Number(data.get('tokens')),
                episode_timeout_seconds: Number(data.get('timeout')),
                aggregate_cap_micro_usd: dollars
                  ? Number(whole) * 1000000 + Number(fraction.padEnd(6, '0'))
                  : null,
              });
              setSaved(result);
              open(result.id);
              await drafts.reload();
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label htmlFor="preparation-package">Task package version</label>
          <select id="preparation-package" name="package" required defaultValue="">
            <option value="" disabled>
              Select an immutable package
            </option>
            {packages.items.map((p) => (
              <option value={p.id} key={p.id}>
                {p.title || p.manifest.task_id} · {p.manifest.task_version} ·{' '}
                {shortId(p.package_sha256)}
              </option>
            ))}
          </select>
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
          <label htmlFor="preparation-preset">Execution preset</label>
          <select
            id="preparation-preset"
            required
            value={presetId}
            onChange={(e) => {
              setPresetId(e.target.value);
              setSelected([]);
            }}
          >
            <option value="" disabled>
              Select a saved preset
            </option>
            {presets.items.map((p) => (
              <option key={p.id} value={p.id}>
                {p.snapshot.name} · {shortId(p.subject_hash)}
              </option>
            ))}
          </select>
          {presets.more && (
            <button type="button" disabled={presets.loading} onClick={() => void presets.more?.()}>
              Load more preset choices
            </button>
          )}
          {!presets.loading && !presets.items.length && (
            <p>An Admin must save an execution preset in Frameworks first.</p>
          )}
          {preset && (
            <ToggleModels
              models={preset.snapshot.models}
              selected={selected}
              change={setSelected}
            />
          )}
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
            Aggregate API budget (USD, optional while planning)
          </label>
          <input
            id="preparation-cap"
            name="cap"
            type="number"
            min={0.000001}
            max={1000}
            step={0.000001}
          />
          <p>
            One trial per selected model, in sequence. The cap applies to the entire group. A blank
            cap grants no spending authority.
          </p>
          <button disabled={busy || !selected.length}>Save preparation</button>
        </Form>
      </section>
      {saved && (
        <section className={styles.panel}>
          <h2>Preparation readiness</h2>
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
          <button disabled>Launch unavailable</button>
          <details>
            <summary>Exact preparation snapshot</summary>
            <pre>{JSON.stringify(saved.snapshot, null, 2)}</pre>
            <small>Binding {saved.subject_hash}</small>
          </details>
        </section>
      )}
      <section className={styles.panel}>
        <h2>Saved preparations</h2>
        {drafts.items.map((draft) => (
          <p key={draft.id}>
            <button onClick={() => open(draft.id)}>
              {draft.snapshot.preset.name} · {shortId(draft.id)} · planning only
            </button>
          </p>
        ))}
        {!drafts.loading && !drafts.items.length && <p>No saved preparations.</p>}
        {drafts.more && (
          <button onClick={() => void drafts.more?.()}>Load more preparations</button>
        )}
      </section>
    </>
  );
}
