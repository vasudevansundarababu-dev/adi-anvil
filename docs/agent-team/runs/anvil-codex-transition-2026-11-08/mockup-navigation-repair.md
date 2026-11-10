# Mockup navigation repair

User request: show the result UI. This is the existing clearly disclosed design mockup, not new execution or measured model evidence.

Only `apps/web/src/components/BenchmarkPreview.tsx` changed: the library path now keeps the `/preview` segment (`slice(0,5)`), and the selected benchmark id is read at path index5. Canonical library route is `/workspace/{project}/benchmarks/preview`; its detail is `/workspace/{project}/benchmarks/preview/{id}`. Previously the generated detail link omitted `/preview` and mounted the operational library. UI MOCKUP and DESIGN PREVIEW disclosures remain intact. No API request, review, approval or backend behavior was added.

To avoid Testing's independent security preview and the historical root dependencies, verification used a separate tracked-source copy at `/private/tmp/anvil-mockup-navigation-2dog0itj`, excluding local environment files/state. Frozen private-cache installation, TypeScript and the Next16.4.1 production build passed:

```
pnpm install --frozen-lockfile --ignore-scripts --offline --store-dir=/private/tmp/anvil-security-web-store --cache-dir=/private/tmp/anvil-security-pnpm-cache
pnpm --filter @anvil/web check
ANVIL_API_PORT=64830 NEXT_TELEMETRY_DISABLED=1 pnpm --filter @anvil/web build
NEXT_TELEMETRY_DISABLED=1 pnpm --filter @anvil/web exec next start --hostname 127.0.0.1 --port 52977
```

New frontend-only preview: `http://127.0.0.1:52977`, process tool session12692. The built routes manifest explicitly targets existing historical loopback API64830. Root page and proxied `/api/v1/health` both returned200. Existing previews55203/64829, backend processes, accounts, data and secrets were not changed. Existing host cookies may support read navigation; cross-origin modifying API requests remain guarded by the backend's original WEB_ORIGIN checks. No credentials were retrieved. Browser verification is handed to the parent agent using the user's existing session.
