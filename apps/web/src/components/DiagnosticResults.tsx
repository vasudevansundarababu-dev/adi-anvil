'use client';
import { useEffect, useState } from 'react';
import { dateTime, shortId, workspaceApi as api, WorkspaceRun } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';
type Result = {
  id: string;
  state: string;
  outcome: string;
  score: number | null;
  candidate: string;
  output_available: boolean;
  task_revision_id: string;
};
export default function DiagnosticResults({
  base,
  run,
  trajectory,
}: {
  base: string;
  run: WorkspaceRun;
  trajectory: boolean;
}) {
  const [rows, setRows] = useState<Result[]>([]),
    [cursor, setCursor] = useState<string | null>(null),
    [output, setOutput] = useState<{ content: string; sha256: string } | null>(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    setRows([]);
    setOutput(null);
    setError('');
    api(base + '/workspace/diagnostic-runs/' + run.id + '/results')
      .then((r) => {
        if (active) {
          setRows(r.items);
          setCursor(r.next_cursor);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [base, run.id]);
  return (
    <section className={styles.panel}>
      <h2>{trajectory ? 'Diagnostic observable evidence' : 'All diagnostic results'}</h2>
      <p className={styles.muted}>
        Whole-run results. Candidate identity, scores and output remain blinded until the review is
        finalized. No private checkpoint or hidden reasoning is exposed.
      </p>
      {error && <p role="alert">{error}</p>}
      <div className={styles.tableScroll}>
        <table>
          <thead>
            <tr>
              <th>Result / task revision</th>
              <th>Candidate</th>
              <th>State / outcome</th>
              <th>Score</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>
                  {shortId(r.id)}
                  <small>{shortId(r.task_revision_id)}</small>
                </td>
                <td>{r.candidate}</td>
                <td>
                  {r.state}
                  <small>{r.outcome}</small>
                </td>
                <td>{r.score === null ? 'Unscored' : r.score + '/100'}</td>
                <td>
                  <button
                    disabled={busy || !r.output_available}
                    onClick={async () => {
                      setBusy(true);
                      setError('');
                      try {
                        setOutput(
                          await api(
                            base +
                              '/workspace/diagnostic-runs/' +
                              run.id +
                              '/results/' +
                              r.id +
                              '/output',
                          ),
                        );
                      } catch (e) {
                        setError((e as Error).message);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Inspect finalized output
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!rows.length && <p>No episodes have been created for this run.</p>}
      {cursor && (
        <button
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              const page = await api(
                base + '/workspace/diagnostic-runs/' + run.id + '/results?after=' + cursor,
              );
              setRows([...rows, ...page.items]);
              setCursor(page.next_cursor);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          Load more results
        </button>
      )}
      {output && (
        <>
          <h3>Retained finalized output</h3>
          <pre>{output.content}</pre>
          <p className={styles.hash}>SHA-256: {output.sha256}</p>
        </>
      )}
      <p className={styles.muted}>
        Run prepared: {dateTime(run.created_at)}. Intermediate trajectory coverage is unavailable
        unless independently retained; missing steps are never synthesized.
      </p>
    </section>
  );
}
