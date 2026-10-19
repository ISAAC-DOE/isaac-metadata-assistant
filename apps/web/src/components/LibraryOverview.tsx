import './library.css';
import type { ReactNode } from 'react';
import { Widget } from './Widget';
import { LABELS } from '../lib/labels';
import type { LibraryOverviewStats } from '../lib/library';

interface LibraryOverviewProps {
  stats: LibraryOverviewStats;
  /** `true` when `GET /api/experiments` declared the list `incomplete`.
   *  Scopes the heading and the note; see the note in the component. */
  readIncomplete?: boolean;
  /**
   * `false` while browsing INSIDE a folder. The figures are workspace totals, and
   * stated under a folder's contents they would read as describing that folder —
   * so the widget keeps its filter and search there and drops the figures.
   */
  showTotals?: boolean;
  /** The id the search box is described by; the hint paragraph lives in the
   *  widget's info panel and carries it. */
  searchHintId: string;
  /** The status filter (`LibraryFacets`), rendered as the headline. */
  facets: ReactNode;
  /** The library toolbar — search and sort. */
  children: ReactNode;
}

/**
 * "WHAT NEEDS ME?" — ONE WIDGET FOR THE LIBRARY'S QUESTION (2026-10-12 clutter
 * audit, owner direction: one widget per question, with the controls that change
 * the view INSIDE it).
 *
 * WHAT IT REPLACED. My Experiments stacked a "Workspace Statistics" card (four
 * figures and a two-line note), then the search box, a hint line under it, and a
 * row of filter chips — two blocks answering one question, with "5" printed three
 * times and "3 need attention" twice before the first row. Measured at 1510px the
 * first row sat at y≈658. This is that card and that toolbar as ONE widget: the
 * headline is the count that answers the question, the two genuine aggregates sit
 * beside it, and the status filter, search and sort are the widget's own body.
 *
 * WHAT MOVED, AND WHERE. `libraryOverviewNote` ("Counts over the records in this
 * workspace. Summary figures only…") and `librarySearchHint` ("Searches every
 * folder…") moved into the widget's info panel. Both are WHY/WHERE-FROM prose, not
 * qualifiers of the headline: they stay in the DOM (`Widget` renders the info
 * panel hidden), the search box is still described by the hint through
 * `aria-describedby`, and the claim-scanning guards read them where they always
 * did.
 *
 * WHAT DID NOT MOVE, AND WHY. When the server declares the read SHORT, the scoped
 * note is a qualifier that must be read BEFORE the figures — `Widget`'s `lead`
 * slot, visible. A caveat hidden behind an info toggle would leave three figures
 * reading as an inventory the data does not support (B-2).
 *
 * `Experiments` (the total) IS NO LONGER RESTATED HERE. The page header's
 * subcount ("5 experiments · 1 ready to export") and the `All Experiments` filter
 * chip already state it; a third copy was the repetition the audit measured.
 * `Runs Recorded` and `Proposals Waiting` stay because they are SUMS that no chip
 * states — see `lib/library.ts::libraryOverviewStats`.
 *
 * NOT `StatCard`/`StatsSection` FROM `screens/statistics/StatsPrimitives.tsx`:
 * those rules are scoped under an ancestor `.statistics`. The shared `Widget`
 * primitive is what both surfaces now build on.
 */
export function LibraryOverview({
  stats,
  readIncomplete = false,
  showTotals = true,
  searchHintId,
  facets,
  children,
}: LibraryOverviewProps) {
  /*
   * B-2 — WHEN THE READ WAS SHORT, THESE ARE NOT WORKSPACE TOTALS, AND THE WIDGET
   * SAYS SO ITSELF. `libraryOverviewStats` computes from the list this read
   * returned; `GET /api/experiments` may declare that list `incomplete`, and its own
   * response description says to "treat a short list as evidence about this read,
   * never as an inventory". Scoping the heading AND the note is what connects the
   * screen's `IncompleteListNote` alert to these figures for a reader who is
   * looking at the numbers rather than at the alert.
   *
   * INSIDE A FOLDER the widget is titled for what it still does there — find an
   * experiment — because the question it answers at the root ("what needs me?")
   * is a workspace question its figures can no longer state.
   */
  const title = !showTotals
    ? LABELS.libraryFindHeading
    : readIncomplete
      ? LABELS.libraryOverviewHeadingPartial
      : LABELS.libraryOverviewHeading;

  return (
    <Widget
      id="library-overview-heading"
      className={showTotals ? 'library-overview' : 'library-find'}
      title={title}
      infoLabel={showTotals ? LABELS.libraryOverviewInfoLabel : LABELS.libraryFindInfoLabel}
      info={
        <>
          {showTotals && !readIncomplete && (
            <p className="library-overview-note">{LABELS.libraryOverviewNote}</p>
          )}
          <p className="library-search-hint" id={searchHintId}>
            {LABELS.librarySearchHint}
          </p>
        </>
      }
      lead={
        showTotals && readIncomplete ? (
          <p className="library-overview-note library-overview-note-partial">
            {LABELS.libraryOverviewNotePartial}
          </p>
        ) : undefined
      }
      headline={
        <div className="library-overview-headline">
          {/* THE STATUS FILTER IS THE HEADLINE (review, 2026-10-18; the spec's
              "switcher = status filter"). The counts a reader comes for — how many
              need attention, are ready, are drafts, are done — ARE the filter, so
              they are stated once, as the control, instead of once as figures and
              again as a chip row underneath. */}
          {facets}
          {showTotals && (
            <dl className="library-overview-grid">
              <div className="library-overview-item">
                <dt className="library-overview-label">{LABELS.libraryOverviewRuns}</dt>
                <dd className="library-overview-value">{stats.totalRuns}</dd>
              </div>
              <div className="library-overview-item">
                <dt className="library-overview-label">{LABELS.libraryOverviewProposals}</dt>
                <dd className="library-overview-value">{stats.openProposals}</dd>
              </div>
            </dl>
          )}
        </div>
      }
    >
      {children}
    </Widget>
  );
}
