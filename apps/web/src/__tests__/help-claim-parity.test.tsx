/*
 * UX-003/UX-004 · THE HELP POPOVER'S CLAIMS, AND THE ONE WORKFLOW VOCABULARY.
 *
 * WHY THIS FILE EXISTS. `components/HelpPanel.tsx` is the screen a first-time
 * scientist opens to learn what the product does, and it shipped two false
 * claims and a second workflow vocabulary — all three green under the whole
 * suite, because no test read the panel's "How it works" list at all.
 *
 *   1. `WORKFLOW_STEPS[0]` said Draft "extracts candidate field values FROM YOUR
 *      FILES, each tagged with cited evidence." No path in this build turns a
 *      file into draft content: `POST /api/uploads` is an unconditional 403 that
 *      declares no multipart form, and the one route that reads scientific
 *      content out of a file — `POST /api/experiments/{id}/ingestion/csv/preview`
 *      — is read-only with NO apply route, which `CLAUDE.md` §15 records as a
 *      committed human decision rather than unfinished work.
 *
 *   2. `WORKFLOW_STEPS[3]` said Validate "checks the exported record against the
 *      official ISAAC v1.05 schema", and the signals paragraph called that
 *      verdict "the only signal that gates export". Measured, `ok = schema_ok
 *      AND exactness_ok`: `export.export_draft` refuses on `check_exactness`
 *      BEFORE `validate_official` is reached. The distinction is not pedantry —
 *      the schema is upstream-owned (`CLAUDE.md` §1), the exactness rule is
 *      ISAAC's own, and §11 forbids any surface from reporting an exactness
 *      refusal as an official-schema error.
 *
 *   3. Help taught Draft · Complete · Export · Validate · Audit while every
 *      per-record surface showed the server-derived spine. Two five-step
 *      sequences, both presented as "the workflow".
 *
 * WHAT IT ASSERTS, and why in this order:
 *
 *  §1 the TRUTH-PATH facts the two bans rest on are still true, read from the
 *     backend and the truth core rather than from any comment about them. If a
 *     later slice genuinely builds a file-to-field path, or folds exactness into
 *     `official.py`, §1 fails FIRST and tells the next reader to revisit the
 *     copy — instead of leaving a stale prohibition standing on nothing. This is
 *     the posture `upload-claim-parity.test.tsx` §1 established.
 *  §2 the panel makes the replacement claims, RENDERED — a claim present in the
 *     module and not on the surface is not a claim.
 *  §3 ONE workflow vocabulary ships, checked structurally against the server
 *     mirror rather than against a transcribed word list, plus the mechanical
 *     absence of the retired label keys.
 *  §4 Help is reachable from the record context, not only from `home`.
 *  §5 the ban patterns are POLARITY-PROVEN on the exact strings that shipped and
 *     on a rephrasing corpus, and are proven NOT to fire on the shipped correct
 *     copy. A guard that only passes on the fixed text is not evidence, and a
 *     guard that fires on true copy teaches the next reader to weaken it.
 *  §7 the SAME detectors, applied to `screens/GuidedCompletion.tsx` — the other
 *     surface that was shipping the same claim class at the same time.
 *
 * ── I-2 · THE SLICE THAT WROTE THIS FILE PUT TWO NEW FALSE CLAIMS WHERE THE
 *    TWO IT RETIRED HAD BEEN, AND NEITHER OF ITS OWN NEW FAMILIES COULD SEE
 *    EITHER ONE. Found by independent review. ──────────────────────────────
 *
 *   4. The replacement for (1) read "file upload is refused, and the
 *      campaign-sheet CSV comparison is read-only with no route that applies
 *      what it found." UNSCOPED — `CLAUDE.md` §11 records the refusal claim as
 *      true of `POST /api/uploads` ONLY — and it NAMED ONE READER AND OMITTED
 *      THE OTHER, on a build whose Governance page mounts a button labelled
 *      "Upload JSON File" (`components/RecordValidator.tsx:241`) one tab away.
 *      The panel's own comment claimed the sentence "names no file READER".
 *      Now scoped, with both readers named; pinned by
 *      `__tests__/upload-claim-parity.test.tsx` §6.
 *   5. The replacement for (2) was headed "TWO gates on export". There are
 *      THREE (`export.py:305`, `:343`, `:347`), and `ExportReadiness.tsx:789-791`
 *      already said so in committed prose, so the product shipped two different
 *      counts of its own export gates on two screens. §1 now COUNTS the refusal
 *      returns mechanically, which is what makes a number safe to print at all.
 *   6. The same claim class was live on `screens/GuidedCompletion.tsx` in three
 *      places, including the `:812` comment that vouched for one instance while
 *      repeating another. §7 reads that screen with the same detectors.
 *   7. `QA-013` — "Every field links to its evidence trail in the record" was
 *      recorded as UNMEASURED. Measured: nothing links, not every field has
 *      evidence (by design), and `!needsYou` suppresses the citation anyway.
 *      Family C exists for that shape.
 *
 * WHAT IT CANNOT CATCH is stated at the END of §5, not here, because the list
 * grew past a paragraph — see "WHAT THESE FAMILIES STILL CANNOT CATCH" below
 * the §5e describes. In one line: three clause-local pattern families, no
 * parser, no backend-authored copy, and a human reviewer is still the backstop
 * for a first occurrence of something nobody has written down yet.
 *
 * (The previous version of this paragraph called Family A "§3's". It is §5's;
 * corrected because a pointer that sends a reader to the wrong section is how a
 * guard goes unread.)
 */

import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

import { describe, it, expect, afterEach, vi } from 'vitest';
import { cleanup, render, fireEvent, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { HelpPanel } from '../components/HelpPanel';
import { TopBar } from '../components/TopBar';
import { ValidateReview } from '../components/ValidateReview';
import { LABELS } from '../lib/labels';
import { CANONICAL_STEPS } from '../lib/workflowSteps';
import { exportReadyRoutes, stubFetchRoutes } from '../test/apiFixtures';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// --- locating the real sources ----------------------------------------------

/** Deliberately NOT `import.meta.url`: under jsdom that is an http URL, not a
 *  file one. Duplicated from the sibling guards rather than exported, so no file
 *  can silently change another's scan. */
function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  return found;
}

/** The repository root, found by the vendored official schema — the one file
 *  `CLAUDE.md` §1 names as the authority, so it is the least likely anchor to
 *  move. §1 reads the BACKEND and the TRUTH CORE, which no other frontend guard
 *  does; the two claims corrected here are claims about them, and a frontend-only
 *  scan could only ever check that the copy agrees with itself. */
function locateRepoRoot(): string {
  let dir = process.cwd();
  for (let i = 0; i < 8; i += 1) {
    if (existsSync(join(dir, 'schema', 'isaac_record_v1.json'))) return dir;
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error(`cannot locate the repository root from ${process.cwd()}`);
}

const SRC_DIR = locateSrcDir();
const REPO_ROOT = locateRepoRoot();

function frontendSource(rel: string): string {
  return readFileSync(join(SRC_DIR, rel), 'utf8');
}

function repoSource(rel: string): string {
  return readFileSync(join(REPO_ROOT, rel), 'utf8');
}

// --- the rendered panel ------------------------------------------------------

/** The panel as a reader meets it: opened, and read off the dialog. RENDERED
 *  rather than source-scanned, because a source scan of `HelpPanel.tsx` matches
 *  every banned phrase in the correction comments that explain why they are
 *  banned — it would fail on the fix. */
/** UX-021 — THE `MemoryRouter` IS REQUIRED, not defensive. The panel now renders a
 *  real `<Link>` to Settings -> Help & Tutorial (the one permanent home of the guided
 *  walkthrough), and `Link` reads router context, so a bare render throws
 *  `Cannot destructure property 'basename' of useContext(...) as it is null` and takes
 *  every test in this file down with it. Wrapping is the right fix rather than
 *  downgrading the `<Link>` to an `<a href>`: in production this panel is mounted
 *  inside `TopBar`, which is inside the router, so the harness was the thing that did
 *  not match reality. This file already used `MemoryRouter` for other components; only
 *  the two `HelpPanel` helpers were bare. */
function renderHelpPanel() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <HelpPanel />
    </MemoryRouter>,
  );
}

function helpPanelText(): string {
  renderHelpPanel();
  fireEvent.click(screen.getByRole('button', { name: 'Help' }));
  return screen.getByRole('dialog').textContent ?? '';
}

/** The `<strong>` label of each item in the "How it works" list, in order. */
function helpStepLabels(): string[] {
  renderHelpPanel();
  fireEvent.click(screen.getByRole('button', { name: 'Help' }));
  const list = screen.getByRole('dialog').querySelector('ol.help-steps');
  if (list === null) throw new Error('the Help panel renders no "How it works" step list');
  return Array.from(list.querySelectorAll('li strong')).map((el) => el.textContent ?? '');
}

// ============================================================================
// §1 — the truth-path facts the bans rest on
// ============================================================================

