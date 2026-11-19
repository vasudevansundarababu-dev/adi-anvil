'use client';
import { useEffect, useRef, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';

type Template = { id: string; template_id: string; version: number; spec_sha256: string };
type Publication = {
  id: string;
  sha256: string;
  raw_record_sha256: string;
  record: {
    status?: string;
    publication_status?: string;
    template_id: string;
    version: number;
    published_at: string;
    template_sha256: string;
    part_hashes: Record<string, string>;
  };
  created_by: string;
  created_at: string;
  revoked: boolean;
  attestation: null | {
    id: string;
    sha256: string;
    expires_at: string;
    self_approved: boolean;
    attested_by: string;
    current: boolean;
  };
};

export default function OfflineTemplatePublication({
  base,
  templates,
}: {
  base: string;
  templates: Template[];
}) {
  const [templateId, setTemplateId] = useState('');
  const [subjects, setSubjects] = useState<Publication[]>([]);
  const [subjectId, setSubjectId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [reviewed, setReviewed] = useState(false);
  const [rationale, setRationale] = useState('');
  const [expires, setExpires] = useState('');
  const [reason, setReason] = useState('');
  const generation = useRef(0);
  const template = templates.find((row) => row.id === templateId);
  const subject = subjects.find((row) => row.id === subjectId);
  const endpoint =
    base + '/dataset-exports/generic/templates/' + templateId + '/offline-publications';

  useEffect(() => {
    const current = ++generation.current;
    setSubjects([]);
    setSubjectId('');
    setFile(null);
    setReviewed(false);
    setRationale('');
    setExpires('');
    setReason('');
    setError('');
    setMessage('');
    if (templateId) {
      api(endpoint)
        .then((result) => {
          if (generation.current === current) setSubjects(result.subjects);
        })
        .catch((e) => {
          if (generation.current === current) setError((e as Error).message);
        });
    }
    return () => {
      generation.current++;
    };
  }, [endpoint, templateId]);
  useEffect(() => {
    setTemplateId('');
  }, [base]);

  async function act(operation: () => Promise<void>) {
    if (busy) return;
    const current = generation.current;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await operation();
    } catch (e) {
      if (generation.current === current) setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function reload(selected?: string) {
    const current = generation.current;
    const result = await api(endpoint);
    if (current === generation.current) {
      setSubjects(result.subjects);
      if (selected) setSubjectId(selected);
      setReviewed(false);
    }
  }

  return (
    <section aria-label="Offline publication review">
      <h3>Offline publication review</h3>
      <p>
        Stage the final published record from your offline export, then review it and explicitly
        attest as Product Owner. A local attestation records your decision; it is not verification
        through the Authoring API.
      </p>
      <label>
        Offline publication template
        <select
          aria-label="Offline publication template"
          value={templateId}
          disabled={busy}
          onChange={(event) => setTemplateId(event.target.value)}
        >
          <option value="">Choose registered template version</option>
          {templates.map((row) => (
            <option key={row.id} value={row.id}>
              {row.template_id} · v{row.version} · {row.spec_sha256}
            </option>
          ))}
        </select>
      </label>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {template && (
        <>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (!file || busy) return;
              void act(async () => {
                if (file.size > 131072)
                  throw new Error('Publication record must be at most 128 KiB.');
                const raw = await file.text();
                if (new TextEncoder().encode(raw).length > 131072)
                  throw new Error('Publication record must be at most 128 KiB.');
                const record = JSON.parse(raw);
                if (
                  !record ||
                  typeof record !== 'object' ||
                  Array.isArray(record) ||
                  (!('status' in record) && !('publication_status' in record)) ||
                  ('status' in record && record.status !== 'published') ||
                  ('publication_status' in record && record.publication_status !== 'published') ||
                  typeof record.published_at !== 'string' ||
                  !/(Z|[+-]\d{2}:\d{2})$/.test(record.published_at) ||
                  !Number.isFinite(Date.parse(record.published_at)) ||
                  Date.parse(record.published_at) > Date.now()
                )
                  throw new Error(
                    'Choose a published record with its dated publication. Candidate and unpublished records cannot be attested.',
                  );
                if (
                  record.template_id !== template.template_id ||
                  record.version !== template.version
                )
                  throw new Error(
                    'The publication record must match the selected external template ID and version.',
                  );
                if (record.template_sha256 !== template.spec_sha256)
                  throw new Error(
                    'The publication record must match the selected exact template SHA-256.',
                  );
                if (
                  !record.part_hashes ||
                  ['authoring', 'execution', 'skills'].some(
                    (key) => !/^[a-f0-9]{64}$/.test(record.part_hashes[key] || ''),
                  )
                )
                  throw new Error(
                    'The publication record must include exact authoring, execution and skills SHA-256 hashes.',
                  );
                const staged = await api(endpoint, 'POST', { record_utf8: raw });
                await reload(staged.id || staged.subject_id);
                setMessage('Publication record staged for review. No approval was granted.');
              });
            }}
          >
            <label>
              Published offline publication record JSON
              <input
                type="file"
                accept="application/json,.json"
                disabled={busy}
                onChange={(event) => {
                  setFile(event.target.files?.[0] || null);
                  setReviewed(false);
                  setError('');
                }}
              />
            </label>
            <button disabled={busy || !file}>Stage publication record for review</button>
          </form>
          <label>
            Staged publication record
            <select
              aria-label="Staged publication record"
              disabled={busy}
              value={subjectId}
              onChange={(event) => {
                setSubjectId(event.target.value);
                setReviewed(false);
                setRationale('');
                setReason('');
              }}
            >
              <option value="">Choose a staged record to review</option>
              {subjects.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.record.published_at} · {row.sha256} ·{' '}
                  {row.revoked
                    ? 'Revoked'
                    : row.attestation?.current
                      ? 'Locally attested'
                      : 'Awaiting current attestation'}
                </option>
              ))}
            </select>
          </label>
          {subject && (
            <div aria-label="Publication record evidence">
              <dl>
                <dt>Publication status</dt>
                <dd>{subject.record.publication_status || subject.record.status}</dd>
                <dt>External template ID and version</dt>
                <dd>
                  {subject.record.template_id} · v{subject.record.version}
                </dd>
                <dt>Published at</dt>
                <dd>{subject.record.published_at}</dd>
                <dt>Original record SHA-256</dt>
                <dd>
                  <code>{subject.raw_record_sha256}</code>
                </dd>
                <dt>Review subject SHA-256</dt>
                <dd>
                  <code>{subject.sha256}</code>
                </dd>
                <dt>Template SHA-256</dt>
                <dd>
                  <code>{subject.record.template_sha256}</code>
                </dd>
                {['authoring', 'execution', 'skills'].map((part) => (
                  <div key={part}>
                    <dt>{part} SHA-256</dt>
                    <dd>
                      <code>{subject.record.part_hashes[part]}</code>
                    </dd>
                  </div>
                ))}
                <dt>Staged by</dt>
                <dd>
                  {subject.created_by} · {subject.created_at}
                </dd>
                <dt>Record state</dt>
                <dd>{subject.revoked ? 'Revoked' : 'Available for review'}</dd>
              </dl>
              {subject.attestation && (
                <p>
                  Local PO attestation:{' '}
                  {subject.attestation.current ? 'current' : 'expired or no longer current'}.
                  Expires {subject.attestation.expires_at}. Attested by{' '}
                  {subject.attestation.attested_by}. Self-approved:{' '}
                  {subject.attestation.self_approved ? 'yes' : 'no'}. Attestation SHA-256:{' '}
                  <code>{subject.attestation.sha256}</code>.
                </p>
              )}
              <p>
                Authoring API verification: no. Runtime qualification and model-call authority are
                separate checks.
              </p>
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!reviewed || busy || subject.revoked) return;
                  void act(async () => {
                    const expiry = new Date(expires);
                    if (!Number.isFinite(expiry.getTime()) || expiry.getTime() <= Date.now())
                      throw new Error('Choose a future attestation expiry.');
                    await api(endpoint + '/' + subject.id + '/attest', 'POST', {
                      subject_sha256: subject.sha256,
                      rationale,
                      expires_at: expiry.toISOString(),
                    });
                    await reload(subject.id);
                    setMessage(
                      'Local Product Owner attestation recorded. Authoring API verification was not claimed.',
                    );
                  });
                }}
              >
                <label>
                  <input
                    type="checkbox"
                    checked={reviewed}
                    disabled={busy || subject.revoked}
                    onChange={(event) => setReviewed(event.target.checked)}
                  />
                  I reviewed this exact publication record and its hashes, and I attest as the
                  project Product Owner.
                </label>
                <label>
                  Publication attestation rationale
                  <textarea
                    minLength={10}
                    maxLength={2000}
                    value={rationale}
                    disabled={busy || subject.revoked}
                    onChange={(event) => setRationale(event.target.value)}
                  />
                </label>
                <label>
                  Publication attestation expiry (local time)
                  <input
                    type="datetime-local"
                    value={expires}
                    disabled={busy || subject.revoked}
                    onChange={(event) => setExpires(event.target.value)}
                  />
                </label>
                <button
                  className={styles.primary}
                  disabled={
                    busy || subject.revoked || !reviewed || rationale.trim().length < 10 || !expires
                  }
                >
                  Record local PO attestation
                </button>
              </form>
              {!subject.revoked && (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (busy || reason.trim().length < 10) return;
                    void act(async () => {
                      await api(endpoint + '/' + subject.id + '/revoke', 'POST', { reason });
                      await reload(subject.id);
                      setMessage(
                        'Publication record revoked. Its attestations can no longer be used.',
                      );
                    });
                  }}
                >
                  <label>
                    Publication revocation reason
                    <textarea
                      minLength={10}
                      maxLength={2000}
                      value={reason}
                      disabled={busy}
                      onChange={(event) => setReason(event.target.value)}
                    />
                  </label>
                  <button disabled={busy || reason.trim().length < 10}>
                    Revoke this publication record
                  </button>
                </form>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
