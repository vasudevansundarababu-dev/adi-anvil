'use client';

import { useEffect, useRef, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';

export default function ImportGenerationSettings({ base }: { base: string }) {
  const [settings, setSettings] = useState<any>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const pending = useRef<{ fingerprint: string; key: string } | null>(null);
  const endpoint = base + '/workspace/import-generation/settings';
  useEffect(() => {
    api(endpoint)
      .then(setSettings)
      .catch((e) => setError(e.message));
  }, [endpoint]);
  return (
    <section className={styles.panel} aria-label="Standard import generation model">
      <h2>Standard import generation model</h2>
      <p>
        One model for the entire Anvil installation generates task verifiers and constraints.
        Evaluation models below run your tasks separately.
      </p>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {!settings && !error && <p role="status">Loading generation settings…</p>}
      {settings?.configured ? (
        <p>
          {settings.provider} · {settings.model_id} · Key saved · Whole-import cap $
          {(settings.default_cap_micro_usd / 1000000).toFixed(2)} · Configuration{' '}
          {String(settings.id).slice(0, 8)}
        </p>
      ) : (
        settings && <p>{settings.missing || 'Generation configuration is unavailable.'}</p>
      )}
      {settings && !settings.can_configure && (
        <p>
          Your project role does not include installation settings access. An installation Admin
          manages this shared model.
        </p>
      )}
      {settings?.can_configure && (
        <details>
          <summary>
            {settings.configured ? 'Save a new generation configuration' : 'Configure generation'}
          </summary>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setError('');
              setMessage('');
              setBusy(true);
              const form = e.currentTarget,
                data = new FormData(form);
              try {
                const cap = Math.round(Number(data.get('cap')) * 1000000);
                if (!Number.isSafeInteger(cap) || cap <= 0)
                  throw new Error('Enter a positive whole-import API budget.');
                const body = {
                  provider: data.get('provider'),
                  model_id: data.get('model'),
                  secret: data.get('secret'),
                  default_cap_micro_usd: cap,
                  max_calls: Number(data.get('calls')),
                  max_output_tokens: Number(data.get('tokens')),
                  enable_paid_generation: data.get('enabled') === 'on',
                };
                const bytes = await crypto.subtle.digest(
                  'SHA-256',
                  new TextEncoder().encode(JSON.stringify(body)),
                );
                const fingerprint = Array.from(new Uint8Array(bytes), (b) =>
                  b.toString(16).padStart(2, '0'),
                ).join('');
                if (pending.current?.fingerprint !== fingerprint)
                  pending.current = { fingerprint, key: crypto.randomUUID() };
                const saved = await api(endpoint, 'POST', body, undefined, pending.current!.key);
                pending.current = null;
                form.reset();
                setSettings(saved);
                setMessage(
                  'Generation model and key saved. Existing imports keep their configuration and cumulative cap.',
                );
              } catch (err) {
                setError((err as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              Provider
              <select name="provider">
                <option value="openai">OpenAI</option>
                <option value="anthropic">Claude</option>
                <option value="gemini">Gemini</option>
              </select>
            </label>
            <label>
              Exact model ID
              <input name="model" required autoComplete="off" />
            </label>
            <label>
              Generation API key
              <input type="password" name="secret" required autoComplete="new-password" />
            </label>
            <label>
              Whole-import API cap (USD)
              <input name="cap" type="number" min="0.000001" step="0.000001" required />
            </label>
            <label>
              Maximum generation calls per import
              <input name="calls" type="number" min="1" max="20" defaultValue="5" required />
            </label>
            <label>
              Maximum output tokens per generation call
              <input
                name="tokens"
                type="number"
                min="1024"
                max="8192"
                defaultValue="8192"
                required
              />
            </label>
            <label>
              <input name="enabled" type="checkbox" />
              Authorize generation with this exact model within each import cap
            </label>
            <p>
              Imports and regenerations share one cap. Saving makes no model request; the server
              must also have generation enabled.
            </p>
            <button disabled={busy}>{busy ? 'Saving…' : 'Save generation configuration'}</button>
          </form>
        </details>
      )}
    </section>
  );
}
