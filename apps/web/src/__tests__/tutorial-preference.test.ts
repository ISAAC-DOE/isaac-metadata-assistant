/*
 * R0 · the guided walkthrough's ONE piece of durable state.
 *
 * The property under test is a DIRECTION, not just a round trip: every failure
 * mode must resolve to NOT COMPLETED. A false "not completed" costs one
 * dismissible offer; a false "completed" costs a reader the walkthrough entirely,
 * with no way to discover it existed. So each case below corrupts the stored value
 * in a different way and asserts the same safe answer, and none of them may throw.
 *
 * It also pins WHAT MAY BE STORED. The key is browser-local, so the honest
 * guarantee is not "it is safe because it is small" but "these four fields and
 * nothing else" — checked by reading the serialized value back, not by trusting
 * the serializer's source.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import {
  NOT_COMPLETED,
  TUTORIAL_ID,
  TUTORIAL_PREFERENCE_KEY,
  TUTORIAL_VERSION,
  clearTutorialPreference,
  isTutorialCompleted,
  markTutorialCompleted,
  readTutorialPreference,
} from '../lib/tutorialPreference';

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('R0 · tutorial preference — the happy path', () => {
  it('is not completed on a browser that has never seen it', () => {
    expect(isTutorialCompleted()).toBe(false);
    expect(readTutorialPreference()).toEqual(NOT_COMPLETED);
    // ...and reading must not CREATE the key. A read that writes would make
    // "has this reader finished it?" unanswerable after the first render.
    expect(localStorage.length).toBe(0);
  });

  it('remembers completion, and survives a reload (a fresh read of the same store)', () => {
    markTutorialCompleted('2099-01-02T03:04:05.000Z');
    expect(isTutorialCompleted()).toBe(true);
    expect(readTutorialPreference()).toEqual({
      tutorialId: TUTORIAL_ID,
      version: TUTORIAL_VERSION,
      completed: true,
      completedAt: '2099-01-02T03:04:05.000Z',
    });
  });

  it('clearing forgets it, and the read falls back to not completed', () => {
    markTutorialCompleted();
    expect(isTutorialCompleted()).toBe(true);
    clearTutorialPreference();
    expect(isTutorialCompleted()).toBe(false);
    expect(localStorage.getItem(TUTORIAL_PREFERENCE_KEY)).toBeNull();
  });
});

describe('R0 · tutorial preference — what may be stored', () => {
  it('stores exactly four fields, and no record content, identity or credential', () => {
    markTutorialCompleted('2099-01-02T03:04:05.000Z');
    const raw = localStorage.getItem(TUTORIAL_PREFERENCE_KEY);
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!) as Record<string, unknown>;
    expect(Object.keys(parsed).sort()).toEqual([
      'completed',
      'completedAt',
      'tutorialId',
      'version',
    ]);
    // The whole serialized value, scanned as one string: nothing that could be a
    // record, a field value, a path, a token or an identity may appear in it.
    expect(raw).not.toMatch(/Bearer|sk-|token|password|secret/i);
    expect(raw).not.toMatch(/\b01[0-9A-HJKMNP-TV-Z]{24}\b/); // a ULID record id
    expect(raw).not.toMatch(/XANES|CuO|sha256|ssrl-archive|K-edge/i);
    // Word-bounded on purpose: an unbounded /uid/ matches "gUIDed" in this
    // tutorial's own id, which would make the guard fail for a reason that has
    // nothing to do with identity.
    expect(raw).not.toMatch(/@|\busername\b|\buid\b|\bemail\b|\bgroups\b/i);
  });

  it('writes only under its own namespaced, versioned key', () => {
    markTutorialCompleted();
    expect(Object.keys({ ...localStorage })).toEqual([TUTORIAL_PREFERENCE_KEY]);
    expect(TUTORIAL_PREFERENCE_KEY).toBe('isaac.tutorial.v1');
  });
});

describe('R0 · tutorial preference — every failure resolves to NOT completed', () => {
  /** Each case writes a different kind of unusable value under the real key. */
  const corrupt: [string, string][] = [
    ['unparseable JSON', '{not json at all'],
    ['an empty string', ''],
    ['a JSON primitive', '"completed"'],
    ['a JSON array', '[{"completed":true}]'],
    ['null', 'null'],
    ['an object with no fields', '{}'],
    ['completed as a string rather than a boolean', JSON.stringify({ tutorialId: TUTORIAL_ID, version: TUTORIAL_VERSION, completed: 'true' })],
    ['completed as 1', JSON.stringify({ tutorialId: TUTORIAL_ID, version: TUTORIAL_VERSION, completed: 1 })],
    ['a different tutorial id', JSON.stringify({ tutorialId: 'some-other-tour', version: TUTORIAL_VERSION, completed: true })],
    ['no version', JSON.stringify({ tutorialId: TUTORIAL_ID, completed: true })],
    ['an OLDER content version', JSON.stringify({ tutorialId: TUTORIAL_ID, version: TUTORIAL_VERSION - 1, completed: true })],
    ['a NEWER content version', JSON.stringify({ tutorialId: TUTORIAL_ID, version: TUTORIAL_VERSION + 1, completed: true })],
    ['version as a string', JSON.stringify({ tutorialId: TUTORIAL_ID, version: String(TUTORIAL_VERSION), completed: true })],
  ];

  it.each(corrupt)('%s reads as not completed, without throwing', (_case, value) => {
    localStorage.setItem(TUTORIAL_PREFERENCE_KEY, value);
    expect(() => readTutorialPreference()).not.toThrow();
    expect(isTutorialCompleted()).toBe(false);
  });

  it('a version bump re-offers the walkthrough to a browser that finished the old one', () => {
    // Exactly what a content bump looks like on disk: a well-formed, genuinely
    // completed record for the PREVIOUS version.
    localStorage.setItem(
      TUTORIAL_PREFERENCE_KEY,
      JSON.stringify({
        tutorialId: TUTORIAL_ID,
        version: TUTORIAL_VERSION - 1,
        completed: true,
        completedAt: '2099-01-01T00:00:00.000Z',
      }),
    );
    expect(isTutorialCompleted()).toBe(false);
  });

  it('a completedAt of the wrong type is dropped, not propagated', () => {
    localStorage.setItem(
      TUTORIAL_PREFERENCE_KEY,
      JSON.stringify({ tutorialId: TUTORIAL_ID, version: TUTORIAL_VERSION, completed: true, completedAt: 12345 }),
    );
    // Completion still holds — the timestamp is decoration, not the answer — but
    // the bad value never reaches a caller.
    expect(readTutorialPreference()).toEqual({
      tutorialId: TUTORIAL_ID,
      version: TUTORIAL_VERSION,
      completed: true,
      completedAt: null,
    });
  });
});

