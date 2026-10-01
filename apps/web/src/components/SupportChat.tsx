'use client';
import { useEffect, useRef, useState } from 'react';

type Api = (path: string, method?: string, body?: unknown) => Promise<any>; // eslint-disable-line @typescript-eslint/no-explicit-any
type Turn = { role: 'user' | 'assistant'; text: string };

const SUGGESTIONS = [
  'What do I need to fill in on this screen?',
  'How does the Product Owner approval work?',
  'How are outputs graded?',
];

// Only labels, headings and form fields are sent: never page text such as outputs or references.
function readScreen() {
  const main = document.querySelector('main');
  const text = (el: Element | null | undefined) => (el?.textContent || '').trim().slice(0, 200);
  const fields = Array.from(
    main?.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(
      'input,select,textarea',
    ) || [],
  )
    .filter((f) => f.type !== 'hidden' && !f.closest('[data-support-ignore]'))
    .slice(0, 80)
    .map((f) => {
      const label = (
        f.labels?.[0]?.textContent ||
        f.getAttribute('aria-label') ||
        f.name ||
        'Field'
      )
        .replace(' * Required', '')
        .trim()
        .slice(0, 200);
      const isChoice = f.type === 'checkbox' || f.type === 'radio';
      return {
        label,
        type: (f instanceof HTMLSelectElement ? 'select' : f.type || 'text').slice(0, 40),
        required: f.required,
        value:
          f.type === 'password' || f.type === 'file'
            ? ''
            : isChoice
              ? String((f as HTMLInputElement).checked)
              : String(f.value || '').slice(0, 500),
        options:
          f instanceof HTMLSelectElement
            ? Array.from(f.options)
                .map((o) => o.text.slice(0, 60))
                .slice(0, 40)
            : [],
      };
    });
  return {
    path: location.pathname.slice(0, 300),
    title: text(main?.querySelector('h1')),
    headings: Array.from(main?.querySelectorAll('h2,h3') || [])
      .map((h) => text(h))
      .filter(Boolean)
      .slice(0, 30),
    fields,
    messages: Array.from(main?.querySelectorAll('[role=alert],[role=status]') || [])
      .map((m) => text(m))
      .filter(Boolean)
      .slice(0, 10),
  };
}

export default function SupportChat({ base, api }: { base: string; api: Api }) {
  const [open, setOpen] = useState(false),
    [turns, setTurns] = useState<Turn[]>([]),
    [question, setQuestion] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'end' });
  }, [turns, busy]);

  async function ask(q: string) {
    const text = q.trim();
    if (!text || busy) return;
    setBusy(true);
    setError('');
    setQuestion('');
    const history = turns.slice(-12);
    setTurns([...turns, { role: 'user', text }]);
    try {
      const result = await api(base + '/support/ask', 'POST', {
        question: text,
        history,
        screen: readScreen(),
      });
      setTurns((t) => [...t, { role: 'assistant', text: result.answer }]);
    } catch (e) {
      setError((e as Error).message + ' The Anvil Help topics on this page still work.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="support" data-support-ignore>
      {open && (
        <section className="support-panel card" role="dialog" aria-label="Ask Anvil">
          <div className="toolbar">
            <strong>Ask Anvil</strong>
            <button type="button" onClick={() => setOpen(false)} aria-label="Close Ask Anvil">
              Close
            </button>
          </div>
          <p className="muted">
            Answers about this screen and Anvil’s process. It explains; it never approves or changes
            anything.
          </p>
          <div className="support-log" aria-live="polite">
            {!turns.length &&
              SUGGESTIONS.map((s) => (
                <button key={s} type="button" className="badge" onClick={() => void ask(s)}>
                  {s}
                </button>
              ))}
            {turns.map((t, i) => (
              <p key={i} className={'support-turn ' + t.role}>
                {t.text}
              </p>
            ))}
            {busy && <p className="muted">Thinking…</p>}
            {error && (
              <p className="banner error" role="alert">
                {error}
              </p>
            )}
            <div ref={end} />
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void ask(question);
            }}
          >
            <label htmlFor="support-question">Your question</label>
            <textarea
              id="support-question"
              value={question}
              maxLength={2000}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void ask(question);
                }
              }}
            />
            <div className="actions">
              <button className="primary" disabled={busy || !question.trim()}>
                Ask
              </button>
            </div>
          </form>
        </section>
      )}
      {!open && (
        <button type="button" className="primary support-open" onClick={() => setOpen(true)}>
          Ask Anvil
        </button>
      )}
    </div>
  );
}
