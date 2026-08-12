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
