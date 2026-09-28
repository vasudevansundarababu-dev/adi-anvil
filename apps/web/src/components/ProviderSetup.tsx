import Form from './Form';
import { useState } from 'react';

export default function ProviderSetup({
  base,
  provider,
  model,
}: {
  base: string;
  provider: string;
  model: string | null;
}) {
  const [message, setMessage] = useState(''),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  return (
    <details>
      <summary>Configure exact model and cost bound</summary>
      <p>
        Secrets are supplied in the local private environment or secret file. Saving this form makes
        no provider request.
      </p>
      <Form
        onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          setBusy(true);
          setError('');
          setMessage('');
          try {
            const csrf =
              document.cookie
                .split('; ')
                .find((x) => x.startsWith('anvil_csrf='))
                ?.split('=')[1] || '';
            const response = await fetch('/api/v1' + base + '/providers/' + provider + '/config', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrf,
                'Idempotency-Key': crypto.randomUUID(),
              },
              body: JSON.stringify({
                model_id: String(f.get('model')),
                max_output_tokens: Number(f.get('tokens')),
                pricing_revision: String(f.get('pricing')) || null,
                bound_micro_usd: f.get('bound') ? Number(f.get('bound')) : null,
                processing_terms_reviewed: false,
              }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error?.message || 'Configuration failed');
            setMessage(
              'Configuration saved. Refresh for updated readiness. Live inference remains disabled.',
            );
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label htmlFor={provider + '-model'}>Exact model ID</label>
        <input
          id={provider + '-model'}
          name="model"
          required
          maxLength={200}
          defaultValue={model || ''}
        />
        <label htmlFor={provider + '-tokens'}>Maximum output tokens</label>
        <input
          id={provider + '-tokens'}
          name="tokens"
          type="number"
          min={1}
          max={8192}
          defaultValue={4096}
          required
        />
        <label htmlFor={provider + '-pricing'}>Reviewed pricing revision reference</label>
        <input id={provider + '-pricing'} name="pricing" />
        <label htmlFor={provider + '-bound'}>Conservative request cost bound (micro USD)</label>
        <input id={provider + '-bound'} name="bound" type="number" min={1} step={1} />
        <button disabled={busy}>Save configuration</button>
      </Form>
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
    </details>
  );
}
