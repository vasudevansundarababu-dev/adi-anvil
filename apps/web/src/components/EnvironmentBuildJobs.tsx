'use client';
import { useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
type Job = { id: string; environment_id: string; state: string; phase: string; revision: number };
export default function EnvironmentBuildJobs({
  base,
  revision = 0,
  onUpdated,
}: {
  base: string;
  revision?: number;
  onUpdated: () => void;
}) {
  const path = base + '/workspace/environments/build-jobs';
  const [jobs, setJobs] = useState<Job[]>([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const load = () => api(path).then(setJobs);
  useEffect(() => {
    let active = true;
    api(path)
      .then((r) => {
        if (active) setJobs(r);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [path, revision]);
  async function act(job: Job, cancel = false) {
    setBusy(true);
    setError('');
    try {
      let current = job;
      if (cancel)
        await api(path + '/' + job.id + '/cancel', 'POST', { expected_revision: current.revision });
      else
        for (let n = 0; n < 4 && ['queued', 'running'].includes(current.state); n++)
          current = await api(path + '/' + job.id + '/resume', 'POST', {
            expected_revision: current.revision,
          });
      await load();
      onUpdated();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details>
      <summary>Durable build jobs · {jobs.length} retained</summary>
      {error && <p role="alert">{error}</p>}
      <p>
        Each phase commits its own immutable receipt. Interrupted local jobs can resume from the
        next phase; cloud dispatch remains off.
      </p>
      <table>
        <thead>
          <tr>
            <th>Build</th>
            <th>State / phase</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id}>
              <td>
                {j.id.slice(0, 8)} · environment {j.environment_id.slice(0, 8)}
              </td>
              <td>
                {j.state} · {j.phase} · revision {j.revision}
              </td>
              <td>
                {['queued', 'running'].includes(j.state) && (
                  <>
                    <button disabled={busy} onClick={() => void act(j)}>
                      Resume build
                    </button>
                    <button disabled={busy} onClick={() => void act(j, true)}>
                      Cancel build
                    </button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
