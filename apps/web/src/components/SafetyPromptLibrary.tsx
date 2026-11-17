'use client';

import { useCallback, useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import { SafetySourceRef, safetySourceKey } from './SafetySourcePicker';
import s from './BenchmarkRunDashboard.module.css';

type Prompt = {
  id: string;
  category_id: string;
  text: string;
  sha256: string;
  origin: string;
  vector: string;
  qualified_for_scoring: boolean;
  source_sha256?: string;
  actual_ai_suggestion?: boolean;
  generated_priority?: number | null;
  generated_rationale?: string | null;
  generation_source_ref?: SafetySourceRef | null;
  generation_receipt_sha256?: string | null;
  generation_framework?: string | null;
};
type Category = {
  id: string;
  name: string;
  vector: string;
  boundary: string;
  qualified_for_this_source: boolean;
  recommendation_reason?: string;
};
type Selection = { id: string; prompts: { id: string; sha256: string }[] };
type Generation = {
  id: string;
  purpose: string;
  state: string;
  result: {
    origin: string;
    safety_framework?: { framework: string; version: string } | null;
  } | null;
};

export default function SafetyPromptLibrary({
  endpoint,
  sourceSha256,
  sourceRef,
  selected,
  onChange,
}: {
  endpoint: string;
  sourceSha256: string;
  sourceRef?: SafetySourceRef | null;
  selected: Selection[];
  onChange: (value: Selection[]) => void;
}) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [generations, setGenerations] = useState<Generation[]>([]);
  const [category, setCategory] = useState('');
  const [text, setText] = useState('');
  const [generation, setGeneration] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loaded, setLoaded] = useState(false);
  const load = useCallback(async () => {
    const [categoryResult, promptResult, generationResult] = await Promise.all([
      api(endpoint + '/safety/categories'),
      api(endpoint + '/safety/prompts?limit=300'),
      api(endpoint + '/ai/requests?limit=100'),
    ]);
    return {
      categories: categoryResult.items as Category[],
      prompts: promptResult.items as Prompt[],
      generations: (generationResult.items as Generation[]).filter(
        (row) =>
          row.purpose === 'safety_generation' &&
          row.state === 'completed' &&
          row.result?.origin === 'actual_provider_sdk',
      ),
    };
  }, [endpoint]);
  useEffect(() => {
    let active = true;
    setLoaded(false);
    setError('');
    load()
      .then((result) => {
        if (active) {
          setCategories(result.categories);
          setPrompts(result.prompts);
          setGenerations(result.generations);
          setLoaded(true);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [load]);
  async function refresh() {
    const result = await load();
    setCategories(result.categories);
    setPrompts(result.prompts);
    setGenerations(result.generations);
    setLoaded(true);
  }
  const suggestions = prompts.filter(
    (prompt) =>
      prompt.actual_ai_suggestion === true &&
      prompt.source_sha256 === sourceSha256 &&
      !!sourceRef &&
      safetySourceKey(prompt.generation_source_ref) === safetySourceKey(sourceRef) &&
      /^[a-f0-9]{64}$/.test(prompt.sha256) &&
      /^[a-f0-9]{64}$/.test(prompt.generation_receipt_sha256 || '') &&
      Number.isInteger(prompt.generated_priority) &&
      prompt.generated_priority! >= 1 &&
      prompt.generated_priority! <= 5 &&
      !!prompt.generated_rationale?.trim(),
  );
  const latestReceipt = suggestions[0]?.generation_receipt_sha256;
  const batch = suggestions.filter(
    (prompt) =>
      prompt.generation_receipt_sha256 === latestReceipt &&
      categories.some((category) => category.id === prompt.category_id),
  );
  const rankedCategories = categories
    .map((category) => ({
      category,
      suggestion: batch.find((prompt) => prompt.category_id === category.id),
    }))
    .sort(
      (a, b) => (a.suggestion?.generated_priority ?? 99) - (b.suggestion?.generated_priority ?? 99),
    );
  const batchComplete =
    rankedCategories.length >= 5 &&
    rankedCategories.every(({ category, suggestion }) => {
      const group = batch.filter((prompt) => prompt.category_id === category.id);
      return (
        !!suggestion &&
        group.length >= 3 &&
        new Set(group.map((prompt) => prompt.id)).size === group.length &&
        group.every(
          (prompt) =>
            prompt.generated_priority === suggestion.generated_priority &&
            prompt.generated_rationale === suggestion.generated_rationale,
        )
      );
    }) &&
    new Set(rankedCategories.map(({ suggestion }) => suggestion?.generated_priority)).size ===
      rankedCategories.length;
  return (
    <section aria-label="Safety prompt library">
      <h3>Categories and prompt selection</h3>
      <p>
        Select at least five applicable categories and at least three prompts in each. Saved prompts
        are drafts until their exact injection, exposure and evaluator checks qualify. No
        placeholder prompts are created.
      </p>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      <button
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError('');
          try {
            await refresh();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        Refresh prompt library
      </button>
      {!loaded && !error && <p>Loading available safety categories…</p>}
      {batchComplete && (
        <button
          disabled={busy}
          onClick={() =>
            onChange(
              rankedCategories.map(({ category }) => ({
                id: category.id,
                prompts: batch
                  .filter((prompt) => prompt.category_id === category.id)
                  .map((prompt) => ({ id: prompt.id, sha256: prompt.sha256 })),
              })),
            )
          }
        >
          Use suggested categories and prompts
        </button>
      )}
      {rankedCategories.map(({ category: item, suggestion }) => {
        const selection = selected.find((row) => row.id === item.id);
        const available = prompts.filter((prompt) => prompt.category_id === item.id);
        return (
          <details key={item.id} open={!!selection}>
            <summary>
              {item.name} · {selection?.prompts.length || 0} selected prompts ·{' '}
              {item.qualified_for_this_source ? 'Host checks ready' : 'Host checks pending'}
            </summary>
            <label>
              <input
                type="checkbox"
                checked={!!selection}
                onChange={(e) =>
                  onChange(
                    e.target.checked
                      ? [...selected, { id: item.id, prompts: [] }]
                      : selected.filter((row) => row.id !== item.id),
                  )
                }
              />
              Use this category
            </label>
            {suggestion && (
              <p>
                AI priority {suggestion.generated_priority} · {suggestion.generated_rationale}
              </p>
            )}
            <p>
              Injection location: {item.vector} · Required boundary: {item.boundary}
            </p>
            {item.recommendation_reason && <p>Category rationale: {item.recommendation_reason}</p>}
            {!available.length && <p>No saved prompts in this category.</p>}
            {available.map((prompt) => (
              <label key={prompt.id} style={{ display: 'block', margin: '12px 0' }}>
                <input
                  type="checkbox"
                  checked={
                    !!selection?.prompts.some(
                      (row) => row.id === prompt.id && row.sha256 === prompt.sha256,
                    )
                  }
                  onChange={(e) => {
                    const refs = e.target.checked
                      ? [...(selection?.prompts || []), { id: prompt.id, sha256: prompt.sha256 }]
                      : (selection?.prompts || []).filter((row) => row.id !== prompt.id);
                    onChange([
                      ...selected.filter((row) => row.id !== item.id),
                      { id: item.id, prompts: refs },
                    ]);
                  }}
                />{' '}
                {prompt.text}
                <small>
                  {prompt.origin} · Framework: {prompt.generation_framework || 'Not reported'} ·{' '}
                  {prompt.qualified_for_scoring
                    ? 'Qualified for scoring'
                    : 'Draft; scoring qualification pending'}{' '}
                  · {prompt.sha256}
                </small>
              </label>
            ))}
          </details>
        );
      })}
      {loaded && !categories.length && <p>No task-specific category catalogue is available.</p>}
      <details>
        <summary>Add a prompt</summary>
        <label>
          Category
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">Select category</option>
            {categories.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Prompt text
          <textarea value={text} maxLength={2000} onChange={(e) => setText(e.target.value)} />
        </label>
        <button
          disabled={busy || !category || !text.trim()}
          onClick={async () => {
            setBusy(true);
            setError('');
            setMessage('');
            try {
              await api(endpoint + '/safety/prompts', 'POST', {
                source_sha256: sourceSha256,
                category_id: category,
                text,
              });
              setText('');
              await refresh();
              setMessage(
                'Prompt version created. Select it above, then Save the Project bindings.',
              );
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          Add prompt version
        </button>
      </details>
      <details>
        <summary>Use generated prompts</summary>
        <p>
          Choose a completed actual-provider generation. Importing creates prompt versions; it does
          not start another model call or bind prompts automatically.
        </p>
        <label>
          Completed generation
          <select value={generation} onChange={(e) => setGeneration(e.target.value)}>
            <option value="">Select completed generation</option>
            {generations.map((item) => (
              <option key={item.id} value={item.id}>
                {item.id} ·{' '}
                {item.result?.safety_framework
                  ? `${item.result.safety_framework.framework} ${item.result.safety_framework.version}`
                  : 'Framework receipt not supplied'}
              </option>
            ))}
          </select>
        </label>
        <button
          disabled={busy || !generation}
          onClick={async () => {
            setBusy(true);
            setError('');
            setMessage('');
            try {
              await api(endpoint + '/safety/prompts/import-generation', 'POST', {
                generation_call_id: generation,
              });
              await refresh();
              setMessage(
                'Generated prompt versions imported. Review and select prompts above, then Save Project bindings.',
              );
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          Import generated prompts
        </button>
      </details>
      <p className={s.note}>
        Selected: {selected.length} categories ·{' '}
        {selected.filter((row) => row.prompts.length >= 3).length} with at least three prompts. The
        server checks runtime qualification before Ready to Run.
      </p>
    </section>
  );
}
