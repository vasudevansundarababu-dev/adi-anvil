'use client';

import { useCallback, useEffect, useState } from 'react';
import { workspaceApi } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';

type Client = {
  id: string;
  name: string;
  can_resolve: boolean;
  expires_at: string;
  revoked: boolean;
  workload_identity: boolean;
};

export default function DatasetExportAccess({ base }: { base: string }) {
  const api = base.replace(/\/workspace$/, '') + '/dataset-exports';
  const [keyless, setKeyless] = useState(false);
  const [clients, setClients] = useState<Client[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const refresh = useCallback(async () => {
    try {
      const [contract, items] = await Promise.all([
        workspaceApi(api + '/contracts'),
        workspaceApi(api + '/clients'),
      ]);
      if (!Array.isArray(items)) throw new Error('Invalid access response');
      setKeyless(contract.authentication?.mode === 'workload_identity');
      setClients(items);
      setError('');
    } catch {
      setError(
        'Unable to load Authoring access. Sign in as this project’s Admin or contact the Forge operator.',
      );
    }
  }, [api]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function revoke(id: string) {
    setBusy(true);
    setError('');
    try {
      await workspaceApi(api + '/clients/' + id + '/revoke', 'POST', {});
      setNotice('Access revoked. Existing service tokens can no longer use this grant.');
      await refresh();
    } catch {
      setError('Revocation could not be confirmed. Refresh access before trying again.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={styles.panel} aria-label="Authoring integration access">
      <h2>Authoring integration access</h2>
      <p>
        Authoring and Forge connect using their managed service identities. You do not need to create,
        copy or store an integration API key.
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {!keyless && (
        <p>
          Keyless integration is awaiting Forge setup and verification. No key entry is required
          from you.
        </p>
      )}
      <p>
        Project scope, expiry, revocation and the sponsoring Admin’s current access are checked on
        every call. Integration access does not authorize model spending or launch a benchmark.
      </p>
      <button disabled={busy} onClick={() => void refresh()}>
        Refresh access
      </button>
      {clients.length === 0 ? (
        <p>No project integration grant is installed. Forge owns this setup.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Connection</th>
              <th>Scope</th>
              <th>Expires</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {clients.map((client) => (
              <tr key={client.id}>
                <td>{client.name}</td>
                <td>
                  {client.workload_identity
                    ? 'Managed service identity'
                    : 'Awaiting service identity migration'}
                </td>
                <td>{client.can_resolve ? 'Validate and provision' : 'Validate only'}</td>
                <td>{new Date(client.expires_at).toLocaleString()}</td>
                <td>
                  {client.revoked
                    ? 'Revoked'
                    : new Date(client.expires_at).getTime() <= Date.now()
                      ? 'Expired'
                      : client.workload_identity && keyless
                        ? 'Grant active; runtime verification separate'
                        : 'Awaiting Forge setup'}
                </td>
                <td>
                  <button disabled={busy || client.revoked} onClick={() => void revoke(client.id)}>
                    Revoke {client.name}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
