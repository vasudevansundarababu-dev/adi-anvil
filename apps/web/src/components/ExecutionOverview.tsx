'use client';
import { useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import s from './BenchmarkRunDashboard.module.css';

type Run = {
  id: string;
  name?: string;
  state: string;
  created_at: string;
  snapshot: { task_group_id: string; repetitions?: number; models: { id: string; name: string }[] };
  report_review?: { ready: boolean };
};
function OperationalExecutionOverview({
  base,
  route,
  canCreate = true,
}: {
  base: string;
  route: string;
  canCreate?: boolean;
}) {
  const [runs, setRuns] = useState<Run[]>([]),
    [names, setNames] = useState<Record<string, string>>({});
  const [search, setSearch] = useState(''),
    [filter, setFilter] = useState(''),
    [error, setError] = useState('');
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let active = true;
    api(base + '/workspace/benchmark')
      .then((result) => {
        if (!active) return;
        setRuns(result.runs);
        setNames(
          Object.fromEntries(
            result.groups.map((x: { id: string; name: string }) => [x.id, x.name]),
          ),
        );
        setLoaded(true);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [base]);
  return (
    <section className={s.root}>
      <div className={s.card}>
        <div className={s.projectSearch}>
          <label>
            Search
            <input
              placeholder="Project name or execution name"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <button onClick={() => setFilter(search)}>Search</button>
          {canCreate && <a href={route + '/execution-groups/new'}>New Execution</a>}
        </div>
        {error && <p role="alert">{error}</p>}
        {!loaded && !error && <p>Loading executions…</p>}
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                {[
                  'Execution Name',
                  'Repetitions',
                  'Project Name',
                  'Date of Run',
                  'Model Names',
                  'Report',
                ].map((x) => (
                  <th key={x}>{x}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs
                .filter((run) =>
                  `${run.name || run.id} ${names[run.snapshot.task_group_id] || ''}`
                    .toLowerCase()
                    .includes(filter.toLowerCase()),
                )
                .map((run) => {
                  const href = `${route}/benchmarks?benchmark_run=${encodeURIComponent(run.id)}&task_group=${encodeURIComponent(run.snapshot.task_group_id)}`;
                  return (
                    <tr key={run.id}>
                      <td>
                        <a href={href}>{run.name || run.id}</a>
                        <small>{run.state}</small>
                      </td>
                      <td>{run.snapshot.repetitions ?? 'Not recorded'}</td>
                      <td>{names[run.snapshot.task_group_id] || 'Project outside loaded page'}</td>
                      <td>{new Date(run.created_at).toLocaleString()}</td>
                      <td>{run.snapshot.models.map((x) => x.name).join(', ')}</td>
                      <td>
                        <a href={href + '&view=Workflow%20Metrics'}>Workflow Metrics</a>
                        {' · '}
                        <a href={href + '&view=Agent%20Performance'}>Agent Performance</a>
                        {' · '}
                        <a
                          href={
                            route + '/expert-review?benchmark_run=' + encodeURIComponent(run.id)
                          }
                        >
                          Expert Review
                        </a>
                        {!run.report_review?.ready && (
                          <small>PDF export subject to report access gates</small>
                        )}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
        {loaded && !runs.length && <p>No recorded benchmark executions.</p>}
        <p className={s.note}>
          Latest recorded benchmark runs, up to 100. Operational execution records remain available
          below until the unified execution API is qualified.
        </p>
      </div>
    </section>
  );
}

export default function ExecutionOverview(props: {
  base: string;
  route: string;
  canCreate?: boolean;
}) {
  return props.canCreate === false ? (
    <ReviewExecutionOverview base={props.base} route={props.route} />
  ) : (
    <OperationalExecutionOverview {...props} />
  );
}

function ReviewExecutionOverview({ base, route }: { base: string; route: string }) {
  type SealedRun = { run_id: string; kind: string; origin: string; created_at: string };
  const [runs, setRuns] = useState<SealedRun[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(true);
  useEffect(() => {
    let active = true;
    setRuns([]);
    setError('');
    setBusy(true);
    api(base + '/workspace/benchmark/review-runs')
      .then((result) => {
        if (active) {
          setRuns(result.items);
          setCursor(result.next_cursor);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [base]);
  return (
    <section className={s.card} aria-label="Executions available for expert review">
      <h2>Executions available for expert review</h2>
      <label>
        Search execution
        <input value={search} onChange={(e) => setSearch(e.target.value)} />
      </label>
      <button onClick={() => setQuery(search)}>Search</button>
      {error && <p role="alert">{error}</p>}
      {busy && <p role="status">Loading reviewable results…</p>}
      <table>
        <thead>
          <tr>
            <th>Execution</th>
            <th>Date of Run</th>
            <th>Result source</th>
            <th>Report</th>
          </tr>
        </thead>
        <tbody>
          {runs
            .filter((run) => run.run_id.toLowerCase().includes(query.toLowerCase()))
            .map((run) => (
              <tr key={run.run_id}>
                <td>
                  {run.run_id}
                  <small>{run.kind}</small>
                </td>
                <td>{new Date(run.created_at).toLocaleString()}</td>
                <td>{run.origin}</td>
                <td>
                  {['Workflow Metrics', 'Agent Performance'].map((name) => (
                    <div key={name}>
                      <a
                        href={
                          route +
                          '/expert-review?benchmark_run=' +
                          encodeURIComponent(run.run_id) +
                          '&view=' +
                          encodeURIComponent(name)
                        }
                      >
                        {name}
                      </a>
                    </div>
                  ))}
                  <a
                    href={route + '/expert-review?benchmark_run=' + encodeURIComponent(run.run_id)}
                  >
                    Expert Review
                  </a>
                </td>
              </tr>
            ))}
        </tbody>
      </table>
      {!busy && !runs.length && <p>No sealed executions available for review.</p>}
      {cursor && (
        <button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError('');
            try {
              const result = await api(
                base + '/workspace/benchmark/review-runs?after=' + encodeURIComponent(cursor),
              );
              setRuns((previous) => [...previous, ...result.items]);
              setCursor(result.next_cursor);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          Load more executions
        </button>
      )}
    </section>
  );
}
