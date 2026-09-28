import Form from './Form';
import { useState } from 'react';

export default function RightsReview({
  base,
  id,
  version,
}: {
  base: string;
  id: string;
  version: number;
}) {
  const [message, setMessage] = useState(''),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  return (
    <details>
      <summary>Review or revoke permitted use</summary>
      <p>
        Record the evidence and exact destination you reviewed. Local evaluation and OpenAI
        processing are separate scopes; neither grants redistribution or training permission.
      </p>
      <Form
        onSubmit={async (e) => {
          e.preventDefault();
          const data = new FormData(e.currentTarget);
          setBusy(true);
          setError('');
          setMessage('');
          try {
            const operation = String(data.get('operation'));
            const csrf =
              document.cookie
                .split('; ')
                .find((x) => x.startsWith('anvil_csrf='))
                ?.split('=')[1] || '';
            const response = await fetch('/api/v1' + base + '/cases/' + id + '/rights', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrf,
                'Idempotency-Key': crypto.randomUUID(),
                'If-Match': String(version),
              },
              body: JSON.stringify({
                operation,
                destination:
                  operation === 'managed_evaluation'
                    ? 'local_fixture'
                    : operation === 'external_processing'
                      ? 'openai'
                      : 'internal_fixture',
                status: String(data.get('status')),
                evidence: String(data.get('evidence')),
                expires_at: data.get('expires_at')
                  ? new Date(String(data.get('expires_at'))).toISOString()
                  : null,
              }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error?.message || 'Rights update failed');
            setMessage('Rights decision recorded for this exact source version.');
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label htmlFor={id + '-operation'}>Permitted operation</label>
        <select id={id + '-operation'} name="operation">
          <option value="managed_evaluation">Local fixture evaluation</option>
          <option value="external_processing">External actor-input processing by OpenAI</option>
          <option value="report_sharing">Internal aggregate report sharing</option>
        </select>
        <label htmlFor={id + '-status'}>Decision</label>
        <select id={id + '-status'} name="status">
          <option value="approved">Approve reviewed scope</option>
          <option value="revoked">Revoke scope</option>
        </select>
        <label htmlFor={id + '-evidence'}>Reviewed rights evidence and limits</label>
        <textarea id={id + '-evidence'} name="evidence" minLength={20} maxLength={5000} required />
        <label htmlFor={id + '-expires'}>Permission expiry (optional, your local time)</label>
        <input id={id + '-expires'} name="expires_at" type="datetime-local" />
        <button disabled={busy}>Record rights decision</button>
      </Form>
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
    </details>
  );
}
