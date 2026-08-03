/*
 * P1 · PRODUCT-FACING LANGUAGE — a vocabulary ratchet over the frontend sources.
 *
 * WHY THIS IS A SEPARATE FILE and not a block inside `hosted-truthfulness.test.tsx`.
 * That file guards a different property: whether copy makes a claim that is FALSE
 * on the hosted deployment (a "local" API, an unqualified data-regime claim). This
 * file guards a property that is not about truth at all — the app's normal product
 * UI described itself in the vocabulary of its own test harness. "Run Synthetic
 * Demo", "Canonical Scenarios Preserved", "Legacy Demo Records Removed" and
 * "Demo answer (synthetic)" were all TRUE; they were simply the wrong register for
 * a scientist opening the app. Merging the two would blur a truth guard with a
 * register guard, and the next reader would not be able to tell which failure they
 * were looking at.
 *
 * WHAT IT ASSERTS. No frontend source file contains, in copy a user can read, any
 * of the retired phrasings in `RETIRED_VOCABULARY` below. Every pattern is pinned
 * in §3 against the exact string that shipped before P1, so a pattern that stops
 * detecting its own defect fails here rather than going quiet.
 *
 * THE DIRECTION OF THE RENAME MATTERS, and this file cannot enforce it. The five
 * records in the workspace are built-in worked examples restored from committed
 * reference files. There is provably no way for a user to create a record in this
 * build: `create_experiment()` has no production caller, `POST /api/uploads` is an
 * unconditional 403, and `POST /api/demo/run` writes nothing at all when its
 * canonical target is unchanged. So the correct replacement vocabulary is
 * "example" / "built-in example" / "reference", NEVER "Create a Record" / "New
 * Experiment" / "Import My Materials" / "Your Records". Renaming toward
 * user-authorship would be a WORSE defect than the jargon, because it would be
 * false rather than merely technical. `FORBIDDEN_CREATION_PROMISE` catches the
 * handful of shapes that have plausibly tempted someone; it is a tripwire, not a
 * detector (see the limits section).
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * WHAT THIS GUARD CANNOT CATCH. Stated plainly, because a guard that looks
 * complete is worse than one that admits its edges.
 *
 *  1. BACKEND-SERVED COPY — AND THIS GAP HAS ALREADY FIRED, so it is not a
 *     hypothetical. This test reads `apps/web/src` only. The most-rendered string
 *     in the entire app — the seed record title — is built in
 *     `apps/api/isaac_api/workspace.py`, and so are the five per-record labels,
 *     the suggested-answer label in `serialize.py`, and every OpenAPI summary and
 *     description the Endpoint Explorer renders verbatim. Nothing here sees any of
 *     them. The Python-side sibling is
 *     `apps/api/tests/test_backend_copy_truthfulness.py`, which guards TRUTH, not
 *     register — so backend register is guarded by review alone.
 *
 *     WHAT IT LET THROUGH: P1 shipped with `routes.py`'s `TAG_EVIDENCE` still
 *     reading "previews of the source fixtures the evidence cites" while the
 *     operation it groups had been reworded to "reference source file". Both render
 *     on the same Endpoint Explorer screen, and no test failed. The review caught
 *     it; a fix-up slice corrected the string. A register guard over
 *     `apps/api/isaac_api/**` string literals is the obvious remedy and was NOT
 *     built here — it is a backend test, out of this file's scope — so treat the
 *     gap as live and check backend copy by hand in any copy slice.
 *
 *  2. COPY COMPOSED AT RUNTIME. A string assembled from parts ("Reset " + noun),
 *     interpolated from a variable, or received in a response body and rendered
 *     as-is is invisible to a source scan. The mode chip's accessible name, for
 *     example, is `${chipText(health)} — ${CHIP_ARIA_DETAIL[...]}`; the halves are
 *     scanned, the joined sentence is not.
 *
 *  3. NOVEL PHRASINGS OF THE SAME REGISTER PROBLEM. This is a ratchet over shapes
 *     that actually shipped, plus close neighbours. "Try the sample workflow",
 *     "Load the test record", "Execute the pipeline harness" and "Restore the
 *     baseline dataset" all pass it today. They are recorded as known gaps, not as
 *     targets: patterns wide enough to catch them would start flagging the honest
 *     mode-and-governance copy that MUST keep its exact wording, and an
 *     over-reaching guard gets weakened by the next person who trips it.
 *
 *  4. TITLES, CSS CLASSES, WIRE NAMES AND IDENTIFIERS ARE OUT OF SCOPE BY DESIGN.
 *     Every pattern below is multi-word or word-plus-digit, so `resetDemo`,
 *     `demo_answer`, `.demo-refused-title`, `ResetDemoDialog`, `POST /api/demo/run`
 *     and `type Mode = 'synthetic'` cannot match. That is deliberate: those are
 *     wire and code names, changing them is a migration, and the project rules
 *     forbid it in a copy slice.
 *
 *  5. COMMENTS ARE STRIPPED, so the prose EXPLAINING a retired string is never
 *     counted as the retired string. The cost is that a false claim living only in
 *     a comment is not caught here. Comments are not rendered, so that is the
 *     right trade — but it does mean this guard says nothing about them.
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

import { describe, it, expect } from 'vitest';

// --- 1. the scan ------------------------------------------------------------

/**
 * Locate `apps/web/src` on disk. Deliberately NOT `import.meta.url`: under the
 * jsdom environment that is an http URL, not a file one. Duplicated from the
 * sibling guards rather than exported, so no file can silently change another's
 * scan — the same reasoning `db-recon-truthfulness.test.tsx` gives.
 */
