'use client';

import { useEffect, useRef, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
import type { ModelConfiguration } from './ModelProfileEditor';

export function currentJudge(model: ModelConfiguration) {
  return (
    model.workspace_profile && model.is_current && !['disabled', 'revoked'].includes(model.status)
  );
}

export default function FixedJudgePicker({
  base,
  value,
  change,
  disabled,
}: {
  base: string;
  value: string;
  change: (id: string) => void;
  disabled: boolean;
}) {
  const [models, setModels] = useState<ModelConfiguration[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const generation = useRef(0);
  useEffect(() => {
    const token = ++generation.current;
    setModels([]);
    setCursor(null);
    setLoading(true);
    setError('');
    api(base + '/workspace/models?current_only=true&limit=100')
      .then((page) => {
        if (token !== generation.current) return;
        setModels(page.items);
        setCursor(page.next_cursor);
      })
      .catch((reason) => {
        if (token === generation.current) setError(reason.message);
      })
      .finally(() => {
        if (token === generation.current) setLoading(false);
      });
    return () => {
      generation.current++;
    };
  }, [base]);
  const available = models.some((model) => model.id === value && currentJudge(model));
  return (
    <fieldset disabled={disabled || loading}>
      <legend>Independent judge</legend>
      <label>
        Independent judge model
        <select
          required
          value={available ? value : ''}
          onChange={(event) => change(event.target.value)}
        >
          <option value="">Select a saved model</option>
          {models.map((model) => (
            <option key={model.id} value={model.id} disabled={!currentJudge(model)}>
              {model.name} · {model.model_id || model.provider}
              {!currentJudge(model) ? ' · Not a current enabled profile' : ''}
            </option>
          ))}
        </select>
      </label>
      {loading && <p role="status">Loading judge models…</p>}
      {error && <p role="alert">{error}</p>}
      {!loading && !models.length && <p>Configure a model in Models &amp; Keys first.</p>}
      {cursor && (
        <button
          type="button"
          onClick={async () => {
            const token = generation.current,
              after = cursor;
            setLoading(true);
            setError('');
            try {
              const page = await api(
                base +
                  '/workspace/models?current_only=true&limit=100&after=' +
                  encodeURIComponent(after),
              );
              if (token !== generation.current) return;
              if (page.next_cursor === after)
                throw new Error('The model list changed. Reopen this configuration to refresh it.');
              setModels((current) => [
                ...new Map([...current, ...page.items].map((model) => [model.id, model])).values(),
              ]);
              setCursor(page.next_cursor);
            } catch (reason) {
              if (token === generation.current) setError((reason as Error).message);
            } finally {
              if (token === generation.current) setLoading(false);
            }
          }}
        >
          Load more judge models
        </button>
      )}
      <p>
        The same saved judge is used across candidate models for these criteria. Its exact model
        version is frozen when saved. Changing it requires a new evaluator configuration.
        Task-specific qualification is still required.
      </p>
    </fieldset>
  );
}
