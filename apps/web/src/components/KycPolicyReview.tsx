'use client';

import { useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import { policyReviewMatches } from '../lib/policyReview';

type Subject = {
  schema_version: string; task_id: string; revision_id: string;
  template: { id: string; version: number; sha256: string };
  policy_set: { product: string; governing_state: string; effective_from: string; effective_until: string;
    state_applicability?: string; not_applicable_rationale?: string; [key: string]: unknown };
};
type Row = { subject: Subject; subject_sha256: string };
type Staged = { id: string; content_sha256: string };

export default function KycPolicyReview({ base, tasks, onBusyChange }: {
  base: string; tasks: { task_id: string; task_version: string }[];
  onBusyChange: (busy: boolean) => void;
}) {
  const endpoint = base + '/golden-banking/v1/policy-reviews';
  const journal = 'forge.policy-review-attempt:' + base;
  const [rows, setRows] = useState<Row[]>([]);
  const [staged, setStaged] = useState<Staged[]>([]);
  const [selected, setSelected] = useState('');
  const [detail, setDetail] = useState<{ id: string; sha256: string; subject: Subject } | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(true);
  const [reviewed, setReviewed] = useState(false);
  const [rationale, setRationale] = useState('');
  const [evidence, setEvidence] = useState('');
  const [evidenceHash, setEvidenceHash] = useState('');
  const [expiry, setExpiry] = useState('');
  const [notice, setNotice] = useState('');
  const [reviews, setReviews] = useState<unknown>(null);
  useEffect(() => {
    try { setUnknown(sessionStorage.getItem(journal) !== null); }
    catch { setUnknown(true); }
  }, [journal]);
  function operation(value: boolean) { setBusy(value); onBusyChange(value); }
  async function refresh() {
    const [subjects, decisions] = await Promise.all([api(endpoint + '/subjects'), api(endpoint)]);
    if (!Array.isArray(subjects) || !Array.isArray(decisions?.records)) throw new Error('Review catalogue is incomplete.');
    setStaged(subjects); setReviews(decisions.records);
  }
  async function mutate(path: string, body: unknown) {
    const key = crypto.randomUUID();
    sessionStorage.setItem(journal, JSON.stringify({ path, body, key, status: 'pending_requires_reconciliation' }));
    try {
      const result = await api(path, 'POST', body, undefined, key);
      return result;
    } catch (e) {
      const failure = e as Error & { status?: number };
      if (!failure.status || failure.status >= 500) setUnknown(true);
      else sessionStorage.removeItem(journal);
      throw e;
    }
  }
  return <details>
    <summary>KYC policy review subjects</summary>
    <p>Stage exact public policy references and their pilot applicability interval. Staging grants no approval. A separate Product Owner decision is required for each subject; rights and case expectations remain separate.</p>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {unknown && <p role="alert">A previous operation needs server reconciliation before another submission. Reloading this page does not clear that hold.</p>}
    <label>Prepared public policy subjects <input type="file" accept=".json,application/json" disabled={busy || unknown} onChange={async event => {
      setError(''); setRows([]);
      try {
        const file = event.target.files?.[0]; if (!file) return;
        if (file.size > 2 * 1048576) throw new Error('Policy review input is limited to2MiB.');
        const value = JSON.parse(await file.text());
        if (!Array.isArray(value.subjects) || !value.subjects.length || value.subjects.length > 100) throw new Error('Provide1–100 exact policy subjects.');
        const values = value.subjects as Row[];
        if (values.some(row => row?.subject?.schema_version !== 'anvil.kyc-policy-domain-subject.v1' ||
            !/^[a-f0-9]{64}$/.test(row.subject_sha256) || !row.subject.policy_set ||
            !policyReviewMatches(tasks, row.subject)))
          throw new Error('Every subject must match an exact task revision in this Project.');
        setRows(values);
      } catch (e) { setError((e as Error).message); }
    }} /></label>
    {!!rows.length && <table><thead><tr><th>Product</th><th>State</th><th>From (inclusive)</th><th>Until (exclusive)</th><th>State applicability</th><th>Subject hash</th></tr></thead>
      <tbody>{rows.map(row => <tr key={row.subject_sha256}><td>{row.subject.policy_set.product}</td><td>{row.subject.policy_set.governing_state}</td><td>{row.subject.policy_set.effective_from}</td><td>{row.subject.policy_set.effective_until}</td><td>{row.subject.policy_set.state_applicability || 'Applicable sources supplied'}</td><td>{row.subject_sha256}</td></tr>)}</tbody></table>}
    <button disabled={busy || unknown || !rows.length} onClick={async () => {
      operation(true); setError('');
      try {
        for (const row of rows) {
          const result = await mutate(endpoint + '/subjects', row.subject);
          if (!result?.id || result.sha256 !== row.subject_sha256 || result.status !== 'staged_not_approved') {
            setUnknown(true); throw new Error('Staging receipt does not match the exact subject; reconcile before continuing.');
          }
          sessionStorage.removeItem(journal);
        }
        await refresh(); setNotice(`Staged ${rows.length} exact subjects. No policy approval was granted.`);
      } catch (e) { setError((e as Error).message); }
      finally { operation(false); }
    }}>Stage policy subjects for review</button>
    <button disabled={busy} onClick={async () => { operation(true); setError(''); try { await refresh(); } catch(e) { setError((e as Error).message); } finally { operation(false); } }}>Reload staged subjects and decisions</button>
    <label>Project-wide staged subjects (only this group's exact task revisions can be reviewed here) <select value={selected} disabled={busy} onChange={async event => {
      const id = event.target.value; setSelected(id); setDetail(null); setReviewed(false); setError('');
      setRationale(''); setEvidence(''); setEvidenceHash(''); setExpiry('');
      if (!id) return;
      operation(true);
      try {
        const value = await api(endpoint + '/subjects/' + encodeURIComponent(id));
        const expected = staged.find(row => row.id === id);
        if (!expected || value.id !== id || value.sha256 !== expected.content_sha256) throw new Error('Staged subject identity changed.');
        if (!policyReviewMatches(tasks, value.subject))
          throw new Error('This subject belongs to another task group. Open its own Project bindings to review it.');
        setDetail(value);
      } catch(e) { setError((e as Error).message); } finally { operation(false); }
    }}><option value="">Choose a staged subject</option>{staged.map(row => <option key={row.id} value={row.id}>{row.id} · {row.content_sha256.slice(0,12)}</option>)}</select></label>
    {detail && <><pre>{JSON.stringify(detail, null, 2)}</pre>
      <label><input type="checkbox" checked={reviewed} disabled={busy || unknown} onChange={e => setReviewed(e.target.checked)} />I reviewed this exact subject and its source evidence.</label>
      <label>Decision rationale <textarea value={rationale} onChange={e => setRationale(e.target.value)} disabled={busy || unknown} /></label>
      <label>Reviewed evidence reference <input value={evidence} onChange={e => setEvidence(e.target.value)} disabled={busy || unknown} /></label>
      <label>Reviewed evidence SHA-256 <input value={evidenceHash} onChange={e => setEvidenceHash(e.target.value)} disabled={busy || unknown} /></label>
      <label>Review expiry <input type="datetime-local" value={expiry} onChange={e => setExpiry(e.target.value)} disabled={busy || unknown} /></label>
      {(['approved','rejected'] as const).map(decision => <button key={decision} disabled={busy || unknown || !reviewed || rationale.trim().length < 10 || !evidence.trim() || !/^[a-f0-9]{64}$/.test(evidenceHash) || !expiry} onClick={async () => {
        operation(true); setError('');
        try {
          const result = await mutate(endpoint + '/subjects/' + encodeURIComponent(detail.id) + '/decisions', { subject_sha256: detail.sha256, decision, rationale: rationale.trim(), evidence_reference: evidence.trim(), evidence_sha256: evidenceHash, expires_at: new Date(expiry).toISOString() });
          if (!result || result.decision !== decision || !result.id) { setUnknown(true); throw new Error('Decision receipt is incomplete; reconcile before another submission.'); }
          sessionStorage.removeItem(journal); setReviewed(false); await refresh(); setNotice('The server recorded the scoped decision. No model run was authorized.');
        } catch(e) { setError((e as Error).message); } finally { operation(false); }
      }}>{decision === 'approved' ? 'Record Product Owner approval' : 'Record rejection'}</button>)}</>}
    {reviews !== null && <details><summary>Recorded decisions</summary><pre>{JSON.stringify(reviews, null, 2)}</pre></details>}
  </details>;
}
