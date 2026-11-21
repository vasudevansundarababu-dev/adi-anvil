'use client';

import { useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';

export default function ReferenceStorageAccess({ base }: { base: string }) {
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [assignment, setAssignment] = useState<string | null>(null);
  const [expires, setExpires] = useState<string | null>(null);
  const path = `${base}/workspace/benchmark/reference-storage-access`;
  useEffect(() => {
    let active = true;
    api(path).then((result) => { if (active) {
      setAllowed(result.allowed);
      setAssignment(result.assignment_id);
      setExpires(result.expires_at);
    } })
      .catch((failure) => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [path]);
  async function change(revoke = false) {
    setBusy(true);
    setError('');
    try {
      await api(revoke ? `${path}/${assignment}/revoke` : path, 'POST',
        revoke ? {} : { confirmation: 'allow_my_protected_reference_import_for_8_hours' });
      const current = await api(path);
      setAllowed(current.allowed);
      setAssignment(current.assignment_id);
      setExpires(current.expires_at);
      setConsent(false);
    } catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  }
  return <section aria-label="Protected reference import access">
    <h3>Protected reference import access</h3>
    {error && <p role="alert">{error}</p>}
    {allowed === null ? <p>Checking your project access…</p> : allowed ? <>
      <p role="status">Your account can import protected references in this project.
        {expires ? ` Temporary access expires ${new Date(expires).toLocaleString()}.` : ''}</p>
      {assignment && <button disabled={busy} onClick={() => void change(true)}>End temporary import access</button>}
    </> : <>
      <p>A recorded source-review assignment protects task references and rubrics during import.
        This grants your current Admin account access to source and evaluation references in this project for eight hours.
        Hidden judge assets, policy and rights approvals, and model calls remain separately controlled.</p>
      <label><input type="checkbox" checked={consent} disabled={busy}
        onChange={(event) => setConsent(event.target.checked)} />
        I authorize temporary protected-reference import access for my account in this project.</label>
      <button disabled={!consent || busy} onClick={() => void change()}>Allow my import access for 8 hours</button>
    </>}
  </section>;
}
