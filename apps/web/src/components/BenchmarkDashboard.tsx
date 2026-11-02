'use client';
import { useState } from 'react';
import styles from './BenchmarkDashboard.module.css';

const models = [
  {
    name: 'OpenAI',
    trials: '6 / 6',
    score: 82,
    constraints: '94%',
    cost: '$0.42',
    duration: '42s',
    coverage: ['92%', '81%', '89%'],
    color: '#37a8fc',
  },
  {
    name: 'Claude',
    trials: '6 / 6',
    score: 79,
    constraints: '89%',
    cost: '$0.38',
    duration: '48s',
    coverage: ['88%', '76%', '82%'],
    color: '#16cbbb',
  },
  {
    name: 'Gemini',
    trials: '5 / 6',
    score: 74,
    constraints: '86%',
    cost: '$0.14',
    duration: '26s',
    coverage: ['84%', 'Incomplete', '77%'],
    color: '#9874ff',
  },
];
const protocol = [
  ['Protocol', 'Expert Work v1'],
  ['Primary metric', 'Weighted task score'],
  ['Aggregation', 'Task-weighted mean'],
  ['Repetitions', '2 per model / task'],
  ['Incomplete trials', 'Reported separately'],
  ['Task / rubric', 'Frozen versions'],
  ['Environment', 'Pinned Docker digest'],
  ['Grading', 'Versioned verifiers'],
];
const tabs = ['Overview', 'Tasks & coverage', 'Failures', 'Run history'] as const;
export default function BenchmarkDashboard({ title, domain }: { title: string; domain: string }) {
  const [collection, setCollection] = useState('My benchmarks');
  const [tab, setTab] = useState<(typeof tabs)[number]>('Overview');
  const [detail, setDetail] = useState<
    'protocol' | 'gdpval' | 'create' | 'review' | 'rerun' | null
  >(null);
  const [model, setModel] = useState<string | null>(null);
  return (
    <section className={styles.preview} aria-label="Illustrative benchmark dashboard">
      <header className={styles.heading}>
        <div>
          <h2>Benchmarks</h2>
          <p>Compare models. Trace failures. Improve evaluations.</p>
        </div>
        <button className={styles.primary} onClick={() => setDetail('create')}>
          + Create benchmark
        </button>
      </header>
      <div className={styles.warning}>
        <strong>DESIGN PREVIEW</strong>
        <span>All displayed results are illustrative · no model requests or saved changes</span>
      </div>
      <nav className={styles.tabs} aria-label="Benchmark collections">
        {['My benchmarks', 'Published references'].map((name) => (
          <button
            key={name}
            aria-pressed={collection === name}
            onClick={() => {
              setCollection(name);
              setDetail(null);
            }}
          >
            {name}
          </button>
        ))}
      </nav>
      {collection === 'Published references' ? (
        <div className={styles.panel}>
          <h3>Published references</h3>
          <p>
            No external reference results are loaded in this preview. Published results will remain
            separate from Anvil-measured results.
          </p>
          <button onClick={() => setDetail('gdpval')}>View GDPVal planned scope</button>
        </div>
      ) : (
        <>
          <div className={styles.selectors}>
            <div className={styles.selected}>
              <div>
                <strong>{title} · Pilot v1.0</strong>
                <span className={styles.pill}>Private · Synthetic demo tasks</span>
              </div>
              <p>3 tasks · 3 models · 2 repetitions · Harbor</p>
            </div>
            <div className={styles.planned}>
              <div>
                <strong>GDPVal</strong>
                <span className={styles.pill}>Planned</span>
                <p>
                  Integration not enabled<small>Target: before Dec 11</small>
                </p>
              </div>
              <button onClick={() => setDetail('gdpval')}>View planned scope</button>
            </div>
          </div>
          <div className={styles.topGrid}>
            <section className={styles.panel} aria-label="Illustrative model comparison">
              <div className={styles.row}>
                <h3>Model comparison</h3>
                <span className={styles.pill}>Mock data</span>
              </div>
              <p>Primary metric: Weighted task score (%) ↑</p>
              <div className={styles.tableScroll}>
                <table>
                  <thead>
                    <tr>
                      {[
                        'Model',
                        'Completed trials',
                        'Weighted task score',
                        'Constraints passed',
                        'Median cost',
                        'Median duration',
                      ].map((name) => (
                        <th key={name}>{name}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {models.map((m) => (
                      <tr key={m.name}>
                        <th>
                          <button
                            className={styles.model}
                            onClick={() => {
                              setModel(m.name);
                              setTab('Run history');
                            }}
                          >
                            <span style={{ color: m.color }} aria-hidden="true">
                              ◆
                            </span>
                            {m.name}
                          </button>
                        </th>
                        <td>{m.trials}</td>
                        <td>
                          <div className={styles.score}>
                            <strong>{m.score}%</strong>
                            <span className={styles.track}>
                              <span style={{ width: m.score + '%', background: m.color }} />
                            </span>
                          </div>
                        </td>
                        <td>{m.constraints}</td>
                        <td>{m.cost}</td>
                        <td>{m.duration}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <footer className={styles.footnote}>
                Small sample · Inspect individual trials before drawing ranking conclusions.
              </footer>
            </section>
            <section className={styles.panel} aria-label="Evaluation protocol">
              <h3>Evaluation protocol</h3>
              <dl className={styles.protocol}>
                {protocol.map(([key, value]) => (
                  <div key={key}>
                    <dt>{key}:</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
              <button className={styles.link} onClick={() => setDetail('protocol')}>
                View protocol & provenance →
              </button>
            </section>
          </div>
          <nav className={styles.tabs} aria-label="Benchmark result views">
            {tabs.map((name) => (
              <button
                key={name}
                aria-pressed={tab === name}
                onClick={() => {
                  setTab(name);
                  setModel(null);
                }}
              >
                {name}
              </button>
            ))}
          </nav>
          {(tab === 'Overview' || tab === 'Tasks & coverage') && (
            <div className={styles.lowerGrid}>
              <section className={styles.panel} aria-label="Illustrative task coverage">
                <h3>Where models struggle</h3>
                <div className={styles.tableScroll}>
                  <table className={styles.heatmap}>
                    <thead>
                      <tr>
                        <th>Model</th>
                        {(domain === 'Banking'
                          ? ['KYC / AML', 'Fraud', 'Risk policy']
                          : domain === 'Marketing'
                            ? ['Allocation', 'Launch planning', 'Recovery']
                            : ['Inventory', 'Pricing', 'Returns']
                        ).map((name) => (
                          <th key={name}>{name}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {models.map((m) => (
                        <tr key={m.name}>
                          <th>{m.name}</th>
                          {m.coverage.map((value, index) => (
                            <td
                              key={index}
                              className={value === 'Incomplete' ? styles.incomplete : styles.heat}
                            >
                              <button
                                onClick={() => {
                                  setModel(
                                    m.name +
                                      ' · ' +
                                      (domain === 'Banking'
                                        ? ['KYC / AML', 'Fraud', 'Risk policy']
                                        : domain === 'Marketing'
                                          ? ['Allocation', 'Launch planning', 'Recovery']
                                          : ['Inventory', 'Pricing', 'Returns'])[index],
                                  );
                                  setTab('Run history');
                                }}
                              >
                                {value}
                              </button>
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              <section className={styles.panel}>
                <h3>Failure modes</h3>
                {[
                  ['Constraint violation', '3'],
                  ['Missing evidence', '2'],
                  ['Tool failure', '1'],
                ].map(([name, count]) => (
                  <button
                    className={styles.failure}
                    key={name}
                    onClick={() => {
                      setTab('Failures');
                      setModel(name);
                    }}
                  >
                    <span>{name}</span>
                    <strong>{count}</strong>
                  </button>
                ))}
                <button className={styles.link} onClick={() => setTab('Failures')}>
                  Inspect trajectories →
                </button>
              </section>
            </div>
          )}
          {tab === 'Failures' && (
            <section className={styles.panel}>
              <h3>{model || 'Failure investigation'}</h3>
              <p>Illustrative failure examples · these are not the outcomes of your live runs.</p>
              <div className={styles.tableScroll}>
                <table>
                  <thead>
                    <tr>
                      <th>Example task</th>
                      <th>Observable issue</th>
                      <th>Review action</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>KYC / AML</td>
                      <td>Decision missing a supporting evidence citation</td>
                      <td>Inspect evidence and rubric</td>
                    </tr>
                    <tr>
                      <td>Fraud response</td>
                      <td>Proposed action exceeds a policy constraint</td>
                      <td>Review hard-failure rule</td>
                    </tr>
                    <tr>
                      <td>Marketing allocation</td>
                      <td>Tool action did not return an output</td>
                      <td>Separate harness failure from answer quality</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <button className={styles.link} onClick={() => setDetail('review')}>
                Review evidence →
              </button>
            </section>
          )}
          {tab === 'Run history' && (
            <section className={styles.panel}>
              <h3>{model ? model + ' · trial preview' : 'Run history'}</h3>
              <p>
                No real runs are loaded in this design preview. The table above is illustrative and
                is not derived from your Astra, Claude or Gemini executions.
              </p>
              <div className={styles.trial}>
                <span>Example trajectory</span>
                <strong>Read evidence → inspect policy → submit decision → verifier review</strong>
                <small>
                  Incomplete trials and infrastructure failures remain separate from scored
                  responses.
                </small>
              </div>
              <button onClick={() => setDetail('protocol')}>
                Inspect pinned evaluation requirements
              </button>
            </section>
          )}
          <section className={styles.loop}>
            <div>
              <h3>Close the evaluation loop</h3>
              <p>
                Turn insights into improvements
                <br />
                and measure the impact.
              </p>
            </div>
            <button
              onClick={() => {
                setTab('Run history');
                setModel(null);
              }}
            >
              Inspect trial
            </button>
            <span aria-hidden="true">→</span>
            <button onClick={() => setDetail('review')}>Review evidence</button>
            <span aria-hidden="true">→</span>
            <button onClick={() => setDetail('review')}>Create version in Praxis</button>
            <span aria-hidden="true">→</span>
            <button onClick={() => setDetail('rerun')}>Re-run in Anvil</button>
          </section>
        </>
      )}
      {detail && (
        <section className={styles.detail} aria-label="Benchmark preview detail">
          <div className={styles.row}>
            <h3>
              {
                {
                  protocol: 'Protocol & provenance',
                  gdpval: 'GDPVal · planned integration',
                  create: 'Create benchmark · preview',
                  review: 'SME review and task revision',
                  rerun: 'Re-run requirements',
                }[detail]
              }
            </h3>
            <button onClick={() => setDetail(null)} aria-label="Close benchmark detail">
              Close
            </button>
          </div>
          {detail === 'protocol' && (
            <p>
              This mock protocol would pin task and rubric versions, task weights, verifier version,
              environment digest and two repetitions per model/task. No actual digests or approvals
              are attached to this illustrative dashboard. Incomplete trials are reported
              separately; comparable results require the same frozen conditions.
            </p>
          )}
          {detail === 'gdpval' && (
            <p>
              Integration is not enabled. Planned scope: review source/version and usage rights, map
              tasks and required tools, implement an execution adapter, preserve the
              benchmark-specific grading protocol, qualify it and publish separately labeled
              results. Target: before December 11, 2026. No GDPVal tasks, scores or runs are
              connected here.
            </p>
          )}
          {detail === 'create' && (
            <p>
              Proposed workflow: select a permitted taskbank → confirm domain/capability profile →
              pin task, rubric, environment and verifier versions → review coverage and protocol →
              qualify and approve. This preview creates no benchmark. Full functionality will be
              implemented in a later build.
            </p>
          )}
          {detail === 'review' && (
            <p>
              Planned Anvil/Praxis integration: completed run → assigned SME review in Praxis →
              review returned and logged in Anvil → approved task revision → new evaluation. This
              API handoff is roadmap work. These preview controls send no task or message and change
              no review records.
            </p>
          )}
          {detail === 'rerun' && (
            <p>
              No run has started. A real run requires qualified task versions, exact model/provider
              selection, reviewed rights and a separately approved budget through Anvil's existing
              execution controls. Unknown requests are never retried by this preview.
            </p>
          )}
        </section>
      )}
      <footer className={styles.bottom}>
        Published references and Anvil-measured results remain separate. Preview values are
        illustrative; GDPVal is not connected.
      </footer>
    </section>
  );
}
