'use client';

import { useState } from 'react';
import { GymApiError, get, send } from './api';
import { Failure, useData } from './ui';

// E-005 §3.1: the data plan's summary line, the exact case set, every case of the bound environment, and one case's
// records with its expected outcome (read-only; RL Engineers and Admins only; every read is audited).

function CaseDrawer({ path, caseId, onClose }: { path: string; caseId: string; onClose: () => void }) {
  const d = useData<any>(`${path}/cases/${encodeURIComponent(caseId)}`);
  return (
    <section className="drawer" role="dialog" aria-label={`Case ${caseId}`}>
      <div className="between">
        <h3>Case {caseId}</h3>
        <button onClick={onClose}>Close</button>
      </div>
      {d.error && (
        <p className="no">
          {(d.error as any)?.error?.code === 'FORBIDDEN'
            ? 'Only an RL Engineer or Admin can open a case with its expected outcome.'
            : 'The case could not be read from Studio’s registry.'}
        </p>
      )}
      {!d.data && !d.error && <p>Loading…</p>}
      {d.data && (
        <>
          <h4>Expected outcome</h4>
          <small>Read-only: SMEs own expected outcomes. This read is recorded.</small>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(d.data.reference, null, 2)}</pre>
          <h4>Application, parties and documents</h4>
          <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 360, overflow: 'auto' }}>
            {JSON.stringify(d.data.records, null, 2)}
          </pre>
        </>
      )}
    </section>
  );
}

