import contract from '../../../../contracts/workflow/workflow-binding.schema.json';

type Schema = Record<string, any>; // Generated schema is data, never executable code.
export type WorkflowNode = {
  id: string;
  kind: string;
  label: string;
  instruction: string;
  role?: string | null;
  inputs?: string[];
  outputs?: string[];
  decision_artifact?: string | null;
  decision_field?: string | null;
  human_mode?: string | null;
  timeout_seconds?: number | null;
};
export type WorkflowGraph = {
  schema_version: string;
  template_id: string;
  template_version: string;
  entry: string;
  roles: { id: string; responsibility: string; tools: string[] }[];
  nodes: WorkflowNode[];
  edges: { id: string; source: string; target: string; outcome: string; loop?: string | null }[];
  artifacts?: { id: string; producer: string; readers: string[]; fields: Record<string, string> }[];
  loops?: { id: string; edge: string; max_iterations: number; exhausted: string }[];
  bounds: {
    transitions: number;
    calls: number;
    wall_seconds: number;
    tokens: number;
    cost_micro_usd: number;
  };
};

// Deliberately small evaluator for this checked-in generated schema. No remote
// refs, coercion, defaults, dynamic expressions or third-party validator required.
function matches(value: unknown, schema: Schema, depth = 0): boolean {
  if (depth > 32) return false;
  if (schema.$ref) {
    const name = schema.$ref.replace('#/$defs/', '');
    return (
      !!(contract.$defs as Schema)[name] &&
      matches(value, (contract.$defs as Schema)[name], depth + 1)
    );
  }
  if (schema.anyOf && !schema.anyOf.some((s: Schema) => matches(value, s, depth + 1))) return false;
  if (schema.const !== undefined && value !== schema.const) return false;
  if (schema.enum && !schema.enum.includes(value)) return false;
  switch (schema.type) {
    case 'null':
      return value === null;
    case 'string':
      return (
        typeof value === 'string' &&
        !value.includes('\0') &&
        !/[\uD800-\uDFFF]/u.test(value) &&
        Array.from(value).length >= (schema.minLength ?? 0) &&
        Array.from(value).length <= (schema.maxLength ?? Infinity) &&
        (!schema.pattern || new RegExp(schema.pattern).test(value))
      );
    case 'integer':
      return (
        typeof value === 'number' &&
        Number.isSafeInteger(value) &&
        value >= (schema.minimum ?? -Infinity) &&
        value <= (schema.maximum ?? Infinity)
      );
    case 'array':
      return (
        Array.isArray(value) &&
        value.length >= (schema.minItems ?? 0) &&
        value.length <= (schema.maxItems ?? Infinity) &&
        value.every((v) => matches(v, schema.items, depth + 1))
      );
    case 'object': {
      if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
      const record = value as Record<string, unknown>;
      if (
        Object.keys(record).length < (schema.minProperties ?? 0) ||
        Object.keys(record).length > (schema.maxProperties ?? Infinity) ||
        !(schema.required ?? []).every((k: string) => Object.hasOwn(record, k))
      )
        return false;
      return Object.entries(record).every(([k, v]) => {
        if (schema.propertyNames && !matches(k, schema.propertyNames, depth + 1)) return false;
        if (schema.properties && Object.hasOwn(schema.properties, k))
          return matches(v, schema.properties[k], depth + 1);
        return schema.additionalProperties === false
          ? false
          : typeof schema.additionalProperties === 'object'
            ? matches(v, schema.additionalProperties, depth + 1)
            : true;
      });
    }
    default:
      return true;
  }
}

