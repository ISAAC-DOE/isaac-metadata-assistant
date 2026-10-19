import './library.css';
import { useId, useRef, type KeyboardEvent } from 'react';
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
  /**
   * The id of a `LABELS.librarySearchHint` paragraph the CALLER renders. When
   * given, the toolbar renders no hint of its own and describes the search box by
   * that id instead — which is how `LibraryOverview` moves the sentence into its
   * info panel (2026-10-12 clutter audit) without the box losing its description:
   * `aria-describedby` reads a hidden element's text, so a screen-reader user still
   * hears it on focus while a sighted reader no longer meets it on every visit.
   */
  hintId?: string;
  /**
   * `false` when the caller renders the status filter itself — `LibraryOverview`
   * makes it the "What Needs Me?" widget's headline (2026-10-18 review: the spec's
   * "switcher = status filter"), so the toolbar keeps only search and sort.
   */
  showFacets?: boolean;
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
  hintId: externalHintId,
  showFacets = true,
}: LibraryToolbarProps) {
  const searchId = useId();
  const hintId = externalHintId ?? `${searchId}-hint`;
  const sortId = `${searchId}-sort`;

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
          {/* `aria-label` repeats the visible label so the select keeps its name
              at phone width, where the label leaves the row (`library.css`). */}
          <select
            id={sortId}
            aria-label={LABELS.librarySortLabel}
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

      {externalHintId === undefined && (
        <p className="library-search-hint" id={hintId}>
          {LABELS.librarySearchHint}
        </p>
      )}

      {showFacets && <LibraryFacets facet={facet} onFacet={onFacet} counts={counts} />}
    </div>
  );
}

/** The facets in reading order for the status filter: the states that need a
 *  reader first, the whole list last. Same set and same counts as `LIBRARY_FACETS`. */
const FACET_ORDER: LibraryFacetId[] = ['needsAttention', 'proposals', 'inReview', 'ready', 'draft', 'done', 'all'];

/**
 * THE STATUS FILTER — the library's radiogroup of facets, each carrying its count
 * over the WHOLE list (see the three load-bearing rules on `LibraryToolbar`).
 * Exported so `LibraryOverview` can make it the widget's headline: the counts a
 * reader comes for ARE the filter, so they are stated once, as the control.
 */
export function LibraryFacets({
  facet,
  onFacet,
  counts,
  variant = 'chips',
}: {
  facet: LibraryFacetId;
  onFacet: (next: LibraryFacetId) => void;
  counts: Record<LibraryFacetId, number>;
  /** `tiles`: the figure-first headline treatment `LibraryOverview` uses. */
  variant?: 'chips' | 'tiles';
}) {
  const visibleFacets = FACET_ORDER.map((id) => LIBRARY_FACETS.find((f) => f.id === id)!).filter(
    (f) => counts[f.id] > 0 || f.id === facet,
  );
  const groupRef = useRef<HTMLDivElement | null>(null);
  /*
   * ONE TAB STOP, ARROW KEYS WITHIN (APG radio group; review, 2026-10-18). Only
   * the checked radio is in the tab sequence; Left/Up and Right/Down move to the
   * previous / next radio and select it, wrapping at the ends; Home / End reach
   * the first / last. Selecting as focus moves is what a radio group does — the
   * filter applies immediately, exactly as a click does.
   */
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const step: Record<string, number | 'first' | 'last'> = {
      ArrowRight: 1,
      ArrowDown: 1,
      ArrowLeft: -1,
      ArrowUp: -1,
      Home: 'first',
      End: 'last',
    };
    const move = step[e.key];
    if (move === undefined || visibleFacets.length === 0) return;
    e.preventDefault();
    // Relative to the radio that has focus (the event's own target), falling back
    // to the checked one — they coincide in normal use, since only the checked
    // radio is tabbable, but a pointer press can focus a radio first.
    const fromId = (e.target as HTMLElement).closest<HTMLElement>('[data-facet]')?.dataset.facet;
    const current = Math.max(
      0,
      visibleFacets.findIndex((f) => f.id === (fromId ?? facet)),
    );
    const n = visibleFacets.length;
    const nextIndex =
      move === 'first' ? 0 : move === 'last' ? n - 1 : (current + move + n) % n;
    const next = visibleFacets[nextIndex];
    onFacet(next.id);
    groupRef.current
      ?.querySelector<HTMLButtonElement>(`[data-facet="${next.id}"]`)
      ?.focus();
  };
  return (
    <>
      {/*
        `role="radiogroup"`, and the label is on the GROUP rather than implied by
        a heading: exactly one of these applies, and a reader arriving by keyboard
        needs to be told that before they start pressing.
      */}
      <div
        ref={groupRef}
        className={`library-facets${variant === 'tiles' ? ' library-facets-tiles' : ''}`}
        role="radiogroup"
        aria-label="Filter these experiments"
        onKeyDown={onKeyDown}
      >
        {variant === 'chips' && (
          <SlidersHorizontal
            className="library-facets-icon"
            size={14}
            strokeWidth={2}
            aria-hidden="true"
          />
        )}
        {visibleFacets.map((f) => (
          <button
            key={f.id}
            type="button"
            role="radio"
            data-facet={f.id}
            aria-checked={f.id === facet}
            tabIndex={f.id === facet ? 0 : -1}
            /*
              THE COUNT SAYS WHICH SET IT COUNTS, to a screen reader. Visually the
              chip's own label supplies that context; read aloud, "Needs Attention
              3" could be a count of anything, and this count in particular is
              deliberately NOT the number of rows currently on screen.

              ONE STRING, not a label span joined to an `.sr-only` ", N of all
              experiments" span (review, 2026-10-18): the two are flex items, and
              Chromium separates flex items with a space when it builds a name,
              so the name read "Needs Attention , 5 of all experiments". The name
              still begins with the visible label (WCAG 2.5.3).
            */
            aria-label={`${f.label}, ${counts[f.id]} of all experiments`}
            className={`library-facet${f.id === facet ? ' is-selected' : ''}`}
            onClick={() => onFacet(f.id)}
          >
            <span className="library-facet-label">{f.label}</span>
            <span className="library-facet-count" aria-hidden="true">
              {counts[f.id]}
            </span>
          </button>
        ))}
      </div>
    </>
  );
}
