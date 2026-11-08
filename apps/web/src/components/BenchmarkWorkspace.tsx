'use client';

import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { workspaceApi } from '../lib/workspace';
import { ModelConfiguration } from './ModelProfileEditor';
import {
  benchmarkGet,
  benchmarkPath,
  benchmarkPost,
  uploadBenchmark,
  BenchmarkBlocker,
  BenchmarkComparison,
  BenchmarkProtocol as Protocol,
  BenchmarkReadiness,
  BenchmarkReceipt,
  BenchmarkReviewPolicy,
  BenchmarkVersion as Version,
} from '../lib/benchmark';
import styles from './ModernWorkspace.module.css';
import BenchmarkScoreReview from './BenchmarkScoreReview';
import BenchmarkCellEvidence from './BenchmarkCellEvidence';
import BenchmarkHistory from './BenchmarkHistory';
import BenchmarkRecovery from './BenchmarkRecovery';

function Blockers({ items }: { items: BenchmarkBlocker[] }) {
  return items.length ? (
    <ul aria-label="Required actions">
      {items.map((b, i) => (
        <li key={b.code + i}>
          <strong>{b.code.replaceAll('_', ' ')}</strong> · {b.action} ({b.fixer})
        </li>
      ))}
    </ul>
  ) : null;
}

export function BenchmarkLibrary({
  items,
  select,
  more,
  busy,
}: {
  items: BenchmarkReceipt[];
  select: (id: string) => void;
  more: (() => void) | null;
  busy: boolean;
}) {
  return (
    <section className={styles.panel} aria-label="Benchmark library">
      <h2>Benchmark library</h2>
      {items.length ? (
        <table>
          <caption>
            Imported task banks — source receipts are distinct from qualified versions
          </caption>
          <thead>
            <tr>
              <th>Task bank</th>
              <th>Version</th>
              <th>Owner</th>
              <th>Tasks</th>
              <th>Source</th>
              <th>Status</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.receipt_id}>
                <td>
                  {item.bank_title || item.bank_id}
                  <br />
                  <small>{item.bank_id}</small>
                </td>
                <td>{item.bank_version}</td>
                <td>{item.source_owner || 'Not recorded in this receipt'}</td>
                <td>{item.task_count}</td>
                <td>{item.source_classification}</td>
                <td>{item.source_state}</td>
                <td>
                  <button type="button" disabled={busy} onClick={() => select(item.receipt_id)}>
                    Inspect {item.bank_id}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p>Awaiting a Praxis task-bank export. No benchmark measurements have been created.</p>
      )}
      {more && (
        <button type="button" disabled={busy} onClick={more}>
          Load more task banks
        </button>
      )}
    </section>
  );
}

export function BenchmarkImport({
  submit,
  busy,
  canWrite,
}: {
  submit: (file: File, key: string) => Promise<void>;
  busy: boolean;
  canWrite: boolean;
}) {
  const [file, setFile] = useState<File | null>(null);
  const key = useRef('');
  return (
    <section className={styles.panel} aria-label="Import a task bank">
      <h2>Import from Praxis</h2>
      <p>
        Upload the SME bundle v1 gzip export. Import validates and stores the original; it does not
        run models or grant source rights.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (file) void submit(file, key.current);
        }}
      >
        <label>
          Praxis export archive{' '}
          <input
            type="file"
            accept=".tar.gz,.tgz,application/gzip"
            disabled={busy || !canWrite}
            onChange={(event) => {
              setFile(event.target.files?.[0] || null);
              key.current = crypto.randomUUID();
            }}
          />
        </label>
        <button type="submit" disabled={busy || !canWrite || !file}>
          Validate and import
        </button>
      </form>
      {!canWrite && <p>Your current access allows inspection only.</p>}
    </section>
  );
}

