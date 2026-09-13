/*
 * THE EXPERIMENT LIBRARY'S VIEW MODEL — `lib/library.ts` and `lib/folders.ts`.
 *
 * THE ACCEPTANCE TEST THIS FILE EXISTS FOR, AND THE PREMISE IT CORRECTS.
 *
 * The plan's acceptance for the Library screen reads: "the shipped worked
 * example's five records ALL TITLED `XANES Example — CuO (Cu K-edge)` are
 * distinguishable in the list. That is the test."
 *
 * **MEASURED: THE FIVE SERVED TITLES ARE ALL DIFFERENT.** Probed over HTTP against
 * a booted application, `GET /api/experiments` returns five DISTINCT titles —
 * `XANES Example — CuO (Cu K-edge) · New Draft`, `· Partially Completed`,
 * `· Ready to Export`, `· Export Review Required`, `· Exported Record` — and
 * `workspace.py`'s own comment beside `_SEED_TITLE_BASE` says so: "the lifecycle
 * suffix below distinguishes the five".
 *
 * THE COLLISION IS MADE BY THIS CLIENT, and that is the real finding. `adapt.
 * stripLifecycleSuffix` removes a known suffix for display, precisely because the
 * row carries its own lifecycle chip — so all five RENDER as one identical line.
 * The plan's claim is true of the SCREEN and false of the PAYLOAD, and a fix that
 * had reasoned from the payload would have concluded there was nothing to fix.
 *
 * SO THE PROPERTY IS TESTED TWICE OVER, and neither is the plan's phrasing:
 *   * the five SERVED titles are distinct (so nobody re-derives the false premise);
 *   * the five DISPLAY titles collide, and every row is nonetheless distinguishable
 *     without opening it.
 *
 * AND IT IS TESTED ON THE HARDER CASE TOO — two records a scientist genuinely
 * names the same thing, which no suffix distinguishes and which is the general form
 * of the defect.
 */

import { describe, it, expect } from 'vitest';
import {
  DEFAULT_LIBRARY_SORT,
  LIBRARY_FACETS,
  LIBRARY_SORTS,
  duplicateDisplayTitles,
  existingFolderPaths,
  facetCounts,
  isAmbiguousTitle,
  matchesQuery,
  selectLibraryRows,
  sortLibraryRows,
} from '../lib/library';
import {
  FOLDER_SEPARATOR,
  ancestorPaths,
  buildFolderTree,
  folderBreadcrumbs,
  folderSegments,
  isWithinFolder,
  rootFolders,
} from '../lib/folders';
import { libraryRows, stripLifecycleSuffix } from '../lib/adapt';
import type { ApiExperimentSummary } from '../lib/types';

function row(overrides: Partial<ApiExperimentSummary> = {}): ApiExperimentSummary {
  return {
    id: '01SYNTH0000000000000000001',
    title: 'A record',
    status: 'needs_attention',
    created_utc: '2026-07-12T00:00:01Z',
    pending_count: 0,
    evidenced_field_count: 0,
    exported: false,
    record_id: null,
    updated_utc: '2026-07-12T00:00:01Z',
    run_count: 0,
    open_proposal_count: 0,
    folder: '',
    technique: null,
    beamline: null,
    ...overrides,
  };
}

const BASE = 'XANES Example — CuO (Cu K-edge)';

/**
 * The five canonical rows as the server ACTUALLY serves them — measured over HTTP
 * on this branch, not composed from the plan's description of them.
 */
