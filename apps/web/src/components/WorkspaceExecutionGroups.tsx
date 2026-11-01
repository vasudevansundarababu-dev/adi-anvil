'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Form from './Form';
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
    conservative_cost_micro_usd: number | null;
    aggregate_cap_micro_usd: number | null;
    authority_reference: string | null;
    models: { model_profile_id: string; missing: string[] }[];
  };
  models: {
    plan_id: string;
    ordinal: number;
    model: { id: string; name: string; provider: string; model_id: string };
    check: { id: string; state: string; error_code: string | null } | null;
  }[];
  snapshot: unknown;
  reservation_retained: boolean;
};
const labels: Record<string, string> = {
  live_dispatch_disabled_in_runtime: 'Live execution is disabled on this server.',
  exact_group_user_authority_required:
    'The operator must bind your exact model, task, pricing and budget authorization to this group.',
  aggregate_api_cap_missing:
    'No aggregate budget is set. Create another preparation with an explicit budget.',
  group_cap_below_conservative_cost_or_above_authority:
    'The group budget must cover the conservative cost and fit your authorized ceiling.',
  exact_package_software_check_approval:
    'The exact Harbor package needs the existing Product Owner software-check approval.',
  real_product_owner_rights_and_run_review:
    'A real assigned Product Owner must review this exact run and external processing rights.',
  two_real_distinct_admin_activation_approvals:
    'Two distinct real Admins must approve model activation.',
  two_real_distinct_admin_paid_scope_approvals:
    'Two distinct real Admins must approve this paid scope.',
  pricing_metadata_missing:
    'This frozen model version has no declared pricing. Save a new model version, preset and preparation.',
  pricing_metadata_expired:
    'Declared pricing has expired. Create a preparation with current pricing.',
  reviewed_pricing_required:
    'Current pricing must be present in the frozen configuration and explicitly authorized.',
  processing_terms_reference_required:
    'The model version needs a provider processing-terms reference.',
  credential_missing: 'The model version has no credential bound to it.',
  bound_credential_rotated:
    'The bound key was rotated. Create a new model version, preset and preparation.',
  model_version_superseded:
    'A selected model version has been superseded. Create a new preparation.',
  adapter_changed_create_new_execution_group:
    'Execution code changed. Create a new group so reviews bind the current code.',
};
const describe = (reason: string) => labels[reason] || reason.replaceAll('_', ' ');

