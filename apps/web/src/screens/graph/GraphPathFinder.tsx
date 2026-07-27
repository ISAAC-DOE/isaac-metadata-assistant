/*
 * P36V PR2 slice B — Find a Path, as its own focused tool.
 *
 * It used to be a bare `<form>` sitting permanently above the canvas, and — for
 * no reason anyone could defend — the surface's only `Clear filters` button was
 * parked inside it. Path finding is now a named disclosure of its own, and
 * clearing filters belongs to the filter chips where it always should have.
 *
 * BEHAVIOUR IS UNCHANGED. Submitting dispatches the same
 * `{ kind: 'path', from, to }` action to the same reducer, which resolves both
 * tokens through `resolveNode` — exact, then basename, then prefix, then
 * substring — and refuses rather than guesses: an unknown token yields
 * `not_found`, a token matching several nodes yields a bounded candidate list,
 * and two unconnected nodes yield `no_path`. Those outcomes are announced in the
 * surface's ONE polite live region; this component adds no second one.
 */
import { ChevronDown, ChevronRight } from '../../components/icons';
import type { GraphAction, GraphViewState } from '../../lib/graphModel';

interface GraphPathFinderProps {
  id: string;
  state: GraphViewState;
  dispatch: (action: GraphAction) => void;
  from: string;
  to: string;
  onFrom: (value: string) => void;
  onTo: (value: string) => void;
}

export function GraphPathFinder({
  id,
  state,
  dispatch,
  from,
  to,
  onFrom,
  onTo,
}: GraphPathFinderProps) {
  const hasPath = state.focus?.kind === 'path';
  const canClear = hasPath || from !== '' || to !== '';
  return (
    <form
      className="memory-graph-pathform"
      id={id}
      onSubmit={(e) => {
        e.preventDefault();
        dispatch({ kind: 'path', from, to });
      }}
    >
      <label className="memory-graph-pathfield">
        <span>From</span>
        <input
          type="text"
          value={from}
          placeholder="file path or concept"
          onChange={(e) => onFrom(e.target.value)}
        />
      </label>
      <label className="memory-graph-pathfield">
        <span>To</span>
        <input
          type="text"
          value={to}
          placeholder="file path or concept"
          onChange={(e) => onTo(e.target.value)}
        />
      </label>
      <button type="submit" className="btn btn-secondary">
        Find Path
      </button>
      {canClear && (
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => {
            onFrom('');
            onTo('');
            if (hasPath) dispatch({ kind: 'clearFocus' });
          }}
        >
          Clear Path
        </button>
      )}
      <p className="memory-graph-pathnote">
        The shortest route through recorded references. A name that matches nothing, or matches
        several nodes, is reported — never guessed at.
      </p>
    </form>
  );
}

/** The disclosure trigger for the tool above. */
export function GraphPathToggle({
  id,
  open,
  onToggle,
}: {
  id: string;
  open: boolean;
  onToggle: () => void;
}) {
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <button
      type="button"
      className="memory-graph-disclosure-btn"
      aria-expanded={open}
      /* Only while the region EXISTS: it is unmounted when closed, and an
         aria-controls pointing at a missing id is a broken reference. */
      aria-controls={open ? id : undefined}
      onClick={onToggle}
    >
      <Chevron size={13} strokeWidth={2} aria-hidden="true" />
      Find a Path
    </button>
  );
}
