'use client';

import Link from 'next/link';
import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { GymApiError, get } from './api';

export type Gym = {
  ws: string;
  me: { id: string; name: string; profile: string; binding_approver: boolean };
  say: (message: string) => void;
  refreshTodo: () => void;
};

export const GymContext = createContext<Gym | null>(null);
export const useGym = () => useContext(GymContext) as Gym;

export function useData<T = any>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<GymApiError | null>(null);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => {
    if (!path) return;
    let live = true;
    get<T>(path)
      .then((d) => live && (setData(d), setError(null)))
      .catch((e) => live && setError(e));
    return () => {
      live = false;
    };
  }, [path, tick]);
  return { data, error, reload };
}

export function Failure({ error }: { error: GymApiError | null }) {
  if (!error) return null;
  return (
    <p className="error" role="alert">
      {error.error?.message ?? error.message}
      {error.error?.code ? <small> · {error.error.code}</small> : null}
    </p>
  );
}

export function Loading({
  data,
  error,
  children,
}: {
  data: unknown;
  error: GymApiError | null;
  children: () => React.ReactNode;
}) {
  if (error) return <Failure error={error} />;
  if (data === null) return <p className="wait">Loading…</p>;
  return <>{children()}</>;
}

const TONE: Record<string, string> = {
  ready: 'good',
  qualified: 'good',
  active: 'good',
  approved: 'good',
  released: 'good',
  pass: 'good',
  blocked: 'bad',
  failed: 'bad',
  revoked: 'bad',
  rejected: 'bad',
  declined: 'bad',
  fail: 'bad',
  requested: 'draft',
  deprecated: 'draft',
  registered: 'progress',
  received: 'progress',
  planned: 'progress',
  sent: 'progress',
  queued: 'progress',
  superseded: 'draft',
  removed: 'draft',
};

export function Badge({ state, label }: { state?: string | null; label?: string }) {
  const s = (state ?? '').toLowerCase();
  return (
    <span className="badge" data-s={TONE[s] ?? 'progress'}>
      {label ?? (s ? s[0].toUpperCase() + s.slice(1).replace(/_/g, ' ') : '—')}
    </span>
  );
}

export function Env({ ok, label, title }: { ok: boolean; label: string; title?: string }) {
  return (
    <span className={`env ${ok ? 'okc' : 'noc'}`} title={title}>
      <span className={`dot ${ok ? 'ok' : 'no'}`} aria-hidden="true" />
      {label}
    </span>
  );
}

export function Tabs({
  items,
  current,
}: {
  items: { href: string; label: string; key: string; badge?: number }[];
  current: string;
}) {
  return (
    <nav className="tabs" aria-label="Sections">
      {items.map((t) => (
        <Link key={t.key} href={t.href} aria-current={t.key === current ? 'page' : undefined}>
          {t.label}
          {t.badge ? (
            <span className="badge" data-s="draft" style={{ marginInlineStart: 6 }}>
              {t.badge}
            </span>
          ) : null}
        </Link>
      ))}
    </nav>
  );
}

export function Hash({ value }: { value?: string | null }) {
  if (!value) return <span>—</span>;
  return <code title={value}>{value.replace('sha256:', '').slice(0, 12)}</code>;
}

export function Search({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  return (
    <form className="search" role="search" onSubmit={(e) => e.preventDefault()}>
      <input
        aria-label={placeholder}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </form>
  );
}
