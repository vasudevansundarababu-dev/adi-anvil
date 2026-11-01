import { useEffect, useState } from 'react';
import Form from './Form';

type Resource = {
  id: string;
  current_revision_id: string;
  lifecycle: string;
  content: { title: string; [key: string]: unknown };
};
type Dimensions = Record<string, string[]>;
type Preview = {
  dimensions: Dimensions;
  evidence: Record<string, { confidence: number; basis: string }>;
  heterogeneity: string[];
  segmentation_advice: string;
};
type Match = {
  revision_id: string;
  title: string;
  total_score: number;
  dimension_scores: Record<string, number>;
  uncovered_requirements: Dimensions;
  reasons: string[];
  task_coverage: { catalog_tasks: number; selected_tasks: number };
  readiness: string;
  estimate_reason: string;
};
type Recommendation = {
  current_revision_id: string;
  content: {
    ranked: Match[];
    excluded: { revision_id: string; title: string; reasons: string[] }[];
    composition: string[];
    strategy: string;
    below_threshold: boolean;
    threshold: number;
    policy: string;
  };
};
type Api = (path: string, method?: string, body?: unknown) => Promise<any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function BenchmarkFactory({
  base,
  api,
  canWrite,
  advisorId,
}: {
  base: string;
  api: Api;
  canWrite: boolean;
  advisorId: string;
}) {
  const [tasks, setTasks] = useState<Resource[]>([]),
    [objectives, setObjectives] = useState<Resource[]>([]),
    [profiles, setProfiles] = useState<Resource[]>([]);
  const [objective, setObjective] = useState(''),
    [selected, setSelected] = useState<string[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null),
    [dimensions, setDimensions] = useState<Dimensions>({});
  const [title, setTitle] = useState(''),
    [profileId, setProfileId] = useState('');
  const [rec, setRec] = useState<Recommendation | null>(null),
    [benchmarks, setBenchmarks] = useState<string[]>([]);
  const [threshold, setThreshold] = useState(75),
    [override, setOverride] = useState('');
  const [catalog, setCatalog] = useState<
    { title: string; revision_id: string; blockers: string[]; readiness: string }[]
  >([]);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  async function load() {
    const [ts, os, ps, bs] = await Promise.all([
      api(base + '/tasks?limit=100'),
      api(base + '/objectives?limit=100'),
      api(base + '/factory/profiles'),
      api(base + '/factory'),
    ]);
    setTasks(ts.filter((r: Resource) => r.lifecycle === 'published'));
    setObjectives(os.filter((r: Resource) => r.lifecycle === 'approved'));
    setProfiles(ps);
    setCatalog(bs);
  }
  useEffect(() => {
    void load().catch((e) => setError(e.message));
  }, [base]); // scoped component remounts on project change
  async function act(fn: () => Promise<void>) {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function resetConfirmation() {
    setProfileId('');
    setRec(null);
    setBenchmarks([]);
  }
  const selection = { objective_revision_id: objective, task_revision_ids: selected };
  const confirmation = { ...selection, title, dimensions };
  const needsOverride =
    !!rec &&
    (rec.content.below_threshold ||
      benchmarks.join() !== rec.content.ranked[0]?.revision_id ||
      rec.content.ranked.some(
        (b) =>
          benchmarks.includes(b.revision_id) && Object.keys(b.uncovered_requirements).length > 0,
      ));
  return (
    <section aria-label="Benchmark Factory workflow">
      <p>
        ADI synthetic · metadata matching only. Registration does not qualify an execution adapter
        or launch a model. This view loads at most 100 tasks, objectives and catalog versions;
        narrow the project for larger populations.
      </p>
      {error && (
        <div role="alert" className="banner error">
          {error}
        </div>
      )}
      {message && (
        <div role="status" className="banner success">
          {message}
        </div>
      )}
      <button disabled={busy} onClick={() => void act(load)}>
        Refresh factory
      </button>
      <label htmlFor="factory-saved-profile">Saved confirmed profile (Optional)</label>
      <select
        id="factory-saved-profile"
        value={profileId}
        onChange={(e) => {
          const p = profiles.find((p) => p.current_revision_id === e.target.value);
          resetConfirmation();
          setPreview(null);
          if (p) {
            setProfileId(p.current_revision_id);
            setDimensions(p.content.dimensions as Dimensions);
            setTitle(p.content.title);
            setObjective(String(p.content.objective_revision_id));
            setSelected(p.content.task_revision_ids as string[]);
            setPreview(p.content.inference as Preview);
          }
        }}
      >
        <option value="">Start a new profile</option>
        {profiles.map((p) => (
          <option key={p.id} value={p.current_revision_id}>
            {p.content.title} · {p.current_revision_id}
          </option>
        ))}
      </select>
      {canWrite ? (
        <>
          <Form
            onSubmit={(e) => {
              e.preventDefault();
              void act(async () => {
                const p = await api(base + '/factory/profile-preview', 'POST', selection);
                setPreview(p);
                setDimensions(p.dimensions);
                setTitle('Profile of selected synthetic tasks');
                resetConfirmation();
              });
            }}
          >
            <h2>Select existing tasks</h2>
            <label htmlFor="factory-objective">Approved objective</label>
            <select
              id="factory-objective"
              required
              value={objective}
              onChange={(e) => {
                setObjective(e.target.value);
                setPreview(null);
                resetConfirmation();
              }}
            >
              <option value="">Select an approved revision</option>
              {objectives.map((o) => (
                <option key={o.id} value={o.current_revision_id}>
                  {o.content.title}
                </option>
              ))}
            </select>
            <label htmlFor="factory-tasks">Published task revisions</label>
            <select
              id="factory-tasks"
              multiple
              required
              value={selected}
              onChange={(e) => {
                setSelected(Array.from(e.target.selectedOptions, (o) => o.value));
                setPreview(null);
                resetConfirmation();
              }}
            >
              {tasks.map((t) => (
                <option key={t.id} value={t.current_revision_id}>
                  {t.content.title}
                </option>
              ))}
            </select>
            {!tasks.length && (
              <p>No published tasks yet. Complete the existing Qualification flow.</p>
            )}
            <button disabled={busy}>Inspect Task Profile</button>
          </Form>
          {preview && (
            <Form
              onSubmit={(e) => {
                e.preventDefault();
                void act(async () => {
                  const p = await api(base + '/factory/profiles', 'POST', confirmation);
                  setProfileId(p.current_revision_id);
                  setRec(null);
                  setBenchmarks([]);
                  await load();
                  setMessage('Confirmed immutable TaskProfile saved.');
                });
              }}
            >
              <h2>Confirm Task Profile</h2>
              <p>{preview.segmentation_advice}</p>
              <label htmlFor="factory-title">Profile / catalog title</label>
              <input
                id="factory-title"
                required
                minLength={3}
                maxLength={200}
                value={title}
                onChange={(e) => {
                  setTitle(e.target.value);
                  resetConfirmation();
                }}
              />
              <p>
                Confirm every dimension. Use comma-separated values. Low-confidence defaults are
                suggestions, not measured facts.
              </p>
              <div className="fieldgrid">
                {Object.entries(dimensions).map(([field, values]) => (
                  <div key={field}>
                    <label htmlFor={'factory-' + field}>{field.replaceAll('_', ' ')}</label>
                    <input
                      id={'factory-' + field}
                      required
                      maxLength={3000}
                      value={values.join(', ')}
                      onChange={(e) => {
                        setDimensions({
                          ...dimensions,
                          [field]: e.target.value.split(',').map((v) => v.trim()),
                        });
                        resetConfirmation();
                      }}
                    />
                    <small>
                      Confidence {preview.evidence[field]?.confidence} ·{' '}
                      {preview.evidence[field]?.basis}
                    </small>
                  </div>
                ))}
              </div>
              <button disabled={busy}>Confirm immutable profile</button>
              <button
                type="button"
                disabled={busy || !profileId}
                onClick={() =>
                  void act(async () => {
                    const b = await api(base + '/factory/benchmarks', 'POST', confirmation);
                    await load();
                    setRec(null);
                    setMessage(
                      'Catalog metadata registered: ' +
                        b.current_revision_id +
                        '. Runtime smoke qualification remains pending.',
                    );
                  })
                }
              >
                Register selected tasks in catalog
              </button>
              {!profileId && <p>Confirm the profile before registering its task selection.</p>}
            </Form>
          )}
          {profileId && (
            <Form
              onSubmit={(e) => {
                e.preventDefault();
                void act(async () => {
                  const r = await api(base + '/factory/recommendations', 'POST', {
                    profile_revision_id: profileId,
                    threshold,
                  });
                  setRec(r);
                  setBenchmarks([]);
                  setMessage('Immutable recommendation snapshot saved.');
                });
              }}
            >
              <label htmlFor="factory-threshold">Coverage threshold (%)</label>
              <input
                id="factory-threshold"
                type="number"
                required
                min={1}
                max={100}
                value={threshold}
                onChange={(e) => {
                  setThreshold(Number(e.target.value));
                  setRec(null);
                }}
              />
              <button disabled={busy}>Recommend benchmarks</button>
            </Form>
          )}
          {rec && (
            <section aria-label="Benchmark recommendations">
              <h2>Recommendations</h2>
              <p>
                {rec.content.strategy} · threshold {rec.content.threshold}% · {rec.content.policy}
              </p>
              <p>
                Profile and catalog versions are pinned. Recompute after catalog changes. Capability
                match is not model performance.
              </p>
              {rec.content.ranked.map((b) => (
                <article key={b.revision_id} className="card">
                  <label>
                    <input
                      type="checkbox"
                      checked={benchmarks.includes(b.revision_id)}
                      onChange={(e) =>
                        setBenchmarks(
                          e.target.checked
                            ? [...benchmarks, b.revision_id]
                            : benchmarks.filter((x) => x !== b.revision_id),
                        )
                      }
                    />
                    Select {b.title}
                  </label>
                  <p>
                    Match score {b.total_score}% · ADI synthetic · exact version {b.revision_id}
                  </p>
                  <p>{b.readiness}</p>
                  <p>
                    Exact selected-task overlap: {b.task_coverage.selected_tasks}; catalog tasks:{' '}
                    {b.task_coverage.catalog_tasks}.
                  </p>
                  <p>Runtime and cost estimates unavailable: {b.estimate_reason}</p>
                  <details>
                    <summary>Dimension scores and reasons</summary>
                    {Object.entries(b.dimension_scores).map(([k, v]) => (
                      <p key={k}>
                        {k}: {v}%
                      </p>
                    ))}
                    <ul>
                      {b.reasons.map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                  </details>
                  <p>
                    Uncovered:{' '}
                    {Object.entries(b.uncovered_requirements)
                      .map(([k, v]) => `${k}: ${v.join(', ')}`)
                      .join('; ') || 'none'}
                  </p>
                </article>
              ))}
              {!rec.content.ranked.length && (
                <p>
                  No compatible catalog versions. Register qualified tasks or create a reviewed
                  draft from gaps.
                </p>
              )}
              {rec.content.excluded.map((b) => (
                <p key={b.revision_id}>
                  Excluded {b.title}: {b.reasons.join(', ')}
                </p>
              ))}
              {!!rec.content.composition.length && (
                <button disabled={busy} onClick={() => setBenchmarks(rec.content.composition)}>
                  Select suggested composition
                </button>
              )}
              <Form
                onSubmit={(e) => {
                  e.preventDefault();
                  void act(async () => {
                    const s = await api(base + '/factory/suite-drafts', 'POST', {
                      recommendation_revision_id: rec.current_revision_id,
                      benchmark_revision_ids: benchmarks,
                      title: 'Factory suite: ' + title,
                      advisor_id: advisorId,
                      override_reason: override,
                    });
                    setMessage(
                      'Suite draft saved: ' +
                        s.id +
                        '. Continue with independent review and freezing in Suites.',
                    );
                  });
                }}
              >
                <label htmlFor="factory-override">
                  Selection rationale {needsOverride ? '' : '(Optional)'}
                </label>
                <textarea
                  id="factory-override"
                  required={needsOverride}
                  minLength={needsOverride ? 10 : undefined}
                  maxLength={2000}
                  value={override}
                  onChange={(e) => setOverride(e.target.value)}
                />
                <button disabled={busy || !benchmarks.length || !advisorId}>
                  Create Suite draft
                </button>
                {!benchmarks.length && (
                  <p>Select compatible benchmark versions to create a suite.</p>
                )}
                {!advisorId && <p>An assigned project member is required.</p>}
              </Form>
              {(rec.content.below_threshold || rec.content.strategy !== 'direct_use') && (
                <button
                  disabled={busy}
                  onClick={() =>
                    void act(async () => {
                      const b = await api(
                        base + '/factory/recommendations/' + rec.current_revision_id + '/gap-draft',
                        'POST',
                        {},
                      );
                      await load();
                      setMessage(
                        'Benchmark gap draft saved: ' +
                          b.id +
                          '. Human review and runtime qualification required; not published.',
                      );
                    })
                  }
                >
                  Create benchmark from gaps
                </button>
              )}
              <p>
                <a href={base.replace('/projects/', '/p/') + '/suites'}>Continue to Suites</a>
              </p>
            </section>
          )}
        </>
      ) : (
        <p>
          RL Engineer access is required to confirm profiles, register metadata or create suites.
        </p>
      )}
      <h2>Existing catalog metadata</h2>
      {!catalog.length && (
        <p>
          No benchmark metadata registered yet. Select published tasks and confirm their profile.
        </p>
      )}
      {catalog.map((b) => (
        <article className="card" key={b.revision_id}>
          <h3>{b.title}</h3>
          <p>ADI synthetic · {b.revision_id}</p>
          <p>{b.readiness}</p>
          <p>{b.blockers.join(', ') || 'No local metadata compatibility blockers'}</p>
        </article>
      ))}
    </section>
  );
}
