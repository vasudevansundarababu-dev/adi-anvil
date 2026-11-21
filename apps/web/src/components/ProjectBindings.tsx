'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import { bindingReads, structuredInputPanel } from '../lib/bindingReads';
import KycInputSetup from './KycInputSetup';
import TaskFlowViewer from './TaskFlowViewer';
import CustomPythonEditor from './CustomPythonEditor';
import SafetyPromptLibrary from './SafetyPromptLibrary';
import SafetySourcePicker, { SafetySourceRef, safetySourceKey } from './SafetySourcePicker';
import GovernedAiAssistant from './GovernedAiAssistant';
import ProjectInputData, { InputDraft, inputSelectionRequest } from './ProjectInputData';
import SkillWorkflowBinding, { SkillMapping, TaskStepOptions } from './SkillWorkflowBinding';
import s from './BenchmarkRunDashboard.module.css';

type Ref = { kind: string; id: string; sha256: string; target: string };
type Category = { id: string; prompts: { id: string; sha256: string }[] };
type Selection = Record<Section, Ref[]> & {
  safety_categories: Category[];
  method: string;
  execution_data?: { id: string; sha256: string } | null;
  skill_mappings?: SkillMapping[];
  safety_source?: SafetySourceRef | null;
};
type Section = 'workflow' | 'policy' | 'data' | 'rubric' | 'safety';
type Option = {
  id: string;
  sha256: string;
  name?: string;
  title?: string;
  kind?: string;
  adapter?: string;
  framework?: string;
  status?: string;
  mime_type?: string;
};
type SkillRequirement = {
  target: string;
  task_id: string;
  task_version: string;
  payload_sha256: string;
  id: string;
  skill_id: string;
  skill: string;
  skill_name?: string;
  capability_association?: string;
  design_step?: string;
  design_role?: string;
  role_mapping_status?: string;
  domain: string;
  role: string;
  step: string | null;
  step_status?: string;
  counting_unit?: string;
  official: boolean;
  criterion_id: string | null;
  maximum_contribution: number;
  scale: { kind: string; levels: number[]; maximum: number | null; unit: string };
  evidence_contract: string;
  existing_component: string;
  qualification_work: string;
  applicability: string;
  applicability_source: string;
  status: string;
  register_sha256: string;
  register_source_sha256: string;
};
type Options = {
  source_sha256: string;
  workflow_step_options?: TaskStepOptions[];
  execution_data_options?: {
    enabled: boolean;
    selected?: { id: string; sha256: string } | null;
    default_input: unknown;
    selected_selection?: {
      source_sha256: string;
      basis: { kind: string; input_id?: string; content_sha256?: string };
      sample: {
        sampling: {
          mode: InputDraft['mode'];
          count?: number | null;
          seed?: string | null;
          case_ids?: string[] | null;
        };
      };
    } | null;
  };
  descriptors: {
    skill_requirements?: SkillRequirement[];
    project: { display_id: number | null };
    policy_rules: {
      target: string;
      task_id: string;
      task_version?: string;
      payload_sha256?: string;
      rubric_criterion_ids?: string[];
      policy_id?: string;
      policy_version?: string;
      constraint_id?: string;
      requirement: string | null;
    }[];
    rubric_criteria: {
      target: string;
      task_id: string;
      task_version?: string;
      payload_sha256?: string;
      criterion_id: string;
      description?: string;
      points?: number;
      weight_bps?: number;
    }[];
  };
  frameworks: Option[];
  packages: Option[];
  environments: Option[];
  policy_sets: Option[];
  actor_inputs: Option[];
  approved_revisions: Option[];
  evaluators: Option[];
  methods?: {
    id: string;
    name: string;
    version?: string;
    compatible: boolean;
    runtime_qualified: boolean;
    sha256?: string;
    default?: boolean;
  }[];
  recommendations: {
    status: string;
    reason: string;
    items: {
      call_id: string;
      source_sha256: string;
      current_eligibility: boolean;
      output: {
        evaluators: { target: string; choices: { id: string; sha256: string; reason: string }[] }[];
        methods: { id: string; sha256: string; reason: string }[];
      };
    }[];
  };
};
type Binding = { id: string; version: number; snapshot_sha256: string; snapshot: Selection };
type Readiness = {
  status: string;
  ready: boolean;
  gaps: { section: string; code: string; target?: string }[];
};
function checkedReadiness(value: unknown): Readiness {
  const result = value as Partial<Readiness> | null;
  if (
    !result ||
    typeof result.status !== 'string' ||
    typeof result.ready !== 'boolean' ||
    !Array.isArray(result.gaps) ||
    result.gaps.some(
      (gap) => !gap || typeof gap.section !== 'string' || typeof gap.code !== 'string',
    )
  )
    throw new Error('The readiness response is incomplete. No execution readiness is confirmed.');
  return result as Readiness;
}
type Task = {
  task_id: string;
  task_version: string;
  title: string;
  actor: unknown;
  template?: {
    id?: string;
    profile_id?: string;
    catalog_workflow_name?: string | null;
    version?: string | number;
  } | null;
  rubric?: {
    criteria: { id: string; description: string; points?: number; weight_bps?: number }[];
  } | null;
  workflow?: unknown;
};
export type ImportedProject = {
  id: string;
  display_id?: number;
  name: string;
  source_version: string | null;
  tasks: Task[];
};
const tabs = [
  'Task Viewer',
  'Policy Binding to Evals',
  'Data & Environments',
  'Rubrics & Evaluators',
  'Trust & Safety',
];
const empty = (): Selection => ({
  workflow: [],
  policy: [],
  data: [],
  rubric: [],
  safety: [],
  safety_categories: [],
  method: 'task-rubric-v1',
});
const reason = (value: string) =>
  ({
    current_deployment_qualification_required:
      'Forge runtime qualification is pending for this deployment.',
    five_applicable_categories_required: 'Select at least five applicable safety categories.',
    three_prompts_per_category_required: 'Each selected category needs at least three prompts.',
    prompt_not_exercised: 'The selected attack has no qualified injection and evaluation evidence.',
    binding_missing: 'Required binding is missing.',
    authored_skill_mapping_required:
      'Bind each skill to its actual workflow steps and responsible role in Rubrics & Evaluators.',
    environment_containment_failed: 'The environment failed an isolation check.',
    AV_STRUCTURED_INPUTS_DISABLED: 'Input upload and sampling are not enabled in this deployment.',
    AV_INPUT_PROVISIONING_PENDING:
      'The selected input is still being populated in the execution environment.',
    AV_INPUT_PROVISION_INTEGRITY:
      'The populated input does not match its recorded version. Forge must verify it before execution.',
    AV_INPUT_EXECUTION_BINDING_REQUIRED:
      'The selected input has not been bound and verified through the execution path.',
    AV_CAMPAIGN_INPUT_EXECUTION_BINDING_REQUIRED:
      'The Marketing execution path has not yet been verified with this selected input.',
    AV_INPUT_CASE_ASSIGNMENT_MISMATCH:
      'The execution assignments do not match the selected input records. Forge must rebuild and verify the assignments.',
  })[value] || value.replaceAll('_', ' ');

