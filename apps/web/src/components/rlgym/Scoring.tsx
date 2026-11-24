'use client';

// D-034: "Scored by" and "How it's scored" for one criterion, from the RL Gym's description of the grader that runs
// (project page: what binds now; run page and report: what the run used).

export function ScoredBy({ s }: { s: any }) {
  if (!s) return <span className="no">Unknown scorer</span>;
  return <span className={s.scored_by?.startsWith('Unknown') ? 'no' : undefined}>{s.scored_by}</span>;
}

export function HowScored({ s }: { s: any }) {
  if (!s) return null;
  return (
    <details>
      <summary>How it&rsquo;s scored</summary>
      {s.checks?.length > 0 && (
        <ul>
          {s.checks.map((c: any) => (
            <li key={c.id}>
              <code>{c.id}</code> · {c.what}
              {c.share_percent ? <small> {c.share_percent}% of the criterion</small> : null}
            </li>
          ))}
        </ul>
      )}
      {s.evidence?.length > 0 && <small>Reads: {s.evidence.join('; ')}.</small>}
      <small>
        Expected values:{' '}
        {s.expected_values ?? 'none (the checks need no expected value)'}.
      </small>
      {s.points && (
        <small>
          S7 points: pass {s.points.anchors.pass} · partial {s.points.anchors.partial} · fail{' '}
          {s.points.anchors.fail} (weight {s.points.weight})
          {s.points.critical ? ' · critical: a fail fails the task' : ''}.
        </small>
      )}
      {(s.judges ?? []).map((j: any) => (
        <div key={j.block_id} className="card">
          <strong>LLM judge: {j.model}</strong>
          <small>
            {j.live ? `live, under approval ${j.approval}` : 'no active judge approval: the mock judge is used'}{' '}
            · pass at score ≥ {j.threshold}
            {j.share_percent ? ` · decides ${j.share_percent}% of the criterion` : ''}
          </small>
          <small>System prompt</small>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{j.system_prompt}</pre>
          <small>Prompt</small>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{j.prompt}</pre>
        </div>
      ))}
      {s.grader_sha256 && <small>grader {String(s.grader_sha256).slice(0, 12)}</small>}
      {s.frozen?.grader_sha256 && <small>frozen grader {String(s.frozen.grader_sha256).slice(0, 12)}</small>}
    </details>
  );
}
