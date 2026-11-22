'use client';

import { useEffect, useState } from 'react';
import { wsBase } from './api';
import { Loading, useData, useGym } from './ui';

export default function Home() {
  const { ws } = useGym();
  const projects = useData<any>(`${wsBase(ws)}/projects`);
  const [project, setProject] = useState('');
  useEffect(() => {
    if (!project && projects.data?.items?.length) setProject(projects.data.items[0].project_id);
  }, [projects.data, project]);
  const board = useData<any>(project ? `${wsBase(ws)}/projects/${project}/leaderboard` : null);
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
        <Loading data={projects.data} error={projects.error}>
          {() => (
            <label>
              <small>Project</small>
              <select
                value={project}
                onChange={(e) => setProject(e.target.value)}
                aria-label="Project"
              >
                {projects.data.items.length === 0 && <option value="">No projects yet</option>}
                {projects.data.items.map((p: any) => (
                  <option key={p.project_id} value={p.project_id}>
                    {p.name} · {p.project_id}
                  </option>
                ))}
              </select>
            </label>
          )}
        </Loading>
      </div>
      <div className="table-wrap scroll">
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
            {(board.data?.rows ?? []).length === 0 && (
              <tr>
                <td colSpan={6} style={{ textAlign: 'left' }}>
                  {projects.data?.items?.length === 0
                    ? 'No projects yet: projects arrive by ADI Forge export.'
                    : (board.data?.empty ?? 'Loading…')}
                  {board.data?.note ? <small>{board.data.note}</small> : null}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}
