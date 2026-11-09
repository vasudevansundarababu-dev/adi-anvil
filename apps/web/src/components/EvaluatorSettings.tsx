'use client';

import { useCallback, useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';

type Configuration = {
  id: string;
  name: string;
  adapter: string;
  status: string;
  configuration_sha256: string;
  validation: null | {
    evidence: { passed: boolean; runtime_version: string; provider_calls: number };
  };
};

export default function EvaluatorSettings({ base }: { base: string }) {
  const endpoint = base + '/workspace/evaluators';
  const [items, setItems] = useState<Configuration[]>([]);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [adapter, setAdapter] = useState('zen');
  const [selected, setSelected] = useState('');
  const reload = useCallback(async () => {
    const value = await api(endpoint);
    setItems(value.items);
  }, [endpoint]);
  useEffect(() => {
    reload().catch((e) => setError(e.message));
  }, [reload]);
  const local = ['builtin', 'zen', 'opa-local', 'nemo', 'promptfoo'].includes(adapter);
  return (
    <section className={styles.panel} aria-label="Evaluator configuration">
      <h2>Evaluators and integrations</h2>
      <p>
        Configure once, test known cases, reuse with compatible policies. Admin and RL Engineer can
        configure evaluators.
      </p>
      <p>Live API calls are off. Saving a key makes no external request.</p>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      <table>
        <thead>
          <tr>
            <th>Configuration</th>
            <th>Evaluator</th>
            <th>Status</th>
            <th>Validation</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>
                <button onClick={() => setSelected(item.id)}>{item.name}</button>
              </td>
              <td>{item.adapter}</td>
              <td>{item.status.replaceAll('_', ' ')}</td>
              <td>
                {item.validation
                  ? `${item.validation.evidence.passed ? 'Passed' : 'Failed'} · ${item.validation.evidence.runtime_version}`
                  : 'Not tested'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!items.length && <p>No evaluator configurations saved for this project.</p>}
      <details>
        <summary>Add evaluator configuration</summary>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const data = new FormData(form);
            setBusy(true);
            setError('');
            setMessage('');
            try {
              const kind = String(data.get('kind'));
              const rawValue = String(data.get('value') || '');
              const value = kind.startsWith('number_')
                ? Number(rawValue)
                : kind === 'allowlist'
                  ? rawValue
                      .split(',')
                      .map((x) => x.trim())
                      .filter(Boolean)
                  : rawValue;
              const body = local
                ? {
                    name: data.get('name'),
                    adapter,
                    rule: {
                      kind,
                      field: data.get('field'),
                      ...(kind === 'required' ? {} : { value }),
                    },
                  }
                : {
                    name: data.get('name'),
                    adapter,
                    endpoint: data.get('endpoint'),
                    resource_id: data.get('resource'),
                    secret: data.get('secret'),
                  };
              const result = await api(endpoint, 'POST', body, undefined, crypto.randomUUID());
              form.reset();
              setSelected(result.id);
              await reload();
              setMessage('Configuration saved. Test it before selecting it for a Run.');
            } catch (err) {
              setError((err as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Name
            <input name="name" maxLength={160} required />
          </label>
          <label>
            Evaluator
            <select value={adapter} onChange={(e) => setAdapter(e.target.value)}>
              <option value="zen">GoRules ZEN · local deterministic rules</option>
              <option value="opa-local">OPA · local deterministic rules</option>
              <option value="builtin">Anvil structured rules · local deterministic checks</option>
              <option value="nemo">NeMo Guardrails · deterministic forbidden literals</option>
              <option value="promptfoo">Promptfoo · deterministic literal assertions</option>
              <option value="opa">OPA · configured decision service</option>
              <option value="arthur">Arthur Engine · prompt validation API</option>
              <option value="openlayer">Openlayer · existing test evaluation API</option>
            </select>
          </label>
          {local ? (
            <>
              <label>
                Check
                <select name="kind" key={adapter}>
                  {['nemo', 'promptfoo'].includes(adapter) ? (
                    <>
                      <option value="forbidden_text">Forbidden literal text</option>
                      {adapter === 'promptfoo' && <option value="equals">Exact text</option>}
                    </>
                  ) : (
                    <>
                      <option value="number_max">Maximum value inclusive</option>
                      <option value="number_min">Minimum value inclusive</option>
                      <option value="equals">Exact text</option>
                      <option value="allowlist">Allowed destinations</option>
                      <option value="required">Required captured field</option>
                    </>
                  )}
                </select>
              </label>
              <label>
                Captured field
                <input name="field" pattern="[A-Za-z][A-Za-z0-9_]*" required />
              </label>
              <label>
                Value or comma separated destinations
                <input name="value" />
              </label>
            </>
          ) : (
            <>
              <label>
                Provisioned service origin
                <input
                  name="endpoint"
                  type="url"
                  required
                  defaultValue={adapter === 'openlayer' ? 'https://api.openlayer.com' : ''}
                  key={adapter}
                />
              </label>
              <label>
                {adapter === 'opa'
                  ? 'Decision path'
                  : adapter === 'arthur'
                    ? 'Arthur Task ID'
                    : 'Openlayer test ID'}
                <input name="resource" required />
              </label>
              <label>
                API key
                <input name="secret" type="password" autoComplete="new-password" required />
              </label>
              <p>
                API validation remains unavailable until a bounded live test is configured. Keys are
                encrypted and never shown again.
              </p>
            </>
          )}
          <button disabled={busy}>{busy ? 'Saving…' : 'Save configuration'}</button>
        </form>
      </details>
      {selected && (
        <details open>
          <summary>Test selected configuration</summary>
          <p>
            Provide known allowed, forbidden and missing-evidence cases. These test the evaluator,
            not model performance.
          </p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError('');
              setMessage('');
              try {
                const cases = JSON.parse(String(new FormData(e.currentTarget).get('cases')));
                const result = await api(
                  endpoint + '/' + selected + '/test',
                  'POST',
                  { cases },
                  undefined,
                  crypto.randomUUID(),
                );
                await reload();
                setMessage(
                  result.status === 'ready'
                    ? 'Known cases passed. This local configuration is ready.'
                    : 'Known cases did not all pass. Configuration is not ready.',
                );
              } catch (err) {
                setError((err as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              Known cases JSON
              <textarea
                name="cases"
                rows={8}
                required
                defaultValue={
                  '[\n  {"facts":{"amount":100},"expected":"pass"},\n  {"facts":{"amount":101},"expected":"fail"},\n  {"facts":{},"expected":"unknown"}\n]'
                }
              />
            </label>
            <button disabled={busy}>Test local evaluator</button>
          </form>
        </details>
      )}
    </section>
  );
}
