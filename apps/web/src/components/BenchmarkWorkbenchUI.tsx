'use client';

import { ReactNode } from 'react';
import styles from './BenchmarkWorkbench.module.css';

export function WorkbenchPanel({
  title,
  note,
  children,
}: {
  title: string;
  note?: string;
  children: ReactNode;
}) {
  return (
    <section className={styles.panel}>
      <header className={styles.panelHead}>
        <h3>{title}</h3>
        {note && <span>{note}</span>}
      </header>
      {children}
    </section>
  );
}

export function WorkbenchEmpty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className={styles.empty}>
      <svg viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <path
          d="M5 25V7m0 18h23M10 20l5-6 5 3 7-9"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
        <path d="M23 8h4v4" stroke="currentColor" strokeWidth="1.4" />
      </svg>
      <h4>{title}</h4>
      <p>{children}</p>
    </div>
  );
}

export function WorkbenchMetric({
  label,
  value,
  note,
  highlight = false,
}: {
  label: string;
  value: ReactNode;
  note: string;
  highlight?: boolean;
}) {
  return (
    <article className={styles.card + (highlight ? ' ' + styles.highlight : '')}>
      <span>{label}</span>
      <strong>{value}</strong>
      <p>{note}</p>
    </article>
  );
}

export function WorkbenchStatus({
  children,
  tone = 'neutral',
}: {
  children: ReactNode;
  tone?: 'neutral' | 'warning' | 'danger' | 'success';
}) {
  return (
    <span className={styles.badge + (tone === 'neutral' ? '' : ' ' + styles[tone])}>
      {children}
    </span>
  );
}

export function WorkbenchAvailability({
  title,
  state,
  reason,
}: {
  title: string;
  state: string;
  reason: string;
}) {
  return (
    <WorkbenchPanel title={title} note={state}>
      <WorkbenchEmpty title={state}>{reason}</WorkbenchEmpty>
    </WorkbenchPanel>
  );
}

export function WorkbenchBar({
  label,
  value,
  display,
}: {
  label: string;
  value: number | null;
  display: string;
}) {
  return (
    <div className={styles.barRow}>
      <div className={styles.barLabel}>
        <span>{label}</span>
        <strong>{display}</strong>
      </div>
      {value !== null && (
        <div
          className={styles.barTrack}
          role="meter"
          aria-label={label}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={value}
        >
          <div className={styles.barFill} style={{ width: `${value}%` }} />
        </div>
      )}
    </div>
  );
}
