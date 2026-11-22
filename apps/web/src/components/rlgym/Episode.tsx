'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useState } from 'react';
import { GymApiError, send, wsBase } from './api';
import { Badge, Failure, Hash, Loading, useData, useGym } from './ui';

// Episode viewer (SCREENS 3.38): read-only, from the sealed evidence. Selecting a criterion highlights its nodes on the
// path and its steps on the timeline (rubric overlay).

const CAUSES: [string, string][] = [
  ['agent_failure', 'Agent failure'],
  ['task_defect', 'Task defect'],
  ['rubric_defect', 'Rubric defect'],
  ['grader_defect', 'Grader defect'],
  ['environment_defect', 'Environment defect'],
  ['infrastructure', 'Infrastructure'],
];

export default function Episode({ runId, episodeId }: { runId: string; episodeId: string }) {
  const { ws, me, say } = useGym();
  const from = useSearchParams().get('from');
  const base = wsBase(ws);
  const data = useData<any>(`${base}/episodes/${episodeId}`);
  const [selected, setSelected] = useState<string | null>(null);
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const back =
    from === 'report'
      ? { href: `/gym/runs/${runId}/report`, label: 'Back to report' }
      : from === 'sme'
        ? { href: `/gym/runs/${runId}/sme`, label: 'Back to SME review' }
        : { href: `/gym/runs/${runId}/episodes`, label: 'Back to episodes' };
  async function setCause(cause: string) {
    try {
      await send('PUT', `${base}/episodes/${episodeId}/suspected-cause`, { cause });
      say('Suspected cause saved (a suggestion until SMEs decide).');
      data.reload();
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  return (
    <Loading data={data.data} error={data.error}>
      {() => {
        const v = data.data;
        const e = v.episode;
        const crit = v.criteria.find((c: any) => c.criterion_id === selected);
        const hiNodes = new Set<string>(crit?.nodes ?? []);
        const hiSteps = new Set<number>(crit?.steps ?? []);
        return (
          <section className="viewer">
            <Link href={back.href}>← {back.label}</Link>
            <small>
              {e.project_name} · {e.run_name} ({e.run_id}) · Episodes · {v.model} v
              {e.system_version} · attempt {e.attempt} · read-only
            </small>
            <div className="between">
              <h3>
                {e.task_id} · r{e.task_revision} · {e.case_id}{' '}
                <Badge
                  state={e.state === 'scored' ? 'ready' : e.state}
                  label={e.state.replace('_', ' ')}
                />{' '}
                {v.score && (
                  <span>
                    {v.score.score} / 100 · {v.score.passed ? 'passed' : 'failed'}
                  </span>
                )}
                {v.safety && (
                  <span>
                    {' '}
                    safety · {v.safety.category_key} · {v.safety.outcome.replace(/_/g, ' ')}
                    {v.safety.critical ? ' · critical' : ''}
                  </span>
                )}
              </h3>
              <span>
                sealed <Hash value={v.sealed_sha256} />
              </span>
            </div>
            <small>{v.note}</small>
            <section className="card">
              <h4>Path taken</h4>
              <div className="graph" role="img" aria-label="Path over the workflow">
                {v.path.nodes.map((n: any, i: number) => (
                  <span key={n.id} className="graphrow">
                    <span
                      className="gnode"
                      data-s={n.failed ? 'failed' : n.taken ? 'taken' : 'skipped'}
                      data-hi={hiNodes.has(n.id) ? 'yes' : undefined}
                      title={`${n.calls} tool calls`}
                    >
                      {n.label}
                      {n.calls > 1 && <small> ×{n.calls}</small>}
                    </span>
                    {i < v.path.nodes.length - 1 && (
                      <span className="gedge" data-s={v.path.edges[i]?.taken ? 'taken' : 'skipped'}>
                        →
                      </span>
                    )}
                  </span>
                ))}
              </div>
              <small>{v.path.summary}</small>
            </section>
            <div className="grid2">
              <section className="card">
                <h4>Criteria</h4>
                <div className="chips">
                  {v.criteria.map((c: any) => (
                    <button
                      key={c.criterion_id}
                      className={selected === c.criterion_id ? 'primary' : undefined}
                      onClick={() =>
                        setSelected(selected === c.criterion_id ? null : c.criterion_id)
                      }
                    >
                      {c.criterion_id}{' '}
                      <Badge
                        state={
                          c.verdict === 'pass'
                            ? 'ready'
                            : c.verdict === 'blocked'
                              ? 'draft'
                              : 'failed'
                        }
                        label={c.verdict}
                      />
                    </button>
                  ))}
                </div>
                {crit && (
                  <dl className="kv">
                    <dt>Verdict</dt>
                    <dd>
                      {crit.verdict} · points {crit.points ?? '—'} · weight {crit.weight}
                      {crit.gate ? ' · gate' : ''}
                    </dd>
                    <dt>Evaluator</dt>
                    <dd>{crit.evaluator}</dd>
                    <dt>Graph nodes</dt>
                    <dd>{crit.nodes.join(', ') || '—'}</dd>
                    <dt>Evidence</dt>
                    <dd>
                      {(crit.detail ?? []).join('; ')}
                      <small>{(crit.evidence_refs ?? []).join(', ')}</small>
                    </dd>
                  </dl>
                )}
                {crit && (crit.block_lines ?? []).length > 0 && (
                  <table className="blocks">
                    <thead>
                      <tr>
                        <th>Block</th>
                        <th>Kind</th>
                        <th>Expected</th>
                        <th>Actual</th>
                        <th>Verdict</th>
                        <th>Code</th>
                      </tr>
                    </thead>
                    <tbody>
                      {crit.block_lines.map((l: any) => (
                        <tr key={l.block_id}>
                          <td>
                            <code>{l.block_id}</code>
                          </td>
                          <td>{l.kind}</td>
                          <td>
                            <code>{JSON.stringify(l.expected)}</code>
                          </td>
                          <td>
                            <code>{JSON.stringify(l.actual)}</code>
                          </td>
                          <td>
                            <Badge
                              state={
                                l.verdict === 'pass'
                                  ? 'ready'
                                  : l.verdict === 'blocked'
                                    ? 'draft'
                                    : 'failed'
                              }
                              label={l.verdict}
                            />
                          </td>
                          <td>{l.verdict === 'fail' ? <code>{l.on_fail}</code> : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>
              <section className="card">
                <h4>Investigate</h4>
                <label>
                  Suspected cause
                  <select
                    value={(e.likely_cause ?? '').replace(/ /g, '_')}
                    disabled={me.profile === 'viewer'}
                    onChange={(ev) => setCause(ev.target.value)}
                  >
                    <option value="">—</option>
                    {CAUSES.map(([k, l]) => (
                      <option key={k} value={k}>
                        {l}
                      </option>
                    ))}
                  </select>
                </label>
                <small>
                  {e.likely_cause
                    ? `${e.likely_cause} · ${e.likely_cause_source === 'rule' ? 'suggested by rule' : 'set by an RL engineer'}`
                    : 'No cause suggested'}
                  . A suggestion until SMEs decide in Authoring.
                </small>
                {v.sme && (
                  <p>
                    SME review {v.sme.batch_id}:{' '}
                    {v.sme.decision
                      ? `${v.sme.decision.replace(/_/g, ' ')} · ${v.sme.rationale}`
                      : v.sme.batch_state}
                  </p>
                )}
                {e.kind === 'case' && (
                  <Link href={`/gym/runs/${runId}/sme?add=${episodeId}`}>Add to SME review</Link>
                )}
                <Link
                  href={`/gym/projects/${e.project_id}/tasks/${e.task_id}?revision=${e.task_revision}`}
                >
                  View task
                </Link>
                <Failure error={failure} />
              </section>
            </div>
            <section className="card">
              <h4>Timeline</h4>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Step</th>
                      <th>Tool call</th>
                      <th>Result</th>
                      <th>Node</th>
                    </tr>
                  </thead>
                  <tbody>
                    {v.timeline.map((t: any) => (
                      <tr key={t.step} data-hi={hiSteps.has(t.step) ? 'yes' : undefined}>
                        <td>{t.step}</td>
                        <td style={{ textAlign: 'left' }}>
                          {t.tool}
                          <small>{JSON.stringify(t.args)}</small>
                        </td>
                        <td>
                          <Badge
                            state={t.status === 'completed' ? 'ready' : 'failed'}
                            label={t.status}
                          />
                          <small>{JSON.stringify(t.observation).slice(0, 140)}</small>
                        </td>
                        <td>{t.node ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <small>
                {v.timeline.length} tool calls · {v.timings?.wall_ms ?? '—'} ms · tokens{' '}
                {v.tokens.in}/{v.tokens.out}
                {v.attempts.length > 1 &&
                  ` · ${v.attempts.length} tries: ${v.attempts.map((a: any) => `${a.try} ${a.outcome}${a.note ? ` (${a.note})` : ''}`).join('; ')}`}
              </small>
            </section>
            <section className="card">
              <h4>Final output</h4>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Field</th>
                      <th>Output</th>
                      <th>Expected (reviewer only)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {v.output.fields.map((f: any) => (
                      <tr key={f.field} data-diff={f.in_expected && !f.matches ? 'yes' : undefined}>
                        <td style={{ textAlign: 'left' }}>{f.field}</td>
                        <td>{JSON.stringify(f.value) ?? '—'}</td>
                        <td>{f.in_expected ? JSON.stringify(f.expected) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <small>{v.output.expected_note}</small>
            </section>
          </section>
        );
      }}
    </Loading>
  );
}
