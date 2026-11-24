'use client';

import { useState } from 'react';
import { GymApiError, send, when, wsBase } from './api';
import { Badge, Failure, Loading, useData, useGym } from './ui';

// E-007 phase 1: the run's verification report, in shadow mode (it reports; it blocks nothing).
const TONE: Record<string, string> = {
  PASS: 'ready',
  FAIL: 'failed',
  INSUFFICIENT_EVIDENCE: 'draft',
  NOT_APPLICABLE: 'draft',
  ERROR: 'failed',
};
const STATUS: Record<string, string> = {
  provisional: 'Provisional',
  verified: 'Verified',
  mismatch: 'Mismatch',
  withheld: 'Withheld',
};

export function Verification({ runId }: { runId: string }) {
  const { ws } = useGym();
  const path = `${wsBase(ws)}/runs/${runId}/verification`;
  const data = useData<any>(path);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<GymApiError | null>(null);
  async function rebuild() {
    setBusy(true);
    setFailure(null);
    try {
      await send('POST', path, {});
      data.reload();
    } catch (e) {
      setFailure(e as GymApiError);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Loading data={data.data} error={data.error}>
      {() => {
        const r = data.data?.report;
        return (
          <section>
            <div className="between">
              <div>
                <h3>Verification</h3>
                <small>
                  Shadow mode: this report checks whether the run can be trusted. It blocks nothing
                  yet.
                </small>
              </div>
              <button onClick={rebuild} disabled={busy}>
                {busy ? 'Checking…' : r ? 'Check again' : 'Check this run'}
              </button>
            </div>
            <Failure error={failure} />
            {!r && <p>No verification report yet. Reports are made when a run completes.</p>}
            {r && (
              <>
                <div className="card">
                  <strong>
                    Score {r.score ?? '—'} ·{' '}
                    <Badge
                      state={r.status === 'mismatch' ? 'failed' : 'draft'}
                      label={STATUS[r.status] ?? r.status}
                    />
                  </strong>
                  <small>
                    {r.mode} · profile {r.profile} · pass {r.pass?.number ?? '—'} · checked{' '}
                    {when(r.created_at)} · {r.header_note}
                  </small>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Check</th>
                        <th>Outcome</th>
                        <th>What it found</th>
                      </tr>
                    </thead>
                    <tbody>
                      {r.checks.map((c: any) => (
                        <tr key={c.id}>
                          <td style={{ textAlign: 'left' }}>
                            <code>{c.id}</code> {c.name}
                          </td>
                          <td>
                            <Badge state={TONE[c.outcome] ?? 'draft'} label={c.shown_as} />
                          </td>
                          <td style={{ textAlign: 'left' }}>
                            {c.detail}
                            {Object.keys(c.evidence ?? {}).length > 0 && (
                              <details>
                                <summary>Evidence</summary>
                                <pre style={{ whiteSpace: 'pre-wrap' }}>
                                  {JSON.stringify(c.evidence, null, 2)}
                                </pre>
                              </details>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <h4>Regression fixtures</h4>
                <small>
                  Synthetic KYC episodes the independent assertions must judge correctly. Their
                  expected outcomes await an SME.
                </small>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Fixture</th>
                        <th>Assertions</th>
                        <th>next_action v1 / v2 (D-041)</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(r.fixtures ?? []).map((f: any) => (
                        <tr key={f.id}>
                          <td style={{ textAlign: 'left' }}>
                            <code>{f.id}</code> {f.title}
                            <small>{f.shows}</small>
                          </td>
                          <td style={{ textAlign: 'left' }}>
                            {Object.entries(f.assertions)
                              .map(([k, v]) => `${k.replace('KYC.', '')} ${v}`)
                              .join(' · ')}
                          </td>
                          <td>
                            {f.next_action.v1} / {f.next_action.v2_d041}
                            {f.v1_mismatch && <Badge state="failed" label="Mismatch under v1" />}
                          </td>
                          <td>
                            <small>{f.status}</small>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>
        );
      }}
    </Loading>
  );
}
