'use client';

// Admin → Live approvals: the owner's written permission for one provider and model, with caps and verified prices.
// Nothing here calls a model; live calls also need ANVIL_LIVE_PROVIDERS_ENABLED=true and a key in the allowlist.
import { useState } from 'react';
import { GymApiError, send, when, wsBase } from './api';
import { Badge, Failure, Loading, useData, useGym } from './ui';

const PROVIDERS = ['anthropic', 'openai', 'google', 'vertex', 'huggingface'];
const USES = ['agent', 'judge', 'generator', 'probe', 'key_test'];

export default function LiveApprovals() {
  const { ws, me, say } = useGym();
  const { data, error, reload } = useData<any>(`${wsBase(ws)}/live/approvals`);
  const [form, setForm] = useState<any>({
    provider: 'anthropic',
    model_id: '',
    hf_revision: '',
    uses: ['agent'],
    per_run_cap_usd: '',
    total_cap_usd: '',
    price_in_per_mtok_usd: '',
    price_out_per_mtok_usd: '',
    prices_note: '',
    expires_at: '',
  });
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const admin = me.profile === 'admin';
  const set = (k: string) => (e: { target: { value: string } }) =>
    setForm({ ...form, [k]: e.target.value });
  return (
    <Loading data={data} error={error}>
      {() =>
        data && (
          <>
            <p>
              A live approval names the exact provider and model, what it may be used for, a per-run
              cap and a total cap, and the prices you verified. A live run is refused without one,
              or when its estimate is over a cap, and it stops at its cap. The person who records an
              approval cannot also start the live run.{' '}
              <Badge
                state={data.live_enabled ? 'ready' : 'draft'}
                label={
                  data.live_enabled ? 'Live calls enabled locally' : 'Live calls disabled locally'
                }
              />
            </p>
            <table className="blocks">
              <thead>
                <tr>
                  <th>Approval</th>
                  <th>Provider · model</th>
                  <th>Uses</th>
                  <th>Caps (run · total)</th>
                  <th>Spent · left</th>
                  <th>Prices / Mtok (in · out)</th>
                  <th>Approved by · expires</th>
                  <th>State</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.items.map((a: any) => (
                  <tr key={a.id}>
                    <td>
                      <code>{a.id}</code>
                    </td>
                    <td>
                      {a.provider} · <code>{a.model_id}</code>
                      {a.hf_revision && <small> @{a.hf_revision.slice(0, 12)}</small>}
                    </td>
                    <td>{a.uses.join(', ')}</td>
                    <td>
                      ${Number(a.per_run_cap_usd)} · ${Number(a.total_cap_usd)}
                    </td>
                    <td>
                      ${Number(a.spent_usd).toFixed(4)} · ${Number(a.remaining_usd).toFixed(4)}
                    </td>
                    <td>
                      ${Number(a.price_in_per_mtok_usd)} · ${Number(a.price_out_per_mtok_usd)}
                      <small>{a.prices_note}</small>
                    </td>
                    <td>
                      {a.approved_by} · {when(a.expires_at)}
                    </td>
                    <td>
                      <Badge
                        state={a.state === 'active' ? 'ready' : 'deprecated'}
                        label={a.state}
                      />
                    </td>
                    <td>
                      {admin && a.state === 'active' && (
                        <button
                          onClick={async () => {
                            const reason = window.prompt('Reason for revoking');
                            if (!reason) return;
                            try {
                              await send('POST', `${wsBase(ws)}/live/approvals/${a.id}/revoke`, {
                                reason,
                              });
                              say(`Approval ${a.id} revoked.`);
                              reload();
                            } catch (e) {
                              setFailure(e as GymApiError);
                            }
                          }}
                        >
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.items.length === 0 && (
              <small>No live approvals. Runs use the controlled mock.</small>
            )}
            {admin && (
              <section className="card">
                <h4>Record a live approval</h4>
                <div className="row">
                  <label>
                    Provider
                    <select value={form.provider} onChange={set('provider')}>
                      {PROVIDERS.map((p) => (
                        <option key={p}>{p}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Exact model id
                    <input value={form.model_id} onChange={set('model_id')} />
                  </label>
                  {form.provider === 'huggingface' && (
                    <label>
                      Revision (40 hex)
                      <input value={form.hf_revision} onChange={set('hf_revision')} />
                    </label>
                  )}
                </div>
                <div className="row">
                  {USES.map((u) => (
                    <label key={u}>
                      <input
                        type="checkbox"
                        checked={form.uses.includes(u)}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            uses: e.target.checked
                              ? [...form.uses, u]
                              : form.uses.filter((x: string) => x !== u),
                          })
                        }
                      />{' '}
                      {u}
                    </label>
                  ))}
                </div>
                <div className="row">
                  <label>
                    Per-run cap (USD)
                    <input value={form.per_run_cap_usd} onChange={set('per_run_cap_usd')} />
                  </label>
                  <label>
                    Total cap (USD)
                    <input value={form.total_cap_usd} onChange={set('total_cap_usd')} />
                  </label>
                  <label>
                    Input price per million tokens (USD)
                    <input
                      value={form.price_in_per_mtok_usd}
                      onChange={set('price_in_per_mtok_usd')}
                    />
                  </label>
                  <label>
                    Output price per million tokens (USD)
                    <input
                      value={form.price_out_per_mtok_usd}
                      onChange={set('price_out_per_mtok_usd')}
                    />
                  </label>
                </div>
                <label>
                  Where and when you verified the prices
                  <input value={form.prices_note} onChange={set('prices_note')} />
                </label>
                <label>
                  Expires (within 31 days)
                  <input
                    type="datetime-local"
                    value={form.expires_at}
                    onChange={set('expires_at')}
                  />
                </label>
                <button
                  className="primary"
                  disabled={!form.model_id || !form.prices_note || !form.expires_at}
                  onClick={async () => {
                    setFailure(null);
                    try {
                      const out = await send('POST', `${wsBase(ws)}/live/approvals`, {
                        ...form,
                        hf_revision: form.provider === 'huggingface' ? form.hf_revision : undefined,
                        expires_at: new Date(form.expires_at).toISOString(),
                      });
                      say(`Live approval ${out.id} recorded.`);
                      reload();
                    } catch (e) {
                      setFailure(e as GymApiError);
                    }
                  }}
                >
                  Record approval
                </button>
                <Failure error={failure} />
              </section>
            )}
          </>
        )
      }
    </Loading>
  );
}
