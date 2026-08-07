import './statistics.css';
import { Link } from 'react-router-dom';

/* `CircleDashed`, not a person or a padlock. This app's dashed treatment means
   "never reads as an established fact" (`signals.css`, the `evCandidate` /
   `evUnknown` chips), which is exactly this tab's condition; a padlock would
   claim a permission denial and a person glyph would imply an identity. */
import { CircleDashed } from '../../components/icons';
import { ROUTES } from '../../lib/routes';
import {
  type CurrentUserSource,
  disabledCurrentUserSource,
} from '../../lib/currentUserContract';
import {
  MY_STATS_PENDING_COPY,
  MY_STATS_PENDING_LABEL,
  MY_STATS_PENDING_REASON,
  MY_STATS_VIEWS,
  personalStatisticsSourceFor,
  type MyStatsPendingReason,
  type MyStatsSource,
} from '../../lib/myStatsContract';
import { ChartAccessPending } from './StatsCharts';
import { StatsSection } from './StatsPrimitives';

/**
 * My Stats — the personal-statistics tab.
 *
 * ── What this renders, and why it renders nothing else ──────────────────────
 *
 * The finished shell of a personal dashboard, and ONE gated state. No figure
 * appears on this tab, because there is no personal figure in this build to
 * appear: the reasons are recorded in `lib/myStatsContract.ts` (no trusted user
 * identity — `docs/identity-trust-contract.md` §6A; no record ownership —
 * `attribution.uploaded_by` fails closed, commit `bdff8f5`).
 *
 * ── The six things this tab must never do, each of which had to be designed
 *    AGAINST rather than merely avoided ─────────────────────────────────────
 *
 *   1. NO WORKSPACE TOTAL PRESENTED AS PERSONAL. This file does not import
 *      `lib/statisticsModel.ts` at all — not `deriveWorkspaceTotals`, not
 *      anything else. A relabelled workspace count is the cheapest possible
 *      false personal claim, so the import is absent rather than unused.
 *   2. NO WORKED-EXAMPLE RECORD AS A PERSONAL RECORD. Nothing here reads
 *      `/api/runtime/records`, in any scope. This tab issues NO request at all.
 *   3. NO PORTAL-WIDE METRIC. Nothing here reads a portal, a database, or any
 *      figure about other people's work.
 *   4. NO FAKE ZEROS. `MyStatsState` carries `access_pending` as a state
 *      distinct from `ready` with empty data, precisely so "0 records" is
 *      unrepresentable here. "0" would claim the reader has no activity; the
 *      truth is that this build cannot attribute activity to anyone.
 *   5. NO SKELETON LEFT BEHIND. There is no loading state on this tab, because
 *      there is nothing to load. The gate is rendered directly, so no shimmering
 *      placeholder chart can survive a resolve that never happens.
 *   6. NO HEADER-DERIVED IDENTITY. No name, no email, no uid, no group, no
 *      "signed in as". Not even as a greeting — §6A shows two of the seven
 *      candidate headers arrive carrying whatever a CLIENT chose to send.
 *      The tab does consume a current-user BOUNDARY
 *      (`lib/currentUserContract.ts`), and that boundary reads no header,
 *      issues no request, and has one implementation that answers `disabled`.
 *      It selects which personal source answers; it never supplies a value that
 *      is rendered.
 *
 * ── Why the layout is finished anyway ───────────────────────────────────────
 *
 * The section shells, the responsive grid and the per-view copy are real, so a
 * future adapter fills them without a redesign — and so a reader can see what the
 * tab is FOR rather than an apology with no shape. Each planned view states the
 * quantity it would count, its unit, the chart form it would take, and the
 * precondition it is waiting on.
 */

/** The two adapters this build wires. Both injectable so a test can prove the
 *  tab renders the state a source reports rather than a hard-coded message. */
export interface MyStatsProps {
  /** An explicit personal-statistics source. When absent, one is SELECTED from
   *  the current-user state — see the note in the component body. */
  source?: MyStatsSource;
  currentUser?: CurrentUserSource;
}

