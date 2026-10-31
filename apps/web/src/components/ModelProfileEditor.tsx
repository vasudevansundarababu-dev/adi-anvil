'use client';
import { useEffect, useRef, useState } from 'react';
import Form from './Form';
import { CredentialMetadata } from './CredentialManager';
import { workspaceApi as api } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';

export type ModelConfiguration = {
  id: string;
  name: string;
  provider: string;
  model_id: string | null;
  credential_present: boolean;
  credential_state: string;
  status: string;
  config_hash: string;
  max_output_tokens: number | null;
  workspace_profile: boolean;
  profile_id: string | null;
  version: number | null;
  profile_row_version: number;
  is_current: boolean;
  credential_binding: { id: string; version_id: string } | null;
  pricing_state: string;
  pricing: {
    reference: string;
    source_url: string;
    input_micro_usd_per_million_tokens: number;
    output_micro_usd_per_million_tokens: number;
    expires_at: string;
  } | null;
  processing_terms: { reviewed: boolean; reference: string | null } | null;
};
function dollars(value: number | undefined) {
  return value === undefined
    ? ''
    : Math.floor(value / 1000000) + '.' + String(value % 1000000).padStart(6, '0');
}
function micros(value: FormDataEntryValue | null) {
  const text = String(value || '');
  if (!/^\d+(\.\d{1,6})?$/.test(text))
    throw new Error('Enter prices in USD with at most six decimal places.');
  const [whole, fraction = ''] = text.split('.');
  const amount = Number(whole) * 1000000 + Number(fraction.padEnd(6, '0'));
  if (!Number.isSafeInteger(amount)) throw new Error('The entered price is too large.');
  return amount;
}
function localTime(value?: string) {
  if (!value) return '';
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
export default function ModelProfileEditor({
  base,
  source,
  credentials,
  saved,
  cancel,
}: {
  base: string;
  source: ModelConfiguration | null;
  credentials: CredentialMetadata[];
  saved: (value: ModelConfiguration) => void;
  cancel: () => void;
}) {
  const [provider, setProvider] = useState(source?.provider || 'openai');
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
    heading.current?.scrollIntoView({ block: 'start' });
  }, []);
  const [credential, setCredential] = useState(
    source?.credential_binding
      ? source.credential_binding.id + ':' + source.credential_binding.version_id
      : '',
  );
  const [pricing, setPricing] = useState(!!source?.pricing),
    [terms, setTerms] = useState(!!source?.processing_terms?.reviewed);
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const available = credentials.filter(
    (c) => c.provider === provider && !c.revoked_at && c.current_version_id,
  );
  const oldBinding =
    !!credential && !available.some((c) => c.id + ':' + c.current_version_id === credential);
  return (
    <section className={styles.panel} aria-label="Model configuration editor">
      <h2 ref={heading} tabIndex={-1}>
        {source ? 'Edit model as new version' : 'Add model profile'}
      </h2>
      {source && (
        <p>
          Based on version {source.version}. Previous settings, approvals and preparation bindings
          stay unchanged.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      <Form
        onSubmit={async (e) => {
          e.preventDefault();
          const data = new FormData(e.currentTarget);
          setBusy(true);
          setError('');
          try {
            const [credentialId, credentialVersion] = credential.split(':');
            const body = {
              name: String(data.get('name')),
              provider,
              model_id: String(data.get('model_id')),
              max_output_tokens: Number(data.get('max_output_tokens')),
              credential_id: credentialId || null,
              credential_version_id: credentialVersion || null,
              pricing: pricing
                ? {
                    reference: String(data.get('pricing_reference')),
                    source_url: String(data.get('pricing_source')),
                    input_micro_usd_per_million_tokens: micros(data.get('input_price')),
                    output_micro_usd_per_million_tokens: micros(data.get('output_price')),
                    expires_at: new Date(String(data.get('pricing_expiry'))).toISOString(),
                  }
                : null,
              processing_terms_reviewed: terms,
              processing_terms_reference: String(data.get('terms_reference') || '') || null,
            };
            saved(
              await api(
                base + '/workspace/models' + (source ? '/' + source.id + '/versions' : ''),
                'POST',
                body,
                source?.profile_row_version,
              ),
            );
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
            disabled={!!source}
            onChange={(e) => {
              setProvider(e.target.value);
              setCredential('');
            }}
          >
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic Claude</option>
            <option value="gemini">Google Gemini</option>
          </select>
        </label>
        {source && <p className={styles.muted}>Changing provider requires a new profile.</p>}
        <label>
          Profile name
          <input
            name="name"
            required
            maxLength={100}
            defaultValue={source?.name || ''}
            placeholder="Research baseline"
          />
        </label>
        <label>
          Exact model ID
          <input
            name="model_id"
            required
            maxLength={200}
            pattern="[A-Za-z0-9][A-Za-z0-9._:/@\-]*"
            defaultValue={source?.model_id || ''}
            placeholder="Enter an entitled provider model ID"
          />
        </label>
        <label>
          Maximum output tokens
          <input
            name="max_output_tokens"
            type="number"
            min={1}
            max={8192}
            required
            defaultValue={source?.max_output_tokens || 4096}
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
          <select
            name="credential_id"
            value={credential}
            onChange={(e) => setCredential(e.target.value)}
          >
            <option value="">No credential · unavailable for dispatch</option>
            {oldBinding && (
              <option value={credential} disabled>
                Previous binding · choose a current credential version
              </option>
            )}
            {available.map((c) => (
              <option key={c.id} value={c.id + ':' + c.current_version_id}>
                {c.name} · {c.current_version_id?.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
        <p className={styles.muted}>
          Binding is exact. Rotation does not silently replace the key in an existing model version.
          No key can be read here.
        </p>
        <details>
          <summary>Pricing and processing terms</summary>
          <p>
            Optional declared metadata only. Saving does not verify pricing, grant data-use rights
            or authorize spending. Keep amounts blank until explicitly reviewed.
          </p>
          <label>
            <input
              type="checkbox"
              checked={pricing}
              onChange={(e) => setPricing(e.target.checked)}
            />
            Include reviewed pricing metadata
          </label>
          {pricing && (
            <>
              <label>
                Pricing reference
                <input
                  name="pricing_reference"
                  required
                  minLength={5}
                  maxLength={200}
                  defaultValue={source?.pricing?.reference || ''}
                />
              </label>
              <label>
                Pricing source (HTTPS)
                <input
                  name="pricing_source"
                  type="url"
                  required
                  maxLength={500}
                  defaultValue={source?.pricing?.source_url || ''}
                />
              </label>
              <label>
                Input price (USD per million tokens)
                <input
                  name="input_price"
                  type="number"
                  min={0}
                  max={1000000}
                  step={0.000001}
                  required
                  defaultValue={dollars(source?.pricing?.input_micro_usd_per_million_tokens)}
                />
              </label>
              <label>
                Output price (USD per million tokens)
                <input
                  name="output_price"
                  type="number"
                  min={0}
                  max={1000000}
                  step={0.000001}
                  required
                  defaultValue={dollars(source?.pricing?.output_micro_usd_per_million_tokens)}
                />
              </label>
              <label>
                Pricing expires (local time)
                <input
                  name="pricing_expiry"
                  type="datetime-local"
                  required
                  defaultValue={localTime(source?.pricing?.expires_at)}
                />
              </label>
            </>
          )}
          <label>
            <input type="checkbox" checked={terms} onChange={(e) => setTerms(e.target.checked)} />I
            reviewed this provider's processing terms
          </label>
          <label>
            Processing terms reference
            <input
              name="terms_reference"
              required={terms}
              minLength={5}
              maxLength={500}
              defaultValue={source?.processing_terms?.reference || ''}
            />
          </label>
        </details>
        <p className={styles.muted}>
          Profiles remain unavailable for dispatch until adapter qualification and all exact-run
          gates are satisfied.
        </p>
        <button className={styles.primary} disabled={busy}>
          {busy ? 'Saving…' : source ? 'Save new model version' : 'Save model profile'}
        </button>
        <button type="button" disabled={busy} onClick={cancel}>
          Cancel
        </button>
      </Form>
    </section>
  );
}
