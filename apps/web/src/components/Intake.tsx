import { useState } from 'react';

type Batch = {
  id: string;
  manifest_hash: string;
  status: string;
  case_count: number;
  errors: { row: number; code: string; artifact_id?: string }[];
};

export default function Intake({ base }: { base: string }) {
  const [manifest, setManifest] = useState(''),
    [batch, setBatch] = useState<Batch | null>(null),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(''),
    [error, setError] = useState('');
  async function request(path: string, body: unknown) {
    const csrf =
      document.cookie
        .split('; ')
        .find((x) => x.startsWith('anvil_csrf='))
        ?.split('=')[1] || '';
    const file = body instanceof FormData;
    const response = await fetch('/api/v1' + base + path, {
      method: 'POST',
      headers: {
        'X-CSRF-Token': csrf,
        'Idempotency-Key': crypto.randomUUID(),
        ...(file ? {} : { 'Content-Type': 'application/json' }),
      },
      body: file ? body : JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok)
      throw new Error(
        typeof result.error?.message === 'string'
          ? result.error.message
          : JSON.stringify(result.error?.message),
      );
    return result.data;
  }
  async function run(work: () => Promise<void>) {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await work();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="card">
      <summary>Partner file and manifest intake</summary>
      <p>
        Upload original files, then preview an <code>anvil.case_import.v1</code> manifest
        referencing their artifact IDs. Rights declarations and review claims require independent
        review.
      </p>
      <p className="banner">
        The local malware scanner is unavailable. Uploaded files remain quarantined and cannot enter
        a committed import.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const data = new FormData(e.currentTarget);
          void run(async () => {
            const item = await request('/artifacts', data);
            setMessage(`Artifact ${item.id}: ${item.scan_status}. ${item.reason}`);
          });
        }}
      >
        <label htmlFor="case-file">Private original file (maximum 25 MiB)</label>
        <input id="case-file" name="file" type="file" required />
        <button disabled={busy}>Upload to quarantine</button>
      </form>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            const result = await request('/imports/validate', JSON.parse(manifest));
            setBatch(result);
            setMessage('Preview saved. No case records have been created.');
          });
        }}
      >
        <label htmlFor="case-manifest">Case manifest JSON</label>
        <textarea
          id="case-manifest"
          value={manifest}
          onChange={(e) => {
            setManifest(e.target.value);
            setBatch(null);
          }}
          required
          spellCheck={false}
        />
        <button disabled={busy}>Validate manifest</button>
      </form>
      {batch && (
        <div>
          <h3>Preview: {batch.status}</h3>
          <p>{batch.case_count} proposed cases</p>
          {batch.errors.length > 0 && (
            <ul>
              {batch.errors.map((e, i) => (
                <li key={i}>
                  Row {e.row + 1}: {e.code.replaceAll('_', ' ')}
                  {e.artifact_id ? ` (${e.artifact_id})` : ''}
                </li>
              ))}
            </ul>
          )}
          {batch.status === 'validated' && (
            <button
              className="primary"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  await request('/imports/' + batch.id + '/commit', {
                    manifest_hash: batch.manifest_hash,
                  });
                  setBatch({ ...batch, status: 'committed' });
                  setMessage(
                    'Import committed. Refresh the case bank to see the unreviewed source records.',
                  );
                })
              }
            >
              Commit validated import
            </button>
          )}
        </div>
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
