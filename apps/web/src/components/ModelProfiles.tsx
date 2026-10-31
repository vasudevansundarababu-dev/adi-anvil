'use client';
import { useCallback, useEffect, useState } from 'react';
import Form from './Form';
import CredentialManager, { CredentialMetadata } from './CredentialManager';
import { workspaceApi as api } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';

type Model = {
  id: string;
  name: string;
  provider: string;
  model_id: string | null;
  credential_present: boolean;
  credential_state: string;
  status: string;
  config_hash: string;
  max_output_tokens: number | null;
};
export default function ModelProfiles({ base }: { base: string }) {
  const [credentials, setCredentials] = useState<CredentialMetadata[]>([]);
  const [provider, setProvider] = useState('openai');
  const [models, setModels] = useState<Model[]>([]),
    [cursor, setCursor] = useState<string | null>(null),
    [editing, setEditing] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  const load = useCallback(async () => {
    try {
      setError('');
      const result = await api(base + '/workspace/models');
      setModels(result.items);
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
      <section className={styles.panel}>
        <div className={styles.pageHead}>
          <div>
            <h2>Model profiles</h2>
            <p className={styles.muted}>
              Multiple exact models per provider. Saving configuration makes no model request.
            </p>
          </div>
          <button
            className={styles.primary}
            onClick={() => {
              setEditing(!editing);
              setMessage('');
            }}
          >
            {editing ? 'Close editor' : 'Add model'}
          </button>
        </div>
        {error && <p role="alert">{error}</p>}
        {message && <p role="status">{message}</p>}
        {models.length ? (
          <div className={styles.tableScroll}>
            <table>
              <thead>
                <tr>
                  <th>Profile</th>
                  <th>Provider / model</th>
                  <th>Credential</th>
                  <th>Availability</th>
                </tr>
              </thead>
              <tbody>
                {models.map((m) => (
                  <tr key={m.id}>
                    <td>
                      <strong>{m.name}</strong>
                      <small>{m.config_hash.slice(0, 12)}</small>
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
                      {m.status === 'revoked' ? 'Revoked' : 'Planning only'}
                      <small>Exact run qualification remains required</small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>No model profiles configured yet.</p>
        )}
        {cursor && (
          <button
            onClick={async () => {
              try {
                const result = await api(base + '/workspace/models?after=' + cursor);
                setModels([...models, ...result.items]);
                setCursor(result.next_cursor);
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            Load more profiles
          </button>
        )}
      </section>
      {editing && (
        <section className={styles.panel}>
          <h2>Add model profile</h2>
          <Form
            onSubmit={async (e) => {
              e.preventDefault();
              const data = new FormData(e.currentTarget);
              setBusy(true);
              setError('');
              try {
                await api(base + '/workspace/models', 'POST', {
                  name: String(data.get('name')),
                  provider: String(data.get('provider')),
                  model_id: String(data.get('model_id')),
                  max_output_tokens: Number(data.get('max_output_tokens')),
                  credential_id: String(data.get('credential_id') || '') || null,
                });
                setEditing(false);
                setMessage(
                  'Profile saved to this project. No inference, activation or paid authority created.',
                );
                await load();
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              Provider
              <select
                name="provider"
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
              >
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic Claude</option>
                <option value="gemini">Google Gemini</option>
              </select>
            </label>
            <label>
              Profile name
              <input name="name" required maxLength={100} placeholder="Research baseline" />
            </label>
            <label>
              Exact model ID
              <input
                name="model_id"
                required
                maxLength={200}
                pattern="[A-Za-z0-9][A-Za-z0-9._:/@\-]*"
                placeholder="Enter an entitled provider model ID"
              />
            </label>
            <label>
              Maximum output tokens
              <input
                name="max_output_tokens"
                type="number"
                defaultValue={4096}
                min={1}
                max={8192}
                required
              />
            </label>
            <label>
              API key
              <input
                type="password"
                disabled
                placeholder="Add write-only values in Credentials below"
              />
            </label>
            <label>
              Credential version
              <select name="credential_id">
                <option value="">Existing private server configuration / missing</option>
                {credentials
                  .filter((c) => c.provider === provider && !c.revoked_at && c.current_version_id)
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} · {c.current_version_id?.slice(0, 8)}
                    </option>
                  ))}
              </select>
            </label>
            <p className={styles.muted}>
              Add or rotate write-only values in Credentials below. Never paste a key into another
              field. Profiles are not available for dispatch until their qualified adapter and
              exact-run gates are satisfied.
            </p>
            <button className={styles.primary} disabled={busy}>
              {busy ? 'Saving…' : 'Save model profile'}
            </button>
          </Form>
        </section>
      )}
      <CredentialManager base={base} onChange={setCredentials} />
    </>
  );
}
