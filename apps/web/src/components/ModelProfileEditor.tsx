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
export default function ModelProfileEditor({
  base,
  source,
  credentials,
  credentialsLoading,
  credentialError,
  refreshCredentials,
  saved,
  cancel,
}: {
  base: string;
  source: ModelConfiguration | null;
  credentials: CredentialMetadata[];
  credentialsLoading: boolean;
  credentialError: string;
  refreshCredentials: () => void;
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
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const available = credentials.filter(
    (c) => c.provider === provider && !c.revoked_at && c.current_version_id,
  );
  const oldBinding =
    !!credential && !available.some((c) => c.id + ':' + c.current_version_id === credential);
  const selectedCredential = available.find(
    (c) => c.id + ':' + c.current_version_id === credential,
  );
  const alreadyLinked =
    source?.credential_binding &&
    source.credential_binding.id + ':' + source.credential_binding.version_id === credential;
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
              // Preserve historical metadata without requiring manual setup.
              pricing: source?.pricing || null,
              processing_terms_reviewed: source?.processing_terms?.reviewed || false,
              processing_terms_reference: source?.processing_terms?.reference || null,
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
        <div role="group" aria-label="Saved API key">
          <strong>API key storage</strong>
          <p role="status">
            {credentialsLoading
              ? 'Checking saved keys…'
              : credentialError
                ? 'Refresh credential versions to check saved key status.'
                : selectedCredential
                  ? 'Saved securely: ' +
                    selectedCredential.name +
                    ' · version ' +
                    selectedCredential.current_version_id?.slice(0, 8)
                  : oldBinding
                    ? 'The saved key binding is no longer current.'
                    : 'No key selected for this model. Choose a saved credential version below.'}
          </p>
          {selectedCredential && (
            <p>
              {alreadyLinked
                ? 'This model version already uses this saved key.'
                : 'Save the model profile to link this selected key.'}
            </p>
          )}
          <p className={styles.muted}>
            Saved key values are hidden. You do not need to paste a saved key again.
          </p>
        </div>
        <label>
          Credential version
          <select
            name="credential_id"
            value={credential}
            disabled={credentialsLoading}
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
        <button type="button" disabled={credentialsLoading} onClick={refreshCredentials}>
          Refresh credential versions
        </button>
        {credentialsLoading && <p role="status">Refreshing credential versions…</p>}
        {credentialError && <p role="alert">{credentialError}</p>}
        {!credentialsLoading && !credentialError && oldBinding && (
          <p role="status">
            The selected key version changed or was revoked. Choose a current credential version.
          </p>
        )}
        {!credentialsLoading && !credentialError && !available.length && (
          <p>
            No current credentials for this provider. Save a matching credential below, then
            refresh.
          </p>
        )}
        <p className={styles.muted}>
          Binding is exact. Rotation does not silently replace the key in an existing model version.
          No key can be read here.
        </p>
        <button
          className={styles.primary}
          disabled={busy || credentialsLoading || !!credentialError || oldBinding}
        >
          {busy ? 'Saving…' : source ? 'Save new model version' : 'Save model profile'}
        </button>
        <button type="button" disabled={busy} onClick={cancel}>
          Cancel
        </button>
      </Form>
    </section>
  );
}
