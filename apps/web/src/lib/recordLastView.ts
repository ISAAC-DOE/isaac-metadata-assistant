/*
 * LIB-005 — Reopen-and-continue.
 *
 * "A scientist leaves and returns later and continues the same scientific
 * work." Measured before writing anything here: `routes.py`'s `reopen`
 * concept is a WORKFLOW STEP regressing (a downstream step un-satisfying an
 * earlier one) — a different thing entirely, and this module does not touch
 * it. Measured too: `ExperimentRow.tsx` always links to the bare
 * `ROUTES.record(id)`, and `resolveRecordView` (`routes.ts`) resolves a bare
 * URL to the `fields` workspace unconditionally. So today, leaving a record on
 * `runs`/`capture`/`graph` and reopening it from the Library always drops the
 * reader back on `fields` — the one workspace they may not have been using.
 *
 * WHAT THIS REMEMBERS, exhaustively: an experiment id, and which of the four
 * record workspaces (`RecordViewId`) the reader was most recently on. NOTHING
 * ELSE. No field value, no draft content, no evidence, no title, no folder, no
 * identity value. A reviewer can confirm that by reading `serialize()` alone.
 *
 * WHY BROWSER-LOCAL, following `tutorialPreference.ts`'s precedent exactly and
 * for the identical reason stated there: this build has no trusted user
 * identity and no server-side profile store (`docs/identity-trust-contract.md`
 * §6A), so there is no honest key to file a per-user "last workspace" under
 * anywhere but the browser. When a server-side profile exists, this module is
 * the only thing that would need to change.
 *
 * WHY `localStorage` AND NOT `sessionStorage`, unlike `tutorialSession.ts`.
 * That module tracks a disposable SERVER-SIDE session that dies with the tab
 * by design (the backend TTL-sweeps it). A record a scientist is working on is
 * not disposable, and "continue tomorrow" is exactly the case this module
 * exists for — so it needs the storage that survives the tab closing.
 *
 * BOUNDED, so an active workspace visited over months cannot grow this key
 * without limit. `MAX_ENTRIES` evicts the LEAST recently touched id, never the
 * fewest-visited one — an LRU, not a frequency count, because "which records
 * has this reader stopped touching" is the honest question to answer when
 * something has to be forgotten.
 *
 * FAIL-SAFE DIRECTION, matching `tutorialPreference.ts`: every failure mode —
 * storage unavailable, absent key, unparseable JSON, wrong shape, an id that
 * is not a non-empty string, a view that is not one of the four recognised
 * ones — resolves to "no remembered view", never to a thrown error and never
 * to a guessed one. The cost of a false "no remembered view" is one reader
 * landing on `fields` exactly as they always have; the cost of trusting a
 * corrupt entry would be silently routing a reader somewhere wrong.
 */

import { RECORD_VIEW_IDS, type RecordViewId } from './routes';

/** The namespaced, VERSIONED storage key. Matches `tutorialPreference.ts`'s
 *  `.v1` convention: the suffix versions the storage SHAPE, not this feature's
 *  behaviour, so a later shape change gets a new key rather than a migration
 *  that has to guess at the old one's meaning. */
export const RECORD_LAST_VIEW_KEY = 'isaac.record-last-view.v1';

/** How many distinct experiment ids this browser remembers at once. Chosen to
 *  comfortably cover an active working set without the key growing without
 *  bound over a year of use — the same order of magnitude as this codebase's
 *  other bounded windows (`PENDING_WINDOW = 50`, `_BOUNDED_PENDING_NOTE`). */
export const MAX_ENTRIES = 50;

interface Entry {
  id: string;
  view: RecordViewId;
}

/** `window.localStorage` when it is usable, else `null`. Access itself can
 *  throw (Safari private mode, a blocked-cookies policy), so it is guarded,
 *  not assumed — identical to `tutorialPreference.ts`'s `storage()`. */
function storage(): Storage | null {
  try {
    if (typeof window === 'undefined') return null;
    return window.localStorage ?? null;
  } catch {
    return null;
  }
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0;
}

function isRecordView(value: unknown): value is RecordViewId {
  return typeof value === 'string' && (RECORD_VIEW_IDS as readonly string[]).includes(value);
}

/**
 * Read the stored list, oldest-touched first. Never throws. A stored value
 * that is not an array, or any element that is not `{id: string, view:
 * RecordViewId}` exactly, causes the WHOLE read to fall back to `[]` — a
 * partially-trusted list is not attempted, matching `tutorialPreference.ts`'s
 * "not repaired or migrated — ignored" rule for a mismatched record.
 */
function readEntries(): Entry[] {
  const store = storage();
  if (store === null) return [];
  let raw: string | null;
  try {
    raw = store.getItem(RECORD_LAST_VIEW_KEY);
  } catch {
    return [];
  }
  if (raw === null || raw === '') return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(parsed)) return [];
  const entries: Entry[] = [];
  for (const item of parsed) {
    if (
      typeof item === 'object' &&
      item !== null &&
      isNonEmptyString((item as Record<string, unknown>).id) &&
      isRecordView((item as Record<string, unknown>).view)
    ) {
      entries.push({
        id: (item as Record<string, unknown>).id as string,
        view: (item as Record<string, unknown>).view as RecordViewId,
      });
    }
  }
  return entries;
}

function writeEntries(entries: Entry[]): void {
  const store = storage();
  if (store === null) return;
  try {
    store.setItem(RECORD_LAST_VIEW_KEY, JSON.stringify(entries));
  } catch {
    /* quota, private mode, or a blocked policy — losing this preference is
       the acceptable failure named in the module comment above. */
  }
}

/**
 * The workspace this browser last saw the reader viewing on this record, or
 * `null` when nothing is remembered (including every failure mode above).
 */
export function lastRecordView(id: string): RecordViewId | null {
  if (!isNonEmptyString(id)) return null;
  const found = readEntries().find((entry) => entry.id === id);
  return found ? found.view : null;
}

/**
 * Record that this browser most recently saw `id` on `view`. Moves the entry
 * to the most-recently-touched end and evicts the least-recently-touched
 * entry once the list exceeds `MAX_ENTRIES`. Silent on every storage failure,
 * for the same reason `markTutorialCompleted` is: the navigation already
 * happened, and refusing to remember it because storage failed would not undo
 * that.
 */
export function rememberRecordView(id: string, view: RecordViewId): void {
  if (!isNonEmptyString(id) || !isRecordView(view)) return;
  const rest = readEntries().filter((entry) => entry.id !== id);
  rest.push({ id, view });
  while (rest.length > MAX_ENTRIES) rest.shift();
  writeEntries(rest);
}

/** Forget everything (used by tests). Never throws. */
export function clearRecordLastView(): void {
  const store = storage();
  if (store === null) return;
  try {
    store.removeItem(RECORD_LAST_VIEW_KEY);
  } catch {
    /* nothing to do — the read path already fails safe */
  }
}
