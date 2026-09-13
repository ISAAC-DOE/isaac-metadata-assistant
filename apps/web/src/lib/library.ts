/*
 * THE EXPERIMENT LIBRARY'S VIEW MODEL. Pure functions over the server's list
 * payload: no fetching, no state, no invented values.
 *
 * ONE RULE GOVERNS EVERY COUNT IN HERE, and it is the rule §11 of `CLAUDE.md`
 * records being learned the hard way: **a count describes the set it is a count
 * of, and says which set that is.** `facetCounts` counts over the WHOLE list
 * (so a chip's number does not change as you type in the search box, which would
 * make the chips useless for deciding where to look); the result heading counts
 * over the FILTERED rows (so it describes what is on screen). Both are computed
 * from the server's rows and neither is ever recomputed from a rendered array.
 *
 * WHY THERE IS NO `Submitted` FACET, stated because the plan asked for one.
 * Whether a record is submitted is not on the list payload and cannot honestly be
 * put there: it needs `export_units()` + a content signature + a revision-history
 * read PER RECORD, and `revision_history.reader()` answers `None` in every
 * deployment without `PGHOST` while migrations `0003`/`0004` are approved but
 * applied nowhere. A `Submitted` chip would therefore match zero rows in every
 * deployment that exists — a filter that is always empty is worse than no filter,
 * because a reader concludes they have no submitted work rather than that we
 * cannot tell. See the comment beside `_summary` in `routes.py`.
 */

import { LABELS } from './labels';
import { isWithinFolder, compareNames, folderSegments } from './folders';
import type { ApiExperimentSummary } from './types';

/**
 * The facets, as `(id, label, predicate)`. Six of the seven reuse a label the app
 * already ships — `CLAUDE.md`-adjacent discipline, and the brief's instruction:
 * inventing a parallel vocabulary for the same states is how a product ends up
 * with three names for one thing, which this repository has already measured
 * itself doing (three nav taxonomies in one rail).
 *
 * `proposals` IS THE ONE NEW LABEL, and it is new because the state it names had
 * no label: "a colleague or an ingestion left me something to judge". It is called
 * `Proposals Waiting` rather than `Needs Review` deliberately — `In Review` is
 * already a status group in this list, and two chips a word apart meaning
 * different things is a worse outcome than one slightly longer name. It is the
 * cross-experiment review lens that `ISAAC_PRODUCT_DECISIONS.md` DEC-09 confirms
 * belongs here as a FILTER rather than as a top-level destination.
 */
export type LibraryFacetId =
  | 'all'
  | 'needsAttention'
  | 'proposals'
  | 'inReview'
  | 'ready'
  | 'draft'
  | 'done';

export interface LibraryFacet {
  id: LibraryFacetId;
  label: string;
  /** True when this row belongs in the facet. Reads server fields only. */
  matches: (s: ApiExperimentSummary) => boolean;
}

export const LIBRARY_FACETS: LibraryFacet[] = [
  { id: 'all', label: LABELS.libraryFacetAll, matches: () => true },
  {
    id: 'needsAttention',
    label: LABELS.groupNeedsAttention,
    matches: (s) => s.status === 'needs_attention',
  },
  {
    id: 'proposals',
    label: LABELS.libraryFacetProposals,
    matches: (s) => count(s.open_proposal_count) > 0,
  },
  { id: 'inReview', label: LABELS.groupInReview, matches: (s) => s.status === 'in_review' },
  { id: 'ready', label: LABELS.groupReady, matches: (s) => s.status === 'ready_to_export' },
  // `Draft` IS `!exported` AND NOT `status !== 'done'`. The two differ, and the
  // difference is the honest one: `exported` is a fact about an artifact existing,
  // which is what the row's own Draft/Exported chip already shows, so this chip and
  // that chip can never disagree. Keying it on `status` would have made a chip
  // labelled `Draft` filter on something the row does not display.
  { id: 'draft', label: LABELS.chipDraft, matches: (s) => !s.exported },
  { id: 'done', label: LABELS.groupDone, matches: (s) => s.status === 'done' },
];

export type LibrarySortId = 'updated' | 'created' | 'title' | 'runs';

export interface LibrarySort {
  id: LibrarySortId;
  label: string;
}

export const LIBRARY_SORTS: LibrarySort[] = [
  { id: 'updated', label: LABELS.librarySortUpdated },
  { id: 'created', label: LABELS.librarySortCreated },
  { id: 'title', label: LABELS.librarySortTitle },
  { id: 'runs', label: LABELS.librarySortRuns },
];

