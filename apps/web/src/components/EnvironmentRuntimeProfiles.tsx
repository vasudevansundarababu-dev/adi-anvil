'use client';
import { useEffect, useState } from 'react';
import { workspaceApi as api } from '../lib/workspace';
const fields: [string, string, string?][] = [
  ['project', 'Existing GCP project'],
  ['region', 'Region', 'us-west1'],
  ['zone', 'Zone', 'us-west1-a'],
  ['network', 'Existing private network'],
  ['subnet', 'Existing subnet'],
  ['machine_type', 'Worker size', 'e2-standard-4'],
  ['boot_image_project', 'Worker boot-image project'],
  ['boot_image', 'Qualified worker boot-image name'],
  ['boot_image_id', 'Exact worker boot-image ID'],
  ['service_account', 'Worker service account'],
  ['manifest_bucket', 'Existing private source/manifest bucket'],
  ['registry', 'Private image registry'],
  ['build_service_account', 'Build service-account resource name'],
  ['builder_image', 'Pinned Docker-builder image digest'],
];
export default function EnvironmentRuntimeProfiles({
  base,
  canAdmin,
}: {
  base: string;
  canAdmin: boolean;
}) {
  const endpoint = base + '/workspace/environments/runtime-profiles';
  const [rows, setRows] = useState<
      { id: string; name: string; status: string; content_sha256: string }[]
    >([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    api(endpoint)
      .then((r) => {
        if (active) setRows(r);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [endpoint]);
  return (
    <details>
      <summary>Runtime profiles · local and GCP configuration</summary>
      <p>
        The local profile is available. GCP profiles are versioned configuration only until
        separately qualified and provisioning is authorized. Saving a profile creates no resources
        and makes no paid call. Workload identity is used; no API key is stored here.
      </p>
      {error && <p role="alert">{error}</p>}
      {rows.map((r) => (
        <p key={r.id}>
          {r.name} · {r.status.replaceAll('_', ' ')} · {r.content_sha256.slice(0, 12)}
        </p>
      ))}
      {canAdmin ? (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError('');
            try {
              const f = new FormData(e.currentTarget);
              const configuration: Record<string, string | number | null> = Object.fromEntries(
                fields.map(([key]) => [key, String(f.get(key)).trim()]),
              );
              for (const key of ['disk_gib', 'max_lifetime_seconds', 'build_timeout_seconds'])
                configuration[key] = Number(f.get(key));
              configuration.validation_receipt_sha256 =
                String(f.get('validation_receipt_sha256') || '').trim() || null;
              await api(endpoint, 'POST', { name: String(f.get('name')), configuration });
              setRows(await api(endpoint));
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Profile name
            <input name="name" required maxLength={120} />
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,minmax(0,1fr))', gap: 12 }}>
            {fields.map(([key, label, value]) => (
              <label key={key}>
                {label}
                <input name={key} required defaultValue={value} />
              </label>
            ))}
            <label>
              Disk GiB
              <input name="disk_gib" type="number" min={20} max={60} defaultValue={30} required />
            </label>
            <label>
              Maximum worker lifetime, seconds
              <input
                name="max_lifetime_seconds"
                type="number"
                min={300}
                max={86400}
                defaultValue={3600}
                required
              />
            </label>
            <label>
              Build timeout, seconds
              <input
                name="build_timeout_seconds"
                type="number"
                min={60}
                max={2400}
                defaultValue={1200}
                required
              />
            </label>
            <label>
              Existing qualification receipt SHA, if available
              <input name="validation_receipt_sha256" pattern="[a-f0-9]{64}" />
            </label>
          </div>
          <button disabled={busy}>Save new runtime profile version</button>
        </form>
      ) : (
        <p>
          An Admin configures the GCP identity and infrastructure profile once. Both roles can use
          configured local environments and execution groups.
        </p>
      )}
    </details>
  );
}
