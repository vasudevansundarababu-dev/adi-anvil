'use client';

import { useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';

export type InputDraft = {
  input_id: string | null;
  content_sha256?: string;
  mode: 'all' | 'explicit_ids' | 'deterministic_random' | 'stratified_state';
  count: string;
  seed: string;
  caseIds: string;
};
export function inputSelectionRequest(value: InputDraft) {
  const sampling: Record<string, unknown> = { mode: value.mode };
  if (value.mode === 'explicit_ids') {
    const ids = value.caseIds.split(/[\s,]+/).filter(Boolean);
    if (!ids.length || ids.length !== new Set(ids).size)
      throw new Error('Enter unique application or campaign IDs.');
    sampling.case_ids = ids;
  } else if (value.mode !== 'all') {
    const count = Number(value.count);
    if (!Number.isSafeInteger(count) || count < 1 || count > 10000 || !value.seed.trim())
      throw new Error('Sampling needs a whole-number count from 1 to 10,000 and an explicit seed.');
    sampling.count = count;
    sampling.seed = value.seed.trim();
  }
  return { input_id: value.input_id, sampling };
}
type Version = {
  id: string;
  filename: string;
  case_count: number;
  content_sha256: string;
  status: string;
};
type Catalogue = {
  enabled: boolean;
  family: string;
  default_input: { location: string; case_dataset: unknown; status: string };
  versions: Version[];
  schema: unknown;
  schema_sha256: string;
  upload: { max_bytes: number };
};
type Preview = {
  version?: Version;
  case_dataset?: Record<string, unknown>;
  preview_gap?: string | null;
  actor_records?: unknown[];
  schema?: unknown;
  schema_sha256?: string;
  total_count?: number;
  preview_truncated?: boolean;
};
export default function ProjectInputData({
  endpoint,
  value,
  savedReference,
  onChange,
  onBusyChange,
}: {
  endpoint: string;
  value: InputDraft | null;
  savedReference?: { id: string; sha256: string } | null;
  onChange: (value: InputDraft) => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [unconfirmed, setUnconfirmed] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [showSchema, setShowSchema] = useState(false);
  const [revision, setRevision] = useState(0);
  const base = endpoint + '/data-inputs';
  useEffect(() => {
    let active = true;
    setCatalogue(null);
    setError('');
    api(base)
      .then((result) => {
        if (
          !result ||
          !Array.isArray(result.versions) ||
          !result.default_input ||
          !Number.isSafeInteger(result.upload?.max_bytes)
        )
          throw new Error('The input catalogue is incomplete. No input readiness is confirmed.');
        if (active) setCatalogue(result);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [base, revision]);
  const draft = value || { input_id: null, mode: 'all' as const, count: '', seed: '', caseIds: '' };
  const unresolvedSaved = !!savedReference && !value;
  function change(patch: Partial<InputDraft>) {
    setPreview(null);
    onChange({ ...draft, ...patch });
  }
  function operation(active: boolean) {
    setBusy(active);
    onBusyChange(active);
  }
  return (
    <section aria-label="Execution input data">
      <h3>Input Data</h3>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {!catalogue && !error && <p>Loading input files…</p>}
      {catalogue && (
        <>
          <p>Default input location: {catalogue.default_input.location}</p>
          <details>
            <summary>Default input version</summary>
            <pre>{JSON.stringify(catalogue.default_input.case_dataset, null, 2)}</pre>
            <p>{catalogue.default_input.status}</p>
          </details>
          {!catalogue.enabled && (
            <p>
              Input upload and sampling are not enabled for this deployment. Existing saved
              selections remain unchanged.
            </p>
          )}
          <label>
            Input file
            <select
              value={unresolvedSaved ? 'saved' : draft.input_id || ''}
              disabled={busy || !catalogue.enabled}
              onChange={(event) =>
                change({
                  input_id: event.target.value || null,
                  content_sha256: catalogue.versions.find(
                    (entry) => entry.id === event.target.value,
                  )?.content_sha256,
                  mode: 'all',
                  count: '',
                  seed: '',
                  caseIds: '',
                })
              }
            >
              {unresolvedSaved && (
                <option value="saved" disabled>
                  Existing saved selection
                </option>
              )}
              <option value="">Default input file</option>
              {draft.input_id &&
                !catalogue.versions.some((entry) => entry.id === draft.input_id) && (
                  <option value={draft.input_id}>Saved input version {draft.input_id}</option>
                )}
              {catalogue.versions.map((version) => (
                <option key={version.id} value={version.id}>
                  {version.filename} · {version.case_count} records
                </option>
              ))}
            </select>
          </label>
          {unresolvedSaved && (
            <p>
              The existing selection {savedReference.id} is preserved. Its file and sampling details
              have not been returned; select a replacement only if you intend to change it.
            </p>
          )}
          {draft.input_id &&
            catalogue.versions
              .filter((version) => version.id === draft.input_id)
              .map((version) => (
                <p key={version.id}>
                  {version.filename}: {version.status.replaceAll('_', ' ')}. Population alone does
                  not establish execution readiness.
                </p>
              ))}
          <label>
            Upload input file{' '}
            <input
              type="file"
              accept=".json,application/json"
              disabled={busy || !catalogue.enabled || unconfirmed}
              onChange={(event) => setFile(event.target.files?.[0] || null)}
            />
          </label>
          <button
            disabled={!file || busy || !catalogue.enabled || unconfirmed}
            onClick={async () => {
              if (!file) return;
              if (file.size > catalogue.upload.max_bytes) {
                setError('The input file exceeds the advertised upload limit.');
                return;
              }
              operation(true);
              setError('');
              setNotice('');
              try {
                const csrf =
                  document.cookie
                    .split('; ')
                    .find((part) => part.startsWith('anvil_csrf='))
                    ?.split('=')[1] || '';
                const response = await fetch('/api/v1' + base, {
                  method: 'POST',
                  headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': csrf,
                    'X-Input-Filename': file.name,
                    'Idempotency-Key': crypto.randomUUID(),
                  },
                  body: file,
                });
                const body = await response.json();
                if (!response.ok) {
                  const detail = body.error?.message;
                  const message =
                    typeof detail === 'string'
                      ? detail
                      : Array.isArray(detail?.errors)
                        ? detail.errors
                            .slice(0, 20)
                            .map(
                              (entry: { path: string; fix: string }) =>
                                `${entry.path}: ${entry.fix}`,
                            )
                            .join(' · ')
                        : detail?.fix || detail?.code || 'Input validation failed.';
                  if (response.status >= 500) setUnconfirmed(true);
                  throw Object.assign(new Error(message), {
                    knownRejection: response.status < 500,
                  });
                }
                const uploaded = body.data as Version;
                if (!uploaded?.id || !uploaded.content_sha256)
                  throw new Error(
                    'Upload outcome is unconfirmed. Refresh input versions before another upload.',
                  );
                setCatalogue(
                  (previous) =>
                    previous && {
                      ...previous,
                      versions: [
                        uploaded,
                        ...previous.versions.filter((entry) => entry.id !== uploaded.id),
                      ],
                    },
                );
                onChange({
                  input_id: uploaded.id,
                  content_sha256: uploaded.content_sha256,
                  mode: 'all',
                  count: '',
                  seed: '',
                  caseIds: '',
                });
                setNotice(
                  'Input version uploaded. Save the Project bindings to select it. Runtime and evaluator qualification are still required.',
                );
                setPreview(null);
              } catch (e) {
                if (!(e as Error & { knownRejection?: boolean }).knownRejection)
                  setUnconfirmed(true);
                setError((e as Error).message);
              } finally {
                operation(false);
              }
            }}
          >
            Upload
          </button>
          {unconfirmed && (
            <p>
              The upload outcome is unconfirmed. No automatic retry will be made. Inspect refreshed
              input versions before proceeding.
            </p>
          )}
          <button disabled={busy} onClick={() => setRevision((previous) => previous + 1)}>
            Refresh input versions
          </button>
          <details>
            <summary>Optional sampling</summary>
            <label>
              Sampling method{' '}
              <select
                value={draft.mode}
                disabled={busy || !catalogue.enabled || unresolvedSaved}
                onChange={(event) => change({ mode: event.target.value as InputDraft['mode'] })}
              >
                <option value="all">All records (default)</option>
                <option value="explicit_ids">Specific application or campaign IDs</option>
                <option value="deterministic_random">Random sample with a recorded seed</option>
                <option value="stratified_state" disabled={catalogue.family !== 'kyc'}>
                  Sample across KYC states
                </option>
              </select>
            </label>
            {draft.mode === 'explicit_ids' && (
              <label>
                Application or campaign IDs{' '}
                <textarea
                  value={draft.caseIds}
                  disabled={busy}
                  onChange={(event) => change({ caseIds: event.target.value })}
                />
              </label>
            )}
            {['deterministic_random', 'stratified_state'].includes(draft.mode) && (
              <>
                <label>
                  Number of records{' '}
                  <input
                    type="number"
                    min={1}
                    max={10000}
                    value={draft.count}
                    disabled={busy}
                    onChange={(event) => change({ count: event.target.value })}
                  />
                </label>
                <label>
                  Sampling seed{' '}
                  <input
                    maxLength={120}
                    value={draft.seed}
                    disabled={busy}
                    onChange={(event) => change({ seed: event.target.value })}
                  />
                </label>
              </>
            )}
            <p>
              Sampling is optional. Nothing is sampled until the selection is saved. The exact
              eligible and selected populations are retained with execution.
            </p>
          </details>
          <button
            disabled={busy || unresolvedSaved}
            onClick={async () => {
              setError('');
              setPreview(null);
              setShowSchema(true);
              operation(true);
              try {
                if (!draft.input_id) {
                  const result = await api(base + '/default/preview');
                  const expected = catalogue.default_input.case_dataset as Record<
                    string,
                    unknown
                  > | null;
                  if (
                    !expected ||
                    !['id', 'version', 'sha256', 'case_count'].every(
                      (key) =>
                        expected[key] !== undefined && expected[key] === result.case_dataset?.[key],
                    ) ||
                    result.schema_sha256 !== catalogue.schema_sha256
                  )
                    throw new Error(
                      'The default preview no longer matches the bound dataset and schema. Refresh the input versions before continuing.',
                    );
                  setPreview(result);
                  setNotice(
                    result.preview_gap
                      ? 'The default Marketing actor-record preview is not implemented yet. The bound dataset and schema are shown; no complete preview is claimed.'
                      : 'Showing bounded records from the bound default input. This does not run or qualify a benchmark.',
                  );
                  return;
                }
                const result = await api(
                  base + '/' + encodeURIComponent(draft.input_id) + '/preview',
                );
                const expectedHash =
                  draft.content_sha256 ||
                  catalogue.versions.find((entry) => entry.id === draft.input_id)?.content_sha256;
                if (
                  !expectedHash ||
                  result.version?.id !== draft.input_id ||
                  result.version?.content_sha256 !== expectedHash ||
                  result.schema_sha256 !== catalogue.schema_sha256
                )
                  throw new Error(
                    'The input preview no longer matches its selected version and schema. Refresh the input versions before continuing.',
                  );
                setPreview(result);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                operation(false);
              }
            }}
          >
            View Data &amp; Schema
          </button>
          {showSchema && (
            <section aria-label="Structured input preview">
              {preview && (
                <>
                  <p>
                    {preview.total_count ?? 'Unknown'} total records. Preview contains{' '}
                    {preview.actor_records?.length || 0} actor-visible records; no private answers.
                  </p>
                  <pre>{JSON.stringify(preview.actor_records || [], null, 2)}</pre>
                  {preview.preview_truncated && (
                    <p>Preview is bounded; it is not the full selected population.</p>
                  )}
                </>
              )}
              <details>
                <summary>Input schema</summary>
                <p>Schema hash: {preview?.schema_sha256 || catalogue.schema_sha256}</p>
                <pre>{JSON.stringify(preview?.schema || catalogue.schema, null, 2)}</pre>
              </details>
            </section>
          )}
        </>
      )}
    </section>
  );
}
