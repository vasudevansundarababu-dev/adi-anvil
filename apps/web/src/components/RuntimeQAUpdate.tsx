'use client';

import { useEffect, useRef, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import s from './ModernWorkspace.module.css';

type Admission = {
  id: string;
  candidate_id: string;
  expected_observation_id: string;
  action: 'activate' | 'rollback';
  image_digest: string;
  source_commit: string;
  lock_digest: string;
  admission_sha256: string;
  expires_at: string;
  blockers: string[];
};
type JobSummary = {
  job_id: string;
  state: string;
  scope: string;
  action?: string;
  admission_id?: string;
  client_operation_id?: string;
};
type Discovery = {
  role: string;
  admissions: Admission[];
  qa_activation_available: boolean;
  qa_rollback_available: boolean;
  blockers?: string[];
};
type Intent = {
  admission_id: string;
  client_operation_id: string;
  request_key: string;
  job_id?: string;
};
type Status = {
  job: {
    id: string;
    role: string;
    scope: string;
    state: string;
    request: {
      admission_id?: string;
      client_operation_id?: string;
      image_digest?: string;
      action?: string;
    };
    request_sha256: string;
  };
  operation_receipts: { id: string; phase: string; receipt_sha256: string; created_at: string }[];
  last_verified_serving_observation: {
    current_image_digest: string | null;
    source_commit: string | null;
    qualification_state: string;
    blockers: string[];
  };
};
const reason = (code: string) =>
  ({
    qualified_QA_operator_not_enabled: 'The qualified QA update operator is not enabled.',
    fresh_operator_ledger_CAS_required:
      'The operator must verify the build limit and unchanged serving version before applying this release.',
    exact_host_readback_required:
      'The operator must verify the actual serving version after the change.',
  })[code] || code.replaceAll('_', ' ');

export default function RuntimeQAUpdate({
  base,
  role,
  label,
  onClose,
}: {
  base: string;
  role: string;
  label: string;
  onClose: () => void;
}) {
  const endpoint = base + '/workspace/runtime-admin';
  const storageKey = 'anvil-runtime-update:' + base + ':' + role;
  const [discovery, setDiscovery] = useState<Discovery | null>(null);
  const [choice, setChoice] = useState('');
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [intent, setIntent] = useState<Intent | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const submitting = useRef(false);
  function retain(value: Intent | null) {
    if (value) sessionStorage.setItem(storageKey, JSON.stringify(value));
    else sessionStorage.removeItem(storageKey);
    setIntent(value);
  }
  async function readJob(id: string, expectedAdmission?: string, expectedOperation?: string) {
    const value = (await api(endpoint + '/updates/' + encodeURIComponent(id))) as Status;
    if (
      value.job?.id !== id ||
      value.job.role !== role ||
      value.job.scope !== 'qa' ||
      !Array.isArray(value.operation_receipts) ||
      !value.last_verified_serving_observation ||
      (expectedAdmission && value.job.request?.admission_id !== expectedAdmission) ||
      (expectedOperation && value.job.request?.client_operation_id !== expectedOperation)
    )
      throw new Error(
        'The update status does not match the requested QA operation. No new operation was submitted.',
      );
    return value;
  }
  useEffect(() => {
    let active = true;
    setBusy(true);
    setError('');
    setDiscovery(null);
    setStatus(null);
    (async () => {
      const saved = sessionStorage.getItem(storageKey);
      let pending = saved ? (JSON.parse(saved) as Intent) : null;
      if (
        pending &&
        (typeof pending.admission_id !== 'string' ||
          typeof pending.request_key !== 'string' ||
          typeof pending.client_operation_id !== 'string')
      )
        throw new Error(
          'The saved update reference could not be verified. Reconcile the existing operation before submitting another.',
        );
      const [data, history] = await Promise.all([
        api(
          endpoint + '/roles/' + encodeURIComponent(role) + '/qa-admissions',
        ) as Promise<Discovery>,
        api(endpoint + '/roles/' + encodeURIComponent(role) + '/updates?limit=20') as Promise<{
          role: string;
          jobs: JobSummary[];
        }>,
      ]);
      if (
        data.role !== role ||
        !Array.isArray(data.admissions) ||
        history.role !== role ||
        !Array.isArray(history.jobs) ||
        history.jobs.some(
          (job) =>
            typeof job.job_id !== 'string' ||
            typeof job.state !== 'string' ||
            typeof job.scope !== 'string',
        ) ||
        data.admissions.some(
          (item) =>
            typeof item.id !== 'string' ||
            typeof item.candidate_id !== 'string' ||
            typeof item.expected_observation_id !== 'string' ||
            !['activate', 'rollback'].includes(item.action) ||
            typeof item.image_digest !== 'string' ||
            typeof item.source_commit !== 'string' ||
            typeof item.lock_digest !== 'string' ||
            typeof item.admission_sha256 !== 'string' ||
            !Array.isArray(item.blockers),
        )
      )
        throw new Error('QA update eligibility is incomplete. No update is available to submit.');
      if (pending && !pending.job_id) {
        const matches = history.jobs.filter(
          (job) =>
            job.scope === 'qa' &&
            job.admission_id === pending!.admission_id &&
            job.client_operation_id === pending!.client_operation_id,
        );
        if (matches.length === 1) pending = { ...pending, job_id: matches[0].job_id };
      }
      const recorded = pending?.job_id
        ? await readJob(pending.job_id, pending.admission_id, pending.client_operation_id)
        : null;
      if (active) {
        setDiscovery(data);
        setStatus(recorded);
        setJobs(history.jobs);
        setIntent(pending);
        if (pending?.job_id) sessionStorage.setItem(storageKey, JSON.stringify(pending));
        setChoice((previous) =>
          data.admissions.some((item) => item.id === previous) ? previous : '',
        );
      }
    })()
      .catch((e) => {
        if (active) {
          setStatus(null);
          setError(e.message);
        }
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [endpoint, role, storageKey, revision]);
  const selected = discovery?.admissions.find((item) => item.id === choice);
  const terminalStates = new Set(['activated', 'rolled_back', 'failed', 'local_qualified']);
  const activeJobs = jobs.filter((job) => !terminalStates.has(job.state));
  const failedAdmissions = new Set(
    jobs
      .filter(
        (job) =>
          job.state === 'failed' || (job.state === 'rolled_back' && job.action === 'activate'),
      )
      .map((job) => job.admission_id),
  );
  const statusMatchesIntent =
    !!status &&
    (!intent ||
      (status.job.id === intent.job_id &&
        status.job.request.admission_id === intent.admission_id &&
        status.job.request.client_operation_id === intent.client_operation_id));
  const canSubmit =
    !!selected &&
    !busy &&
    !intent &&
    !activeJobs.length &&
    !failedAdmissions.has(selected.id) &&
    (selected.action === 'activate'
      ? discovery?.qa_activation_available === true
      : discovery?.qa_rollback_available === true) &&
    Number.isFinite(Date.parse(selected.expires_at)) &&
    Date.parse(selected.expires_at) > Date.now();
  return (
    <section className={s.panel} aria-label={'QA update ' + label}>
      <div className={s.pageHead}>
        <h3>{label} update</h3>
        <button disabled={busy} onClick={onClose}>
          Close update details
        </button>
      </div>
      <p>
        Only independently admitted QA releases are offered. Selecting or queueing a release does
        not mean it is installed or ready for benchmarking.
      </p>
      {busy && <p role="status">Checking recorded update eligibility or status…</p>}
      {error && <p role="alert">{error}</p>}
      <button disabled={busy} onClick={() => setRevision((previous) => previous + 1)}>
        Refresh eligibility &amp; reconcile
      </button>
      {!!activeJobs.length && (
        <p>
          An existing runtime operation is still active or has an unknown outcome. Reconcile it
          before another update.
        </p>
      )}
      {!!jobs.length && (
        <details>
          <summary>Recent runtime operations</summary>
          {jobs.map((job) => (
            <p key={job.job_id}>
              {job.scope} · {job.action || 'Operation'} · {job.state} · {job.job_id}
              {job.scope === 'qa' && !intent && (
                <button
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    setError('');
                    try {
                      setStatus(await readJob(job.job_id));
                    } catch (e) {
                      setError((e as Error).message);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  View recorded update
                </button>
              )}
            </p>
          ))}
        </details>
      )}
      {discovery && (
        <>
          {(discovery.blockers || []).map((blocker) => (
            <p key={blocker}>{reason(blocker)}</p>
          ))}
          {!discovery.admissions.length && (
            <p>No eligible QA release or rollback is available for this runtime.</p>
          )}
          <label>
            Eligible QA release
            <select
              disabled={busy || !!intent}
              value={choice}
              onChange={(event) => setChoice(event.target.value)}
            >
              <option value="">Select a reviewed release</option>
              {discovery.admissions.map((item) => (
                <option key={item.id} value={item.id} disabled={failedAdmissions.has(item.id)}>
                  {item.action === 'rollback' ? 'Rollback' : 'Update'} ·{' '}
                  {item.source_commit.slice(0, 12)} · {item.image_digest.slice(-12)}
                </option>
              ))}
            </select>
          </label>
          {selected && (
            <details open>
              <summary>Selected release evidence</summary>
              <p>
                Action: {selected.action}. Eligibility expires{' '}
                {new Date(selected.expires_at).toLocaleString()}.
              </p>
              <p style={{ overflowWrap: 'anywhere' }}>Image: {selected.image_digest}</p>
              <p style={{ overflowWrap: 'anywhere' }}>
                Source: {selected.source_commit} · dependency lock: {selected.lock_digest}
              </p>
              <p style={{ overflowWrap: 'anywhere' }}>
                Independent admission: {selected.admission_sha256}
              </p>
              {selected.blockers.map((blocker) => (
                <p key={blocker}>{reason(blocker)}</p>
              ))}
            </details>
          )}
          <button
            disabled={!canSubmit}
            onClick={async () => {
              if (!selected || !canSubmit || submitting.current) return;
              submitting.current = true;
              setBusy(true);
              setError('');
              setStatus(null);
              const pending = {
                admission_id: selected.id,
                client_operation_id: crypto.randomUUID(),
                request_key: crypto.randomUUID(),
              };
              let referenceRetained = false;
              let queued = false;
              try {
                // Retain the intent before the POST; an uncertain response blocks all
                // further submissions until a read-only reconciliation finds the job.
                retain(pending);
                referenceRetained = true;
                const result = await api(
                  endpoint + '/roles/' + encodeURIComponent(role) + '/qa-updates',
                  'POST',
                  {
                    candidate_id: selected.candidate_id,
                    expected_observation_id: selected.expected_observation_id,
                    admission_id: selected.id,
                    client_operation_id: pending.client_operation_id,
                    action: selected.action,
                  },
                  undefined,
                  pending.request_key,
                );
                if (
                  typeof result.job_id !== 'string' ||
                  result.scope !== 'qa' ||
                  result.action !== selected.action
                )
                  throw new Error(
                    'The update response could not be confirmed. Reconcile its status before proceeding.',
                  );
                queued = true;
                retain({ ...pending, job_id: result.job_id });
                setStatus(await readJob(result.job_id, selected.id, pending.client_operation_id));
              } catch (e) {
                const status = (e as Error & { status?: number }).status;
                if (
                  !queued &&
                  referenceRetained &&
                  status &&
                  status >= 400 &&
                  status < 500 &&
                  status !== 408
                )
                  retain(null);
                setError((e as Error).message);
              } finally {
                submitting.current = false;
                setBusy(false);
              }
            }}
          >
            {selected?.action === 'rollback' ? 'Request QA rollback' : 'Request QA update'}
          </button>
        </>
      )}
      {intent && !status && (
        <p role="alert">
          The update outcome is not confirmed. The request is retained and will not be submitted
          again. Use read-only reconciliation or ask the release operator to inspect it.
        </p>
      )}
      {status && (
        <section aria-label="Recorded QA update status">
          <h4>Recorded operation: {status.job.state.replaceAll('_', ' ')}</h4>
          <p>
            Job {status.job.id} · {status.job.request.action || 'Action not recorded'}
          </p>
          <p>
            The job state and physical serving observation are separate. A completed software update
            does not establish evaluator or benchmark readiness.
          </p>
          <p style={{ overflowWrap: 'anywhere' }}>Request record: {status.job.request_sha256}</p>
          <p style={{ overflowWrap: 'anywhere' }}>
            Last verified serving image:{' '}
            {status.last_verified_serving_observation.current_image_digest || 'Not verified'}
          </p>
          <p>
            Runtime qualification:{' '}
            {status.last_verified_serving_observation.qualification_state.replaceAll('_', ' ')}
          </p>
          {(status.last_verified_serving_observation.blockers || []).map((blocker) => (
            <p key={blocker}>{reason(blocker)}</p>
          ))}
          <details>
            <summary>Operation receipts</summary>
            {status.operation_receipts.length ? (
              status.operation_receipts.map((receipt) => (
                <p key={receipt.id} style={{ overflowWrap: 'anywhere' }}>
                  {receipt.phase} · {receipt.created_at} · {receipt.receipt_sha256}
                </p>
              ))
            ) : (
              <p>No physical operation receipt is recorded yet.</p>
            )}
          </details>
          {statusMatchesIntent && ['activated', 'rolled_back'].includes(status.job.state) && (
            <button
              disabled={busy}
              onClick={() => {
                retain(null);
                setStatus(null);
                setRevision((previous) => previous + 1);
              }}
            >
              Check subsequent eligible releases
            </button>
          )}
          {statusMatchesIntent &&
            status.job.state === 'failed' &&
            discovery?.admissions.some(
              (item) =>
                item.id !== status.job.request.admission_id && !failedAdmissions.has(item.id),
            ) && (
              <button
                disabled={busy}
                onClick={() => {
                  retain(null);
                  setStatus(null);
                  setChoice('');
                  setRevision((previous) => previous + 1);
                }}
              >
                Review newly admitted corrective releases
              </button>
            )}
        </section>
      )}
      <p>
        Staging and Production remain on hold. This control does not enable paid model calls or
        automatically retry a failed operation.
      </p>
    </section>
  );
}
