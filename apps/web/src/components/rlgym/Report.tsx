'use client';

import Link from 'next/link';
import { EdgeCaseForm, edgeBody, edgeReady, emptyEdge, type EdgeParts } from './EdgeCase';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { GymApiError, send, wsBase } from './api';
import { PolicyMapSummary } from './PolicyMap';
import { Badge, Failure, Hash, Loading, useData, useGym } from './ui';
import { HowScored, ScoredBy } from './Scoring';

// The run report (SCREENS 3.22-3.36): five views, drill-downs and the PDF preview. Every view comes from the same
// report view the PDF prints, identified by view_sha256.

type Model = { system_id: string; name: string; version: number };
const VIEWS: [string, string][] = [
  ['overview', 'Overview'],
  ['tasks', 'Task results'],
  ['agent', 'Agent performance'],
  ['failures', 'Failures & evidence'],
  ['ts', 'Trust & Safety'],
];
const COLORS = ['var(--green)', '#3a7bd5', '#c77d16', '#7a3fbf', '#b3261e'];

function pct(v?: number | null) {
  return v === null || v === undefined ? '—' : `${Math.round(v * 100)}%`;
}
function num(v?: number | null) {
  return v === null || v === undefined ? '—' : String(v);
}

export default function Report({ id, rest }: { id: string; rest: string[] }) {
  if (rest[0] === 'pdf') return <PdfPreview id={id} />;
  if (rest[0] === 'drill')
    return <Drill id={id} kind={rest[1]} keyName={decodeURIComponent(rest[2] ?? '')} />;
  return <ReportView id={id} view={rest[0] ?? 'overview'} />;
}

function Frame({
  id,
  header,
  view,
  children,
}: {
  id: string;
  header: any;
  view?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="report">
      <div className="between">
        <p>
          {header.cohort} · manifest <Hash value={header.manifest_sha256} />{' '}
          {header.scoring && <small>{header.scoring}</small>}
          {header.agent_view && <small>{header.agent_view.note}</small>}
          {header.agent_view?.known_leaks?.length > 0 && (
            <small className="no">
              Known data leaks on {header.environment}: {header.agent_view.known_leaks.join('; ')}.
            </small>
          )}
          {header.rescored && (
            <Badge state="draft" label={`Re-scored · pass ${header.pass.number}`} />
          )}
        </p>
        {header.ready && (
          <Link className="primary" href={`/gym/runs/${id}/report/pdf`}>
            Export PDF
          </Link>
        )}
      </div>
      {view && (
        <nav className="tabs" aria-label="Report views">
          {VIEWS.map(([key, label]) => (
            <Link
              key={key}
              href={`/gym/runs/${id}/report/${key}`}
              aria-current={key === view ? 'page' : undefined}
            >
              {label}
            </Link>
          ))}
        </nav>
      )}
      {children}
      <small>{header.footer}</small>
    </section>
  );
}

function ReportView({ id, view }: { id: string; view: string }) {
  const { ws } = useGym();
  const data = useData<any>(`${wsBase(ws)}/runs/${id}/report?tab=${view}`);
  return (
    <Loading data={data.data} error={data.error}>
      {() =>
        !data.data.ready ? (
          <div className="banner" role="status">
            {data.data.message}
          </div>
        ) : (
          <Frame id={id} header={data.data.header} view={view}>
            {view === 'overview' && (
              <OverviewView id={id} v={data.data.view} models={data.data.header.models} />
            )}
            {view === 'tasks' && (
              <TasksView id={id} v={data.data.view} models={data.data.header.models} />
            )}
            {view === 'agent' && (
              <AgentView id={id} v={data.data.view} models={data.data.header.models} />
            )}
            {view === 'failures' && (
              <FailuresView id={id} v={data.data.view} models={data.data.header.models} />
            )}
            {view === 'ts' && (
              <TsView id={id} v={data.data.view} models={data.data.header.models} />
            )}
            <small>
              View <Hash value={data.data.view_sha256} />
              {data.data.renders?.[0] && ` · last PDF rep-${id}-r${data.data.renders[0].revision}`}
            </small>
          </Frame>
        )
      }
    </Loading>
  );
}

export function ScoreCards({ cards }: { cards: any[] }) {
  return (
    <div className="grid3">
      {cards.map((c) => (
        <section className="card" key={c.system_id}>
          <div className="between">
            <h4>
              {c.name} v{c.version}
            </h4>
            {c.gate && <Badge state={c.gate === 'PASSED' ? 'ready' : 'failed'} label={c.gate} />}
          </div>
          <p className="big">
            {num(c.mean)}
            <small> /100</small>
          </p>
          <small>
            automated · likely range{' '}
            {c.likely_range ? `${c.likely_range[0]}–${c.likely_range[1]}` : '—'} · {c.scored} scored
            · passed {pct(c.pass_rate)}
          </small>
          {c.gate_notes.length > 0 && <small className="error">{c.gate_notes.join('; ')}</small>}
        </section>
      ))}
    </div>
  );
}

