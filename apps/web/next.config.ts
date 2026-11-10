import type { NextConfig } from 'next';
const apiPort = process.env.ANVIL_API_PORT || '8200';
if (!/^[0-9]+$/.test(apiPort) || Number(apiPort) < 1024 || Number(apiPort) > 65535) {
  throw new Error('ANVIL_API_PORT must be an unprivileged local port');
}
const config: NextConfig = {
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: '/api/:path*', destination: `http://127.0.0.1:${Number(apiPort)}/api/:path*` },
    ];
  },
};
export default config;
