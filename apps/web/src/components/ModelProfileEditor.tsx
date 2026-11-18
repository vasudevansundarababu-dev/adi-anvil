'use client';
import { useEffect, useRef, useState } from 'react';
import Form from './Form';
import { CredentialMetadata } from './CredentialManager';
import { workspaceApi as api } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';
import OpenWeightModelTable from './OpenWeightModelTable';

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
  group?: string;
  hub?: { catalog_id: string; repository: string; revision: string } | null;
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
  initialProvider = 'openai',
}: {
  base: string;
  source: ModelConfiguration | null;
  credentials: CredentialMetadata[];
  credentialsLoading: boolean;
  credentialError: string;
  refreshCredentials: () => void;
  saved: (value: ModelConfiguration, count?: number) => void;
  cancel: () => void;
  initialProvider?: string;
}) {
  const [provider, setProvider] = useState(source?.provider || initialProvider);
  const [catalogId, setCatalogId] = useState(source?.hub?.catalog_id || '');
  const [catalog, setCatalog] = useState<
    {
      id: string;
      label: string;
      repositories: { repository: string; revision: string; repository_url: string }[];
    }[]
  >([]);
  const [modelId, setModelId] = useState(source?.model_id || '');
  const [hubRevision, setHubRevision] = useState(source?.hub?.revision || '');
  const [catalogError, setCatalogError] = useState('');
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const bulk = provider === 'huggingface' && !source;
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
            if (bulk) {
              if (!selectedModels.length) throw new Error('Select at least one model version.');
              const models = catalog.flatMap((item) =>
                item.repositories
                  .filter((repo) => selectedModels.includes(item.id + ':' + repo.repository))
                  .map((repo) => ({
                    catalog_id: item.id,
                    repository: repo.repository,
                    revision: repo.revision,
                  })),
              );
              const result = await api(base + '/workspace/models/catalog/register', 'POST', {
                models,
                credential_id: credentialId || null,
                credential_version_id: credentialVersion || null,
              });
              saved(result.items[0], result.items.length);
              return;
            }
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
              open_weight_catalog_id:
                provider === 'huggingface' ? String(data.get('catalog_id')) : null,
              hub_revision: provider === 'huggingface' ? String(data.get('hub_revision')) : null,
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
            <option value="huggingface">Hugging Face · Open Weight Models</option>
          </select>
        </label>
        {source && <p className={styles.muted}>Changing provider requires a new profile.</p>}
        {provider === 'huggingface' && (
          <>
            <p>
              One saved Hugging Face token can be linked to every model. Repository terms, access
              and an inference runtime must be configured separately. Saving does not contact
              Hugging Face.
            </p>
            {catalogError && <p role="alert">{catalogError}</p>}
            {bulk ? (
              <>
                <p>
                  Select models together and attach the same saved Hugging Face credential version
                  to all of them. Each model keeps its exact repository and version for Run
                  selection.
                </p>
                <OpenWeightModelTable
                  catalog={catalog}
                  selected={selectedModels}
                  onChange={setSelectedModels}
                  disabled={busy || !!catalogError}
                />
              </>
            ) : (
              <>
                <label>
                  Open Weight Models catalog
                  <select
                    name="catalog_id"
                    required
                    value={catalogId}
                    onChange={(event) => {
                      const value = event.target.value;
                      setCatalogId(value);
                      const choices = catalog.find((item) => item.id === value)?.repositories || [];
                      setModelId(choices.length === 1 ? choices[0].repository : '');
                      setHubRevision(choices.length === 1 ? choices[0].revision : '');
                    }}
                  >
                    <option value="" disabled>
                      Select a catalog model
                    </option>
                    {catalog.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Repository variant
                  <select
                    value={
                      catalog
                        .find((item) => item.id === catalogId)
                        ?.repositories.some((item) => item.repository === modelId)
                        ? modelId
                        : ''
                    }
                    onChange={(event) => {
                      const repository = catalog
                        .find((item) => item.id === catalogId)
                        ?.repositories.find((item) => item.repository === event.target.value);
                      setModelId(repository?.repository || '');
                      setHubRevision(repository?.revision || '');
                    }}
                  >
                    <option value="">Choose a repository variant or enter one below</option>
                    {catalog
                      .find((item) => item.id === catalogId)
                      ?.repositories.map((item) => (
                        <option key={item.repository} value={item.repository}>
                          {item.repository} · observed commit {item.revision.slice(0, 12)}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  Exact Hub commit revision
                  <input
                    name="hub_revision"
                    required
                    pattern="[0-9a-f]{40}"
                    minLength={40}
                    maxLength={40}
                    value={hubRevision}
                    onChange={(event) => setHubRevision(event.target.value)}
                    placeholder="40-character commit SHA"
                  />
                </label>
                <p className={styles.muted}>
                  Repository choices and commits come from public Hub metadata. Base, instruct and
                  quantized variants are explicit choices. This does not verify your account access
                  or provision inference. You can enter another exact commit below.
                </p>
              </>
            )}
          </>
        )}
        {!bulk && (
          <>
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
                value={modelId}
                onChange={(event) => setModelId(event.target.value)}
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
          </>
        )}
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
                    : 'No key selected. Choose a saved credential version below.'}
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
          disabled={
            busy ||
            credentialsLoading ||
            !!credentialError ||
            oldBinding ||
            (bulk && (!selectedModels.length || !!catalogError))
          }
        >
          {busy
            ? 'Saving…'
            : source
              ? 'Save new model version'
              : bulk
                ? 'Save selected models with shared credential'
                : 'Save model profile'}
        </button>
        <button type="button" disabled={busy} onClick={cancel}>
          Cancel
        </button>
      </Form>
    </section>
  );
}