function Bars({
  perModel,
  models,
  scale = 100,
  format = num,
}: {
  perModel: any;
  models: Model[];
  scale?: number;
  format?: (v: any) => string;
}) {
  return (
    <div className="bars">
      {models.map((m, i) => {
        const v = perModel?.[m.system_id];
        const width =
          v === null || v === undefined ? 0 : Math.max(0, Math.min(100, (100 * v) / scale));
        return (
          <div className="barrow" key={m.system_id}>
            <span>{m.name}</span>
            <div className="track">
              <div style={{ width: `${width}%`, background: COLORS[i % COLORS.length] }} />
            </div>
            <span>{format(v)}</span>
          </div>
        );
      })}
    </div>
  );
}

export function Radar({
  axes,
  models,
  size = 260,
}: {
  axes: { capability: string; per_model: any }[];
  models: Model[];
  size?: number;
}) {
  const n = axes.length;
  if (n < 3) return null;
  const c = size / 2;
  const r = c - 46;
  const pt = (i: number, v: number) => [
    c + ((r * v) / 100) * Math.sin((2 * Math.PI * i) / n),
    c - ((r * v) / 100) * Math.cos((2 * Math.PI * i) / n),
  ];
  const poly = (vals: number[]) =>
    vals
      .map((v, i) =>
        pt(i, v)
          .map((x) => x.toFixed(1))
          .join(','),
      )
      .join(' ');
  return (
    <figure>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label="Capability profile"
      >
        {[25, 50, 75, 100].map((ring) => (
          <polygon
            key={ring}
            points={poly(axes.map(() => ring))}
            fill="none"
            stroke="var(--line)"
          />
        ))}
        {axes.map((a, i) => {
          const [x, y] = pt(i, 120);
          return (
            <text
              key={a.capability}
              x={x}
              y={y}
              fontSize="9"
              textAnchor="middle"
              fill="var(--muted)"
            >
              {a.capability}
            </text>
          );
        })}
        {models.map((m, j) => (
          <polygon
            key={m.system_id}
            points={poly(axes.map((a) => a.per_model?.[m.system_id] ?? 0))}
            fill={COLORS[j % COLORS.length]}
            fillOpacity={0.12}
            stroke={COLORS[j % COLORS.length]}
          />
        ))}
      </svg>
      <figcaption>
        {models.map((m, j) => (
          <small key={m.system_id} style={{ color: COLORS[j % COLORS.length], marginInlineEnd: 8 }}>
            ■ {m.name}
          </small>
        ))}
      </figcaption>
    </figure>
  );
}

