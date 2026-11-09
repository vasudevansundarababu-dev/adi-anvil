'use client';

import { useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import BenchmarkDashboard from './BenchmarkDashboard';
import styles from './BenchmarkPreview.module.css';

const benchmarks = [
  {
    id: 'banking',
    name: 'Banking decision intelligence',
    domain: 'Banking',
    description: 'Multi-hop KYC, AML investigation and guarded fraud response.',
    tasks: 300,
    version: '1.0.0',
    fit: 96,
    horizon: 'Multi-step',
    capabilities: ['Evidence synthesis', 'Risk reasoning', 'Policy constraints'],
    gap: 'Cross-border escalation scenarios need additional coverage.',
  },
  {
    id: 'marketing',
    name: '12-week product launch',
    domain: 'Marketing',
    description: 'Allocate budgets, respond to market changes and recover a launch plan.',
    tasks: 240,
    version: '1.0.0',
    fit: 84,
    horizon: 'Long horizon',
    capabilities: ['Planning', 'Budget allocation', 'Recovery'],
    gap: 'Does not cover banking policy or regulatory decisions.',
  },
  {
    id: 'commerce',
    name: 'Commerce operations',
    domain: 'Commerce',
    description: 'Balance inventory, pricing and customer outcomes under constraints.',
    tasks: 200,
    version: '0.1.0',
    fit: 71,
    horizon: 'Multi-step',
    capabilities: ['Trade-offs', 'Tool use', 'Constraint handling'],
    gap: 'Supplier disruption and returns need expert-authored cases.',
  },
];
const stages = ['Benchmark library', 'Task profile', 'Recommendations', 'Suite composer'] as const;

export default function BenchmarkPreview() {
  const pathname = usePathname();
  const router = useRouter();
  const libraryPath = pathname.split('/').slice(0, 5).join('/');
  const active = benchmarks.find((b) => b.id === pathname.split('/')[5]);
  const [stage, setStage] = useState<(typeof stages)[number]>('Benchmark library');
  const [domain, setDomain] = useState('All domains');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<string[]>(['banking']);
  const [notice, setNotice] = useState('');
  const [objective, setObjective] = useState(
    'Evaluate evidence-based banking decisions under policy constraints',
  );
  const visible = benchmarks.filter(
    (b) =>
      (domain === 'All domains' || domain === b.domain) &&
      `${b.name} ${b.description}`.toLowerCase().includes(search.toLowerCase()),
  );
  const chosen = benchmarks.filter((b) => selected.includes(b.id));
  function toggle(id: string) {
    setSelected((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id],
    );
    setNotice('Preview selection updated. No benchmark or run has been saved.');
  }
  if (active)
    return (
      <>
        <div>
          <button onClick={() => router.push(libraryPath)}>← Back to benchmarks</button>
        </div>
        <BenchmarkDashboard key={active.id} title={active.name} domain={active.domain} />
      </>
    );
  return (
    <div className={styles.preview}>
      <div className={styles.notice}>
        <strong>Interactive mockup</strong>
        <span>
          Illustrative benchmark definitions, counts and fit scores. No published taskbanks or
          measured model results.
        </span>
      </div>
      <section className={styles.hero}>
        <div>
          <span className={styles.eyebrow}>BENCHMARK FACTORY</span>
          <h2>From domain expertise to measurable capability.</h2>
          <p>Discover benchmarks, understand coverage and compose a versioned evaluation suite.</p>
        </div>
        <button
          className={styles.primary}
          onClick={() => {
            setStage('Task profile');
            setNotice('Configure an illustrative task profile below.');
          }}
        >
          Create benchmark <span aria-hidden="true">↗</span>
        </button>
      </section>
      <div className={styles.stats}>
        {[
          ['03', 'Domain collections', 'Illustrative catalog'],
          ['740', 'Sample tasks', 'Mock inventory · not authored'],
          ['14', 'Profile dimensions', 'Planned coverage model'],
          [String(selected.length).padStart(2, '0'), 'Selected benchmarks', 'In this preview only'],
        ].map(([value, label, caption]) => (
          <div key={label}>
            <strong>{value}</strong>
            <span>{label}</span>
            <small>{caption}</small>
          </div>
        ))}
      </div>
      <nav className={styles.tabs} aria-label="Benchmark preview stages">
        {stages.map((name, index) => (
          <button
            key={name}
            aria-pressed={stage === name}
            onClick={() => {
              setStage(name);
              setNotice('');
            }}
          >
            <span>{index + 1}</span>
            {name}
          </button>
        ))}
      </nav>
      {stage === 'Benchmark library' && (
        <>
          <div className={styles.sectionHeading}>
            <div>
              <h2>Benchmark library</h2>
              <p>Purpose-built collections for business decisions and agent behavior.</p>
            </div>
            <span className={styles.tag}>Preview catalog</span>
          </div>
          <div className={styles.filters}>
            <label>
              Search benchmarks
              <input
                placeholder="Search by name or capability…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            <label>
              Domain
              <select value={domain} onChange={(e) => setDomain(e.target.value)}>
                {['All domains', 'Banking', 'Marketing', 'Commerce'].map((name) => (
                  <option key={name}>{name}</option>
                ))}
              </select>
            </label>
            <span>{visible.length} collections</span>
          </div>
          <div className={styles.cards}>
            {visible.map((b) => (
              <article className={styles.card} key={b.id}>
                <div className={styles.cardTop}>
                  <span className={styles.icon} aria-hidden="true">
                    {b.domain === 'Banking' ? '▥' : b.domain === 'Marketing' ? '↗' : '◇'}
                  </span>
                  <span className={styles.tag}>Illustrative draft</span>
                </div>
                <small className={styles.eyebrow}>
                  <a href={libraryPath + '/' + b.id}>{b.domain}</a> · v{b.version}
                </small>
                <h3>
                  <a href={libraryPath + '/' + b.id}>{b.name}</a>
                </h3>
                <p>{b.description}</p>
                <div className={styles.chips}>
                  {b.capabilities.map((c) => (
                    <span key={c}>{c}</span>
                  ))}
                </div>
                <div className={styles.metadata}>
                  <div>
                    <strong>{b.tasks}</strong>
                    <small>Mock samples</small>
                  </div>
                  <div>
                    <strong>{b.horizon}</strong>
                    <small>Task horizon</small>
                  </div>
                </div>
                <div className={styles.cardActions}>
                  <button onClick={() => router.push(libraryPath + '/' + b.id)}>
                    View benchmark
                  </button>
                  <button aria-pressed={selected.includes(b.id)} onClick={() => toggle(b.id)}>
                    {selected.includes(b.id) ? '✓ In suite' : '+ Add to suite'}
                  </button>
                </div>
              </article>
            ))}
          </div>
          {!visible.length && <p role="status">No preview benchmarks match these filters.</p>}
          <div className={styles.bottom}>
            <div>
              <strong>Build around your own domain tasks</strong>
              <p>Start with task requirements, then inspect fit and missing coverage.</p>
            </div>
            <button onClick={() => setStage('Task profile')}>Define task profile →</button>
          </div>
        </>
      )}
      {stage === 'Task profile' && (
        <section className={styles.surface}>
          <span className={styles.eyebrow}>01 / DEFINE REQUIREMENTS</span>
          <h2>What do you want to measure?</h2>
          <p>Banking is the example profile. Edits stay in this browser preview.</p>
          <label>
            Evaluation objective
            <textarea value={objective} onChange={(e) => setObjective(e.target.value)} />
          </label>
          <div className={styles.profileGrid}>
            {[
              ['Domain', ['Banking', 'Marketing', 'Commerce']],
              ['Task type', ['Evidence-based decision', 'Planning', 'Investigation']],
              ['Horizon', ['Multi-step', 'Long horizon', 'Single step']],
              ['Environment', ['Harbor sandbox', 'Static diagnostic']],
              ['Expected artifact', ['Decision + evidence trail', 'Allocation plan']],
              ['Review', ['SME + professor/guide verification']],
            ].map(([label, options]) => (
              <label key={label as string}>
                {label}
                <select>
                  {(options as string[]).map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          <div className={styles.detail}>
            <strong>Capabilities to assess</strong>
            <div className={styles.chips}>
              {[
                'Evidence synthesis',
                'Risk reasoning',
                'Tool use',
                'Policy constraints',
                'Recovery',
              ].map((c) => (
                <span key={c}>{c}</span>
              ))}
            </div>
            <p>
              Source rights, immutable versions and reviewer approval are required before any real
              release.
            </p>
          </div>
          <button className={styles.primary} onClick={() => setStage('Recommendations')}>
            Preview recommendations →
          </button>
        </section>
      )}
      {stage === 'Recommendations' && (
        <section className={styles.surface}>
          <span className={styles.eyebrow}>02 / EXPLAINABLE MATCHING</span>
          <h2>Recommendations for a banking profile</h2>
          <p>Fit scores below are illustrative design values, not calculated recommendations.</p>
          {benchmarks.map((b) => (
            <div className={styles.recommendation} key={b.id}>
              <div className={styles.fit}>
                <strong>{b.fit}%</strong>
                <small>Mock fit</small>
              </div>
              <div>
                <h3>{b.name}</h3>
                <p>{b.gap}</p>
                <div className={styles.chips}>
                  {b.capabilities.map((c) => (
                    <span key={c}>{c}</span>
                  ))}
                </div>
              </div>
              <button aria-pressed={selected.includes(b.id)} onClick={() => toggle(b.id)}>
                {selected.includes(b.id) ? '✓ In suite' : 'Add to suite'}
              </button>
            </div>
          ))}
          <button className={styles.primary} onClick={() => setStage('Suite composer')}>
            Compose suite →
          </button>
        </section>
      )}
      {stage === 'Suite composer' && (
        <section className={styles.surface}>
          <span className={styles.eyebrow}>03 / VERSIONED COMPOSITION</span>
          <h2>Your evaluation suite</h2>
          <p>
            {chosen.length} selected preview benchmarks · {chosen.reduce((n, b) => n + b.tasks, 0)}{' '}
            illustrative samples
          </p>
          {chosen.map((b) => (
            <div className={styles.recommendation} key={b.id}>
              <div>
                <h3>{b.name}</h3>
                <p>
                  v{b.version} · {b.domain} · Mock draft
                </p>
              </div>
              <label>
                Weight
                <input
                  type="number"
                  min="1"
                  max="100"
                  defaultValue="100"
                  aria-label={b.name + ' weight'}
                />
              </label>
              <button onClick={() => toggle(b.id)}>Remove</button>
            </div>
          ))}
          {!chosen.length && <p>Select a benchmark from the library to compose this preview.</p>}
          <div className={styles.detail}>
            <strong>Release gates still required</strong>
            <p>
              Expert-authored tasks → professor/guide verification → rights and verifier
              qualification → pinned protocol → approved budget. Praxis SME assignment and
              returned-review logging are planned integrations.
            </p>
          </div>
          <button
            disabled={!chosen.length}
            className={styles.primary}
            onClick={() =>
              setNotice('Mock suite preview complete. Nothing was saved, approved or dispatched.')
            }
          >
            Preview suite summary
          </button>
          <button onClick={() => setStage('Benchmark library')}>Back to library</button>
        </section>
      )}
      {notice && (
        <p className={styles.feedback} role="status">
          {notice}
        </p>
      )}
    </div>
  );
}
