import { useRef, useState } from 'react';

const topics: Record<string, string[]> = {
  factory: ['How are benchmark matches ranked?', 'What does catalog registration mean?'],
  objectives: ['How do I write a measurable objective?', 'What is required for approval?'],
  imports: ['Why is input required?', 'Why is publication blocked?', 'How do I resume an import?'],
  suites: ['How are dataset versions attached?', 'Why freeze a suite?'],
  protocols: ['What does a protocol bind?', 'Can I change a frozen version?'],
  runs: ['Why can’t I launch imported tasks?', 'Which dataset version will run?'],
};
const definitions = [
  {
    keys: ['benchmark', 'catalog', 'rank', 'profile'],
    text: 'Confirm all fourteen TaskProfile dimensions against the selected published tasks. Matching uses hard interface/schema/modality/environment/access/rights filters followed by fixed weighted metadata overlap. Registration stores metadata only; adapter smoke qualification remains pending. Recommendations pin exact revisions. Overrides need a recorded rationale; gap creation saves a draft and starts no execution.',
    field: 'factory-objective',
  },
  {
    keys: ['input', 'mapping', 'taskspec'],
    text: 'TaskSpec 1.0 requires schema_version, external_id, instruction and input. Input is a JSON object containing information available to the candidate. Keep reference answers in the separate reference field. CSV requires explicit external_id, instruction and input mappings.',
    field: 'map-input',
  },
  {
    keys: ['publish', 'publication', 'blocked'],
    text: 'Publish is available only after ingestion completes with zero blocking errors and the objective remains approved. Publication freezes a data version; it does not grant rights, approve scoring or start a model. Use the primary publication control; Anvil Help cannot publish or approve.',
    field: 'task-source',
  },
  {
    keys: ['resume', 'retry', 'cancel'],
    text: 'The import monitor shows durable progress. Cancel stops further chunks. Retry resumes a failed or cancelled import from its last committed checkpoint, up to three explicit retries. Help cannot perform these actions.',
    field: 'task-source',
  },
  {
    keys: ['objective', 'measurable', 'approval'],
    text: 'Describe an observable hypothesis, business context and measurement/acceptance plan. Separate Researcher, Advisor and Product Owner reviews are required. A synthetic example: assess whether a candidate preserves budget constraints across five original tasks.',
    field: 'hypothesis',
  },
  {
    keys: ['version', 'suite', 'protocol', 'freeze', 'dataset'],
    text: 'A DatasetVersion is immutable. A suite attachment stores its exact version ID. A protocol binds an approved objective and frozen suite. Run configuration records the selected DatasetVersion and TaskSpec schema version; later imports never replace it.',
    field: 'dataset-suite',
  },
  {
    keys: ['run', 'launch', 'model'],
    text: 'The current importer reaches run configuration. Arbitrary imported tasks still require execution qualification and a supported adapter. Fixture responses cannot evaluate them. Live model calls remain disabled and require separate rights and paid approvals.',
    field: 'dataset-protocol',
  },
];

export default function AnvilHelp({ screen }: { screen: string }) {
  const [open, setOpen] = useState(false),
    [question, setQuestion] = useState('');
  const [answers, setAnswers] = useState<{ text: string; field?: string }[]>([]);
  const [feedback, setFeedback] = useState('');
  const launcher = useRef<HTMLButtonElement>(null),
    input = useRef<HTMLInputElement>(null);
  function ask(value: string) {
    const lower = value.toLowerCase();
    const answer = definitions.find((d) => d.keys.some((k) => lower.includes(k)));
    setAnswers((old) => [
      ...old,
      answer || {
        text: 'Static help has no grounded answer for that question. Check the screen’s validation message and the task-import documentation. I cannot inspect your uploaded data, credentials or another project.',
      },
    ]);
    setQuestion('');
    setFeedback('');
  }
  return (
    <aside className="card" aria-label="Anvil Help">
      <button
        ref={launcher}
        aria-expanded={open}
        onClick={() => {
          setOpen(!open);
          if (!open) requestAnimationFrame(() => input.current?.focus());
        }}
      >
        Anvil Help
      </button>
      {open && (
        <div
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              setOpen(false);
              launcher.current?.focus();
            }
          }}
        >
          <h2>Anvil Help — {screen}</h2>
          <p>
            Static grounded help · TaskSpec 1.0 / ingestion foundation v1. No model calls. Questions
            stay in this component’s memory and are not sent or saved. Do not enter secrets.
          </p>
          <div className="actions">
            {(
              topics[screen] || ['What is the next workflow step?', 'What does a protocol bind?']
            ).map((q) => (
              <button key={q} onClick={() => ask(q)}>
                {q}
              </button>
            ))}
          </div>
          <label htmlFor="anvil-help-question">Ask about this screen (Optional)</label>
          <input
            ref={input}
            id="anvil-help-question"
            value={question}
            maxLength={500}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && question.trim()) ask(question);
            }}
          />
          <button disabled={!question.trim()} onClick={() => ask(question)}>
            Ask
          </button>
          <div aria-live="polite">
            {answers.map((a, i) => (
              <div key={i}>
                <p>{a.text}</p>
                {a.field && (
                  <button onClick={() => document.getElementById(a.field!)?.focus()}>
                    Focus related field (when visible)
                  </button>
                )}
              </div>
            ))}
          </div>
          <p>
            <a href="/help/task-import.html" target="_blank" rel="noreferrer">
              Static help and error documentation
            </a>
          </p>
          {!!answers.length && (
            <>
              <button onClick={() => setFeedback('Helpful feedback noted for this session.')}>
                Helpful
              </button>
              <button
                onClick={() =>
                  setFeedback(
                    'Unhelpful feedback noted for this session. Use the documentation for further guidance.',
                  )
                }
              >
                Unhelpful
              </button>
              <p role="status">{feedback}</p>
            </>
          )}
          <button
            onClick={() => {
              setAnswers([]);
              setQuestion('');
              setFeedback('');
            }}
          >
            Reset conversation
          </button>
          <button
            onClick={() => {
              setOpen(false);
              launcher.current?.focus();
            }}
          >
            Collapse help
          </button>
        </div>
      )}
    </aside>
  );
}
