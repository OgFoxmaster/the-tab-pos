import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Extra hostnames (for previews or reverse proxies) are supplied per process, so no
// environment-specific host is committed to the repository.
const allowedHosts = (process.env.VITE_ALLOWED_HOSTS || '')
  .split(',')
  .map((host) => host.trim())
  .filter(Boolean);

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0',
    ...(allowedHosts.length ? { allowedHosts } : {}),
    // When VITE_API_BASE_URL=/api, the dev server proxies to the local FastAPI app so
    // the browser sees one origin (no CORS) and the service worker never caches the API.
    proxy: {
      '/api': {
        target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
