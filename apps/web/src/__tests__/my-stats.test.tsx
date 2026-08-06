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
import { type CurrentUserSource } from '../lib/currentUserContract';
import { MyStats } from '../screens/statistics/MyStats';
import { currentUserSourceReporting, fixtureCurrentUser } from '../test/adapterFixtures';
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

/**
 * The copy units of a subtree — a thin wrapper over the SHARED {@link copyUnitsFrom}
 * in the block below, so the two suites cannot extract differently. Round 3 had two
 * hand-written copies of this, one on each side of the shared block's sentinels,
 * and the lockstep test could not see either of them.
 */
function copyUnitsOf(root: HTMLElement): string[] {
  return copyUnitsFrom(root, ACCESSIBLE_NAME_ATTRS);
}

/**
 * The ONE element matching `selector`, or a failure.
 *
 * FAILS CLOSED, matching the browser copy — and it did not before. The browser side
 * threw on `roots.length !== 1`; this side used `querySelector` and silently took
 * the first. MEASURED at 134eac2: a second `<p>You have no records.</p>` appended to
 * `.placeholder` left the extracted lead set UNCHANGED, so the false sentence was
 * never compared against anything.
 */
function soleElement(container: HTMLElement, selector: string): HTMLElement {
  const found = container.querySelectorAll(selector);
  expect(found.length, `expected exactly one ${selector}, found ${found.length}`).toBe(1);
  return found[0] as HTMLElement;
}

/* ── the emptiness matcher, and the three generations of hole it has had ─────
 *
 * The two layers now in force, and why, are documented inside the shared block
 * below — read that first. This is the failure record that produced them, kept
 * because each generation's fix was itself defeated and the pattern in HOW is
 * more useful than the individual holes.
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
 *
 * GENERATION 3 — CLAUSE SCOPING OVER AN ALLOWLIST OF JOINERS, DEFEATED BY DELETING
 * ONE COMMA. `clausesOf` split on `, and|but|so|or|yet` and `; `, so generation
 * 2's own example sentence — with the comma removed —
 *
 *     You have no records and this preview cannot tell you more than that.
 *
 * was ONE clause and `cannot` was in it. RE-MEASURED at 4b86f7e rather than taken
 * on report: rendered in the panel as a `stats-note` paragraph, it passed all 231
 * tests of the five statistics vitest files — 71 of them in this file, including
 * trap 4, whose title claims to check for a zero "IN WORDS" — and all 40 browser
 * tests in `e2e/specs/charts.spec.ts`, including the one titled "no zero". A third
 * independent reviewer measured nine further evasions of the same kind, all
 * re-measured here: a colon, a parenthesis, `while`, `whereas`, `although`,
 * `because`, a newline, an em-dash (which was explicitly exempt), and one
 * `Your export count is zero — no way to say otherwise.`
 *
 * THE CONCLUSION IS STRUCTURAL AND IT IS THE REVIEWER'S: a guard shaped like an
 * allowlist of joiners will keep losing. So the enforcement point is INVERTED
 * rather than widened — an allowlist of approved SENTENCES, compared as an exact
 * set, with this matcher demoted to a second layer over that allowlist's own
 * entries. Two changes are also made inside the matcher, because both were wrong
 * on their own terms: the em-dash exemption was justified by a cost that did not
 * exist (measured), and the escape now has to open BEFORE the claim it excuses
 * ends, which is what all ten of the reviewer's sentences turn on.
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
 * which is applied to these entries, and by whoever reads the diff.
 *
 * NO NEW SENTENCE can reach this tab without appearing here. That is the exact
 * claim, and it is narrower than the one this comment used to make ("there is no
 * way to change what this tab says without the new sentence appearing here"),
 * which was FALSE — see limitation 2 below, measured.
 *
 * WHAT IS COMPARED. Every text NODE of the subtree, plus every accessible-name
 * attribute on it (see {@link ACCESSIBLE_NAME_ATTRS}) — an `aria-label` is copy a
 * reader is read out, and a guard over text nodes alone would not see it. Each
 * unit is whitespace-normalised and split into sentences, and the UNIQUE set is
 * compared, sorted, in full.
 *
 * ══ WHAT LAYER 1 DOES NOT CATCH ═════════════════════════════════════════════
 *
 * These live HERE, next to the guard, and not only in a commit message — a
 * limitation recorded where nobody reads it is a limitation nobody knows about.
 * Each one is measured.
 *
 * 1 · SCOPE. `#statistics-tabpanel-mine` and the `.placeholder > p` page lead,
 *     and nothing else. Copy elsewhere on the page is somebody else's guard.
 *
 * 2 · UNORDERED AND UNPAIRED. A SET is compared, so the guard is blind to which
 *     title a description sits under and to where an approved sentence appears.
 *     MEASURED: swapping the `description` strings of `readiness_trend` and
 *     `exports_over_time` in `lib/myStatsContract.ts` passed the ENTIRE frontend
 *     suite — 2799 of 2799 at the time of measurement, which was every test in the
 *     repository except the pairing pin, since that pin did not exist yet — and the
 *     tab then described each view as the other. Not a false personal zero, so not
 *     the class this file exists to stop, but not nothing either, which is why
 *     `MY_STATS_VIEWS` title→description pairing is pinned separately in
 *     `the planned views` describe-block below.
 *
 * 3 · UNIQUE, NOT A MULTISET, and that one is deliberate: five planned views
 *     share the gate label `Needs records linked to an account.`, and three share
 *     `Will render as a line chart.`, so a multiset would pin how many views
 *     happen to sit behind each precondition and would fail on a re-labelling
 *     that says nothing new. Repeating a sentence that is already approved states
 *     no new claim; saying anything else does, and that is what is caught.
 *
 * 4 · NAME INDIRECTION IS NOT FOLLOWED BY THE EXTRACTOR. `aria-labelledby` /
 *     `aria-describedby` point at copy by ID, so the name a reader hears need not
 *     be inside the subtree at all. MEASURED at 134eac2: a `<span id="evil">You
 *     have no records.</span>` in `.placeholder` plus `aria-labelledby="evil"` on
 *     the panel `<h2>` changed NEITHER set — a screen-reader user hears the false
 *     claim where a sighted user reads "Personal Statistics".
 *
 *     It is now closed by a SEPARATE rule rather than by the extractor: every
 *     IDREF on a panel descendant must resolve, and must resolve INSIDE the panel,
 *     so the copy it names is already in the compared set — see `every name
 *     reference inside the panel resolves inside the panel` below. Forbidding the
 *     attributes outright would have been simpler and is not available: measured,
 *     `StatsSection` renders `<section aria-labelledby={id}>` and the panel
 *     contains two of them, each pointing at its own heading. The panel ROOT is
 *     excluded by name — its `aria-labelledby` is the required tabpanel↔tab wiring
 *     and points out of scope on purpose.
 *
 * 5 · LAYER 2's THIRD-PERSON SUBJECT LIST is itself a vocabulary allowlist of
 *     exactly the kind that keeps losing — `whoever is signed in has no records`
 *     passes it. Stated at {@link READER_IN_THIRD_PERSON}; acceptable only
 *     because layer 1 rejects the sentence on the way in.
 *
 * The browser copy of the EXTRACTOR is no longer a re-implementation, and the
 * reason previously given for that ("the production build must not import
 * Playwright types") was not the obstacle: {@link copyUnitsFrom} takes
 * `(root, attrs)`, closes over nothing, needs no Playwright type, and is passed
 * BY VALUE to `locator.evaluate`. It now lives in this shared block, so the
 * lockstep test covers it.
 */

