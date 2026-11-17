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
    [message, setMessage] = useState(''),
    [methodKey, setMethodKey] = useState('task-rubric-v1');
  const load = () => api(endpoint).then((r) => setData(r.methods));
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [endpoint]);
  return (
    <section className={s.root}>
      <div className={s.card}>
        <h2>Benchmark methods</h2>
        <p>
          A method defines how results are assessed. An evaluator checks a particular criterion,
          policy or trace. The task supplies its rubric; its environment binding selects the tested
          evaluators. A method listed here is not proof that a task is ready to run.
        </p>
        <ol>
          <li>
            Open the task and verify its dataset, environment, policies and evaluator bindings.
          </li>
          <li>Use the task rubric for its own criteria and scoring scale.</li>
          <li>Add compatible safety checks or a separately qualified judge when required.</li>
          <li>
            Select the compatible methods in the benchmark configuration, then save the Execution
            Group.
          </li>
          <li>
            Check readiness and cost before starting a Run; inspect its evidence and coverage
            afterward.
          </li>
        </ol>
        <p>
          KYC uses its versioned 100-point rubric. Marketing Task2 uses weighted 0–4 criterion
          levels. These task profiles require their own qualified bindings. HumanEval+ is
          coding-only; GDPval-AA and Agents Last Exam require their original suites and harnesses.
          Selecting those names cannot produce an official score for an arbitrary business task.
        </p>
        {error && <p role="alert">{error}</p>}
        {message && <p role="status">{message}</p>}
        <table>
          <thead>
            <tr>
              <th>Method</th>
              <th>Version</th>
              <th>Method support</th>
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
                instruction_weight:
                  methodKey === 'custom-gdpval-v1' ? Number(f.get('instruction')) : 40,
                accuracy_weight: methodKey === 'custom-gdpval-v1' ? Number(f.get('accuracy')) : 30,
                tone_weight: methodKey === 'custom-gdpval-v1' ? Number(f.get('tone')) : 30,
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
            <select
              name="method_key"
              aria-label="Source method"
              value={methodKey}
              onChange={(e) => setMethodKey(e.target.value)}
            >
              {data?.catalog.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </label>
          {methodKey === 'custom-gdpval-v1' && (
            <p>
              These weights apply only to the separate Custom GDPval judge metrics. They do not
              change the task rubric. Judge calls require separate qualification and budget
              admission.
            </p>
          )}
          {methodKey === 'custom-gdpval-v1' && (
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
          )}
          <button disabled={busy} className={s.primary}>
            Save methodology
          </button>
        </form>
      </div>
    </section>
  );
}