describe('R0 · tutorial preference — storage itself unavailable', () => {
  it('a throwing getItem reads as not completed', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError: storage is blocked');
    });
    expect(() => isTutorialCompleted()).not.toThrow();
    expect(isTutorialCompleted()).toBe(false);
  });

  it('a throwing setItem does not break finishing the walkthrough', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError');
    });
    // The reader has already been shown the walkthrough; refusing to finish it
    // because a preference could not be saved would be the worse outcome.
    expect(() => markTutorialCompleted()).not.toThrow();
  });

  it('a throwing removeItem does not break clearing', () => {
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('SecurityError');
    });
    expect(() => clearTutorialPreference()).not.toThrow();
  });
});

describe('R0 · tutorial preference — the fallback cannot be corrupted by a caller', () => {
  it('NOT_COMPLETED is frozen, so a mutation cannot make a later read lie', () => {
    expect(Object.isFrozen(NOT_COMPLETED)).toBe(true);
    // A caller trying to flip the shared fallback must not succeed. (In a module
    // without "use strict" this would silently no-op; either way the value holds.)
    try {
      (NOT_COMPLETED as { completed: boolean }).completed = true;
    } catch {
      /* strict-mode TypeError is an equally acceptable outcome */
    }
    expect(readTutorialPreference().completed).toBe(false);
  });
});
