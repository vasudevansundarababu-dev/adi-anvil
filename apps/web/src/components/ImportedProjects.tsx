'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import ProjectBindings, { ImportedProject } from './ProjectBindings';
import { projectPresentation } from '../lib/projectPresentation';
import TaskFlowViewer from './TaskFlowViewer';
import s from './BenchmarkRunDashboard.module.css';

type Group = ImportedProject & {
  content_sha256?: string;
  source_sha256?: string;
  source_project_id?: string;
  display_id?: number;
  readiness?: Status;
  source_origin?: { kind: string };
};
type Status = { status: string; ready: boolean };
type ImportResult = {
  id?: string;
  status?: string;
  source_sha256?: string;
  project_created?: boolean;
  received_parts?: number;
  expected_parts?: number;
  validation?: {
    valid: boolean | null;
    package_sha256?: string;
    validation_coverage?: string;
    errors?: { code: string; message: string; fix?: string }[];
    anvil_requirements?: { code: string; status: string }[];
    review_gates?: { code: string; status: string }[];
  };
};

type ImportedProjectsProps = {
  base: string;
  canAdmin?: boolean;
};

export default function ImportedProjects(props: ImportedProjectsProps) {
  return <ScopedImportedProjects key={props.base} {...props} />;
}

function ScopedImportedProjects({
  base,
  canAdmin = false,
}: ImportedProjectsProps) {
  const [groups, setGroups] = useState<Group[]>([]),
    [selected, setSelected] = useState<Group | null>(null);
  const [bindingTab, setBindingTab] = useState(0);
  const [bindingLocked, setBindingLocked] = useState(false);
  const [statuses, setStatuses] = useState<Record<string, Status>>({});
  const [after, setAfter] = useState<number | null>(null),
    [listLoading, setListLoading] = useState(false);
  const [imported, setImported] = useState<Group | null>(null),
    [previewTask, setPreviewTask] = useState(0);
  const [search, setSearch] = useState(''),
    [filter, setFilter] = useState('');
  const [importing, setImporting] = useState(false),
    [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0),
    [busy, setBusy] = useState(false);
  const [error, setError] = useState(''),
    [phase, setPhase] = useState('');
  const [unconfirmed, setUnconfirmed] = useState(false);
  const [receipt, setReceipt] = useState<ImportResult['validation'] | null>(null);
  const generation = useRef(0);
  const load = useCallback(
    async (cursor = 0) => {
      const current = ++generation.current;
      setListLoading(true);
      if (!cursor) setGroups([]);
      try {
        const result = await api(
          `${base}/imported-projects?include_tasks=true&limit=20&after_display_id=${cursor}&q=${encodeURIComponent(filter)}`,
        );
        if (current !== generation.current) return [];
        if (!Array.isArray(result.items)) throw new Error('Project list response is incomplete.');
        setGroups((previous) =>
          cursor
            ? [...new Map([...previous, ...result.items].map((item) => [item.id, item])).values()]
            : result.items,
        );
        setAfter(result.next_after_display_id);
        setStatuses((previous) => ({
          ...previous,
          ...Object.fromEntries(
            result.items
              .filter((item: Group) => item.readiness)
              .map((item: Group) => [item.id, item.readiness]),
          ),
        }));
        return result.items as Group[];
      } catch (error) {
        if (current === generation.current) throw error;
        return [];
      } finally {
        if (current === generation.current) setListLoading(false);
      }
    },
    [base, filter],
  );
  useEffect(() => {
    void load().catch((e) => setError(e.message));
    return () => {
      generation.current++;
    };
  }, [load]);
  async function open(group: Group) {
    setSelected(group);
    setImporting(false);
    setError('');
    if (group.readiness) setStatuses((previous) => ({ ...previous, [group.id]: group.readiness! }));
  }
  async function upload() {
    if (!file) return;
    setBusy(true);
    setError('');
    setReceipt(null);
    setProgress(0);
    setPhase('Uploading package');
    let accepted = false;
    try {
      const result = await new Promise<ImportResult>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/v1' + base + '/workspace/benchmark/import');
        const csrf =
          document.cookie
            .split('; ')
            .find((x) => x.startsWith('anvil_csrf='))
            ?.split('=')[1] || '';
        xhr.setRequestHeader('X-CSRF-Token', csrf);
        xhr.setRequestHeader('Idempotency-Key', crypto.randomUUID());
        xhr.setRequestHeader('Content-Type', 'application/zip');
        xhr.timeout = 120000;
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) setProgress(Math.round((e.loaded / e.total) * 100));
        };
        xhr.upload.onload = () => setPhase('Upload complete. Server is validating the package.');
        xhr.onload = () => {
          try {
            const body = JSON.parse(xhr.responseText);
            if (xhr.status >= 200 && xhr.status < 300) resolve(body.data);
            else {
              const validation = body.error?.message;
              if (
                validation &&
                typeof validation === 'object' &&
                (validation.valid === false || validation.valid === null) &&
                Array.isArray(validation.errors)
              )
                setReceipt(validation);
              reject(
                Object.assign(
                  new Error(
                    typeof body.error?.message === 'string'
                      ? body.error.message
                      : 'Package validation or import failed. No successful import confirmed.',
                  ),
                  { outcomeUnconfirmed: xhr.status >= 500 },
                ),
              );
            }
          } catch {
            reject(
              Object.assign(
                new Error(
                  'Invalid server response. Import outcome is unconfirmed; inspect existing Projects before retrying.',
                ),
                { outcomeUnconfirmed: true },
              ),
            );
          }
        };
        xhr.onerror = xhr.ontimeout = () =>
          reject(
            Object.assign(
              new Error(
                'Connection interrupted. Import outcome is unconfirmed; inspect existing Projects before retrying.',
              ),
              { outcomeUnconfirmed: true },
            ),
          );
        xhr.send(file);
      });
      accepted = true;
      setReceipt(result.validation || null);
      if (result.status === 'batch_incomplete') {
        if (
          result.project_created !== false ||
          !Number.isSafeInteger(result.received_parts) ||
          !Number.isSafeInteger(result.expected_parts) ||
          result.received_parts! < 1 ||
          result.expected_parts! <= result.received_parts!
        )
          throw new Error(
            'The batch receipt is incomplete. Inspect Projects before importing again.',
          );
        setPhase(
          `Received ${result.received_parts} of ${result.expected_parts} package parts. No Project created yet. Choose the next part.`,
        );
        setFile(null);
        setProgress(100);
        return;
      }
      if (typeof result.id !== 'string' || !result.id)
        throw new Error(
          'The import response has no Project ID. Inspect Projects before importing again.',
        );
      const group = (await api(
        `${base}/imported-projects/${encodeURIComponent(result.id)}`,
      )) as Group;
      if (group.id !== result.id || !Array.isArray(group.tasks))
        throw new Error(
          'Import was accepted, but the Project detail could not be confirmed. Inspect Projects before importing again.',
        );
      if (result.source_sha256 && group.source_sha256 !== result.source_sha256)
        throw new Error(
          'The imported Project source does not match its receipt. Inspect Projects before importing again.',
        );
      setPhase(
        'Package validation and import succeeded. Required bindings remain subject to qualification.',
      );
      setImported(group);
      setPreviewTask(0);
      setProgress(100);
      if (group.readiness)
        setStatuses((previous) => ({ ...previous, [group.id]: group.readiness! }));
    } catch (e) {
      setError((e as Error).message);
      if (accepted || (e as Error & { outcomeUnconfirmed?: boolean }).outcomeUnconfirmed)
        setUnconfirmed(true);
    } finally {
      setBusy(false);
    }
  }
  if (selected)
    return (
      <>
        <label>
          Current Project
          <select
            value={selected.id}
            disabled={bindingLocked}
            onChange={(event) => {
              const project = groups.find((item) => item.id === event.target.value);
              if (project) void open(project);
            }}
          >
            {[...new Map([...groups, selected].map((item) => [item.id, item])).values()].map(
              (item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ),
            )}
          </select>
        </label>
        {bindingLocked && (
          <p>Save your changes before switching Projects. A save in progress must finish first.</p>
        )}
        <button
          disabled={bindingLocked}
          onClick={() => {
            if (bindingLocked) return;
            setSelected(null);
            void load().catch((e) => setError(e.message));
          }}
        >
          Back to Projects
        </button>
        {error && <p role="alert">{error}</p>}
        <ProjectBindings
          key={selected.id}
          base={base}
          group={selected}
          canAdmin={canAdmin}
          initialTab={bindingTab}
          onTabChange={setBindingTab}
          onNavigationLockChange={setBindingLocked}
        />
      </>
    );
  return (
    <section className={s.root}>
      <div className={s.card}>
        <h2>{importing ? 'Import Project' : 'Projects'}</h2>
        {error && <p role="alert">{error}</p>}
        {importing ? (
          <>
            <label>
              Authoring export package{' '}
              <input
                type="file"
                accept=".zip"
                disabled={busy}
                onChange={(e) => {
                  setFile(e.target.files?.[0] || null);
                  setImported(null);
                  setPhase('');
                  setProgress(0);
                }}
              />
            </label>
            <button
              disabled={!file || busy || !!imported || unconfirmed}
              onClick={() => void upload()}
            >
              {busy ? 'Importing…' : 'Validate & Import'}
            </button>
            <progress value={progress} max={100} aria-label="File upload progress" />
            <p role="status">{phase}</p>
            {receipt && (
              <section aria-label="Import validation receipt">
                <h3>Validation checks for this package part</h3>
                <p>
                  Package conformance:{' '}
                  {receipt.valid === true
                    ? 'Passed'
                    : receipt.valid === false
                      ? 'Failed'
                      : 'Not confirmed'}
                </p>
                <p>Coverage: {receipt.validation_coverage || 'Not returned'}</p>
                <p style={{ overflowWrap: 'anywhere' }}>
                  Package hash: {receipt.package_sha256 || 'Not returned'}
                </p>
                {(receipt.errors || []).slice(0, 30).map((check, index) => (
                  <p key={'error-' + index}>
                    {check.code}: {check.message}
                    {check.fix ? ' ' + check.fix : ''}
                  </p>
                ))}
                {!!receipt.errors && receipt.errors.length > 30 && (
                  <p>Showing the first 30 validation errors.</p>
                )}
                {(receipt.anvil_requirements || []).map((check, index) => (
                  <p key={'requirement-' + index}>
                    {check.code.replaceAll('_', ' ')}: {check.status}
                  </p>
                ))}
                {(receipt.review_gates || []).map((check, index) => (
                  <p key={'review-' + index}>
                    {check.code.replaceAll('_', ' ')}: {check.status}
                  </p>
                ))}
                <p>
                  Package conformance does not establish runtime readiness or complete pending
                  reviews.
                </p>
              </section>
            )}
            {unconfirmed && (
              <p role="alert">
                The import outcome is unconfirmed. Inspect Projects before starting another import.
              </p>
            )}
            {imported && (
              <section aria-label="Imported Project task viewer">
                <h3>{imported.name}</h3>
                <p>
                  Project {imported.display_id ?? 'ID not returned'} ·{' '}
                  {statuses[imported.id]?.status || 'Readiness not confirmed'}
                </p>
                <p>
                  The package was accepted. Environment and evaluator bindings are checked
                  separately before Ready to Run.
                </p>
                <label>
                  Task
                  <select
                    value={previewTask}
                    onChange={(event) => setPreviewTask(Number(event.target.value))}
                  >
                    {imported.tasks.map((task, index) => (
                      <option key={task.task_id} value={index}>
                        {task.title}
                      </option>
                    ))}
                  </select>
                </label>
                {imported.tasks[previewTask] && (
                  <TaskFlowViewer
                    key={imported.tasks[previewTask].task_id}
                    task={imported.tasks[previewTask]}
                    inline
                    onClose={() => {}}
                  />
                )}
                <button
                  disabled={busy}
                  onClick={() => {
                    setBindingTab(0);
                    void open(imported);
                  }}
                >
                  Next
                </button>
              </section>
            )}
            <p>
              The server validates package structure, template/task references, hashes and policy
              sources. Detailed approval checks must be supported by the importer; upload completion
              alone is not validation success.
            </p>
            <button
              disabled={busy}
              onClick={() => {
                setImporting(false);
                void load().catch((error) => setError(error.message));
              }}
            >
              {imported || unconfirmed ? 'Back to Projects' : 'Cancel'}
            </button>
          </>
        ) : (
          <>
            <div className={s.projectSearch}>
              <label>
                Search Projects
                <input
                  value={search}
                  maxLength={200}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Project name"
                />
              </label>
              <button onClick={() => setFilter(search)}>Search</button>
              <button
                onClick={() => {
                  setImporting(true);
                  setImported(null);
                  setUnconfirmed(false);
                  setReceipt(null);
                  setFile(null);
                  setPhase('');
                  setProgress(0);
                  setError('');
                }}
              >
                Import
              </button>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    {[
                      'Project ID',
                      'Project Name',
                      'Execution',
                      'Template / Version',
                      'Number of Tasks',
                      'Task Type',
                      'Status',
                    ].map((x) => (
                      <th key={x}>{x}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {groups.map((group) => {
                    const presentation = projectPresentation(group.tasks);
                    return (
                      <tr key={group.id}>
                        <td>{group.display_id ?? 'Numeric ID pending'}</td>
                        <td>
                          <button onClick={() => void open(group)}>{group.name}</button>
                          {group.source_origin?.kind === 'praxis_authored_batch' && (
                            <small>Authoring Project name is not included in this batch export.</small>
                          )}
                        </td>
                        <td>{presentation.execution}</td>
                        <td>
                          {presentation.templates.map((template) => (
                            <div key={template}>{template}</div>
                          ))}
                        </td>
                        <td>{group.tasks.length}</td>
                        <td>{presentation.taskType}</td>
                        <td>{statuses[group.id]?.status || 'Binding readiness not checked'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {listLoading && <p role="status">Loading Projects…</p>}
            {!listLoading && !groups.length && (
              <p>
                {filter
                  ? 'No Projects match this search.'
                  : 'No imported Projects. Import an approved Authoring export package.'}
              </p>
            )}
            {after !== null && after !== undefined && (
              <button
                disabled={listLoading}
                onClick={() => void load(after).catch((error) => setError(error.message))}
              >
                Load more Projects
              </button>
            )}
          </>
        )}
      </div>
    </section>
  );
}
