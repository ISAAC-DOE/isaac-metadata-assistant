/**
 * The Statistics visualization system, in a real browser.
 * @responsive
 *
 * ── Why this cannot be a jsdom test ────────────────────────────────────────
 *
 * Every chart on the Statistics surface measures its own plot column — a direct
 * `getBoundingClientRect()` read at mount, plus a `ResizeObserver` for later
 * changes — and renders SVG at 1:1 pixel scale. jsdom has neither layout (its
 * `getBoundingClientRect` returns 0, which the hook ignores) nor
 * `ResizeObserver`, so the vitest suite necessarily renders at the hook's
 * documented fallback width and can prove nothing about real geometry.
 * Four things are therefore only checkable here, and all four are the ones that
 * actually break:
 *
 *   1. the plot really fills the width it was given, at every viewport;
 *   2. no chart forces two-dimensional scrolling — the page never scrolls
 *      sideways, and a wide block scrolls INSIDE its own container;
 *   3. the axis band is inside the chart's box, so no card grows a tiny nested
 *      vertical scroll around clipped tick labels;
 *   4. the text equivalents survive at 375px and at 200% zoom, where a naive
 *      implementation drops the table or clips the summary.
 *
 * Both Statistics scopes are covered. The ORDINARY workspace is permanently
 * empty, so it draws no chart at all — which is itself an assertion worth making
 * (an empty workspace must not draw an empty axis). The populated charts exist
 * only inside a worked-example session.
 */

import { expect, test } from '../fixtures';
import { SURFACES } from '../surfaces';

const STATISTICS_EXAMPLE = SURFACES.find((s) => s.id === 'statistics-example')!;
const STATISTICS_ORDINARY = SURFACES.find((s) => s.id === 'statistics')!;
const STATISTICS_MINE = SURFACES.find((s) => s.id === 'statistics-mine')!;

/*
 * ── the My Stats copy guard, duplicated from `src/__tests__/my-stats.test.tsx` ──
 *
 * TWO LAYERS, and the first is the one that matters: an ALLOWLIST OF APPROVED
 * SENTENCES compared as an exact set, with the emptiness matcher demoted to a
 * second layer over that allowlist's own entries. The reasoning is inside the
 * block; the short version is that three generations of pattern-shaped guard were
 * each defeated by punctuation, the third by deleting one comma.
 *
 * `src/__tests__/my-stats.test.tsx` is the AUTHORITY: it carries the
 * two-directional polarity table, the clause-scope and denial-position pairs, the
 * retired-literal parity assertion, the fourteen measured evasions, and the record
 * of all three generations. This is a byte-identical copy, and the lockstep is a
 * TEST there ("the two copies are byte-identical") rather than the
 * request-in-a-comment it used to be — the older version of this block said "Keep
 * them in lockstep", and a comment cannot fail.
 *
 * Declared at module scope, not inside the test, so the two blocks are identical
 * down to the indentation.
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

/* ══ LAYER 1 · THE APPROVED SENTENCES ═══════════════════════════════════════
 *
 * WHY THE ENFORCEMENT POINT MOVED. Three generations of this guard were an
 * ALLOWLIST OF SYNTAX, and each was defeated by one syntactic route:
 *
 *   1. a three-phrase literal list      → a phrase that was not in it;
 *   2. a whole-sentence modal escape    → a conjoined clause, so `cannot`
 *                                         anywhere excused a zero anywhere;
 *   3. a clause splitter over five      → DELETING ONE COMMA. Generation 2's own
 *      joiners (`, and|but|so|or|yet`,    example sentence, comma removed, was
 *      `; `)                              rendered in the panel and passed ALL 231
 *                                         tests of the five statistics vitest
 *                                         files — 71 of them in
 *                                         `my-stats.test.tsx` — and ALL 40 browser
 *                                         tests in `charts.spec.ts`. Re-measured
 *                                         at 4b86f7e before this was written.
 *
 * A guard shaped like an allowlist of joiners will keep losing, because the set
 * of ways English joins two clauses is open and the set of ways a maintainer can
 * write one is larger still. So the PRIMARY guard is no longer a pattern over
 * free prose. It is EXACT SET EQUALITY between the sentences this tab renders and
 * the two lists below.
 *
 * The consequence is the point: inserting ANY new sentence into the panel fails
 * immediately — false or true, punctuated any way at all, because nothing is
 * being parsed for meaning. Editing an approved sentence fails until the list is
 * updated, which puts the changed claim in the diff.
 *
 * HOW A LEGITIMATE COPY CHANGE PROCEEDS. Edit the copy; the set test fails and
 * prints the difference; transcribe the new sentence into the list below IN THE
 * SAME COMMIT. That transcription is the moment honesty is judged — by layer 2,
 * which is applied to these entries, and by whoever reads the diff. There is no
 * way to change what this tab says without the new sentence appearing here.
 *
 * WHAT IS COMPARED. Every text NODE of the subtree, plus every accessible-name
 * attribute on it (see {@link ACCESSIBLE_NAME_ATTRS}) — an `aria-label` is copy a
 * reader is read out, and a guard over text nodes alone would not see it. Each
 * unit is whitespace-normalised and split into sentences, and the UNIQUE set is
 * compared, sorted, in full.
 *
 * UNIQUE, NOT A MULTISET, and that is a deliberate weakening of one edge: five
 * planned views share the gate label `Needs records linked to an account.`, and
 * three share `Will render as a line chart.`, so a multiset would pin how many
 * views happen to sit behind each precondition and would fail on a re-labelling
 * that says nothing new. Repeating a sentence that is already approved states no
 * new claim; saying anything else does, and that is what is caught.
 */

