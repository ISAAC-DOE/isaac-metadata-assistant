/*
 * THE FIVE BUILT-IN WORKED-EXAMPLE RECORD IDS, as a BUILD-TIME CONSTANT.
 *
 * WHY THE CLIENT MAY HOLD THESE AT ALL, and why holding them discloses nothing.
 * These are not data about a workspace: they are five fixed ids this build ships,
 * chosen by the backend at authoring time (`apps/api/isaac_api/workspace.py`,
 * `_SEED_ID_PREFIX` / `CANONICAL_IDS`) and already public in the repository, in the
 * end-to-end fixtures and in `docs/`. Asking "is this id one of the five" is
 * answered from the bundle, with NO request, so it can never be an existence
 * oracle: it says which id was typed, never what any scope contains.
 *
 * WHAT THIS MUST NOT BECOME, stated because the temptation is obvious. The backend
 * deliberately refuses to look for a canonical id outside the scope the request
 * carried — `load_experiment` "NEVER seeds. A canonical worked-example id therefore
 * resolves to `None` in the normal scope, which is what makes a normal-scope
 * request for one a 404 rather than a silent cross-scope read"
 * (`workspace.py:3587-3592`). This constant exists precisely SO THAT the client can
 * explain that 404 without anyone asking the server to cross a scope. Nothing here
 * may be turned into a request that does, and no copy built on it may claim that a
 * record exists somewhere else — only that this id is a worked-example id and that
 * worked-example records live in a temporary workspace.
 *
 * DRIFT IS CAUGHT BY TEST, not by discipline: `__tests__/example-record-ids.test.ts`
 * reads `workspace.py` and fails if these five stop matching `CANONICAL_IDS`.
 */

/** The five fixed worked-example ids, mirroring `workspace.py::CANONICAL_IDS`. */
export const EXAMPLE_RECORD_IDS = [
  '01SYNTHXANESSEED0000000001',
  '01SYNTHXANESSEED0000000002',
  '01SYNTHXANESSEED0000000003',
  '01SYNTHXANESSEED0000000004',
  '01SYNTHXANESSEED0000000005',
] as const;

const EXAMPLE_RECORD_ID_SET: ReadonlySet<string> = new Set(EXAMPLE_RECORD_IDS);

/**
 * Is this id one of the five built-in worked-example records?
 *
 * A pure, offline, exact-match test. It is NOT evidence that a record exists, in
 * this scope or any other — only that the id is one this build ships as a
 * worked-example seed.
 */
export function isExampleRecordId(id: string | null | undefined): boolean {
  return typeof id === 'string' && EXAMPLE_RECORD_ID_SET.has(id);
}