const CANONICAL: ApiExperimentSummary[] = [
  row({
    id: '01SYNTHXANESSEED0000000001',
    title: `${BASE} · New Draft`,
    scenario: 'Example 1 · at setup: extraction only',
    status: 'needs_attention',
    created_utc: '2026-07-12T00:00:01Z',
    updated_utc: '2026-07-12T00:00:01Z',
    pending_count: 5,
    evidenced_field_count: 26,
    technique: 'HERFD-XAS',
    beamline: '15-2',
  }),
  row({
    id: '01SYNTHXANESSEED0000000002',
    title: `${BASE} · Partially Completed`,
    scenario: 'Example 2 · at setup: some answers confirmed',
    status: 'needs_attention',
    created_utc: '2026-07-12T00:00:02Z',
    updated_utc: '2026-07-12T00:00:02Z',
    pending_count: 2,
    evidenced_field_count: 26,
    technique: 'HERFD-XAS',
    beamline: '15-2',
  }),
  row({
    id: '01SYNTHXANESSEED0000000003',
    title: `${BASE} · Ready to Export`,
    scenario: 'Example 3 · at setup: all answers confirmed',
    status: 'ready_to_export',
    created_utc: '2026-07-12T00:00:03Z',
    updated_utc: '2026-07-12T00:00:03Z',
    evidenced_field_count: 26,
    technique: 'HERFD-XAS',
    beamline: '15-2',
  }),
  row({
    id: '01SYNTHXANESSEED0000000004',
    title: `${BASE} · Export Review Required`,
    scenario: 'Example 4 · at setup: descriptor uncertainty omitted',
    status: 'in_review',
    created_utc: '2026-07-12T00:00:04Z',
    updated_utc: '2026-07-12T00:00:04Z',
    evidenced_field_count: 26,
    technique: 'HERFD-XAS',
    beamline: '15-2',
  }),
  row({
    id: '01SYNTHXANESSEED0000000005',
    title: `${BASE} · Exported Record`,
    scenario: 'Example 5 · at setup: export run',
    status: 'done',
    created_utc: '2026-07-12T00:00:05Z',
    updated_utc: '2026-07-12T00:00:05Z',
    evidenced_field_count: 26,
    exported: true,
    record_id: '01SYNTHXANESSEED0000000005',
    technique: 'HERFD-XAS',
    beamline: '15-2',
  }),
];

describe('LIB-002 · the five worked-example rows are distinguishable without opening one', () => {
  it('the five SERVED titles are all DIFFERENT — the plan said they were identical', () => {
    // Recorded so nobody re-derives the false premise from the plan document.
    expect(new Set(CANONICAL.map((r) => r.title)).size).toBe(5);
  });

  it('...and the five DISPLAY titles collide, which is what this client does to them', () => {
    const displayed = CANONICAL.map((r) => stripLifecycleSuffix(r.title));
    expect(new Set(displayed).size).toBe(1);
    expect(displayed[0]).toBe(BASE);
  });

  it('every one of the five rows is nonetheless distinguishable on the list', () => {
    const rows = libraryRows(CANONICAL);
    // THE PROPERTY, stated as a set: each row must differ from every other row in
    // something a reader can SEE, without opening it. Asserted over the whole
    // visible tuple rather than over one field, so a change that made four of the
    // five differentiators disappear would fail here rather than pass on the fifth.
    const visible = rows.map((r) =>
      JSON.stringify([r.title, r.scenario, r.lifecycle, r.group, r.trailing, r.disambiguator]),
    );
    expect(new Set(visible).size).toBe(5);
    // AND EVERY ROW CARRIES THE RECORD ID, because the display titles collide.
    expect(rows.every((r) => r.disambiguator !== undefined)).toBe(true);
    expect(new Set(rows.map((r) => r.disambiguator)).size).toBe(5);
  });

  it('two records a scientist genuinely names the same thing are also distinguished', () => {
    // THE HARDER CASE, and the general form of the defect: no lifecycle suffix, no
    // scenario label, same status, same everything a chip could show.
    const rows = libraryRows([
      row({ id: '01AAA00000000000000000001', title: 'Copper oxide pellet' }),
      row({ id: '01AAA00000000000000000002', title: 'Copper oxide pellet' }),
    ]);
    expect(rows[0].disambiguator).toBe('01AAA00000000000000000001');
    expect(rows[1].disambiguator).toBe('01AAA00000000000000000002');
  });

  it('a row whose title is unique carries NO id, so it stays quiet', () => {
    // An id beside every title is noise a reader learns to skip, which is how it
    // would fail to help on the rows where it matters.
    const rows = libraryRows([
      row({ id: '01AAA00000000000000000001', title: 'Copper oxide pellet' }),
      row({ id: '01AAA00000000000000000002', title: 'Nickel foil reference' }),
    ]);
    expect(rows.every((r) => r.disambiguator === undefined)).toBe(true);
  });

  it('collision is judged case- and whitespace-insensitively', () => {
    // Two titles a reader cannot tell apart ARE a collision, whatever the bytes say.
    const duplicates = duplicateDisplayTitles(['Copper Oxide', ' copper oxide ']);
    expect(isAmbiguousTitle('Copper Oxide', duplicates)).toBe(true);
    expect(isAmbiguousTitle('copper oxide', duplicates)).toBe(true);
    expect(isAmbiguousTitle('Nickel foil', duplicates)).toBe(false);
  });
});

