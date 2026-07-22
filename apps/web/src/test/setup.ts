import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import { clearAllSessions } from '../lib/assistantSession';

afterEach(() => {
  cleanup();
  // Isolate the P29.1 ephemeral assistant session (in-memory mirror +
  // sessionStorage) between tests so a conversation appended in one test can
  // never leak into another.
  clearAllSessions();
  try {
    sessionStorage.clear();
  } catch {
    /* sessionStorage unavailable in this environment */
  }
});
