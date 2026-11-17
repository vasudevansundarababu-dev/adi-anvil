'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import FrozenWorkflowEvidence, { WorkflowProvenance } from './FrozenWorkflowEvidence';
import ScoreCalculation from './ScoreCalculation';
import s from './ExpertReview.module.css';

type Measurement =
  | { kind: 'ratio'; numerator: number; denominator: number }
  | { kind: 'count'; value: number };
type Measurements = Record<string, Measurement>;
type JudgeDesign = {
  selection: 'fixed' | 'candidate';
  judge_model_binding_sha256: string;
  candidate_model_binding_sha256: string;
  same_model_as_candidate: boolean | null;
  model: { name?: string; provider?: string; model_id?: string };
  limitation: string;
};
type Assessment = {
  id: string;
  award: number | null;
  status: 'scored' | 'unscored' | 'not_applicable' | 'comment_only';
  rationale: string;
  evidence_ids: string[];
  reviewer: string;
  created_at: string;
  measurements?: Measurements | null;
};
type Diagnosis = {
  id: string;
  failure_mode: string;
  attribution: string;
  certainty: string;
  evaluator_finding: string;
  rationale: string;
  evidence_ids: string[];
  reviewer: string;
  created_at: string;
};
type Item = WorkflowProvenance & {
  id: string;
  case_id: string;
  model_key: string;
  repetition: number;
  role: string;
  step: string;
  skill_id: string;
  skill: string;
  skill_name?: string;
  capability_association?: string;
  design_step?: string;
  criterion_id: string | null;
  official?: boolean;
  weight?: number;
  scale: {
    kind?: string;
    levels: number[];
    maximum: number | null;
    unit: string;
    measures?: Record<string, { kind: 'ratio' | 'count'; denominator_source?: string }>;
  };
  automated: {
    award: number | null;
    reason: string;
    evaluator: string;
    judge_design?: JudgeDesign;
    calibration_sha256?: string;
    configuration_sha256?: string;
    measurements?: Measurements | null;
    comparison_contract?: { method: string } | null;
  };
  expected: string;
  observed: string;
  evidence: { id: string; title: string; excerpt: string; sha256: string | null }[];
  expert: Assessment | null;
  diagnosis: Diagnosis | null;
  history: { id: string; kind: string; reviewer: string; created_at: string; summary: string }[];
  evidence_contract?: {
    gates?: Record<string, unknown>;
    critical_failures?: unknown[];
    normalizer_scope?: string | null;
    reference_sha256?: string | null;
    reference_binding?: { sha256?: string | null } | null;
  };
  disputed?: boolean;
  expert_assessments?: (Assessment & { reviewer_id: string })[];
  correction_flags?: {
    id: string;
    owner: string;
    rationale: string;
    suggested_change: string;
    sent_to_praxis: boolean;
  }[];
};
type Review = {
  run_id: string;
  snapshot_sha256: string;
  review_revision: string;
  origin: string;
  permissions: { sme_review: boolean; rl_diagnosis: boolean };
  items: Item[];
  coverage: {
    eligible: number;
    assessed: number;
    comparable: number;
    comment_only: number;
    unscored: number;
    diagnostic_components?: {
      required: number;
      automated_measured: number;
      expert_measured: number;
      fully_measured_targets: number;
      fully_reviewed_targets: number;
      comparable_targets: number;
    };
  };
  full_expert_score: number | null;
  gates?: Record<string, unknown>;
  model_comparisons?: {
    model_key: string;
    matched_generated_score: number | null;
    matched_expert_score: number | null;
    full_expert_score: number | null;
    coverage: { eligible: number; comparable: number };
  }[];
};
const words = (value: string) => value.replaceAll('_', ' ');
const skillName = (item: Item) => item.skill_name || item.skill;
const isDigest = (value?: string) => /^[a-f0-9]{64}$/.test(value || '');
const hasMappingDigest = (item: Item) => isDigest(item.skill_mapping_sha256);
const hasEvaluatorIdentity = (item: Item) =>
  typeof item.automated.evaluator === 'string' && !!item.automated.evaluator.trim();
const comparisonKey = (item: Item) =>
  item.source?.task_id &&
  item.source.task_version &&
  isDigest(item.source.payload_sha256) &&
  hasMappingDigest(item) &&
  hasEvaluatorIdentity(item)
    ? JSON.stringify([
        item.source.task_id,
        item.source.task_version,
        item.source.payload_sha256,
        item.skill_mapping_sha256 || null,
        item.case_id,
        item.repetition,
        item.role,
        item.step,
        item.skill_id,
        item.criterion_id,
        item.official ?? null,
        item.weight ?? null,
        item.scale.kind || null,
        item.scale.levels,
        item.scale.maximum,
        item.scale.unit,
        item.scale.measures || null,
        item.evidence_contract?.normalizer_scope || null,
        item.automated.evaluator,
        item.evidence_contract?.reference_sha256 ?? null,
        item.evidence_contract?.reference_binding?.sha256 ?? null,
      ])
    : JSON.stringify(['unconfirmed_source_mapping_or_evaluator', item.id]);
