'use client';

import { useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';

const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
export default function KycInputSetup({ base, endpoint, bindingId, blocked, onBusyChange }: {
  base: string; endpoint: string; bindingId?: string; blocked: boolean;
  onBusyChange: (busy: boolean) => void;
}) {
  const [resolution, setResolution] = useState('');
  const [caseImport, setCaseImport] = useState('');
  const [error, setError] = useState('');
  const [unknown, setUnknown] = useState(false);
  const [busy, setBusy] = useState(false);
  const [receipt, setReceipt] = useState<{ id: string; content_sha256: string; input_count: number; project_binding_id: string } | null>(null);
  const [prepared, setPrepared] = useState<unknown>(null);
  const [turns, setTurns] = useState(3);
  const [reconciled, setReconciled] = useState(false);
  const journal = 'forge.native-input-setup:' + endpoint;
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(journal);
      if (raw) {
        const saved = JSON.parse(raw);
        setUnknown(true); // A retained attempt requires server readback, never a fresh submission.
        setResolution(saved.resolution || ''); setCaseImport(saved.caseImport || '');
      }
    } catch { setUnknown(true); }
    setReconciled(true);
  }, [journal]);
  async function submit(prepare: boolean) {
    if (!reconciled || unknown || blocked || busy || !bindingId || !uuid.test(resolution) || !uuid.test(caseImport)) return;
    setBusy(true); onBusyChange(true); setError('');
    try {
      const key = crypto.randomUUID();
      sessionStorage.setItem(journal, JSON.stringify({ resolution, caseImport, bindingId, prepare, key,
        turns, resolved_input: receipt, status: 'pending_requires_reconciliation' }));
      if (prepare && receipt) {
        const result = await api(endpoint + '/native-packages', 'POST', {
          max_model_calls: turns, resolved_input: { id: receipt.id, sha256: receipt.content_sha256 },
        }, undefined, key);
        if (!result || !Array.isArray(result.packages) || !result.packages.length ||
            !Array.isArray(result.restored_workflow_refs) || !Array.isArray(result.restored_data_refs) ||
            !Array.isArray(result.restored_rubric_refs) || result.run_authority !== 'not_granted' || result.model_calls !== 0)
          throw new Error('Package preparation receipt was incomplete; reconcile before another submission.');
        setPrepared(result);
      } else {
        const result = await api(base + '/golden-banking/v1/anvil/application-inputs', 'POST', {
          resolution_id: resolution, case_import_id: caseImport, preparation_binding_id: bindingId,
        }, undefined, key);
        if (!result || !uuid.test(result.id) || !/^[a-f0-9]{64}$/.test(result.content_sha256) || result.project_binding_id !== bindingId)
          throw new Error('Input binding receipt was incomplete; reconcile before another submission.');
        setReceipt(result);
      }
      sessionStorage.removeItem(journal);
    } catch (e) {
      const failure = e as Error & { status?: number };
      setError(failure.message);
      if (!failure.status || failure.status >= 500) setUnknown(true);
      else sessionStorage.removeItem(journal);
    } finally {
      setBusy(false); onBusyChange(false);
    }
  }
  return <details>
    <summary>Native KYC input setup</summary>
    <p>Save the Project input selection first. Link its exact imported tasks and registered case pack here. This does not approve policy, rights or expectations and starts no model call.</p>
    <p>Saved preparation binding: {bindingId || 'Save required'}</p>
    <label>Source resolution ID <input value={resolution} disabled={busy || !!receipt || unknown} onChange={e => setResolution(e.target.value.trim())} /></label>
    <label>Registered case import ID <input value={caseImport} disabled={busy || !!receipt || unknown} onChange={e => setCaseImport(e.target.value.trim())} /></label>
    <button disabled={!reconciled || blocked || busy || unknown || !!receipt || !bindingId || !uuid.test(resolution) || !uuid.test(caseImport)} onClick={() => void submit(false)}>Bind tasks to registered inputs</button>
    {error && <p role="alert">{error}</p>}
    {unknown && <p role="alert">The operation outcome is unconfirmed. Reconcile the saved server records before another submission.</p>}
    {receipt && <><p>Stored {receipt.input_count} task/input assignments. Reviews and qualification remain separate.</p><pre>{JSON.stringify(receipt, null, 2)}</pre>
      <label>Package limit: model turns per case <input type="number" min={1} max={100} value={turns} disabled={busy || unknown || !!prepared} onChange={e => setTurns(Number(e.target.value))} /></label>
      <button disabled={receipt.project_binding_id !== bindingId || blocked || busy || unknown || !!prepared || !Number.isInteger(turns) || turns < 1 || turns > 100} onClick={() => void submit(true)}>Prepare native package bindings</button>
      <p>This limit applies only to a separately authorized future run. Preparing packages makes no model calls.</p></>}
    {!!prepared && <pre>{JSON.stringify(prepared, null, 2)}</pre>}
  </details>;
}
