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
      {d?.latest_run?.placeholder_graded && (
        <p>
          <strong className="no">TEST — graded on placeholder rules, not valid as a result</strong>
        </p>
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
                      <td className={cs.full_marks ? 'ok' : cs.awaiting ? '' : 'no'}>
                        {cs.awaiting
                          ? `not graded: ${cs.awaiting.status.replace('_', ' ')} (${cs.awaiting.reasons.join('; ')})`
                          : cs.points}
                      </td>
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
      <LookupBaseline path={path} />
      <BulletinBlind path={path} />
      <ProbeInvents path={path} />
    </section>
  );
}

// G4 (E-011 §3): the no-AI lookup baseline. A fixed decision table over the case's records is played through each
// task's procedure and scored against the true references. Above the gate, the cases don't need reasoning (G-01).
function LookupBaseline({ path }: { path: string }) {
  const { say } = useGym();
  const data = useData<any>(`${path}/lookup-run`);
  const [gate, setGate] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const d = data.data;
  const last = d?.latest_run;
  const value = gate === '' ? String(d?.default_threshold_percent ?? 60) : gate;
  async function run() {
    setBusy(true);
    setFailure(null);
    try {
      await send('POST', `${path}/lookup-run`, { threshold_percent: Number(value) });
      say('Lookup baseline finished.');
      data.reload();
    } catch (e) {
      setFailure(e as GymApiError);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card">
      <div className="between">
        <div>
          <h3>Lookup baseline (G-01)</h3>
          <small>
            A fixed decision table over each case&rsquo;s records, with no model, played through the task&rsquo;s steps
            and scored against the true references. If it scores above the gate, the cases don&rsquo;t need
            reasoning. Shown on each run&rsquo;s Verification tab.
          </small>
        </div>
        <div className="row">
          <label>
            Gate (%)
            <input
              type="number"
              min={0}
              max={100}
              value={value}
              onChange={(e) => setGate(e.target.value)}
              style={{ width: 70 }}
            />
          </label>
          <button className="primary" onClick={run} disabled={busy}>
            {busy ? 'Running…' : 'Run lookup baseline'}
          </button>
        </div>
      </div>
      <Failure error={failure} />
      {last && (
        <>
          <p>
            <Badge
              state={last.summary.gate.passed ? 'ready' : 'failed'}
              label={`${last.summary.points_percent}% of points · gate ${last.summary.gate.threshold_percent}% · ${
                last.summary.gate.passed ? 'needs reasoning' : 'a lookup solves it'
              }`}
            />{' '}
            <small>
              Full marks on {last.summary.full_marks} of {last.summary.cases} cases · right decision on{' '}
              {last.summary.decisions_right} · {when(last.created_at)} · {last.lookup}
            </small>
          </p>
          <details>
            <summary>Cases</summary>
            <table>
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Lookup decided</th>
                  <th>Reference</th>
                  <th>Points</th>
                </tr>
              </thead>
              <tbody>
                {last.cases
                  .filter((cs: any) => !cs.skipped)
                  .map((cs: any) => (
                    <tr key={`${cs.task_id}:${cs.case_id}`}>
                      <td>
                        <code>{cs.case_id}</code>
                      </td>
                      <td>{Object.values(cs.lookup).join(' · ')}</td>
                      <td>{Object.values(cs.truth).join(' · ')}</td>
                      <td className={cs.full_marks ? 'ok' : 'no'}>{cs.points}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </section>
  );
}

// G-02 (Studio generator 2.1.0): on rule-change cases the honest baseline applies the starting rules correctly and never
// reads the bulletin. The cases need the bulletin only if it gets few of them right (default gate 40%).
function BulletinBlind({ path }: { path: string }) {
  const { say } = useGym();
  const data = useData<any>(`${path}/bulletin-blind-run`);
  const [gate, setGate] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const last = data.data?.latest_run;
  const value = gate === '' ? String(data.data?.default_threshold_percent ?? 40) : gate;
  async function run() {
    setBusy(true);
    setFailure(null);
    try {
      await send('POST', `${path}/bulletin-blind-run`, { threshold_percent: Number(value) });
      say('Bulletin-blind baseline finished.');
      data.reload();
    } catch (e) {
      setFailure(e as GymApiError);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card">
      <div className="between">
        <div>
          <h3>Bulletin-blind baseline (G-02)</h3>
          <small>
            The reference approach on the starting rules, never reading the bulletin, on the rule-change cases only;
            scored against the answer with the bulletin. Above the gate, the cases don&rsquo;t need the bulletin.
          </small>
        </div>
        <div className="row">
          <label>
            Gate (%)
            <input type="number" min={0} max={100} value={value} onChange={(e) => setGate(e.target.value)} style={{ width: 70 }} />
          </label>
          <button className="primary" onClick={run} disabled={busy}>
            {busy ? 'Running…' : 'Run bulletin-blind baseline'}
          </button>
        </div>
      </div>
      <Failure error={failure} />
      {last && (
        <p>
          <Badge
            state={last.summary.gate.passed ? 'ready' : 'failed'}
            label={`${last.summary.right_percent}% right on ${last.summary.cases} rule-change cases · gate ${last.summary.gate.threshold_percent}%`}
          />{' '}
          <small>
            {last.summary.points_percent}% of points · {when(last.created_at)}
            {last.placeholder_graded ? ' · TEST — graded on placeholder rules, not valid as a result' : ''}
          </small>
        </p>
      )}
    </section>
  );
}

// Grader probe (verification only, never a run or a model): the reference agent's episode plus one audit-trail id the
// environment never returned. evidence_faithfulness must fail as CRITICAL on every gradable case.
function ProbeInvents({ path }: { path: string }) {
  const { say } = useGym();
  const data = useData<any>(`${path}/probe-invents-run`);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const last = data.data?.latest_run;
  async function run() {
    setBusy(true);
    setFailure(null);
    try {
      await send('POST', `${path}/probe-invents-run`, {});
      say('Probe: invents evidence finished.');
      data.reload();
    } catch (e) {
      setFailure(e as GymApiError);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card">
      <div className="between">
        <div>
          <h3>Probe: invents evidence</h3>
          <small>
            A grader check, not a model: the reference approach with one audit-trail id the environment never
            returned. Evidence faithfulness must fail as critical on every case.
          </small>
        </div>
        <button className="primary" onClick={run} disabled={busy}>
          {busy ? 'Running…' : 'Run probe: invents evidence'}
        </button>
      </div>
      <Failure error={failure} />
      {last && (
        <p>
          <Badge
            state={last.summary.passed ? 'ready' : 'failed'}
            label={`caught as critical on ${last.summary.caught} of ${last.summary.cases} cases`}
          />{' '}
          <small>
            {when(last.created_at)}
            {last.placeholder_graded ? ' · TEST — graded on placeholder rules, not valid as a result' : ''}
          </small>
        </p>
      )}
    </section>
  );
}
