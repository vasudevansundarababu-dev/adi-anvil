import { useState } from 'react';

type Evidence = {
  id: string;
  output: string;
  outcome: string;
  criteria: { id: string; label: string }[];
  capabilities: string[];
};
export default function FindingComposer({ base, advisor }: { base: string; advisor: string }) {
  const [episode, setEpisode] = useState(''),
    [evidence, setEvidence] = useState<Evidence | null>(null),
    [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [busy, setBusy] = useState(false);
  async function request(path: string, body?: unknown) {
    const csrf =
      document.cookie
        .split('; ')
        .find((x) => x.startsWith('anvil_csrf='))
        ?.split('=')[1] || '';
    const r = await fetch('/api/v1' + base + path, {
      method: body ? 'POST' : 'GET',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf,
        'Idempotency-Key': crypto.randomUUID(),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const j = await r.json();
    if (!r.ok)
      throw new Error(
        typeof j.error?.message === 'string' ? j.error.message : JSON.stringify(j.error?.message),
      );
    return j.data;
  }
  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="card">
      <summary>Create an evidence-linked finding</summary>
      <p>
        Use a finalized episode ID from the run console. Describe observable behavior separately
        from possible explanations.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () =>
            setEvidence(await request('/episodes/' + encodeURIComponent(episode) + '/evidence')),
          );
        }}
      >
        <label htmlFor="finding-episode">Finalized episode ID</label>
        <input
          id="finding-episode"
          value={episode}
          onChange={(e) => {
            setEpisode(e.target.value);
            setEvidence(null);
          }}
          required
        />
        <button disabled={busy}>Load reviewed output</button>
      </form>
      {evidence && (
        <>
          <h3>Reviewed output · {evidence.outcome}</h3>
          <pre>{evidence.output}</pre>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              void run(async () => {
                await request('/findings', {
                  title: String(f.get('title')),
                  episode_id: evidence.id,
                  observation: String(f.get('observation')),
                  hypothesis: String(f.get('hypothesis')) || null,
                  alternatives: String(f.get('alternatives')).split('\n').filter(Boolean),
                  confidence: String(f.get('confidence')),
                  criterion: String(f.get('criterion')),
                  capability: String(f.get('capability')),
                  output_quote: String(f.get('quote')),
                  advisor_id: advisor,
                });
                setEvidence(null);
                setMessage(
                  'Draft finding saved. Refresh and submit it for independent technical review.',
                );
              });
            }}
          >
            <label htmlFor="finding-title">Title</label>
            <input id="finding-title" name="title" required />
            <label htmlFor="finding-observation">Observed behavior</label>
            <textarea id="finding-observation" name="observation" minLength={10} required />
            <label htmlFor="finding-quote">Verbatim output evidence</label>
            <textarea id="finding-quote" name="quote" minLength={3} required />
            <label htmlFor="finding-criterion">Rubric criterion</label>
            <select id="finding-criterion" name="criterion">
              {evidence.criteria.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.id} · {c.label}
                </option>
              ))}
            </select>
            <label htmlFor="finding-capability">Task capability</label>
            <select id="finding-capability" name="capability">
              {evidence.capabilities.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
            <label htmlFor="finding-hypothesis">Possible explanation (optional hypothesis)</label>
            <textarea id="finding-hypothesis" name="hypothesis" />
            <label htmlFor="finding-alternatives">Alternative explanations (one per line)</label>
            <textarea id="finding-alternatives" name="alternatives" />
            <label htmlFor="finding-confidence">Confidence in interpretation</label>
            <select id="finding-confidence" name="confidence">
              <option>unknown</option>
              <option>low</option>
              <option>medium</option>
              <option>high</option>
            </select>
            <button className="primary" disabled={busy}>
              Save finding draft
            </button>
          </form>
        </>
      )}
      {error && (
        <p role="alert" className="banner error">
          {error}
        </p>
      )}
      {message && (
        <p role="status" className="banner">
          {message}
        </p>
      )}
    </details>
  );
}
