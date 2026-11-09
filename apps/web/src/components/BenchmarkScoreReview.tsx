'use client';

import { useState } from 'react';
import { BenchmarkComparison, benchmarkGet, benchmarkPost } from '../lib/benchmark';
import styles from './ModernWorkspace.module.css';

type StoredScore = {
  score_revision_id: string;
  revision: number;
  projection_sha256: string;
  review_state: string;
  reviews: number;
  projection: {
    review_requirements: {
      state?: string;
      reviewer_assignment_ids?: string[];
      first_assignment_id?: string;
      second_assignment_id?: string;
      adjudicator_assignment_id?: string;
    };
  };
};

export default function BenchmarkScoreReview({
  base,
  runId,
  canWrite,
  userId,
  comparison,
  canAdmin = false,
}: {
  base: string;
  runId: string;
  canWrite: boolean;
  userId: string;
  comparison: BenchmarkComparison;
  canAdmin?: boolean;
}) {
  const [stored, setStored] = useState<StoredScore | null>(null);
  const [assignment, setAssignment] = useState(''),
    [evidence, setEvidence] = useState('');
  const [rationale, setRationale] = useState(''),
    [decision, setDecision] = useState('approved');
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const [duties, setDuties] = useState<
    { assignment_id: string; user_id: string; user_name?: string }[]
  >([]);
  const [inspected, setInspected] = useState(false);
  const [correctCell, setCorrectCell] = useState(''),
    [criterion, setCriterion] = useState(''),
    [points, setPoints] = useState(''),
    [correctionEvidence, setCorrectionEvidence] = useState('');
  const refresh = async () => {
    setBusy(true);
    setError('');
    try {
      const [score, people] = await Promise.all([
        benchmarkGet<StoredScore>(base, '/comparisons/' + runId + '/results'),
        benchmarkGet<{ items: typeof duties }>(base, '/review-assignments'),
      ]);
      setStored(score);
      setDuties(people.items.filter((duty) => duty.user_id === userId));
      setInspected(false);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const policy = stored?.projection.review_requirements;
  const assigned = duties.filter((duty) =>
    (
      policy?.reviewer_assignment_ids || [
        policy?.first_assignment_id,
        policy?.second_assignment_id,
        policy?.adjudicator_assignment_id,
      ]
    ).includes(duty.assignment_id),
  );
  const locked = [
    'approved',
    'adjudicated',
    'reviewed',
    'admin_run_exempt',
    'admin_approved',
    'policy_no_review',
  ].includes(stored?.review_state || '');
  return (
    <section className={styles.panel} aria-label="Independent score review">
      <h2>Independent score review</h2>
      <p>
        Review an exact stored score revision. A different, currently assigned evaluator must submit
        the decision; this does not authorize a paid judge or certify model performance.
      </p>
      <button type="button" disabled={busy} onClick={() => void refresh()}>
        Load current score revision
      </button>
      {error && <p role="alert">{error}</p>}
      {stored && (
        <>
          <p role="status">
            Revision {stored.revision} · {stored.review_state} · {stored.reviews} recorded reviews
          </p>
          <details>
            <summary>Exact score binding</summary>
            <p>
              SHA-256: <code>{stored.projection_sha256}</code>
            </p>
          </details>
          {!assigned.length && (
            <p>You do not hold a current review duty assigned by this frozen protocol.</p>
          )}
          {locked && (
            <p>
              This report-authorized publication is immutable. Its actual authorization basis,
              predecessor and any recorded reviewer decisions are retained.
            </p>
          )}
          {!locked && (
            <>
              {canAdmin && (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    setBusy(true);
                    setError('');
                    void benchmarkPost(base, '/comparisons/' + runId + '/report-approval', {
                      expected_result_sha256: stored.projection_sha256,
                      rationale,
                    })
                      .then(() => refresh())
                      .catch((failure) => setError((failure as Error).message))
                      .finally(() => setBusy(false));
                  }}
                >
                  <label>
                    Admin report approval rationale
                    <textarea
                      required
                      minLength={10}
                      maxLength={2000}
                      value={rationale}
                      onChange={(event) => setRationale(event.target.value)}
                    />
                  </label>
                  <button disabled={busy}>Approve this exact report as Admin</button>
                  <p>This records an Admin authorization, not a fabricated independent review.</p>
                </form>
              )}
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  setBusy(true);
                  setError('');
                  void benchmarkPost<StoredScore>(base, '/comparisons/' + runId + '/reviews', {
                    score_revision_id: stored.score_revision_id,
                    expected_projection_sha256: stored.projection_sha256,
                    assignment_id: assignment,
                    decision,
                    evidence_sha256: evidence,
                    rationale,
                  })
                    .then((value) => {
                      setStored(value);
                      setInspected(false);
                    })
                    .catch((failure) => setError((failure as Error).message))
                    .finally(() => setBusy(false));
                }}
              >
                <label>
                  Your current evaluation-review assignment reference{' '}
                  <select
                    required
                    value={assignment}
                    onChange={(event) => setAssignment(event.target.value)}
                    disabled={busy || !canWrite || !assigned.length}
                  >
                    <option value="">Select your assigned review position</option>
                    {assigned.map((duty) => (
                      <option key={duty.assignment_id} value={duty.assignment_id}>
                        {duty.assignment_id === policy?.first_assignment_id
                          ? 'First review'
                          : duty.assignment_id === policy?.second_assignment_id
                            ? 'Second review'
                            : 'Independent adjudicator'}{' '}
                        · {duty.user_name || 'Current user'}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Review evidence SHA-256{' '}
                  <input
                    required
                    pattern="[a-f0-9]{64}"
                    value={evidence}
                    onChange={(event) => setEvidence(event.target.value)}
                    disabled={busy || !canWrite}
                  />
                  <button
                    type="button"
                    disabled={busy || !canWrite}
                    onClick={() => setEvidence(stored.projection_sha256)}
                  >
                    Use this exact score projection as review evidence
                  </button>
                </label>
                <label>
                  Decision{' '}
                  <select
                    value={decision}
                    onChange={(event) => setDecision(event.target.value)}
                    disabled={busy || !canWrite}
                  >
                    <option value="approved">Approve this revision</option>
                    <option value="disputed">Dispute</option>
                    <option value="changes_required">Request changes</option>
                    <option value="adjudicated">Adjudicate an existing dispute</option>
                  </select>
                </label>
                <label>
                  Evidence-based rationale{' '}
                  <textarea
                    required
                    minLength={10}
                    maxLength={2000}
                    value={rationale}
                    onChange={(event) => setRationale(event.target.value)}
                    disabled={busy || !canWrite}
                  />
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={inspected}
                    disabled={busy || !canWrite}
                    onChange={(event) => setInspected(event.target.checked)}
                  />
                  I inspected this revision and its authorized captured evidence.
                </label>
                <button
                  disabled={busy || !canWrite || !assigned.length || !inspected || !assignment}
                >
                  Record immutable review
                </button>
              </form>
              {assigned.some(
                (duty) => duty.assignment_id === policy?.adjudicator_assignment_id,
              ) && (
                <details>
                  <summary>Correct a disputed criterion in a successor revision</summary>
                  <p>
                    First and second review must record the dispute. Corrections preserve the
                    original native observations and require fresh review of the successor; no model
                    is rerun.
                  </p>
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      setBusy(true);
                      setError('');
                      void benchmarkPost<StoredScore>(
                        base,
                        '/comparisons/' + runId + '/corrections',
                        {
                          score_revision_id: stored.score_revision_id,
                          expected_projection_sha256: stored.projection_sha256,
                          assignment_id: policy?.adjudicator_assignment_id,
                          rationale,
                          corrections: [
                            {
                              cell_id: correctCell,
                              criterion_id: criterion,
                              earned_points: points,
                              evidence_sha256: correctionEvidence,
                            },
                          ],
                        },
                      )
                        .then((value) => {
                          setStored(value);
                          setInspected(false);
                        })
                        .catch((failure) => setError((failure as Error).message))
                        .finally(() => setBusy(false));
                    }}
                  >
                    <label>
                      Captured cell{' '}
                      <select
                        required
                        value={correctCell}
                        disabled={busy || !canWrite}
                        onChange={(event) => setCorrectCell(event.target.value)}
                      >
                        <option value="">Select a captured cell</option>
                        {comparison.cells
                          .filter((cell) => cell.state === 'completed' && cell.validity === 'valid')
                          .map((cell) => (
                            <option key={cell.cell_id} value={cell.cell_id}>
                              Slot {cell.slot + 1}, repetition {cell.repetition + 1} ·{' '}
                              {cell.cell_id}
                            </option>
                          ))}
                      </select>
                    </label>
                    <label>
                      Criterion reference{' '}
                      <input
                        required
                        value={criterion}
                        disabled={busy || !canWrite}
                        onChange={(event) => setCriterion(event.target.value)}
                      />
                    </label>
                    <label>
                      Corrected earned points{' '}
                      <input
                        required
                        inputMode="decimal"
                        pattern="(?:0|[1-9][0-9]{0,6})(?:\.[0-9]{1,8})?"
                        value={points}
                        disabled={busy || !canWrite}
                        onChange={(event) => setPoints(event.target.value)}
                      />
                    </label>
                    <label>
                      Captured output or native-report SHA-256{' '}
                      <input
                        required
                        pattern="[a-f0-9]{64}"
                        value={correctionEvidence}
                        disabled={busy || !canWrite}
                        onChange={(event) => setCorrectionEvidence(event.target.value)}
                      />
                    </label>
                    <label>
                      Correction rationale{' '}
                      <textarea
                        required
                        minLength={10}
                        maxLength={2000}
                        value={rationale}
                        disabled={busy || !canWrite}
                        onChange={(event) => setRationale(event.target.value)}
                      />
                    </label>
                    <button disabled={busy || !canWrite || !correctCell}>
                      Save immutable corrected successor
                    </button>
                  </form>
                </details>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