export const DEFAULT_LIBRARY_SORT: LibrarySortId = 'updated';

/**
 * Does this row match the search text?
 *
 * WHAT IS SEARCHED, and why each field is in the list: the **full server title**
 * (not the display title — see `libraryRows`, which strips a lifecycle suffix for
 * display; a reader typing `Exported Record` must still find the row whose title
 * says so), the `scenario` label, the `folder` path, the `technique`, the
 * `beamline`, and the record `id` plus the exported `record_id`, because an id is
 * what a person pastes out of a filename or a colleague's message.
 *
 * WHAT IS NOT SEARCHED: nothing scientific beyond the two record-level values the
 * row already displays. A search that silently matched on a field the row does not
 * show would return rows whose relevance a reader cannot see.
 *
 * Case-insensitive substring, not fuzzy. A fuzzy match on 26-character ULIDs
 * produces confident nonsense, and there is no relevance signal here to rank by.
 */
export function matchesQuery(s: ApiExperimentSummary, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  const haystack = [s.title, s.scenario, s.folder, s.technique, s.beamline, s.id, s.record_id]
    .map(text)
    .join(' ')
    .toLowerCase();
  return haystack.includes(needle);
}

/**
 * A STRING FROM A VALUE THE TYPE PROMISES IS A STRING -- because the type is a
 * promise about a server RESPONSE, which is not a promise at all.
 *
 * THIS EXISTS BECAUSE THE ABSENCE OF IT CRASHED THE WHOLE SCREEN, found by the
 * suite rather than reasoned about. `sortLibraryRows` called
 * `a.updated_utc.localeCompare(...)` directly; a row without that key threw
 * `Cannot read properties of undefined (reading 'localeCompare')` INSIDE
 * `Array.sort`, React unwound, and -- because this app has no ErrorBoundary
 * anywhere -- the entire My Experiments screen rendered as an empty `<div />`.
 * One missing string, every row lost.
 *
 * IT IS THE RULE §11 OF `CLAUDE.md` RECORDS BEING LEARNED TWICE ON THE BACKEND,
 * applied on the client: a malformed or absent value in something already served
 * must be READ, not refused, because the reader did nothing wrong and their
 * records must not simply vanish. A typed refusal is the right answer to a bad
 * REQUEST; it is the wrong answer to a response shape.
 *
 * IT COERCES NOTHING AND INVENTS NOTHING. A non-string becomes `''`, which is
 * `workspace._as_str`'s exact policy server-side and for the identical reason
 * given there: `String()` cannot fail, so a coercing version would manufacture
 * `"5"` out of a number and `"[object Object]"` out of a structure. `''` puts the
 * value in the bucket a MISSING key was already in.
 */
