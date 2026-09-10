/*
 * R1b · ONE upload claim, four sites — and the ban on the absolute form.
 *
 * WHY THIS FILE EXISTS. Four surfaces describe the same boundary to a reader:
 *
 *   - `screens/GovernancePage.tsx`   → Governance & Safety → Policy
 *   - `screens/LoadMaterials.tsx`    → the approval-gated on-ramp's warning line
 *   - `lib/settingsContent.ts`       → Settings → Data & Privacy →
 *                                      `no-real-experiment-data`
 *   - `lib/mcpConnectContent.ts`     → Settings → Connect Your Agent, the
 *                                      `no-upload` row of the refused-capability
 *                                      list
 *
 * Nothing pinned them to each other, and they drifted. `settingsContent.ts` was
 * corrected to say that file UPLOAD is refused with nothing parsed, *while* the
 * CSV preview and the record validator do read what you paste or pick. The other
 * two kept the older, absolute sentence — "every file upload is refused
 * outright, whatever it contains, and no file is read, parsed, or inspected" —
 * which is FALSE of this build, and false on the very page that mounts the
 * validator one tab away (`GovernancePage.tsx`'s `validator` tab renders
 * `components/RecordValidator.tsx`, which calls `file.text()`).
 *
 * THE FOURTH ARRIVED LATE, AND IT ARRIVED FALSE. It shipped reading "File
 * ingestion is refused for this whole deployment, agent or not" — the same
 * deployment-wide claim the other three had already been corrected for — and it
 * passed this guard untouched, because it was not in `SITES` and because §3
 * bans the shapes that shipped ("no file is read/parsed/inspected") rather than
 * the claim, and "ingestion" is not one of them. A claim that escapes a ratchet
 * by synonym is not held by it. Adding the site is the fix; the wording change
 * alone would have left the next one free to drift the same way.
 *
 * WHAT IT ASSERTS, and why in this order:
 *
 *  §1 the file-reading controls REALLY EXIST in this build. The ban in §3 is
 *     only justified while they do. If a later slice genuinely removes both
 *     readers, §1 fails first and tells the next reader to revisit §3 rather
 *     than leaving a stale prohibition standing on nothing.
 *  §2 all four sites make the SAME claim — the refusal, the two readers by
 *     name, in-memory-not-stored, outcome-not-content. Parity is the property
 *     that was missing; a site that states half of it is a site that will drift
 *     again.
 *  §3 no site states the absolute "no file is read/parsed/inspected".
 *  §4 the guard is proven on the exact string that shipped, so a pattern
 *     narrowed until it detects nothing fails here rather than going quiet.
 *
 * WHAT IT CANNOT CATCH, stated plainly. It is a parity ratchet over four claim
 * shapes, not a detector for "is this paragraph true". A novel phrasing that
 * implies the app never reads a file — "your files never leave your machine",
 * "nothing you pick is opened" — satisfies every pattern here. A human reviewer
 * remains the backstop for newly written data claims. It also reads
 * `apps/web/src` only: backend-served copy (`routes.py`'s refusal reason, the
 * OpenAPI descriptions the Endpoint Explorer renders) is invisible to it.
 *
 * A FIFTH SITE, ADDED LATER, AND DELIBERATELY KEPT OUT OF §§2–4. Found by
 * review: `lib/transcriptCaptureContent.ts`'s `voiceAudioHandling` claimed
 * "This application declares no upload endpoint for it to reach" — false;
 * `POST /api/uploads` IS declared (`apps/api/isaac_api/routes.py`). That is a
 * DIFFERENT false-claim shape from the four above — an existence claim about
 * the upload ROUTE, not a reading claim about the validator or the CSV
 * preview — and the sentence is not about either reader at all, so forcing it
 * into `SITES`/`SHARED_CLAIM` would fail on correct copy rather than catch
 * anything. §5 below pins the narrower, real invariant it needs: no site may
 * claim the upload route does not exist; the true and stronger claim is that
 * the one route that exists refuses every request it gets.
 */

