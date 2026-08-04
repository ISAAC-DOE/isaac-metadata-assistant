/**
 * Global teardown — discard the shared worked-example session.
 *
 * A session is a real directory on the backend
 * (`workspace_root()/_tutorial/<session_id>/`) holding five materialised
 * records. The backend reclaims an abandoned one by TTL sweep, so leaving it
 * would not corrupt anything, but a suite that opens a server-side resource on
 * every run and never closes it is a suite that leaves 24 hours of litter per
 * run on a developer's machine.
 *
 * IDEMPOTENT, AND NEVER FATAL. `DELETE /api/tutorial/sessions/{id}` answers 204
 * for a session that is already gone — the postcondition the caller asked for
 * already holds — and a 404 (no backend, or a base URL that no longer serves
 * the route) is treated as success for the same reason. Cleanup must never turn
 * a green run red: the run's verdict was decided by the specs, and a failure to
 * tidy up afterwards is reported to stdout, not raised.
 *
 * The handoff file is removed whatever the DELETE did, so a later run cannot
 * inherit a pointer to a session this one intended to discard. (Setup also
 * removes it up front, so the two ends are independent.)
 */

import {
  disposeWorkedExampleSession,
  readWorkedExampleSession,
  unpublishWorkedExampleSession,
} from './worked-example';

export default async function globalTeardown(): Promise<void> {
  let sessionId: string | null = null;
  try {
    sessionId = readWorkedExampleSession().sessionId;
  } catch {
    // No handoff file: setup failed before publishing, or a previous teardown
    // already ran. Nothing to discard, and nothing worth reporting.
    return;
  }

  try {
    const status = await disposeWorkedExampleSession(sessionId);
    const ok = status === 204 || status === 404;
    // eslint-disable-next-line no-console
    console.log(
      ok
        ? `[e2e] worked-example session discarded (DELETE → ${status}).`
        : `[e2e] WARNING: DELETE of worked-example session ${sessionId} returned ${status}. ` +
            `Nothing failed because of it — the backend's TTL sweep reclaims the session — but ` +
            `the disposal contract says 204/404, so this is worth a look.`
    );
  } catch (cause) {
    // eslint-disable-next-line no-console
    console.log(
      `[e2e] WARNING: could not discard worked-example session ${sessionId}: ` +
        `${(cause as Error).message}. The backend's TTL sweep will reclaim it.`
    );
  } finally {
    unpublishWorkedExampleSession();
  }
}
