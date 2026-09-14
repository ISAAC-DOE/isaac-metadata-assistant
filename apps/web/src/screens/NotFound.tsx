import './screens.css';
import { Link, useHref, useLocation } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { TriangleAlert } from '../components/icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';

/**
 * QA-020 — THE HONEST NOT-FOUND STATE.
 *
 * WHAT IT REPLACES, and why the previous behaviour was a defect rather than a
 * simplification. `App.tsx`'s catch-all was
 * `<Route path="*" element={<Navigate to={ROUTES.experiments} replace />} />`.
 * Every unrecognised path therefore became My Experiments, silently — and
 * `replace` ERASED the attempted URL from history, so Back could not recover
 * it and the reader had no way to see what they had asked for. Found by
 * navigating the hosted deployment to `/krish/validator`: it landed on
 * `<h1>My Experiments</h1>` with the path rewritten and no message at all.
 *
 * A stale bookmark, a mistyped path, or a link from an old document is a
 * perfectly ordinary thing for a scientist to arrive with, and the product's
 * answer was to pretend they had asked for something else.
 *
 * THE ATTEMPTED PATH IS SHOWN, WHICH IS THE POINT. It is the one piece of
 * information the reader needs to tell a typo from a genuinely dead link, and
 * it is exactly what the old `replace` destroyed.
 *
 * *** WHAT THIS SCREEN MUST NOT SAY, because the honest scope is narrow. ***
 * This is an unrecognised PATH, not a missing record. A record that does not
 * exist is a DIFFERENT case and is already handled correctly elsewhere:
 * `/record/<unknown-ULID>` matches `ROUTE_PATTERNS.record` and reaches
 * `RecordWorkbench`, which has its own not-found handling for a record the
 * server does not return. So this screen may not say "that record was not
 * found", may not speculate that anything was deleted or discarded, and may
 * not imply the reader's record is gone — it knows only that no screen in this
 * application answers to this address.
 *
 * IT ALSO DOES NOT GUESS A DESTINATION. There is no "did you mean ...?": that
 * would require a similarity rule nobody specified, and a wrong guess on this
 * screen sends a reader somewhere they did not ask for, which is the defect
 * being fixed one step further along.
 *
 * The path is rendered as TEXT and never as a link or as HTML — it is
 * attacker-controllable in the sense that anyone can put anything in a URL, and
 * React escapes it by construction. `decodeURIComponent` is deliberately NOT
 * applied: a percent-encoded path shown raw is the path the reader actually
 * requested, and decoding could render control characters or a lookalike.
 */
export function NotFound() {
  /*
   * THE BASENAME IS PREPENDED, AND THAT IS A FIX FOR A DEFECT THIS SCREEN SHIPPED
   * WITH — found by independent review (I-1).
   *
   * React Router STRIPS the basename from `useLocation().pathname`. The deployed
   * basename is `/krish` (`Dockerfile` `ARG BASE_PATH=/krish` -> `VITE_BASE_PATH`
   * -> `App.tsx`'s `BASENAME`), so a reader who typed `/krish/validator` was shown
   *
   *     You asked for: /validator
   *
   * — a different string from the one in their URL bar, on the one screen whose
   * entire purpose is to let them tell a typo from a dead link. `/krish/validator`
   * is the EXACT url this screen's own commit message cites as the discovery that
   * motivated it, so the defect was in the demonstration case.
   *
   * IT WAS INVISIBLE BECAUSE BOTH TEST HARNESSES USED `MemoryRouter` WITH NO
   * `basename`, so the fixture could not produce the input the assertion exists
   * for. That is the same shape as every other vacuous guard this programme has
   * found; `__tests__/not-found-state.test.tsx` now drives the deployed basename
   * explicitly.
   *
   * THE BASENAME IS TAKEN FROM THE ROUTER, NOT FROM THE BUILD, and that is the
   * second version of this fix. The first imported `App`'s `BASENAME` (derived from
   * `import.meta.env.BASE_URL`) and was wrong twice over: it is `''` under vitest,
   * so the regression test could not see the deployed case it exists for, and
   * `NotFound` importing from `App` while `App` imports `NotFound` is a CYCLE.
   *
   * `useHref('/')` asks the router what the application root resolves to — `/krish/`
   * under the deployed basename, `/` without one. It therefore cannot disagree with
   * the router by construction, works identically for `BrowserRouter` and
   * `MemoryRouter`, and is measurable in a test that supplies a basename.
   *
   * `search` and `hash` are still excluded: they are not part of what failed to
   * match, and a query string can be long enough to bury the part that matters.
   */
  const location = useLocation();
  const basename = useHref('/').replace(/\/+$/, '');
  const attempted = `${basename}${location.pathname}`;

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="breadcrumb" breadcrumb={LABELS.screenNotFound} />}
      mainPad="centered"
    >
      <div className="centered-col">
        {/* Exactly one `<h1>`, per `e2e/specs/structure.spec.ts`, and visible
            rather than `sr-only`: unlike the on-ramp screens that use a hidden
            heading to preserve a deliberate visual design, the whole purpose of
            THIS surface is to tell a sighted reader something went wrong. A
            hidden heading here would reproduce the silence it exists to fix. */}
        <div className="notfound">
          <span className="notfound-icon" aria-hidden="true">
            <TriangleAlert size={22} strokeWidth={2.2} />
          </span>
          <h1 className="notfound-title">{LABELS.screenNotFound}</h1>
          <p className="notfound-body">{LABELS.notFoundExplanation}</p>
          <p className="notfound-attempted">
            {LABELS.notFoundAttemptedLabel}{' '}
            <span className="mono notfound-path">{attempted}</span>
          </p>
          <p className="notfound-scope">{LABELS.notFoundRecordScope}</p>
          <Link className="btn btn-primary" to={ROUTES.experiments}>
            {LABELS.actionGoToExperiments}
          </Link>
        </div>
      </div>
    </AppShell>
  );
}
