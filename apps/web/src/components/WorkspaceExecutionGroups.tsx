'use client';
import { useCallback, useEffect, useState } from 'react';
import { money, shortId, workspaceApi as api } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';
type Group = {
  id: string;
  subject_hash: string;
  state: string;
  status: string;
  readiness: {
    ready: boolean;
    missing: string[];
    aggregate_cap_micro_usd: number | null;
    conservative_cost_micro_usd: number | null;
    models: { model_profile_id: string; missing: string[] }[];
  };
  models: {
    plan_id: string;
    model: { id: string; name: string; provider: string; model_id: string };
    check: { id: string; state: string; error_code: string | null } | null;
  }[];
  snapshot: {
    preparation: {
      package: { manifest: { task_id: string; task_version: string } };
      preset: { name: string };
    };
  };
};
const labels: Record<string, string> = {
  admin_run_authorization_required:
    'Admin can authorize this configuration and budget by selecting Run.',
  live_dispatch_disabled_in_runtime: 'Live execution is disabled on this server.',
  pricing_metadata_missing: 'Add pricing to a new version of this model profile.',
  reviewed_pricing_required: 'Current pricing is required before running this model.',
  credential_missing: 'Add a provider key to a new version of this model profile.',
  processing_terms_reference_required: 'Add the provider processing-terms reference.',
  adapter_changed_create_new_execution_group:
    'Execution software changed. Create a new execution group.',
};
const describe = (value: string) => labels[value] || value.replaceAll('_', ' ');
export default function WorkspaceExecutionGroups({
  base,
  groupId,
  canAdmin = false,
}: {
  base: string;
  groupId?: string;
  canAdmin?: boolean;
}) {
  const endpoint = base + '/workspace/execution-groups',
    href = base.replace('/projects/', '/workspace/') + '/execution-groups';
  const [items, setItems] = useState<Group[]>([]),
    [selected, setSelected] = useState<Group | null>(null),
    [cursor, setCursor] = useState<string | null>(null),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const reload = useCallback(
    async (after?: string) => {
      setLoading(true);
      setError('');
      try {
        const value = await api(
          endpoint + (groupId ? '/' + groupId : after ? '?after=' + after : ''),
        );
        if (groupId) setSelected(value);
        else {
          setItems((old) => (after ? [...old, ...value.items] : value.items));
          setCursor(value.next_cursor);
        }
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    },
    [endpoint, groupId],
  );
  useEffect(() => {
    setSelected(null);
    setItems([]);
    void reload();
  }, [reload]);
  useEffect(() => {
    if (!selected || !['queued', 'running'].includes(selected.status)) return;
    const timer = setInterval(() => void reload(), 3000);
    return () => clearInterval(timer);
  }, [selected?.status, reload]);
  async function command(action: string) {
    if (!selected) return;
    setBusy(true);
    setError('');
    try {
      setSelected(
        await api(
          endpoint + '/' + selected.id + '/' + action,
          'POST',
          action === 'launch' && canAdmin
            ? {
                subject_hash: selected.subject_hash,
                aggregate_cap_micro_usd: selected.readiness.aggregate_cap_micro_usd,
                rights_confirmed: true,
              }
            : undefined,
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const blocked =
    selected &&
    (selected.readiness.missing.some(
      (r) => r !== 'admin_run_authorization_required' || !canAdmin,
    ) ||
      selected.readiness.models.some((m) => m.missing.length > 0));
  return (
    <section
      className={styles.panel}
      aria-label={groupId ? 'Execution group dashboard' : 'Execution groups'}
    >
      {groupId ? (
        <a className="button" href={href}>
          ← Execution groups
        </a>
      ) : (
        <>
          <h2>Execution groups</h2>
          <p>Choose a group to view its runs and results.</p>
          <a className={'button ' + styles.primary} href={href + '/new'}>
            Create execution group
          </a>
        </>
      )}
      <button disabled={loading || busy} onClick={() => void reload()}>
        Refresh
      </button>
      {loading && <p role="status">Loading execution groups…</p>}
      {error && <p role="alert">{error}</p>}
      {!groupId && !loading && !items.length && !error && <p>No execution groups yet.</p>}
      {!groupId &&
        items.map((g) => (
          <article className={styles.panel} key={g.id}>
            <h3>
              <a href={href + '/' + g.id}>Execution group {shortId(g.id)}</a>
            </h3>
            <p>
              {g.snapshot.preparation.package.manifest.task_id} ·{' '}
              {g.snapshot.preparation.preset.name}
            </p>
            <p>
              {g.status} · {g.models.length} models · Budget{' '}
              {g.readiness.aggregate_cap_micro_usd === null
                ? 'not set'
                : money(g.readiness.aggregate_cap_micro_usd)}
            </p>
            <a href={href + '/' + g.id}>{g.state === 'draft' ? 'Open & run' : 'View dashboard'}</a>
          </article>
        ))}
      {!groupId && cursor && (
        <button disabled={loading} onClick={() => void reload(cursor)}>
          Load more
        </button>
      )}
      {groupId && selected && (
        <>
          <h2>Execution group {shortId(selected.id)}</h2>
          <p>
            {selected.snapshot.preparation.package.manifest.task_id} · Task version{' '}
            {selected.snapshot.preparation.package.manifest.task_version} ·{' '}
            {selected.snapshot.preparation.preset.name}
          </p>
          <p role="status">
            {selected.state === 'draft'
              ? blocked
                ? 'Setup needed'
                : 'Ready to run'
              : describe(selected.status)}
          </p>
          <p>
            Budget:{' '}
            {selected.readiness.aggregate_cap_micro_usd === null
              ? 'not set'
              : money(selected.readiness.aggregate_cap_micro_usd)}{' '}
            · Estimated ceiling:{' '}
            {selected.readiness.conservative_cost_micro_usd === null
              ? 'unknown'
              : money(selected.readiness.conservative_cost_micro_usd)}
          </p>
          <ul>
            {selected.readiness.missing.map((r) => (
              <li key={r}>{describe(r)}</li>
            ))}
          </ul>
          {selected.state === 'draft' ? (
            <>
              {canAdmin && (
                <p>
                  By selecting Run, you confirm processing rights for this task and authorize the
                  saved model versions and budget shown above.
                </p>
              )}
              <div className={styles.actions}>
                <button
                  className={styles.primary}
                  disabled={busy || !!blocked}
                  onClick={() => void command('launch')}
                >
                  Run
                </button>
                <a className="button" href={href + '/new'}>
                  Create another group
                </a>
              </div>
            </>
          ) : (
            <button
              disabled={
                busy ||
                !selected.models.some(
                  (m) => m.check && ['queued', 'running'].includes(m.check.state),
                )
              }
              onClick={() => void command('cancel')}
            >
              Cancel remaining runs
            </button>
          )}
          <h3>Model runs</h3>
          {selected.models.map((m) => (
            <article key={m.plan_id} className={styles.panel}>
              <h4>{m.model.name}</h4>
              <p>
                {m.model.provider} / {m.model.model_id}
              </p>
              <ul>
                {selected.readiness.models
                  .find((s) => s.model_profile_id === m.model.id)
                  ?.missing.map((r) => (
                    <li key={r}>{describe(r)}</li>
                  ))}
              </ul>
              {m.check ? (
                <>
                  <p>
                    {m.check.state}
                    {m.check.error_code ? ' · ' + describe(m.check.error_code) : ''}
                  </p>
                  <a href={base.replace('/projects/', '/workspace/') + '/runs?run=' + m.check.id}>
                    View run dashboard
                  </a>
                </>
              ) : (
                <p>Not started</p>
              )}
            </article>
          ))}
          <details>
            <summary>Task, evaluations & exact configuration</summary>
            <pre>{JSON.stringify(selected.snapshot, null, 2)}</pre>
          </details>
          {selected.state !== 'draft' && (
            <p>
              Models run in sequence. Failed, unknown or cancelled runs stop later models. Budget
              reservations remain held until reconciled.
            </p>
          )}
        </>
      )}
    </section>
  );
}
