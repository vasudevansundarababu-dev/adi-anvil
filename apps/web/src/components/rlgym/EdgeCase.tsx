'use client';

// A new case kind (or an S4 edge case) in the same four plain-English parts (work package 2.12): scenario context,
// the edge-case twist, the expected outcome and rationale, and slice tags (complexity, archetype).

export type EdgeParts = {
  scenario_context: string;
  twist: string;
  expected_outcome: string;
  rationale: string;
  complexity: string;
  archetype: string;
};

export const emptyEdge: EdgeParts = {
  scenario_context: '',
  twist: '',
  expected_outcome: '',
  rationale: '',
  complexity: '',
  archetype: '',
};

/** Complete when the three text parts are filled; slice tags may default to the episode's task on the server. */
export function edgeReady(p: EdgeParts, needTags: boolean) {
  const text = p.scenario_context.trim() && p.twist.trim() && p.expected_outcome.trim();
  return Boolean(text && (!needTags || (p.complexity.trim() && p.archetype.trim())));
}

export function edgeBody(p: EdgeParts) {
  return {
    scenario_context: p.scenario_context,
    twist: p.twist,
    expected_outcome: p.expected_outcome,
    rationale: p.rationale || undefined,
    slice_tags: { complexity: p.complexity || undefined, archetype: p.archetype || undefined },
  };
}

export function EdgeCaseForm({
  value,
  onChange,
  lists,
  tagsHint,
}: {
  value: EdgeParts;
  onChange: (p: EdgeParts) => void;
  lists?: { complexity?: string[]; archetype?: string[] };
  tagsHint?: string;
}) {
  const set = (k: keyof EdgeParts) => (e: { target: { value: string } }) =>
    onChange({ ...value, [k]: e.target.value });
  const tag = (k: 'complexity' | 'archetype', label: string) =>
    lists?.[k]?.length ? (
      <label>
        {label}
        <select value={value[k]} onChange={set(k)}>
          <option value="">Choose…</option>
          {lists[k]!.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      </label>
    ) : (
      <label>
        {label}
        <input value={value[k]} onChange={set(k)} placeholder={tagsHint} />
      </label>
    );
  return (
    <fieldset className="edge-parts">
      <label>
        1 · Scenario context (who the customer is, what they ask for)
        <textarea rows={2} value={value.scenario_context} onChange={set('scenario_context')} />
      </label>
      <label>
        2 · Edge-case twist (the anomaly, conflict or missing record)
        <textarea rows={2} value={value.twist} onChange={set('twist')} />
      </label>
      <label>
        3 · Expected outcome (the exact decision)
        <input value={value.expected_outcome} onChange={set('expected_outcome')} />
      </label>
      <label>
        Rationale (why)
        <input value={value.rationale} onChange={set('rationale')} />
      </label>
      <div className="row">
        {tag('complexity', '4 · Complexity')}
        {tag('archetype', 'Archetype')}
      </div>
    </fieldset>
  );
}
