import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import { clearAllSessions } from '../lib/assistantSession';
import { __resetTutorialStore } from '../lib/tutorialController';

afterEach(() => {
  cleanup();
  // Isolate the guided walkthrough. Its runtime state lives in a MODULE store
  // (it has to survive the route changes the walkthrough performs), and its
  // completion flag lives in localStorage — so without this a walkthrough
  // started or completed in one test would leak into every later test in the
  // same file, and "the offer is shown to a first-time reader" would pass or
  // fail depending on test order.
  try {
    localStorage.clear();
  } catch {
    /* localStorage unavailable in this environment */
  }
  __resetTutorialStore();
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
