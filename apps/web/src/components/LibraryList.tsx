import './queue.css';
import './library.css';
import { ExperimentRow } from './ExperimentRow';
import { LABELS } from '../lib/labels';
import { TUTORIAL_ANCHORS } from '../lib/tutorialSteps';
import type { ExperimentSummary } from '../lib/types';

interface LibraryListProps {
  rows: ExperimentSummary[];
}

/**
 * THE FLAT RESULT LIST — used when a facet or a search has narrowed the Library.
 *
 * IT CARRIES `TUTORIAL_ANCHORS.experimentsQueue`, and that is a correctness
 * requirement rather than a copy-paste. The guided walkthrough resolves that
 * anchor to describe "what this list holds", and its steps are authored against
 * an anchor rather than a component — so a second way of rendering the same list
 * that omitted it would leave the walkthrough pointing at nothing on a screen
 * that visibly has a list on it. Each row carries `experimentRow` for the same
 * reason, and the walkthrough resolves the FIRST in document order deliberately:
 * that step describes what a row IS, not one particular record.
 *
 * IT REUSES `ExperimentRow` RATHER THAN RE-RENDERING A ROW. The row owns the
 * accessible name that tells two identically-titled records apart, the
 * lifecycle chip, the date choice and the metadata line; a second implementation
 * of any of those would drift from the grouped view, and the two are on screen
 * within one keystroke of each other.
 */
export function LibraryList({ rows }: LibraryListProps) {
  return (
    <div className="queue" data-tutorial-anchor={TUTORIAL_ANCHORS.experimentsQueue}>
      <div className="queue-rows">
        {rows.map((exp) => (
          <ExperimentRow exp={exp} key={exp.id} />
        ))}
      </div>
    </div>
  );
}

/**
 * NO ROWS MATCH THE CURRENT VIEW — which is a different screen from an empty
 * workspace, and the difference is the whole reason this component exists.
 *
 * `EmptyExperiments` says "start your first experiment". Rendering that in front
 * of somebody who has forty records and typed a word matching none of them would
 * be the worst false claim this screen could make. So the copy here says the
 * opposite thing explicitly — nothing is hidden or lost, the filters are
 * narrowing — and offers the one action that resolves it.
 *
 * THE CLEAR CONTROL RESETS THE FACET AND THE QUERY AND DELIBERATELY NOT THE
 * FOLDER. A reader who browsed into a folder chose to be there; throwing them
 * back to the root would undo a navigation they did not ask to undo. The
 * breadcrumb above is how they leave.
 */
export function LibraryNoResults({ onClear }: { onClear: () => void }) {
  return (
    <section className="library-no-results" aria-labelledby="library-no-results-title">
      <h2 className="library-no-results-title" id="library-no-results-title">
        {LABELS.libraryNoResultsTitle}
      </h2>
      <p className="library-no-results-body">{LABELS.libraryNoResultsBody}</p>
      <button type="button" className="btn btn-secondary" onClick={onClear}>
        {LABELS.libraryClearFilters}
      </button>
    </section>
  );
}
