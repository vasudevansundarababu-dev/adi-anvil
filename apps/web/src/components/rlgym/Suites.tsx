'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { GymApiError, send, short, when, wsBase } from './api';
import { Badge, Env, Failure, Hash, Loading, Tabs, useData, useGym } from './ui';

export function SuitesTab({ project }: { project: string }) {
  const { ws, say } = useGym();
  const router = useRouter();
  const { data, error } = useData<any>(`${wsBase(ws)}/projects/${project}/suites`);
  const [name, setName] = useState('');
  const [failure, setFailure] = useState<GymApiError | null>(null);
  async function draft(suiteId: string) {
    setFailure(null);
    try {
      const sv = await send('POST', `${wsBase(ws)}/suites/${suiteId}/drafts`, {
        project_id: project,
      });
      router.push(`/gym/projects/${project}/suites/${sv.id}`);
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  return (
    <Loading data={data} error={error}>
      {() => (
        <>
          <small>
            A suite always covers all ready tasks of the project. Two runs are comparable only on
            the same suite version.
          </small>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Suite</th>
                  <th>Versions</th>
                  <th>Runs</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 && (
                  <tr>
                    <td colSpan={4} style={{ textAlign: 'left' }}>
                      No suites yet: the default suite is created by the next export.
                    </td>
                  </tr>
                )}
                {data.items.map((s: any) => (
                  <tr key={s.suite_id}>
                    <td>
                      <strong>{s.name}</strong>
                      <small>
                        {s.suite_id}
                        {s.is_default ? ' · default (all ready tasks after the latest export)' : ''}
                      </small>
                    </td>
                    <td>
                      {s.versions.map((v: any) => (
                        <div key={v.id}>
                          <Link href={`/gym/projects/${project}/suites/${v.id}`}>
                            {v.state === 'draft' ? 'Draft' : `v${v.version}`}
                          </Link>{' '}
                          <small>
                            {v.state === 'saved' ? (
                              <>
                                <Hash value={v.suite_sha256} /> · planned on{' '}
                                {short(v.planned_on_env_version)} · {when(v.saved_at)}
                              </>
                            ) : (
                              'not saved'
                            )}
                          </small>
                        </div>
                      ))}
                    </td>
                    <td>
                      <small>{s.runs_note}</small>
                    </td>
                    <td>
                      <button onClick={() => draft(s.suite_id)}>
                        {s.versions.some((v: any) => v.state === 'draft')
                          ? 'Open draft'
                          : 'New suite version'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="row">
            <input
              aria-label="New suite name"
              placeholder="New suite name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <button
              disabled={!name.trim()}
              onClick={async () => {
                setFailure(null);
                try {
                  const sv = await send('POST', `${wsBase(ws)}/projects/${project}/suites`, {
                    name,
                  });
                  say(`Suite ${sv.suite_id} created as a draft.`);
                  router.push(`/gym/projects/${project}/suites/${sv.id}`);
                } catch (e) {
                  setFailure(e as GymApiError);
                }
              }}
            >
              New suite
            </button>
          </div>
          <Failure error={failure} />
        </>
      )}
    </Loading>
  );
}

export function SuiteEditor({ project, id, step }: { project: string; id: string; step: string }) {
  const { ws, say } = useGym();
  const router = useRouter();
  const path = `${wsBase(ws)}/suite-versions/${id}`;
  const { data, error, reload } = useData<any>(path);
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const [moreData, setMoreData] = useState(false);
  async function act(method: 'POST' | 'PATCH', url: string, body: unknown, message?: string) {
    setFailure(null);
    try {
      const r = await send(method, url, body);
      if (message) say(message);
      reload();
      return r;
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  const base = `/gym/projects/${project}/suites/${id}`;
  return (
    <Loading data={data} error={error}>
      {() => {
        const draft = data.state === 'draft';
        return (
          <div className="work">
            <aside>
              <Link href={`/gym/projects/${project}/suites`}>← Back to project</Link>
              <h3>{data.name}</h3>
              <div className="row">
                <Badge
                  state={draft ? 'draft' : 'ready'}
                  label={draft ? 'Draft' : `Saved · v${data.version}`}
                />
                {data.suite_sha256 && <Hash value={data.suite_sha256} />}
              </div>
              <small>Planned on {short(data.planned_on_env_version)}</small>
              <h4>Can this suite run?</h4>
              {data.checklist.items.map((i: any) => (
                <div className="check" key={i.key}>
                  <i className={i.ok ? 'ok' : 'no'}>{i.ok ? '✓' : '✕'}</i>
                  <span>
                    {i.label}
                    {i.detail && <small>{i.detail}</small>}
                    {draft && i.short && !i.ok && (
                      <button
                        className="link"
                        onClick={() =>
                          act('PATCH', path, { lower: i.cell_key }, 'Quota lowered to what exists.')
                        }
                      >
                        Lower to what exists
                      </button>
                    )}
                  </span>
                </div>
              ))}
              {draft && data.checklist.items.some((i: any) => i.short && !i.ok) && (
                <div className="row">
                  <button
                    onClick={() =>
                      act('PATCH', path, { lower_all: true }, 'All short quotas lowered.')
                    }
                  >
                    Lower all of them to what exists
                  </button>
                  <button
                    onClick={() =>
                      act(
                        'PATCH',
                        path,
                        { missing_policy: 'use_available' },
                        'The suite uses what is available.',
                      )
                    }
                  >
                    Use what is available
                  </button>
                  <button onClick={() => setMoreData(true)}>
                    Send to Studio inbox (more data)
                  </button>
                </div>
              )}
              {draft && (
                <div className="row">
                  <button
                    className="primary"
                    disabled={!data.checklist.can_run}
                    onClick={async () => {
                      const r = await act('POST', `${path}/save`, {});
                      if (r) say(`Saved as ${r.label}.`);
                    }}
                  >
                    Save suite version
                  </button>
                  <button
                    onClick={async () => {
                      await fetch(path, {
                        method: 'DELETE',
                        credentials: 'same-origin',
                        headers: { 'X-CSRF-Token': csrfCookie() },
                      });
                      router.push(`/gym/projects/${project}/suites`);
                    }}
                  >
                    Discard draft
                  </button>
                </div>
              )}
              {!draft && data.checklist.can_run && (
                <Link
                  className="primary"
                  href={`/gym/runs/new?project=${project}&suite=${data.id}`}
                >
                  Run benchmark
                </Link>
              )}
              {data.inbox_items.map((item: any) => (
                <small key={item.id}>
                  Studio inbox {item.studio_id ?? item.id} · more data · {item.state}
                  {item.released_version ? ` · released ${item.released_version}` : ''}
                </small>
              ))}
              <Failure error={failure} />
            </aside>
            <main>
              <Tabs
                current={step}
                items={[
                  { key: 'bindings', label: '1 Bindings', href: `${base}/bindings` },
                  { key: 'data', label: '2 Data plan', href: `${base}/data` },
                  { key: 'ts', label: '3 Trust & Safety', href: `${base}/ts` },
                ]}
              />
              {step === 'bindings' && <Bindings data={data} draft={draft} act={act} path={path} />}
              {step === 'data' && <DataPlan data={data} draft={draft} act={act} path={path} />}
              {step === 'ts' && <TrustSafety data={data} draft={draft} act={act} path={path} />}
              {moreData && (
                <MoreDataForm
                  data={data}
                  path={path}
                  close={() => setMoreData(false)}
                  done={reload}
                />
              )}
            </main>
          </div>
        );
      }}
    </Loading>
  );
}

function csrfCookie() {
  return (
    document.cookie
      .split('; ')
      .find((x) => x.startsWith('anvil_csrf='))
      ?.slice('anvil_csrf='.length) ?? ''
  );
}

type Act = (method: 'POST' | 'PATCH', url: string, body: unknown, message?: string) => Promise<any>;

function Bindings({
  data,
  draft,
  act,
  path,
}: {
  data: any;
  draft: boolean;
  act: Act;
  path: string;
}) {
  const [choice, setChoice] = useState<Record<string, string>>({});
  const [reason, setReason] = useState('');
  const [suggestions, setSuggestions] = useState<any>(null);
  return (
    <>
      {data.bindings.map((b: any) => (
        <section className="card" key={b.alias}>
          <div className="between">
            <strong>{b.alias}</strong>
            <Env
              ok={b.ok}
              label={b.ok ? `binds ${short(b.binds_now)} · ${b.seed_family}` : b.reason_unbound}
            />
          </div>
          <div>
            {b.rule_label} · <small>source {b.source.replace('_', ' ')}</small>
            {b.reason && <small>Reason: {b.reason}</small>}
          </div>
          {draft && (
            <div className="grid3">
              <label>
                Binding
                <select
                  value={choice[b.alias] ?? ''}
                  onChange={(e) => setChoice({ ...choice, [b.alias]: e.target.value })}
                  aria-label={`Binding ${b.alias}`}
                >
                  <option value="">Follow project rule</option>
                  {b.options.map((o: any) => (
                    <option key={o.pinned_version_id} value={o.pinned_version_id}>
                      {o.label} ({o.cases} cases)
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Reason (custom only)
                <input value={reason} onChange={(e) => setReason(e.target.value)} />
              </label>
              <button
                onClick={() =>
                  act(
                    'PATCH',
                    path,
                    {
                      bindings: [
                        choice[b.alias]
                          ? {
                              alias: b.alias,
                              rule_kind: 'pinned',
                              pinned_version_id: choice[b.alias],
                              reason,
                              source: 'custom',
                            }
                          : { alias: b.alias, rule_kind: 'project_rule' },
                      ],
                    },
                    'Binding saved on the draft; the data plan is re-checked against the bound data.',
                  )
                }
              >
                Apply
              </button>
            </div>
          )}
        </section>
      ))}
      {draft && (
        <section className="card">
          <div className="between">
            <h4>Suggest bindings</h4>
            <button
              onClick={async () =>
                setSuggestions(await send('POST', `${path}/suggestions/bindings`, {}))
              }
            >
              Suggest bindings
            </button>
          </div>
          <small>
            Rule-based (no model is approved locally); a person applies it and the suite records the
            source.
          </small>
          {suggestions?.suggestions.map((s: any) => (
            <div className="card" key={s.name}>
              <strong>
                {s.name} {s.recommended && <Badge state="ready" label="Recommended" />}
              </strong>
              <small>{s.reason}</small>
              <button
                onClick={() => act('PATCH', path, { bindings: s.bindings }, `Applied: ${s.name}.`)}
              >
                Apply
              </button>
            </div>
          ))}
        </section>
      )}
      <section className="card">
        <h4>Evaluators · {data.criteria.length} criteria</h4>
        <small>
          {data.criteria.filter((c: any) => c.rule_kind === 'project_rule').length} follow the
          project rule (Latest qualified; a new version starts a new cohort).
        </small>
        <div className="row">
          {data.criteria.map((c: any) => (
            <Env
              key={c.criterion_id}
              ok={c.ok}
              label={`${c.criterion_id} v${c.binds_now ?? '—'}`}
            />
          ))}
        </div>
      </section>
    </>
  );
}

function DataPlan({
  data,
  draft,
  act,
  path,
}: {
  data: any;
  draft: boolean;
  act: Act;
  path: string;
}) {
  const plan = data.plan;
  const [sample, setSample] = useState(String(plan.sample_size));
  const [quotas, setQuotas] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(plan.completeness_quotas).map(([k, v]) => [k, String(v)])),
  );
  const [edges, setEdges] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(plan.required_edges).map(([k, v]) => [k, String(v)])),
  );
  const [seed, setSeed] = useState(String(plan.sampling_seed));
  const [mix, setMix] = useState<any>(null);
  // D-038: the bound environment's own edge cases, plus any the saved plan still requires (shown as missing).
  const edgeTags: string[] = Array.from(
    new Set([
      ...(data.edge_catalog ?? []).map((e: any) => e.tag),
      ...Object.keys(plan.required_edges ?? {}),
    ]),
  );
  const strata = Array.from(
    new Set(
      data.cells
        .filter((c: any) => c.dimension_values.application_type)
        .map((c: any) => c.dimension_values.application_type),
    ),
  );
  const completeness = Object.keys(plan.completeness_quotas);
  const total = Object.values(quotas).reduce((a, b) => a + Number(b || 0), 0);
  function applyPlan(next?: any) {
    const body = next ?? {
      sample_size: Number(sample),
      completeness_quotas: Object.fromEntries(
        Object.entries(quotas).map(([k, v]) => [k, Number(v)]),
      ),
      required_edges: Object.fromEntries(
        Object.entries(edges)
          .filter(([, v]) => v !== '' && Number(v) > 0)
          .map(([k, v]) => [k, Number(v)]),
      ),
      sampling_seed: Number(seed),
    };
    return act(
      'PATCH',
      path,
      { data_plan: body, ...(next ? { plan_source: 'ai_suggestion' } : {}) },
      'Data plan updated; availability re-checked.',
    );
  }
  return (
    <>
      <small>
        A run never creates input data: it selects cases from {short(data.planned_on_env_version)}
        &apos;s case catalog. {data.tasks.count} ready tasks
        {data.tasks.unmatched.length
          ? ` · unmatched: ${data.tasks.unmatched.join(', ')}`
          : ' · every task matches cases'}
        .
      </small>
      <div className="grid4">
        <label>
          Sample size (cases per run, per model and attempt)
          <input
            type="number"
            min={1}
            value={sample}
            onChange={(e) => setSample(e.target.value)}
            disabled={!draft}
          />
        </label>
        <label>
          Stratify by
          <select disabled>
            <option>application type of the suite&rsquo;s tasks (equal shares)</option>
          </select>
        </label>
        <label>
          Sampling seed
          <input
            type="number"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            disabled={!draft}
          />
        </label>
        <div className="stat">
          <small>Missing policy</small>
          <strong style={{ fontSize: 15 }}>
            {plan.missing_policy === 'use_available' ? 'Use what is available' : 'Block'}
          </strong>
        </div>
      </div>
      <div className="grid4">
        {completeness.map((c) => (
          <label key={c}>
            {c} (%)
            <input
              type="number"
              min={0}
              max={100}
              value={quotas[c]}
              onChange={(e) => setQuotas({ ...quotas, [c]: e.target.value })}
              disabled={!draft}
            />
          </label>
        ))}
        <div className={total === 100 ? 'ok' : 'no'}>Total {total}%</div>
      </div>
      <table>
        <thead>
          <tr>
            <th>Application type</th>
            {completeness.map((c) => (
              <th key={c}>{c}: requested / available</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {strata.map((t: any) => (
            <tr key={t}>
              <td>{t}</td>
              {completeness.map((c) => {
                const cell = data.cells.find((x: any) => x.cell_key === `${t}|${c}`);
                const shortCell = cell && cell.quota > cell.available;
                return (
                  <td key={c} className={shortCell ? 'no' : ''}>
                    {cell?.quota} / {cell?.available}
                    {cell?.original_quota != null && (
                      <small>lowered from {cell.original_quota}</small>
                    )}
                    {cell?.inbox_item_id && <small>more data asked</small>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <section className="card">
        <h4>Required edge cases (at least N each)</h4>
        <small>
          The edge cases {short(data.planned_on_env_version)} has, counted from its cases (D-038).
        </small>
        {edgeTags.length === 0 && <p>This environment version has no edge-case tags.</p>}
        <div className="grid4">
          {edgeTags.map((tag: string) => {
            const cell = data.cells.find((x: any) => x.cell_key === `edge:${tag}`);
            const known = (data.edge_catalog ?? []).find((e: any) => e.tag === tag);
            return (
              <label key={tag}>
                <code>{tag}</code>
                <small>
                  {known
                    ? `${known.available} cases · ${Object.keys(known.application_types)
                        .map((t) => t.replace(/_/g, ' '))
                        .join(', ')}`
                    : 'not in this environment version'}
                </small>
                <input
                  type="number"
                  min={0}
                  value={edges[tag] ?? ''}
                  onChange={(e) => setEdges({ ...edges, [tag]: e.target.value })}
                  disabled={!draft}
                />
                {cell && (
                  <small className={cell.quota > cell.available ? 'no' : 'ok'}>
                    {cell.quota} requested / {cell.available} available
                  </small>
                )}
              </label>
            );
          })}
        </div>
      </section>
      {draft && (
        <div className="row">
          <button className="primary" disabled={total !== 100} onClick={() => applyPlan()}>
            Apply data plan
          </button>
          <button
            onClick={async () => setMix(await send('POST', `${path}/suggestions/data-mix`, {}))}
          >
            Suggest mix
          </button>
        </div>
      )}
      {mix && (
        <section className="card">
          <small>
            Rule-based (no model): proposals never ask for more than exists; short cells are listed
            for a more-data item.
          </small>
          {mix.suggestions.map((s: any) => (
            <div className="card" key={s.name}>
              <strong>
                {s.name} {s.recommended && <Badge state="ready" label="Recommended" />}
              </strong>
              <small>{s.reason}</small>
              {s.capped.length > 0 && <small>Capped: {s.capped.join(', ')}</small>}
              {s.plan && <button onClick={() => applyPlan(s.plan)}>Apply</button>}
            </div>
          ))}
        </section>
      )}
    </>
  );
}

function MoreDataForm({
  data,
  path,
  close,
  done,
}: {
  data: any;
  path: string;
  close: () => void;
  done: () => void;
}) {
  const { say } = useGym();
  const cells = data.cells.filter((c: any) => c.quota > c.available);
  const [desc, setDesc] = useState<Record<string, string>>({});
  const [lineage, setLineage] = useState('same_seed_family');
  const [neededBy, setNeededBy] = useState('');
  const [why, setWhy] = useState('');
  const [failure, setFailure] = useState<GymApiError | null>(null);
  return (
    <>
      <div className="backdrop" onClick={close} />
      <section className="drawer" role="dialog" aria-label="Send to Studio inbox (more data)">
        <h3>Send to Studio inbox · more data</h3>
        <small>
          This is the only place in the RL Gym where more data is asked for. It changes nothing now;
          Studio plans a new environment version.
        </small>
        {cells.map((c: any) => (
          <label key={c.cell_key}>
            <strong>{c.cell_key.replace('|', ' · ')}</strong>
            <small>
              need {c.original_quota ?? c.quota} · have {c.available} · request{' '}
              {(c.original_quota ?? c.quota) - c.available}
            </small>
            <textarea
              rows={2}
              placeholder="The case in business terms, the rule it tests, the field values that make it that case, what to vary"
              value={desc[c.cell_key] ?? ''}
              onChange={(e) => setDesc({ ...desc, [c.cell_key]: e.target.value })}
            />
          </label>
        ))}
        <label>
          Data lineage
          <select value={lineage} onChange={(e) => setLineage(e.target.value)}>
            <option value="same_seed_family">
              Same seed family (comparable with earlier runs)
            </option>
            <option value="new_seed_family">New seed family (new leaderboard group)</option>
          </select>
        </label>
        <label>
          Why
          <input value={why} onChange={(e) => setWhy(e.target.value)} />
        </label>
        <label>
          Needed by
          <select value={neededBy} onChange={(e) => setNeededBy(e.target.value)}>
            <option value="">No date</option>
            <option value="2026-11-28">This week</option>
            <option value="2026-12-01">Before 1 Dec 2026</option>
          </select>
        </label>
        <div className="row">
          <button
            className="primary"
            disabled={cells.some((c: any) => !(desc[c.cell_key] ?? '').trim())}
            onClick={async () => {
              setFailure(null);
              try {
                const r = await send('POST', `${path}/more-data`, {
                  descriptions: desc,
                  lineage,
                  needed_by: neededBy || undefined,
                  why,
                });
                say(`More-data item ${r.item.id} queued for Studio's next-version inbox.`);
                done();
                close();
              } catch (e) {
                setFailure(e as GymApiError);
              }
            }}
          >
            Send to Studio inbox
          </button>
          <button onClick={close}>Close</button>
        </div>
        <Failure error={failure} />
      </section>
    </>
  );
}

function TrustSafety({
  data,
  draft,
  act,
  path,
}: {
  data: any;
  draft: boolean;
  act: Act;
  path: string;
}) {
  const ts = data.ts;
  const [suggestion, setSuggestion] = useState<any>(null);
  const [unticked, setUnticked] = useState<Record<string, boolean>>({});
  return (
    <>
      <div className="row">
        <label className="row">
          <input
            type="checkbox"
            checked={ts.enabled}
            disabled={!draft}
            onChange={(e) =>
              act(
                'PATCH',
                path,
                { ts_settings: { enabled: e.target.checked } },
                e.target.checked ? 'Trust & Safety on.' : 'Trust & Safety off.',
              )
            }
          />
          Trust &amp; Safety for this suite
        </label>
        <Badge
          state={
            ts.state === 'approved' ? 'ready' : ts.state === 'generated' ? 'registered' : 'draft'
          }
          label={ts.state}
        />
      </div>
      <small>
        Domain {ts.domain} · {ts.prompts_per_category} prompts per category · placement{' '}
        {ts.placement.replace('_', ' ')} · strategies {ts.strategies.join(', ')}. Prompts come from
        the RL Gym&rsquo;s local template generator and are synthetic; Promptfoo&rsquo;s red-team
        generator is not used (Promptfoo runs only as a scoring plug-in).
      </small>
      {ts.placement !== 'user_message' && (
        <small>
          Studio OpenEnv environments (for example golden-kyc-openenv) have no injection point: there,
          every attack is delivered in the user message, so hidden instructions in documents or tool
          output are not tested (D-040). The run records where each attack was actually delivered.
        </small>
      )}
      {draft && ts.enabled && (
        <div className="row">
          <button
            onClick={async () => setSuggestion(await send('POST', `${path}/suggestions/ts`, {}))}
          >
            Suggest categories
          </button>
          <button
            disabled={!ts.categories.length}
            onClick={() =>
              act('POST', `${path}/ts/generate`, {}, 'Prompts generated; review and approve them.')
            }
          >
            Generate prompts
          </button>
        </div>
      )}
      {suggestion && (
        <section className="card">
          <small>
            Rule-based (no model).{' '}
            {suggestion.skipped.length
              ? `Skipped: ${suggestion.skipped.map((s: any) => `${s.key} (${s.reason})`).join('; ')}`
              : ''}
          </small>
          <button
            onClick={() =>
              act(
                'PATCH',
                path,
                { ts_categories: suggestion.categories },
                `${suggestion.categories.length} categories applied.`,
              )
            }
          >
            Apply {suggestion.categories.length} categories
          </button>
        </section>
      )}
      {ts.categories.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Category</th>
              <th>Boundary tested</th>
              <th>Observable check</th>
              <th>Plugin</th>
            </tr>
          </thead>
          <tbody>
            {ts.categories.map((c: any) => (
              <tr key={c.key}>
                <td>
                  {c.name}
                  <small>{c.category_group}</small>
                </td>
                <td>{c.boundary_tested}</td>
                <td>{c.observable_check}</td>
                <td>{c.promptfoo_plugin ?? 'custom policy'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {ts.prompts.length > 0 && (
        <section className="card">
          <h4>Review prompts ({ts.prompts.filter((p: any) => p.approved).length} kept)</h4>
          {ts.prompts.map((p: any) => (
            <label key={p.id} className="row" style={{ alignItems: 'start' }}>
              <input
                type="checkbox"
                disabled={!draft}
                checked={unticked[p.id] === undefined ? p.approved : !unticked[p.id]}
                onChange={(e) => setUnticked({ ...unticked, [p.id]: !e.target.checked })}
              />
              <span>
                <small>
                  {p.category_key} · {p.strategy} · {p.severity}
                </small>
                {p.text}
              </span>
            </label>
          ))}
          {draft && ts.state !== 'draft' && (
            <div className="row">
              <button
                onClick={() =>
                  act(
                    'POST',
                    `${path}/ts/review`,
                    {
                      prompts: Object.fromEntries(
                        Object.entries(unticked).map(([k, v]) => [k, !v]),
                      ),
                    },
                    'Review saved.',
                  )
                }
              >
                Save review
              </button>
              <button
                className="primary"
                disabled={ts.state === 'approved'}
                onClick={() =>
                  act('POST', `${path}/ts/approve`, {}, 'Prompt set approved and frozen.')
                }
              >
                Approve prompt set
              </button>
            </div>
          )}
          {ts.prompt_set_sha256 && (
            <small>
              Approved {when(ts.approved_at)} · prompt set <Hash value={ts.prompt_set_sha256} />
            </small>
          )}
        </section>
      )}
    </>
  );
}
