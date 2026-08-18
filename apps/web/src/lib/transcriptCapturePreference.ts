/*
 * The transcript-capture first-use guidance's ONE piece of durable state: "has
 * this browser seen the guidance for the current version of this panel?"
 *
 * A SECOND MODULE RATHER THAN A SECOND FLAG IN `tutorialPreference.ts`, and the
 * separation is the point: finishing the guided walkthrough must never mark this
 * guidance seen, and dismissing this guidance must never mark the walkthrough
 * complete. Two records under two keys cannot be conflated by a later edit.
 *
 * WHY BROWSER-LOCAL, AND WHY THE PANEL SAYS SO. Identical to the walkthrough's
 * reason, and it is not restated here so the two cannot drift: see
 * `tutorialPreference.ts`. There is no server profile to file a per-user
 * preference in and no identity this build trusts to key one by.
 *
 * WHAT MAY BE STORED HERE, exhaustively: this guidance's own id, its version
 * number, a boolean, and a timestamp. NO transcript text, NO record content, NO
 * field value, NO record id, NO run id, NO identity value, NO credential, NO
 * path. That list is checkable by reading `serialize()` alone — and it matters
 * more here than for the walkthrough, because this panel handles free text a
 * scientist dictated.
 *
 * FAIL-SAFE DIRECTION, AND IT POINTS THE SAME WAY. Every failure — storage
 * unavailable, absent key, unparseable JSON, wrong shape, wrong id, an
 * unrecognised version — resolves to NOT SEEN, so the guidance is shown again.
 * The cost of a false "not seen" is one dismissible panel; the cost of a false
 * "seen" is a scientist who is never told how to speak to this thing. Nothing
 * here throws.
 */

/** The namespaced, VERSIONED storage key. The `.v1` suffix versions the storage
 *  SHAPE; `GUIDANCE_VERSION` below versions the guidance's CONTENT. */
export const CAPTURE_GUIDANCE_KEY = 'isaac.transcriptCaptureGuidance.v1';

/** This guidance's identity, distinct from the walkthrough's. */
export const CAPTURE_GUIDANCE_ID = 'isaac-transcript-capture-guidance';

/**
 * The CONTENT version. Bump it when the guidance text changes materially, and
 * every browser is shown it again — a stored record for a different version
 * reads as not seen, never as seen and never as an error.
 */
export const CAPTURE_GUIDANCE_VERSION = 1;

export interface CaptureGuidancePreference {
  guidanceId: string;
  version: number;
  seen: boolean;
  /** ISO-8601, or null when never dismissed. A local clock reading. */
  seenAt: string | null;
}

/** The value every failure path resolves to. Frozen so a caller cannot mutate
 *  the shared fallback and make a later read lie. */
export const NOT_SEEN: CaptureGuidancePreference = Object.freeze({
  guidanceId: CAPTURE_GUIDANCE_ID,
  version: CAPTURE_GUIDANCE_VERSION,
  seen: false,
  seenAt: null,
});

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

/** Read the stored record, or `NOT_SEEN`. Never throws; never repairs. */
export function readCaptureGuidancePreference(): CaptureGuidancePreference {
  const store = storage();
  if (store === null) return NOT_SEEN;

  let raw: string | null;
  try {
    raw = store.getItem(CAPTURE_GUIDANCE_KEY);
  } catch {
    return NOT_SEEN;
  }
  if (raw === null || raw === '') return NOT_SEEN;

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return NOT_SEEN;
  }
  if (!isRecord(parsed)) return NOT_SEEN;
  if (parsed.guidanceId !== CAPTURE_GUIDANCE_ID) return NOT_SEEN;
  if (parsed.version !== CAPTURE_GUIDANCE_VERSION) return NOT_SEEN;
  if (parsed.seen !== true) return NOT_SEEN;

  const seenAt = typeof parsed.seenAt === 'string' ? parsed.seenAt : null;
  return {
    guidanceId: CAPTURE_GUIDANCE_ID,
    version: CAPTURE_GUIDANCE_VERSION,
    seen: true,
    seenAt,
  };
}

/** The one question the panel asks on mount. */
export function isCaptureGuidanceSeen(): boolean {
  return readCaptureGuidancePreference().seen;
}

/** The ONE serializer. Everything written to this key passes through here. */
function serialize(seenAt: string): string {
  const record: CaptureGuidancePreference = {
    guidanceId: CAPTURE_GUIDANCE_ID,
    version: CAPTURE_GUIDANCE_VERSION,
    seen: true,
    seenAt,
  };
  return JSON.stringify(record);
}

/**
 * Record that this browser has seen the guidance. A storage failure is swallowed
 * on purpose: the guidance has already been read, and blocking the panel because
 * a preference could not be saved would be worse than showing it again.
 */
export function markCaptureGuidanceSeen(nowIso: string = new Date().toISOString()): void {
  const store = storage();
  if (store === null) return;
  try {
    store.setItem(CAPTURE_GUIDANCE_KEY, serialize(nowIso));
  } catch {
    /* quota, private mode, or a blocked policy — the read path fails safe */
  }
}

/** Forget the record, so the guidance is offered again. Never throws. */
export function clearCaptureGuidancePreference(): void {
  const store = storage();
  if (store === null) return;
  try {
    store.removeItem(CAPTURE_GUIDANCE_KEY);
  } catch {
    /* nothing to do — the read path already fails safe */
  }
}
