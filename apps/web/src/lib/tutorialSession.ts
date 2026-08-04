/**
 * Persistence for an IN-PROGRESS worked-example session.
 *
 * Deliberately separate from `tutorialPreference.ts`, which persists whether the
 * walkthrough has ever been COMPLETED. The two have different lifetimes and
 * different storage, and conflating them was never an option:
 *
 * - completion is a durable fact about this browser -> `localStorage`, survives
 *   the tab closing (see `tutorialPreference.ts`);
 * - an open session is a disposable server-side workspace -> `sessionStorage`,
 *   dies with the tab. That is the correct lifetime: the backend reclaims an
 *   abandoned session by TTL sweep, so a pointer that outlived the tab would
 *   usually name a session that no longer exists.
 *
 * The stored `index` is what makes refresh recovery a RESUME rather than a
 * restart. Without it a reload would drop the reader back to step one inside a
 * session whose records they had already worked through.
 *
 * Every read is fail-safe: an absent, unparseable, wrong-shaped or
 * wrong-version payload is reported as "no session" rather than throwing. A
 * walkthrough must never be able to break the app it is teaching.
 */

/** Versions the storage SHAPE. Bump when the payload's fields change. */
export const TUTORIAL_SESSION_KEY = 'isaac.tutorial.session.v1';

export interface TutorialSessionRecord {
  /** The server-minted session id. Opaque here; never parsed or constructed. */
  sessionId: string;
  /** Which step the reader had reached, so a reload resumes instead of restarting. */
  index: number;
}

/** `sessionStorage`, or `null` where it is unavailable (SSR, or a privacy mode
 *  that throws on access). Probed defensively — reading the property itself can
 *  throw in some browsers, which is why this is wrapped rather than tested. */
function store(): Storage | null {
  try {
    return typeof sessionStorage === 'undefined' ? null : sessionStorage;
  } catch {
    return null;
  }
}

/**
 * The persisted session, or `null`.
 *
 * Returns `null` — never throws and never a partial record — for: no storage,
 * no entry, invalid JSON, a non-object, a missing/empty `sessionId`, or a
 * non-finite / negative / non-integer `index`. A half-valid payload is treated
 * as absent, because resuming at a garbage step is worse than restarting.
 */
export function readTutorialSession(): TutorialSessionRecord | null {
  const s = store();
  if (!s) return null;
  let raw: string | null;
  try {
    raw = s.getItem(TUTORIAL_SESSION_KEY);
  } catch {
    return null;
  }
  if (!raw) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof parsed !== 'object' || parsed === null) return null;
  const { sessionId, index } = parsed as Record<string, unknown>;
  if (typeof sessionId !== 'string' || sessionId === '') return null;
  if (typeof index !== 'number' || !Number.isInteger(index) || index < 0) return null;
  return { sessionId, index };
}

/** Persist the open session. Silently no-ops when storage is unavailable or
 *  full — losing resume position is a degraded experience, not a failure worth
 *  propagating into the walkthrough. */
export function writeTutorialSession(record: TutorialSessionRecord): void {
  const s = store();
  if (!s) return;
  try {
    s.setItem(TUTORIAL_SESSION_KEY, JSON.stringify(record));
  } catch {
    /* storage full or denied: resume position is best-effort */
  }
}

/** Update only the step, leaving the session id alone. No-op when no session is
 *  stored — it must not resurrect a disposed session under a fresh id. */
export function updateTutorialSessionIndex(index: number): void {
  const current = readTutorialSession();
  if (!current) return;
  writeTutorialSession({ ...current, index });
}

/** Forget the open session. Called on completion, dismissal, and when the
 *  server reports the session is gone. Idempotent. */
export function clearTutorialSession(): void {
  const s = store();
  if (!s) return;
  try {
    s.removeItem(TUTORIAL_SESSION_KEY);
  } catch {
    /* nothing to do: the pointer is already unusable */
  }
}