describe('search', () => {
  it('searches the FULL served title, not the stripped display title', () => {
    // A reader typing what they can read in the record's own header must find it.
    expect(matchesQuery(CANONICAL[4], 'Exported Record')).toBe(true);
    expect(stripLifecycleSuffix(CANONICAL[4].title)).not.toContain('Exported Record');
  });

  it('searches exactly the five fields the placeholder names, and the ids', () => {
    const target = row({
      id: '01ZZZ00000000000000000009',
      title: 'Nickel foil',
      folder: 'Cu K-edge/2026',
      technique: 'HERFD-XAS',
      beamline: '15-2',
      record_id: '01RRR00000000000000000009',
      scenario: 'Example 9 · at setup: nothing',
    });
    for (const needle of [
      'nickel', // name
      'Cu K-edge/2026', // folder
      'herfd', // technique
      '15-2', // beamline
      '01ZZZ', // id
      '01RRR', // exported record id
      'Example 9', // scenario
    ]) {
      expect(matchesQuery(target, needle), needle).toBe(true);
    }
    expect(matchesQuery(target, 'not in any field')).toBe(false);
  });

  it('an empty or whitespace query matches everything', () => {
    expect(matchesQuery(row(), '')).toBe(true);
    expect(matchesQuery(row(), '   ')).toBe(true);
  });

  it('DOES NOT CRASH on a row missing the fields it reads', () => {
    // A server response shape is not a promise however the type is written, and the
    // measured consequence of assuming otherwise is documented on `library.text`:
    // one absent string threw inside `Array.sort`, React unwound, and the ENTIRE
    // screen rendered as an empty `<div />` because this app has no ErrorBoundary.
    const partial = { id: 'x', status: 'done' } as unknown as ApiExperimentSummary;
    expect(() => matchesQuery(partial, 'anything')).not.toThrow();
    expect(matchesQuery(partial, 'x')).toBe(true);
  });
});

describe('sort', () => {
  it('defaults to last-updated, newest first', () => {
    expect(DEFAULT_LIBRARY_SORT).toBe('updated');
    const rows = sortLibraryRows(
      [
        row({ id: 'a', updated_utc: '2026-01-01T00:00:00Z' }),
        row({ id: 'b', updated_utc: '2026-03-01T00:00:00Z' }),
        row({ id: 'c', updated_utc: '2026-02-01T00:00:00Z' }),
      ],
      'updated',
    );
    expect(rows.map((r) => r.id)).toEqual(['b', 'c', 'a']);
  });

  it('breaks EVERY tie by id, so the order is stable rather than arbitrary', () => {
    // The five example records are one second apart and identically titled after the
    // display strip. A comparator returning 0 for a tie would leave their order down
    // to the engine's sort stability — reproducible in practice, unspecified in
    // principle, and impossible to write a test against.
    for (const sort of LIBRARY_SORTS.map((s) => s.id)) {
      const identical = [
        row({ id: 'ccc' }),
        row({ id: 'aaa' }),
        row({ id: 'bbb' }),
      ];
      expect(sortLibraryRows(identical, sort).map((r) => r.id), sort).toEqual([
        'aaa',
        'bbb',
        'ccc',
      ]);
    }
  });

  it('sorts a copy and never mutates the caller array', () => {
    // The caller's array is the fetch result and is shared with `facetCounts`.
    const original = [row({ id: 'b' }), row({ id: 'a' })];
    const snapshot = original.map((r) => r.id);
    sortLibraryRows(original, 'title');
    expect(original.map((r) => r.id)).toEqual(snapshot);
  });

  it('a row with NO updated_utc sorts LAST, never first', () => {
    // Direction is a decision, not a fallout: placing it first would have a record
    // with no known last-changed date claim to be the most recently touched thing in
    // the workspace.
    const rows = sortLibraryRows(
      [
        { ...row({ id: 'missing' }), updated_utc: undefined } as unknown as ApiExperimentSummary,
        row({ id: 'known', updated_utc: '2020-01-01T00:00:00Z' }),
      ],
      'updated',
    );
    expect(rows.map((r) => r.id)).toEqual(['known', 'missing']);
  });

  it('sorts by name numerically, so Run 2 precedes Run 10', () => {
    const rows = sortLibraryRows(
      [row({ id: 'a', title: 'Run 10' }), row({ id: 'b', title: 'Run 2' })],
      'title',
    );
    expect(rows.map((r) => r.title)).toEqual(['Run 2', 'Run 10']);
  });

  it('sorts by run count, most first, and a missing count reads as zero', () => {
    const rows = sortLibraryRows(
      [
        row({ id: 'a', run_count: 1 }),
        { ...row({ id: 'b' }), run_count: undefined } as unknown as ApiExperimentSummary,
        row({ id: 'c', run_count: 7 }),
      ],
      'runs',
    );
    expect(rows.map((r) => r.id)).toEqual(['c', 'a', 'b']);
  });
});