import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect, afterEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { GovernancePage } from '../screens/GovernancePage';
import { LoadMaterials } from '../screens/LoadMaterials';
import { ConnectYourAgentPanel } from '../screens/settings/ConnectYourAgent';
import { settingsConcepts } from '../lib/settingsContent';
import { MCP_CAPABILITIES_REFUSED } from '../lib/mcpConnectContent';
import { CAPTURE_COPY } from '../lib/transcriptCaptureContent';

afterEach(cleanup);

// --- locating and reading the real sources -----------------------------------

/** Deliberately NOT `import.meta.url`: under jsdom that is an http URL, not a
 *  file one. Duplicated from the sibling guards rather than exported, so no file
 *  can silently change another's scan. */
function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  return found;
}

const SRC_DIR = locateSrcDir();

/*
 * A comment-stripping source reader was here. It is deliberately GONE: the two
 * page-level sites are checked by RENDERING them (see `policyTabText` below), not
 * by scanning their source, because a source scan of `GovernancePage.tsx` matches
 * `/validator/i` on its `import { RecordValidator }` line and would pass without a
 * word of copy saying so. Rendering is the stronger check, so the reader it
 * replaced is removed rather than left dangling for a future edit to reach for.
 */

/** The raw source, comments included — for the §1 capability proof, which is
 *  about what the code DOES, not about what any copy says. */
function rawSource(path: string): string {
  return readFileSync(join(SRC_DIR, path), 'utf8');
}

const SETTINGS_FACTS = {
  dataRegime: 'synthetic-only',
  persistence: 'ephemeral',
  recordSchemaVersion: '1.05',
};

function noRealDataDetail(): string {
  const found = settingsConcepts(SETTINGS_FACTS).find((c) => c.id === 'no-real-experiment-data');
  if (!found) throw new Error('no such concept: no-real-experiment-data');
  return `${found.heading} ${found.summary} ${found.detail}`;
}

/**
 * The four sites, as the text a reader actually meets.
 *
 * The first two are RENDERED, not source-scanned. A source scan of
 * `GovernancePage.tsx` matches `/validator/i` on its `import { RecordValidator }`
 * line, so the "names the validator" assertion would pass without a word of copy
 * saying so — a vacuous guard is worse than none. Rendering also proves the copy
 * is on the surface the reader is looking at rather than merely present in the
 * module.
 */
