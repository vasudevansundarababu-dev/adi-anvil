'use client';

import { useEffect, useRef, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';

export type WorkspaceAccess = {
  profile: 'admin' | 'rl_engineer' | 'sme_reviewer' | null;
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
  const [saving, setSaving] = useState<string | null>(null);
  const [message, setMessage] = useState('');
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
      <p>
        Assign SME review to an existing project member to review results and score skills. This
        does not grant execution or deployment access.
      </p>
      {loading && <p role="status">Loading people…</p>}
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {page && (
        <>
          <p className={styles.notice}>{page.management_reason}</p>
          <div className={styles.tableScroll}>
            <table>
              <thead>
                <tr>
                  <th>Person</th>
                  <th>Workspace profile</th>
                  <th>SME result review</th>
                  <th>Access history</th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((person) => (
                  <tr key={person.id}>
                    <td>{person.name}</td>
                    <td>{person.access.label}</td>
                    <td>
                      <span>
                        {person.preserved_duties.includes('sme-reviewer')
                          ? 'Assigned'
                          : 'Not assigned'}
                      </span>{' '}
                      <button
                        disabled={saving !== null}
                        onClick={async () => {
                          const active = !person.preserved_duties.includes('sme-reviewer');
                          const current = generation.current;
                          setSaving(person.id);
                          setError('');
                          setMessage('');
                          try {
                            await api(
                              base + '/workspace/benchmark/expert-review-membership',
                              'PUT',
                              { user_id: person.id, active },
                            );
                            if (current !== generation.current) return;
                            setPage(
                              (previous) =>
                                previous && {
                                  ...previous,
                                  items: previous.items.map((item) =>
                                    item.id === person.id
                                      ? {
                                          ...item,
                                          preserved_duties: active
                                            ? [...item.preserved_duties, 'sme-reviewer']
                                            : item.preserved_duties.filter(
                                                (role) => role !== 'sme-reviewer',
                                              ),
                                        }
                                      : item,
                                  ),
                                },
                            );
                            setMessage(
                              `${person.name}: SME review ${active ? 'assigned' : 'removed'}.`,
                            );
                          } catch (e) {
                            if (current === generation.current) setError((e as Error).message);
                          } finally {
                            if (current === generation.current) setSaving(null);
                          }
                        }}
                      >
                        {saving === person.id
                          ? 'Saving…'
                          : person.preserved_duties.includes('sme-reviewer')
                            ? 'Remove SME review'
                            : 'Assign SME review'}
                      </button>
                    </td>
                    <td>
                      <details>
                        <summary>Access record</summary>
                        <p>{person.access.label}</p>
                        <p className={styles.muted}>
                          Prior decisions and access history are preserved.
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
