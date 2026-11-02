import './library.css';
import type { ReactNode } from 'react';
import { LABELS } from '../lib/labels';
import type { LibraryOverviewStats } from '../lib/library';

interface LibraryOverviewProps {
  stats: LibraryOverviewStats;
  /** `true` when `GET /api/experiments` declared the list `incomplete`.
   *  Scopes the figures with one visible line; see the note in the component. */
  readIncomplete?: boolean;
  /**
   * `false` while browsing INSIDE a folder. The sums are workspace totals, and
   * stated under a folder's contents they would read as describing that folder —
   * so the bar keeps its filter and search there and drops the sums.
   */
  showTotals?: boolean;
  /** The id the search box is described by. The hint is rendered here, for
   *  assistive technology only. */
  searchHintId: string;
  /** The status filter (`LibraryFacets`), first on the row. */
  facets: ReactNode;
  /** The library toolbar — search and sort, on the same row. */
  children: ReactNode;
}

/**
 * THE LIBRARY BAR — one quiet row: the status filter, then search and sort.
 *
 * 2026-11-02 (owner direction, "less text, fewer equal-weight things"): this was
 * the "What Needs Me?" card — a heading, an info tip, six figure tiles, a line of
 * sums and the toolbar, all inside a card frame, above a list whose group headers
 * restated the same counts. It is now the filter chips on the same line as search
 * and sort, with no heading, no info tip and no frame.
 *
 * WHAT STAYS, AND WHY.
 * - The chips are still the radiogroup `LibraryToolbar` documents (counts over the
 *   whole list, only rendered when they would match something).
 * - `Runs Recorded` and `Proposals Waiting` are SUMS that no chip states
 *   (`lib/library.ts::libraryOverviewStats`), so they stay — but only when they are
 *   above zero. "0 Runs Recorded" on a fresh workspace says nothing a reader can use.
 * - B-2: when the server declares the read SHORT, the sums are not workspace totals,
 *   and one visible line says so beside them. That is a qualifier of a figure, so it
 *   is shown rather than tucked away.
 * - The search box keeps its description ("Searches every folder…") through
 *   `aria-describedby`; the sentence is for assistive technology, since a sighted
 *   reader sees results from every folder in the list itself.
 */
export function LibraryOverview({
  stats,
  readIncomplete = false,
  showTotals = true,
  searchHintId,
  facets,
  children,
}: LibraryOverviewProps) {
  const sums: Array<[string, number]> = showTotals
    ? (
        [
          [LABELS.libraryOverviewRuns, stats.totalRuns],
          [LABELS.libraryOverviewProposals, stats.openProposals],
        ] as Array<[string, number]>
      ).filter(([, value]) => value > 0)
    : [];

  return (
    <div className={`library-overview${showTotals ? '' : ' library-find'}`}>
      <div className="library-bar">
        <div className="library-bar-filters">
          {facets}
          {sums.length > 0 && (
            <dl className="library-overview-grid">
              {sums.map(([label, value]) => (
                <div className="library-overview-item" key={label}>
                  <dt className="library-overview-label">{label}</dt>
                  <dd className="library-overview-value">{value}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
        {children}
      </div>
      <p className="sr-only" id={searchHintId}>
        {LABELS.librarySearchHint}
      </p>
      {showTotals && readIncomplete && (
        <p className="library-overview-note library-overview-note-partial">
          {LABELS.libraryOverviewNotePartial}
        </p>
      )}
    </div>
  );
}
