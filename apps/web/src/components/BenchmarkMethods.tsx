'use client';

import { useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import s from './BenchmarkRunDashboard.module.css';

type Method = {
  id: string;
  name: string;
  version: string;
  status: string;
  reason: string | null;
  scope: string;
};
export default function BenchmarkMethods({ base }: { base: string }) {
  const endpoint = base + '/workspace/benchmark';
  const [data, setData] = useState<{
    catalog: Method[];
    configured: { id: string; name: string; configuration: Method }[];
  } | null>(null);
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState('');
  const load = () => api(endpoint).then((r) => setData(r.methods));
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [endpoint]);
  return (
    <section className={s.root}>
      <div className={s.card}>
        <h2>Benchmark methods</h2>
        <p>
          Configure once. Select compatible, versioned methods in an Execution Group. Both Admin and
          RL Engineer can configure methods.
        </p>
        {error && <p role="alert">{error}</p>}
        {message && <p role="status">{message}</p>}
        <table>
          <thead>
            <tr>
              <th>Method</th>
              <th>Version</th>
              <th>Availability</th>
              <th>Scope</th>
            </tr>
          </thead>
          <tbody>
            {data?.catalog.map((m) => (
              <tr key={m.id}>
                <td>{m.name}</td>
                <td>{m.version}</td>
                <td>
                  {m.status.replaceAll('_', ' ')}
                  <p>{m.reason}</p>
                </td>
                <td>{m.scope}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <h3>Saved configurations</h3>
        {data?.configured.map((m) => (
          <p key={m.id}>
            <strong>{m.name}</strong> · {m.configuration.name} v{m.configuration.version} ·{' '}
            {m.configuration.status.replaceAll('_', ' ')}
          </p>
        ))}
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            setBusy(true);
            setError('');
            try {
              await api(endpoint + '/methods', 'POST', {
                name: f.get('name'),
                method_key: f.get('method_key'),
                instruction_weight: Number(f.get('instruction')),
                accuracy_weight: Number(f.get('accuracy')),
                tone_weight: Number(f.get('tone')),
              });
              await load();
              setMessage(
                'Versioned configuration saved. A configuration does not turn an unavailable harness into a completed evaluation.',
              );
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Name
            <input name="name" required maxLength={160} />
          </label>
          <label>
            Source method
            <select name="method_key" aria-label="Source method">
              {data?.catalog.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </label>
          <p>
            Custom GDPval judge weights are separate from the 81-point Task score. Paid judge calls
            remain off.
          </p>
          <div className={s.actions}>
            {[
              ['instruction', 40],
              ['accuracy', 30],
              ['tone', 30],
            ].map(([k, v]) => (
              <label key={k}>
                {k} %<input name={String(k)} type="number" min={0} max={100} defaultValue={v} />
              </label>
            ))}
          </div>
          <button disabled={busy} className={s.primary}>
            Save methodology
          </button>
        </form>
      </div>
    </section>
  );
}
