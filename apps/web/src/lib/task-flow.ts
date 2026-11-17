// Display projection only. Never infer decisions or loops from task prose.
import { workflowGraph } from './workflow-graph';
export type FlowNode = {
  id: string;
  label: string;
  instruction: string;
  kind?: string;
  detail?: string;
  role?: string;
};
export type TaskFlow = {
  nodes: FlowNode[];
  edges: { from: string; to: string; label?: string; loop?: boolean }[];
  reason: string;
};
const record = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
const text = (value: unknown, maximum = 20000): value is string =>
  typeof value === 'string' && value.length <= maximum && !value.includes('\0');

// Read-only projection of Praxis's published wire format. This never grants
// execution authority or rewrites the source into Anvil's runtime graph schema.
function praxisFlow(value: unknown): TaskFlow | null {
  const graph = record(value);
  if (
    !graph ||
    !['praxis.workflow_graph.v1', 'praxis.workflow_graph.v1-proposed'].includes(
      String(graph.schemaVersion),
    )
  )
    return null;
  const array = (value: unknown, maximum: number) =>
    Array.isArray(value) && value.length <= maximum && value.every((item) => record(item))
      ? (value as Record<string, unknown>[])
      : null;
  const nodes = array(graph.nodes, 100),
    edges = array(graph.edges, 400),
    roles = array(graph.roles, 30),
    artifacts = array(graph.artifacts, 300),
    loops = array(graph.loops ?? [], 30);
  if (!nodes?.length || !edges || !roles || !artifacts || !loops) return null;
  const unique = (rows: Record<string, unknown>[]) =>
    rows.every((row) => text(row.id, 120) && row.id.length > 0) &&
    new Set(rows.map((row) => row.id)).size === rows.length;
  if (![nodes, edges, roles, artifacts, loops].every(unique)) return null;
  const nodeIds = new Set(nodes.map((node) => node.id)),
    roleById = new Map(roles.map((role) => [role.id, role])),
    artifactById = new Map(artifacts.map((artifact) => [artifact.id, artifact]));
  const edgeById = new Map(edges.map((edge) => [edge.id, edge]));
  const loopByEdge = new Map<string, Record<string, unknown>>();
  for (const loop of loops) {
    if (
      !text(loop.returnEdgeId, 120) ||
      !edgeById.has(loop.returnEdgeId) ||
      loopByEdge.has(loop.returnEdgeId) ||
      !Number.isSafeInteger(loop.maxIterations) ||
      Number(loop.maxIterations) < 1 ||
      Number(loop.maxIterations) > 1000 ||
      !nodeIds.has(loop.exhaustedTarget)
    )
      return null;
    loopByEdge.set(loop.returnEdgeId, loop);
  }
  for (const edge of edges)
    if (
      !nodeIds.has(edge.from) ||
      !nodeIds.has(edge.to) ||
      !text(edge.label ?? '', 500) ||
      (edge.port !== undefined && !text(edge.port, 120))
    )
      return null;
  const kinds = new Set([
    'input',
    'agent_step',
    'decision',
    'join',
    'human_step',
    'external_system',
    'output',
    'escalation',
  ]);
  for (const node of nodes) {
    if (!kinds.has(String(node.type)) || !text(node.label, 300)) return null;
    if (node.type === 'agent_step' && !roleById.has(node.roleId)) return null;
    if (node.roleId !== undefined && !roleById.has(node.roleId)) return null;
    for (const key of ['inputRefs', 'provides', 'sendsRefs', 'permittedEvidence']) {
      const refs = node[key];
      if (
        refs !== undefined &&
        (!Array.isArray(refs) ||
          refs.length > 300 ||
          refs.some((id) => !artifactById.has(id) || artifactById.get(id)?.visibility !== 'actor'))
      )
        return null;
    }
    for (const key of ['outputArtifact', 'returnsArtifact'])
      if (
        node[key] !== undefined &&
        (!artifactById.has(node[key]) || artifactById.get(node[key])?.visibility !== 'actor')
      )
        return null;
    if (
      node.type === 'join' &&
      (!Array.isArray(node.requiredInputs) ||
        node.requiredInputs.length < 2 ||
        node.requiredInputs.some(
          (id) =>
            !nodeIds.has(id) || !edges.some((edge) => edge.from === id && edge.to === node.id),
        ))
    )
      return null;
    if (
      !['instruction', 'prompt', 'request', 'question'].every(
        (key) => node[key] === undefined || text(node[key]),
      )
    )
      return null;
  }
  // Undeclared cycles are not guessed to be bounded returns by this viewer.
  const visiting = new Set<unknown>(),
    visited = new Set<unknown>();
  function visit(id: unknown): boolean {
    if (visiting.has(id)) return false;
    if (visited.has(id)) return true;
    visiting.add(id);
    if (
      !edges!
        .filter((edge) => edge.from === id && !loopByEdge.has(String(edge.id)))
        .every((edge) => visit(edge.to))
    )
      return false;
    visiting.delete(id);
    visited.add(id);
    return true;
  }
  if (!nodes.every((node) => visit(node.id))) return null;
  return {
    nodes: nodes.map((node) => {
      const role = roleById.get(node.roleId);
      return {
        id: String(node.id),
        label: String(node.label),
        kind: String(node.type),
        role: role ? String(role.name || role.id) : undefined,
        instruction: String(node.instruction ?? node.prompt ?? node.request ?? node.question ?? ''),
        detail: [
          String(node.type),
          role && `Role: ${role.name || role.id}`,
          node.type === 'human_step' &&
            (node.simulated === true ? 'Environment-simulated approver' : 'Authored human step'),
          node.type === 'external_system' && `External system: ${node.system || node.label}`,
          Array.isArray(node.inputRefs) &&
            node.inputRefs.length &&
            `Inputs: ${node.inputRefs.join(', ')}`,
          node.outputArtifact && `Output: ${node.outputArtifact}`,
          node.type === 'join' && `Requires: ${(node.requiredInputs as string[]).join(', ')}`,
        ]
          .filter(Boolean)
          .join(' · '),
      };
    }),
    edges: edges.map((edge) => {
      const loop = loopByEdge.get(String(edge.id));
      const label = String(edge.label || edge.port || '');
      return {
        from: String(edge.from),
        to: String(edge.to),
        loop: !!loop,
        label: loop
          ? `${label} · max ${loop.maxIterations} returns · exhausted → ${loop.exhaustedTarget}`
          : label,
      };
    }),
    reason: `Authoring workflow (${graph.schemaVersion}); ${roles.length} role${roles.length === 1 ? '' : 's'}. Definition only; runtime qualification is separate.`,
  };
}
export function taskFlow(actor: unknown): TaskFlow {
  const empty = (reason: string): TaskFlow => ({ nodes: [], edges: [], reason });
  if (!actor || typeof actor !== 'object') return empty('No structured task flow was captured.');
  const source = actor as Record<string, unknown>;
  if (source.workflowGraph) {
    const authored = praxisFlow(source.workflowGraph);
    if (authored) return authored;
    const graph = workflowGraph(source.workflowGraph);
    if (!graph) return empty('This workflow graph is malformed or uses unsupported semantics.');
    return {
      nodes: graph.nodes.map((n) => ({
        id: n.id,
        label: n.label,
        instruction: n.instruction,
        kind: n.kind,
        role: n.role || undefined,
        detail: [
          n.kind,
          n.role && `Role: ${n.role}`,
          n.human_mode === 'scripted_fixture'
            ? 'Scripted human response'
            : n.human_mode === 'actual'
              ? 'Actual human response — execution unavailable until restore/resume qualification'
              : '',
          n.timeout_seconds && `Timeout: ${n.timeout_seconds}s`,
          n.inputs?.length && `Inputs: ${n.inputs.join(', ')}`,
          n.outputs?.length && `Outputs: ${n.outputs.join(', ')}`,
        ]
          .filter(Boolean)
          .join(' · '),
      })),
      edges: graph.edges.map((e) => ({
        from: e.source,
        to: e.target,
        label: e.loop
          ? `${e.outcome} · max ${graph.loops!.find((l) => l.id === e.loop)!.max_iterations} returns`
          : e.outcome,
        loop: !!e.loop,
      })),
      reason: 'Authored workflow graph v1. Definition only; runtime qualification is separate.',
    };
  }
  if (record(source.profile)?.id === 'golden-kyc-reusable-v1') {
    const steps = record(record(source.sections)?.S5)?.steps;
    if (Array.isArray(steps) && steps.length > 0 && steps.length <= 100) {
      if (
        !steps.every((step) => {
          const value = record(step);
          return (
            value &&
            text(value.action) &&
            value.action.trim().length > 0 &&
            (value.tool === undefined || text(value.tool, 300)) &&
            (value.failureBehaviour === undefined || text(value.failureBehaviour))
          );
        })
      )
        return empty('The authored KYC procedure has an unsupported step format.');
      const nodes = steps.map((value, index) => {
        const step = value as Record<string, string>;
        return {
          id: `procedure-step-${index + 1}`,
          label: `Step ${index + 1} · ${step.action.slice(0, 70)}`,
          instruction: step.action,
          detail: [
            step.tool && `Tool: ${step.tool}`,
            step.failureBehaviour && `Failure handling: ${step.failureBehaviour}`,
          ]
            .filter(Boolean)
            .join(' · '),
        };
      });
      return {
        nodes,
        edges: nodes.slice(1).map((node, index) => ({ from: nodes[index].id, to: node.id })),
        reason:
          'Single-agent KYC procedure in its authored order. Display step numbers do not create runtime graph IDs; no decisions, handoffs or loops are inferred from prose.',
      };
    }
  }
  if (!Array.isArray(source.stages) || !source.stages.length)
    return empty('No ordered stages were captured. Task instructions are available below.');
  if (source.stages.length > 100) return empty('The captured flow exceeds the viewer limit.');
  const nodes: FlowNode[] = [];
  const ids = new Set<string>();
  for (const raw of source.stages) {
    if (!raw || typeof raw !== 'object') return empty('The captured stage format is unsupported.');
    const stage = raw as Record<string, unknown>;
    if (
      typeof stage.id !== 'string' ||
      !stage.id ||
      ids.has(stage.id) ||
      typeof stage.instruction !== 'string' ||
      stage.instruction.length > 20000
    )
      return empty('The captured stage format is unsupported.');
    ids.add(stage.id);
    nodes.push({ id: stage.id, label: stage.id, instruction: stage.instruction });
  }
  return {
    nodes,
    edges: nodes.slice(1).map((node, i) => ({ from: nodes[i].id, to: node.id })),
    reason:
      'Ordered stage projection from the frozen task. No decisions, human steps or loops have been inferred.',
  };
}
const xml = (value: string) =>
  value.replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' })[c]!,
  );
