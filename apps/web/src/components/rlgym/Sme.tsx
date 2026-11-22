'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { GymApiError, send, wsBase } from './api';
import { Badge, Failure, Hash, Loading, useData, useGym } from './ui';

// Run page → SME review (SCREENS 3.39): choose episodes, send a batch to Authoring, follow the SMEs' decisions and act
// on them. SMEs work only in Authoring; decisions arrive from there.

export default function Sme({ runId }: { runId: string }) {
  const { ws, say, me } = useGym();
  const base = wsBase(ws);
  const add = useSearchParams().get('add');
  const data = useData<any>(`${base}/runs/${runId}/sme-review`);
  const [picked, setPicked] = useState<string[]>(add ? [add] : []);
  const [failedOnly, setFailedOnly] = useState(true);
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const live = (data.data?.batches ?? []).some((b: any) =>
    ['building', 'sent', 'in_review'].includes(b.state),
  );
  const { reload } = data;
  useEffect(() => {
    if (!live) return;
    const t = setInterval(reload, 3000);
    return () => clearInterval(t);
  }, [live, reload]);
  const canWrite = me.profile !== 'viewer';
  async function act(method: 'POST', path: string, body: object, message: string) {
    try {
      const out = await send(method, path, body);
      say(message);
      setFailure(null);
      reload();
      return out;
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  return (
    <Loading data={data.data} error={data.error}>
      {() => {
        const d = data.data;
        const rows = d.candidates.filter(
          (c: any) => !c.in_batch && (!failedOnly || !c.passed || c.id === add),
        );
        return (
          <div className="grid2 sme">
            <section className="card">
              <h3>
                SME review · {runId} · project {d.project_id}
              </h3>
              <small>Batches go to Authoring project {d.project_id}; SMEs decide there.</small>
              {!d.can_send && <p>SME review is available when the run is completed.</p>}
              <div className="toolbar">
                <label className="row">
                  <input
                    type="checkbox"
                    checked={failedOnly}
                    onChange={(e) => setFailedOnly(e.target.checked)}
                  />
                  Failed only
                </label>
                <button
                  className="primary"
                  disabled={!canWrite || !d.can_send || picked.length === 0}
                  onClick={async () => {
                    const out = await act(
                      'POST',
                      `${base}/runs/${runId}/sme-review-batches`,
                      { episode_ids: picked },
                      'Batch built; sending to Authoring.',
                    );
                    if (out) setPicked([]);
                  }}
                >
                  Send {picked.length} to SME review
                </button>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Include</th>
                      <th>Episode</th>
                      <th>Model</th>
                      <th>Score</th>
                      <th>Suspected cause</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.length === 0 && (
                      <tr>
                        <td colSpan={5} style={{ textAlign: 'left' }}>
                          No episodes to send.
                        </td>
                      </tr>
                    )}
                    {rows.map((c: any) => (
                      <tr key={c.id}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`Include ${c.id}`}
                            disabled={!canWrite}
                            checked={picked.includes(c.id)}
                            onChange={(e) =>
                              setPicked((p) =>
                                e.target.checked ? [...p, c.id] : p.filter((x) => x !== c.id),
                              )
                            }
                          />
                        </td>
                        <td style={{ textAlign: 'left' }}>
                          <Link href={`/gym/runs/${runId}/episodes/${c.id}?from=sme`}>
                            {c.task_id} r{c.task_revision} · {c.case_id} · a{c.attempt}
                          </Link>
                        </td>
                        <td>{c.system_id}</td>
                        <td>
                          {c.score} · {c.passed ? 'passed' : 'failed'}
                        </td>
                        <td>{c.likely_cause ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Failure error={failure} />
            </section>
            <div>
              {d.batches.length === 0 && (
                <section className="card">
                  <p>No batch yet. Tick episodes and send them to SME review.</p>
                </section>
              )}
              {d.batches.map((b: any) => (
                <section className="card" key={b.id}>
                  <div className="between">
                    <h4>
                      Batch {b.id} · {b.items.length} items
                    </h4>
                    <Badge
                      state={
                        b.state === 'decided' || b.state === 'validated'
                          ? 'ready'
                          : b.state === 'building'
                            ? 'draft'
                            : 'queued'
                      }
                      label={b.state.replace('_', ' ')}
                    />
                  </div>
                  <small>
                    package <Hash value={b.batch_sha256} />
                    {b.forge_batch_ref && ` · Authoring ${b.forge_batch_ref}`}
                  </small>
                  <ol className="steps">
                    <li data-done={b.progress.sent ? 'yes' : undefined}>Sent to Authoring</li>
                    <li data-done={b.progress.decided > 0 ? 'yes' : undefined}>
                      SMEs reviewing ({b.progress.decided} of {b.progress.total} decided
                      {b.progress.deciders.length ? ` · ${b.progress.deciders.join(', ')}` : ''})
                    </li>
                    <li data-done={b.progress.all_decided ? 'yes' : undefined}>
                      All items decided
                    </li>
                    <li data-done={b.progress.follow_ups_done ? 'yes' : undefined}>
                      Follow-ups done
                    </li>
                  </ol>
                  {b.reviewed_scores.length > 0 && (
                    <div className="row">
                      {b.reviewed_scores.map((r: any) => (
                        <small key={r.system_id}>
                          {r.system_id}: {r.automated} → {r.reviewed} · automated → reviewed ·{' '}
                          {r.excluded} excluded
                        </small>
                      ))}
                    </div>
                  )}
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Episode</th>
                          <th>SME decision</th>
                          <th>In reviewed score</th>
                          <th>Follow-up</th>
                        </tr>
                      </thead>
                      <tbody>
                        {b.items.map((i: any) => (
                          <tr key={i.id}>
                            <td style={{ textAlign: 'left' }}>
                              <Link href={`/gym/runs/${runId}/episodes/${i.episode_id}?from=sme`}>
                                {i.task_id} r{i.task_revision}
                              </Link>
                              <small>
                                {i.system_id} · {i.case_id} · {i.score ?? '—'}
                              </small>
                            </td>
                            <td style={{ textAlign: 'left' }}>
                              {i.decision_label ??
                                (b.state === 'building' ? 'Sending' : 'Awaiting SME decision')}
                              {i.rationale && <small>{i.rationale}</small>}
                              {i.decided_by && <small>{i.decided_by}</small>}
                            </td>
                            <td>
                              {i.decision ? (i.excluded_from_reviewed ? 'Excluded' : 'Kept') : '—'}
                            </td>
                            <td style={{ textAlign: 'left' }}>
                              <FollowUp
                                item={i}
                                canWrite={canWrite}
                                act={act}
                                base={base}
                                runId={runId}
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              ))}
              <small>
                The automated score never changes. The reviewed score leaves out episodes the SMEs
                found invalid; confirmed agent failures stay in.
              </small>
            </div>
          </div>
        );
      }}
    </Loading>
  );
}

function FollowUp({
  item,
  canWrite,
  act,
  base,
  runId,
}: {
  item: any;
  canWrite: boolean;
  act: any;
  base: string;
  runId: string;
}) {
  const f = item.follow_up ?? {};
  if (!item.decision) return <>—</>;
  if (item.decision === 'grader_wrong') {
    return item.fix ? (
      <span>
        Fixed in the RL Gym, no Studio inbox item: {item.fix.id} v{item.fix.version} ·{' '}
        {item.fix.state}
        <small>
          <Link href={`/gym/admin/evaluators`}>Evaluator page</Link> · Re-score is explicit (run ⋯
          Re-score…)
        </small>
      </span>
    ) : (
      <button
        disabled={!canWrite}
        onClick={() =>
          act(
            'POST',
            `${base}/sme-review-items/${item.id}/grader-fix`,
            {},
            'Fix version created with this episode as a known case.',
          )
        }
      >
        Create fix version ({item.criterion_id})
      </button>
    );
  }
  if (item.decision === 'task_correction') {
    if (item.validation) {
      return (
        <span>
          Validation run{' '}
          <Link href={`/gym/runs/${item.validation.run_id}`}>{item.validation.run_id}</Link> ·{' '}
          {item.validation.state}
          {item.validation.state === 'completed' &&
            ` · ${item.validation.result.replace('_', ' ')}`}
          {item.validation.criteria?.length > 0 && (
            <small>
              {item.validation.criteria
                .map((c: any) => `${c.criterion_id}: ${c.before} → ${c.after}`)
                .join('; ')}
            </small>
          )}
        </span>
      );
    }
    return item.corrected_revision ? (
      <button
        disabled={!canWrite}
        onClick={() =>
          act(
            'POST',
            `${base}/sme-review-items/${item.id}/validation-run`,
            {},
            'Validation run admitted.',
          )
        }
      >
        Start validation run (r{item.corrected_revision})
      </button>
    ) : (
      <span>{f.text}</span>
    );
  }
  if (item.inbox_item) {
    return (
      <span>
        {f.text} · {item.inbox_item.state}
      </span>
    );
  }
  return <span>{f.text ?? '—'}</span>;
}