describe('facets', () => {
  it('counts over the WHOLE list, so a chip never shrinks as you type', () => {
    // The chips exist to say where the work is before a reader has narrowed
    // anything. A number that moved with the search box would be answering a
    // question they had not asked.
    const counts = facetCounts(CANONICAL);
    expect(counts.all).toBe(5);
    expect(counts.needsAttention).toBe(2);
    expect(counts.inReview).toBe(1);
    expect(counts.ready).toBe(1);
    expect(counts.done).toBe(1);
    expect(counts.draft).toBe(4); // four are not exported
    expect(counts.proposals).toBe(0);
  });

  it('there is NO `submitted` facet, and its absence is deliberate', () => {
    // Whether a record is submitted needs a content signature plus a
    // revision-history read PER RECORD, and that reader answers nothing at all in a
    // deployment without a database — while the migrations that would give it one
    // are approved and applied nowhere. The chip would match zero rows in every
    // deployment that exists, and a permanently empty filter tells a reader they
    // have no submitted work rather than that we cannot tell.
    expect(LIBRARY_FACETS.map((f) => f.id)).not.toContain('submitted');
  });

  it('`draft` keys on `exported`, so it can never disagree with the row chip', () => {
    expect(facetCounts([row({ exported: false, status: 'done' })]).draft).toBe(1);
    expect(facetCounts([row({ exported: true, status: 'needs_attention' })]).draft).toBe(0);
  });

  it('`proposals` counts rows with something waiting, tolerating a missing count', () => {
    expect(facetCounts([row({ open_proposal_count: 3 })]).proposals).toBe(1);
    expect(facetCounts([row({ open_proposal_count: 0 })]).proposals).toBe(0);
    const partial = { ...row(), open_proposal_count: undefined } as unknown as ApiExperimentSummary;
    expect(facetCounts([partial]).proposals).toBe(0);
  });
});

describe('selection', () => {
  it('combines folder, facet and query', () => {
    const rows = [
      row({ id: 'a', folder: 'Cu/2026', title: 'Alpha', status: 'needs_attention' }),
      row({ id: 'b', folder: 'Cu/2026', title: 'Beta', status: 'done' }),
      row({ id: 'c', folder: 'Ni', title: 'Alpha', status: 'needs_attention' }),
    ];
    const selected = selectLibraryRows(rows, {
      query: 'alpha',
      facet: 'needsAttention',
      sort: 'title',
      folder: 'Cu',
    });
    expect(selected.map((r) => r.id)).toEqual(['a']);
  });

  it('searching from inside a folder SPANS its subtree by default', () => {
    // Cross-folder search is the default rather than a mode a reader has to find,
    // and a folder shows its descendants — the alternative hides a record from the
    // folder a reader believes it is in.
    const rows = [row({ id: 'deep', folder: 'Cu/2026/October' })];
    expect(
      selectLibraryRows(rows, { query: '', facet: 'all', sort: 'title', folder: 'Cu' }),
    ).toHaveLength(1);
    expect(
      selectLibraryRows(rows, {
        query: '',
        facet: 'all',
        sort: 'title',
        folder: 'Cu',
        exactFolder: true,
      }),
    ).toHaveLength(0);
  });

  it('the root includes unfiled records as well as filed ones', () => {
    const rows = [row({ id: 'filed', folder: 'Cu' }), row({ id: 'loose', folder: '' })];
    expect(
      selectLibraryRows(rows, { query: '', facet: 'all', sort: 'title', folder: '' }),
    ).toHaveLength(2);
  });
});

