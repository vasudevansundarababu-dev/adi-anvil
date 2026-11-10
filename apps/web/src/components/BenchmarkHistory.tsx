'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { benchmarkGet } from '../lib/benchmark';
import styles from './ModernWorkspace.module.css';

type Item = {
  run_id: string;
  protocol_revision_id: string;
  state: string;
  origin: string;
  planned_cells: number;
  created_at: string;
};

export default function BenchmarkHistory({
  base,
  select,
}: {
  base: string;
  select: (id: string) => void;
}) {
  const [items, setItems] = useState<Item[]>([]),
    [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const generation = useRef(0);
  const load = useCallback(
    async (after?: string) => {
      const request = ++generation.current;
      setBusy(true);
      setError('');
      try {
        const value = await benchmarkGet<{ items: Item[]; next_cursor: string | null }>(
          base,
          '/comparisons?limit=25' + (after ? '&after=' + encodeURIComponent(after) : ''),
        );
        if (request !== generation.current) return;
        setItems((old) =>
          after
            ? [
                ...old,
                ...value.items.filter((item) => !old.some((row) => row.run_id === item.run_id)),
              ]
            : value.items,
        );
        setCursor(value.next_cursor);
      } catch (failure) {
        if (request === generation.current) setError((failure as Error).message);
      } finally {
        if (request === generation.current) setBusy(false);
      }
    },
    [base],
  );
  useEffect(() => {
    void load();
    return () => {
      generation.current++;
    };
  }, [load]);
  return (
    <section className={styles.panel} aria-label="Comparison history" aria-busy={busy}>
      <h2>Saved comparisons</h2>
      <p>Reopen a saved comparison after reconnecting or returning to this page.</p>
      <button type="button" disabled={busy} onClick={() => void load()}>
        Refresh comparisons
      </button>
      {error && <p role="alert">{error}</p>}
      {!items.length && !busy && !error && (
        <p>No comparisons have been admitted in this project.</p>
      )}
      {!!items.length && (
        <table>
          <caption>Durable comparison history</caption>
          <thead>
            <tr>
              <th>Created</th>
              <th>Status</th>
              <th>Cells</th>
              <th>Origin</th>
              <th>Inspect</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.run_id}>
                <td>{new Date(item.created_at).toLocaleString()}</td>
                <td>{item.state.replaceAll('_', ' ')}</td>
                <td>{item.planned_cells}</td>
                <td>{item.origin}</td>
                <td>
                  <button type="button" disabled={busy} onClick={() => select(item.run_id)}>
                    Open comparison {item.run_id.slice(0, 8)}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {cursor && (
        <button type="button" disabled={busy} onClick={() => void load(cursor)}>
          Load more comparisons
        </button>
      )}
    </section>
  );
}
