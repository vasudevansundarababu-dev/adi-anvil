'use client';
import Form from './Form';
import BenchmarkFactory from './BenchmarkFactory';
import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';

type Api = (
  path: string,
  method?: string,
  body?: unknown,
  version?: number,
  envelope?: boolean,
) => Promise<any>; // eslint-disable-line @typescript-eslint/no-explicit-any
type Person = { id: string; name: string };
type Criterion = { id: string; label: string; weight_bps: number; anchors: Record<string, string> };
type Rubric = { criteria: Criterion[]; threshold: number; critical_rules?: string[] };
type Options = {
  cases: { id: string; title: string; capabilities: string[]; split: string }[];
  rubric_template: Rubric;
  reviewers: Person[];
  admins: Person[];
  default_graders: Person[];
};
type Plan = {
  id: string;
  title: string;
  state: 'draft' | 'submitted' | 'approved' | 'changes_requested';
  row_version: number;
  created_by: string;
  background: { notes?: string; sources?: { label: string; url: string }[] };
  case_ids: string[];
  rubric: Rubric | null;
  grader_ids: string[];
  candidates: string[];
  task_ids: string[];
  self_approved: boolean | null;
  decision_rationale: string | null;
  objective: {
    lifecycle: string;
    title: string;
    hypothesis: string;
    measurement_plan: string;
    business_context: string;
  };
  components: { kind: string; title: string; lifecycle: string }[];
  run?: { id: string; state: string; row_version: number };
  missing: string[];
};

const STEPS = ['Objective', 'Research', 'Tasks & data', 'Rubric', 'Benchmark & run'];
const CANDIDATES: Record<string, string> = {
  'fixture-correct': 'Reference fixture answer (scripted)',
  'fixture-constraint-blind': 'Constraint-blind fixture answer (scripted)',
};
const STATE: Record<Plan['state'], string> = {
  draft: 'Draft',
  submitted: 'Waiting for Admin',
  approved: 'Approved — ready to run',
  changes_requested: 'Changes requested',
};

