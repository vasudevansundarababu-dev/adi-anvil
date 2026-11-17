'use client';
import { useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import s from './ModernWorkspace.module.css';

type Catalog = {
  groups: { id: string; name: string; environments: { id: string }[] }[];
  runs: {
    id: string;
    state: string;
    created_at: string;
    snapshot: { task_group_id: string; models: { id: string; name: string }[] };
  }[];
};
type Summary = {
  model_key: string;
  percent: string | null;
  mean_points: string | null;
  cells: number;
  unresolved_cells?: number;
};
export default function WorkspaceHome({ base, route }: { base: string; route: string }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null),
    [modelCount, setModelCount] = useState<number | null>(null);
  const [selected, setSelected] = useState(''),
    [rows, setRows] = useState<Summary[]>([]),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(false);
  useEffect(() => {
    let active = true;
    api(base + '/workspace/benchmark')
      .then((value) => {
        if (active) {
          setCatalog(value);
          setSelected(value.groups[0]?.id || '');
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    api(base + '/workspace/models?current_only=true')
      .then((value) => {
        if (active) setModelCount(value.next_cursor ? null : value.items.length);
      })
      .catch(() => {
        if (active) setModelCount(null);
      });
    return () => {
      active = false;
    };
  }, [base]);
  const run = catalog?.runs.find(
    (x) => x.snapshot.task_group_id === selected && x.state === 'completed',
  );
  useEffect(() => {
    let active = true;
    setRows([]);
    if (!run) return;
    setLoading(true);
    api(`${base}/workspace/benchmark/runs/${run.id}`)
      .then((value) => {
        if (active) setRows(value.summary.models);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [base, run?.id]);
  const environments = catalog
    ? new Set(catalog.groups.flatMap((x) => x.environments.map((e) => e.id))).size
    : null;
  const modelNames = Object.fromEntries(run?.snapshot.models.map((x) => [x.id, x.name]) || []);
  return (
    <>
      {error && <p role="alert">{error}</p>}
      <div className={s.grid}>
        {[
          ['Projects', catalog?.groups.length],
          ['Benchmarks run', catalog?.runs.filter((x) => x.state === 'completed').length],
          ['Environment versions', environments],
          ['Configured models', modelCount],
        ].map(([label, value]) => (
          <section className={s.panel} key={label}>
            <h3>{label}</h3>
            <strong>{value ?? 'Unavailable'}</strong>
          </section>
        ))}
      </div>
      <p className={s.muted}>
        Counts reflect the loaded Project/benchmark page (up to 100 records). Environment versions
        are imported bindings, not a claim of active GCP instances. Missing counts are not zero.
      </p>
      <section className={s.panel}>
        <div className={s.actions}>
          <h2>Leaderboard</h2>
          <label>
            Project
            <select value={selected} onChange={(e) => setSelected(e.target.value)}>
              <option value="" disabled>
                Select Project
              </option>
              {catalog?.groups.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p>
          Latest completed execution for the selected Project. Only the same frozen execution cohort
          is compared. Software controls remain labelled in the report; they are not paid-model
          performance.
        </p>
        {loading ? (
          <p>Loading recorded scores…</p>
        ) : !run ? (
          <p>No completed benchmark results for this Project.</p>
        ) : (
          <div className={s.tableScroll}>
            <table>
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Model</th>
                  <th>Score</th>
                  <th>Executed cells</th>
                  <th>Unresolved</th>
                  <th>Report</th>
                </tr>
              </thead>
              <tbody>
                {[...rows]
                  .sort(
                    (a, b) =>
                      (b.percent === null ? -1 : Number(b.percent)) -
                      (a.percent === null ? -1 : Number(a.percent)),
                  )
                  .map((x, i) => (
                    <tr key={x.model_key}>
                      <td>{x.percent === null ? 'Unranked' : i + 1}</td>
                      <td>{modelNames[x.model_key] || x.model_key}</td>
                      <td>{x.percent === null ? 'Unscored' : x.percent + '%'}</td>
                      <td>{x.cells}</td>
                      <td>{x.unresolved_cells ?? 'Not recorded'}</td>
                      <td>
                        <a
                          href={`${route}/benchmarks?benchmark_run=${run.id}&task_group=${selected}&view=Report%20preview`}
                        >
                          View Report
                        </a>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
