/*
 * P36V PR2 slice B — the graph's filter disclosure and its active-filter chips.
 *
 * WHY this file exists: every filter control used to sit permanently open above
 * the canvas — a node-type select, a cluster search box, a cluster select, one
 * checkbox per relationship type and a Browse-only grouping select, plus three
 * explanatory notes. Thirteen controls and seven prose blocks stood between the
 * card heading and the graph. The controls are all still here, unchanged: they
 * moved behind ONE disclosure, with a chip row that says what is currently
 * narrowing the view even while the panel is shut.
 *
 * THE CHIP ROW'S CONTRACT: every chip names something the view is WITHHOLDING,
 * and every X widens the visible set. The count on the Filters trigger is the
 * same number as the count of non-search chips, by construction — see
 * `hiddenFilterCount` and `hiddenRelationTypes`.
 *
 * WHAT DID NOT CHANGE: filter SEMANTICS. Every control dispatches exactly the
 * `GraphAction` it dispatched before — `filterType`, `filterCommunity`,
 * `filterRelation` — through the same reducer, so the same inputs produce the
 * same visible node and edge sets. `relationToggleAction` is the old inline
 * checkbox handler lifted verbatim so the checkbox and its chip cannot drift.
 *
 * HUMANISATION BOUNDARY: relationship values are relabelled through the closed,
 * measured five-value map in `lib/displayLabels.ts`. Cluster names are NOT —
 * they are arbitrary upstream data (`SHE_work_function_eV`, `test_export.py`,
 * `record_id`), and a snake_case → Title Case rule over them would fabricate
 * readings like "She Work Function Ev". They render verbatim, with the raw
 * identifier in `title`.
 */
import { useEffect, useRef, type Ref } from 'react';
import { ChevronDown, ChevronRight, X } from '../../components/icons';
import { relationDisplayLabel } from '../../lib/displayLabels';
import {
  communityLabelAmong,
  communityOptionLabel,
  type GraphAction,
  type GraphCommunityEntry,
  type GraphIndex,
  type GraphTypeFilter,
  type GraphViewState,
} from '../../lib/graphModel';
import type { BrowseGrouping } from './GraphBrowse';

/**
 * The relationship-filter action for ticking/unticking ONE type.
 *
 * Lifted verbatim out of the old inline checkbox `onChange`, so the checkbox and
 * the chip's remove button are the same operation rather than two copies of it.
 * Everything ticked is "no filter" (`null`); anything less is the exact set —
 * including the empty set, which honestly draws no references at all.
 */
export function relationToggleAction(
  rel: string,
  state: GraphViewState,
  index: GraphIndex,
): GraphAction {
  const current = state.relationFilter ?? [...index.relationTypes];
  const next = current.includes(rel) ? current.filter((r) => r !== rel) : [...current, rel];
  return {
    kind: 'filterRelation',
    relations: next.length === index.relationTypes.length ? null : next,
  };
}

export interface ActiveFilterChip {
  key: string;
  /** Human-readable label. Ours is Title Case; graph-derived text is verbatim. */
  label: string;
  /** The exact underlying value, exposed as `title` — never replaced by the label. */
  raw: string | null;
  /** Accessible name of the chip's remove control. */
  removeLabel: string;
  /** The action that removes JUST this filter. */
  action: GraphAction;
}

/**
 * The relationship types currently WITHHELD — the projection's vocabulary minus
 * whatever is still ticked. `null` is "no relationship filter at all", so
 * nothing is hidden.
 *
 * Derived against `index.relationTypes` (the payload's own sorted order) rather
 * than read off `state.relationFilter`, because `relationFilter` names the set
 * that is still SHOWN. Everything a reader needs to be told about — and every
 * chip — concerns the complement.
 *
 * Note this is honest about a full-set filter too: `relation calls imports
 * imports_from references shares_data_with` leaves `relationFilter` non-null but
 * hides nothing, and this returns `[]` for it.
 */
export function hiddenRelationTypes(state: GraphViewState, index: GraphIndex): string[] {
  const shown = state.relationFilter;
  if (shown === null) return [];
  const kept = new Set(shown);
  return index.relationTypes.filter((rel) => !kept.has(rel));
}

/** Whether the relationship filter names NO type at all — every reference is
 *  withheld, so the canvas honestly draws none. Worth stating in words: a column
 *  of "Hiding: …" chips only adds up to "nothing is drawn" for a reader who
 *  already knows how many members the vocabulary has. */
