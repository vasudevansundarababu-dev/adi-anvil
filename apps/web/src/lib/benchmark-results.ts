import {
  benchmarkGet,
  benchmarkPath,
  BenchmarkComparison,
  BenchmarkStoredScore,
} from './benchmark';

export async function loadBenchmarkResults(base: string, runId: string) {
  const path = '/comparisons/' + encodeURIComponent(runId);
  const [comparison, score] = await Promise.all([
    benchmarkGet<BenchmarkComparison>(base, path),
    benchmarkGet<BenchmarkStoredScore>(base, path + '/results').catch((failure: unknown) => {
      // Only the endpoint's specific absence response means no stored score.
      // Denied access, lost connections and other conflicts remain errors.
      if (
        failure instanceof Error &&
        'status' in failure &&
        failure.status === 409 &&
        failure.message === 'No stored score revision is available'
      )
        return null;
      throw failure;
    }),
  ]);
  if (comparison.run_id !== runId)
    throw Object.assign(new Error('Stored comparison identity changed'), { status: 409 });
  if (
    score &&
    (score.projection.protocol_sha256 !== comparison.subject_sha256 ||
      score.projection.origin !== comparison.origin)
  )
    throw Object.assign(
      new Error('Stored score does not match this comparison protocol and origin'),
      {
        status: 409,
      },
    );
  if (
    score &&
    ![
      'approved',
      'adjudicated',
      'reviewed',
      'admin_run_exempt',
      'admin_approved',
      'policy_no_review',
    ].includes(score.review_state) &&
    score.projection.models.some((model) => model.primary !== null)
  )
    throw Object.assign(
      new Error('A primary result requires a stored approved review publication'),
      {
        status: 409,
      },
    );
  return { comparison, score };
}

export function benchmarkResultExport(
  base: string,
  runId: string,
  revisionId: string,
  format: 'json' | 'csv' | 'report' | 'atif',
) {
  return (
    '/api/v1' +
    benchmarkPath(base) +
    '/comparisons/' +
    encodeURIComponent(runId) +
    '/exports/' +
    format +
    '?score_revision_id=' +
    encodeURIComponent(revisionId)
  );
}

export function measuredDuration(milliseconds: number | null) {
  if (milliseconds === null) return 'Unknown';
  return milliseconds < 1000
    ? `${milliseconds} ms`
    : `${(milliseconds / 1000).toLocaleString('en-US', { maximumFractionDigits: 3 })} s`;
}

export function benchmarkResultsAccessInvalid(failure: unknown) {
  return (
    failure instanceof Error &&
    [401, 403, 404, 409].includes((failure as Error & { status?: number }).status || 0)
  );
}

export function recordedCost(microUsd: number | null) {
  if (microUsd === null) return 'Unknown';
  return (microUsd / 1_000_000).toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  });
}
