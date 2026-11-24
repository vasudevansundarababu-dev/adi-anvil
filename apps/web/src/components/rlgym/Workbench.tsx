'use client';

import { useState } from 'react';
import { GymApiError, get, send, when, wsBase } from './api';
import { Badge, Failure, useData, useGym } from './ui';

// E-004 §3.2-3.3: the grader workbench. Drafts are one person's experiment (recorded, no approval); a draft re-score
// is a new draft pass that never changes the run's reported score; "Ready for leaderboard" needs a second person.

export function GraderWorkbench({ project, criteria }: { project: string; criteria: any[] }) {
  const { ws, say } = useGym();
  const base = `${wsBase(ws)}/projects/${project}/grader-drafts`;
  const data = useData<any>(base);
  const [open, setOpen] = useState<string | null>(null);
  const [form, setForm] = useState<any>({});
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const editable = criteria
    .map((cr: any) => ({
      cr,
      blocks: (cr.scoring?.checks ?? []).filter((c: any) => c.kind === 'plugin' || c.kind === 'rubric'),
    }))
    .filter((x) => x.blocks.length > 0);
  async function save(criterion: string) {
    setFailure(null);
    const overrides: any = {};
    const off: string[] = [];
    for (const [bid, f] of Object.entries<any>(form)) {
      if (f.off) {
        off.push(bid);
        continue;
      }
      const settings: any = {};
      if (f.judge) settings.judge = f.judge;
      if (f.rubric) settings.rubric = f.rubric;
      if (f.threshold !== undefined && f.threshold !== '') settings.threshold = Number(f.threshold);
      const o: any = {};
      if (Object.keys(settings).length) o.settings = settings;
      if (f.share !== undefined && f.share !== '') o.share_percent = Number(f.share);
      if (Object.keys(o).length) overrides[bid] = o;
    }
    try {
      await send('POST', base, {
        criterion_id: criterion,
        block_overrides: overrides,
        disabled_blocks: off,
        note: form.__note,
      });
      say('Draft saved (an experiment; nothing changes until a draft is approved).');
      setForm({});
      setOpen(null);
      data.reload();
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  async function act(path: string, body: any, message: string) {
    setFailure(null);
    try {
      await send('POST', `${wsBase(ws)}${path}`, body);
      say(message);
      data.reload();
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  if (editable.length === 0) return null;
  return (
    <details>
      <summary>Grader workbench (drafts, re-score, ready for leaderboard)</summary>
      <small>
        Change a judge or rubric block as a draft: the judge (approved models only), its prompt, the pass threshold, its
        share of the criterion, or turn it off. Try drafts on a finished run with &ldquo;Re-score with drafts&rdquo;
        on its run page. &ldquo;Ready for leaderboard&rdquo; needs a second RL Engineer or Admin to approve.
      </small>
      {editable.map(({ cr, blocks }) => (
        <div key={cr.criterion_id} className="card">
          <div className="between">
            <strong>{cr.criterion_id}</strong>
            <button onClick={() => setOpen(open === cr.criterion_id ? null : cr.criterion_id)}>
              {open === cr.criterion_id ? 'Close' : 'New draft'}
            </button>
          </div>
          {open === cr.criterion_id &&
            blocks.map((b: any) => {
              const f = form[b.id] ?? {};
              const set = (k: string, v: any) => setForm({ ...form, [b.id]: { ...f, [k]: v } });
              const j = (cr.scoring?.judges ?? []).find((x: any) => x.block_id === b.id);
              return (
                <div key={b.id} className="grid4">
                  <label className="row">
                    <input type="checkbox" checked={!f.off} onChange={(e) => set('off', !e.target.checked)} />
                    <code>{b.id}</code> on
                  </label>
                  <label>
                    Judge
                    <select value={f.judge ?? ''} onChange={(e) => set('judge', e.target.value)} disabled={f.off}>
                      <option value="">{j ? `as now (${j.model})` : 'as now'}</option>
                      {(data.data?.judges ?? []).map((m: string) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Pass at score ≥
                    <input
                      type="number"
                      min={0}
                      max={1}
                      step="0.05"
                      placeholder={j ? String(j.threshold) : '0.7'}
                      value={f.threshold ?? ''}
                      onChange={(e) => set('threshold', e.target.value)}
                      disabled={f.off}
                    />
                  </label>
                  <label>
                    Share of the criterion (%)
                    <input
                      type="number"
                      min={0}
                      max={100}
                      placeholder={j?.share_percent ? String(j.share_percent) : ''}
                      value={f.share ?? ''}
                      onChange={(e) => set('share', e.target.value)}
                      disabled={f.off}
                    />
                  </label>
                  <label style={{ gridColumn: '1 / -1' }}>
                    Prompt (rubric)
                    <textarea
                      rows={3}
                      placeholder={j?.rubric ?? ''}
                      value={f.rubric ?? ''}
                      onChange={(e) => set('rubric', e.target.value)}
                      disabled={f.off}
                    />
                  </label>
                </div>
              );
            })}
          {open === cr.criterion_id && (
            <div className="row">
              <input
                placeholder="Note (optional)"
                value={form.__note ?? ''}
                onChange={(e) => setForm({ ...form, __note: e.target.value })}
              />
              <button className="primary" onClick={() => save(cr.criterion_id)}>
                Save draft
              </button>
            </div>
          )}
          <ul>
            {(data.data?.drafts ?? [])
              .filter((d: any) => d.criterion_id === cr.criterion_id)
              .slice(0, 5)
              .map((d: any) => (
                <li key={d.id}>
                  <small>
                    <code>{d.id}</code> · {when(d.created_at)} · on v{d.base_version} ·{' '}
                    {JSON.stringify(d.settings)}
                    {d.note ? ` · ${d.note}` : ''}
                  </small>{' '}
                  <button
                    onClick={() => {
                      const reason = window.prompt('Why is this draft ready for the leaderboard?');
                      if (reason) act(`/grader-drafts/${d.id}/propose`, { reason }, 'Proposed; a second person approves.');
                    }}
                  >
                    Ready for leaderboard…
                  </button>
                </li>
              ))}
          </ul>
        </div>
      ))}
      {(data.data?.promotions ?? []).length > 0 && (
        <>
          <h4>Proposals</h4>
          <ul>
            {data.data.promotions.map((p: any) => (
              <li key={p.id}>
                <code>{p.id}</code> {p.criterion_id} from draft <code>{p.draft_id}</code> · {p.reason} ·{' '}
                <Badge state={p.state === 'approved' ? 'ready' : p.state === 'rejected' ? 'failed' : 'draft'} label={p.state} />
                {p.fix_version && <small> → {p.configuration_id} v{p.fix_version}</small>}
                {p.state === 'proposed' && (
                  <>
                    {' '}
                    <button onClick={() => act(`/grader-promotions/${p.id}/decide`, { approve: true, reason: 'approved' }, 'Approved: a new grader version was created and tested.')}>
                      Approve
                    </button>{' '}
                    <button onClick={() => act(`/grader-promotions/${p.id}/decide`, { approve: false, reason: 'rejected' }, 'Rejected.')}>
                      Reject
                    </button>
                    <small> (a different person from the proposer)</small>
                  </>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      <Failure error={failure} />
    </details>
  );
}

export function RunDrafts({ run }: { run: any }) {
  const { ws, say } = useGym();
  const drafts = useData<any>(`${wsBase(ws)}/projects/${run.project_id}/grader-drafts`);
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [cmp, setCmp] = useState<any>(null);
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const draftPasses = (run.passes ?? []).filter((p: any) => p.is_draft);
  async function rescore() {
    if (!window.confirm('Re-score this run with the chosen drafts? No agent is called; judge blocks call their judge (live judges spend under their approval). The run’s reported score does not change.')) return;
    setBusy(true);
    setFailure(null);
    try {
      setCmp(await send('POST', `${wsBase(ws)}/runs/${run.id}/draft-rescore`, { draft_ids: picked }));
      say('Draft re-score done.');
    } catch (e) {
      setFailure(e as GymApiError);
    } finally {
      setBusy(false);
    }
  }
  async function show(passId: string) {
    setFailure(null);
    try {
      setCmp(await get(`${wsBase(ws)}/runs/${run.id}/draft-passes/${passId}`));
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  if (!['completed', 'cancelled'].includes(run.state)) return null;
  return (
    <details className="card">
      <summary>Re-score with drafts (grader experiments)</summary>
      <ul>
        {(drafts.data?.drafts ?? []).map((d: any) => (
          <li key={d.id}>
            <label className="row">
              <input
                type="checkbox"
                checked={picked.includes(d.id)}
                onChange={(e) => setPicked(e.target.checked ? [...picked, d.id] : picked.filter((x) => x !== d.id))}
              />
              <code>{d.id}</code> {d.criterion_id} · {when(d.created_at)} {d.note ? `· ${d.note}` : ''}
            </label>
          </li>
        ))}
      </ul>
      {(drafts.data?.drafts ?? []).length === 0 && <small>No drafts yet: make one on the project page (Evaluators).</small>}
      <button className="primary" disabled={!picked.length || busy} onClick={rescore}>
        {busy ? 'Re-scoring…' : 'Re-score with drafts'}
      </button>
      {draftPasses.length > 0 && (
        <p>
          Earlier draft passes:{' '}
          {draftPasses.map((p: any) => (
            <button key={p.id} onClick={() => show(p.id)}>
              pass {p.pass}
            </button>
          ))}
        </p>
      )}
      <Failure error={failure} />
      {cmp && (
        <>
          <p>
            Draft pass {cmp.draft_pass} vs reported pass {cmp.base_pass}: {cmp.changed} verdict(s) changed ·{' '}
            <small>{cmp.note}</small>
          </p>
          <div className="table-wrap scroll" style={{ maxHeight: 360 }}>
            <table>
              <thead>
                <tr>
                  <th>Episode</th>
                  <th>Criterion</th>
                  <th>Reported</th>
                  <th>Draft</th>
                  <th>Benchmark review</th>
                </tr>
              </thead>
              <tbody>
                {cmp.rows.map((r: any) => (
                  <tr key={r.episode_id + r.criterion_id} className={r.changed ? 'no' : ''}>
                    <td>{r.episode_id}</td>
                    <td>{r.criterion_id}</td>
                    <td>{r.base ?? '—'}</td>
                    <td>{r.draft}</td>
                    <td>
                      <small>
                        {r.sme.map((x: any) => `${x.decision}${x.criterion_id ? ` (${x.criterion_id})` : ''}`).join('; ') || '—'}
                      </small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </details>
  );
}
