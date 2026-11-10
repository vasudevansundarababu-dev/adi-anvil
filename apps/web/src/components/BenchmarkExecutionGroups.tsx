'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { workspaceApi as api } from '../lib/workspace';
import s from './BenchmarkRunDashboard.module.css';

export default function BenchmarkExecutionGroups({ base, route }: { base: string; route: string }) {
  const [plans, setPlans] = useState<
      {
        id: string;
        name: string;
        snapshot_sha256: string;
        runnable: boolean;
        snapshot: { planned_cells: number; source_project?: { name: string } };
      }[]
    >([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const router = useRouter();
  useEffect(() => {
    api(base + '/workspace/benchmark')
      .then((r) => setPlans(r.plans))
      .catch((e) => setError(e.message));
  }, [base]);
  return (
    <section className={s.root}>
      <div className={s.card}>
        <div className={s.actions}>
          <h3>Benchmark Execution Groups</h3>
          <button onClick={() => router.push(route + '/benchmarks?configure=1&new_run=1')}>
            Import Project / create benchmark group
          </button>
        </div>
        <p>
          Reusable Task Group, agent, environment and evaluator selections. Each saved group can
          produce several independently stored Runs.
        </p>
        {error && <p role="alert">{error}</p>}
        {plans.map((p) => (
          <div className={s.plan} key={p.id}>
            <div>
              <strong>{p.name}</strong>
              <small>
                {p.snapshot.source_project?.name || 'Imported Task Group'} ·{' '}
                {p.snapshot.planned_cells} executions
              </small>
            </div>
            <button
              disabled={busy || !p.runnable}
              onClick={async () => {
                setBusy(true);
                try {
                  const r = await api(base + '/workspace/benchmark/runs', 'POST', {
                    plan_id: p.id,
                    expected_plan_sha256: p.snapshot_sha256,
                  });
                  router.push(
                    route +
                      '/benchmarks?benchmark_run=' +
                      r.id +
                      '&task_group=' +
                      r.snapshot.task_group_id,
                  );
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Start benchmark Run
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
