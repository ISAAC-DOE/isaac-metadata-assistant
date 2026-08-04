/**
 * Discard the mutation suite's worked-example session.
 *
 * Same contract as the read-only suite's teardown: idempotent (204 for an absent
 * session, 404 treated as success), never fatal, and the handoff file goes
 * whatever the DELETE did. Cleanup must not be able to turn a green run red.
 *
 * This suite's workspace directory is deliberately left in place — `env.ts`
 * explains why (a failed run leaves an INSPECTABLE workspace), and the next run's
 * `globalSetup` wipes it. Only the server-side session is released here.
 */

import { MUT_API_BASE, MUT_SESSION_FILE } from './env';
import {
  disposeWorkedExampleSession,
  readWorkedExampleSession,
  unpublishWorkedExampleSession,
} from '../worked-example';

export default async function globalTeardown(): Promise<void> {
  let sessionId: string;
  try {
    sessionId = readWorkedExampleSession(MUT_SESSION_FILE).sessionId;
  } catch {
    return; // setup failed before publishing, or already torn down
  }
  try {
    const status = await disposeWorkedExampleSession(sessionId, MUT_API_BASE);
    // eslint-disable-next-line no-console
    console.log(`[mutation-teardown] session discarded (DELETE → ${status}).`);
  } catch (cause) {
    // eslint-disable-next-line no-console
    console.log(
      `[mutation-teardown] WARNING: could not discard session ${sessionId}: ` +
        `${(cause as Error).message}. The backend's TTL sweep will reclaim it.`
    );
  } finally {
    unpublishWorkedExampleSession(MUT_SESSION_FILE);
  }
}