/**
 * Attributes that put copy into the accessible name or description, and so into
 * the claim set.
 *
 * `placeholder`, `label` and `abbr` are the NATIVE spellings beside their ARIA
 * counterparts: round 3 listed `aria-placeholder` and not `placeholder`, which is
 * the one an author actually writes. `label` covers `<option>` / `<optgroup>` and
 * `abbr` covers `<th>`. None of them appears on this panel today — they are here
 * because the cost of listing an attribute is nil and the cost of missing one is
 * a claim read out to somebody.
 *
 * NOT here, and deliberately: `aria-labelledby` and `aria-describedby`. Those name
 * copy BY REFERENCE, so adding them to this list would read an ID, not a sentence.
 * They are forbidden on panel descendants instead — see limitation 4 above.
 */
const ACCESSIBLE_NAME_ATTRS: readonly string[] = [
  'aria-label',
  'aria-description',
  'aria-roledescription',
  'aria-valuetext',
  'aria-placeholder',
  'placeholder',
  'title',
  'alt',
  'label',
  'abbr',
];

/** Attributes that name copy BY REFERENCE, which no text scan can follow. */
const NAME_INDIRECTION_ATTRS: readonly string[] = ['aria-labelledby', 'aria-describedby'];

/**
 * Every text node of `root` AND every accessible-name attribute on it, as a list of
 * raw copy units — one entry per authored string, not one joined blob.
 *
 * Per UNIT, deliberately. Joining a subtree with spaces is right for a substring
 * scan and wrong for a sentence set: it welds a heading with no full stop onto the
 * paragraph after it ("Personal Statistics What this tab will show…") and invents a
 * sentence nobody wrote. A text node is the smallest thing an author edits, so it
 * is the unit.
 *
 * The attributes come last and are prefixed with nothing: an `aria-label` is copy,
 * and it belongs in the same set as visible text. `aria-hidden` subtrees are NOT
 * skipped — a decorative icon carries no text, and anything that does carry text is
 * visible to somebody.
 *
 * SHARED BY BOTH SUITES, which is why it takes `attrs` as a parameter and closes
 * over nothing at all: the browser copy hands it to `locator.evaluate`, which
 * serialises the function and runs it in the page. It uses only DOM globals that
 * exist in jsdom and in Chromium.
 */