function CaseTable({ rows, onView }: { rows: any[]; onView: (id: string) => void }) {
  return (
    <div className="table-wrap scroll" style={{ maxHeight: 360 }}>
      <table>
        <thead>
          <tr>
            <th>Case</th>
            <th>Application type</th>
            <th>Complete</th>
            <th>Edge case (family)</th>
            <th>Task</th>
            <th>View</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r: any) => (
            <tr key={r.case_id}>
              <td style={{ textAlign: 'left' }}>
                <code>{r.case_id}</code>
              </td>
              <td>{r.application_type}</td>
              <td>{r.completeness}</td>
              <td>
                {(r.edge_cases ?? []).join(', ') || '—'}
                {(r.edge_families ?? []).length > 0 && <small>{r.edge_families.join(', ')}</small>}
              </td>
              <td>{r.task ? `${r.task.task_id.slice(0, 8)} r${r.task.revision}` : '—'}</td>
              <td>
                <button aria-label={`View ${r.case_id}`} title="View the case" onClick={() => onView(r.case_id)}>
                  👁
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CasesPanel({ path, plan, prompts }: { path: string; plan: any; prompts: number }) {
  const set = useData<any>(`${path}/case-set`);
  const [show, setShow] = useState<'' | 'set' | 'all'>('');
  const [open, setOpen] = useState<string | null>(null);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [page, setPage] = useState(0);
  const [all, setAll] = useState<any>(null);
  const [failure, setFailure] = useState<GymApiError | null>(null);
  async function browse(nextPage = 0) {
    setFailure(null);
    const q = new URLSearchParams({
      ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v)),
      offset: String(nextPage * 50),
      limit: '50',
    });
    try {
      setAll(await get(`${path}/cases?${q}`));
      setPage(nextPage);
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  const cs = set.data;
  return (
    <section className="card">
      <h4>Cases</h4>
      {cs ? (
        <p>
          {cs.cases.length} cases ({cs.case_set}) + {prompts} safety prompts, per model and attempt
          {cs.short?.length ? ` · ${cs.short.length} cell(s) short of what the plan asks` : ''}
          {' · '}
          {cs.every_case_matches_a_task ? 'every case matches a task' : 'some cases match no task'}
        </p>
      ) : (
        <p>{set.error ? 'The case set could not be read from Studio’s registry.' : 'Reading the case set…'}</p>
      )}
      <div className="row">
        <button onClick={() => setShow(show === 'set' ? '' : 'set')} disabled={!cs}>
          👁 View case set
        </button>
        <button
          onClick={() => {
            setShow(show === 'all' ? '' : 'all');
            if (!all) browse(0);
          }}
        >
          Browse all cases
        </button>
        <small>Plan: seed {plan.sampling_seed}</small>
      </div>
      {show === 'set' && cs && <CaseTable rows={cs.cases} onView={setOpen} />}
      {show === 'all' && (
        <>
          <div className="row">
            {(['application_type', 'completeness', 'edge_case', 'family'] as const).map((k) => (
              <label key={k}>
                <small>{k.replace('_', ' ')}</small>
                <input
                  value={filters[k] ?? ''}
                  onChange={(e) => setFilters({ ...filters, [k]: e.target.value })}
                  placeholder={k === 'edge_case' ? 'tag or none' : ''}
                />
              </label>
            ))}
            <button onClick={() => browse(0)}>Filter</button>
          </div>
          <Failure error={failure} />
          {all && (
            <>
              <small>
                {all.total} cases on {all.environment} · page {page + 1} of{' '}
                {Math.max(1, Math.ceil(all.total / 50))}
              </small>
              <CaseTable rows={all.cases} onView={setOpen} />
              <div className="row">
                <button disabled={page === 0} onClick={() => browse(page - 1)}>
                  Previous
                </button>
                <button disabled={(page + 1) * 50 >= all.total} onClick={() => browse(page + 1)}>
                  Next
                </button>
              </div>
            </>
          )}
        </>
      )}
      {open && <CaseDrawer path={path} caseId={open} onClose={() => setOpen(null)} />}
    </section>
  );
}

// E-005 §3.2 / E-001 §6b: the bound environment's edge cases grouped by family, each variant's state and cases, the
// "at least N" minimum, and "Request variant" (inside an existing family; SMEs write the expected outcome).
export function EdgeFamilies({
  path,
  draft,
  edges,
  setEdges,
  cells,
  extraTags,
}: {
  path: string;
  draft: boolean;
  edges: Record<string, string>;
  setEdges: (e: Record<string, string>) => void;
  cells: any[];
  extraTags: string[];
}) {
  const cat = useData<any>(`${path}/edge-catalog`);
  const [form, setForm] = useState<any>(null);
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const [sent, setSent] = useState<any>(null);
  const [recipeFor, setRecipeFor] = useState<any>(null);
  async function writeRecipe() {
    setFailure(null);
    try {
      const out = await send('POST', `${path}/edge-variants/${encodeURIComponent(recipeFor.tag)}/recipe`, {
        recipe: JSON.parse(recipeFor.recipe || '[]'),
        products: String(recipeFor.products || '').split(',').map((x: string) => x.trim()).filter(Boolean),
        minimum_per_product: Number(recipeFor.minimum || 10),
        expected_revision: cat.data?.revision,
      });
      setSent(out);
      setRecipeFor(null);
      cat.reload();
    } catch (e) {
      setFailure(
        e instanceof SyntaxError
          ? ({ error: { message: 'The recipe must be JSON (a list of conditions)', code: 'VALIDATION_FAILED' } } as any)
          : (e as GymApiError),
      );
    }
  }
  const known = new Set((cat.data?.families ?? []).flatMap((f: any) => f.variants.map((v: any) => v.tag)));
  const orphan = extraTags.filter((t) => !known.has(t));
  function required(tag: string) {
    const cell = cells.find((x: any) => x.cell_key === `edge:${tag}`);
    return (
      <>
        <input
          type="number"
          min={0}
          aria-label={`At least N cases of ${tag}`}
          value={edges[tag] ?? ''}
          onChange={(e) => setEdges({ ...edges, [tag]: e.target.value })}
          disabled={!draft}
          style={{ width: 70 }}
        />
        {cell && (
          <small className={cell.quota > cell.available ? 'no' : 'ok'}>
            {cell.quota} / {cell.available}
          </small>
        )}
      </>
    );
  }
  async function submit() {
    setFailure(null);
    try {
      const out = await send('POST', `${path}/edge-variants`, {
        ...form,
        products: String(form.products || '')
          .split(',')
          .map((x: string) => x.trim())
          .filter(Boolean),
        minimum_per_product: Number(form.minimum_per_product || 10),
        expected_revision: cat.data?.revision,
      });
      setSent(out);
      setForm(null);
      cat.reload();
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  return (
    <section className="card">
      <div className="between">
        <h4>Edge cases (at least N each)</h4>
        <button onClick={() => setForm(form ? null : { kind: 'variant', family_id: '' })}>
          + Request edge case variant
        </button>
      </div>
      {cat.error && <p className="no">Studio&rsquo;s edge-case catalog could not be read.</p>}
      {cat.data && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Family / variant</th>
                <th>What it means</th>
                <th>Applies to</th>
                <th>State</th>
                <th>Available</th>
                <th>Required</th>
              </tr>
            </thead>
            <tbody>
              {cat.data.families.map((f: any) => [
                <tr key={f.family_id}>
                  <td style={{ textAlign: 'left' }} colSpan={6}>
                    <strong>{f.name}</strong> <small>{f.description}</small>
                  </td>
                </tr>,
                ...f.variants.map((v: any) => (
                  <tr key={f.family_id + v.tag}>
                    <td style={{ textAlign: 'left' }}>
                      ↳ {v.name} <code>{v.tag}</code>
                      {v.kind === 'boundary' && <small>boundary case</small>}
                    </td>
                    <td style={{ textAlign: 'left' }}>
                      <small>{v.twist || v.context || '—'}</small>
                    </td>
                    <td>
                      <small>{(v.products ?? []).join(', ').replace(/_/g, ' ')}</small>
                    </td>
                    <td>
                      <small>
                        {v.state === 'needs_recipe' ? 'waiting for recipe' : v.state}
                        {v.outcome_status && v.outcome_status !== 'confirmed' ? ' · waiting for SME outcome' : ''}
                      </small>
                      {v.state === 'needs_recipe' && (
                        <button
                          onClick={() =>
                            setRecipeFor({ tag: v.tag, recipe: '[]', products: (v.products ?? []).join(', '), minimum: v.minimum_per_product ?? 10 })
                          }
                        >
                          Write recipe
                        </button>
                      )}
                    </td>
                    <td>{v.available}</td>
                    <td>{v.in_this_version ? required(v.tag) : <small>not in this version</small>}</td>
                  </tr>
                )),
              ])}
              {orphan.map((t) => (
                <tr key={t}>
                  <td style={{ textAlign: 'left' }}>
                    <code>{t}</code>
                  </td>
                  <td colSpan={4}>
                    <small className="no">required by the plan but not in this environment version</small>
                  </td>
                  <td>{required(t)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {recipeFor && (
        <div className="card">
          <small>
            Recipe for <code>{recipeFor.tag}</code>: the conditions Studio&rsquo;s generator uses (for example{' '}
            <code>[{'{'}&quot;collection&quot;: &quot;documents&quot;, &quot;field&quot;: &quot;kind&quot;, &quot;op&quot;: &quot;equals&quot;, &quot;value&quot;: &quot;passport&quot;{'}'}]</code>).
            The SME&rsquo;s expected outcome is not changed. Studio checks feasibility at once.
          </small>
          <textarea
            rows={5}
            value={recipeFor.recipe}
            onChange={(e) => setRecipeFor({ ...recipeFor, recipe: e.target.value })}
            aria-label="Recipe (JSON)"
          />
          <div className="row">
            <input
              value={recipeFor.products}
              onChange={(e) => setRecipeFor({ ...recipeFor, products: e.target.value })}
              aria-label="Products"
            />
            <input
              type="number"
              min={1}
              value={recipeFor.minimum}
              onChange={(e) => setRecipeFor({ ...recipeFor, minimum: e.target.value })}
              aria-label="At least per product"
            />
            <button className="primary" onClick={writeRecipe}>
              Send recipe to Studio
            </button>
            <button onClick={() => setRecipeFor(null)}>Cancel</button>
          </div>
        </div>
      )}
      {sent && (
        <p className="ok">
          Request sent to Studio
          {sent.feasibility ? ` · feasibility: ${JSON.stringify(sent.feasibility)}` : ''}
          {sent.inbox_item_id ? ` · inbox item ${sent.inbox_item_id}` : ''}.
        </p>
      )}
      {form && (
        <div className="card">
          <small>
            Propose a variation or a boundary case inside an existing family. Studio checks whether it&rsquo;s data
            only or needs an environment change; an SME writes its expected outcome.
          </small>
          <div className="grid4">
            <label>
              Family
              <select value={form.family_id} onChange={(e) => setForm({ ...form, family_id: e.target.value })}>
                <option value="">Choose…</option>
                {(cat.data?.families ?? []).map((f: any) => (
                  <option key={f.family_id} value={f.family_id}>
                    {f.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Kind
              <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                <option value="variant">Variation</option>
                <option value="boundary">Boundary case</option>
              </select>
            </label>
            <label>
              Name
              <input value={form.name ?? ''} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label>
              Tag
              <input
                value={form.tag ?? ''}
                placeholder="e.g. passport_expires_today"
                onChange={(e) => setForm({ ...form, tag: e.target.value })}
              />
            </label>
            <label>
              Context
              <input value={form.context ?? ''} onChange={(e) => setForm({ ...form, context: e.target.value })} />
            </label>
            <label>
              Twist
              <input value={form.twist ?? ''} onChange={(e) => setForm({ ...form, twist: e.target.value })} />
            </label>
            <label>
              Products (comma-separated)
              <input value={form.products ?? ''} onChange={(e) => setForm({ ...form, products: e.target.value })} />
            </label>
            <label>
              At least per product
              <input
                type="number"
                min={1}
                value={form.minimum_per_product ?? 10}
                onChange={(e) => setForm({ ...form, minimum_per_product: e.target.value })}
              />
            </label>
          </div>
          <label>
            Reason
            <input value={form.reason ?? ''} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
          </label>
          <div className="row">
            <button
              className="primary"
              disabled={!form.family_id || !(form.name ?? '').trim() || !(form.reason ?? '').trim()}
              onClick={submit}
            >
              Send request to Studio
            </button>
            <button onClick={() => setForm(null)}>Cancel</button>
          </div>
        </div>
      )}
      <Failure error={failure} />
    </section>
  );
}

// E-006 §3: Trust & Safety categories: applies here? (from the tasks' tools and which operations reach the customer),
// severity, prompts (View), source, grader, can be graded on this environment.
export function SafetyTable({ path }: { path: string }) {
  const t = useData<any>(`${path}/ts-categories`);
  const [open, setOpen] = useState<string | null>(null);
  if (t.error) return <p className="no">The category table could not be computed.</p>;
  if (!t.data) return <p>Checking the categories…</p>;
  const d = t.data;
  const cat = d.categories.find((c: any) => c.key === open);
  return (
    <section className="card">
      <h4>Categories</h4>
      <small>
        Customer-facing operations ({d.operation_audience.source}):{' '}
        {d.operation_audience.customer_facing.join(', ') || 'none'} · attacks delivered in the{' '}
        {(d.delivered_as ?? '—').replace('_', ' ')}.
      </small>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Category</th>
              <th>What it tests</th>
              <th>Applies here?</th>
              <th>Severity</th>
              <th>Prompts</th>
              <th>Graded by</th>
              <th>Can be graded here</th>
              <th>Recent</th>
            </tr>
          </thead>
          <tbody>
            {d.categories.map((c: any) => (
              <tr key={c.key}>
                <td style={{ textAlign: 'left' }}>
                  {c.name}
                  <small>{c.group}</small>
                </td>
                <td style={{ textAlign: 'left' }}>
                  <small>{c.what_it_tests}</small>
                </td>
                <td className={c.applies === 'No' ? 'no' : ''}>
                  {c.applies}
                  <small>{c.applies_why}</small>
                </td>
                <td>{(c.severity ?? []).join(', ') || '—'}</td>
                <td>
                  {c.prompts.length}{' '}
                  <button aria-label={`View prompts for ${c.name}`} onClick={() => setOpen(open === c.key ? null : c.key)}>
                    👁
                  </button>
                </td>
                <td>
                  <small>{c.grader}</small>
                </td>
                <td className={c.can_be_graded ? '' : 'no'}>
                  {c.can_be_graded ? 'Yes' : 'No'}
                  {c.can_be_graded_why && <small>{c.can_be_graded_why}</small>}
                </td>
                <td>
                  <small>
                    {Object.entries(c.recent)
                      .map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`)
                      .join(' · ') || '—'}
                  </small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {cat && (
        <section className="drawer" role="dialog" aria-label={`Prompts for ${cat.name}`}>
          <div className="between">
            <h4>{cat.name}: prompts</h4>
            <button onClick={() => setOpen(null)}>Close</button>
          </div>
          <small>
            Source: {cat.source ?? '—'} · approved {cat.approved_at ? new Date(cat.approved_at).toLocaleString() : '—'}
          </small>
          <ul>
            {cat.prompts.map((p: any) => (
              <li key={p.id}>
                <code>{p.id}</code> · {p.severity} · {p.strategy} · delivered in the{' '}
                {(p.delivered_as ?? '—').replace('_', ' ')} {p.approved ? '' : '· not approved'}
                <pre style={{ whiteSpace: 'pre-wrap' }}>{p.text}</pre>
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}
