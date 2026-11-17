'use client';

import { useCallback, useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';

type Pending = {
  execution_id: string;
  request_key: string;
  request_sha256: string;
  deadline: string;
  request: { instruction: string; inputs: Record<string, unknown>; outputs: { id: string; fields: Record<string, string> }[] };
};

export default function WorkflowHumanInbox({ base }: { base: string }) {
  const [items, setItems] = useState<Pending[]>([]);
  const [selected, setSelected] = useState<string>('');
  const [values, setValues] = useState<Record<string, Record<string, string | boolean | number | null>>>({});
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      const value: { items: Pending[] } = await api(base + '/workflows/human-requests');
      setItems(value.items);
    } catch { setMessage('Human requests could not be loaded.'); }
  }, [base]);
  useEffect(() => { setItems([]); setSelected(''); setValues({}); setMessage(''); void load(); }, [load]);
  if (!items.length && !message) return null;
  return <section aria-label="Workflow human requests">
    <h3>Your workflow requests</h3>
    <p>Responses are recorded under your signed-in identity. Responding grants no spending authority.</p>
    <button type="button" onClick={() => void load()} disabled={busy}>Refresh requests</button>
    {message && <p role="status">{message}</p>}
    {items.map(item => {
      const key = item.execution_id + ':' + item.request_key;
      return <article key={key}>
        <p>{item.request.instruction}</p>
        <p>Respond by {new Date(item.deadline).toLocaleString()}</p>
        <details><summary>Supplied information</summary>
          <pre>{JSON.stringify(item.request.inputs, null, 2)}</pre>
        </details>
        <button type="button" disabled={busy} onClick={() => {
          setSelected(key); setValues(Object.fromEntries(item.request.outputs.map(output => [output.id, Object.fromEntries(Object.entries(output.fields).map(([field, type]) => [field, type === 'string' ? '' : type === 'integer' ? 0 : type === 'boolean' ? false : null]))]))); setMessage('');
        }}>Write response</button>
        {selected === key && <form onSubmit={async event => {
          event.preventDefault(); setBusy(true); setMessage('');
          try {
            await api(base + '/workflows/' + item.execution_id + '/human-answers', 'POST', { request_key: item.request_key, request_sha256: item.request_sha256, response: values });
            setValues({}); setSelected(''); setMessage('Response recorded. The workflow can now resume.'); await load();
          } catch (error) { setMessage(error instanceof Error ? error.message : 'Response could not be recorded.'); }
          finally { setBusy(false); }
        }}>
          {item.request.outputs.map(output => <fieldset key={output.id}><legend>{output.id}</legend>
            {Object.entries(output.fields).map(([field, type]) => {
              const value = values[output.id]?.[field];
              const fieldId = key + ':' + output.id + ':' + field;
              const update = (next: string | boolean | number | null) => setValues(current => ({ ...current, [output.id]: { ...current[output.id], [field]: next } }));
              return <div key={field}><label htmlFor={fieldId}>{field}</label>
                {type === 'string' ? <textarea id={fieldId} required maxLength={8192} value={String(value ?? '')} onChange={event => update(event.target.value)} />
                  : type === 'integer' ? <input id={fieldId} required type="number" step="1" value={Number(value ?? 0)} onChange={event => update(event.target.valueAsNumber)} />
                  : <select id={fieldId} value={value === null ? 'unknown' : String(value)} onChange={event => update(event.target.value === 'unknown' ? null : event.target.value === 'true')}>
                    {type === 'boolean_or_unknown' && <option value="unknown">Unknown</option>}
                    <option value="true">Yes</option><option value="false">No</option>
                  </select>}
              </div>;
            })}
          </fieldset>)}
          <button type="submit" disabled={busy}>Record response</button>
          <button type="button" disabled={busy} onClick={async () => {
            setBusy(true); setMessage('');
            try {
              await api(base + '/workflows/' + item.execution_id + '/human-answers', 'POST', { request_key: item.request_key, request_sha256: item.request_sha256, outcome: 'error', response: {} });
              setSelected(''); setValues({}); setMessage('Unable-to-complete response recorded.'); await load();
            } catch (error) { setMessage(error instanceof Error ? error.message : 'Response could not be recorded.'); }
            finally { setBusy(false); }
          }}>Record unable to complete</button>
        </form>}
      </article>;
    })}
  </section>;
}
