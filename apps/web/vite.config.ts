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
      // committed baseline data files, needing no browser and no backend. They
      // were previously enforced only inside the ~30-minute `browser-a11y` job,
      // which is why a stale hand-maintained total could be merged and only
      // discovered afterwards. Running them here puts the answer in the fast
      // `frontend` job instead. See `e2e/baseline-aggregate.ts`.
      //
      // ON THE DEPENDENCY CHAIN, stated as measured rather than as hoped. An
      // earlier revision of this comment claimed "no Playwright import anywhere
      // in their dependency chain (`a11y-baseline` -> `surfaces` -> `env`, all
      // of which only read `process.env`)". That is FALSE: `e2e/surfaces.ts:46`
      // references `@playwright/test`. What is true, and is the thing the safety
      // argument actually needs, is narrower — the reference is a TYPE-ONLY
      // inline `import(...)` in a type position, erased at transform time, and
      // there is no value import of `@playwright/test` anywhere in the chain.
      // `src/__tests__/baseline-invariant-wiring.test.ts` asserts exactly that,
      // so a future value import fails there instead of breaking `npm test` in
      // CI only.
      //
      // `.invariant.test.ts`, never `.spec.ts`. All THREE Playwright configs
      // discover by a different pattern — `playwright.config.ts`
      // `/.*\.spec\.ts$/`, `playwright.mutation.config.ts` the UNANCHORED
      // `/.*\.spec\.ts/` scoped to `e2e/mutation`, and `playwright.bench.config.ts`
      // `/.*\.bench\.ts$/` — so this pattern cannot collide with any of them.
      // ("Both configs", and the claim that all of them are `$`-anchored, were
      // wrong on both counts; `e2e/tsconfig.json`'s own `//include` note records
      // an earlier slice making the same "only two configs" mistake.)
      'e2e/**/*.invariant.test.ts',
    ],
  },
});