function policyTabText(): string {
  render(
    <MemoryRouter
      initialEntries={['/governance']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <GovernancePage />
    </MemoryRouter>,
  );
  return screen.getByRole('tabpanel').textContent ?? '';
}

function loadMaterialsWarnText(): string {
  const { container } = render(
    <MemoryRouter
      initialEntries={['/load']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <LoadMaterials />
    </MemoryRouter>,
  );
  const warn = container.querySelector('.onramp-warn');
  if (warn === null) throw new Error('the on-ramp governance warning is not rendered');
  return warn.textContent ?? '';
}

/**
 * The Connect Your Agent tab's refused-capability row, as the reader meets it.
 *
 * Read off the content module the way `noRealDataDetail` is — the claim is
 * authored there and the row is the unit that makes it, so scanning the whole
 * panel would let a neighbouring paragraph supply half the claim and count as
 * parity. A site has to state the whole thing WHERE IT STATES THE REFUSAL, or a
 * reader of the capability table gets the half-truth on its own.
 *
 * It still RENDERS the panel and asserts the row is on the surface, because the
 * failure mode a constant-read misses is copy that exists in the module and is
 * not shown. `getByText` throws when it is not found, so the render is a real
 * assertion rather than a decoration.
 */
function mcpNoUploadRow(): string {
  const row = MCP_CAPABILITIES_REFUSED.find((c) => c.id === 'no-upload');
  if (!row) throw new Error('no such refused capability: no-upload');
  render(<ConnectYourAgentPanel onOpenExplorer={() => {}} />);
  screen.getByText(row.detail);
  return `${row.action} ${row.detail}`;
}

const SITES: [string, () => string][] = [
  ['Governance → Policy', policyTabText],
  ['the Load Materials on-ramp warning', loadMaterialsWarnText],
  ['Settings → Data & Privacy → no-real-experiment-data', noRealDataDetail],
  ['Settings → Connect Your Agent → the no-upload capability row', mcpNoUploadRow],
];

// --- §1 the readers this ban is justified by ---------------------------------

/**
 * The two controls that DO read a user-chosen file. Each is proven by the read
 * call itself, not by a comment about it — `Blob.text()` with a `FileReader`
 * fallback, reached from an `<input type="file">` change handler.
 */
const FILE_READING_CONTROLS: [string, string][] = [
  ['the standalone record validator', 'components/RecordValidator.tsx'],
  ['the campaign-sheet reconciliation preview', 'components/CsvReconcilePanel.tsx'],
];

describe('R1b §1 · the file-reading controls exist, so the absolute claim is false', () => {
  it.each(FILE_READING_CONTROLS)('%s reads the chosen file', (_what, path) => {
    const src = rawSource(path);
    // The read itself.
    expect(src).toMatch(/file\.text\(\)/);
    expect(src).toMatch(/new FileReader\(\)/);
    // ...reached from a real file picker, so a user can actually get there.
    expect(src).toMatch(/type="file"/);
  });

  it('the Governance page mounts one of them one tab away from its own policy copy', () => {
    const src = rawSource('screens/GovernancePage.tsx');
    expect(src).toMatch(/<RecordValidator\s*\/>/);
  });
});

// --- §2 the shared claim -----------------------------------------------------

/**
 * The four parts of the one claim. Every site must state ALL of them: a site
 * that states the refusal without the readers is the exact half-truth this file
 * exists to stop, and a site that names the readers without the in-memory bound
 * over-discloses in the other direction (it sounds like the file is kept).
 *
 * The patterns are deliberately tolerant of wording — the sites read differently
 * because their contexts differ, and forcing four identical paragraphs would be
 * worse copy for no extra truth. What is pinned is the CLAIM, not the sentence.
 */
const SHARED_CLAIM: [string, RegExp][] = [
  ['file upload is refused outright', /file upload is refused outright/i],
  ['the record validator is named as a reader', /validator/i],
  ['the CSV/campaign-sheet preview is named as a reader', /(csv|campaign sheet)/i],
  [
    'what those two do read is read in memory and not stored',
    /in memory[^.]{0,80}(never stored|discard)|(never stored|discard)[^.]{0,80}in memory/i,
  ],
  [
    'only the outcome is recorded, never the content',
    /(only|just)[^.]{0,40}outcome[^.]{0,60}never[^.]{0,20}content/i,
  ],
];

describe('R1b §2 · all four sites state the same claim', () => {
  for (const [site, text] of SITES) {
    describe(site, () => {
      it.each(SHARED_CLAIM)('states %s', (_what, pattern) => {
        expect(text()).toMatch(pattern);
      });
    });
  }
});

// --- §3 the absolute form is banned -----------------------------------------

/**
 * The shapes that assert nothing anywhere reads a file. Each is an ABSOLUTE:
 * scoped forms — "the refused upload is never read", "no file is parsed at all"
 * as a clause on the upload refusal — are the correct wording and must pass.
 *
 * `parsed at all` is excluded from the first pattern on purpose:
 * `settingsContent.ts` says "file upload is refused outright, with no file
 * parsed at all", where the subject is unambiguously the refused upload. The
 * pattern targets the unrestricted claim about reading, which is the one that
 * shipped false.
 */
const ABSOLUTE_NO_READ: [string, RegExp][] = [
  ['no file is read/inspected anywhere', /\bno file is (ever )?(read|inspected)\b/i],
  ['no file is read, parsed, or inspected', /\bno file is read, parsed,? (or|and) inspected\b/i],
  ['nothing is read, parsed, or inspected', /\bnothing is (ever )?read, parsed,? (or|and) inspected\b/i],
  ['no file you choose is ever opened or read', /\bno file (you|a user) (choose|chooses|picks?) is (ever )?(opened|read)\b/i],
];

/*
 * §3b — POLARITY. Found by negative control while integrating this slice, and the
 * finding is recorded because the guard as first written did not survive it.
 *
 * The control inverted the disclosure to `No review tool reads a file you paste or
 * pick` and ALL 35 assertions still passed. §2 only requires each site to MENTION
 * the validator, the CSV preview, the in-memory bound and the outcome-only bound —
 * a negation keeps every one of those words. §3 bans four specific sentences that
 * shipped, and the inverted sentence is not one of them. So the four topics were
 * pinned and the CLAIM'S DIRECTION was not: the guard could not tell "these two do
 * read" from "these two do not read", which is the entire difference between the
 * true wording and the false one.
 *
 * Two additions, because either alone is defeatable:
 *
 * The fix is ONE tight pattern plus a regression fixture, and the two rejected
 * alternatives are worth recording because both are tempting and both are wrong:
 *
 *   A greedy `[^.]{0,60}` window between the negator and the reader noun produces
 *   FALSE POSITIVES on the correct copy. `settingsContent` reads "…with no file
 *   parsed at all, while the CSV preview and the record validator do read what you
 *   paste or pick" — the `no` attaches to the refused UPLOAD, and a window that
 *   crosses the comma reads it as attaching to the readers. So the window is
 *   `[^.,]` — a negator only counts when it governs the same clause.
 *
 *   Requiring an AFFIRMATIVE reader sentence (name a reader, say it reads, contain
 *   no negator) was tried and abandoned. Correct copy pairs the two polarities in
 *   one sentence on purpose — "Two review tools DO READ a file you paste or pick,
 *   and NEITHER adds it to the workspace" — so the negator test excluded the very
 *   sentence it was meant to find, failing all three sites. Detecting polarity in
 *   English needs a parser, and a guard that misfires on true copy is worse than
 *   the gap it closes: it trains the next reader to weaken it.
 *
 * So the structural half is a FIXTURE, not a parser: §4b pins the exact inverted
 * sentence the control used and asserts the pattern rejects it. Deterministic, and
 * it cannot rot into vacuity the way a topic-mention check did.
 */
const NEGATED_READER: [string, RegExp][] = [
  [
    'a negator governing the reader nouns in the same clause',
    /\b(no|neither|none of|not one)\b[^.,]{0,30}\b(review tool|validator|preview|reconciliation)\b[^.,]{0,30}\b(read|reads|parse|parses|inspect|inspects|open|opens)\b/i,
  ],
  [
    'a reader noun denied in the same clause',
    /\b(review tool|validator|csv preview|campaign sheet)\b[^.,]{0,30}\b(never|does not|do not|doesn't|don't|cannot|can't)\b[^.,]{0,20}\b(read|reads|parse|parses|inspect|inspects|open|opens)\b/i,
  ],
];

/** The exact sentence the integration negative control substituted, which the
 *  first version of this guard passed. Kept verbatim as a fixture. */
const INVERTED_DISCLOSURE =
  'No review tool reads a file you paste or pick, and neither adds it to the workspace: ' +
  'the Validator on the next tab, and campaign-sheet CSV reconciliation on a record’s ' +
  'evidence trail. Each checks the text in memory and discards it, and records only the ' +
  'outcome — never the content.';

describe('R1b §3 · no site claims the absolute "no file is read"', () => {
  for (const [site, text] of SITES) {
    it.each(ABSOLUTE_NO_READ)(`${site} never claims %s`, (_what, pattern) => {
      expect(text()).not.toMatch(pattern);
    });
  }
});

describe('R1b §3b · no site denies that the two review tools read', () => {
  for (const [site, text] of SITES) {
    it.each(NEGATED_READER)(`${site} never states %s`, (_what, pattern) => {
      expect(text()).not.toMatch(pattern);
    });
  }
});

describe('R1b §4b · the polarity pattern is proven on the string that defeated §2', () => {
  it('rejects the inverted disclosure', () => {
    const caught = NEGATED_READER.filter(([, p]) => p.test(INVERTED_DISCLOSURE)).map(
      ([label]) => label
    );
    expect(
      caught,
      'the inverted disclosure ("No review tool reads…") is not caught. This exact ' +
        'sentence passed all 35 assertions of the first version of this guard, because ' +
        '§2 checks only that the validator and the CSV preview are MENTIONED and a ' +
        'negation mentions them just as well. If this assertion fails, the guard has ' +
        'regressed to pinning topics instead of the claim.'
    ).not.toHaveLength(0);
  });

  // One test PER SITE, not one loop over all of them. `policyTabText` renders, and
  // `cleanup` runs between tests rather than between calls — looping renders the
  // second site on top of the first, and the by-role query then matches two
  // tabpanels. That is a harness artefact, not a copy defect, and it is easy to
  // misread as one.
  for (const [site, text] of SITES) {
    it(`does NOT fire on the correct copy of ${site}`, () => {
      // Hoisted: `text()` RENDERS, and `.filter` would call it once per pattern —
      // two renders in one test, which the by-role query reports as an ambiguous
      // match rather than as the copy defect it is not.
      const rendered = text();
      const fired = NEGATED_READER.filter(([, p]) => p.test(rendered)).map(([label]) => label);
      expect(
        fired,
        `${site} is correct copy and must not trip the polarity pattern. A false ` +
          `positive here is worse than the gap it closes: it teaches the next reader ` +
          `to weaken the guard rather than fix the copy.`
      ).toEqual([]);
    });
  }
});

// --- §4 the guard is proven on the string that shipped ----------------------

/** `screens/GovernancePage.tsx` and `screens/LoadMaterials.tsx` at `b595a50` —
 *  the same absolute sentence in both, word for word in its load-bearing half. */
const RETIRED_GOVERNANCE_ABSOLUTE =
  'Nothing is uploaded to a model or index without that approval: every file upload is ' +
  'refused outright, whatever it contains, and no file is read, parsed, or inspected.';

const RETIRED_LOAD_MATERIALS_ABSOLUTE =
  'Every file upload is refused outright, whatever it contains — no file is read, parsed, ' +
  'or inspected. Keeping real or private artifacts out is the operator’s responsibility, ' +
  'not a check this software performs.';

function absoluteClaims(text: string): string[] {
  return ABSOLUTE_NO_READ.filter(([, pattern]) => pattern.test(text)).map(([label]) => label);
}

function missingClaims(text: string): string[] {
  return SHARED_CLAIM.filter(([, pattern]) => !pattern.test(text)).map(([label]) => label);
}

describe('R1b §4 · the guard rejects the exact strings that shipped', () => {
  it.each([
    ['the Governance → Policy sentence', RETIRED_GOVERNANCE_ABSOLUTE],
    ['the Load Materials warning', RETIRED_LOAD_MATERIALS_ABSOLUTE],
  ])('flags %s as an absolute no-read claim', (_what, retired) => {
    expect(absoluteClaims(retired).length).toBeGreaterThan(0);
  });

  it.each([
    ['the Governance → Policy sentence', RETIRED_GOVERNANCE_ABSOLUTE],
    ['the Load Materials warning', RETIRED_LOAD_MATERIALS_ABSOLUTE],
  ])('flags %s as missing most of the shared claim', (_what, retired) => {
    // Both retired strings state the refusal and nothing else about the readers.
    expect(missingClaims(retired)).toContain('the record validator is named as a reader');
    expect(missingClaims(retired)).toContain(
      'what those two do read is read in memory and not stored',
    );
  });

  it('leaves the correctly scoped wording alone', () => {
    for (const scoped of [
      // `settingsContent.ts`'s corrected formulation, which is the model.
      'file upload is refused outright, with no file parsed at all, while the CSV preview and ' +
        'the record validator do read what you paste or pick — in memory, never stored, and ' +
        'logged only as an outcome, never as content.',
      // A refusal scoped to the upload path, which is true and must stay sayable.
      'every file upload is refused outright, whatever it contains, and the refused upload is ' +
        'never read, parsed, or inspected.',
    ]) {
      expect(absoluteClaims(scoped), scoped).toEqual([]);
    }
  });
});

// --- §5 no site anywhere claims the upload ROUTE does not exist -------------
//
// `lib/transcriptCaptureContent.ts`'s `voiceAudioHandling` is about audio, not
// about the validator or the CSV preview, so it does not belong in `SITES`/
// `SHARED_CLAIM` above (§2 requires naming both readers, which an
// audio-privacy sentence has no business doing) — see the file header. The
// false shape it shipped was an EXISTENCE claim about the upload route
// ("declares no upload endpoint for it to reach"), not a reading claim, so it
// needs its own ban and its own polarity proof rather than reuse of §3/§3b,
// which are about a different sentence entirely.
//
// THE BAN ITSELF NEEDS NO READER VOCABULARY, so unlike the claim-parity check
// above it is not scoped to one site. It runs over all FIVE surfaces that
// discuss the upload path (the original four `SITES` plus the capture site),
// AND over every string value `CAPTURE_COPY` currently holds, so a future key
// making the same mistake is caught without anyone remembering to list it.
//
// PATTERN HISTORY: the first version of this ban shipped with two patterns
// that missed 7 of 8 plausible phrasings an independent review tried against
// it — including a one-word edit ("route" for "endpoint") of the very
// sentence it was written to catch. The widened set below was re-measured
// against the same eight phrasings; see the probe at the bottom of this
// section, which is a real test and fails if any of the eight goes uncaught.

function captureVoiceAudioHandling(): string {
  return CAPTURE_COPY.voiceAudioHandling;
}

/**
 * Four shapes of "the upload route does not exist / cannot receive
 * anything", covering declarative ("X declares no route"), existential
 * ("there is no route"), passive ("no route is declared"), and capability
 * ("nothing can receive an upload") phrasings. None of the four needs the
 * word "upload" to precede "endpoint/route/api" — `(upload\s+)?` is optional
 * throughout, and endpoint/route/api all take an optional plural `s?`.
 */
const ABSOLUTE_NO_ENDPOINT: [string, RegExp][] = [
  [
    'declares/has/exposes no (upload) endpoint/route/api',
    /\b(declares|declared|has|exposes|expose)\s+no\s+(upload\s+)?(endpoint|route|api)s?\b/i,
  ],
  [
    'there is/are no (upload) endpoint/route/api',
    /\bthere\s+(is|are)\s+no\s+(upload\s+)?(endpoint|route|api)s?\b/i,
  ],
  [
    'no (upload) endpoint/route/api is/are declared/exposed',
    /\bno\s+(upload\s+)?(endpoint|route|api)s?\s+(is|are)\s+(declared|exposed)\b/i,
  ],
  [
    'nothing/no-X can receive or accept an upload',
    /\b(nothing|no\s+\S+)\b[^.,]{0,40}\b(receive|receives|accept|accepts)\b[^.,]{0,30}\bupload\b/i,
  ],
];

/** The exact sentence that shipped, before this slice's first correction.
 *  Kept verbatim as the primary polarity fixture. */
const RETIRED_CAPTURE_ABSOLUTE =
  'Audio stays in this tab’s memory. It is never uploaded, never written to ' +
  'disk, and is discarded when you clear it, leave this record, or reload the ' +
  'page. This application declares no upload endpoint for it to reach.';

/**
 * Eight plausible future phrasings of the same false existence claim, used
 * by an independent review to show the first pattern set caught only one of
 * them. Re-measured here on every change to `ABSOLUTE_NO_ENDPOINT` — this is
 * the "re-run the probe yourself" requirement, not a one-time note.
 */
const PLAUSIBLE_NO_ENDPOINT_PHRASINGS = [
  'There is no endpoint here that accepts an upload.',
  'This application exposes no route that accepts a file.',
  'Nothing in this build can receive an upload.',
  'No upload API is declared.',
  'This application declares no endpoint for uploads.',
  'The application has no upload endpoints.',
  'There is no upload route for it to reach.',
  'This application declares no upload route.',
];

function noEndpointClaims(text: string): string[] {
  return ABSOLUTE_NO_ENDPOINT.filter(([, pattern]) => pattern.test(text)).map(([label]) => label);
}

describe('R1b §5 · no upload-claim site, and no CAPTURE_COPY string, claims the route does not exist', () => {
  it('flags the retired sentence as an absolute no-endpoint claim', () => {
    expect(
      noEndpointClaims(RETIRED_CAPTURE_ABSOLUTE),
      'the retired sentence ("This application declares no upload endpoint for ' +
        'it to reach") shipped false — POST /api/uploads is declared — and this ' +
        'assertion is the polarity proof: if it fails, the pattern set below has ' +
        'gone quiet and would not have caught the defect it was written for.',
    ).not.toHaveLength(0);
  });

  it('the eight-phrasing probe: every plausible future false phrasing is caught', () => {
    const missed = PLAUSIBLE_NO_ENDPOINT_PHRASINGS.filter((s) => noEndpointClaims(s).length === 0);
    expect(
      missed,
      'one or more plausible false phrasings of "the upload route does not ' +
        'exist" is not caught by ABSOLUTE_NO_ENDPOINT. Widen the pattern set — ' +
        'do not narrow this list to make the test pass.',
    ).toEqual([]);
  });

  it('the corrected capture copy does not trip any pattern', () => {
    expect(noEndpointClaims(captureVoiceAudioHandling()), captureVoiceAudioHandling()).toEqual([]);
  });

  describe('applies to all five upload-claim surfaces, not just the capture site', () => {
    const ALL_FIVE: [string, () => string][] = [...SITES, ['transcript capture: voiceAudioHandling', captureVoiceAudioHandling]];
    for (const [site, text] of ALL_FIVE) {
      it(`${site} does not claim the route does not exist`, () => {
        // Hoisted to ONE call: `text()` renders for three of the five sites,
        // and `cleanup` runs between TESTS, not between calls — a second call
        // in the same test (e.g. as a would-be assertion message) renders the
        // site twice with no cleanup in between, which trips `getByRole`/
        // `getByText`'s "multiple elements found" as a false failure. Same
        // harness artefact §4b already documents for `policyTabText`.
        const rendered = text();
        expect(noEndpointClaims(rendered), rendered).toEqual([]);
      });
    }
  });

  it('no string value anywhere in CAPTURE_COPY claims the route does not exist', () => {
    const offenders: string[] = [];
    for (const [key, value] of Object.entries(CAPTURE_COPY)) {
      if (typeof value !== 'string') continue; // functions (e.g. summaryStored) are excluded — see below
      if (noEndpointClaims(value).length > 0) offenders.push(key);
    }
    expect(
      offenders,
      'a CAPTURE_COPY string other than voiceAudioHandling now claims the ' +
        'upload route does not exist. Note: string-returning FUNCTIONS in ' +
        'CAPTURE_COPY (summaryStored, runTargetsRun, etc.) are not scanned by ' +
        'this loop, because it iterates typeof === "string" values only — a ' +
        'future key of that shape needs its own assertion.',
    ).toEqual([]);
  });
});

/**
 * §5b — the affirmative claim, pinned TOLERANTLY (per `SHARED_CLAIM`'s own
 * rule at :222, "What is pinned is the CLAIM, not the sentence"). The ban
 * above is satisfied by deleting the sentence outright, so an affirmative
 * pin is still needed to keep the reassurance from being silently dropped —
 * but a literal-phrase pin (`/upload route/i` + `/refuses every request/i`)
 * would fail a truthful reword like "its single upload endpoint declines all
 * requests", which the independent review used as its own example. Only the
 * capture site makes this specific two-part claim (no multipart form
 * anywhere; the one route refuses everything), so — unlike the ban above —
 * this is scoped to that one site rather than run over all five.
 */
const CAPTURE_AFFIRMATIVE_CLAIM: [string, RegExp][] = [
  [
    'no multipart form exists anywhere in this application',
    /\bno\s+multipart\s+form\b[^.,]{0,40}\b(anywhere|declared|exists)\b/i,
  ],
  [
    'the one upload route/endpoint refuses or declines every/all requests',
    /\bupload\s+(route|endpoint)\b[^.,]{0,60}\b(refuses|refused|reject(s)?|declin(es|ed)|den(ies|ied))\b[^.,]{0,30}\b(every|all|any)\b[^.,]{0,20}\brequests?\b/i,
  ],
];

describe('R1b §5b · the capture site states the affirmative claim, tolerant of wording', () => {
  it.each(CAPTURE_AFFIRMATIVE_CLAIM)('states %s', (_what, pattern) => {
    expect(captureVoiceAudioHandling()).toMatch(pattern);
  });

  it('a truthful reword still satisfies the tolerant pattern (regression fixture)', () => {
    const reword =
      'Audio stays in this tab’s memory. This application declares no multipart ' +
      'form anywhere, and its single upload endpoint declines all requests, so ' +
      'nothing in this capture path has anywhere to send it.';
    for (const [, pattern] of CAPTURE_AFFIRMATIVE_CLAIM) {
      expect(reword).toMatch(pattern);
    }
    // ...and the reword must still pass the ban above.
    expect(noEndpointClaims(reword)).toEqual([]);
  });
});