export function MyStats({ source, currentUser = disabledCurrentUserSource }: MyStatsProps) {
  /*
   * IDENTITY IS READ FIRST, AND IT SELECTS A SOURCE RATHER THAN UNLOCKING DATA.
   *
   * `personalStatisticsSourceFor` returns the unconfigured source for EVERY
   * current-user state, including `present`, because knowing who the reader is
   * would not by itself make one dataset on this tab answerable — six of the
   * eight also need per-record attribution, which fails closed by design. Wiring
   * a real current-user source therefore changes nothing here, which is the
   * intended and tested behaviour, pinned at BOTH levels:
   *
   *   · `identity alone never selects a personal source` in
   *     `current-user-contract.test.ts` sweeps the whole state union through the
   *     PURE FUNCTION. (This comment used to cite `my-stats.test.tsx`, where that
   *     test has never lived, and to imply the sweep covered the component. It
   *     covers neither this file nor the `??` selection on the next line.)
   *   · `a present current user changes nothing on this tab` in
   *     `my-stats.test.tsx` renders THIS COMPONENT with a source reporting a
   *     `present` user and asserts the same gate copy, so the wiring below is
   *     covered where it is written rather than one layer down.
   *
   * `currentUser.get()` reads no header and issues no request — see
   * `lib/currentUserContract.ts`, which is a boundary, not an identity seam.
   */
  const resolved = source ?? personalStatisticsSourceFor(currentUser.get());

  /*
   * ONE probe, through the real adapter boundary, rather than a hard-coded
   * sentence. `workflowCounts()` is the first dataset a personal dashboard would
   * answer, so the tab's headline state is whatever the configured source says
   * about it — which means wiring a real source later changes this tab's
   * behaviour instead of requiring this file to be rewritten.
   *
   * Only `access_pending` and `unavailable` have a rendering here. `ready` and
   * `loading` are deliberately NOT handled: this build's only source cannot
   * return them, and writing speculative branches for payloads no adapter
   * produces is how a placeholder chart gets shipped. The exhaustive fallback
   * below states the state's own name rather than inventing a picture for it.
   */
  const headline = resolved.workflowCounts();

  return (
    <>
      <StatsSection
        id="stats-mine-gate"
        title="Personal Statistics"
        sub="What this tab will show once records are associated with a signed-in account."
        icon={<CircleDashed size={18} strokeWidth={2} aria-hidden="true" />}
      >
        {headline.status === 'access_pending' ? (
          <ChartAccessPending title="Not Available in This Preview">
            {MY_STATS_PENDING_COPY[headline.reason]}
          </ChartAccessPending>
        ) : headline.status === 'unavailable' ? (
          <ChartAccessPending title="Not Available in This Preview">
            {headline.message}
          </ChartAccessPending>
        ) : (
          /* Reachable only if a source is wired that this build does not ship.
             It states the state it received and draws nothing, which is the only
             honest thing to do with a payload no view here knows how to read. */
          <ChartAccessPending title="Not Available in This Preview">
            {`The personal-statistics source reported "${headline.status}", and this preview has no view built for it, so nothing is shown.`}
          </ChartAccessPending>
        )}
        <p className="stats-note">
          Personal statistics will appear here once experiments are associated with your signed-in
          account. Two things are missing today, and both are properties of this preview rather than
          of your work: nothing here establishes who you are, and no record in this workspace
          carries an author, so there is no way to select the records that are yours.
        </p>
        <p className="stats-note">
          Nothing on this tab is hidden from you, and none of the figures below are zero — they are
          absent. A count of zero would say you have no records; what is true is that this build
          cannot tell whose records these are.
        </p>
        <p className="stats-actions">
          <Link to={ROUTES.settingsTab('privacy')}>Open Data &amp; Privacy Settings</Link>
          <Link to={ROUTES.statisticsTab('general')}>See Workspace Statistics</Link>
        </p>
      </StatsSection>

      <StatsSection
        id="stats-mine-planned"
        title="Views Prepared for Your Account"
        sub="Each view below is defined as a typed dataset, so it can be filled in without changing this page's layout. None of them is drawing anything right now."
      >
        <ul className="stats-plan-grid">
          {MY_STATS_VIEWS.map((view) => {
            const reason: MyStatsPendingReason = MY_STATS_PENDING_REASON[view.id];
            return (
              <li className="stats-plan-card" key={view.id}>
                <h3 className="stats-plan-title">{view.title}</h3>
                <p className="stats-plan-desc">{view.description}</p>
                <p className="stats-plan-meta">
                  {/* Composed in JS, not interpolated into JSX. `Will render as a
                      {view.form}.` renders as THREE text nodes, so any reader that
                      joins text nodes — a screen reader, a translation tool, this
                      repo's own test helpers — sees "a bar chart ." with a space
                      before the period. */}
                  <span className="stats-plan-form">{`Will render as a ${view.form}.`}</span>{' '}
                  <span className="stats-plan-gate">{`${MY_STATS_PENDING_LABEL[reason]}.`}</span>
                </p>
              </li>
            );
          })}
        </ul>
        <p className="stats-note">
          Each description names the unit it would count — records, fields, or validation issues —
          because a dashboard that blurs records into fields states a number nobody can act on. That
          is the same distinction the workspace figures keep, where evidence support is counted in
          fields beside the number of records those fields came from.
        </p>
      </StatsSection>
    </>
  );
}
