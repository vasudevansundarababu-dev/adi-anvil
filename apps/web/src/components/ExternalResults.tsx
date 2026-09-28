import { useState } from 'react';

export default function ExternalResults({ base, runId }: { base: string; runId: string }) {
  const [manifest, setManifest] = useState('');
  const [batch, setBatch] = useState<{
    id: string;
    manifest_hash: string;
    status: string;
    errors: { row?: number; code: string }[];
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  async function command(path: string, body: unknown) {
    setBusy(true);
    setMessage('');
    try {
      const csrf =
        document.cookie
          .split('; ')
          .find((x) => x.startsWith('anvil_csrf='))
          ?.split('=')[1] || '';
      const response = await fetch('/api/v1' + base + path, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrf,
          'Idempotency-Key': crypto.randomUUID(),
        },
        body: JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(
          typeof result.error?.message === 'string'
            ? result.error.message
            : JSON.stringify(result.error?.message),
        );
      return result.data;
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="card">
      <summary>Import reported results</summary>
      <p>
        Execution stays customer- or partner-reported after Anvil review. No candidate is invoked.
        Missing output remains unscorable; missing traces remain missing.
      </p>
      <p className="muted">
        Use an anvil.external_results.v1 manifest for run {runId}. General uploaded files remain
        quarantined until a scanner is qualified. Aggregate-only manifests may explicitly omit
        output.
      </p>
      <label htmlFor={'external-' + runId}>External results manifest</label>
      <textarea
        id={'external-' + runId}
        rows={12}
        value={manifest}
        onChange={(e) => {
          setManifest(e.target.value);
          setBatch(null);
        }}
      />
      <button
        disabled={busy || !manifest.trim()}
        onClick={async () => {
          try {
            setBatch(
              await command('/runs/' + runId + '/external-results/validate', JSON.parse(manifest)),
            );
          } catch (e) {
            setMessage((e as Error).message);
          }
        }}
      >
        Validate without importing
      </button>
      {batch && (
        <div>
          <p>Batch: {batch.status}</p>
          {batch.errors.map((e, i) => (
            <p key={i}>
              {e.row === undefined ? 'Manifest' : 'Attempt ' + (e.row + 1)}: {e.code}
            </p>
          ))}
          {batch.status === 'validated' && (
            <button
              disabled={busy}
              onClick={async () => {
                try {
                  await command('/imports/' + batch.id + '/commit-results', {
                    manifest_hash: batch.manifest_hash,
                  });
                  setBatch({ ...batch, status: 'committed' });
                  setMessage(
                    'Imported. Refresh the run to inspect reported attempts and pending Anvil reviews.',
                  );
                } catch (e) {
                  setMessage((e as Error).message);
                }
              }}
            >
              Commit this validated manifest
            </button>
          )}
        </div>
      )}
      {message && <p role="status">{message}</p>}
    </details>
  );
}
