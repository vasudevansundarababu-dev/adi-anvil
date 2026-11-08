'use client';

import { useState } from 'react';
import { benchmarkGet } from '../lib/benchmark';

type Evidence = {
  cell_id: string;
  origin: string;
  criteria: {
    criterion_id: string;
    earned_points: string;
    possible_points: string;
    output_sha256: string;
  }[];
  outputs: { path: string; sha256: string; byte_size: number; text: string }[];
  missing: string[];
};

export default function BenchmarkCellEvidence({
  base,
  runId,
  cellId,
}: {
  base: string;
  runId: string;
  cellId: string;
}) {
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  return (
    <div>
      <button
        type="button"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          setError('');
          setEvidence(null);
          void benchmarkGet<Evidence>(
            base,
            '/comparisons/' +
              encodeURIComponent(runId) +
              '/cells/' +
              encodeURIComponent(cellId) +
              '/evidence',
          )
            .then(setEvidence)
            .catch((failure) => setError((failure as Error).message))
            .finally(() => setBusy(false));
        }}
      >
        {busy ? 'Loading evidence…' : 'Inspect authorized output and criteria'}
      </button>
      {error && <p role="alert">{error}</p>}
      {evidence && (
        <>
          <p>Evidence origin: {evidence.origin}</p>
          {evidence.missing.length > 0 && <p>Unavailable: {evidence.missing.join(', ')}</p>}
          {evidence.criteria.length > 0 && (
            <table>
              <caption>Stored criterion observations</caption>
              <thead>
                <tr>
                  <th>Criterion</th>
                  <th>Earned</th>
                  <th>Possible</th>
                  <th>Output binding</th>
                </tr>
              </thead>
              <tbody>
                {evidence.criteria.map((item) => (
                  <tr key={item.criterion_id}>
                    <td>{item.criterion_id}</td>
                    <td>{item.earned_points}</td>
                    <td>{item.possible_points}</td>
                    <td>
                      <code>{item.output_sha256}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {evidence.outputs.map((output) => (
            <details key={output.path + output.sha256}>
              <summary>
                {output.path} · {output.byte_size} bytes
              </summary>
              <p>
                SHA-256: <code>{output.sha256}</code>
              </p>
              <pre>{output.text}</pre>
            </details>
          ))}
          {!evidence.outputs.length && <p>No captured output is available for this cell.</p>}
        </>
      )}
    </div>
  );
}
