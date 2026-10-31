'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import CredentialManager, { CredentialMetadata } from './CredentialManager';
import ModelProfileEditor, { ModelConfiguration as Model } from './ModelProfileEditor';
import { workspaceApi as api, shortId } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';

export default function ModelProfiles({ base }: { base: string }) {
  const [credentials, setCredentials] = useState<CredentialMetadata[]>([]);
  const [models, setModels] = useState<Model[]>([]),
    [cursor, setCursor] = useState<string | null>(null),
    [editing, setEditing] = useState(false),
    [source, setSource] = useState<Model | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  const [history, setHistory] = useState<{ items: Model[]; next_cursor: number | null } | null>(
      null,
    ),
    [historyId, setHistoryId] = useState('');
  const generation = useRef(0);
  const load = useCallback(async () => {
    const current = ++generation.current;
    setBusy(true);
    try {
      const result = await api(base + '/workspace/models?current_only=true');
      if (current === generation.current) {
        setModels(result.items);
        setCursor(result.next_cursor);
      }
    } catch (e) {
      if (current === generation.current) setError((e as Error).message);
    } finally {
      if (current === generation.current) setBusy(false);
    }
  }, [base]);
  useEffect(() => {
    void load();
    return () => {
      generation.current++;
    };
  }, [load]);
  const credentialsChanged = useCallback(
    (values: CredentialMetadata[]) => {
      setCredentials(values);
      void load();
    },
    [load],
  );
  async function openHistory(id: string) {
    try {
      setHistory(await api(base + '/workspace/models/' + id + '/versions'));
      setHistoryId(id);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <>
      {!editing && (
        <section className={styles.panel} aria-label="Model profile list" aria-busy={busy}>
          <div className={styles.pageHead}>
            <div>
              <h2>Model profiles</h2>
              <p className={styles.muted}>
                Multiple exact models per provider. Changes create new versions; saving
                configuration makes no model request.
              </p>
            </div>
            <button
              className={styles.primary}
              onClick={() => {
                setEditing(!editing);
                setSource(null);
                setMessage('');
              }}
            >
              {editing ? 'Close editor' : 'Add model'}
            </button>
          </div>
          {error && <p role="alert">{error}</p>}
          {message && <p role="status">{message}</p>}
          {busy && <p role="status">Loading model profiles…</p>}
          {models.length ? (
            <div className={styles.tableScroll}>
              <table>
                <thead>
                  <tr>
                    <th>Profile</th>
                    <th>Provider / model</th>
                    <th>Credential</th>
                    <th>Availability</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {models.map((m) => (
                    <tr key={m.id}>
                      <td>
                        <strong>{m.name}</strong>
                        <small>
                          {m.version ? 'Version ' + m.version : 'Legacy configuration'} ·{' '}
                          {shortId(m.config_hash)}
                        </small>
                      </td>
                      <td>
                        {m.provider}
                        <small>{m.model_id || 'Exact model missing'}</small>
                      </td>
                      <td>
                        {m.credential_state ||
                          (m.credential_present ? 'Server configured' : 'Key missing')}
                      </td>
                      <td>
                        {m.status === 'disabled'
                          ? 'Disabled'
                          : m.status === 'revoked'
                            ? 'Revoked'
                            : 'Planning only'}
                        <small>Pricing: {m.pricing_state.replaceAll('_', ' ')}</small>
                        <small>Exact run qualification remains required</small>
                      </td>
                      <td>
                        {m.workspace_profile && (
                          <div className={styles.actions}>
                            <button
                              disabled={!m.is_current || ['disabled', 'revoked'].includes(m.status)}
                              onClick={() => {
                                setSource(m);
                                setEditing(true);
                                setError('');
                                setMessage('');
                              }}
                            >
                              Edit as new version
                            </button>
                            <button onClick={() => void openHistory(m.id)}>Version history</button>
                            <button
                              disabled={!m.is_current || m.status === 'disabled'}
                              onClick={async () => {
                                try {
                                  setError('');
                                  await api(
                                    base + '/workspace/models/' + m.id + '/disable',
                                    'POST',
                                    {},
                                    m.profile_row_version,
                                  );
                                  setMessage(
                                    'Profile disabled for new preparations. All historical bindings remain intact.',
                                  );
                                  await load();
                                  if (historyId) await openHistory(m.id);
                                } catch (e) {
                                  setError((e as Error).message);
                                }
                              }}
                            >
                              Disable profile
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            !busy && <p>No model profiles configured yet.</p>
          )}
          {cursor && (
            <button
              disabled={busy}
              onClick={async () => {
                const current = generation.current;
                setBusy(true);
                try {
                  const result = await api(
                    base + '/workspace/models?current_only=true&after=' + cursor,
                  );
                  if (current === generation.current) {
                    setModels((old) => [...old, ...result.items]);
                    setCursor(result.next_cursor);
                  }
                } catch (e) {
                  if (current === generation.current) setError((e as Error).message);
                } finally {
                  if (current === generation.current) setBusy(false);
                }
              }}
            >
              Load more profiles
            </button>
          )}
        </section>
      )}
      {editing && (
        <ModelProfileEditor
          key={source?.id || 'new'}
          base={base}
          source={source}
          credentials={credentials}
          cancel={() => {
            setEditing(false);
            setSource(null);
          }}
          saved={(value) => {
            setEditing(false);
            setSource(null);
            setMessage(
              source
                ? 'New model version saved. Earlier preparation bindings stay unchanged.'
                : 'Profile saved to this project. No inference, activation or paid authority created.',
            );
            void load();
            void openHistory(value.id);
          }}
        />
      )}
      {history && !editing && (
        <section className={styles.panel}>
          <h2>Model version history</h2>
          <p>
            Saved configurations are immutable. Superseded or disabled versions cannot be selected
            for a new preparation.
          </p>
          {history.items.map((m) => (
            <details key={m.id}>
              <summary>
                Version {m.version} · {m.name} · {m.is_current ? 'current' : 'historical'}
                {m.status === 'disabled' ? ' · disabled' : ''}
              </summary>
              <p>
                {m.provider}/{m.model_id} · {m.max_output_tokens} output tokens
              </p>
              <p>
                Credential: {m.credential_state}. Pricing: {m.pricing_state.replaceAll('_', ' ')}.
              </p>
              <pre>
                {JSON.stringify(
                  {
                    profile_id: m.profile_id,
                    connection_id: m.id,
                    config_hash: m.config_hash,
                    credential_binding: m.credential_binding,
                    pricing: m.pricing,
                    processing_terms: m.processing_terms,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          ))}
          {history.next_cursor && (
            <button
              onClick={async () => {
                try {
                  const next = await api(
                    base +
                      '/workspace/models/' +
                      historyId +
                      '/versions?after=' +
                      history.next_cursor,
                  );
                  setHistory({ ...next, items: [...history.items, ...next.items] });
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              Load more versions
            </button>
          )}
        </section>
      )}
      <CredentialManager base={base} onChange={credentialsChanged} />
    </>
  );
}
