type Template = {
  id?: string;
  profile_id?: string;
  catalog_workflow_name?: string | null;
  version?: string | number;
};
type Task = { actor?: unknown; workflow?: unknown; template?: Template | null };
const object = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};

// Source metadata, not execution qualification. Missing declarations stay missing.
export function projectPresentation(tasks: readonly Task[]) {
  const templates = new Set<string>(),
    modes = new Set<string>(),
    execution = new Set<string>();
  for (const task of tasks) {
    const actor = object(task.actor),
      wrapper = object(task.workflow);
    const graph = object(wrapper.graph ?? task.workflow ?? actor.workflowGraph);
    const profile = task.template?.profile_id || object(actor.profile).id;
    const template = task.template;
    if (template) {
      const name = template.catalog_workflow_name || template.profile_id || template.id;
      if (name)
        templates.add(
          `${name} · ${template.version === undefined ? 'version not declared' : 'v' + template.version}`,
        );
    }
    if (profile === 'golden-kyc-reusable-v1') {
      modes.add('Single agent');
      execution.add('Harbor');
    } else if (graph.agentMode === 'MULTI' || graph.agentMode === 'SINGLE') {
      modes.add(graph.agentMode === 'MULTI' ? 'Multi-agent' : 'Single agent');
      execution.add('Harbor + LangGraph');
    } else if (typeof graph.schema_version === 'string' && Array.isArray(graph.nodes)) {
      const roles = new Set(
        graph.nodes
          .map(object)
          .filter((node) => node.kind === 'agent_step' && typeof node.role === 'string')
          .map((node) => node.role),
      );
      modes.add(
        roles.size > 1 ? 'Multi-agent' : roles.size === 1 ? 'Single agent' : 'Not declared',
      );
      execution.add('Harbor + LangGraph');
    } else {
      modes.add('Not declared');
      execution.add('Not declared');
    }
  }
  return {
    templates: templates.size ? [...templates] : ['Template not declared'],
    taskType: modes.size ? [...modes].join(' / ') : 'Not declared',
    execution: execution.size ? [...execution].join(' / ') : 'Not declared',
  };
}
