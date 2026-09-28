export default function ReportSummary({ content }: { content: Record<string, unknown> }) {
  const facts = content.facts as Record<string, number | string | null> | undefined;
  if (!facts) return null;
  return (
    <div>
      <p className="banner">
        Execution origin: {String(facts.origin).replaceAll('_', ' ')}. Descriptive custom-suite
        evidence only.
      </p>
      <div className="stats">
        <div>
          <strong>{facts.case_count}</strong>
          <small>Source cases</small>
        </div>
        <div>
          <strong>{facts.family_count}</strong>
          <small>Source families</small>
        </div>
        <div>
          <strong>{facts.valid}</strong>
          <small>Valid scored episodes</small>
        </div>
        <div>
          <strong>
            {facts.mean_score === null ? 'Not established' : Number(facts.mean_score).toFixed(2)}
          </strong>
          <small>Mean reviewed score / 100</small>
        </div>
      </div>
      <p>
        {facts.passes} pass; {facts.failures} fail; {facts.invalid} invalid; {facts.unscorable}{' '}
        unscorable; {facts.unknown} execution unknown; {facts.cancelled} cancelled; {facts.pending}{' '}
        pending.
      </p>
      <p className="muted">{facts.denominator_definition}</p>
      <p>{facts.limitations}</p>
      <p className="muted">
        No named benchmark comparison, institutional endorsement, human baseline, internal causal
        reasoning, improvement or commercial acceptance is established.
      </p>
    </div>
  );
}
