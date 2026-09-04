/*
 * The Run browser's paging constants, in a `.ts` module rather than beside the
 * component that uses them.
 *
 * WHY THEY LIVE HERE. The scale benchmark (`e2e/mutation/run-scale.bench.ts`) has to
 * know the first-page size: it waits for the cards the product actually renders, and
 * above that size a bare `target` would wait for cards that will never exist. Reading
 * the number from the component is the only way that stays true when the default
 * changes — but `e2e/tsconfig.json` deliberately does not set `jsx`, so it cannot
 * import a `.tsx` file at all. A literal `50` in the benchmark would compile and would
 * be a second copy of a product decision, silently wrong the day the UI changed.
 *
 * So the decision lives in a module both sides can read, and `RunsSection` re-exports
 * it for the callers that already import it from there.
 */

/**
 * How many runs the Runs section asks for at a time.
 *
 * 50 IS MEASURED, NOT ROUND. `docs/run-scale-measurements.md` §2: 50 runs is 373 KiB
 * and 28 ms of API time; ~100 is still comfortable at ~1.1 s to a fully usable screen;
 * 250 is noticeable; 500 is bad and shows the first long tasks. 50 sits with a whole
 * page of headroom below the point where anything degrades, which is what a first page
 * should do — the reader waits for it before they can do anything at all.
 *
 * IT IS A UI DEFAULT AND NOT A PRODUCT MAXIMUM. There is no limit on how many runs a
 * record may have, the route's own description says so, and no string the component
 * renders may imply otherwise: Load More is offered until every match is loaded, and
 * the count always names the record's real total beside whatever is on screen.
 *
 * It is also well under the route's `RUN_PAGE_MAX` of 200, which bounds ONE RESPONSE
 * and is a different decision belonging to a different layer. A UI that requested the
 * server's ceiling would be treating a safety bound as a recommendation.
 */
export const RUNS_PAGE_SIZE = 50;

/**
 * `RUN_PAGE_MAX` (`apps/api/isaac_api/routes.py`) — the largest page the run listing
 * route will EVER return in one response, mirrored here for exactly one purpose: a
 * change-feed signal that a run moved elsewhere has to decide, WITHOUT a round trip,
 * whether the section can re-read everything currently on screen in a single bounded
 * request. That decision has to be made client-side before the request is sent, so
 * this is a case the general "do not retype a server bound" rule (see `_RUN_LIMIT_DESC`
 * in `routes.py`, which interpolates rather than retypes) cannot avoid: there is no
 * request this value could instead be read off. If the server's bound ever changes,
 * this one has to change with it — ~~NO TEST IN THIS TREE PINS THAT AGREEMENT TODAY, and
 * that is a named gap rather than an oversight papered over: closing it needs either a
 * committed test reading `RUN_PAGE_MAX` out of the OpenAPI document this build already
 * serves, or a Python-side test asserting the two literals match, and neither exists
 * yet.~~
 *
 * **CLOSED 2026-09-03, and the sentence above is struck rather than deleted because
 * "no test pins this" is exactly the kind of claim a future session acts on.**
 * `apps/api/tests/test_run_page_bound_parity.py` now does BOTH of the two things that
 * paragraph named: it asserts the served OpenAPI parameter's `maximum` IS
 * `routes.RUN_PAGE_MAX`, and it asserts this literal equals that constant, failing with
 * both numbers named so the message says which side moved.
 *
 * WHAT IS STILL TRUE, AND IS WHY THE COPY REMAINS A COPY: the check closes the DRIFT,
 * not the duplication. The better fix is for the run listing to SERVE this bound and
 * for `RunsSection` to read it, at which point this constant disappears; that is a
 * change to that component's over-the-cap decision and belongs to a slice that owns it.
 *
 * A record with more runs LOADED than this cannot be silently reconciled in one
 * request; see `RunsSection`'s "over the cap" path, which shows a note and a Refresh
 * control instead of guessing at a limit the server would clamp or refuse.
 */
export const RUN_LIST_LIMIT_MAX = 200;