function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  return found;
}

const SRC_DIR = locateSrcDir();

/** Tests and fixtures are copy ABOUT the app, not copy the app renders. Internal
 *  test code is allowed — required, even — to keep calling a generated fixture a
 *  fixture and a retired string by its retired name. */
const NOT_USER_FACING_DIRS = new Set(['__tests__', 'test']);
const isColocatedTest = (name: string): boolean => /\.test\.tsx?$/.test(name);

function frontendSourceFiles(dir: string = SRC_DIR): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!NOT_USER_FACING_DIRS.has(entry.name)) found.push(...frontendSourceFiles(full));
    } else if (
      /\.tsx?$/.test(entry.name) &&
      !entry.name.endsWith('.d.ts') &&
      !isColocatedTest(entry.name)
    ) {
      found.push(relative(SRC_DIR, full).split(sep).join('/'));
    }
  }
  return found.sort();
}

/**
 * Strip comments — both `/* … *\/` (which also removes `{/* … *\/}` JSX comments)
 * and `//` line comments, with the `[^:'"`]` guard that keeps `https://…` inside a
 * literal from being eaten. Then collapse whitespace, because JSX wraps prose
 * across lines and TypeScript concatenates long strings: the browser renders
 * "Reset Workspace on My Experiments" from a source that reads
 * `Reset Workspace on My\n    Experiments`, and a phrase matched in the DOM would
 * otherwise go unmatched in the file.
 */
