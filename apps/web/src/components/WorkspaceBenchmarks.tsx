'use client';

import BenchmarkFactory from './BenchmarkFactory';
import AnvilHelp from './AnvilHelp';
import { workspaceApi, WorkspaceTask } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';
import { usePathname } from 'next/navigation';
import BenchmarkPreview from './BenchmarkPreview';
import BenchmarkWorkspace from './BenchmarkWorkspace';

export default function WorkspaceBenchmarks({
  base,
  route,
  userId,
  canWrite,
  canAdmin,
  tasks,
}: {
  base: string;
  route: string;
  userId: string;
  canWrite: boolean;
  canAdmin: boolean;
  tasks: WorkspaceTask[];
}) {
  const section = usePathname().split('/')[4];
  const connected = section === 'catalog';
  return (
    <>
      {section === 'preview' ? (
        <>
          <aside className={styles.mockupBanner} aria-label="UI mockup disclosure">
            <strong>UI MOCKUP</strong>
            <span>Illustrative data · No live benchmark execution · Functionality planned</span>
          </aside>
          <BenchmarkPreview />
        </>
      ) : !connected ? (
        <BenchmarkWorkspace
          key={base}
          base={base}
          userId={userId}
          canWrite={canWrite}
          canAdmin={canAdmin}
        />
      ) : (
        <>
          <section className={styles.panel} aria-label="Benchmark scope">
            <h2>Build a benchmark from versioned tasks</h2>
            <p>
              Confirm task requirements, register catalog metadata, compare coverage and save an
              exact-version Suite draft. These actions make no model request and grant no rights or
              spending authority.
            </p>
            <p>
              The current matching workflow supports qualified static synthetic diagnostic tasks
              with an approved objective. Executable Harbor tasks are shown separately below;
              importing one does not register or publish a benchmark.
            </p>
            <a href="#benchmark-catalog">Open catalog and task profiles</a>
          </section>
          <section className={styles.panel} aria-label="Executable task candidates">
            <h2>Executable task candidates</h2>
            <p>
              {tasks.length} loaded task records. This is the current inventory page, not a count of
              independent expert-authored or professor-verified samples.
            </p>
            {tasks.length ? (
              <ul>
                {tasks.map((task) => (
                  <li key={task.id}>
                    <a href={route + '/tasks/' + encodeURIComponent(task.id)}>{task.title}</a>
                    {' · Version ' + task.task_version}
                    {' · ' +
                      (task.package_built ? 'Package saved; run gates apply' : 'Needs preparation')}
                    {' · '}
                    <a href={route + '/runs?task=' + encodeURIComponent(task.task_id)}>
                      Inspect run history
                    </a>
                  </li>
                ))}
              </ul>
            ) : (
              <p>
                No executable tasks loaded. Import a supported task to inspect its qualification.
              </p>
            )}
            <a href={route + '/tasks'}>Open full task inventory</a>
          </section>
          <section className={styles.panel} id="benchmark-catalog" aria-label="Benchmark catalog">
            <h2>Catalog and task profiles</h2>
            <p>
              Select approved objective and published diagnostic task versions. Confirm all profile
              dimensions before registration. Full benchmark manifests, release qualification and
              expert TaskBank publication remain roadmap work.
            </p>
            <BenchmarkFactory
              key={base}
              base={base}
              api={workspaceApi}
              canWrite={canWrite}
              advisorId={userId}
            />
          </section>
        </>
      )}
      {connected && <AnvilHelp screen="factory" />}
    </>
  );
}