export function noRelationshipsShown(state: GraphViewState, index: GraphIndex): boolean {
  return index.relationTypes.length > 0 && state.relationFilter?.length === 0;
}

/**
 * How many filters are active BEHIND the disclosure — the number the Filters
 * button reports. Search is deliberately excluded: its box stays permanently
 * visible in the primary toolbar, so counting it would report a filter as
 * hidden when it is not.
 *
 * Each WITHHELD relationship type counts as one, so this number and the chip row
 * can never disagree — the row draws exactly one chip per withheld type. Counting
 * the relationship filter as a single unit (its previous behaviour) meant a
 * five-value payload with four types unticked reported "1 active" beside four
 * chips. A full-set filter hides nothing and is therefore counted as nothing.
 */
export function hiddenFilterCount(state: GraphViewState, index: GraphIndex): number {
  return (
    (state.typeFilter !== 'all' ? 1 : 0) +
    (state.communityFilter !== 'all' ? 1 : 0) +
    hiddenRelationTypes(state, index).length
  );
}

const TYPE_CHIP_LABEL: Record<Exclude<GraphTypeFilter, 'all'>, string> = {
  file: 'Files Only',
  concept: 'Concepts Only',
};

/**
 * Every filter currently narrowing the view, as removable chips.
 *
 * THE ROW DESCRIBES WHAT IS WITHHELD, AND EVERY X WIDENS. That is the whole
 * contract: a chip names something the view is not showing, and its remove
 * control puts it back. `Clear All Filters` beside it widens the most of all.
 *
 * Search IS included here even though its box is visible, because `Clear All
 * Filters` clears it — a chip row that omitted it would let one control clear
 * something the row never admitted was on.
 */
export function activeFilterChips(
  state: GraphViewState,
  index: GraphIndex,
): ActiveFilterChip[] {
  const chips: ActiveFilterChip[] = [];

  if (state.search.trim() !== '') {
    chips.push({
      key: 'search',
      label: `Search: ${state.search}`,
      raw: state.search,
      removeLabel: 'Clear the search filter',
      action: { kind: 'search', query: '' },
    });
  }

  if (state.typeFilter !== 'all') {
    chips.push({
      key: 'type',
      label: TYPE_CHIP_LABEL[state.typeFilter],
      raw: state.typeFilter,
      removeLabel: 'Clear the node type filter',
      action: { kind: 'filterType', value: 'all' },
    });
  }

  if (state.communityFilter !== 'all') {
    const entry = index.communityById.get(state.communityFilter);
    // The cluster's own name, verbatim, plus the disambiguating id when another
    // cluster shares that name. Never renamed, never re-cased.
    const shown = entry
      ? communityLabelAmong(entry, index.communitiesBySize)
      : `cluster ${state.communityFilter}`;
    chips.push({
      key: 'community',
      label: `Cluster: ${shown}`,
      raw: state.communityFilter,
      removeLabel: 'Clear the cluster filter',
      action: { kind: 'filterCommunity', id: 'all' },
    });
  }

  /*
   * ONE chip per WITHHELD relationship type.
   *
   * This used to iterate `state.relationFilter` — the set still SHOWN — which
   * inverted the row's meaning wherever the payload carries more than two
   * relation values. Against the real projection (references 389 · imports 382 ·
   * calls 160 · imports_from 69 · shares_data_with 2), unticking "Calls" alone
   * drew FOUR chips — Imports, Imports From, References, Shares Data With — none
   * of them filtering anything, no chip at all for the one type actually hidden,
   * and each X labelled "Remove the Imports relationship filter" while actually
   * removing 382 more edges from the view. Every sibling control in this row
   * widens; those X's narrowed.
   *
   * The action is `relationToggleAction`, unchanged and shared with the checkbox,
   * so the chip's X and the tick are the same operation: on a hidden type it
   * re-ticks, and re-ticking the last hidden one collapses the filter back to
   * `null`.
   */
  for (const rel of hiddenRelationTypes(state, index)) {
    const shown = relationDisplayLabel(rel);
    chips.push({
      key: `relation-${rel}`,
      label: `Hiding: ${shown}`,
      raw: rel,
      removeLabel: `Show ${shown} references again`,
      action: relationToggleAction(rel, state, index),
    });
  }

  return chips;
}

