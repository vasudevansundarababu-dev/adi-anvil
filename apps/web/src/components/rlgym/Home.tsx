'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useState } from 'react';
import { wsBase } from './api';
import { Badge, Loading, useData, useGym } from './ui';

// Home · Leaderboard (SCREENS 3.3): the latest completed benchmark run of one project, in one frozen cohort.
export default function Home() {
  const { ws } = useGym();
  const query = useSearchParams();
  const home = useData<any>(`${wsBase(ws)}/home`);
  const [picked, setPicked] = useState(query.get('project') ?? '');
  const [cohort, setCohort] = useState('');
  const projects = home.data?.projects ?? [];
  const project =
    picked || (projects.find((p: any) => p.has_results) ?? projects[0])?.project_id || '';
  const board = useData<any>(
    project
      ? `${wsBase(ws)}/projects/${project}/leaderboard${cohort ? `?cohort=${cohort}` : ''}`
      : null,
  );
  const b = board.data;
  return (
    <main className="page">
      <div className="between">
        <div>
          <h2>Leaderboard</h2>
          <small>
            Only systems in the same frozen cohort (suite, environment and evaluator versions) are
            ranked together.
          </small>
        </div>
        <Loading data={home.data} error={home.error}>
          {() => (
            <div className="row">
              <label>
                <small>Project</small>
                <select
                  value={project}
                  onChange={(e) => {
                    setPicked(e.target.value);
                    setCohort('');
                  }}
                  aria-label="Project"
                >
                  {projects.length === 0 && <option value="">No projects yet</option>}
                  {projects.map((p: any) => (
                    <option key={p.project_id} value={p.project_id}>
                      {p.name} · {p.project_id}
                    </option>
                  ))}
                </select>
              </label>
              {b?.cohorts?.length > 0 && (
                <label>
                  <small>Cohort</small>
                  <select
                    value={b.cohort.key}
                    onChange={(e) => setCohort(e.target.value)}
                    aria-label="Cohort"
                  >
                    {b.cohorts.map((c: any) => (
                      <option key={c.key} value={c.key}>
                        {c.label} · {c.runs} run{c.runs === 1 ? '' : 's'}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          )}
        </Loading>
      </div>
      {b?.run && (
        <p>
          Latest completed run{' '}
          <Link href={`/gym/runs/${b.run.id}`}>
            {b.run.id} · {b.run.name}
          </Link>{' '}
          · {b.cohort.label}
          <small>{b.note}</small>
        </p>
      )}
      <div className="table-wrap scroll">
        <table>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Model</th>
              <th>Score</th>
              <th>Gate</th>
              <th>Executed cells</th>
              <th>Unresolved</th>
              <th>Report</th>
            </tr>
          </thead>
          <tbody>
            {(b?.rows ?? []).length === 0 && (
              <tr>
                <td colSpan={7} style={{ textAlign: 'left' }}>
                  {projects.length === 0
                    ? 'No projects yet: projects arrive by ADI Forge export.'
                    : (b?.empty ?? 'Loading…')}
                </td>
              </tr>
            )}
            {(b?.rows ?? []).map((r: any) => (
              <tr key={r.system_id}>
                <td>{r.rank ?? 'Unranked'}</td>
                <td style={{ textAlign: 'left' }}>{r.model}</td>
                <td>
                  {r.score === null ? 'Unscored' : `${r.score}%`}
                  {r.reviewed && (
                    <small>
                      reviewed · automated {r.automated} · {r.excluded} excluded
                    </small>
                  )}
                  {!r.reviewed && r.likely_range && (
                    <small>
                      likely range {r.likely_range[0]}–{r.likely_range[1]}
                    </small>
                  )}
                </td>
                <td>
                  {r.gate ? (
                    <Badge state={r.gate === 'PASSED' ? 'ready' : 'failed'} label={r.gate} />
                  ) : (
                    '—'
                  )}
                  {r.gate_notes.length > 0 && <small>{r.gate_notes.join('; ')}</small>}
                </td>
                <td>{r.executed_cells}</td>
                <td>{r.unresolved}</td>
                <td>
                  <Link href={`/gym/runs/${b.run.id}/report`}>View report</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {b?.gate_note && b.rows.length > 0 && <small>{b.gate_note}</small>}
    </main>
  );
}
