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