export function taskFlowLayout(flow: TaskFlow) {
  const forward = flow.edges.filter((edge) => !edge.loop);
  const degree = new Map(
    flow.nodes.map((node) => [node.id, forward.filter((edge) => edge.to === node.id).length]),
  );
  const level = new Map(flow.nodes.map((node) => [node.id, 0]));
  const queue = flow.nodes.filter((node) => degree.get(node.id) === 0).map((node) => node.id);
  for (let index = 0; index < queue.length; index++)
    for (const edge of forward.filter((edge) => edge.from === queue[index])) {
      level.set(edge.to, Math.max(level.get(edge.to) || 0, (level.get(edge.from) || 0) + 1));
      degree.set(edge.to, (degree.get(edge.to) || 0) - 1);
      if (degree.get(edge.to) === 0) queue.push(edge.to);
    }
  const groups = new Map<number, FlowNode[]>();
  for (const node of flow.nodes) {
    const rank = level.get(node.id) || 0;
    groups.set(rank, [...(groups.get(rank) || []), node]);
  }
  const gutter = 60 + flow.edges.filter((edge) => edge.loop).length * 12;
  const width = Math.max(
    660,
    ...[...groups.values()].map((nodes) => nodes.length * 240 + gutter * 2),
  );
  const positions = flow.nodes.map((node) => {
    const rank = level.get(node.id) || 0,
      peers = groups.get(rank)!;
    return {
      node,
      x:
        (width - peers.length * 240) / 2 +
        peers.findIndex((peer) => peer.id === node.id) * 240 +
        20,
      y: 100 + rank * 140,
      width: 200,
      height: 90,
    };
  });
  const byId = new Map(positions.map((position) => [position.node.id, position]));
  let loops = 0,
    skips = 0;
  const edges = flow.edges.flatMap((edge) => {
    const a = byId.get(edge.from),
      b = byId.get(edge.to);
    if (!a || !b) return [];
    if (edge.loop) {
      const x = 20 + loops++ * 12;
      return [
        {
          ...edge,
          path: `M${a.x} ${a.y + 45} H${x} V${b.y + 45} H${b.x}`,
          labelX: x + 4,
          labelY: a.y + 30,
        },
      ];
    }
    const startX = a.x + 100,
      endX = b.x + 100,
      startY = a.y + 90,
      endY = b.y;
    if (endY - startY > 100) {
      const x = width - 18 - (skips++ % 5) * 10;
      return [
        {
          ...edge,
          path: `M${startX} ${startY} V${startY + 16} H${x} V${endY - 16} H${endX} V${endY}`,
          labelX: x - 8,
          labelY: startY + 12,
        },
      ];
    }
    const y = (startY + endY) / 2;
    return [
      {
        ...edge,
        path: `M${startX} ${startY} V${y} H${endX} V${endY}`,
        labelX: Math.min(startX, endX) + 5,
        labelY: y - 5,
      },
    ];
  });
  return {
    width,
    height: Math.max(300, ...positions.map((position) => position.y + position.height + 75)),
    nodes: positions,
    edges,
  };
}
export function taskFlowSvg(
  flow: TaskFlow,
  title: string,
  version: string,
  selectedId?: string,
): string {
  const width = Math.max(600, flow.nodes.length * 220 + 40);
  if (flow.nodes.some((n) => n.kind)) {
    const layout = taskFlowLayout(flow);
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${layout.width}" height="${layout.height}" role="img" aria-label="Read-only authored workflow"><title>${xml(title)} — ${xml(version)}</title><rect width="100%" height="100%" fill="white"/><text x="20" y="25" font-family="sans-serif">${xml(title.slice(0, 100))}</text><text x="20" y="50" font-family="sans-serif">Task version: ${xml(version)} · Authored workflow · Read only</text><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="#45677d"/></marker></defs>${layout.edges
      .map((e) => {
        const label = e.loop
          ? e.label?.match(/max \d+ returns/)?.[0] || 'Bounded return'
          : (e.label || '').slice(0, 36);
        const anchor = !e.loop && e.labelX > layout.width - 120 ? 'end' : 'start';
        return `<g><title>${xml(e.label || '')}</title><path d="${e.path}" fill="none" stroke="${e.loop ? '#965b14' : '#45677d'}" marker-end="url(#arrow)"/><text x="${e.labelX}" y="${e.labelY}" text-anchor="${anchor}" font-size="10" font-family="sans-serif">${xml(label)}</text></g>`;
      })
      .join('')}${layout.nodes
      .map(({ node: n, x, y }) => {
        const stroke = n.id === selectedId ? '#087f82' : '#45677d';
        const fill =
          n.id === selectedId
            ? '#ccece9'
            : n.kind === 'human_step'
              ? '#e9e0f5'
              : n.kind === 'escalation'
                ? '#ffe4e4'
                : n.kind === 'join'
                  ? '#dff1e5'
                  : n.kind === 'external_system'
                    ? '#fff4d8'
                    : '#eef5f9';
        return `<g><title>${xml(n.label)}${n.role ? ' · ' + xml(n.role) : ''}</title>${n.kind === 'decision' ? `<polygon points="${x + 100},${y} ${x + 200},${y + 45} ${x + 100},${y + 90} ${x},${y + 45}" fill="#fff4d8" stroke="${stroke}"/>` : `<rect x="${x}" y="${y}" width="200" height="90" rx="${n.kind === 'human_step' ? 25 : 8}" fill="${fill}" stroke="${stroke}" stroke-width="${n.id === selectedId ? 3 : 1}"/>`}<text x="${x + 12}" y="${y + 32}" font-family="sans-serif" font-size="12">${xml(n.label.slice(0, 27))}</text><text x="${x + 12}" y="${y + 48}" font-family="sans-serif" font-size="12">${xml(n.label.slice(27, 54))}</text><text x="${x + 12}" y="${y + 68}" font-family="sans-serif" font-size="9">${xml((n.role || n.kind || '').slice(0, 35))}</text></g>`;
      })
      .join(
        '',
      )}<text x="20" y="${layout.height - 20}" font-family="sans-serif" font-size="11">Authored definition only; no observed execution or human approval implied.</text></svg>`;
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="230" viewBox="0 0 ${width} 230" role="img" aria-label="Read-only task flow"><title>${xml(title)} — ${xml(version)}</title><rect width="100%" height="100%" fill="white"/><text x="20" y="30" fill="#17354b" font-family="sans-serif" font-size="17">${xml(title.slice(0, 100))}</text><text x="20" y="55" fill="#425b6c" font-family="sans-serif" font-size="12">Task version: ${xml(version)} · Ordered stage projection · Read only</text><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="#45677d"/></marker></defs>${flow.nodes.map((node, i) => `${i ? `<line x1="${20 + (i - 1) * 220 + 180}" y1="135" x2="${20 + i * 220}" y2="135" stroke="#45677d" stroke-width="2" marker-end="url(#arrow)"/>` : ''}<g><rect x="${20 + i * 220}" y="95" width="180" height="80" rx="10" fill="#eef5f9" stroke="#45677d"/><text x="${30 + i * 220}" y="140" font-family="sans-serif" font-size="14" fill="#17354b">${xml(node.label.slice(0, 22))}</text></g>`).join('')}<text x="20" y="210" fill="#425b6c" font-family="sans-serif" font-size="12">Authored stages only; no observed execution path is implied.</text></svg>`;
}