export function BenchmarkVersion({ version }: { version: Version }) {
  return (
    <section className={styles.panel} aria-label="Immutable benchmark version">
      <h2>Frozen benchmark version</h2>
      <p>
        Version {version.benchmark_revision_id}. Package readiness, admission and measured
        performance remain separate.
      </p>
      <table>
        <caption>Exact task and qualification bindings</caption>
        <thead>
          <tr>
            <th>Task</th>
            <th>Points</th>
            <th>Criteria</th>
            <th>Qualification</th>
          </tr>
        </thead>
        <tbody>
          {version.tasks.map((task) => (
            <tr key={task.task_revision_id}>
              <td>{version.task_labels?.[task.task_revision_id] || task.source_id}</td>
              <td>{task.possible_points}</td>
              <td>{task.criterion_count}</td>
              <td>{task.qualification_id}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <details>
        <summary>Immutable provenance</summary>
        <pre>{JSON.stringify(version, null, 2)}</pre>
      </details>
    </section>
  );
}

export function BenchmarkProtocol({
  models,
  base,
  version,
  freeze,
  busy,
  canWrite,
}: {
  models: ModelConfiguration[];
  base: string;
  version: Version;
  freeze: (ids: string[], expires: string, policy: BenchmarkReviewPolicy) => Promise<void>;
  busy: boolean;
  canWrite: boolean;
}) {
  const [ids, setIds] = useState(['', '', '']);
  const [expiry, setExpiry] = useState('');
  const [thresholds, setThresholds] = useState<Record<string, string>>({});
  const [critical, setCritical] = useState<Record<string, string>>({});
  const [duties, setDuties] = useState(['', '', '']);
  const [confirmed, setConfirmed] = useState(false);
  const [assignments, setAssignments] = useState<
    { assignment_id: string; user_id: string; user_name?: string; expires_at: string }[]
  >([]);
  const [assignmentError, setAssignmentError] = useState('');
  useEffect(() => {
    let active = true;
    void benchmarkGet<{ items: typeof assignments }>(base, '/review-assignments')
      .then((result) => {
        if (active) setAssignments(result.items);
      })
      .catch((failure) => {
        if (active) setAssignmentError((failure as Error).message);
      });
    return () => {
      active = false;
    };
  }, [base]);
  const distinctPeople =
    new Set(duties.map((id) => assignments.find((item) => item.assignment_id === id)?.user_id))
      .size === 3;
  return (
    <section className={styles.panel} aria-label="Comparison configuration">
      <h2>Configure an offline software comparison</h2>
      <p>
        Three exact model configurations × three tasks × two repetitions. At most three active
        trials. This mode makes no paid model or judge requests and is not a model-performance
        benchmark.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void freeze(ids, expiry, {
            tasks: version.tasks.map((task) => ({
              task_revision_id: task.task_revision_id,
              pass_threshold_percent: thresholds[task.task_revision_id],
              critical_criterion_ids: (critical[task.task_revision_id] || '')
                .split(',')
                .map((id) => id.trim())
                .filter(Boolean),
            })),
            calibration_sha256: version.calibration_sha256,
            first_assignment_id: duties[0],
            second_assignment_id: duties[1],
            adjudicator_assignment_id: duties[2],
            sample_percent: 10,
            borderline_percentage_points: 5,
          });
        }}
      >
        {ids.map((value, slot) => (
          <label key={slot}>
            Model slot {slot + 1}{' '}
            <select
              required
              value={value}
              disabled={busy || !canWrite}
              onChange={(event) =>
                setIds((current) =>
                  current.map((v, index) => (index === slot ? event.target.value : v)),
                )
              }
            >
              <option value="">Select a current configuration</option>
              {models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name} · {model.provider} · {model.model_id || 'Model not selected'} ·
                  version {model.version}
                </option>
              ))}
            </select>
          </label>
        ))}
        <fieldset disabled={busy || !canWrite}>
          <legend>Declared review policy</legend>
          <p>
            Supply the task owner's thresholds and critical criterion IDs. None are inferred from
            the code. A stable 10% sample, critical failures and results within five percentage
            points of a threshold require a second review.
          </p>
          {version.tasks.map((task) => (
            <div key={task.task_revision_id}>
              <label>
                Task {version.task_labels?.[task.task_revision_id] || task.source_id}: pass
                threshold (%){' '}
                <input
                  required
                  type="number"
                  min="0"
                  max="100"
                  step="0.00000001"
                  value={thresholds[task.task_revision_id] || ''}
                  onChange={(event) =>
                    setThresholds((current) => ({
                      ...current,
                      [task.task_revision_id]: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                Critical criterion IDs (comma separated; empty means none declared){' '}
                <input
                  value={critical[task.task_revision_id] || ''}
                  onChange={(event) =>
                    setCritical((current) => ({
                      ...current,
                      [task.task_revision_id]: event.target.value,
                    }))
                  }
                />
              </label>
            </div>
          ))}
          {assignmentError && <p role="alert">{assignmentError}</p>}
          {['First reviewer', 'Second reviewer', 'Adjudicator'].map((name, index) => (
            <label key={name}>
              {name}{' '}
              <select
                required
                value={duties[index]}
                onChange={(event) =>
                  setDuties((current) =>
                    current.map((id, position) => (position === index ? event.target.value : id)),
                  )
                }
              >
                <option value="">Choose a current individual assignment</option>
                {assignments.map((item) => (
                  <option key={item.assignment_id} value={item.assignment_id}>
                    {item.user_name || item.user_id} · expires{' '}
                    {new Date(item.expires_at).toLocaleString()}
                  </option>
                ))}
              </select>
            </label>
          ))}
          {!distinctPeople && <p>Three different assigned people are required.</p>}
          <p>
            Calibration binding: <code>{version.calibration_sha256}</code>
          </p>
          <label>
            <input
              required
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            I confirm these declared thresholds, critical criteria and reviewer duties for this
            exact software protocol.
          </label>
        </fieldset>
        <label>
          Protocol expiry{' '}
          <input
            required
            type="datetime-local"
            value={expiry}
            onChange={(event) => setExpiry(event.target.value)}
            disabled={busy || !canWrite}
          />
        </label>
        <button
          disabled={
            busy ||
            !canWrite ||
            new Set(ids).size !== 3 ||
            ids.some((id) => !id) ||
            !expiry ||
            !distinctPeople ||
            duties.some((id) => !id) ||
            !confirmed ||
            version.tasks.some((task) => !thresholds[task.task_revision_id])
          }
        >
          Freeze exact offline protocol
        </button>
      </form>
    </section>
  );
}

export function BenchmarkMatrix({
  comparison,
  base,
}: {
  comparison: BenchmarkComparison;
  base: string;
}) {
  const tasks = [...new Set(comparison.cells.map((cell) => cell.task_revision_id))];
  return (
    <section className={styles.panel} aria-label="Comparison matrix">
      <h2>Comparison matrix</h2>
      <p>
        {comparison.state} · {comparison.cells.length} stored cells of {comparison.planned_cells}{' '}
        planned · origin: {comparison.origin}
      </p>
      <table>
        <caption>Stored task, model-slot and repetition states</caption>
        <thead>
          <tr>
            <th>Task revision</th>
            {[1, 2, 3].map((slot) => (
              <th key={slot}>
                Model slot {slot}
                {comparison.model_slots?.find((item) => item.slot === slot - 1) && (
                  <>
                    <br />
                    <small>
                      {comparison.model_slots.find((item) => item.slot === slot - 1)?.provider} ·{' '}
                      {comparison.model_slots.find((item) => item.slot === slot - 1)?.model_id}
                    </small>
                  </>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => (
            <tr key={task}>
              <th scope="row">{comparison.task_labels?.[task] || task}</th>
              {[0, 1, 2].map((slot) => (
                <td key={slot}>
                  {comparison.cells
                    .filter((cell) => cell.task_revision_id === task && cell.slot === slot)
                    .map((cell) => (
                      <details key={cell.cell_id}>
                        <summary>
                          Repetition {cell.repetition + 1}: {cell.state}
                        </summary>
                        <p>Validity: {cell.validity || 'Not established'}</p>
                        <p>Cell {cell.cell_id}</p>
                        <BenchmarkCellEvidence
                          base={base}
                          runId={comparison.run_id}
                          cellId={cell.cell_id}
                        />
                      </details>
                    ))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <Blockers items={comparison.blockers || []} />
    </section>
  );
}

export function BenchmarkResults({
  comparison,
  base,
}: {
  comparison: BenchmarkComparison;
  base: string;
}) {
  const results = comparison.scorecard;
  return (
    <section className={styles.panel} aria-label="Comparison results">
      <h2>Results and evidence</h2>
      {!results ? (
        <p>
          No scorecard has been published. Pending, failed or invalid trials do not count as model
          zeroes.
        </p>
      ) : (
        <>
          <p>
            {results.complete
              ? 'Complete, reviewed scorecard'
              : results.execution_complete
                ? 'Execution evidence is complete. Comparable primary results remain unavailable until mandatory independent review is recorded.'
                : 'Incomplete comparison — primary result unavailable; no winner declared.'}
          </p>
          <table>
            <caption>Stored primary results</caption>
            <thead>
              <tr>
                <th>Model slot</th>
                <th>Raw points</th>
                <th>Percent</th>
                <th>Completeness</th>
              </tr>
            </thead>
            <tbody>
              {results.models.map((model) => (
                <tr key={model.slot}>
                  <td>{model.slot + 1}</td>
                  <td>
                    {model.primary == null
                      ? 'Unavailable'
                      : `${model.primary.earned_points} / ${model.primary.possible_points}`}
                  </td>
                  <td>{model.primary == null ? 'Unavailable' : `${model.primary.percent}%`}</td>
                  <td>
                    {model.scored} / {model.planned} scored · {model.completion}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <details>
            <summary>Unranked diagnostics and measured runtime</summary>
            <p>
              Diagnostic means use only complete suite repetitions out of81 points. They do not
              replace missing trials or mandatory review and do not establish model performance.
            </p>
            <table>
              <caption>Complete-repetition diagnostics</caption>
              <thead>
                <tr>
                  <th>Slot</th>
                  <th>Complete repetitions</th>
                  <th>Diagnostic mean</th>
                  <th>Median duration</th>
                  <th>Cost status</th>
                </tr>
              </thead>
              <tbody>
                {results.models.map((model) => (
                  <tr key={model.slot}>
                    <td>{model.slot + 1}</td>
                    <td>{model.diagnostic.complete_repetitions.length} / 2</td>
                    <td>
                      {model.diagnostic.complete_repetition_mean
                        ? `${model.diagnostic.complete_repetition_mean.earned_points} / 81 (${model.diagnostic.complete_repetition_mean.percent}%)`
                        : 'Unavailable'}
                    </td>
                    <td>
                      {model.duration.median_ms == null
                        ? 'Unknown'
                        : `${model.duration.median_ms} ms from ${model.duration.samples} trials`}
                    </td>
                    <td>{model.cost.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
      <p>
        Offline software evidence does not establish live model performance. Unknown usage and costs
        remain unknown.
      </p>
      <a
        href={
          '/api/v1' +
          benchmarkPath(base) +
          '/comparisons/' +
          encodeURIComponent(comparison.run_id) +
          '/exports/json'
        }
      >
        Download authorized JSON
      </a>
      {' · '}
      <a
        href={
          '/api/v1' +
          benchmarkPath(base) +
          '/comparisons/' +
          encodeURIComponent(comparison.run_id) +
          '/exports/csv'
        }
      >
        Download redacted CSV
      </a>
      {' · '}
      <a
        href={
          '/api/v1' +
          benchmarkPath(base) +
          '/comparisons/' +
          encodeURIComponent(comparison.run_id) +
          '/exports/report'
        }
      >
        Download redacted report
      </a>
      {' · '}
      <a
        href={
          '/api/v1' +
          benchmarkPath(base) +
          '/comparisons/' +
          encodeURIComponent(comparison.run_id) +
          '/exports/atif'
        }
      >
        Download authorized Harbor trajectories
      </a>
      <p>
        Private trajectory downloads require a current individual evaluation assignment. They omit
        hidden reasoning and evaluator reference material.
      </p>
    </section>
  );
}

export default function BenchmarkWorkspace({
  base,
  canWrite,
  canAdmin,
  userId,
}: {
  base: string;
  canWrite: boolean;
  canAdmin: boolean;
  userId: string;
}) {
  const router = useRouter(),
    pathname = usePathname(),
    query = useSearchParams();
  const [items, setItems] = useState<BenchmarkReceipt[]>([]),
    [cursor, setCursor] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<BenchmarkReceipt | null>(null),
    [version, setVersion] = useState<Version | null>(null);
  const [protocol, setProtocol] = useState<Protocol | null>(null),
    [comparison, setComparison] = useState<BenchmarkComparison | null>(null);
  const [readiness, setReadiness] = useState<BenchmarkReadiness | null>(null),
    [models, setModels] = useState<ModelConfiguration[]>([]);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  const [reviewId, setReviewId] = useState(''),
    [buildId, setBuildId] = useState('');
  const [evidence, setEvidence] = useState(''),
    [reviewExpiry, setReviewExpiry] = useState(''),
    [rights, setRights] = useState(false);
  const [cancelReason, setCancelReason] = useState('');
  const generation = useRef(0);
  const receiptId = query.get('receipt'),
    versionId = query.get('version'),
    protocolId = query.get('protocol'),
    comparisonId = query.get('comparison');
  const bankSearch = query.get('bank_search') || '',
    sourceClass = query.get('source_class') || '';
  const libraryFilters =
    (bankSearch ? '&q=' + encodeURIComponent(bankSearch) : '') +
    (sourceClass ? '&classification=' + encodeURIComponent(sourceClass) : '');
  const select = useCallback(
    (key: string, id: string) => {
      const next = new URLSearchParams();
      next.set(key, id);
      router.replace(pathname + '?' + next.toString());
    },
    [pathname, router],
  );
  const act = async (action: () => Promise<void>) => {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await action();
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const loadLibrary = useCallback(
    async (after?: string) => {
      const result = await benchmarkGet<{ items: BenchmarkReceipt[]; next_cursor: string | null }>(
        base,
        '/library?limit=25' + libraryFilters + (after ? '&after=' + encodeURIComponent(after) : ''),
      );
      setItems((current) =>
        after
          ? [
              ...current,
              ...result.items.filter(
                (item) => !current.some((old) => old.receipt_id === item.receipt_id),
              ),
            ]
          : result.items,
      );
      setCursor(result.next_cursor);
    },
    [base, libraryFilters],
  );
  useEffect(() => {
    const current = ++generation.current;
    setError('');
    setReceipt(null);
    setVersion(null);
    setProtocol(null);
    setComparison(null);
    setReadiness(null);
    setBuildId('');
    void (async () => {
      try {
        const library = await benchmarkGet<{
          items: BenchmarkReceipt[];
          next_cursor: string | null;
        }>(base, '/library?limit=25' + libraryFilters);
        if (current !== generation.current) return;
        setItems(library.items);
        setCursor(library.next_cursor);
        if (receiptId) {
          const value = await benchmarkGet<BenchmarkReceipt>(
            base,
            '/imports/' + encodeURIComponent(receiptId),
          );
          if (current !== generation.current) return;
          setReceipt(value);
          const build =
            value.latest_build ||
            library.items.find((item) => item.receipt_id === receiptId)?.latest_build;
          if (build) {
            setBuildId(build.build_id);
            const ready = await benchmarkGet<BenchmarkReadiness>(
              base,
              '/builds/' + build.build_id + '/readiness',
            );
            if (current === generation.current) setReadiness(ready);
          }
        }
        if (protocolId) {
          const value = await benchmarkGet<Protocol>(
            base,
            '/protocols/' + encodeURIComponent(protocolId),
          );
          if (current !== generation.current) return;
          setProtocol(value);
          const ready = await benchmarkGet<BenchmarkReadiness>(
            base,
            '/protocols/' + value.protocol_revision_id + '/readiness',
          );
          if (current === generation.current) setReadiness(ready);
        }
        if (versionId) {
          const value = await benchmarkGet<Version>(
            base,
            '/versions/' + encodeURIComponent(versionId),
          );
          if (current !== generation.current) return;
          setVersion(value);
          const configurations = await workspaceApi(base + '/workspace/models?current_only=true');
          if (current === generation.current)
            setModels(
              configurations.items.filter(
                (model: ModelConfiguration) => model.is_current && model.status !== 'disabled',
              ),
            );
        }
        if (comparisonId) {
          const value = await benchmarkGet<BenchmarkComparison>(
            base,
            '/comparisons/' + encodeURIComponent(comparisonId),
          );
          if (current === generation.current) setComparison(value);
        }
      } catch (failure) {
        if (current === generation.current) setError((failure as Error).message);
      }
    })();
    return () => {
      generation.current++;
    };
  }, [base, receiptId, versionId, protocolId, comparisonId, libraryFilters]);
  useEffect(() => {
    if (!comparisonId) return;
    let active = true;
    const timer = window.setInterval(() => {
      void benchmarkGet<BenchmarkComparison>(
        base,
        '/comparisons/' + encodeURIComponent(comparisonId),
      )
        .then((value) => {
          if (active) {
            setComparison(value);
            setError('');
          }
        })
        .catch(() => {
          if (active)
            setError(
              'Connection interrupted. Showing the last confirmed state; reconnecting automatically.',
            );
        });
    }, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [base, comparisonId]);
  const submitBuild = (event: FormEvent) => {
    event.preventDefault();
    void act(async () => {
      if (!receipt) return;
      const value = await benchmarkPost<{ build_id: string }>(
        base,
        '/imports/' + receipt.receipt_id + '/build',
        { expected_manifest_sha256: receipt.manifest_sha256, review_id: reviewId },
      );
      setBuildId(value.build_id);
      setReadiness(await benchmarkGet(base, '/builds/' + value.build_id + '/readiness'));
      setMessage('Package build saved. Qualification is a separate action.');
    });
  };
  return (
    <div aria-busy={busy}>
      <section className={styles.panel}>
        <h1>Benchmarks</h1>
        <p>Versioned Praxis task banks, qualified Harbor packages and inspectable comparisons.</p>
        <p>
          Paid candidate and judge calls remain disabled. Source authenticity is not execution
          approval.
        </p>
        <button type="button" disabled={busy} onClick={() => void act(() => loadLibrary())}>
          Refresh library
        </button>
        <form
          key={bankSearch + ':' + sourceClass}
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            const filters = new URLSearchParams();
            if (data.get('bank_search'))
              filters.set('bank_search', String(data.get('bank_search')));
            if (data.get('source_class'))
              filters.set('source_class', String(data.get('source_class')));
            router.replace(pathname + (filters.size ? '?' + filters.toString() : ''));
          }}
        >
          <label>
            Find a task bank <input name="bank_search" maxLength={100} defaultValue={bankSearch} />
          </label>
          <label>
            Source classification{' '}
            <select name="source_class" defaultValue={sourceClass}>
              <option value="">All classifications</option>
              <option value="original_synthetic_fixture">Original fictional fixture</option>
              <option value="partner_restricted">Restricted partner source</option>
              <option value="public_licensed">Public licensed source</option>
            </select>
          </label>
          <button disabled={busy}>Search task banks</button>
        </form>
      </section>
      {error && <p role="alert">{error}</p>}
      <p role="status" aria-live="polite">
        {busy ? 'Working…' : message}
      </p>
      <BenchmarkLibrary
        items={items}
        busy={busy}
        select={(id) => select('receipt', id)}
        more={cursor ? () => void act(() => loadLibrary(cursor)) : null}
      />
      <BenchmarkImport
        busy={busy}
        canWrite={canWrite}
        submit={(file, key) =>
          act(async () => {
            const value = await uploadBenchmark(base, file, key);
            select('receipt', value.receipt_id);
          })
        }
      />
      <BenchmarkHistory base={base} select={(id) => select('comparison', id)} />
      {receipt && (
        <section className={styles.panel} aria-label="Source and qualification">
          <h2>
            {receipt.bank_id} · {receipt.bank_version}
          </h2>
          <p>
            {receipt.task_count} tasks · {receipt.source_classification} · signature{' '}
            {receipt.signature_status} · {receipt.source_state}
          </p>
          <a href={'/api/v1' + benchmarkPath(base) + '/imports/' + receipt.receipt_id + '/errors'}>
            Inspect redacted validation findings
          </a>
          <details>
            <summary>Record an assigned source-rights review</summary>
            <p>
              An administrator with a current individual assignment must supply existing review
              evidence. This records a human decision; importing a file does not approve it.
            </p>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void act(async () => {
                  const value = await benchmarkPost<{ review_id: string }>(
                    base,
                    '/imports/' + receipt.receipt_id + '/reviews',
                    {
                      expected_manifest_sha256: receipt.manifest_sha256,
                      evidence_artifact_id: evidence,
                      rights_confirmed: rights,
                      expires_at: new Date(reviewExpiry).toISOString(),
                    },
                  );
                  setReviewId(value.review_id);
                  setMessage('Source-rights review recorded.');
                });
              }}
            >
              <label>
                Existing review evidence reference{' '}
                <input
                  required
                  value={evidence}
                  onChange={(event) => setEvidence(event.target.value)}
                />
              </label>
              <label>
                Review expires{' '}
                <input
                  required
                  type="datetime-local"
                  value={reviewExpiry}
                  onChange={(event) => setReviewExpiry(event.target.value)}
                />
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={rights}
                  onChange={(event) => setRights(event.target.checked)}
                />
                I confirm the source processing rights documented in this evidence.
              </label>
              <button disabled={busy || !canAdmin || !rights}>Record source review</button>
              {!canAdmin && (
                <p>A project administrator with a current assignment records source rights.</p>
              )}
            </form>
          </details>
          <form onSubmit={submitBuild}>
            <label>
              Current source-rights review reference{' '}
              <input
                required
                value={reviewId}
                onChange={(event) => setReviewId(event.target.value)}
                disabled={busy || !canWrite}
              />
            </label>
            <button disabled={busy || !canWrite || !reviewId}>Build reviewed source</button>
          </form>
          {readiness && (
            <>
              <h3>Qualification: {readiness.state || 'Pending'}</h3>
              <Blockers items={readiness.blockers} />
              <button
                disabled={busy || !canAdmin || !buildId}
                onClick={() =>
                  void act(async () => {
                    const operation = await benchmarkPost<{ operation_id: string }>(
                      base,
                      '/builds/' + buildId + '/qualify',
                      { expected_subject_sha256: readiness.subject_sha256 },
                    );
                    setMessage('Qualification queued: ' + operation.operation_id);
                  })
                }
              >
                Request native qualification
              </button>
              <button
                disabled={busy || !buildId}
                onClick={() =>
                  void act(async () =>
                    setReadiness(await benchmarkGet(base, '/builds/' + buildId + '/readiness')),
                  )
                }
              >
                Refresh qualification
              </button>
              <button
                disabled={busy || !canWrite || !readiness.software_qualified}
                onClick={() =>
                  void act(async () => {
                    const value = await benchmarkPost<Version>(
                      base,
                      '/builds/' + buildId + '/freeze',
                      { expected_subject_sha256: readiness.subject_sha256 },
                    );
                    select('version', value.benchmark_revision_id);
                  })
                }
              >
                Freeze qualified version
              </button>
            </>
          )}
        </section>
      )}
      {version && (
        <>
          <BenchmarkVersion version={version} />
          <BenchmarkProtocol
            models={models}
            base={base}
            version={version}
            busy={busy}
            canWrite={canWrite}
            freeze={(ids, expires, policy) =>
              act(async () => {
                const value = await benchmarkPost<Protocol>(base, '/protocols', {
                  benchmark_revision_id: version.benchmark_revision_id,
                  expected_benchmark_sha256: version.subject_sha256,
                  slots: ids.map((id) => ({
                    connection_id: id,
                    transport: 'offline_contract',
                    configuration_sha256: models.find((model) => model.id === id)!.config_hash,
                  })),
                  expires_at: new Date(expires).toISOString(),
                  review_policy: policy,
                });
                select('protocol', value.protocol_revision_id);
              })
            }
          />
        </>
      )}
      {protocol && (
        <section className={styles.panel} aria-label="Frozen protocol">
          <h2>Frozen protocol</h2>
          <p>{protocol.protocol.origin} · two repetitions · up to three active trials</p>
          <Blockers items={readiness?.blockers || []} />
          <button
            disabled={busy || !canAdmin || !readiness?.ready}
            onClick={() =>
              void act(async () => {
                const value = await benchmarkPost<BenchmarkComparison>(
                  base,
                  '/protocols/' + protocol.protocol_revision_id + '/launch',
                  { expected_subject_sha256: protocol.subject_sha256 },
                );
                select('comparison', value.run_id);
              })
            }
          >
            Launch offline software comparison
          </button>
          <button
            disabled={busy}
            onClick={() =>
              void act(async () =>
                setReadiness(
                  await benchmarkGet(
                    base,
                    '/protocols/' + protocol.protocol_revision_id + '/readiness',
                  ),
                ),
              )
            }
          >
            Recheck admission
          </button>
        </section>
      )}
      {comparison && (
        <>
          <BenchmarkMatrix comparison={comparison} base={base} />
          <BenchmarkResults comparison={comparison} base={base} />
          <BenchmarkScoreReview
            key={comparison.run_id}
            base={base}
            runId={comparison.run_id}
            canWrite={canWrite}
            userId={userId}
            comparison={comparison}
          />
          <BenchmarkRecovery
            base={base}
            comparison={comparison}
            canAdmin={canAdmin}
            changed={setComparison}
          />
          <section className={styles.panel}>
            <h2>Cancel remaining work</h2>
            <p>Cancellation preserves completed evidence and ambiguous-dispatch reservations.</p>
            <label>
              Reason{' '}
              <input
                value={cancelReason}
                onChange={(event) => setCancelReason(event.target.value)}
              />
            </label>
            <button
              disabled={busy || !canWrite || cancelReason.trim().length < 10}
              onClick={() =>
                void act(async () => {
                  setComparison(
                    await benchmarkPost(base, '/comparisons/' + comparison.run_id + '/cancel', {
                      expected_subject_sha256: comparison.subject_sha256,
                      rationale: cancelReason,
                    }),
                  );
                })
              }
            >
              Cancel comparison
            </button>
          </section>
        </>
      )}
    </div>
  );
}
