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
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
});