function renderedCopy(path: string): string {
  return readFileSync(join(SRC_DIR, path), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|[^:'"`\\])\/\/[^\n]*/g, '$1')
    .replace(/\s+/g, ' ');
}

// --- 2. the allowlist -------------------------------------------------------

/**
 * EXPLICIT, per-file, per-STRING, per-OCCURRENCE exemptions. Deliberately not
 * "exempt this file": an allowlisted file would go on absorbing new defects
 * invisibly. Each entry exempts exactly ONE occurrence of an exact substring —
 * `scannedCopy` removes the first match and nothing else — so a SECOND occurrence
 * of the same string in the same file is still flagged, and so is every other
 * retired phrasing anywhere in that file.
 *
 * ONE occurrence, not all of them, because the justification for each exemption is
 * a justification for a specific SITE: `RESET SYNTHETIC DEMO` is exempt because it
 * is the wire value one request body must carry. Nothing justifies a second copy,
 * and the previous mechanism (`copy.split(allowed).join(' ')`) removed every
 * occurrence, so a second one — including one used as user-visible copy — would
 * have been silently laundered. The per-entry count is pinned at 1 by
 * `the allowlist exempts ONE occurrence…` below, so if a legitimate second site
 * ever appears the guard fails and forces a deliberate decision rather than
 * absorbing it.
 *
 * Everything here is on the project's MUST-NOT-CHANGE list — a wire constant, or a
 * statement of what the runtime MODE is. Renaming any of them would either break
 * the protocol or make the app misreport itself, which is a worse defect than the
 * register problem this file exists to prevent.
 */
const ALLOWED: Readonly<Record<string, readonly string[]>> = {
  /*
   * The confirmation phrase for `POST /api/demo/reset`, pinned character-for-
   * character to `_RESET_CONFIRMATION` in `apps/api/isaac_api/routes.py`. It is a
   * WIRE VALUE and is never surfaced to a user: the dialog asks the operator to
   * type "RESET", and the client sends this constant on their behalf. Renaming it
   * on one side only would make every reset fail closed with a 409.
   */
  'lib/api.ts': ['RESET SYNTHETIC DEMO'],
};

/** How many times `needle` occurs in `haystack` (non-overlapping, exact). */
function occurrences(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1;
}

/**
 * Remove the FIRST occurrence of `needle` only. A space replaces it so the text on
 * either side is not spliced into a phrase the source never contained — the same
 * reasoning the backend guard's allowlist gives for using containment rather than
 * excision.
 */
function removeOneOccurrence(haystack: string, needle: string): string {
  const at = haystack.indexOf(needle);
  if (at === -1) return haystack;
  return `${haystack.slice(0, at)} ${haystack.slice(at + needle.length)}`;
}

function scannedCopy(path: string): string {
  let copy = renderedCopy(path);
  for (const allowed of ALLOWED[path] ?? []) copy = removeOneOccurrence(copy, allowed);
  return copy;
}

// --- 3. the retired vocabulary ---------------------------------------------

/**
 * Each entry is `[label, pattern, theStringThatShipped]`. The third element is not
 * decoration: §5 asserts every pattern still flags its own retired string, so a
 * pattern that is narrowed until it detects nothing fails loudly.
 *
 * Every pattern is multi-word or word-plus-digit on purpose — see limit (4).
 */
const RETIRED_VOCABULARY: readonly [string, RegExp, string][] = [
  [
    '"Demo" as the name of a control',
    /\b(run|reset|open|start|re-?run)\s+(the\s+)?(shared\s+)?(synthetic\s+)?demo\b/i,
    "actionRunDemo: 'Run Synthetic Demo'",
  ],
  [
    '"synthetic demo" as the name of the thing the user is looking at',
    /\bsynthetic\s+demo\b/i,
    'Restores the workspace to exactly the canonical synthetic demo scenarios',
  ],
  [
    '"demo data" as the label for the built-in examples',
    /\bdemo\s+data\b/i,
    "none: 'demo data only'",
  ],
  [
    '"Demo answer" as the label on a suggested value',
    /\bdemo\s+answers?\b/i,
    'aria-label="Demo answer suggestion"',
  ],
  [
    'the built-in examples called fixtures',
    /\b(synthetic|committed|seeded|source|two)[- ]fixtures?\b/i,
    'It reads only the two committed synthetic fixtures',
  ],
  [
    'a filename called a fixture basename',
    /\bfixture\s+(basename|allowlist|name)\b/i,
    'Path traversal rejected — pass a bare fixture basename.',
  ],
  [
    'seeding vocabulary in user-visible copy',
    /\b(re-?seed(s|ed|ing)?|seeded\s+fixture|canonical\s+seed|seed\s+content)\b/i,
    'been edited since it was seeded, and re-seeding it would discard those edits',
  ],
  [
    '"Scenario N" as the name of a record',
    /\bscenario\s+\d/i,
    'Scenario 2 · seeded: partial answers applied',
  ],
  [
    // Determiner-or-adjective + "scenario" is the shape that means "a record".
    // The BARE noun is deliberately not matched: `scenario` is a wire field name
    // on `GET /api/experiments` rows and a TypeScript property, and both are on
    // the must-not-change list.
    '"scenario" as the user-facing word for a record',
    /\b(edited|canonical|the\s+five|the|this|that)\s+scenarios?\b/i,
    'Demo not run — the scenario has been edited',
  ],
  ['"Legacy Demo Records"', /\blegacy\s+demo\b/i, "resetCountLegacy: 'Legacy Demo Records Removed'"],
  ['the "Safe · Fake" tag', /safe\s*·\s*fake/i, '<span className="onramp-tag">Safe · Fake</span>'],
  ['"the reference happy path"', /\bhappy\s+path\b/i, 'the reference happy path · ~10s'],
  [
    'the API described as a local backend',
    /\blocal\s+UI\s+backend\b/i,
    'ISAAC Metadata Assistant — local UI backend',
  ],
];

/**
 * The OPPOSITE failure: renaming toward a promise this build cannot keep. A
 * tripwire on the shapes that have plausibly tempted someone, NOT a detector for
 * the class — see limit (3). `New Record` is included because it is the exact
 * string P1 removed: a btn-primary on `/experiments` that navigated to the same
 * route as the example-run button beside it.
 */
const FORBIDDEN_CREATION_PROMISE: readonly [string, RegExp][] = [
  ['a control offering to create a record', /\bnew\s+(record|experiment)\b/i],
  ['a control offering to create a record', /\bcreate\s+(a\s+|your\s+)?(new\s+)?(record|experiment)\b/i],
  /*
   * Title Case, and CASE-SENSITIVE on purpose: this catches a LABEL or heading
   * ("Your Records"), not the ordinary possessive in a sentence. The app already
   * says "My Experiments" and "Loading your experiments…", and that framing is
   * pre-existing, out of P1's scope, and arguably fine — it names the workspace
   * the viewer is looking at, not who authored the records in it. A case-insensitive
   * pattern here would flag it, and the likely response would be to weaken the
   * pattern rather than to think about the difference. Recorded as a known gap:
   * a lower-case "your records" would slip through.
   */
  ["a heading calling the built-in examples the user's own", /\bYour\s+(Own\s+)?(Records|Experiments|Data)\b/],
  ['an import affordance the build does not have', /\bimport\s+(my|your)\b/i],
];

// --- 4. the guard over the real sources ------------------------------------

describe('P1 · product-facing language — the scan itself', () => {
  const files = frontendSourceFiles();

  it('scans the real source files, not a duplicate of the strings in them', () => {
    expect(files.length).toBeGreaterThan(40);
    // The surfaces P1 actually reworded must all be inside the scan, or a
    // regression on any of them would pass unnoticed.
    for (const covered of [
      'components/GuidedPrompt.tsx',
      'components/ResetDemoDialog.tsx',
      'components/TopBar.tsx',
      'lib/adapt.ts',
      'lib/api.ts',
      'lib/labels.ts',
      'lib/settingsContent.ts',
      'screens/ExperimentsHome.tsx',
      'screens/GuidedCompletion.tsx',
      'screens/LoadMaterials.tsx',
      'screens/statistics/StatisticsPage.tsx',
    ]) {
      expect(files, `${covered} must be scanned`).toContain(covered);
    }
  });

  it('excludes test and fixture code, which is allowed to name retired strings', () => {
    expect(files.some((f) => f.startsWith('__tests__/'))).toBe(false);
    expect(files.some((f) => f.startsWith('test/'))).toBe(false);
    expect(files.some((f) => /\.test\.tsx?$/.test(f))).toBe(false);
    // this very file, and the fixture module, are among the things excluded
    expect(files).not.toContain('__tests__/product-facing-language.test.tsx');
    expect(files).not.toContain('test/apiFixtures.ts');
  });

  it('reads wrapped JSX prose as one sentence', () => {
    // The remedy line in the drift refusal is concatenated across two source
    // lines; without the whitespace collapse the guard would read it as two
    // fragments and a phrase spanning the break would be invisible.
    expect(renderedCopy('lib/labels.ts')).toContain(
      'use Reset Workspace on My Experiments',
    );
    // ...and the comments that explain the retired wording are gone, so a note
    // ABOUT a defect is never counted as the defect.
    expect(renderedCopy('lib/labels.ts')).not.toContain('NOT "New Record"');
  });
});

describe('P1 · product-facing language — no retired vocabulary in user-visible copy', () => {
  const files = frontendSourceFiles();

  it.each(RETIRED_VOCABULARY.map(([label, pattern]) => [label, pattern] as const))(
    'no file contains %s',
    (_label, pattern) => {
      const offenders = files.filter((path) => pattern.test(scannedCopy(path)));
      expect(offenders).toEqual([]);
    },
  );
});

describe('P1 · product-facing language — no copy promises record creation', () => {
  const files = frontendSourceFiles();

  it.each(FORBIDDEN_CREATION_PROMISE)('no file contains %s', (_label, pattern) => {
    const offenders = files.filter((path) => pattern.test(scannedCopy(path)));
    expect(offenders).toEqual([]);
  });
});

// --- 4b. R0 · the guided walkthrough's own copy ------------------------------

/*
 * A SECOND, NARROWER RATCHET, over the files R0 authored.
 *
 * WHY IT IS SCOPED TO THOSE FILES AND NOT TO THE WHOLE APP. The terms below
 * ("synthetic", "fixture", "demo", "mock", "scenario", …) are exactly the words
 * the app's GOVERNANCE copy is required to use: `db-recon-truthfulness.test.tsx`
 * asserts the Governance banner, the Governance & Safety policy tab and the Help
 * popover each say "records shown here are synthetic" / "the visible workspace
 * remains synthetic", and `hosted-truthfulness.test.tsx` pins the mode claims
 * verbatim. A repo-wide ban on those words would break a required-claim guard —
 * which is the failure this file's own header warns about: dropping a true claim
 * while removing jargon is a WORSE defect than the jargon.
 *
 * So the rule applied here is the honest one: NEW product copy is written in
 * product language, and the existing disclosure copy keeps the precise technical
 * wording its guards require. The walkthrough is new product copy, and every word
 * a reader sees in it comes from these three files.
 */
const TUTORIAL_COPY_FILES: readonly string[] = [
  'lib/tutorialSteps.ts',
  'components/TutorialPromotion.tsx',
  'components/GuidedTutorial.tsx',
  'screens/settings/HelpAndTutorial.tsx',
];

/** `[label, pattern, aStringItMustFlag]` — the third element keeps a pattern from
 *  being narrowed until it detects nothing, the same discipline §5 applies to the
 *  retired vocabulary above. */
const HARNESS_VOCABULARY: readonly [string, RegExp, string][] = [
  ['"synthetic" in any form', /\bsynthetic/i, 'the synthetic workspace'],
  ['"demo"', /\bdemos?\b/i, 'run the demo'],
  ['"fixture"', /\bfixtures?\b/i, 'restored from committed fixtures'],
  ['"scenario"', /\bscenarios?\b/i, 'open Scenario 2'],
  ['"mock"', /\bmock(ed|s)?\b/i, 'a mock record'],
  ['"fake"', /\bfake[ds]?\b/i, 'safe, fake data'],
  ['"seeded"/"seed data"', /\b(seeded|seed\s+data|test\s+data)\b/i, 'seeded test data'],
  ['"dummy"', /\bdummy\b/i, 'a dummy value'],
  ['"sandbox"', /\bsandbox(ed)?\b/i, 'a sandbox workspace'],
];

describe("R0 · the guided walkthrough's copy uses no harness vocabulary", () => {
  it('scans the real walkthrough copy files, all of which exist and are scanned', () => {
    const files = frontendSourceFiles();
    for (const path of TUTORIAL_COPY_FILES) {
      expect(files, `${path} must be scanned`).toContain(path);
      // Non-trivial: a file reduced to a stub would pass every pattern below.
      expect(renderedCopy(path).length, `${path} looks empty`).toBeGreaterThan(400);
    }
  });

  it.each(HARNESS_VOCABULARY.map(([label, pattern]) => [label, pattern] as const))(
    'no walkthrough copy file contains %s',
    (_label, pattern) => {
      const offenders = TUTORIAL_COPY_FILES.filter((path) => pattern.test(scannedCopy(path)));
      expect(offenders).toEqual([]);
    },
  );

  it.each(HARNESS_VOCABULARY.map(([label, pattern, shipped]) => [label, pattern, shipped]))(
    '%s is still detected',
    (_label, pattern, shipped) => {
      expect((pattern as RegExp).test(shipped as string)).toBe(true);
    },
  );

  it('leaves the walkthrough\'s actual copy alone — it must pass its own ratchet', () => {
    for (const shipped of [
      'Take the Guided Walkthrough',
      'Start Tutorial',
      'Skip for Now',
      'Skip Tutorial',
      'Replay Tutorial',
      'Close Tutorial',
      'Tutorial complete',
      'Help & Tutorial',
      'What My Experiments Contains',
      'Opening a Worked Example',
      'How Readiness Is Shown',
      'The Trust Readout',
      'Finding What Is Still Missing',
      'How Evidence Works',
      'Answering a Question',
      'How Confirmation Works',
      'When You Do Not Know',
      'How Validation Works',
      'Why Export Can Be Blocked',
      'Repairing What Blocks Export',
      'How Export Becomes Available',
      'Where the Standalone Validator Lives',
      'Where Settings and API Access Live',
      'Replaying This Walkthrough',
      'The records here are worked examples rebuilt from reference files committed to this build',
      'Example workspace',
    ]) {
      const harness = HARNESS_VOCABULARY.filter(([, p]) => p.test(shipped)).map(([l]) => l);
      expect(harness, `${shipped} is wrongly flagged as harness vocabulary`).toEqual([]);
      const retired = RETIRED_VOCABULARY.filter(([, p]) => p.test(shipped)).map(([l]) => l);
      expect(retired, `${shipped} is wrongly flagged as retired vocabulary`).toEqual([]);
      const promised = FORBIDDEN_CREATION_PROMISE.filter(([, p]) => p.test(shipped)).map(([l]) => l);
      expect(promised, `${shipped} is wrongly read as a creation promise`).toEqual([]);
    }
  });
});

// --- 5. the guard is proven on the strings it was written for ---------------

describe('P1 · product-facing language — every pattern still flags its own defect', () => {
  it.each(RETIRED_VOCABULARY.map(([label, pattern, shipped]) => [label, pattern, shipped]))(
    '%s is still detected',
    (_label, pattern, shipped) => {
      expect((pattern as RegExp).test(shipped as string)).toBe(true);
    },
  );

  it('flags every retired label from labels.ts as a set, not one lucky match', () => {
    const retiredLabels = [
      'Run Synthetic Demo',
      'Run Demo',
      'Reset Demo',
      'Reset Shared Synthetic Demo',
      'Reset Shared Demo',
      'Canonical Scenarios Preserved',
      'Legacy Demo Records Removed',
      'Demo not run — the scenario has been edited',
      'Edited scenario',
    ];
    for (const retired of retiredLabels) {
      const flagged = RETIRED_VOCABULARY.some(([, pattern]) => pattern.test(retired));
      expect(flagged, `${retired} is no longer flagged`).toBe(true);
    }
  });

  it('leaves the replacement vocabulary alone', () => {
    // If any of these tripped a pattern the guard would be unusable, because the
    // shipped copy would fail its own ratchet.
    for (const shipped of [
      'Open the Worked Example',
      'Run the Worked Example',
      'Reset Workspace',
      'Reset the Shared Workspace',
      'Reset Shared Workspace',
      'Built-in Examples Restored',
      'Additional Records Removed',
      'Example not re-run — this record has been edited',
      'Edited record',
      'Worked Example: CuO Cu K-edge XANES',
      'a complete example run · ~10s',
      'Built-in Example',
      'Example Run — Running',
      'Example answer suggestion',
      'example data only',
      'Confirm the example value',
      'Open a Record',
      'No experiments yet — open the built-in example to see a complete record.',
      'This is a shared, hosted example workspace.',
      'the built-in example is restored from fixed reference files',
      'Only the two committed reference files may be previewed.',
    ]) {
      const flagged = RETIRED_VOCABULARY.filter(([, p]) => p.test(shipped)).map(([l]) => l);
      expect(flagged, `${shipped} is wrongly flagged`).toEqual([]);
      const promised = FORBIDDEN_CREATION_PROMISE.filter(([, p]) => p.test(shipped)).map(([l]) => l);
      expect(promised, `${shipped} is wrongly read as a creation promise`).toEqual([]);
    }
  });

  it('leaves the mode and governance claims alone — they must keep their wording', () => {
    /*
     * These state what the runtime MODE is, and the project rules forbid changing
     * them: renaming any of them would make the app misreport itself. They are
     * listed here rather than allowlisted because no pattern should be touching
     * them in the first place — if one starts to, this test says so before someone
     * "fixes" the copy.
     */
    for (const claim of [
      // R0 renamed the CHIP to "Example workspace". "Synthetic workspace" is
      // still shipped copy — it leads the Governance banner and titles the Help
      // popover's governance section — and it must keep that wording: the
      // WORKSPACE_CLAIMS guard in `db-recon-truthfulness.test.tsx` REQUIRES the
      // word ("records shown here are synthetic" / "visible workspace remains
      // synthetic"), so removing it there would break a required-claim guard
      // rather than tidy a register. Both spellings are therefore listed.
      'Synthetic workspace',
      'Example workspace',
      'test DB diagnostics',
      'test DB check failed',
      'Synthetic-only mode — file upload is refused outright.',
      'CSV preview is available only in synthetic-only mode.',
      'This deployment runs in a synthetic-only data mode.',
      'Real or private data upload is approval-gated and not enabled in this workspace.',
      'Project memory indexes this project\'s source code, docs, schema, and test fixtures.',
      'A read-only reference for the canonical official ISAAC schema.',
    ]) {
      const flagged = RETIRED_VOCABULARY.filter(([, p]) => p.test(claim)).map(([l]) => l);
      expect(flagged, `${claim} is wrongly flagged`).toEqual([]);
    }
  });

  it('the creation tripwire flags the shapes it was written for', () => {
    for (const promise of [
      'New Record',
      'New Experiment',
      'Create a Record',
      'Create your record',
      'Import My Materials',
      'Your Records',
    ]) {
      const flagged = FORBIDDEN_CREATION_PROMISE.some(([, p]) => p.test(promise));
      expect(flagged, `${promise} is no longer flagged`).toBe(true);
    }
  });

  it('the allowlist exempts exact strings, never whole files', () => {
    for (const [path, allowed] of Object.entries(ALLOWED)) {
      expect(frontendSourceFiles(), `${path} must still be scanned`).toContain(path);
      for (const value of allowed) {
        // an allowlisted string must really be in that file (no dead exemptions)
        expect(renderedCopy(path), `${path} no longer contains ${value}`).toContain(value);
        // ...and it must really be something a pattern would otherwise flag, or
        // the exemption is silently widening the guard's blind spot
        expect(
          RETIRED_VOCABULARY.some(([, p]) => p.test(value)),
          `${value} is exempted but no pattern flags it — remove the exemption`,
        ).toBe(true);
      }
    }
    // and the exemption is surgical: the rest of that file really is still scanned
    // (it is not reduced to a stub by the removal).
    //
    // The assertion that used to sit here — `expect(scannedCopy('lib/api.ts'))
    // .not.toContain('RESET SYNTHETIC DEMO')` — was TAUTOLOGICAL: `scannedCopy`
    // removes that string, so it could not fail for any state of the source. It is
    // gone; the real property is pinned by the next test, which can fail.
    expect(scannedCopy('lib/api.ts').length).toBeGreaterThan(1000);
  });

  /*
   * P1 review — THE ALLOWLIST'S DEPTH, which the mechanism previously got wrong.
   *
   * `scannedCopy` used `copy.split(allowed).join(' ')`, removing EVERY occurrence
   * while the comment beside it claimed a second occurrence would still fail. The
   * review disproved it by adding a second `'RESET SYNTHETIC DEMO'` to `lib/api.ts`
   * and watching the suite stay green. Two properties are now pinned:
   *
   *   (a) each allowlisted string occurs exactly ONCE in its file — so if a second
   *       site ever appears, this fails and forces a decision instead of absorbing
   *       it; and
   *   (b) the removal really is one-deep — proven by doubling the REAL file's copy
   *       and showing the surviving occurrence is still flagged by a real pattern.
   *
   * (b) uses the production `removeOneOccurrence`, not a re-implementation, so the
   * proof cannot drift away from the mechanism it is proving.
   */
  it('the allowlist exempts ONE occurrence — a second copy of the same phrase still fails', () => {
    for (const [path, allowed] of Object.entries(ALLOWED)) {
      for (const value of allowed) {
        const raw = renderedCopy(path);
        expect(
          occurrences(raw, value),
          `${path} contains ${occurrences(raw, value)} copies of "${value}"; the ` +
            'allowlist exempts exactly ONE, so either remove the extra site or ' +
            'justify it here deliberately',
        ).toBe(1);

        const doubled = `${raw} ${value}`;
        const swept = removeOneOccurrence(doubled, value);
        expect(occurrences(swept, value), 'the removal must be one-deep').toBe(1);
        const flagged = RETIRED_VOCABULARY.filter(([, p]) => p.test(swept)).map(([l]) => l);
        expect(flagged, `a second copy of "${value}" in ${path} would not be caught`)
          .not.toEqual([]);
      }
    }
  });
});
