/*
 * LIB-005 · reopen-and-continue — the browser-local "which workspace was I on"
 * store.
 *
 * As with `tutorial-preference.test.ts`, the property under test is a
 * DIRECTION: every failure mode (missing storage, corrupt JSON, a wrong
 * shape, an unrecognised view, an empty id) must resolve to "nothing
 * remembered" — never a throw, and never a guessed view. A false negative
 * costs one reader landing on `fields` exactly as they always have; a false
 * positive would silently route them to a workspace they never asked for.
 *
 * It also pins WHAT MAY BE STORED (`id` and `view`, nothing else), the LRU
 * eviction order, and the `MAX_ENTRIES` bound — read back from the serialized
 * value, not trusted from the source.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import {
  MAX_ENTRIES,
  RECORD_LAST_VIEW_KEY,
  clearRecordLastView,
  lastRecordView,
  rememberRecordView,
} from '../lib/recordLastView';

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('LIB-005 · record-last-view — the happy path', () => {
  it('remembers nothing on a browser that has never seen a record', () => {
    expect(lastRecordView('exp-1')).toBeNull();
    // a read must not CREATE the key
    expect(localStorage.length).toBe(0);
  });

  it('remembers the view, and survives a reload (a fresh read of the same store)', () => {
    rememberRecordView('exp-1', 'runs');
    expect(lastRecordView('exp-1')).toBe('runs');
  });

  it('the LAST write wins for a given id', () => {
    rememberRecordView('exp-1', 'runs');
    rememberRecordView('exp-1', 'graph');
    expect(lastRecordView('exp-1')).toBe('graph');
  });

  it('two different ids are tracked independently', () => {
    rememberRecordView('exp-1', 'runs');
    rememberRecordView('exp-2', 'capture');
    expect(lastRecordView('exp-1')).toBe('runs');
    expect(lastRecordView('exp-2')).toBe('capture');
  });

  it('clearing forgets everything', () => {
    rememberRecordView('exp-1', 'runs');
    clearRecordLastView();
    expect(lastRecordView('exp-1')).toBeNull();
  });

  it('stores ONLY {id, view} — nothing else, checked by reading the serialized value', () => {
    rememberRecordView('exp-1', 'graph');
    const raw = localStorage.getItem(RECORD_LAST_VIEW_KEY);
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw as string);
    expect(parsed).toEqual([{ id: 'exp-1', view: 'graph' }]);
  });
});

describe('LIB-005 · record-last-view — fail-safe direction', () => {
  it('an id that has never been remembered resolves to null', () => {
    rememberRecordView('exp-1', 'runs');
    expect(lastRecordView('exp-2')).toBeNull();
  });

  it('an empty id is refused on write and on read, never crashes', () => {
    expect(() => rememberRecordView('', 'runs')).not.toThrow();
    expect(lastRecordView('')).toBeNull();
    expect(localStorage.length).toBe(0);
  });

  it('an unrecognised view is refused on write — the stored list is untouched', () => {
    rememberRecordView('exp-1', 'runs');
    // @ts-expect-error — deliberately wrong-typed, proving the runtime guard
    rememberRecordView('exp-1', 'not-a-real-view');
    expect(lastRecordView('exp-1')).toBe('runs');
  });

  it('corrupt JSON at the key resolves to null, not a throw', () => {
    localStorage.setItem(RECORD_LAST_VIEW_KEY, '{not json');
    expect(() => lastRecordView('exp-1')).not.toThrow();
    expect(lastRecordView('exp-1')).toBeNull();
  });

  it('a non-array value at the key resolves to null', () => {
    localStorage.setItem(RECORD_LAST_VIEW_KEY, JSON.stringify({ id: 'exp-1', view: 'runs' }));
    expect(lastRecordView('exp-1')).toBeNull();
  });

  it('an entry with an unrecognised view value is dropped, not read as though valid', () => {
    localStorage.setItem(
      RECORD_LAST_VIEW_KEY,
      JSON.stringify([{ id: 'exp-1', view: 'not-a-real-view' }]),
    );
    expect(lastRecordView('exp-1')).toBeNull();
  });

  it('an entry with a non-string id is dropped', () => {
    localStorage.setItem(RECORD_LAST_VIEW_KEY, JSON.stringify([{ id: 7, view: 'runs' }]));
    expect(lastRecordView('7')).toBeNull();
  });

  it('one malformed entry does not poison the well-formed entries beside it', () => {
    localStorage.setItem(
      RECORD_LAST_VIEW_KEY,
      JSON.stringify([
        { id: 'exp-1', view: 'not-a-real-view' },
        { id: 'exp-2', view: 'graph' },
      ]),
    );
    expect(lastRecordView('exp-1')).toBeNull();
    expect(lastRecordView('exp-2')).toBe('graph');
  });

  it('a storage write failure (quota/private mode) is swallowed, not thrown', () => {
    const spy = vi
      .spyOn(Storage.prototype, 'setItem')
      .mockImplementation(() => {
        throw new DOMException('quota exceeded');
      });
    expect(() => rememberRecordView('exp-1', 'runs')).not.toThrow();
    spy.mockRestore();
  });

  it('a storage read failure is swallowed and reads as nothing remembered', () => {
    rememberRecordView('exp-1', 'runs');
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked');
    });
    expect(() => lastRecordView('exp-1')).not.toThrow();
    expect(lastRecordView('exp-1')).toBeNull();
    spy.mockRestore();
  });
});

describe('LIB-005 · record-last-view — bounded, LRU eviction', () => {
  it('does not grow without bound: the oldest-TOUCHED id is evicted first', () => {
    for (let i = 0; i < MAX_ENTRIES; i += 1) {
      rememberRecordView(`exp-${i}`, 'runs');
    }
    // touch exp-0 again so it is no longer the least-recently-touched entry
    rememberRecordView('exp-0', 'graph');
    // one more distinct id pushes the list one over the bound
    rememberRecordView(`exp-${MAX_ENTRIES}`, 'capture');

    const raw = localStorage.getItem(RECORD_LAST_VIEW_KEY) as string;
    const parsed: Array<{ id: string; view: string }> = JSON.parse(raw);
    expect(parsed.length).toBe(MAX_ENTRIES);

    // exp-0 was RE-touched after exp-1, so exp-1 — not exp-0 — is the true
    // least-recently-touched entry and must be the one evicted.
    expect(parsed.some((e) => e.id === 'exp-1')).toBe(false);
    expect(lastRecordView('exp-0')).toBe('graph');
    expect(lastRecordView(`exp-${MAX_ENTRIES}`)).toBe('capture');
  });
});
