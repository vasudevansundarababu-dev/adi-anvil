'use client';

import Link from 'next/link';
import { useState } from 'react';
import { GymApiError, send, when, wsBase } from './api';
import { Badge, Failure, Hash, Loading, Search, Tabs, useData, useGym } from './ui';

const STATUS_TONE: Record<string, string> = {
  Ready: 'ready',
  'Not tested in 24 h': 'requested',
  Unreachable: 'failed',
  'Setup pending': 'registered',
  Disabled: 'revoked',
  'Live calls disabled': 'deprecated',
};

const PROVIDER_LABEL: Record<string, string> = {
  huggingface: 'Hugging Face',
  openai: 'OpenAI',
  google: 'Google (Gemini API)',
  anthropic: 'Anthropic',
  mistral: 'Mistral',
  vertex: 'Gemini on Vertex AI',
  mock: 'Controlled mock (local)',
};

export function Models({ parts }: { parts: string[] }) {
  const sub = parts[0] ?? 'frontier';
  if (parts[0] === 'model' && parts[1]) return <ModelPage id={parts[1]} />;
  return (
    <>
      <Tabs
        current={sub}
        items={[
          { key: 'open', label: 'Open weight (Hugging Face)', href: '/gym/admin/models/open' },
          {
            key: 'frontier',
            label: 'Frontier (closed weight)',
            href: '/gym/admin/models/frontier',
          },
          { key: 'fine-tuned', label: 'ADI fine-tuned', href: '/gym/admin/models/fine-tuned' },
          { key: 'sets', label: 'Model sets', href: '/gym/admin/models/sets' },
        ]}
      />
      {sub === 'fine-tuned' && (
        <p>Fine-tuned models provided by ADI will appear here. Coming later.</p>
      )}
      {sub === 'sets' && <ModelSets />}
      {(sub === 'open' || sub === 'frontier') && (
        <ModelList kind={sub === 'open' ? 'open_weight' : 'frontier'} />
      )}
    </>
  );
}

