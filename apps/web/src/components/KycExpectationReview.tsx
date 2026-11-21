'use client';

import { useEffect, useRef, useState } from 'react';
import { bindingReads } from '../lib/bindingReads';
import { workspaceApi as api } from '../lib/workspace';

type Row = { id: string; pack_id: string; content_sha256: string; created_at: string };
type Detail = { id: string; sha256: string; subject: { pack_id: string; private_packet_sha256: string;
  population_sha256: string; cases: { application_id: string; snapshot_sha256: string; expectation_sha256: string }[] };
  current_review: { ready: boolean; code?: string; receipt_id?: string } };
type Attempt = { path: string; key: string; target: string; operation: 'decision' | 'revoke'; body: Record<string, string> };
const sha = /^[a-f0-9]{64}$/;
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
function exactExpiry(value: Date) {
  return value.toISOString().replace('.000Z', 'Z').replace(/\.(\d{3})Z$/, (_all, ms) => '.' + ms + '000Z');
}

export default function KycExpectationReview({ base, blocked, onBusyChange }: {
  base: string; blocked: boolean; onBusyChange: (value: boolean) => void;
}) {
  const endpoint = base + '/golden-banking/v1/expectation-reviews';
  const journal = 'forge.expectation-review:' + endpoint;
  const [rows, setRows] = useState<Row[]>([]);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [choice, setChoice] = useState('');
  const [packetHash, setPacketHash] = useState('');
  const [reviewed, setReviewed] = useState(false);
  const [rationale, setRationale] = useState('');
  const [evidence, setEvidence] = useState('');
  const [expiry, setExpiry] = useState('');
  const [revokeReason, setRevokeReason] = useState('');
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    try { setUnknown(sessionStorage.getItem(journal) !== null); }
    catch { setUnknown(true); }
    return () => controller.current?.abort();
  }, [journal]);
  function operation(value: boolean) { setBusy(value); onBusyChange(value); }
  async function read(path: string) {
    controller.current?.abort(); controller.current = new AbortController();
    const [value] = await bindingReads<unknown>([path],
      (url, signal) => api(url, 'GET', undefined, undefined, undefined, signal), controller.current);
    return value;
  }
  async function action(work: () => Promise<void>) {
    operation(true); setError(''); setNotice('');
    try { await work(); } catch (error) { setError((error as Error).message); }
    finally { operation(false); }
  }
  async function mutate(attempt: Attempt) {
    sessionStorage.setItem(journal, JSON.stringify(attempt));
    try {
      const result = await api(attempt.path, 'POST', attempt.body, undefined, attempt.key);
      if (result?.run_authority !== 'not_granted' ||
          (attempt.operation === 'decision' && (!uuid.test(result.id) || !sha.test(result.sha256) || result.decision !== attempt.body.decision || result.case_count !== detail?.subject.cases.length)) ||
          (attempt.operation === 'revoke' && result.revoked !== true)) {
        setUnknown(true); throw new Error('Review receipt needs reconciliation before another submission.');
      }
      sessionStorage.removeItem(journal);
      setNotice(attempt.operation === 'decision'
        ? 'Owner decision recorded. No run is authorized. An approved current population must be saved into a new preparation.'
        : 'Review revoked. Future admission and grading recheck this decision.');
      setReviewed(false); setChoice(''); setDetail(null);
    } catch (error) {
      const failure = error as Error & { status?: number };
      if (!failure.status || failure.status >= 500) setUnknown(true);
      else sessionStorage.removeItem(journal);
      throw error;
    }
  }
  return <details>
    <summary>KYC private expectation reviews</summary>
    <p>Review the private packet through your private review channel. This screen shows salted hashes and decisions only. Do not paste or upload expected answers here. Policy approval and Run processing rights are separate.</p>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {unknown && <p role="alert">A retained review attempt requires server reconciliation. Refreshing does not clear this hold.</p>}
    <button disabled={busy || blocked} onClick={() => void action(async () => {
      const value = await read(endpoint + '/subjects') as { subjects?: Row[] };
      if (!Array.isArray(value?.subjects)) throw new Error('Expectation review catalogue is incomplete.');
      setRows(value.subjects); if (!value.subjects.length) setNotice('No private expectation population has been staged. Gym must prepare the private review packet first.');
    })}>Load expectation review subjects</button>
    {unknown && <button disabled={busy || blocked} onClick={() => void action(async () => {
      const raw = sessionStorage.getItem(journal); if (!raw) throw new Error('No retained attempt is available; operator reconciliation is required.');
      const attempt = JSON.parse(raw) as Attempt;
      if (!['decision', 'revoke'].includes(attempt.operation) || !attempt.key || !attempt.target) throw new Error('Retained attempt is invalid.');
      const body = { [attempt.operation === 'decision' ? 'subject_id' : 'receipt_id']: attempt.target, ...attempt.body };
      const bytes = new TextEncoder().encode(JSON.stringify(Object.fromEntries(Object.keys(body).sort().map(key => [key, body[key]]))));
      const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), v => v.toString(16).padStart(2, '0')).join('');
      const value = await read(`${endpoint}/attempts/${encodeURIComponent(attempt.key)}?target_id=${encodeURIComponent(attempt.target)}&operation=${attempt.operation}&body_sha256=${hash}`) as { committed?: boolean; body_sha256?: string; response?: { run_authority?: string } };
      if (value.committed !== true || value.body_sha256 !== hash || value.response?.run_authority !== 'not_granted')
        throw new Error('No matching committed review is observed yet. Keep the hold; do not submit another decision.');
      sessionStorage.removeItem(journal); setUnknown(false); setDetail(null);
      setNotice('The exact retained review was committed. Reconciliation completed without submitting it again.');
    })}>Reconcile retained review attempt</button>}
    {!!rows.length && <table><thead><tr><th>Pack</th><th>Created</th><th>Subject SHA-256</th><th>Review</th></tr></thead><tbody>
      {rows.map(row => <tr key={row.id}><td>{row.pack_id}</td><td>{row.created_at}</td><td>{row.content_sha256}</td><td>
        <button disabled={busy || blocked} onClick={() => void action(async () => {
          setDetail(null); setReviewed(false); setChoice(''); setPacketHash('');
          const value = await read(endpoint + '/subjects/' + row.id) as Detail;
          if (value?.id !== row.id || value.sha256 !== row.content_sha256 || !Array.isArray(value.subject?.cases) || !sha.test(value.subject.private_packet_sha256))
            throw new Error('Exact expectation review metadata required.');
          setDetail(value);
        })}>Inspect</button></td></tr>)}</tbody></table>}
    {detail && <fieldset disabled={busy || blocked || unknown}><legend>Exact population review</legend>
      <p>Pack: {detail.subject.pack_id} · {detail.subject.cases.length} cases</p>
      <p>Subject: {detail.sha256}</p><p>Private packet: {detail.subject.private_packet_sha256}</p>
      <p>Current review: {detail.current_review.ready ? 'Approved current population' : detail.current_review.code || 'Pending'}</p>
      <details><summary>Application and salted expectation hashes</summary><table><thead><tr><th>Application</th><th>Snapshot SHA-256</th><th>Salted expectation SHA-256</th></tr></thead>
        <tbody>{detail.subject.cases.map(item => <tr key={item.application_id}><td>{item.application_id}</td><td>{item.snapshot_sha256}</td><td>{item.expectation_sha256}</td></tr>)}</tbody></table></details>
      <label>SHA-256 of the privately reviewed canonical packet<input value={packetHash} onChange={e => setPacketHash(e.target.value.trim())} /></label>
      <label>Decision<select value={choice} onChange={e => setChoice(e.target.value)}><option value="">Choose a decision</option><option value="approved">Approve</option><option value="rejected">Reject</option></select></label>
      <label>Rationale<textarea value={rationale} onChange={e => setRationale(e.target.value)} /></label>
      <label>Private review evidence reference<input value={evidence} onChange={e => setEvidence(e.target.value)} /></label>
      <label>Review expires<input type="datetime-local" value={expiry} onChange={e => setExpiry(e.target.value)} /></label>
      <label><input type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)} />I reviewed this exact private packet and population.</label>
      <button disabled={!reviewed || !choice || packetHash !== detail.subject.private_packet_sha256 || rationale.length < 10 || !evidence || !expiry}
        onClick={() => void action(async () => {
          const expires = new Date(expiry); if (!Number.isFinite(expires.getTime()) || expires.getTime() <= Date.now()) throw new Error('Choose a future review expiry.');
          await mutate({ path: endpoint + '/subjects/' + detail.id + '/decisions', target: detail.id, operation: 'decision', key: crypto.randomUUID(),
            body: { subject_sha256: detail.sha256, private_packet_sha256: packetHash, decision: choice,
              rationale, evidence_reference: evidence, expires_at: exactExpiry(expires) } });
        })}>Record owner decision</button>
      {detail.current_review.ready && detail.current_review.receipt_id && <div>
        <label>Revocation reason<input value={revokeReason} onChange={e => setRevokeReason(e.target.value)} /></label>
        <button disabled={revokeReason.length < 10} onClick={() => void action(async () => {
          const target = detail.current_review.receipt_id!;
          await mutate({ path: endpoint + '/' + target + '/revoke', target, operation: 'revoke', key: crypto.randomUUID(), body: { reason: revokeReason } });
        })}>Revoke this review</button></div>}
    </fieldset>}
  </details>;
}
