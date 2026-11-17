'use client';

type Criterion = {
  id: string;
  description: string;
  earned_points: string | null;
  possible_points: string;
};
type Cell = {
  id: string;
  task_key: string;
  model_key: string;
  environment_key: string;
  repetition: number;
  assessment: {
    criteria: Criterion[];
    earned_points: string | null;
    possible_points: string;
    failure_modes?: { id: string; title?: string }[];
  };
};
type Axis = {
  id: string;
  label: string;
  value: number | null;
  decided: number;
  planned: number;
  unknown: number;
  numerator?: string | number;
  denominator?: string | number;
  basis?: string;
};

export default function ReportCalculations({
  cells,
  series,
  names,
  inspect,
}: {
  cells: Cell[];
  series: { model_key: string; name: string; axes: Axis[] }[];
  names: Record<string, string>;
  inspect: (cell: string) => void;
}) {
  const groups = new Map<
    string,
    {
      model: string;
      environment: string;
      repetition: number;
      criterion: string;
      description: string;
      earned: number;
      possible: number;
      scored: number;
      unscored: number;
      awards: Map<string, number>;
      cells: string[];
    }
  >();
  for (const cell of cells)
    for (const criterion of cell.assessment.criteria) {
      const key = JSON.stringify([
        cell.model_key,
        cell.environment_key,
        cell.repetition,
        criterion.id,
      ]);
      const group = groups.get(key) || {
        model: cell.model_key,
        environment: cell.environment_key,
        repetition: cell.repetition,
        criterion: criterion.id,
        description: criterion.description,
        earned: 0,
        possible: 0,
        scored: 0,
        unscored: 0,
        awards: new Map(),
        cells: [] as string[],
      };
      const earned = criterion.earned_points === null ? null : Number(criterion.earned_points),
        possible = Number(criterion.possible_points);
      if (
        earned === null ||
        !Number.isFinite(earned) ||
        !Number.isFinite(possible) ||
        possible <= 0 ||
        earned < 0 ||
        earned > possible
      )
        group.unscored++;
      else {
        group.earned += earned;
        group.possible += possible;
        group.scored++;
        group.awards.set(String(earned), (group.awards.get(String(earned)) || 0) + 1);
        if (earned < possible) group.cells.push(cell.id);
      }
      groups.set(key, group);
    }
  const full = cells.filter(
    (c) =>
      c.assessment.earned_points !== null &&
      c.assessment.criteria.length > 0 &&
      c.assessment.criteria.every((x) => x.earned_points !== null),
  );
  return (
    <section aria-label="Report calculations and evidence">
      <h3>How scores are calculated</h3>
      <p>
        {cells.length} selected execution cells; {full.length} have complete criterion awards and a
        stored total. {cells.length - full.length} remain incomplete or unscored. These counts are
        execution cells, not distinct customer applications.
      </p>
      <p>
        Criterion percentage = earned points ÷ evaluated possible points × 100. Unscored
        observations are disclosed separately. Model, environment and repetition cohorts are never
        silently merged in the table below. Numeric scores do not override mandatory or
        critical-failure gates.
      </p>
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th>Model / Environment / Repetition</th>
              <th>Rubric criterion</th>
              <th>Awards</th>
              <th>Calculation</th>
              <th>Coverage</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {[...groups.entries()].map(([key, g]) => (
              <tr key={key}>
                <td>
                  {names[g.model] || g.model}
                  <small>
                    {g.environment} · repetition {g.repetition}
                  </small>
                </td>
                <td>
                  {g.description}
                  <small>{g.criterion}</small>
                </td>
                <td>
                  {[...g.awards.entries()]
                    .map(([points, count]) => `${count} × ${points}`)
                    .join(' + ') || 'Not evaluated'}
                </td>
                <td>
                  {g.possible
                    ? `${g.earned} / ${g.possible} = ${((g.earned / g.possible) * 100).toFixed(2)}%`
                    : 'Not evaluated'}
                </td>
                <td>
                  {g.scored} scored · {g.unscored} unscored
                </td>
                <td>
                  {g.cells.length ? (
                    <button onClick={() => inspect(g.cells[0])}>
                      Inspect {g.cells.length} affected cell{g.cells.length === 1 ? '' : 's'}
                    </button>
                  ) : (
                    'No observed point loss'
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>Spider chart definitions and coverage</summary>
        <p>
          Each series represents the named model in the selected scope. Axes have separate evidence
          cohorts. Missing values are gaps. No polygon area or composite safety score is calculated.
        </p>
        <table>
          <thead>
            <tr>
              <th>Series</th>
              <th>Axis</th>
              <th>Value / evidence basis</th>
              <th>Coverage</th>
            </tr>
          </thead>
          <tbody>
            {series.flatMap((v) =>
              v.axes.map((axis) => (
                <tr key={v.model_key + axis.id}>
                  <td>{v.name}</td>
                  <td>{axis.label}</td>
                  <td>
                    {axis.value === null ? 'Not evaluated' : `${axis.value}%`}
                    {axis.numerator !== undefined && axis.denominator !== undefined && (
                      <small>
                        {axis.numerator} / {axis.denominator}
                      </small>
                    )}
                    <small>{axis.basis || 'See bound evaluator evidence'}</small>
                  </td>
                  <td>
                    {axis.decided} / {axis.planned} decided; {axis.unknown} unknown
                  </td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </details>
      <details>
        <summary>Failure cause limitations</summary>
        <p>
          A lost rubric point is an observation, not a diagnosed root cause. Reasoning failure is
          not inferred from an incorrect answer. Policy omission, misapplication, unsupported
          claims, tool/MCP errors and evaluator failures require their own evidence. Missing causal
          evidence remains unresolved.
        </p>
      </details>
    </section>
  );
}