function ModelList({ kind }: { kind: 'open_weight' | 'frontier' }) {
  const { ws, say } = useGym();
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [form, setForm] = useState<any>(null);
  const params = new URLSearchParams({ kind, ...(q ? { q } : {}), ...(status ? { status } : {}) });
  const list = useData<any>(`${wsBase(ws)}/systems?${params}`);
  return (
    <>
      <div className="toolbar">
        <Search value={q} onChange={setQ} placeholder="Search models" />
        <label>
          <small>Status</small>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            aria-label="Model status"
          >
            <option value="">All</option>
            {Object.keys(STATUS_TONE).map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <button className="primary" onClick={() => setForm({ kind })}>
          New model
        </button>
      </div>
      {list.data && !list.data.live_enabled && (
        <small>
          Live provider calls are off locally. Models on a real provider are recorded and show “Live
          calls disabled”; only the controlled mock answers probes.
        </small>
      )}
      <Loading data={list.data} error={list.error}>
        {() => (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Model</th>
                  <th>{kind === 'open_weight' ? 'Hugging Face' : 'Provider'}</th>
                  <th>{kind === 'open_weight' ? 'Serving' : 'Limits'}</th>
                  <th>Credential</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'left' }}>
                      No models in this state.
                    </td>
                  </tr>
                )}
                {list.data.items.map((m: any) => (
                  <tr key={m.system_id}>
                    <td>
                      <Link className="link" href={`/gym/admin/models/model/${m.system_id}`}>
                        {m.name}
                      </Link>
                      <small>
                        Version {m.latest.version} · <Hash value={m.latest.config_sha256} />
                        {m.synthetic ? ' · synthetic' : ''}
                      </small>
                    </td>
                    <td>
                      {PROVIDER_LABEL[m.latest.provider] ?? m.latest.provider}
                      <small>
                        {kind === 'open_weight'
                          ? `${m.latest.model_id} · Revision ${(m.latest.hf_revision ?? '').slice(0, 8)}`
                          : `model ID ${m.latest.model_id}`}
                      </small>
                    </td>
                    <td>
                      {kind === 'open_weight'
                        ? m.latest.serving.mode
                        : `${m.latest.limits.rpm} rpm · $${m.latest.limits.spend_per_episode_usd} / episode`}
                    </td>
                    <td>
                      Saved key · {m.key.name} ••••{m.key.last4}
                    </td>
                    <td>
                      <Badge state={STATUS_TONE[m.status]} label={m.status} />
                    </td>
                    <td>
                      <div className="row" style={{ justifyContent: 'flex-end' }}>
                        <button
                          onClick={() =>
                            setForm({
                              ...m.latest,
                              name: m.name,
                              system_id: m.system_id,
                              edit: true,
                            })
                          }
                        >
                          Edit as new version
                        </button>
                        <button
                          onClick={async () => {
                            const p = await send(
                              'POST',
                              `${wsBase(ws)}/systems/${m.system_id}/versions/${m.latest.version}/probe`,
                              {},
                            );
                            say(
                              `${m.name} v${m.latest.version}: ${p.result}${p.latency_ms != null ? ` · ${p.latency_ms} ms` : ''}`,
                            );
                            list.reload();
                          }}
                        >
                          Test now
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Loading>
      {form && <ModelForm initial={form} close={() => setForm(null)} done={list.reload} />}
    </>
  );
}

function ModelForm({
  initial,
  close,
  done,
}: {
  initial: any;
  close: () => void;
  done: () => void;
}) {
  const { ws, say } = useGym();
  const kind = initial.kind;
  const [provider, setProvider] = useState(
    initial.provider ?? (kind === 'open_weight' ? 'huggingface' : 'mock'),
  );
  const [name, setName] = useState(initial.name ?? '');
  const [modelId, setModelId] = useState(initial.model_id ?? '');
  const [revision, setRevision] = useState(initial.hf_revision ?? '');
  const [temperature, setTemperature] = useState(
    initial.params?.temperature == null ? '' : String(initial.params.temperature),
  );
  const [maxTokens, setMaxTokens] = useState(String(initial.params?.max_output_tokens ?? 4096));
  const [timeout, setTimeoutS] = useState(String(initial.params?.timeout_s ?? 120));
  const [rpm, setRpm] = useState(String(initial.limits?.rpm ?? 60));
  const [spend, setSpend] = useState(String(initial.limits?.spend_per_episode_usd ?? 0.4));
  const [note, setNote] = useState('');
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const [saving, setSaving] = useState(false);
  const keys = useData<any>(`${wsBase(ws)}/keys?provider=${provider}`);
  const key = keys.data?.items?.find((k: any) => k.is_default && k.status !== 'revoked');
  async function save() {
    setFailure(null);
    setSaving(true);
    const body = {
      kind,
      provider,
      name,
      model_id: modelId,
      hf_revision: kind === 'open_weight' && provider === 'huggingface' ? revision : undefined,
      params: {
        // Empty: no temperature is sent (some models, e.g. Haiku 5.5, reject sampling parameters).
        temperature: temperature.trim() === '' ? undefined : Number(temperature),
        max_output_tokens: Number(maxTokens),
        timeout_s: Number(timeout),
      },
      limits: { rpm: Number(rpm), spend_per_episode_usd: Number(spend) },
      change_note: note || undefined,
    };
    try {
      const r = initial.edit
        ? await send('POST', `${wsBase(ws)}/systems/${initial.system_id}/versions`, body)
        : await send('POST', `${wsBase(ws)}/systems`, body);
      if (initial.edit && !r.created) {
        // D-052: settings identical to an existing version make no new one. Say so here, never silently.
        setFailure(
          new GymApiError({
            code: 'NO_NEW_VERSION',
            status: 200,
            message: `Not saved as a new version: these settings are exactly version ${r.version}'s. Change a setting to make a new version, or use version ${r.version}.`,
          }),
        );
        done();
        return;
      }
      say(
        initial.edit
          ? `Saved as version ${r.version}${r.probe?.result ? ` · test: ${r.probe.result}` : ''}.`
          : `Model ${r.system.name} saved and tested.`,
      );
      done();
      close();
    } catch (e) {
      console.error('[rlgym] model save failed:', e);
      setFailure(
        e instanceof GymApiError
          ? e
          : new GymApiError({
              code: 'SAVE_FAILED',
              status: 0,
              message: `Save failed: ${String(e)}`,
            }),
      );
    } finally {
      setSaving(false);
    }
  }
  return (
    <>
      <div className="backdrop" onClick={close} />
      <section
        className="drawer"
        role="dialog"
        aria-label={initial.edit ? 'Edit as new version' : 'New model'}
      >
        <h3>
          {initial.edit
            ? `Edit ${initial.name} as a new version`
            : kind === 'open_weight'
              ? 'New open-weight model'
              : 'New frontier model'}
        </h3>
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} disabled={initial.edit} />
        </label>
        <label>
          Provider
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            disabled={initial.edit}
          >
            {(kind === 'open_weight'
              ? ['huggingface', 'mock']
              : ['anthropic', 'google', 'openai', 'mistral', 'mock']
            ).map((p) => (
              <option key={p} value={p}>
                {PROVIDER_LABEL[p]}
              </option>
            ))}
          </select>
        </label>
        <label>
          {kind === 'open_weight' && provider === 'huggingface'
            ? 'Hugging Face repository'
            : 'Model ID'}
          <input
            value={modelId}
            onChange={(e) => setModelId(e.target.value)}
            placeholder={provider === 'mock' ? 'mock/diligent-v1' : ''}
          />
        </label>
        {kind === 'open_weight' && provider === 'huggingface' && (
          <label>
            Revision (pinned commit hash)
            <input
              value={revision}
              onChange={(e) => setRevision(e.target.value)}
              placeholder="40-character commit hash"
            />
            <small>
              “Use latest” needs Hugging Face access, which is off locally; paste the commit hash.
            </small>
          </label>
        )}
        {key ? (
          <small>
            Uses the workspace {PROVIDER_LABEL[provider]} key {key.name} ••••{key.last4} (Admin →
            Keys).
          </small>
        ) : (
          keys.data && (
            <p className="banner">
              No {PROVIDER_LABEL[provider]} key in this workspace yet.{' '}
              <Link href="/gym/admin/keys">Add it in Keys first</Link>.
            </p>
          )
        )}
        <div className="grid3">
          <label>
            Temperature
            <input
              type="number"
              min={0}
              step={0.1}
              value={temperature}
              placeholder="not sent"
              onChange={(e) => setTemperature(e.target.value)}
            />
            <small>Leave empty to send no temperature.</small>
          </label>
          <label>
            Max output tokens
            <input
              type="number"
              min={1}
              value={maxTokens}
              onChange={(e) => setMaxTokens(e.target.value)}
            />
          </label>
          <label>
            Timeout per call (s)
            <input
              type="number"
              min={1}
              value={timeout}
              onChange={(e) => setTimeoutS(e.target.value)}
            />
          </label>
          <label>
            Rate limit (rpm)
            <input type="number" min={1} value={rpm} onChange={(e) => setRpm(e.target.value)} />
          </label>
          <label>
            Spend per episode ($)
            <input
              type="number"
              min={0.01}
              step={0.01}
              value={spend}
              onChange={(e) => setSpend(e.target.value)}
            />
          </label>
        </div>
        {initial.edit && (
          <label>
            What changed
            <input value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
        )}
        <div className="row">
          <button className="primary" disabled={saving || !key || !modelId.trim()} onClick={save}>
            {saving ? 'Saving…' : 'Save and test'}
          </button>
          <button onClick={close}>Close</button>
        </div>
        <Failure error={failure} />
      </section>
    </>
  );
}

function ModelPage({ id }: { id: string }) {
  const { ws, say } = useGym();
  const { data, error, reload } = useData<any>(`${wsBase(ws)}/systems/${id}`);
  const [reason, setReason] = useState('');
  return (
    <Loading data={data} error={error}>
      {() => (
        <div className="work">
          <aside>
            <Link href={`/gym/admin/models/${data.kind === 'open_weight' ? 'open' : 'frontier'}`}>
              ← Back to models
            </Link>
            <h4>Credential</h4>
            <dl className="kv">
              <dt>Uses</dt>
              <dd>
                {data.key.name} ••••{data.key.last4}
              </dd>
              <dt>Managed in</dt>
              <dd>
                <Link href="/gym/admin/keys">Admin → Keys</Link>
              </dd>
              <dt>Last rotated</dt>
              <dd>{when(data.key.rotated_at)}</dd>
            </dl>
            <button
              onClick={async () => {
                const p = await send(
                  'POST',
                  `${wsBase(ws)}/systems/${id}/versions/${data.latest.version}/probe`,
                  {},
                );
                say(`Test: ${p.result}`);
                reload();
              }}
            >
              Test now
            </button>
            {data.enabled ? (
              <>
                <label>
                  Reason to disable
                  <input value={reason} onChange={(e) => setReason(e.target.value)} />
                </label>
                <button
                  disabled={!reason.trim()}
                  onClick={async () => {
                    await send('POST', `${wsBase(ws)}/systems/${id}/disable`, { reason });
                    reload();
                  }}
                >
                  Disable
                </button>
              </>
            ) : (
              <button
                onClick={async () => {
                  await send('POST', `${wsBase(ws)}/systems/${id}/enable`, {});
                  reload();
                }}
              >
                Enable
              </button>
            )}
          </aside>
          <main>
            <div className="row">
              <h3>{data.name}</h3>
              <Badge state={STATUS_TONE[data.status]} label={data.status} />
              {data.synthetic && <Badge state="deprecated" label="Synthetic · controlled mock" />}
            </div>
            <dl className="kv">
              <dt>Provider</dt>
              <dd>{PROVIDER_LABEL[data.latest.provider]}</dd>
              <dt>Model ID</dt>
              <dd>{data.latest.model_id}</dd>
              {data.latest.hf_revision && (
                <>
                  <dt>Revision</dt>
                  <dd>
                    <code>{data.latest.hf_revision}</code>
                  </dd>
                </>
              )}
              <dt>Parameters</dt>
              <dd>
                temperature {data.latest.params.temperature ?? 'not sent'} · max output{' '}
                {data.latest.params.max_output_tokens} · timeout {data.latest.params.timeout_s} s
              </dd>
              <dt>Limits</dt>
              <dd>
                {data.latest.limits.rpm} rpm · ${data.latest.limits.spend_per_episode_usd} / episode
              </dd>
              <dt>Version</dt>
              <dd>
                v{data.latest.version} · <Hash value={data.latest.config_sha256} />
              </dd>
            </dl>
            <section className="card">
              <h4>Version history</h4>
              {data.versions.map((v: any) => (
                <small key={v.version}>
                  v{v.version} · {v.change_note ?? '—'} · {when(v.created_at)} · {v.created_by}
                </small>
              ))}
            </section>
            <section className="card">
              <h4>Connection tests</h4>
              {data.probes.length === 0 && <small>Not tested yet.</small>}
              {data.probes.map((p: any) => (
                <small key={p.id}>
                  {when(p.probed_at)} · v{p.system_version} · {p.result}
                  {p.latency_ms != null ? ` · ${p.latency_ms} ms` : ''} · {p.mode.replace('_', ' ')}
                  {p.details?.note ? ` · ${p.details.note}` : ''}
                </small>
              ))}
            </section>
            <section className="card">
              <h4>Used in</h4>
              <small>{data.runs_note}</small>
            </section>
          </main>
        </div>
      )}
    </Loading>
  );
}

function ModelSets() {
  const { ws, say } = useGym();
  const sets = useData<any>(`${wsBase(ws)}/model-sets`);
  const systems = useData<any>(`${wsBase(ws)}/systems`);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [picked, setPicked] = useState<Record<string, number>>({});
  const [failure, setFailure] = useState<GymApiError | null>(null);
  return (
    <>
      <div className="toolbar">
        <small>
          Named, versioned line-ups of model versions. Editing a set creates a new version; runs
          keep the version they used.
        </small>
        <button className="primary" onClick={() => setOpen(true)}>
          New model set
        </button>
      </div>
      <Loading data={sets.data} error={sets.error}>
        {() => (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Model set</th>
                  <th>Models (pinned versions)</th>
                  <th>Used in runs</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {sets.data.items.length === 0 && (
                  <tr>
                    <td colSpan={4} style={{ textAlign: 'left' }}>
                      No model sets.
                    </td>
                  </tr>
                )}
                {sets.data.items.map((s: any) => (
                  <tr key={s.id}>
                    <td>
                      {s.name}
                      <small>
                        v{s.version} · by {s.created_by}
                      </small>
                    </td>
                    <td>
                      {s.members.map((m: any) => `${m.name} v${m.system_version}`).join(' · ')}
                    </td>
                    <td>—</td>
                    <td>
                      <button
                        onClick={() => {
                          setName(s.name);
                          setPicked(
                            Object.fromEntries(
                              s.members.map((m: any) => [m.system_id, m.system_version]),
                            ),
                          );
                          setOpen(true);
                        }}
                      >
                        Edit as new version
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Loading>
      {open && (
        <section className="card">
          <h4>Model set</h4>
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          {(systems.data?.items ?? [])
            .filter((m: any) => m.enabled)
            .map((m: any) => (
              <label key={m.system_id} className="row">
                <input
                  type="checkbox"
                  checked={m.system_id in picked}
                  onChange={(e) => {
                    const next = { ...picked };
                    if (e.target.checked) next[m.system_id] = m.latest.version;
                    else delete next[m.system_id];
                    setPicked(next);
                  }}
                />
                {m.name} v{m.latest.version}
              </label>
            ))}
          <div className="row">
            <button
              className="primary"
              disabled={!name.trim() || Object.keys(picked).length === 0}
              onClick={async () => {
                setFailure(null);
                try {
                  const r = await send('POST', `${wsBase(ws)}/model-sets`, {
                    name,
                    members: Object.entries(picked).map(([system_id, system_version]) => ({
                      system_id,
                      system_version,
                    })),
                  });
                  say(r.created ? `Model set saved as v${r.version}.` : 'No change.');
                  setOpen(false);
                  sets.reload();
                } catch (e) {
                  setFailure(e as GymApiError);
                }
              }}
            >
              Save model set
            </button>
            <button onClick={() => setOpen(false)}>Close</button>
          </div>
          <Failure error={failure} />
        </section>
      )}
    </>
  );
}

export function Keys() {
  const { ws, me, say } = useGym();
  const { data, error, reload } = useData<any>(`${wsBase(ws)}/keys`);
  const [form, setForm] = useState<{ rotate?: any } | null>(null);
  const [provider, setProvider] = useState('anthropic');
  const [name, setName] = useState('');
  const [secret, setSecret] = useState('');
  const [failure, setFailure] = useState<GymApiError | null>(null);
  async function save() {
    setFailure(null);
    try {
      if (form?.rotate)
        await send('POST', `${wsBase(ws)}/keys/${form.rotate.id}/rotate`, { secret });
      else
        await send('POST', `${wsBase(ws)}/keys`, {
          provider,
          name,
          secret,
          scope: 'workspace_default',
        });
      say(
        form?.rotate
          ? 'Key rotated; models pick it up at their next call (no new model versions).'
          : 'Key saved. It is never shown again.',
      );
      setSecret('');
      setForm(null);
      reload();
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  return (
    <>
      <div className="toolbar">
        <small>
          The workspace key store: each key is entered once, kept in the encrypted local store and
          never shown again (last four characters only).
          {me.profile !== 'admin' ? ' Keys are managed by an Admin.' : ''}
        </small>
        <button className="primary" disabled={me.profile !== 'admin'} onClick={() => setForm({})}>
          Add key
        </button>
      </div>
      <Loading data={data} error={error}>
        {() => (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Key</th>
                  <th>Provider</th>
                  <th>Saved</th>
                  <th>Used by</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((k: any) => (
                  <tr key={k.id}>
                    <td>
                      {k.name}
                      <small>
                        {k.kind.replace('_', ' ')} · {k.scope.replace('_', ' ')}
                        {k.is_default ? ' · default' : ''}
                      </small>
                    </td>
                    <td>{PROVIDER_LABEL[k.provider]}</td>
                    <td>
                      ••••{k.last4}
                      <small>
                        rotated {when(k.rotated_at)} · {k.rotated_by}
                      </small>
                    </td>
                    <td>{k.used_by} models</td>
                    <td>
                      <Badge
                        state={
                          k.status === 'valid'
                            ? 'ready'
                            : k.status === 'revoked'
                              ? 'revoked'
                              : 'requested'
                        }
                        label={k.status}
                      />
                      {k.status_note && <small>{k.status_note}</small>}
                    </td>
                    <td>
                      {me.profile === 'admin' && k.status !== 'revoked' && (
                        <div className="row" style={{ justifyContent: 'flex-end' }}>
                          <button
                            onClick={async () => {
                              try {
                                await send('POST', `${wsBase(ws)}/keys/${k.id}/test`, {});
                                reload();
                              } catch (e) {
                                setFailure(e as GymApiError);
                              }
                            }}
                          >
                            Test
                          </button>
                          {k.provider !== 'mock' && k.kind !== 'service_account' && (
                            <button onClick={() => setForm({ rotate: k })}>Rotate</button>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Loading>
      {form && (
        <section className="card">
          <h4>{form.rotate ? `Rotate ${form.rotate.name}` : 'Add key'}</h4>
          {!form.rotate && (
            <div className="grid2">
              <label>
                Provider
                <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                  {['huggingface', 'anthropic', 'openai', 'google', 'mistral'].map((p) => (
                    <option key={p} value={p}>
                      {PROVIDER_LABEL[p]}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Name
                <input value={name} onChange={(e) => setName(e.target.value)} />
              </label>
            </div>
          )}
          <label>
            Key / token
            <input
              type="password"
              autoComplete="off"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
            />
          </label>
          <small>
            Saving does not call the provider, so the key starts “untested”. Test checks it by
            listing the provider’s models (no inference, no cost), only when live calls are on and a
            live approval allows key tests.
          </small>
          <div className="row">
            <button
              className="primary"
              disabled={secret.length < 8 || (!form.rotate && !name.trim())}
              onClick={save}
            >
              Save
            </button>
            <button onClick={() => setForm(null)}>Close</button>
          </div>
          <Failure error={failure} />
        </section>
      )}
    </>
  );
}
