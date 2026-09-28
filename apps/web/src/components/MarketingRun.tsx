import { useCallback, useEffect, useState } from 'react';
import Form from './Form';

type Readiness = {
  ready: boolean;
  missing_gates: string[];
  subject_hash?: string;
  connection_id?: string;
  connection_hash?: string;
  pricing_expires_at?: string;
};
type Detail = {
  readiness: Readiness;
  episode: {
    step: number;
    state: string;
    observation: { customers: number; total_spent_usd: number; remaining_budget_usd: number };
  } | null;
  calls: { step: number; status: string; error_code: string | null }[];
  budget: { reserved_micro_usd: number; settled_micro_usd: number } | null;
  billing_status: string;
};

async function request(path: string, body?: unknown, version?: number) {
  const response = await fetch('/api/v1' + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token':
        document.cookie
          .split('; ')
          .find((x) => x.startsWith('anvil_csrf='))
          ?.split('=')[1] || '',
      'Idempotency-Key': crypto.randomUUID(),
      ...(version === undefined ? {} : { 'If-Match': String(version) }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || 'Marketing request failed');
  return data.data;
}

export default function MarketingRun({
  base,
  id,
  version,
  state,
  admin,
  researcher,
  refresh,
}: {
  base: string;
  id: string;
  version: number;
  state?: string;
  admin: boolean;
  researcher: boolean;
  refresh: () => Promise<void>;
}) {
  const [detail, setDetail] = useState<Detail | null>(null),
    [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      setDetail(await request(base + '/runs/' + id + '/marketing'));
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  }, [base, id]);
  useEffect(() => {
    void load();
  }, [load, state]);
  useEffect(() => {
    if (!['queued', 'running'].includes(state || '')) return;
    const timer = setInterval(() => void load(), 3000);
    return () => clearInterval(timer);
  }, [load, state]);
  async function act(fn: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError('');
    try {
      await fn();
      setMessage(success);
      await load();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="12-week marketing execution">
      <h3>12-week marketing task · OpenAI gpt-6-sol</h3>
      <p>
        One episode, up to 13 responses: weekly decisions plus a final board memo. $100 cumulative
        API ceiling; at most $13 reserved for this run. The simulated campaign budget is separate.
      </p>
      <p>
        <a href="/help/marketing-run.html" target="_blank" rel="noreferrer">
          Setup and approval walkthrough
        </a>
      </p>
      {detail && (
        <>
          <p role="status">
            {detail.readiness.ready ? 'Ready for an explicit paid launch.' : 'Paid launch blocked.'}
          </p>
          <ul>
            {detail.readiness.missing_gates.map((gate) => (
              <li key={gate}>{gate.replaceAll('_', ' ')}</li>
            ))}
          </ul>
          {detail.episode && (
            <>
              <p>
                Response {Math.min(detail.episode.step, 13)} of 13 · {detail.episode.state}
              </p>
              <p>
                Simulated results: {detail.episode.observation.customers} customers · $
                {detail.episode.observation.total_spent_usd.toLocaleString()} spent · $
                {detail.episode.observation.remaining_budget_usd.toLocaleString()} remaining.
              </p>
              <ol>
                {detail.calls.map((call) => (
                  <li key={call.step}>
                    {call.step === 13 ? 'Final memo' : 'Week ' + call.step}: {call.status}
                    {call.error_code ? ' · ' + call.error_code : ''}
                  </li>
                ))}
              </ol>
            </>
          )}
          {detail.budget && (
            <p>
              API reservations retained: $
              {(detail.budget.reserved_micro_usd / 1_000_000).toFixed(2)}. {detail.billing_status}
            </p>
          )}
          {researcher && state === 'draft' && (
            <button
              className="primary"
              disabled={busy || !detail.readiness.ready}
              onClick={() =>
                void act(
                  () => request(base + '/runs/' + id + '/launch', {}, version),
                  'Paid marketing run queued.',
                )
              }
            >
              Launch paid 12-week run
            </button>
          )}
          {admin && state === 'draft' && detail.readiness.subject_hash && (
            <details>
              <summary>Record real Admin approval</summary>
              <p>
                Two distinct real Admins must each approve the provider and exact run. Demo
                identities are rejected. Sign in again within ten minutes of approval. These
                controls do not launch a run.
              </p>
              <Form
                onSubmit={(e) => {
                  e.preventDefault();
                  const form = new FormData(e.currentTarget);
                  const purpose = String(form.get('purpose'));
                  const r = detail.readiness;
                  void act(
                    () =>
                      request(
                        base +
                          (purpose === 'activation'
                            ? '/connections/' + r.connection_id + '/approvals'
                            : '/runs/' + id + '/paid-approvals'),
                        {
                          purpose,
                          subject_hash:
                            purpose === 'activation' ? r.connection_hash : r.subject_hash,
                          cap_micro_usd: 100_000_000,
                          authority_reference: String(form.get('evidence')),
                          expires_at: new Date(String(form.get('expires'))).toISOString(),
                        },
                      ),
                    'Approval recorded for this exact scope.',
                  );
                }}
              >
                <label htmlFor={id + '-purpose'}>Approval scope</label>
                <select id={id + '-purpose'} name="purpose">
                  <option value="activation">Provider activation</option>
                  <option value="paid_scope">Exact run and $100 cumulative ceiling</option>
                </select>
                <label htmlFor={id + '-evidence'}>Reviewed authority reference</label>
                <textarea id={id + '-evidence'} name="evidence" required minLength={10} />
                <label htmlFor={id + '-expires'}>Approval expiry (local time)</label>
                <input id={id + '-expires'} name="expires" type="datetime-local" required />
                <p>
                  Must expire by{' '}
                  {detail.readiness.pricing_expires_at || 'the reviewed pricing expiry'}.
                </p>
                <button disabled={busy}>Record my approval</button>
              </Form>
            </details>
          )}
        </>
      )}
      <button disabled={busy} onClick={() => void load()}>
        Refresh marketing readiness
      </button>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
