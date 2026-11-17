'use client';

import { useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import { captureDatabaseStatus } from '../lib/captureDatabaseStatus';
import RuntimeQAUpdate from './RuntimeQAUpdate';
import s from './ModernWorkspace.module.css';

type RuntimeRole = {
  role: string;
  current_image_digest: string | null;
  candidate_image_digest: string | null;
  source_commit: string | null;
  lock_digest: string | null;
  architecture: string | null;
  interpreter: string | null;
  installed_adapters: { name: string; version: string }[];
  last_successful_operation: string | null;
  operation_evidence_digest: string | null;
  qualification_state: string;
  expires_at: string | null;
  revoked: boolean | null;
  rollback_digest: string | null;
  last_verified_at: string | null;
  provenance: string | null;
  blockers: string[];
  candidate_blockers: string[];
  qa_operator?: { qa_activation_available: boolean; qa_rollback_available: boolean };
};
type Inventory = {
  roles: RuntimeRole[];
  candidate_staging_only: boolean;
  deployment_available: boolean;
  capture_database?: unknown;
};
const labels: Record<string, string> = {
  api: 'API',
  'business-worker': 'Business worker',
  'golden-grader': 'Evaluator grader',
  'golden-scheduler': 'Execution scheduler',
  'golden-native-coordinator': 'Harbor coordinator',
  'task-environment': 'Task environment',
  'isolated-python-runner': 'Custom Python runner',
};
const reasons: Record<string, string> = {
  actual_role_observation_required: 'The installed runtime has not been verified.',
  invalid_operator_observation: 'The recorded runtime evidence could not be verified.',
  deployed_role_observation_required: 'A check of the deployed runtime is still required.',
  independent_runtime_qualification_required:
    'Installed software has not passed independent execution checks.',
  qualification_revoked: 'The previous runtime qualification was revoked.',
  current_qualification_required: 'Runtime qualification has expired.',
  source_bound_operation_qualification_required:
    'A successful operation with the exact Project binding is not yet verified.',
  independent_exact_release_checks_required:
    'The candidate release still needs its independent checks.',
  fresh_build_ledger_failure_chain_and_CAS_required:
    'The build and retry limits must be checked before rollout.',
  Harbor_gated_rollout_required: 'The candidate has not completed the QA release process.',
  candidate_allowlist_expired_or_revoked: 'The candidate release is no longer authorized.',
};
const reason = (code: string) => reasons[code] || code.replaceAll('_', ' ');
export default function RuntimeInventory({ base }: { base: string }) {
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [updateRole, setUpdateRole] = useState<string | null>(null);
  const captureDatabase = captureDatabaseStatus(inventory?.capture_database);
  useEffect(() => {
    let active = true;
    setBusy(true);
    setError('');
    setInventory(null);
    api(base + '/workspace/runtime-admin/roles')
      .then((value) => {
        if (
          !value ||
          !Array.isArray(value.roles) ||
          value.roles.some(
            (role: RuntimeRole) =>
              typeof role.role !== 'string' ||
              !Array.isArray(role.installed_adapters) ||
              !Array.isArray(role.blockers) ||
              !Array.isArray(role.candidate_blockers),
          )
        )
          throw new Error('Runtime inventory response is incomplete. No runtime is marked Ready.');
        if (active) setInventory(value);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [base, revision]);
  return (
    <section className={s.panel} aria-label="Installed runtime software">
      <div className={s.pageHead}>
        <h2>Installed software & runtime checks</h2>
        <button disabled={busy} onClick={() => setRevision((value) => value + 1)}>
          Refresh runtime checks
        </button>
      </div>
      <p>
        Versions and status come from the deployed runtime evidence. A saved framework profile does
        not install or qualify software.
      </p>
      {busy && <p role="status">Loading recorded runtime checks…</p>}
      {error && <p role="alert">{error}</p>}
      {inventory && (
        <>
          <section aria-label="Capture database readiness">
            <h3>Capture database</h3>
            <strong>{captureDatabase.ready ? 'Ready' : 'Not ready'}</strong>
            <p>Configuration: {captureDatabase.configurationReady ? 'Ready' : 'Not ready'}</p>
            <p>{captureDatabase.message}</p>
            <p>Forge provisioning owns this setup. Runtime qualification is still required.</p>
          </section>
          <div className={s.tableScroll}>
            <table>
              <thead>
                <tr>
                  <th>Runtime</th>
                  <th>Software & version</th>
                  <th>Status</th>
                  <th>Last checked</th>
                  <th>Update</th>
                </tr>
              </thead>
              <tbody>
                {inventory.roles.map((role) => {
                  const ready =
                    role.qualification_state === 'reported_qualified' &&
                    role.revoked === false &&
                    role.blockers.length === 0;
                  return (
                    <tr key={role.role}>
                      <td>{labels[role.role] || role.role}</td>
                      <td>
                        {role.installed_adapters.length
                          ? role.installed_adapters.map((adapter) => (
                              <div key={adapter.name}>
                                {adapter.name} · {adapter.version}
                              </div>
                            ))
                          : 'Not verified'}
                      </td>
                      <td>
                        <strong>{ready ? 'Ready' : 'Not ready'}</strong>
                        {!ready &&
                          role.blockers.map((blocker) => <p key={blocker}>{reason(blocker)}</p>)}
                        {!ready && !role.blockers.length && (
                          <p>Current execution evidence is incomplete.</p>
                        )}
                      </td>
                      <td>
                        {role.last_verified_at
                          ? new Date(role.last_verified_at).toLocaleString()
                          : 'Not checked'}
                        <details>
                          <summary>Runtime evidence</summary>
                          <p>Observed in: {role.provenance || 'Unknown'}</p>
                          <p>
                            Last successful operation:{' '}
                            {role.last_successful_operation || 'Not verified'}
                          </p>
                          <p>
                            Qualification expiry:{' '}
                            {role.expires_at
                              ? new Date(role.expires_at).toLocaleString()
                              : 'Unknown'}
                          </p>
                          <p style={{ overflowWrap: 'anywhere' }}>
                            Current image: {role.current_image_digest || 'Unknown'}
                          </p>
                          <p style={{ overflowWrap: 'anywhere' }}>
                            Source: {role.source_commit || 'Unknown'} · dependency lock:{' '}
                            {role.lock_digest || 'Unknown'}
                          </p>
                          <p>
                            Platform: {role.architecture || 'Unknown'} · interpreter:{' '}
                            {role.interpreter || 'Unknown'}
                          </p>
                          <p style={{ overflowWrap: 'anywhere' }}>
                            Operation evidence: {role.operation_evidence_digest || 'Unknown'}
                          </p>
                          <p style={{ overflowWrap: 'anywhere' }}>
                            Rollback image: {role.rollback_digest || 'Unknown'}
                          </p>
                        </details>
                      </td>
                      <td>
                        <button
                          disabled={busy || !role.qa_operator}
                          title="Check independently admitted QA updates and recorded operation status."
                          onClick={() => setUpdateRole(role.role)}
                        >
                          Update
                        </button>
                        <small>
                          {role.qa_operator
                            ? 'Check eligible releases and serving evidence.'
                            : 'The QA update interface is not available in this deployment.'}
                        </small>
                        {role.candidate_image_digest && (
                          <details>
                            <summary>Candidate awaiting checks</summary>
                            <p style={{ overflowWrap: 'anywhere' }}>
                              {role.candidate_image_digest}
                            </p>
                            {role.candidate_blockers.map((blocker) => (
                              <p key={blocker}>{reason(blocker)}</p>
                            ))}
                          </details>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {!inventory.roles.length && <p>No runtime observations are available.</p>}
          {updateRole && (
            <RuntimeQAUpdate
              key={base + updateRole}
              base={base}
              role={updateRole}
              label={labels[updateRole] || updateRole}
              onClose={() => setUpdateRole(null)}
            />
          )}
          <p>
            Run still verifies the exact Project, evaluator, environment and release bindings before
            execution.
          </p>
        </>
      )}
    </section>
  );
}
