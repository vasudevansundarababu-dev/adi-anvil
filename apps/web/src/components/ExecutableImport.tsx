'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';

const reasons: Record<string, string> = {
  paid_generation_not_enabled:
    'Generation is disabled for this server or configuration. Ask the installation operator to enable it, then try again.',
  generation_configuration_revoked:
    'This generation configuration was revoked. Select the updated installation configuration before regenerating.',
  generation_pricing_expired:
    'Cost support for this generation model has expired. The installation operator must refresh it before another request.',
  project_admin_processing_permission_required:
    'An Admin needs to start generation for this exact source and configuration. Local editing and testing remain available.',
  whole_import_cap_exhausted:
    'This import reached its budget or generation-call limit. Manual editing and testing do not spend model budget.',
  dispatch_outcome_unknown:
    'The response or usage could not be confirmed. The reservation remains held and the request is not retried automatically.',
  generation_refused: 'The configured generation model refused the request.',
  generation_truncated:
    'The generation model returned an incomplete response. Check its output limit before regenerating within the remaining cap.',
  StoreUnavailable:
    'The saved generation key is unavailable. Save an updated installation configuration and explicitly select it for this import.',
};

export default function ExecutableImport({
  base,
  sourceId,
  sourceSha,
  onReady,
}: {
  base: string;
  sourceId: string;
  sourceSha: string;
  onReady?: () => void;
}) {
  const [family, setFamily] = useState<any>(null);
  const [settings, setSettings] = useState<any>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState('');
  const [artifactJson, setArtifactJson] = useState('');
  const [editing, setEditing] = useState(false);
  const pending = useRef<{ fingerprint: string; key: string } | null>(null);
  const load = useCallback(async () => {
    const [value, config] = await Promise.all([
      api(base + '/workspace/tasks/' + sourceId + '/executable-import'),
      api(base + '/workspace/import-generation/settings'),
    ]);
    setFamily(value);
    setSettings(config);
    setLoaded(true);
  }, [base, sourceId]);
  const current = family?.revisions?.[0];
  const active = ['queued', 'generating', 'validating'].includes(current?.state);
  useEffect(() => {
    let live = true;
    load().catch((e) => {
      if (live) setError(e.message);
    });
    return () => {
      live = false;
    };
  }, [load]);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => void load().catch((e) => setError(e.message)), 2000);
    return () => window.clearInterval(timer);
  }, [active, load]);
  async function action(path: string, body: unknown = {}) {
    setBusy(true);
    setError('');
    try {
      const bytes = await crypto.subtle.digest(
        'SHA-256',
        new TextEncoder().encode(JSON.stringify({ base, path, body })),
      );
      const fingerprint = Array.from(new Uint8Array(bytes), (b) =>
        b.toString(16).padStart(2, '0'),
      ).join('');
      if (pending.current?.fingerprint !== fingerprint)
        pending.current = { fingerprint, key: crypto.randomUUID() };
      setFamily(
        await api(base + '/workspace/' + path, 'POST', body, undefined, pending.current!.key),
      );
      pending.current = null;
      onReady?.();
    } catch (e) {
      setError((e as Error).message);
      try {
        await load();
      } catch {
        /* Retain the original action error and its retry key. */
      }
    } finally {
      setBusy(false);
    }
  }
  const revisionBase =
    family && current ? 'executable-imports/' + family.id + '/revisions/' + current.id : '';
  return (
    <section className={styles.panel} aria-label="Executable import progress">
      <h3>Make this task executable</h3>
      {error && <p role="alert">{error}</p>}
      {!loaded && !error && <p role="status">Loading import state…</p>}
      {settings && (
        <p>
          Generation model:{' '}
          {family?.generation_model
            ? family.generation_model.provider +
              ' / ' +
              family.generation_model.model_id +
              (current?.settings_id && current.settings_id !== family.settings_id
                ? ' (next generation)'
                : ' (bound version)')
            : settings.configured
              ? settings.provider + ' / ' + settings.model_id
              : 'Not configured'}{' '}
          · Framework: Harbor · Supplied Docker image
        </p>
      )}
      {settings?.configured && (
        <p>
          Whole-import cap: $
          {((family?.cap_micro_usd ?? settings.default_cap_micro_usd) / 1000000).toFixed(6)}.
          Evaluation uses a separate run budget.
        </p>
      )}
      {!family && loaded && (
        <p>
          The source is validated. Generate code, check the supplied tools and run automated tests
          before this task is Ready.
        </p>
      )}
      {family && (
        <>
          {!active &&
            settings?.configured &&
            settings?.can_authorize_processing &&
            settings.id !== family.settings_id && (
              <div>
                <p>
                  A newer installation model configuration is available: {settings.provider} /{' '}
                  {settings.model_id}. Switching keeps all spent and reserved costs and this
                  import’s original cap.
                </p>
                <button
                  disabled={busy}
                  onClick={() =>
                    void action('executable-imports/' + family.id + '/rebind', {
                      settings_id: settings.id,
                      base_revision_id: family.current_revision_id,
                    })
                  }
                >
                  Use updated generation configuration
                </button>
              </div>
            )}
          <p role="status">
            {current?.state.replaceAll('_', ' ')} · Accounted generation cost $
            {(family.charged_micro_usd / 1000000).toFixed(6)} · Reserved $
            {(family.reserved_micro_usd / 1000000).toFixed(6)} · Remaining $
            {(family.remaining_micro_usd / 1000000).toFixed(6)}
          </p>
          {family.ready_revision_id && (
            <p>
              A validated Ready version is retained. New drafts keep earlier run bindings unchanged.
            </p>
          )}
          {current?.report?.error && (
            <p role="alert">
              {current.report.stage?.replaceAll('_', ' ')}:{' '}
              {reasons[current.report.error] || current.report.error}
            </p>
          )}
          {current?.cancel_requested && active && (
            <p role="status">
              Cancellation requested. Any in-flight request is accounted for before this import
              stops.
            </p>
          )}
          {current?.report?.tools && (
            <details>
              <summary>Tool validation</summary>
              <ul>
                {current.report.tools.map((t: any) => (
                  <li key={t.tool}>
                    {t.tool}: {t.status}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {current?.report?.fixtures && (
            <details>
              <summary>Verifier tests (software validation)</summary>
              <ul>
                {current.report.fixtures.map((t: any) => (
                  <li key={t.id}>
                    {t.id}: {t.passed ? 'Passed' : 'Failed'} · reward {t.reward_bps / 100}%
                  </li>
                ))}
              </ul>
            </details>
          )}
          {!!current?.report?.source_qa_fixtures?.length && (
            <details>
              <summary>Held-out source QA</summary>
              <p>
                These source checks stay separate from the generation prompt and candidate
                environment.
              </p>
              <ul>
                {current.report.source_qa_fixtures.map((t: any) => (
                  <li key={t.id}>
                    {t.id}: {t.passed ? 'Passed' : 'Failed'}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
      {loaded && !active && (
        <button
          disabled={busy || !(family?.configuration_available ?? settings?.configured)}
          onClick={() =>
            void action('tasks/' + sourceId + '/generate', {
              rights_confirmed:
                !!settings?.can_authorize_processing &&
                !!(
                  family?.generation_model?.paid_generation_enabled ??
                  settings?.paid_generation_enabled
                ),
              source_sha256: sourceSha,
              settings_id: family?.settings_id || settings?.id,
              cap_micro_usd: family?.cap_micro_usd ?? settings?.default_cap_micro_usd,
            })
          }
        >
          {busy ? 'Starting…' : family ? 'Regenerate within remaining cap' : 'Import & generate'}
        </button>
      )}
      {(family?.generation_model?.paid_generation_enabled ?? settings?.paid_generation_enabled) && (
        <p>
          {settings.can_authorize_processing
            ? 'By selecting Import & generate or Regenerate, you confirm permission to process this exact source with the bound generation model within the cap shown.'
            : 'Paid generation requires the project Admin’s current permission to process this exact source. Local editing and testing remain available.'}
        </p>
      )}
      {!settings?.configured && loaded && (
        <p>Set up the installation generation model and cap in Models & keys.</p>
      )}
      {active && (
        <button
          disabled={busy}
          onClick={() => void action('executable-imports/' + family.id + '/cancel')}
        >
          Cancel import
        </button>
      )}
      {current && !active && (
        <>
          <button
            disabled={busy}
            onClick={async () => {
              setError('');
              try {
                const value = await api(base + '/workspace/' + revisionBase + '/code');
                await action('executable-imports/' + family.id + '/edit', {
                  base_revision_id: current.id,
                  code: value.code,
                });
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            Test again (no model call)
          </button>
          <button
            disabled={busy}
            onClick={async () => {
              setError('');
              try {
                const value = await api(base + '/workspace/' + revisionBase + '/code');
                setCode(value.code);
                setArtifactJson(JSON.stringify(value, null, 2));
                setEditing(true);
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            Inspect / edit generated Python
          </button>
          <a
            className="button"
            href={'/api/v1' + base + '/workspace/' + revisionBase + '/notebook'}
          >
            Download review notebook
          </a>
          <details>
            <summary>Open in Colab or JupyterLab</summary>
            <p>
              Download the notebook, then use File → Upload notebook in Colab or open it in
              JupyterLab. It contains code but no private reference fixtures or credentials. Upload
              your edited notebook below; Anvil reruns authoritative checks in a fresh supplied
              environment. Hosted notebook results do not certify that environment.
            </p>
            <a href="https://colab.research.google.com/" target="_blank" rel="noreferrer">
              Open Google Colab
            </a>
          </details>
          <label>
            Return edited notebook
            <input
              type="file"
              accept=".ipynb"
              disabled={busy}
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                try {
                  if (file.size > 524288) throw new Error('Notebook must be under 512 KiB.');
                  const notebook = JSON.parse(await file.text());
                  await action('executable-imports/' + family.id + '/edit', {
                    base_revision_id: current.id,
                    notebook,
                  });
                } catch (err) {
                  setError((err as Error).message);
                }
                e.target.value = '';
              }}
            />
          </label>
          {editing && (
            <div>
              <label>
                rules.py
                <textarea
                  rows={24}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  spellCheck={false}
                />
              </label>
              <button
                disabled={busy}
                onClick={() => {
                  void action('executable-imports/' + family.id + '/edit', {
                    base_revision_id: current.id,
                    code,
                  });
                  setEditing(false);
                }}
              >
                Save new draft & test
              </button>
              <details>
                <summary>Generated test fixtures & rule mappings</summary>
                <p>
                  Edit the generated artifact set as JSON. Source instructions, images, generation
                  model and budget stay bound to this import.
                </p>
                <textarea
                  aria-label="Generated artifact JSON"
                  rows={20}
                  value={artifactJson}
                  onChange={(e) => setArtifactJson(e.target.value)}
                  spellCheck={false}
                />
                <button
                  disabled={busy}
                  onClick={async () => {
                    try {
                      const artifacts = JSON.parse(artifactJson);
                      await action('executable-imports/' + family.id + '/edit', {
                        base_revision_id: current.id,
                        artifacts,
                      });
                      setEditing(false);
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  Save artifact draft & test
                </button>
              </details>
            </div>
          )}
          <details>
            <summary>Revision history</summary>
            <ul>
              {family.revisions.map((r: any) => (
                <li key={r.id}>
                  {String(r.id).slice(0, 8)} · {r.kind} · {r.state}
                  {r.generation_model && (
                    <>
                      {' '}
                      · {r.generation_provider} / {r.generation_model} · configuration{' '}
                      {String(r.settings_id).slice(0, 8)}
                    </>
                  )}
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
    </section>
  );
}
