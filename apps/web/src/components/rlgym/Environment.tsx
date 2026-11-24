'use client';

import { useState } from 'react';
import { short } from './api';
import { Badge, useData } from './ui';

// E-005 §2: the suite's environment in one plain line, what scores each criterion (D-034, on the project page), and a
// collapsed Experiment section: pin another environment version (one person, with a reason; only versions that need
// no re-authoring; others greyed with the reason). Any experiment marks the suite "not leaderboard-eligible".
export function EnvironmentSummary({
  data,
  draft,
  act,
  path,
}: {
  data: any;
  draft: boolean;
  act: (method: any, url: string, body: any, okMessage: string) => any;
  path: string;
}) {
  const opts = useData<any>(`${path}/environment-options`);
  const [pick, setPick] = useState<Record<string, string>>({});
  const [reason, setReason] = useState('');
  const anyUnbound = data.bindings.some((b: any) => !b.ok);
  return (
    <section className="card">
      {data.bindings.map((b: any) => {
        const o = (opts.data?.bindings ?? []).find((x: any) => x.alias === b.alias);
        const cur = o?.versions.find((v: any) => v.version_id === b.binds_now);
        return (
          <div key={b.alias}>
            <p>
              <strong>Data:</strong> {short(b.binds_now)}
              {cur?.cases ? ` · ${cur.cases} cases` : ''} ·{' '}
              {b.rule_label?.toLowerCase().includes('pinned')
                ? `pinned to this version`
                : 'follows the newest qualified version of this data'}
              {o?.experiment && <Badge state="draft" label="Experiment: not leaderboard-eligible" />}
              {o?.legacy_pin && <Badge state="draft" label="Experiment?" />}
            </p>
            {o?.legacy_pin && (
              <small>
                This suite pins a version from before experiments were marked. It is left as it is; it isn&rsquo;t
                counted as an experiment unless you pin again here.
              </small>
            )}
            {anyUnbound && !b.ok && (
              <p className="no">
                The project rule can&rsquo;t bind: {b.reason_unbound}. See Advanced: binding rules below.
              </p>
            )}
            <details>
              <summary>Experiment: pin another environment version</summary>
              <small>
                One person, with a reason. Only versions that are built and qualified and need no re-authoring can be
                chosen. Pinning marks this suite &ldquo;Experiment: not leaderboard-eligible&rdquo;. Changing the
                project&rsquo;s own rule stays a two-person override. Not checked yet: {o?.not_checked}.
              </small>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Version</th>
                      <th>Cases</th>
                      <th>Can be used?</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(o?.versions ?? []).map((v: any) => (
                      <tr key={v.version_id} className={v.selectable ? '' : 'muted'}>
                        <td style={{ textAlign: 'left' }}>
                          <label className="row">
                            <input
                              type="radio"
                              name={`pin-${b.alias}`}
                              disabled={!draft || !v.selectable}
                              checked={pick[b.alias] === v.version_id}
                              onChange={() => setPick({ ...pick, [b.alias]: v.version_id })}
                            />
                            {short(v.version_id)} {v.current && <small>(current)</small>}
                          </label>
                        </td>
                        <td>{v.cases ?? '—'}</td>
                        <td style={{ textAlign: 'left' }}>
                          {v.selectable ? 'Yes' : <small className="no">{v.reasons.join('; ')}</small>}
                          {v.warnings.map((w: string) => (
                            <small key={w}>{w}</small>
                          ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {draft && (
                <div className="row">
                  <input
                    aria-label="Reason for the experiment"
                    placeholder="Reason (required)"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                  <button
                    className="primary"
                    disabled={!pick[b.alias] || !reason.trim()}
                    onClick={() =>
                      act(
                        'PATCH',
                        path,
                        {
                          bindings: [
                            {
                              alias: b.alias,
                              rule_kind: 'pinned',
                              pinned_version_id: pick[b.alias],
                              source: 'experiment',
                              reason: reason.trim(),
                            },
                          ],
                        },
                        'Pinned as an experiment; this suite is not leaderboard-eligible.',
                      )
                    }
                  >
                    Save (pin as experiment)
                  </button>
                  {o?.experiment && (
                    <button
                      onClick={() =>
                        act(
                          'PATCH',
                          path,
                          { bindings: [{ alias: b.alias, rule_kind: 'project_rule' }] },
                          'Back on the project rule.',
                        )
                      }
                    >
                      Use the project rule again
                    </button>
                  )}
                </div>
              )}
            </details>
          </div>
        );
      })}
      <small>
        Graders: each criterion&rsquo;s &ldquo;Scored by&rdquo; and how it&rsquo;s scored is on the project page
        (Evaluators) and, for a run, on its run page and report.
      </small>
    </section>
  );
}