describe('folders — a projection of the experiment list, and nothing else', () => {
  it('a path exists exactly while an experiment names it', () => {
    expect(buildFolderTree([row({ folder: '' })]).size).toBe(0);
    const tree = buildFolderTree([row({ folder: 'Cu' })]);
    expect([...tree.keys()]).toEqual(['Cu']);
    // AND THERE IS NO WAY TO MAKE AN EMPTY ONE. `buildFolderTree` is the only
    // producer of folder nodes in the app and it reads nothing but this list, so a
    // folder with no members is unrepresentable rather than merely unusual.
  });

  it('synthesises intermediate levels so a breadcrumb has no holes', () => {
    const tree = buildFolderTree([row({ folder: 'a/b/c' })]);
    expect([...tree.keys()].sort()).toEqual(['a', 'a/b', 'a/b/c']);
    expect(tree.get('a')!.directCount).toBe(0);
    expect(tree.get('a')!.totalCount).toBe(1);
    expect(tree.get('a/b/c')!.directCount).toBe(1);
  });

  it('wires parent to child regardless of the order rows arrive in', () => {
    // Parent/child wiring is a second pass BECAUSE a parent may be created after its
    // child. Doing it inline would drop the edge whenever a deeper path was seen
    // first — a list-order dependency, and therefore a bug only some workspaces
    // would ever show.
    for (const order of [
      ['a/b', 'a'],
      ['a', 'a/b'],
    ]) {
      const tree = buildFolderTree(order.map((folder, i) => row({ id: `x${i}`, folder })));
      expect(tree.get('a')!.children, order.join(',')).toEqual(['a/b']);
    }
  });

  it('counts direct members and subtree totals separately', () => {
    const tree = buildFolderTree([
      row({ id: '1', folder: 'a' }),
      row({ id: '2', folder: 'a/b' }),
      row({ id: '3', folder: 'a/b' }),
    ]);
    expect(tree.get('a')!.directCount).toBe(1);
    expect(tree.get('a')!.totalCount).toBe(3);
    expect(tree.get('a/b')!.directCount).toBe(2);
  });

  it('containment is SEGMENT-aware, not a string prefix', () => {
    // A naive `startsWith` puts `Cu K-edge 2` inside `Cu K-edge`, which would show a
    // reader rows that are not there.
    expect(isWithinFolder('Cu K-edge 2', 'Cu K-edge')).toBe(false);
    expect(isWithinFolder('Cu K-edge/2026', 'Cu K-edge')).toBe(true);
    expect(isWithinFolder('Cu K-edge', 'Cu K-edge')).toBe(true);
    expect(isWithinFolder('', '')).toBe(true);
    expect(isWithinFolder('anything', '')).toBe(true);
  });

  it('breadcrumbs name every level and return nothing for the root', () => {
    expect(folderBreadcrumbs('')).toEqual([]);
    expect(folderBreadcrumbs('a/b/c')).toEqual([
      { path: 'a', name: 'a' },
      { path: 'a/b', name: 'b' },
      { path: 'a/b/c', name: 'c' },
    ]);
  });

  it('ancestors exclude the path itself', () => {
    expect(ancestorPaths('a/b/c')).toEqual(['a', 'a/b']);
    expect(ancestorPaths('a')).toEqual([]);
    expect(ancestorPaths('')).toEqual([]);
  });

  it('roots and children sort numerically', () => {
    const tree = buildFolderTree([
      row({ id: '1', folder: 'Run 10' }),
      row({ id: '2', folder: 'Run 2' }),
      row({ id: '3', folder: 'a/Run 10' }),
      row({ id: '4', folder: 'a/Run 2' }),
    ]);
    expect(rootFolders(tree)).toEqual(['a', 'Run 2', 'Run 10']);
    expect(tree.get('a')!.children).toEqual(['a/Run 2', 'a/Run 10']);
  });

  it('offers every existing path as a destination, and nothing else', () => {
    // NO "new folder" entry, and that is the model rather than an omission: a path
    // is created by being typed into a move or a create, so the UI offers a text
    // field beside this list rather than an action with nothing behind it.
    expect(existingFolderPaths([row({ folder: 'a/b/c' }), row({ folder: '' })])).toEqual([
      'a',
      'a/b',
      'a/b/c',
    ]);
  });

  it('tolerates a wrong-typed folder rather than crashing the projection', () => {
    const partial = { ...row(), folder: 7 } as unknown as ApiExperimentSummary;
    expect(() => buildFolderTree([partial])).not.toThrow();
    expect(buildFolderTree([partial]).size).toBe(0);
    expect(existingFolderPaths([partial])).toEqual([]);
  });

  it('the separator matches the one the server joins with', () => {
    // SEPARATOR PARITY IS LOAD-BEARING: the server joins with it and this module
    // splits on it. A mismatch would not error — it would silently render every
    // nested path as one flat name. Pinned against a path the server actually
    // returned for a nested assignment (measured over HTTP: ` /Cu K-edge//2026
    // campaign/ ` normalised to `Cu K-edge/2026 campaign`).
    expect(FOLDER_SEPARATOR).toBe('/');
    expect(folderSegments('Cu K-edge/2026 campaign')).toEqual(['Cu K-edge', '2026 campaign']);
  });
});
