import './library.css';
import { LABELS } from '../lib/labels';
import type { LibraryOverviewStats } from '../lib/library';

interface LibraryOverviewProps {
  stats: LibraryOverviewStats;
  /** `true` when `GET /api/experiments` declared the list `incomplete`.
   *  Scopes the heading and the note; see the note in the component. */
  readIncomplete?: boolean;
}

/**
 * UX-017's LIBRARY HALF — a compact "Workspace Statistics" strip.
 *
 * NOT `StatCard`/`StatsSection` FROM `screens/statistics/StatsPrimitives.tsx`,
 * and that is a measured constraint rather than a style choice: every one of
 * those primitives' rules (`.statistics .stat-card`, `.statistics
 * .stats-figure`, …) is scoped under an ancestor `.statistics` class in
 * `statistics.css`. Reusing the components without that ancestor would render
 * unstyled markup; wrapping this screen's own root in a `className="statistics"`
 * to borrow it would be importing another screen's identity rather than its
 * styling. So this is a small, independent presentation, in `library.css`,
 * following the SAME accessible shape (`<dl>` of labelled figures) rather than
 * the same component.
 *
 * FOUR FIGURES, DELIBERATELY FEW. `LibraryToolbar`'s facet chips already show
 * the workflow-status breakdown (Needs Attention / In Review / Ready / Draft /
 * Done) as interactive filters with their own counts — repeating all of that
 * here as static figures would be the same numbers said twice in one screen,
 * which is exactly the density this screen's sibling nav slot was demoted for
 * (`89d9f07c`: "3,820 px, 422 visible text elements"). What is shown here is
 * either a plain total (`Experiments`, `Needs Attention` — the two figures a
 * returning scientist reads a Library FOR) or a genuine aggregate the chips do
 * not state at all: `Runs Recorded` and `Proposals Waiting` are SUMS across
 * every experiment, not counts of records matching a predicate. See
 * `lib/library.ts::libraryOverviewStats` for exactly what each counts.
 */
export function LibraryOverview({ stats, readIncomplete = false }: LibraryOverviewProps) {
  /*
   * B-2 — WHEN THE READ WAS SHORT, THESE ARE NOT WORKSPACE TOTALS, AND THE STRIP
   * SAYS SO ITSELF. `libraryOverviewStats` computes from the list this read
   * returned; `GET /api/experiments` may declare that list `incomplete`, and its own
   * response description says to "treat a short list as evidence about this read,
   * never as an inventory". Publishing four figures under "Workspace Statistics" in
   * that state is a completeness claim the data does not support.
   *
   * The screen's `IncompleteListNote` (role="alert") already renders above this, so
   * a caveat is on screen — but it speaks about "the list", not about these totals.
   * Scoping the heading AND the note is what connects the two for a reader who is
   * looking at the numbers rather than at the alert.
   */
  return (
    <section className="library-overview" aria-labelledby="library-overview-heading">
      <h2 className="library-overview-heading" id="library-overview-heading">
        {readIncomplete ? LABELS.libraryOverviewHeadingPartial : LABELS.libraryOverviewHeading}
      </h2>
      <dl className="library-overview-grid">
        <div className="library-overview-item">
          <dt className="library-overview-label">{LABELS.libraryOverviewTotal}</dt>
          <dd className="library-overview-value mono">{stats.total}</dd>
        </div>
        <div className="library-overview-item" data-tone={stats.needsAttention > 0 ? 'attention' : undefined}>
          <dt className="library-overview-label">{LABELS.libraryOverviewNeedsAttention}</dt>
          <dd className="library-overview-value mono">{stats.needsAttention}</dd>
        </div>
        <div className="library-overview-item">
          <dt className="library-overview-label">{LABELS.libraryOverviewRuns}</dt>
          <dd className="library-overview-value mono">{stats.totalRuns}</dd>
        </div>
        <div className="library-overview-item">
          <dt className="library-overview-label">{LABELS.libraryOverviewProposals}</dt>
          <dd className="library-overview-value mono">{stats.openProposals}</dd>
        </div>
      </dl>
      <p className="library-overview-note">{readIncomplete ? LABELS.libraryOverviewNotePartial : LABELS.libraryOverviewNote}</p>
    </section>
  );
}