function copyUnitsFrom(root: Element, attrs: readonly string[]): string[] {
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
}

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
 * ITS JOB IS SMALLER NOW, AND IT STILL HAS HOLES — round 3 wrote "AND IT IS A JOB
 * IT CAN DO" here and a fourth reviewer defeated it four ways in the same commit,
 * so the claim is withdrawn rather than restated. What is true is narrower: it no
 * longer has to police free prose written by anyone. It is applied to the 43
 * enumerated entries of the two lists above, so it has to catch a bad ADDITION —
 * a false sentence somebody transcribed into an allowlist while adding it to the
 * panel. That is a review aid with a review attached, not a perimeter, and it
 * should not be read as one.
 *
 * It is kept, rather than deleted, because the transcription step is exactly
 * where a false claim would arrive looking legitimate.
 *
 * ONE WIDENING IS NEVERTHELESS CORRECT HERE, and the reasoning matters because it
 * looks like the reasoning round 3 rejected. Round 3 concluded "a guard shaped
 * like an allowlist of joiners will keep losing" — a PERIMETER argument, and sound
 * as one. It does not apply to a matcher whose entire input is 43 enumerated
 * sentences: there a false positive is visible on the very next run and costs one
 * line of triage, so the balance that makes widening a losing game outside is
 * reversed inside. See {@link clausesOf}.
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
 * A sentence's coordinate clauses, split on a bare coordinator (`and`, `but`, `so`,
 * `or`, `yet`) with or WITHOUT a preceding comma, on any comma, on `; `, and on the
 * em-dash.
 *
 * ROUND 3 SPLIT ON `,\s+(and|but|so|or|yet)`, `;\s+` and the em-dash — the comma
 * being MANDATORY — and that is the MIRROR of the hole round 3 was fixing. Round 3
 * lost to a denial moved AFTER the claim with the comma deleted; a fourth reviewer
 * moved the denial BEFORE the claim and deleted the comma, which keeps the sentence
 * in ONE clause, so the positional rule sees an escape opening before the trigger
 * ends and excuses it. MEASURED at 134eac2, all four came back UNFLAGGED:
 *
 *     This preview cannot tell whose records these are and you have no records.
 *     Unable to attribute anything, you have no records.
 *     This build cannot say who you are but you have no records.
 *     A count of zero would be wrong and you have no records.
 *
 * The first is in the tab's own voice, so this is the accidental-edit case as well
 * as the adversarial one. The decisive control was the LEGITIMATE flow: sentence 1
 * rendered in `MyStats.tsx` AND transcribed into both allowlists — 284 of 284 tests
 * passed, layer 1 satisfied because it had been transcribed, layer 2 silent, and the
 * tab stating a false personal zero.
 *
 * MEASURED COST OF THE WIDENING: zero. All four mirrors flagged, all 14
 * `REVIEWER_EVASIONS` still flagged, and zero false positives across all 43
 * approved entries — which is exactly what `no approved sentence asserts that the
 * reader has nothing` asserts, on every run, rather than on trust.
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
 *
 * WHAT THIS WIDENING DOES **NOT** CLOSE, said here because this is where a
 * maintainer transcribing a sentence will be reading. The mirror is closed for a
 * BARE COORDINATOR only. `REVIEWER_EVASIONS` below enumerates nine joiners that
 * escaped when the denial came AFTER the claim; every one of them still escapes
 * when the denial comes FIRST — measured unflagged: a colon, a parenthetical,
 * `Because …`, `While/Although/Since/Whereas …`, no joiner at all, and
 * `… therefore …`.
 *
 * That is tolerable for exactly one reason, and it is not this matcher's doing:
 * LAYER 1 IS THE PERIMETER AND IT HOLDS. Any of those sentences rendered in the
 * panel fails layer 1 immediately, because it is not in the allowlist. Reaching
 * this matcher's holes requires transcribing the sentence into the allowlist in
 * both copies — i.e. editing the test file, which is where a human reviewer reads
 * the new claim. Do not read this note as a licence to trust the matcher alone.
 */
