'use client';

import { useState } from 'react';
import { GymApiError, send, when, wsBase } from './api';
import { Badge, Failure, useData, useGym } from './ui';

// E-007 §7.2: the reference agent. Each task's approach (from its S5 steps; decisions from the case's hidden reference
// answers) is confirmed once by a person (owner default: an Admin for the SME). V-04: the agent must score full marks
// on every task; V-01: a second run on a fresh instance must match step by step. No model is called.
export function ReferencePanel({ path }: { path: string }) {
  const { ws, say } = useGym();
  const data = useData<any>(`${path}/reference`);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<GymApiError | null>(null);
  async function confirm(t: any, verdict: string) {
    setFailure(null);
    try {
      await send('POST', `${wsBase(ws)}/task-imports/${t.task_import_id}/reference-confirmation`, {
        verdict,
        note: note[t.task_import_id],
      });
      say(verdict === 'confirmed' ? 'Reference approach confirmed.' : 'Recorded as not right.');
      data.reload();
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  async function run() {
    setBusy(true);
    setFailure(null);
    try {
      await send('POST', `${path}/reference-run`, { replay: true, cases_per_task: 3 });
      say('Reference agent run finished.');
      data.reload();
    } catch (e) {
      setFailure(e as GymApiError);
    } finally {
      setBusy(false);
    }
  }
  const d = data.data;
  const results = Object.fromEntries((d?.latest_run?.tasks ?? []).map((t: any) => [`${t.task_id}:${t.revision}`, t]));
  return (
    <section>
      <div className="between">
        <div>
          <h3>Reference agent</h3>
          <small>
            A deterministic agent that follows each task&rsquo;s S5 steps with the case&rsquo;s hidden reference answers, through the
            same tools and hidden IDs a model gets. V-04: it must score full marks; V-01: a second run on a fresh
            instance must match. No model is called; judge lines use the local mock judge.
          </small>
        </div>
        <button className="primary" onClick={run} disabled={busy}>
          {busy ? 'Running…' : 'Run reference agent'}
        </button>
      </div>
      <Failure error={failure} />
      {d?.latest_run && (
        <small>
          Last run {when(d.latest_run.created_at)} on {d.latest_run.environment} · {d.latest_run.judge}
        </small>
      )}
      {(d?.tasks ?? []).map((t: any) => {
        const r = results[`${t.task_id}:${t.revision}`];
        return (
          <div key={t.task_import_id} className="card">
            <div className="between">
              <strong>
                Task {t.task_id.slice(0, 8)} r{t.revision}
              </strong>
              {t.confirmation ? (
                <Badge
                  state={t.confirmation.verdict === 'confirmed' ? 'ready' : 'failed'}
                  label={`${t.confirmation.verdict === 'confirmed' ? 'Confirmed' : 'Not right'} · ${when(t.confirmation.decided_at)}`}
                />
              ) : (
                <Badge state="draft" label="Not confirmed" />
              )}
            </div>
            <details>
              <summary>Reference approach</summary>
              <pre style={{ whiteSpace: 'pre-wrap' }}>{t.summary.text}</pre>
              <div className="row">
                <button className="primary" onClick={() => confirm(t, 'confirmed')}>
                  Confirm
                </button>
                <input
                  placeholder="What's not right (required for Not right)"
                  value={note[t.task_import_id] ?? ''}
                  onChange={(e) => setNote({ ...note, [t.task_import_id]: e.target.value })}
                />
                <button onClick={() => confirm(t, 'not_right')} disabled={!(note[t.task_import_id] ?? '').trim()}>
                  Not right
                </button>
              </div>
              {t.confirmation?.note && <small>Note: {t.confirmation.note}</small>}
            </details>
            {r && (
              <table>
                <thead>
                  <tr>
                    <th>Case</th>
                    <th>Points</th>
                    <th>Replay (V-01)</th>
                    <th>Where it couldn&rsquo;t follow the task</th>
                  </tr>
                </thead>
                <tbody>
                  {r.cases.map((cs: any) => (
                    <tr key={cs.case_id}>
                      <td>
                        <code>{cs.case_id}</code>
                      </td>
                      <td className={cs.full_marks ? 'ok' : 'no'}>{cs.points}</td>
                      <td>
                        {cs.replay
                          ? cs.replay.observations_match && cs.replay.end_state_match && cs.replay.verdicts_match
                            ? 'identical'
                            : `differs${cs.replay.first_different_step ? ` from step ${cs.replay.first_different_step}` : ''}`
                          : '—'}
                      </td>
                      <td style={{ textAlign: 'left' }}>
                        <small>{(cs.failures ?? []).map((f: any) => f.reason).join('; ') || '—'}</small>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        );
      })}
    </section>
  );
}
