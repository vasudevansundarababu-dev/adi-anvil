// RL Gym v2 client: reads view endpoints only; every write sends CSRF and an Idempotency-Key.
export type ApiError = {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  status: number;
};

export class GymApiError extends Error {
  error: ApiError;
  constructor(error: ApiError) {
    super(error.message);
    this.error = error;
  }
}

const MESSAGES: Record<string, string> = {
  NOT_FOUND: 'Not found or no longer available',
  REGISTRY_UNAVAILABLE: "Studio's registry is not answering; try again",
  FORGE_UNAVAILABLE: 'Authoring is not answering; try again',
  TENANT_SCOPE_VIOLATION: 'Not in this workspace',
  UNAUTHENTICATED: 'Sign in required',
};

function csrf() {
  return (
    document.cookie
      .split('; ')
      .find((x) => x.startsWith('anvil_csrf='))
      ?.slice('anvil_csrf='.length) ?? ''
  );
}

async function parse(res: Response) {
  const text = await res.text();
  const json = text ? JSON.parse(text) : {};
  if (!res.ok) {
    const e = json.error ?? {};
    throw new GymApiError({
      code: e.code ?? `HTTP_${res.status}`,
      message:
        MESSAGES[e.code] ??
        e.message ??
        (typeof json.detail === 'string' ? json.detail : res.statusText),
      details: e.details,
      status: res.status,
    });
  }
  return json.data;
}

export function wsBase(ws: string) {
  return `/api/v1/workspaces/${encodeURIComponent(ws)}`;
}

export async function get<T = any>(path: string): Promise<T> {
  return parse(await fetch(path, { credentials: 'same-origin', cache: 'no-store' }));
}

export async function send<T = any>(
  method: 'POST' | 'PUT' | 'PATCH',
  path: string,
  body: unknown,
  key?: string,
): Promise<T> {
  return parse(
    await fetch(path, {
      method,
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf(),
        'Idempotency-Key': key ?? crypto.randomUUID(),
      },
      body: JSON.stringify(body ?? {}),
    }),
  );
}

export function short(versionId?: string | null) {
  return versionId ? versionId.replace('@', ' ') : '—';
}

export function when(value?: string | null) {
  if (!value) return '—';
  const d = new Date(value);
  return d.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function age(value?: string | null) {
  if (!value) return '';
  const minutes = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round(minutes / 60);
  return hours < 48 ? `${hours} h` : `${Math.round(hours / 24)} days`;
}

// "golden-kyc-openenv@11" → "@11" (the contract is named once, in the rule).
export function at(versionId?: string | null) {
  return versionId ? `@${versionId.split('@').pop()}` : '—';
}

// Environment versions the owner has said not to bind (24 Nov 2026: "Don't bind any project or suite to it [@9]").
// Pickers show them greyed out with this reason; nothing here changes what the RL Gym will bind by rule.
export const HELD_VERSIONS: Record<string, string> = {
  'golden-kyc-openenv@9':
    "Held by the owner (24 Nov 2026): don't bind any project or suite to @9. Its leak fix is partial (D-039: the passport_only shape remains).",
};