function clausesOf(sentence: string): string[] {
  return sentence.split(/\s+(?:and|but|so|or|yet)\s+|,\s+|;\s+|\s*[—–]\s*/i);
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
    const panel = soleElement(container, '#statistics-tabpanel-mine');
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
     * The five General-tab reads still happen on mount (they are not tab-keyed),
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
        'GET /api/schema',
      ].sort(),
    );
    expect(calls.filter((c) => c.includes('/api/experiments'))).toEqual([]);
    expect(calls.filter((c) => c.includes('/api/demo'))).toEqual([]);
  });

  /** TRAP 3 — a portal-wide metric. Nothing here names or reads a portal. */
  it('3 — names no portal, database or cross-user metric', async () => {
    const { container } = await renderMineTab();
    const text = textOf(soleElement(container, '#statistics-tabpanel-mine'));
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
    const panel = soleElement(container, '#statistics-tabpanel-mine');
    const text = textOf(panel);

    expect(text).not.toMatch(/\b0\b/);
    expect(text).toMatch(/none of the figures below are zero — they are absent/);
    expect(text).toMatch(/cannot tell whose records these are/);

    /*
     * …and NO CLAUSE ASSERTS THAT THE READER HAS NOTHING — in digits or in words.
     * Checked per clause, with the positional modal escape documented above, so
     * the sentences that legitimately DENY a zero stay legal while a clause that
     * states one cannot borrow a denial from its neighbour or from its own tail.
     *
     * The whole set is reported rather than the first match, so a copy edit that
     * introduces two says so once.
     *
     * THIS IS NO LONGER THE PRIMARY GUARD, and it must not be relied on as one.
     * Three generations of it were evaded by punctuation; what actually stops a
     * new sentence — false OR true — is `the approved-sentence allowlist` below,
     * which compares the rendered set to an enumerated one. This check survives
     * because it is what reads the allowlist's entries.
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
    const panel = soleElement(container, '#statistics-tabpanel-mine');
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
    const text = textOf(soleElement(container, '#statistics-tabpanel-mine'));
    expect(text).not.toMatch(/signed in as|@|Signed in|Hello|Welcome back/i);

    const source = String((await import('../screens/statistics/MyStats?raw')).default);
    const contract = String((await import('../lib/myStatsContract?raw')).default);
    /*
     * THE CURRENT-USER BOUNDARY IS SCANNED TOO, and it has to be: `MyStats.tsx`
     * now imports it, so it is inside this tab's dependency chain. It is also the
     * one module in the app that WRITES the seven header names down — as string
     * literals in a frozen record of what §6A observed — which is exactly the
     * module a reader would expect to find reading them. It does not: the scans
     * below fail on any header access, any transport, and any use of this app's
     * API client.
     */
    const identity = String((await import('../lib/currentUserContract?raw')).default);
    for (const [name, module] of [
      ['MyStats.tsx', source],
      ['myStatsContract.ts', contract],
      ['currentUserContract.ts', identity],
    ] as const) {
      /*
       * No header read, and no fetch of any kind, in any of the three modules.
       *
       * WHERE THE HEADER NAMES DO APPEAR, stated precisely because the previous
       * version of this comment got it wrong: it said "`X-authentik` appears only
       * inside the prose that explains why it must not be used", which had stopped
       * being true of the module this same hunk added. In `currentUserContract.ts`
       * the seven names are `const` STRING LITERALS in `IDENTITY_CANDIDATE_HEADERS`
       * and in the frozen `HEADER_OBSERVATION_6A` table — real code, not prose. The
       * claim that holds is the narrower one the comment eight lines above already
       * makes: nothing reads a header BY them. That is what the scans assert.
       */
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
       * None of the THREE modules contains the substring `api.` in prose (checked
       * — "neither" was written when the loop had two), so this needs no stripping.
       */
      expect(module, `${name} must not call this app's API client`).not.toMatch(/\bapi\s*\.\s*[a-zA-Z]/);
      expect(module, `${name} must not open a transport of its own`).not.toMatch(
        /XMLHttpRequest|EventSource|sendBeacon|WebSocket|\bimport\s*\(/,
      );

      /*
       * …AND NO COOKIE, AND NO BROWSER STORAGE. The list above had no entry for
       * either, so `void document.cookie; void window.localStorage;` inside
       * `disabledCurrentUserSource.get()` was invisible to every guard in this repo
       * — while `currentUserContract.ts`'s own module head offered "no
       * `document.cookie`" as evidence that it is not an identity seam. A cookie is
       * the shortest path a future SPA slice has from "no identity" to a username,
       * and it needs no transport and no header at all.
       *
       * COMMENTS ARE STRIPPED FIRST, and they have to be: that module head names
       * `document.cookie` in order to disclaim it, so a whole-text scan would be
       * satisfied by deleting the disclaimer instead of the dependency — trap 1's
       * reasoning, applied here. The stripper is deliberately naive (block
       * comments, then whole-line `//`), which is sound for these three files
       * because none of them contains `/*` inside a string or a regular expression
       * — checked. The two assertions below prove the stripper both kept the code
       * and removed the prose, so a stripper that returned `''` could not make this
       * pass vacuously.
       */
      const code = module.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/^[ \t]*\/\/.*$/gm, ' ');
      expect(code, `${name}: the comment stripper must leave code behind`).toMatch(/\bexport\b/);
      if (name === 'currentUserContract.ts') {
        /* …and it really did remove prose that names the thing being scanned for:
           this module's head disclaims `document.cookie` in words. A stripper that
           returned the text unchanged would fail the scan below on that sentence,
           and one that returned `''` would fail the `export` check above. */
        expect(module, 'the module head names document.cookie in prose').toMatch(
          /document\s*\.\s*cookie/,
        );
      }
      expect(code, `${name} must not read a cookie or browser storage`).not.toMatch(
        /document\s*\.\s*cookie|localStorage|sessionStorage/,
      );

      // …and it cannot even IMPORT the client. Matched against the import
      // statements, per trap 1's reasoning: a whole-text scan would be satisfied
      // by deleting the explanation rather than the dependency.
      const imports = module.match(/^import[\s\S]*?from\s+'[^']+';$/gm) ?? [];
      for (const line of imports) {
        expect(line, `${name} must not import the API client`).not.toMatch(/lib\/api'|\/api'$/);
      }

      /*
       * THE EXACT DEPENDENCY SET OF EACH CONTRACT MODULE.
       *
       * This used to read `if (name === 'myStatsContract.ts') expect(imports)
       * .toEqual([])` — "imports NOTHING at all, which is the strongest possible
       * form of this". That claim STOPPED BEING TRUE when the contract began
       * selecting a personal source from a current-user state, and the honest
       * replacement is not a weaker scan but a narrower one: the exact set of
       * specifiers each module may name. `./currentUserContract` is a type-and-
       * union dependency on a module that itself imports nothing; anything else
       * appearing here is a deliberate, reviewed change rather than a silent one.
       */
      const specifiers = imports
        .map((line) => /from\s+'([^']+)';$/.exec(line)?.[1] ?? '')
        .sort();
      if (name === 'myStatsContract.ts') expect(specifiers).toEqual(['./currentUserContract']);
      if (name === 'currentUserContract.ts') expect(specifiers).toEqual([]);
    }
  });
});

// --- layer 1 · the approved-sentence allowlist -------------------------------

/**
 * FOURTEEN SENTENCES A THIRD INDEPENDENT REVIEWER MEASURED AS PASSING at 4b86f7e,
 * each inserted into production copy one at a time.
 *
 * The first ten defeated the clause splitter: every one states a personal zero and
 * then follows it with a denial, joined by something the splitter did not know
 * about — or, in entry 2, by nothing at all. The last four defeated the
 * personal-subject gate by naming the reader in the third person.
 *
 * ALL FOURTEEN RE-MEASURED against the matcher as it stood at 4b86f7e, rather than
 * accepted from the review: all fourteen came back UNFLAGGED. Every one of them is
 * now reported, and every one of them additionally fails layer 1 when inserted into
 * production copy — measured one at a time, fourteen runs.
 *
 * They are listed separately from `MUST_FLAG` because they carry a second job:
 * `an approved sentence that asserts an emptiness is rejected` runs the layer-2
 * matcher over each of them as though somebody had transcribed it into the
 * allowlist, which is the one route into the panel that layer 1 cannot see past.
 */
