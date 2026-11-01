'use client';

import { useEffect, useRef, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';

export type WorkspaceAccess = {
  profile: 'admin' | 'rl_engineer' | null;
  label: string;
  capabilities: string[];
  mapping_state: 'recorded' | 'current_grants_changed' | 'not_recorded' | 'legacy_only';
};
type Person = { id: string; name: string; access: WorkspaceAccess; preserved_duties: string[] };
type PeoplePage = { items: Person[]; next_cursor: string | null; management_reason: string };

export default function WorkspacePeople({ base }: { base: string }) {
  const [page, setPage] = useState<PeoplePage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const generation = useRef(0);
  useEffect(() => {
    const current = ++generation.current;
    setPage(null);
    setError('');
    setLoading(true);
    api(base + '/workspace/people')
      .then((value) => {
        if (generation.current === current) setPage(value);
      })
      .catch((e) => {
        if (generation.current === current) setError(e.message);
      })
      .finally(() => {
        if (generation.current === current) setLoading(false);
      });
    return () => {
      generation.current++;
    };
  }, [base]);
  return (
    <section className={styles.panel}>
      <h2>Project people</h2>
      <p>
        Admin includes engineering work. Each person keeps one account and their project history.
      </p>
      {loading && <p role="status">Loading people…</p>}
      {error && <p role="alert">{error}</p>}
      {page && (
        <>
          <p className={styles.notice}>{page.management_reason}</p>
          <div className={styles.tableScroll}>
            <table>
              <thead>
                <tr>
                  <th>Person</th>
                  <th>Workspace profile</th>
                  <th>Access history</th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((person) => (
                  <tr key={person.id}>
                    <td>{person.name}</td>
                    <td>{person.access.label}</td>
                    <td>
                      <details>
                        <summary>Access record</summary>
                        <p>{person.access.label}</p>
                        <p className={styles.muted}>
                          Current access uses Admin or RL Engineer. Prior decisions and access
                          history are preserved.
                        </p>
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!page.items.length && !loading && <p>No active people in this project.</p>}
          {page.next_cursor && (
            <button
              disabled={loading}
              onClick={async () => {
                const current = generation.current;
                setLoading(true);
                setError('');
                try {
                  const next = await api(base + '/workspace/people?after=' + page.next_cursor);
                  if (current === generation.current)
                    setPage({ ...next, items: [...page.items, ...next.items] });
                } catch (e) {
                  if (current === generation.current) setError((e as Error).message);
                } finally {
                  if (current === generation.current) setLoading(false);
                }
              }}
            >
              Load more people
            </button>
          )}
        </>
      )}
    </section>
  );
}
