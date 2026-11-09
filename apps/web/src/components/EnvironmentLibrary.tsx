'use client';

import { useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import s from './BenchmarkRunDashboard.module.css';
import EnvironmentTaskBindings from './EnvironmentTaskBindings';
import EnvironmentDataImport from './EnvironmentDataImport';

type Template = {
  id: string;
  name: string;
  version: string;
  scenarios: string[];
  collections: string[];
  tools: string[];
  source_binding: string;
};
type Pack = { id: string; template_id: string; scenario_id: string; content_sha256: string };
type Environment = {
  id: string;
  name: string;
  manifest_sha256: string;
  readiness?: { status: string };
  manifest: { template_id: string; scenario_id: string; pack_sha256: string; tools: string[] };
};
type Instance = {
  id: string;
  environment_id: string;
  generation: number;
  state: string;
  initial_sha256: string;
};
type Receipt = {
  id: string;
  kind: string;
  content: {
    passed?: boolean;
    status?: string;
    checks?: { check: string; passed: boolean }[];
    reason?: string;
  };
  content_sha256: string;
};
type Library = {
  templates: Template[];
  packs: Pack[];
  environments: Environment[];
  instances: Instance[];
};
type World = {
  instance: Instance;
  state: {
    records: Record<string, Record<string, unknown>[]>;
    files: { path: string; size: number; sha256: string }[];
  };
  events: { id: string; sequence: number; operation: string; result: unknown }[];
};

const examples: Record<string, Record<string, unknown>> = {
  list_records: { collection: 'cases' },
  read_file: { path: 'documents/address.txt' },
  query_statements: {
    company_id: 'fictional-1-1',
    period_id: 'fictional-1-1-2025',
    line_item: 'revenue',
  },
  calculate_financial: {
    line_ids: ['fictional-1-1-2025-assets', 'fictional-1-1-2025-liabilities'],
    operator: 'subtract',
  },
  save_analysis: { text: 'My analysis', source_ids: ['fictional-1-1-2025-revenue'] },
  create_campaign: {
    objective: 'Phone launch',
    copy: 'noise cancelling',
    audience_ids: ['student'],
  },
  allocate_budget: { campaign_id: 'campaign', amount: '100.00', currency: 'INR' },
  request_approval: { target_id: 'campaign' },
  schedule_placement: { target_id: 'campaign', channel: 'social' },
  render_variant: {
    channel: 'search',
    locale: 'en-IN',
    caption: 'Fictional caption',
    disclosure: 'Fictional reference offer',
  },
  inspect_asset: { path: 'assets/search-en-IN.png' },
  submit_variant: { target_id: 'search-en-IN' },
  screen_case: { case_id: 'case' },
  request_information: { case_id: 'case', reason: 'Please provide missing evidence' },
  record_decision: {
    case_id: 'case',
    decision: 'needs_review',
    rationale: 'Required evidence is incomplete',
    evidence_ids: [],
  },
  ownership_paths: { entity_id: 'company' },
  query_transactions: {
    account_id: 'account',
    start: '2026-01-01T00:00:00Z',
    end: '2026-01-15T12:00:00Z',
  },
  record_step: {
    case_id: 'case',
    note: 'Investigated supplied history',
    transaction_ids: ['txn-0'],
  },
  link_case: { case_id: 'case', related_case_id: 'related-case' },
  record_disposition: {
    case_id: 'case',
    disposition: 'escalated',
    rationale: 'Further investigation required',
  },
};

export default function EnvironmentLibrary({
  base,
  canAdmin = false,
}: {
  base: string;
  canAdmin?: boolean;
}) {
  const endpoint = base + '/workspace/environments';
  const [library, setLibrary] = useState<Library | null>(null);
  const [templateId, setTemplateId] = useState('BOD-FIN'),
    [scenario, setScenario] = useState('comparable');
  const [selected, setSelected] = useState<Environment | null>(null),
    [receipts, setReceipts] = useState<Receipt[]>([]);
  const [world, setWorld] = useState<World | null>(null);
  const [packRecords, setPackRecords] = useState<Record<string, Record<string, unknown>[]>>({});
  const [packRef, setPackRef] = useState({ id: '', seed: 1 });
  const [operation, setOperation] = useState('list_records'),
    [argumentsText, setArguments] = useState('{"collection":"companies"}');
  const [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [busy, setBusy] = useState(false);
  const [result, setResult] = useState<unknown>(null);
  const [evidenceId, setEvidenceId] = useState<string | undefined>();
  const [componentTab, setComponentTab] = useState('Database');
  const template = library?.templates.find((t) => t.id === templateId);
  const load = async () => setLibrary(await api(endpoint));
  useEffect(() => {
    let active = true;
    api(endpoint)
      .then((r) => {
        if (active) setLibrary(r);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [endpoint]);
  const act = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await fn();
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const inspect = async (id: string) => {
    const d = await api(endpoint + '/versions/' + id);
    setSelected(d.environment);
    setReceipts(d.receipts);
    setPackRecords(d.pack.content.records);
    setPackRef({ id: d.pack.id, seed: d.pack.content.seed });
    setWorld(null);
    setEvidenceId(undefined);
    setResult(null);
  };
  const refreshWorld = async (id: string) => {
    setWorld(await api(endpoint + '/instances/' + id));
    setEvidenceId(undefined);
  };
  const exportJSON = (value: unknown, name: string) => {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }),
    );
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <section className={s.root} aria-label="Environment library">
      <div className={s.card}>
        <h2>Environments</h2>
        <p>
          Six reference templates · versioned data · actual local component state. Existing model
          benchmarks and scoring are unchanged.
        </p>
        <p>
          <strong>Local synthetic reference runtime.</strong> No cloud provisioning, native
          isolation or model calls. Published Praxis task bindings are still required for authentic
          benchmark execution.
        </p>
        {error && <p role="alert">{error}</p>}
        {message && <p role="status">{message}</p>}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            void act(async () => {
              const built = await api(endpoint + '/builds', 'POST', {
                template: templateId,
                scenario,
                seed: Number(form.get('seed')),
                name: form.get('name'),
                runtime_profile: 'local-reference-v1',
              });
              await inspect(built.environment.id);
              setMessage(
                built.state === 'validated_local'
                  ? 'Built locally: components populated, read back, mutated, isolated and reset. Inspect the checks and register the exact version.'
                  : 'Local validation failed. Inspect the retained checks.',
              );
            });
          }}
        >
          <div className={s.actions}>
            <label>
              Template
              <select
                aria-label="Environment template"
                value={templateId}
                onChange={(e) => {
                  const t = library!.templates.find((t) => t.id === e.target.value)!;
                  setTemplateId(t.id);
                  setScenario(t.scenarios[0]);
                }}
              >
                {library?.templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Scenario
              <select
                aria-label="Environment scenario"
                value={scenario}
                onChange={(e) => setScenario(e.target.value)}
              >
                {template?.scenarios.map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label>
              Generator seed
              <input name="seed" type="number" min={0} max={2147483647} defaultValue={1} required />
            </label>
            <label>
              Name
              <input name="name" required maxLength={120} defaultValue="Reference environment" />
            </label>
          </div>
          <p>{template?.source_binding}</p>
          <button className={s.primary} disabled={busy}>
            Build and validate local environment
          </button>
        </form>
      </div>
      <div className={s.card}>
        <h3>Saved environment versions</h3>
        <div
          style={{ maxHeight: '24rem', overflow: 'auto' }}
          role="region"
          aria-label="Saved environment versions"
          tabIndex={0}
        >
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Template / scenario</th>
                <th>Pack</th>
                <th>Status</th>
                <th>Inspect</th>
              </tr>
            </thead>
            <tbody>
              {library?.environments.map((v) => (
                <tr key={v.id}>
                  <td>{v.name}</td>
                  <td>
                    {v.manifest.template_id} · {v.manifest.scenario_id}
                  </td>
                  <td>{v.manifest.pack_sha256.slice(0, 12)}</td>
                  <td>{v.readiness?.status.replaceAll('_', ' ') || 'Inspect receipts'}</td>
                  <td>
                    <button disabled={busy} onClick={() => void act(() => inspect(v.id))}>
                      Open version {v.id.slice(0, 8)}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!library?.environments.length && (
          <p>No environment versions yet. Select a template above.</p>
        )}
      </div>
      {selected && (
        <div className={s.card}>
          <h3>{selected.name}</h3>
          <p>
            {selected.manifest.template_id} · {selected.manifest.scenario_id} · immutable version{' '}
            {selected.id.slice(0, 8)}
          </p>
          <div className={s.actions}>
            <button
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  const r = await api(endpoint + `/versions/${selected.id}/validate`, 'POST');
                  await inspect(selected.id);
                  setMessage(
                    r.content.passed
                      ? 'Actual load, mutation, isolation and reset checks passed locally.'
                      : 'Validation failed. Inspect individual checks.',
                  );
                })
              }
            >
              Validate local components
            </button>
            <button
              disabled={busy || !receipts.some((r) => r.kind === 'validation' && r.content.passed)}
              onClick={() =>
                void act(async () => {
                  await api(endpoint + `/versions/${selected.id}/register`, 'POST');
                  await inspect(selected.id);
                  setMessage(
                    'Registered local reference version. Cloud and authentic Task readiness are separate.',
                  );
                })
              }
            >
              Register local version
            </button>
            <button
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  const i = await api(endpoint + `/versions/${selected.id}/instances`, 'POST');
                  await refreshWorld(i.id);
                  setOperation('list_records');
                  setArguments(
                    JSON.stringify({
                      collection: library?.templates.find(
                        (t) => t.id === selected.manifest.template_id,
                      )?.collections[0],
                    }),
                  );
                })
              }
            >
              Open isolated local instance
            </button>
            <button
              onClick={() =>
                exportJSON(
                  { environment: selected, receipts },
                  'environment-version-and-receipts.json',
                )
              }
            >
              Export manifest and receipts
            </button>
          </div>
          <div className={s.actions}>
            {library?.instances
              .filter((i) => i.environment_id === selected.id)
              .map((i) => (
                <button
                  key={i.id}
                  disabled={busy}
                  onClick={() => void act(() => refreshWorld(i.id))}
                >
                  Resume instance {i.id.slice(0, 8)} · generation {i.generation}
                </button>
              ))}
          </div>
          <p>
            Changing data creates a new pack and environment version. Reset restores the pinned
            pack; it never generates fresh data.
          </p>
          {receipts
            .filter((r) => r.kind === 'validation' || r.kind === 'registration')
            .slice(0, 4)
            .map((r) => (
              <details key={r.id}>
                <summary>
                  {r.kind} ·{' '}
                  {r.content.passed === undefined
                    ? r.content.status
                    : r.content.passed
                      ? 'Passed locally'
                      : 'Failed'}
                </summary>
                {r.content.checks?.map((c) => (
                  <p key={c.check}>
                    {c.passed ? 'Pass' : 'Fail'} · {c.check.replaceAll('_', ' ')}
                  </p>
                ))}
                <p>{r.content.reason}</p>
                <code>{r.content_sha256}</code>
              </details>
            ))}
        </div>
      )}
      {selected && (
        <EnvironmentDataImport
          key={'data-' + selected.id}
          base={base}
          template={selected.manifest.template_id}
          scenario={selected.manifest.scenario_id}
          seed={packRef.seed}
          packId={packRef.id}
          records={packRecords}
          onCreated={async (id) => {
            await inspect(id);
            await load();
          }}
        />
      )}
      {world && selected && (
        <div className={s.card}>
          <h3>Live component workspace</h3>
          <p>
            Instance {world.instance.id.slice(0, 8)} · generation {world.instance.generation} ·{' '}
            {world.instance.state}
          </p>
          <div className={s.actions}>
            <button disabled={busy} onClick={() => void act(() => refreshWorld(world.instance.id))}>
              Refresh state
            </button>
            <button
              disabled={busy || world.instance.state !== 'active'}
              onClick={() =>
                void act(async () => {
                  const r = await api(
                    endpoint + `/instances/${world.instance.id}/evidence`,
                    'POST',
                  );
                  exportJSON(r, 'trusted-environment-evidence.json');
                  setEvidenceId(r.id);
                  setResult(r);
                })
              }
            >
              Export trusted evidence
            </button>
            <button
              disabled={busy || world.instance.state !== 'active'}
              onClick={() =>
                void act(async () => {
                  await api(endpoint + `/instances/${world.instance.id}/reset`, 'POST', {
                    expected_generation: world.instance.generation,
                  });
                  await refreshWorld(world.instance.id);
                  setMessage(
                    'Restored the exact pinned initial state. Earlier events remain in evidence history.',
                  );
                })
              }
            >
              Reset to pinned data
            </button>
            <button
              disabled={busy || world.instance.state !== 'active'}
              onClick={() =>
                void act(async () => {
                  await api(endpoint + `/instances/${world.instance.id}/close`, 'POST');
                  await refreshWorld(world.instance.id);
                  setMessage('Instance closed; data and evidence retained.');
                })
              }
            >
              Close instance
            </button>
          </div>
          <div className={s.actions} aria-label="Environment components">
            {['Database', 'Software', 'API', 'Files'].map((tab) => (
              <button
                key={tab}
                aria-pressed={componentTab === tab}
                onClick={() => setComponentTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>
          {componentTab === 'Database' && <h4>Database records</h4>}
          {componentTab === 'Database' &&
            Object.entries(world.state.records).map(([key, rows]) => (
              <details key={key}>
                <summary>
                  {key.replaceAll('_', ' ')} · {rows.length} records
                </summary>
                <div style={{ overflowX: 'auto' }}>
                  <table>
                    <thead>
                      <tr>
                        {Object.keys(rows[0] || {}).map((field) => (
                          <th key={field}>{field.replaceAll('_', ' ')}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.slice(0, 100).map((row, index) => (
                        <tr key={String(row.id || index)}>
                          {Object.keys(rows[0] || {}).map((field) => (
                            <td key={field}>
                              {row[field] === null
                                ? 'Unknown'
                                : typeof row[field] === 'object'
                                  ? JSON.stringify(row[field])
                                  : String(row[field])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {rows.length > 100 && (
                  <p>First 100 rows shown; full state is preserved in evidence.</p>
                )}
              </details>
            ))}
          {componentTab === 'Software' && (
            <div>
              <h4>Application workspace</h4>
              <p>
                The scoped tools below query and change this instance. Changes persist in its
                application-owned records and event trail.
              </p>
              <p>Collections: {Object.keys(world.state.records).join(', ')}</p>
            </div>
          )}
          {componentTab === 'Software' && (world.state.records.approvals || []).length > 0 && (
            <details>
              <summary>Simulated business approval requests</summary>
              <p>
                These belong to the reference campaign workflow, not Anvil configuration or source
                approval. Agents cannot approve their own requests.
              </p>
              {world.state.records.approvals.map((row) => (
                <div key={String(row.id)}>
                  <p>
                    {String(row.target_id)} · {String(row.status)}
                  </p>
                  {row.status === 'pending' && canAdmin && (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        const form = new FormData(e.currentTarget);
                        void act(async () => {
                          await api(
                            endpoint + `/instances/${world.instance.id}/approvals/${row.id}`,
                            'POST',
                            { decision: form.get('decision'), rationale: form.get('rationale') },
                          );
                          await refreshWorld(world.instance.id);
                        });
                      }}
                    >
                      <label>
                        Decision
                        <select name="decision">
                          <option value="approved">Approve local simulation</option>
                          <option value="rejected">Reject local simulation</option>
                        </select>
                      </label>
                      <label>
                        Reason
                        <input name="rationale" required minLength={10} maxLength={2000} />
                      </label>
                      <button disabled={busy}>Record actual Admin decision</button>
                    </form>
                  )}
                  {row.status === 'pending' && !canAdmin && (
                    <p>A project Admin must perform the business decision.</p>
                  )}
                </div>
              ))}
            </details>
          )}
          {componentTab === 'API' && (
            <div>
              <h4>Typed tool service</h4>
              <p>{selected.manifest.tools.join(' · ')}</p>
              <p>
                Calls are bounded and server-captured. External vendor calls, publication, payments
                and regulatory filings are unavailable.
              </p>
            </div>
          )}
          {componentTab === 'Files' && <h4>Actual files</h4>}
          {componentTab === 'Files' &&
            world.state.files.map((f) => (
              <p key={f.path}>
                <a
                  href={
                    '/api/v1' +
                    endpoint +
                    `/instances/${world.instance.id}/files?path=` +
                    encodeURIComponent(f.path)
                  }
                >
                  {f.path}
                </a>{' '}
                · {f.size} bytes · {f.sha256.slice(0, 12)}
              </p>
            ))}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void act(async () => {
                const args = JSON.parse(argumentsText);
                const r = await api(endpoint + `/instances/${world.instance.id}/tools`, 'POST', {
                  operation,
                  arguments: args,
                  expected_generation: world.instance.generation,
                });
                setResult(r);
                await refreshWorld(world.instance.id);
              });
            }}
          >
            <h4>Environment tools</h4>
            <label>
              Operation
              <select
                aria-label="Environment operation"
                value={operation}
                onChange={(e) => {
                  setOperation(e.target.value);
                  setArguments(JSON.stringify(examples[e.target.value] || {}, null, 2));
                }}
              >
                {selected.manifest.tools.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </label>
            <details>
              <summary>Advanced operation arguments</summary>
              <label>
                Operation arguments JSON
                <textarea
                  aria-label="Operation arguments"
                  value={argumentsText}
                  onChange={(e) => setArguments(e.target.value)}
                  rows={5}
                  maxLength={16384}
                />
              </label>
            </details>
            {(() => {
              try {
                const values = JSON.parse(argumentsText);
                return Object.entries(values).map(([key, value]) => (
                  <label key={key}>
                    {key.replaceAll('_', ' ')}
                    <input
                      aria-label={'Tool ' + key}
                      value={Array.isArray(value) ? JSON.stringify(value) : String(value ?? '')}
                      onChange={(e) => {
                        let next: unknown = e.target.value;
                        if (Array.isArray(value)) {
                          try {
                            next = JSON.parse(e.target.value);
                          } catch {
                            return;
                          }
                        }
                        setArguments(JSON.stringify({ ...values, [key]: next }, null, 2));
                      }}
                    />
                  </label>
                ));
              } catch {
                return <p>Correct the advanced JSON before executing.</p>;
              }
            })()}
            <button disabled={busy || world.instance.state !== 'active'}>Execute local tool</button>
          </form>
          {result !== null && (
            <details>
              <summary>Stored result / evidence</summary>
              <pre>{JSON.stringify(result, null, 2)}</pre>
            </details>
          )}
          <details>
            <summary>Ordered tool events · {world.events.length} visible</summary>
            {world.events.map((e) => (
              <p key={e.id}>
                #{e.sequence} · {e.operation} · {JSON.stringify(e.result)}
              </p>
            ))}
          </details>
        </div>
      )}
      {selected && (
        <EnvironmentTaskBindings
          key={selected.id}
          base={base}
          environmentId={selected.id}
          records={world?.state.records}
          evidenceId={evidenceId}
        />
      )}
    </section>
  );
}
