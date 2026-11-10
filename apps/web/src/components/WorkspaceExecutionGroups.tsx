'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { money, shortId, workspaceApi as api } from '../lib/workspace';
import { runBlockers } from '../lib/executionReadiness';
import {
  describeReason,
  describeRunReason,
  reasonCatalog,
  runBlockerItems,
} from '../lib/readinessCatalog';
import ReasonList from './ReasonList';
import styles from './ModernWorkspace.module.css';
type Group = {
  preparation_id: string;
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
    trial: number;
    plan_id: string;
    model: { id: string; name: string; provider: string; model_id: string };
    check: { id: string; state: string; error_code: string | null } | null;
  }[];
  snapshot: {
    preparation: {
      package: { source_id?: string; manifest: { task_id: string; task_version: string } };
      preset: { name: string };
    };
  };
};
// Status and run error codes keep their previous fallback; readiness codes use the catalog.
const describe = (value: string, canAdmin: boolean) =>
  Object.hasOwn(reasonCatalog, value)
    ? describeRunReason(value, canAdmin)
    : value.replaceAll('_', ' ');
export default function WorkspaceExecutionGroups({
  base,
  groupId,
  canAdmin = false,
  expectedSourceId,
  onUpdated,
  createHref,
  onRunAttempt,
}: {
  base: string;
  groupId?: string;
  canAdmin?: boolean;
  expectedSourceId?: string;
  onUpdated?: (id: string) => void;
  createHref?: string;
  onRunAttempt?: () => void;
}) {
  const endpoint = base + '/workspace/execution-groups',
    href = base.replace('/projects/', '/workspace/') + '/execution-groups';
  const [items, setItems] = useState<Group[]>([]),
    [selected, setSelected] = useState<Group | null>(null),
    [cursor, setCursor] = useState<string | null>(null),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const [runAttempted, setRunAttempted] = useState(false);
  const blockerPanel = useRef<HTMLDivElement>(null);
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
    if (action === 'launch') onRunAttempt?.();
    setBusy(true);
    setError('');
    try {
      let current = selected;
      if (action === 'launch') {
        current = await api(endpoint + '/' + selected.id);
        setSelected(current);
        if (current.state === 'launched') return;
        if (current.state === 'draft' && runBlockers(current.readiness, canAdmin).length) {
          setRunAttempted(true);
          requestAnimationFrame(() => blockerPanel.current?.focus());
          return;
        }
      }
      setSelected(
        await api(
          endpoint + '/' + current.id + '/' + action,
          'POST',
          action === 'launch' && canAdmin
            ? {
                subject_hash: current.subject_hash,
                aggregate_cap_micro_usd: current.readiness.aggregate_cap_micro_usd,
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
  const workspace = base.replace('/projects/', '/workspace/');
  const to = {
    workspace,
    configure: createHref || href + '/new',
    share: selected ? href + '/' + selected.id : href,
    run: selected?.state === 'draft' ? '#execution-group-run' : undefined,
  };
  const blockerItems = selected ? runBlockerItems(selected.readiness, canAdmin) : [];
  const blockers = selected ? runBlockers(selected.readiness, canAdmin) : [];
  if (
    selected &&
    expectedSourceId &&
    selected.snapshot.preparation.package.source_id !== expectedSourceId
  )
    return (
      <p role="alert">
        This execution group belongs to a different task version. Open it from Execution groups.
      </p>
    );
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
              ? blockers.length > 0
                ? 'Setup needed'
                : 'Ready to run'
              : describe(selected.status, canAdmin)}
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
          <ReasonList
            items={selected.readiness.missing.map((r) => describeReason(r, canAdmin))}
            canAdmin={canAdmin}
            to={to}
          />
          {selected.state === 'draft' ? (
            <>
              {!!blockers.length && (
                <div
                  className={styles.error}
                  ref={blockerPanel}
                  tabIndex={-1}
                  role={runAttempted ? 'alert' : 'status'}
                >
                  <h3>Run cannot start yet</h3>
                  <ReasonList items={blockerItems} canAdmin={canAdmin} to={to} />
                  <p>No model request has been sent for this draft.</p>
                </div>
              )}
              {canAdmin && (
                <p>
                  By selecting Run, you confirm permission to process this task with the selected
                  models and authorize the budget shown above.
                </p>
              )}
              <div className={styles.actions}>
                <button
                  id="execution-group-run"
                  className={styles.primary}
                  disabled={busy}
                  onClick={() => void command('launch')}
                >
                  {busy ? 'Checking run…' : 'Run'}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    setError('');
                    try {
                      const next = await api(endpoint, 'POST', {
                        preparation_id: selected.preparation_id,
                      });
                      if (onUpdated) onUpdated(next.id);
                      else window.location.assign(href + '/' + next.id);
                    } catch (e) {
                      setError((e as Error).message);
                      setBusy(false);
                    }
                  }}
                >
                  Update configuration
                </button>
                <a className="button" href={createHref || href + '/new'}>
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
              <h4>
                {m.model.name} · Trial {m.trial || 1}
              </h4>
              <p>
                {m.model.provider} / {m.model.model_id}
              </p>
              <ReasonList
                items={(
                  selected.readiness.models.find((s) => s.model_profile_id === m.model.id)
                    ?.missing || []
                ).map((r) => describeReason(r, canAdmin))}
                canAdmin={canAdmin}
                to={to}
              />
              {m.check ? (
                <>
                  <p>
                    {m.check.state}
                    {m.check.error_code ? ' · ' + describe(m.check.error_code, canAdmin) : ''}
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
