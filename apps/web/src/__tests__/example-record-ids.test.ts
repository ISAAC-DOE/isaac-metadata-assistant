/*
 * THE CLIENT'S COPY OF THE FIVE WORKED-EXAMPLE IDS MUST BE THE BACKEND'S.
 *
 * `lib/exampleRecords.ts` is a hand-written mirror of `workspace.py::CANONICAL_IDS`,
 * and a hand-written mirror rots silently — the failure mode is not a crash but a
 * panel quietly falling back to the wrong explanation for a renamed seed. So the
 * parity is asserted against the Python source itself, the same way
 * `backend-down-state.test.tsx` derives its sub-read suffixes from `api.ts` rather
 * than trusting a list.
 *
 * READ-ONLY, and of a file already in this repository: nothing here connects to a
 * database, reads a workspace, or asks any scope what it holds.
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { EXAMPLE_RECORD_IDS, isExampleRecordId } from '../lib/exampleRecords';

const __dirname = dirname(fileURLToPath(import.meta.url));
const WORKSPACE_PY = resolve(__dirname, '../../../..', 'apps/api/isaac_api/workspace.py');
const SOURCE = readFileSync(WORKSPACE_PY, 'utf8');

/** The ids the backend actually builds, reconstructed from its own two constants. */
function backendCanonicalIds(): string[] {
  const prefix = /^_SEED_ID_PREFIX = "([^"]+)"/m.exec(SOURCE)?.[1];
  expect(prefix, 'workspace.py no longer defines _SEED_ID_PREFIX as a literal').toBeDefined();

  const seeds = new Map<string, string>();
  for (const m of SOURCE.matchAll(/^(SEED_[A-Z_]+_ID) = _SEED_ID_PREFIX \+ "([^"]+)"$/gm)) {
    seeds.set(m[1], `${prefix}${m[2]}`);
  }

  // Only the names CANONICAL_IDS itself lists count — a seed constant that exists
  // but is not canonical must not silently enter the client's set.
  const block = /CANONICAL_IDS = frozenset\(\s*\{([^}]*)\}/.exec(SOURCE)?.[1];
  expect(block, 'workspace.py no longer defines CANONICAL_IDS as a frozenset literal').toBeDefined();
  const names = (block ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s.length > 0);

  return names.map((name) => {
    const id = seeds.get(name);
    expect(id, `CANONICAL_IDS names ${name}, which is not built from _SEED_ID_PREFIX`).toBeDefined();
    return id as string;
  });
}

describe('the client-side worked-example id set', () => {
  it('is exactly workspace.py::CANONICAL_IDS', () => {
    const backend = backendCanonicalIds();
    expect(backend).toHaveLength(5);
    expect([...backend].sort()).toEqual([...EXAMPLE_RECORD_IDS].sort());
  });

  it('recognises each backend id and nothing else', () => {
    for (const id of backendCanonicalIds()) expect(isExampleRecordId(id)).toBe(true);
    // A real, ordinary record id is not an example id, and neither is nothing.
    expect(isExampleRecordId('01ARZ3NDEKTSV4RRFFQ69G5FAV')).toBe(false);
    expect(isExampleRecordId('')).toBe(false);
    expect(isExampleRecordId(null)).toBe(false);
    expect(isExampleRecordId(undefined)).toBe(false);
    // Not a prefix or substring test: only an exact id counts.
    expect(isExampleRecordId(`${EXAMPLE_RECORD_IDS[0]}X`)).toBe(false);
    expect(isExampleRecordId(EXAMPLE_RECORD_IDS[0].slice(0, -1))).toBe(false);
  });

  it('is a build-time constant — recognising an id makes no request', () => {
    // The membership test is pure. If it ever needed the network it would be an
    // existence oracle across scopes, which is the thing the backend's
    // `load_experiment` refuses to be (`workspace.py`: "NEVER seeds").
    const fetchSpy = globalThis.fetch;
    let called = 0;
    globalThis.fetch = (() => {
      called += 1;
      throw new Error('example-id recognition must never issue a request');
    }) as typeof fetch;
    try {
      expect(isExampleRecordId(EXAMPLE_RECORD_IDS[2])).toBe(true);
    } finally {
      globalThis.fetch = fetchSpy;
    }
    expect(called).toBe(0);
  });
});