/** Attributes that put copy into the accessible name, and so into the claim set. */
const ACCESSIBLE_NAME_ATTRS: readonly string[] = [
  'aria-label',
  'aria-description',
  'aria-roledescription',
  'aria-valuetext',
  'aria-placeholder',
  'title',
  'alt',
];

/**
 * EVERY SENTENCE THE MY STATS PANEL MAY RENDER. Nothing else may appear in
 * `#statistics-tabpanel-mine`.
 *
 * Transcribed from the rendered DOM, not imported from
 * `lib/myStatsContract.ts` — deriving this list from the constants the panel
 * renders would make the comparison circular and it would pass whatever the
 * panel said. The duplication is the mechanism.
 */
const APPROVED_PANEL_SENTENCES: readonly string[] = [
  'Personal Statistics',
  'What this tab will show once records are associated with a signed-in account.',
  'Not Available in This Preview',
  'Records in this preview are not associated with an account, so this view cannot tell which of them are yours.',
  'It is not showing zero — it has no way to select your records at all.',
  'Personal statistics will appear here once experiments are associated with your signed-in account.',
  'Two things are missing today, and both are properties of this preview rather than of your work: nothing here establishes who you are, and no record in this workspace carries an author, so there is no way to select the records that are yours.',
  'Nothing on this tab is hidden from you, and none of the figures below are zero — they are absent.',
  'A count of zero would say you have no records;',
  'what is true is that this build cannot tell whose records these are.',
  'Open Data & Privacy Settings',
  'See Workspace Statistics',
  'Views Prepared for Your Account',
  'Each view below is defined as a typed dataset, so it can be filled in without changing this page\'s layout.',
  'None of them is drawing anything right now.',
  'Records You Author, by Workflow Step',
  'how many records you author sit at each step of the five-step workflow, counted once each at their first unsatisfied step.',
  'Will render as a bar chart.',
  'Needs records linked to an account.',
  'Evidence Support in Records You Author',
  'what share of the fields in records you author is supported by evidence, counted in fields rather than in records.',
  'Will render as a stacked bar.',
  'Records You Authored and Records You Contributed To',
  'how many records name you as their author, and how many you contributed to without authoring.',
  'A record can be both, so the two are never added together.',
  'Will render as a comparison rows.',
  'What Most Often Blocks Records You Author',
  'which unmet requirements appear most often across the records you author.',
  'One record can carry several, so these do not sum to a record count.',
  'Export Readiness Over Time',
  'how many records you author were ready to export in each period.',
  'Will render as a line chart.',
  'Validation Issues Over Time',
  'how many schema-validation issues were raised against the records you author, in each period.',
  'Needs change history this preview does not keep.',
  'Exports You Made Over Time',
  'how many official records you exported in each period.',
  'Your Recent Activity',
  'the most recent changes you made, each linking to the record it affected.',
  'Will render as a list.',
  'Each description names the unit it would count — records, fields, or validation issues — because a dashboard that blurs records into fields states a number nobody can act on.',
  'That is the same distinction the workspace figures keep, where evidence support is counted in fields beside the number of records those fields came from.',
];

/**
 * …AND THE PAGE LEAD, which renders OUTSIDE the panel and is the one piece of
 * this tab's copy the panel-scoped set cannot see. `StatisticsPage.tsx` sets it
 * per tab; this is the `mine` branch's sentence.
 */
const APPROVED_MINE_LEAD_SENTENCES: readonly string[] = [
  'This preview cannot tell whose records these are, so this tab states that rather than a figure.',
];

