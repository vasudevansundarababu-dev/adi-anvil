'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';

type Template = { id: string; template_id: string; version: number; spec_sha256: string };
type Receipt = {
  status: string;
  requirements: string[];
  publication_verified: boolean;
  conformance: { passed: boolean; origin: string; requirements?: string[] };
};

export default function TemplateSetup({ base }: { base: string }) {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const generation = useRef(0);
  const load = useCallback(async () => {
    const current = ++generation.current;
    try {
      const rows = await api(base + '/dataset-exports/generic/templates');
      if (current === generation.current) setTemplates(rows);
    } catch (e) {
      if (current === generation.current) setError((e as Error).message);
    }
  }, [base]);
  useEffect(() => {
    void load();
    return () => {
      generation.current++;
    };
  }, [load]);
  return (
    <section className={styles.panel} aria-label="Template setup">
      <h2>Template setup</h2>
      <p>
        Register an exact template specification before importing its tasks. Registration does not
        approve publication, qualify a runtime or authorize model calls.
      </p>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          if (!file || busy) return;
          setBusy(true);
          setError('');
          setMessage('');
          setReceipt(null);
          try {
            if (file.size > 1048576)
              throw new Error('Template specification must be at most 1 MiB.');
            const body = JSON.parse(await file.text());
            if (
              !body ||
              typeof body !== 'object' ||
              Array.isArray(body) ||
              !body.authoring ||
              !body.execution ||
              !body.skills
            )
              throw new Error('Choose the full template specification, not a publication record.');
          const row = await api(base + '/dataset-exports/generic/templates', 'POST', body);
            setMessage(
              'Registered template ' +
                row.template_id +
                ' · version ' +
                row.version +
                ' · SHA-256 ' +
                row.spec_sha256,
            );
            await load();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          Template specification JSON
          <input
            type="file"
            accept="application/json,.json"
            disabled={busy}
            onChange={(event) => {
              setFile(event.target.files?.[0] || null);
              setError('');
            }}
          />
        </label>
        <button className={styles.primary} disabled={busy || !file}>
          Register exact template
        </button>
      </form>
      <div className={styles.tableScroll}>
        <table aria-label="Registered template versions">
          <thead>
            <tr>
              <th>Template</th>
              <th>Version</th>
              <th>SHA-256</th>
              <th>Readiness</th>
            </tr>
          </thead>
          <tbody>
            {templates.map((item) => (
              <tr key={item.id}>
                <td>{item.template_id}</td>
                <td>{item.version}</td>
                <td>
                  <code>{item.spec_sha256}</code>
                </td>
                <td>
                  <button
                    disabled={busy}
                    onClick={async () => {
                      setBusy(true);
                      setError('');
                      setReceipt(null);
                      try {
                        const result = await api(
                          base + '/dataset-exports/generic/templates/' + item.id + '/qualify',
                          'POST',
                          {},
                        );
                        setReceipt(result.receipt);
                        setMessage(
                          'Template version ' +
                            item.version +
                            ' qualification: ' +
                            result.receipt.status +
                            '.',
                        );
                      } catch (e) {
                        setError((e as Error).message);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Check qualification v{item.version}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {receipt && (
        <div role="status">
          <h3>Qualification result: {receipt.status}</h3>
          <p>
            Publication verified: {receipt.publication_verified ? 'yes' : 'no'}. Runtime check:{' '}
            {receipt.conformance.origin}.
          </p>
          <ul>
            {[
              ...new Set([...receipt.requirements, ...(receipt.conformance.requirements || [])]),
            ].map((code) => (
              <li key={code}>{code}</li>
            ))}
          </ul>
          <p>This is a technical check only. It does not authorize a benchmark or model calls.</p>
        </div>
      )}
    </section>
  );
}
