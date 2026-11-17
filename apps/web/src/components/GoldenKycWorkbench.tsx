'use client';

import { useCallback, useEffect, useState } from 'react';
import { workspaceApi } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';
import DatasetExportAccess from './DatasetExportAccess';

type Pack = {
  id: string;
  manifest: { version: string; application_count: number; legal_qualification: string };
};
type Application = { id: string; product: string; state: string; snapshot_sha256: string };
type Trial = {
  id: string;
  application_id: string;
  model_label: string;
  repetition: number;
  generation: number;
  closed: boolean;
};
type Command = {
  id: string;
  status: string;
  result?: {
    trial_id?: string;
    trial_token?: string;
    generation?: number;
    error?: string;
    result?: unknown;
  };
};
type Imported = {
  id: string;
  task_group_id: string;
  environment_id: string;
  binding_count: number;
  evaluator_count: number;
  readiness: { software_run: string; model_benchmark: string; review_blockers: string[] };
};
type AnvilRun = {
  id: string;
  state: string;
  result?: { cells?: number; unscored_cells?: number };
  snapshot: { planned_cells: number };
};
type NativeTask = {
  resolved_task_id: string;
  task_id: string;
  title: string;
  revision: string;
  state?: string;
  case_count?: number;
  ready_for_package: boolean;
  anvil_requirements: string[];
};

