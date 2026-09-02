/**
 * Nothing to dispose, and saying so is the point.
 *
 * The mutation suite's teardown DELETEs the worked-example session it opened. This
 * suite opens none — its records live in the ordinary scope of a workspace
 * directory `globalSetup` wipes at the start of the next run. Leaving the directory
 * in place is deliberate: a failed run stays inspectable.
 */
export default async function globalTeardown() {
  // intentionally empty
}
