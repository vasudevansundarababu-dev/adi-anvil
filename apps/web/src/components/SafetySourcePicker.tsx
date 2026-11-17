'use client';

import { useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';

export type SafetySourceRef = { id: string; version: string; configuration_sha256: string };
type Source = {
  id: string;
  name: string;
  ref: SafetySourceRef | null;
  implementation_status?: string;
  qualified_for_this_source: boolean;
  eligibility?: { ready: boolean; reasons: string[] };
  definition?: Record<string, unknown>;
};
export const safetySourceKey = (ref?: SafetySourceRef | null) =>
  ref ? `${ref.id}:${ref.version}:${ref.configuration_sha256}` : '';
function SourceRules({ definition }: { definition?: Record<string, unknown> }) {
  const evaluator = definition?.evaluator;
  const rules =
    evaluator && typeof evaluator === 'object' && !Array.isArray(evaluator)
      ? (evaluator as Record<string, unknown>)
      : null;
  const labels: Record<string, string> = {
    candidate_pass: 'Agent passes',
    candidate_fail: 'Agent fails',
    candidate_unknown: 'Agent is unscored',
    containment_pass: 'Containment passes',
    containment_fail: 'Containment fails',
    containment_unknown: 'Containment is unscored',
    detection_recovery: 'Detection and recovery',
    critical_incidents: 'Critical incidents',
  };
  return (
    <>
      {definition?.placement && <p>Placement: {String(definition.placement)}</p>}
      {rules ? (
        <>
          <h4>How evaluated</h4>
          <p>Evaluator: {String(rules.id || 'Not supplied')}</p>
          <dl>
            {Object.entries(labels)
              .filter(([key]) => typeof rules[key] === 'string')
              .map(([key, label]) => (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>{String(rules[key]).replaceAll('_', ' ')}</dd>
                </div>
              ))}
          </dl>
        </>
      ) : (
        <p>Evaluation rules are not available for this source.</p>
      )}
      {definition && (
        <details>
          <summary>Source version evidence</summary>
          <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
            {JSON.stringify(definition, null, 2)}
          </pre>
        </details>
      )}
    </>
  );
}

export default function SafetySourcePicker({
  endpoint,
  sourceSha256,
  value,
  disabled,
  onChange,
}: {
  endpoint: string;
  sourceSha256: string;
  value?: SafetySourceRef | null;
  disabled: boolean;
  onChange: (value: SafetySourceRef | null) => void;
}) {
  const [items, setItems] = useState<Source[]>([]),
    [error, setError] = useState(''),
    [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let active = true;
    setLoaded(false);
    setError('');
    setItems([]);
    api(endpoint + '/safety/sources')
      .then((result) => {
        if (
          result.source_sha256 !== sourceSha256 ||
          !Array.isArray(result.items) ||
          result.items.some(
            (row: Source) =>
              typeof row.id !== 'string' ||
              typeof row.name !== 'string' ||
              (row.ref &&
                (row.ref.id !== row.id ||
                  typeof row.ref.version !== 'string' ||
                  !/^[a-f0-9]{64}$/.test(row.ref.configuration_sha256))),
          )
        )
          throw new Error(
            'Safety sources could not be confirmed for this Project revision. Reload before changing the source.',
          );
        if (active) {
          setItems(result.items);
          setLoaded(true);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [endpoint, sourceSha256]);
  const selected = items.find(
    (row) => row.ref && safetySourceKey(row.ref) === safetySourceKey(value),
  );
  return (
    <section aria-label="Safety test source">
      <h3>Choose test source</h3>
      <p>
        Select an implemented source for this Project. A saved draft does not establish runtime
        qualification. Framework adaptations are separate from published benchmark results.
      </p>
      {error && <p role="alert">{error}</p>}
      {!loaded && !error && <p>Loading source availability…</p>}
      <label>
        Test source
        <select
          aria-label="Test source"
          value={safetySourceKey(value)}
          disabled={disabled || !loaded || !!error}
          onChange={(event) => {
            const ref =
              items.find((row) => row.ref && safetySourceKey(row.ref) === event.target.value)
                ?.ref || null;
            onChange(ref);
          }}
        >
          <option value="">Choose a source</option>
          {!!value && !selected && (
            <option value={safetySourceKey(value)}>
              Saved source version · availability not confirmed
            </option>
          )}
          {items.map((row) => (
            <option
              key={row.id}
              value={row.ref ? safetySourceKey(row.ref) : 'unsupported:' + row.id}
              disabled={!row.ref}
            >
              {row.name} · {row.ref ? 'Version ' + row.ref.version : 'Not available'}
            </option>
          ))}
        </select>
      </label>
      {loaded && !!value && !selected && (
        <p role="alert">
          The saved source version is not in the current catalogue. It has not been replaced
          automatically.
        </p>
      )}
      {items.map((row) => (
        <details key={row.id} open={row === selected}>
          <summary>
            {row.name} ·{' '}
            {row.qualified_for_this_source === true && row.eligibility?.ready === true
              ? 'Ready'
              : 'Not ready'}
          </summary>
          <p>
            {row.implementation_status?.replaceAll('_', ' ') ||
              'Implementation status not reported'}
          </p>
          {(row.eligibility?.reasons || []).map((reason) => (
            <p key={reason}>{reason.replaceAll('_', ' ')}</p>
          ))}
          {!row.ref && <p>This adapter cannot be selected.</p>}
          <SourceRules definition={row.definition} />
          {row.ref && (
            <small style={{ overflowWrap: 'anywhere' }}>
              Source version {row.ref.version} · configuration {row.ref.configuration_sha256}
            </small>
          )}
        </details>
      ))}
    </section>
  );
}
