'use client';
import { useCallback, useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import WorkspacePreparation from './WorkspacePreparation';
import s from './ModernWorkspace.module.css';

type ReadyProject = {
  id: string;
  display_id: number;
  name: string;
  readiness: { ready: boolean; status: string };
  packages: { id: string; task_id: string; task_version: string }[];
  project_binding: { task_group_id: string; id: string; snapshot_sha256: string } | null;
};
export default function NewProjectExecution({
  base,
  canAdmin,
  open,
}: {
  base: string;
  canAdmin: boolean;
  open: (id: string) => void;
}) {
  const [projects, setProjects] = useState<ReadyProject[]>([]),
    [selected, setSelected] = useState('');
  const [after, setAfter] = useState<number | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState('');
  const load = useCallback(
    async (cursor = 0) => {
      setLoading(true);
      setError('');
      try {
        const page = await api(
          `${base}/imported-projects?ready_only=true&limit=20&after_display_id=${cursor}`,
        );
        setProjects((prev) => (cursor ? [...prev, ...page.items] : page.items));
        setAfter(page.next_after_display_id);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    },
    [base],
  );
  useEffect(() => {
    setProjects([]);
    setSelected('');
    void load();
  }, [load]);
  const project = projects.find((p) => p.id === selected && p.readiness.ready);
  return (
    <>
      <section className={s.panel}>
        <h2>New Execution</h2>
        <label>
          Project
          <select value={selected} disabled={loading} onChange={(e) => setSelected(e.target.value)}>
            <option value="" disabled>
              Choose a Ready to Run Project
            </option>
            {projects
              .filter((p) => p.readiness.ready)
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_id} · {p.name}
                </option>
              ))}
          </select>
        </label>
        {loading && <p role="status">Checking qualified Projects…</p>}
        {error && <p role="alert">{error}</p>}
        {!loading && !projects.length && (
          <p>
            No Ready to Run Projects in this page. Complete bindings and runtime qualification
            first.
          </p>
        )}
        {after !== null && (
          <button disabled={loading} onClick={() => void load(after)}>
            Load more Projects
          </button>
        )}
        <p>
          Only currently qualified Projects are selectable. Run performs fresh identity, model,
          revocation and budget checks.
        </p>
      </section>
      {project &&
        project.project_binding &&
        (project.packages.length ? (
          <BudgetBoundPreparation
            key={project.id + project.project_binding.snapshot_sha256}
            base={base}
            packageId={project.packages.length === 1 ? project.packages[0].id : undefined}
            createGroup
            runOnSave
            canAuthorizeRun={canAdmin}
            projectBinding={project.project_binding}
            allowedPackageIds={project.packages.map((p) => p.id)}
            open={open}
          />
        ) : (
          <p role="alert">
            The Project has no available bound execution packages. Forge must repair runtime
            qualification before running.
          </p>
        ))}
    </>
  );
}

function BudgetBoundPreparation(props: React.ComponentProps<typeof WorkspacePreparation>) {
  const [budget, setBudget] = useState<{
    id: string;
    active: boolean;
    available_micro_usd: number;
    models: { id: string }[];
  } | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const groupId = props.projectBinding!.task_group_id;
  useEffect(() => {
    let active = true;
    setLoaded(false);
    setError('');
    api(props.base + '/imported-projects/' + encodeURIComponent(groupId) + '/execution-budget')
      .then((value) => {
        if (active) {
          setBudget(value);
          setLoaded(true);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [props.base, groupId, revision]);
  if (error)
    return (
      <p role="alert">
        {error}
        <button onClick={() => setRevision((value) => value + 1)}>Reload shared budget</button>
      </p>
    );
  if (!loaded) return <p role="status">Checking shared QA budget…</p>;
  if (!budget?.active)
    return (
      <section className={s.panel}>
        <p>
          A current shared QA budget is required. An Admin can authorize it in this Project’s
          binding screen. Existing expired or revoked budgets require operator resolution.
        </p>
        <a href={props.base.replace('/projects/', '/workspace/') + '/projects'}>Open Projects</a>
        <button onClick={() => setRevision((value) => value + 1)}>Reload shared budget</button>
      </section>
    );
  return (
    <>
      <p>
        Available shared QA allowance: ${(budget.available_micro_usd / 1000000).toFixed(4)}. The
        full selected case, model and repetition plan must fit; Forge does not silently reduce it.
      </p>
      <WorkspacePreparation
        {...props}
        executionBudgetId={budget.id}
        budgetModelIds={budget.models.map((model) => model.id)}
      />
    </>
  );
}
