'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { GymApiError, age, get, send, wsBase } from './api';
import { GymContext, type Gym } from './ui';
import Home from './Home';
import { ProjectsList, ProjectPage } from './Projects';
import Admin from './Admin';
import Runs from './Runs';

type Me = {
  id: string;
  name: string;
  workspaces: { id: string; slug: string; name: string; profile: string }[];
};

export default function RLGym({ enabled }: { enabled: boolean }) {
  const pathname = usePathname();
  const parts = pathname
    .replace(/^\/gym\/?/, '')
    .split('/')
    .filter(Boolean)
    .map(decodeURIComponent);
  const [me, setMe] = useState<Me | null>(null);
  const [home, setHome] = useState<any>(null);
  const [problem, setProblem] = useState<GymApiError | null>(null);
  const [feedback, setFeedback] = useState('');
  const [todoOpen, setTodoOpen] = useState(false);
  const [todo, setTodo] = useState<any>(null);
  const ws = me?.workspaces[0]?.slug;

  useEffect(() => {
    if (!enabled) return;
    get<Me>('/api/v1/rlgym/me').then(setMe).catch(setProblem);
  }, [enabled]);

  const refreshTodo = useCallback(() => {
    if (!ws) return;
    get(`${wsBase(ws)}/todo`)
      .then(setTodo)
      .catch(() => undefined);
    get(`${wsBase(ws)}/home`)
      .then(setHome)
      .catch(setProblem);
  }, [ws]);
  useEffect(() => {
    refreshTodo();
    const t = setInterval(refreshTodo, 5000);
    return () => clearInterval(t);
  }, [refreshTodo, pathname]);

  if (!enabled) {
    return (
      <div id="gym">
        <main className="page">
          <h2>RL Gym v2 is off</h2>
          <p>
            The new RL Gym is behind the local setting <code>RLGYM_V2=1</code>. The existing
            workspace is at <a href="/workspace">/workspace</a>.
          </p>
        </main>
      </div>
    );
  }
  if (problem?.error?.code === 'UNAUTHENTICATED' || problem?.error?.status === 401) {
    return (
      <div id="gym">
        <header>
          <div>
            <h2>ADI Anvil · RL Gym</h2>
            <small>Frontier Evaluation &amp; Diagnostics Platform</small>
          </div>
        </header>
        <main className="page">
          <h3>Sign in</h3>
          <p>
            Sign in with your assigned local Keycloak identity. Each identity is a distinct person;
            switching people means signing out.
          </p>
          <p>
            <a
              className="button primary"
              href="/api/v1/auth/login"
              style={{
                padding: '8px 12px',
                background: '#2563eb',
                color: '#fff',
                borderRadius: 8,
                textDecoration: 'none',
              }}
            >
              Sign in with Keycloak
            </a>
          </p>
        </main>
      </div>
    );
  }
  if (me && !ws) {
    return (
      <div id="gym">
        <main className="page">
          <h3>No workspace</h3>
          <p>
            You are signed in as {me.name} but are not a member of any RL Gym workspace. An Admin
            can invite you.
          </p>
        </main>
      </div>
    );
  }
  if (!me || !ws || !home)
    return (
      <div id="gym">
        <p className="page">Loading RL Gym…</p>
      </div>
    );

  const gym: Gym = { ws, me: { ...home.me, name: me.name }, say: setFeedback, refreshTodo };
  const section = parts[0] ?? 'home';
  let body: React.ReactNode;
  if (section === 'home') body = <Home />;
  else if (section === 'projects' && parts[1])
    body = <ProjectPage id={parts[1]} tab={parts[2] ?? 'tasks'} rest={parts.slice(3)} />;
  else if (section === 'projects') body = <ProjectsList />;
  else if (section === 'runs') body = <Runs parts={parts.slice(1)} />;
  else if (section === 'admin') body = <Admin parts={parts.slice(1)} />;
  else
    body = (
      <p className="page">
        Not found or no longer available. <Link href="/gym">Back to Home</Link>
      </p>
    );

  const menu = [
    ['home', 'Home', '/gym'],
    ['projects', 'Projects', '/gym/projects'],
    ['runs', 'Runs', '/gym/runs'],
    ['admin', 'Admin', '/gym/admin/models/frontier'],
  ];
  return (
    <GymContext.Provider value={gym}>
      <div id="gym">
        <header>
          <div>
            <h2>RL Gym</h2>
            <small>
              Workspace {home.workspace.slug} · {me.name} · {labelOf(home.me.profile)}
              {home.me.binding_approver ? ' · binding approver' : ''}
            </small>
          </div>
          <nav
            aria-label="Main"
            className="row"
            style={{ padding: 0, border: 0, background: 'none' }}
          >
            {menu.map(([key, label, href]) => (
              <Link
                key={key}
                className="navlink"
                href={href}
                aria-current={section === key ? 'page' : undefined}
              >
                {label}
              </Link>
            ))}
            <Bell count={todo?.count ?? home.todo_count} open={todoOpen} setOpen={setTodoOpen} />
          </nav>
          <div className="row">
            <a href="/workspace" title="The existing Anvil workspace stays available">
              <small>Previous workspace</small>
            </a>
            <button
              onClick={() =>
                send('POST', '/api/v1/auth/logout', {}).finally(() => {
                  window.location.href = '/gym';
                })
              }
            >
              Sign out
            </button>
          </div>
          {todoOpen && <TodoPanel todo={todo} close={() => setTodoOpen(false)} />}
        </header>
        {body}
        <p className="feedback" aria-live="polite">
          {feedback}
        </p>
      </div>
    </GymContext.Provider>
  );
}

