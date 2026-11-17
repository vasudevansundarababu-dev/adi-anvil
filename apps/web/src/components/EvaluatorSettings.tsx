'use client';

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import type { ModelConfiguration } from './ModelProfileEditor';
import FixedJudgePicker, { currentJudge } from './FixedJudgePicker';
import styles from './ModernWorkspace.module.css';

type Configuration = {
  id: string;
  name: string;
  adapter: string;
  status: string;
  evaluation_mode?: 'deterministic' | 'native_ordinal' | 'native_semantic' | 'native_diagnostic';
  configuration_sha256: string;
  configuration?: {
    native_semantic?: { model_selection: 'candidate' | 'fixed'; judge_model_profile_id?: string };
    semantic_judge_model?: { name?: string; model_id?: string };
  };
  validation: null | {
    evidence: {
      passed: boolean;
      runtime_version?: string;
      native_semantic_version?: string;
      native_diagnostic_version?: string;
      provider_calls?: number;
      validation_scope?: string;
    };
  };
};

export default function EvaluatorSettings({ base }: { base: string }) {
  const endpoint = base + '/workspace/evaluators';
  const [items, setItems] = useState<Configuration[]>([]);
  const [catalog, setCatalog] = useState<
    {
      id: string;
      name: string;
      status: string;
      version?: string;
      capability: string;
      reason: string;
    }[]
  >([]);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [adapter, setAdapter] = useState('zen');
  const [judgeModel, setJudgeModel] = useState('');
  const [selected, setSelected] = useState('');
  const [protocolModels, setProtocolModels] = useState<ModelConfiguration[]>([]);
  const [protocolSelected, setProtocolSelected] = useState<string[]>([]);
  const [protocolCursor, setProtocolCursor] = useState<string | null>(null);
  const [protocolLoading, setProtocolLoading] = useState(false);
  const [protocolError, setProtocolError] = useState('');
  const protocolGeneration = useRef(0);
  const activeBase = useRef(base);
  const contextGeneration = useRef(0);
  useLayoutEffect(() => {
    activeBase.current = base;
    contextGeneration.current++;
    protocolGeneration.current++;
    setSelected('');
    setJudgeModel('');
    setItems([]);
    setCatalog([]);
    setMessage('');
    setError('');
    setBusy(false);
    return () => {
      contextGeneration.current++;
      protocolGeneration.current++;
    };
  }, [base]);
  const reload = useCallback(async () => {
    const generation = contextGeneration.current;
    const value = await api(endpoint);
    if (activeBase.current !== base || generation !== contextGeneration.current) return;
    setItems(value.items);
    setCatalog(value.catalog || []);
  }, [base, endpoint]);
  useEffect(() => {
    const generation = contextGeneration.current;
    reload().catch((e) => {
      if (activeBase.current === base && generation === contextGeneration.current)
        setError(e.message);
    });
  }, [base, reload]);
  const ordinal = adapter === 'builtin-ordinal';
  const semantic = adapter === 'builtin-semantic';
  const diagnostic = adapter === 'builtin-diagnostic';
  const selectedConfiguration = items.find((item) => item.id === selected);
  const fixedJudgeId =
    selectedConfiguration?.configuration?.native_semantic?.model_selection === 'fixed'
      ? selectedConfiguration.configuration.native_semantic.judge_model_profile_id
      : undefined;
  const fixedJudgeReady =
    !!fixedJudgeId &&
    protocolModels.some((model) => model.id === fixedJudgeId && currentJudge(model));
  useEffect(() => {
    const generation = ++protocolGeneration.current;
    setProtocolModels([]);
    setProtocolSelected(fixedJudgeId ? [fixedJudgeId] : []);
    setProtocolCursor(null);
    setProtocolError('');
    if (selectedConfiguration?.evaluation_mode !== 'native_semantic') return;
    setProtocolLoading(true);
    api(base + '/workspace/models?current_only=true&limit=100')
      .then((page) => {
        if (generation !== protocolGeneration.current) return;
        setProtocolModels(page.items);
        setProtocolCursor(page.next_cursor);
      })
      .catch((err) => {
        if (generation === protocolGeneration.current) setProtocolError(err.message);
      })
      .finally(() => {
        if (generation === protocolGeneration.current) setProtocolLoading(false);
      });
    return () => {
      protocolGeneration.current++;
    };
  }, [base, selected, selectedConfiguration?.evaluation_mode, fixedJudgeId]);
  const local = ['builtin', 'builtin-ordinal', 'zen', 'opa-local', 'nemo', 'promptfoo'].includes(
    adapter,
  );
  return (
    <section className={styles.panel} aria-label="Evaluator configuration">
      <h2>Evaluators and integrations</h2>
      <p>
        Evaluators check task criteria, policy decisions and captured evidence. Qualified task
        imports reuse tested configurations and bind their exact versions to the shared environment.
        Admin and RL Engineer can also configure and test evaluators here.
      </p>
      <p>
        A configuration is available for selection only after its required validation passes. Review
        bindings under Projects; benchmark methods determine how the resulting checks are assessed.
        A saved configuration alone does not qualify a task or authorize paid calls.
      </p>
      <details>
        <summary>Integration catalog and actual capabilities</summary>
        <table>
          <thead>
            <tr>
              <th>Integration</th>
              <th>Runtime</th>
              <th>Capability</th>
              <th>Readiness</th>
            </tr>
          </thead>
          <tbody>
            {catalog.map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td>{c.version || '—'}</td>
                <td>{c.capability}</td>
                <td>
                  {c.status.replaceAll('_', ' ')} · {c.reason}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
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
                <button disabled={busy} onClick={() => setSelected(item.id)}>
                  {item.name}
                </button>
              </td>
              <td>{item.adapter}</td>
              <td>
                {['native_semantic', 'native_diagnostic'].includes(item.evaluation_mode || '') &&
                item.status === 'ready'
                  ? 'Software validated · Project binding required'
                  : item.status.replaceAll('_', ' ')}
              </td>
              <td>
                {item.evaluation_mode === 'native_semantic'
                  ? item.validation?.evidence.validation_scope === 'sdk_mock_software_protocol_only'
                    ? `Software protocol ${item.validation.evidence.passed ? 'passed' : 'failed'}`
                    : 'Software validation required'
                  : item.evaluation_mode === 'native_diagnostic'
                    ? item.validation?.evidence.validation_scope ===
                      'manufactured_measurement_software_controls_only'
                      ? `Measurement software ${item.validation.evidence.passed ? 'passed' : 'failed'}`
                      : 'Measurement software validation required'
                    : item.validation
                      ? `${item.validation.evidence.passed ? 'Passed' : 'Failed'} · ${item.validation.evidence.runtime_version || item.validation.evidence.native_semantic_version || 'Validation receipt'}`
                      : 'Not tested'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!items.length && (
        <p role="status">
          No evaluator configurations are saved for this project. Task evaluator setup has not
          completed. Complete the qualified task import before benchmarking; creating an empty
          configuration will not supply its task-specific checks or policy bindings.
        </p>
      )}
      <details>
        <summary>Add evaluator configuration</summary>
        <form
          key={base}
          onSubmit={async (e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const data = new FormData(form);
            const generation = contextGeneration.current;
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
                  : kind === 'equals' && ['true', 'false'].includes(rawValue)
                    ? rawValue === 'true'
                    : rawValue;
              let nativeProgram;
              if (ordinal || semantic || diagnostic) {
                nativeProgram = JSON.parse(String(data.get('nativeProgram')));
                if (semantic) {
                  if (!judgeModel) throw new Error('Choose an independent judge model.');
                  if (
                    !nativeProgram ||
                    Array.isArray(nativeProgram) ||
                    typeof nativeProgram !== 'object'
                  )
                    throw new Error('Enter a judge profile object with criterion IDs and limits.');
                  if (
                    (nativeProgram.schema_version &&
                      nativeProgram.schema_version !== 'anvil.native-semantic-program.v2') ||
                    (nativeProgram.model_selection && nativeProgram.model_selection !== 'fixed') ||
                    (nativeProgram.judge_model_profile_id &&
                      nativeProgram.judge_model_profile_id !== judgeModel)
                  )
                    throw new Error(
                      'The profile must use the selected independent judge. Remove conflicting model selection fields.',
                    );
                  nativeProgram = {
                    ...nativeProgram,
                    schema_version: 'anvil.native-semantic-program.v2',
                    model_selection: 'fixed',
                    judge_model_profile_id: judgeModel,
                  };
                }
              }
              const body =
                ordinal || semantic || diagnostic
                  ? {
                      name: data.get('name'),
                      adapter: 'builtin',
                      [semantic
                        ? 'native_semantic'
                        : diagnostic
                          ? 'native_diagnostic'
                          : 'native_ordinal']: nativeProgram,
                    }
                  : local
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
              if (activeBase.current !== base || generation !== contextGeneration.current) return;
              form.reset();
              setJudgeModel('');
              setSelected(result.id);
              await reload();
              if (activeBase.current !== base || generation !== contextGeneration.current) return;
              setMessage(
                semantic
                  ? 'Judge profile saved. Exact case, model, reference and runtime qualification is required before selection. Saving makes no model call.'
                  : diagnostic
                    ? 'Skill measurement profile saved. Validate its software below; exact Project, evidence and runtime qualification are still required.'
                    : 'Configuration saved. Test it before selecting it for a Run.',
              );
            } catch (err) {
              if (activeBase.current === base && generation === contextGeneration.current)
                setError((err as Error).message);
            } finally {
              if (activeBase.current === base && generation === contextGeneration.current)
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
              <option value="builtin">Forge structured rules · local deterministic checks</option>
              <option value="builtin-ordinal">
                Forge native 0–4 anchors · deterministic facts
              </option>
              <option value="builtin-semantic">Forge native 0–4 semantic judge</option>
              <option value="builtin-diagnostic">Forge skill diagnostic measurements</option>
              <option value="nemo">NeMo Guardrails · deterministic forbidden literals</option>
              <option value="promptfoo">Promptfoo · deterministic literal assertions</option>
              <option value="opa">OPA · configured decision service</option>
              <option value="arthur">Arthur Engine · prompt validation API</option>
              <option value="openlayer">Openlayer · existing test evaluation API</option>
            </select>
          </label>
          {semantic ? (
            <>
              <FixedJudgePicker
                key={base}
                base={base}
                value={judgeModel}
                change={setJudgeModel}
                disabled={busy}
              />
              <label>
                Native semantic judge profile JSON
                <textarea
                  key="semantic-program"
                  name="nativeProgram"
                  rows={10}
                  maxLength={49152}
                  required
                  defaultValue={JSON.stringify(
                    {
                      criterion_ids: [],
                      max_input_bytes: 32768,
                      max_output_tokens: 1024,
                      max_calls: 1,
                    },
                    null,
                    2,
                  )}
                />
              </label>
              <p>
                Specify the exact criterion IDs, input byte limit, output token limit and one call
                per batch. Reviewed anchors and reference evidence stay private and are bound to
                each case in Project bindings.
              </p>
              <p>
                A saved profile is not ready until its software runtime and exact case/model purpose
                are qualified. Candidate and judge calls share the Run budget. Saving this profile
                makes no model call and does not establish human calibration.
              </p>
            </>
          ) : diagnostic ? (
            <>
              <label>
                Skill measurement profile JSON
                <textarea
                  key="diagnostic-program"
                  name="nativeProgram"
                  rows={8}
                  maxLength={49152}
                  required
                  defaultValue={JSON.stringify(
                    {
                      schema_version: 'anvil.native-diagnostic-program.v1',
                      method: 'anvil.diagnostic-measure.v1',
                      target_ids: ['K.FILE'],
                    },
                    null,
                    2,
                  )}
                />
              </label>
              <p>
                Select the exact skill IDs from the Project skill mappings. This measures captured
                evidence against each skill's defined contract; it adds no official task points.
                Missing evidence stays unscored. Software validation does not qualify the
                environment, semantic labels or human references.
              </p>
            </>
          ) : ordinal ? (
            <>
              <label>
                Native 0–4 anchor program JSON
                <textarea
                  key="ordinal-program"
                  name="nativeProgram"
                  rows={12}
                  maxLength={49152}
                  required
                />
              </label>
              <p>
                Define named JSON-pointer selectors and one explicit anchor for each award 0, 1, 2,
                3 and 4. Each anchor has a description and conditions over captured facts. Exactly
                one anchor must match; missing or ambiguous evidence stays unscored. No Python or
                model calls execute here.
              </p>
              <p>
                Test all five awards and an unscored case below. Software tests do not establish
                human calibration; exact rubric, reference and deployment qualification remain
                required in Project bindings.
              </p>
            </>
          ) : local ? (
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
      {selected && selectedConfiguration?.evaluation_mode === 'native_semantic' && (
        <section aria-label="Semantic judge software validation">
          {fixedJudgeId ? (
            <p>
              Saved independent judge:{' '}
              {selectedConfiguration.configuration?.semantic_judge_model?.name ||
                selectedConfiguration.configuration?.semantic_judge_model?.model_id ||
                fixedJudgeId}
              . Validation uses only this model. A changed judge needs a new configuration.
            </p>
          ) : (
            <p>
              Legacy candidate-as-judge profile. The evaluator changes with the candidate; these
              results must not be described as a comparison using one independent judge.
            </p>
          )}
          <p>
            Semantic judges use private, case-bound evaluation. Local known-case tests cannot
            qualify this judge for a benchmark. Software validation tests the installed SDK and
            parser only, using fixed mock responses. It makes no external or paid call and does not
            test model quality. Review its exact rubric, model, reference and runtime bindings under
            Projects.
          </p>
          {protocolError && <p role="alert">{protocolError}</p>}
          {fixedJudgeId && !protocolLoading && !fixedJudgeReady && (
            <p>
              The saved judge is not in the loaded enabled profiles. Load more models if available;
              if it was disabled or replaced, create a new evaluator configuration.
            </p>
          )}
          <fieldset disabled={busy || protocolLoading}>
            <legend>
              {fixedJudgeId
                ? 'Saved independent judge to validate'
                : 'Saved models to validate (choose up to eight)'}
            </legend>
            {protocolModels.map((model) => {
              const available = currentJudge(model);
              const checked = protocolSelected.includes(model.id);
              return (
                <label key={model.id}>
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={
                      !!fixedJudgeId ||
                      (!available && !checked) ||
                      (!checked && protocolSelected.length >= 8)
                    }
                    onChange={(e) =>
                      setProtocolSelected((current) =>
                        e.target.checked
                          ? [...current, model.id]
                          : current.filter((id) => id !== model.id),
                      )
                    }
                  />
                  {model.name} · {model.model_id || model.provider}
                  {!available && ' · Not a current enabled model profile'}
                </label>
              );
            })}
            {!protocolLoading && !protocolModels.length && (
              <p>No saved model profiles are available. Configure them in Models &amp; Keys.</p>
            )}
          </fieldset>
          {protocolLoading && <p role="status">Loading saved models…</p>}
          {protocolCursor && (
            <button
              disabled={busy || protocolLoading}
              onClick={async () => {
                const generation = protocolGeneration.current,
                  cursor = protocolCursor;
                setProtocolLoading(true);
                setProtocolError('');
                try {
                  const page = await api(
                    base +
                      '/workspace/models?current_only=true&limit=100&after=' +
                      encodeURIComponent(cursor),
                  );
                  if (generation !== protocolGeneration.current) return;
                  if (page.next_cursor === cursor)
                    throw new Error('Model list changed. Select the profile again to refresh it.');
                  setProtocolModels((current) => [
                    ...new Map(
                      [...current, ...page.items].map((model) => [model.id, model]),
                    ).values(),
                  ]);
                  setProtocolCursor(page.next_cursor);
                } catch (err) {
                  if (generation === protocolGeneration.current)
                    setProtocolError((err as Error).message);
                } finally {
                  if (generation === protocolGeneration.current) setProtocolLoading(false);
                }
              }}
            >
              Load more models
            </button>
          )}
          <button
            disabled={
              busy ||
              protocolLoading ||
              (fixedJudgeId ? !fixedJudgeReady : !protocolSelected.length)
            }
            onClick={async () => {
              const generation = contextGeneration.current;
              setBusy(true);
              setError('');
              setMessage('');
              try {
                const result = await api(
                  endpoint + '/' + selected + '/test-semantic-runtime',
                  'POST',
                  { model_profile_ids: protocolSelected },
                  undefined,
                  crypto.randomUUID(),
                );
                if (activeBase.current !== base || generation !== contextGeneration.current) return;
                await reload();
                if (activeBase.current !== base || generation !== contextGeneration.current) return;
                setMessage(
                  result.status === 'ready'
                    ? 'Software protocol validated for the selected saved models. Project qualification is still required before benchmarking.'
                    : 'Software protocol validation did not pass. This profile is not ready for benchmark selection.',
                );
              } catch (err) {
                if (activeBase.current === base && generation === contextGeneration.current)
                  setError((err as Error).message);
              } finally {
                if (activeBase.current === base && generation === contextGeneration.current)
                  setBusy(false);
              }
            }}
          >
            {busy ? 'Validating…' : 'Validate software protocol'}
          </button>
        </section>
      )}
      {selected && selectedConfiguration?.evaluation_mode === 'native_diagnostic' && (
        <section aria-label="Skill measurement software validation">
          <h4>Validate skill measurement software</h4>
          <p>
            Runs known positive, negative, missing-evidence and wrong-context controls for the saved
            skill IDs. No model calls are made. A pass checks measurement arithmetic and evidence
            handling; it does not establish benchmark readiness or human calibration.
          </p>
          <button
            disabled={busy}
            onClick={async () => {
              const generation = contextGeneration.current;
              setBusy(true);
              setError('');
              setMessage('');
              try {
                const result = await api(
                  endpoint + '/' + selected + '/test-diagnostic-runtime',
                  'POST',
                  {},
                  undefined,
                  crypto.randomUUID(),
                );
                if (activeBase.current !== base || generation !== contextGeneration.current) return;
                await reload();
                if (activeBase.current !== base || generation !== contextGeneration.current) return;
                setMessage(
                  result.status === 'ready'
                    ? 'Skill measurement software controls passed. Exact Project binding, source evidence and independent runtime qualification remain required.'
                    : 'Skill measurement software controls failed. Configuration is not ready.',
                );
              } catch (err) {
                if (activeBase.current === base && generation === contextGeneration.current)
                  setError((err as Error).message);
              } finally {
                if (activeBase.current === base && generation === contextGeneration.current)
                  setBusy(false);
              }
            }}
          >
            {busy ? 'Validating…' : 'Validate measurement software'}
          </button>
        </section>
      )}
      {selected &&
        !['native_semantic', 'native_diagnostic'].includes(
          selectedConfiguration?.evaluation_mode || '',
        ) && (
          <details open>
            <summary>Test selected configuration</summary>
            <p>
              Provide known allowed, forbidden and missing-evidence cases. These test the evaluator,
              not model performance. Native 0–4 configurations require integer expected awards 0, 1,
              2, 3, 4 and null for an unscored case.
            </p>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                const generation = contextGeneration.current;
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
                  if (activeBase.current !== base || generation !== contextGeneration.current)
                    return;
                  await reload();
                  if (activeBase.current !== base || generation !== contextGeneration.current)
                    return;
                  setMessage(
                    result.status === 'ready'
                      ? 'Known cases passed. This local configuration is ready.'
                      : 'Known cases did not all pass. Configuration is not ready.',
                  );
                } catch (err) {
                  if (activeBase.current === base && generation === contextGeneration.current)
                    setError((err as Error).message);
                } finally {
                  if (activeBase.current === base && generation === contextGeneration.current)
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