function FrozenGates({
  gates,
  episodeCriticalFailures,
  label,
}: {
  gates?: Record<string, unknown>;
  episodeCriticalFailures?: unknown[];
  label: string;
}) {
  const entries =
    gates && typeof gates === 'object' && !Array.isArray(gates) ? Object.entries(gates) : [];
  const critical = Array.isArray(gates?.critical_failures) ? gates.critical_failures : null;
  return (
    <section aria-label={label}>
      <h4>{label}</h4>
      {critical && (
        <p style={{ color: critical.length ? '#b42318' : undefined }}>
          <strong>Critical failures recorded: {critical.length}</strong>
        </p>
      )}
      {Array.isArray(episodeCriticalFailures) && (
        <div>
          <p style={{ color: episodeCriticalFailures.length ? '#b42318' : undefined }}>
            <strong>Episode critical failures recorded: {episodeCriticalFailures.length}</strong>
          </p>
          {!!episodeCriticalFailures.length && (
            <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
              {JSON.stringify(episodeCriticalFailures, null, 2)}
            </pre>
          )}
          <p>
            This episode record does not replace the other decision, mandatory-condition or safety
            gates.
          </p>
        </div>
      )}
      {entries.length ? (
        <dl>
          {entries.map(([key, value]) => (
            <div key={key}>
              <dt>{words(key)}</dt>
              <dd>
                {value === null || value === undefined ? (
                  'Not recorded'
                ) : typeof value === 'object' ? (
                  <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
                    {JSON.stringify(value, null, 2)}
                  </pre>
                ) : (
                  String(value)
                )}
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p>Gate evidence is not recorded in this view. No pass is inferred.</p>
      )}
    </section>
  );
}
const diagnostic = (item: Item) =>
  item.official === false || item.scale.kind === 'diagnostic_measure';
const award = (value: number | null, item: Item, measures?: Measurements | null) => {
  if (diagnostic(item))
    return measures && Object.keys(measures).length
      ? Object.entries(measures)
          .map(
            ([name, measure]) =>
              words(name) +
              ': ' +
              (measure.kind === 'ratio'
                ? `${measure.numerator} / ${measure.denominator}`
                : measure.value),
          )
          .join(' · ')
      : 'Unscored';
  return value === null ? 'Unscored' : value + ' / ' + item.scale.maximum + ' ' + item.scale.unit;
};
const missingMeasures = (item: Item, measures?: Measurements | null) =>
  diagnostic(item)
    ? Object.keys(item.scale.measures || {})
        .filter((name) => !measures?.[name])
        .map(words)
    : [];
function MeasureCoverage({ item, measures }: { item: Item; measures?: Measurements | null }) {
  const missing = missingMeasures(item, measures);
  return missing.length ? (
    <small>Missing measures: {missing.join(', ')}. Partial diagnostic coverage.</small>
  ) : null;
}

export default function ExpertReview({
  base,
  runId,
  report,
}: {
  base: string;
  runId: string;
  report: 'Workflow Metrics' | 'Agent Performance' | 'Expert Review';
}) {
  const [review, setReview] = useState<Review | null>(null);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [sample, setSample] = useState('');
  const [snapshot, setSnapshot] = useState<{ id: string; content_sha256: string } | null>(null);
  const [snapshotBusy, setSnapshotBusy] = useState(false);
  const endpoint =
    base + '/workspace/benchmark/runs/' + encodeURIComponent(runId) + '/expert-review';
  const load = useCallback(async () => {
    setError('');
    try {
      setReview(await api(endpoint));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to read expert assessments.');
    }
  }, [endpoint]);
  useEffect(() => {
    let active = true;
    setReview(null);
    setSelected(null);
    setSnapshot(null);
    api(endpoint)
      .then((value) => {
        if (active) setReview(value);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [endpoint]);
  const item = review?.items.find((row) => row.id === selected);
  const judges = [
    ...new Map(
      (review?.items || []).flatMap((row) =>
        row.automated.judge_design
          ? [
              [
                JSON.stringify([
                  row.model_key,
                  row.automated.judge_design.selection,
                  row.automated.judge_design.judge_model_binding_sha256,
                ]),
                { candidate: row.model_key, design: row.automated.judge_design },
              ] as const,
            ]
          : [],
      ),
    ).values(),
  ];
  if (!review)
    return (
      <section className={s.root} aria-label={report}>
        <h2>{report}</h2>
        {error ? (
          <>
            <p role="alert">{error}</p>
            <button onClick={load}>Reload reviews</button>
          </>
        ) : (
          <p role="status">Loading recorded assessments…</p>
        )}
      </section>
    );
  return (
    <section className={s.root} aria-label={report}>
      <div className={s.heading}>
        <h2>{report}</h2>
        <span>{review.origin}</span>
      </div>
      <p>
        {review.coverage.assessed} of {review.coverage.eligible} eligible targets assessed by
        experts · {review.coverage.comparable} comparable pairs · {review.coverage.comment_only}{' '}
        comments only · {review.coverage.unscored} unscored
      </p>
      {review.coverage.diagnostic_components && (
        <p>
          Diagnostic evidence components: {review.coverage.diagnostic_components.automated_measured}{' '}
          / {review.coverage.diagnostic_components.required} measured by Forge;{' '}
          {review.coverage.diagnostic_components.expert_measured} /{' '}
          {review.coverage.diagnostic_components.required} reviewed by experts.{' '}
          {review.coverage.diagnostic_components.comparable_targets} diagnostic targets have
          complete comparable measures. Missing components do not become zero or full coverage.
        </p>
      )}
      <div className={s.stages}>
        <div>
          <small>STAGE 1</small>
          <h3>Forge Generated Scores</h3>
          <p>Recorded evaluator awards for this execution.</p>
        </div>
        <div>
          <small>STAGE 2</small>
          <h3>Human / Expert Reviewed Scores</h3>
          <p>
            {review.full_expert_score === null
              ? 'Full expert official-rubric score unavailable at this coverage.'
              : review.full_expert_score + ' / 100 · official rubric'}
          </p>
        </div>
      </div>
      {!!judges.length && (
        <section aria-label="Evaluator methodology">
          <h3>Which evaluator produced these scores?</h3>
          <p>
            Evaluator identity and calibration are separate from the candidate model. A fixed judge
            does not remove judge bias. Inspect each observation for its exact calibration and
            evidence.
          </p>
          <ul>
            {judges.map(({ candidate, design }) => (
              <li
                key={candidate + ':' + design.selection + ':' + design.judge_model_binding_sha256}
              >
                <strong>{candidate}</strong>:{' '}
                {design.selection === 'fixed' ? 'Fixed judge' : 'Candidate as judge'} ·{' '}
                {design.model.name || design.model.model_id || 'Model label unavailable'}
                {design.model.provider && ` (${design.model.provider})`}
                {design.same_model_as_candidate === true &&
                  ' · Judge and candidate use the same provider/model'}
                {design.same_model_as_candidate === null && ' · Same-model overlap unknown'}
                <p>{design.limitation}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section aria-label="Original execution gates">
        <h3>Original execution gates</h3>
        <p>
          Task averages and expert awards never clear critical failures or safety gates. Per-case
          gates remain bound to their original execution evidence.
        </p>
        <details>
          <summary>Execution gate record</summary>
          <FrozenGates gates={review.gates} label="Frozen execution gate record" />
        </details>
      </section>
      <details>
        <summary>Export both reports</summary>
        <label>
          Review sample selection
          <input
            value={sample}
            onChange={(e) => setSample(e.target.value)}
            placeholder="Describe the reviewed population or sample selection."
          />
        </label>
        <button
          disabled={snapshotBusy || sample.trim().length < 10}
          onClick={async () => {
            setSnapshotBusy(true);
            setError('');
            try {
              setSnapshot(
                await api(endpoint.replace(/\/expert-review$/, '/report-snapshots'), 'POST', {
                  expected_review_revision: review.review_revision,
                  snapshot_sha256: review.snapshot_sha256,
                  sample_selection: sample,
                }),
              );
            } catch (e) {
              setError(e instanceof Error ? e.message : 'Unable to freeze the reports.');
            } finally {
              setSnapshotBusy(false);
            }
          }}
        >
          {snapshotBusy ? 'Preparing report snapshot…' : 'Create report snapshot'}
        </button>
        {snapshot && (
          <p>
            <a
              href={
                '/api/v1' +
                endpoint.replace(/\/expert-review$/, '/report-snapshots/') +
                encodeURIComponent(snapshot.id) +
                '?format=pdf'
              }
            >
              Export PDF
            </a>
            {' · '}
            <a
              href={
                '/api/v1' +
                endpoint.replace(/\/expert-review$/, '/report-snapshots/') +
                encodeURIComponent(snapshot.id) +
                '?format=json'
              }
            >
              Report evidence JSON
            </a>
            <small>{snapshot.content_sha256}</small>
          </p>
        )}
      </details>
      {error && <p role="alert">{error}</p>}
      {report === 'Agent Performance' && (
        <SkillHeatmap items={review.items} onSelect={setSelected} />
      )}
      {!!review.model_comparisons?.length && (
        <section aria-label="Matched model score comparison">
          <h3>Forge and expert scores by model</h3>
          <p>
            Both bars use the same reviewed official rubric items within each model. These are
            scores for that reviewed sample; different model samples are not directly comparable.
            Diagnostic skill awards add no official points. Safety and critical-failure gates remain
            in force.
          </p>
          <p>
            <span style={{ color: '#087f82' }}>■ Forge generated</span> ·{' '}
            <span style={{ color: '#7045bd' }}>■ Human / Expert reviewed</span>
          </p>
          {review.model_comparisons.map((model) => (
            <div key={model.model_key} className={s.modelBars}>
              <strong>{model.model_key}</strong>
              <small>
                {model.coverage.comparable} comparable items / {model.coverage.eligible} eligible ·
                Full expert score:{' '}
                {model.full_expert_score === null
                  ? 'Incomplete coverage'
                  : model.full_expert_score.toFixed(1) + ' / 100'}
              </small>
              {(
                [
                  ['Forge generated', model.matched_generated_score, '#087f82'],
                  ['Human / Expert reviewed', model.matched_expert_score, '#7045bd'],
                ] as const
              ).map(([label, value, color]) => (
                <div key={label} className={s.barRow}>
                  <span>{label}</span>
                  <div className={s.barTrack}>
                    <div
                      style={{
                        width: value === null ? '0%' : `${Math.max(0, Math.min(100, value))}%`,
                        background: color,
                      }}
                    />
                  </div>
                  <strong>{value === null ? 'Unscored' : value.toFixed(1) + ' / 100'}</strong>
                </div>
              ))}
            </div>
          ))}
        </section>
      )}
      <div className={s.table}>
        <table>
          <thead>
            <tr>
              <th>
                {report === 'Workflow Metrics'
                  ? 'Case and criterion'
                  : 'Skill and responsible role'}
              </th>
              <th>Model / repetition</th>
              <th>Forge</th>
              <th>Expert</th>
              <th>RL engineer finding</th>
            </tr>
          </thead>
          <tbody>
            {review.items.map((row) => (
              <tr key={row.id}>
                <td>
                  <button className={s.link} onClick={() => setSelected(row.id)}>
                    {row.case_id} ·{' '}
                    {report === 'Workflow Metrics'
                      ? row.criterion_id || row.skill_id
                      : skillName(row)}
                  </button>
                  <small>
                    {row.role} · {row.step || 'Authored workflow step mapping pending'}
                  </small>
                  <small>
                    Capability association: {row.capability_association || 'Not declared'}. This is
                    not a capability score or an internal-cause finding.
                  </small>
                </td>
                <td>
                  {row.model_key}
                  <small>Repetition {row.repetition}</small>
                </td>
                <td>
                  {award(row.automated.award, row, row.automated.measurements)}
                  <MeasureCoverage item={row} measures={row.automated.measurements} />
                  {row.automated.judge_design && (
                    <small>
                      {row.automated.judge_design.selection === 'fixed'
                        ? 'Fixed judge'
                        : 'Candidate as judge'}{' '}
                      · {row.automated.judge_design.model.model_id || 'Inspect binding identity'}
                    </small>
                  )}
                </td>
                <td>
                  {row.disputed
                    ? 'Expert assessments disputed'
                    : row.expert
                      ? row.expert.status === 'scored'
                        ? award(row.expert.award, row, row.expert.measurements)
                        : words(row.expert.status)
                      : 'Awaiting expert review'}
                  {row.expert?.status === 'scored' && (
                    <MeasureCoverage item={row} measures={row.expert.measurements} />
                  )}
                </td>
                <td>
                  {row.diagnosis ? (
                    <>
                      <strong>{words(row.diagnosis.failure_mode)}</strong>
                      <small>
                        {words(row.diagnosis.certainty)} · {words(row.diagnosis.attribution)}
                      </small>
                      <small>Evaluator · {words(row.diagnosis.evaluator_finding)}</small>
                    </>
                  ) : (
                    'Awaiting diagnosis'
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!review.items.length && (
        <p>No eligible skill observations have been recorded for this execution.</p>
      )}
      {item && (
        <FrozenGates
          gates={item.evidence_contract?.gates}
          episodeCriticalFailures={item.evidence_contract?.critical_failures}
          label="Selected observation gates"
        />
      )}
      {item && <FrozenWorkflowEvidence item={item} label="Frozen workflow binding" />}
      {item?.automated.judge_design && (
        <section aria-label="Selected evaluator binding">
          <h3>Evaluator binding</h3>
          <p>{item.automated.judge_design.limitation}</p>
          <dl>
            <dt>Selection</dt>
            <dd>
              {item.automated.judge_design.selection === 'fixed'
                ? 'Fixed judge across candidates'
                : 'Candidate as judge'}
            </dd>
            <dt>Judge provider / model</dt>
            <dd>
              {item.automated.judge_design.model.provider || 'Unknown'} /{' '}
              {item.automated.judge_design.model.model_id || 'Unknown'}
            </dd>
            <dt>Judge binding SHA-256</dt>
            <dd>
              <code>{item.automated.judge_design.judge_model_binding_sha256}</code>
            </dd>
            <dt>Candidate binding SHA-256</dt>
            <dd>
              <code>{item.automated.judge_design.candidate_model_binding_sha256}</code>
            </dd>
            <dt>Evaluator configuration SHA-256</dt>
            <dd>
              <code>{item.automated.configuration_sha256 || 'Unavailable'}</code>
            </dd>
            <dt>Calibration SHA-256</dt>
            <dd>
              <code>{item.automated.calibration_sha256 || 'Unavailable'}</code>
            </dd>
            <dt>Judge and candidate use the same provider/model</dt>
            <dd>
              {item.automated.judge_design.same_model_as_candidate === null
                ? 'Unknown'
                : item.automated.judge_design.same_model_as_candidate
                  ? 'Yes'
                  : 'No'}
            </dd>
          </dl>
        </section>
      )}
      {item && <ScoreCalculation item={item} />}
      {item?.evidence_contract?.normalizer_scope && (
        <section aria-label="Measurement scope">
          <h4>Measurement scope</h4>
          <p>{words(item.evidence_contract.normalizer_scope)}</p>
        </section>
      )}
      {item && (
        <section aria-label="Same-case model evidence">
          <h3>
            {item.case_id} · {skillName(item)} · comparison evidence
          </h3>
          <p>
            Same task revision, case, role, workflow step, skill, criterion, mapping, repetition and
            recorded evaluator identity. Recorded reference fingerprints must also match. A matching
            evaluator name does not establish its qualification or configuration. Missing or
            unconfirmed source and evaluator identities are not substituted.
          </p>
          <ObservationModelBars
            items={review.items.filter((row) => comparisonKey(row) === comparisonKey(item))}
          />
          <div className={s.evidenceModels}>
            {review.items
              .filter((row) => comparisonKey(row) === comparisonKey(item))
              .map((row) => (
                <article key={row.id} className={s.root}>
                  <h4>{row.model_key}</h4>
                  <p>
                    Evaluator: {row.automated.evaluator || 'Identity not recorded'}
                    <small>
                      Reference fingerprint:{' '}
                      {row.evidence_contract?.reference_sha256 || 'Not recorded'}
                    </small>
                  </p>
                  <p>
                    Forge: {award(row.automated.award, row, row.automated.measurements)}
                    <small>{row.automated.reason}</small>
                    <MeasureCoverage item={row} measures={row.automated.measurements} />
                  </p>
                  <p>
                    Expert:{' '}
                    {row.disputed
                      ? 'Disputed'
                      : row.expert?.status === 'scored'
                        ? award(row.expert.award, row, row.expert.measurements)
                        : row.expert
                          ? words(row.expert.status)
                          : 'Not reviewed'}
                  </p>
                  <p>
                    <strong>Observed</strong>
                    <br />
                    {row.observed}
                  </p>
                  {row.evidence_contract?.normalizer_scope && (
                    <p>
                      <strong>Measurement scope</strong>
                      <br />
                      {words(row.evidence_contract.normalizer_scope)}
                    </p>
                  )}
                  <FrozenGates
                    gates={row.evidence_contract?.gates}
                    episodeCriticalFailures={row.evidence_contract?.critical_failures}
                    label={'Recorded gates · ' + row.model_key}
                  />
                  <FrozenWorkflowEvidence
                    item={row}
                    label={'Frozen workflow binding · ' + row.model_key}
                  />
                  <p>
                    <strong>Failure finding</strong>
                    <br />
                    {row.diagnosis
                      ? `${words(row.diagnosis.failure_mode)} · ${words(row.diagnosis.certainty)} · ${words(row.diagnosis.attribution)}`
                      : 'No engineering diagnosis recorded'}
                  </p>
                  {row.evidence.map((evidence) => (
                    <details key={evidence.id}>
                      <summary>{evidence.title}</summary>
                      <p>{evidence.excerpt}</p>
                      <small>{evidence.sha256 || 'No artifact digest recorded'}</small>
                    </details>
                  ))}
                  <button onClick={() => setSelected(row.id)}>Review this observation</button>
                </article>
              ))}
          </div>
        </section>
      )}
      {item && (
        <ReviewEditor
          key={item.id + ':' + review.review_revision}
          review={review}
          item={item}
          endpoint={endpoint}
          saved={load}
          close={() => setSelected(null)}
        />
      )}
    </section>
  );
}

function ReviewEditor({
  review,
  item,
  endpoint,
  saved,
  close,
}: {
  review: Review;
  item: Item;
  endpoint: string;
  saved: () => Promise<void>;
  close: () => void;
}) {
  const [status, setStatus] = useState<Assessment['status']>(item.expert?.status || 'comment_only');
  const [points, setPoints] = useState(
    item.expert?.award === null || item.expert?.award === undefined
      ? ''
      : String(item.expert.award),
  );
  const [measureDraft, setMeasureDraft] = useState<
    Record<string, { numerator: string; denominator: string; value: string }>
  >(() =>
    Object.fromEntries(
      Object.keys(item.scale.measures || {}).map((name) => {
        const measure = item.expert?.measurements?.[name];
        return [
          name,
          {
            numerator: measure?.kind === 'ratio' ? String(measure.numerator) : '',
            denominator: measure?.kind === 'ratio' ? String(measure.denominator) : '',
            value: measure?.kind === 'count' ? String(measure.value) : '',
          },
        ];
      }),
    ),
  );
  const [rationale, setRationale] = useState(item.expert?.rationale || '');
  const [refs, setRefs] = useState<string[]>(item.expert?.evidence_ids || []);
  const [diagnosis, setDiagnosis] = useState({
    failure_mode: item.diagnosis?.failure_mode || 'unresolved',
    attribution: item.diagnosis?.attribution || 'unresolved',
    certainty: item.diagnosis?.certainty || 'unresolved',
    evaluator_finding: item.diagnosis?.evaluator_finding || 'unresolved',
    rationale: item.diagnosis?.rationale || '',
    evidence_ids: item.diagnosis?.evidence_ids || [],
  });
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState('');
  const [issue, setIssue] = useState('evaluator'),
    [suggestion, setSuggestion] = useState('');
  const [resolutionIds, setResolutionIds] = useState<string[]>([]);
  const toggle = (list: string[], id: string) =>
    list.includes(id) ? list.filter((v) => v !== id) : [...list, id];
  const save = async (kind: 'assess' | 'diagnose' | 'resolve' | 'correction') => {
    const measurements: Measurements = {};
    if ((kind === 'assess' || kind === 'resolve') && status === 'scored' && diagnostic(item)) {
      for (const [name, contract] of Object.entries(item.scale.measures || {})) {
        const values = measureDraft[name];
        if (
          !values ||
          (contract.kind === 'ratio'
            ? values.numerator === '' && values.denominator === ''
            : values.value === '')
        )
          continue;
        const valid = (value: string, minimum: number) =>
          value.trim() !== '' &&
          Number.isSafeInteger(Number(value)) &&
          Number(value) >= minimum &&
          Number(value) <= 1000000000;
        if (
          contract.kind === 'ratio' &&
          valid(values.numerator, 0) &&
          valid(values.denominator, 1) &&
          Number(values.numerator) <= Number(values.denominator)
        )
          measurements[name] = {
            kind: 'ratio',
            numerator: Number(values.numerator),
            denominator: Number(values.denominator),
          };
        else if (contract.kind === 'count' && valid(values.value, 0))
          measurements[name] = { kind: 'count', value: Number(values.value) };
        else {
          setMessage(
            'Enter valid whole-number counts. Ratios need a positive denominator and a numerator between zero and that denominator.',
          );
          return;
        }
      }
      if (!Object.keys(measurements).length) {
        setMessage(
          'Enter at least one bound diagnostic measure, or mark the observation as insufficient evidence.',
        );
        return;
      }
    }
    if (
      kind === 'assess' &&
      (!rationale.trim() ||
        (status === 'scored' &&
          !diagnostic(item) &&
          (points === '' || !item.scale.levels.includes(Number(points)))) ||
        (status !== 'comment_only' && !refs.length))
    ) {
      setMessage(
        'Enter a rationale, select a permitted award when scored, and cite the evidence for the assessment.',
      );
      return;
    }
    if (kind === 'diagnose' && (!diagnosis.rationale.trim() || !diagnosis.evidence_ids.length)) {
      setMessage(
        'Select supporting evidence and explain the diagnosis, including any unresolved gap.',
      );
      return;
    }
    if (
      (kind === 'resolve' || kind === 'correction') &&
      (rationale.trim().length < 10 || !refs.length)
    ) {
      setMessage('Enter a rationale and select the supporting evidence in the SME panel.');
      return;
    }
    if (
      kind === 'resolve' &&
      (status !== 'scored' ||
        (!diagnostic(item) && (points === '' || !item.scale.levels.includes(Number(points)))) ||
        resolutionIds.length < 2)
    ) {
      setMessage('Choose the final native-scale award and include all conflicting assessments.');
      return;
    }
    if (kind === 'correction' && suggestion.trim().length < 10) {
      setMessage('Describe the correction or investigation needed.');
      return;
    }
    setBusy(true);
    setMessage('');
    try {
      await api(endpoint + '/' + encodeURIComponent(item.id) + '/' + kind, 'POST', {
        expected_review_revision: review.review_revision,
        snapshot_sha256: review.snapshot_sha256,
        ...(kind === 'assess' || kind === 'resolve'
          ? {
              status,
              award: status === 'scored' && !diagnostic(item) ? Number(points) : null,
              ...(status === 'scored' && diagnostic(item) ? { measurements } : {}),
              rationale,
              evidence_ids: refs,
              ...(kind === 'resolve' ? { review_ids: resolutionIds } : {}),
            }
          : kind === 'correction'
            ? { issue, suggested_change: suggestion, rationale, evidence_ids: refs }
            : diagnosis),
      });
      await saved();
    } catch (e) {
      setMessage(
        e instanceof Error
          ? e.message
          : 'Unable to save. Reload the latest review before trying again.',
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className={s.editor} aria-label="Expert skill review">
      <div className={s.heading}>
        <div>
          <h3>{skillName(item)}</h3>
          <p>
            {item.case_id} · {item.role} · {item.skill_id} · {item.model_key} · repetition{' '}
            {item.repetition}
          </p>
        </div>
        <button onClick={close}>Close review</button>
      </div>
      <div className={s.columns}>
        <section>
          <h4>Expected work</h4>
          <p>{item.expected}</p>
        </section>
        <section>
          <h4>Observed behavior</h4>
          <p>{item.observed}</p>
        </section>
      </div>
      <details open>
        <summary>Recorded evidence</summary>
        {item.evidence.map((evidence) => (
          <article className={s.evidence} key={evidence.id}>
            <strong>{evidence.title}</strong>
            <p>{evidence.excerpt}</p>
            <small>
              {evidence.id}
              {evidence.sha256 && ' · ' + evidence.sha256}
            </small>
            <RecordedEvidence
              endpoint={
                endpoint +
                '/' +
                encodeURIComponent(item.id) +
                '/evidence/' +
                encodeURIComponent(evidence.id)
              }
            />
          </article>
        ))}
      </details>
      <div className={s.columns}>
        <section>
          <small>DOMAIN SME</small>
          <h3>Score the skill</h3>
          <p>
            Forge result · {award(item.automated.award, item, item.automated.measurements)}
            <br />
            {item.automated.reason}
            <MeasureCoverage item={item} measures={item.automated.measurements} />
          </p>
          <small>{item.automated.evaluator}</small>
          <fieldset disabled={busy || !review.permissions.sme_review}>
            <legend>Human / Expert Reviewed Score</legend>
            <label>
              Assessment
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as Assessment['status'])}
              >
                <option value="comment_only">Comment only</option>
                <option
                  value="scored"
                  disabled={diagnostic(item) && !Object.keys(item.scale.measures || {}).length}
                >
                  Scored
                </option>
                <option value="unscored">Insufficient evidence</option>
                <option value="not_applicable">Outside authored scope</option>
              </select>
            </label>
            {status === 'scored' && !diagnostic(item) && (
              <label>
                Award
                <select value={points} onChange={(e) => setPoints(e.target.value)}>
                  <option value="">Select award</option>
                  {item.scale.levels.map((level) => (
                    <option key={level} value={level}>
                      {level} / {item.scale.maximum} {item.scale.unit}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {status === 'scored' && diagnostic(item) && (
              <fieldset>
                <legend>Diagnostic evidence measures</legend>
                <p>
                  Enter the observed counts for the bound measure. Empty measures stay missing;
                  these values add no official rubric points.
                </p>
                {Object.entries(item.scale.measures || {}).map(([name, contract]) => (
                  <fieldset key={name}>
                    <legend>{words(name)}</legend>
                    {(contract.kind === 'ratio' ? ['numerator', 'denominator'] : ['value']).map(
                      (field) => (
                        <label key={field}>
                          {words(name)} {field}
                          <input
                            type="number"
                            min={field === 'denominator' ? 1 : 0}
                            max={1000000000}
                            step={1}
                            value={
                              measureDraft[name]?.[
                                field as 'numerator' | 'denominator' | 'value'
                              ] || ''
                            }
                            onChange={(event) =>
                              setMeasureDraft((previous) => ({
                                ...previous,
                                [name]: { ...previous[name], [field]: event.target.value },
                              }))
                            }
                          />
                        </label>
                      ),
                    )}
                    {contract.denominator_source && (
                      <small>Denominator scope: {words(contract.denominator_source)}</small>
                    )}
                  </fieldset>
                ))}
              </fieldset>
            )}
            <label>
              Expert rationale
              <textarea value={rationale} onChange={(e) => setRationale(e.target.value)} />
            </label>
            <fieldset>
              <legend>Evidence for the assessment</legend>
              {item.evidence.map((e) => (
                <label className={s.check} key={e.id}>
                  <input
                    type="checkbox"
                    checked={refs.includes(e.id)}
                    onChange={() => setRefs(toggle(refs, e.id))}
                  />
                  {e.title}
                </label>
              ))}
            </fieldset>
            <button onClick={() => save('assess')}>Save assessment &amp; comments</button>
          </fieldset>
          {!review.permissions.sme_review && <p>Assessment requires an assigned SME Reviewer.</p>}
        </section>
        <section>
          <small>RL ENGINEER</small>
          <h3>Identify the failure mode</h3>
          <fieldset disabled={busy || !review.permissions.rl_diagnosis}>
            <legend>Evidence and attribution</legend>
            {(
              [
                [
                  'failure_mode',
                  'Task finding',
                  [
                    'unresolved',
                    'no_failure',
                    'input_omission',
                    'extraction_error',
                    'policy_selection',
                    'policy_application',
                    'stale_version',
                    'handoff',
                    'tool_failure',
                    'evidence_unavailable',
                    'reference_ambiguity',
                  ],
                ],
                [
                  'attribution',
                  'Attributed to',
                  ['unresolved', 'agent', 'environment_tool', 'task_reference', 'none'],
                ],
                ['certainty', 'Strength of evidence', ['observed', 'likely', 'unresolved']],
                [
                  'evaluator_finding',
                  'Evaluator finding',
                  ['unresolved', 'agrees', 'false_pass', 'false_fail', 'insufficient_evidence'],
                ],
              ] as const
            ).map(([field, title, choices]) => (
              <label key={field}>
                {title}
                <select
                  value={diagnosis[field]}
                  onChange={(e) => setDiagnosis({ ...diagnosis, [field]: e.target.value })}
                >
                  {choices.map((choice) => (
                    <option key={choice} value={choice}>
                      {words(choice)}
                    </option>
                  ))}
                </select>
              </label>
            ))}
            <label>
              Diagnosis rationale
              <textarea
                value={diagnosis.rationale}
                onChange={(e) => setDiagnosis({ ...diagnosis, rationale: e.target.value })}
              />
            </label>
            <fieldset>
              <legend>Supporting evidence</legend>
              {item.evidence.map((e) => (
                <label className={s.check} key={e.id}>
                  <input
                    type="checkbox"
                    checked={diagnosis.evidence_ids.includes(e.id)}
                    onChange={() =>
                      setDiagnosis({
                        ...diagnosis,
                        evidence_ids: toggle(diagnosis.evidence_ids, e.id),
                      })
                    }
                  />
                  {e.title}
                </label>
              ))}
            </fieldset>
            <button onClick={() => save('diagnose')}>Save diagnosis</button>
          </fieldset>
          {!review.permissions.rl_diagnosis && <p>Diagnosis requires an assigned RL Engineer.</p>}
        </section>
      </div>
      {message && <p role="alert">{message}</p>}
      {item.disputed && (
        <fieldset disabled={busy || !review.permissions.sme_review}>
          <legend>Resolve conflicting expert assessments</legend>
          {(item.expert_assessments || []).map((assessment) => (
            <label className={s.check} key={assessment.id}>
              <input
                type="checkbox"
                checked={resolutionIds.includes(assessment.id)}
                onChange={() => setResolutionIds(toggle(resolutionIds, assessment.id))}
              />
              {assessment.reviewer} ·{' '}
              {assessment.status === 'scored'
                ? award(assessment.award, item, assessment.measurements)
                : words(assessment.status)}{' '}
              · {assessment.rationale}
            </label>
          ))}
          <p>Set the resolved award, rationale and evidence in the SME panel above.</p>
          <button onClick={() => save('resolve')}>Save resolution</button>
        </fieldset>
      )}
      <details>
        <summary>Flag a correction</summary>
        <fieldset disabled={busy || !review.permissions.sme_review}>
          <legend>Source or evaluator correction</legend>
          <label>
            Issue type
            <select value={issue} onChange={(e) => setIssue(e.target.value)}>
              {[
                'task_instruction',
                'reference_answer',
                'policy_interpretation',
                'rubric_definition',
                'evaluator',
                'missing_evidence',
              ].map((value) => (
                <option value={value} key={value}>
                  {words(value)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Suggested correction
            <textarea value={suggestion} onChange={(e) => setSuggestion(e.target.value)} />
          </label>
          <p>
            The flag includes the SME rationale and selected evidence above. The server links it to
            the source revision and responsible owner.
          </p>
          <button onClick={() => save('correction')}>Save correction flag</button>
        </fieldset>
        {(item.correction_flags || []).map((flag) => (
          <p key={flag.id}>
            {flag.owner} · {flag.rationale} · {flag.suggested_change} ·{' '}
            {flag.sent_to_praxis ? 'Delivered to Authoring' : 'Delivery pending'}
          </p>
        ))}
      </details>
      {busy && <p role="status">Saving review…</p>}
      <details>
        <summary>Assessment and diagnosis history</summary>
        {item.history.map((entry) => (
          <article key={entry.id}>
            <strong>
              {words(entry.kind)} · {entry.reviewer}
            </strong>
            <p>{entry.summary}</p>
            <small>{new Date(entry.created_at).toLocaleString()}</small>
          </article>
        ))}
      </details>
    </section>
  );
}

function ObservationModelBars({ items }: { items: Item[] }) {
  const [stage, setStage] = useState<'generated' | 'expert'>('generated');
  const colors = ['#087f82', '#7045bd', '#2474e8'];
  return (
    <section aria-label="Same-case model award comparison">
      <h4>Model comparison for this observation</h4>
      <label>
        Comparison stage
        <select value={stage} onChange={(e) => setStage(e.target.value as 'generated' | 'expert')}>
          <option value="generated">Forge Generated Scores</option>
          <option value="expert">Human / Expert Reviewed Scores</option>
        </select>
      </label>
      <p>
        Each color identifies a model. Bar length shows its recorded award divided by the same
        native maximum, or one diagnostic ratio with its own denominator. Counts stay counts. This
        view adds no points or capability scores and never clears a critical failure.
      </p>
      {items.map((row, index) => {
        const unresolved = stage === 'expert' && (row.disputed || row.expert?.status !== 'scored');
        const value =
          stage === 'generated' ? row.automated.award : unresolved ? null : row.expert!.award;
        const measures =
          stage === 'generated'
            ? row.automated.measurements
            : unresolved
              ? null
              : row.expert!.measurements;
        const maximum = row.scale.maximum;
        const valid =
          typeof value === 'number' &&
          Number.isFinite(value) &&
          row.scale.levels.includes(value) &&
          typeof maximum === 'number' &&
          Number.isFinite(maximum) &&
          maximum > 0;
        const ratios = diagnostic(row) && measures ? Object.entries(measures) : [];
        return (
          <div key={row.id} className={s.modelBars}>
            <strong style={{ color: colors[index % colors.length] }}>■ {row.model_key}</strong>
            {unresolved ? (
              <p>
                {row.disputed
                  ? 'Expert assessments disputed'
                  : 'Not reviewed; no score substituted'}
              </p>
            ) : diagnostic(row) ? (
              ratios.length ? (
                ratios.map(([name, measure]) => {
                  const ratio =
                    measure.kind === 'ratio' &&
                    Number.isInteger(measure.numerator) &&
                    Number.isInteger(measure.denominator) &&
                    measure.denominator > 0 &&
                    measure.numerator >= 0 &&
                    measure.numerator <= measure.denominator;
                  return (
                    <div key={name} className={s.barRow}>
                      <span>{words(name)}</span>
                      <div className={s.barTrack}>
                        {ratio && measure.kind === 'ratio' && (
                          <div
                            style={{
                              width: `${(100 * measure.numerator) / measure.denominator}%`,
                              background: colors[index % colors.length],
                            }}
                          />
                        )}
                      </div>
                      <strong>
                        {ratio && measure.kind === 'ratio'
                          ? `${measure.numerator} / ${measure.denominator}`
                          : measure.kind === 'count'
                            ? `${measure.value} count`
                            : 'Unscored'}
                      </strong>
                    </div>
                  );
                })
              ) : (
                <p>Unscored; diagnostic measurements unavailable</p>
              )
            ) : (
              <div className={s.barRow}>
                <span>Native award</span>
                <div className={s.barTrack}>
                  {valid && (
                    <div
                      style={{
                        width: `${(100 * value!) / maximum!}%`,
                        background: colors[index % colors.length],
                      }}
                    />
                  )}
                </div>
                <strong>
                  {valid ? `${value} / ${maximum}` : 'Unscored; no award substituted'}
                </strong>
              </div>
            )}
          </div>
        );
      })}
    </section>
  );
}

function SkillHeatmap({ items, onSelect }: { items: Item[]; onSelect: (id: string) => void }) {
  const [stage, setStage] = useState<'generated' | 'expert'>('generated');
  const [page, setPage] = useState(0);
  const { models, rows } = useMemo(() => {
    const grouped = new Map<string, { first: Item; models: Map<string, Item[]> }>();
    for (const item of items) {
      const key = comparisonKey(item);
      let row = grouped.get(key);
      if (!row) {
        row = { first: item, models: new Map() };
        grouped.set(key, row);
      }
      row.models.set(item.model_key, [...(row.models.get(item.model_key) || []), item]);
    }
    return {
      models: [...new Set(items.map((item) => item.model_key))],
      rows: [...grouped.entries()],
    };
  }, [items]);
  const totalPages = Math.max(1, Math.ceil(rows.length / 50));
  const current = Math.min(page, totalPages - 1);
  return (
    <section aria-label="Skill and model heatmap">
      <h3>Recorded awards by skill and model</h3>
      <label>
        Score stage
        <select value={stage} onChange={(e) => setStage(e.target.value as 'generated' | 'expert')}>
          <option value="generated">Forge Generated Scores</option>
          <option value="expert">Human / Expert Reviewed Scores</option>
        </select>
      </label>
      <p>
        Green: full native award · Amber: partial award · Red: zero · Blue: diagnostic evidence
        measures · Grey: unscored, disputed or missing. Each cell retains its native scale. Select
        an award to inspect the evidence. Diagnostic skill awards are separate from official task
        scores. Rows compare only the same task revision, workflow mapping and measurement scale.
        Unconfirmed source identities remain separate observations.
      </p>
      <div className={s.table}>
        <table>
          <thead>
            <tr>
              <th>Application / campaign, skill and role</th>
              {models.map((model) => (
                <th key={model}>{model}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(current * 50, (current + 1) * 50).map(([key, row]) => (
              <tr key={key}>
                <th>
                  {row.first.case_id} · {skillName(row.first)}
                  <small>
                    {row.first.role} · {row.first.step} · repetition {row.first.repetition}
                  </small>
                  <small>
                    {row.first.source
                      ? `${row.first.source.task_id} · revision ${row.first.source.task_version} · payload ${row.first.source.payload_sha256}`
                      : 'Source identity unconfirmed — comparison unavailable'}
                  </small>
                  {row.first.skill_mapping_sha256 && (
                    <small>Mapping: {row.first.skill_mapping_sha256}</small>
                  )}
                  {!hasMappingDigest(row.first) && (
                    <small>Workflow mapping unconfirmed — comparison unavailable</small>
                  )}
                  {!hasEvaluatorIdentity(row.first) && (
                    <small>Evaluator identity unconfirmed — comparison unavailable</small>
                  )}
                </th>
                {models.map((model) => (
                  <td key={model}>
                    {row.models.has(model) ? (
                      row.models.get(model)!.map((item) => {
                        const value =
                          stage === 'generated'
                            ? item.automated.award
                            : item.disputed || item.expert?.status !== 'scored'
                              ? null
                              : item.expert.award;
                        const measures =
                          stage === 'generated'
                            ? item.automated.measurements
                            : item.disputed || item.expert?.status !== 'scored'
                              ? null
                              : item.expert.measurements;
                        const css =
                          diagnostic(item) && measures && Object.keys(measures).length
                            ? s.measuredAward
                            : value === null
                              ? s.unscoredAward
                              : value === item.scale.maximum
                                ? s.fullAward
                                : value === 0
                                  ? s.zeroAward
                                  : s.partialAward;
                        return (
                          <button
                            key={item.id}
                            className={css}
                            onClick={() => onSelect(item.id)}
                            aria-label={`${item.case_id} · ${skillName(item)} · ${model} · ${award(value, item, measures)}`}
                          >
                            {award(value, item, measures)}
                          </button>
                        );
                      })
                    ) : (
                      <span className={s.unscoredAward}>Missing observation</span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={s.heading}>
        <button disabled={current === 0} onClick={() => setPage(current - 1)}>
          Previous skills
        </button>
        <span>
          Rows {rows.length ? current * 50 + 1 : 0}–{Math.min(rows.length, (current + 1) * 50)} of{' '}
          {rows.length}
        </span>
        <button disabled={current + 1 >= totalPages} onClick={() => setPage(current + 1)}>
          Next skills
        </button>
      </div>
    </section>
  );
}

function RecordedEvidence({ endpoint }: { endpoint: string }) {
  const [evidence, setEvidence] = useState<{ content: unknown; sha256: string } | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  return (
    <>
      <button
        disabled={busy}
        onClick={async () => {
          if (evidence) {
            setOpen(!open);
            return;
          }
          setBusy(true);
          setError('');
          try {
            setEvidence(await api(endpoint));
            setOpen(true);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? 'Loading evidence…' : open ? 'Close recorded evidence' : 'Open recorded evidence'}
      </button>
      {error && <p role="alert">{error}</p>}
      {open && evidence && (
        <>
          <small>Recorded evidence digest: {evidence.sha256}</small>
          <pre
            style={{
              maxHeight: 400,
              overflow: 'auto',
              whiteSpace: 'pre-wrap',
              overflowWrap: 'anywhere',
            }}
          >
            {JSON.stringify(evidence.content, null, 2)}
          </pre>
        </>
      )}
    </>
  );
}
