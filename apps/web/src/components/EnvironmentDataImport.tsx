'use client';

import { useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import s from './BenchmarkRunDashboard.module.css';

export default function EnvironmentDataImport({
  base,
  template,
  scenario,
  seed,
  packId,
  records,
  onCreated,
}: {
  base: string;
  template: string;
  scenario: string;
  seed: number;
  packId: string;
  records: Record<string, Record<string, unknown>[]>;
  onCreated: (id: string) => Promise<void>;
}) {
  const [collection, setCollection] = useState(''),
    [mapping, setMapping] = useState<Record<string, string>>({});
  const [text, setText] = useState(''),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  return (
    <details className={s.card}>
      <summary>Populate or replace data in a new version</summary>
      <p>
        Map a CSV into one supported collection. The other reference components remain synthetic.
        Your original CSV and declared usage basis are retained; old versions remain unchanged.
      </p>
      {error && <p role="alert">{error}</p>}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const form = new FormData(e.currentTarget);
          setBusy(true);
          setError('');
          try {
            const endpoint = base + '/workspace/environments';
            const pack = await api(endpoint + '/packs/import-csv', 'POST', {
              template,
              scenario,
              seed,
              base_pack_id: packId,
              collection,
              csv_text: text,
              field_mapping: mapping,
              source_name: form.get('source'),
              usage_basis: form.get('usage'),
            });
            const env = await api(endpoint + '/versions', 'POST', {
              pack_id: pack.id,
              name: form.get('name'),
            });
            await onCreated(env.id);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          New environment version name
          <input name="name" required maxLength={120} defaultValue="Updated data reference" />
        </label>
        <label>
          Source name
          <input name="source" required maxLength={120} />
        </label>
        <label>
          Declared usage basis
          <textarea name="usage" required minLength={10} maxLength={2000} rows={2} />
        </label>
        <label>
          Target collection
          <select
            required
            value={collection}
            onChange={(e) => {
              const key = e.target.value;
              setCollection(key);
              setMapping(
                Object.fromEntries(Object.keys(records[key]?.[0] || {}).map((k) => [k, k])),
              );
            }}
          >
            <option value="">Select collection</option>
            {Object.entries(records)
              .filter(([, rows]) => rows.length)
              .map(([key]) => (
                <option key={key}>{key}</option>
              ))}
          </select>
        </label>
        <label>
          Upload CSV
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              if (file.size > 262144) {
                setError('CSV must be at most 256 KiB.');
                return;
              }
              setText(await file.text());
            }}
          />
        </label>
        <label>
          CSV preview
          <textarea
            aria-label="Environment CSV source"
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={262144}
            rows={5}
            required
          />
        </label>
        <h4>Source column mapping</h4>
        {Object.keys(mapping).map((target) => (
          <label key={target}>
            {target.replaceAll('_', ' ')}
            <input
              required
              value={mapping[target]}
              onChange={(e) => setMapping({ ...mapping, [target]: e.target.value })}
            />
          </label>
        ))}
        <p>
          Exact decimals stay text; booleans use true/false and arrays use JSON string arrays.
          Invalid types, unresolved relationships and incomplete mappings are rejected.
        </p>
        <button disabled={busy || !collection || !text}>
          Materialize new data and environment version
        </button>
      </form>
    </details>
  );
}
