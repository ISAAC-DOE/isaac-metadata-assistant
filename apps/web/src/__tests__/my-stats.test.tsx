import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { ROUTES, STATISTICS_TAB_IDS, isStatisticsTab } from '../lib/routes';
import {
  MY_STATS_PENDING_COPY,
  MY_STATS_PENDING_LABEL,
  MY_STATS_PENDING_REASON,
  MY_STATS_VIEWS,
  unconfiguredMyStatsSource,
  type MyStatsSource,
} from '../lib/myStatsContract';
import { MyStats } from '../screens/statistics/MyStats';
import { statisticsRecordsBody, statisticsRoutes, stubFetchRoutes } from '../test/apiFixtures';

/**
 * Statistics · My Stats — the personal tab, its gate, and the two tabs above it.
 *
 * ── The thing this file exists to prevent ───────────────────────────────────
 *
 * This build has no trusted user identity and no record ownership, so it can
 * produce NO personal figure. A personal-statistics tab is therefore the single
 * most likely place in the app to state something false, and there are six
 * specific ways to do it. Each has its own test below, and each is a test about
 * ABSENCE — which is exactly the kind that rots quietly, so each one names the
 * plausible wrong answer it is excluding.
 *
 *   1. a workspace-wide total relabelled as personal
 *   2. worked-example records presented as the reader's own
 *   3. a portal-wide metric
 *   4. a fake zero ("0 records", which claims no activity)
 *   5. a chart skeleton left behind after loading resolves
 *   6. any header-derived identity
 *
 * The fixture used throughout is `statisticsRoutes()`, which really does serve
 * five records with real counts. That is deliberate: a test against an EMPTY
 * workspace could not tell "shows nothing because there is nothing" from "shows
 * nothing because it refuses to attribute". With records present, any leak of a
 * workspace figure onto this tab has a number to leak.
 */

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderAt(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

const MINE = `${ROUTES.statistics}?tab=mine`;

async function renderMineTab() {
  const calls = stubFetchRoutes(statisticsRoutes());
  const view = renderAt(MINE);
  await view.findByText('Not Available in This Preview');
  return { ...view, calls };
}

/** Every text node of a subtree, space-joined — see `statistics-page.test.tsx`. */
function textOf(root: HTMLElement): string {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const parts: string[] = [];
  while (walker.nextNode()) parts.push(walker.currentNode.textContent ?? '');
  return parts.join(' ').replace(/\s+/g, ' ').trim();
}

/* ── the emptiness matcher, and the two generations of hole it has had ───────
 *
 * GENERATION 1 — DIGIT-SHAPED GUARDS. Trap 4 used `/\b\d+\b/` and `/\b0\b/`, plus
 * a per-sentence check that fired on three literal phrases:
 *
 *     if (!/no records|no activity|nothing to show/i.test(sentence)) continue;
 *
 * "zero" is in neither list, so the whole suite passed with this sentence
 * inserted into the panel — a FALSE PERSONAL ZERO, stated in words, on the one
 * tab in the app that cannot know the answer:
 *
 *     Zero records are attributed to you, and your export count is zero.
 *
 * The lesson was not "add zero to the list": a list of phrases guards phrases,
 * and the claim being guarded is a CLASS — an emptiness value applied to a
 * countable unit of the reader's work.
 *
 * GENERATION 2 — A CLASS MATCHER WITH A SENTENCE-WIDE ESCAPE. The replacement was
 * a whole-sentence OR: a trigger anywhere plus a modal token anywhere excused the
 * whole sentence. A second independent reviewer inserted, into the production
 * copy, and passed 117 files / 2697 vitest tests and all 8 browser tests:
 *
 *     You have no records, and this preview cannot tell you more than that.
 *     Nothing to show.
 *
 * `cannot` sat in the SECOND clause and excused the first — and this tab's whole
 * house voice is built from `would` / `cannot` / `rather than`, so the likeliest
 * copy edit on this surface was also the evasion. It could not be fixed by
 * editing the token list, because the legitimate copy "A count of zero WOULD say
 * you have no records" has exactly the same shape.
 *
 * The fix is therefore SCOPE, not vocabulary: the trigger and the escape are
 * evaluated together, PER CLAUSE. And the second sentence exposed a separate
 * regression — the class matcher had LOST `nothing to show`, which the retired
 * literal list caught. Measured, at 9494bdb: `Nothing to show.` → old literal
 * list `true`, class matcher `false`. That loss was invisible in the polarity
 * table because its `MUST_FLAG` entry ("Nothing to show — zero exports.") is
 * flagged by "zero exports" and not by the phrase. Hence
 * `retired literal parity` below: whenever a class matcher replaces a literal
 * list, assert the new one flags everything the old one did.
 */

/* >>> SHARED-EMPTINESS-MATCHER-START >>>
 *
 * THIS BLOCK EXISTS TWICE, BYTE FOR BYTE, between these two sentinels:
 * `src/__tests__/my-stats.test.tsx` (the authority) and
 * `e2e/specs/charts.spec.ts`. The two cannot share a module —
 * `tsconfig.app.json` includes only `src`, `e2e/tsconfig.json` is a separate
 * standalone project, and the production build must not depend on Playwright
 * types — so the lockstep is ASSERTED by `the two copies are byte-identical` in
 * `my-stats.test.tsx` rather than asked for in a comment. Edit both, or the
 * assertion fails.
 */

/** A quantity noun this tab could state a personal count of. */
const COUNT_NOUN = 'records?|experiments?|exports?|fields?|figures?|activity|drafts?|issues?|questions?|counts?';

/** The emptiness values a count can be given. */
const EMPTY_WORD = 'zero|none|nil|nought|naught|nothing|empty';

/** The reader, named. */
const PERSONAL = /\byou\b|\byour\b|\byours\b/i;

/**
 * Emptiness applied to a countable unit. A CLAIM ONLY WHERE THE READER IS NAMED,
 * because the class this file guards is "an emptiness value applied to a
 * countable unit of THE READER'S work" and the reader is part of that definition.
 *
 * That narrowing is deliberate and it has a cost worth stating: this tab really
 * does say, truthfully, "no record in this workspace carries an author" — a
 * WORKSPACE fact with no personal subject. Under a sentence-wide escape that
 * clause was excused by a `no way` three clauses later, which is an accident;
 * under clause scoping without this gate it would be reported, which is a false
 * positive on true copy. A workspace figure leaking onto this tab is trap 1's
 * job, and trap 1 forbids the import that would supply one.
 */
const PERSONAL_EMPTINESS: readonly RegExp[] = [
  // Prepositive: "no records", "zero records", "none of the figures",
  // "not a single record".
  new RegExp(
    `\\b(?:zero|none|nil|nought|naught|no|not a single)\\b(?:\\s+\\S+){0,2}?\\s+\\b(?:${COUNT_NOUN})\\b`,
    'i',
  ),
  // Postpositive: "your export count is zero", "your records number zero",
  // "your record count stands at zero", "your records list is empty".
  new RegExp(
    `\\b(?:${COUNT_NOUN})\\b[^.;]{0,40}?\\b(?:is|are|was|were|remains?|numbers?|stands?|sits?)\\b(?:\\s+at)?\\s+(?:${EMPTY_WORD})\\b`,
    'i',
  ),
];

/**
 * Forms that carry the reader inside the pattern, so they need no separate
 * personal gate — and that a count noun would miss.
 */
const NAMES_THE_READER: readonly RegExp[] = [
  // Negated-verb: "you have not authored any records", "you haven't exported any".
  new RegExp(
    `\\byou(?:r|rs)?\\b[^.;]{0,60}?\\b(?:not|never|n't)\\b[^.;]{0,40}?\\bany\\b(?:\\s+\\S+){0,2}?\\s+\\b(?:${COUNT_NOUN})\\b`,
    'i',
  ),
  // Direct personal predicate with NO count noun at all: "you have zero",
  // "you have authored nothing", "you have no work here".
  new RegExp(
    `\\byou\\b\\s+(?:have|has|had|hold|own)\\b(?:\\s+\\S+){0,2}?\\s+\\b(?:${EMPTY_WORD}|no)\\b`,
    'i',
  ),
  // Attribution: "nothing is attributed to you", "none of it belongs to you".
  // `you(?:rs)?` and not `you(?:r|rs)?`, so the honest "…rather than of your
  // work" is not swept in by the possessive.
  new RegExp(`\\b(?:${EMPTY_WORD})\\b[^.;]{0,40}?\\b(?:to|for|of)\\s+you(?:rs)?\\b`, 'i'),
];

/**
 * Emptiness with NO subject, which on a personal tab reads as personal anyway.
 * "Nothing to show." names nobody and means "you have nothing".
 *
 * The first two entries are the retired literal list's own idioms, kept as
 * literals on purpose: they have no grammatical subject for a class rule to bind
 * to. `there is nothing` is matched only at a clause end, so the tab's true
 * "there is nothing measured to read" is not swept in.
 */
const SUBJECTLESS_EMPTINESS: readonly RegExp[] = [
  /\bnothing\s+to\s+(?:show|see|display|report|list)\b/i,
  /\bthere\s+(?:is|are|was|were)\s+(?:none|nothing)\b(?=\s*[.;,!?]|$)/i,
  new RegExp(
    `\\bthere\\s+(?:is|are|was|were)\\s+(?:no|zero)\\b(?:\\s+\\S+){0,2}?\\s+\\b(?:${COUNT_NOUN})\\b`,
    'i',
  ),
];

/**
 * The one escape, and it is deliberately NOT plain negation.
 *
 * The tab's most important sentence is "A count of zero WOULD say you have no
 * records" — a hypothetical that denies the claim, and a page-wide ban on the
 * word would flag exactly the copy doing the honest work. So a triggered clause
 * passes only when IT — not some other clause of the same sentence — is framed as
 * a HYPOTHETICAL or as a statement about what this build CANNOT DO.
 *
 * `\bnot\b` is not in this list on purpose. It was the obvious escape and it is
 * a hole: "You have not exported any records" is a false personal claim that
 * wears a negation, which is why the negated-verb pattern exists and why the
 * frame has to be about modality rather than polarity.
 */
const DENIAL_FRAME = /\bwould\b|\bcannot\b|\bcan't\b|\bunable\b|\bno way\b|\brather than\b|\b(?:is|are) absent\b/i;

/**
 * A sentence's coordinate clauses. Split on the coordinators that join two
 * independent claims — `, and`, `, so`, `, but`, `, or`, `, yet`, `; ` — and NOT
 * on the em-dash, which on this surface introduces an appositive that continues
 * the same claim ("none of the figures below are zero — they are absent").
 */
function clausesOf(sentence: string): string[] {
  return sentence.split(/,\s+(?:and|but|so|or|yet)\s+|;\s+/i);
}

/** True when `clause` states that a countable unit of the reader's work is empty. */
function triggersEmptiness(clause: string): boolean {
  if (SUBJECTLESS_EMPTINESS.some((p) => p.test(clause))) return true;
  if (NAMES_THE_READER.some((p) => p.test(clause))) return true;
  return PERSONAL.test(clause) && PERSONAL_EMPTINESS.some((p) => p.test(clause));
}

/** Every CLAUSE of `text` that asserts the reader has nothing. */
function emptinessClaims(text: string): string[] {
  const claims: string[] = [];
  for (const sentence of text.split(/(?<=[.;])\s+/)) {
    for (const clause of clausesOf(sentence)) {
      if (triggersEmptiness(clause) && !DENIAL_FRAME.test(clause)) claims.push(clause.trim());
    }
  }
  return claims;
}

/** True when any clause of `sentence` asserts that the reader has nothing. */
function assertsEmptiness(sentence: string): boolean {
  return emptinessClaims(sentence).length > 0;
}

/* <<< SHARED-EMPTINESS-MATCHER-END <<< */

// --- the tablist ------------------------------------------------------------

describe('the two top-level tabs', () => {
  const tablist = () => screen.getByRole('tablist', { name: 'Statistics sections' });

  it('exposes exactly two tabs, in order, with General ISAAC selected by default', async () => {
    stubFetchRoutes(statisticsRoutes());
    renderAt(ROUTES.statistics);
    await screen.findByRole('heading', { name: 'Workspace at a Glance' });

    const tabs = within(tablist()).getAllByRole('tab');
    expect(tabs.map((t) => t.textContent)).toEqual(['General ISAAC', 'My Stats']);
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
    expect(tabs[1]).toHaveAttribute('aria-selected', 'false');
  });

  it('uses a roving tabindex — exactly one tab is in the tab order', async () => {
    stubFetchRoutes(statisticsRoutes());
    renderAt(ROUTES.statistics);
    await screen.findByRole('heading', { name: 'Workspace at a Glance' });

    const tabs = within(tablist()).getAllByRole('tab');
    expect(tabs.map((t) => t.tabIndex)).toEqual([0, -1]);
  });

  it('wires the selected tab to a rendered tabpanel, and the panel back to it', async () => {
    stubFetchRoutes(statisticsRoutes());
    renderAt(ROUTES.statistics);
    await screen.findByRole('heading', { name: 'Workspace at a Glance' });

    const selected = within(tablist()).getAllByRole('tab')[0];
    const panelId = selected.getAttribute('aria-controls');
    expect(panelId).toBe('statistics-tabpanel-general');
    const panel = document.getElementById(panelId!);
    expect(panel).toHaveAttribute('role', 'tabpanel');
    expect(panel).toHaveAttribute('aria-labelledby', selected.id);
    // `aria-controls` only on the SELECTED tab, matching the app's other tablists.
    expect(within(tablist()).getAllByRole('tab')[1].getAttribute('aria-controls')).toBeNull();
  });

  it('switches on ArrowRight and moves focus with the selection', async () => {
    stubFetchRoutes(statisticsRoutes());
    renderAt(ROUTES.statistics);
    await screen.findByRole('heading', { name: 'Workspace at a Glance' });

    const first = within(tablist()).getAllByRole('tab')[0];
    first.focus();
    fireEvent.keyDown(first, { key: 'ArrowRight' });

    const tabs = within(tablist()).getAllByRole('tab');
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true');
    expect(tabs[1]).toHaveFocus();
    await screen.findByRole('heading', { name: 'Personal Statistics' });
  });

  /*
   * DEEP-LINKING IS THE POINT, not a nicety. A tab held only in `useState` cannot
   * be linked to, bookmarked, or reloaded back into — and that exact defect
   * shipped once on Governance & Safety, where the Validator tab was unreachable
   * by link. Both directions are asserted: the URL selects the tab, and activating
   * the tab writes the URL.
   */
  it('is deep-linkable: ?tab=mine selects My Stats on arrival', async () => {
    await renderMineTab();
    const tabs = within(tablist()).getAllByRole('tab');
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true');
    expect(tabs[0]).toHaveAttribute('aria-selected', 'false');
  });

  it('an unrecognised ?tab= value falls back to General ISAAC without throwing', async () => {
    stubFetchRoutes(statisticsRoutes());
    renderAt(`${ROUTES.statistics}?tab=not-a-tab`);
    await screen.findByRole('heading', { name: 'Workspace at a Glance' });
    expect(within(tablist()).getAllByRole('tab')[0]).toHaveAttribute('aria-selected', 'true');
  });

  it('activating a tab writes the ?tab= value the route helper builds', async () => {
    stubFetchRoutes(statisticsRoutes());
    renderAt(ROUTES.statistics);
    await screen.findByRole('heading', { name: 'Workspace at a Glance' });

    fireEvent.click(within(tablist()).getAllByRole('tab', { name: 'My Stats' })[0]);
    await screen.findByRole('heading', { name: 'Personal Statistics' });
    expect(ROUTES.statisticsTab('mine')).toBe('/statistics?tab=mine');
  });

  it('declares its ids in one place, and the type guard agrees with them', () => {
    expect([...STATISTICS_TAB_IDS]).toEqual(['general', 'mine']);
    expect(isStatisticsTab('general')).toBe(true);
    expect(isStatisticsTab('mine')).toBe(true);
    for (const bad of ['General', '', null, undefined, 'general ']) {
      expect(isStatisticsTab(bad as string | null)).toBe(false);
    }
  });
});

// --- what belongs in which tab ---------------------------------------------

describe('the General ISAAC tab keeps the workspace material', () => {
  it('holds the three workspace sections and the privacy claim, and NOT the personal gate', async () => {
    stubFetchRoutes(statisticsRoutes());
    renderAt(ROUTES.statistics);
    await screen.findByRole('heading', { name: 'Workspace at a Glance' });

    for (const name of [
      'Workspace at a Glance',
      'Workflow Distribution',
      'Evidence and Validation',
      'This Application Collects No Analytics',
    ]) {
      expect(screen.getByRole('region', { name })).toBeInTheDocument();
    }
    expect(screen.queryByRole('heading', { name: 'Personal Statistics' })).toBeNull();
  });

  /*
   * THE PRIVACY CLAIM STAYS UNCOLLAPSED. Project Memory and the API surface moved
   * into a collapsed disclosure; this section did not, because it is a governance
   * claim about what the application measures, and a claim behind a disclosure is
   * a weaker claim.
   */
  it('leaves the no-analytics claim outside the collapsed region', async () => {
    stubFetchRoutes(statisticsRoutes());
    const { container } = renderAt(ROUTES.statistics);
    await screen.findByRole('heading', { name: 'Workspace at a Glance' });

    const section = container.querySelector('section[aria-labelledby="stats-no-analytics"]');
    expect(section).not.toBeNull();
    expect(section!.closest('details')).toBeNull();
  });

  it('collapses the build internals — runtime, Project Memory and the API surface — by default', async () => {
    stubFetchRoutes(statisticsRoutes());
    const { container } = renderAt(ROUTES.statistics);
    await screen.findByText('Synthetic-Only');

    const details = container.querySelector('details.stats-technical');
    expect(details).not.toBeNull();
    expect(details!.hasAttribute('open')).toBe(false);
    for (const name of ['Runtime', 'Project Memory', 'API Surface']) {
      expect(screen.getByRole('region', { name }).closest('details')).toBe(details);
    }
  });
});

// --- the six traps ----------------------------------------------------------

describe('My Stats invents no personal figure — the six traps', () => {
  /*
   * TRAP 1 — a workspace total relabelled as personal.
   *
   * The fixture serves five records whose derived totals are 5 / 2 / 1 / 1, and
   * `deriveWorkspaceTotals` sits one import away in `lib/statisticsModel.ts`. If
   * any of those numbers reached this tab it would be a false personal claim
   * built from a correct workspace one.
   */
  it('1 — states no workspace total, and imports the model that would supply one nowhere', async () => {
    const { container } = await renderMineTab();
    const panel = container.querySelector('#statistics-tabpanel-mine') as HTMLElement;
    const text = textOf(panel);

    expect(statisticsRecordsBody.total).toBe(5);
    for (const label of ['Total Records', 'Need Attention', 'Ready to Export', 'Exported']) {
      expect(text, `${label} must not appear on the personal tab`).not.toContain(label);
    }
    // No bare figure of any kind: no digit sequence stands as a statistic here.
    expect(text).not.toMatch(/\b\d+\b/);

    /*
     * …and the source of such a figure is not even IMPORTABLE from this module.
     * Matched against the module's import statements rather than its whole text,
     * because the header comment necessarily NAMES the module it must not import —
     * a substring scan would be satisfied by deleting the explanation.
     */
    const source = String((await import('../screens/statistics/MyStats?raw')).default);
    const imports = source.match(/^import[\s\S]*?from\s+'[^']+';$/gm) ?? [];
    expect(imports.length).toBeGreaterThan(2);
    for (const line of imports) {
      expect(line, 'My Stats must not import the workspace model').not.toContain(
        'statisticsModel',
      );
    }
    expect(source).not.toMatch(/\bderiveWorkspaceTotals\s*\(/);
  });

  /*
   * TRAP 2 — worked-example records presented as the reader's own. The strongest
   * form of this guard is that the tab issues no request at all: with no read,
   * there is no record set to mislabel, in any scope.
   */
  it('2 — issues NO request, so no record in any scope can be shown as personal', async () => {
    const { calls } = await renderMineTab();
    /*
     * The four General-tab reads still happen on mount (they are not tab-keyed),
     * and NOTHING else does. `stubFetchRoutes` records each call as
     * `"<METHOD> <path>"`, so this asserts the method too — every request is a GET,
     * and this tab therefore cannot mutate anything either.
     *
     * THE MULTISET, NOT THE SET. This was `new Set(calls)`, which de-duplicates —
     * so a SECOND read of an already-fetched path was undetectable. An independent
     * reviewer added a bare `void api.getRuntimeRecords();` to `MyStats` (the
     * realistic wrong implementation, since nothing on this surface writes
     * `fetch(` by hand) and this trap passed. Sorted, so the assertion is about
     * WHICH calls and HOW MANY, not about mount order, which React may legally
     * change.
     */
    expect([...calls].sort()).toEqual(
      [
        'GET /api/about',
        'GET /api/graph/status',
        'GET /api/openapi',
        'GET /api/runtime/records',
      ].sort(),
    );
    expect(calls.filter((c) => c.includes('/api/experiments'))).toEqual([]);
    expect(calls.filter((c) => c.includes('/api/demo'))).toEqual([]);
  });

  /** TRAP 3 — a portal-wide metric. Nothing here names or reads a portal. */
  it('3 — names no portal, database or cross-user metric', async () => {
    const { container } = await renderMineTab();
    const text = textOf(container.querySelector('#statistics-tabpanel-mine') as HTMLElement);
    for (const word of ['portal', 'Postgres', 'PostgreSQL', 'database', 'everyone', 'all users']) {
      expect(text.toLowerCase()).not.toContain(word.toLowerCase());
    }
  });

  /*
   * TRAP 4 — the fake zero, and the one this tab most had to be designed against.
   * "0 records" is not a neutral placeholder: it asserts that the reader has no
   * activity. The truth is that this build cannot attribute activity to anyone,
   * and the copy has to say THAT.
   */
  it('4 — renders no zero, in digits OR IN WORDS, and says explicitly that absence is not zero', async () => {
    const { container } = await renderMineTab();
    const panel = container.querySelector('#statistics-tabpanel-mine') as HTMLElement;
    const text = textOf(panel);

    expect(text).not.toMatch(/\b0\b/);
    expect(text).toMatch(/none of the figures below are zero — they are absent/);
    expect(text).toMatch(/cannot tell whose records these are/);

    /*
     * …and NO CLAUSE ASSERTS THAT THE READER HAS NOTHING — in digits or in words.
     * Checked per clause, with the modal escape documented above, so the sentences
     * that legitimately DENY a zero stay legal while a clause that states one
     * cannot borrow the denial from its neighbour.
     *
     * The whole set is reported rather than the first match, so a copy edit that
     * introduces two says so once.
     */
    expect(
      emptinessClaims(text),
      'a clause on the personal tab asserts the reader has nothing; this build cannot know that',
    ).toEqual([]);

    /*
     * …AND THE GUARD BITES ON THIS TAB'S OWN RENDERED COPY, proved by mutating
     * that copy rather than by counting how many honest sentences happen to trip
     * the trigger.
     *
     * The previous form of this check was `triggered.length >= 3` plus "every
     * triggered sentence is modally framed". Both are satisfied by "everything
     * matched and everything was excused" — which is precisely the state a
     * sentence-wide escape is in when it lets a false clause through, so the
     * check could not distinguish the design from the defect. These two mutations
     * can only pass if the trigger reaches real rendered text AND the escape is
     * what excuses it AND the escape is scoped to the clause.
     *
     * Mutation 1: delete ONE modal word from the tab's own zero-denying sentence.
     */
    const withoutModal = text.replace(
      'A count of zero would say you have no records',
      'A count of zero says you have no records',
    );
    expect(withoutModal, 'mutation 1 must actually apply to the rendered text').not.toBe(text);
    expect(emptinessClaims(withoutModal)).toEqual(['A count of zero says you have no records;']);

    /*
     * Mutation 2: append the exact two sentences the second independent reviewer
     * inserted into `MyStats.tsx` above the actions row. Both passed the whole
     * suite at 9494bdb. The first is the clause-scope evasion; the second is the
     * phrase the class matcher had lost from the retired literal list.
     */
    const reviewerInsertion =
      'You have no records, and this preview cannot tell you more than that. Nothing to show.';
    expect(emptinessClaims(`${text} ${reviewerInsertion}`)).toEqual([
      'You have no records',
      'Nothing to show.',
    ]);
  });

  /*
   * TRAP 5 — a skeleton left behind. There is no loading state on this tab because
   * there is nothing to load, so no placeholder can survive a resolve that never
   * happens. Asserted as the absence of BOTH a status region and any drawn plot.
   */
  it('5 — has no loading state and no chart skeleton, drawn or otherwise', async () => {
    const { container } = await renderMineTab();
    const panel = container.querySelector('#statistics-tabpanel-mine') as HTMLElement;
    expect(panel.querySelector('[role="status"]')).toBeNull();
    expect(panel.querySelector('figure.stats-chart')).toBeNull();
    expect(panel.querySelector('svg.stats-chart-columns')).toBeNull();
    expect(panel.querySelector('.stats-chart-track')).toBeNull();
    expect(panel.querySelector('.stats-chart-grid')).toBeNull();
    // No axis, no ticks, no empty plot of any kind. The only SVGs are the
    // section's decorative heading glyphs.
    for (const svg of panel.querySelectorAll('svg')) {
      expect(svg.closest('.stats-card-icon')).not.toBeNull();
    }
  });

  /*
   * TRAP 6 — header-derived identity. `docs/identity-trust-contract.md` §6A
   * records that two of the seven candidate identity headers arrive carrying
   * whatever a CLIENT chose to send, so no header may name the reader — not even
   * as a greeting.
   */
  it('6 — displays no identity, and the module reads no header', async () => {
    const { container } = await renderMineTab();
    const text = textOf(container.querySelector('#statistics-tabpanel-mine') as HTMLElement);
    expect(text).not.toMatch(/signed in as|@|Signed in|Hello|Welcome back/i);

    const source = String((await import('../screens/statistics/MyStats?raw')).default);
    const contract = String((await import('../lib/myStatsContract?raw')).default);
    for (const [name, module] of [
      ['MyStats.tsx', source],
      ['myStatsContract.ts', contract],
    ] as const) {
      // No header read, and no fetch of any kind, in either module. `X-authentik`
      // appears only inside the prose that explains why it must not be used.
      expect(module, name).not.toMatch(/headers\s*[.[]/);
      expect(module, name).not.toMatch(/\bfetch\s*\(/);
      expect(module, name).not.toMatch(/getHeader|request\.headers/);

      /*
       * …AND NO REQUEST THROUGH THIS APP'S OWN CLIENT, which is the form the
       * defect would actually take. The `/\bfetch\s*\(/` scan above is a source
       * scan for a call NOTHING on this surface makes by hand: every read in this
       * app goes through `lib/api.ts`'s `api` object, so a reviewer's
       * `void api.getRuntimeRecords();` was invisible to it — and to trap 2, which
       * de-duplicated its call list. Both holes are closed; this is the one that
       * closes it at the source rather than at the call log.
       *
       * Neither module contains the substring `api.` in prose (checked), so this
       * needs no comment stripping.
       */
      expect(module, `${name} must not call this app's API client`).not.toMatch(/\bapi\s*\.\s*[a-zA-Z]/);
      expect(module, `${name} must not open a transport of its own`).not.toMatch(
        /XMLHttpRequest|EventSource|sendBeacon|WebSocket|\bimport\s*\(/,
      );

      // …and it cannot even IMPORT the client. Matched against the import
      // statements, per trap 1's reasoning: a whole-text scan would be satisfied
      // by deleting the explanation rather than the dependency.
      // (`myStatsContract.ts` imports NOTHING at all, which is the strongest
      // possible form of this and is asserted as such.)
      const imports = module.match(/^import[\s\S]*?from\s+'[^']+';$/gm) ?? [];
      for (const line of imports) {
        expect(line, `${name} must not import the API client`).not.toMatch(/lib\/api'|\/api'$/);
      }
      if (name === 'myStatsContract.ts') expect(imports).toEqual([]);
    }
  });
});

// --- the matcher itself -----------------------------------------------------

/**
 * THE GUARD, GUARDED. Polarity is pinned in both directions against worked
 * examples, because a matcher that flags nothing passes every test above.
 *
 * The list is ordered by generation, and every entry after the first eight was
 * MEASURED to pass at some point:
 *
 *   · entries 1–8 predate the class matcher — entry 1 is the sentence generation
 *     1's digit-shaped guards let through;
 *   · entries 9–10 are the exact two sentences a SECOND independent reviewer
 *     inserted into `MyStats.tsx` production copy at 9494bdb, which passed
 *     117 files / 2697 vitest tests and all 8 browser tests in
 *     `e2e/specs/charts.spec.ts` — including the one titled "renders the gate,
 *     and no chart, no skeleton and no zero";
 *   · entries 11–16 are six further sentences the reviewer measured as passing
 *     the sentence-wide escape, re-measured here before being listed;
 *   · entries 17–20 are the four the class matcher lost relative to the two
 *     narrower guards it replaced.
 */
describe('the emptiness matcher', () => {
  const MUST_FLAG: readonly string[] = [
    // 1–8 · the original table.
    'Zero records are attributed to you, and your export count is zero.',
    'You have no records.',
    'Your export count is zero.',
    'No records are attributed to you.',
    'You have not authored any records.',
    'Nothing to show — zero exports.',
    'Your evidence fields are none.',
    'There are no experiments of yours in this workspace.',
    // 9–10 · the second reviewer's insertion, verbatim.
    'You have no records, and this preview cannot tell you more than that.',
    'Nothing to show.',
    // 11–16 · measured to pass the sentence-wide escape.
    'Nothing is attributed to you.',
    'Your records list is empty.',
    'Not a single record is attributed to you.',
    'You have authored nothing.',
    'Your record count stands at zero.',
    'Your records number zero.',
    // 17–20 · lost when the class matcher replaced the two narrower guards.
    'There are none.',
    'There is none.',
    'You have zero.',
    'You have no work here.',
  ];

  /** The tab's real copy. Every one of these is TRUE and must stay sayable. */
  const MUST_PASS: readonly string[] = [
    'A count of zero would say you have no records;',
    'Nothing on this tab is hidden from you, and none of the figures below are zero — they are absent.',
    'Two things are missing today, and both are properties of this preview rather than of your work: nothing here establishes who you are, and no record in this workspace carries an author, so there is no way to select the records that are yours.',
    'It is not showing zero — it has no way to select your records at all.',
    'what is true is that this build cannot tell whose records these are.',
    'None of them is drawing anything right now.',
    'Records in this preview are not associated with an account, so this view cannot tell which of them are yours.',
    'how many records you author sit at each step of the five-step workflow, counted once each at their first unsatisfied step.',
    // The `not_recorded` sentence, which is the closest true copy to a false one:
    // "there is nothing measured to read" is emptiness about the BUILD's records
    // of activity, not about the reader's work, and the subjectless idiom is
    // deliberately anchored to a clause end so this is not swept in.
    'Nothing is being withheld; there is nothing measured to read.',
    'This view needs a signed-in account, and this preview has none, so there is nobody to describe.',
  ];

  it.each(MUST_FLAG)('flags a false personal zero: %s', (sentence) => {
    expect(assertsEmptiness(sentence)).toBe(true);
  });

  it.each(MUST_PASS)('leaves the honest copy alone: %s', (sentence) => {
    expect(assertsEmptiness(sentence)).toBe(false);
  });

  it('rejects plain negation as a frame — "not" is not an escape', () => {
    // The hole the first version of this escape had. "not" reads as a denial and
    // is not one: it is exactly how an emptiness ASSERTION is normally phrased.
    expect(DENIAL_FRAME.test('You have not exported any records.')).toBe(false);
    expect(assertsEmptiness('You have not exported any records.')).toBe(true);
  });

  /*
   * SCOPE, NOT VOCABULARY. The generation-2 hole was that a modal token anywhere
   * in a sentence excused a trigger anywhere else in it. These four pairs differ
   * ONLY in whether the modal governs the trigger's own clause, so they cannot
   * both pass unless the escape is clause-scoped.
   */
  it.each([
    ['You have no records, and this preview cannot tell you more than that.', 'A count of zero would say you have no records.'],
    ['Your export count is zero, so nothing further can be shown.', 'Your export count would be zero, which is not what this says.'],
    ['You have not authored any records; this preview is unable to say more.', 'It would be false to say you have not authored any records.'],
    ['Nothing is attributed to you, and that cannot be established here.', 'Nothing would be attributed to you rather than to an account.'],
  ])('an escape in ANOTHER clause does not excuse: %s', (claim, denial) => {
    expect(assertsEmptiness(claim), `must be FLAGGED: ${claim}`).toBe(true);
    expect(assertsEmptiness(denial), `must PASS: ${denial}`).toBe(false);
  });

  /*
   * RETIRED LITERAL PARITY.
   *
   * The class matcher replaced this per-sentence filter:
   *
   *     /no records|no activity|nothing to show/i
   *
   * and silently lost one of its three phrases. Measured at 9494bdb:
   * `Nothing to show.` → retired list `true`, class matcher `false`. The loss was
   * invisible in the table above because the entry that looks like it covers the
   * phrase ("Nothing to show — zero exports.") is flagged by "zero exports".
   *
   * So the retired literals get their own explicit assertion. WHENEVER A CLASS
   * MATCHER REPLACES A LITERAL LIST, ASSERT THE NEW ONE FLAGS EVERYTHING THE OLD
   * ONE DID.
   *
   * One honest exception is recorded rather than hidden: the retired list fired
   * on any sentence containing the substring, including impersonal ones like
   * "this build has no records", which the class matcher deliberately does not
   * flag — see `PERSONAL_EMPTINESS`. Each literal is therefore exercised in the
   * personal form this tab could actually state it in.
   */
  const RETIRED_LITERAL_SENTENCES: readonly [string, string][] = [
    ['no records', 'You have no records.'],
    ['no activity', 'There is no activity on your account.'],
    ['nothing to show', 'Nothing to show.'],
  ];

  it.each(RETIRED_LITERAL_SENTENCES)(
    'still flags what the retired literal list caught: %s',
    (literal, sentence) => {
      expect(sentence.toLowerCase(), 'the fixture must contain the retired literal').toContain(
        literal,
      );
      expect(assertsEmptiness(sentence)).toBe(true);
    },
  );

  /*
   * THE LOCKSTEP, TESTED RATHER THAN REQUESTED.
   *
   * `e2e/specs/charts.spec.ts` carries the same matcher, because the two suites
   * cannot share a module (`tsconfig.app.json` includes only `src`;
   * `e2e/tsconfig.json` is a separate standalone project; the production build
   * must not depend on Playwright types). That file used to say "Keep them in
   * lockstep" in a comment — and they then drifted in the way this whole
   * describe-block exists to prevent, because a comment cannot fail.
   *
   * Both copies are delimited by the same sentinels and compared byte for byte.
   */
  it('the two copies are byte-identical — the browser suite is in lockstep', async () => {
    const START = '/* >>> SHARED-EMPTINESS-MATCHER-START >>>';
    const END = '/* <<< SHARED-EMPTINESS-MATCHER-END <<< */';

    function sharedBlock(raw: string, where: string): string {
      const from = raw.indexOf(START);
      const to = raw.indexOf(END);
      expect(from, `${where} must carry the start sentinel`).toBeGreaterThanOrEqual(0);
      expect(to, `${where} must carry the end sentinel after the start`).toBeGreaterThan(from);
      return raw.slice(from, to + END.length);
    }

    const here = sharedBlock(
      String((await import('./my-stats.test.tsx?raw')).default),
      'my-stats.test.tsx',
    );
    const there = sharedBlock(
      String((await import('../../e2e/specs/charts.spec.ts?raw')).default),
      'e2e/specs/charts.spec.ts',
    );

    // Vacuity guard: the block must be the real thing, not two empty slices.
    expect(here).toContain('function emptinessClaims');
    expect(here).toContain('SUBJECTLESS_EMPTINESS');
    expect(here.length).toBeGreaterThan(2000);
    expect(there, 'the browser copy of the emptiness matcher has drifted').toBe(here);
  });
});

// --- the gate itself --------------------------------------------------------

describe('the gated state', () => {
  it('states the reason the adapter reported, not a hard-coded sentence', async () => {
    await renderMineTab();
    // `workflow_counts` waits on record ownership, so THAT is the sentence shown —
    // not the signed-in-account one and not the not-recorded one.
    expect(MY_STATS_PENDING_REASON.workflow_counts).toBe('no_record_ownership');
    expect(screen.getByText(MY_STATS_PENDING_COPY.no_record_ownership)).toBeInTheDocument();
    expect(screen.queryByText(MY_STATS_PENDING_COPY.no_signed_in_account)).toBeNull();
  });

  it('renders whatever a DIFFERENT source reports, so the boundary is real', () => {
    const unavailable: MyStatsSource = {
      ...unconfiguredMyStatsSource,
      id: 'test-double',
      workflowCounts: () => ({ status: 'unavailable', message: 'The personal source failed.' }),
    };
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <MyStats source={unavailable} />
      </MemoryRouter>,
    );
    expect(screen.getByText('The personal source failed.')).toBeInTheDocument();
  });

  /*
   * A `ready` payload has NO view here, and the tab says so rather than drawing
   * one. Speculative branches for payloads no adapter produces are how a
   * placeholder chart gets shipped.
   */
  it('a ready payload draws nothing and names the state it received', () => {
    const ready: MyStatsSource = {
      ...unconfiguredMyStatsSource,
      id: 'test-double',
      workflowCounts: () => ({
        status: 'ready',
        data: { byStep: [{ key: 'export', label: 'Export', count: 3 }], recordsCounted: 3 },
      }),
    };
    const { container } = render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <MyStats source={ready} />
      </MemoryRouter>,
    );
    expect(screen.getByText(/reported "ready", and this preview has no view built for it/)).toBeInTheDocument();
    expect(container.querySelector('figure.stats-chart')).toBeNull();
    // The payload's own figure never reaches the DOM.
    expect(textOf(container)).not.toContain('Export 3');
  });

  /*
   * THE PAGE LEAD IS PART OF THIS TAB'S CLAIM SURFACE, even though it renders
   * outside the panel.
   *
   * It sits directly above the tablist, so on `?tab=mine` it was reading as a
   * promise about the panel below it while naming four sections that are on the
   * OTHER tab — workflow readiness, evidence, Project Memory and the API surface.
   * `StatisticsPage.tsx` recorded that as deliberate; it is now tab-scoped, and
   * this is the assertion that keeps it so.
   *
   * The emptiness rule is applied here too, because the lead is the one piece of
   * copy on this tab that trap 4's panel-scoped guard cannot see.
   */
  it('the page lead describes THIS tab, not the sections on the other one', async () => {
    const { container } = await renderMineTab();
    const lead = container.querySelector('.placeholder > p') as HTMLElement;
    expect(lead, 'the page lead must exist').not.toBeNull();
    const text = textOf(lead);

    for (const promise of ['workflow readiness', 'evidence', 'Project Memory', 'API surface']) {
      expect(text, `the My Stats lead must not promise ${promise}`).not.toContain(promise);
    }
    // …nor name a workspace: this tab reads nothing in either scope, so a
    // workspace clause would imply the gate depends on which one is open.
    expect(text).not.toMatch(/workspace/i);
    expect(text).toContain('cannot tell whose records these are');
    expect(emptinessClaims(text)).toEqual([]);
    expect(text).not.toMatch(/\b\d+\b/);
  });

  /*
   * …AND IT DOES NOT REPEAT A SECTION SUBTITLE.
   *
   * The lead's first sentence used to be byte-identical to the `stats-mine-gate`
   * section's `sub`, which renders a few lines below it in the same viewport —
   * the same sentence twice, which is not emphasis. The duplicate was removed
   * from the LEAD, because the subtitle is the component's own self-description
   * and is the only place that sentence appears when `MyStats` is mounted alone.
   *
   * Compared per SENTENCE rather than as whole strings, so a lead that merely
   * embeds the subtitle inside a longer paragraph is caught too.
   */
  it('the page lead does not repeat a section subtitle', async () => {
    const { container } = await renderMineTab();
    const sentencesOf = (el: HTMLElement) =>
      textOf(el)
        .split(/(?<=[.;])\s+/)
        .map((s) => s.trim())
        .filter((s) => s.length > 12);

    const lead = sentencesOf(container.querySelector('.placeholder > p') as HTMLElement);
    expect(lead.length, 'the lead must have at least one sentence').toBeGreaterThan(0);

    const subs = [...container.querySelectorAll('p.stats-card-sub')] as HTMLElement[];
    expect(subs.length, 'the panel must render section subtitles to compare against').toBe(2);

    for (const sub of subs) {
      for (const sentence of sentencesOf(sub)) {
        expect(lead, `the page lead repeats a section subtitle: "${sentence}"`).not.toContain(
          sentence,
        );
      }
    }
  });

  it('offers a route back to the workspace figures and to the privacy settings', async () => {
    await renderMineTab();
    expect(screen.getByRole('link', { name: 'See Workspace Statistics' })).toHaveAttribute(
      'href',
      '/statistics?tab=general',
    );
    expect(screen.getByRole('link', { name: 'Open Data & Privacy Settings' })).toHaveAttribute(
      'href',
      ROUTES.settingsTab('privacy'),
    );
  });
});

// --- the planned views -----------------------------------------------------

describe('the planned views describe a shape without asserting a figure', () => {
  it('lists all eight, each with a title, a description, a form and a gate marker', async () => {
    await renderMineTab();
    expect(MY_STATS_VIEWS).toHaveLength(8);

    for (const view of MY_STATS_VIEWS) {
      const heading = screen.getByRole('heading', { level: 3, name: view.title });
      const card = heading.closest('.stats-plan-card') as HTMLElement;
      expect(card, `${view.id} must render a card`).not.toBeNull();
      const text = textOf(card);
      expect(text).toContain(view.description);
      // One string, not an interpolation split across text nodes — see the
      // `stats-plan-form` note in `MyStats.tsx`.
      expect(card.querySelector('.stats-plan-form')?.textContent).toBe(
        `Will render as a ${view.form}.`,
      );
      expect(text).toContain(MY_STATS_PENDING_LABEL[MY_STATS_PENDING_REASON[view.id]]);
    }
  });

  it('every description names the unit it would count', async () => {
    // The conflation this guards is records-versus-fields, which is the same one
    // `EvidenceTotals` keeps apart with `totalFields` beside `recordsCounted`.
    for (const view of MY_STATS_VIEWS) {
      expect(
        /\brecords?\b|\bfields\b|\bissues\b|\bchanges\b/.test(view.description),
        `${view.id} must name its unit: "${view.description}"`,
      ).toBe(true);
    }
  });

  it('states no count anywhere in the planned-view grid', async () => {
    const { container } = await renderMineTab();
    const grid = container.querySelector('.stats-plan-grid') as HTMLElement;
    expect(grid).not.toBeNull();
    expect(textOf(grid)).not.toMatch(/\b\d+\b/);
  });
});

// --- the adapter -----------------------------------------------------------

describe('unconfiguredMyStatsSource', () => {
  const methods = [
    'workflowCounts',
    'readinessTrend',
    'validationIssuesOverTime',
    'evidenceSupportDistribution',
    'exportsOverTime',
    'commonBlockers',
    'recentActivity',
    'ownedVsCollaborated',
  ] as const;

  it('answers access_pending for all eight datasets, with a declared reason', () => {
    for (const method of methods) {
      const state = unconfiguredMyStatsSource[method]();
      expect(state.status, method).toBe('access_pending');
      if (state.status !== 'access_pending') throw new Error('unreachable');
      expect(
        ['no_signed_in_account', 'no_record_ownership', 'not_recorded'],
        method,
      ).toContain(state.reason);
    }
  });

  it('covers every dataset id — a new one cannot arrive with no method', () => {
    expect(methods).toHaveLength(Object.keys(MY_STATS_PENDING_REASON).length);
    expect(MY_STATS_VIEWS.map((v) => v.id).sort()).toEqual(
      Object.keys(MY_STATS_PENDING_REASON).sort(),
    );
  });

  it('is frozen, so nothing can swap a dataset in at runtime', () => {
    expect(Object.isFrozen(unconfiguredMyStatsSource)).toBe(true);
    expect(Object.isFrozen(MY_STATS_PENDING_REASON)).toBe(true);
    expect(Object.isFrozen(MY_STATS_VIEWS)).toBe(true);
  });

  it('every pending sentence blames the application, never the reader', () => {
    for (const [reason, copy] of Object.entries(MY_STATS_PENDING_COPY)) {
      expect(copy.length, reason).toBeGreaterThan(40);
      /*
       * No sentence tells the reader they have nothing. The word "zero" IS
       * allowed, and one sentence uses it — "It is not showing zero" — because
       * denying the zero is the point; what is forbidden is asserting one.
       *
       * ONE DEFINITION FOR BOTH SURFACES. This used to be its own pattern —
       * `(you have|there are|there is) (no|none|zero)` — while the RENDERED panel
       * was guarded only by digit shapes. Two definitions of one rule, and only
       * the constants here were covered by the stricter of the two;
       * `assertsEmptiness` is now the single definition, applied to these
       * constants and to the rendered panel in trap 4.
       *
       * BUT THE FIRST UNIFICATION WAS PARTLY A LOSS, and the comment that
       * replaced this one called the retired pattern "the weaker one", which was
       * not measured and was wrong. Measured at 9494bdb, the class matcher did NOT
       * flag four sentences this pattern did: `There are none.` ·
       * `There is none.` · `You have zero.` · `You have no work here.` — none of
       * which names a count noun, which is what the class rule was keyed on. All
       * four are in `MUST_FLAG` (entries 17–20) and are now covered by
       * `NAMES_THE_READER` and `SUBJECTLESS_EMPTINESS`.
       *
       * The honest summary is that the current matcher is a superset of the
       * retired pattern on every PERSONAL form, and deliberately narrower on
       * impersonal ones — see `PERSONAL_EMPTINESS` for why, and
       * `retired literal parity` for the assertion.
       */
      expect(emptinessClaims(copy), reason).toEqual([]);
      expect(copy, reason).not.toMatch(/\b0\b/);
      expect(copy, reason).toMatch(/this (preview|view)/i);
    }
  });

  /*
   * …and the same rule over every other string this module hands the tab. The
   * pending copy was guarded and the view descriptions were not, which is the
   * same asymmetry one level down.
   */
  it('no view title, description or gate label asserts an emptiness either', () => {
    for (const view of MY_STATS_VIEWS) {
      expect(emptinessClaims(view.title), view.id).toEqual([]);
      expect(emptinessClaims(view.description), view.id).toEqual([]);
    }
    for (const [reason, label] of Object.entries(MY_STATS_PENDING_LABEL)) {
      expect(emptinessClaims(label), reason).toEqual([]);
    }
  });
});

// --- switching tabs does not re-read --------------------------------------

describe('switching tabs is free', () => {
  it('issues no additional request when the reader moves between tabs', async () => {
    const calls = stubFetchRoutes(statisticsRoutes());
    renderAt(ROUTES.statistics);
    await screen.findByText('Synthetic-Only');
    const afterLoad = calls.length;

    const tablist = screen.getByRole('tablist', { name: 'Statistics sections' });
    fireEvent.click(within(tablist).getByRole('tab', { name: 'My Stats' }));
    await screen.findByRole('heading', { name: 'Personal Statistics' });
    fireEvent.click(within(tablist).getByRole('tab', { name: 'General ISAAC' }));
    await screen.findByRole('heading', { name: 'Workspace at a Glance' });

    await waitFor(() => expect(calls.length).toBe(afterLoad));
  });
});