export default function GoldenKycWorkbench({
  base,
  route,
  canAdmin,
}: {
  base: string;
  route?: string;
  canAdmin: boolean;
}) {
  const api = base.replace(/\/workspace$/, '') + '/golden-banking/v1';
  const [packs, setPacks] = useState<Pack[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [trials, setTrials] = useState<Trial[]>([]);
  const [imports, setImports] = useState<Imported[]>([]);
  const [anvilRuns, setAnvilRuns] = useState<AnvilRun[]>([]);
  const [nativeTasks, setNativeTasks] = useState<NativeTask[]>([]);
  const [selectedTasks, setSelectedTasks] = useState<string[]>([]);
  const [modelTurns, setModelTurns] = useState(3);
  const [notice, setNotice] = useState('');
  const [selected, setSelected] = useState('');
  const [filter, setFilter] = useState('');
  const [commandId, setCommandId] = useState('');
  const [command, setCommand] = useState<Command | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState<{
    trial_id: string;
    trial_token: string;
    generation: number;
  } | null>(null);
  const [action, setAction] = useState('application.read');
  const [argumentsText, setArgumentsText] = useState('{}');

  const refresh = useCallback(async () => {
    try {
      const [p, t, i, r, n] = await Promise.all([
        workspaceApi(api + '/packs'),
        workspaceApi(api + '/trials'),
        workspaceApi(api + '/anvil/imports'),
        workspaceApi(api + '/anvil/runs'),
        workspaceApi(api + '/paid-tasks'),
      ]);
      setPacks(p);
      setTrials(t);
      setImports(i);
      setAnvilRuns(r);
      setNativeTasks(n);
      setSelectedTasks((current) =>
        current.filter((id) =>
          n.some((task: NativeTask) => task.resolved_task_id === id && task.ready_for_package),
        ),
      );
      setError('');
      if (p[0]) setApplications(await workspaceApi(api + '/packs/' + p[0].id + '/applications'));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load Golden KYC');
    }
  }, [api]);
  async function prepareTaskPackages() {
    setBusy(true);
    setError('');
    try {
      const result = await workspaceApi(api + '/paid-task-packages', 'POST', {
        resolved_task_ids: selectedTasks,
        max_model_calls: modelTurns,
      });
      setNotice(
        `Prepared ${result.task_count} reusable state task packages. Choose these together in an execution group with one shared budget. No model call has started.`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Task package preparation failed');
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function submit(path: string, body: unknown) {
    setBusy(true);
    setError('');
    try {
      const result = await workspaceApi(api + path, 'POST', body);
      setCommandId(result.command_id);
      setCommand(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Command failed');
    } finally {
      setBusy(false);
    }
  }
  async function anvilAction(path: string, body: unknown) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await workspaceApi(api + path, 'POST', body);
      setNotice(
        path.endsWith('/import')
          ? `Imported ${result.binding_count} task bindings and ${result.evaluator_count} evaluator configurations into Forge.`
          : `Forge run ${result.run_id} queued. Paid calls remain off.`,
      );
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Forge action failed');
    } finally {
      setBusy(false);
    }
  }
  async function inspect() {
    setBusy(true);
    try {
      const result: Command = await workspaceApi(api + '/commands/' + commandId);
      setCommand(result);
      if (result.result?.trial_id && result.result.trial_token) {
        setActive({
          trial_id: result.result.trial_id,
          trial_token: result.result.trial_token,
          generation: result.result.generation ?? 0,
        });
      }
      if (result.status !== 'queued') await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to inspect command');
    } finally {
      setBusy(false);
    }
  }
  async function download(trial: Trial) {
    try {
      const data = await workspaceApi(api + '/trials/' + trial.id + '/export');
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
      );
      const link = document.createElement('a');
      link.href = url;
      link.download = 'golden-kyc-' + trial.application_id + '.json';
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed');
    }
  }
  return (
    <>
      {canAdmin && <DatasetExportAccess key={base} base={base} />}
      <section className={styles.panel} aria-label="Golden KYC pilot">
        <h2>Golden Bank · KYC pilot</h2>
        <p>5 reusable state tasks · shared application dataset, environment and evaluators</p>
        <p>
          California, New York, Texas, Florida and Illinois tasks each process their assigned
          application cases. Import loads the shared evaluator configurations and environment
          bindings. This panel runs software qualification; actual model benchmarks require separate
          admission. Policy and independent case reviews remain visible in the results.
        </p>
        {error && <p role="alert">{error}</p>}
        {notice && <p role="status">{notice}</p>}
        <h3>Actual model benchmark preparation</h3>
        <p>
          Publish, author and review the five reusable state workflows in Authoring, then export and
          resolve them in Forge. Forge supplies the shared cases, environment and evaluator
          bindings. Software qualification below does not run a model benchmark.
        </p>
        {nativeTasks.length === 0 ? (
          <p>No corrected Authoring state tasks have been resolved in this project yet.</p>
        ) : (
          <fieldset>
            <legend>Reviewed state tasks received from Authoring</legend>
            {nativeTasks.map((task) => (
              <div key={task.resolved_task_id}>
                <label>
                  <input
                    type="checkbox"
                    disabled={!task.ready_for_package || busy}
                    checked={selectedTasks.includes(task.resolved_task_id)}
                    onChange={(e) =>
                      setSelectedTasks((current) =>
                        e.target.checked
                          ? [...current, task.resolved_task_id]
                          : current.filter((id) => id !== task.resolved_task_id),
                      )
                    }
                  />
                  {task.title || task.task_id} · {task.state || 'Binding needs attention'} ·{' '}
                  {task.case_count ?? '?'} application cases · revision {task.revision}
                </label>
                {task.anvil_requirements.map((reason) => (
                  <p key={reason}>{reason}</p>
                ))}
              </div>
            ))}
            <label>
              Maximum model turns per application{' '}
              <input
                type="number"
                min={1}
                max={100}
                value={modelTurns}
                onChange={(e) => setModelTurns(Number(e.target.value))}
              />
            </label>
            {canAdmin && (
              <button
                disabled={
                  busy ||
                  selectedTasks.length === 0 ||
                  selectedTasks.length > 5 ||
                  !Number.isInteger(modelTurns) ||
                  modelTurns < 1 ||
                  modelTurns > 100
                }
                onClick={() => void prepareTaskPackages()}
              >
                Prepare selected benchmark tasks
              </button>
            )}
          </fieldset>
        )}
        <p>
          <a href={base.replace('/projects/', '/workspace/') + '/execution-groups/new'}>
            Configure the shared benchmark run
          </a>{' '}
          ·{' '}
          <a href={base.replace('/projects/', '/workspace/') + '/evaluators'}>
            Inspect evaluator configurations
          </a>
        </p>
        <h3>Dataset and software qualification</h3>
        <button disabled={busy} onClick={() => void refresh()}>
          Refresh inventory
        </button>{' '}
        {canAdmin && (
          <button disabled={busy} onClick={() => void submit('/seed', {})}>
            Prepare frozen 200-case pilot
          </button>
        )}
        {canAdmin && packs[0] && (
          <button
            disabled={busy}
            onClick={() => void anvilAction('/anvil/import', { pack_id: packs[0].id })}
          >
            Import and bind in Forge
          </button>
        )}
        {imports[0] && (
          <div>
            <p>
              {imports[0].binding_count} task bindings · {imports[0].evaluator_count} evaluator
              configurations · Software run: {imports[0].readiness.software_run}
            </p>
            <p>
              Scored model benchmark: {imports[0].readiness.model_benchmark}. Required reviews:
              state and bank-charter rules; independent case expectations.
            </p>
            {canAdmin && (
              <button
                disabled={busy || imports[0].readiness.software_run !== 'ready'}
                onClick={() =>
                  void anvilAction('/anvil/runs', { import_id: imports[0].id, repetitions: 1 })
                }
              >
                Run dataset software qualification in Forge
              </button>
            )}
          </div>
        )}
        {anvilRuns.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Forge run</th>
                <th>Status</th>
                <th>Cells</th>
                <th>Report</th>
              </tr>
            </thead>
            <tbody>
              {anvilRuns.map((run) => (
                <tr key={run.id}>
                  <td>{run.id.slice(0, 8)}</td>
                  <td>{run.state}</td>
                  <td>
                    {run.result?.cells ?? 0}/{run.snapshot.planned_cells}
                    {run.result?.unscored_cells !== undefined
                      ? ` · ${run.result.unscored_cells} unscored`
                      : ''}
                  </td>
                  <td>
                    <a
                      href={
                        (route || '/workspace/' + base.split('/')[2]) +
                        '/benchmarks?benchmark_run=' +
                        encodeURIComponent(run.id)
                      }
                    >
                      Open Forge result and report
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {packs.length === 0 ? (
          <p>
            No pilot has been prepared in this project. Preparation requires the dedicated Golden
            scheduler.
          </p>
        ) : (
          packs.map((p) => (
            <p key={p.id}>
              {p.manifest.version} · {p.manifest.application_count} applications · Legal
              qualification: {p.manifest.legal_qualification}
            </p>
          ))
        )}
        {commandId && (
          <div aria-live="polite">
            <p>Command: {command?.status || 'accepted; awaiting scheduler'}</p>
            <button disabled={busy} onClick={() => void inspect()}>
              Check command
            </button>
            {command?.result && (
              <pre>
                {JSON.stringify(
                  {
                    ...command.result,
                    trial_token: command.result.trial_token
                      ? '[private trial credential retained in this tab]'
                      : undefined,
                  },
                  null,
                  2,
                )}
              </pre>
            )}
          </div>
        )}
      </section>
      <section className={styles.panel} aria-label="Golden application inventory">
        <h3>Application inventory</h3>
        <label>
          Filter by application, state or product{' '}
          <input value={filter} onChange={(e) => setFilter(e.target.value)} />
        </label>
        <p>
          {
            applications.filter((a) =>
              [a.id, a.state, a.product].join(' ').toLowerCase().includes(filter.toLowerCase()),
            ).length
          }{' '}
          matching applications
        </p>
        <label>
          Application{' '}
          <select
            aria-label="Application"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="">Choose an application</option>
            {applications
              .filter((a) =>
                [a.id, a.state, a.product].join(' ').toLowerCase().includes(filter.toLowerCase()),
              )
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.id} · {a.state} · {a.product}
                </option>
              ))}
          </select>
        </label>{' '}
        {canAdmin && (
          <button
            disabled={busy || !selected || !packs[0]}
            onClick={() =>
              void submit('/trials', {
                pack_id: packs[0].id,
                application_id: selected,
                model_label: 'software-toolkit',
                repetition: 1,
              })
            }
          >
            Start clean software trial
          </button>
        )}
      </section>
      {active && (
        <section className={styles.panel} aria-label="Assigned investigation toolkit">
          <h3>Investigation toolkit</h3>
          <p>Trial {active.trial_id}. All commands are scoped to this assignment.</p>
          <label>
            Tool{' '}
            <select aria-label="Tool" value={action} onChange={(e) => setAction(e.target.value)}>
              {[
                'application.read',
                'documents.list',
                'document.read',
                'document.compare',
                'policy.read',
                'identity.check',
                'document.check',
                'address.check',
                'screening.check',
                'authority.check',
                'operation.lookup',
                'operation.read',
                'information.request',
                'information.read',
                'finding.write',
                'finding.resolve',
                'specialist.refer',
                'specialist.read',
                'search',
                'search.read',
                'recommend',
              ].map((a) => (
                <option key={a}>{a}</option>
              ))}
            </select>
          </label>
          <label>
            Tool arguments{' '}
            <textarea
              rows={5}
              value={argumentsText}
              onChange={(e) => setArgumentsText(e.target.value)}
            />
          </label>
          <button
            disabled={busy}
            onClick={() => {
              try {
                void submit('/trials/' + active.trial_id + '/actions', {
                  generation: active.generation,
                  trial_token: active.trial_token,
                  action,
                  arguments: JSON.parse(argumentsText),
                });
              } catch {
                setError('Enter valid JSON tool arguments.');
              }
            }}
          >
            Submit tool action
          </button>
        </section>
      )}
      {canAdmin && packs[0] && (
        <button
          disabled={busy}
          onClick={() => void submit('/runs', { pack_id: packs[0].id, repetitions: 1 })}
        >
          Prepare 200 clean software trial cells
        </button>
      )}
      <section className={styles.panel}>
        <h3>Retained trials</h3>
        {trials.length === 0 ? (
          <p>No trials yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Application</th>
                <th>Run label</th>
                <th>Repetition</th>
                <th>Status</th>
                <th>Record</th>
              </tr>
            </thead>
            <tbody>
              {trials.map((t) => (
                <tr key={t.id}>
                  <td>{t.application_id}</td>
                  <td>{t.model_label}</td>
                  <td>{t.repetition}</td>
                  <td>{t.closed ? 'Recommendation submitted' : 'Investigation active'}</td>
                  <td>
                    <button onClick={() => void download(t)}>Export assessment</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
