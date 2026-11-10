'use client';
import { useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
type Attempt = {
  id: string;
  state: string;
  environment_id: string;
  model_key: string;
  repetition: number;
  parent_attempt_id: string | null;
  evidence_receipt_id: string | null;
  error_code: string | null;
};
export default function EnvironmentRunControls({
  base,
  run,
  state,
}: {
  base: string;
  run: string;
  state: string;
}) {
  const [items, setItems] = useState<Attempt[]>([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState('');
  const path = base + '/workspace/environments/runs/' + run;
  useEffect(() => {
    let active = true;
    api(path + '/attempts')
      .then((r) => {
        if (active) setItems(r);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [path, state]);
  const act = async (action: 'cancel' | 'retry') => {
    setBusy(true);
    setError('');
    try {
      const r = await api(path + '/' + action, 'POST', {});
      if (action === 'retry') {
        const url = new URL(window.location.href);
        url.searchParams.set('benchmark_run', r.id);
        url.searchParams.delete('cell');
        window.location.assign(url.toString());
      } else
        setMessage(
          'Cancellation requested. Available evidence is retained; no action is replayed.',
        );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const download = async (id: string) => {
    try {
      const data = await api(base + '/workspace/environments/receipts/' + id);
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
      );
      const a = document.createElement('a');
      a.href = url;
      a.download = 'environment-evidence-' + id + '.json';
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <details>
      <summary>Environment attempts, retained evidence and retry</summary>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {['queued', 'running'].includes(state) ? (
        <button disabled={busy} onClick={() => void act('cancel')}>
          Cancel environment Run
        </button>
      ) : (
        <button disabled={busy} onClick={() => void act('retry')}>
          Retry in a new linked Run
        </button>
      )}
      <p>
        Retries create fresh isolated instances and retain original attempts. Uncertain native
        execution is never blindly replayed.
      </p>
      <table>
        <thead>
          <tr>
            <th>Attempt</th>
            <th>State</th>
            <th>Environment</th>
            <th>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr key={a.id}>
              <td>
                {a.id.slice(0, 8)} · {a.model_key} · repetition {a.repetition + 1}
                {a.parent_attempt_id && ' · linked retry'}
              </td>
              <td>
                {a.state}
                {a.error_code && ' · ' + a.error_code}
              </td>
              <td>{a.environment_id.slice(0, 8)}</td>
              <td>
                {a.evidence_receipt_id ? (
                  <button onClick={() => void download(a.evidence_receipt_id!)}>
                    Download attempt evidence
                  </button>
                ) : (
                  'Not captured'
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
