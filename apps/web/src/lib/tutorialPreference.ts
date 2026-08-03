/*
 * The guided walkthrough's ONE piece of durable state: "has this browser
 * finished the current version of the walkthrough?"
 *
 * WHY BROWSER-LOCAL, AND WHY THAT IS SAID OUT LOUD IN THE UI.
 *
 * This build has no user identity it trusts and no profile store. The Authentik
 * edge does put candidate identity headers on the request, but ISAAC consumes
 * none of them, and two of the seven are permanently disqualified from ever
 * being read as identity (see `docs/identity-trust-contract.md` §6A). There is
 * therefore no honest key to file a per-user preference under, and no server
 * profile to file it in. So completion is remembered by the BROWSER, and the
 * Settings copy says so rather than implying it follows the reader to another
 * device. When a server-side profile exists, this module is the only thing that
 * has to change — the tutorial UI never touches storage directly.
 *
 * WHAT MAY BE STORED HERE, exhaustively: the tutorial's own id, its version
 * number, a boolean, and a completion timestamp. NO record content, NO field
 * value, NO record id, NO identity value (username, uid, email, group), NO
 * credential, NO path. A reviewer should be able to confirm that by reading
 * `serialize()` alone.
 *
 * FAIL-SAFE DIRECTION. Every failure mode — storage unavailable, absent key,
 * unparseable JSON, wrong shape, wrong tutorial id, a version this build does
 * not recognise — resolves to NOT COMPLETED. That direction is deliberate: the
 * cost of a false "not completed" is one dismissible offer, and the cost of a
 * false "completed" is a reader who is never offered the walkthrough at all.
 * Nothing in here throws.
 */

/** The namespaced, VERSIONED storage key. The `.v1` suffix versions the storage
 *  SHAPE; `TUTORIAL_VERSION` below versions the walkthrough's CONTENT. They are
 *  different things and are deliberately not merged: adding a step re-offers the
 *  tutorial without abandoning a key, and changing the record shape gets a new
 *  key without having to pretend the content changed. */
export const TUTORIAL_PREFERENCE_KEY = 'isaac.tutorial.v1';

/** The walkthrough's identity. A future second tutorial gets its own id and its
 *  own record, so finishing one can never mark the other complete. */
export const TUTORIAL_ID = 'isaac-guided-walkthrough';

/**
 * The CONTENT version. Bump it when the step list changes materially, and every
 * browser is offered the walkthrough again — a stored record for a different
 * version reads as not completed (never as completed, and never as an error).
 */
export const TUTORIAL_VERSION = 1;

export interface TutorialPreference {
  tutorialId: string;
  version: number;
  completed: boolean;
  /** ISO-8601, or null when never completed. A local clock reading — not an
   *  identity value and not derived from any record. */
  completedAt: string | null;
}

/** The value every failure path resolves to. Frozen so a caller cannot mutate
 *  the shared fallback and make a later read lie. */
export const NOT_COMPLETED: TutorialPreference = Object.freeze({
  tutorialId: TUTORIAL_ID,
  version: TUTORIAL_VERSION,
  completed: false,
  completedAt: null,
});

/** `window.localStorage` when it is usable, else null. Access itself can throw
 *  (Safari private mode, a blocked-cookies policy), so it is guarded, not
 *  assumed. */
function storage(): Storage | null {
  try {
    if (typeof window === 'undefined') return null;
    return window.localStorage ?? null;
  } catch {
    return null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Read the stored record, or `NOT_COMPLETED`. This never throws and never
 * returns a partially-trusted object: a record that does not match this
 * tutorial's id, or does not carry this build's version, is not repaired or
 * migrated — it is ignored.
 */
export function readTutorialPreference(): TutorialPreference {
  const store = storage();
  if (store === null) return NOT_COMPLETED;

  let raw: string | null;
  try {
    raw = store.getItem(TUTORIAL_PREFERENCE_KEY);
  } catch {
    return NOT_COMPLETED;
  }
  if (raw === null || raw === '') return NOT_COMPLETED;

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return NOT_COMPLETED;
  }
  if (!isRecord(parsed)) return NOT_COMPLETED;

  if (parsed.tutorialId !== TUTORIAL_ID) return NOT_COMPLETED;
  if (parsed.version !== TUTORIAL_VERSION) return NOT_COMPLETED;
  if (parsed.completed !== true) return NOT_COMPLETED;

  const completedAt = typeof parsed.completedAt === 'string' ? parsed.completedAt : null;
  return { tutorialId: TUTORIAL_ID, version: TUTORIAL_VERSION, completed: true, completedAt };
}

/** The one question the UI asks. Completion is scoped to THIS build's tutorial
 *  version — a bump re-offers the walkthrough. */
export function isTutorialCompleted(): boolean {
  return readTutorialPreference().completed;
}

/**
 * The ONE serializer. Everything the app can ever write to this key passes
 * through here, so the "what may be stored" list above is checkable in one
 * place.
 */
function serialize(completedAt: string): string {
  const record: TutorialPreference = {
    tutorialId: TUTORIAL_ID,
    version: TUTORIAL_VERSION,
    completed: true,
    completedAt,
  };
  return JSON.stringify(record);
}

/**
 * Record that this browser finished the current version. A storage failure is
 * swallowed on purpose: the walkthrough has already been shown, and refusing to
 * finish it because a preference could not be saved would be a worse outcome
 * than being offered it again next visit.
 */
export function markTutorialCompleted(nowIso: string = new Date().toISOString()): void {
  const store = storage();
  if (store === null) return;
  try {
    store.setItem(TUTORIAL_PREFERENCE_KEY, serialize(nowIso));
  } catch {
    /* quota, private mode, or a blocked policy — see the note above */
  }
}

/** Forget the record entirely (used by tests, and available to a future
 *  "show me this again on every visit" control). Never throws. */
export function clearTutorialPreference(): void {
  const store = storage();
  if (store === null) return;
  try {
    store.removeItem(TUTORIAL_PREFERENCE_KEY);
  } catch {
    /* nothing to do — the read path already fails safe */
  }
}