const REVIEWER_EVASIONS: readonly string[] = [
  // 1–10 · a denial that FOLLOWS the claim, joined ten different ways.
  'You have no records — this preview cannot tell you more than that.',
  'You have no records and this preview cannot tell you more than that.',
  'You have no records: this preview cannot tell you more.',
  'You have no records (this preview cannot tell you more).',
  'You have no records while this preview cannot tell more.',
  'You have no records whereas the workspace cannot say.',
  'You have no records although this cannot be confirmed.',
  'You have no records because nothing would be attributed.',
  'You have no records\nand this preview cannot tell you more.',
  'Your export count is zero — no way to say otherwise.',
  // 11–14 · the reader named in the third person, past the personal gate.
  'This account has no records.',
  'The signed-in user has no records.',
  'The current user has authored zero records.',
  'The reader has no experiments.',
];

/**
 * THE PRIMARY GUARD. The panel's rendered sentences must be EXACTLY the approved
 * set — not a subset, not a superset, no substring matching anywhere.
 *
 * Every test in here is about a set difference, so none of them can be evaded by
 * how a sentence is punctuated, joined, framed or spelled: an unapproved sentence
 * fails because it is unapproved.
 */
describe('the approved-sentence allowlist', () => {
  it('the panel renders exactly the approved sentences, and nothing else', async () => {
    const { container } = await renderMineTab();
    const panel = soleElement(container, '#statistics-tabpanel-mine');

    const rendered = sentenceSet(copyUnitsOf(panel));
    // Vacuity guard first: a broken extractor returning [] would otherwise be
    // reported as a mismatch against a list, which reads like a copy change.
    expect(rendered.length, 'the extractor found no copy at all — it is broken').toBeGreaterThan(30);
    expect(
      rendered,
      'the My Stats panel renders a sentence that is not on the approved list, or no ' +
        'longer renders one that is. If the change is intended, transcribe it into ' +
        'APPROVED_PANEL_SENTENCES in the SAME commit — that entry is where the claim gets reviewed.',
    ).toEqual([...APPROVED_PANEL_SENTENCES].sort());
  });

  it('the page lead renders exactly the approved lead sentence', async () => {
    const { container } = await renderMineTab();
    // `soleElement`, not `querySelector`: a SECOND `.placeholder > p` used to leave
    // the extracted lead set unchanged — see the note on `soleElement`.
    const lead = soleElement(container, '.placeholder > p');
    expect(sentenceSet(copyUnitsOf(lead))).toEqual([...APPROVED_MINE_LEAD_SENTENCES].sort());
  });

  /*
   * THE DESIGN, DEMONSTRATED. Every one of the fourteen measured evasions is
   * rejected by set difference — and so is a sentence that is perfectly TRUE.
   * That is not a bug in the guard, it is the whole mechanism: layer 1 does not
   * read meaning, so it cannot be argued with, and the cost is that an honest copy
   * addition has to be transcribed. The two `it.each` cases below are the same
   * assertion over the two polarities, which is the point being made.
   */
  it.each([...REVIEWER_EVASIONS, 'This preview also has no view for a readiness trend.'])(
    'a sentence the panel does not currently render is rejected, whatever it says: %s',
    async (inserted) => {
      const { container } = await renderMineTab();
      const panel = soleElement(container, '#statistics-tabpanel-mine');
      const withInsertion = sentenceSet([...copyUnitsOf(panel), inserted]);
      expect(withInsertion).not.toEqual([...APPROVED_PANEL_SENTENCES].sort());
    },
  );

  /*
   * …and DELETING an approved sentence fails too, in the other direction. A guard
   * that only rejected additions would let the tab's own zero-denying sentence be
   * removed, which is how the honest copy stops being said.
   */
  it('removing an approved sentence fails as well — the set is exact in both directions', async () => {
    const { container } = await renderMineTab();
    const panel = soleElement(container, '#statistics-tabpanel-mine');
    const units = copyUnitsOf(panel);
    const removed = units.filter((unit) => !unit.includes('A count of zero would say'));
    expect(removed.length, 'the removal must apply').toBeLessThan(units.length);
    expect(sentenceSet(removed)).not.toEqual([...APPROVED_PANEL_SENTENCES].sort());
  });

  /*
   * THE ACCESSIBLE-NAME HALF OF THE EXTRACTOR IS EXERCISED HERE, because the panel
   * currently carries NONE of those attributes — measured: the extraction over
   * `#statistics-tabpanel-mine` yields text nodes only. An unexercised branch of a
   * guard is the same defect as a guard with a hole (it is how `IN_SEGMENT_LABEL_SLOTS`
   * shipped untested), so the mechanism is proved by planting one.
   *
   * `aria-label` is the realistic route: a decorative icon or an icon-only control
   * gets a name, the name is copy, and it is read out to exactly the readers who
   * cannot see the paragraph that qualifies it.
   */
  it.each([...ACCESSIBLE_NAME_ATTRS])(
    'reads copy out of the %s attribute, not just out of text nodes',
    async (attribute) => {
      const { container } = await renderMineTab();
      const panel = soleElement(container, '#statistics-tabpanel-mine');
      const before = sentenceSet(copyUnitsOf(panel));
      expect(before, 'the panel must start clean').toEqual([...APPROVED_PANEL_SENTENCES].sort());

      const heading = panel.querySelector('h2') as HTMLElement;
      expect(heading, 'the panel must have a heading to plant the attribute on').not.toBeNull();
      heading.setAttribute(attribute, 'You have no records.');

      const after = sentenceSet(copyUnitsOf(panel));
      expect(after, `copy in ${attribute} is invisible to the extractor`).toContain(
        'You have no records.',
      );
      expect(after).not.toEqual([...APPROVED_PANEL_SENTENCES].sort());
      // …and layer 2 reports it as well, so the two layers agree about attributes.
      expect(assertsEmptiness('You have no records.')).toBe(true);
    },
  );

  /*
   * LIMITATION 4, CLOSED BY REQUIRING EVERY REFERENCE TO RESOLVE INSIDE THE PANEL.
   *
   * `aria-labelledby` and `aria-describedby` name copy by ID, so the accessible name
   * can live anywhere in the document and the panel-scoped extractor cannot follow
   * it. MEASURED at 134eac2: a `<span id="evil">You have no records.</span>` inside
   * `.placeholder` plus `aria-labelledby="evil"` on the panel `<h2>` changed NEITHER
   * the panel set nor the lead set — the screen-reader user hears the false claim,
   * the sighted reader sees "Personal Statistics".
   *
   * THE OBVIOUS FIX WAS TO FORBID BOTH ATTRIBUTES INSIDE THE PANEL, on the grounds
   * that the panel uses neither. THAT GROUND IS FALSE, and it was measured, not
   * assumed: `StatsPrimitives.tsx`'s `StatsSection` renders
   * `<section aria-labelledby={id}>` and the panel contains TWO of them, so a
   * blanket prohibition fails on shipped, correct markup.
   *
   * What is actually wrong with the plant is not the attribute — it is that the
   * reference points OUT of the compared subtree. Both real sections point at their
   * own `<h2>`, which is inside the panel and therefore already in the sentence set.
   * So the rule is: every IDREF on a panel descendant must resolve, and must resolve
   * to an element the panel contains. The panel ROOT is excluded by name: its
   * `aria-labelledby` points at the tab, which is deliberately outside this scope.
   */
  it('every name reference inside the panel resolves inside the panel', async () => {
    const { container } = await renderMineTab();
    const panel = soleElement(container, '#statistics-tabpanel-mine');

    const references: string[] = [];
    const offenders: string[] = [];
    for (const element of panel.querySelectorAll('*')) {
      for (const attribute of NAME_INDIRECTION_ATTRS) {
        const value = element.getAttribute(attribute);
        if (value === null) continue;
        for (const id of value.split(/\s+/).filter((token) => token !== '')) {
          const where = `<${element.tagName.toLowerCase()} ${attribute}="${id}">`;
          references.push(where);
          const target = container.ownerDocument.getElementById(id);
          if (target === null || !panel.contains(target)) offenders.push(where);
        }
      }
    }
    expect(
      offenders,
      'a panel descendant names its accessible copy by an ID that is not inside the panel, ' +
        'so the approved-sentence set cannot see what a screen reader will read out. Put the ' +
        'referenced copy inside the panel, or add it to APPROVED_PANEL_SENTENCES and widen ' +
        'this scope deliberately.',
    ).toEqual([]);
    // Vacuity guard: the two `StatsSection` cards, each labelled by its own heading.
    // A version of this test that found no reference at all would pass on nothing.
    expect(references, 'no name reference was inspected — the scan is broken').toEqual([
      '<section aria-labelledby="stats-mine-gate">',
      '<section aria-labelledby="stats-mine-planned">',
    ]);

    // The panel ROOT keeps its own `aria-labelledby`, which points OUT by design,
    // and that exception is asserted rather than left unstated.
    expect(panel.getAttribute('aria-labelledby')).toBe('statistics-tab-mine');
  });

  /* …and the rule BITES, on the reviewer's exact plant. */
  it('reports the aria-labelledby plant the two sentence sets cannot see', async () => {
    const { container } = await renderMineTab();
    const panel = soleElement(container, '#statistics-tabpanel-mine');
    const placeholder = soleElement(container, '.placeholder');

    const evil = document.createElement('span');
    evil.id = 'evil';
    evil.textContent = 'You have no records.';
    placeholder.appendChild(evil);
    const heading = panel.querySelector('h2') as HTMLElement;
    heading.setAttribute('aria-labelledby', 'evil');

    // Layer 1 is blind to it — the measurement, kept live rather than described.
    expect(sentenceSet(copyUnitsOf(panel))).toEqual([...APPROVED_PANEL_SENTENCES].sort());
    // …and the plant does reference real copy, so it is not inert.
    expect(container.ownerDocument.getElementById('evil')?.textContent).toBe(
      'You have no records.',
    );
    // …and the resolution rule is what reports it: outside the panel.
    expect(panel.contains(container.ownerDocument.getElementById('evil'))).toBe(false);
    const offenders = [...panel.querySelectorAll('*')].flatMap((element) =>
      NAME_INDIRECTION_ATTRS.flatMap((attribute) => {
        const value = element.getAttribute(attribute);
        if (value === null) return [];
        return value
          .split(/\s+/)
          .filter((id) => id !== '')
          .filter((id) => {
            const target = container.ownerDocument.getElementById(id);
            return target === null || !panel.contains(target);
          })
          .map((id) => `${element.tagName.toLowerCase()} ${attribute}="${id}"`);
      }),
    );
    expect(offenders).toEqual(['h2 aria-labelledby="evil"']);
  });

  /*
   * …and the OTHER half of that plant: the second `.placeholder > p`, which used to
   * be swallowed by `querySelector`. `soleElement` is what fails now.
   */
  it('refuses to extract the page lead when there is more than one', async () => {
    const { container } = await renderMineTab();
    const placeholder = soleElement(container, '.placeholder');
    const second = document.createElement('p');
    second.textContent = 'You have no records.';
    placeholder.appendChild(second);

    expect(container.querySelectorAll('.placeholder > p')).toHaveLength(2);
    // The old `querySelector` returned the FIRST one and the false sentence was
    // never compared against anything: proved, not asserted.
    expect(
      sentenceSet(copyUnitsOf(container.querySelector('.placeholder > p') as HTMLElement)),
    ).toEqual([...APPROVED_MINE_LEAD_SENTENCES].sort());
    expect(() => soleElement(container, '.placeholder > p')).toThrow();
  });

  it('carries no duplicate entry, so the sorted comparison is well defined', () => {
    for (const [name, list] of [
      ['APPROVED_PANEL_SENTENCES', APPROVED_PANEL_SENTENCES],
      ['APPROVED_MINE_LEAD_SENTENCES', APPROVED_MINE_LEAD_SENTENCES],
    ] as const) {
      expect(new Set(list).size, `${name} lists a sentence twice`).toBe(list.length);
    }
  });

  /*
   * …and each entry is ONE sentence, so an entry cannot smuggle a second claim in
   * behind a full stop. Checked with the same splitter the comparison uses.
   */
  it('every entry is a single sentence under the splitter that compares them', () => {
    for (const entry of [...APPROVED_PANEL_SENTENCES, ...APPROVED_MINE_LEAD_SENTENCES]) {
      expect(sentencesOfCopy(entry), `"${entry}" is more than one sentence`).toEqual([entry]);
    }
  });

  /*
   * LAYER 2, APPLIED WHERE IT NOW BELONGS. The emptiness matcher reads the
   * allowlist's own entries, so a false sentence transcribed into it — the one
   * route past layer 1 — is reported.
   */
  it('no approved sentence asserts that the reader has nothing', () => {
    for (const entry of [...APPROVED_PANEL_SENTENCES, ...APPROVED_MINE_LEAD_SENTENCES]) {
      expect(emptinessClaims(entry), `approved sentence: ${entry}`).toEqual([]);
    }
  });

  it.each([...REVIEWER_EVASIONS])(
    'an approved sentence that asserts an emptiness is rejected: %s',
    (sentence) => {
      const wouldBeApproved = [...APPROVED_PANEL_SENTENCES, sentence];
      const flagged = wouldBeApproved.filter((entry) => assertsEmptiness(entry));
      expect(flagged).toEqual([sentence]);
    },
  );
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
   * POSITION, NOT PRESENCE — the generation-3 fix, and the one that catches all
   * ten of the third reviewer's sentences without knowing what joins two clauses.
   * Each pair contains the SAME claim and the SAME modal vocabulary; they differ
   * only in whether the denial opens before the claim ends or after it.
   */
  it.each([
    [
      'You have no records and this preview cannot tell you more than that.',
      'A count of zero would say you have no records.',
    ],
    ['You have no records: this preview cannot tell you more.', 'It would be wrong to say you have no records.'],
    [
      'Your export count is zero — no way to say otherwise.',
      'Nothing would be attributed to you rather than to an account.',
    ],
    ['The reader has no experiments.', 'A count of zero would say the reader has no experiments.'],
  ])('a denial that FOLLOWS the claim does not unsay it: %s', (claim, denial) => {
    expect(assertsEmptiness(claim), `must be FLAGGED: ${claim}`).toBe(true);
    expect(assertsEmptiness(denial), `must PASS: ${denial}`).toBe(false);
  });

  /*
   * …AND THE MIRROR OF THAT, which is how a FOURTH reviewer got past the positional
   * rule: put the denial FIRST and delete the comma, so the whole sentence stays one
   * clause and the escape legitimately opens before the trigger ends. All four
   * MEASURED unflagged at 134eac2, sentence 1 additionally rendered in the panel and
   * transcribed into both allowlists — 284 of 284 passing.
   *
   * The must-PASS half of each pair carries the SAME denial vocabulary in a position
   * that really does govern the claim's own clause, so the pair cannot be satisfied
   * by simply flagging everything with `and` in it.
   */
  it.each([
    [
      'This preview cannot tell whose records these are and you have no records.',
      'This preview cannot tell whose records these are, and a count of zero would say you have no records.',
    ],
    [
      'Unable to attribute anything, you have no records.',
      'Unable to attribute anything, this build would be wrong to say you have no records.',
    ],
    [
      'This build cannot say who you are but you have no records.',
      'This build cannot say who you are, but it would be wrong to say you have no records.',
    ],
    [
      'A count of zero would be wrong and you have no records.',
      'A count of zero would be wrong, so it would be wrong to say you have no records.',
    ],
  ])('a denial that PRECEDES the claim in another clause does not excuse it: %s', (claim, denial) => {
    expect(assertsEmptiness(claim), `must be FLAGGED: ${claim}`).toBe(true);
    expect(assertsEmptiness(denial), `must PASS: ${denial}`).toBe(false);
  });

  /*
   * …and a BARE coordinator really does end a clause, asserted on the splitter
   * itself rather than only through the four sentences above — so a future
   * narrowing of `clausesOf` fails here with the reason visible.
   */
  it.each(['and', 'but', 'so', 'or', 'yet'])('splits on a bare "%s", with no comma', (joiner) => {
    expect(clausesOf(`you have records ${joiner} you have none`)).toEqual([
      'you have records',
      'you have none',
    ]);
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

    // Vacuity guard: the block must be the real thing, not two empty slices —
    // and it must carry BOTH layers, since layer 1 is what the browser copy is
    // now mostly for.
    expect(here).toContain('function emptinessClaims');
    expect(here).toContain('SUBJECTLESS_EMPTINESS');
    expect(here).toContain('const APPROVED_PANEL_SENTENCES');
    expect(here).toContain('const APPROVED_MINE_LEAD_SENTENCES');
    expect(here).toContain('function sentenceSet');
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
   * WIRING AN IDENTITY CHANGES NOTHING — ASSERTED AT THE COMPONENT, not one layer
   * down.
   *
   * `MyStats.tsx` claims both adapters are "injectable so a test can prove the tab
   * renders the state a source reports", and no test passed `currentUser` at all:
   * the `source ?? personalStatisticsSourceFor(currentUser.get())` selection was
   * covered by nothing, and the file's own comment cited a test in the wrong file
   * for it. `current-user-contract.test.ts` sweeps the PURE FUNCTION over the whole
   * state union; this renders the component with the one state that could plausibly
   * unlock something.
   *
   * §8-relevant, and the reason it is worth a render rather than a unit call: the
   * fixture user carries a subject value AND a display name, so if the selection
   * ever grew a greeting or a scoped read, the assertions below would catch the
   * value on screen as well as the changed gate.
   */
  it('a present current user changes nothing on this tab', () => {
    const reporting = currentUserSourceReporting({
      status: 'present',
      user: fixtureCurrentUser,
    });
    /* Wrapped in a spy so "the component consulted it" is measured rather than
       assumed — a component that ignored the prop entirely would satisfy every
       assertion below. */
    const get = vi.fn(reporting.get);
    const currentUser: CurrentUserSource = { id: reporting.id, get };
    const { container } = render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <MyStats currentUser={currentUser} />
      </MemoryRouter>,
    );

    // The SAME gate sentence the disabled default produces — `no_record_ownership`,
    // not `no_signed_in_account`: knowing who the reader is does not make one
    // dataset here answerable, because no record carries an author.
    expect(screen.getByText(MY_STATS_PENDING_COPY.no_record_ownership)).toBeInTheDocument();
    expect(screen.queryByText(MY_STATS_PENDING_COPY.no_signed_in_account)).toBeNull();

    // Nothing about the person reaches the DOM: not the subject key, not the
    // display name, not a greeting, not an origin header name.
    const text = textOf(container);
    const { displayName } = fixtureCurrentUser;
    // …and the fixture really does carry one, or that assertion means nothing.
    expect(displayName, 'the fixture must name somebody').not.toBeNull();
    expect(text).not.toContain(fixtureCurrentUser.subject.value);
    expect(text).not.toContain(String(displayName));
    expect(text).not.toContain(fixtureCurrentUser.subject.observedFrom);
    expect(text).not.toMatch(/signed in as|Signed in|Hello|Welcome back/i);
    // …and no figure appeared, personal or otherwise.
    expect(container.querySelector('figure.stats-chart')).toBeNull();
    expect(text).not.toMatch(/\b\d+\b/);

    // THE SOURCE WAS ACTUALLY CONSULTED — once, on this render.
    expect(get).toHaveBeenCalledTimes(1);
    expect(get).toHaveReturnedWith({ status: 'present', user: fixtureCurrentUser });
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
    const lead = soleElement(container, '.placeholder > p');
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

    const lead = sentencesOf(soleElement(container, '.placeholder > p'));
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

  /*
   * WHICH DESCRIPTION SITS UNDER WHICH TITLE — layer 1's limitation 2, pinned here
   * because a SET comparison cannot see a pairing.
   *
   * MEASURED at 134eac2: swapping the `description` strings of `readiness_trend` and
   * `exports_over_time` in `lib/myStatsContract.ts` passed the whole frontend suite,
   * 2799 of 2799, while the tab described each view as the other — "Export Readiness
   * Over Time … how many official records you exported in each period." Both
   * sentences are approved, so the set is unchanged; both are individually TRUE of
   * some view, so layer 2 has nothing to say; and every sentence still names a unit,
   * so the guard above passes too.
   *
   * Transcribed rather than derived from `MY_STATS_VIEWS`, for the same reason the
   * approved-sentence lists are: a table built from the thing it checks passes
   * whatever that thing says. The duplication IS the mechanism.
   */
  it('pairs each planned view with its own title and description', () => {
    const pairs = MY_STATS_VIEWS.map((view) => [view.id, view.title, view.description]);
    expect(
      pairs,
      'a planned view has been re-titled, re-described, re-ordered or re-paired. Every ' +
        'sentence here is already on APPROVED_PANEL_SENTENCES, so the approved-sentence set ' +
        'CANNOT see a swap — this is the only test that can.',
    ).toEqual([
      [
        'workflow_counts',
        'Records You Author, by Workflow Step',
        'how many records you author sit at each step of the five-step workflow, counted once each at their first unsatisfied step.',
      ],
      [
        'evidence_support_distribution',
        'Evidence Support in Records You Author',
        'what share of the fields in records you author is supported by evidence, counted in fields rather than in records.',
      ],
      [
        'owned_vs_collaborated',
        'Records You Authored and Records You Contributed To',
        'how many records name you as their author, and how many you contributed to without authoring. A record can be both, so the two are never added together.',
      ],
      [
        'common_blockers',
        'What Most Often Blocks Records You Author',
        'which unmet requirements appear most often across the records you author. One record can carry several, so these do not sum to a record count.',
      ],
      [
        'readiness_trend',
        'Export Readiness Over Time',
        'how many records you author were ready to export in each period.',
      ],
      [
        'validation_issues_over_time',
        'Validation Issues Over Time',
        'how many schema-validation issues were raised against the records you author, in each period.',
      ],
      [
        'exports_over_time',
        'Exports You Made Over Time',
        'how many official records you exported in each period.',
      ],
      [
        'recent_activity',
        'Your Recent Activity',
        'the most recent changes you made, each linking to the record it affected.',
      ],
    ]);
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
