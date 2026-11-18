'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import CredentialManager, { CredentialMetadata } from './CredentialManager';
import ModelProfileEditor, { ModelConfiguration as Model } from './ModelProfileEditor';
import { workspaceApi as api, shortId } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';
import ImportGenerationSettings from './ImportGenerationSettings';

export default function ModelProfiles({ base }: { base: string }) {
  const [catalog, setCatalog] = useState<
    {
      id: string;
      label: string;
      publisher: string;
      license_claim: string;
      repositories: { repository: string; revision: string; repository_url: string }[];
    }[]
  >([]);
  const [catalogSelection, setCatalogSelection] = useState<string[]>([]);
  const [sharedCredential, setSharedCredential] = useState('');
  const [catalogError, setCatalogError] = useState('');
  const [group, setGroup] = useState('all');
  const [newProvider, setNewProvider] = useState('openai');
  useEffect(() => {
    let active = true;
    api(base + '/workspace/models/catalog')
      .then((value) => {
        if (active) setCatalog(value.items);
      })
      .catch((e) => {
        if (active) setCatalogError((e as Error).message);
      });
    return () => {
      active = false;
    };
  }, [base]);
  const [credentials, setCredentials] = useState<CredentialMetadata[]>([]);
  const [credentialsLoading, setCredentialsLoading] = useState(true),
    [credentialError, setCredentialError] = useState('');
  const credentialGeneration = useRef(0);
  const refreshCredentials = useCallback(async () => {
    const current = ++credentialGeneration.current;
    setCredentialsLoading(true);
    setCredentialError('');
    try {
      const values = new Map<string, CredentialMetadata>();
      const seen = new Set<string>();
      let after: string | null = null;
      do {
        const page = await api(
          base +
            '/workspace/credentials?limit=100' +
            (after ? '&after=' + encodeURIComponent(after) : ''),
        );
        if (current !== credentialGeneration.current) return;
        for (const item of page.items as CredentialMetadata[]) values.set(item.id, item);
        after = page.next_cursor;
        if (after && seen.has(after))
          throw new Error(
            'Credential list changed while loading. Refresh credential versions again.',
          );
        if (after) seen.add(after);
      } while (after);
      setCredentials([...values.values()]);
    } catch (e) {
      if (current === credentialGeneration.current) setCredentialError((e as Error).message);
    } finally {
      if (current === credentialGeneration.current) setCredentialsLoading(false);
    }
  }, [base]);
  useEffect(() => {
    void refreshCredentials();
    const focus = () => void refreshCredentials();
    window.addEventListener('focus', focus);
    return () => {
      credentialGeneration.current++;
      window.removeEventListener('focus', focus);
    };
  }, [refreshCredentials]);
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
    [historyId, setHistoryId] = useState(''),
    [historyFocus, setHistoryFocus] = useState(0);
  const generation = useRef(0);
  const historyGeneration = useRef(0),
    historyHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (!editing && historyFocus) {
      historyHeading.current?.focus();
      historyHeading.current?.scrollIntoView({ block: 'start' });
    }
  }, [historyFocus, editing]);
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
      historyGeneration.current++;
    };
  }, [load]);
  const credentialsChanged = useCallback(() => {
    void refreshCredentials();
    void load();
  }, [load, refreshCredentials]);
  async function openHistory(id: string) {
    const current = ++historyGeneration.current;
    setError('');
    try {
      const result = await api(base + '/workspace/models/' + id + '/versions');
      if (current === historyGeneration.current) {
        setHistory(result);
        setHistoryId(id);
        setHistoryFocus((old) => old + 1);
      }
    } catch (e) {
      if (current === historyGeneration.current) setError((e as Error).message);
    }
  }
  return (
    <>
      <ImportGenerationSettings base={base} />
      {!editing && (
        <section className={styles.panel} aria-label="Open Weight Models">
          <h2>Open Weight Models</h2>
          <p>
            All models from your workbook are listed below. Save one Hugging Face credential and
            reuse it across model profiles. Accept repository terms in Hugging Face separately.
          </p>
          <p>
            Repository choices and commit revisions were observed in public Hub metadata. License
            claims and your account access require review. Inference runtime setup is pending; no
            model calls are enabled.
          </p>
          {catalogError && <p role="alert">{catalogError}</p>}
          <details>
            <summary>View workbook model catalog ({catalog.length})</summary>
            <ul>
              {catalog.map((item) => (
                <li key={item.id}>
                  {item.publisher} · {item.label} · License claim: {item.license_claim} · Setup
                  pending
                </li>
              ))}
            </ul>
          </details>
          <form
            onSubmit={async (event) => {
              event.preventDefault();
              setBusy(true);
              setError('');
              setMessage('');
              try {
                const [credentialId, credentialVersion] = sharedCredential.split(':');
                const selected = catalog
                  .flatMap((item) =>
                    item.repositories.map((repo) => ({
                      catalog_id: item.id,
                      repository: repo.repository,
                      revision: repo.revision,
                    })),
                  )
                  .filter((item) =>
                    catalogSelection.includes(item.catalog_id + ':' + item.repository),
                  );
                const result = await api(base + '/workspace/models/catalog/register', 'POST', {
                  models: selected,
                  credential_id: credentialId || null,
                  credential_version_id: credentialVersion || null,
                });
                setMessage(
                  result.items.length +
                    ' exact model versions registered. Live execution remains disabled.',
                );
                setCatalogSelection([]);
                setGroup('open-weight-models');
                await load();
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              Shared Hugging Face credential
              <select
                value={sharedCredential}
                onChange={(event) => setSharedCredential(event.target.value)}
                disabled={credentialsLoading}
              >
                <option value="">Configure models now; link a token later</option>
                {credentials
                  .filter(
                    (item) =>
                      item.provider === 'huggingface' &&
                      !item.revoked_at &&
                      item.current_version_id,
                  )
                  .map((item) => (
                    <option key={item.id} value={item.id + ':' + item.current_version_id}>
                      {item.name} · version {item.current_version_id?.slice(0, 8)}
                    </option>
                  ))}
              </select>
            </label>
            <details>
              <summary>
                Select repository variants and versions ({catalogSelection.length} selected)
              </summary>
              <button
                type="button"
                disabled={!catalog.length || !!catalogError}
                onClick={() =>
                  setCatalogSelection(
                    catalog.flatMap((item) =>
                      item.repositories.map((repo) => item.id + ':' + repo.repository),
                    ),
                  )
                }
              >
                Select all listed versions
              </button>
              <button type="button" onClick={() => setCatalogSelection([])}>
                Clear selection
              </button>
              {catalog.map((item) => (
                <fieldset key={item.id}>
                  <legend>{item.label}</legend>
                  {item.repositories.map((repo) => {
                    const key = item.id + ':' + repo.repository;
                    return (
                      <label key={key} style={{ display: 'block' }}>
                        <input
                          type="checkbox"
                          checked={catalogSelection.includes(key)}
                          onChange={(event) =>
                            setCatalogSelection((current) =>
                              event.target.checked
                                ? [...current, key]
                                : current.filter((value) => value !== key),
                            )
                          }
                        />
                        {repo.repository} · commit {repo.revision}
                        <a href={repo.repository_url} target="_blank" rel="noreferrer">
                          {' '}
                          Repository and terms
                        </a>
                      </label>
                    );
                  })}
                </fieldset>
              ))}
            </details>
            <button
              className={styles.primary}
              disabled={
                busy ||
                credentialsLoading ||
                !catalogSelection.length ||
                (!!sharedCredential &&
                  !credentials.some(
                    (item) =>
                      !item.revoked_at &&
                      item.id + ':' + item.current_version_id === sharedCredential,
                  ))
              }
            >
              Add selected model versions
            </button>
          </form>
          <button
            onClick={() => {
              setSource(null);
              setNewProvider('huggingface');
              setEditing(true);
            }}
          >
            Configure a catalog model
          </button>
        </section>
      )}
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
                setNewProvider('openai');
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
          <label>
            Model group
            <select value={group} onChange={(e) => setGroup(e.target.value)}>
              <option value="all">All models</option>
              <option value="open-weight-models">Open Weight Models</option>
              <option value="provider-models">Provider models</option>
            </select>
          </label>
          {!busy &&
            models.length > 0 &&
            !models.some((m) => group === 'all' || (m.group || 'provider-models') === group) && (
              <p>
                No saved profiles in this group. Configure a catalog model above to select an exact
                repository and revision.
              </p>
            )}
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
                  {models
                    .filter((m) => group === 'all' || (m.group || 'provider-models') === group)
                    .map((m) => (
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
                          {m.hub && <small>Hub revision {m.hub.revision} · Setup pending</small>}
                        </td>
                        <td>
                          {m.credential_present
                            ? 'Saved key linked'
                            : m.credential_state === 'rotated'
                              ? 'Key rotated · select current version'
                              : m.credential_state === 'revoked'
                                ? 'Key revoked'
                                : 'No key linked'}
                        </td>
                        <td>
                          {m.status === 'disabled'
                            ? 'Disabled'
                            : m.status === 'revoked'
                              ? 'Revoked'
                              : 'Planning only'}
                        </td>
                        <td>
                          {m.workspace_profile && (
                            <div className={styles.actions}>
                              <button
                                disabled={
                                  !m.is_current || ['disabled', 'revoked'].includes(m.status)
                                }
                                onClick={() => {
                                  setSource(m);
                                  setEditing(true);
                                  setError('');
                                  setMessage('');
                                }}
                              >
                                Edit as new version
                              </button>
                              <button onClick={() => void openHistory(m.id)}>
                                Version history
                              </button>
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
          initialProvider={newProvider}
          credentials={credentials}
          credentialsLoading={credentialsLoading}
          credentialError={credentialError}
          refreshCredentials={() => void refreshCredentials()}
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
          <h2 ref={historyHeading} tabIndex={-1}>
            Model version history
          </h2>
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
              <p>Credential: {m.credential_state}.</p>
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
                const current = historyGeneration.current;
                try {
                  const next = await api(
                    base +
                      '/workspace/models/' +
                      historyId +
                      '/versions?after=' +
                      history.next_cursor,
                  );
                  if (current === historyGeneration.current)
                    setHistory({ ...next, items: [...history.items, ...next.items] });
                } catch (e) {
                  if (current === historyGeneration.current) setError((e as Error).message);
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