/** One raw copy unit, whitespace-normalised and split into sentences. */
function sentencesOfCopy(raw: string): string[] {
  const normalised = raw.replace(/\s+/g, ' ').trim();
  if (normalised === '') return [];
  return normalised
    .split(/(?<=[.;!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence !== '');
}

/** The unique, sorted sentence set of a list of raw copy units. */
function sentenceSet(units: readonly string[]): string[] {
  return [...new Set(units.flatMap(sentencesOfCopy))].sort();
}

/* ══ LAYER 2 · THE EMPTINESS MATCHER ════════════════════════════════════════
 *
 * ITS JOB IS SMALLER NOW, AND IT IS A JOB IT CAN DO. It no longer has to police
 * free prose written by anyone; it is applied to the entries of the two lists
 * above, so it has to catch a bad ADDITION — a false sentence somebody
 * transcribed into an allowlist while adding it to the panel. That is a review
 * aid with a review attached, not a perimeter.
 *
 * It is kept, rather than deleted, because the transcription step is exactly
 * where a false claim would arrive looking legitimate.
 */

/** A quantity noun this tab could state a personal count of. */
const COUNT_NOUN = 'records?|experiments?|exports?|fields?|figures?|activity|drafts?|issues?|questions?|counts?';

/** The emptiness values a count can be given. */
const EMPTY_WORD = 'zero|none|nil|nought|naught|nothing|empty';

/** The reader, named in the second person. */
const PERSONAL = /\byou\b|\byour\b|\byours\b/i;

/**
 * The reader, named in the THIRD person — and this pattern is an admission.
 *
 * The personal gate below (which is real: see `PERSONAL_EMPTINESS`) let four
 * hand-written sentences through, all measured passing at 4b86f7e:
 *
 *     This account has no records.       The signed-in user has no records.
 *     The reader has no experiments.     The current user has authored zero records.
 *
 * On a tab headed "Views Prepared for Your Account", `This account has no
 * records.` is a likelier edit than most of the `MUST_FLAG` table. The previous
 * version of the comment below concluded that a leak here "is trap 1's job, and
 * trap 1 forbids the import that would supply one" — which is true of a DERIVED
 * figure and covers none of these four, because they are hand-written copy with
 * no arithmetic behind them.
 *
 * So they are covered here, and this list is honestly a vocabulary allowlist of
 * exactly the kind the header above says will keep losing. Measured against the
 * pattern as written: `whoever is signed in has no records`, `this workspace's
 * owner has no records` and `the viewer has no records` all pass it. That is
 * acceptable ONLY because layer 1 rejects any of them on the way in. Do not promote
 * this pattern into a perimeter, and do not read the four nouns it does list as a
 * closed set of ways to name a person.
 */
const READER_IN_THIRD_PERSON =
  /\bthis account\b|\bthe (?:signed[- ]in |current |logged[- ]in )?(?:user|reader|author|account holder)\b/i;

/** True when `clause` names the reader as its subject, in either person. */
function namesTheReaderAsSubject(clause: string): boolean {
  return PERSONAL.test(clause) || READER_IN_THIRD_PERSON.test(clause);
}

/**
 * Emptiness applied to a countable unit. A CLAIM ONLY WHERE THE READER IS NAMED,
 * because the class this file guards is "an emptiness value applied to a
 * countable unit of THE READER'S work" and the reader is part of that definition.
 *
 * THE COST OF THAT NARROWING, STATED AT FULL SIZE. What it buys is real: this tab
 * truthfully says "no record in this workspace carries an author", a WORKSPACE
 * fact with no personal subject, and under clause scoping without this gate it
 * would be reported as a false positive on true copy. What it costs is the four
 * third-person sentences named on `READER_IN_THIRD_PERSON`, which the gate let
 * through and which that pattern now covers — partially, by an open-ended list of
 * subject nouns. The exposure is stated there rather than described as covered.
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
 * The escape, and TWO properties of it are load-bearing.
 *
 * 1 · IT IS ABOUT MODALITY, NOT POLARITY. The tab's most important sentence is
 *     "A count of zero WOULD say you have no records" — a hypothetical that
 *     denies the claim — so a page-wide ban on the words would flag exactly the
 *     copy doing the honest work. `\bnot\b` is deliberately absent: it was the
 *     obvious escape and it is a hole, because "You have not exported any
 *     records" is a false personal claim wearing a negation.
 *
 * 2 · IT MUST OPEN BEFORE THE CLAIM ENDS. A denial that FOLLOWS a claim does not
 *     unsay it. "You have no records and this preview cannot tell you more than
 *     that" states the zero, then reports the preview's ignorance OF it — and
 *     that shape is what every one of the ten evasions a third reviewer measured
 *     at 4b86f7e had in common, whatever punctuation joined the two halves:
 *     em-dash, colon, parenthesis, `while`, `whereas`, `although`, `because`, a
 *     newline, or nothing at all. Widening the joiner list would have caught some
 *     of them and lost to the next one; the positional rule catches all ten
 *     without knowing what a joiner is.
 *
 *     "Before the claim ENDS" and not "before it starts", because the frame can
 *     sit INSIDE the trigger: "Nothing would be attributed to you rather than to
 *     an account" is honest copy whose trigger match begins at "Nothing".
 */
const DENIAL_FRAME = /\bwould\b|\bcannot\b|\bcan't\b|\bunable\b|\bno way\b|\brather than\b|\b(?:is|are) absent\b/i;

/**
 * A sentence's coordinate clauses, split on the coordinators that join two
 * independent claims — `, and`, `, so`, `, but`, `, or`, `, yet`, `; ` — AND ON
 * THE EM-DASH.
 *
 * THE EM-DASH USED TO BE EXEMPT AND THE STATED REASON WAS FALSE. The exemption
 * was justified here by true copy it would flag: "none of the figures below are
 * zero — they are absent". Measured on that exact fragment against the matcher as
 * it stood at 4b86f7e: `triggers=false`, `personal=false` — it does not trigger
 * AT ALL, because the sibling personal-subject gate added in the same commit
 * already excludes it (that clause names no reader). So the exemption was defended
 * by a cost the same commit had eliminated, and it let
 * `You have no records — this preview cannot tell you more than that.` through.
 * The measured cost of splitting is zero.
 *
 * ONE CORRECTION TO THE NOTE THAT PROMPTED THIS. It recorded `denial=false` on the
 * same fragment; measured, `DENIAL_FRAME` matches it — `are absent` is one of its
 * alternatives, added in the same commit for this very sentence. The conclusion is
 * unaffected, since `triggers=false` settles it alone, but the figure is corrected
 * rather than repeated.
 */
function clausesOf(sentence: string): string[] {
  return sentence.split(/,\s+(?:and|but|so|or|yet)\s+|;\s+|\s*[—–]\s*/i);
}

/** Where a denial frame opens in `clause`, or `null` if none does. */
function denialFrameAt(clause: string): number | null {
  const found = DENIAL_FRAME.exec(clause);
  return found === null ? null : found.index;
}

/**
 * Where the EARLIEST emptiness trigger in `clause` ends, or `null` when the
 * clause states no emptiness about the reader's work.
 */
function triggerEndsAt(clause: string): number | null {
  const patterns: readonly RegExp[] = [
    ...SUBJECTLESS_EMPTINESS,
    ...NAMES_THE_READER,
    ...(namesTheReaderAsSubject(clause) ? PERSONAL_EMPTINESS : []),
  ];
  let earliest: number | null = null;
  for (const pattern of patterns) {
    const found = pattern.exec(clause);
    if (found === null) continue;
    const end = found.index + found[0].length;
    if (earliest === null || end < earliest) earliest = end;
  }
  return earliest;
}

/** Every CLAUSE of `text` that asserts the reader has nothing. */
function emptinessClaims(text: string): string[] {
  const claims: string[] = [];
  for (const sentence of text.split(/(?<=[.;])\s+/)) {
    for (const clause of clausesOf(sentence)) {
      const claimEnds = triggerEndsAt(clause);
      if (claimEnds === null) continue;
      const frame = denialFrameAt(clause);
      if (frame !== null && frame < claimEnds) continue;
      claims.push(clause.trim());
    }
  }
  return claims;
}

/** True when any clause of `sentence` asserts that the reader has nothing. */
function assertsEmptiness(sentence: string): boolean {
  return emptinessClaims(sentence).length > 0;
}

/* <<< SHARED-EMPTINESS-MATCHER-END <<< */

/**
 * Open the Technical Details disclosure, which holds two of the four charts, and
 * ASSERT THAT EVERY CHART PLOT IS ON ITS MEASURED WIDTH.
 *
 * ── What the poll is, and what it is NOT ────────────────────────────────────
 *
 * It is not a race-guard. This docstring used to say those two charts mount
 * "inside `display: none`, where `ResizeObserver` reports a content width of 0",
 * and that "on open, the observer fires again with the real width and React
 * re-renders one frame later". All three claims are false, they contradict
 * `StatsCharts.tsx:132-160` — which was right — in the same commit, and a
 * maintainer who trusted them would delete the line that makes these charts work.
 *
 * MEASURED in this suite's own headless Chromium, disclosure CLOSED: the plot
 * computes `display: flex` and `content-visibility: visible`, its
 * `getBoundingClientRect().width` is 918, and the SVG already carries
 * `width="918"` BEFORE any click. Nothing is racing. (What is `content-visibility:
 * hidden` is the UA's `::details-content` pseudo-element, measured on the
 * `<details>` itself — which is why the subtree is skipped by `ResizeObserver`
 * while still having a layout box.)
 *
 * So the poll is an ASSERTION: it says every plot's SVG width equals its column,
 * which is only true because `useChartWidth` reads the box SYNCHRONOUSLY in its
 * ref callback. Negative control, re-measured: delete
 * `apply(node.getBoundingClientRect().width)` and this poll never settles — both
 * SVGs sit at the 560px fallback while their columns measure 918. Across all five
 * viewport projects, 25 of this file's 45 runs fail, i.e. 5 of its 9 tests per
 * project, and the five are exactly the worked-example tests — the only ones that
 * call this function. The four that pass draw no chart (the empty-workspace test
 * and the three My Stats tests).
 *
 * NOT LOAD-DEPENDENT, and this paragraph used to say it was. It read "an isolated
 * single-project run failed 3 of 8, so WHICH of the eight fail is load-dependent".
 * Re-measured three times in isolation — `--project=desktop-1280x800`, twice at
 * the default worker count and once at `--workers=1` — the result is 5 failed /
 * 4 passed every time, the same five. The 3 was a single reading whose conditions
 * were never identified, and the inference drawn from it is withdrawn.
 *
 * WHY THE HOOK'S OBSERVER DOES NOT DELIVER AFTER OPEN IS NOT ISOLATED, and this
 * paragraph used to assert a cause it does not have. It said "The observer alone
 * never delivers, not even 1.5s after the region is opened", chaining that to the
 * skipped-subtree rule stated above. The rule explains the CLOSED state only.
 * Measured on the same node in the same session: a separately hand-installed
 * `ResizeObserver` on that `.stats-chart-plot`, while the `<details>` was still
 * closed, reported `[]` for 1.5s and then DID deliver `[918]` on open. So an
 * observer on that element can receive a post-open observation. The hook's does
 * not, the effect reproduces, and the mechanism is recorded as unidentified —
 * see `StatsCharts.tsx`, "THE POST-OPEN FAILURE IS OBSERVED AND ITS MECHANISM IS
 * NOT ISOLATED".
 *
 * It is spelled as a poll rather than a bare assertion only so that a genuine
 * future re-render (a breakpoint reflow) is tolerated rather than turned into a
 * flake. The value it converges on is fixed at mount.
 */
async function openTechnicalDetails(page: import('@playwright/test').Page): Promise<void> {
  const summary = page.locator('details.stats-technical > summary');
  await expect(summary).toBeVisible();
  await summary.click();
  await expect(page.locator('details.stats-technical')).toHaveAttribute('open', '');
  await expect
    .poll(
      () =>
        page.evaluate(() =>
          Array.from(document.querySelectorAll('figure.stats-chart')).filter((figure) => {
            const plot = figure.querySelector('.stats-chart-plot') as HTMLElement | null;
            const svg = figure.querySelector('svg') as SVGSVGElement | null;
            if (!plot || !svg) return false;
            return (
              Math.abs(Number(svg.getAttribute('width')) - plot.getBoundingClientRect().width) > 1
            );
          }).length,
        ),
      { message: 'every chart plot must settle on its measured width' },
    )
    .toBe(0);
}

test.describe('@responsive Statistics charts (worked example)', () => {
  test('every chart carries BOTH text equivalents, at this viewport', async ({ page, app }) => {
    await app.open(STATISTICS_EXAMPLE);
    await openTechnicalDetails(page);

    const figures = page.locator('figure.stats-chart');
    const count = await figures.count();
    // Workflow bars · the evidence stack · operations by method · operations by
    // group. A count is asserted so a chart silently disappearing reads as a
    // failure rather than as a vacuous pass over zero figures.
    expect(count, 'the populated page draws four charts').toBe(4);

    for (let i = 0; i < count; i++) {
      const figure = figures.nth(i);
      const caption = (await figure.locator('figcaption').first().innerText()).trim();

      // 1 · the summary sentence: a real element, present without any interaction,
      // and NOT inside the data-table disclosure (a closed `<details>` is hidden
      // from assistive technology, so the sentence would vanish with it).
      const summary = figure.locator('p.sr-only').first();
      await expect(summary, `${caption}: summary sentence`).toHaveCount(1);
      const summaryText = (await summary.textContent())?.trim() ?? '';
      expect(summaryText.length, `${caption}: summary must not be empty`).toBeGreaterThan(10);
      /*
       * Not inside the chart's OWN data-table disclosure. Scoped to that
       * disclosure rather than to any `<details>`, because two of these charts
       * legitimately live inside the collapsed Technical Details region — and that
       * hides the whole region, chart and text together, which is the reader's own
       * choice. What must never happen is the PICTURE being available while its
       * text equivalent sits behind a second, separate disclosure.
       */
      expect(
        await summary
          .locator('xpath=ancestor::details[contains(@class,"stats-chart-table-wrap")]')
          .count(),
        `${caption}: the summary must not be inside the data-table disclosure`,
      ).toBe(0);

      // 2 · the data table, reachable in one interaction and with real rows.
      const toggle = figure.locator('summary.stats-chart-table-toggle');
      await expect(toggle, `${caption}: data-table toggle`).toBeVisible();
      await toggle.click();
      const rows = figure.locator('table.stats-chart-table tbody tr');
      expect(await rows.count(), `${caption}: table rows`).toBeGreaterThan(0);
      await expect(figure.locator('table.stats-chart-table thead th').first()).toBeVisible();
    }
  });

  test('the drawn SVG claims nothing — the text is authoritative', async ({ page, app }) => {
    await app.open(STATISTICS_EXAMPLE);
    await openTechnicalDetails(page);

    const svgs = page.locator('figure.stats-chart svg');
    const count = await svgs.count();
    expect(count).toBeGreaterThan(0);
    for (let i = 0; i < count; i++) {
      await expect(svgs.nth(i)).toHaveAttribute('aria-hidden', 'true');
      await expect(svgs.nth(i)).toHaveAttribute('focusable', 'false');
    }
  });

  test('each plot is measured, fills its column, and includes its axis band', async ({
    page,
    app,
  }) => {
    await app.open(STATISTICS_EXAMPLE);
    await openTechnicalDetails(page);

    const measurements = await page.evaluate(() => {
      const out: {
        caption: string;
        plotWidth: number;
        svgWidth: number;
        viewBox: string;
        svgHeight: number;
        renderedHeight: number;
      }[] = [];
      for (const figure of document.querySelectorAll('figure.stats-chart')) {
        const plot = figure.querySelector('.stats-chart-plot') as HTMLElement | null;
        const svg = figure.querySelector('svg') as SVGSVGElement | null;
        if (!plot || !svg) continue;
        out.push({
          caption: (figure.querySelector('figcaption')?.textContent ?? '').trim().slice(0, 40),
          plotWidth: Math.round(plot.getBoundingClientRect().width),
          svgWidth: Number(svg.getAttribute('width')),
          viewBox: svg.getAttribute('viewBox') ?? '',
          svgHeight: Number(svg.getAttribute('height')),
          renderedHeight: Math.round(svg.getBoundingClientRect().height),
        });
      }
      return out;
    });

    expect(measurements.length).toBeGreaterThan(0);
    for (const m of measurements) {
      // MEASURED, not the fallback: the SVG width tracks the plot column to
      // within a pixel of rounding.
      expect(Math.abs(m.svgWidth - m.plotWidth), `${m.caption}: svg width vs plot`).toBeLessThanOrEqual(1);
      // 1:1 coordinates — the viewBox equals the rendered box, so `<text>` is
      // never scaled down and a hairline is one pixel.
      expect(m.viewBox, `${m.caption}: viewBox`).toBe(`0 0 ${m.svgWidth} ${m.svgHeight}`);
      // The declared height is the height actually taken, so the axis band is
      // inside the box rather than clipped by it.
      expect(Math.abs(m.renderedHeight - m.svgHeight), `${m.caption}: height`).toBeLessThanOrEqual(1);
    }
  });

  test('no chart forces two-dimensional scrolling', async ({ page, app }) => {
    await app.open(STATISTICS_EXAMPLE);
    await openTechnicalDetails(page);
    // Open every data table too: a wide table is the most likely thing to widen
    // the page, so the check is made in the state where it could.
    const toggles = page.locator('summary.stats-chart-table-toggle');
    for (let i = 0; i < (await toggles.count()); i++) await toggles.nth(i).click();

    const overflow = await page.evaluate(() => ({
      docScroll: document.documentElement.scrollWidth,
      docClient: document.documentElement.clientWidth,
      bodyScroll: document.body.scrollWidth,
      // Any chart element whose own box is wider than the plot column it sits in
      // AND that is not inside a declared scroll container.
      escapees: Array.from(document.querySelectorAll('figure.stats-chart *'))
        .filter((el) => {
          const box = el.getBoundingClientRect();
          if (box.width === 0) return false;
          const plot = el.closest('figure.stats-chart') as HTMLElement | null;
          if (!plot) return false;
          if (el.closest('.stats-scroll')) return false; // scrolls inside itself, by design
          return box.right > plot.getBoundingClientRect().right + 1;
        })
        .map((el) => `${el.tagName.toLowerCase()}.${el.className}`),
    }));

    expect(overflow.docScroll, 'the page must not scroll sideways').toBeLessThanOrEqual(
      overflow.docClient,
    );
    expect(overflow.bodyScroll).toBeLessThanOrEqual(overflow.docClient);
    expect(overflow.escapees, 'chart content must stay inside its figure or its own scroller').toEqual([]);
  });

  test('the wide block scrolls inside its own container, not the page', async ({ page, app }) => {
    await app.open(STATISTICS_EXAMPLE);
    await openTechnicalDetails(page);
    await page.locator('summary.stats-chart-table-toggle').first().click();

    // Every data table is wrapped in the surface's declared scroll container, so
    // a long group name can never widen the page.
    const unwrapped = await page.evaluate(
      () =>
        Array.from(document.querySelectorAll('table.stats-chart-table')).filter(
          (t) => t.closest('.stats-scroll') === null,
        ).length,
    );
    expect(unwrapped, 'every chart table must sit in a .stats-scroll container').toBe(0);
  });
});

test.describe('@responsive Statistics charts (empty ordinary workspace)', () => {
  /*
   * An empty workspace draws NO chart — not an empty axis, not a row of zero
   * bars, not a table of zeros. A zero-filled plot is a measurement claim, and
   * the ordinary workspace of this deployment is permanently empty, so this is
   * the state most readers see.
   */
  test('draws no RECORD-derived chart, no axis and no table', async ({ page, app }) => {
    await app.open(STATISTICS_ORDINARY);

    /*
     * Scoped to the record-derived sections, which is the honest scope. The API
     * surface DOES draw two charts here and should: they describe the build's own
     * contract, not the workspace, so they have real data in every scope. (They
     * also sit inside the collapsed Technical Details region, and a closed
     * `<details>` still holds its children in the DOM — so a page-wide
     * `toHaveCount(0)` would fail for a reason that has nothing to do with the
     * empty workspace.)
     */
    for (const region of ['Workflow Distribution', 'Evidence and Validation']) {
      const section = page.getByRole('region', { name: region });
      await expect(section.locator('figure.stats-chart'), region).toHaveCount(0);
      await expect(section.locator('.stats-chart-grid'), region).toHaveCount(0);
      await expect(section.locator('table.stats-chart-table'), region).toHaveCount(0);
    }
    // …and it says so in words, rather than leaving a blank card.
    await expect(page.getByText(/No bar is drawn rather than a row of zeros/)).toBeVisible();
  });
});

/**
 * Every text node of a subtree AND every accessible-name attribute on it, read in
 * the page and returned as raw copy units.
 *
 * Per UNIT, matching `copyUnitsOf` in `src/__tests__/my-stats.test.tsx`, and NOT
 * `innerText`: `innerText` collapses the whole subtree into one string, so a
 * heading with no full stop is welded onto the paragraph after it and the split
 * invents a sentence nobody wrote. The extraction has to happen in the page
 * (there is no DOM here), so it is a `page.evaluate` — the ATTRIBUTE LIST is
 * passed in from the shared block rather than restated, so the two suites cannot
 * disagree about what counts as an accessible name.
 */
async function copyUnitsIn(
  page: import('@playwright/test').Page,
  selector: string,
): Promise<string[]> {
  return page.evaluate(
    ({ selector: sel, attrs }) => {
      const roots = Array.from(document.querySelectorAll(sel));
      if (roots.length !== 1) throw new Error(`expected exactly one ${sel}, found ${roots.length}`);
      const root = roots[0];
      const units: string[] = [];
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) units.push(walker.currentNode.textContent ?? '');
      for (const element of [root, ...Array.from(root.querySelectorAll('*'))]) {
        for (const attribute of attrs) {
          const value = element.getAttribute(attribute);
          if (value !== null) units.push(value);
        }
      }
      return units;
    },
    { selector, attrs: [...ACCESSIBLE_NAME_ATTRS] },
  );
}

test.describe('@responsive Statistics · My Stats', () => {
  /*
   * THE PRIMARY GUARD, IN THE BROWSER. Exact set equality between the sentences
   * this tab renders and the enumerated list in the shared block above.
   *
   * This is the browser half of the inversion described there: three generations
   * of pattern-shaped guard were evaded by punctuation, the third by deleting one
   * comma, so what is checked here is no longer "does this read as a false zero"
   * but "is this sentence on the list". Nothing about it depends on how a sentence
   * is joined, framed or spelled.
   *
   * A SEPARATE TEST from the no-chart/no-zero one below, and deliberately: that
   * one is a set of independent absences, and folding a whole-copy comparison into
   * it would report a copy edit as a charting failure.
   */
  test('renders EXACTLY the approved sentences — panel and page lead', async ({ page, app }) => {
    await app.open(STATISTICS_MINE);
    await expect(page.getByRole('heading', { name: 'Personal Statistics' })).toBeVisible();

    const rendered = sentenceSet(await copyUnitsIn(page, '#statistics-tabpanel-mine'));
    expect(rendered.length, 'the extractor found no copy at all — it is broken').toBeGreaterThan(30);
    expect(
      rendered,
      'the My Stats panel renders a sentence that is not on the approved list, or no longer ' +
        'renders one that is. If the change is intended, transcribe it into ' +
        'APPROVED_PANEL_SENTENCES — in BOTH copies of the shared block — in the same commit.',
    ).toEqual([...APPROVED_PANEL_SENTENCES].sort());

    const lead = sentenceSet(await copyUnitsIn(page, '.placeholder > p'));
    expect(lead).toEqual([...APPROVED_MINE_LEAD_SENTENCES].sort());

    /*
     * …and the comparison is exact in both directions, demonstrated against the
     * copy this browser just rendered: one added sentence and one removed sentence
     * each fail. The added one is TRUE, which is the design rather than a bug — a
     * guard that reads no meaning cannot be argued with, and the cost is that an
     * honest addition must be transcribed.
     */
    expect(sentenceSet([...rendered, 'This preview also has no view for a readiness trend.'])).not.toEqual(
      [...APPROVED_PANEL_SENTENCES].sort(),
    );
    expect(
      sentenceSet(rendered.filter((sentence) => !sentence.includes('A count of zero would say'))),
    ).not.toEqual([...APPROVED_PANEL_SENTENCES].sort());
  });

  test('renders the gate, and no chart, no skeleton and no zero', async ({ page, app }) => {
    await app.open(STATISTICS_MINE);

    await expect(page.getByRole('heading', { name: 'Personal Statistics' })).toBeVisible();
    await expect(page.getByText('Not Available in This Preview')).toBeVisible();

    const panel = page.locator('#statistics-tabpanel-mine');
    await expect(panel.locator('figure.stats-chart')).toHaveCount(0);
    await expect(panel.locator('.stats-chart-grid')).toHaveCount(0);
    await expect(panel.locator('[role="status"]')).toHaveCount(0);

    // No figure at all: a personal tab that cannot attribute a record must not
    // display a count, and "0" is a count.
    const text = (await panel.innerText()).replace(/\s+/g, ' ');
    expect(text, 'no numeral may appear on the personal tab').not.toMatch(/\d/);

    /*
     * …AND NO ZERO IN WORDS. `/\d/` above is digit-shaped, and so was every other
     * emptiness guard on this tab, so a first reviewer's insertion — "Zero records
     * are attributed to you, and your export count is zero." — passed all 8 tests
     * in this file, INCLUDING THIS ONE, whose title claims to check for "no zero".
     *
     * The word-shaped replacement then had its OWN hole, and it was scope rather
     * than vocabulary: a modal token anywhere in a sentence excused a trigger
     * anywhere else in it. A second reviewer inserted, and this test passed:
     *
     *     You have no records, and this preview cannot tell you more than that.
     *     Nothing to show.
     *
     * Clause scoping fixed that and was itself defeated by DELETING THE COMMA, so
     * this check is NO LONGER THE PRIMARY GUARD. The test above it is: exact set
     * equality against an enumerated list, which rejects an unapproved sentence
     * whatever it says. What survives here is the matcher, with two corrections —
     * the em-dash is no longer exempt, and a denial must open BEFORE the claim it
     * excuses ends — see the shared block above, and
     * `src/__tests__/my-stats.test.tsx`, which is the authority and carries the
     * polarity table.
     */
    const claims = emptinessClaims(text);
    expect(claims, 'a clause on the personal tab asserts the reader has nothing').toEqual([]);

    /*
     * …and the guard BITES on the copy this browser actually rendered. Mutation,
     * not a count: the previous check here counted how many sentences reached the
     * trigger and required each to be modally framed, which is satisfied by
     * "everything matched and everything was excused" — the exact state that let
     * the second reviewer's sentence through. Removing one modal word from the
     * tab's own zero-denying sentence must produce a report.
     */
    const withoutModal = text.replace(
      'A count of zero would say you have no records',
      'A count of zero says you have no records',
    );
    expect(withoutModal, 'the mutation must apply to the rendered text').not.toBe(text);
    expect(emptinessClaims(withoutModal)).toEqual(['A count of zero says you have no records;']);

    // …and the second reviewer's two sentences, verbatim, are both reported —
    // both as a whole-sentence verdict and when appended to the rendered text.
    expect(
      assertsEmptiness('You have no records, and this preview cannot tell you more than that.'),
    ).toBe(true);
    expect(assertsEmptiness('Nothing to show.')).toBe(true);
    expect(
      emptinessClaims(
        `${text} You have no records, and this preview cannot tell you more than that. Nothing to show.`,
      ),
    ).toEqual(['You have no records', 'Nothing to show.']);

    /*
     * …and the THIRD reviewer's, which is the same sentence with the comma taken
     * out plus two of the nine other joiners measured at 4b86f7e. All three passed
     * this test then. The full table of fourteen lives in
     * `src/__tests__/my-stats.test.tsx` as `REVIEWER_EVASIONS`; three are repeated
     * here because this file is the one that runs against a real browser's copy.
     */
    for (const evasion of [
      'You have no records and this preview cannot tell you more than that.',
      'You have no records — this preview cannot tell you more than that.',
      'The signed-in user has no records.',
    ]) {
      expect(assertsEmptiness(evasion), `must be FLAGGED: ${evasion}`).toBe(true);
      expect(emptinessClaims(`${text} ${evasion}`).length, evasion).toBeGreaterThan(0);
    }
  });

  test('lists all eight planned views as headings', async ({ page, app }) => {
    await app.open(STATISTICS_MINE);
    await expect(
      page.locator('#statistics-tabpanel-mine .stats-plan-card h3'),
    ).toHaveCount(8);
  });
});
