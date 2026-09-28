import Form from './Form';
import { useState } from 'react';

type Contact = { id: string; name: string; email: string; status: string; row_version: number };
type Sender = { id: string; name: string; status: string; scenario: string; row_version: number };
type Kit = {
  id: string;
  current_revision_id: string;
  lifecycle: string;
  content: { title: string };
};
type Approval = {
  id: string;
  kit_revision_id: string;
  contact_id: string;
  binding_hash: string;
  expires_at: string;
};
type Delivery = { id: string; status: string; attempts: number; error_code: string | null };

export default function FixtureDelivery({ base, roles }: { base: string; roles: string[] }) {
  const [contacts, setContacts] = useState<Contact[]>([]),
    [senders, setSenders] = useState<Sender[]>([]),
    [kits, setKits] = useState<Kit[]>([]),
    [approvals, setApprovals] = useState<Approval[]>([]),
    [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [loaded, setLoaded] = useState(false);
  const admin = roles.includes('admin'),
    sales = roles.includes('sales'),
    owner = roles.includes('product-owner');
  async function request(path: string, body?: unknown, version?: number) {
    const csrf =
      document.cookie
        .split('; ')
        .find((x) => x.startsWith('anvil_csrf='))
        ?.split('=')[1] || '';
    const r = await fetch('/api/v1' + base + path, {
      method: body ? 'POST' : 'GET',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf,
        'Idempotency-Key': crypto.randomUUID(),
        ...(version ? { 'If-Match': String(version) } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const result = await r.json();
    if (!r.ok)
      throw new Error(
        typeof result.error?.message === 'string'
          ? result.error.message
          : JSON.stringify(result.error?.message),
      );
    return result.data;
  }
  async function load() {
    setSenders(await request('/fixture-senders'));
    if (sales || owner) {
      setContacts(await request('/sales-contacts'));
      setKits(await request('/sales-kits'));
      setApprovals(await request('/delivery-approvals'));
      setDeliveries(await request('/sales-deliveries'));
    }
    setLoaded(true);
  }
  async function run(work: () => Promise<unknown>) {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await work();
      await load();
      setMessage('Local fixture state saved. No email sent.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="card">
      <summary>Network-free mail simulation</summary>
      <p>
        This tests approval and delivery-state handling using reserved <code>.invalid</code>{' '}
        recipients. Real email sending is unavailable. Simulated acceptance does not mean inbox
        delivery or reading.
      </p>
      <button disabled={busy} onClick={() => void run(load)}>
        {loaded ? 'Refresh simulation state' : 'Load simulation controls'}
      </button>
      {admin && (
        <Form
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            void run(() =>
              request('/fixture-senders', {
                name: String(f.get('name')),
                scenario: String(f.get('scenario')),
              }),
            );
          }}
        >
          <h3>Configure a fixture sender</h3>
          <label htmlFor="fixture-sender-name">Name</label>
          <input id="fixture-sender-name" name="name" minLength={3} required />
          <label htmlFor="fixture-scenario">Simulated result</label>
          <select id="fixture-scenario" name="scenario">
            <option value="accepted">Accepted (simulation)</option>
            <option value="failed">Known failure</option>
            <option value="unknown">Unknown acceptance</option>
          </select>
          <button disabled={busy}>Save fixture sender draft</button>
        </Form>
      )}
      {loaded &&
        admin &&
        senders.map((s) => (
          <div className="card" key={s.id}>
            <strong>{s.name}</strong>
            <p>
              {s.status} · {s.scenario}
            </p>
            {s.status === 'draft' && (
              <button
                disabled={busy}
                onClick={() =>
                  void run(() =>
                    request('/fixture-senders/' + s.id + '/activate', {}, s.row_version),
                  )
                }
              >
                Activate as a distinct Admin
              </button>
            )}
          </div>
        ))}
      {sales && (
        <Form
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            void run(() =>
              request('/sales-contacts', {
                name: String(f.get('name')),
                email: String(f.get('email')),
                organization_label: String(f.get('organization')),
                contact_basis: String(f.get('basis')),
              }),
            );
          }}
        >
          <h3>Propose a synthetic contact</h3>
          <label htmlFor="fixture-contact-name">Name</label>
          <input id="fixture-contact-name" name="name" minLength={2} required />
          <label htmlFor="fixture-contact-email">Reserved fixture address</label>
          <input
            id="fixture-contact-email"
            name="email"
            placeholder="test@lab.invalid"
            pattern=".+@.+\.invalid"
            required
          />
          <label htmlFor="fixture-contact-org">Organization label</label>
          <input id="fixture-contact-org" name="organization" minLength={2} required />
          <label htmlFor="fixture-contact-basis">Test purpose and contact basis</label>
          <textarea id="fixture-contact-basis" name="basis" minLength={10} required />
          <button disabled={busy}>Save synthetic contact draft</button>
        </Form>
      )}
      {loaded &&
        (sales || owner) &&
        contacts.map((c) => (
          <div className="card" key={c.id}>
            <strong>{c.name}</strong>
            <p>
              {c.email} · {c.status}
            </p>
            {owner && (
              <div className="actions">
                <button
                  disabled={busy || c.status === 'approved'}
                  onClick={() =>
                    void run(() =>
                      request(
                        '/sales-contacts/' + c.id + '/decision',
                        { status: 'approved' },
                        c.row_version,
                      ),
                    )
                  }
                >
                  Approve contact
                </button>
                <button
                  disabled={busy || c.status === 'suppressed'}
                  onClick={() =>
                    void run(() =>
                      request(
                        '/sales-contacts/' + c.id + '/decision',
                        { status: 'suppressed' },
                        c.row_version,
                      ),
                    )
                  }
                >
                  Suppress contact
                </button>
              </div>
            )}
          </div>
        ))}
      {loaded && owner && (
        <Form
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            void run(() =>
              request('/sales-kits/' + String(f.get('kit')) + '/delivery-approvals', {
                recipient_contact_id: String(f.get('contact')),
                sender_connection_id: String(f.get('sender')),
                expires_in_minutes: 60,
              }),
            );
          }}
        >
          <h3>Approve an exact simulated delivery</h3>
          <label htmlFor="delivery-kit">Reviewed kit</label>
          <select id="delivery-kit" name="kit" required>
            <option value="">Select kit</option>
            {kits
              .filter((k) => k.lifecycle === 'approved')
              .map((k) => (
                <option key={k.id} value={k.id}>
                  {k.content.title} · {k.id.slice(0, 8)}
                </option>
              ))}
          </select>
          <label htmlFor="delivery-contact">Approved recipient</label>
          <select id="delivery-contact" name="contact" required>
            <option value="">Select contact</option>
            {contacts
              .filter((c) => c.status === 'approved')
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.email}
                </option>
              ))}
          </select>
          <label htmlFor="delivery-sender">Active fixture sender</label>
          <select id="delivery-sender" name="sender" required>
            <option value="">Select sender</option>
            {senders
              .filter((s) => s.status === 'active')
              .map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} · {s.scenario}
                </option>
              ))}
          </select>
          <p>
            Approval expires in one hour and binds the exact report, email, PDF, recipient and
            sender.
          </p>
          <button disabled={busy}>Approve fixture delivery</button>
        </Form>
      )}
      {loaded &&
        sales &&
        approvals.map((a) => {
          const kit = kits.find((k) => k.current_revision_id === a.kit_revision_id);
          return (
            <div className="card" key={a.id}>
              <p>
                {contacts.find((c) => c.id === a.contact_id)?.email} · approval {a.id.slice(0, 8)}
              </p>
              <p>Expires {new Date(a.expires_at).toLocaleString()}</p>
              <button
                disabled={busy || !kit || new Date(a.expires_at) < new Date()}
                onClick={() =>
                  kit &&
                  void run(() =>
                    request('/sales-kits/' + kit.id + '/simulate-send', {
                      delivery_approval_id: a.id,
                      content_hash: a.binding_hash,
                    }),
                  )
                }
              >
                Simulate approved delivery
              </button>
            </div>
          );
        })}
      {loaded && deliveries.length > 0 && (
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Delivery</th>
                <th>Fixture state</th>
                <th>Attempts</th>
              </tr>
            </thead>
            <tbody>
              {deliveries.map((d) => (
                <tr key={d.id}>
                  <td>{d.id.slice(0, 8)}</td>
                  <td>
                    {d.status}
                    {d.error_code ? ' · ' + d.error_code : ''}
                  </td>
                  <td>{d.attempts}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {error && (
        <p className="banner error" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="banner" role="status">
          {message}
        </p>
      )}
    </details>
  );
}