function ModelTable({ head, rows }: { head: React.ReactNode[]; rows: React.ReactNode[][] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {head.map((h, i) => (
              <th key={i}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((cell, j) => (
                <td key={j} style={j === 0 ? { textAlign: 'left' } : undefined}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const drill = (id: string, kind: string, key = '') =>
  `/gym/runs/${id}/report/drill/${kind}${key ? `/${encodeURIComponent(key)}` : ''}`;

function OverviewView({ id, v, models }: { id: string; v: any; models: Model[] }) {
  return (
    <>
      <ScoreCards cards={v.cards} />
      {v.observations?.warning && (
        <p className="badge warn" role="status">
          {v.observations.warning}
        </p>
      )}
      <section className="card">
        <div className="between">
          <h3>SME review sample</h3>
          <Link href={`/gym/runs/${id}/sme`}>Open SME review in the run</Link>
        </div>
        <p>{v.review_sample.state}</p>
      </section>
      <PolicyMapSummary summary={v.policy_maps} />
      <div className="row">
        <Link href={drill(id, 'policy')}>Policy findings & document evidence</Link>
        <Link href={drill(id, 'risk')}>Risk & escalation summary</Link>
        <Link href={`/gym/runs/${id}/report/ts`}>Trust & Safety results</Link>
        <Link href={drill(id, 'axes')}>Inspect axes, weights and coverage</Link>
      </div>
      <div className="grid2">
        <section className="card">
          <h3>Capability profile</h3>
          <Radar axes={v.capability_profile} models={models} />
        </section>
        <section className="card">
          <h3>Scores by task</h3>
          <ModelTable
            head={['Task', ...models.map((m) => m.name)]}
            rows={v.scores_by_task.map((t: any) => [
              <span key="t">
                <Link href={drill(id, 'task', t.task_id)}>
                  {t.task_id} r{t.revision}
                </Link>
                <small>{t.label}</small>
              </span>,
              ...models.map((m) => num(t.per_model[m.system_id])),
            ])}
          />
        </section>
      </div>
    </>
  );
}

function TasksView({ id, v, models }: { id: string; v: any; models: Model[] }) {
  const [sort, setSort] = useState('failed');
  const [page, setPage] = useState(1);
  const criteria = [...v.criteria].sort((a: any, b: any) =>
    sort === 'id'
      ? a.criterion_id.localeCompare(b.criterion_id)
      : Math.min(...models.map((m) => a.per_model[m.system_id] ?? 1)) -
        Math.min(...models.map((m) => b.per_model[m.system_id] ?? 1)),
  );
  const pages = Math.max(1, Math.ceil(criteria.length / 10));
  return (
    <>
      <h3>Tasks</h3>
      <ModelTable
        head={['Task', ...models.map((m) => `${m.name} (mean · failed cases)`)]}
        rows={v.tasks.map((t: any) => [
          <span key="t">
            <Link href={drill(id, 'task', t.task_id)}>
              {t.task_id} r{t.revision}
            </Link>
            <small>{t.label}</small>
          </span>,
          ...models.map(
            (m) =>
              `${num(t.per_model[m.system_id]?.mean)} · ${t.per_model[m.system_id]?.failed_cases ?? 0}`,
          ),
        ])}
      />
      {(v.slices ?? []).length > 0 && (
        <>
          <h3>Results by complexity and archetype</h3>
          <small>Slice tags from the authored tasks (the template's S1 lists).</small>
          <ModelTable
            head={['Slice', 'Episodes', ...models.map((m) => `${m.name} passed · failed`)]}
            rows={v.slices.map((s: any) => [
              <span key="s">
                {s.dimension} · <code>{s.value}</code>
              </span>,
              s.episodes,
              ...models.map(
                (m) =>
                  `${pct(s.per_model[m.system_id]?.pass_rate)} · ${s.per_model[m.system_id]?.failed ?? 0}`,
              ),
            ])}
          />
        </>
      )}
      <h3>Results by stratum</h3>
      <ModelTable
        head={['Stratum', 'Episodes', ...models.map((m) => `${m.name} passed`)]}
        rows={v.strata.map((s: any) => [
          <span key="s">
            {s.dimension} · {s.value}
            {s.small_sample && <small>small sample</small>}
          </span>,
          s.episodes,
          ...models.map((m) => pct(s.per_model[m.system_id])),
        ])}
      />
      <div className="between">
        <h3>Per criterion</h3>
        <label>
          Sort{' '}
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="failed">Failed most first</option>
            <option value="id">Criterion ID</option>
          </select>
        </label>
      </div>
      <ModelTable
        head={[
          'Criterion',
          'Capability',
          ...models.map((m) => m.name),
          'Blocked',
          'Evaluator',
          'Scored by',
        ]}
        rows={criteria.slice((page - 1) * 10, page * 10).map((c: any) => [
          c.criterion_id,
          <Link key="c" href={drill(id, 'capability', c.capability)}>
            {c.capability}
          </Link>,
          ...models.map((m) => pct(c.per_model[m.system_id])),
          c.blocked,
          c.evaluator,
          <span key="s" style={{ textAlign: 'left' }}>
            <ScoredBy s={c.scoring} />
            <HowScored s={c.scoring} />
          </span>,
        ])}
      />
      <div className="row">
        <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
          Previous
        </button>
        <small>
          page {page} of {pages}
        </small>
        <button disabled={page >= pages} onClick={() => setPage(page + 1)}>
          Next
        </button>
      </div>
    </>
  );
}

function AgentView({ id, v, models }: { id: string; v: any; models: Model[] }) {
  return (
    <>
      <ScoreCards cards={v.cards} />
      <div className="grid2">
        <section className="card">
          <div className="between">
            <h3>Capability comparison</h3>
            <Link href={drill(id, 'axes')}>Inspect axes, weights and coverage</Link>
          </div>
          {v.capabilities.map((a: any) => (
            <div key={a.capability}>
              <Link href={drill(id, 'capability', a.capability)}>{a.capability}</Link>
              <Bars perModel={a.per_model} models={models} />
            </div>
          ))}
        </section>
        <section className="card">
          <h3>Capability profile</h3>
          <Radar axes={v.capabilities} models={models} />
        </section>
      </div>
      {v.case ? (
        <section className="card">
          <div className="between">
            <h3>Same case · {v.case.case_id}</h3>
            <small>
              Cases where the models disagree:{' '}
              {v.disagreement_cases.slice(0, 8).map((c: string) => (
                <Link key={c} href={drill(id, 'case', c)} style={{ marginInlineEnd: 6 }}>
                  {c}
                </Link>
              ))}
            </small>
          </div>
          <CaseBody id={id} c={v.case} models={models} />
        </section>
      ) : (
        <p>No case where the models disagree.</p>
      )}
    </>
  );
}

function Heat({ value }: { value?: number | null }) {
  const s =
    value === null || value === undefined
      ? 'none'
      : value >= 80
        ? 'meets'
        : value >= 50
          ? 'partial'
          : 'fails';
  return (
    <span className="heat" data-s={s}>
      {value === null || value === undefined ? 'unscored' : value}
    </span>
  );
}

function CaseBody({ id, c, models }: { id: string; c: any; models: Model[] }) {
  return (
    <>
      <p>
        {c.task.task_id} r{c.task.revision} · {c.dimensions.application_type} ·{' '}
        {c.dimensions.completeness}
        {c.dimensions.edge_cases.length ? ` · ${c.dimensions.edge_cases.join(', ')}` : ''}
      </p>
      {c.required && (
        <p>
          <strong>Required:</strong> {c.required.decision} → {c.required.next_action}
          {c.required.exceptions?.length
            ? ` · exceptions ${c.required.exceptions.join(', ')}`
            : ''}{' '}
          · {c.required.party_count} parties <small>{c.required_note}</small>
        </p>
      )}
      <h4>Skill comparison</h4>
      <ModelTable
        head={['Capability', ...models.map((m) => m.name)]}
        rows={c.heatmap.map((h: any) => [
          h.capability,
          ...models.map((m) => <Heat key={m.system_id} value={h.per_model[m.system_id]} />),
        ])}
      />
      <small>≥80 meets · 50–79 partial · &lt;50 fails · unscored is shown separately.</small>
      <h4>Same-case outcome and evidence</h4>
      {c.per_model.map((pm: any) =>
        pm.episodes.map((e: any) => (
          <div className="card" key={e.episode_id}>
            <div className="between">
              <strong>
                {pm.name} · attempt {e.attempt}
              </strong>
              <Badge
                state={e.verdict === 'passed' ? 'ready' : 'failed'}
                label={e.verdict ?? e.state}
              />
            </div>
            <div className="strip">
              {e.workflow.map((w: any) => (
                <span key={w.id} data-s={w.state} title={w.state}>
                  {w.label}
                </span>
              ))}
            </div>
            <small>
              Outcome {e.outcome} · score {num(e.score)} · likely cause {e.likely_cause ?? '—'}
              {e.failed_criteria.length ? ` · failed ${e.failed_criteria.join(', ')}` : ''}
            </small>
            <div className="row">
              <Link href={`/gym/runs/${id}/episodes/${e.episode_id}?from=report`}>
                Evidence {e.episode_id}
              </Link>
              {e.verdict === 'failed' && (
                <Link href={drill(id, 'review', e.episode_id)}>Diagnose</Link>
              )}
              {e.diagnostic && <small>Diagnosis: {e.diagnostic}</small>}
            </div>
          </div>
        )),
      )}
    </>
  );
}

function FailuresView({ id, v, models }: { id: string; v: any; models: Model[] }) {
  const [model, setModel] = useState('');
  const [cause, setCause] = useState('');
  const [complexity, setComplexity] = useState('');
  const [archetype, setArchetype] = useState('');
  const [page, setPage] = useState(1);
  const rows = v.episodes.filter(
    (e: any) =>
      (!model || e.system_id === model) &&
      (!cause || (e.likely_cause ?? '') === cause) &&
      (!complexity || e.complexity === complexity) &&
      (!archetype || e.archetype === archetype),
  );
  const pages = Math.max(1, Math.ceil(rows.length / 20));
  return (
    <>
      <div className="grid3">
        {v.per_model.map((p: any) => (
          <section className="card" key={p.system_id}>
            <h4>{p.name}</h4>
            <p>
              Failed episodes {p.failed} of {p.scored} scored
            </p>
            <small>
              errored {p.errored} · timed out {p.timed_out}
            </small>
          </section>
        ))}
      </div>
      {(v.by_on_fail ?? []).length > 0 && (
        <>
          <h3>Failed verifier blocks by code</h3>
          <small>
            One count per failed block (State, Process or Rubric), grouped by its on_fail code.
          </small>
          <ModelTable
            head={['Code', ...models.map((m) => m.name), 'Blocks', 'Example: expected → actual']}
            rows={v.by_on_fail.map((r: any) => [
              <code key="c">{r.code}</code>,
              ...models.map((m) => r.per_model[m.system_id] ?? 0),
              Object.entries(r.blocks)
                .map(([b, n]) => `${b} (${n})`)
                .join(', '),
              <span key="x">
                <Link href={`/gym/runs/${id}/episodes/${r.example.episode_id}?from=report`}>
                  {r.example.case_id} · {r.example.block_id}
                </Link>
                <small>
                  {JSON.stringify(r.example.expected)} → {JSON.stringify(r.example.actual)}
                </small>
              </span>,
            ])}
          />
        </>
      )}
      {(v.slices ?? []).length > 0 && (
        <>
          <h3>Failures by complexity and archetype</h3>
          <ModelTable
            head={['Slice', ...models.map((m) => `${m.name} failed`)]}
            rows={v.slices.map((s: any) => [
              <span key="s">
                {s.dimension} · <code>{s.value}</code>
              </span>,
              ...models.map((m) => s.per_model[m.system_id]?.failed ?? 0),
            ])}
          />
        </>
      )}
      <h3>Failures by likely cause</h3>
      <small>{v.cause_note}</small>
      <ModelTable
        head={['Likely cause', ...models.map((m) => m.name), 'Example']}
        rows={v.by_cause.map((r: any) => [
          r.cause,
          ...models.map((m) => r.per_model[m.system_id] ?? 0),
          <Link key="x" href={drill(id, 'case', r.example_case)}>
            {r.example_case}
          </Link>,
        ])}
      />
      <div className="toolbar">
        <label>
          Model{' '}
          <select value={model} onChange={(e) => (setModel(e.target.value), setPage(1))}>
            <option value="">All</option>
            {models.map((m) => (
              <option key={m.system_id} value={m.system_id}>
                {m.name}
              </option>
            ))}
          </select>
        </label>
        {(['complexity', 'archetype'] as const).map((dim) => {
          const values = Array.from(
            new Set((v.episodes as any[]).map((e) => e[dim]).filter(Boolean)),
          ) as string[];
          if (!values.length) return null;
          const [value, setValue] =
            dim === 'complexity' ? [complexity, setComplexity] : [archetype, setArchetype];
          return (
            <label key={dim}>
              {dim === 'complexity' ? 'Complexity' : 'Archetype'}{' '}
              <select value={value} onChange={(e) => (setValue(e.target.value), setPage(1))}>
                <option value="">All</option>
                {values.map((x) => (
                  <option key={x} value={x}>
                    {x}
                  </option>
                ))}
              </select>
            </label>
          );
        })}
        <label>
          Cause{' '}
          <select value={cause} onChange={(e) => (setCause(e.target.value), setPage(1))}>
            <option value="">All</option>
            {v.by_cause.map((r: any) => (
              <option key={r.cause} value={r.cause}>
                {r.cause}
              </option>
            ))}
          </select>
        </label>
      </div>
      <ModelTable
        head={['Episode', 'Model', 'Score', 'Likely cause', 'Failed criteria', 'SME', '']}
        rows={rows.slice((page - 1) * 20, page * 20).map((e: any) => [
          <span key="e">
            <Link href={`/gym/runs/${id}/episodes/${e.episode_id}?from=report`}>
              {e.task_id} · {e.case_id} · a{e.attempt}
            </Link>
            <small>
              <Link href={drill(id, 'case', e.case_id)}>compare models on this case</Link>
            </small>
          </span>,
          e.model,
          e.score ?? e.state,
          e.likely_cause ?? '—',
          e.failed_criteria.join(', '),
          e.sme,
          <Link key="d" href={drill(id, 'review', e.episode_id)}>
            {e.diagnosis ?? 'Diagnose'}
          </Link>,
        ])}
      />
      <div className="row">
        <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
          Previous
        </button>
        <small>
          {rows.length} failed episodes · page {page} of {pages}
        </small>
        <button disabled={page >= pages} onClick={() => setPage(page + 1)}>
          Next
        </button>
      </div>
      <section className="card">
        <h3>SME review sample</h3>
        <p>{v.review_sample.state}</p>
      </section>
    </>
  );
}

function TsView({ id, v, models }: { id: string; v: any; models: Model[] }) {
  if (!v.enabled) return <p>{v.message}</p>;
  return (
    <>
      <div className="banner" role="note">
        {v.note}
      </div>
      <div className="grid3">
        {v.cards.map((c: any) => (
          <section className="card" key={c.system_id}>
            <div className="between">
              <h4>{c.name}</h4>
              {c.gate && <Badge state={c.gate === 'PASSED' ? 'ready' : 'failed'} label={c.gate} />}
            </div>
            <p>
              Attacks the model acted on {c.acted_on} of {c.attacks}
            </p>
            <small>
              {c.blocked} blocked by the environment · {c.critical} critical incidents ·{' '}
              {c.resisted} resisted
              {c.unscored ? ` · ${c.unscored} unscored` : ''}
            </small>
            <div className="stack" aria-label="Outcome of the attacks">
              <span
                data-s="scored"
                style={{ width: `${(100 * c.resisted) / (c.attacks || 1)}%` }}
              />
              <span data-s="queued" style={{ width: `${(100 * c.blocked) / (c.attacks || 1)}%` }} />
              <span
                data-s="errored"
                style={{ width: `${(100 * c.not_blocked) / (c.attacks || 1)}%` }}
              />
            </div>
          </section>
        ))}
      </div>
      <h3>Critical incidents</h3>
      {v.critical_incidents.length === 0 ? (
        <p>None.</p>
      ) : (
        <ModelTable
          head={['Episode', 'Model', 'Category', 'What happened']}
          rows={v.critical_incidents.map((i: any) => [
            <Link key="e" href={`/gym/runs/${id}/episodes/${i.episode_id}?from=report`}>
              {i.episode_id}
            </Link>,
            i.model,
            <Link key="c" href={drill(id, 'tscat', i.category_key)}>
              {i.category}
            </Link>,
            i.what_happened,
          ])}
        />
      )}
      <div className="grid2">
        <section className="card">
          <h3>Resistance by category</h3>
          {v.by_category.map((c: any) => (
            <div key={c.key}>
              <Link href={drill(id, 'tscat', c.key)}>{c.name}</Link>
              <Bars perModel={c.resistance} models={models} scale={1} format={pct} />
            </div>
          ))}
        </section>
        <section className="card">
          <h3>Safety profile</h3>
          <Radar
            axes={v.by_category.map((c: any) => ({
              capability: c.name,
              per_model: Object.fromEntries(
                Object.entries(c.resistance).map(([k, x]: any) => [k, (x ?? 0) * 100]),
              ),
            }))}
            models={models}
          />
          <small>100 = resisted every attempt.</small>
        </section>
      </div>
      <h3>Refusal rate by attack style</h3>
      <ModelTable
        head={['Strategy', ...models.map((m) => m.name)]}
        rows={v.by_style.map((s: any) => [
          s.strategy,
          ...models.map((m) => pct(s.refusal_rate[m.system_id])),
        ])}
      />
      <h3>By category</h3>
      <ModelTable
        head={['Category', ...models.map((m) => m.name)]}
        rows={v.by_category.map((c: any) => [
          <span key="c">
            <Link href={drill(id, 'tscat', c.key)}>{c.name}</Link>
            <small>{c.boundary}</small>
          </span>,
          ...models.map((m) => {
            const x = c.per_model[m.system_id] ?? {};
            return `${(x.acted_blocked ?? 0) + (x.acted_not_blocked ?? 0)} of ${x.attempts ?? 0} · ${x.acted_blocked ?? 0} blocked · ${x.acted_not_blocked ?? 0} not blocked`;
          }),
        ])}
      />
    </>
  );
}

function Drill({ id, kind, keyName }: { id: string; kind: string; keyName: string }) {
  const { ws } = useGym();
  const data = useData<any>(
    `${wsBase(ws)}/runs/${id}/report/drill?kind=${kind}&key=${encodeURIComponent(keyName)}`,
  );
  const titles: Record<string, string> = {
    capability: `Capability · ${keyName}`,
    axes: 'Axes, weights and coverage',
    task: `Task · ${keyName}`,
    case: `Case · ${keyName}`,
    review: 'Review item',
    tscat: 'Trust & Safety category',
    policy: 'Policy findings and document evidence',
    risk: 'Risk and escalation summary',
  };
  return (
    <Loading data={data.data} error={data.error}>
      {() => {
        const d = data.data.drill;
        const models: Model[] = data.data.header.models;
        return (
          <Frame id={id} header={data.data.header}>
            <nav className="crumbs">
              <Link href={`/gym/runs/${id}/report`}>Report</Link> › {titles[kind] ?? kind}
            </nav>
            {kind === 'capability' && (
              <ModelTable
                head={[
                  'Criterion',
                  'Weight',
                  ...models.map((m) => m.name),
                  'Coverage',
                  'Disagreement cases',
                ]}
                rows={d.criteria.map((c: any) => [
                  c.criterion_id,
                  c.weight,
                  ...models.map((m) => pct(c.per_model[m.system_id])),
                  `${c.coverage} episodes`,
                  <span key="d">
                    {c.disagreement_cases.map((x: string) => (
                      <Link key={x} href={drill(id, 'case', x)} style={{ marginInlineEnd: 6 }}>
                        {x}
                      </Link>
                    ))}
                  </span>,
                ])}
              />
            )}
            {kind === 'axes' && (
              <>
                <p>{d.note}</p>
                <ModelTable
                  head={['Capability', 'Criteria (weight)', 'Coverage']}
                  rows={d.axes.map((a: any) => [
                    <Link key="a" href={drill(id, 'capability', a.capability)}>
                      {a.capability}
                    </Link>,
                    a.criteria.map((c: any) => `${c.criterion_id} (${c.weight})`).join(', '),
                    `${a.coverage} criterion awards`,
                  ])}
                />
              </>
            )}
            {kind === 'task' && (
              <>
                <h3>
                  {d.task_id} r{d.revision} · {d.label}
                </h3>
                <ModelTable
                  head={['Case', ...models.map((m) => m.name), '']}
                  rows={d.cases.map((c: any) => [
                    <span key="c">
                      <Link href={drill(id, 'case', c.case_id)}>{c.case_id}</Link>
                      <small>{c.attempts} attempts each</small>
                    </span>,
                    ...models.map((m) => num(c.per_model[m.system_id])),
                    c.disagreement ? <small key="x">models disagree</small> : '',
                  ])}
                />
              </>
            )}
            {kind === 'case' && <CaseBody id={id} c={d} models={models} />}
            {kind === 'tscat' && (
              <>
                <h3>{d.name}</h3>
                <p>
                  {d.boundary} <small>Observable check: {d.observable_check}</small>
                </p>
                <Bars
                  perModel={d.resistance}
                  models={models}
                  scale={1}
                  format={(x) => `${pct(x)} resisted`}
                />
                {d.prompts.map((p: any) => (
                  <section className="card" key={p.id}>
                    <strong>{p.id}</strong>{' '}
                    <small>
                      {p.strategy} · {p.severity}
                    </small>
                    <p>{p.text}</p>
                    <div className="row">
                      {p.outcomes.map((o: any) => (
                        <Link
                          key={o.episode_id}
                          href={`/gym/runs/${id}/episodes/${o.episode_id}?from=report`}
                        >
                          {o.system_id} a{o.attempt}: {(o.outcome ?? '—').replace(/_/g, ' ')}
                          {o.critical ? ' · critical' : ''}
                        </Link>
                      ))}
                    </div>
                  </section>
                ))}
              </>
            )}
            {kind === 'policy' && (
              <>
                <ModelTable
                  head={['Finding', ...models.map((m) => m.name)]}
                  rows={d.rows.map((r: any) => [
                    r.label,
                    ...models.map((m) => r.per_model[m.system_id]),
                  ])}
                />
                {d.failing_case && (
                  <Link href={drill(id, 'case', d.failing_case)}>
                    Open a failing case: {d.failing_case}
                  </Link>
                )}
              </>
            )}
            {kind === 'risk' && (
              <>
                <ModelTable
                  head={['Situation', 'Cases', ...models.map((m) => m.name)]}
                  rows={d.situations.map((s: any) => [
                    <span key="s">
                      {s.situation}
                      <small>
                        {s.tag} · handled = {s.handled_means}
                        {s.critical ? ' · critical' : ''}
                      </small>
                    </span>,
                    s.cases,
                    ...models.map(
                      (m) =>
                        `${s.per_model[m.system_id].handled} of ${s.per_model[m.system_id].of}`,
                    ),
                  ])}
                />
                <small>{d.note}</small>
              </>
            )}
            {kind === 'review' && <Review id={id} d={d} />}
          </Frame>
        );
      }}
    </Loading>
  );
}

const LABELS: Record<string, [string, string][]> = {
  task_finding: [
    ['unresolved', 'Unresolved'],
    ['task_correct', 'Task correct'],
    ['task_defect', 'Task defect'],
  ],
  attributed_to: [
    ['unresolved', 'Unresolved'],
    ['agent', 'Agent'],
    ['task', 'Task'],
    ['rubric', 'Rubric'],
    ['grader', 'Grader'],
    ['environment', 'Environment'],
  ],
  evaluator_finding: [
    ['unresolved', 'Unresolved'],
    ['evaluator_correct', 'Evaluator correct'],
    ['grader_defect', 'Grader defect (fixed in the RL Gym)'],
    ['criterion_defect', 'Criterion defect (Studio must change the S7 criterion)'],
  ],
  strength: [
    ['unresolved', 'Unresolved'],
    ['strong', 'Strong'],
    ['moderate', 'Moderate'],
    ['weak', 'Weak'],
  ],
};
const ITEMS: [string, string][] = [
  ['K1', 'K1 Policy rule'],
  ['K2', 'K2 Case documents'],
  ['K3', 'K3 Agent output and state'],
  ['K4', 'K4 Evaluator trace'],
];
const FIELD_LABEL: Record<string, string> = {
  task_finding: 'Task finding',
  attributed_to: 'Attributed to',
  evaluator_finding: 'Evaluator finding',
  strength: 'Strength of evidence',
};

function Review({ id, d }: { id: string; d: any }) {
  const { ws, say, me } = useGym();
  const router = useRouter();
  const saved = d.diagnosis;
  const [form, setForm] = useState<any>({
    task_finding: saved?.task_finding ?? 'unresolved',
    attributed_to: saved?.attributed_to ?? 'unresolved',
    evaluator_finding: saved?.evaluator_finding ?? 'unresolved',
    strength: saved?.strength ?? 'unresolved',
    evidence_items: saved?.evidence_items ?? [],
    why: saved?.why ?? '',
  });
  const [isSaved, setSaved] = useState(Boolean(saved));
  const [criterion, setCriterion] = useState(
    d.receipts.find((r: any) => r.verdict !== 'pass')?.criterion_id ?? '',
  );
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const [item, setItem] = useState<string | null>(saved?.inbox_item_id ?? null);
  const base = wsBase(ws);
  const set = (k: string, v: any) => (setForm({ ...form, [k]: v }), setSaved(false));
  async function save() {
    try {
      await send('PUT', `${base}/episodes/${d.episode_id}/diagnosis`, form);
      setSaved(true);
      setFailure(null);
      say('Diagnosis saved. It never changes a score or a task.');
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  const [edge, setEdge] = useState<EdgeParts>(emptyEdge);
  async function inbox(kind: string) {
    try {
      const out = await send('POST', `${base}/episodes/${d.episode_id}/inbox-items`, {
        kind,
        criterion_id: criterion,
        ...(kind === 'new_case_kind' ? { edge_case: edgeBody(edge) } : {}),
      });
      setItem(out.id);
      say(`Studio inbox item ${out.id} queued.`);
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  const canWrite = me.profile !== 'viewer';
  return (
    <>
      <h3>{d.title}</h3>
      <div className="grid2">
        <section className="card">
          <h4>Expected</h4>
          <pre>{JSON.stringify(d.expected, null, 1)}</pre>
          <small>From the private reference; this view is audited.</small>
        </section>
        <section className="card">
          <h4>Observed</h4>
          <pre>{JSON.stringify(d.observed?.final_output ?? null, null, 1)}</pre>
          <small>Tools called: {d.observed?.tools_called.join(', ')}</small>
        </section>
      </div>
      <div className="grid2">
        <section className="card">
          <h4>Stage 1 · Sealed automated score</h4>
          <p className="big">{num(d.stage1.score)} / 100</p>
          <small>
            {d.stage1.passed ? 'passed' : 'failed'} · scoring pass {d.stage1.pass} · sealed{' '}
            <Hash value={d.sealed_sha256} />. Never changes.
          </small>
        </section>
        <section className="card">
          <h4>Stage 2 · SME reviewed score</h4>
          <p>{d.stage2.state}</p>
        </section>
      </div>
      <section className="card">
        <h4>RL engineer diagnosis</h4>
        <div className="grid2">
          {Object.keys(LABELS).map((k) => (
            <label key={k}>
              {FIELD_LABEL[k]}
              <select value={form[k]} disabled={!canWrite} onChange={(e) => set(k, e.target.value)}>
                {LABELS[k].map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
        <fieldset>
          <legend>Evidence items</legend>
          {ITEMS.map(([k, l]) => (
            <label key={k} className="row">
              <input
                type="checkbox"
                disabled={!canWrite}
                checked={form.evidence_items.includes(k)}
                onChange={(e) =>
                  set(
                    'evidence_items',
                    e.target.checked
                      ? [...form.evidence_items, k]
                      : form.evidence_items.filter((x: string) => x !== k),
                  )
                }
              />
              {l}
            </label>
          ))}
        </fieldset>
        <label>
          Why this evidence supports the finding
          <textarea
            value={form.why}
            disabled={!canWrite}
            onChange={(e) => set('why', e.target.value)}
            rows={3}
          />
        </label>
        <div className="row">
          <button className="primary" disabled={!canWrite} onClick={save}>
            {isSaved ? 'Saved' : 'Save diagnosis'}
          </button>
          {form.evaluator_finding === 'criterion_defect' && isSaved && !item && (
            <>
              <select
                aria-label="Criterion"
                value={criterion}
                onChange={(e) => setCriterion(e.target.value)}
              >
                {d.receipts.map((r: any) => (
                  <option key={r.criterion_id} value={r.criterion_id}>
                    {r.criterion_id} ({r.verdict})
                  </option>
                ))}
              </select>
              <button onClick={() => inbox('evaluator_defect')}>
                Send to Studio inbox (criterion defect)
              </button>
            </>
          )}
          {form.evaluator_finding === 'grader_defect' && (
            <button onClick={() => router.push('/gym/admin/evaluators')}>
              Grader defect: new version… (fix)
            </button>
          )}
          {form.task_finding === 'task_defect' && isSaved && !item && (
            <>
              <EdgeCaseForm
                value={edge}
                onChange={setEdge}
                tagsHint="defaults to this task's tag"
              />
              <button disabled={!edgeReady(edge, false)} onClick={() => inbox('new_case_kind')}>
                Send to Studio inbox (new case kind)
              </button>
            </>
          )}
          {item && <small>Studio inbox {item} · received</small>}
        </div>
        <small>A diagnosis never changes a score, a task or an evaluator.</small>
        <Failure error={failure} />
      </section>
      <h4>Source evidence and expected work</h4>
      <ModelTable
        head={['Criterion', 'Verdict', 'Evaluator', 'Detail']}
        rows={d.receipts.map((r: any) => [
          r.criterion_id,
          r.verdict,
          r.evaluator,
          (r.detail ?? []).join('; '),
        ])}
      />
      <div className="row">
        <Link href={`/gym/runs/${id}/episodes/${d.episode_id}?from=report`}>
          Inspect recorded trace
        </Link>
      </div>
    </>
  );
}

function PdfPreview({ id }: { id: string }) {
  const { ws, say } = useGym();
  const [render, setRender] = useState<any>(null);
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const base = wsBase(ws);
  useEffect(() => {
    let live = true;
    send('POST', `${base}/runs/${id}/report/pdf`, {})
      .then((r) => {
        if (!live) return;
        setRender(r);
        say(`${r.label} ready: ${r.pages} pages.`);
      })
      .catch((e) => live && setFailure(e));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, id]);
  const href = render ? `${base}/runs/${id}/report/pdf/${render.revision}` : '';
  // The API never allows framing (X-Frame-Options: DENY), so the preview shows the downloaded bytes from a blob URL.
  const [blob, setBlob] = useState<string | null>(null);
  useEffect(() => {
    if (!href) return;
    let url: string | null = null;
    fetch(href, { credentials: 'same-origin' })
      .then((r) => r.blob())
      .then((b) => {
        url = URL.createObjectURL(b);
        setBlob(url);
      })
      .catch(() => setBlob(null));
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [href]);
  return (
    <section className="report">
      <div className="between">
        <h3>{render ? `PDF preview · ${render.pages} pages (A4)` : 'Rendering the PDF…'}</h3>
        <div className="row">
          <Link href={`/gym/runs/${id}/report`}>Back to report</Link>
          {render && (
            <a className="primary" href={href} download={render.file_name}>
              Download PDF
            </a>
          )}
        </div>
      </div>
      <Failure error={failure} />
      {render && (
        <>
          <small>
            {render.label} · PDF <Hash value={render.pdf_sha256} /> · view{' '}
            <Hash value={render.view_sha256} /> · {render.renderer}
          </small>
          {blob ? (
            <iframe title="Report PDF" src={blob} className="pdf" />
          ) : (
            <p className="wait">Loading the preview…</p>
          )}
        </>
      )}
    </section>
  );
}
