/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Local-first, offline: no external network, no proxying to the API in this static build.
export default defineConfig({
  // Deploy base path (e.g. '/krish/'), baked at build time by the Docker
  // frontend stage. Default '/' keeps local dev and CI builds unchanged.
  base: process.env.VITE_BASE_PATH || '/',
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: true,
    include: [
      'src/**/*.{test,spec}.{ts,tsx}',
      // The e2e BASELINE INVARIANTS — arithmetic and string shape over the two
      // committed baseline data files, with no browser, no backend and no
      // Playwright import anywhere in their dependency chain
      // (`a11y-baseline` -> `surfaces` -> `env`, all of which only read
      // `process.env`). They were previously enforced only inside the ~30-minute
      // `browser-a11y` job, which is why a stale hand-maintained total could be
      // merged and only discovered afterwards. Running them here puts the answer
      // in the fast `frontend` job instead. See `e2e/baseline-aggregate.ts`.
      //
      // `.invariant.test.ts`, never `.spec.ts`: both Playwright configs discover
      // with `testMatch: /.*\.spec\.ts$/`, so this pattern cannot collide with
      // the browser suites.
      'e2e/**/*.invariant.test.ts',
    ],
  },
});
