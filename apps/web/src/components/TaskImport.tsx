import Form from './Form';
import { useEffect, useState } from 'react';

type Resource = {
  id: string;
  current_revision_id: string;
  row_version: number;
  lifecycle: string;
  content: {
    title: string;
    objective_revision_id?: string;
    suite_revision_id?: string;
    mode?: string;
  };
};
type Batch = {
  provenance: { classification: string; source_owner: string | null; status: string };
  publication_blocker: string | null;
  id: string;
  dataset_id: string;
  status: string;
  revision: number;
  normalized_sha256: string;
  published_version_id: string | null;
  mapping: Record<string, string>;
  columns: string[];
  source: { original_filename: string; sha256: string };
  counts: { received: number; valid: number; invalid: number; duplicates: number };
  errors: { row: number; field: string; code: string; message: string }[];
  preview: { row: number; spec: Record<string, unknown>; has_reference: boolean }[];
  job?: {
    state: string;
    checkpoint: number;
    records_total: number;
    bytes_processed: number;
    error_code: string | null;
    started_at: string | null;
    elapsed_seconds: number | null;
  };
};
type Version = {
  version_id: string;
  version_number: number;
  dataset_id: string;
  counts: { valid: number };
  objective_id: string;
  source?: { provenance?: { classification: string; source_owner: string | null } };
};
const fields = [
  'schema_version',
  'external_id',
  'title',
  'instruction',
  'input',
  'reference',
  'metadata',
  'metadata.domain',
  'metadata.difficulty',
  'metadata.locale',
  'metadata.tags',
];

