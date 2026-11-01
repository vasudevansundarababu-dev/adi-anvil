'use client';
import { useCallback, useEffect, useState } from 'react';
import Form from './Form';
import { workspaceApi as api } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';

export type CredentialMetadata = {
  id: string;
  name: string;
  provider: string;
  current_version_id: string | null;
  revoked_at: string | null;
  created_at: string;
};
export default function CredentialManager({
  base,
  onChange,
}: {
  base: string;
  onChange: (values: CredentialMetadata[]) => void;
}) {
  const [credentials, setCredentials] = useState<CredentialMetadata[]>([]),
    [cursor, setCursor] = useState<string | null>(null),
    [entryAvailable, setEntryAvailable] = useState(false),
    [editor, setEditor] = useState<'new' | CredentialMetadata | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  const load = useCallback(
    async (saved?: CredentialMetadata) => {
      try {
        const result = await api(base + '/workspace/credentials');
        const current =
          result.items.find((item: CredentialMetadata) => item.id === saved?.id) || saved;
        const values = saved
          ? [current, ...result.items.filter((item: CredentialMetadata) => item.id !== saved.id)]
          : result.items;
        setCredentials(values);
        onChange(values);
        setEntryAvailable(result.entry_available);
        setCursor(result.next_cursor);
      } catch (e) {
        setError((e as Error).message);
      }
    },
    [base, onChange],
  );
  useEffect(() => {
    void load();
    const focus = () => void load();
    window.addEventListener('focus', focus);
    return () => window.removeEventListener('focus', focus);
  }, [load]);
  async function revoke(record: CredentialMetadata) {
    setBusy(true);
    setError('');
    try {
      const saved = await api(base + '/workspace/credentials/' + record.id + '/revoke', 'POST', {});
      setMessage('Credential revoked for future use. Historical records were preserved.');
      await load(saved);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className={styles.panel}>
      <div className={styles.pageHead}>
        <div>
          <h2>Credentials</h2>
          <p className={styles.muted}>
            Write-only values, versioned metadata. Keys never appear in lists or exports.
          </p>
        </div>
        <button
          disabled={!entryAvailable || busy}
          onClick={() => {
            setEditor(editor ? null : 'new');
            setError('');
            setMessage('');
          }}
        >
          {editor ? 'Close credential editor' : 'Add credential'}
        </button>
      </div>
      {!entryAvailable && (
        <p>
          Cloud key entry awaits the managed secret-store adapter. Existing private server
          configuration remains separate.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {credentials.length ? (
        <div className={styles.tableScroll}>
          <table>
            <thead>
              <tr>
                <th>Name / provider</th>
                <th>Version / state</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {credentials.map((c) => (
                <tr key={c.id}>
                  <td>
                    {c.name}
                    <small>{c.provider}</small>
                  </td>
                  <td>
                    {c.current_version_id?.slice(0, 8) || 'No version'}
                    <small>{c.revoked_at ? 'Revoked' : 'Configured · not live-qualified'}</small>
                  </td>
                  <td>
                    <div className={styles.actions}>
                      <button
                        disabled={busy || !!c.revoked_at || !entryAvailable}
                        onClick={() => {
                          setEditor(c);
                          setMessage('');
                          setError('');
                        }}
                      >
                        Rotate
                      </button>
                      <button
                        disabled={busy || !!c.revoked_at || !entryAvailable}
                        onClick={() => void revoke(c)}
                      >
                        Revoke
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>No project credentials configured.</p>
      )}
      {cursor && (
        <button
          disabled={busy}
          onClick={async () => {
            try {
              const next = await api(base + '/workspace/credentials?after=' + cursor);
              const existing = new Set(credentials.map((item) => item.id));
              const values = [
                ...credentials,
                ...next.items.filter((item: CredentialMetadata) => !existing.has(item.id)),
              ];
              setCredentials(values);
              onChange(values);
              setCursor(next.next_cursor);
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        >
          Load more credentials
        </button>
      )}
      {editor && (
        <Form
          key={typeof editor === 'string' ? editor : editor.id}
          onSubmit={async (e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const data = new FormData(form);
            const secret = String(data.get('secret'));
            const input = form.elements.namedItem('secret') as HTMLInputElement;
            input.value = '';
            setBusy(true);
            setError('');
            try {
              let saved: CredentialMetadata;
              if (editor === 'new') {
                saved = await api(base + '/workspace/credentials', 'POST', {
                  name: String(data.get('credential_name')),
                  provider: String(data.get('credential_provider')),
                  secret,
                });
              } else {
                saved = await api(
                  base + '/workspace/credentials/' + editor.id + '/versions',
                  'POST',
                  {
                    secret,
                  },
                );
              }
              setEditor(null);
              setMessage(
                'Credential version saved. The value cannot be read back; no model request was sent.',
              );
              await load(saved);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <h3 style={{ marginTop: 20 }}>
            {editor === 'new' ? 'New credential' : 'Rotate ' + editor.name}
          </h3>
          {editor === 'new' ? (
            <>
              <label>
                Credential name
                <input name="credential_name" required maxLength={100} autoComplete="off" />
              </label>
              <label>
                Credential provider
                <select name="credential_provider">
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic Claude</option>
                  <option value="gemini">Google Gemini</option>
                  <option value="langsmith">LangSmith</option>
                </select>
              </label>
            </>
          ) : (
            <p>{editor.provider} · new immutable version</p>
          )}
          <label>
            Secret value
            <input
              name="secret"
              type="password"
              required
              maxLength={8192}
              autoComplete="off"
              spellCheck={false}
            />
          </label>
          <p className={styles.muted}>
            Local encrypted storage only. Saving grants no spending authority. Credential changes
            require a recent sign-in. Rotation invalidates profiles bound to the older version for
            future dispatch.
          </p>
          <button className={styles.primary} disabled={busy}>
            {busy ? 'Saving…' : 'Save credential version'}
          </button>
        </Form>
      )}
    </section>
  );
}
