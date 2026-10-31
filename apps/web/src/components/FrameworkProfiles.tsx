'use client';
import { useCallback, useEffect, useState } from 'react';
import Form from './Form';
import { workspaceApi as api } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';

type Profile = {
  id: string;
  name: string;
  framework: string;
  config_hash: string;
  config: {
    runtime_version: string | null;
    qualification: string;
    trace_export_enabled: boolean;
    dispatch_enabled: boolean;
    tracing_project: string | null;
  };
};
const catalog = [
  [
    'harbor',
    'Harbor',
    'Evaluation runner',
    'Existing pinned 0.25.0 structured/staged adapter. Profile binding remains separate from live readiness.',
  ],
  [
    'langsmith',
    'LangSmith',
    'Tracing / evaluation',
    'Adapter not implemented. No external traces are sent.',
  ],
  [
    'semantic_kernel',
    'Semantic Kernel',
    'Candidate agent orchestration',
    'Adapter not implemented. SDK selection does not replace Anvil / LangGraph.',
  ],
];
export default function FrameworkProfiles({
  base,
  onSaved,
}: {
  base: string;
  onSaved?: () => void;
}) {
  const [profiles, setProfiles] = useState<Profile[]>([]),
    [cursor, setCursor] = useState<string | null>(null),
    [editing, setEditing] = useState(false),
    [framework, setFramework] = useState('harbor'),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  const load = useCallback(async () => {
    try {
      const result = await api(base + '/workspace/frameworks');
      setProfiles(result.items);
      setCursor(result.next_cursor);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [base]);
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <>
      <div className={styles.pageHead}>
        <p className={styles.muted}>
          Configure registered integrations by their role. Metadata never installs an SDK or enables
          dispatch.
        </p>
        <button className={styles.primary} onClick={() => setEditing(!editing)}>
          {editing ? 'Close editor' : 'Add framework'}
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      <div className={styles.grid}>
        {catalog.map(([id, name, role, note]) => (
          <section key={id} className={styles.panel}>
            <span className={styles.tag}>{role}</span>
            <h2>{name}</h2>
            <p>{note}</p>
            <button
              onClick={() => {
                setFramework(id);
                setEditing(true);
                setError('');
              }}
            >
              Configure {name}
            </button>
          </section>
        ))}
      </div>
      {editing && (
        <section className={styles.panel}>
          <h2>Add framework profile</h2>
          <Form
            onSubmit={async (e) => {
              e.preventDefault();
              const form = new FormData(e.currentTarget);
              setBusy(true);
              setError('');
              try {
                await api(base + '/workspace/frameworks', 'POST', {
                  name: String(form.get('name')),
                  framework,
                  runtime_version:
                    framework === 'harbor'
                      ? '0.25.0'
                      : String(form.get('runtime_version') || '') || null,
                  tracing_project:
                    framework === 'langsmith'
                      ? String(form.get('tracing_project') || '') || null
                      : null,
                });
                setMessage(
                  'Framework metadata saved. No SDK installed, trace exported or execution enabled.',
                );
                setEditing(false);
                await load();
                onSaved?.();
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              Framework
              <select value={framework} onChange={(e) => setFramework(e.target.value)}>
                {catalog.map(([id, name]) => (
                  <option key={id} value={id}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Profile name
              <input name="name" required maxLength={100} placeholder="Research workspace" />
            </label>
            {framework === 'harbor' ? (
              <p>Existing local worker · Harbor 0.25.0 · no hosted Harbor key required.</p>
            ) : (
              <label>
                Pinned runtime / SDK version
                <input
                  name="runtime_version"
                  maxLength={64}
                  placeholder="Leave unset until reviewed"
                />
              </label>
            )}
            {framework === 'langsmith' && (
              <>
                <label>
                  Tracing project
                  <input
                    name="tracing_project"
                    maxLength={100}
                    placeholder="Permitted project reference"
                  />
                </label>
                <label>
                  LangSmith API key
                  <input type="password" disabled placeholder="Credential integration pending" />
                </label>
                <p>
                  External trace export is off. Saving a project reference sends nothing to
                  LangSmith.
                </p>
              </>
            )}
            {framework === 'semantic_kernel' && (
              <p>
                Semantic Kernel compatibility is explicit. Microsoft Agent Framework is a separate
                future choice. No arbitrary plugins or code are installed here.
              </p>
            )}
            <button className={styles.primary} disabled={busy}>
              {busy ? 'Saving…' : 'Save framework profile'}
            </button>
          </Form>
        </section>
      )}
      <section className={styles.panel}>
        <h2>Saved framework profiles</h2>
        {profiles.length ? (
          <div className={styles.tableScroll}>
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Framework / runtime</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {profiles.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <strong>{p.name}</strong>
                      <small>{p.config_hash.slice(0, 12)}</small>
                    </td>
                    <td>
                      {p.framework}
                      <small>{p.config.runtime_version || 'Version not selected'}</small>
                    </td>
                    <td>
                      {p.config.qualification}
                      <small>Dispatch off · trace export off</small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>No saved framework profiles.</p>
        )}
        {cursor && (
          <button
            onClick={async () => {
              try {
                const next = await api(base + '/workspace/frameworks?after=' + cursor);
                setProfiles([...profiles, ...next.items]);
                setCursor(next.next_cursor);
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            Load more profiles
          </button>
        )}
      </section>
    </>
  );
}
