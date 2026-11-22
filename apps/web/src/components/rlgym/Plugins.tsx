'use client';

// Admin → Evaluators → Verifier plug-ins (D22): installed versions, install from a manifest, re-test, deprecate,
// revoke. A version is qualified only when its own known cases pass; Studio lists qualified versions for S7 blocks.
import { useState } from 'react';
import { GymApiError, send, wsBase } from './api';
import { Badge, Failure, Loading, useData, useGym } from './ui';

export default function PluginsPanel() {
  const { ws, me, say } = useGym();
  const { data, error, reload } = useData<any>(`${wsBase(ws)}/evaluators/plugins?all=true`);
  const [manifest, setManifest] = useState('');
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const admin = me.profile === 'admin';
  async function act(path: string, body: object, done: string) {
    setFailure(null);
    try {
      await send('POST', `${wsBase(ws)}${path}`, body);
      say(done);
      reload();
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  return (
    <section className="card">
      <h4>Verifier plug-ins</h4>
      <small>
        Each plug-in runs in its own sandbox image with no network, a read-only file system and
        limits. A version is qualified when its known cases give their expected verdicts.
      </small>
      <Loading data={data} error={error}>
        {() =>
          data && (
            <table className="blocks">
              <thead>
                <tr>
                  <th>Plug-in</th>
                  <th>Version</th>
                  <th>Upstream</th>
                  <th>Image</th>
                  <th>Known cases</th>
                  <th>State</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.items.map((p: any) => (
                  <tr key={`${p.id}-${p.version}`}>
                    <td>
                      {p.name} <code>{p.id}</code>
                    </td>
                    <td>{p.version}</td>
                    <td>{p.upstream ? `${p.upstream.package} ${p.upstream.version}` : '—'}</td>
                    <td>
                      <code>{String(p.image).slice(0, 19)}…</code>
                    </td>
                    <td>
                      {(p.known_case_results ?? [])
                        .map((k: any) => `${k.name}: ${k.result}`)
                        .join(' · ')}
                    </td>
                    <td>
                      <Badge
                        state={
                          p.state === 'qualified'
                            ? 'ready'
                            : p.state === 'revoked'
                              ? 'failed'
                              : 'deprecated'
                        }
                        label={p.state}
                      />
                    </td>
                    <td>
                      {admin && p.state !== 'revoked' && (
                        <span className="row">
                          <button
                            onClick={() =>
                              act(
                                `/evaluators/plugins/${p.id}/${p.version}/test`,
                                {},
                                `${p.id} ${p.version} tested.`,
                              )
                            }
                          >
                            Re-test
                          </button>
                          {(['deprecate', 'revoke'] as const).map((a) => (
                            <button
                              key={a}
                              onClick={() => {
                                const reason = window.prompt(`Reason to ${a} ${p.id} ${p.version}`);
                                if (reason)
                                  act(
                                    `/evaluators/plugins/${p.id}/${p.version}/${a}`,
                                    { reason },
                                    `${p.id} ${p.version}: ${a}d.`,
                                  );
                              }}
                            >
                              {a === 'deprecate' ? 'Deprecate' : 'Revoke'}
                            </button>
                          ))}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        }
      </Loading>
      {admin && (
        <>
          <label>
            Install a plug-in version (paste its adi.verifier-plugin.v1 manifest; the image must
            already be in local Docker)
            <textarea rows={4} value={manifest} onChange={(e) => setManifest(e.target.value)} />
          </label>
          <button
            className="primary"
            disabled={!manifest.trim()}
            onClick={() => {
              let parsed: object;
              try {
                parsed = JSON.parse(manifest);
              } catch {
                say('The manifest is not valid JSON.');
                return;
              }
              act('/evaluators/plugins', { manifest: parsed }, 'Plug-in installed and tested.');
            }}
          >
            Install plug-in version
          </button>
        </>
      )}
      <Failure error={failure} />
    </section>
  );
}
