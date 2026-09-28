import { useState } from 'react';

type Item = {
  item_key: string;
  label: string;
  status: string;
  declared_status: string | null;
  explanation: string;
  row_version: number;
  editable: boolean;
  evidence_ids: string[];
  owner_user_id: string | null;
  blocks_operations: string[];
};
type Snapshot = {
  source_revision_id: string;
  can_edit: boolean;
  items: Item[];
  local_blockers: string[];
  boundary: string;
  evidence_options: { id: string; classification: string; sha256: string }[];
};

export default function CaseReadiness({
  base,
  id,
  members,
}: {
  base: string;
  id: string;
  members: { id: string; name: string }[];
}) {
  const [data, setData] = useState<Snapshot | null>(null),
    [selected, setSelected] = useState<Item | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  async function request(item?: Item, body?: unknown) {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const csrf =
        document.cookie
          .split('; ')
          .find((x) => x.startsWith('anvil_csrf='))
          ?.split('=')[1] || '';
      const response = await fetch(
        '/api/v1' + base + '/cases/' + id + '/readiness' + (item ? '/' + item.item_key : ''),
        {
          method: item ? 'PATCH' : 'GET',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrf,
            ...(item
              ? { 'If-Match': String(item.row_version), 'Idempotency-Key': crypto.randomUUID() }
              : {}),
          },
          ...(item ? { body: JSON.stringify(body) } : {}),
        },
      );
      const result = await response.json();
      if (!response.ok) throw new Error(result.error?.message || 'Readiness request failed');
      setData(result.data);
      setSelected(null);
      if (item) setMessage('Gap annotation saved for this source version.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <button disabled={busy} onClick={() => void request()}>
        {data ? 'Refresh readiness' : 'View readiness and gaps'}
      </button>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {data && (
        <>
          <p className="banner">
            {data.local_blockers.length
              ? data.local_blockers.length + ' local readiness gaps remain.'
              : 'No local readiness gaps detected. Task qualification and independent reviews remain required.'}
          </p>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Readiness item</th>
                  <th>Current status</th>
                  <th>Explanation</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.item_key}>
                    <td>{item.label}</td>
                    <td>{item.status.replaceAll('_', ' ')}</td>
                    <td>{item.explanation}</td>
                    <td>
                      {data.can_edit && item.editable && (
                        <button disabled={busy} onClick={() => setSelected(item)}>
                          Record {item.label.toLowerCase()} gap
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted">{data.boundary}</p>
          {selected && (
            <form
              aria-label="Gap annotation"
              key={selected.item_key}
              onSubmit={(event) => {
                event.preventDefault();
                const form = new FormData(event.currentTarget);
                void request(selected, {
                  source_revision_id: data.source_revision_id,
                  status: form.get('status'),
                  explanation: form.get('explanation'),
                  owner_user_id: form.get('owner') || null,
                  evidence_ids: form.getAll('evidence'),
                });
              }}
            >
              <h3>{selected.label}</h3>
              <label htmlFor={id + '-gap-status'}>Gap status</label>
              <select
                id={id + '-gap-status'}
                name="status"
                defaultValue={selected.declared_status || 'missing'}
              >
                <option value="missing">Missing</option>
                <option value="partial">Partial</option>
                <option value="available">Available — evidence required</option>
              </select>
              <label htmlFor={id + '-gap-explanation'}>Gap explanation or resolution</label>
              <textarea
                id={id + '-gap-explanation'}
                name="explanation"
                defaultValue={selected.declared_status ? selected.explanation : ''}
                minLength={10}
                maxLength={2000}
                required
              />
              <label htmlFor={id + '-gap-owner'}>Responsible project member (optional)</label>
              <select
                id={id + '-gap-owner'}
                name="owner"
                defaultValue={selected.owner_user_id || ''}
              >
                <option value="">Unassigned</option>
                {Array.from(new Map(members.map((m) => [m.id, m])).values()).map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
              <fieldset>
                <legend>Supporting source evidence</legend>
                {data.evidence_options.map((file) => (
                  <label key={file.id}>
                    <input
                      type="checkbox"
                      name="evidence"
                      value={file.id}
                      defaultChecked={selected.evidence_ids.includes(file.id)}
                    />
                    {file.classification.replaceAll('_', ' ')} · digest {file.sha256.slice(0, 12)}
                  </label>
                ))}
              </fieldset>
              <div className="actions">
                <button disabled={busy}>Save gap annotation</button>
                <button type="button" onClick={() => setSelected(null)}>
                  Cancel gap editing
                </button>
              </div>
            </form>
          )}
        </>
      )}
    </div>
  );
}