export function labelOf(profile?: string) {
  return (
    { admin: 'Admin', rl_engineer: 'RL Engineer', viewer: 'Viewer' }[profile ?? ''] ?? profile ?? ''
  );
}

function Bell({
  count,
  open,
  setOpen,
}: {
  count: number;
  open: boolean;
  setOpen: (v: boolean) => void;
}) {
  return (
    <button
      className="bell"
      aria-expanded={open}
      aria-label={`To do, ${count} open`}
      onClick={() => setOpen(!open)}
    >
      🔔<span className="count">{count}</span>
    </button>
  );
}

function TodoPanel({ todo, close }: { todo: any; close: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const key = (e: KeyboardEvent) => e.key === 'Escape' && close();
    const click = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (ref.current && !ref.current.contains(target) && !target.closest('.bell')) close();
    };
    document.addEventListener('keydown', key);
    document.addEventListener('mousedown', click);
    return () => {
      document.removeEventListener('keydown', key);
      document.removeEventListener('mousedown', click);
    };
  }, [close]);
  return (
    <div id="notif" ref={ref} role="dialog" aria-label="To do">
      <div className="between">
        <h3>To do · {todo?.count ?? 0}</h3>
        <button onClick={close} aria-label="Close">
          ✕
        </button>
      </div>
      {!todo?.count && <p>Nothing is waiting on anyone.</p>}
      {todo?.groups?.map((g: any) => (
        <section className="stack" key={g.key}>
          <h4>
            {g.label} <small>{g.items.length}</small>
          </h4>
          {g.items.map((item: any) => (
            <div
              key={item.id}
              className={`tcard ${item.severity === 'bad' ? 'bad' : item.severity === 'warn' ? 'warn' : ''}`}
            >
              <strong>{item.title}</strong>
              <small>{item.reason}</small>
              <small>
                {item.project_name ? `${item.project_name} · ${item.project_id} · ` : ''}
                {age(item.created_at)}
              </small>
              {item.action_label ? (
                <Link href={item.link} onClick={close}>
                  {item.action_label}
                </Link>
              ) : (
                <small>(waiting, no action)</small>
              )}
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}
