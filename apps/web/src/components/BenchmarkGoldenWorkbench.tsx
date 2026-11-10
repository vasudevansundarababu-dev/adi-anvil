'use client';

import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { benchmarkGet, benchmarkPost } from '../lib/benchmark';
import { DashboardSnapshot, dashboardSnapshotQuery } from '../lib/benchmark-dashboard';
import {
  GoldenDataset,
  GoldenPage,
  GoldenVersion,
  RemediationProposal,
  goldenDraftSource,
} from '../lib/benchmark-golden';
import {
  WorkbenchAvailability,
  WorkbenchEmpty,
  WorkbenchPanel,
  WorkbenchStatus,
  WorkbenchMetric,
} from './BenchmarkWorkbenchUI';
import styles from './BenchmarkWorkbench.module.css';

const personas = [
  ['prompt_injection', 'Prompt injection attempt'],
  ['customer_urgency', 'Customer urgency / emotional pressure'],
  ['contradictory_instructions', 'Contradictory instructions'],
  ['repetitive_loop', 'Repetitive loop attack'],
] as const;

export default function BenchmarkGoldenWorkbench({
  base,
  data,
  canWrite,
  canAdmin,
  userId,
  onStored,
}: {
  base: string;
  data: DashboardSnapshot;
  canWrite: boolean;
  canAdmin: boolean;
  userId: string;
  onStored: () => void;
}) {
  const [datasets, setDatasets] = useState<GoldenDataset[]>([]),
    [datasetCursor, setDatasetCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState(''),
    [versions, setVersions] = useState<GoldenVersion[]>([]),
    [versionCursor, setVersionCursor] = useState<string | null>(null);
  const [proposals, setProposals] = useState<RemediationProposal[]>([]),
    [proposalCursor, setProposalCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(true),
    [error, setError] = useState(''),
    [message, setMessage] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [datasetName, setDatasetName] = useState(''),
    [description, setDescription] = useState('');
  const [archiveRationale, setArchiveRationale] = useState('');
  const selectedDataset = datasets.find((dataset) => dataset.id === selected);
  const canArchive =
    !!selectedDataset &&
    !selectedDataset.archived &&
    (canAdmin || selectedDataset.created_by === userId);
  const canWriteCase = !!selectedDataset && !selectedDataset.archived && canWrite;
  const [caseKey, setCaseKey] = useState(''),
    [title, setTitle] = useState(''),
    [category, setCategory] = useState('task_correctness');
  const [input, setInput] = useState(''),
    [expected, setExpected] = useState(''),
    [task, setTask] = useState('FX-001'),
    [buildId, setBuildId] = useState('');
  const [persona, setPersona] = useState<string>('prompt_injection'),
    [proposalTitle, setProposalTitle] = useState(''),
    [rationale, setRationale] = useState(''),
    [prompt, setPrompt] = useState('');
  const [predecessor, setPredecessor] = useState(''),
    [inspected, setInspected] = useState<GoldenVersion | null>(null);
  const [assignment, setAssignment] = useState(''),
    [evidence, setEvidence] = useState(''),
    [evidenceHash, setEvidenceHash] = useState(''),
    [reviewRationale, setReviewRationale] = useState(''),
    [humanReviewed, setHumanReviewed] = useState(false),
    [decision, setDecision] = useState('verified');
  const generation = useRef(0);
  const contextQuery = dashboardSnapshotQuery(data.context).toString();
  const cohortFocused =
    data.context.model.length > 0 ||
    data.context.task !== 'all' ||
    data.context.period !== 'all' ||
    data.context.environment !== 'all' ||
    !!(
      data.context.run_id ||
      data.context.score_revision_id ||
      data.context.trace_id ||
      data.context.cluster
    );
  const contextSuffix = contextQuery ? '&' + contextQuery : '';
  const anchorTrace = data.traces.find((trace) => trace.id === data.context.trace_id);
  const source = goldenDraftSource(anchorTrace, buildId);
  useEffect(() => {
    const taskId = anchorTrace?.task_label.match(/\bFX-00[123]\b/)?.[0];
    if (taskId) setTask(taskId);
  }, [anchorTrace?.id, anchorTrace?.task_label]);

  const load = useCallback(async () => {
    const request = ++generation.current;
    setBusy(true);
    setError('');
    setInspected(null);
    setVersions([]);
    setSelected('');
    setVersionCursor(null);
    try {
      const [banks, intents] = await Promise.all([
        benchmarkGet<GoldenPage<GoldenDataset>>(base, '/golden-datasets?limit=25'),
        benchmarkGet<GoldenPage<RemediationProposal>>(
          base,
          '/remediation?limit=25' + contextSuffix,
        ),
      ]);
      if (request === generation.current) {
        setDatasets(banks.items);
        setDatasetCursor(banks.next_cursor);
        setProposals(intents.items);
        setProposalCursor(intents.next_cursor);
        setLoaded(true);
      }
    } catch (failure) {
      if (request === generation.current) {
        setDatasets([]);
        setProposals([]);
        setVersions([]);
        setInspected(null);
        setLoaded(false);
        setError((failure as Error).message);
      }
    } finally {
      if (request === generation.current) setBusy(false);
    }
  }, [base, contextSuffix]);
  useEffect(() => {
    void load();
    return () => {
      generation.current++;
    };
  }, [load]);
  async function act(operation: () => Promise<void>) {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      await operation();
    } catch (failure) {
      setError((failure as Error).message);
      setInspected(null);
      if ([401, 403, 404, 409].includes((failure as Error & { status?: number }).status || 0)) {
        setLoaded(false);
        setDatasets([]);
        setVersions([]);
        setProposals([]);
      }
    } finally {
      setBusy(false);
    }
  }
  async function versionList(datasetId: string, after?: string) {
    const page = await benchmarkGet<GoldenPage<GoldenVersion>>(
      base,
      '/golden-datasets/' +
        encodeURIComponent(datasetId) +
        '/versions?limit=25' +
        contextSuffix +
        (after ? '&after=' + encodeURIComponent(after) : ''),
    );
    setVersions((old) =>
      after
        ? [...old, ...page.items.filter((item) => !old.some((current) => current.id === item.id))]
        : page.items,
    );
    setVersionCursor(page.next_cursor);
  }
  async function chooseDataset(datasetId: string) {
    setSelected(datasetId);
    setVersions([]);
    setInspected(null);
    setPredecessor('');
    if (datasetId) await versionList(datasetId);
  }
  function saveDataset(event: FormEvent) {
    event.preventDefault();
    void act(async () => {
      const item = await benchmarkPost<GoldenDataset>(base, '/golden-datasets', {
        name: datasetName,
        description,
      });
      setDatasets((old) => [item, ...old]);
      setSelected(item.id);
      setVersions([]);
      setMessage('Dataset metadata saved. No case or verification was created.');
      onStored();
      setDatasetName('');
      setDescription('');
    });
  }
  function saveVersion(event: FormEvent) {
    event.preventDefault();
    void act(async () => {
      const version = await benchmarkPost<GoldenVersion>(
        base,
        '/golden-datasets/' + encodeURIComponent(selected) + '/versions',
        {
          case_key: caseKey,
          title,
          category,
          input_text: input,
          expected_output: expected,
          fictional_task_id: task,
          ...source,
          predecessor_id: predecessor || null,
        },
      );
      setMessage(
        `Immutable case revision ${version.revision} (${version.id}) saved with status ${version.status}. Human verification remains separate; current context filters may exclude unbound drafts.`,
      );
      onStored();
      await versionList(selected);
      setInput('');
      setExpected('');
      setPredecessor('');
    });
  }
  function archiveDataset(event: FormEvent) {
    event.preventDefault();
    if (!canArchive || archiveRationale.trim().length < 10) return;
    void act(async () => {
      await benchmarkPost(base, '/golden-datasets/' + encodeURIComponent(selected) + '/archive', {
        rationale: archiveRationale.trim(),
      });
      setDatasets((old) =>
        old.map((dataset) => (dataset.id === selected ? { ...dataset, archived: true } : dataset)),
      );
      setArchiveRationale('');
      setMessage(
        'Dataset archived. Immutable history is preserved; qualification and approvals are unchanged.',
      );
      onStored();
    });
  }
  function saveProposal(event: FormEvent) {
    event.preventDefault();
    void act(async () => {
      const item = await benchmarkPost<RemediationProposal>(base, '/remediation', {
        title: proposalTitle,
        persona,
        rationale,
        proposed_prompt: prompt,
        fictional_task_id: task,
        ...source,
        offline_only: true,
      });
      onStored();
      const page = await benchmarkGet<GoldenPage<RemediationProposal>>(
        base,
        '/remediation?limit=25' + contextSuffix,
      );
      setProposals(page.items);
      setProposalCursor(page.next_cursor);
      setMessage(
        `Remediation proposal ${item.id} saved. No prompt was applied and no provider was called. Context filters may exclude unbound drafts.`,
      );
      setPrompt('');
    });
  }
  function verify(event: FormEvent) {
    event.preventDefault();
    if (!inspected) return;
    void act(async () => {
      const item = await benchmarkPost<GoldenVersion>(
        base,
        '/golden-versions/' + encodeURIComponent(inspected.id) + '/verification',
        {
          assignment_id: assignment,
          evidence_artifact_id: evidence,
          evidence_sha256: evidenceHash,
          expected_content_sha256: inspected.content_sha256,
          decision,
          human_reviewed: humanReviewed,
          rationale: reviewRationale,
        },
      );
      setInspected(item);
      onStored();
      setVersions((old) => old.map((version) => (version.id === item.id ? item : version)));
      setHumanReviewed(false);
      setMessage(
        'Explicit human verification decision recorded. Original revisions remain unchanged.',
      );
    });
  }
  return (
    <>
      <div className={styles.actions} style={{ marginBottom: 16 }}>
        <button type="button" disabled={busy} onClick={() => void load()}>
          Refresh saved proposals & datasets
        </button>
        <span className={styles.muted}>
          Project dataset metadata · cases and proposals follow the selected context. Changing
          context resets unsaved draft fields.
        </span>
      </div>
      {error && (
        <p role="alert" className={styles.alert}>
          {error}
        </p>
      )}
      {message && (
        <p role="status" className={styles.message}>
          {message}
        </p>
      )}
      <aside className={styles.provenance}>
        <strong>Human-controlled remediation</strong>
        <span>
          {source.source_anchor
            ? `Selected evidence: ${anchorTrace?.label}. New records bind this actual comparison cell.`
            : source.source_trace_id
              ? `Selected historical software control: ${anchorTrace?.label}. Drafts preserve this trace reference, but it grants no current source authority or verification eligibility.`
              : 'No eligible comparison cell selected. Manual case drafts may be saved, but missing source anchors remain explicit verification blockers.'}{' '}
          Historical controls never become manufactured comparison cells.
        </span>
      </aside>
      <div className={styles.cards}>
        <WorkbenchMetric
          label={cohortFocused ? 'COHORT DATASETS' : 'DATASET METADATA'}
          value={data.curation?.datasets ?? 'Unavailable'}
          note={
            cohortFocused
              ? 'Datasets with matching case revisions in this context; registry below is project-wide.'
              : 'Stored project dataset registry; no execution implied.'
          }
        />
        <WorkbenchMetric
          label="COHORT CASE REVISIONS"
          value={data.curation?.case_versions ?? 'Unavailable'}
          note="Immutable cases matched to this selected context."
        />
        <WorkbenchMetric
          label="STORED VERIFIED CASES"
          value={data.curation?.verified_cases ?? 'Unavailable'}
          note="Actual human decisions, not a regression pass rate."
        />
        <WorkbenchMetric
          label="BLOCKED OFFLINE INTENTS"
          value={data.curation?.blocked_intents ?? 'Unavailable'}
          note="Recorded intentions are not executed or passed tests."
        />
      </div>
      <div className={styles.equalGrid}>
        <WorkbenchPanel title="Adversarial persona proposal" note="Offline intent only">
          <form className={styles.form} onSubmit={saveProposal}>
            <label className={styles.field}>
              Proposal title
              <input
                required
                maxLength={160}
                value={proposalTitle}
                onChange={(event) => setProposalTitle(event.target.value)}
                disabled={!canWrite || busy}
              />
            </label>
            <label className={styles.field}>
              Persona scenario
              <select
                value={persona}
                onChange={(event) => setPersona(event.target.value)}
                disabled={!canWrite || busy}
              >
                {personas.map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              Fictional control task
              <select
                value={task}
                onChange={(event) => setTask(event.target.value)}
                disabled={!canWrite || busy || !!anchorTrace}
              >
                {['FX-001', 'FX-002', 'FX-003'].map((id) => (
                  <option key={id}>{id}</option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              Source build reference (optional, exact UUID)
              <input
                value={buildId}
                onChange={(event) => setBuildId(event.target.value)}
                disabled={!canWrite || busy || !!source.source_trace_id}
              />
            </label>
            <label className={styles.field}>
              Evidence-based rationale
              <textarea
                required
                minLength={10}
                maxLength={2000}
                value={rationale}
                onChange={(event) => setRationale(event.target.value)}
                disabled={!canWrite || busy}
              />
            </label>
            <label className={styles.field}>
              Proposed prompt change (saved only)
              <textarea
                value={prompt}
                maxLength={8192}
                onChange={(event) => setPrompt(event.target.value)}
                disabled={!canWrite || busy}
              />
            </label>
            <p className={styles.muted}>
              No persona execution, model request, code edit or prompt deployment occurs when a
              proposal is saved.
            </p>
            <button className={styles.primary} disabled={!canWrite || busy}>
              Save immutable proposal
            </button>
          </form>
        </WorkbenchPanel>
        <WorkbenchAvailability
          title="Regression pass rate"
          state="Not run"
          reason="No compatible, executed golden-regression cohort is stored. Verified case counts are not a pass rate, and queued or blocked intentions never count as successful tests."
        />
      </div>
      <WorkbenchPanel title="Remediation proposal registry" note="Actual persisted proposals">
        {proposals.length ? (
          <div className={styles.tableWrap}>
            <table>
              <caption>
                Project proposals; selected trace context is preserved in their immutable anchors
              </caption>
              <thead>
                <tr>
                  <th>Proposal / persona</th>
                  <th>State</th>
                  <th>Authority</th>
                  <th>Offline execution intent</th>
                </tr>
              </thead>
              <tbody>
                {proposals.map((proposal) => (
                  <tr key={proposal.id}>
                    <td>
                      {proposal.content.title}
                      <small>{proposal.content.persona.replaceAll('_', ' ')}</small>
                      <small>
                        {proposal.content.source_anchor
                          ? `Cell ${proposal.content.source_anchor.cell_id}`
                          : proposal.content.source_trace_id
                            ? `Historical trace ${proposal.content.source_trace_id} · no current authority`
                            : 'Unbound draft'}
                      </small>
                    </td>
                    <td>
                      <WorkbenchStatus>{proposal.state}</WorkbenchStatus>
                    </td>
                    <td>
                      {proposal.provider_calls} provider calls
                      <small>Auto-applied: {String(proposal.auto_applied)}</small>
                    </td>
                    <td>
                      <button
                        disabled={busy || !canWrite}
                        onClick={() =>
                          void act(async () => {
                            const value = await benchmarkPost<RemediationProposal>(
                              base,
                              '/remediation/' + encodeURIComponent(proposal.id) + '/run-intents',
                              {
                                expected_content_sha256: proposal.content_sha256,
                                offline_only: true,
                                max_steps: 10,
                                max_output_bytes: 8192,
                              },
                            );
                            onStored();
                            setProposals((old) =>
                              old.map((item) => (item.id === value.id ? value : item)),
                            );
                            setMessage(
                              'Offline execution intention recorded. Inspect its actual status; recording an intent does not execute or pass a test.',
                            );
                          })
                        }
                      >
                        Record bounded offline intent
                      </button>
                      {proposal.run_intents.length > 0 && (
                        <details>
                          <summary>
                            {proposal.run_intents.length} stored intents ·{' '}
                            {proposal.run_intents[proposal.run_intents.length - 1].state}
                          </summary>
                          <p className={styles.muted}>
                            {proposal.run_intents[proposal.run_intents.length - 1].code.replaceAll(
                              '_',
                              ' ',
                            )}
                            . No execution success is inferred.
                          </p>
                          <pre className={styles.code}>
                            {JSON.stringify(proposal.run_intents, null, 2)}
                          </pre>
                        </details>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <WorkbenchEmpty
            title={
              loaded
                ? 'No remediation proposals'
                : busy
                  ? 'Loading saved proposals'
                  : 'Proposal registry unavailable'
            }
          >
            {loaded
              ? 'Select an observed failure or write a human-authored fictional proposal. Nothing is generated or applied automatically.'
              : 'Awaiting the authorized stored proposal registry. No execution or successful test is inferred.'}
          </WorkbenchEmpty>
        )}
        {proposalCursor && (
          <div className={styles.panelBody}>
            <button
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  const page = await benchmarkGet<GoldenPage<RemediationProposal>>(
                    base,
                    '/remediation?limit=25' +
                      contextSuffix +
                      '&after=' +
                      encodeURIComponent(proposalCursor),
                  );
                  setProposals((old) => [
                    ...old,
                    ...page.items.filter((item) => !old.some((current) => current.id === item.id)),
                  ]);
                  setProposalCursor(page.next_cursor);
                })
              }
            >
              Load more proposals
            </button>
          </div>
        )}
      </WorkbenchPanel>
      <div style={{ height: 20 }} />
      <div className={styles.equalGrid}>
        <WorkbenchPanel title="Golden dataset registry" note="Human-reviewed anchors">
          <form className={styles.form} onSubmit={saveDataset}>
            <label className={styles.field}>
              New dataset name
              <input
                required
                maxLength={160}
                value={datasetName}
                onChange={(event) => setDatasetName(event.target.value)}
                disabled={!canWrite || busy}
              />
            </label>
            <label className={styles.field}>
              Description
              <textarea
                maxLength={2000}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                disabled={!canWrite || busy}
              />
            </label>
            <button disabled={!canWrite || busy}>Create dataset metadata</button>
          </form>
          <div className={styles.panelBody}>
            <label className={styles.field}>
              Choose a stored dataset
              <select
                value={selected}
                disabled={busy}
                onChange={(event) => void act(() => chooseDataset(event.target.value))}
              >
                <option value="">Select dataset</option>
                {datasets.map((dataset) => (
                  <option value={dataset.id} key={dataset.id}>
                    {dataset.name}
                    {dataset.archived ? ' · archived' : ''}
                  </option>
                ))}
              </select>
            </label>
            {!datasets.length && (
              <p>
                {loaded
                  ? 'No golden datasets are stored for this project.'
                  : 'Awaiting the authorized dataset registry.'}
              </p>
            )}
            {datasetCursor && (
              <button
                disabled={busy}
                onClick={() =>
                  void act(async () => {
                    const page = await benchmarkGet<GoldenPage<GoldenDataset>>(
                      base,
                      '/golden-datasets?limit=25&after=' + encodeURIComponent(datasetCursor),
                    );
                    setDatasets((old) => [
                      ...old,
                      ...page.items.filter(
                        (item) => !old.some((current) => current.id === item.id),
                      ),
                    ]);
                    setDatasetCursor(page.next_cursor);
                  })
                }
              >
                Load more datasets
              </button>
            )}
          </div>
          {canArchive && (
            <form className={styles.form} onSubmit={archiveDataset}>
              <label className={styles.field}>
                Archive rationale
                <textarea
                  required
                  minLength={10}
                  maxLength={2000}
                  value={archiveRationale}
                  onChange={(event) => setArchiveRationale(event.target.value)}
                  disabled={busy}
                />
              </label>
              <p className={styles.muted}>
                Archiving preserves immutable history and changes no qualification or approval. New
                case revisions will be disabled.
              </p>
              <button disabled={busy || archiveRationale.trim().length < 10}>
                Archive dataset
              </button>
            </form>
          )}
        </WorkbenchPanel>
        <WorkbenchPanel
          title="Author a golden case revision"
          note="Draft until independently verified"
        >
          <form className={styles.form} onSubmit={saveVersion}>
            <label className={styles.field}>
              Case key
              <input
                required
                pattern="[A-Za-z0-9][A-Za-z0-9_.-]{0,79}"
                value={caseKey}
                onChange={(event) => setCaseKey(event.target.value)}
                disabled={!canWriteCase || busy}
              />
            </label>
            <label className={styles.field}>
              Case title
              <input
                required
                maxLength={160}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                disabled={!canWriteCase || busy}
              />
            </label>
            <label className={styles.field}>
              Category
              <select
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                disabled={!canWriteCase || busy}
              >
                {['safety', 'factuality', 'tone', 'latency', 'task_correctness'].map((value) => (
                  <option key={value} value={value}>
                    {value.replaceAll('_', ' ')}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              Authorized fictional input
              <textarea
                required
                maxLength={16384}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                disabled={!canWriteCase || busy}
              />
            </label>
            <label className={styles.field}>
              Human-authored expected output
              <textarea
                required
                maxLength={16384}
                value={expected}
                onChange={(event) => setExpected(event.target.value)}
                disabled={!canWriteCase || busy}
              />
            </label>
            <label className={styles.field}>
              Predecessor revision (optional)
              <select
                value={predecessor}
                onChange={(event) => setPredecessor(event.target.value)}
                disabled={!canWriteCase || busy}
              >
                <option value="">New case anchor</option>
                {versions
                  .filter((version) => version.case_key === caseKey)
                  .map((version) => (
                    <option key={version.id} value={version.id}>
                      {version.case_key} · revision {version.revision}
                    </option>
                  ))}
              </select>
            </label>
            <p className={styles.muted}>
              Task {task}.{' '}
              {source.source_trace_id
                ? `Historical trace ${source.source_trace_id}; no current source authority.`
                : `Source build ${source.source_build_id || 'not supplied'}.`}{' '}
              Expected output is never copied from a private grader. A draft is not verified and
              does not change existing task scoring.
            </p>
            <button className={styles.primary} disabled={!canWriteCase || busy}>
              Save immutable case revision
            </button>
          </form>
        </WorkbenchPanel>
      </div>
      <WorkbenchPanel title="Golden case history" note="Immutable content and verification state">
        {versions.length ? (
          <div className={styles.tableWrap}>
            <table>
              <caption>Authorized case revisions for the selected dataset</caption>
              <thead>
                <tr>
                  <th>Case / revision</th>
                  <th>Category</th>
                  <th>Status</th>
                  <th>Author</th>
                  <th>Inspection</th>
                </tr>
              </thead>
              <tbody>
                {versions.map((version) => (
                  <tr key={version.id}>
                    <td>
                      {version.case_key}
                      <small>
                        Revision {version.revision} · {version.content.title}
                      </small>
                    </td>
                    <td>{version.content.category}</td>
                    <td>
                      <WorkbenchStatus
                        tone={
                          version.status === 'verified'
                            ? 'success'
                            : version.status === 'rejected'
                              ? 'danger'
                              : 'warning'
                        }
                      >
                        {version.status}
                      </WorkbenchStatus>
                      <small>{version.permissions.verification_blockers.join(' · ')}</small>
                    </td>
                    <td>{version.created_by === userId ? 'You' : version.created_by}</td>
                    <td>
                      <button
                        disabled={busy}
                        onClick={() =>
                          void act(async () => {
                            const value = await benchmarkGet<GoldenVersion>(
                              base,
                              '/golden-versions/' +
                                encodeURIComponent(version.id) +
                                (contextQuery ? '?' + contextQuery : ''),
                            );
                            setInspected(value);
                            setHumanReviewed(false);
                          })
                        }
                      >
                        Inspect authorized revision
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <WorkbenchEmpty title={selected ? 'No authorized case versions' : 'Choose a dataset'}>
            Golden verification remains an explicit independent human decision. No Verified records
            are seeded to fill this table.
          </WorkbenchEmpty>
        )}
        {versionCursor && (
          <div className={styles.panelBody}>
            <button
              disabled={busy}
              onClick={() => void act(() => versionList(selected, versionCursor))}
            >
              Load more case history
            </button>
          </div>
        )}
      </WorkbenchPanel>
      {inspected && (
        <div className={styles.panelBody}>
          <WorkbenchPanel
            title={`Case ${inspected.case_key} · revision ${inspected.revision}`}
            note={inspected.status}
          >
            <div className={styles.panelBody}>
              <p className={styles.identifier}>Content SHA-256 {inspected.content_sha256}</p>
              <p className={styles.identifier}>
                {inspected.content.source_trace_id
                  ? `Historical source trace: ${inspected.content.source_trace_id}. It does not grant current source authority.`
                  : inspected.source_build_id
                    ? `Exact source build: ${inspected.source_build_id}`
                    : 'No current source build is bound.'}
              </p>
              {inspected.content.historical_source_binding && (
                <details>
                  <summary>Immutable historical evidence anchor</summary>
                  <p className={styles.identifier}>
                    Task {inspected.content.historical_source_binding.task_id}
                    <br />
                    Artifact {inspected.content.historical_source_binding.artifact_id}
                    <br />
                    Source commit {inspected.content.historical_source_binding.source_commit}
                    <br />
                    Source record SHA-256{' '}
                    {inspected.content.historical_source_binding.source_record_sha256}
                    <br />
                    Current authority:{' '}
                    {String(inspected.content.historical_source_binding.current_authority)}
                  </p>
                </details>
              )}
              <h4>Authorized input</h4>
              <pre className={styles.code}>{inspected.content.input_text}</pre>
              <h4>Human-authored expected output</h4>
              <pre className={styles.code}>{inspected.content.expected_output}</pre>
              <p className={styles.muted}>
                Task scoring authority: {String(inspected.is_task_scoring_authority)}. This case is
                a regression anchor, not a replacement rubric.
              </p>
              {inspected.verification && (
                <p>
                  Recorded {inspected.verification.decision} by {inspected.verification.verifier_id}{' '}
                  at {new Date(inspected.verification.created_at).toLocaleString()}
                </p>
              )}
              {inspected.permissions.verification_blockers.map((blocker) => (
                <p key={blocker} className={styles.muted}>
                  {blocker.replaceAll('_', ' ')}
                </p>
              ))}
            </div>
            {inspected.status === 'draft' && (
              <form className={styles.form} onSubmit={verify}>
                <label className={styles.field}>
                  Current independent evaluation assignment
                  <input
                    required
                    value={assignment}
                    onChange={(event) => setAssignment(event.target.value)}
                    disabled={busy || !inspected.permissions.can_verify || !canWrite}
                  />
                </label>
                <label className={styles.field}>
                  Existing verification evidence artifact
                  <input
                    required
                    value={evidence}
                    onChange={(event) => setEvidence(event.target.value)}
                    disabled={busy || !inspected.permissions.can_verify || !canWrite}
                  />
                </label>
                <label className={styles.field}>
                  Evidence SHA-256
                  <input
                    required
                    pattern="[a-f0-9]{64}"
                    value={evidenceHash}
                    onChange={(event) => setEvidenceHash(event.target.value)}
                    disabled={busy || !inspected.permissions.can_verify || !canWrite}
                  />
                </label>
                <label className={styles.field}>
                  Decision
                  <select
                    value={decision}
                    onChange={(event) => setDecision(event.target.value)}
                    disabled={busy || !inspected.permissions.can_verify || !canWrite}
                  >
                    <option value="verified">Verify this exact case revision</option>
                    <option value="rejected">Reject this revision</option>
                  </select>
                </label>
                <label className={styles.field}>
                  Evidence-based rationale
                  <textarea
                    required
                    minLength={10}
                    value={reviewRationale}
                    onChange={(event) => setReviewRationale(event.target.value)}
                    disabled={busy || !inspected.permissions.can_verify || !canWrite}
                  />
                </label>
                <label className={styles.check}>
                  <input
                    type="checkbox"
                    checked={humanReviewed}
                    onChange={(event) => setHumanReviewed(event.target.checked)}
                    disabled={busy || !inspected.permissions.can_verify || !canWrite}
                  />
                  I personally inspected this exact content and its authorized source evidence.
                </label>
                <button
                  disabled={
                    busy || !canWrite || !inspected.permissions.can_verify || !humanReviewed
                  }
                >
                  Record immutable human decision
                </button>
              </form>
            )}
          </WorkbenchPanel>
        </div>
      )}
      <p className={styles.muted}>
        {canWrite
          ? 'Write access does not grant source rights, reviewer independence or execution authority.'
          : 'Your current role allows authorized inspection only.'}{' '}
        {canAdmin && 'Administrator access does not bypass independent verification.'}
      </p>
    </>
  );
}
