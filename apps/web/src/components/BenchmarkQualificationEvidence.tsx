'use client';

import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { benchmarkGet } from '../lib/benchmark';
import styles from './BenchmarkResults.module.css';

export type QualificationEvidence = {
  operation_id: string;
  build_id: string;
  state: string;
  scope: 'qualification_evidence';
  model_performance: false;
  comparison_admitted: false;
  primary: null;
  qualifications: {
    qualification_id: string;
    task_id: string;
    outcome: string;
    report_sha256: string;
    subject_sha256: string;
    binding_sha256: string;
    trials: {
      mode: string;
      points: number;
      possible_points: number;
      seal_sha256: string | null;
      native_receipt_sha256: string | null;
      provider_calls: number;
      source_hashes: Record<string, string>;
      controls: Record<string, boolean> | null;
      public_capture: null | {
        outputs: {
          path: string;
          sha256: string;
          byte_size: number;
          text: string | null;
        }[];
        missing: string[];
        criteria: {
          criterion_id: string;
          earned_points: string;
          possible_points: string;
        }[];
      };
    }[];
  }[];
};

export function QualificationEvidenceReport({ evidence }: { evidence: QualificationEvidence }) {
  return (
    <>
      <div className={styles.origin}>
        <strong>Individual software qualification</strong>
        <span>
          Fictional control trials · No comparison admission · No official primary · Not live model
          performance
        </span>
      </div>
      <div className={styles.summary}>
        <article>
          <span>Operation state</span>
          <strong>{evidence.state.replaceAll('_', ' ')}</strong>
        </article>
        <article>
          <span>Stored task receipts</span>
          <strong>{evidence.qualifications.length}</strong>
        </article>
        <article>
          <span>Official primary</span>
          <strong>Unavailable</strong>
        </article>
        <article>
          <span>Comparison admission</span>
          <strong>Not granted</strong>
        </article>
      </div>
      <div className={styles.sectionTitle}>
        <div>
          <h3>Actual qualification trials</h3>
          <p>
            Control-trial points test the software evaluator. They do not measure a candidate model
            or replace human reviews.
          </p>
        </div>
      </div>
      <div className={styles.cellList}>
        {evidence.qualifications.map((qualification) => (
          <details className={styles.cell} key={qualification.qualification_id}>
            <summary>
              <span>{qualification.task_id}</span>
              <span>{qualification.outcome}</span>
              <span>{qualification.trials.length} retained trials</span>
              <span>Qualification receipt</span>
            </summary>
            <div className={styles.cellBody}>
              <p>
                Qualification: <code>{qualification.qualification_id}</code>
              </p>
              {qualification.trials.map((trial, index) => (
                <details key={trial.mode + index} className={styles.detail}>
                  <summary>
                    {trial.mode} · control result {trial.points} / {trial.possible_points}
                  </summary>
                  <p>Recorded provider calls: {trial.provider_calls}</p>
                  {trial.public_capture ? (
                    <>
                      {trial.public_capture.missing.length > 0 && (
                        <p>Declared outputs absent: {trial.public_capture.missing.join(', ')}</p>
                      )}
                      {trial.public_capture.outputs.map((output) => (
                        <details key={output.path + output.sha256}>
                          <summary>
                            {output.path} · {output.byte_size} captured bytes
                          </summary>
                          <p className={styles.identifier}>SHA-256: {output.sha256}</p>
                          {output.text === null ? (
                            <p>Text preview unavailable. The captured file digest is retained.</p>
                          ) : (
                            <pre>{output.text}</pre>
                          )}
                        </details>
                      ))}
                      {trial.public_capture.criteria.length > 0 && (
                        <table>
                          <caption>Public criterion observations from this control trial</caption>
                          <thead>
                            <tr>
                              <th>Criterion</th>
                              <th>Earned</th>
                              <th>Possible</th>
                            </tr>
                          </thead>
                          <tbody>
                            {trial.public_capture.criteria.map((criterion) => (
                              <tr key={criterion.criterion_id}>
                                <td>{criterion.criterion_id}</td>
                                <td>{criterion.earned_points}</td>
                                <td>{criterion.possible_points}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </>
                  ) : (
                    <p>
                      No public output capture was persisted with this historical receipt. Missing
                      evidence is not reconstructed.
                    </p>
                  )}
                  <details>
                    <summary>Native receipt and isolation controls</summary>
                    <p className={styles.identifier}>
                      Native receipt SHA-256: {trial.native_receipt_sha256 || 'Not retained'}
                    </p>
                    <p className={styles.identifier}>
                      Output seal SHA-256: {trial.seal_sha256 || 'Not retained'}
                    </p>
                    {trial.controls && Object.keys(trial.controls).length ? (
                      <pre>{JSON.stringify(trial.controls, null, 2)}</pre>
                    ) : (
                      <p>Isolation control observations were not retained for this receipt.</p>
                    )}
                    <h4>Source digests</h4>
                    <pre>{JSON.stringify(trial.source_hashes, null, 2)}</pre>
                  </details>
                </details>
              ))}
              <details className={styles.detail}>
                <summary>Exact task receipt binding</summary>
                <dl className={styles.provenance}>
                  <div>
                    <dt>Report SHA-256</dt>
                    <dd>{qualification.report_sha256}</dd>
                  </div>
                  <div>
                    <dt>Subject SHA-256</dt>
                    <dd>{qualification.subject_sha256}</dd>
                  </div>
                  <div>
                    <dt>Binding SHA-256</dt>
                    <dd>{qualification.binding_sha256}</dd>
                  </div>
                </dl>
              </details>
            </div>
          </details>
        ))}
        {!evidence.qualifications.length && (
          <p className={styles.cellBody}>
            No completed qualification receipts are stored for this operation.
          </p>
        )}
      </div>
      <footer className={styles.footer}>
        <p className={styles.identifier}>
          Operation: {evidence.operation_id}
          <br />
          Build: {evidence.build_id}
        </p>
      </footer>
    </>
  );
}

export default function BenchmarkQualificationEvidence({
  base,
  operationId,
  select,
}: {
  base: string;
  operationId: string | null;
  select: (id: string) => void;
}) {
  const [identifier, setIdentifier] = useState(operationId || '');
  const [evidence, setEvidence] = useState<QualificationEvidence | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const generation = useRef(0);
  const refresh = useCallback(async () => {
    if (!operationId) return;
    const request = ++generation.current;
    setBusy(true);
    setError('');
    setEvidence(null);
    try {
      const value = await benchmarkGet<QualificationEvidence>(
        base,
        '/qualification-operations/' + encodeURIComponent(operationId) + '/evidence',
      );
      if (
        value.operation_id !== operationId ||
        value.scope !== 'qualification_evidence' ||
        value.model_performance !== false ||
        value.comparison_admitted !== false ||
        value.primary !== null
      )
        throw new Error('Unexpected qualification evidence binding');
      if (request === generation.current) setEvidence(value);
    } catch (failure) {
      if (request === generation.current) setError((failure as Error).message);
    } finally {
      if (request === generation.current) setBusy(false);
    }
  }, [base, operationId]);
  useEffect(() => {
    setIdentifier(operationId || '');
    void refresh();
    return () => {
      generation.current++;
    };
  }, [operationId, refresh]);
  function open(event: FormEvent) {
    event.preventDefault();
    if (identifier === operationId) void refresh();
    else select(identifier);
  }
  return (
    <section className={styles.results} aria-label="Individual qualification evidence">
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>BENCHMARK / INDIVIDUAL EXECUTION EVIDENCE</p>
          <h2>Qualification evidence</h2>
          <p>
            Inspect an actual stored operation without admitting a comparison or approving results.
          </p>
        </div>
        {operationId && (
          <button type="button" disabled={busy} onClick={() => void refresh()}>
            {busy ? 'Loading evidence…' : 'Refresh qualification evidence'}
          </button>
        )}
      </header>
      <form className={styles.evidenceLookup} onSubmit={open}>
        <label>
          Stored qualification operation reference
          <input
            required
            pattern="[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"
            value={identifier}
            onChange={(event) => setIdentifier(event.target.value)}
            placeholder="Operation UUID"
          />
        </label>
        <button disabled={busy}>Open stored evidence</button>
      </form>
      {error && (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      )}
      {busy && (
        <p role="status" className={styles.cellBody}>
          Reading authorized persisted qualification evidence…
        </p>
      )}
      {evidence ? (
        <QualificationEvidenceReport evidence={evidence} />
      ) : (
        !busy &&
        !error && (
          <div className={styles.empty}>
            <h3>No individual execution evidence selected</h3>
            <p>
              Open an existing operation reference or request qualification through the
              reviewed-source workflow. Missing source rights, evaluator reviews or runtime
              prerequisites remain blocking requirements.
            </p>
            <p>
              A complete comparison additionally requires three distinct assigned reviewers before
              admission. This evidence view does not assign or approve anyone.
            </p>
          </div>
        )
      )}
    </section>
  );
}