export function workflowGraph(value: unknown): WorkflowGraph | null {
  try {
    if (!matches(value, contract.$defs.WorkflowGraph)) return null;
    const g = value as WorkflowGraph;
    const artifacts = g.artifacts ?? [],
      loops = g.loops ?? [];
    for (const group of [g.nodes, g.edges, g.roles, artifacts, loops])
      if (new Set(group.map((v) => v.id)).size !== group.length) return null;
    const nodes = new Map(g.nodes.map((n) => [n.id, n]));
    const roles = new Set(g.roles.map((r) => r.id));
    const art = new Map(artifacts.map((a) => [a.id, a]));
    const edgeById = new Map(g.edges.map((e) => [e.id, e]));
    if (nodes.get(g.entry)?.kind !== 'input') return null;
    for (const e of g.edges) {
      if (!nodes.has(e.source) || !nodes.has(e.target)) return null;
      if (e.loop && loops.find((l) => l.id === e.loop)?.edge !== e.id) return null;
    }
    for (const n of g.nodes) {
      const inputs = n.inputs ?? [],
        outputs = n.outputs ?? [];
      if (
        new Set(inputs).size !== inputs.length ||
        new Set(outputs).size !== outputs.length ||
        [...inputs, ...outputs].some((id) => !art.has(id))
      )
        return null;
      if (n.role && !roles.has(n.role)) return null;
      if (['agent_step', 'human_step'].includes(n.kind) && !n.role) return null;
      if (
        n.kind === 'human_step'
          ? !n.human_mode || !n.timeout_seconds
          : !!n.human_mode || !!n.timeout_seconds
      )
        return null;
      if (n.kind === 'decision') {
        if (
          !n.decision_artifact ||
          !n.decision_field ||
          !inputs.includes(n.decision_artifact) ||
          !['boolean', 'boolean_or_unknown'].includes(
            art.get(n.decision_artifact)?.fields[n.decision_field] ?? '',
          )
        )
          return null;
      } else if (n.decision_artifact || n.decision_field) return null;
      const outcomes = g.edges.filter((e) => e.source === n.id).map((e) => e.outcome);
      const expected =
        n.kind === 'decision'
          ? ['true', 'false', 'unknown', 'error']
          : n.kind === 'human_step'
            ? ['next', 'timeout', 'error']
            : ['output', 'escalation'].includes(n.kind)
              ? []
              : ['next'];
      const actual = [...new Set(outcomes.filter((o) => o !== 'exhausted'))].sort();
      if (actual.join() !== expected.sort().join()) return null;
      if (['decision', 'human_step'].includes(n.kind) && new Set(outcomes).size !== outcomes.length)
        return null;
      if (n.kind === 'join' && g.edges.filter((e) => e.target === n.id).length < 2) return null;
      if (n.kind === 'input' && n.id !== g.entry) return null;
      if (outputs.some((id) => art.get(id)?.producer !== n.id)) return null;
      if (n.role && inputs.some((id) => !art.get(id)?.readers.includes(n.role!))) return null;
    }
    for (const a of artifacts) {
      if (
        !nodes.get(a.producer)?.outputs?.includes(a.id) ||
        a.readers.some((r) => !roles.has(r)) ||
        new Set(a.readers).size !== a.readers.length
      )
        return null;
    }
    const forward = (id: string) =>
      g.edges.filter((e) => e.source === id && !e.loop).map((e) => e.target);
    const reverse = (id: string) =>
      g.edges.filter((e) => e.target === id && !e.loop).map((e) => e.source);
    const reach = (id: string, adjacent: (id: string) => string[]) => {
      const seen = new Set<string>(),
        todo = [id];
      while (todo.length) {
        const n = todo.pop()!;
        if (!seen.has(n)) {
          seen.add(n);
          todo.push(...adjacent(n));
        }
      }
      return seen;
    };
    const visiting = new Set<string>(),
      visited = new Set<string>();
    const visit = (id: string) => {
      if (visiting.has(id)) throw Error('undeclared_cycle');
      if (visited.has(id)) return;
      visiting.add(id);
      forward(id).forEach(visit);
      visiting.delete(id);
      visited.add(id);
    };
    visit(g.entry);
    if (
      g.nodes.some((n) =>
        (n.inputs ?? []).some(
          (a) => art.get(a)!.producer === n.id || !reach(art.get(a)!.producer, forward).has(n.id),
        ),
      )
    )
      return null;
    if (
      visited.size !== nodes.size ||
      g.nodes.some(
        (n) =>
          ![...reach(n.id, forward)].some((id) =>
            ['output', 'escalation'].includes(nodes.get(id)!.kind),
          ),
      )
    )
      return null;
    const regions: Set<string>[] = [];
    for (const l of loops) {
      const e = edgeById.get(l.edge);
      if (!e || e.loop !== l.id || !['true', 'false'].includes(e.outcome) || e.source === e.target)
        return null;
      const downstream = reach(e.target, forward),
        upstream = reach(e.source, reverse);
      const region = new Set([...downstream].filter((n) => upstream.has(n)));
      if (!downstream.has(e.source) || region.has(l.exhausted) || !nodes.has(l.exhausted))
        return null;
      const exits = g.edges.filter((x) => x.source === e.source && x.outcome === 'exhausted');
      if (exits.length !== 1 || exits[0].target !== l.exhausted || exits[0].loop) return null;
      if (regions.some((other) => [...region].some((n) => other.has(n)))) return null;
      if (
        g.edges.some((x) => region.has(x.target) && x.target !== e.target && !region.has(x.source))
      )
        return null;
      regions.push(region);
    }
    if (
      g.edges.some(
        (e) =>
          e.outcome === 'exhausted' &&
          !loops.some((l) => l.exhausted === e.target && edgeById.get(l.edge)?.source === e.source),
      )
    )
      return null;
    return g;
  } catch {
    return null;
  }
}
