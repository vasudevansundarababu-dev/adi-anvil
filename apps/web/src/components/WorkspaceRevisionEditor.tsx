'use client';
import { useEffect, useState } from 'react';
import Form from './Form';
import { dateTime, shortId, workspaceApi as api } from '../lib/workspace';
import styles from './ModernWorkspace.module.css';

type Fields = {
  title: string;
  capabilities?: string[];
  rubric_revision_id?: string;
  threshold?: number;
  criteria?: { id: string; label: string; weight_bps: number }[];
  comparison_policy?: string;
  pass_policy?: string;
  max_output_tokens?: number;
  episode_timeout_seconds?: number;
};
type Model = {
  revision_id: string;
  resource_id: string;
  kind: string;
  revision: number;
  content_hash: string;
  current_revision_id: string;
  row_version: number;
  lifecycle: string;
  can_save: boolean;
  blocked_reason: string | null;
  content: Fields;
  limitations: string;
  rubric_options: { id: string; title: string; revision: number; lifecycle: string }[];
};
type Version = { id: string; revision: number; content_hash: string; created_at: string };
export default function WorkspaceRevisionEditor({
  base,
  revisionId,
  href,
  returnHref,
  onSaved,
}: {
  base: string;
  revisionId: string;
  href: (id: string) => string;
  returnHref: string;
  onSaved: (id: string) => void;
}) {
  const [model, setModel] = useState<Model | null>(null),
    [draft, setDraft] = useState<Fields | null>(null),
    [versions, setVersions] = useState<Version[]>([]),
    [cursor, setCursor] = useState<number | null>(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [saved, setSaved] = useState('');
  const [capabilitiesText, setCapabilitiesText] = useState('');
  useEffect(() => {
    let active = true;
    setError('');
    setModel(null);
    api(base + '/workspace/revisions/' + revisionId + '/editor')
      .then(async (m) => {
        if (!active) return;
        setModel(m);
        setDraft(m.content);
        setCapabilitiesText((m.content.capabilities || []).join(', '));
        const h = await api(base + '/workspace/resources/' + m.resource_id + '/versions');
        if (active) {
          setVersions(h.items);
          setCursor(h.next_cursor);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [base, revisionId]);
  const change = <K extends keyof Fields>(key: K, value: Fields[K]) =>
    setDraft((current) => (current ? { ...current, [key]: value } : current));
  if (!model || !draft)
    return (
      <section className={styles.panel}>
        <a href={returnHref}>← Return to run snapshot</a>
        {error ? <p role="alert">{error}</p> : <p role="status">Loading the exact revision…</p>}
      </section>
    );
  const dirty = JSON.stringify(model.content) !== JSON.stringify(draft);
  return (
    <>
      <div className={styles.pageHead}>
        <div>
          <a href={returnHref}>← Return to run snapshot</a>
          <h2>
            {model.kind === 'protocol' ? 'Evaluation protocol' : model.kind} · version{' '}
            {model.revision}
          </h2>
          <span className={styles.tag}>{model.lifecycle}</span>
        </div>
        <a href={href(model.current_revision_id)}>Open current version</a>
      </div>
      {error && <p role="alert">{error}</p>}
      {saved && <p role="status">{saved}</p>}
      <p className={styles.notice}>{model.limitations}</p>
      {model.blocked_reason && <p role="status">{model.blocked_reason}</p>}
      <div className={styles.grid}>
        <section className={styles.panel}>
          <Form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError('');
              try {
                const updated = await api(
                  base + '/workspace/revisions/' + model.revision_id + '/successor',
                  'POST',
                  draft,
                  model.row_version,
                );
                setModel(updated);
                setDraft(updated.content);
                setSaved(
                  'Draft version ' +
                    updated.revision +
                    ' saved. Prior run snapshots and approvals remain attached to their original versions.',
                );
                onSaved(updated.revision_id);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <fieldset
              disabled={!model.can_save || busy}
              style={{ border: 0, padding: 0, margin: 0 }}
            >
              <label>
                Title
                <input
                  required
                  minLength={3}
                  maxLength={200}
                  value={draft.title}
                  onChange={(e) => change('title', e.target.value)}
                />
              </label>
              {model.kind === 'task' && (
                <>
                  <label>
                    Capabilities (comma separated)
                    <input
                      required
                      value={capabilitiesText}
                      onChange={(e) => {
                        setCapabilitiesText(e.target.value);
                        change(
                          'capabilities',
                          e.target.value
                            .split(',')
                            .map((v) => v.trim())
                            .filter(Boolean),
                        );
                      }}
                    />
                  </label>
                  <label>
                    Rubric version
                    <select
                      value={draft.rubric_revision_id}
                      onChange={(e) => change('rubric_revision_id', e.target.value)}
                    >
                      {model.rubric_options.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.title} · version {r.revision} · {r.lifecycle}
                        </option>
                      ))}
                    </select>
                  </label>
                  <small>
                    Use an exact project rubric revision. Qualification still requires its reviewed
                    version.
                  </small>
                </>
              )}
              {model.kind === 'rubric' && (
                <>
                  <label>
                    Pass threshold (0–100)
                    <input
                      required
                      type="number"
                      min={0}
                      max={100}
                      step="0.01"
                      value={draft.threshold}
                      onChange={(e) => change('threshold', Number(e.target.value))}
                    />
                  </label>
                  <h3>Criteria</h3>
                  {draft.criteria?.map((criterion, i) => (
                    <div key={criterion.id} className={styles.diagnostic}>
                      <small>{criterion.id} · existing private anchors preserved</small>
                      <label>
                        Criterion label
                        <input
                          required
                          maxLength={200}
                          value={criterion.label}
                          onChange={(e) =>
                            change(
                              'criteria',
                              draft.criteria!.map((c, n) =>
                                n === i ? { ...c, label: e.target.value } : c,
                              ),
                            )
                          }
                        />
                      </label>
                      <label>
                        Weight (%)
                        <input
                          required
                          type="number"
                          min={0.01}
                          max={100}
                          step="0.01"
                          value={criterion.weight_bps / 100}
                          onChange={(e) =>
                            change(
                              'criteria',
                              draft.criteria!.map((c, n) =>
                                n === i
                                  ? { ...c, weight_bps: Math.round(Number(e.target.value) * 100) }
                                  : c,
                              ),
                            )
                          }
                        />
                      </label>
                    </div>
                  ))}
                  <p>
                    Weight total:{' '}
                    {(draft.criteria || []).reduce((sum, c) => sum + c.weight_bps, 0) / 100}% · must
                    equal100%
                  </p>
                  <small>
                    Calibration is not revalidated by saving. Fresh scientific review remains
                    required.
                  </small>
                </>
              )}
              {model.kind === 'protocol' && (
                <>
                  <label>
                    Comparison policy
                    <textarea
                      required
                      minLength={20}
                      maxLength={5000}
                      value={draft.comparison_policy}
                      onChange={(e) => change('comparison_policy', e.target.value)}
                    />
                  </label>
                  <label>
                    Pass policy
                    <textarea
                      required
                      minLength={10}
                      maxLength={5000}
                      value={draft.pass_policy}
                      onChange={(e) => change('pass_policy', e.target.value)}
                    />
                  </label>
                  <label>
                    Maximum output tokens
                    <input
                      required
                      type="number"
                      min={1}
                      max={8192}
                      value={draft.max_output_tokens}
                      onChange={(e) => change('max_output_tokens', Number(e.target.value))}
                    />
                  </label>
                  <label>
                    Episode timeout (seconds)
                    <input
                      required
                      type="number"
                      min={1}
                      max={600}
                      value={draft.episode_timeout_seconds}
                      onChange={(e) => change('episode_timeout_seconds', Number(e.target.value))}
                    />
                  </label>
                </>
              )}
              <div className={styles.actions}>
                <button className={styles.primary} disabled={!dirty || busy}>
                  {busy ? 'Saving…' : 'Save new draft version'}
                </button>
                <a href={returnHref}>Cancel</a>
              </div>
            </fieldset>
          </Form>
        </section>
        <section className={styles.panel}>
          <h2>Review changes</h2>
          <small>Before · version {model.revision}</small>
          <pre>{JSON.stringify(model.content, null, 2)}</pre>
          <small>After · proposed draft</small>
          <pre>{JSON.stringify(draft, null, 2)}</pre>
          <p className={styles.hash}>Base SHA-256: {model.content_hash}</p>
        </section>
      </div>
      <section className={styles.panel}>
        <h2>Version history</h2>
        <table>
          <thead>
            <tr>
              <th>Version</th>
              <th>Created</th>
              <th>Binding</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((v) => (
              <tr key={v.id}>
                <td>
                  <a href={href(v.id)}>Version {v.revision}</a>
                </td>
                <td>{dateTime(v.created_at)}</td>
                <td>
                  <code>{shortId(v.content_hash)}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {cursor && (
          <button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                const page = await api(
                  base + '/workspace/resources/' + model.resource_id + '/versions?after=' + cursor,
                );
                setVersions([...versions, ...page.items]);
                setCursor(page.next_cursor);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Load older versions
          </button>
        )}
      </section>
    </>
  );
}
