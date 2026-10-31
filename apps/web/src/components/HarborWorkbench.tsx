'use client';

import { useEffect, useState } from 'react';

type Source = {
  id: string;
  task_id: string;
  task_version: string;
  source_sha256: string;
  actor_spec: unknown;
  export_receipts?: {
    id: string;
    record_id: string;
    record_hash: string;
    envelope_sha256: string;
    attestation: string;
  }[];
};
type Package = {
  id: string;
  package_sha256: string;
  manifest: unknown;
  approval: unknown;
  live_execution: string;
};
type Check = {
  id: string;
  state: string;
  invocation_count: number;
  result: unknown;
  error_code: string | null;
};
type Api = (path: string, method?: string, body?: unknown) => Promise<any>;

export default function HarborWorkbench({
  base,
  api,
  canApprove,
  canPlan,
  canAdmin,
}: {
  base: string;
  api: Api;
  canApprove: boolean;
  canPlan: boolean;
  canAdmin: boolean;
}) {
  const [sources, setSources] = useState<Source[]>([]);
  const [selected, setSelected] = useState<Source | null>(null);
  const [pkg, setPackage] = useState<Package | null>(null);
  const [check, setCheck] = useState<Check | null>(null);
  const [checks, setChecks] = useState<Check[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [rationale, setRationale] = useState('');

  useEffect(() => {
    api(base + '/praxis-sources')
      .then(setSources)
      .catch((e) => setError(e.message));
  }, [api, base]);
  useEffect(() => {
    if (!selected) return;
    let active = true;
    api(base + '/praxis-sources/' + selected.id + '/packages')
      .then((items: Package[]) => {
        if (active) setPackage(items[0] || null);
      })
      .catch((e) => setError(e.message));
    return () => {
      active = false;
    };
  }, [api, base, selected?.id]);
  useEffect(() => {
    if (!pkg) return;
    let active = true;
    api(base + '/harbor-packages/' + pkg.id + '/checks')
      .then((items: Check[]) => {
        if (!active) return;
        setChecks(items);
        setCheck((current) =>
          current && items.some((c) => c.id === current.id) ? current : items[0] || null,
        );
      })
      .catch((e) => setError(e.message));
    return () => {
      active = false;
    };
  }, [api, base, pkg?.id, check?.id, check?.state]);
  useEffect(() => {
    if (!check || !['queued', 'running'].includes(check.state)) return;
    const timer = setInterval(
      () =>
        api(base + '/harbor-checks/' + check.id)
          .then(setCheck)
          .catch((e) => setError(e.message)),
      1500,
    );
    return () => clearInterval(timer);
  }, [api, base, check]);

  async function act(action: () => Promise<void>) {
    setBusy(true);
    setError('');
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-label="Praxis to Harbor">
      <h2>Praxis → Harbor</h2>
      <p>
        Import a structured Praxis export, inspect the actor view, build an immutable package, then
        request a synthetic software check.
      </p>
      <p>
        Reference and empty-output checks verify the harness. They do not measure a model. Live
        agent execution is blocked until spending and isolation controls are qualified. Source
        review and declared rights do not grant Anvil approval.
      </p>
      {error && <p role="alert">{error}</p>}
      <label>
        Praxis task export (.json){' '}
        <input
          type="file"
          accept=".json,application/json"
          disabled={busy}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file)
              void act(async () => {
                if (file.size > 1048576) throw new Error('Export exceeds 1 MiB');
                const source = await api(base + '/praxis-sources', 'POST', {
                  payload: await file.text(),
                });
                setSelected(source);
                setPackage(null);
                setCheck(null);
                setSources(await api(base + '/praxis-sources'));
              });
          }}
        />
      </label>
      <label>
        Imported revision{' '}
        <select
          aria-label="Imported revision"
          value={selected?.id || ''}
          onChange={(e) => {
            setSelected(sources.find((s) => s.id === e.target.value) || null);
            setPackage(null);
            setCheck(null);
          }}
        >
          <option value="">Select a source</option>
          {sources.map((s) => (
            <option key={s.id} value={s.id}>
              {s.task_id} · {s.task_version}
            </option>
          ))}
        </select>
      </label>
      {selected && (
        <>
          <p>
            Exact source SHA-256: <code>{selected.source_sha256}</code>
          </p>
          <details>
            <summary>Inspect actor-visible task</summary>
            <pre>{JSON.stringify(selected.actor_spec, null, 2)}</pre>
          </details>
          {!!selected.export_receipts?.length && (
            <details>
              <summary>Praxis source lineage</summary>
              <pre>{JSON.stringify(selected.export_receipts, null, 2)}</pre>
            </details>
          )}
          <button
            disabled={busy}
            onClick={() =>
              void act(async () =>
                setPackage(
                  await api(base + '/praxis-sources/' + selected.id + '/build', 'POST', {}),
                ),
              )
            }
          >
            Build Harbor package
          </button>
        </>
      )}
      {pkg && (
        <>
          <p>
            Package SHA-256: <code>{pkg.package_sha256}</code>
          </p>
          <details>
            <summary>Inspect package manifest</summary>
            <pre>{JSON.stringify(pkg.manifest, null, 2)}</pre>
          </details>
          {!pkg.approval && canApprove && (
            <>
              <label>
                Product Owner rationale{' '}
                <textarea value={rationale} onChange={(e) => setRationale(e.target.value)} />
              </label>
              <button
                disabled={busy || rationale.trim().length < 10}
                onClick={() =>
                  void act(async () =>
                    setPackage(
                      await api(base + '/harbor-packages/' + pkg.id + '/approve', 'POST', {
                        package_sha256: pkg.package_sha256,
                        rationale,
                        scope: 'synthetic_software_checks_only',
                      }),
                    ),
                  )
                }
              >
                Approve synthetic software checks
              </button>
            </>
          )}
          {Boolean(pkg.approval) && canPlan && (
            <div>
              <button
                disabled={busy}
                onClick={() =>
                  void act(async () =>
                    setCheck(
                      await api(base + '/harbor-packages/' + pkg.id + '/checks', 'POST', {
                        candidate: 'reference',
                      }),
                    ),
                  )
                }
              >
                Run reference check
              </button>
              <button
                disabled={busy}
                onClick={() =>
                  void act(async () =>
                    setCheck(
                      await api(base + '/harbor-packages/' + pkg.id + '/checks', 'POST', {
                        candidate: 'constraint_failure',
                      }),
                    ),
                  )
                }
              >
                Run hard-failure check
              </button>
              <button
                disabled={busy}
                onClick={() =>
                  void act(async () =>
                    setCheck(
                      await api(base + '/harbor-packages/' + pkg.id + '/checks', 'POST', {
                        candidate: 'empty_output',
                      }),
                    ),
                  )
                }
              >
                Run empty-output check
              </button>
            </div>
          )}
        </>
      )}
      {pkg && canPlan && (
        <AgentPlanPanel
          base={base}
          api={api}
          packageId={pkg.id}
          canApprove={canApprove}
          canAdmin={canAdmin}
          onRun={setCheck}
        />
      )}
      {check && (
        <section aria-live="polite">
          <label>
            Check history{' '}
            <select
              value={check.id}
              onChange={(e) => setCheck(checks.find((c) => c.id === e.target.value) || null)}
            >
              {checks.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.id.slice(0, 8)} · {c.state}
                </option>
              ))}
            </select>
          </label>
          <h3>Check: {check.state}</h3>
          <p>
            Dispatches: {check.invocation_count}. {check.error_code || ''}
          </p>
          {['queued', 'running'].includes(check.state) && (
            <button
              disabled={busy}
              onClick={() =>
                void act(async () =>
                  setCheck(await api(base + '/harbor-checks/' + check.id + '/cancel', 'POST', {})),
                )
              }
            >
              Cancel check
            </button>
          )}
          {Boolean(check.result) && (
            <>
              <CheckAnalysis result={check.result} base={base} />
              <details>
                <summary>Results and analysis</summary>
                <pre>{JSON.stringify(check.result, null, 2)}</pre>
              </details>
            </>
          )}
        </section>
      )}
    </section>
  );
}

