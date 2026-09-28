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
        Record the evidence you reviewed. This local scope grants no external processing, raw
        redistribution or training permission.
      </p>
      <form
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
                  operation === 'managed_evaluation' ? 'local_fixture' : 'internal_fixture',
                status: String(data.get('status')),
                evidence: String(data.get('evidence')),
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
          <option value="report_sharing">Internal aggregate report sharing</option>
        </select>
        <label htmlFor={id + '-status'}>Decision</label>
        <select id={id + '-status'} name="status">
          <option value="approved">Approve reviewed scope</option>
          <option value="revoked">Revoke scope</option>
        </select>
        <label htmlFor={id + '-evidence'}>Reviewed rights evidence and limits</label>
        <textarea id={id + '-evidence'} name="evidence" minLength={20} maxLength={5000} required />
        <button disabled={busy}>Record rights decision</button>
      </form>
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
    </details>
  );
}
