'use client';

type Measurement =
  | { kind: 'ratio'; numerator: number; denominator: number }
  | { kind: 'count'; value: number };
type Input = {
  official?: boolean;
  weight?: number;
  scale: { kind?: string; maximum: number | null; levels: number[]; unit: string };
  automated: {
    award: number | null;
    comparison_contract?: { method: string } | null;
    measurements?: Record<string, Measurement> | null;
  };
  expert: {
    status: string;
    award: number | null;
    measurements?: Record<string, Measurement> | null;
  } | null;
  disputed?: boolean;
};
const number = (value: number) => value.toLocaleString('en-US', { maximumFractionDigits: 6 });
export default function ScoreCalculation({ item }: { item: Input }) {
  const diagnostic = item.official === false || item.scale.kind === 'diagnostic_measure';
  const validWeight =
    typeof item.weight === 'number' && Number.isFinite(item.weight) && item.weight >= 0;
  const maximum = item.scale.maximum;
  const usable =
    validWeight && typeof maximum === 'number' && Number.isFinite(maximum) && maximum > 0;
  return (
    <details aria-label="Observation score calculation">
      <summary>How this observation is scored</summary>
      {diagnostic ? (
        <>
          <p>
            Diagnostic measures contribute no official points. Use their recorded counts,
            numerators, denominators and missing-measure coverage; no capability composite is
            inferred.
          </p>
          {item.automated.comparison_contract?.method === 'anvil-logical-effect-subset-v2' && (
            <section aria-label="Logical effect score calculation">
              <h4>Logical effect calculation</h4>
              <p>
                Match the reviewed structured facts to the actual arguments and persisted result.
                Real invocation IDs and whole-body hashes verify evidence integrity. Free-text
                meaning uses separate evaluators. Arrays keep their full membership and can appear
                in any order; one invocation can satisfy at most one obligation.
              </p>
              {(
                [
                  ['Forge generated', item.automated.measurements],
                  [
                    'Human / Expert reviewed',
                    item.disputed || item.expert?.status !== 'scored'
                      ? null
                      : item.expert.measurements,
                  ],
                ] as const
              ).map(([stage, measures]) => (
                <div key={stage}>
                  <strong>{stage}</strong>
                  {(
                    [
                      ['precision', 'Precision', 'observed eligible invocations'],
                      ['recall', 'Recall', 'reviewed obligations'],
                    ] as const
                  ).map(([key, label, denominator]) => {
                    const value = measures?.[key];
                    const valid =
                      value?.kind === 'ratio' &&
                      Number.isInteger(value.numerator) &&
                      Number.isInteger(value.denominator) &&
                      value.denominator > 0 &&
                      value.numerator >= 0 &&
                      value.numerator <= value.denominator;
                    return (
                      <p key={key}>
                        {label}:{' '}
                        {valid && value?.kind === 'ratio'
                          ? `${value.numerator} matched effects ÷ ${value.denominator} ${denominator} = ${number((100 * value.numerator) / value.denominator)}%`
                          : 'Unscored; no resolved recorded ratio'}
                      </p>
                    );
                  })}
                </div>
              ))}
              <p>
                Additional invocations count in precision. Unmet obligations count in recall. These
                diagnostic ratios add no official task points.
              </p>
            </section>
          )}
        </>
      ) : (
        <>
          <p>
            Native permitted awards: {item.scale.levels.join(' / ')} {item.scale.unit}. Frozen
            target weight: {validWeight ? number(item.weight!) : 'Not recorded'}.
          </p>
          <p>Weighted contribution = recorded award ÷ native maximum × frozen target weight.</p>
          {!usable && (
            <p>
              The weight or native maximum is unavailable. A weighted contribution cannot be
              calculated.
            </p>
          )}
          {(
            [
              ['Forge generated', item.automated.award],
              [
                'Human / Expert reviewed',
                item.disputed || item.expert?.status !== 'scored' ? null : item.expert.award,
              ],
            ] as const
          ).map(([label, value]) => (
            <p key={label}>
              {label}:{' '}
              {usable &&
              typeof value === 'number' &&
              Number.isFinite(value) &&
              item.scale.levels.includes(value)
                ? `${number(value)} ÷ ${number(maximum!)} × ${number(item.weight!)} = ${number((value / maximum!) * item.weight!)} weighted points`
                : item.disputed && label === 'Human / Expert reviewed'
                  ? 'Disputed; no resolved contribution'
                  : 'Contribution unavailable; no value is substituted'}
              .
            </p>
          ))}
          <p>
            This is one observation’s contribution. The report’s matched-sample score is 100 × the
            sum of comparable weighted contributions ÷ the sum of their target weights. Repetitions
            and applications remain separate observations. Full scores require complete expected
            coverage; critical and safety gates remain separate.
          </p>
        </>
      )}
    </details>
  );
}
