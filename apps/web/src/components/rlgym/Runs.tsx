'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { wsBase } from './api';
import { useData, useGym } from './ui';

// Runs, admission, execution and scoring are work package 2.7; this screen says so instead of pretending.
export default function Runs({ parts }: { parts: string[] }) {
  const { ws } = useGym();
  const query = useSearchParams();
  const project = query.get('project');
  const detail = useData<any>(project ? `${wsBase(ws)}/projects/${project}` : null);
  if (parts[0] === 'new') {
    return (
      <main className="page">
        <h2>New run</h2>
        {detail.data && (
          <p>
            Project <strong>{detail.data.name}</strong> · {detail.data.project_id} ·{' '}
            <span>{detail.data.state}</span>
          </p>
        )}
        <div className="banner" role="status">
          <strong>Not built yet (work package 2.7).</strong> The admission checklist, dry run,
          frozen manifest, episode execution on Harbor and scoring are the next packages. No run can
          be started from the RL Gym v2 yet, and no model is called. The existing workspace keeps
          its own runs at <a href="/workspace">/workspace</a>.
        </div>
        <Link href={project ? `/gym/projects/${project}` : '/gym/projects'}>Back</Link>
      </main>
    );
  }
  return (
    <main className="page">
      <div className="between">
        <h2>Runs</h2>
        <Link href="/gym/runs/new">New run</Link>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Run</th>
              <th>Project</th>
              <th>Models</th>
              <th>State</th>
              <th>Report</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={5} style={{ textAlign: 'left' }}>
                No runs. Runs arrive with work package 2.7 (admission, execution, scoring).
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </main>
  );
}
