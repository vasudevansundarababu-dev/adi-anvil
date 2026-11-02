'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
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
    [saveError, setSaveError] = useState(''),
    [saveUncertain, setSaveUncertain] = useState(false),
    [message, setMessage] = useState('');
  const saveFeedback = useRef<HTMLDivElement>(null);
  const confirmation = useRef<HTMLParagraphElement>(null);
  const editorHeading = useRef<HTMLHeadingElement>(null);
  const saveAttempt = useRef<string | null>(null);
  useEffect(() => {
    if (editor) {
      editorHeading.current?.focus();
      editorHeading.current?.scrollIntoView({ block: 'start' });
    }
  }, [editor]);
  useEffect(() => {
    const target = saveError ? saveFeedback.current : message ? confirmation.current : null;
    target?.focus();
    target?.scrollIntoView({ block: 'center' });
  }, [saveError, message]);
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
        setError(
          saved
            ? 'Your key was saved, but the credential list could not refresh. ' +
                (e as Error).message
            : (e as Error).message,
        );
        if (saved) {
          setCredentials((old) => [saved, ...old.filter((item) => item.id !== saved.id)]);
          onChange([saved]);
        }
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
    <section className={styles.panel} aria-label="Project credentials">
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
            setSaveError('');
            saveAttempt.current = null;
            setMessage('');
          }}
        >
          {editor ? 'Close credential editor' : 'Add credential'}
        </button>
      </div>
      {!entryAvailable && (
        <p>
          Managed credential storage is not configured on this server. Ask your installation
          administrator to complete setup.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {message && (
        <p role="status" ref={confirmation} tabIndex={-1}>
          {message}
        </p>
      )}
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
                    <small>
                      {c.revoked_at
                        ? 'Revoked'
                        : c.current_version_id
                          ? 'Saved securely'
                          : 'No saved value'}
                    </small>
                  </td>
                  <td>
                    <div className={styles.actions}>
                      <button
                        disabled={busy || !!c.revoked_at || !entryAvailable}
                        onClick={() => {
                          setEditor(c);
                          setMessage('');
                          setError('');
                          setSaveError('');
                          saveAttempt.current = null;
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
          onInput={() => {
            saveAttempt.current = null;
          }}
          onSubmit={async (e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const data = new FormData(form);
            const secret = String(data.get('secret'));
            const input = form.elements.namedItem('secret') as HTMLInputElement;
            setBusy(true);
            setError('');
            setSaveError('');
            setSaveUncertain(false);
            setMessage('');
            try {
              const attempt = saveAttempt.current || crypto.randomUUID();
              saveAttempt.current = attempt;
              let saved: CredentialMetadata;
              if (editor === 'new') {
                saved = await api(
                  base + '/workspace/credentials',
                  'POST',
                  {
                    name: String(data.get('credential_name')),
                    provider: String(data.get('credential_provider')),
                    secret,
                  },
                  undefined,
                  attempt,
                );
              } else {
                saved = await api(
                  base + '/workspace/credentials/' + editor.id + '/versions',
                  'POST',
                  {
                    secret,
                  },
                  undefined,
                  attempt,
                );
              }
              input.value = '';
              saveAttempt.current = null;
              setEditor(null);
              setMessage(
                'Key saved securely: ' +
                  saved.name +
                  '. Select its Credential version in the model editor and save the model profile to link it. The key value stays hidden.',
              );
              await load(saved);
            } catch (e) {
              const message = (e as Error).message;
              const status = (e as Error & { status?: number }).status;
              const uncertain = !status || status >= 500 || status === 408;
              setSaveUncertain(uncertain);
              setSaveError(
                /Reauthentication required|Sign in required/i.test(message)
                  ? 'Sign in again before saving a new key or rotating it. No new key was saved. Existing keys are unchanged.'
                  : uncertain
                    ? 'The connection was interrupted, so the save result is unknown. Retry without changing these fields to safely confirm the same save.'
                    : message,
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          <h3 style={{ marginTop: 20 }} ref={editorHeading} tabIndex={-1}>
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
          {saveError && (
            <div role="alert" ref={saveFeedback} tabIndex={-1} className={styles.error}>
              <strong>{saveUncertain ? 'Save could not be confirmed' : 'Key not saved'}</strong>
              <p>{saveError}</p>
              {/Sign in again/i.test(saveError) && (
                <a className="button" href="/api/v1/auth/login">
                  Sign in again
                </a>
              )}
            </div>
          )}
          <button className={styles.primary} disabled={busy}>
            {busy ? 'Saving…' : 'Save credential version'}
          </button>
        </Form>
      )}
    </section>
  );
}