/** The chip row + the single `Clear All Filters` control. Rendered only when at
 *  least one filter is on, so it never occupies space it has nothing to say in.
 *
 *  FOCUS IS MOVED DELIBERATELY. Every control in this row can unmount its own
 *  subtree: the last chip's X empties the row, and `Clear All Filters` removes
 *  the row it is standing in. A browser then falls back to `<body>`, dumping a
 *  keyboard user at the top of the document — a regression the previous
 *  unconditionally-mounted "Clear filters" button could not have. So a chip's X
 *  hands focus to the next chip's X, and the last chip's X (like `Clear All
 *  Filters`) hands it to the Filters trigger, which is always mounted. */
export function GraphActiveFilters({
  chips,
  dispatch,
  onClearAll,
  onFocusFiltersToggle,
  noRelationships = false,
}: {
  chips: ActiveFilterChip[];
  dispatch: (action: GraphAction) => void;
  onClearAll: () => void;
  /** Focus the always-mounted Filters disclosure trigger. */
  onFocusFiltersToggle: () => void;
  /** Every relationship type is withheld, so no reference is drawn at all. */
  noRelationships?: boolean;
}) {
  const removeRefs = useRef(new Map<string, HTMLButtonElement>());
  /** The chip key to focus after the next render; `null` = the Filters trigger;
   *  `undefined` = nothing pending. */
  const pendingFocus = useRef<string | null | undefined>(undefined);

  // Deliberately un-keyed: it must run after the render that removed the control
  // the user just activated, whether that render kept the row or emptied it.
  useEffect(() => {
    const key = pendingFocus.current;
    if (key === undefined) return;
    pendingFocus.current = undefined;
    const next = key === null ? null : removeRefs.current.get(key);
    if (next && next.isConnected) next.focus();
    else onFocusFiltersToggle();
  });

  if (chips.length === 0) return null;
  return (
    <div className="memory-graph-chips" role="group" aria-label="Active filters">
      {chips.map((chip, i) => (
        <span className="memory-graph-chip" key={chip.key} title={chip.raw ?? undefined}>
          <span className="memory-graph-chip-label">{chip.label}</span>
          <button
            type="button"
            className="memory-graph-chip-remove"
            aria-label={chip.removeLabel}
            ref={(el) => {
              if (el) removeRefs.current.set(chip.key, el);
              else removeRefs.current.delete(chip.key);
            }}
            onClick={() => {
              pendingFocus.current = chips[i + 1]?.key ?? null;
              dispatch(chip.action);
            }}
          >
            <X size={11} strokeWidth={2.2} aria-hidden="true" />
          </button>
        </span>
      ))}
      <button
        type="button"
        className="memory-graph-chips-clear"
        onClick={() => {
          pendingFocus.current = null;
          onClearAll();
        }}
      >
        Clear All Filters
      </button>
      {noRelationships && (
        <span className="memory-graph-chips-note">
          No references are drawn — every relationship type is hidden.
        </span>
      )}
    </div>
  );
}

interface GraphFiltersPanelProps {
  id: string;
  index: GraphIndex;
  state: GraphViewState;
  dispatch: (action: GraphAction) => void;
  communityQuery: string;
  onCommunityQuery: (value: string) => void;
  grouping: BrowseGrouping;
  onGrouping: (value: BrowseGrouping) => void;
}

/**
 * The disclosure body: node type, cluster (search + select), relationship types,
 * and — in Browse — the grouping. Every control that used to sit permanently on
 * the surface is here; none was removed.
 */