type AgentPlan = {
  id: string;
  ready: boolean;
  missing_gates: string[];
  subject_hash: string;
  config: {
    model: string;
    connection_hash: string;
    max_total_micro_usd: number;
    max_calls: number;
    max_output_tokens: number;
  };
  mechanism: string;
  calls?: unknown[];
};

function AgentPlanPanel({
  base,
  api,
  packageId,
  canApprove,
  canAdmin,
  onRun,
}: {
  base: string;
  api: Api;
  packageId: string;
  canApprove: boolean;
  canAdmin: boolean;
  onRun: (check: Check) => void;
}) {
  const [connections, setConnections] = useState<
    { id: string; model_id: string; provider_key: string }[]
  >([]);
  const [connection, setConnection] = useState('');
  const [dollars, setDollars] = useState('');
  const [plan, setPlan] = useState<AgentPlan | null>(null);
  const [error, setError] = useState('');
  const [evidence, setEvidence] = useState('');
  const [expires, setExpires] = useState('');
  const [authorityRef, setAuthorityRef] = useState('');
  const [adminPurpose, setAdminPurpose] = useState('activation');
  const [rationale, setRationale] = useState('');
  useEffect(() => {
    setPlan(null);
    api(base + '/harbor-agent-connections')
      .then(setConnections)
      .catch((e) => setError(e.message));
  }, [api, base, packageId]);
  async function act(fn: () => Promise<void>) {
    setError('');
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const selected = connections.find((c) => c.id === connection);
  return (
    <section aria-label="Agent model run">
      <h3>Run an agent in Harbor</h3>
      <p>
        The Anvil structured JSON agent requests one provider response per stage. Responses are
        data, not executable code. A saved plan does not authorize spending.
      </p>
      {error && <p role="alert">{error}</p>}
      <label>
        Configured provider and exact model{' '}
        <select value={connection} onChange={(e) => setConnection(e.target.value)}>
          <option value="">Select a configured OpenAI connection</option>
          {connections.map((c) => (
            <option key={c.id} value={c.id}>
              {c.provider_key} · {c.model_id}
            </option>
          ))}
        </select>
      </label>
      {!connections.length && (
        <p>
          Configure an exact provider model in Providers first. Keys are supplied to the server and
          never uploaded with a task.
        </p>
      )}
      <label>
        Maximum total API spend (USD){' '}
        <input
          type="number"
          min="0.01"
          max="1000"
          step="0.01"
          value={dollars}
          onChange={(e) => setDollars(e.target.value)}
        />
      </label>
      <button
        disabled={!selected || !Number.isFinite(Number(dollars)) || Number(dollars) <= 0}
        onClick={() =>
          void act(async () =>
            setPlan(
              await api(base + '/harbor-packages/' + packageId + '/agent-plans', 'POST', {
                connection_id: connection,
                agent: 'anvil-structured-json-v1',
                model: selected!.model_id,
                max_total_micro_usd: Math.round(Number(dollars) * 1000000),
                trials: 1,
              }),
            ),
          )
        }
      >
        Save agent run plan
      </button>
      {plan && (
        <>
          <p>
            {plan.config.model} · one trial · at most {plan.config.max_calls} requests ·{' '}
            {plan.config.max_output_tokens} output tokens per request · ceiling $
            {(plan.config.max_total_micro_usd / 1000000).toFixed(2)}.
          </p>
          <p>{plan.mechanism}</p>
          <p>{plan.ready ? 'Ready for explicit launch' : 'Blocked — no inference dispatched'}</p>
          {!!plan.missing_gates.length && (
            <ul>
              {plan.missing_gates.map((g) => (
                <li key={g}>{g.replaceAll('_', ' ')}</li>
              ))}
            </ul>
          )}
          <button
            onClick={() =>
              void act(async () => setPlan(await api(base + '/harbor-agent-plans/' + plan.id)))
            }
          >
            Refresh run readiness
          </button>
          {canApprove && (
            <details>
              <summary>Product Owner: exact run and processing-rights review</summary>
              <p>
                Review the actor material, provider processing terms and rights evidence before
                recording this decision. Synthetic test identities cannot approve paid execution.
              </p>
              <label>
                Rights evidence artifact ID{' '}
                <input value={evidence} onChange={(e) => setEvidence(e.target.value)} />
              </label>
              <label>
                Rights and run review rationale{' '}
                <textarea value={rationale} onChange={(e) => setRationale(e.target.value)} />
              </label>
              <button
                disabled={!evidence || rationale.length < 10 || !expires}
                onClick={() =>
                  void act(async () => {
                    await api(base + '/harbor-agent-plans/' + plan.id + '/review', 'POST', {
                      subject_hash: plan.subject_hash,
                      rights_evidence_id: evidence,
                      rationale,
                      expires_at: new Date(expires).toISOString(),
                    });
                    setPlan(await api(base + '/harbor-agent-plans/' + plan.id));
                  })
                }
              >
                Approve exact run and external processing rights
              </button>
              <label>
                Rights review expiry (your local time){' '}
                <input
                  type="datetime-local"
                  value={expires}
                  onChange={(e) => setExpires(e.target.value)}
                />
              </label>
              <button
                disabled={rationale.length < 10}
                onClick={() =>
                  void act(async () => {
                    await api(base + '/harbor-agent-plans/' + plan.id + '/revoke-review', 'POST', {
                      rationale,
                    });
                    setPlan(await api(base + '/harbor-agent-plans/' + plan.id));
                  })
                }
              >
                Revoke this plan's processing-rights review
              </button>
            </details>
          )}
          {canAdmin && (
            <details>
              <summary>Admin: provider activation or exact paid scope</summary>
              <p>
                Each decision requires a recently authenticated real Admin. Two distinct active
                Admins must each approve; synthetic identities are rejected.
              </p>
              <label>
                Approval{' '}
                <select value={adminPurpose} onChange={(e) => setAdminPurpose(e.target.value)}>
                  <option value="activation">Exact provider activation</option>
                  <option value="paid_scope">This exact paid run</option>
                </select>
              </label>
              <label>
                User authority reference{' '}
                <input value={authorityRef} onChange={(e) => setAuthorityRef(e.target.value)} />
              </label>
              <label>
                Approval expiry (your local time){' '}
                <input
                  type="datetime-local"
                  value={expires}
                  onChange={(e) => setExpires(e.target.value)}
                />
              </label>
              <button
                disabled={!authorityRef || !expires}
                onClick={() =>
                  void act(async () => {
                    await api(
                      base + '/harbor-agent-plans/' + plan.id + '/admin-approvals',
                      'POST',
                      {
                        purpose: adminPurpose,
                        subject_hash:
                          adminPurpose === 'activation'
                            ? plan.config.connection_hash
                            : plan.subject_hash,
                        authority_reference: authorityRef,
                        expires_at: new Date(expires).toISOString(),
                      },
                    );
                    setPlan(await api(base + '/harbor-agent-plans/' + plan.id));
                  })
                }
              >
                Record my Admin approval
              </button>
            </details>
          )}
          <button
            disabled={!plan.ready}
            onClick={() =>
              void act(async () => {
                const launched = await api(
                  base + '/harbor-agent-plans/' + plan.id + '/launch',
                  'POST',
                  {},
                );
                onRun(await api(base + '/harbor-checks/' + launched.check_id));
              })
            }
          >
            Run agent in Harbor
          </button>
          {!!plan.calls?.length && (
            <details>
              <summary>Provider accounting evidence</summary>
              <pre>{JSON.stringify(plan.calls, null, 2)}</pre>
            </details>
          )}
        </>
      )}
    </section>
  );
}

function CheckAnalysis({ result, base }: { result: unknown; base: string }) {
  const data = result as {
    diagnostics: {
      reward: number;
      diagnostic_score?: number;
      hard_failures?: string[];
      criteria?: Record<string, { passed: boolean; weight_bps: number }>;
      stages?: {
        stage_id: string;
        reward: number;
        diagnostic_score?: number;
        hard_failures?: string[];
        criteria?: Record<string, { passed: boolean; weight_bps: number }>;
      }[];
    };
    evidence?: { artifact_id: string; kind: string; sha256: string }[];
  };
  const stages = data.diagnostics.stages || [{ ...data.diagnostics, stage_id: 'Decision' }];
  return (
    <section aria-label="Software check analysis">
      <p>
        <strong>Reward: {data.diagnostics.reward}</strong> ·{' '}
        {(result as { model_performance?: boolean }).model_performance
          ? 'Model outputs with automated scoring; scientific review pending.'
          : 'Synthetic software verification; no model performance measured.'}
      </p>
      {stages.map((stage) => (
        <div key={stage.stage_id}>
          <h4>{stage.stage_id}</h4>
          <p>
            Reward {stage.reward}; diagnostic score {stage.diagnostic_score ?? 'unavailable'}. Hard
            failures: {stage.hard_failures?.join(', ') || 'none'}.
          </p>
          {stage.criteria && (
            <table>
              <thead>
                <tr>
                  <th>Criterion</th>
                  <th>Result</th>
                  <th>Weight</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(stage.criteria).map(([id, c]) => (
                  <tr key={id}>
                    <td>{id}</td>
                    <td>{c.passed ? 'Pass' : 'Fail'}</td>
                    <td>{c.weight_bps / 100}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}
      {!!data.evidence?.length && (
        <details>
          <summary>Retained evidence artifacts</summary>
          <ul>
            {data.evidence.map((e) => (
              <li key={e.artifact_id}>
                <a href={'/api/v1' + base + '/artifacts/' + e.artifact_id + '/content'}>{e.kind}</a>{' '}
                · {e.sha256}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
