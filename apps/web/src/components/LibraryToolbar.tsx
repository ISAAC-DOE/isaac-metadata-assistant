import './library.css';
import { useId } from 'react';
import { Search, SlidersHorizontal, X } from './icons';
import { LABELS } from '../lib/labels';
import {
  LIBRARY_FACETS,
  LIBRARY_SORTS,
  type LibraryFacetId,
  type LibrarySortId,
} from '../lib/library';

interface LibraryToolbarProps {
  query: string;
  onQuery: (next: string) => void;
  facet: LibraryFacetId;
  onFacet: (next: LibraryFacetId) => void;
  sort: LibrarySortId;
  onSort: (next: LibrarySortId) => void;
  /** One count per facet, over the WHOLE list. See `facetCounts`. */
  counts: Record<LibraryFacetId, number>;
}

/**
 * SEARCH, FILTER AND SORT FOR THE EXPERIMENT LIBRARY.
 *
 * THREE THINGS ABOUT THE CHIPS ARE LOAD-BEARING RATHER THAN STYLISTIC.
 *
 * 1. A CHIP IS ONLY RENDERED WHEN IT WOULD MATCH SOMETHING. A filter that leads
 *    to an empty list is not a filter, it is a dead end a reader has to discover
 *    by pressing it — and on this screen it is worse than that: a chip reading
 *    `Ready to Export 0` invites the conclusion that nothing is ready, when the
 *    honest reading is that this workspace has no such records. The one exception
 *    is the chip that is CURRENTLY SELECTED, which stays rendered even at zero,
 *    because removing the control a reader is standing on would leave them unable
 *    to get back.
 *
 * 2. THE COUNTS ARE OVER THE WHOLE LIST, NEVER OVER THE FILTERED ROWS. That is
 *    `facetCounts`' contract and it is the reason the chips are usable: a number
 *    that shrank as you typed would be answering a question you had not asked.
 *    The count of what is ON SCREEN is stated separately, beside the results,
 *    where it describes the thing it is a count of.
 *
 * 3. THEY ARE `radio`, NOT `checkbox` OR `tab`. Exactly one facet applies at a
 *    time, which is what a radio group means; `checkbox` would promise
 *    multi-select and `tab` would promise that each chip owns a panel. The
 *    keyboard behaviour a reader gets from the platform is then correct without
 *    this component implementing arrow-key handling of its own.
 *
 * THE SEARCH BOX NAMES WHAT IT SEARCHES. `librarySearchPlaceholder` lists the
 * five fields `matchesQuery` actually reads, and a test pins the two against each
 * other — a box that silently searched more than it admitted would return rows
 * whose relevance a reader cannot see.
 */
export function LibraryToolbar({
  query,
  onQuery,
  facet,
  onFacet,
  sort,
  onSort,
  counts,
}: LibraryToolbarProps) {
  const searchId = useId();
  const hintId = `${searchId}-hint`;
  const sortId = `${searchId}-sort`;

  const visibleFacets = LIBRARY_FACETS.filter(
    (f) => counts[f.id] > 0 || f.id === facet,
  );

  return (
    <div className="library-toolbar">
      <div className="library-toolbar-row">
        <div className="library-search">
          <label className="sr-only" htmlFor={searchId}>
            {LABELS.librarySearchLabel}
          </label>
          <Search className="library-search-icon" size={16} strokeWidth={2} aria-hidden="true" />
          <input
            id={searchId}
            className="library-search-input"
            type="search"
            value={query}
            placeholder={LABELS.librarySearchPlaceholder}
            aria-describedby={hintId}
            onChange={(e) => onQuery(e.target.value)}
          />
          {/*
            THE CLEAR CONTROL IS ONLY RENDERED WHEN THERE IS SOMETHING TO CLEAR.
            A permanently visible × over an empty box is a control that does
            nothing, which is the failure mode this screen's own history records
            two other controls being removed for.
          */}
          {query !== '' && (
            <button
              type="button"
              className="library-search-clear"
              aria-label="Clear the search"
              onClick={() => onQuery('')}
            >
              <X size={14} strokeWidth={2.25} aria-hidden="true" />
            </button>
          )}
        </div>

        <div className="library-sort">
          <label className="library-sort-label" htmlFor={sortId}>
            {LABELS.librarySortLabel}
          </label>
          <select
            id={sortId}
            className="library-sort-select"
            value={sort}
            onChange={(e) => onSort(e.target.value as LibrarySortId)}
          >
            {LIBRARY_SORTS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <p className="library-search-hint" id={hintId}>
        {LABELS.librarySearchHint}
      </p>

      {/*
        `role="radiogroup"`, and the label is on the GROUP rather than implied by
        a heading: exactly one of these applies, and a reader arriving by keyboard
        needs to be told that before they start pressing.
      */}
      <div
        className="library-facets"
        role="radiogroup"
        aria-label="Filter these experiments"
      >
        <SlidersHorizontal
          className="library-facets-icon"
          size={14}
          strokeWidth={2}
          aria-hidden="true"
        />
        {visibleFacets.map((f) => (
          <button
            key={f.id}
            type="button"
            role="radio"
            aria-checked={f.id === facet}
            className={`library-facet${f.id === facet ? ' is-selected' : ''}`}
            onClick={() => onFacet(f.id)}
          >
            <span className="library-facet-label">{f.label}</span>
            {/*
              THE COUNT SAYS WHICH SET IT COUNTS, to a screen reader. Visually the
              chip's own label supplies that context; read aloud, "Needs Attention
              3" could be a count of anything, and this count in particular is
              deliberately NOT the number of rows currently on screen.
            */}
            <span className="library-facet-count" aria-hidden="true">
              {counts[f.id]}
            </span>
            <span className="sr-only">
              , {counts[f.id]} of all experiments
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