describe('UX-003 §1 · no path in this build turns a file into draft content', () => {
  it('POST /api/uploads is an unconditional 403 that parses nothing', () => {
    const routes = repoSource('apps/api/isaac_api/routes.py');
    // The route exists (so "no upload endpoint is declared" would itself be false)
    // and its handler has exactly one, unconditional, refusing return.
    expect(routes).toMatch(/"\/uploads"/);
    expect(routes).toMatch(/def uploads\(\):/);
    expect(routes).toMatch(/JSONResponse\(status_code=403, content=payload\)/);
  });

  it('no multipart parser is reachable anywhere in the API package', () => {
    // `UploadFile` and `File(` are the only ways FastAPI accepts a file part.
    // Comments mentioning multipart are expected and are not a parser, so the
    // assertion is about the DECLARATIONS.
    const routes = repoSource('apps/api/isaac_api/routes.py');
    expect(routes).not.toMatch(/\bUploadFile\b/);
    expect(routes).not.toMatch(/=\s*File\(/);
  });

  it('the CSV preview writes nothing and has no apply route', () => {
    const routes = repoSource('apps/api/isaac_api/routes.py');
    expect(routes).toMatch(/ingestion\/csv\/preview/);
    // The route's own description states the boundary this copy relies on.
    expect(routes).toMatch(/no draft change, no revision bump, no export/);
    // And there is no sibling that APPLIES a preview.
    expect(routes).not.toMatch(/ingestion\/csv\/apply/);
  });
});

describe('UX-004 §1 · exactness is a real SECOND gate, and it is ISAAC’s own', () => {
  it('export refuses on exactness before the official schema is consulted', () => {
    const exportPy = repoSource('src/isaac_records/export.py');
    const exactnessAt = exportPy.indexOf('exactness_report = check_exactness(record, root)');
    const officialAt = exportPy.indexOf('official_report = validate_official(record, root)');
    expect(exactnessAt, 'export.py no longer calls check_exactness').toBeGreaterThan(-1);
    expect(officialAt, 'export.py no longer calls validate_official').toBeGreaterThan(-1);
    expect(
      exactnessAt,
      'the copy says a record can be schema-valid and still refused; that depends on ' +
        'the exactness gate running, and on export refusing there.',
    ).toBeLessThan(officialAt);
  });

  it('the CLI exit code is the schema verdict AND exactness, not the schema alone', () => {
    expect(repoSource('src/isaac_records/cli.py')).toMatch(
      /return 0 if \(report\.ok and exactness\.ok\) else 1/,
    );
  });

  it('the exactness rule is deliberately NOT part of official schema validation', () => {
    const official = repoSource('src/isaac_records/official.py');
    expect(
      official,
      'if exactness ever moves into validate_official, the copy that calls it ' +
        "“ISAAC’s, not the schema’s” has to be revisited before this guard is relaxed.",
    ).not.toMatch(/check_exactness/);
  });

  /*
   * I-2 — THE ARITY, READ FROM `export.py` RATHER THAN COUNTED BY HAND.
   *
   * The panel used to be headed "Two gates on export" and its step-5 text said
   * "both export gates". There are THREE. `screens/ExportReadiness.tsx:789-791`
   * had said so in committed prose the whole time ("it clears THREE gates, not
   * two"), and `lib/officialAttribution.ts:164` calls them (CORRECTED: this read
   * `:11,164` and "the first two"; `:11` is item 3 of that module's three-item
   * producer list and states no count, and the pair is the LAST two, paired at
   * `:13` — item 1 is the upstream schema, the one that is not ISAAC's)
   * "ISAAC's two gates" — ISAAC's OWN — beside the upstream schema, which is the
   * same arithmetic from the other end. So the product shipped two different
   * counts of its own export gates on two screens.
   *
   * THIS TEST IS THE REASON THE COPY MAY SAY A NUMBER AT ALL. A count claim is
   * only safe beside a mechanical count: if a fourth refusal return is added, or
   * one is removed, this fails FIRST and sends the next reader to the copy —
   * instead of leaving a stale number on the screen a first-time scientist reads.
   * It counts `return ExportResult(False, ...)` occurrences inside `export_draft`
   * rather than the word "gate", because the function body is the authority and
   * prose about it is not.
   */
  it('export_draft has exactly THREE refusal returns and ONE success return', () => {
    const exportPy = repoSource('src/isaac_records/export.py');
    const start = exportPy.indexOf('def export_draft(');
    expect(start, 'export.py no longer declares export_draft').toBeGreaterThan(-1);
    // The body ends at the next top-level `def`/`class`, which is how this stays
    // a count over ONE function rather than over the module.
    const after = exportPy.slice(start + 1);
    const nextTop = after.search(/\n(?:def |class )/);
    const body = nextTop === -1 ? after : after.slice(0, nextTop);

    const refusals = body.match(/return ExportResult\(\s*False\b/g) ?? [];
    const successes = body.match(/return ExportResult\(\s*True\b/g) ?? [];
    expect(
      refusals.length,
      `export_draft has ${refusals.length} refusal returns, and the Help popover ` +
        'says THREE. Either a gate was added or one was removed — read the ' +
        'function, then fix "Three gates on export" and step 5\'s "all three ' +
        'export gates" in components/HelpPanel.tsx, and the two sentences in ' +
        'screens/GuidedCompletion.tsx, in the same change.',
    ).toBe(3);
    expect(successes.length, 'export_draft must have exactly one success return').toBe(1);
  });

  it('the three gates are the ones the copy names, in the order it names them', () => {
    const exportPy = repoSource('src/isaac_records/export.py');
    const draftGate = exportPy.indexOf('if not draft_report.ok:');
    const exactness = exportPy.indexOf('exactness_report = check_exactness(record, root)');
    const official = exportPy.indexOf('official_report = validate_official(record, root)');
    for (const [what, at] of [
      ['the no-guessing draft report gate', draftGate],
      ['check_exactness', exactness],
      ['validate_official', official],
    ] as [string, number][]) {
      expect(at, `export_draft no longer contains ${what}`).toBeGreaterThan(-1);
    }
    // The copy says "in order", so the order is pinned, not just the membership.
    expect(draftGate).toBeLessThan(exactness);
    expect(exactness).toBeLessThan(official);
  });
});

/*
 * QA-013 §1 — THE EVIDENCE CLAIM, MEASURED. The ledger recorded
 * "Every field links to its evidence trail in the record" as UNMEASURED and
 * warned "Do not read UX-003/004 as having validated it". Measured, it was false
 * three independent ways, and each of the three is read from the component here
 * rather than from a comment about it. If a later slice genuinely builds a link,
 * or drops the `!needsYou` suppression, THESE fail first and send the next reader
 * to the copy — which is the posture §1 above already establishes for the other
 * two claim families.
 */
describe('QA-013 §1 · nothing in a field row links anywhere, and not every field has a citation', () => {
  it('EvidenceRow renders no link, no button and no handler — spans only', () => {
    const src = frontendSource('components/EvidenceRow.tsx');
    for (const [what, pattern] of [
      ['an anchor', /<a[\s>]/],
      ['an href', /href=/],
      ['a router Link', /\bLink\b/],
      ['a button', /<button|role="button"/],
      ['a click handler', /onClick/],
    ] as [string, RegExp][]) {
      expect(
        pattern.test(src),
        `components/EvidenceRow.tsx now contains ${what}. The Help copy says ` +
          'citations "show inline" precisely because there is nothing to click and ' +
          'nowhere to go; if that changed, the copy may (and should) change too.',
      ).toBe(false);
    }
  });

  it('FieldRow renders no link out to an evidence trail either', () => {
    const src = frontendSource('components/FieldRow.tsx');
    for (const pattern of [/<a[\s>]/, /href=/, /<Link\b/, /\bnavigate\(/]) {
      expect(
        pattern.test(src),
        `components/FieldRow.tsx now matches ${pattern}. The retired copy claimed ` +
          'every field LINKS to its evidence trail; if a link now exists, revisit the ' +
          '"Where evidence lives" copy rather than relaxing this.',
      ).toBe(false);
    }
  });

  it('the citation block is gated on evidence EXISTING and on not awaiting you', () => {
    const src = frontendSource('components/FieldRow.tsx');
    // Both halves of the gate, as one expression: a field with no evidence shows
    // no citation, and a field awaiting confirmation shows none either.
    expect(src).toMatch(/field\.evidence && field\.evidence\.length > 0 && !needsYou/);
  });

  it('a field with no evidence is a DESIGNED state, not an edge case', () => {
    /*
     * `CLAUDE.md` §5: a value with no support stays missing. The row says so,
     * which is why "every field" could never have been true.
     *
     * INVERTED 2026-09-14 — this assertion was PINNING A CASING DEFECT.
     * ~~`expect(frontendSource('components/FieldRow.tsx')).toMatch(/'honestly missing'/)`~~
     * required the row to keep a hardcoded lowercase literal — quoted here so
     * the old text is not lost: `'honestly missing'`, and its sibling
     * `'awaiting your confirmation'`. Both rendered in the VALUE slot 10px from
     * a Title Case `<StatusChip>` announcing the same state, which
     * `casing-and-copy.md:12` assigns to the chip (Register 1), and neither was
     * ever in `LABELS`. A test requiring the literal's presence is a test that
     * fails when the defect is fixed, so it is inverted rather than deleted.
     *
     * WHAT IS PINNED NOW IS THE CLAIM, NOT THE SENTENCE: the row must still
     * RENDER the no-evidence state distinctly (it branches on `missing`, and
     * `StatusChip` carries the words), and it must NOT have gone back to a
     * hardcoded literal in that slot.
     */
    const src = frontendSource('components/FieldRow.tsx');
    // The state is still a first-class branch of the row, not an edge case.
    expect(src).toMatch(/const missing = field\.status === 'missing'/);
    expect(src).toMatch(/{needsYou \|\| missing \? \(/);
    // …and it is announced by the chip, from the registry, exactly once.
    expect(src).toMatch(/<StatusChip kind={kind} \/>/);
    /* THE RETIRED LITERALS ARE POLICED SOMEWHERE ELSE, DELIBERATELY. Asserting
       their absence over this file's raw text would fail on the correction
       comment that quotes them — the same trap `CLAUDE.md` §11 records for the
       CSS phantom sweep that counted `var()` written inside comments. The
       comment-stripped, tree-wide version of that check lives in
       `src/__tests__/casing-registers.test.tsx` §4 (the anti-hardcode ratchet),
       which is where a reintroduction anywhere under `components/` or
       `screens/` is caught rather than only here. */
  });

  it('the sidecar sentence is true: build_sidecar exists and the CLI writes it beside the record', () => {
    expect(repoSource('src/isaac_records/export.py')).toMatch(/def build_sidecar\(/);
    expect(repoSource('src/isaac_records/cli.py')).toMatch(
      /records_dir \/ f"\{rid\}\.evidence\.json"/,
    );
  });
});

// ============================================================================
// §2 — the replacement claims, rendered
// ============================================================================

/**
 * Each required claim, as a pattern over the panel's rendered text.
 *
 * Tolerant of wording on purpose — what is pinned is the CLAIM, not the
 * sentence. Every one of these is a claim whose ABSENCE re-opens a false
 * impression: without the two-gate statement, naming the schema alone is the
 * UX-004 defect again; without the file-to-field denial, a reader has nothing
 * correcting the UX-003 impression.
 */
const REQUIRED_CLAIMS: [string, RegExp][] = [
  [
    'a value is put in a record by a person',
    /\bvalue\b[^.]{0,60}\bperson\b|\bperson\b[^.]{0,60}\b(put|typed|types|enters?)\b/i,
  ],
  [
    'no control reads one of your files and fills a field from it',
    /\b(no|nothing|never)\b[^.]{0,40}\b(reads?|read)\b[^.]{0,40}\b(files?)\b[^.]{0,40}\b(fills?|filled|field)\b/i,
  ],
  /*
   * I-2 — SCOPED, NOT DELETED. This used to be
   * `/\bupload\b[^.]{0,30}\b(refused|disabled|blocked)\b/i`, which the sentence
   * "file upload is refused" satisfied — and that sentence was UNSCOPED, on a
   * build whose Governance page mounts a button labelled "Upload JSON File"
   * (`components/RecordValidator.tsx:241`) one tab away. `CLAUDE.md` §11 records
   * the refusal claim as true of `POST /api/uploads` ONLY, and records the same
   * claim class shipping false three times before, each time repaired by SCOPING
   * it. The pattern now REQUIRES the scope: the refusal has to be predicated of
   * the upload route/endpoint/path, not of the application.
   */
  [
    'the upload refusal is scoped to the upload ROUTE, not stated of the app',
    /\bupload\s+(route|endpoint|path)\b[^.]{0,40}\b(refus\w+|declin\w+|reject\w+|disabled|blocked)\b/i,
  ],
  /*
   * I-2 — AND BOTH READERS ARE NAMED. The retired sentence named ONE (the
   * campaign-sheet CSV comparison) and omitted the other, while the panel's own
   * comment claimed it "names no file READER". Naming one and omitting the other
   * is the half-disclosure `__tests__/upload-claim-parity` §2 exists to stop, and
   * it is worse than naming neither: a reader is told the exhaustive-sounding
   * truth about the reader that changes nothing, and nothing about the one with
   * "Upload" on its face. Measured: exactly two components under `apps/web/src`
   * declare an `<input type="file">`, so "both" is a closed set.
   */
  [
    'the record validator is named as one of the two file readers',
    /\bvalidator\b/i,
  ],
  [
    'the CSV / campaign-sheet comparison is named as the other',
    /\b(csv|campaign[- ]sheet)\b/i,
  ],
  [
    'what those two do read is applied to no record',
    /\b(csv|campaign[- ]sheet)\b[^.]{0,110}\b(read-only|no route that applies|nothing is applied|apply nothing|applies nothing|change no record|write nothing)\b/i,
  ],
  [
    'no control other than those two accepts a file',
    /\b(only two|two)\s+controls?\b[^.]{0,40}\b(read|reads)\b|\bno other control\b[^.]{0,30}\bfile\b/i,
  ],
  [
    'dictated words survive whether or not a proposal is accepted',
    /\bnote\b[^.]{0,120}\bproposal\b|\bproposal\b[^.]{0,120}\b(note|survive)\b/i,
  ],
  /*
   * I-2 — THE CLAIM IS NOW THREE GATES, NOT TWO, AND THE COUNT IS PINNED BY §1's
   * mechanical read of `export_draft`. The retired pattern required
   * `gated -> schema -> anchored-pattern exactness` and so was SATISFIED BY THE
   * FALSE SENTENCE: it pinned that two gates were named and could not notice
   * that a third was missing. A pattern that a false claim satisfies is not a
   * guard for that claim.
   *
   * `[\s\S]`, NOT `[^.]`, throughout. The copy contains the literal `v1.05`, so
   * a dot-excluding window cannot reach across it — the first version of the
   * retired pattern failed on correct copy for exactly that reason, which is the
   * `QA-010` hazard: `[^.]` is only a sentence proxy and breaks on version
   * numbers.
   *
   * AND THIS RULE WAS STATED HERE WHILE 8 OF FAMILY B's 13 PATTERNS STILL USED
   * `[^.]` — 11 window occurrences — in the one family whose whole subject is
   * "ISAAC v1.05". They are `[\s\S]` now; §5g measures the change in both
   * directions and shows it introduces no false positive on any of the 16
   * correct-copy fixtures. A rule documented in one family and not applied to
   * the next is the shape this file has been caught in twice.
   */
  [
    'export runs three checks, and the copy says three',
    /\bthree\b[\s\S]{0,20}\b(checks?|gates?)\b/i,
  ],
  [
    'the first of the three is the no-guessing draft check',
    /\bno[- ]guessing\b[\s\S]{0,20}\b(draft|checks?)\b/i,
  ],
  [
    'the second is ISAAC’s own anchored-pattern exactness check',
    /\banchored[- ]pattern exactness\b/i,
  ],
  [
    'the third is the official ISAAC v1.05 schema',
    /\bofficial ISAAC\s*v1\.05 schema\b/i,
  ],
  [
    'an exactness refusal is ISAAC’s, not the schema’s',
    /\bISAAC’s, not the schema’s|\bISAAC's, not the schema's/i,
  ],
  [
    'a record can be schema-valid and still refused',
    // Widened from `valid against official ISAAC v1.05` to allow the back-
    // reference the corrected copy uses ("valid against that schema"), which is
    // unambiguous because the schema is named by its version 12 words earlier in
    // the same paragraph. The CLAIM is pinned; the wording is not.
    /\bvalid against (official ISAAC v1\.05|that|the official)\b[^.]{0,60}\b(still be refused|refused)\b/i,
  ],
  [
    'no screen reports such a refusal as a schema error',
    /\bno screen\b[^.]{0,60}\bschema error\b/i,
  ],
  [
    'the audit and advisory tiers gate nothing',
    /\b(neither|nor)\b[^.]{0,80}\b(gates? (anything|nothing)|never blocks)\b/i,
  ],
  /*
   * QA-013 — the evidence claim, SCOPED. The retired sentence was "Every field
   * links to its evidence trail in the record", false three ways (see the
   * `QA-013 §1` describe above). Both halves of the replacement are required:
   * WHERE citations appear, and the two states that show none. Requiring only
   * the first would let the universal quantifier come back in a new sentence.
   */
  [
    'citations appear inline beside the value, scoped to where evidence was recorded',
    // NO LEADING `\b`, and this is the `QA-011` family of trap rather than a
    // style choice. `helpPanelText()` reads the DIALOG's `textContent`, which
    // concatenates the `<h3>` straight onto the `<p>` — "...Where evidence
    // livesCitations show inline..." — so there is no word boundary before
    // "Citations" and `\bcitations?\b` cannot match however correct the copy is.
    // The first version of this pattern had it and failed on the fixed text.
    /citations?\b[\s\S]{0,40}\binline\b[\s\S]{0,60}\bwhere\b[\s\S]{0,30}\bevidence\b/i,
  ],
  [
    'a field honestly missing or awaiting confirmation shows no citation',
    /\b(honestly missing|awaiting)\b[\s\S]{0,60}\b(shows? none|no citation|none)\b/i,
  ],
  [
    'exports write an evidence sidecar beside the official record',
    /\bevidence sidecar\b[\s\S]{0,60}\bofficial record\b/i,
  ],
];

describe('UX-003/UX-004 §2 · the Help panel states the replacement claims', () => {
  it.each(REQUIRED_CLAIMS)('states %s', (_what, pattern) => {
    expect(helpPanelText()).toMatch(pattern);
  });
});

// ============================================================================
// §3 — ONE workflow vocabulary
// ============================================================================

/** The five words Help used to teach. Kept verbatim as a fixture. */
const RETIRED_STEP_WORDS = ['Draft', 'Complete', 'Export', 'Validate', 'Audit'] as const;

/** The label keys that carried them. */
const RETIRED_LABEL_KEYS = [
  'stepDraft',
  'stepComplete',
  'stepExport',
  'stepValidate',
  'stepAudit',
] as const;

describe('UX-003 §3 · one workflow vocabulary, and it is the server’s', () => {
  it('the Help step list IS the server-derived spine, in order', () => {
    // Structural, not a transcribed word list: a rename in `workflow.py` (mirrored
    // in `lib/workflowSteps.ts`) moves both sides at once, and a Help list that
    // stops matching the mirror fails here rather than teaching a second wording.
    expect(helpStepLabels()).toEqual(CANONICAL_STEPS.map((s) => s.label));
  });

  it('every canonical step is explained — none silently omitted', () => {
    const labels = helpStepLabels();
    expect(labels).toHaveLength(CANONICAL_STEPS.length);
    for (const step of CANONICAL_STEPS) {
      expect(labels, `${step.label} is a canonical step with no Help entry`).toContain(step.label);
    }
  });

  it('the retired label keys are gone from LABELS', () => {
    for (const key of RETIRED_LABEL_KEYS) {
      expect(
        Object.prototype.hasOwnProperty.call(LABELS, key),
        `LABELS.${key} is back. It was one of five words forming a SECOND five-step ` +
          'workflow, taught only by Help while every record surface showed the ' +
          "server's spine. Use `lib/workflowSteps.ts` for step wording.",
      ).toBe(false);
    }
  });

  it('no file under apps/web/src reads a retired step label', () => {
    /*
     * Scans for the USE form `LABELS.<key>` only, and deliberately not for the
     * DECLARATION form `<key>:`. Two reasons, and the first one is a defect this
     * guard had on its first run:
     *
     *   - `lib/labels.ts` records the retirement by QUOTING the five declarations
     *     verbatim inside a block comment, which is exactly the evidence a future
     *     reader needs, and a declaration-shaped pattern flags it. A
     *     comment-stripping reader was the alternative and was rejected: it is a
     *     new text tool that would report a plausible wrong answer on any input
     *     it mis-parses, which is the failure mode this repository has been
     *     caught by three times.
     *   - Nothing is lost, because DECLARATION is already pinned mechanically by
     *     the `hasOwnProperty` test above — a key that is declared is a key that
     *     exists on `LABELS`, and that test reads the real object, not its source.
     *
     * `stepExport` is scanned like the rest here: as a `LABELS.` member reference
     * it is unambiguous, and `Export` being the one word the two vocabularies
     * share is handled separately in the rendered-label test below.
     */
    const offenders: string[] = [];
    for (const rel of ['components/HelpPanel.tsx', 'lib/labels.ts', 'components/TopBar.tsx']) {
      const src = frontendSource(rel);
      for (const key of RETIRED_LABEL_KEYS) {
        if (new RegExp(`LABELS\\.${key}\\b`).test(src)) offenders.push(`${rel}: ${key}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('the retired five are not rendered as the Help step labels', () => {
    const labels = helpStepLabels();
    // `Export` is a label in BOTH vocabularies — it is the one word the two
    // sequences share — so it is deliberately not an offender on its own.
    const collision = RETIRED_STEP_WORDS.filter(
      (w) => w !== 'Export' && labels.includes(w),
    );
    expect(collision).toEqual([]);
  });
});

// ============================================================================
// §4 — Help is reachable from a record
// ============================================================================

function renderTopBar(variant: 'home' | 'record') {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <TopBar variant={variant} title="Synthetic XANES 001" />
    </MemoryRouter>,
  );
}

describe('UX-003 §4 · Help is reachable from the record context', () => {
  it.each(['home', 'record'] as const)('the %s top bar mounts the Help trigger', (variant) => {
    const view = renderTopBar(variant);
    const trigger = view.getByRole('button', { name: 'Help' });
    expect(trigger.getAttribute('aria-haspopup')).toBe('dialog');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
  });

  it('the record top bar opens the SAME panel, not a second help surface', () => {
    const view = renderTopBar('record');
    fireEvent.click(view.getByRole('button', { name: 'Help' }));
    const dialog = view.getByRole('dialog');
    // One dialog, and it is the one carrying the workflow list.
    expect(view.getAllByRole('dialog')).toHaveLength(1);
    expect(dialog.querySelector('ol.help-steps')).not.toBeNull();
  });
});

// ============================================================================
// §5 — the bans, polarity-proven
// ============================================================================

/*
 * FAMILY A — "this product extracts field values from your files".
 *
 * A clause-local AFFIRMATIVE detector rather than a literal ban, because the
 * measured failure mode in this repository is a one-word edit of the retired
 * sentence walking straight through a literal (§11: a widened guard once caught
 * 1 of 8 plausible rephrasings). A clause is flagged when it pairs an extraction
 * verb, a field/value noun and a source-file noun AND carries no negator.
 *
 * The clause window — splitting on `.`, `;`, `:` and `,` — is what makes it
 * usable on correct copy. `upload-claim-parity.test.tsx` §3b records the same
 * finding from the other direction: a window that crosses a comma reads a
 * negation governing one clause as governing the next, and a guard that
 * misfires on true copy is worse than the gap it closes.
 */
const EXTRACTION_VERB =
  /\b(extract|extracts|extracted|extracting|pull|pulls|pulled|lift|lifts|lifted|harvest|harvests|harvested|scrape|scrapes|scraped|parse|parses|parsed|import|imports|imported|ingest|ingests|ingested|derive|derives|derived|populate|populates|populated|prefill|prefills|prefilled|autofill|autofills|autofilled|fill|fills|filled|read|reads|reading|detect|detects|detected|recognise|recognises|recognize|recognizes|infer|infers|inferred|tag|tags|tagged)\b/i;

const FIELD_NOUN =
  /\b(field|fields|value|values|metadata|candidate|candidates|record|records|draft|drafts|answer|answers)\b/i;

const SOURCE_FILE_NOUN =
  /\b(file|files|spreadsheet|spreadsheets|document|documents|upload|uploads|csv|csvs|pdf|pdfs|screenshot|screenshots|attachment|attachments|workbook|workbooks|sheet|sheets)\b/i;

const NEGATOR =
  /\b(no|not|never|neither|nor|none|nothing|cannot|can't|won't|doesn't|don't|refuse|refused|refuses|refusal|without|disabled|blocked|read-only)\b/i;

/*
 * I-2 · THE ADJUNCT STRIP, AND THE HOLE IT CLOSES.
 *
 * `NEGATOR` above is CLAUSE-WIDE, and an independent review measured what that
 * costs: "extracts field values from your spreadsheets WITH NO MANUAL TYPING"
 * escapes the whole family, because the negator belongs to an ADJUNCT — a
 * trailing phrase bolted onto the claim — and not to the claim's own predicate.
 * The sentence affirms the capability and denies only the typing, so a
 * clause-wide negator reads a marketing flourish as a refusal. Five of the
 * nineteen entries in the corpus below escape this way, measured.
 *
 * THE RULE: a negator only counts if it governs the clause's MAIN predicate.
 * Operationalised as "strip a trailing adjunct headed by one of a small closed
 * set of heads, then apply the negator to what is left". Not a parser, and it
 * does not pretend to be one — the heads are enumerated and the strip is
 * anchored to the END of the clause (`$`), so it can only ever remove a trailing
 * phrase, never the subject or the verb.
 *
 * WHY THIS IS SAFE ON CORRECT COPY, measured rather than argued. The correct
 * copy this product ships pairs its negator with the PREDICATE, not with an
 * adjunct — "No control here reads one of your files and fills a field from
 * it", "which report what they found and apply nothing to a record" — so the
 * strip removes nothing that was carrying the negation. The one case that looks
 * dangerous is `settingsContent.ts`'s "is read-only with no route that applies
 * what it found": the strip DOES remove "with no route that applies what it
 * found", and the clause still carries `read-only`, which is itself a NEGATOR
 * token. §5d re-measures all of this on every run, and the before/after ratios
 * are asserted below rather than described.
 */
/*
 * -- `QA-010` IS LIVE IN THIS FILE, AND IT WAS LIVE IN THE ONE PLACE IT IS
 *    DOCUMENTED. -----------------------------------------------------------
 *
 * `:427-430` of this same file records the hazard and states the remedy -- "the
 * copy contains the literal `v1.05`, so a dot-excluding window cannot reach
 * across it ... `[^.]` is only a sentence proxy and breaks on version numbers"
 * -- and then applies it to Family B's WINDOWS while leaving the three CLAUSE
 * SPLITS on the version-naive character class. Measured:
 *
 *   'Draft extracts candidate field values from your v1.05 spreadsheets.'
 *   split on [.;:,] -> ['Draft extracts candidate field values from your v1',
 *                       '05 spreadsheets', '']
 *
 * The required tokens are now in DIFFERENT chunks -- extraction verb and field
 * noun in the first, source-file noun in the second -- so no chunk satisfies the
 * conjunction and the ban cannot fire. In a guard whose subject vocabulary is
 * literally "ISAAC v1.05", that is not a corner case.
 *
 * AND THE CORPUS COULD NOT SEE IT: before this change, ZERO of the 19
 * `EXTRACTION_REPHRASINGS` and ZERO of the 6 `UNIVERSAL_EVIDENCE_REPHRASINGS`
 * contained a decimal, so the `100%` assertions in §5b were measured on a corpus
 * that systematically omitted the token that defeats the detector. A ratio is a
 * property of its corpus, and this one could not have caught this class.
 * Decimal-bearing entries are added below, and §5f measures the split fix
 * against them the way §5b measures the adjunct strip.
 *
 * SCOPE OF THE CLAIM, because the review's own figure did not reproduce here. It
 * reported 4 of 4 paired probes escaping; four independently written probes
 * escape 2 of 4. Whether a version number defeats the detector depends on WHERE
 * it falls relative to the three required tokens -- "ISAAC v1.05 records are
 * populated from the spreadsheet you provide" leaves all three in the trailing
 * chunk and is caught either way. So the defect is real and the mechanism is
 * exactly as described; the RATE is a property of the probe set, and 4/4 must
 * not be quoted as a reproduction. §5f asserts the rate it measures.
 *
 * WHY A LOOKBEHIND AND NOT A SENTENCE PARSER: the only failure being fixed is a
 * dot BETWEEN TWO DIGITS. `(?<!\d)[.](?!\d)` declines exactly those and leaves
 * every other separator alone, so it cannot change any existing verdict -- and
 * §5f asserts that it does not, on both the 19-entry and 6-entry corpora as they
 * stood before the additions.
 */
const CLAUSE_SPLIT = /(?<!\d)[.](?!\d)|[;:,]/;

/** The PRE-FIX splitter, kept so §5f can MEASURE the improvement instead of
 *  asserting it -- the same posture §5b takes for the adjunct strip. */
const CLAUSE_SPLIT_VERSION_NAIVE = /[.;:,]/;

const ADJUNCT_HEAD =
  /\s+(?:with|without|requiring|requires|needing|needs|so\s+(?:you|that|nothing|nobody|no\s+one)|at\s+no|and\s+no\s+need|instead\s+of)\b[\s\S]*$/i;

/** A clause with its trailing adjunct removed. Exported for the §5b ratio test. */
function stripAdjunct(clause: string): string {
  return clause.replace(ADJUNCT_HEAD, '');
}

/** Every clause that affirms a file-to-field capability. Empty is the pass. */
function fileToFieldClaims(text: string): string[] {
  return text
    .split(CLAUSE_SPLIT)
    .map((c) => c.trim())
    .filter(
      (c) =>
        EXTRACTION_VERB.test(c) &&
        FIELD_NOUN.test(c) &&
        SOURCE_FILE_NOUN.test(c) &&
        // THE ONE CHANGE: the negator is applied to the adjunct-stripped clause.
        !NEGATOR.test(stripAdjunct(c)),
    );
}

/** The PRE-FIX behaviour, kept so §5b can measure the improvement rather than
 *  assert it. Deleting this would leave the ratio in a comment, which is where
 *  this repository has been caught publishing unmeasured numbers before. */
function fileToFieldClaimsClauseWideNegator(text: string): string[] {
  return text
    .split(CLAUSE_SPLIT)
    .map((c) => c.trim())
    .filter(
      (c) =>
        EXTRACTION_VERB.test(c) &&
        FIELD_NOUN.test(c) &&
        SOURCE_FILE_NOUN.test(c) &&
        !NEGATOR.test(c),
    );
}

/** Family A with the PRE-FIX splitter and the CURRENT negator, so §5f isolates
 *  the split as the single changed variable. */
function fileToFieldClaimsVersionNaiveSplit(text: string): string[] {
  return text
    .split(CLAUSE_SPLIT_VERSION_NAIVE)
    .map((c) => c.trim())
    .filter(
      (c) =>
        EXTRACTION_VERB.test(c) &&
        FIELD_NOUN.test(c) &&
        SOURCE_FILE_NOUN.test(c) &&
        !NEGATOR.test(stripAdjunct(c)),
    );
}

/*
 * FAMILY B — "the official schema is the whole export gate".
 *
 * Literal patterns here rather than a clause detector, because this family is
 * an EXCLUSIVITY claim and exclusivity has a small, enumerable vocabulary
 * ("only", "sole", "solely", "nothing but"). B6 additionally retires the exact
 * step-4 sentence and its near rephrasings; it is safe to ban inside Help
 * because Help no longer has a step that is a bare schema check.
 *
 * ── I-2 · THAT PARAGRAPH WAS THE WHOLE DEFECT, AND IT IS KEPT ABOVE RATHER
 *    THAN REWRITTEN, because the reasoning in it is exactly what let two false
 *    claims ship past this family on the day it was written. ───────────────
 *
 * "Exclusivity has a small, enumerable vocabulary" is true and was the wrong
 * premise. The family's job is not to catch EXCLUSIVITY; it is to catch "the
 * official schema is the whole export gate", and English has at least two ways
 * to say that without one exclusivity word:
 *
 *   - BY COUNTING. "Two gates on export" asserts the schema-plus-exactness pair
 *     IS the set, and contains no "only". It shipped as an `<h3>` on this very
 *     panel, and as "only when BOTH export gates pass" in step 5. There are
 *     THREE (`export.py:305`, `:343`, `:347` — pinned mechanically in §1).
 *   - BY VERBING. "The official ISAAC schema check runs next and DECIDES
 *     export." contains no exclusivity word either, and shipped on
 *     `screens/GuidedCompletion.tsx:826` plus a second instance in the same
 *     screen's body copy at `:1235`.
 *
 * Measured by an independent review: the original seven patterns caught 2 of
 * its 12-entry corpus. Re-measured here on a 20-entry corpus: 10 of 20 — and
 * every one of the ten misses is a count claim or a verbed claim. §5b asserts
 * both ratios so neither can decay into a comment.
 *
 * ── THE EXEMPTIONS ARE THE HARD PART, AND THEY ARE EXPLICIT ──────────────
 *
 * TWO places in this product say a number of gates that is NOT three, and both
 * are CORRECT, because they are about a different operation. A pattern that
 * "harmonised" them would replace one false claim with another. They are masked
 * out of the text BEFORE the bans run — never silenced by weakening a pattern —
 * so each exemption is a visible, named, testable decision:
 *
 *   1. `lib/officialAttribution.ts:45,164,272` and `components/RunFindings.tsx:323`
 *      say "ISAAC's two gates". That is ISAAC's OWN two — the no-guessing draft
 *      check and the exactness gate, which `export.py` folds into ONE findings
 *      list — counted beside the upstream schema. Three total. Correct.
 *      `components/ValidateReview.tsx`'s standing note now says the same thing in
 *      the same words ("ISAAC's own two gates"), which is why closing the
 *      exemption below cost no new one.
 *   2. `POST /api/validate/record` "reports the two gates separately"
 *      (`schema_ok` and `exactness_errors`), mirrored in `test/apiFixtures.ts`.
 *      That route's contract is `ok = schema_ok AND exactness_ok`; the
 *      no-guessing draft check is not in its path. Two. Correct.
 *
 * ── THERE WAS A THIRD EXEMPTION, IT WAS RECORDED AS CONTESTED, AND THE
 *    CONTEST IS NOW SETTLED AGAINST THE SENTENCE. ─────────────────────────
 *
 * Exemption 3 masked `components/ValidateReview.tsx:420`: ~~"Beyond the official
 * schema, ISAAC applies one gate of its own (anchored-pattern exactness). On a
 * candidate record its findings arrive in the same list as the rest and are not
 * labelled apart, so nothing below names the official ISAAC schema as the source
 * unless a written record was checked."~~ It was exempted on instruction, whose
 * stated reason was that the screen validates a pasted record through
 * `POST /api/validate/record`; the CONTESTED note recorded that the reason does
 * not hold, and that note was right. MEASURED AGAIN, the sentence was false three
 * ways at once:
 *
 *   - `ValidateReview` calls `POST /api/experiments/{id}/validate`, not
 *     `/api/validate/record`, and its own last clause sends the reader AWAY to the
 *     Standalone Validator — so it was never the standalone route's copy.
 *   - ISAAC's own gates on the `export_draft` path number TWO (`export.py:305`,
 *     `:343`), so "one" undercounted them; and NAMING the one it counted is what
 *     `officialAttribution.ts:163-169` forbids in terms — "it may not name ONE of
 *     ISAAC's two gates either … the same defect one level finer".
 *   - "nothing below names the official ISAAC schema as the source unless a
 *     written record was checked" predated the `official_validator_ran`
 *     discriminator. `_validate_unit`'s DRY-RUN branch publishes
 *     `official_validator_ran: true` whenever `validate_official` produced the
 *     findings, so a candidate record's findings really are headed "Official ISAAC
 *     schema findings" by `officialFindingsHeading`.
 *
 * The copy is corrected, the mask is DELETED rather than left standing, and §8
 * now covers the site the exemption used to hide — rendered, with the retired
 * sentence proven still-caught in the same describe. A permanent exemption for a
 * site that has been made compliant is how a guard ends up narrower than it reads.
 */

/** Spans that are a CORRECT gate count about a different operation. Masked out
 *  before the bans run. Each is justified in the block comment above. */
const ROUTE_QUALIFIED_GATE_COUNTS: RegExp[] = [
  /\bISAAC[’']s\s+(?:own\s+)?two\s+gates?\b/gi,
  /\bwhich\s+of\s+ISAAC[’']s\s+two\s+gates?\b/gi,
  /\btwo\s+gates,?\s+reported\s+separately\b/gi,
  /\breports?\s+the\s+two\s+gates\s+separately\b/gi,
];

function maskRouteQualifiedCounts(text: string): string {
  let out = text;
  for (const pattern of ROUTE_QUALIFIED_GATE_COUNTS) {
    out = out.replace(pattern, ' [ROUTE-QUALIFIED GATE COUNT] ');
  }
  return out;
}

const SCHEMA_IS_THE_WHOLE_GATE: [string, RegExp][] = [
  [
    'an exclusive gate on export, named and verbed',
    /\b(only|sole|solely|single|one)\b[\s\S]{0,25}\b(signal|gates?|check|thing|rule|verdict)\b[\s\S]{0,45}\b(gates?|gating|blocks?|blocking|authoris\w*|authoriz\w*|decides?)\b[\s\S]{0,25}\bexports?\b/i,
  ],
  [
    'an exclusive gate adjacent to the word export',
    /\b(only|sole|single) (signal|gate|check|rule|verdict)\b[\s\S]{0,30}\bexports?\b/i,
  ],
  [
    'the schema verdict described as the only gate',
    /\b(schema|official validation)\b[\s\S]{0,40}\b(is|remains) the (only|sole|single)\b/i,
  ],
  [
    'export gated only/solely on something',
    /\b(gated|blocked|decided|refused|validated) (only|solely|exclusively|purely|just) (on|by|against)\b/i,
  ],
  [
    'nothing but X gates export',
    /\bnothing (but|other than|else|more than)\b[\s\S]{0,50}\b(gates?|blocks?|refus\w*)\b/i,
  ],
  [
    'the retired step-4 sentence: a bare check against the official schema',
    /\bchecks? the (exported )?record against the official ISAAC( v1\.05)? schema\b/i,
  ],
  [
    'an exactness refusal reported as a schema error',
    /\b(exactness|anchored[- ]pattern)\b[\s\S]{0,60}\b(schema (error|violation|failure)|invalid against)\b/i,
  ],
  // ---- I-2 additions: the COUNT claims and the VERBED claims ---------------
  [
    'a COUNT of the export gates that is not three, with export named',
    /\b(one|two|four|five|both|1|2|4|5)\b[\s\S]{0,20}\b(export\s+)?gates?\b[\s\S]{0,25}\bexport|\bexport\b[\s\S]{0,25}\b(one|two|four|five|both)\b[\s\S]{0,15}\bgates?\b/i,
  ],
  [
    'a bare count of the gates, as a heading or a clause',
    // NO INLINE LOOKAHEAD. The first version carried
    // `(?!\s+of\s+(?:its|their)\s+own)` as belt-and-braces beside the mask, and
    // §5e caught the consequence: with the lookahead in the pattern, the
    // then-existing "one gate of its own" EXEMPTION became dead code — it could
    // never be the thing doing the exempting, so the mask looked load-bearing
    // while achieving nothing. One mechanism, in one place, provable in both
    // directions. The exemption list is that mechanism. (That exemption has since
    // been DELETED because the copy it covered was corrected — see the block
    // comment above and §8 — and the lookahead must not come back in its place:
    // with it here, `ValidateReview`'s retired sentence would pass this pattern
    // and §8's polarity twin could not fail.)
    /\b(one|two|four|five|both)\s+(?:export\s+)?gates?\b/i,
  ],
  [
    'the schema described as what decides or determines export',
    /\b(schema|official validation)\b[\s\S]{0,45}\b(decides?|determines?|settles?)\b[\s\S]{0,25}\bexports?\b/i,
  ],
  [
    'the schema check described as the next or the only remaining check',
    /\b(official\s+)?(ISAAC\s+)?(v1\.05\s+)?schema\s+check\b[\s\S]{0,20}\b(runs?\s+next|is\s+what\s+remains|remains|comes?\s+next)\b/i,
  ],
  [
    'export decided by the schema, verbed in the passive with no exclusivity word',
    /\bexports?\b[\s\S]{0,30}\bis\s+(decided|determined|settled)\s+by\s+the\s+(official\s+)?(ISAAC\s+)?(v1\.05\s+)?schema\b/i,
  ],
  [
    'an enumeration of the export gates that omits the no-guessing draft check',
    // The retired HelpPanel sentence, which named exactly two by enumerating
    // them and so carried no count word at all. TEMPERED on `no-guessing`: a
    // truthful three-gate reword using the same "gated on" frame must pass, and
    // the only mechanical difference is whether the draft check is named. Proven
    // both ways in §5e.
    /\bexports?\b[\s\S]{0,25}\bgated\s+on\b(?:(?!no[-\s]guessing)[\s\S]){0,100}\bexactness\b/i,
  ],
];

function schemaWholeGateClaims(text: string): string[] {
  const masked = maskRouteQualifiedCounts(text);
  return SCHEMA_IS_THE_WHOLE_GATE.filter(([, p]) => p.test(masked)).map(([label]) => label);
}

/** The PRE-FIX seven patterns, unmasked, kept so §5b can MEASURE the
 *  improvement instead of asserting it. */
const SCHEMA_GATE_PATTERNS_BEFORE_I2 = 7;
function schemaWholeGateClaimsBeforeI2(text: string): string[] {
  return SCHEMA_IS_THE_WHOLE_GATE.slice(0, SCHEMA_GATE_PATTERNS_BEFORE_I2)
    .filter(([, p]) => p.test(text))
    .map(([label]) => label);
}

/*
 * FAMILY C — "every X has a Y", on a build where X is allowed to have no Y.
 *
 * ADDED FOR `QA-013`, which is the FOURTH claim of this shape found on this one
 * surface. "Every field links to its evidence trail in the record" was false
 * three ways at once, and the two families above are structurally blind to it:
 * Family A needs an extraction verb and a source-file noun, Family B is about
 * export gates. The common shape is an UNSCOPED UNIVERSAL QUANTIFIER over a
 * relation the product deliberately allows to be absent — which, in a product
 * whose central policy is "a field with no support stays empty", is a shape
 * worth a detector of its own.
 *
 * It is a clause-local detector like Family A, and it is cheap: a universal
 * quantifier, a subject noun, a possession/linking verb, an evidence noun, and
 * NO scoping or negating token in the same clause. The scoper list is what makes
 * it usable — the corrected copy says "WHERE evidence was recorded", and a
 * detector that fired on that would be worse than the gap it closes.
 */
const UNIVERSAL = /\b(every|each|all)\b/i;
const CLAIM_SUBJECT = /\b(field|fields|value|values|record|records|answer|answers|entry|entries)\b/i;
const POSSESSION_VERB =
  /\b(links?|linked|has|have|carries|carry|shows?|showing|displays?|includes?|include|comes? with|gets?)\b/i;
const EVIDENCE_NOUN =
  /\b(evidence|citation|citations|trail|trails|provenance|source|sources|support)\b/i;
const SCOPER =
  /\b(where|wherever|whenever|if|when|unless|only|some|most|no|not|never|none|nothing|honestly missing|awaiting)\b/i;

/** Every clause that makes an unscoped universal evidence claim. Empty is the pass. */
function universalEvidenceClaims(text: string): string[] {
  return text
    .split(CLAUSE_SPLIT)
    .map((c) => c.trim())
    .filter(
      (c) =>
        UNIVERSAL.test(c) &&
        CLAIM_SUBJECT.test(c) &&
        POSSESSION_VERB.test(c) &&
        EVIDENCE_NOUN.test(c) &&
        !SCOPER.test(c),
    );
}

/** Family C with the PRE-FIX splitter, for the same reason. */
function universalEvidenceClaimsVersionNaiveSplit(text: string): string[] {
  return text
    .split(CLAUSE_SPLIT_VERSION_NAIVE)
    .map((c) => c.trim())
    .filter(
      (c) =>
        UNIVERSAL.test(c) &&
        CLAIM_SUBJECT.test(c) &&
        POSSESSION_VERB.test(c) &&
        EVIDENCE_NOUN.test(c) &&
        !SCOPER.test(c),
    );
}

// --- §5a the exact strings that shipped -------------------------------------

/** `components/HelpPanel.tsx:7` at `508e3c64`, verbatim. */
const RETIRED_EXTRACTION_CLAIM =
  'Draft extracts candidate field values from your files, each tagged with cited evidence.';

/** `components/HelpPanel.tsx:10` at `508e3c64`, verbatim. */
const RETIRED_VALIDATE_CLAIM =
  'Validate checks the exported record against the official ISAAC v1.05 schema.';

/** `components/HelpPanel.tsx:139-140` at `508e3c64`, verbatim. */
const RETIRED_ONLY_GATE_CLAIM =
  'Official Validation is the ISAAC v1.05 schema verdict — the only signal that gates export.';

/*
 * ── I-2 · FOUR MORE RETIRED STRINGS, AND ONE OF THEM WAS A "CORRECT COPY"
 *    FIXTURE IN THIS FILE UNTIL NOW. ─────────────────────────────────────────
 *
 * The first version of this guard shipped `RETIRED_TWO_GATE_SENTENCE` below as a
 * `CORRECT_COPY_FIXTURES` entry labelled "the two-gate statement", and asserted
 * that NEITHER family fires on it. That assertion passed, and it was the defect:
 * the sentence names two of the three gates `export_draft` actually applies, so
 * the file was mechanically certifying a false claim as correct copy. Moving it
 * here is the substantive change — a fixture that asserts a false claim is clean
 * is worse than no fixture, because it reads as evidence.
 */

/** `components/HelpPanel.tsx:294` at `43544c6c`, verbatim (the `<h3>`). */
const RETIRED_TWO_GATES_HEADING = 'Two gates on export';

/** `components/HelpPanel.tsx:60` at `43544c6c`, verbatim (step 5). */
const RETIRED_BOTH_GATES_STEP =
  'writes the official ISAAC record plus an evidence sidecar — and only when both export gates pass.';

/** `components/HelpPanel.tsx:296-297` at `43544c6c` — the enumeration that
 *  stopped at two, with no count word in it at all. */
const RETIRED_TWO_GATE_SENTENCE =
  "Export is gated on the official ISAAC v1.05 schema and on ISAAC's own anchored-pattern " +
  'exactness check.';

/** `screens/GuidedCompletion.tsx:826` at `43544c6c`, verbatim. */
const RETIRED_DECIDES_EXPORT_NOTE = 'The official ISAAC schema check runs next and decides export.';

/** `screens/GuidedCompletion.tsx:1235-1236` at `43544c6c` — the same claim in the
 *  body copy of the same screen, 409 lines away, which the `:812` comment
 *  vouched for while itself repeating it. */
const RETIRED_SCHEMA_RUNS_NEXT_BODY =
  'Every blocker the system refused to guess is now confirmed or resolved. The official schema ' +
  'check runs next, on the Review Export Readiness screen.';

/** `components/HelpPanel.tsx:351` at `43544c6c`, verbatim — the `QA-013` claim. */
const RETIRED_EVERY_FIELD_LINKS = 'Every field links to its evidence trail in the record.';

/**
 * `components/ValidateReview.tsx:420-425` as it shipped, verbatim — the span
 * Family B's third exemption used to mask. It was NOT a false positive: see the
 * three measured falsehoods in the exemptions block comment above. Kept as a
 * fixture rather than as prose so §8 can prove the detector reaches it now that
 * the mask is gone, which a rendered assertion on the corrected copy cannot do.
 */
const RETIRED_ONE_GATE_NOTE =
  'Beyond the official schema, ISAAC applies one gate of its own (anchored-pattern ' +
  'exactness). On a candidate record its findings arrive in the same list as the rest ' +
  'and are not labelled apart, so nothing below names the official ISAAC schema as the ' +
  'source unless a written record was checked.';

describe('UX-003/UX-004 §5a · the guard fails on the strings that shipped', () => {
  it('catches the retired extraction claim', () => {
    expect(
      fileToFieldClaims(RETIRED_EXTRACTION_CLAIM),
      'the exact sentence that shipped is not caught. If this fails, Family A has ' +
        'been narrowed until it detects nothing, and the copy it guards is unguarded.',
    ).not.toHaveLength(0);
  });

  it('catches the retired step-4 claim', () => {
    expect(schemaWholeGateClaims(RETIRED_VALIDATE_CLAIM)).not.toHaveLength(0);
  });

  it('catches the retired "only signal that gates export" claim', () => {
    expect(schemaWholeGateClaims(RETIRED_ONLY_GATE_CLAIM)).not.toHaveLength(0);
  });

  // ---- the four I-2 strings, each with the reason it is now banned ---------

  it.each([
    ['the "Two gates on export" heading', RETIRED_TWO_GATES_HEADING],
    ['step 5\'s "only when both export gates pass"', RETIRED_BOTH_GATES_STEP],
    ['the enumeration that stopped at two', RETIRED_TWO_GATE_SENTENCE],
    ['GuidedCompletion\'s "decides export" status note', RETIRED_DECIDES_EXPORT_NOTE],
    ['GuidedCompletion\'s "schema check runs next" body copy', RETIRED_SCHEMA_RUNS_NEXT_BODY],
  ])('catches %s', (_what, retired) => {
    expect(
      schemaWholeGateClaims(retired),
      `"${retired}" shipped, and export_draft applies THREE gates (§1 counts them ` +
        'mechanically). If this no longer fires, Family B has gone quiet on the exact ' +
        'claim class it was extended for.',
    ).not.toHaveLength(0);
  });

  it('catches the retired "Every field links to its evidence trail" claim', () => {
    expect(
      universalEvidenceClaims(RETIRED_EVERY_FIELD_LINKS),
      'the QA-013 sentence is not caught. It was false three ways: nothing in a field ' +
        'row links (EvidenceRow renders spans only), not every field has evidence ' +
        '(CLAUDE.md §5 guarantees it), and `!needsYou` suppresses the citation anyway.',
    ).not.toHaveLength(0);
  });
});

// --- §5b the rephrasing corpora, WITH THE BEFORE/AFTER RATIOS MEASURED ------

/**
 * Plausible rephrasings, INCLUDING one-word edits of the retired sentences.
 *
 * The requirement is 100%, not "most": §11 records a widened guard in this
 * repository catching 1 of 8, and a one-word edit of a retired sentence walking
 * straight through. Each entry is a sentence a well-meaning author could write
 * next, not an adversarial construction.
 *
 * I-2 EXTENDED IT FROM 13 TO 19, and the six additions are all one shape: a
 * negator that belongs to an ADJUNCT rather than to the claim. An independent
 * review found this hole by construction ("...with no manual typing"); the
 * additions generalise it across the adjunct heads `with`, `without`, `so you
 * never`, `at no`, `requiring no` and `instead of`.
 */
const EXTRACTION_REPHRASINGS: string[] = [
  RETIRED_EXTRACTION_CLAIM,
  // One-word edits of the retired sentence.
  'Draft extracts candidate field values from your documents, each tagged with cited evidence.',
  'Draft extracts candidate field values from your spreadsheets.',
  // Verb swaps.
  'Draft pulls candidate values out of your spreadsheets.',
  'Draft lifts candidate metadata straight out of the document you provide.',
  'We parse your CSV and derive metadata candidates from it.',
  'ISAAC ingests your experiment files into a draft with cited evidence.',
  // Voice and subject swaps.
  'Field values are extracted from the files you provide.',
  'The assistant reads your uploaded files and fills in the fields it finds.',
  'Each field is prefilled from the source spreadsheet.',
  // Imperative product promises.
  'Upload a spreadsheet and ISAAC will populate the record fields from it.',
  'Point it at a screenshot and it will detect the values for you.',
  // ---- I-2: the adjunct-shadowed forms, which the clause-wide negator missed.
  'It extracts field values from your spreadsheets with no manual typing.',
  'It extracts field values from your spreadsheets without manual typing.',
  'ISAAC populates the record fields from your workbook with no data entry needed.',
  'Field values are read from your CSV so you never have to type them.',
  'It parses your spreadsheet and fills every field, requiring no transcription.',
  'Candidate values are lifted from the document at no effort to you.',
  'It ingests your files and prefills the draft instead of you keying it in.',
  // ---- THE DECIMAL-BEARING CLASS, which the corpus systematically omitted.
  //
  // Before these four, no entry in this corpus contained a decimal, so the
  // `100%` assertion above was measured on a corpus that could not see the
  // token that defeats the splitter. Two of the four escaped the version-naive
  // split and two did not — §5f asserts that split, because "all four escape"
  // would overstate the defect and "the class is closed" would understate the
  // reason the ratio moved.
  //
  // Each is a sentence an author of THIS product could plausibly write: `v1.05`
  // is the schema version named on nearly every surface in it.
  'Draft extracts candidate field values from your v1.05 spreadsheets.',
  'Field values are extracted from your v1.05 workbook automatically.',
  'ISAAC v1.05 records are populated from the spreadsheet you provide.',
  'It parses your v1.05 CSV and fills the record fields from it.',
];

const SCHEMA_GATE_REPHRASINGS: string[] = [
  RETIRED_VALIDATE_CLAIM,
  RETIRED_ONLY_GATE_CLAIM,
  'Official Validation is the ISAAC v1.05 schema verdict — the only signal that blocks export.',
  'The official schema is the sole gate on export.',
  'The official schema verdict is the only check that gates export.',
  'Export is gated only on the official ISAAC v1.05 schema.',
  'Export is gated solely by the official schema.',
  'The official schema verdict is the only gate that matters here.',
  'Nothing but the official schema blocks export.',
  'Validate checks the record against the official ISAAC schema.',
  // ---- I-2: the COUNT claims, none of which contains an exclusivity word.
  RETIRED_TWO_GATES_HEADING,
  RETIRED_BOTH_GATES_STEP,
  RETIRED_TWO_GATE_SENTENCE,
  'There are two gates on export.',
  'Both gates must pass before a record is written.',
  // ---- I-2: the VERBED claims, likewise exclusivity-word-free.
  RETIRED_DECIDES_EXPORT_NOTE,
  RETIRED_SCHEMA_RUNS_NEXT_BODY,
  'The official ISAAC v1.05 schema determines export.',
  'Export is decided by the official ISAAC schema.',
  'The official schema check is what remains.',
  // ---- THE DECIMAL-BEARING CLASS, added with the `[\s\S]` widening (§5g).
  //
  // The first of these was caught by ZERO patterns while 8 of the 13 used
  // `[^.]`; the second — the same sentence with `v1.05` deleted — was caught by
  // one. A pair that differs only in a version number, with different verdicts,
  // is the `QA-010` hazard stated as a test rather than as a comment.
  'That is the only ISAAC v1.05 rule that blocks an export.',
  'That is the only ISAAC rule that blocks an export.',
];

const UNIVERSAL_EVIDENCE_REPHRASINGS: string[] = [
  RETIRED_EVERY_FIELD_LINKS,
  'Every field has an evidence trail.',
  'Each field carries its citations.',
  'All fields link to the evidence behind them.',
  'Every value comes with a citation.',
  'Each record field shows its provenance.',
  // ---- the decimal-bearing class, same reason as Family A's four above. Both
  // of these escaped the version-naive split completely (§5f measures it).
  'Every field in an ISAAC v1.05 record has an evidence trail.',
  'Each v1.05 record field carries its citations.',
];

describe('UX-003 §5b · Family A catches every plausible rephrasing', () => {
  it('catches 100% of the extraction corpus', () => {
    const missed = EXTRACTION_REPHRASINGS.filter((s) => fileToFieldClaims(s).length === 0);
    expect(
      missed,
      `${EXTRACTION_REPHRASINGS.length - missed.length}/${EXTRACTION_REPHRASINGS.length} ` +
        'caught. A rephrasing that escapes is a claim that can silently return.',
    ).toEqual([]);
  });

  /*
   * THE IMPROVEMENT, MEASURED RATHER THAN DESCRIBED.
   *
   * `14/19 -> 19/19` is asserted here, not written in a comment, because this
   * repository has repeatedly been caught publishing a ratio it did not
   * re-measure. If someone deletes the adjunct strip, this test names the exact
   * clauses that go free. If someone adds a corpus entry the strip cannot reach,
   * the test above fails and this one records how far short it fell.
   *
   * HONESTY NOTE ON THE NUMBER: an independent review measured the pre-fix
   * family at 10/20 on ITS OWN 20-entry corpus and reported that a verified
   * adjunct strip took it to 13/20. THIS FILE'S CORPUS IS NOT THAT CORPUS —
   * it could not be reproduced here — so 14/19 and 19/19 are measurements of
   * THIS corpus and must not be quoted as a reproduction of the reviewer's.
   * What reproduces is the DIRECTION and the CAUSE: a clause-wide negator lets
   * adjunct-shadowed claims through, and stripping the adjunct closes them.
   * 19/19 is therefore evidence about the six escapes named above, and NOT
   * evidence that the strip generalises to phrasings nobody has written down.
   */
  /*
   * RE-MEASURED WHEN THE CORPUS GREW, AND THE NUMERATOR AND DENOMINATOR BOTH
   * MOVED. The four decimal-bearing entries took the corpus from 19 to 23, and
   * the clause-wide-negator reference catches all four (none of them contains a
   * negator), so `14/19 -> 19/19` became `18/23 -> 23/23`. The OLD figures are
   * recorded here rather than overwritten, because the thing worth carrying
   * forward is that they were correct about the 19-entry corpus and say nothing
   * about a 23-entry one. WHAT DID NOT MOVE IS THE FINDING: the five misses are
   * the same five adjunct-shadowed clauses, asserted below by count and by the
   * classifier that follows.
   */
  it('the adjunct strip is what closes the gap: 18/23 before, 23/23 after', () => {
    const before = EXTRACTION_REPHRASINGS.filter(
      (s) => fileToFieldClaimsClauseWideNegator(s).length === 0,
    );
    const after = EXTRACTION_REPHRASINGS.filter((s) => fileToFieldClaims(s).length === 0);
    expect(EXTRACTION_REPHRASINGS.length, 'the corpus size the ratio is over').toBe(23);
    expect(EXTRACTION_REPHRASINGS.length - before.length, 'pre-fix catch count').toBe(18);
    expect(EXTRACTION_REPHRASINGS.length - after.length, 'post-fix catch count').toBe(23);
    expect(before.length, 'the pre-fix misses are the adjunct-shadowed ones').toBe(5);
    expect(after).toEqual([]);
    // The five are ADJUNCT-shadowed, not decimal-shadowed: the adjunct
    // reference shares the FIXED splitter, so a decimal entry cannot be one of
    // these misses. Asserted, so the two fixes cannot be confused for each other.
    for (const missed of before) {
      expect(
        ADJUNCT_HEAD.test(missed),
        `"${missed}" is a pre-fix miss that carries no trailing adjunct, so the ` +
          'adjunct diagnosis does not cover it.',
      ).toBe(true);
    }
  });
});

describe('UX-004 §5b · Family B catches every plausible rephrasing', () => {
  it('catches 100% of the schema-is-the-whole-gate corpus', () => {
    const missed = SCHEMA_GATE_REPHRASINGS.filter((s) => schemaWholeGateClaims(s).length === 0);
    expect(
      missed,
      `${SCHEMA_GATE_REPHRASINGS.length - missed.length}/${SCHEMA_GATE_REPHRASINGS.length} caught.`,
    ).toEqual([]);
  });

  /*
   * Same posture as Family A's ratio test, and the same honesty note: an
   * independent review measured the original seven patterns at 2/12 on its own
   * corpus. On THIS 20-entry corpus they catch 10/20, and the extended set
   * catches 20/20. The two "before" figures are not comparable — different
   * corpora — and neither is quoted as the other.
   */
  /*
   * RE-MEASURED WHEN THE TWO DECIMAL CONTROLS JOINED THE CORPUS: 20 -> 22
   * entries, and the first seven patterns catch BOTH of them once their windows
   * are `[\s\S]`, so `10/20 -> 20/20` became `12/22 -> 22/22`. The old figures
   * were correct about the 20-entry corpus and are recorded rather than
   * overwritten. THE DIAGNOSIS IS UNCHANGED: the misses are still exactly 10,
   * still all count claims or verbed claims, and the classifier below still
   * proves it entry by entry.
   *
   * NOTE WHAT `schemaWholeGateClaimsBeforeI2` IS AND IS NOT. It slices the LIVE
   * pattern list, so "before I-2" means "the original seven patterns AS THEY
   * EXIST TODAY" — i.e. with the §5g widening applied. It isolates the I-2
   * ADDITIONS, not the window change; §5g isolates the window change.
   */
  it('the count and verb patterns are what close the gap: 12/22 before, 22/22 after', () => {
    const before = SCHEMA_GATE_REPHRASINGS.filter(
      (s) => schemaWholeGateClaimsBeforeI2(s).length === 0,
    );
    const after = SCHEMA_GATE_REPHRASINGS.filter((s) => schemaWholeGateClaims(s).length === 0);
    expect(SCHEMA_GATE_REPHRASINGS.length, 'the corpus size the ratio is over').toBe(22);
    expect(SCHEMA_GATE_REPHRASINGS.length - before.length, 'pre-I-2 catch count').toBe(12);
    expect(SCHEMA_GATE_REPHRASINGS.length - after.length, 'post-I-2 catch count').toBe(22);
    expect(after).toEqual([]);
    // ...and every pre-I-2 miss is a count claim or a verbed claim, which is the
    // diagnosis the extension rests on. If a miss appears that is neither, the
    // diagnosis is incomplete and the pattern set needs more than counts/verbs.
    for (const missed of before) {
      expect(
        /\b(one|two|four|five|both)\b/i.test(missed) ||
          // `decided|determined|settled` were missing from the first version of
          // this classifier, so "Export is decided by the official ISAAC schema"
          // — a PASSIVE verbed claim, and one of the ten misses — was reported as
          // outside the diagnosis. The claim was verbed; the classifier was not
          // complete. Corrected rather than dropped, because a classifier that
          // under-reports its own coverage is the same defect one level up.
          /\b(decides?|decided|determines?|determined|settles?|settled|runs?\s+next|is\s+what\s+remains|gated\s+on)\b/i.test(
            missed,
          ),
        `"${missed}" escaped the original patterns and is neither a count claim nor ` +
          'a verbed claim. The I-2 diagnosis does not cover it.',
      ).toBe(true);
    }
  });
});

describe('QA-013 §5b · Family C catches every plausible rephrasing', () => {
  it('catches 100% of the universal-evidence corpus', () => {
    const missed = UNIVERSAL_EVIDENCE_REPHRASINGS.filter(
      (s) => universalEvidenceClaims(s).length === 0,
    );
    expect(
      missed,
      `${UNIVERSAL_EVIDENCE_REPHRASINGS.length - missed.length}/` +
        `${UNIVERSAL_EVIDENCE_REPHRASINGS.length} caught.`,
    ).toEqual([]);
  });
});

// --- §5g the QA-010 WINDOW fix in Family B, MEASURED both directions -------
//
// `:427-437` states the `[\s\S]`-not-`[^.]` rule and applied it to ONE pattern.
// Eight of the thirteen still used `[^.]` — 11 window occurrences — so in the
// family whose subject vocabulary is "ISAAC v1.05", a dot-excluding window
// could not reach across the version number in its own subject.
//
// The pre-fix list is RECONSTRUCTED from the live one by narrowing exactly the
// entries that were widened, rather than copied — a copy would stop describing
// the patterns the moment one of them changed.

/** 0-based indices of the entries whose windows this change widened. Asserted
 *  below against the live list, so a reorder or an insertion fails here rather
 *  than silently re-pointing the measurement at the wrong patterns. */
const WIDENED_ENTRY_INDICES = [0, 1, 2, 4, 6, 9, 10, 11];

function schemaWholeGateClaimsNarrowWindows(text: string): string[] {
  const masked = maskRouteQualifiedCounts(text);
  return SCHEMA_IS_THE_WHOLE_GATE.filter(([, p], i) => {
    const pattern = WIDENED_ENTRY_INDICES.includes(i)
      ? // `split`/`join`, not `replaceAll`: this package's `lib` target predates
        // ES2021 and `npx tsc -b` rejects `replaceAll` outright.
        new RegExp(p.source.split('[\\s\\S]').join('[^.]'), p.flags)
      : p;
    return pattern.test(masked);
  }).map(([label]) => label);
}

describe('QA-010 §5g · Family B window widening, both directions', () => {
  it('the widened set is exactly the 8 entries with 11 occurrences it claims', () => {
    const widened = SCHEMA_IS_THE_WHOLE_GATE.map(([, p], i) => [i, p] as const).filter(
      ([, p]) => p.source.includes('[\\s\\S]'),
    );
    // Entries 7 and 12 already used `[\s\S]` before this change, so the set of
    // patterns CONTAINING it is 10, of which 8 are the ones narrowed above.
    expect(
      widened.map(([i]) => i),
      'a pattern was added, removed or reordered. WIDENED_ENTRY_INDICES points at ' +
        'positions, so §5g would otherwise go on measuring the wrong patterns and ' +
        'keep passing.',
    ).toEqual([0, 1, 2, 4, 6, 7, 9, 10, 11, 12]);
    const narrowedOccurrences = WIDENED_ENTRY_INDICES.map(
      (i) => (SCHEMA_IS_THE_WHOLE_GATE[i][1].source.match(/\[\\s\\S\]/g) ?? []).length,
    ).reduce((a, b) => a + b, 0);
    expect(narrowedOccurrences, 'window occurrences under narrowing').toBe(11);
  });

  it('the review’s negative control escaped ENTIRELY with narrow windows', () => {
    const withVersion = 'That is the only ISAAC v1.05 rule that blocks an export.';
    expect(
      schemaWholeGateClaimsNarrowWindows(withVersion),
      'if this now FIRES, the narrow-window reconstruction is not reproducing the ' +
        'pre-fix behaviour and the ratio below means nothing.',
    ).toEqual([]);
    expect(schemaWholeGateClaims(withVersion)).toEqual([
      'an exclusive gate on export, named and verbed',
    ]);
  });

  it('the SAME sentence without the version number was caught either way', () => {
    // The pair is the whole argument: identical claim, one token apart, and only
    // the narrow window could tell them apart — which is exactly what a
    // sentence proxy must not do.
    const withoutVersion = 'That is the only ISAAC rule that blocks an export.';
    expect(schemaWholeGateClaimsNarrowWindows(withoutVersion)).toEqual([
      'an exclusive gate on export, named and verbed',
    ]);
    expect(schemaWholeGateClaims(withoutVersion)).toEqual([
      'an exclusive gate on export, named and verbed',
    ]);
  });

  it('the widening introduces NO false positive on any correct-copy fixture', () => {
    // The §3b risk, measured rather than argued: a wider window can cross a
    // sentence boundary and flag two unrelated clauses as one claim. Measured
    // over all 16 fixtures, it flags nothing new — and nothing at all.
    const regressions = CORRECT_COPY_FIXTURES.filter(
      ([, text]) =>
        schemaWholeGateClaims(text).length > schemaWholeGateClaimsNarrowWindows(text).length,
    ).map(([what]) => what);
    expect(
      regressions,
      'widening a window made a family fire on correct copy. That teaches the next ' +
        'reader to weaken the guard rather than fix the copy (§3b), so narrow the ' +
        'specific window rather than accepting this.',
    ).toEqual([]);
    for (const [, text] of CORRECT_COPY_FIXTURES) {
      expect(schemaWholeGateClaims(text)).toEqual([]);
    }
  });

  /*
   * 21/22, not a dramatic number, AND THAT IS THE HONEST FRAMING. The widening
   * closes exactly ONE entry of this corpus — the decimal-bearing control — and
   * it is quoted at 1 rather than inflated, because the other 21 were already
   * caught and the corpus was never designed to probe windows. The value of the
   * change is not the ratio; it is that the SPECIFIC escape class named at
   * `:427-437` can no longer walk through 8 of the 13 patterns. §5b's own
   * honesty note makes the same distinction for a different fix.
   */
  it('and it costs no coverage: 21/22 narrow, 22/22 wide', () => {
    const narrow = SCHEMA_GATE_REPHRASINGS.filter(
      (x) => schemaWholeGateClaimsNarrowWindows(x).length > 0,
    ).length;
    const wide = SCHEMA_GATE_REPHRASINGS.filter((x) => schemaWholeGateClaims(x).length > 0).length;
    expect(narrow, 'narrow-window catch count').toBe(21);
    expect(wide, 'wide-window catch count').toBe(22);
  });
});

// --- §5f the QA-010 split fix, MEASURED with its corpus ---------------------
//
// Same posture as §5b: the pre-fix behaviour is kept as a function so the
// improvement is measured rather than described, and the honest caveat travels
// with the number. Two directions are asserted for each family — the previously
// escaping input is shown to have escaped, and shown not to escape now.

describe('QA-010 §5f · the version-aware clause split, both directions', () => {
  /** The four decimal-bearing entries, by the property that defines the class
   *  rather than by index — an index would silently follow a corpus reorder. */
  const DECIMAL_A = EXTRACTION_REPHRASINGS.filter((x) => /\d\.\d/.test(x));
  const DECIMAL_C = UNIVERSAL_EVIDENCE_REPHRASINGS.filter((x) => /\d\.\d/.test(x));

  it('the corpus now CONTAINS the class at all — it contained none of it before', () => {
    // The review's central point: a ratio asserted as a test is only as good as
    // its corpus. Zero decimal-bearing entries is the state this replaces.
    expect(DECIMAL_A.length, 'Family A decimal-bearing entries').toBe(4);
    expect(DECIMAL_C.length, 'Family C decimal-bearing entries').toBe(2);
  });

  it('Family A: the version-naive split let 2 of the 4 through; the fix lets 0', () => {
    const escapedBefore = DECIMAL_A.filter((x) => fileToFieldClaimsVersionNaiveSplit(x).length === 0);
    const escapedAfter = DECIMAL_A.filter((x) => fileToFieldClaims(x).length === 0);
    expect(escapedBefore.length, 'escapes under /[.;:,]/').toBe(2);
    expect(escapedAfter, 'escapes under the version-aware split').toEqual([]);
    // NAMED, so the two that escaped are not confused with the two that did not.
    // A version number defeats the conjunction only when it falls BETWEEN the
    // required tokens; in the other two, all three survive in one chunk.
    expect(escapedBefore).toEqual([
      'Draft extracts candidate field values from your v1.05 spreadsheets.',
      'Field values are extracted from your v1.05 workbook automatically.',
    ]);
  });

  it('Family C: the version-naive split let 2 of 2 through; the fix lets 0', () => {
    const escapedBefore = DECIMAL_C.filter(
      (x) => universalEvidenceClaimsVersionNaiveSplit(x).length === 0,
    );
    const escapedAfter = DECIMAL_C.filter((x) => universalEvidenceClaims(x).length === 0);
    expect(escapedBefore.length, 'escapes under /[.;:,]/').toBe(2);
    expect(escapedAfter, 'escapes under the version-aware split').toEqual([]);
  });

  it('the fix moves NO verdict on the pre-existing, decimal-free corpora', () => {
    // The lookbehind declines only a dot between two digits, so on a corpus
    // with no decimal in it the two splitters must agree exactly. If this ever
    // fails, the fix is doing more than it claims and the §5b figures above are
    // no longer measurements of the adjunct strip alone.
    for (const corpus of [
      EXTRACTION_REPHRASINGS.filter((x) => !/\d\.\d/.test(x)),
      UNIVERSAL_EVIDENCE_REPHRASINGS.filter((x) => !/\d\.\d/.test(x)),
      CORRECT_COPY_FIXTURES.map(([, text]) => text),
    ]) {
      for (const entry of corpus) {
        expect(fileToFieldClaimsVersionNaiveSplit(entry), entry).toEqual(
          fileToFieldClaims(entry),
        );
        expect(universalEvidenceClaimsVersionNaiveSplit(entry), entry).toEqual(
          universalEvidenceClaims(entry),
        );
      }
    }
  });

  it('the shipped panel is unaffected by the split change', () => {
    // The panel's copy contains `v1.05`, so this is the one place the change
    // could plausibly have created a false positive on real copy. §5c already
    // asserts the panel trips no ban; this asserts the two splitters AGREE on
    // it, which is the stronger statement and localises any future difference.
    const panel = helpPanelText();
    expect(fileToFieldClaims(panel)).toEqual(fileToFieldClaimsVersionNaiveSplit(panel));
    expect(universalEvidenceClaims(panel)).toEqual(
      universalEvidenceClaimsVersionNaiveSplit(panel),
    );
    expect(panel, 'the panel really does contain a decimal, or this proves nothing').toMatch(
      /\d\.\d/,
    );
  });
});

// --- §5c the bans, applied to the shipped panel -----------------------------

describe('UX-003/UX-004 §5c · the shipped panel makes none of these claims', () => {
  it('makes no file-to-field capability claim', () => {
    const flagged = fileToFieldClaims(helpPanelText());
    expect(
      flagged,
      'the Help panel affirms a file-to-field capability this build does not have. ' +
        'POST /api/uploads is an unconditional 403 and the CSV preview has no apply route.',
    ).toEqual([]);
  });

  it('never attributes the whole export gate to the official schema', () => {
    const flagged = schemaWholeGateClaims(helpPanelText());
    expect(
      flagged,
      'export_draft applies THREE gates (§1 counts them). The schema is upstream-owned ' +
        "and the other two are ISAAC's; no surface may conflate them (CLAUDE.md §11).",
    ).toEqual([]);
  });

  it('makes no unscoped universal claim about evidence', () => {
    const flagged = universalEvidenceClaims(helpPanelText());
    expect(
      flagged,
      'a field is allowed to have no evidence by design (CLAUDE.md §5), and a field ' +
        'awaiting confirmation shows no citation even when evidence exists.',
    ).toEqual([]);
  });
});

// --- §5d no false positives on correct copy ---------------------------------

/**
 * The correct copy must NOT trip any family.
 *
 * This is not a decoration. §5c already reads the shipped panel, but it reads it
 * as a whole; these fixtures isolate the sentences most likely to be flagged —
 * the ones that mention files, reading, fields, gating and evidence BECAUSE they
 * are denying or scoping exactly the claims banned above. A false positive here
 * is the outcome `upload-claim-parity.test.tsx` §3b warns about: it teaches the
 * next reader to weaken the guard rather than fix the copy.
 *
 * I-2 REMOVED ONE ENTRY AND ADDED SIX. The removed one — "the two-gate
 * statement" — turned out to be a FALSE claim this file was certifying as
 * correct; it now lives in §5a as `RETIRED_TWO_GATE_SENTENCE`. The six additions
 * are the corrected copy plus the four route-qualified gate counts that must
 * stay sayable.
 */
const CORRECT_COPY_FIXTURES: [string, string][] = [
  [
    'the file-to-field denial, with both readers named and the refusal scoped',
    'No control here reads one of your files and fills a field from it. The upload route ' +
      'refuses every request, and only two controls read a file you pick — the Validator ' +
      'and the campaign-sheet CSV comparison — which report what they found and apply ' +
      'nothing to a record.',
  ],
  [
    'the file-to-field denial as it shipped at 43544c6c (still correctly scoped as prose)',
    'No control here reads one of your files and fills a field from it: file upload is ' +
      'refused, and the campaign-sheet CSV comparison is read-only with no route that ' +
      'applies what it found.',
  ],
  [
    'the capture disclosure',
    'Dictating into Capture does not write a field either. It stores every segment you ' +
      'dictate as a note, and anything it recognises becomes a proposal for a person to ' +
      'review.',
  ],
  [
    'the THREE-gate statement',
    "Export runs three checks, in order: the no-guessing draft checks, ISAAC's own " +
      'anchored-pattern exactness check, and the official ISAAC v1.05 schema. The first ' +
      "two are ISAAC's, not the schema's — a record can be valid against that schema and " +
      'still be refused here, and no screen reports such a refusal as a schema error. ' +
      'Neither the evidence audit nor advisory review gates anything.',
  ],
  [
    'step 5, corrected',
    'writes the official ISAAC record plus an evidence sidecar — and only when all three ' +
      'export gates pass.',
  ],
  [
    'a truthful three-gate reword that keeps the retired "gated on" frame',
    "Export is gated on the no-guessing draft checks, on ISAAC's own anchored-pattern " +
      'exactness check, and on the official ISAAC v1.05 schema.',
  ],
  [
    "GuidedCompletion's corrected status note and body copy",
    'Three gates decide export; the schema is one of them. Every blocker the system ' +
      'refused to guess is now confirmed or resolved. Three gates decide export, and they ' +
      'run on the Review Export Readiness screen.',
  ],
  [
    'the signals paragraph',
    'Evidence Audit is a deterministic evidence-coverage count. Official Validation is the ' +
      "ISAAC v1.05 schema verdict. Advisory review is a set of deterministic local checks " +
      "over the record's own content; it never blocks or authorizes anything. Neither the " +
      'evidence audit nor advisory review gates anything.',
  ],
  [
    'the corrected evidence sentence',
    'Citations show inline beside the value where evidence was recorded; a field honestly ' +
      'missing or awaiting your confirmation shows none. Exports write an evidence sidecar ' +
      '(<record>.evidence.json) beside the official record.',
  ],
  [
    'the validator screen’s own legitimate line',
    'Checked against official ISAAC schema v1.05',
  ],
  // ---- the four route-qualified gate counts, each CORRECT about its own route.
  [
    "officialAttribution's “ISAAC’s two gates” (ISAAC's OWN two, beside the schema)",
    'It names the gate and declines to say which of ISAAC’s two gates refused — ' +
      'export.py folds the no-guessing findings and the exactness findings into a single list.',
  ],
  [
    'ValidateReview’s CORRECTED standing note, which names ISAAC’s own two and claims neither',
    'Beyond the official schema there are ISAAC’s own two gates — the no-guessing checks ' +
      'and its anchored-pattern exactness gate. When either refuses, their findings arrive ' +
      'in one list, are not labelled apart from each other, and this check does not record ' +
      'which of the two produced them.',
  ],
  [
    'the POST /api/validate/record contract, which really does have two gates',
    'Two gates, reported separately. schema_ok and errors are the vendored official ' +
      'schema’s verdict; ok is narrower.',
  ],
  [
    'the same contract restated the other way round',
    'POST /api/validate/record reports the two gates separately (schema_ok and ' +
      'exactness_errors).',
  ],
  [
    "ExportReadiness's committed three-gate prose",
    'It clears THREE gates, not two — export.py runs check_exactness on the assembled ' +
      'record between the no-guessing report and the official validator.',
  ],
  [
    'the workflow steps that quantify over something OTHER than evidence',
    'opens a record. Every step below is re-derived from that record’s current state ' +
      'each time it is read. dry-runs the export over every unit of the record and reports ' +
      'what would still refuse.',
  ],
];

describe('UX-003/UX-004/QA-013 §5d · no family fires on correct copy', () => {
  it.each(CORRECT_COPY_FIXTURES)('%s trips no ban', (_what, text) => {
    expect(fileToFieldClaims(text)).toEqual([]);
    expect(schemaWholeGateClaims(text)).toEqual([]);
    expect(universalEvidenceClaims(text)).toEqual([]);
  });
});

// --- §5e the exemptions and the limitations, both PROVEN ---------------------

describe('I-2 §5e · the route-qualified exemptions are real exemptions, not dead code', () => {
  /*
   * An exemption that never fires is indistinguishable from one that is not
   * needed, and an exemption nobody can see is how a ban gets quietly widened
   * into uselessness. Each of these asserts BOTH directions: the span IS caught
   * without the mask, and IS NOT caught with it. If a future pattern change made
   * an exemption unnecessary, this fails and the exemption should be deleted
   * rather than left standing.
   */
  it.each([
    [
      "ISAAC's two gates",
      'It declines to say which of ISAAC’s two gates refused.',
    ],
    [
      'reports the two gates separately',
      'POST /api/validate/record reports the two gates separately (schema_ok and exactness_errors).',
    ],
    [
      'two gates, reported separately',
      'Two gates, reported separately. schema_ok and errors are the official schema’s verdict.',
    ],
  ])('%s is caught WITHOUT the mask and exempt WITH it', (_what, text) => {
    const unmasked = SCHEMA_IS_THE_WHOLE_GATE.filter(([, p]) => p.test(text)).map(([l]) => l);
    expect(
      unmasked,
      'this exemption is dead code: the pattern set no longer fires on the span at ' +
        'all, so masking it achieves nothing. Delete the exemption rather than keep a ' +
        'guard that looks narrower than it is.',
    ).not.toHaveLength(0);
    expect(schemaWholeGateClaims(text), 'the exemption does not hold').toEqual([]);
  });

  it('the enumeration pattern is TEMPERED, proven both ways', () => {
    // Named the draft check -> clean. Omitted it -> flagged. Same frame, one
    // difference, and it is the difference that makes the claim false.
    expect(schemaWholeGateClaims(RETIRED_TWO_GATE_SENTENCE)).not.toHaveLength(0);
    expect(
      schemaWholeGateClaims(
        "Export is gated on the no-guessing draft checks, on ISAAC's own anchored-pattern " +
          'exactness check, and on the official ISAAC v1.05 schema.',
      ),
    ).toEqual([]);
  });
});

describe('I-2 §5e · the ONE measured false positive, recorded rather than papered over', () => {
  /*
   * MEASURED, AND IT IS PRE-EXISTING — present with the clause-wide negator and
   * with the adjunct strip alike, so it is not a cost of this change.
   *
   * `lib/settingsContent.ts:342` ships the model formulation of the scoped
   * upload claim: "...while the CSV preview and the record validator do read
   * what you paste or pick...". Family A flags it, because `record` in "the
   * record validator" satisfies FIELD_NOUN as a component NAME rather than as
   * the object of the verb — a noun-phrase ambiguity no regex resolves.
   *
   * THE REMEDY IS SCOPE, NOT A DENYLIST. Family A is applied to the Help panel's
   * rendered text and to the corpora in this file, and to nothing else; widening
   * it to `settingsContent` would need a proper-noun denylist over caller-chosen
   * free text, which is the construction `upload-claim-parity.test.tsx:262` and
   * `export.build_sidecar` both record failing here. Pinning the false positive
   * makes the limitation mechanical: if someone later fixes it, THIS fails and
   * the paragraph above has to be updated with them.
   */
  const SETTINGS_MODEL_FORMULATION =
    'file upload is refused outright, with no file parsed at all, while the CSV preview ' +
    'and the record validator do read what you paste or pick — in memory, never stored, ' +
    'and logged only as an outcome, never as content.';

  it('Family A flags settingsContent’s correct copy, and always did', () => {
    expect(fileToFieldClaims(SETTINGS_MODEL_FORMULATION)).not.toHaveLength(0);
    expect(fileToFieldClaimsClauseWideNegator(SETTINGS_MODEL_FORMULATION)).not.toHaveLength(0);
  });

  it('so Family A is not run over that module — only over Help and these corpora', () => {
    // A structural statement of the scope, so "we only run it on Help" is a fact
    // about this file rather than a claim in a comment: the only production text
    // any family is applied to in §5c is the Help panel's own rendered output.
    const thisFile = frontendSource('__tests__/help-claim-parity.test.tsx');
    expect(thisFile).toMatch(/fileToFieldClaims\(helpPanelText\(\)\)/);
    expect(thisFile).not.toMatch(/fileToFieldClaims\(\s*frontendSource\(/);
  });
});

/*
 * WHAT THESE FAMILIES STILL CANNOT CATCH — extended for I-2 and QA-013, and
 * kept honest rather than kept short.
 *
 *  - FAMILY A is a clause-local affirmative detector, not a parser. A phrasing
 *    with none of its three ingredients — "just point ISAAC at your data and it
 *    does the rest" — passes everything here. The adjunct strip closes six
 *    measured escapes; it enumerates its adjunct heads, so a seventh head
 *    ("bar none", "hands-free", "zero-touch") escapes until someone adds it.
 *    And it carries one measured FALSE POSITIVE, pinned above.
 *  - FAMILY B is pattern-based and now includes COUNT claims, which means it is
 *    coupled to a number: it bans one/two/four/five and permits three. §1 is what
 *    makes that safe, by counting `export_draft`'s refusal returns mechanically.
 *    If a fourth gate is ever added, §1 fails first — but until someone edits
 *    this file, Family B would then be banning the TRUE count. That is a known,
 *    deliberate coupling, not an oversight.
 *  - FAMILY B's exemptions are a closed list of THREE spans (four patterns; two
 *    of them cover the same `validate/record` sentence written both ways round).
 *    A fourth correct route-qualified count, written in different words, will be
 *    flagged as a false positive. That is the intended failure direction (noisy,
 *    not silent). The list was FOUR spans until `ValidateReview`'s "one gate of
 *    its own" exemption was deleted rather than renewed — it had been recorded as
 *    CONTESTED, the contest was settled against the sentence, and the corrected
 *    copy needs no exemption of its own because it reuses exemption 1's wording.
 *  - FAMILY C needs a universal quantifier word. "A field links to its evidence
 *    trail" — singular, generic, and exactly as false — passes. So does "fields
 *    link to their evidence". It also needs an evidence noun, so "All fields show
 *    where their value came from" escapes (measured).
 *  - NONE of the three reads backend-authored copy. The OpenAPI descriptions the
 *    Endpoint Explorer renders are invisible to every pattern in this file, and
 *    `test/apiFixtures.ts` mirrors several of them.
 *  - A HUMAN REVIEWER REMAINS THE BACKSTOP. Every defect these families were
 *    extended for was found by a person reading the copy against the source,
 *    not by a pattern. The families stop a RETURN; they do not detect a first
 *    occurrence of something nobody has written down yet.
 */

// ============================================================================
// §7 — THE SAME CLAIM CLASS ON THE OTHER SURFACE THAT SHIPPED IT
// ============================================================================
//
// This file is named for the Help popover, and §7 reads a different screen. It
// is here rather than in a sibling file on purpose, and the reason is the defect
// it closes.
//
// I-2's Family B additions were written because "Two gates on export" shipped on
// HelpPanel. THE SAME CLAIM CLASS WAS SHIPPING ON `screens/GuidedCompletion.tsx`
// AT THE SAME TIME, in three places: the status-bar note at `:826` ("The official
// ISAAC schema check runs next and decides export."), the body copy of the
// finished panel at `:1235` (the same claim, 409 lines away), and the `:812`
// comment that vouched for the second while repeating the first. `CLAUDE.md` §15
// records what happens when a claim class is fixed on one surface and left on
// another — "all N artifacts are fixed" is itself a checkable claim, and this
// repository has published it unchecked.
//
// ONE DETECTOR, TWO SURFACES, and that is why §7 is not a separate file. The
// sibling guards in this repository deliberately DUPLICATE their source readers
// "so no file can silently change another's scan" — but duplicating a
// fourteen-pattern ban set is the opposite trade: two copies drift, and the copy
// that drifts is the one nobody is reading. Family B is defined once, above, and
// applied to both surfaces here.
//
// RENDERED, NOT SOURCE-SCANNED, for the reason `helpPanelText` records: a source
// scan of `GuidedCompletion.tsx` matches every banned phrase inside the
// correction comments that explain why they are banned, so it would fail on the
// fix and pass on the defect.

/** The finished-completion screen — `pending: []` from the first load, which is
 *  the branch that renders BOTH corrected sentences at once. */
async function completionFinishedText(): Promise<string> {
  stubFetchRoutes(exportReadyRoutes('demo'));
  const view = render(
    <MemoryRouter
      initialEntries={['/record/demo/complete']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
  // The anchor `completion-export.test.tsx` already uses for this branch.
  await view.findByText('Nothing is left for you to confirm.');

  const done = document.querySelector('.completion-done');
  const note = document.querySelector('.statusbar-note');
  expect(done, 'the finished completion panel did not render').toBeTruthy();
  expect(note, 'the completion status bar rendered no note').toBeTruthy();
  // Scoped to the two elements that carried the claim, deliberately not to the
  // whole document: the app shell around them mounts other surfaces' copy, and a
  // ban that reads everything on the page reports their wording as this screen's
  // defect.
  return `${done?.textContent ?? ''} ${note?.textContent ?? ''}`;
}

describe('I-2 §7 · GuidedCompletion never attributes export to the official schema', () => {
  it('the finished panel and its status note make no whole-gate claim', async () => {
    const rendered = await completionFinishedText();
    expect(
      schemaWholeGateClaims(rendered),
      'GuidedCompletion attributes export to the official ISAAC schema. export_draft ' +
        'applies THREE gates (§1 counts them mechanically), the schema is the LAST of ' +
        'the three, and CLAUDE.md §11 forbids any surface from reporting an ISAAC-gate ' +
        'refusal as an official-schema error.',
    ).toEqual([]);
  });

  it('it states the three-gate claim positively, not merely avoiding the false one', async () => {
    // A ban is satisfied by saying nothing. This screen is where a reader is sent
    // onward to the export screen, so the forward-looking sentence has to be
    // present as well as true — otherwise the "fix" is a deletion.
    const rendered = await completionFinishedText();
    expect(rendered).toMatch(/\bthree\b[\s\S]{0,20}\bgates?\b/i);
  });

  it('POLARITY: both retired GuidedCompletion strings are caught by the same detector', () => {
    // The rendered assertions above cannot fail if the detector has gone quiet,
    // so the detector is proven separately on the exact strings that shipped.
    expect(schemaWholeGateClaims(RETIRED_DECIDES_EXPORT_NOTE)).not.toHaveLength(0);
    expect(schemaWholeGateClaims(RETIRED_SCHEMA_RUNS_NEXT_BODY)).not.toHaveLength(0);
  });
});

// ============================================================================
// §8 — THE SITE FAMILY B'S THIRD EXEMPTION USED TO HIDE
// ============================================================================
//
// `components/ValidateReview.tsx` carried "ISAAC applies one gate of its own
// (anchored-pattern exactness)" behind a mask recorded as CONTESTED. The contest
// is settled (see the exemptions block comment above): the sentence was false on
// the count, false to name the gate it counted, and false in its last clause,
// which predated `official_validator_ran`.
//
// SO THE MASK IS GONE AND THE SITE IS COVERED, which is the whole point. An
// exemption for a site that has been made compliant is a standing permission
// nobody granted, and the next sentence to land on that text inherits it.
//
// RENDERED, NOT SOURCE-SCANNED, for the reason §6 and §7 both record: this
// component's correction comment quotes the retired sentence verbatim, so a
// source scan would fail on the fix and pass on the defect.

/** The standing note as a reader meets it, with the review in its `data` state. */
async function validateReviewNoteText(): Promise<string> {
  const id = 'EXP-SYNTHETIC-1';
  const path = (rel: string) => `/api/experiments/${id}${rel}`;
  stubFetchRoutes({
    [`POST ${path('/validate')}`]: {
      body: {
        ok: true,
        errors: [],
        schema: 'ISAAC v1.05',
        dry_run: true,
        runs: [
          {
            run_id: 'RUN-1',
            run_label: 'Run 1',
            record_id: 'REC-1',
            ok: true,
            errors: [],
            dry_run: true,
            official_validator_ran: true,
          },
        ],
      },
    },
    [`GET ${path('/warnings')}`]: {
      body: { advisory: true, gating: false, warnings: [], dry_run: true, runs: [] },
    },
    [`GET ${path('/evidence-classification')}`]: {
      body: {
        record_rev: 3,
        field_results: [],
        counts: {
          supported: 0,
          inferred_candidate: 0,
          insufficient_evidence: 0,
          conflicting_evidence: 0,
          unknown: 0,
          unreadable: 0,
        },
      },
    },
  } as Parameters<typeof stubFetchRoutes>[0]);

  render(<ValidateReview experimentId={id} />);
  fireEvent.click(screen.getByRole('button', { name: 'Validate & Review' }));
  await screen.findByText(/1 run checked/);

  // Scoped to the notes this screen writes itself, deliberately not to the whole
  // section: the per-unit headings below are `officialAttribution.ts`'s own words,
  // and a ban that read them would report the register's copy as this screen's.
  const notes = Array.from(document.querySelectorAll('.vr-note'));
  expect(notes.length, 'the standing notes did not render').toBeGreaterThan(0);
  return notes.map((n) => n.textContent ?? '').join(' ');
}

describe('§8 · ValidateReview never miscounts or singles out ISAAC’s own gates', () => {
  it('the standing notes make no whole-gate claim', async () => {
    const rendered = await validateReviewNoteText();
    expect(
      schemaWholeGateClaims(rendered),
      'ValidateReview states a gate count Family B bans. `export_draft` applies ' +
        'THREE gates (§1 counts them mechanically), TWO of which are ISAAC’s own, and ' +
        '`officialAttribution.ts:163-169` forbids naming one of those two: the wire ' +
        'does not record which refused.',
    ).toEqual([]);
  });

  it('it names BOTH of ISAAC’s own gates and claims neither', async () => {
    // A ban is satisfied by saying nothing, and the valuable half of this note is
    // the part that stops a reader taking a dry-run finding for a schema error. So
    // the positive content is asserted too: both gates named, and the pointer to the
    // surface that DOES report them separately.
    const rendered = await validateReviewNoteText();
    expect(rendered).toMatch(/ISAAC[’']s own two gates/);
    expect(rendered).toMatch(/no-guessing checks/);
    expect(rendered).toMatch(/anchored-pattern exactness gate/);
    expect(rendered).toMatch(/does not record which of the two/);
    expect(rendered).toMatch(/Standalone Validator/);
  });

  it('it does not attribute a candidate record’s findings to the document', async () => {
    // The retired clause read "nothing below names the official ISAAC schema as the
    // source unless a written record was checked". `_validate_unit`'s DRY-RUN branch
    // publishes `official_validator_ran: true` whenever `validate_official` produced
    // the findings, so that clause was false about the commonest failing payload in
    // the product. The corrected note points at each unit's own heading instead.
    const rendered = await validateReviewNoteText();
    expect(rendered).not.toMatch(/unless a written record was checked/);
    expect(rendered).toMatch(/Each unit below says whether the official ISAAC schema/);
  });

  it('POLARITY: the retired sentence is caught by the same detector, unmasked', () => {
    // The rendered assertions cannot fail if the mask were reinstated or the
    // patterns went quiet, so the detector is proven on the exact span that shipped.
    // This is the assertion that would have gone red on the day the exemption was
    // added, and it is why the exemption was deleted rather than renewed.
    expect(schemaWholeGateClaims(RETIRED_ONE_GATE_NOTE)).not.toHaveLength(0);
  });
});
