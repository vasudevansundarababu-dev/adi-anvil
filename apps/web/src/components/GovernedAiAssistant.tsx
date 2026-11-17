'use client';

import { useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import { ModelConfiguration } from './ModelProfileEditor';
import { SafetySourceRef } from './SafetySourcePicker';

type Budget = {
  id: string;
  active: boolean;
  available_micro_usd: number;
  cap_micro_usd: number;
  models: { id: string }[];
};
type Request = {
  id: string;
  purpose: string;
  state: string;
  bound_micro_usd: number;
  actual_micro_usd: number | null;
  result: {
    origin: string;
    source_sha256: string;
    output: unknown;
    error_code: string | null;
  } | null;
};
type Purpose =
  | 'evaluator_recommendation'
  | 'method_recommendation'
  | 'safety_generation'
  | 'custom_code_generation';
const labels: Record<Purpose, string> = {
  evaluator_recommendation: 'Recommend evaluators',
  method_recommendation: 'Recommend benchmark method',
  safety_generation: 'Generate safety prompts',
  custom_code_generation: 'Generate custom Python',
};

export default function GovernedAiAssistant({
  endpoint,
  base,
  sourceSha256,
  canAdmin,
  target,
  safetyCategories,
  safetySource,
  onRefresh,
  onUseGeneratedCode,
}: {
  endpoint: string;
  base: string;
  sourceSha256: string;
  canAdmin: boolean;
  target?: string;
  safetyCategories: string[];
  safetySource?: SafetySourceRef | null;
  onRefresh: () => Promise<void>;
  onUseGeneratedCode: (draft: { target: string; code: string; request_id: string }) => void;
}) {
  const [models, setModels] = useState<ModelConfiguration[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [model, setModel] = useState('');
  const [budget, setBudget] = useState<Budget | null>(null);
  const [purpose, setPurpose] = useState<Purpose>('evaluator_recommendation');
  const [rights, setRights] = useState(false);
  const [requests, setRequests] = useState<Request[]>([]);
  const [estimate, setEstimate] = useState<{ body: string; bound_micro_usd: number } | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [uncertain, setUncertain] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const selectedModel = models.find((item) => item.id === model);
  const body = {
    budget_id: budget?.id,
    source_sha256: sourceSha256,
    model_profile_id: model,
    purpose,
    target: purpose === 'custom_code_generation' ? target || null : null,
    safety_categories: purpose === 'safety_generation' ? safetyCategories : null,
    ...(purpose === 'safety_generation' && safetySource ? { safety_source: safetySource } : {}),
    max_output_tokens: Math.min(8192, selectedModel?.max_output_tokens || 1024),
  };
  const signature = JSON.stringify(body);
  const safetyIncomplete =
    purpose === 'safety_generation' && (!safetySource || safetyCategories.length < 5);
  const pending = requests.some((item) =>
    ['queued', 'dispatching', 'execution_unknown'].includes(item.state),
  );
  useEffect(() => {
    let active = true;
    setLoaded(false);
    setError('');
    setEstimate(null);
    Promise.all([
      api(endpoint + '/execution-budget'),
      api(base + '/workspace/models?current_only=true'),
      api(endpoint + '/ai/options'),
      api(endpoint + '/ai/requests?limit=100'),
    ])
      .then(([saved, modelPage, options, history]) => {
        if (!active) return;
        setBudget(saved);
        setModels(modelPage.items);
        setCursor(modelPage.next_cursor);
        setEnabled(options.enabled && options.component_qualified);
        setRequests(history.items);
        setLoaded(true);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [endpoint, base, sourceSha256]);
  async function refresh() {
    const [saved, history, options] = await Promise.all([
      api(endpoint + '/execution-budget'),
      api(endpoint + '/ai/requests?limit=100'),
      api(endpoint + '/ai/options'),
    ]);
    setBudget(saved);
    setRequests(history.items);
    setEnabled(options.enabled && options.component_qualified);
    await onRefresh();
  }
  async function loadMoreModels() {
    if (!cursor) return;
    setBusy(true);
    setError('');
    try {
      const result = await api(
        base + '/workspace/models?current_only=true&after=' + encodeURIComponent(cursor),
      );
      setModels((previous) => [
        ...new Map([...previous, ...result.items].map((item) => [item.id, item])).values(),
      ]);
      setCursor(result.next_cursor);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details>
      <summary>AI recommendations and prompt generation</summary>
      <p>
        Uses configured models and saved keys. Recommendations rank measurement fit; cost does not
        affect evaluator ranking. AI assistance and the resulting benchmark share one aggregate
        budget of at most $2.
      </p>
      {error && <p role="alert">{error}</p>}
      {!loaded && !error && <p>Loading AI setup…</p>}
      {loaded && !enabled && (
        <p>AI runtime qualification or activation is pending. No model call is made.</p>
      )}
      {loaded && !budget && (
        <fieldset>
          <legend>Shared QA budget</legend>
          <p>
            Select all model connections needed for setup and benchmarking. Creating the budget
            reserves the existing pilot allowance and makes no model call.
          </p>
          {models.map((item) => (
            <label key={item.id} style={{ display: 'block' }}>
              <input
                type="checkbox"
                checked={selected.includes(item.id)}
                disabled={
                  !canAdmin || busy || (!selected.includes(item.id) && selected.length >= 8)
                }
                onChange={(e) =>
                  setSelected((previous) =>
                    e.target.checked
                      ? [...previous, item.id]
                      : previous.filter((id) => id !== item.id),
                  )
                }
              />
              {item.name} · {item.provider}/{item.model_id}
            </label>
          ))}
          {cursor && (
            <button disabled={busy} onClick={loadMoreModels}>
              More configured models
            </button>
          )}
          <label>
            <input
              type="checkbox"
              checked={rights}
              onChange={(e) => setRights(e.target.checked)}
              disabled={!canAdmin || busy}
            />
            I confirm processing rights and authorize a shared aggregate QA budget up to $2 within
            the existing pilot.
          </label>
          <button
            disabled={!canAdmin || busy || !rights || !selected.length}
            onClick={async () => {
              setBusy(true);
              setError('');
              try {
                setBudget(
                  await api(endpoint + '/execution-budget', 'POST', {
                    source_sha256: sourceSha256,
                    model_profile_ids: selected,
                    aggregate_cap_micro_usd: 2000000,
                    rights_confirmed: true,
                  }),
                );
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Authorize shared QA budget
          </button>
        </fieldset>
      )}
      {budget && (
        <>
          <p>
            Shared budget: ${(budget.cap_micro_usd / 1000000).toFixed(2)} · available $
            {(budget.available_micro_usd / 1000000).toFixed(4)} ·{' '}
            {budget.active ? 'Active' : 'Expired or revoked'}
          </p>
          <label>
            AI model
            <select value={model} onChange={(e) => setModel(e.target.value)} disabled={busy}>
              <option value="">Select saved model connection</option>
              {models
                .filter((item) => budget.models.some((binding) => binding.id === item.id))
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} · {item.provider}/{item.model_id}
                  </option>
                ))}
            </select>
          </label>
          {cursor && (
            <button disabled={busy} onClick={loadMoreModels}>
              More configured models
            </button>
          )}
          <label>
            Request
            <select
              value={purpose}
              onChange={(e) => setPurpose(e.target.value as Purpose)}
              disabled={busy}
            >
              {Object.entries(labels).map(([id, label]) => (
                <option
                  key={id}
                  value={id}
                  disabled={
                    (id === 'custom_code_generation' && !target) ||
                    (id === 'safety_generation' && (safetyCategories.length < 5 || !safetySource))
                  }
                >
                  {label}
                </option>
              ))}
            </select>
          </label>
          {purpose === 'custom_code_generation' && (
            <p>Exact rule or skill: {target || 'Open Custom on a binding row first.'}</p>
          )}
          {purpose === 'safety_generation' && (
            <p>
              {safetyCategories.length} selected categories; at least five qualified categories are
              required. Generation is followed by prompt inspection and selection.
              {!safetySource && ' Save the chosen test source first.'}
            </p>
          )}
          <button
            disabled={
              busy ||
              !budget.active ||
              !enabled ||
              !model ||
              pending ||
              uncertain ||
              safetyIncomplete
            }
            onClick={async () => {
              setBusy(true);
              setError('');
              setEstimate(null);
              try {
                const value = await api(endpoint + '/ai/estimate', 'POST', body);
                setEstimate({ body: signature, bound_micro_usd: value.bound_micro_usd });
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Check request estimate
          </button>
          {estimate?.body === signature && (
            <p>
              Maximum request reservation: ${(estimate.bound_micro_usd / 1000000).toFixed(6)}.
              Benchmark spending uses the remaining shared allowance.
            </p>
          )}
          <button
            disabled={
              !canAdmin ||
              busy ||
              !enabled ||
              !budget.active ||
              !model ||
              pending ||
              uncertain ||
              safetyIncomplete ||
              estimate?.body !== signature
            }
            onClick={async () => {
              setBusy(true);
              setError('');
              try {
                const value = await api(endpoint + '/ai/requests', 'POST', body);
                setRequests((previous) => [value, ...previous]);
                setEstimate(null);
              } catch (e) {
                setError((e as Error).message);
                const status = (e as Error & { status?: number }).status;
                if (!status || status >= 500) setUncertain(true);
              } finally {
                setBusy(false);
              }
            }}
          >
            Generate AI suggestion
          </button>
        </>
      )}
      {uncertain && (
        <p role="alert">
          The request outcome is unconfirmed. Do not submit it again. Check recorded requests; an
          operator must reconcile unresolved execution.
        </p>
      )}
      <button
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError('');
          try {
            await refresh();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        Refresh recorded requests
      </button>
      {requests.map((item) => (
        <details key={item.id}>
          <summary>
            {labels[item.purpose as Purpose] || item.purpose} · {item.state}
          </summary>
          <p>
            Request {item.id} · maximum reservation ${(item.bound_micro_usd / 1000000).toFixed(6)} ·
            actual{' '}
            {item.actual_micro_usd === null
              ? 'Unknown'
              : '$' + (item.actual_micro_usd / 1000000).toFixed(6)}
          </p>
          {item.result && (
            <>
              <p>
                {item.result.origin} · {item.result.error_code || 'Recorded result'}
              </p>
              <pre>{JSON.stringify(item.result.output, null, 2)}</pre>
              {item.purpose === 'custom_code_generation' &&
                item.state === 'completed' &&
                item.result.origin === 'actual_provider_sdk' &&
                item.result.source_sha256 === sourceSha256 &&
                !!target &&
                typeof item.result.output === 'object' &&
                item.result.output !== null &&
                'target' in item.result.output &&
                item.result.output.target === target &&
                'code' in item.result.output &&
                typeof item.result.output.code === 'string' && (
                  <button
                    onClick={() => {
                      const draft = item.result!.output as { target: string; code: string };
                      onUseGeneratedCode({ ...draft, request_id: item.id });
                    }}
                  >
                    Use generated draft in Custom editor
                  </button>
                )}
            </>
          )}
        </details>
      ))}
      <p>
        Suggestions do not change bindings or start a benchmark. Review the output, keep or change
        recommendations, then Save. No automatic request retries.
      </p>
    </details>
  );
}