export default function EvaluationWizard({
  base,
  api,
  userId,
  canAuthor,
  canApprove,
  canResearch,
}: {
  base: string;
  api: Api;
  userId: string;
  canAuthor: boolean;
  canApprove: boolean;
  canResearch: boolean;
}) {
  const [plans, setPlans] = useState<Plan[]>([]),
    [options, setOptions] = useState<Options | null>(null),
    [current, setCurrent] = useState<Plan | null>(null),
    [creating, setCreating] = useState(false),
    [step, setStep] = useState(0),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  const load = useCallback(async () => {
    try {
      const [list, opts] = await Promise.all([
        api(base + '/evaluations'),
        api(base + '/evaluations/options'),
      ]);
      setPlans(list);
      setOptions(opts);
      setCurrent((old) => (old ? list.find((p: Plan) => p.id === old.id) || null : null));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [api, base]);
  useEffect(() => {
    void load();
  }, [load]);

  async function run(work: () => Promise<Plan | void>, success: string) {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const plan = await work();
      if (plan) setCurrent(plan);
      setMessage(success);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const save = (body: Record<string, unknown>, next?: number) =>
    run(async () => {
      const plan = await api(
        base + '/evaluations/' + current!.id,
        'PATCH',
        body,
        current!.row_version,
      );
      if (next !== undefined) setStep(next);
      return plan;
    }, 'Saved.');

  const editable =
    !!current &&
    canAuthor &&
    current.created_by === userId &&
    ['draft', 'changes_requested'].includes(current.state);
  const people = [...(options?.reviewers || []), ...(options?.admins || [])].filter(
    (p, i, all) => all.findIndex((q) => q.id === p.id) === i,
  );
  const name = (id: string) => people.find((p) => p.id === id)?.name || id;

  return (
    <section aria-label="Evaluations">
      {error && (
        <div className="banner error" role="alert">
          {error}
        </div>
      )}
      {message && (
        <div className="banner success" role="status">
          {message}
        </div>
      )}
      {!current && !creating && (
        <>
          <div className="actions">
            {canAuthor && (
              <button
                className="primary"
                onClick={() => {
                  setCreating(true);
                  setStep(0);
                }}
              >
                New evaluation
              </button>
            )}
          </div>
          <div className="grid" style={{ marginTop: 18 }}>
            {plans.map((p) => (
              <article className="card" key={p.id}>
                <h3>{p.title}</h3>
                <span className="badge">{STATE[p.state]}</span>
                {p.self_approved && <span className="badge">Self-approved</span>}
                <p className="muted">
                  {p.case_ids.length} task set{p.case_ids.length === 1 ? '' : 's'} ·{' '}
                  {p.rubric ? 'rubric defined' : 'no rubric yet'}
                  {p.run ? ' · run ' + p.run.state : ''}
                </p>
                <button
                  onClick={() => {
                    setCurrent(p);
                    setStep(p.state === 'draft' ? 0 : 4);
                  }}
                >
                  Open
                </button>
              </article>
            ))}
          </div>
          {!plans.length && (
            <p className="empty">
              No evaluations yet.{' '}
              {canAuthor
                ? 'Start one with “New evaluation”.'
                : 'An Admin or RL Engineer starts evaluations.'}
            </p>
          )}
        </>
      )}

      {creating && (
        <Form
          className="card"
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            void run(async () => {
              const plan = await api(base + '/evaluations', 'POST', {
                title: f.get('title'),
                hypothesis: f.get('hypothesis'),
                success_criteria: f.get('success'),
                business_context: f.get('context') || '',
              });
              setCreating(false);
              setStep(1);
              return plan;
            }, 'Evaluation created. Next: research.');
          }}
        >
          <Stepper step={0} onPick={() => undefined} />
          <h2>Step 1 · Research objective</h2>
          <ObjectiveFields />
          <div className="actions">
            <button className="primary" disabled={busy}>
              Create and continue
            </button>
            <button type="button" onClick={() => setCreating(false)}>
              Cancel
            </button>
          </div>
        </Form>
      )}

      {current && (
        <div className="card">
          <div className="toolbar">
            <div>
              <div className="eyebrow">Evaluation</div>
              <h2>{current.title}</h2>
              <span className="badge">{STATE[current.state]}</span>
              {current.self_approved && <span className="badge">Self-approved</span>}
            </div>
            <button onClick={() => setCurrent(null)}>Back to evaluations</button>
          </div>
          <Stepper step={step} onPick={setStep} />

          {step === 0 && (
            <Form
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                void save(
                  {
                    title: f.get('title'),
                    hypothesis: f.get('hypothesis'),
                    success_criteria: f.get('success'),
                    business_context: f.get('context') || '',
                  },
                  1,
                );
              }}
            >
              <h3>Step 1 · Research objective</h3>
              <fieldset disabled={!editable} style={{ border: 0, padding: 0 }}>
                <ObjectiveFields plan={current} />
              </fieldset>
              {editable && (
                <div className="actions">
                  <button className="primary" disabled={busy}>
                    Save and continue
                  </button>
                </div>
              )}
            </Form>
          )}

          {step === 1 && (
            <ResearchStep
              plan={current}
              editable={editable}
              busy={busy}
              onSave={(body) => void save(body, 2)}
              factory={
                canResearch ? (
                  <BenchmarkFactory base={base} api={api} canWrite={canAuthor} advisorId="" />
                ) : null
              }
            />
          )}

          {step === 2 && options && (
            <Form
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                void save({ case_ids: f.getAll('case') }, 3);
              }}
            >
              <h3>Step 3 · Import tasks and data</h3>
              <p className="muted">
                Choose the task sets to evaluate. Built-in sets are original ADI synthetic cases
                with hidden reference answers; graders see the references, candidates never do.
              </p>
              <fieldset disabled={!editable} style={{ border: 0, padding: 0 }}>
                {options.cases.map((c) => (
                  <label key={c.id} style={{ fontWeight: 400 }}>
                    <input
                      type="checkbox"
                      name="case"
                      value={c.id}
                      defaultChecked={current.case_ids.includes(c.id)}
                    />
                    <strong>{c.id}</strong> — {c.title}{' '}
                    <span className="muted">({c.capabilities.join(', ')})</span>
                  </label>
                ))}
              </fieldset>
              <p className="banner">
                Your own CSV/JSONL tasks can be imported and versioned under Build → Tasks &amp;
                data. Imported tasks can be attached to suites but cannot run against the fixture
                candidates yet.
              </p>
              {editable && (
                <div className="actions">
                  <button className="primary" disabled={busy}>
                    Save and continue
                  </button>
                </div>
              )}
            </Form>
          )}

          {step === 3 && options && (
            <RubricStep
              key={current.id + current.row_version}
              initial={current.rubric || options.rubric_template}
              editable={editable}
              busy={busy}
              onSave={(rubric) => void save({ rubric }, 4)}
            />
          )}

          {step === 4 && options && (
            <div>
              <h3>Step 5 · Select benchmark and run</h3>
              <Form
                onSubmit={(e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  void save({
                    candidates: f.getAll('candidate'),
                    grader_ids: f.getAll('grader'),
                  });
                }}
              >
                <fieldset disabled={!editable} style={{ border: 0, padding: 0 }}>
                  <p className="muted">
                    The benchmark is a frozen suite of the task sets you chose, scored with your
                    rubric. Candidates are scripted fixture answers; results are illustrative, not
                    model performance.
                  </p>
                  <div className="split">
                    <div>
                      <strong>Candidates</strong>
                      {Object.entries(CANDIDATES).map(([key, label]) => (
                        <label key={key} style={{ fontWeight: 400 }}>
                          <input
                            type="checkbox"
                            name="candidate"
                            value={key}
                            defaultChecked={current.candidates.includes(key)}
                          />
                          {label}
                        </label>
                      ))}
                    </div>
                    <div>
                      <strong>Graders (up to two)</strong>
                      <p className="muted" style={{ margin: '4px 0' }}>
                        The first grades every output; the second checks critical, borderline and a
                        10% sample.
                      </p>
                      {people.map((p) => (
                        <label key={p.id} style={{ fontWeight: 400 }}>
                          <input
                            type="checkbox"
                            name="grader"
                            value={p.id}
                            defaultChecked={current.grader_ids.includes(p.id)}
                          />
                          {p.name}
                        </label>
                      ))}
                    </div>
                  </div>
                </fieldset>
                {editable && (
                  <div className="actions">
                    <button disabled={busy}>Save choices</button>
                  </div>
                )}
              </Form>

              <h4>Summary</h4>
              <ul>
                <li>Objective: {current.objective.title}</li>
                <li>Task sets: {current.case_ids.join(', ') || 'none chosen'}</li>
                <li>
                  Rubric:{' '}
                  {current.rubric
                    ? `${current.rubric.criteria.length} criteria, pass at ${current.rubric.threshold}`
                    : 'not defined'}
                </li>
                <li>Graders: {current.grader_ids.map(name).join(', ') || 'none'}</li>
              </ul>
              {current.missing.length > 0 && (
                <div className="banner">Before submitting: {current.missing.join('; ')}.</div>
              )}
              {current.decision_rationale && current.state !== 'approved' && (
                <div className="banner">Admin: {current.decision_rationale}</div>
              )}

              {editable && (
                <div className="actions">
                  <button
                    className="primary"
                    disabled={busy || current.missing.length > 0}
                    onClick={() =>
                      void run(
                        () =>
                          api(
                            base + '/evaluations/' + current.id + '/submit',
                            'POST',
                            {},
                            current.row_version,
                          ),
                        'Submitted to the Admin.',
                      )
                    }
                  >
                    Submit to Admin
                  </button>
                </div>
              )}

              {current.state === 'submitted' && canApprove && (
                <Form
                  className="card"
                  onSubmit={(e) => {
                    e.preventDefault();
                    const f = new FormData(e.currentTarget);
                    const decision = (e.nativeEvent as SubmitEvent).submitter?.getAttribute(
                      'value',
                    );
                    void run(
                      () =>
                        api(
                          base + '/evaluations/' + current.id + '/decision',
                          'POST',
                          { decision, rationale: f.get('rationale') },
                          current.row_version,
                        ),
                      decision === 'approve'
                        ? 'Approved. The suite is frozen and the run is ready.'
                        : 'Changes requested.',
                    );
                  }}
                >
                  <h4>Admin decision</h4>
                  <p className="muted">
                    Approving reviews the objective, rubric, tasks, data rights, suite and protocol
                    together and prepares the run.
                  </p>
                  <label htmlFor="rationale">Rationale</label>
                  <textarea id="rationale" name="rationale" required minLength={10} />
                  <div className="actions">
                    <button className="primary" name="decision" value="approve" disabled={busy}>
                      Approve
                    </button>
                    <button name="decision" value="changes_requested" disabled={busy}>
                      Request changes
                    </button>
                  </div>
                </Form>
              )}
              {current.state === 'submitted' && !canApprove && (
                <p className="muted">Waiting for the Admin’s decision.</p>
              )}

              {current.state === 'approved' && current.run && (
                <div className="card">
                  <h4>Run</h4>
                  <p>
                    Run state: <span className="badge">{current.run.state}</span>
                  </p>
                  {current.run.state === 'draft' && canAuthor ? (
                    <button
                      className="primary"
                      disabled={busy}
                      onClick={() =>
                        void run(async () => {
                          await api(
                            base + '/runs/' + current.run!.id + '/launch',
                            'POST',
                            {},
                            current.run!.row_version,
                          );
                        }, 'Run launched. Graders will see outputs in their review inbox.')
                      }
                    >
                      Run evaluation
                    </button>
                  ) : (
                    <p className="muted">
                      Follow progress in Run &amp; review → Runs; graders work in the Review inbox.
                    </p>
                  )}
                </div>
              )}
              {current.components.length > 0 && (
                <details>
                  <summary>Versioned records in this evaluation</summary>
                  <ul>
                    {current.components.map((c, i) => (
                      <li key={i}>
                        {c.kind}: {c.title} — <span className="badge">{c.lifecycle}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function Stepper({ step, onPick }: { step: number; onPick: (i: number) => void }) {
  return (
    <ol className="stepper" aria-label="Evaluation steps">
      {STEPS.map((s, i) => (
        <li key={s} aria-current={i === step ? 'step' : undefined}>
          <button type="button" onClick={() => onPick(i)}>
            <span>{i + 1}</span> {s}
          </button>
        </li>
      ))}
    </ol>
  );
}

function ObjectiveFields({ plan }: { plan?: Plan }) {
  return (
    <>
      <label htmlFor="ev-title">Title</label>
      <input
        id="ev-title"
        name="title"
        required
        minLength={3}
        defaultValue={plan?.objective.title}
      />
      <label htmlFor="ev-hypothesis">Hypothesis — what do you expect to observe?</label>
      <textarea
        id="ev-hypothesis"
        name="hypothesis"
        required
        minLength={10}
        defaultValue={plan?.objective.hypothesis}
      />
      <label htmlFor="ev-success">What does success look like?</label>
      <textarea
        id="ev-success"
        name="success"
        required
        minLength={20}
        defaultValue={plan?.objective.measurement_plan}
        placeholder="For example: score at least 70 on every task with no critical constraint violation."
      />
      <label htmlFor="ev-context">Business context (optional)</label>
      <input id="ev-context" name="context" defaultValue={plan?.objective.business_context} />
    </>
  );
}

function ResearchStep({
  plan,
  editable,
  busy,
  onSave,
  factory,
}: {
  plan: Plan;
  editable: boolean;
  busy: boolean;
  onSave: (body: Record<string, unknown>) => void;
  factory: ReactNode;
}) {
  const [sources, setSources] = useState(plan.background.sources || []);
  return (
    <div>
      <Form
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          onSave({
            background_notes: f.get('notes') || '',
            sources: sources.filter((s) => s.label.trim()),
          });
        }}
      >
        <h3>Step 2 · Research</h3>
        <p className="muted">
          Background and sources are notes for reviewers; they never block the next step.
        </p>
        <fieldset disabled={!editable} style={{ border: 0, padding: 0 }}>
          <label htmlFor="ev-notes">Background notes</label>
          <textarea id="ev-notes" name="notes" defaultValue={plan.background.notes || ''} />
          <strong>Sources</strong>
          {sources.map((s, i) => (
            <div className="fieldgrid" key={i}>
              <input
                aria-label={`Source ${i + 1} name`}
                placeholder="Name"
                value={s.label}
                onChange={(e) =>
                  setSources(sources.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))
                }
              />
              <input
                aria-label={`Source ${i + 1} link`}
                placeholder="https://…"
                value={s.url}
                onChange={(e) =>
                  setSources(sources.map((x, j) => (j === i ? { ...x, url: e.target.value } : x)))
                }
              />
            </div>
          ))}
          {editable && (
            <div className="actions">
              <button
                type="button"
                onClick={() => setSources([...sources, { label: '', url: '' }])}
              >
                Add source
              </button>
            </div>
          )}
        </fieldset>
        {editable && (
          <div className="actions">
            <button className="primary" disabled={busy}>
              Save and continue
            </button>
          </div>
        )}
      </Form>
      {factory && (
        <details>
          <summary>Benchmark research (Benchmark Factory)</summary>
          <p className="muted">
            Profile your task requirements and compare catalog benchmarks. Findings here inform your
            task and rubric choices; recommendations pin exact task versions, so they are not bound
            to this evaluation’s new tasks automatically.
          </p>
          {factory}
        </details>
      )}
    </div>
  );
}

function RubricStep({
  initial,
  editable,
  busy,
  onSave,
}: {
  initial: Rubric;
  editable: boolean;
  busy: boolean;
  onSave: (rubric: Rubric) => void;
}) {
  const [criteria, setCriteria] = useState<Criterion[]>(initial.criteria),
    [threshold, setThreshold] = useState(initial.threshold),
    [rules, setRules] = useState((initial.critical_rules || []).join('\n'));
  const total = criteria.reduce((s, c) => s + c.weight_bps, 0) / 100;
  const update = (i: number, patch: Partial<Criterion>) =>
    setCriteria(criteria.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  return (
    <Form
      onSubmit={(e) => {
        e.preventDefault();
        onSave({
          criteria,
          threshold,
          critical_rules: rules
            .split('\n')
            .map((r) => r.trim())
            .filter(Boolean),
        });
      }}
    >
      <h3>Step 4 · Define the rubric</h3>
      <p className="muted">
        Started from the ADI template. Weights must total 100%. Each criterion is scored 0–4 using
        its anchors.
      </p>
      <fieldset disabled={!editable} style={{ border: 0, padding: 0 }}>
        {criteria.map((c, i) => (
          <div className="card" key={i}>
            <div className="fieldgrid">
              <div>
                <label htmlFor={`cr-id-${i}`}>ID</label>
                <input
                  id={`cr-id-${i}`}
                  required
                  pattern="[A-Za-z0-9_-]{1,30}"
                  value={c.id}
                  onChange={(e) => update(i, { id: e.target.value })}
                />
              </div>
              <div>
                <label htmlFor={`cr-label-${i}`}>Criterion</label>
                <input
                  id={`cr-label-${i}`}
                  required
                  value={c.label}
                  onChange={(e) => update(i, { label: e.target.value })}
                />
              </div>
              <div>
                <label htmlFor={`cr-weight-${i}`}>Weight %</label>
                <input
                  id={`cr-weight-${i}`}
                  type="number"
                  min={0.01}
                  max={100}
                  step={0.01}
                  required
                  value={c.weight_bps / 100}
                  onChange={(e) =>
                    update(i, { weight_bps: Math.round(Number(e.target.value) * 100) })
                  }
                />
              </div>
            </div>
            <details>
              <summary>Score anchors 0–4</summary>
              {['0', '1', '2', '3', '4'].map((k) => (
                <div key={k}>
                  <label htmlFor={`cr-${i}-a${k}`}>Score {k}</label>
                  <input
                    id={`cr-${i}-a${k}`}
                    required
                    value={c.anchors[k] || ''}
                    onChange={(e) => update(i, { anchors: { ...c.anchors, [k]: e.target.value } })}
                  />
                </div>
              ))}
            </details>
            {editable && criteria.length > 1 && (
              <div className="actions">
                <button
                  type="button"
                  onClick={() => setCriteria(criteria.filter((_, j) => j !== i))}
                >
                  Remove criterion
                </button>
              </div>
            )}
          </div>
        ))}
        {editable && (
          <div className="actions">
            <button
              type="button"
              onClick={() =>
                setCriteria([
                  ...criteria,
                  {
                    id: 'R' + (criteria.length + 1),
                    label: '',
                    weight_bps: 0,
                    anchors: { '0': '', '1': '', '2': '', '3': '', '4': '' },
                  },
                ])
              }
            >
              Add criterion
            </button>
            <span className={total === 100 ? 'badge' : 'badge error'}>Total {total}%</span>
          </div>
        )}
        <label htmlFor="cr-threshold">Pass mark (0–100)</label>
        <input
          id="cr-threshold"
          type="number"
          min={0}
          max={100}
          required
          value={threshold}
          onChange={(e) => setThreshold(Number(e.target.value))}
        />
        <label htmlFor="cr-rules">Extra critical rules (optional, one per line)</label>
        <textarea
          id="cr-rules"
          value={rules}
          onChange={(e) => setRules(e.target.value)}
          placeholder="Each task set already includes its own critical rule."
        />
      </fieldset>
      {editable && (
        <div className="actions">
          <button className="primary" disabled={busy || total !== 100}>
            Save and continue
          </button>
        </div>
      )}
    </Form>
  );
}
