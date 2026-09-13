import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { composeDocumentTitle, routeDocumentTitle } from './documentTitle';

/**
 * THE ROUTE-DERIVED FLOOR. Mounted ONCE, and deliberately not per screen.
 *
 * See `documentTitle.ts` for why the floor is central rather than delegated: a
 * screen that forgets to set a title leaves the PREVIOUS route's title in the
 * tab strip, which misidentifies the page rather than merely under-describing
 * it. This runs on every navigation whether a screen cooperates or not.
 *
 * A `null` from `routeDocumentTitle` means the URL resolves elsewhere (`/` and
 * the `*` fallback both `<Navigate replace>`), and the title is left untouched
 * rather than set to a name for a page nobody is on.
 */
export function useRouteDocumentTitle(): void {
  const { pathname, search } = useLocation();
  useEffect(() => {
    const title = routeDocumentTitle(pathname, search);
    if (title !== null) document.title = title;
  }, [pathname, search]);
}

/**
 * A REFINEMENT of the route-derived title, for a screen that holds honest truth
 * the route does not carry — today only the record screen, once its bundle has
 * loaded and it knows the record's name.
 *
 * ── THE ORDERING THIS DEPENDS ON, STATED BECAUSE IT IS LOAD-BEARING ─────────
 *
 * `<DocumentTitle />` is rendered as an EARLIER SIBLING of `<Routes />` in
 * `App.tsx`. React flushes effects in tree order, so the floor is written
 * before any screen's refinement in the same commit, and the refinement wins.
 * Reversing those two JSX lines would silently reverse the precedence and the
 * record's name would flicker away on every navigation — so `App.tsx` carries a
 * comment saying so, and `__tests__/document-title.test.tsx` pins the outcome
 * rather than the ordering, which is the property that actually matters.
 *
 * ── THE TRAP THIS HOOK'S DEPENDENCY LIST EXISTS TO AVOID ────────────────────
 *
 * The location is in the dependency list even though it is not used to BUILD
 * the title. Without it: on the record screen, a navigation that changes only
 * `?run=<id>` re-runs the floor (its deps include `search`) but NOT this
 * refinement (its segments are unchanged) — so the record's name would be
 * dropped from the title by an act that did not change the record. With it,
 * every location change re-applies the refinement after the floor. Measured as
 * a real sequence on this screen, not hypothesised: `RunsSection` pushes
 * `?view=runs&run=<id>` on every row open.
 *
 * Passing `null` — the honest state while a record is still loading — leaves
 * the floor's title in place and asserts nothing about the record.
 */
export function useDocumentTitle(
  segments: readonly (string | null | undefined)[] | null,
): void {
  const { pathname, search } = useLocation();
  const composed = segments === null ? null : composeDocumentTitle(segments);
  useEffect(() => {
    if (composed !== null) document.title = composed;
  }, [composed, pathname, search]);
}

/**
 * The floor as a component, so it can sit in the tree ABOVE `<Routes />` and
 * take effect on every route without any screen importing anything.
 */
export function DocumentTitle(): null {
  useRouteDocumentTitle();
  return null;
}