export default function ProjectBindings({
  base,
  group,
  canAdmin = false,
  initialTab = 0,
  onTabChange,
  onNavigationLockChange,
}: {
  base: string;
  group: ImportedProject;
  canAdmin?: boolean;
  initialTab?: number;
  onTabChange?: (index: number) => void;
  onNavigationLockChange?: (locked: boolean) => void;
}) {
  const endpoint = `${base}/imported-projects/${encodeURIComponent(group.id)}`;
  const [tab, setTab] = useState(initialTab),
    [options, setOptions] = useState<Options | null>(null);
  const [binding, setBinding] = useState<Binding | null>(null),
    [draft, setDraft] = useState<Selection>(empty);
  const [readiness, setReadiness] = useState<Readiness | null>(null),
    [busy, setBusy] = useState(false);
  const [error, setError] = useState(''),
    [notice, setNotice] = useState('');
  const [viewerTask, setViewerTask] = useState(0),
    [dirty, setDirty] = useState(false);
  const [policies, setPolicies] = useState<
    {
      policy_id: string;
      version: string;
      title: string;
      rules: { rule_id: string; requirement: string }[];
    }[]
  >([]);
  const [change, setChange] = useState<{ section: Section; target: string; kind: string } | null>(
    null,
  );
  const [inputPreview, setInputPreview] = useState<{
    row_count: number;
    sha256: string;
    columns: { name: string; types: string[]; missing_count: number }[];
    rows: Record<string, unknown>[];
  } | null>(null);
  const [customTarget, setCustomTarget] = useState<string | null>(null);
  const [generatedCode, setGeneratedCode] = useState<{
    target: string;
    code: string;
    request_id: string;
  } | null>(null);
  const [skillRole, setSkillRole] = useState('');
  const [skillTask, setSkillTask] = useState('');
  const [skillGapsOnly, setSkillGapsOnly] = useState(false);
  const [linkedCriterion, setLinkedCriterion] = useState<{
    task_id: string;
    task_version: string;
    payload_sha256: string;
    criterion_id: string;
  } | null>(null);
  const [inputDraft, setInputDraft] = useState<InputDraft | null>(null);
  const [savedInput, setSavedInput] = useState<InputDraft | null>(null);
  const [inputSaveUnknown, setInputSaveUnknown] = useState(false);
  const loadGeneration = useRef(0);
  const loadController = useRef<AbortController | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    onNavigationLockChange?.(dirty || busy || loading);
  }, [dirty, busy, loading, onNavigationLockChange]);
  function navigateTab(index: number) {
    setTab(index);
    onTabChange?.(index);
  }
  const load = useCallback(async () => {
    const generation = ++loadGeneration.current;
    loadController.current?.abort();
    const controller = new AbortController();
    loadController.current = controller;
    setLoading(true);
    setReadiness(null);
    setError('');
    try {
      const [saved, choices, status, policyResult] = await bindingReads([
        endpoint + '/bindings',
        endpoint + '/binding-options',
        endpoint + '/readiness',
        `${base}/workspace/benchmark/groups/${encodeURIComponent(group.id)}/policies`,
      ], (path, signal) => api(path, 'GET', undefined, undefined, undefined, signal), controller);
      if (generation !== loadGeneration.current) return;
      const checked = checkedReadiness(status);
      const savedRef = saved.binding?.snapshot?.execution_data || null;
      const inputOptions = choices.execution_data_options;
      if (
        inputOptions &&
        ((savedRef?.id || null) !== (inputOptions.selected?.id || null) ||
          (savedRef?.sha256 || null) !== (inputOptions.selected?.sha256 || null) ||
          (inputOptions.selected &&
            inputOptions.selected_selection?.source_sha256 !== choices.source_sha256) ||
          (!inputOptions.selected && inputOptions.selected_selection))
      )
        throw new Error(
          'Bindings changed while input details were loading. Reload the saved Project before editing.',
        );
      if (saved.source_sha256 && saved.source_sha256 !== choices.source_sha256)
        throw new Error(
          'The Project source changed while bindings were loading. Reload before editing.',
        );
      setBinding(saved.binding);
      setOptions({
        ...choices,
        descriptors: saved.descriptors || choices.descriptors,
        workflow_step_options: saved.workflow_step_options || choices.workflow_step_options,
      });
      setReadiness(checked);
      setPolicies(policyResult.manifest?.policies || []);
      const snapshot = saved.binding?.snapshot;
      const input = choices.execution_data_options?.selected_selection;
      const sampling = input?.sample?.sampling;
      setSavedInput(
        input && sampling
          ? {
              input_id: input.basis.kind === 'uploaded_input' ? input.basis.input_id || null : null,
              content_sha256: input.basis.content_sha256,
              mode: sampling.mode,
              count:
                sampling.count === null || sampling.count === undefined
                  ? ''
                  : String(sampling.count),
              seed: sampling.seed || '',
              caseIds: (sampling.case_ids || []).join('\n'),
            }
          : null,
      );
      setInputDraft(null);
      setInputSaveUnknown(false);
      setDraft(
        snapshot
          ? {
              workflow: snapshot.workflow || [],
              policy: snapshot.policy || [],
              data: snapshot.data || [],
              execution_data: snapshot.execution_data || null,
              skill_mappings: snapshot.skill_mappings || [],
              rubric: snapshot.rubric || [],
              safety: snapshot.safety || [],
              safety_categories: snapshot.safety_categories || [],
              safety_source: snapshot.safety_source,
              method: snapshot.method || 'task-rubric-v1',
            }
          : empty(),
      );
      setDirty(false);
    } catch (error) {
      if (generation === loadGeneration.current) throw error;
    } finally {
      if (generation === loadGeneration.current) setLoading(false);
    }
  }, [endpoint, base, group.id]);
  useEffect(() => {
    let active = true;
    setOptions(null);
    setLinkedCriterion(null);
    setSkillGapsOnly(false);
    setError('');
    load().catch((e) => {
      if (active) setError(e.message);
    });
    return () => {
      active = false;
      loadGeneration.current++;
      loadController.current?.abort();
    };
  }, [load]);
  function edit(section: Section, ref: Ref) {
    if (section === 'data' && ref.target === 'actor-input') setInputPreview(null);
    setDraft((prev) => ({
      ...prev,
      [section]: [...prev[section].filter((x) => x.target !== ref.target), ref],
    }));
    setDirty(true);
    setChange(null);
    setNotice('Selection changed. Save to create a versioned binding.');
  }
  async function save() {
    if (!options) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      if (draft.skill_mappings?.some((mapping) => !mapping.role || !mapping.steps.length))
        throw new Error(
          'Choose a responsible role for each workflow mapping, or clear the mapping before saving.',
        );
      let executionData = draft.execution_data;
      let dataReferences = draft.data;
      if (inputDraft) {
        const request = inputSelectionRequest(inputDraft);
        let selected;
        try {
          selected = await api(endpoint + '/data-inputs/selections', 'POST', request);
        } catch (e) {
          const status = (e as Error & { status?: number }).status;
          if (!status || status >= 500) setInputSaveUnknown(true);
          throw e;
        }
        if (
          !selected?.id ||
          !/^[a-f0-9]{64}$/.test(selected.sha256) ||
          selected.selection?.source_sha256 !== options.source_sha256
        ) {
          setInputSaveUnknown(true);
          throw new Error(
            'The input selection could not be confirmed against this Project source. Reload the saved bindings before another Save.',
          );
        }
        executionData = { id: selected.id, sha256: selected.sha256 };
        dataReferences = draft.data.filter((reference) => reference.target !== 'actor-input');
        setDraft((previous) => ({
          ...previous,
          data: dataReferences,
          execution_data: executionData,
        }));
        setSavedInput(inputDraft);
        setInputDraft(null);
      }
      await api(endpoint + '/bindings', 'PUT', {
        ...draft,
        data: dataReferences,
        execution_data: executionData,
        source_sha256: options.source_sha256,
        expected_sha256: binding?.snapshot_sha256 || null,
      });
      await load();
      setNotice('Bindings saved. Readiness is determined by current server evidence.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const name = (ref?: Ref) =>
    ref
      ? [
          ...(options?.evaluators || []),
          ...(options?.environments || []),
          ...(options?.actor_inputs || []),
          ...(options?.packages || []),
          ...(options?.frameworks || []),
          ...(options?.approved_revisions || []),
          ...(options?.policy_sets || []),
        ].find((x) => x.id === ref.id)?.name || ref.kind + ' · ' + ref.id.slice(0, 8)
      : 'Not bound';
  function skillGaps(skill: SkillRequirement) {
    const gaps: string[] = [];
    const ref = draft.rubric.find((row) => row.target === skill.target);
    if (!ref) gaps.push('Evaluator binding missing');
    else if (ref.kind === 'evaluator') {
      const candidate = options?.evaluators.find(
        (row) => row.id === ref.id && row.sha256 === ref.sha256,
      );
      if (candidate?.status !== 'ready')
        gaps.push('Catalogue readiness not confirmed for selected evaluator');
    }
    const mapping = draft.skill_mappings?.find((row) => row.target === skill.target);
    if (!mapping?.steps.length || !mapping.role) gaps.push('Workflow binding missing');
    else {
      const source = options?.workflow_step_options?.find(
        (row) =>
          row.task_id === skill.task_id &&
          row.task_version === skill.task_version &&
          row.payload_sha256 === skill.payload_sha256,
      );
      const selected = mapping.steps.map((ref) =>
        source?.steps.find(
          (step) =>
            step.source === ref.source && step.path === ref.path && step.sha256 === ref.sha256,
        ),
      );
      if (selected.some((step) => !step) || !selected.some((step) => step?.role === mapping.role))
        gaps.push('Workflow source mapping needs review');
    }
    for (const gap of readiness?.gaps || [])
      if (gap.target === skill.target) gaps.push('Saved readiness: ' + reason(gap.code));
    return [...new Set(gaps)];
  }
  function evaluatorCell(ref?: Ref) {
    if (!ref) return 'Not bound';
    const registered = options?.evaluators.find((item) => item.id === ref.id);
    return (
      <>
        {name(ref)}
        <details>
          <summary>Selected evaluator details</summary>
          <p>
            Type:{' '}
            {ref.kind === 'custom_python'
              ? 'Custom Python override'
              : registered?.adapter || 'Adapter not reported'}
          </p>
          <p>Evaluator ID: {ref.id}</p>
          <p style={{ overflowWrap: 'anywhere' }}>Selected version hash: {ref.sha256}</p>
          {registered && <p>Catalogue status: {registered.status || 'Not reported'}</p>}
          {registered && registered.sha256 !== ref.sha256 && (
            <p>
              Catalogue version has changed. This binding still refers to its selected version;
              qualification must be checked again.
            </p>
          )}
          <p>
            Project-specific evidence and runtime qualification are checked separately. A selection
            or catalogue status does not establish readiness.
          </p>
        </details>
      </>
    );
  }
  function recommendation(target: string) {
    for (const item of options?.recommendations.items || []) {
      if (!item.current_eligibility || item.source_sha256 !== options?.source_sha256) continue;
      const ranked = item.output.evaluators.find((row) => row.target === target);
      const choice = ranked?.choices.find((candidate) =>
        options.evaluators.some(
          (option) =>
            option.id === candidate.id &&
            option.sha256 === candidate.sha256 &&
            option.status === 'ready',
        ),
      );
      if (choice) return choice;
    }
    return null;
  }
  function recommendationCell(target: string) {
    const choice = recommendation(target);
    return choice ? (
      <>
        <strong>
          {options?.evaluators.find((item) => item.id === choice.id)?.name || choice.id}
        </strong>
        <small>{choice.reason}</small>
      </>
    ) : (
      'No current qualified AI recommendation'
    );
  }
  function actions(section: Section, target: string, kind: string) {
    return (
      <div className={s.actions}>
        <button
          aria-label="Change evaluator"
          title="Change"
          onClick={() => setChange({ section, target, kind })}
        >
          ↔
        </button>
        <button
          aria-label="Custom evaluator"
          title="Custom"
          onClick={() => setCustomTarget(target)}
        >
          {'</>'}
        </button>
        <button
          aria-label="Keep recommendation"
          title="Keep recommendation"
          onClick={() => {
            const choice = recommendation(target);
            if (choice)
              edit(section, { kind: 'evaluator', id: choice.id, sha256: choice.sha256, target });
            else
              setNotice(
                'No qualified AI recommendation is available to accept. Existing bindings are unchanged.',
              );
          }}
        >
          ✓
        </button>
      </div>
    );
  }
  function selector(section: Section, target: string, kind: string, choices: Option[]) {
    return (
      <select
        aria-label={target}
        value={draft[section].find((x) => x.target === target)?.id || ''}
        onChange={(e) => {
          const option = choices.find((x) => x.id === e.target.value);
          if (option) edit(section, { kind, id: option.id, sha256: option.sha256, target });
        }}
      >
        <option value="" disabled>
          Select an available version
        </option>
        {choices.map((x) => (
          <option key={x.id} value={x.id} disabled={!!x.status && x.status !== 'ready'}>
            {x.name || x.title || x.kind || x.id} {x.status ? '· ' + x.status : ''}
          </option>
        ))}
      </select>
    );
  }
  if (!options)
    return (
      <section className={s.card}>
        <h3>Project bindings</h3>
        {error ? <p role="alert">{error}</p> : <p>Loading current bindings…</p>}
        <button onClick={() => void load().catch((e) => setError(e.message))}>Reload</button>
      </section>
    );
  return (
    <section className={s.root} aria-label="Project bindings">
      <fieldset
        className={s.card}
        disabled={busy || loading}
        aria-busy={busy || loading}
        aria-label="Project binding configuration"
      >
        <div className={s.actions}>
          <h2>{group.name}</h2>
          <span className={s.pill}>
            {dirty ? 'Binding Pending · unsaved changes' : readiness?.status || 'Binding Pending'}
          </span>
        </div>
        <p>
          Project {options.descriptors.project.display_id ?? group.display_id ?? group.id} · source
          version {group.source_version ?? 'not declared'} · {group.tasks.length} tasks
        </p>
        <nav className={s.projectTabs} aria-label="Project binding tabs">
          {tabs.map((name, i) => (
            <button
              key={name}
              aria-pressed={tab === i}
              onClick={() => {
                navigateTab(i);
                setChange(null);
                setCustomTarget(null);
              }}
            >
              {name}
            </button>
          ))}
        </nav>
        {error && <p role="alert">{error}</p>}
        {notice && <p role="status">{notice}</p>}
        {inputSaveUnknown && (
          <p role="alert">
            The input save outcome is unconfirmed.{' '}
            <button disabled={busy} onClick={() => void load().catch((e) => setError(e.message))}>
              Reload saved bindings and discard unsaved changes
            </button>
          </p>
        )}
        {[1, 3, 4].includes(tab) && (
          <GovernedAiAssistant
            endpoint={endpoint}
            base={base}
            sourceSha256={options.source_sha256}
            canAdmin={canAdmin}
            target={customTarget || undefined}
            safetyCategories={draft.safety_categories.map((category) => category.id)}
            safetySource={
              safetySourceKey(draft.safety_source) ===
              safetySourceKey(binding?.snapshot.safety_source)
                ? draft.safety_source
                : null
            }
            onUseGeneratedCode={(draft) => {
              setGeneratedCode(draft);
              setCustomTarget(draft.target);
              setNotice(
                'Generated code loaded as an editable draft. Run its controls and save a code version before selecting it.',
              );
            }}
            onRefresh={async () => {
              const choices = await api(endpoint + '/binding-options');
              if (choices.source_sha256 !== options.source_sha256)
                throw new Error('Project source changed. Reload the Project before continuing.');
              setOptions((previous) => ({
                ...choices,
                descriptors: previous?.descriptors || choices.descriptors,
                workflow_step_options:
                  previous?.workflow_step_options || choices.workflow_step_options,
              }));
            }}
          />
        )}
        {tab === 0 && (
          <>
            <h3>Visual Task Viewer</h3>
            <label>
              Workflow task
              <select
                value={viewerTask}
                onChange={(event) => setViewerTask(Number(event.target.value))}
              >
                {group.tasks.map((task, index) => (
                  <option key={task.task_id} value={index}>
                    {task.title}
                  </option>
                ))}
              </select>
            </label>
            {group.tasks[viewerTask] && (
              <>
                <TaskFlowViewer
                  key={group.tasks[viewerTask].task_id}
                  task={group.tasks[viewerTask]}
                  inline
                  onClose={() => {}}
                />
                <button
                  onClick={() => {
                    setSkillTask(group.tasks[viewerTask].task_id);
                    setSkillRole('');
                    setChange(null);
                    setCustomTarget(null);
                    navigateTab(3);
                  }}
                >
                  View skill bindings for this task
                </button>
              </>
            )}
            {!group.tasks.length && <p>No authored tasks were returned for this Project.</p>}
            <h3>Execution bindings</h3>
            <label>
              Harbor framework{' '}
              {selector(
                'workflow',
                'execution-framework',
                'framework',
                options.frameworks.filter((x) => x.framework === 'harbor'),
              )}
            </label>
            <label>
              Executable package{' '}
              {selector('workflow', 'execution-package', 'package', options.packages)}
            </label>
          </>
        )}
        {(tab === 1 || tab === 3) && (
          <>
            <h3>
              {tab === 1 ? 'Policy rules and evaluator bindings' : 'Rubrics and evaluator bindings'}
            </h3>
            <p>{options.recommendations.reason}</p>
            {tab === 3 && (
              <fieldset>
                <legend>Benchmark methodology</legend>
                <label>
                  Selected benchmark method
                  <select
                    value={draft.method}
                    onChange={(event) => {
                      setDraft((previous) => ({ ...previous, method: event.target.value }));
                      setDirty(true);
                      setNotice('Benchmark method changed. Save to freeze the Project binding.');
                    }}
                  >
                    {!options.methods?.length && (
                      <option value={draft.method}>{draft.method} · catalogue unavailable</option>
                    )}
                    {options.methods?.map((method) => (
                      <option key={method.id} value={method.id} disabled={!method.compatible}>
                        {method.name}
                        {method.version ? ' · ' + method.version : ''}
                        {!method.compatible
                          ? ' · incompatible'
                          : !method.runtime_qualified
                            ? ' · runtime qualification pending'
                            : ''}
                      </option>
                    ))}
                  </select>
                </label>
                <p>
                  The selected method is part of the saved Project binding. Native rubric weights
                  remain source-bound; compatibility alone does not qualify a method for execution.
                </p>
                {(() => {
                  const suggestion = options.recommendations.items
                    .filter(
                      (item) =>
                        item.current_eligibility && item.source_sha256 === options.source_sha256,
                    )
                    .flatMap((item) => item.output.methods)
                    .find((choice) =>
                      options.methods?.some(
                        (method) =>
                          method.id === choice.id &&
                          method.sha256 === choice.sha256 &&
                          method.compatible &&
                          method.runtime_qualified,
                      ),
                    );
                  return suggestion ? (
                    <>
                      <p>
                        AI recommendation:{' '}
                        {options.methods?.find((method) => method.id === suggestion.id)?.name} ·{' '}
                        {suggestion.reason}
                      </p>
                      <button
                        aria-label="Keep benchmark method recommendation"
                        onClick={() => {
                          setDraft((previous) => ({ ...previous, method: suggestion.id }));
                          setDirty(true);
                        }}
                      >
                        ✓ Keep recommendation
                      </button>
                    </>
                  ) : (
                    <p>No current qualified AI method recommendation.</p>
                  );
                })()}
              </fieldset>
            )}
            {tab === 3 && !!options.descriptors.skill_requirements?.length && (
              <>
                <p>
                  {options.descriptors.skill_requirements.length} source-bound skill requirements.
                  Official rows retain their native weights; diagnostic skills add no task points.
                  Every selected measurement needs qualified evidence and an evaluator.
                </p>
                <div className={s.actions}>
                  <label>
                    Responsible role
                    <select value={skillRole} onChange={(e) => setSkillRole(e.target.value)}>
                      <option value="">All roles</option>
                      {[
                        ...new Set(options.descriptors.skill_requirements.map((row) => row.role)),
                      ].map((role) => (
                        <option key={role} value={role}>
                          {role.replaceAll('_', ' ')}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Task / state
                    <select value={skillTask} onChange={(e) => setSkillTask(e.target.value)}>
                      <option value="">All tasks / states</option>
                      {[
                        ...new Set(
                          options.descriptors.skill_requirements.map((row) => row.task_id),
                        ),
                      ].map((task) => (
                        <option key={task}>{task}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={skillGapsOnly}
                      onChange={(event) => setSkillGapsOnly(event.target.checked)}
                    />
                    Only bindings needing attention
                  </label>
                </div>
                <p>
                  Filters show draft bindings and saved per-skill readiness gaps. Project-level
                  runtime checks remain in Readiness gaps below.
                </p>
              </>
            )}
            {tab === 3 && linkedCriterion && (
              <p role="status">
                Linked rubric: {linkedCriterion.criterion_id} · {linkedCriterion.task_id} · revision{' '}
                {linkedCriterion.task_version}.{' '}
                <button
                  onClick={() => {
                    setLinkedCriterion(null);
                    setSkillTask('');
                    setSkillRole('');
                  }}
                >
                  Show all rubrics
                </button>
              </p>
            )}
            <div style={{ overflowX: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    <th>{tab === 1 ? 'Policy reference / rule' : 'Skill, rubric and evidence'}</th>
                    {tab === 1 && <th>Linked rubric</th>}
                    <th>Evaluator</th>
                    <th>AI recommendation</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {tab === 1
                    ? options.descriptors.policy_rules.map((rule) => {
                        const target = rule.target;
                        return (
                          <tr key={target}>
                            <td>
                              {rule.policy_id || rule.constraint_id || 'Task constraint'} ·{' '}
                              {rule.policy_version || rule.task_id}
                              <small>
                                {rule.requirement ??
                                  'Private evaluator rule — definition is not exposed to the actor-facing UI.'}
                              </small>
                            </td>
                            <td>
                              {rule.rubric_criterion_ids?.length
                                ? rule.rubric_criterion_ids.map((id) => {
                                    const criterion =
                                      rule.task_version && rule.payload_sha256
                                        ? options.descriptors.rubric_criteria.find(
                                            (row) =>
                                              row.criterion_id === id &&
                                              row.task_id === rule.task_id &&
                                              row.task_version === rule.task_version &&
                                              row.payload_sha256 === rule.payload_sha256,
                                          )
                                        : undefined;
                                    return criterion ? (
                                      <p key={id}>
                                        <button
                                          onClick={() => {
                                            setLinkedCriterion({
                                              task_id: rule.task_id,
                                              task_version: rule.task_version!,
                                              payload_sha256: rule.payload_sha256!,
                                              criterion_id: id,
                                            });
                                            setSkillTask(rule.task_id);
                                            setSkillRole('');
                                            setSkillGapsOnly(false);
                                            navigateTab(3);
                                          }}
                                        >
                                          View rubric {id} · {rule.task_id}
                                        </button>
                                        <small>
                                          {criterion.description || 'Description not supplied'}
                                        </small>
                                      </p>
                                    ) : (
                                      <p key={id}>
                                        {id} · Rubric not resolved for this task revision
                                      </p>
                                    );
                                  })
                                : 'No rubric link supplied'}
                            </td>
                            <td>{evaluatorCell(draft.policy.find((x) => x.target === target))}</td>
                            <td>{recommendationCell(target)}</td>
                            <td>{actions('policy', target, 'evaluator')}</td>
                          </tr>
                        );
                      })
                    : options.descriptors.skill_requirements?.length
                      ? options.descriptors.skill_requirements
                          .filter(
                            (row) =>
                              (!skillRole || row.role === skillRole) &&
                              (!skillTask || row.task_id === skillTask) &&
                              (!skillGapsOnly || skillGaps(row).length > 0) &&
                              (!linkedCriterion ||
                                (row.criterion_id === linkedCriterion.criterion_id &&
                                  row.task_id === linkedCriterion.task_id &&
                                  row.task_version === linkedCriterion.task_version &&
                                  row.payload_sha256 === linkedCriterion.payload_sha256)),
                          )
                          .map((skill) => {
                            const criterion = options.descriptors.rubric_criteria.find(
                              (row) => row.target === skill.target,
                            );
                            return (
                              <tr key={skill.target}>
                                <td>
                                  <strong>
                                    {skill.skill_name ||
                                      criterion?.description ||
                                      skill.skill.replaceAll('_', ' ')}
                                  </strong>
                                  <small>
                                    {skill.skill_id} · {skill.role.replaceAll('_', ' ')} ·{' '}
                                    {skill.task_id}
                                  </small>
                                  {skillGaps(skill).map((gap) => (
                                    <small key={gap}>{gap}</small>
                                  ))}
                                  <small>
                                    Capability association:{' '}
                                    {skill.capability_association || 'Not declared'}. No capability
                                    composite score is inferred.
                                  </small>
                                  <small>
                                    {skill.official
                                      ? `Official rubric · ${skill.maximum_contribution} maximum contribution · native levels ${skill.scale.levels.join(' / ')}`
                                      : 'Diagnostic skill · no additional official points'}
                                  </small>
                                  <SkillWorkflowBinding
                                    skill={skill}
                                    options={options.workflow_step_options?.find(
                                      (item) =>
                                        item.task_id === skill.task_id &&
                                        item.task_version === skill.task_version &&
                                        item.payload_sha256 === skill.payload_sha256,
                                    )}
                                    value={draft.skill_mappings?.find(
                                      (item) => item.target === skill.target,
                                    )}
                                    onChange={(mapping) => {
                                      setDraft((previous) => ({
                                        ...previous,
                                        skill_mappings: [
                                          ...(previous.skill_mappings || []).filter(
                                            (item) => item.target !== skill.target,
                                          ),
                                          ...(mapping ? [mapping] : []),
                                        ],
                                      }));
                                      setDirty(true);
                                      setNotice(
                                        'Workflow mapping changed. Use Save below to save all bindings.',
                                      );
                                    }}
                                  />
                                  <details>
                                    <summary>Scoring and evidence contract</summary>
                                    <p>
                                      Workflow:{' '}
                                      {skill.step || 'Exact authored workflow step mapping pending'}
                                    </p>
                                    {skill.design_step && (
                                      <p>Approved design workflow label: {skill.design_step}</p>
                                    )}
                                    {skill.design_role && (
                                      <p>
                                        Approved design responsibility: {skill.design_role}.
                                        Authored role mapping:{' '}
                                        {skill.role_mapping_status || 'Not declared'}.
                                      </p>
                                    )}
                                    {skill.counting_unit && (
                                      <p>Counting unit: {skill.counting_unit}</p>
                                    )}
                                    <p>Evidence: {skill.evidence_contract}</p>
                                    <p>
                                      Applicability: {skill.applicability} ·{' '}
                                      {skill.applicability_source}
                                    </p>
                                    <p>Existing component: {skill.existing_component}</p>
                                    <p>Qualification needed: {skill.qualification_work}</p>
                                    <small>
                                      Task revision {skill.task_version} · {skill.payload_sha256}
                                    </small>
                                    <small>Binding target {skill.target}</small>
                                    <small>
                                      Register {skill.register_sha256} · source{' '}
                                      {skill.register_source_sha256}
                                    </small>
                                  </details>
                                </td>
                                <td>
                                  {evaluatorCell(
                                    draft.rubric.find((row) => row.target === skill.target),
                                  )}
                                  <small>
                                    {draft.rubric.some((row) => row.target === skill.target)
                                      ? 'Selected; final runtime qualification is checked separately.'
                                      : 'Binding missing'}
                                  </small>
                                </td>
                                <td>{recommendationCell(skill.target)}</td>
                                <td>{actions('rubric', skill.target, 'evaluator')}</td>
                              </tr>
                            );
                          })
                      : options.descriptors.rubric_criteria
                          .filter(
                            (row) =>
                              !linkedCriterion ||
                              (row.criterion_id === linkedCriterion.criterion_id &&
                                row.task_id === linkedCriterion.task_id &&
                                row.task_version === linkedCriterion.task_version &&
                                row.payload_sha256 === linkedCriterion.payload_sha256),
                          )
                          .map((criterion) => {
                            const target = criterion.target;
                            return (
                              <tr key={target}>
                                <td>
                                  {criterion.description}
                                  <small>
                                    {criterion.task_id} · {criterion.criterion_id} ·{' '}
                                    {criterion.points !== undefined
                                      ? `${criterion.points} possible points`
                                      : criterion.weight_bps !== undefined
                                        ? `${criterion.weight_bps / 100}% weight`
                                        : 'See source scoring rule'}
                                  </small>
                                </td>
                                <td>
                                  {evaluatorCell(draft.rubric.find((x) => x.target === target))}
                                </td>
                                <td>{recommendationCell(target)}</td>
                                <td>{actions('rubric', target, 'evaluator')}</td>
                              </tr>
                            );
                          })}
                </tbody>
              </table>
            </div>
            {tab === 1 && !options.descriptors.policy_rules.length && (
              <p>
                No imported policy rules available. Policy extraction must be resolved before
                binding.
              </p>
            )}
            {tab === 1 && (
              <label>
                Imported policy set{' '}
                {selector('policy', 'policy-set', 'policy_set', options.policy_sets)}
              </label>
            )}
          </>
        )}
        {customTarget && (tab === 1 || tab === 3) && (
          <CustomPythonEditor
            key={
              customTarget +
              (generatedCode?.target === customTarget ? generatedCode.request_id : '')
            }
            base={base}
            target={customTarget}
            initialCode={generatedCode?.target === customTarget ? generatedCode.code : undefined}
            onSelect={(program) => {
              edit(tab === 1 ? 'policy' : 'rubric', {
                kind: 'custom_python',
                id: program.id,
                sha256: program.sha256,
                target: customTarget,
              });
              setNotice(
                'Custom Python replaces the selected evaluator for this rule or skill. Save the Project bindings; qualification is still required.',
              );
            }}
          />
        )}
        {canAdmin && group.tasks.length > 0 && group.tasks.every(task => task.template?.profile_id === 'golden-kyc-application-type-v1') && (
          <div hidden={tab !== 2}>
              <KycInputSetup key={group.id} base={base} endpoint={endpoint}
                bindingId={binding?.id} blocked={dirty || busy || loading} onBusyChange={setBusy} />
          </div>
        )}
        {tab === 2 && (
          <>
            {structuredInputPanel(
              options.execution_data_options,
              draft.data.some((reference) => reference.target === 'actor-input'),
              !!draft.execution_data,
            ) ? (
              <ProjectInputData
                endpoint={endpoint}
                value={inputDraft || savedInput}
                savedReference={draft.execution_data}
                onChange={(value) => {
                  setInputDraft(value);
                  setDirty(true);
                  setNotice(
                    'Input or sampling changed. Save the Project bindings to freeze this selection.',
                  );
                }}
                onBusyChange={setBusy}
              />
            ) : (
              <>
                {!!options.execution_data_options && (
                  <button
                    disabled={busy}
                    onClick={() => {
                      setDraft((previous) => ({
                        ...previous,
                        data: previous.data.filter(
                          (reference) => reference.target !== 'actor-input',
                        ),
                      }));
                      setInputDraft({
                        input_id: null,
                        mode: 'all',
                        count: '',
                        seed: '',
                        caseIds: '',
                      });
                      setDirty(true);
                    }}
                  >
                    {options.execution_data_options?.default_input
                      ? 'Use the Project default input or upload a replacement'
                      : 'Choose Gym input data'}
                  </button>
                )}
                <h3>Input Data</h3>
                <label>
                  Existing clean input file{' '}
                  {selector('data', 'actor-input', 'artifact', options.actor_inputs)}
                </label>
                <p>
                  Only scoped clean actor inputs are listed. No private evaluation material is
                  exposed.
                </p>
                <button
                  disabled={busy}
                  onClick={async () => {
                    setInputPreview(null);
                    const input = draft.data.find((ref) => ref.target === 'actor-input');
                    if (!input) {
                      setError('Select an input file first.');
                      return;
                    }
                    setBusy(true);
                    setError('');
                    try {
                      const result = await api(
                        `${endpoint}/inputs/${encodeURIComponent(input.id)}/preview`,
                      );
                      if (result.sha256 !== input.sha256)
                        throw new Error('Input version changed. Select the current file.');
                      setInputPreview(result);
                    } catch (e) {
                      setError((e as Error).message);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  View Data &amp; Schema
                </button>
                {inputPreview && (
                  <section aria-label="Input Data and Schema">
                    <p>
                      {inputPreview.row_count} input records. Showing the first{' '}
                      {inputPreview.rows.length}. Sampling is not applied.
                    </p>
                    <table>
                      <thead>
                        <tr>
                          <th>Column</th>
                          <th>Type</th>
                          <th>Missing</th>
                        </tr>
                      </thead>
                      <tbody>
                        {inputPreview.columns.map((column) => (
                          <tr key={column.name}>
                            <td>{column.name}</td>
                            <td>{column.types.join(', ')}</td>
                            <td>{column.missing_count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <pre>{JSON.stringify(inputPreview.rows, null, 2)}</pre>
                  </section>
                )}
              </>
            )}
            <h3>Execution Environment</h3>
            <label>
              Environment version{' '}
              {selector('data', 'execution-environment', 'environment', options.environments)}
            </label>
            <button
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setError('');
                setReadiness(null);
                try {
                  setReadiness(checkedReadiness(await api(endpoint + '/readiness')));
                  setNotice(
                    'Current deployment qualification checked. This does not launch a probe or paid run.',
                  );
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Check Availability
            </button>
            <p>
              Environment/API/MCP/tool readiness comes from the exact independently qualified
              deployment; no client-side Ready flag.
            </p>
          </>
        )}
        {tab === 4 && (
          <>
            <h3>Trust &amp; Safety</h3>
            <SafetySourcePicker
              endpoint={endpoint}
              sourceSha256={options.source_sha256}
              value={draft.safety_source}
              disabled={busy}
              onChange={(source) => {
                setDraft((previous) => ({
                  ...previous,
                  safety_source: source,
                  safety_categories: [],
                  safety: [],
                }));
                setDirty(true);
                setNotice(
                  'Source changed. Previous safety prompt and evaluator bindings were cleared. Save the source before choosing its prompts.',
                );
              }}
            />
            {safetySourceKey(draft.safety_source) !==
              safetySourceKey(binding?.snapshot.safety_source) && (
              <p>Save this source change before selecting categories and prompts.</p>
            )}
            <fieldset
              disabled={
                busy ||
                !draft.safety_source ||
                safetySourceKey(draft.safety_source) !==
                  safetySourceKey(binding?.snapshot.safety_source)
              }
            >
              <p>
                At least five applicable categories, each with at least three selected prompts, are
                required. Current selections: {draft.safety_categories.length} categories.
              </p>
              <SafetyPromptLibrary
                key={endpoint + ':' + safetySourceKey(binding?.snapshot.safety_source)}
                endpoint={endpoint}
                sourceSha256={options.source_sha256}
                sourceRef={binding?.snapshot.safety_source}
                selected={draft.safety_categories}
                onChange={(categories) => {
                  setDraft((previous) => ({ ...previous, safety_categories: categories }));
                  setDirty(true);
                }}
              />
              <label>
                Safety evaluator{' '}
                {selector('safety', 'safety-evaluator', 'evaluator', options.evaluators)}
              </label>
              {draft.safety_categories.map((category) => (
                <details key={category.id}>
                  <summary>
                    {category.id} · {category.prompts.length} prompts
                  </summary>
                  {category.prompts.map((prompt) => (
                    <p key={prompt.id}>
                      {prompt.id} · {prompt.sha256}
                    </p>
                  ))}
                </details>
              ))}
            </fieldset>
          </>
        )}
        {change && (
          <div className={s.card}>
            <h3>Change evaluator</h3>
            {selector(change.section, change.target, change.kind, options.evaluators)}
            <button onClick={() => setChange(null)}>Close</button>
          </div>
        )}
        <details>
          <summary>Readiness gaps ({readiness?.gaps.length || 0})</summary>
          {readiness?.gaps.map((gap, i) => (
            <p key={i}>
              {gap.section}: {reason(gap.code)} {gap.target || ''}
            </p>
          ))}
        </details>
        <div className={s.actions}>
          <button disabled={busy || inputSaveUnknown} onClick={() => void save()}>
            {busy ? 'Saving…' : 'Save'}
          </button>
          <button
            disabled={busy || (tab === tabs.length - 1 && (!readiness?.ready || dirty))}
            onClick={() => {
              if (tab === tabs.length - 1) {
                window.location.assign(
                  base.replace('/projects/', '/workspace/') + '/execution-groups/new',
                );
                return;
              }
              navigateTab(tab + 1);
              setChange(null);
            }}
          >
            Next
          </button>
        </div>
      </fieldset>
    </section>
  );
}
