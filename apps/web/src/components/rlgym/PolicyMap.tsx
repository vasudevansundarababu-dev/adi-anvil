// D-056: what Authoring's policy_id_map did at reset. Per episode (from the sealed evidence) and per run (counts).

export function PolicyMapRecord({ record }: { record: any }) {
  if (!record) return null;
  return (
    <section className="card">
      <h4>
        Policy map: {record.applied ? 'applied' : 'warning'}
        {!record.applied && record.warning ? `: ${record.warning}` : ''}
      </h4>
      {record.applied ? (
        <ul>
          {record.rules.map((r: any) => (
            <li key={r.original}>
              S4 rule <code>{r.original}</code> shown to the agent as{' '}
              <strong>{r.shown.join(', ')}</strong>
            </li>
          ))}
        </ul>
      ) : (
        <p>S4 was shown to the agent exactly as authored.</p>
      )}
      <small>
        Map for {record.map_environment_version ?? '—'} · this run uses {record.environment_version}
        {record.unmapped?.length ? ` · not in the map: ${record.unmapped.join(', ')}` : ''}. The
        evidence keeps the original ids.
      </small>
    </section>
  );
}

export function PolicyMapSummary({ summary }: { summary: any }) {
  if (!summary) return null;
  return (
    <section className="card">
      <h3>Policy map</h3>
      <p>
        Applied in {summary.applied} episode{summary.applied === 1 ? '' : 's'} · warned in{' '}
        {summary.warned}
      </p>
      {summary.rules.map((r: any) => (
        <small key={r.original + r.shown.join()}>
          {r.original} → {r.shown.join(', ')}
        </small>
      ))}
      {summary.warnings.map((w: any) => (
        <small key={w.reason} className="no">
          {w.episodes} × {w.reason}
        </small>
      ))}
    </section>
  );
}
