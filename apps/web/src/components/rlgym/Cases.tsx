'use client';

import { useState } from 'react';
import { GymApiError, get } from './api';
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
