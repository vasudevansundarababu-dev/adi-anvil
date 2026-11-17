'use client';

import { useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';

type Job = {
  id?: string;
  job_id?: string;
  state: string;
  result?: {
    passed: boolean;
    control_coverage_complete: boolean;
    cases: {
      expected_status: string;
      actual_status: string;
      passed: boolean;
      error_type?: string;
      line?: number;
    }[];
  } | null;
};

export default function CustomPythonEditor({
  base,
  target,
  onSelect,
  initialCode,
}: {
  base: string;
  target: string;
  onSelect?: (program: { id: string; sha256: string }) => void;
  initialCode?: string;
}) {
  const endpoint = `${base}/workspace/custom-evaluators`;
  const [code, setCode] = useState(
    initialCode ??
      'def evaluate(actual, expected):\n    # Replace with the rule for this criterion.\n    return {"status": "unscored"}\n',
  );
  const [cases, setCases] = useState('[]');
  const [saved, setSaved] = useState<{
    id: string;
    sha256: string;
    can_select_for_binding?: boolean;
  } | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const [pollExpired, setPollExpired] = useState(false);
  const [unconfirmed, setUnconfirmed] = useState(false);
  const pending = !!job && ['queued', 'claimed'].includes(job.state);
  const jobId = job?.job_id || job?.id;
  useEffect(() => {
    if (!pending || !jobId) return;
    let active = true,
      timer: ReturnType<typeof setTimeout>;
    let polls = 0;
    async function refresh() {
      try {
        const value = await api(`${endpoint}/jobs/${encodeURIComponent(jobId!)}`);
        if (!active) return;
        setJob(value);
        if (['queued', 'claimed'].includes(value.state) && ++polls < 30)
          timer = setTimeout(refresh, 2000);
        else if (['queued', 'claimed'].includes(value.state)) setPollExpired(true);
      } catch (e) {
        if (active) {
          setError((e as Error).message);
          setPollExpired(true);
        }
      }
    }
    timer = setTimeout(refresh, 2000);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [endpoint, jobId, pending]);
  function edited() {
    setSaved(null);
    setJob(null);
    setError('');
    setPollExpired(false);
    setUnconfirmed(false);
  }
  async function run() {
    setBusy(true);
    setError('');
    let submitted = false;
    try {
      const parsed = JSON.parse(cases);
      if (!Array.isArray(parsed) || !parsed.length)
        throw new Error('Add at least one test case with actual, expected and expected_status.');
      submitted = true;
      const value = await api(
        saved ? `${endpoint}/${saved.id}/test` : `${endpoint}/preview`,
        'POST',
        saved ? { cases: parsed } : { code, cases: parsed },
      );
      setJob(value);
      setPollExpired(false);
    } catch (e) {
      setError((e as Error).message);
      if (submitted && !(e as Error & { status?: number }).status) setUnconfirmed(true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Custom Python evaluator">
      <h3>Custom Python</h3>
      <p>
        Rule: {target}. Define evaluate(actual, expected). Tests run in the isolated Python
        environment using only the inputs you provide.
      </p>
      <label>
        Python code
        <textarea
          aria-label="Python code"
          rows={10}
          value={code}
          disabled={busy || pending || unconfirmed}
          onChange={(e) => {
            edited();
            setCode(e.target.value);
          }}
          style={{ width: '100%', fontFamily: 'monospace' }}
        />
      </label>
      <label>
        Test cases (JSON)
        <textarea
          aria-label="Custom test cases"
          rows={6}
          value={cases}
          disabled={busy || pending || unconfirmed}
          onChange={(e) => {
            edited();
            setCases(e.target.value);
          }}
          style={{ width: '100%', fontFamily: 'monospace' }}
        />
      </label>
      <p>
        Each case contains actual, expected and expected_status (pass, partial, fail or unscored).
        Use your own test inputs; private benchmark references are not shown here.
      </p>
      <button disabled={busy || pending || unconfirmed} onClick={() => void run()}>
        Run
      </button>{' '}
      <button
        disabled={busy || pending || unconfirmed || !!saved}
        onClick={async () => {
          setBusy(true);
          setError('');
          try {
            setSaved(await api(endpoint, 'POST', { name: `Custom ${target}`.slice(0, 120), code }));
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        Save code version
      </button>
      {saved && <p>Code version saved. Test this version with Run.</p>}
      {saved?.can_select_for_binding && onSelect && (
        <button disabled={busy || pending || unconfirmed} onClick={() => onSelect(saved)}>
          Use for this rubric
        </button>
      )}
      {error && <p role="alert">{error}</p>}
      {unconfirmed && (
        <p>
          The submission response was lost. Do not run it again until the existing job is
          reconciled.
        </p>
      )}
      {job && <p role="status">Test: {job.state}</p>}
      {pollExpired && (
        <p>
          Automatic status checks stopped. The existing test may still be running; do not submit it
          again.
          <button
            onClick={async () => {
              try {
                setJob(await api(`${endpoint}/jobs/${encodeURIComponent(jobId!)}`));
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            Refresh test status
          </button>
        </p>
      )}
      {job?.result && (
        <div aria-label="Custom Python test results">
          <p>
            {job.result.passed
              ? 'All supplied test expectations matched.'
              : 'One or more test expectations failed.'}{' '}
            {job.result.control_coverage_complete
              ? 'Pass, fail and unscored controls covered.'
              : 'Pass, fail and unscored controls are incomplete.'}
          </p>
          <table>
            <thead>
              <tr>
                <th>Case</th>
                <th>Expected</th>
                <th>Observed</th>
                <th>Result / Error</th>
              </tr>
            </thead>
            <tbody>
              {job.result.cases.map((c, index) => (
                <tr key={index}>
                  <td>{index + 1}</td>
                  <td>{c.expected_status}</td>
                  <td>{c.actual_status}</td>
                  <td>
                    {c.error_type
                      ? `${c.error_type}${c.line ? ` at line ${c.line}` : ''}`
                      : c.passed
                        ? 'Matched'
                        : 'Did not match'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p>
        Custom benchmark scoring is pending qualification.{' '}
        {onSelect
          ? 'Choose Use for this rubric to replace its selected evaluator, then Save the Project bindings. The Project remains Binding Pending until qualification passes.'
          : 'Policy-rule custom binding is not yet supported; this editor only saves and tests code.'}
      </p>
    </section>
  );
}
