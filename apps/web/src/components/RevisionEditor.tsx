'use client';

type Resource = {
  kind: string;
  lifecycle: string;
  content: Record<string, unknown>;
};

const fields: Record<string, [string, string][]> = {
  objective: [
    ['hypothesis', 'Observable hypothesis'],
    ['business_context', 'Business context and scope'],
    ['measurement_plan', 'Measurement and acceptance plan'],
  ],
  suite: [
    ['selection_method', 'Selection method'],
    ['exposure_note', 'Exposure and comparison limits'],
  ],
  protocol: [
    ['comparison_policy', 'Comparison policy'],
    ['pass_policy', 'Pass policy'],
  ],
  finding: [
    ['observation', 'Observation'],
    ['hypothesis', 'Hypothesis (optional)'],
    ['output_quote', 'Verbatim output evidence'],
  ],
  task: [],
  rubric: [],
  report: [],
};

export default function RevisionEditor({
  resource,
  busy,
  onSave,
  onClose,
}: {
  resource: Resource;
  busy: boolean;
  onSave: (body: Record<string, unknown>) => void;
  onClose: () => void;
}) {
  const draft = ['draft', 'changes_requested'].includes(resource.lifecycle);
  return (
    <form
      className="card"
      aria-label="Revision editor"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const body = { ...resource.content };
        for (const key of ['title', ...(fields[resource.kind] || []).map(([key]) => key)]) {
          body[key] =
            key === 'hypothesis' && resource.kind === 'finding'
              ? String(data.get(key) || '') || null
              : String(data.get(key) || '');
        }
        // Reports recompute all derived evidence on the server for each new revision.
        if (resource.kind === 'report') {
          delete body.facts;
          delete body.reviewed_findings;
          delete body.evidence_manifest_hash;
        }
        onSave(body);
      }}
    >
      <h2>{draft ? 'Edit draft' : 'Create successor draft'}</h2>
      <p>
        Saving appends a new version and requires fresh review. Existing approvals remain attached
        to the previous version.
      </p>
      {!draft && (
        <p className="banner">
          Dependent runs and downloads require current approved versions. Creating this successor
          may block them until the affected work is reviewed.
        </p>
      )}
      <label htmlFor="revision-title">Title</label>
      <input
        id="revision-title"
        name="title"
        defaultValue={String(resource.content.title || '')}
        minLength={3}
        maxLength={200}
        required
      />
      {(fields[resource.kind] || []).map(([key, label]) => (
        <div key={key}>
          <label htmlFor={'revision-' + key}>{label}</label>
          <textarea
            id={'revision-' + key}
            name={key}
            defaultValue={String(resource.content[key] || '')}
            required={!(resource.kind === 'finding' && key === 'hypothesis')}
          />
        </div>
      ))}
      <p className="muted">
        This editor preserves assigned reviewers, evidence references, task selections and scoring
        rules.
      </p>
      <div className="actions">
        <button className="primary" disabled={busy}>
          Save new version
        </button>
        <button type="button" disabled={busy} onClick={onClose}>
          Cancel editing
        </button>
      </div>
    </form>
  );
}