export function GraphFiltersPanel({
  id,
  index,
  state,
  dispatch,
  communityQuery,
  onCommunityQuery,
  grouping,
  onGrouping,
}: GraphFiltersPanelProps) {
  const needle = communityQuery.trim().toLowerCase();
  const match = (c: GraphCommunityEntry) =>
    needle === '' ||
    (c.name ?? '').toLowerCase().includes(needle) ||
    c.id.toLowerCase().includes(needle);
  const multi = index.communitiesBySize.filter((c) => !c.isSingleton && match(c));
  const single = index.communitiesBySize.filter((c) => c.isSingleton && match(c));

  return (
    <div className="memory-graph-filters-panel" id={id}>
      <div className="memory-graph-filters-grid">
        <label className="memory-graph-filter">
          <span>Node Type</span>
          <select
            value={state.typeFilter}
            onChange={(e) =>
              dispatch({ kind: 'filterType', value: e.target.value as GraphTypeFilter })
            }
          >
            <option value="all">Files &amp; concepts</option>
            <option value="file">Files only</option>
            <option value="concept">Concepts only</option>
          </select>
        </label>
        <label className="memory-graph-filter">
          <span>Find a Cluster</span>
          <input
            type="text"
            value={communityQuery}
            placeholder="narrow the list…"
            onChange={(e) => onCommunityQuery(e.target.value)}
          />
        </label>
        {/* P36R S10 — labelled "Cluster", not "Community". Every option this
            control renders says "cluster"; the payload field stays
            `community_id` and the command keyword stays `community`. Option text
            is `communityOptionLabel`, i.e. the upstream name VERBATIM plus its
            own file count as a separate `·` segment. */}
        <label className="memory-graph-filter">
          <span>Cluster</span>
          <select
            value={state.communityFilter}
            onChange={(e) => dispatch({ kind: 'filterCommunity', id: e.target.value })}
          >
            <option value="all">All clusters</option>
            {multi.length > 0 && (
              <optgroup label="Multi-file clusters">
                {multi.map((c) => (
                  <option key={c.id} value={c.id}>
                    {communityOptionLabel(c)}
                  </option>
                ))}
              </optgroup>
            )}
            {single.length > 0 && (
              <optgroup label="Single-file clusters (label is one file's name)">
                {single.map((c) => (
                  <option key={c.id} value={c.id}>
                    {communityOptionLabel(c)}
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </label>
        {state.mode === 'browse' && (
          <label className="memory-graph-filter">
            <span>Group By</span>
            <select value={grouping} onChange={(e) => onGrouping(e.target.value as BrowseGrouping)}>
              <option value="type">File type</option>
              <option value="community">Cluster</option>
            </select>
          </label>
        )}
      </div>

      {/* The full cluster caveat — how clusters are derived, how many hold a
          single file, and that they are not schema categories — lives in About
          This Graph → Cluster Colors. This one line keeps the caveat where the
          filtering actually happens. */}
      <p className="memory-graph-community-note">
        Clusters are advisory groupings derived automatically upstream and named after one
        representative node — not categories the schema recognises.
      </p>

      <fieldset className="memory-graph-relations">
        <legend>Relationship Types</legend>
        <div className="memory-graph-relations-row">
          {index.relationTypes.map((rel) => {
            const checked = state.relationFilter === null || state.relationFilter.includes(rel);
            return (
              <label className="memory-graph-relation-check" key={rel} title={rel}>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => dispatch(relationToggleAction(rel, state, index))}
                />
                {/* The closed five-value map. The backend's exact string stays
                    reachable as the label's `title`. */}
                <span>{relationDisplayLabel(rel)}</span>
              </label>
            );
          })}
          {index.relationTypes.length === 0 && (
            <span className="memory-graph-relations-note">
              No relationship values are present in this projection.
            </span>
          )}
          <span className="memory-graph-relations-note">
            unticking one also stops paths travelling through it
          </span>
        </div>
      </fieldset>
    </div>
  );
}

/** The disclosure trigger. Reports the active count so a collapsed panel never
 *  hides the fact that the view is filtered. */
export function GraphFiltersToggle({
  id,
  open,
  count,
  onToggle,
  buttonRef,
}: {
  id: string;
  open: boolean;
  count: number;
  onToggle: () => void;
  /** Always mounted, so it is where focus lands when a chip-row control removes
   *  itself (see `GraphActiveFilters`). */
  buttonRef?: Ref<HTMLButtonElement>;
}) {
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <button
      ref={buttonRef}
      type="button"
      className="memory-graph-disclosure-btn"
      aria-expanded={open}
      /* Only while the region EXISTS: it is unmounted when closed, and an
         aria-controls pointing at a missing id is a broken reference. */
      aria-controls={open ? id : undefined}
      onClick={onToggle}
    >
      <Chevron size={13} strokeWidth={2} aria-hidden="true" />
      Filters
      {count > 0 && (
        <span className="memory-graph-disclosure-count">
          {count}
          <span className="memory-graph-visually-hidden"> active</span>
        </span>
      )}
    </button>
  );
}
