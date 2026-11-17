'use client';

import { useEffect, useState } from 'react';
import ExpertReview from './ExpertReview';
import s from './BenchmarkRunDashboard.module.css';

const reports = ['Workflow Metrics', 'Agent Performance', 'Expert Review'] as const;
type Report = (typeof reports)[number];
const checked = (value: string | null): Report =>
  reports.find((report) => report === value) || 'Expert Review';

// Uses only the sealed, role-authorized review projection. It does not fetch
// model settings, execution controls or hidden reference material.
export default function ExpertReviewReports({
  base,
  runId,
  initialView,
}: {
  base: string;
  runId: string;
  initialView: string | null;
}) {
  const [report, setReport] = useState<Report>(() => checked(initialView));
  useEffect(() => {
    setReport(checked(initialView));
  }, [initialView]);
  return (
    <>
      <nav className={s.actions} aria-label="Sealed execution reports">
        {reports.map((name) => (
          <button key={name} aria-pressed={name === report} onClick={() => setReport(name)}>
            {name}
          </button>
        ))}
      </nav>
      <ExpertReview key={JSON.stringify([base, runId])} base={base} runId={runId} report={report} />
    </>
  );
}
