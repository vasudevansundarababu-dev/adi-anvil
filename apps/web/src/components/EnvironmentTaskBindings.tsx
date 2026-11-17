'use client';

import { useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import s from './BenchmarkRunDashboard.module.css';

type Requirement = {
  kind: string;
  id: string;
  description: string;
  field: string;
  compatible_evaluators: { id: string; name: string; adapter: string }[];
};
type Task = {
  task_group_id: string;
  task_group_name: string;
  task_id: string;
  task_version: string;
  title: string;
  payload_sha256: string;
  fields: string[];
  requirements: Requirement[];
  supported: boolean;
  reason: string;
};
type Mapping = {
  target: string;
  collection: string;
  record_id: string;
  field: string;
  transform: string;
};

export default function EnvironmentTaskBindings({
  base,
  environmentId,
  records,
  evidenceId,
}: {
  base: string;
  environmentId: string;
  records?: Record<string, Record<string, unknown>[]>;
  evidenceId?: string;
}) {
  const endpoint = base + '/workspace/environments';
  const [tasks, setTasks] = useState<Task[]>([]),
    [taskKey, setTaskKey] = useState('');
  const [fields, setFields] = useState<Mapping[]>([]),
    [evaluators, setEvaluators] = useState<Record<string, string>>({});
  const [bindings, setBindings] = useState<
    {
      id: string;
      task_id: string;
      task_version: string;
      environment_id: string;
      snapshot_sha256: string;
    }[]
  >([]);
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [result, setResult] = useState<unknown>(null);
  const task = tasks.find((t) => t.task_group_id + ':' + t.task_id === taskKey);
  const load = async () => {
    const r = await api(endpoint + '/bindings');
    setBindings(
      r.bindings.filter((b: { environment_id: string }) => b.environment_id === environmentId),
    );
  };
  useEffect(() => {
    let active = true;
    Promise.all([
      api(endpoint + `/versions/${environmentId}/binding-options`),
      api(endpoint + '/bindings'),
    ])
      .then(([a, b]) => {
        if (active) {
          setTasks(a.tasks);
          setBindings(
            b.bindings.filter(
              (v: { environment_id: string }) => v.environment_id === environmentId,
            ),
          );
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [endpoint, environmentId]);
  const choose = (key: string) => {
    setTaskKey(key);
    setResult(null);
    const t = tasks.find((t) => t.task_group_id + ':' + t.task_id === key);
    setFields(
      t?.fields.map((target) => ({
        target,
        collection: '',
        record_id: '',
        field: '',
        transform: 'identity',
      })) || [],
    );
    setEvaluators({});
  };
  return (
    <div className={s.card}>
      <h3>Frozen Task and evaluator binding</h3>
      <p>
        Import the published Task in Tasks first. Map trusted environment fields and choose
        compatible tested evaluators; the original rubric and rule meanings remain unchanged.
      </p>
      {error && <p role="alert">{error}</p>}
      <label>
        Imported Task
        <select
          aria-label="Environment binding Task"
          value={taskKey}
          onChange={(e) => choose(e.target.value)}
        >
          <option value="">Select a frozen Task</option>
          {tasks.map((t) => (
            <option
              key={t.task_group_id + ':' + t.task_id}
              value={t.task_group_id + ':' + t.task_id}
            >
              {t.task_group_name} · {t.task_id} v{t.task_version}
            </option>
          ))}
        </select>
      </label>
      {!tasks.length && <p>No imported Tasks are available in this Project.</p>}
      {task && (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError('');
            try {
              const body = {
                environment_id: environmentId,
                task_group_id: task.task_group_id,
                task_id: task.task_id,
                expected_task_sha256: task.payload_sha256,
                fields,
                evaluators: task.requirements.map((r) => ({
                  kind: r.kind,
                  requirement: r.id,
                  configuration_id: evaluators[r.kind + ':' + r.id],
                })),
              };
              const r = await api(endpoint + '/bindings', 'POST', body);
              setResult(r);
              await load();
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <p>{task.reason}</p>
          <h4>Trusted evidence fields</h4>
          {fields.map((m, index) => (
            <div className={s.actions} key={m.target}>
              <strong>{m.target}</strong>
              <label>
                Collection
                <select
                  required
                  value={m.collection}
                  onChange={(e) =>
                    setFields(
                      fields.map((f, i) =>
                        i === index
                          ? { ...f, collection: e.target.value, record_id: '', field: '' }
                          : f,
                      ),
                    )
                  }
                >
                  <option value="">Select collection</option>
                  {Object.keys(records || {}).map((k) => (
                    <option key={k}>{k}</option>
                  ))}
                </select>
              </label>
              <label>
                Record
                <select
                  required
                  value={m.record_id}
                  onChange={(e) =>
                    setFields(
                      fields.map((f, i) =>
                        i === index ? { ...f, record_id: e.target.value, field: '' } : f,
                      ),
                    )
                  }
                >
                  <option value="">Select record</option>
                  {records?.[m.collection]?.map((r) => (
                    <option key={String(r.id)}>{String(r.id)}</option>
                  ))}
                </select>
              </label>
              <label>
                Field
                <select
                  required
                  value={m.field}
                  onChange={(e) =>
                    setFields(
                      fields.map((f, i) => (i === index ? { ...f, field: e.target.value } : f)),
                    )
                  }
                >
                  <option value="">Select field</option>
                  {Object.keys(
                    records?.[m.collection]?.find((r) => r.id === m.record_id) || {},
                  ).map((k) => (
                    <option key={k}>{k}</option>
                  ))}
                </select>
              </label>
              <label>
                Transform
                <select
                  value={m.transform}
                  onChange={(e) =>
                    setFields(
                      fields.map((f, i) => (i === index ? { ...f, transform: e.target.value } : f)),
                    )
                  }
                >
                  <option value="identity">Exact value</option>
                  <option value="count">Count array items</option>
                </select>
              </label>
            </div>
          ))}
          {!records && (
            <p>Open a local instance to inspect its available collections and fields.</p>
          )}
          <h4>Original criteria and constraints</h4>
          {task.requirements.map((r) => (
            <label key={r.kind + ':' + r.id}>
              {r.kind} · {r.id} — {r.description}
              <select
                required
                value={evaluators[r.kind + ':' + r.id] || ''}
                onChange={(e) =>
                  setEvaluators({ ...evaluators, [r.kind + ':' + r.id]: e.target.value })
                }
              >
                <option value="">
                  {r.compatible_evaluators.length
                    ? 'Select a tested evaluator'
                    : 'No compatible tested evaluator configured'}
                </option>
                {r.compatible_evaluators.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name} · {v.adapter}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <button
            disabled={
              busy ||
              !task.supported ||
              !records ||
              task.requirements.some((r) => !r.compatible_evaluators.length)
            }
          >
            Save immutable technical binding
          </button>
        </form>
      )}
      <h4>Saved bindings</h4>
      {!bindings.length && <p>No Task is technically bound to this version yet.</p>}
      {bindings.map((b) => (
        <div key={b.id}>
          <p>
            {b.task_id} v{b.task_version} · {b.snapshot_sha256.slice(0, 12)}
          </p>
          <button
            disabled={busy || !evidenceId}
            onClick={async () => {
              setBusy(true);
              setError('');
              try {
                setResult(
                  await api(endpoint + '/assessments', 'POST', {
                    binding_id: b.id,
                    evidence_receipt_id: evidenceId,
                  }),
                );
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Evaluate captured evidence
          </button>
        </div>
      ))}
      <p>
        These are manual local evidence assessments, not model Runs. Missing evidence leaves the
        score unresolved. Live model dispatch remains off.
      </p>
      {result !== null && (
        <details open>
          <summary>Binding / assessment receipt</summary>
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}