export default function WorkspaceExecutionGroups({
  base,
  preparationId,
  canReview = false,
  canAdmin = false,
}: {
  base: string;
  preparationId: string;
  canReview?: boolean;
  canAdmin?: boolean;
}) {
  const [groups, setGroups] = useState<Group[]>([]),
    [selected, setSelected] = useState<Group | null>(null),
    [cursor, setCursor] = useState<string | null>(null),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(''),
    [evidence, setEvidence] = useState('');
  const generation = useRef(0),
    heading = useRef<HTMLHeadingElement>(null);
  const route = base + '/workspace/execution-groups';
  const reload = useCallback(
    async (after?: string) => {
      const current = ++generation.current;
      setLoading(true);
      setError('');
      try {
        const page = await api(
          route + '?preparation_id=' + preparationId + (after ? '&after=' + after : ''),
        );
        if (current !== generation.current) return;
        setGroups((old) => (after ? [...old, ...page.items] : page.items));
        setCursor(page.next_cursor);
      } catch (e) {
        if (current === generation.current) setError((e as Error).message);
      } finally {
        if (current === generation.current) setLoading(false);
      }
    },
    [route, preparationId],
  );
  useEffect(() => {
    setGroups([]);
    setSelected(null);
    void reload();
    return () => {
      generation.current++;
    };
  }, [reload]);
  useEffect(() => {
    if (selected?.id) {
      heading.current?.focus();
      setEvidence('');
    }
  }, [selected?.id]);
  useEffect(() => {
    if (!selected || !['queued', 'running'].includes(selected.status)) return;
    let active = true;
    const timer = setInterval(
      () =>
        void api(route + '/' + selected.id)
          .then((value) => {
            if (active) setSelected(value);
          })
          .catch((e) => {
            if (active) setError(e.message);
          }),
      2500,
    );
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [route, selected?.id, selected?.status]);
  async function command(path: string, body: unknown = {}) {
    setBusy(true);
    setError('');
    try {
      const value = await api(route + path, 'POST', body);
      if (value.id) setSelected(value);
      await reload();
      return value;
    } catch (e) {
      setError((e as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  }
  const workspaceRoute = base.replace('/projects/', '/workspace/');
  return (
    <section className={styles.panel} aria-label="Evaluation execution groups">
      <h2>Run this evaluation</h2>
      <p>
        Create a reviewable execution group from this saved preparation. This step makes no model
        request and reserves no money.
      </p>
      <button disabled={busy} onClick={() => void command('', { preparation_id: preparationId })}>
        Create execution group
      </button>
      <button disabled={busy || loading} onClick={() => void reload()}>
        Refresh execution groups
      </button>
      {loading && <p role="status">Loading execution groups…</p>}
      {error && <p role="alert">{error}</p>}
      {!loading && !groups.length && !error && (
        <p>
          No execution group yet. Create one to review costs, authorization and launch readiness.
        </p>
      )}
      {groups.map((group) => (
        <p key={group.id}>
          <button
            disabled={busy}
            onClick={() => {
              setSelected(group);
              setEvidence('');
            }}
          >
            {shortId(group.id)} · {group.status}
          </button>
        </p>
      ))}
      {cursor && (
        <button disabled={loading || busy} onClick={() => void reload(cursor)}>
          Load more execution groups
        </button>
      )}
      {selected && (
        <section aria-labelledby="execution-group-heading">
          <h3 id="execution-group-heading" ref={heading} tabIndex={-1}>
            Execution group · {shortId(selected.id)}
          </h3>
          <p role="status">
            {selected.state === 'draft'
              ? selected.readiness.ready
                ? 'Ready for explicit launch'
                : 'Setup required · no model dispatched'
              : 'Execution ' + selected.status}
          </p>
          <p>
            Aggregate budget:{' '}
            {selected.readiness.aggregate_cap_micro_usd === null
              ? 'not set'
              : money(selected.readiness.aggregate_cap_micro_usd)}
            . Conservative cost:{' '}
            {selected.readiness.conservative_cost_micro_usd === null
              ? 'unknown'
              : money(selected.readiness.conservative_cost_micro_usd)}
            .
          </p>
          <p>
            Models run in sequence. Unknown, cancelled or operationally failed runs stop later
            models. Reservations remain held until separately reconciled; cancellation does not
            release them.
          </p>
          <ul>
            {selected.readiness.missing.map((reason) => (
              <li key={reason}>{describe(reason)}</li>
            ))}
          </ul>
          {selected.models.map((model) => (
            <div key={model.plan_id}>
              <h4>
                {model.model.name} · {model.model.provider}/{model.model.model_id}
              </h4>
              <ul>
                {selected.readiness.models
                  .find((item) => item.model_profile_id === model.model.id)
                  ?.missing.map((reason) => (
                    <li key={reason}>{describe(reason)}</li>
                  ))}
              </ul>
              {model.check && (
                <p>
                  <a href={workspaceRoute + '/runs?run=' + model.check.id}>
                    View run · {model.check.state}
                  </a>
                  {model.check.error_code ? ' · ' + describe(model.check.error_code) : ''}
                </p>
              )}
            </div>
          ))}
          <button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                setSelected(await api(route + '/' + selected.id));
                setError('');
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Refresh launch readiness
          </button>
          {selected.state === 'draft' ? (
            <button
              disabled={busy || !selected.readiness.ready}
              onClick={() => void command('/' + selected.id + '/launch')}
            >
              Launch evaluation
            </button>
          ) : (
            <button
              disabled={
                busy ||
                !selected.models.some(
                  (model) => model.check && ['queued', 'running'].includes(model.check.state),
                )
              }
              onClick={() => void command('/' + selected.id + '/cancel')}
            >
              Cancel remaining runs
            </button>
          )}
          {selected.state === 'draft' && canReview && (
            <details>
              <summary>Review processing rights and this exact run</summary>
              <p>
                Review the task, provider terms and permissions. Synthetic test identities cannot
                approve paid processing.
              </p>
              <Form
                onSubmit={async (e) => {
                  e.preventDefault();
                  const data = new FormData(e.currentTarget);
                  const result = await command('/' + selected.id + '/rights-evidence', {
                    reference: data.get('reference'),
                    description: data.get('description'),
                  });
                  if (result) setEvidence(result.artifact_id);
                }}
              >
                <label>
                  Rights document link or reference
                  <input name="reference" required minLength={5} maxLength={500} />
                </label>
                <label>
                  Evidence description
                  <textarea name="description" required minLength={10} maxLength={2000} />
                </label>
                <button disabled={busy}>Record evidence reference</button>
              </Form>
              <Form
                onSubmit={(e) => {
                  e.preventDefault();
                  const data = new FormData(e.currentTarget);
                  void command('/' + selected.id + '/review', {
                    subject_hash: selected.subject_hash,
                    rights_evidence_id: evidence,
                    rationale: data.get('rationale'),
                    expires_at: new Date(String(data.get('expiry'))).toISOString(),
                  });
                }}
              >
                <label>
                  Rights evidence artifact ID
                  <input required value={evidence} onChange={(e) => setEvidence(e.target.value)} />
                </label>
                <label>
                  Review rationale
                  <textarea name="rationale" minLength={10} maxLength={2000} required />
                </label>
                <label>
                  Review expiry
                  <input name="expiry" type="datetime-local" required />
                </label>
                <button disabled={busy}>Approve exact rights and run scope</button>
              </Form>
            </details>
          )}
          {canReview && (
            <details>
              <summary>Revoke rights/run review</summary>
              <Form
                onSubmit={(e) => {
                  e.preventDefault();
                  void command('/' + selected.id + '/revoke-review', {
                    rationale: new FormData(e.currentTarget).get('rationale'),
                  });
                }}
              >
                <label>
                  Revocation rationale
                  <textarea name="rationale" required minLength={10} maxLength={2000} />
                </label>
                <button disabled={busy}>Revoke group review</button>
              </Form>
            </details>
          )}
          {selected.state === 'draft' && canAdmin && (
            <details>
              <summary>Admin activation and paid-scope decisions</summary>
              <p>
                Two distinct real Admins must each record activation and paid-scope decisions after
                reviewing exact model versions, rates and limits. A recent sign-in is required.
              </p>
              <Form
                onSubmit={(e) => {
                  e.preventDefault();
                  const data = new FormData(e.currentTarget);
                  void command('/' + selected.id + '/admin-approvals', {
                    purpose: data.get('purpose'),
                    subject_hash: selected.subject_hash,
                    authority_reference: data.get('reference'),
                    expires_at: new Date(String(data.get('expiry'))).toISOString(),
                  });
                }}
              >
                <label>
                  Decision
                  <select name="purpose">
                    <option value="activation">Activate exact model versions</option>
                    <option value="paid_scope">Approve this paid scope</option>
                  </select>
                </label>
                <label>
                  Authorization reference
                  <input name="reference" required minLength={5} />
                </label>
                <label>
                  Decision expiry
                  <input name="expiry" type="datetime-local" required />
                </label>
                <button disabled={busy}>Record Admin decision</button>
              </Form>
            </details>
          )}
          <details>
            <summary>Operator authorization and exact snapshot</summary>
            <p>
              The operator records separately approved authority in the owner-only local
              workspace-authority.json file. Creating a group or saving a key does not grant
              authority. Do not place a provider key in this file.
            </p>
            <p>
              Project: {base.replace('/projects/', '')} · exact group subject:{' '}
              {selected.subject_hash}
            </p>
            <pre>{JSON.stringify(selected.snapshot, null, 2)}</pre>
          </details>
        </section>
      )}
    </section>
  );
}