async function request(
  base: string,
  path: string,
  method = 'GET',
  body?: unknown,
  version?: number,
) {
  const csrf =
    document.cookie
      .split('; ')
      .find((x) => x.startsWith('anvil_csrf='))
      ?.split('=')[1] || '';
  const file = body instanceof FormData;
  const response = await fetch('/api/v1' + base + path, {
    method,
    headers: {
      'X-CSRF-Token': csrf,
      'Idempotency-Key': crypto.randomUUID(),
      ...(file ? {} : { 'Content-Type': 'application/json' }),
      ...(version ? { 'If-Match': String(version) } : {}),
    },
    ...(body === undefined ? {} : { body: file ? body : JSON.stringify(body) }),
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      typeof result.error?.message === 'string'
        ? result.error.message
        : JSON.stringify(result.error?.message),
    );
  return result.data;
}
async function all(base: string, path: string): Promise<Resource[]> {
  let after = '';
  const rows: Resource[] = [];
  do {
    const r = await fetch(
      '/api/v1' + base + path + '?limit=100' + (after ? '&after=' + after : ''),
    );
    const page = await r.json();
    if (!r.ok) throw new Error('Unable to load ' + path);
    rows.push(...page.data);
    after = page.meta.next_cursor || '';
  } while (after);
  return rows;
}

export default function TaskImport({
  base,
  objective,
  canAttach,
  onClose,
}: {
  base: string;
  objective: Resource;
  canAttach: boolean;
  onClose: () => void;
}) {
  const [batch, setBatch] = useState<Batch | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [version, setVersion] = useState<Version | null>(null);
  const [history, setHistory] = useState<{ id: string; status: string; dataset_id: string }[]>([]);
  const [suites, setSuites] = useState<Resource[]>([]),
    [protocols, setProtocols] = useState<Resource[]>([]);
  const [suite, setSuite] = useState(''),
    [protocol, setProtocol] = useState('');
  const [attached, setAttached] = useState(false),
    [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [filename, setFilename] = useState('');
  const [classification, setClassification] = useState(''),
    [owner, setOwner] = useState(''),
    [basis, setBasis] = useState(''),
    [generator, setGenerator] = useState(''),
    [seed, setSeed] = useState('');
  async function work(fn: () => Promise<void>) {
    setBusy(true);
    setError('');
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void work(async () => {
      setHistory(await request(base, `/objectives/${objective.id}/task-imports`));
      setSuites(
        (await all(base, '/suites')).filter(
          (s) => s.content.objective_revision_id === objective.current_revision_id,
        ),
      );
      setProtocols((await all(base, '/protocols')).filter((p) => p.lifecycle === 'approved'));
    });
  }, [base, objective.id, objective.current_revision_id]);
  const selectedSuite = suites.find((s) => s.id === suite);
  const mappingChanged =
    !!batch &&
    (Object.keys(mapping).length !== Object.keys(batch.mapping).length ||
      Object.entries(mapping).some(([key, value]) => batch.mapping[key] !== value));
  useEffect(() => {
    if (!batch || !['queued', 'extracting', 'validating'].includes(batch.status)) return;
    const timer = setTimeout(() => {
      void request(base, '/task-imports/' + batch.id)
        .then((b: Batch) => {
          setBatch(b);
        })
        .catch((e) => setError(e.message));
    }, 1000);
    return () => clearTimeout(timer);
  }, [base, batch]);
  const eligible = protocols.filter(
    (p) => p.content.suite_revision_id === selectedSuite?.current_revision_id,
  );
  return (
    <section className="card" aria-label="Task and data import">
      <h2>Import tasks — {objective.content.title}</h2>
      <p>
        CSV or JSONL, UTF-8, maximum 25 MiB / 10,000 tasks. References stay separate from actor
        inputs. Publication validates structure; rights, scoring and execution qualification remain
        separate.
      </p>
      <a href="/examples/synthetic-five-tasks.jsonl" download>
        Download five-task synthetic example
      </a>
      <button onClick={onClose}>Close import</button>
      {history.length > 0 && (
        <>
          <label htmlFor="saved-task-import">Resume an import</label>
          <select
            id="saved-task-import"
            value={batch?.id || ''}
            onChange={(e) => {
              const id = e.target.value;
              if (!id) return;
              void work(async () => {
                const b = await request(base, '/task-imports/' + id);
                setBatch(b);
                setMapping(b.mapping);
                setAttached(false);
                setVersion(
                  b.published_version_id
                    ? await request(base, '/dataset-versions/' + b.published_version_id)
                    : null,
                );
              });
            }}
          >
            <option value="">Choose saved import</option>
            {history.map((h) => (
              <option key={h.id} value={h.id}>
                {h.status} · {h.id}
              </option>
            ))}
          </select>
        </>
      )}
      <Form
        onSubmit={(e) => {
          e.preventDefault();
          const form = new FormData(e.currentTarget);
          const f = form.get('file') as File;
          setFilename(f.name);
          void work(async () => {
            const artifact = await request(base, '/artifacts?purpose=task_import', 'POST', form);
            const b = await request(base, `/objectives/${objective.id}/task-imports`, 'POST', {
              artifact_id: artifact.id,
              ...(batch ? { dataset_id: batch.dataset_id } : {}),
              mapping: {},
              provenance: {
                classification,
                source_owner: owner,
                basis,
                ...(classification === 'adi_synthetic'
                  ? { generator_version: generator, seed }
                  : {}),
              },
            });
            setBatch(b);
            setVersion(null);
            setAttached(false);
            setMapping(
              Object.fromEntries(fields.filter((k) => b.columns.includes(k)).map((k) => [k, k])),
            );
            setHistory(await request(base, `/objectives/${objective.id}/task-imports`));
          });
        }}
      >
        <label htmlFor="task-source">Task source file</label>
        <input
          id="task-source"
          name="file"
          type="file"
          accept=".csv,.jsonl"
          required
          disabled={busy}
        />
        <button disabled={busy}>
          {batch ? 'Upload corrected file to this dataset' : 'Upload and preview'}
        </button>
        <label htmlFor="source-classification">Source provenance</label>
        <select
          id="source-classification"
          required
          value={classification}
          onChange={(e) => setClassification(e.target.value)}
        >
          <option value="">Declare the source class</option>
          <option value="adi_synthetic">ADI synthetic</option>
          <option value="bodhium_restricted">Bodhium restricted</option>
          <option value="adi_praxis_sme">ADI Praxis SME</option>
          <option value="public_permitted">Permitted public</option>
          <option value="third_party_licensed">Licensed third-party</option>
        </select>
        <label htmlFor="source-owner">Original source owner</label>
        <input
          id="source-owner"
          required
          minLength={3}
          maxLength={200}
          value={owner}
          onChange={(e) => setOwner(e.target.value)}
        />
        <label htmlFor="source-basis">Declaration basis</label>
        <textarea
          id="source-basis"
          required
          minLength={10}
          maxLength={1000}
          value={basis}
          onChange={(e) => setBasis(e.target.value)}
        />
        {classification === 'adi_synthetic' && (
          <>
            <label htmlFor="source-generator">Generator / authoring version</label>
            <input
              id="source-generator"
              required
              maxLength={100}
              value={generator}
              onChange={(e) => setGenerator(e.target.value)}
            />
            <label htmlFor="source-seed">Seed / authoring recipe identifier</label>
            <input
              id="source-seed"
              required
              maxLength={100}
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
            />
          </>
        )}
        <p>
          Author declaration only; no independent license or privacy clearance. Non-synthetic
          publication remains blocked pending reviewed controls. Re-upload to correct an immutable
          source declaration.
        </p>
        {batch && (
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setBatch(null);
              setVersion(null);
              setAttached(false);
            }}
          >
            Start a separate dataset
          </button>
        )}
      </Form>
      {busy && <p role="status">Processing {filename || 'import'}…</p>}
      {error && (
        <p role="alert" className="banner error">
          {error}
        </p>
      )}
      {batch && (
        <>
          <p>
            Source: {batch.provenance.classification} · owner{' '}
            {batch.provenance.source_owner || 'unclassified'} · {batch.provenance.status}
          </p>
          {batch.publication_blocker && <p role="status">{batch.publication_blocker}</p>}
          {batch.job && (
            <div role="status">
              <p>
                Ingestion: {batch.job.state} · {batch.job.checkpoint} / {batch.job.records_total}{' '}
                records · {batch.job.bytes_processed} bytes ·{' '}
                {batch.job.started_at ? 'Started ' + batch.job.started_at : 'Waiting for worker'}
                {batch.job.elapsed_seconds !== null
                  ? ` · ${batch.job.elapsed_seconds}s elapsed`
                  : ''}
              </p>
              {batch.job.error_code && (
                <p>
                  Import stopped ({batch.job.error_code}). Retry from the last checkpoint or upload
                  a corrected file.
                </p>
              )}
              {['queued', 'extracting', 'validating', 'failed'].includes(batch.job.state) && (
                <button
                  disabled={busy}
                  onClick={() =>
                    void work(async () =>
                      setBatch(await request(base, `/task-imports/${batch.id}/cancel`, 'POST', {})),
                    )
                  }
                >
                  Cancel import
                </button>
              )}
              {['failed', 'cancelled'].includes(batch.job.state) && (
                <button
                  disabled={busy}
                  onClick={() =>
                    void work(async () =>
                      setBatch(await request(base, `/task-imports/${batch.id}/retry`, 'POST', {})),
                    )
                  }
                >
                  Retry from checkpoint
                </button>
              )}
            </div>
          )}
          <h3>{batch.status === 'published' ? 'Published import' : 'Mapping and validation'}</h3>
          <p>
            {batch.source.original_filename} · SHA-256 {batch.source.sha256}
          </p>
          {['ready', 'invalid'].includes(batch.status) && (
            <Form
              onSubmit={(e) => {
                e.preventDefault();
                void work(async () => {
                  const b = await request(base, `/task-imports/${batch.id}/validate`, 'POST', {
                    mapping,
                    revision: batch.revision,
                  });
                  setBatch(b);
                });
              }}
            >
              <div className="fieldgrid">
                {fields.map((field) => (
                  <div key={field}>
                    <label htmlFor={'map-' + field}>{field}</label>
                    <select
                      id={'map-' + field}
                      value={mapping[field] || ''}
                      required={
                        batch.source.original_filename.toLowerCase().endsWith('.csv') &&
                        ['external_id', 'instruction', 'input'].includes(field)
                      }
                      disabled={busy}
                      onChange={(e) => {
                        const value = e.target.value;
                        setMapping((old) => {
                          const next = { ...old };
                          if (value) next[field] = value;
                          else delete next[field];
                          return next;
                        });
                      }}
                    >
                      <option value="">Automatic / unmapped</option>
                      {batch.columns.map((col) => (
                        <option key={col}>{col}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
              <button disabled={busy}>Revalidate mapping</button>
            </Form>
          )}
          <p>
            {batch.counts.received} received · {batch.counts.valid} valid · {batch.counts.invalid}{' '}
            invalid · {batch.counts.duplicates} duplicate rows
          </p>
          {mappingChanged && batch.status !== 'published' && (
            <p>Revalidate the changed mapping before publication.</p>
          )}
          {batch.errors.length > 0 && (
            <div role="alert">
              <h4>Validation errors</h4>
              <ul>
                {batch.errors.map((e, i) => (
                  <li key={i}>
                    Row {e.row} · {e.field} · {e.code}: {e.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <h4>First 20 tasks (reference answers excluded)</h4>
          {batch.preview.map((row) => (
            <details key={row.row}>
              <summary>
                Row {row.row}: {String(row.spec.title || row.spec.external_id || 'Invalid task')}
                {batch.errors.some((e) => e.row === row.row) ? ' — errors' : ''}
              </summary>
              <pre>{JSON.stringify(row.spec, null, 2)}</pre>
              <p>Reference supplied: {row.has_reference ? 'yes' : 'no'}</p>
              {batch.errors
                .filter((e) => e.row === row.row)
                .map((e, i) => (
                  <p key={i}>
                    {e.field}: {e.code} — {e.message}
                  </p>
                ))}
            </details>
          ))}
          {!version && (
            <button
              disabled={
                busy || batch.status !== 'ready' || mappingChanged || !!batch.publication_blocker
              }
              onClick={() =>
                void work(async () => {
                  const v = await request(base, `/task-imports/${batch.id}/publish`, 'POST', {
                    revision: batch.revision,
                    normalized_sha256: batch.normalized_sha256,
                  });
                  setVersion(v);
                  setBatch({ ...batch, status: 'published', published_version_id: v.version_id });
                })
              }
            >
              Publish immutable dataset
            </button>
          )}
        </>
      )}
      {version && (
        <div>
          <h3>Dataset version {version.version_number} published</h3>
          <p>
            {version.counts.valid} imported tasks · {version.version_id}
          </p>
          {canAttach ? (
            <>
              <label htmlFor="dataset-suite">Attach to suite</label>
              <select
                id="dataset-suite"
                value={suite}
                onChange={(e) => {
                  setSuite(e.target.value);
                  setProtocol('');
                  setAttached(false);
                }}
              >
                <option value="">Select existing suite</option>
                {suites.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.content.title} ({s.lifecycle})
                  </option>
                ))}
              </select>
              <button
                disabled={busy || !selectedSuite}
                onClick={() =>
                  void work(async () => {
                    await request(
                      base,
                      '/suites/' + suite + '/dataset-version',
                      'PUT',
                      { version_id: version.version_id },
                      selectedSuite!.row_version,
                    );
                    setAttached(true);
                    if (eligible.length === 1) setProtocol(eligible[0].current_revision_id);
                  })
                }
              >
                Attach exact version
              </button>
              {attached && (
                <>
                  <p>
                    Exact version attached. Existing scientific approvals do not qualify the new
                    tasks.
                  </p>
                  <label htmlFor="dataset-protocol">Approved protocol</label>
                  <select
                    id="dataset-protocol"
                    value={protocol}
                    onChange={(e) => setProtocol(e.target.value)}
                  >
                    <option value="">Select protocol</option>
                    {eligible.map((p) => (
                      <option key={p.id} value={p.current_revision_id}>
                        {p.content.title}
                      </option>
                    ))}
                  </select>
                  {!eligible.length && (
                    <p>
                      Freeze this suite and approve a protocol for its exact revision, then resume
                      this import.
                    </p>
                  )}
                  {protocol && (
                    <a
                      href={`/p/${base.split('/')[2]}/runs?objective=${objective.id}&suite=${suite}&protocol=${protocol}&dataset=${version.version_id}`}
                    >
                      Configure run
                    </a>
                  )}
                </>
              )}
            </>
          ) : (
            <p>
              An RL Engineer can resume this import and attach the published version to a suite.
            </p>
          )}
        </div>
      )}
    </section>
  );
}

export function DatasetRunConfiguration({ base, onSaved }: { base: string; onSaved: () => void }) {
  const [selection, setSelection] = useState<{
    objective: Resource;
    suite: Resource;
    protocol: Resource;
    dataset: Version;
  } | null>(null);
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [saved, setSaved] = useState('');
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (!q.get('dataset')) return;
    let cancelled = false;
    void (async () => {
      try {
        const [objective, suite, protocols, dataset] = await Promise.all([
          request(base, '/objectives/' + q.get('objective')),
          request(base, '/suites/' + q.get('suite')),
          all(base, '/protocols'),
          request(base, '/dataset-versions/' + q.get('dataset')),
        ]);
        const protocol = protocols.find((p) => p.current_revision_id === q.get('protocol'));
        if (
          !protocol ||
          protocol.content.suite_revision_id !== suite.current_revision_id ||
          dataset.objective_id !== objective.id ||
          suite.content.objective_revision_id !== objective.current_revision_id
        )
          throw new Error(
            'Selection is stale or mismatched; configure again from the published import.',
          );
        if (!cancelled) setSelection({ objective, suite, protocol, dataset });
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [base]);
  return (
    <>
      {error && <p role="alert">{error}</p>}
      {selection && (
        <section className="card" aria-label="Configure imported run">
          <h2>Configure imported run</h2>
          <p>Objective: {selection.objective.content.title}</p>
          <p>Suite: {selection.suite.content.title}</p>
          <p>Protocol: {selection.protocol.content.title}</p>
          <p>
            Dataset version {selection.dataset.version_number} · {selection.dataset.version_id}
          </p>
          <p>
            Source: {selection.dataset.source?.provenance?.classification ?? 'unclassified'} ·
            owner: {selection.dataset.source?.provenance?.source_owner ?? 'unknown'}
          </p>
          <p>
            <strong>{selection.dataset.counts.valid} imported tasks selected</strong>
          </p>
          <p>
            Save the exact version in a draft run. Execution requires task qualification and a
            supported adapter. No model calls will be made.
          </p>
          <button
            disabled={busy || !!saved}
            onClick={async () => {
              setBusy(true);
              setError('');
              try {
                const run = await request(base, '/runs', 'POST', {
                  protocol_revision_id: selection.protocol.current_revision_id,
                  dataset_version_id: selection.dataset.version_id,
                  ...(selection.protocol.content.mode === 'external_result_import_v1'
                    ? { external_origin: 'customer_reported' }
                    : {}),
                });
                setSaved(run.id);
                onSaved();
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Save configured run
          </button>
          {saved && <p role="status">Run configured with immutable dataset binding: {saved}</p>}
        </section>
      )}
    </>
  );
}
