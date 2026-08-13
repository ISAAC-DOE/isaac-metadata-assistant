/*
 * Typed mutation-refusal discriminators, shared by every screen that writes.
 *
 * THIS FILE EXISTS BECAUSE THERE WERE TWO CONSUMERS AND ONLY ONE OF THEM KNEW.
 * `POST /edit` began refusing an unstorable correction with `422
 * invalid_field_value`, and the Complete screen was taught to read it. The
 * Assistant's confirmation path also calls `api.editField` — through
 * `confirmProposal`, which catches only 412 and rethrows — and nothing there
 * knew about the new status, so the same input produced an unhandled promise
 * rejection and no user feedback at all.
 *
 * Duplicating the predicate into the second consumer would have created the
 * second definition of "the record refused this value", which is the mistake
 * `is_sha256_shaped` was exported in the backend to avoid. One definition, two
 * callers.
 */

/**
 * The HTTP status carried by a thrown mutation error, if it carries one.
 *
 * Duck-typed rather than `instanceof ApiError`: a transport failure, a rejected
 * `fetch`, and a test double all reach a `catch` as something that may or may not have
 * a `status`. `undefined` means "this error does not say", which callers must not
 * translate into a claim about what happened to the record.
 *
 * Lived privately in `assistantAgent.ts`; hoisted here when a second caller appeared,
 * rather than copied.
 */
export function statusOf(err: unknown): number | undefined {
  if (typeof err === 'object' && err !== null && 'status' in err) {
    return (err as { status?: number }).status;
  }
  return undefined;
}

/**
 * Did the server refuse this write because the VALUE cannot be stored?
 *
 * Narrow on purpose. A 422 from `POST /edit` has three other causes — a missing
 * `confirmed_by_user`, a body naming no recognised editable field (which includes an
 * asset whose hash is still an open question), and whatever a future validation adds
 * — and none of them entitles a screen to say "the field still holds the value it held
 * before". So the `error` CODE is read, not just the status; an unrecognised 422 falls
 * through to whatever generic notice the caller has, which claims less.
 *
 * Takes `unknown` rather than `ApiError`: one caller holds a typed `ApiError | null`
 * from component state, the other holds the `unknown` of a `catch`. The body is narrowed
 * here rather than cast (`ApiError` deliberately does not model per-route payloads), and
 * anything that does not have the expected shape returns false — the fail-closed
 * direction, which under-claims rather than over-claims.
 */
export function isUnstorableFieldValue(err: unknown): boolean {
  if (typeof err !== 'object' || err === null) return false;
  if ((err as { status?: unknown }).status !== 422) return false;
  const body = (err as { body?: unknown }).body;
  if (typeof body !== 'object' || body === null) return false;
  return (body as { error?: unknown }).error === 'invalid_field_value';
}

/**
 * Did the ANSWER to this write come from an authenticating edge rather than from
 * ISAAC? Duck-typed for the same reason `statusOf` is.
 *
 * The signal itself is established in `lib/api.ts::interceptedByEdge` — an HTML
 * content type on an `/api/*` path, or a redirect whose final URL left
 * `API_BASE`. Neither can be produced by an ordinary failure, which is exactly
 * why this may drive a sentence as specific as "your session ended".
 */
function wasIntercepted(err: unknown): boolean {
  if (typeof err !== 'object' || err === null) return false;
  return (err as { htmlIntercept?: unknown }).htmlIntercept === true;
}

/** The one remedy, shared so the five write surfaces cannot drift apart. */
const SIGN_IN_REMEDY = 'Reload the page to sign in again, then try again.';

/**
 * The notice a WRITE surface shows when it failed — the session sentence when
 * the failure says the session ended, and the caller's own fallback otherwise.
 *
 * WHY THIS EXISTS. Every mutation site rendered `err.message`, which for an edge
 * intercept is a transport sentence written for a developer, and the reader was
 * left to guess. `CsvReconcilePanel` was worse than uninformative: its generic
 * branch reads "The CSV could not be processed. Please check the file and try
 * again", so an expired session blamed the scientist's file for a response the
 * file had nothing to do with, and sent them to re-export a perfectly good CSV.
 * A single helper rather than five copies, for the reason this whole module
 * exists: five copies is five definitions of "the session ended".
 *
 * THE THREE SIGNALS, AND WHY EACH ONE ENTITLES US TO CLAIM THE WRITE DID NOT
 * HAPPEN.
 *
 *  - An INTERCEPT means the request never reached ISAAC at all (see
 *    `wasIntercepted`), so there is nothing it could have changed.
 *  - A 401 is the only status `apps/api/isaac_api/auth.py` produces, and its
 *    middleware rejects before routing — no handler runs.
 *  - A 403 in this application is always a pre-mutation gate (`runtime_mode`
 *    refusals, the always-refusing uploads route); none of them writes first.
 *
 * The claim is deliberately about what the SERVER did, not about what the screen
 * now shows: nothing here reloads or re-reads, so the caller must not use it to
 * imply the view is current.
 *
 * `fallback` is evaluated by the caller and returned untouched for every other
 * failure. This helper never reinterprets a failure it cannot name.
 */
export function mutationFailureCopy(err: unknown, fallback: string): string {
  if (wasIntercepted(err)) {
    return (
      'A sign-in page was returned in place of the ISAAC API, so this request never ' +
      `reached it and nothing was changed. ${SIGN_IN_REMEDY}`
    );
  }
  const status = statusOf(err);
  if (status === 401) {
    return (
      'The ISAAC API rejected this request as unauthenticated (HTTP 401) before it was ' +
      `carried out, so nothing was changed. ${SIGN_IN_REMEDY}`
    );
  }
  if (status === 403) {
    return (
      'The ISAAC API refused this request as unauthorized (HTTP 403) before it was ' +
      `carried out, so nothing was changed. ${SIGN_IN_REMEDY}`
    );
  }
  return fallback;
}
