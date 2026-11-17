'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { taskFlow, taskFlowSvg, taskFlowLayout } from '../lib/task-flow';

const object = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
export default function TaskFlowViewer({
  task,
  onClose,
  inline = false,
}: {
  task: {
    task_id: string;
    task_version: string;
    title: string;
    actor: unknown;
    workflow?: unknown;
  };
  onClose: () => void;
  inline?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [nodeId, setNodeId] = useState('');
  const workflowMeta =
    task.workflow && typeof task.workflow === 'object' && !Array.isArray(task.workflow)
      ? (task.workflow as Record<string, unknown>)
      : {};
  const flow = task.workflow
    ? taskFlow({ workflowGraph: workflowMeta.graph ?? task.workflow })
    : taskFlow(task.actor);
  const layout = taskFlowLayout(flow);
  const node = flow.nodes.find((n) => n.id === nodeId) || flow.nodes[0];
  const actor =
    task.actor && typeof task.actor === 'object' ? (task.actor as Record<string, unknown>) : {};
  const kyc = object(actor.profile).id === 'golden-kyc-reusable-v1';
  const section = (key: string) => object(object(actor.sections)[key]);
  const tools =
    kyc && Array.isArray(section('S3').tools)
      ? (section('S3').tools as unknown[])
          .filter((tool): tool is string => typeof tool === 'string')
          .slice(0, 100)
      : [];
  const policyRefs =
    kyc && Array.isArray(section('S4').statePolicies)
      ? (section('S4').statePolicies as unknown[]).map(object).slice(0, 100)
      : [];
  const graphSource = object(workflowMeta.graph ?? task.workflow ?? actor.workflowGraph);
  const roles = Array.isArray(graphSource.roles) ? graphSource.roles.map(object) : [];
  const selectedRole = node?.role
    ? roles.find((role) => role.id === node.role || role.name === node.role)
    : undefined;
  const roleTools =
    selectedRole && Array.isArray(selectedRole.tools)
      ? selectedRole.tools.filter((tool): tool is string => typeof tool === 'string').slice(0, 100)
      : [];
  const records = (key: string) =>
    Array.isArray(actor[key])
      ? (actor[key] as unknown[])
          .filter((v): v is Record<string, unknown> => !!v && typeof v === 'object')
          .slice(0, 100)
      : [];
  useEffect(() => {
    const element = dialog.current;
    // Native removal releases the top layer. Closing during effect cleanup
    // queues a close event on StrictMode replay and removes the reopened viewer.
    if (!inline && element && !element.open) element.showModal();
  }, [inline]);
  function download() {
    const url = URL.createObjectURL(
      new Blob([taskFlowSvg(flow, task.title, task.task_version)], { type: 'image/svg+xml' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = `${task.task_id.replace(/[^a-zA-Z0-9_-]/g, '_')}-flow.svg`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const Container = inline ? 'section' : 'dialog';
  return (
    <Container
      ref={inline ? undefined : dialog}
      onClose={inline ? undefined : onClose}
      aria-labelledby={titleId}
      style={{
        width: inline ? '100%' : 'min(1100px, 94vw)',
        maxHeight: inline ? undefined : '90vh',
        overflow: 'auto',
        padding: 24,
        borderRadius: 12,
      }}
    >
      {!inline && (
        <button onClick={() => dialog.current?.close()} style={{ float: 'right' }}>
          Close task viewer
        </button>
      )}
      <h2 id={titleId}>{task.title}</h2>
      <p>
        {task.task_id} · Task version {task.task_version} · Read only
      </p>
      <p>{flow.reason}</p>
      {Array.isArray(workflowMeta.execution_blockers) && workflowMeta.execution_blockers.length ? (
        <p>Workflow execution qualification is pending.</p>
      ) : null}
      {typeof workflowMeta.graph_sha256 === 'string' && (
        <p style={{ overflowWrap: 'anywhere' }}>Graph SHA256: {workflowMeta.graph_sha256}</p>
      )}
      {!!flow.nodes.length && (
        <>
          <button onClick={download}>Export this graph (SVG)</button>
          <div
            tabIndex={0}
            aria-label="Scrollable task flow"
            style={{ overflow: 'auto', maxHeight: '55vh', marginTop: 16 }}
          >
            {flow.nodes.some((n) => n.kind) ? (
              // Only our XML-escaped, self-contained SVG is used as an image.
              // This renders authored edges, including branches/returns, faithfully.
              // Selection is also available in the accessible list below.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                alt="Authored task workflow with labelled branches and bounded returns"
                style={{ maxWidth: 'none', cursor: 'pointer' }}
                onClick={(event) => {
                  const bounds = event.currentTarget.getBoundingClientRect();
                  const x = ((event.clientX - bounds.left) * layout.width) / bounds.width,
                    y = ((event.clientY - bounds.top) * layout.height) / bounds.height;
                  const hit = layout.nodes.find(
                    (node) =>
                      x >= node.x &&
                      x <= node.x + node.width &&
                      y >= node.y &&
                      y <= node.y + node.height,
                  );
                  if (hit) setNodeId(hit.node.id);
                }}
                src={`data:image/svg+xml,${encodeURIComponent(taskFlowSvg(flow, task.title, task.task_version, node?.id))}`}
              />
            ) : (
              <svg
                width={Math.max(600, flow.nodes.length * 220 + 40)}
                height={120}
                role="group"
                aria-label="Authored task stages"
              >
                <defs>
                  <marker
                    id="task-flow-arrow"
                    markerWidth="8"
                    markerHeight="8"
                    refX="7"
                    refY="4"
                    orient="auto"
                  >
                    <path d="M0 0 L8 4 L0 8 Z" fill="#45677d" />
                  </marker>
                </defs>
                {flow.nodes.map((n, i) => (
                  <g key={n.id}>
                    {i > 0 && (
                      <line
                        x1={20 + (i - 1) * 220 + 180}
                        x2={20 + i * 220}
                        y1={60}
                        y2={60}
                        stroke="#45677d"
                        strokeWidth={2}
                        markerEnd="url(#task-flow-arrow)"
                      />
                    )}
                    <rect
                      x={20 + i * 220}
                      y={20}
                      width={180}
                      height={80}
                      rx={10}
                      fill={node?.id === n.id ? '#d4eaf4' : '#eef5f9'}
                      stroke="#45677d"
                    />
                    <text x={30 + i * 220} y={65} fill="#17354b">
                      {n.label.slice(0, 22)}
                    </text>
                  </g>
                ))}
              </svg>
            )}
          </div>
          <nav aria-label="Task stage details">
            {flow.nodes.map((n) => (
              <button key={n.id} onClick={() => setNodeId(n.id)} aria-pressed={node?.id === n.id}>
                {n.label}
              </button>
            ))}
          </nav>
          {flow.nodes.some((n) => n.kind) && (
            <details>
              <summary>Authored connections</summary>
              <ul>
                {flow.edges.map((edge, index) => (
                  <li key={index}>
                    {edge.from} → {edge.to}: {edge.label}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {node && (
            <section aria-label="Selected task stage">
              <h3>{node.label}</h3>
              {node.detail && <p>{node.detail}</p>}
              <p style={{ whiteSpace: 'pre-wrap' }}>{node.instruction}</p>
            </section>
          )}
        </>
      )}
      {typeof actor.objective === 'string' && (
        <section>
          <h3>Objective</h3>
          <p>{actor.objective}</p>
        </section>
      )}
      {typeof actor.instructions === 'string' && (
        <section>
          <h3>Task instructions</h3>
          <p style={{ whiteSpace: 'pre-wrap' }}>{actor.instructions}</p>
        </section>
      )}
      {kyc && (
        <>
          <section>
            <h3>Reusable assignment</h3>
            {Object.entries({
              trigger: 'Workflow trigger',
              businessContext: 'Business context',
              deliverable: 'Deliverable',
              governingState: 'Governing state',
              scope: 'Scope',
              language: 'Language',
            }).map(
              ([key, label]) =>
                typeof section('S1')[key] === 'string' && (
                  <p key={key}>
                    <strong>{label}</strong>
                    <br />
                    {String(section('S1')[key])}
                  </p>
                ),
            )}
          </section>
          <details>
            <summary>Input and output contracts</summary>
            {typeof section('S2').inputContract === 'string' && (
              <p style={{ whiteSpace: 'pre-wrap' }}>
                <strong>Application input</strong>
                <br />
                {String(section('S2').inputContract)}
              </p>
            )}
            {typeof section('S6').outputContract === 'string' && (
              <p style={{ whiteSpace: 'pre-wrap' }}>
                <strong>Required output</strong>
                <br />
                {String(section('S6').outputContract)}
              </p>
            )}
          </details>
          <details>
            <summary>Authored policy references</summary>
            {policyRefs.length ? (
              <ul>
                {policyRefs.map((policy, index) => (
                  <li key={index}>
                    <strong>
                      {typeof policy.ruleId === 'string'
                        ? policy.ruleId
                        : 'Policy identity missing'}
                    </strong>{' '}
                    · version{' '}
                    {typeof policy.ruleVersion === 'string' ? policy.ruleVersion : 'missing'}
                    <p>
                      {typeof policy.locator === 'string'
                        ? policy.locator
                        : 'Publication locator missing'}
                    </p>
                    <small style={{ overflowWrap: 'anywhere' }}>
                      {typeof policy.contentSha256 === 'string'
                        ? policy.contentSha256
                        : 'Content hash missing'}
                    </small>
                  </li>
                ))}
              </ul>
            ) : (
              <p>No authored state-policy references were captured.</p>
            )}
          </details>
        </>
      )}
      <details>
        <summary>Permitted actions and tools</summary>
        {node?.role && <p>Selected role: {node.role}</p>}
        <ul>
          {roleTools.map((tool) => (
            <li key={tool}>{tool}</li>
          ))}
          {tools.map((tool) => (
            <li key={tool}>{tool}</li>
          ))}
          {records('actions').map((action, i) => (
            <li key={i}>
              {typeof action.id === 'string' ? action.id : 'Action'}
              {typeof action.description === 'string' ? ` — ${action.description}` : ''}
            </li>
          ))}
        </ul>
        {!records('actions').length && !tools.length && !roleTools.length && (
          <p>
            {roles.length
              ? 'Choose an agent stage to inspect its permitted tools.'
              : 'No action list was captured.'}
          </p>
        )}
      </details>
      <details>
        <summary>Actor-visible evidence and policy references</summary>
        {records('evidence')
          .filter((e) => e.visibility === 'actor')
          .map((e, i) => (
            <section key={i}>
              <h4>{typeof e.id === 'string' ? e.id : 'Evidence'}</h4>
              <p style={{ whiteSpace: 'pre-wrap' }}>
                {typeof e.content === 'string'
                  ? e.content
                  : 'See the task artifact for this evidence.'}
              </p>
            </section>
          ))}
        <ul>
          {records('constraints').map((rule, i) => (
            <li key={i}>
              {typeof rule.description === 'string'
                ? rule.description
                : 'See the source task constraint.'}
            </li>
          ))}
        </ul>
      </details>
      <p>
        This viewer shows the captured task definition. It does not imply an observed execution
        path.
      </p>
    </Container>
  );
}
