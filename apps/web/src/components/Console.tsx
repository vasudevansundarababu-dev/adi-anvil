'use client';
import Form from './Form';
import { useCallback, useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import Intake from './Intake';
import ProviderSetup from './ProviderSetup';
import RightsReview from './RightsReview';
import CaseReadiness from './CaseReadiness';
import ExternalResults from './ExternalResults';
import GraphMap from './GraphMap';
import RevisionEditor from './RevisionEditor';
import ReportSummary from './ReportSummary';
import FindingComposer from './FindingComposer';
import FixtureDelivery from './FixtureDelivery';
import TaskImport, { DatasetRunConfiguration } from './TaskImport';
import HarborWorkbench from './HarborWorkbench';
import AnvilHelp from './AnvilHelp';
import MarketingRun from './MarketingRun';
import BenchmarkFactory from './BenchmarkFactory';
import EvaluationWizard from './EvaluationWizard';
import SupportChat from './SupportChat';

type Member = { id: string; name: string; role: string };
type Project = { id: string; name: string; roles: string[] };
type User = { id: string; name: string; projects: Project[] };
type Episode = {
  id: string;
  state: string;
  outcome: string;
  score: number | null;
  invocation_count: number;
};
type Row = {
  id: string;
  created_by?: string;
  kind: string;
  lifecycle: string;
  state?: string;
  origin?: string;
  dataset_version_id?: string;
  dataset_snapshot?: {
    task_count: number;
    version_number: number;
    task_schema_version: string;
    source_provenance?: { classification: string; source_owner: string | null };
  };
  my_review_submitted?: boolean;
  episodes?: Episode[];
  episode_count?: number;
  pending_execution?: number;
  pending_reviews?: number;
  finalized_reviews?: number;
  row_version: number;
  current_revision_id: string;
  content_hash: string;
  content: Record<string, unknown>;
  reviews?: { purpose: string; decision: string; rationale: string }[];
};
type Review = {
  id: string;
  title: string;
  state: string;
  row_version: number;
  output: string;
  execution_origin: string;
  evidence_limitations: string[];
  trace_coverage: string;
  references: string[];
  adjudication_allowed: boolean;
  issue_resolution_allowed: boolean;
  issues: { id: string; code: string; rationale: string; status: string }[];
  rubric: {
    criteria: { id: string; label: string; anchors: Record<string, string> }[];
    critical_rules: string[];
  };
  submitted_assessments?: unknown[];
};
type Graph = {
  truncated: boolean;
  projection_status: string;
  source: string;
  canonical_sequence: number;
  as_of_sequence: number;
  nodes: { id: string; label: string; kind: string; status: string; hash: string }[];
  edges: { source: string; target: string; relation: string }[];
};
const modules = [
  'evaluations',
  'objectives',
  'cases',
  'rubrics',
  'tasks',
  'factory',
  'harbor',
  'suites',
  'protocols',
  'runs',
  'reviews',
  'diagnostics',
  'findings',
  'reports',
  'sales-kits',
  'providers',
];
// Two-row menu: groups on top, the selected group's pages below. Suites and Protocols are
// created by the evaluation wizard; they stay reachable from its records, not the menu.
const groups: { label: string; modules: string[] }[] = [
  { label: 'Home', modules: ['evaluations'] },
  { label: 'Build', modules: ['objectives', 'cases', 'tasks', 'rubrics', 'factory', 'harbor'] },
  { label: 'Run & review', modules: ['runs', 'reviews'] },
  { label: 'Insights', modules: ['diagnostics', 'findings', 'reports', 'sales-kits'] },
  { label: 'Settings', modules: ['providers'] },
];
const labels: Record<string, string> = {
  evaluations: 'Evaluations',
  objectives: 'Research objectives',
  cases: 'Tasks & data',
  rubrics: 'Rubrics',
  tasks: 'Qualification',
  factory: 'Benchmarks',
  harbor: 'Praxis → Harbor',
  suites: 'Suites',
  protocols: 'Protocols',
  runs: 'Run console',
  reviews: 'Review inbox',
  diagnostics: 'Diagnostics',
  reports: 'Reports',
  'sales-kits': 'Sales Kit',
  providers: 'Providers',
};
const notes: Record<string, string> = {
  evaluations:
    'Five steps from objective to run. One Product Owner approval covers the whole plan.',
  objectives: 'Define the question, measurement and scope before evaluation.',
  cases: 'Original synthetic cases. Intake, rights and readiness stay separate.',
  rubrics: 'Anchored criteria and calibration evidence, bound to exact versions.',
  tasks: 'Publish only after content, research and rights reviews.',
  factory: 'Confirm task requirements, compare catalog metadata and prepare a Suite draft.',
  harbor: 'Versioned Praxis imports and isolated synthetic software verification.',
  suites: 'Freeze exact task versions and disclose selection limits.',
  protocols: 'Bind the suite, candidates and independent reviewers.',
  runs: 'Explicit execution through the durable queue. Fixture results are illustrative.',
  reviews: 'Independent, blinded judgments. Missing grades are never treated as zero.',
  diagnostics: 'Observable evidence and relationships. Internal causal reasoning remains unknown.',
  reports: 'Reviewed evidence, honest denominators and internal draft downloads.',
  providers: 'Configuration does not authorize inference. No live models are enabled.',
};
labels.findings = 'Findings';
notes.findings =
  'Reviewed observations and explicitly labeled hypotheses, linked to output evidence.';

async function api(
  path: string,
  method = 'GET',
  body?: unknown,
  version?: number,
  envelope = false,
) {
  const csrf =
    document.cookie
      .split('; ')
      .find((x) => x.startsWith('anvil_csrf='))
      ?.split('=')[1] || '';
  const r = await fetch('/api/v1' + path, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrf,
      ...(method === 'GET' ? {} : { 'Idempotency-Key': crypto.randomUUID() }),
      ...(version ? { 'If-Match': String(version) } : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error?.message || 'Request failed');
  return envelope ? j : j.data;
}
const text = (v: unknown) => (typeof v === 'string' ? v : JSON.stringify(v, null, 2));

export default function Console() {
  const router = useRouter(),
    pathname = usePathname();
  const parts = pathname.split('/');
  const [user, setUser] = useState<User | null>(null),
    [ready, setReady] = useState(false),
    [dark, setDark] = useState(false);
  const [rows, setRows] = useState<Row[]>([]),
    [members, setMembers] = useState<Member[]>([]),
    [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [busy, setBusy] = useState(false),
    [search, setSearch] = useState(''),
    [form, setForm] = useState(false);
  const [options, setOptions] = useState<Record<string, Row[]>>({});
  const [importObjective, setImportObjective] = useState<Row | null>(null);
  const [query, setQuery] = useState('');
  const [pageInfo, setPageInfo] = useState<{
    inventory_total: number;
    matching_total: number;
    qualified_sources?: number;
    source_versions?: number;
    source_families?: number;
    next_cursor: string | null;
  } | null>(null);
  const [review, setReview] = useState<Review | null>(null),
    [editing, setEditing] = useState<Row | null>(null),
    [graph, setGraph] = useState<Graph | null>(null),
    [node, setNode] = useState<Graph['nodes'][number] | null>(null);
  const project = user?.projects.find((p) => p.id === parts[2]) || user?.projects[0];
  const role = (...r: string[]) => !!project?.roles.some((x) => r.includes(x));
  const contentRole = role(
    'researcher',
    'advisor',
    'data-engineer',
    'reviewer',
    'adjudicator',
    'product-owner',
  );
  const visibleModules = modules.filter((module) => {
    if (module === 'harbor') return role('researcher', 'data-engineer', 'product-owner');
    if (module === 'providers') return role('admin');
    if (module === 'reviews') return role('reviewer', 'adjudicator');
    if (module === 'diagnostics') return role('researcher', 'advisor');
    if (module === 'runs')
      return role('researcher', 'advisor', 'data-engineer', 'product-owner', 'admin');
    if (module === 'sales-kits') return role('researcher', 'advisor', 'product-owner', 'sales');
    if (module === 'objectives') return contentRole || role('sales');
    return contentRole;
  });
  const section = modules.includes(parts[3]) ? parts[3] : visibleModules[0] || 'objectives';
  const visibleGroups = groups
    .map((g) => ({ label: g.label, pages: g.modules.filter((m) => visibleModules.includes(m)) }))
    .filter((g) => g.pages.length);
  // Suites and Protocols open from evaluation records and belong to the Build area.
  const activeGroup =
    visibleGroups.find((g) => g.pages.includes(section)) ||
    (['suites', 'protocols'].includes(section)
      ? visibleGroups.find((g) => g.label === 'Build')
      : undefined);
  const base = project ? '/projects/' + project.id : '';
  useEffect(() => {
    let active = true;
    api('/me')
      .then((value) => {
        if (active) setUser(value);
      })
      .catch(() => {
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setReady(true);
      });
    return () => {
      active = false;
    };
  }, []);
  const reload = useCallback(async () => {
    if (!base) return;
    setError('');
    try {
      if (section === 'factory' || section === 'evaluations' || section === 'harbor') {
        setRows([]);
        setPageInfo(null);
        setMembers(await api(base + '/members'));
        return;
      }
      const response = await api(
        base + '/' + section + '?q=' + encodeURIComponent(query),
        'GET',
        undefined,
        undefined,
        true,
      );
      const data = response.data;
      setPageInfo(response.meta.inventory_total === undefined ? null : response.meta);
      if (section === 'diagnostics') {
        setGraph(data);
        setRows([]);
      } else setRows(section === 'factory' ? [] : data);
      if (project?.roles.some((r) => r !== 'sales')) setMembers(await api(base + '/members'));
      else setMembers([]);
    } catch (e) {
      setError((e as Error).message);
      setRows([]);
    }
  }, [base, section, project?.roles, query]);
  useEffect(() => {
    void reload();
  }, [reload]);
  useEffect(() => {
    setForm(false);
    setImportObjective(null);
    setEditing(null);
    setSearch('');
    setQuery('');
  }, [base, section]);
  useEffect(() => {
    if (section !== 'runs' || !rows.some((row) => (row.pending_execution || 0) > 0)) return;
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const updated: Row[] = await api(base + '/runs');
        const detailed = await Promise.all(
          updated.map((row) =>
            rows.some((old) => old.id === row.id && old.episodes)
              ? api(base + '/runs/' + row.id)
              : row,
          ),
        );
        if (!cancelled) setRows(detailed);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    }, 2000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [base, section, rows]);
  async function act(
    fn: () => Promise<unknown>,
    success = 'Saved to the project audit trail.',
    refresh = true,
  ) {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await fn();
      setMessage(success);
      if (refresh) await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function member(role: string, name?: string) {
    return members.find((m) => m.role === role && (!name || m.name === name))?.id || '';
  }
  async function openForm() {
    setForm(!form);
    if (['suites', 'protocols', 'reports'].includes(section)) {
      const kinds =
        section === 'suites'
          ? ['objectives', 'tasks']
          : section === 'protocols'
            ? ['objectives', 'suites', 'providers']
            : ['runs', 'findings'];
      const o: Record<string, Row[]> = {};
      for (const k of kinds) {
        o[k] = [];
        let cursor: string | null = null;
        do {
          const page = await api(
            base + '/' + k + '?limit=100' + (cursor ? '&after=' + cursor : ''),
            'GET',
            undefined,
            undefined,
            true,
          );
          o[k].push(...page.data);
          cursor = page.meta.next_cursor || null;
        } while (cursor);
      }
      setOptions(o);
    }
  }
  async function create(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const value = (k: string) => String(data.get(k) || '');
    let body: Record<string, unknown> = { title: value('title') };
    if (section === 'objectives')
      body = {
        ...body,
        origin: value('origin'),
        entry_type: value('entry_type'),
        hypothesis: value('hypothesis'),
        business_context: value('business_context'),
        measurement_plan: value('measurement_plan'),
        researcher_id: member('researcher'),
        advisor_id: member('advisor'),
        product_owner_id: member('product-owner'),
      };
    if (section === 'suites')
      body = {
        ...body,
        objective_revision_id: value('objective'),
        task_revision_ids: data.getAll('tasks'),
        selection_method: value('selection_method'),
        exposure_note: value('exposure_note'),
        advisor_id: member('advisor'),
        planned_source_count: 200,
      };
    if (section === 'protocols')
      body = {
        ...body,
        objective_revision_id: value('objective'),
        suite_revision_id: value('suite'),
        candidates:
          value('mode') === 'external_result_import_v1'
            ? ['external-reported']
            : value('mode') === 'marketing_interactive_v1'
              ? ['openai-marketing']
              : ['fixture-correct', 'fixture-constraint-blind'],
        repetitions: 1,
        reviewer_ids: [member('reviewer', 'reviewer-1'), member('reviewer', 'reviewer-2')],
        adjudicator_id: member('adjudicator'),
        advisor_id: member('advisor'),
        comparison_policy: value('comparison_policy'),
        pass_policy: value('pass_policy'),
        mode: value('mode'),
        ...(value('mode') === 'marketing_interactive_v1'
          ? {
              connection_id: value('connection'),
              connection_hash: options.providers?.find((p) => p.id === value('connection'))
                ?.content_hash,
              max_output_tokens: 8192,
              episode_timeout_seconds: 600,
            }
          : {}),
      };
    if (section === 'reports')
      body = {
        ...body,
        run_id: value('run'),
        finding_revision_ids: data.getAll('findings'),
        advisor_id: member('advisor'),
        reviewer_id: member('reviewer', 'reviewer-1'),
        product_owner_id: member('product-owner'),
        audience: 'internal_fixture',
      };
    await act(async () => {
      await api(base + '/' + section, 'POST', body);
      setForm(false);
    });
  }
  const change = (r: Row, action: string, body?: unknown) =>
    act(() =>
      api(base + '/' + section + '/' + r.id + '/' + action, 'POST', body ?? {}, r.row_version),
    );
  function decision(r: Row, purpose: string) {
    const rationale = window.prompt(
      'Review rationale (at least 10 characters). This is a synthetic local exercise.',
    );
    if (rationale) void change(r, 'decisions', { purpose, decision: 'approve', rationale });
  }
  async function grade(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!review) return;
    const form = new FormData(e.currentTarget);
    const scores: Record<string, number> = {},
      evidence: Record<string, string> = {};
    for (const c of review.rubric.criteria) {
      scores[c.id] = Number(form.get(c.id));
      evidence[c.id] = String(form.get(c.id + '-evidence'));
    }
    await act(async () => {
      await api(
        base +
          '/episodes/' +
          review.id +
          (review.adjudication_allowed ? '/adjudicate' : '/assessments'),
        'POST',
        {
          scores,
          critical: form.getAll('critical'),
          evidence,
          rationale: String(form.get('rationale')),
        },
        review.row_version,
      );
      setReview(null);
    }, 'Independent assessment saved. Required secondary review or adjudication remains separate.');
  }
  if (!ready)
    return (
      <main>
        <p role="status">Loading your session…</p>
      </main>
    );
  if (!user)
    return (
      <main className="login">
        <img src="/brand/adi-anvil-logo-v1.png" alt="ADI Anvil" />
        <h1>ADI Anvil</h1>
        <p>Frontier Evaluation &amp; Diagnostics Platform</p>
        <div className="banner">Local synthetic workspace · no live inference</div>
        <p className="muted">
          Sign in with your assigned local identity. Each role uses a distinct account.
        </p>
        <a className="button primary" href="/api/v1/auth/login">
          Sign in with Keycloak
        </a>
      </main>
    );
  return (
    <div className={dark ? 'dark' : ''}>
      <header>
        <div>
          <strong>ADI Anvil</strong>
          <small>Frontier Evaluation &amp; Diagnostics Platform</small>
        </div>
        <div className="tools">
          <a className="button" href={'/workspace/' + project?.id + '/overview'}>
            Modern workspace
          </a>
          <small>
            {user.name} · {project?.roles.join(', ')}
          </small>
          <button
            onClick={() => setDark(!dark)}
            aria-label="Toggle color theme"
            aria-pressed={dark}
          >
            {dark ? 'Light' : 'Dark'} theme
          </button>
          <button
            onClick={() =>
              act(async () => {
                await api('/auth/logout', 'POST', {});
                setUser(null);
              })
            }
          >
            Sign out
          </button>
        </div>
      </header>
      <nav aria-label="Project areas">
        {visibleGroups.map((g) => (
          <a
            key={g.label}
            href={'/p/' + project?.id + '/' + g.pages[0]}
            aria-current={g === activeGroup ? 'page' : undefined}
          >
            {g.label}
          </a>
        ))}
      </nav>
      {activeGroup && activeGroup.pages.length > 1 && (
        <nav aria-label={activeGroup.label + ' pages'} className="subnav">
          {activeGroup.pages.map((m) => (
            <a
              key={m}
              href={'/p/' + project?.id + '/' + m}
              aria-current={section === m ? 'page' : undefined}
            >
              {labels[m]}
            </a>
          ))}
        </nav>
      )}
      <main>
        <div className="toolbar">
          <div>
            <div className="eyebrow">{project?.name}</div>
            <h1>{labels[section]}</h1>
            <p className="muted">{notes[section]}</p>
          </div>
          <div>
            <label htmlFor="project">Project</label>
            <select
              id="project"
              value={project?.id}
              onChange={(e) => router.push('/p/' + e.target.value + '/' + section)}
            >
              {user.projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="banner">
          Built-in cases are ADI synthetic; uploaded sources have separate provenance declarations.
          Fixture execution is illustrative; no measured frontier-model performance.
        </div>
        {error && (
          <div className="banner error" role="alert">
            {error}
          </div>
        )}
        {message && (
          <div className="banner success" role="status">
            {message}
          </div>
        )}
        {!['factory', 'evaluations', 'harbor'].includes(section) && (
          <div className="toolbar">
            <div>
              <label htmlFor="search">Search this view</label>
              <input
                id="search"
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search titles or status"
              />
              {pageInfo && (
                <button onClick={() => setQuery(search)} disabled={busy}>
                  Search all records
                </button>
              )}
            </div>
            <div className="actions">
              <button onClick={() => void reload()} disabled={busy}>
                Refresh
              </button>
              {role('researcher') &&
                ['objectives', 'suites', 'protocols', 'reports'].includes(section) && (
                  <button className="primary" onClick={() => void openForm()}>
                    New {section === 'objectives' ? 'objective' : section.slice(0, -1)}
                  </button>
                )}
              {section === 'cases' && role('data-engineer') && (
                <button
                  className="primary"
                  disabled={busy || !member('reviewer', 'reviewer-1') || !member('advisor')}
                  onClick={() =>
                    act(
                      () =>
                        api(base + '/fixtures/import', 'POST', {
                          case_ids: ['MKT-001', 'FIN-001', 'STR-001'],
                          reviewer_id: member('reviewer', 'reviewer-1'),
                          advisor_id: member('advisor'),
                        }),
                      'Three original fixtures imported; review drafts and rights before publishing.',
                    )
                  }
                >
                  Import built-in synthetic cases
                </button>
              )}
              {section === 'cases' && role('data-engineer') && (
                <button
                  disabled={busy || !member('reviewer', 'reviewer-1') || !member('advisor')}
                  onClick={() =>
                    act(
                      async () => {
                        await api(base + '/fixtures/import', 'POST', {
                          case_ids: ['MKT-LH-001'],
                          reviewer_id: member('reviewer', 'reviewer-1'),
                          advisor_id: member('advisor'),
                        });
                        setSearch('MKT-LH-001');
                        setQuery('MKT-LH-001');
                        if (query === 'MKT-LH-001') await reload();
                      },
                      '12-week marketing case, task and rubric drafts imported. Review rights and qualification before use.',
                      false,
                    )
                  }
                >
                  Import 12-week marketing task
                </button>
              )}
            </div>
          </div>
        )}
        {importObjective && (
          <TaskImport
            base={base}
            objective={{
              ...importObjective,
              content: { ...importObjective.content, title: String(importObjective.content.title) },
            }}
            canAttach={role('researcher')}
            onClose={() => setImportObjective(null)}
          />
        )}
        {section === 'runs' && role('researcher') && (
          <DatasetRunConfiguration base={base} onSaved={() => void reload()} />
        )}
        <AnvilHelp screen={importObjective ? 'imports' : section} />
        {base && <SupportChat base={base} api={api} />}
        {section === 'evaluations' && user && (
          <EvaluationWizard
            key={base}
            base={base}
            api={api}
            userId={user.id}
            canAuthor={role('researcher')}
            canApprove={role('product-owner')}
            canResearch={role('researcher', 'advisor')}
          />
        )}
        {section === 'harbor' && (
          <HarborWorkbench
            key={base}
            base={base}
            api={api}
            canApprove={role('product-owner')}
            canPlan={role('researcher', 'product-owner')}
            canAdmin={role('admin')}
          />
        )}
        {section === 'factory' && (
          <BenchmarkFactory
            key={base}
            base={base}
            api={api}
            canWrite={role('researcher')}
            advisorId={member('advisor')}
          />
        )}
        {editing && (
          <RevisionEditor
            key={editing.current_revision_id}
            resource={editing}
            busy={busy}
            onClose={() => setEditing(null)}
            onSave={(body) =>
              void act(async () => {
                const draft = ['draft', 'changes_requested'].includes(editing.lifecycle);
                await api(
                  base + '/' + section + '/' + editing.id + (draft ? '/draft' : '/successor'),
                  draft ? 'PATCH' : 'POST',
                  body,
                  editing.row_version,
                );
                setEditing(null);
              }, 'New draft version saved. Fresh review is required.')
            }
          />
        )}
        {form && (
          <Form className="card" onSubmit={create}>
            <h2>New {section.slice(0, -1)}</h2>
            <label htmlFor="title">Title</label>
            <input id="title" name="title" required minLength={3} />
            {section === 'objectives' && (
              <>
                <div className="fieldgrid">
                  <div>
                    <label htmlFor="origin">Origin</label>
                    <select id="origin" name="origin">
                      <option value="adi_initiated">ADI initiated</option>
                      <option value="customer_requested">Customer requested</option>
                    </select>
                  </div>
                  <div>
                    <label htmlFor="entry_type">Starting point</label>
                    <select id="entry_type" name="entry_type">
                      <option value="capability">Capability led</option>
                      <option value="benchmark">Benchmark led</option>
                    </select>
                  </div>
                </div>
                <label htmlFor="hypothesis">Observable hypothesis</label>
                <textarea id="hypothesis" name="hypothesis" required minLength={10} />
                <label htmlFor="business_context">Business context and scope</label>
                <textarea id="business_context" name="business_context" required />
                <label htmlFor="measurement_plan">Measurement and acceptance plan</label>
                <textarea
                  id="measurement_plan"
                  name="measurement_plan"
                  required
                  minLength={20}
                  placeholder="Cases, candidates, rubric, exclusions and descriptive comparison limits"
                />
              </>
            )}
            {['suites', 'protocols'].includes(section) && (
              <>
                <label htmlFor="objective">Approved objective</label>
                <select id="objective" name="objective" required>
                  <option value="">Select an approved revision</option>
                  {options.objectives
                    ?.filter((r) => r.lifecycle === 'approved')
                    .map((r) => (
                      <option key={r.id} value={r.current_revision_id}>
                        {text(r.content.title)}
                      </option>
                    ))}
                </select>
              </>
            )}
            {section === 'suites' && (
              <>
                <fieldset>
                  <legend>Published task versions</legend>
                  {options.tasks
                    ?.filter((r) => r.lifecycle === 'published')
                    .map((r) => (
                      <label key={r.id}>
                        <input type="checkbox" name="tasks" value={r.current_revision_id} />
                        {text(r.content.title)}
                      </label>
                    ))}
                </fieldset>
                <label htmlFor="selection_method">Selection method</label>
                <textarea
                  id="selection_method"
                  name="selection_method"
                  required
                  defaultValue="Three supplied original synthetic cases; convenience sample for pipeline verification."
                />
                <label htmlFor="exposure_note">Exposure and comparison limits</label>
                <textarea
                  id="exposure_note"
                  name="exposure_note"
                  required
                  defaultValue="Development fixtures only. Predetermined answers; no benchmark generalization or independent expert validation."
                />
              </>
            )}
            {section === 'protocols' && (
              <>
                <label htmlFor="suite">Frozen suite</label>
                <select id="suite" name="suite" required>
                  <option value="">Select frozen suite</option>
                  {options.suites
                    ?.filter((r) => r.lifecycle === 'frozen')
                    .map((r) => (
                      <option key={r.id} value={r.current_revision_id}>
                        {text(r.content.title)}
                      </option>
                    ))}
                </select>
                <label htmlFor="mode">Execution mode</label>
                <select id="mode" name="mode">
                  <option value="fixture">Two deterministic fixture candidates</option>
                  <option value="marketing_interactive_v1">
                    12-week marketing · OpenAI gpt-6-sol
                  </option>
                  <option value="external_result_import_v1">
                    Reported external results — no candidate dispatch
                  </option>
                </select>
                <label htmlFor="connection">OpenAI connection (required for marketing mode)</label>
                <select id="connection" name="connection">
                  <option value="">Select configured connection</option>
                  {options.providers
                    ?.filter(
                      (p) =>
                        p.content.provider_key === 'openai' && p.content.model_id === 'gpt-6-sol',
                    )
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        gpt-6-sol · {p.id}
                      </option>
                    ))}
                </select>
                <p>
                  One attempt per case. Both assigned reviewers and an independent adjudicator are
                  required.
                </p>
                <label htmlFor="comparison_policy">Comparison policy</label>
                <textarea
                  id="comparison_policy"
                  name="comparison_policy"
                  required
                  defaultValue="Same actor inputs and task versions; illustrative fixture pipeline verification only. No measured model ranking."
                />
                <label htmlFor="pass_policy">Pass policy</label>
                <textarea
                  id="pass_policy"
                  name="pass_policy"
                  required
                  defaultValue="Frozen rubric threshold; critical violation overrides numeric pass. Missing judgments stay pending."
                />
              </>
            )}
            {section === 'reports' && (
              <>
                <label htmlFor="run">Reviewed run</label>
                <select id="run" name="run" required>
                  <option value="">Choose reviewed run</option>
                  {options.runs?.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.id}
                    </option>
                  ))}
                </select>
                <p>
                  Internal fixture audience only. Technical, domain, audience and release approvals
                  required.
                </p>
              </>
            )}
            {section === 'reports' && (
              <fieldset>
                <legend>Approved findings from the selected run</legend>
                {options.findings
                  ?.filter((r) => r.lifecycle === 'approved')
                  .map((r) => (
                    <label key={r.id}>
                      <input name="findings" type="checkbox" value={r.current_revision_id} />
                      {text(r.content.title)}
                    </label>
                  ))}
              </fieldset>
            )}
            <p className="muted">
              Reviews are assigned to the project&apos;s distinct local test identities. Assignments
              are bound to this revision.
            </p>
            <button className="primary" disabled={busy}>
              Save draft
            </button>
          </Form>
        )}
        {section === 'findings' && role('researcher') && (
          <FindingComposer key={base} base={base} advisor={member('advisor')} />
        )}
        {((section === 'sales-kits' && role('sales', 'product-owner')) ||
          (section === 'providers' && role('admin'))) && (
          <FixtureDelivery key={base} base={base} roles={project?.roles || []} />
        )}
        {section === 'cases' && role('data-engineer') && <Intake key={base} base={base} />}
        {section === 'cases' && (
          <div className="stats">
            <div>
              <strong>{pageInfo?.inventory_total ?? rows.length}</strong>
              <small>Actual source cases</small>
            </div>
            <div>
              <strong>{pageInfo?.source_versions ?? '—'}</strong>
              <small>Source versions</small>
            </div>
            <div>
              <strong>{pageInfo?.source_families ?? '—'}</strong>
              <small>Source families</small>
            </div>
            <div>
              <strong>{pageInfo?.qualified_sources ?? 0}</strong>
              <small>Sources with published tasks</small>
            </div>
            <div>
              <strong>200</strong>
              <small>Planning target · not evidence of receipt</small>
            </div>
          </div>
        )}
        {section === 'diagnostics' && graph && (
          <>
            <div className="banner">
              Projection: {graph.projection_status} · {graph.source} · applied{' '}
              {graph.as_of_sequence} / canonical {graph.canonical_sequence}
            </div>
            <div className="split">
              <div className="card">
                <h2>Evidence relationships</h2>
                <p className="muted">
                  Select a node to inspect its exact version. Lines represent recorded evidence
                  relationships, not causality.
                </p>
                <GraphMap
                  nodes={graph.nodes.filter((n) =>
                    n.label.toLowerCase().includes(search.toLowerCase()),
                  )}
                  edges={graph.edges}
                  selected={node?.id}
                  onSelect={setNode}
                />
                {graph.truncated && (
                  <p className="muted">
                    Bounded view: at most 200 nodes and 500 relationships. Additional evidence may
                    be outside this snapshot.
                  </p>
                )}
              </div>
              <div className="card">
                <h2>Node inspector</h2>
                {node ? (
                  <>
                    <h3>{node.label}</h3>
                    <p>
                      {node.kind} · {node.status}
                    </p>
                    <p className="muted" style={{ overflowWrap: 'anywhere' }}>
                      {['episode', 'capability', 'case_family'].includes(node.kind)
                        ? 'Evidence ID'
                        : 'Revision'}{' '}
                      {node.id}
                      <br />
                      Digest {node.hash}
                    </p>
                    <h3>Linked records</h3>
                    {graph.edges
                      .filter((e) => e.source === node.id || e.target === node.id)
                      .map((e, i) => {
                        const linked = graph.nodes.find(
                          (n) => n.id === (e.source === node.id ? e.target : e.source),
                        );
                        return (
                          <p key={i}>
                            {e.relation.replaceAll('_', ' ')} →{' '}
                            {linked && (
                              <button
                                aria-label={'Inspect ' + linked.label}
                                onClick={() => {
                                  setSearch('');
                                  setNode(linked);
                                }}
                              >
                                {linked.label}
                              </button>
                            )}
                          </p>
                        );
                      })}
                  </>
                ) : (
                  <p>Select an evidence node.</p>
                )}
              </div>
            </div>
            <details className="card">
              <summary>Canonical relationship table</summary>
              <div className="tablewrap">
                <table>
                  <thead>
                    <tr>
                      <th>From</th>
                      <th>Relationship</th>
                      <th>To</th>
                    </tr>
                  </thead>
                  <tbody>
                    {graph.edges.map((e, i) => (
                      <tr key={i}>
                        <td>{graph.nodes.find((n) => n.id === e.source)?.label}</td>
                        <td>{e.relation}</td>
                        <td>{graph.nodes.find((n) => n.id === e.target)?.label}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </>
        )}
        {review && (
          <Form className="card" onSubmit={grade}>
            <h2>Blind review · {review.title}</h2>
            <p>
              Execution origin: {review.execution_origin} · Trace coverage: {review.trace_coverage}
            </p>
            {review.evidence_limitations.map((limitation, i) => (
              <p key={i}>{limitation}</p>
            ))}
            <div className="split">
              <div>
                <h3>Candidate output</h3>
                <pre>{review.output}</pre>
              </div>
              <div>
                <h3>Assigned private reference</h3>
                {review.references.map((r, i) => (
                  <pre key={i}>{r}</pre>
                ))}
              </div>
            </div>
            {review.rubric.criteria.map((c) => (
              <fieldset key={c.id}>
                <legend>
                  {c.id} · {c.label}
                </legend>
                <label htmlFor={c.id}>Anchored score</label>
                <select id={c.id} name={c.id} required>
                  <option value="">Select judgment</option>
                  {Object.entries(c.anchors).map(([n, a]) => (
                    <option key={n} value={n}>
                      {n} — {a}
                    </option>
                  ))}
                </select>
                <label htmlFor={c.id + '-evidence'}>Verbatim output evidence</label>
                <input
                  id={c.id + '-evidence'}
                  name={c.id + '-evidence'}
                  minLength={3}
                  required
                  placeholder="Paste a supporting span from the output"
                />
              </fieldset>
            ))}
            <fieldset>
              <legend>Critical violations (independent of numeric score)</legend>
              {review.rubric.critical_rules.map((rule) => (
                <label key={rule}>
                  <input name="critical" type="checkbox" value={rule} />
                  {rule}
                </label>
              ))}
            </fieldset>
            <label htmlFor="rationale">Review rationale</label>
            <textarea name="rationale" id="rationale" minLength={10} required />
            {review.submitted_assessments && (
              <details>
                <summary>Submitted judgments for adjudication</summary>
                <pre>{text(review.submitted_assessments)}</pre>
              </details>
            )}
            {review.issues?.map((issue) => (
              <p className="banner" key={issue.id}>
                {issue.code.replaceAll('_', ' ')} · {issue.status}: {issue.rationale}
              </p>
            ))}
            <div className="actions">
              {review.issue_resolution_allowed &&
                (['invalid', 'resume_review'] as const).map((decision) => (
                  <button
                    key={decision}
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      const rationale = window.prompt(
                        'Independent issue-resolution rationale (at least 10 characters)',
                      );
                      if (rationale)
                        void act(async () => {
                          await api(
                            base + '/episodes/' + review.id + '/resolve-issue',
                            'POST',
                            { decision, rationale },
                            review.row_version,
                          );
                          setReview(null);
                        });
                    }}
                  >
                    {decision === 'invalid'
                      ? 'Mark evidence invalid, no candidate score'
                      : 'Return to independent review'}
                  </button>
                ))}
              {role('reviewer') && review.state !== 'review_blocked' && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    const rationale = window.prompt(
                      'Explain the reference ambiguity (at least 10 characters)',
                    );
                    if (rationale)
                      void act(async () => {
                        await api(
                          base + '/episodes/' + review.id + '/review-issues',
                          'POST',
                          { code: 'ambiguous_reference', rationale },
                          review.row_version,
                        );
                        setReview(null);
                      });
                  }}
                >
                  Flag ambiguous reference
                </button>
              )}
              <button className="primary" disabled={busy || review.state === 'review_blocked'}>
                {review.adjudication_allowed
                  ? 'Submit independent adjudication'
                  : 'Submit independent assessment'}
              </button>
              <button type="button" onClick={() => setReview(null)}>
                Close review
              </button>
            </div>
          </Form>
        )}
        {rows
          .filter((r) => pageInfo || JSON.stringify(r).toLowerCase().includes(search.toLowerCase()))
          .map((r) => (
            <article className="card" key={r.id}>
              <div className="toolbar">
                <h2>{text(r.content?.title || r.id)}</h2>
                <span className="badge">{r.lifecycle || r.state || 'pending'}</span>
              </div>
              {r.content && (
                <div>
                  {[
                    'hypothesis',
                    'measurement_plan',
                    'selection_method',
                    'exposure_note',
                    'comparison_policy',
                    'pass_policy',
                    'observation',
                  ].map((k) =>
                    r.content[k] ? (
                      <p key={k}>
                        <strong>{k.replaceAll('_', ' ')}: </strong>
                        {text(r.content[k])}
                      </p>
                    ) : null,
                  )}
                  {r.kind === 'case' && (
                    <>
                      <CaseReadiness
                        key={r.current_revision_id}
                        base={base}
                        id={r.id}
                        members={members}
                      />
                      <p>
                        {text(r.content.external_case_id)} · {text(r.content.family_id)} · source
                        version {text(r.content.source_version)}
                      </p>
                      <p className="muted">{text(r.content.rights_note)}</p>
                    </>
                  )}
                  {r.kind === 'rubric' && (
                    <div className="tablewrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Criterion</th>
                            <th>Weight</th>
                            <th>Anchors</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(
                            r.content.criteria as {
                              id: string;
                              label: string;
                              weight_bps: number;
                              anchors: Record<string, string>;
                            }[]
                          )?.map((c) => (
                            <tr key={c.id}>
                              <td>
                                {c.id} · {c.label}
                              </td>
                              <td>{c.weight_bps / 100}%</td>
                              <td>
                                {Object.entries(c.anchors).map(([n, a]) => (
                                  <div key={n}>
                                    {n}: {a}
                                  </div>
                                ))}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
              {section === 'runs' && (
                <>
                  {r.dataset_snapshot && (
                    <p className="banner">
                      Imported dataset version {r.dataset_snapshot.version_number} ·{' '}
                      {r.dataset_snapshot.task_count} tasks · TaskSpec{' '}
                      {r.dataset_snapshot.task_schema_version} · {r.dataset_version_id}. Configured
                      only; task qualification and supported execution are pending. Source:{' '}
                      {r.dataset_snapshot.source_provenance?.classification ?? 'unclassified'} ·
                      owner: {r.dataset_snapshot.source_provenance?.source_owner ?? 'unknown'}.
                    </p>
                  )}
                  <p>
                    Origin: {r.origin} ·{' '}
                    {r.origin === 'illustrative'
                      ? 'Actual model cost: not applicable to network-free fixtures'
                      : r.origin === 'adi_executed'
                        ? 'Real model execution on original synthetic inputs. Review pending; billing is not independently verified.'
                        : 'External execution is reported, not independently reproduced. Cost is not verified by Anvil.'}
                  </p>
                  <p>
                    {r.episode_count ?? 0} episodes · {r.pending_execution ?? 0} pending execution ·{' '}
                    {r.pending_reviews ?? 0} awaiting review · {r.finalized_reviews ?? 0} finalized
                    reviews
                  </p>
                  {!!r.pending_execution && (
                    <p className="muted">Execution status refreshes every two seconds.</p>
                  )}
                  {r.origin === 'adi_executed' && (
                    <MarketingRun
                      base={base}
                      id={r.id}
                      version={r.row_version}
                      state={r.state}
                      admin={role('admin')}
                      researcher={role('researcher')}
                      refresh={reload}
                    />
                  )}
                  <div className="actions">
                    {r.state === 'draft' &&
                      !r.dataset_version_id &&
                      r.origin === 'illustrative' &&
                      role('researcher') && (
                        <button
                          className="primary"
                          disabled={busy}
                          onClick={() => void change(r, 'launch')}
                        >
                          Launch fixture evaluation
                        </button>
                      )}
                    {r.state !== 'reviewed' && r.state !== 'cancelled' && role('researcher') && (
                      <button onClick={() => void change(r, 'cancel')}>
                        Cancel pending execution
                      </button>
                    )}
                  </div>
                  {r.state === 'draft' &&
                    !r.dataset_version_id &&
                    (r.origin === 'customer_reported' || r.origin === 'partner_reported') &&
                    role('data-engineer') && <ExternalResults base={base} runId={r.id} />}
                  {r.episodes && (
                    <div className="tablewrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Episode</th>
                            <th>State</th>
                            <th>Outcome</th>
                            <th>Score</th>
                            <th>Invocations</th>
                          </tr>
                        </thead>
                        <tbody>
                          {r.episodes.map((e) => (
                            <tr key={e.id}>
                              <td>{e.id.slice(0, 8)}</td>
                              <td>{e.state}</td>
                              <td>{e.outcome}</td>
                              <td>{e.score ?? 'Not established'}</td>
                              <td>{e.invocation_count}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
              {section === 'reviews' && (
                <div className="actions">
                  <button
                    className="primary"
                    disabled={busy || r.my_review_submitted}
                    onClick={() =>
                      act(
                        async () => setReview(await api(base + '/reviews/' + r.id)),
                        'Assigned evidence loaded; other unfinished grades are withheld. Source material may identify the candidate.',
                      )
                    }
                  >
                    {r.my_review_submitted ? 'Your judgment is recorded' : 'Open blinded review'}
                  </button>
                </div>
              )}
              {r.kind === 'report' && <ReportSummary content={r.content} />}
              {r.kind === 'report' && r.lifecycle === 'approved' && (
                <>
                  <button
                    className="primary"
                    disabled={busy}
                    onClick={() => void change(r, 'build')}
                  >
                    Build reviewed PDF &amp; evidence kit
                  </button>
                  <div className="actions">
                    {[
                      'sales-kit.pdf',
                      'sales-kit.html',
                      'evidence.zip',
                      'email-draft.txt',
                      'internal-brief.txt',
                    ].map((name) => (
                      <a
                        className="button"
                        key={name}
                        href={'/api/v1' + base + '/reports/' + r.id + '/download/' + name}
                      >
                        {name}
                      </a>
                    ))}
                  </div>
                </>
              )}
              {section === 'sales-kits' && (
                <>
                  <p className="banner">{text(r.content.label)}</p>
                  <p>{text(r.content.tested)}</p>
                  <p>{text(r.content.boundary)}</p>
                  <div className="actions">
                    <button disabled>Email sending disabled</button>
                  </div>
                  {r.lifecycle === 'approved' && role('researcher', 'product-owner', 'sales') && (
                    <div className="actions">
                      {[
                        ['sales-kit.pdf', 'Download PDF'],
                        ['sales-kit.html', 'Download HTML'],
                        ['evidence.zip', 'Download evidence ZIP'],
                        ['email-draft.txt', 'Download email draft'],
                        ['internal-brief.txt', 'Download internal brief'],
                      ].map(([name, label]) => (
                        <a
                          className="button"
                          key={name}
                          href={'/api/v1' + base + '/sales-kits/' + r.id + '/download/' + name}
                        >
                          {label}
                        </a>
                      ))}
                    </div>
                  )}
                </>
              )}
              {section === 'providers' && role('admin') && (
                <ProviderSetup
                  base={base}
                  provider={String(r.content.provider_key)}
                  model={r.content.model_id as string | null}
                />
              )}
              <div className="actions">
                {r.created_by === user.id &&
                  role('researcher', 'data-engineer') &&
                  [
                    'objective',
                    'rubric',
                    'task',
                    'suite',
                    'protocol',
                    'finding',
                    'report',
                  ].includes(r.kind) && (
                    <button
                      disabled={busy}
                      onClick={() => {
                        setForm(false);
                        setEditing(r);
                      }}
                    >
                      {['draft', 'changes_requested'].includes(r.lifecycle)
                        ? 'Edit draft'
                        : 'Create successor'}
                    </button>
                  )}
                {r.lifecycle === 'draft' &&
                  role('researcher', 'data-engineer') &&
                  [
                    'objective',
                    'rubric',
                    'task',
                    'suite',
                    'protocol',
                    'finding',
                    'report',
                  ].includes(r.kind) && (
                    <button disabled={busy} onClick={() => void change(r, 'submit')}>
                      Submit for review
                    </button>
                  )}
                {r.lifecycle === 'submitted' && r.content && (
                  <>
                    {role('researcher') &&
                      r.kind === 'objective' &&
                      r.content.researcher_id === user.id && (
                        <button onClick={() => decision(r, 'research')}>
                          Recommend research scope
                        </button>
                      )}
                    {role('advisor') && r.content.advisor_id === user.id && (
                      <button
                        onClick={() =>
                          decision(
                            r,
                            r.kind === 'objective'
                              ? 'advisor'
                              : r.kind === 'rubric'
                                ? 'calibration'
                                : r.kind === 'task'
                                  ? 'research'
                                  : 'technical',
                          )
                        }
                      >
                        Approve {r.kind === 'rubric' ? 'calibration' : 'technical review'}
                      </button>
                    )}
                    {role('reviewer') && r.content.reviewer_id === user.id && (
                      <button
                        onClick={() => decision(r, r.kind === 'report' ? 'domain' : 'content')}
                      >
                        Approve domain content
                      </button>
                    )}
                    {role('product-owner') && r.content.product_owner_id === user.id && (
                      <button
                        onClick={() => decision(r, r.kind === 'objective' ? 'scope' : 'audience')}
                      >
                        Approve {r.kind === 'objective' ? 'scope' : 'audience'}
                      </button>
                    )}
                    {role('product-owner') && r.kind === 'report' && (
                      <button onClick={() => decision(r, 'release')}>
                        Approve internal release
                      </button>
                    )}
                  </>
                )}
                {r.kind === 'case' && role('product-owner') && (
                  <RightsReview base={base} id={r.id} version={r.row_version} />
                )}
                {r.kind === 'objective' &&
                  r.lifecycle === 'approved' &&
                  role('researcher', 'data-engineer') && (
                    <button onClick={() => setImportObjective(r)}>Import tasks</button>
                  )}
                {r.kind === 'task' && r.lifecycle === 'qualified' && role('data-engineer') && (
                  <button onClick={() => void change(r, 'publish')}>Publish qualified task</button>
                )}
                {r.kind === 'suite' && r.lifecycle === 'approved' && role('researcher') && (
                  <button onClick={() => void change(r, 'freeze')}>Freeze suite</button>
                )}
                {r.kind === 'protocol' &&
                  r.lifecycle === 'approved' &&
                  r.content.mode !== 'external_result_import_v1' &&
                  role('researcher') && (
                    <button
                      className="primary"
                      onClick={() =>
                        act(
                          () =>
                            api(base + '/runs', 'POST', {
                              protocol_revision_id: r.current_revision_id,
                            }),
                          'Run created. Open Run console to explicitly launch.',
                        )
                      }
                    >
                      {r.content.mode === 'marketing_interactive_v1'
                        ? 'Prepare marketing run'
                        : 'Prepare fixture run'}
                    </button>
                  )}
                {r.kind === 'protocol' &&
                  r.lifecycle === 'approved' &&
                  r.content.mode === 'external_result_import_v1' &&
                  role('researcher') &&
                  ['customer_reported', 'partner_reported'].map((origin) => (
                    <button
                      key={origin}
                      onClick={() =>
                        act(
                          () =>
                            api(base + '/runs', 'POST', {
                              protocol_revision_id: r.current_revision_id,
                              external_origin: origin,
                            }),
                          'Reported run prepared. A Data Engineer can validate and commit its manifest in Run console.',
                        )
                      }
                    >
                      Prepare {origin.replace('_', '-')} run
                    </button>
                  ))}
                {!['reviews', 'providers', 'sales-kits'].includes(section) && (
                  <button
                    onClick={() =>
                      act(
                        async () => {
                          const full = await api(base + '/' + section + '/' + r.id);
                          setRows((old) => old.map((x) => (x.id === r.id ? full : x)));
                        },
                        'Current evidence and history loaded.',
                        false,
                      )
                    }
                  >
                    {section === 'runs' ? 'Inspect episodes' : 'Load review history'}
                  </button>
                )}
              </div>
              {r.reviews?.map((v, i) => (
                <p key={i} className="muted">
                  {v.purpose}: {v.decision} — {v.rationale}
                </p>
              ))}
              <details>
                <summary>Version and evidence details</summary>
                <p className="muted">
                  Revision {r.current_revision_id} · hash {r.content_hash}
                </p>
                <pre>{text(r.content)}</pre>
              </details>
            </article>
          ))}
        {pageInfo && (
          <div className="actions">
            <p>
              {rows.length} of {pageInfo.matching_total} matching records loaded
            </p>
            {pageInfo.next_cursor && (
              <button
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    const page = await api(
                      base +
                        '/' +
                        section +
                        '?q=' +
                        encodeURIComponent(query) +
                        '&after=' +
                        pageInfo.next_cursor,
                      'GET',
                      undefined,
                      undefined,
                      true,
                    );
                    setRows((prior) => [...prior, ...page.data]);
                    setPageInfo(page.meta);
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Load more records
              </button>
            )}
          </div>
        )}
        {!rows.length &&
          !error &&
          !['diagnostics', 'factory', 'evaluations', 'harbor'].includes(section) && (
            <div className="card empty">
              {query
                ? 'No records match this search.'
                : 'No records in this view yet. Start with an objective and the original synthetic cases.'}
            </div>
          )}
        <footer>
          ADI Anvil · Local diagnostic workspace · External inference and sending require separate
          authorization.
        </footer>
      </main>
    </div>
  );
}
