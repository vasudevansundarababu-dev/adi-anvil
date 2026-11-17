'use client';

import { useState } from 'react';
import { BenchmarkComparison, benchmarkGet, benchmarkPost } from '../lib/benchmark';
import styles from './ModernWorkspace.module.css';

export default function BenchmarkRecovery({
  base,
  comparison,
  canAdmin,
  changed,
}: {
  base: string;
  comparison: BenchmarkComparison;
  canAdmin: boolean;
  changed: (value: BenchmarkComparison) => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  const [cell, setCell] = useState(''),
    [notes, setNotes] = useState(''),
    [confirmed, setConfirmed] = useState(false);
  const path = '/comparisons/' + comparison.run_id;
  const action = async (work: () => Promise<void>) => {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await work();
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const unknown = comparison.cells.filter(
    (row) => row.state === 'dispatch_unknown' && !row.reconciled,
  );
  return (
    <section className={styles.panel} aria-label="Resume and reconciliation" aria-busy={busy}>
      <h2>Resume and inspect interrupted work</h2>
      <p>
        Resume keeps the same checkpoint, cells and budgets. It never retries an unknown or failed
        attempt or undoes cancellation.
      </p>
      {!canAdmin && (
        <p>A project administrator must request resumption or reconcile interrupted actors.</p>
      )}
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      <button
        type="button"
        disabled={busy || !canAdmin}
        onClick={() =>
          void action(async () => {
            const value = await benchmarkPost<{
              comparison: BenchmarkComparison;
              resumable: number;
            }>(base, path + '/resume', {
              expected_subject_sha256: comparison.subject_sha256,
              expected_event_seq: comparison.checkpoint_event_seq,
            });
            changed(value.comparison);
            setMessage(
              value.resumable +
                ' untouched or captured cells remain available to the configured operator.',
            );
          })
        }
      >
        Resume untouched or captured work
      </button>{' '}
      <button
        type="button"
        disabled={busy || !canAdmin}
        onClick={() =>
          void action(async () => {
            const value = await benchmarkPost<{ comparison: BenchmarkComparison; expired: number }>(
              base,
              path + '/reconcile-expired',
              {
                expected_subject_sha256: comparison.subject_sha256,
              },
            );
            changed(value.comparison);
            setMessage(
              value.expired + ' expired leases recorded; ambiguous outcomes remain unknown.',
            );
          })
        }
      >
        Check expired work
      </button>
      {!!unknown.length && (
        <details>
          <summary>Record stopped-actor evidence for an unknown outcome</summary>
          <p>
            After inspecting and stopping the owned native actors, an assigned administrator can
            record that inspection. This is a human attestation, not an automatic environment check.
            It releases capacity; the result remains unknown and unscored.
          </p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void action(async () => {
                let after = 0,
                  sequence: number | undefined;
                for (let page = 0; page < 20; page++) {
                  const events = await benchmarkGet<{
                    items: { cell_id: string; event_seq: number; state: string }[];
                    next_event_seq: number | null;
                  }>(base, path + '/events?limit=100&after_event_seq=' + after);
                  for (const event of events.items)
                    if (event.cell_id === cell) sequence = event.event_seq;
                  if (events.next_event_seq == null) break;
                  after = events.next_event_seq;
                }
                if (sequence == null)
                  throw new Error(
                    'The selected cell has no confirmed event checkpoint. Refresh the comparison.',
                  );
                const evidence = await benchmarkPost<{
                  evidence_artifact_id: string;
                  evidence_sha256: string;
                }>(base, path + '/operator-evidence', { evidence_text: notes });
                const value = await benchmarkPost<{ comparison: BenchmarkComparison }>(
                  base,
                  path + '/reconciliations',
                  {
                    expected_subject_sha256: comparison.subject_sha256,
                    expected_event_seq: sequence,
                    cell_id: cell,
                    evidence_artifact_id: evidence.evidence_artifact_id,
                    evidence_sha256: evidence.evidence_sha256,
                    owned_actors_stopped_confirmed: confirmed,
                  },
                );
                changed(value.comparison);
                setMessage(
                  'Inspection recorded. Unknown evidence was preserved, capacity released and no attempt retried.',
                );
              });
            }}
          >
            <label>
              Unknown cell{' '}
              <select
                required
                value={cell}
                disabled={busy || !canAdmin}
                onChange={(event) => {
                  setCell(event.target.value);
                  setConfirmed(false);
                }}
              >
                <option value="">Select a cell</option>
                {unknown.map((row) => (
                  <option value={row.cell_id} key={row.cell_id}>
                    Slot {row.slot + 1}, repetition {row.repetition + 1} · {row.cell_id}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Inspection references and observations{' '}
              <textarea
                required
                minLength={10}
                maxLength={65536}
                value={notes}
                disabled={busy || !canAdmin}
                onChange={(event) => setNotes(event.target.value)}
              />
            </label>
            <p>Use inspection references; omit credentials and private task rules.</p>
            <label>
              <input
                type="checkbox"
                checked={confirmed}
                disabled={busy || !canAdmin}
                onChange={(event) => setConfirmed(event.target.checked)}
              />
              I inspected this cell and confirm its owned native actors are stopped.
            </label>
            <button disabled={busy || !canAdmin || !confirmed || !cell || notes.trim().length < 10}>
              Record my inspection and release capacity
            </button>
          </form>
        </details>
      )}
    </section>
  );
}