function text(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

/**
 * A number from a value the type promises is a number, else `0`.
 *
 * `sortLibraryRows`' arithmetic on `run_count` yields `NaN` for a missing key,
 * and a comparator returning `NaN` leaves the sort order UNSPECIFIED rather than
 * merely wrong -- a worse failure than the crash above, because it does not throw
 * and so leaves no trace at all.
 */
function count(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

/**
 * One count per facet, over the WHOLE list — never over the filtered rows.
 *
 * The chips exist to tell a reader where the work is before they have narrowed
 * anything. A chip whose number shrank as they typed would be answering a question
 * they had not asked, and would read as "there are no records needing attention"
 * when it means "none matching what you typed".
 */
export function facetCounts(
  summaries: ApiExperimentSummary[],
): Record<LibraryFacetId, number> {
  const out = {} as Record<LibraryFacetId, number>;
  for (const facet of LIBRARY_FACETS) {
    out[facet.id] = summaries.filter(facet.matches).length;
  }
  return out;
}

export interface LibraryQuery {
  query: string;
  facet: LibraryFacetId;
  sort: LibrarySortId;
  /**
   * Show only experiments at or beneath this folder path. `''` is the root and
   * includes everything, filed or not — which is what makes CROSS-FOLDER SEARCH
   * the default rather than a mode a reader has to find.
   */
  folder: string;
  /**
   * When true, restrict to EXACTLY `folder` instead of `folder` and beneath.
   * Browsing a folder shows its own rows with its subfolders listed separately;
   * searching from inside one deliberately spans the subtree.
   */
  exactFolder?: boolean;
}

/**
 * The server's rows, filtered and sorted. Returns the API shape untouched — the
 * display mapping is `adapt.ts`'s job, and keeping the two apart is what lets a
 * row's rendered text differ from the text that was searched.
 */
export function selectLibraryRows(
  summaries: ApiExperimentSummary[],
  q: LibraryQuery,
): ApiExperimentSummary[] {
  const facet = LIBRARY_FACETS.find((f) => f.id === q.facet) ?? LIBRARY_FACETS[0];
  const rows = summaries.filter(
    (s) =>
      (q.exactFolder
        ? text(s.folder) === q.folder
        : isWithinFolder(text(s.folder), q.folder)) &&
      facet.matches(s) &&
      matchesQuery(s, q.query),
  );
  return sortLibraryRows(rows, q.sort);
}

/**
 * Sort a copy, never in place — the caller's array is the fetch result and is
 * shared with the facet counts above.
 *
 * EVERY ORDER IS TOTAL, and that is deliberate rather than tidy. All five example
 * records are one second apart and identically titled after the display strip, so
 * a comparator that returned 0 for a tie would leave their order down to the
 * engine's sort stability — reproducible in practice, unspecified in principle,
 * and impossible to write a test against. `id` breaks every tie, so the same list
 * always renders in the same order.
 */
export function sortLibraryRows(
  rows: ApiExperimentSummary[],
  sort: LibrarySortId,
): ApiExperimentSummary[] {
  const out = [...rows];
  // EVERY FIELD READ THROUGH `text`/`count`, INCLUDING `id` AND `title`, WHICH THE
  // SERVER ALWAYS SENDS. That is not belt-and-braces for its own sake: the tie
  // breaker is the LAST line of defence in every comparator here, so a crash in it
  // would take the screen down on exactly the input the rest of the hardening was
  // written for. Hardening five fields and leaving the sixth is how the measured
  // defect below would have come back through one stub.
  switch (sort) {
    case 'created':
      out.sort(
        (a, b) =>
          text(b.created_utc).localeCompare(text(a.created_utc)) ||
          text(a.id).localeCompare(text(b.id)),
      );
      break;
    case 'title':
      out.sort(
        (a, b) =>
          compareNames(text(a.title), text(b.title)) || text(a.id).localeCompare(text(b.id)),
      );
      break;
    case 'runs':
      out.sort(
        (a, b) =>
          count(b.run_count) - count(a.run_count) || text(a.id).localeCompare(text(b.id)),
      );
      break;
    case 'updated':
    default:
      // NEWEST FIRST, by a WHOLE-SECOND timestamp. Two records changed in the same
      // second are genuinely indistinguishable by this key — the server's own
      // contract says so — so `id` decides, and the order is stable rather than
      // arbitrary. This is the one place the second-precision limit is visible,
      // and it is a tie in a sort rather than a wrong answer.
      //
      // AN ABSENT `updated_utc` SORTS LAST, NOT FIRST, and that direction is a
      // decision rather than a fallout of `''`. `''` compares below every real
      // ISO timestamp, and this order is DESCENDING, so a row with no value
      // lands at the bottom -- which is the honest place for it. Placing it
      // first would have a record with no known last-changed date claim to be
      // the most recently touched thing in the workspace.
      out.sort(
        (a, b) =>
          text(b.updated_utc).localeCompare(text(a.updated_utc)) ||
          text(a.id).localeCompare(text(b.id)),
      );
      break;
  }
  return out;
}

/**
 * WHICH DISPLAY TITLES COLLIDE IN THE ROWS BEING RENDERED.
 *
 * THIS IS THE FUNCTION THE LIBRARY EXISTS FOR. The five shipped example records
 * are `XANES Example — CuO (Cu K-edge) · New Draft` … `· Exported Record` on the
 * wire — five DISTINCT titles — and `adapt.stripLifecycleSuffix` removes the
 * suffix for display, so all five render as one identical line. Two experiments a
 * scientist genuinely names the same thing collide for the plainer reason. Either
 * way a reader cannot tell one row from the row above it, and that is the defect.
 *
 * THE REMEDY IS TO SHOW A DIFFERENTIATOR ONLY WHERE ONE IS NEEDED, and this
 * returns the set of colliding titles so the row can decide. The pattern is not
 * invented here: `IngestionProposalsPanel` already surfaces a run id only when
 * `duplicateRunLabels` shows the label is ambiguous among the runs on screen, for
 * the identical reason — an id on every row is noise, an id on the two ambiguous
 * rows is information.
 *
 * IT IS COMPUTED OVER THE RENDERED ROWS, NOT THE WHOLE LIST, and that is the
 * correct scope rather than the convenient one: ambiguity is a property of what
 * the reader can see. Two identically-titled records in different folders are not
 * confusable while only one of them is on screen.
 */
export function duplicateDisplayTitles(displayTitles: string[]): Set<string> {
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const title of displayTitles) {
    const key = title.trim().toLowerCase();
    if (seen.has(key)) duplicates.add(key);
    seen.add(key);
  }
  return duplicates;
}

/** Is this row's display title ambiguous among the rows on screen? */
export function isAmbiguousTitle(displayTitle: string, duplicates: Set<string>): boolean {
  return duplicates.has(displayTitle.trim().toLowerCase());
}

/**
 * UX-017's LIBRARY HALF — the scientist-facing statistics that used to require
 * a trip to the demoted Statistics destination, computed over the SAME
 * `summaries` array `ExperimentsHome` already holds (`GET /api/experiments`
 * is unpaginated — see `routes.py::list_experiments`'s own docstring — so this
 * is the server's true total, never `array.length` read from a filtered or
 * paged subset).
 *
 * WORKSPACE-SCOPED, NEVER PERSONAL — the correction that matters most here.
 * `MyStats.tsx` and the `8ce85a87` fix to `SettingsPage.tsx` both establish why:
 * this build has no trusted authentication boundary
 * (`docs/identity-trust-contract.md` §6A) and no per-record author, so "your
 * activity" is a claim nothing here can back. Every figure below is a fact
 * about the WORKSPACE — how many experiments, how many runs, how many
 * proposals are waiting — never attributed to "you". Do not add a per-person
 * figure beside these; add it beside `MyStats.tsx`'s existing gate instead, so
 * the one place that already states the absent-identity reason keeps doing so.
 *
 * TWO OF THE FOUR ARE NOT DUPLICATES OF THE FACET CHIPS, and that is why this
 * function exists rather than reusing `facetCounts` alone. `LIBRARY_FACETS`
 * counts RECORDS matching a predicate (e.g. "records with at least one open
 * proposal"); `totalRuns` and `openProposals` below are SUMS across every
 * record — "how much has been captured", not "how many records need
 * attention". The other two (`total`, `needsAttention`) — ~~`exported`~~, which is
 * NOT a field on this interface; corrected 2026-09-13 after an independent review
 * (B-3) caught the docstring naming a field the type does not have — are read
 * straight off
 * `facetCounts` rather than recomputed, so the two surfaces can never disagree
 * about what they both claim to count.
 */
export interface LibraryOverviewStats {
  /** Every experiment in the workspace — `facetCounts(...).all`. */
  total: number;
  /** `facetCounts(...).needsAttention`. */
  needsAttention: number;
  /** The SUM of `run_count` over every experiment — not a record count. */
  totalRuns: number;
  /** The SUM of `open_proposal_count` over every experiment — not the count of
   *  records carrying at least one (that is the `proposals` facet chip). */
  openProposals: number;
}

export function libraryOverviewStats(
  summaries: ApiExperimentSummary[],
): LibraryOverviewStats {
  const counts = facetCounts(summaries);
  let totalRuns = 0;
  let openProposals = 0;
  for (const s of summaries) {
    totalRuns += count(s.run_count);
    openProposals += count(s.open_proposal_count);
  }
  return {
    total: counts.all,
    needsAttention: counts.needsAttention,
    totalRuns,
    openProposals,
  };
}

/**
 * The folders to OFFER as move destinations: every path that already exists,
 * plus nothing else.
 *
 * **THERE IS NO "NEW FOLDER" ENTRY HERE, AND THAT IS NOT AN OMISSION.** A new path
 * comes into existence by being typed into a move or a create — that write IS the
 * creation — so the UI offers a text field beside this list rather than a
 * "create folder" action that would have nothing to act on. Read `lib/folders.ts`
 * for the whole model.
 */
export function existingFolderPaths(summaries: ApiExperimentSummary[]): string[] {
  const paths = new Set<string>();
  for (const s of summaries) {
    if (!text(s.folder)) continue;
    const segments = folderSegments(text(s.folder));
    for (let i = 1; i <= segments.length; i += 1) {
      paths.add(segments.slice(0, i).join('/'));
    }
  }
  return [...paths].sort(compareNames);
}
