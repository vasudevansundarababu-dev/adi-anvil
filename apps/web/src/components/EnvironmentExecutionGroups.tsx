'use client';
import { useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import s from './BenchmarkRunDashboard.module.css';
type Group = {
  id: string;
  name: string;
  tasks: { task_id: string; title: string; environment_ids: string[] }[];
  environments: { id: string; name: string }[];
};
type Version = {
  id: string;
  name: string;
  manifest: { template_id: string };
  readiness: { local_registered: boolean };
};
type Binding = { id: string; task_id: string; task_group_id: string };
export default function EnvironmentExecutionGroups({
  base,
  route,
}: {
  base: string;
  route: string;
}) {
  const [groups, setGroups] = useState<Group[]>([]),
    [versions, setVersions] = useState<Version[]>([]),
    [group, setGroup] = useState(''),
    [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [busy, setBusy] = useState(false);
  const [purpose, setPurpose] = useState('technical_rehearsal'),
    [members, setMembers] = useState<
      Record<
        string,
        { task: string; binding: string; actions: string; source?: string; policyFields?: string }
      >
    >({}),
    [bindings, setBindings] = useState<Record<string, Binding[]>>({}),
    [native, setNative] = useState(false),
    [installedOpenEnv, setInstalledOpenEnv] = useState(false);
  const selected = groups.find((g) => g.id === group);
  useEffect(() => {
    let active = true;
    Promise.all([
      api(base + '/workspace/benchmark'),
      api(base + '/workspace/environments'),
      api(base + '/workspace/environments/execution-capabilities'),
    ])
      .then(([b, e, c]) => {
        if (!active) return;
        setGroups(b.groups);
        setVersions(e.environments.filter((v: Version) => v.readiness.local_registered));
        setNative(c.harbor_host_mediated);
        setInstalledOpenEnv(c.installed_openenv_available);
        setGroup(b.groups[0]?.id || '');
        const initial: typeof members = {};
        for (const v of e.environments) {
          const t = e.templates.find((t: { id: string }) => t.id === v.manifest.template_id);
          initial[v.id] = {
            task: b.groups[0]?.tasks[0]?.task_id || '',
            binding: '',
            actions: JSON.stringify(
              [{ operation: 'list_records', arguments: { collection: t.collections[0] } }],
              null,
              2,
            ),
          };
        }
        setMembers(initial);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [base]);
  const choose = async (v: Version) => {
    try {
      const d = await api(base + '/workspace/environments/bindings');
      setBindings((old) => ({
        ...old,
        [v.id]: (d.bindings || []).filter(
          (b: { environment_id: string }) => b.environment_id === v.id,
        ),
      }));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div className={`${s.root} ${s.card}`}>
      <h3>Environment-backed execution group</h3>
      <p>
        Run saved tool scripts against real versioned component state. These software controls are
        not models. Existing model settings and Task scoring remain unchanged.
      </p>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {!groups.length ? (
        <p>
          Import a Praxis Project in Tasks first. No source approvals or Tasks are generated here.
        </p>
      ) : (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError('');
            try {
              const f = new FormData(e.currentTarget);
              const ids = f.getAll('environment').map(String);
              const body = {
                name: String(f.get('name')),
                task_group_id: group,
                purpose,
                harness: String(f.get('harness')),
                repetitions: Number(f.get('repetitions')),
                candidates: f.get('empty')
                  ? ['configured-tools-v1', 'empty-tools-v1']
                  : ['configured-tools-v1'],
                members: ids.map((id) => ({
                  environment_id: id,
                  task_id: members[id].task,
                  source_environment_id:
                    members[id].source ||
                    selected?.tasks.find((t) => t.task_id === members[id].task)?.environment_ids[0],
                  policy_fields: JSON.parse(members[id].policyFields || '[]'),
                  binding_id:
                    purpose === 'bound_task_evaluation' ? members[id].binding || null : null,
                  actions: JSON.parse(members[id].actions),
                })),
              };
              const p = await api(base + '/workspace/environments/execution-plans', 'POST', body);
              setMessage('Execution group saved. Starting the exact frozen plan.');
              const r = await api(base + '/workspace/benchmark/runs', 'POST', {
                plan_id: p.id,
                expected_plan_sha256: p.snapshot_sha256,
              });
              window.location.assign(route + '/benchmarks?benchmark_run=' + r.id);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <div className={s.grid}>
            <label>
              Name
              <input name="name" required defaultValue="Environment software execution" />
            </label>
            <label>
              Imported Project
              <select
                aria-label="Environment execution Project"
                value={group}
                onChange={(e) => {
                  setGroup(e.target.value);
                  const task = groups.find((g) => g.id === e.target.value)?.tasks[0]?.task_id || '';
                  setMembers((old) =>
                    Object.fromEntries(
                      Object.entries(old).map(([id, m]) => [
                        id,
                        { ...m, task, binding: '', source: '' },
                      ]),
                    ),
                  );
                }}
              >
                {groups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Evaluation purpose
              <select value={purpose} onChange={(e) => setPurpose(e.target.value)}>
                <option value="technical_rehearsal">
                  Technical rehearsal · Task score not evaluated
                </option>
                <option value="bound_task_evaluation">
                  Exact published Task and evaluator bindings
                </option>
              </select>
            </label>
            <label>
              Harness
              <select name="harness">
                <option value="local-components-v1">Local components</option>
                <option value="openenv-local-v1">
                  Local episode protocol · OpenEnv not qualified
                </option>
                <option value="openenv-0.12-local-v1" disabled={!installedOpenEnv}>
                  OpenEnv 0.12 · local engineering trial
                  {!installedOpenEnv ? ' · operator not configured' : ''}
                </option>
                <option value="harbor-host-mediated-v1" disabled={!native}>
                  Harbor 0.25 · host-mediated software{!native ? ' · operator not configured' : ''}
                </option>
              </select>
            </label>
            <label>
              Repetitions
              <input name="repetitions" type="number" min="1" max="5" defaultValue="1" required />
            </label>
          </div>
          <label>
            <input name="empty" type="checkbox" /> Include empty software control for comparison
          </label>
          <div style={{ maxHeight: '32rem', overflow: 'auto' }}>
            {versions.map((v) => (
              <details
                key={v.id}
                onToggle={(e) => {
                  if (e.currentTarget.open && !bindings[v.id]) void choose(v);
                }}
              >
                <summary>
                  <label>
                    <input
                      type="checkbox"
                      name="environment"
                      value={v.id}
                      onChange={(e) => {
                        if (e.target.checked) {
                          const detail = e.currentTarget.closest('details');
                          if (detail) detail.open = true;
                        }
                      }}
                    />
                    {v.name}
                  </label>
                </summary>
                <label>
                  Task
                  <select
                    value={members[v.id]?.task || ''}
                    onChange={(e) =>
                      setMembers((old) => ({
                        ...old,
                        [v.id]: { ...old[v.id], task: e.target.value, binding: '', source: '' },
                      }))
                    }
                  >
                    {selected?.tasks.map((t) => (
                      <option key={t.task_id} value={t.task_id}>
                        {t.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Source-authored environment condition
                  <select
                    value={
                      members[v.id]?.source ||
                      selected?.tasks.find((t) => t.task_id === members[v.id]?.task)
                        ?.environment_ids[0] ||
                      ''
                    }
                    onChange={(e) =>
                      setMembers((old) => ({
                        ...old,
                        [v.id]: { ...old[v.id], source: e.target.value },
                      }))
                    }
                  >
                    {selected?.tasks
                      .find((t) => t.task_id === members[v.id]?.task)
                      ?.environment_ids.map((id) => (
                        <option key={id} value={id}>
                          {selected.environments.find((e) => e.id === id)?.name || id}
                        </option>
                      ))}
                  </select>
                </label>
                {purpose === 'bound_task_evaluation' && (
                  <label>
                    Frozen evaluator binding
                    <select
                      value={members[v.id]?.binding || ''}
                      onChange={(e) =>
                        setMembers((old) => ({
                          ...old,
                          [v.id]: { ...old[v.id], binding: e.target.value },
                        }))
                      }
                    >
                      <option value="">Choose an existing exact binding</option>
                      {(bindings[v.id] || [])
                        .filter(
                          (b) => b.task_group_id === group && b.task_id === members[v.id]?.task,
                        )
                        .map((b) => (
                          <option key={b.id} value={b.id}>
                            {b.id.slice(0, 8)}
                          </option>
                        ))}
                    </select>
                  </label>
                )}
                <label>
                  Explicit software tool actions
                  <textarea
                    aria-label={'Tool script ' + v.manifest.template_id}
                    rows={5}
                    value={members[v.id]?.actions || '[]'}
                    onChange={(e) =>
                      setMembers((old) => ({
                        ...old,
                        [v.id]: { ...old[v.id], actions: e.target.value },
                      }))
                    }
                  />
                </label>
                <details>
                  <summary>Optional custom-policy evidence fields</summary>
                  <p>
                    Map frozen policy verifier field names to trusted collection/record/field
                    values. Missing fields stay Unknown. This does not change policy meaning or Task
                    weights.
                  </p>
                  <textarea
                    aria-label={'Policy fields ' + v.manifest.template_id}
                    rows={4}
                    value={members[v.id]?.policyFields || '[]'}
                    onChange={(e) =>
                      setMembers((old) => ({
                        ...old,
                        [v.id]: { ...old[v.id], policyFields: e.target.value },
                      }))
                    }
                  />
                  <small>
                    Each mapping uses target, collection, record_id, field and transform (identity
                    or count).
                  </small>
                </details>
              </details>
            ))}
          </div>
          {!versions.length && (
            <p>Validate and register environment versions in Environments first.</p>
          )}
          <button className={s.primary} disabled={busy || !versions.length}>
            {busy ? 'Saving…' : 'Save execution group and Run'}
          </button>
          <p>
            Task scoring requires published source bindings. Rehearsals retain Unknown / Not
            evaluated scores. Paid model and cloud dispatch are off.
          </p>
        </form>
      )}
    </div>
  );
}
