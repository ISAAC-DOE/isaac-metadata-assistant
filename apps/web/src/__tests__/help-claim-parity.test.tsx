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
 *
 * WHAT IT CANNOT CATCH, stated plainly. §3's Family A is a clause-local
 * affirmative detector, not a parser: it flags a clause that pairs an
 * extraction verb, a field noun and a source-file noun with no negator in the
 * same clause. A novel phrasing that implies the capability without any of the
 * three nouns — "just point ISAAC at your data and it does the rest" — passes
 * every pattern here. A human reviewer remains the backstop for newly written
 * capability claims. It also reads the Help panel's own rendered text and
 * `apps/web/src`: backend-authored copy (the OpenAPI descriptions the Endpoint
 * Explorer renders) is invisible to it.
 */

import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

import { describe, it, expect, afterEach } from 'vitest';
import { cleanup, render, fireEvent, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { HelpPanel } from '../components/HelpPanel';
import { TopBar } from '../components/TopBar';
import { LABELS } from '../lib/labels';
import { CANONICAL_STEPS } from '../lib/workflowSteps';

afterEach(cleanup);

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
function helpPanelText(): string {
  render(<HelpPanel />);
  fireEvent.click(screen.getByRole('button', { name: 'Help' }));
  return screen.getByRole('dialog').textContent ?? '';
}

/** The `<strong>` label of each item in the "How it works" list, in order. */
function helpStepLabels(): string[] {
  render(<HelpPanel />);
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
  ['file upload is refused', /\bupload\b[^.]{0,30}\b(refused|disabled|blocked)\b/i],
  [
    'the CSV comparison is read-only with no route that applies it',
    /\b(csv|campaign[- ]sheet)\b[^.]{0,80}\b(read-only|no route that applies|nothing is applied)\b/i,
  ],
  [
    'dictated words survive whether or not a proposal is accepted',
    /\bnote\b[^.]{0,120}\bproposal\b|\bproposal\b[^.]{0,120}\b(note|survive)\b/i,
  ],
  [
    'export is gated on the official schema AND on ISAAC’s exactness check',
    // `[\s\S]`, NOT `[^.]`. The sentence contains the literal `v1.05`, so a
    // dot-excluding window cannot reach across it — the first version of this
    // pattern failed on correct copy for exactly that reason, which is a useful
    // reminder that `[^.]` is a sentence proxy and breaks on version numbers.
    /\bgated\b[\s\S]{0,60}\bschema\b[\s\S]{0,60}\banchored[- ]pattern exactness\b/i,
  ],
  [
    'an exactness refusal is ISAAC’s, not the schema’s',
    /\bISAAC’s, not the schema’s|\bISAAC's, not the schema's/i,
  ],
  [
    'a record can be schema-valid and still refused',
    /\bvalid against official ISAAC v1\.05\b[^.]{0,60}\b(still be refused|refused)\b/i,
  ],
  [
    'no screen reports such a refusal as a schema error',
    /\bno screen\b[^.]{0,60}\bschema error\b/i,
  ],
  [
    'the audit and advisory tiers gate nothing',
    /\b(neither|nor)\b[^.]{0,80}\b(gates? (anything|nothing)|never blocks)\b/i,
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

/** Every clause that affirms a file-to-field capability. Empty is the pass. */
function fileToFieldClaims(text: string): string[] {
  return text
    .split(/[.;:,]/)
    .map((c) => c.trim())
    .filter(
      (c) =>
        EXTRACTION_VERB.test(c) &&
        FIELD_NOUN.test(c) &&
        SOURCE_FILE_NOUN.test(c) &&
        !NEGATOR.test(c),
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
 */
const SCHEMA_IS_THE_WHOLE_GATE: [string, RegExp][] = [
  [
    'an exclusive gate on export, named and verbed',
    /\b(only|sole|solely|single|one)\b[^.]{0,25}\b(signal|gates?|check|thing|rule|verdict)\b[^.]{0,45}\b(gates?|gating|blocks?|blocking|authoris\w*|authoriz\w*|decides?)\b[^.]{0,25}\bexports?\b/i,
  ],
  [
    'an exclusive gate adjacent to the word export',
    /\b(only|sole|single) (signal|gate|check|rule|verdict)\b[^.]{0,30}\bexports?\b/i,
  ],
  [
    'the schema verdict described as the only gate',
    /\b(schema|official validation)\b[^.]{0,40}\b(is|remains) the (only|sole|single)\b/i,
  ],
  [
    'export gated only/solely on something',
    /\b(gated|blocked|decided|refused|validated) (only|solely|exclusively|purely|just) (on|by|against)\b/i,
  ],
  [
    'nothing but X gates export',
    /\bnothing (but|other than|else|more than)\b[^.]{0,50}\b(gates?|blocks?|refus\w*)\b/i,
  ],
  [
    'the retired step-4 sentence: a bare check against the official schema',
    /\bchecks? the (exported )?record against the official ISAAC( v1\.05)? schema\b/i,
  ],
  [
    'an exactness refusal reported as a schema error',
    /\b(exactness|anchored[- ]pattern)\b[^.]{0,60}\b(schema (error|violation|failure)|invalid against)\b/i,
  ],
];

function schemaWholeGateClaims(text: string): string[] {
  return SCHEMA_IS_THE_WHOLE_GATE.filter(([, p]) => p.test(text)).map(([label]) => label);
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
});

// --- §5b the rephrasing corpus ----------------------------------------------

/**
 * Plausible rephrasings, INCLUDING one-word edits of the retired sentences.
 *
 * The requirement is 100%, not "most": §11 records a widened guard in this
 * repository catching 1 of 8, and a one-word edit of a retired sentence walking
 * straight through. Each entry is a sentence a well-meaning author could write
 * next, not an adversarial construction.
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
});

describe('UX-004 §5b · Family B catches every plausible rephrasing', () => {
  it('catches 100% of the schema-is-the-whole-gate corpus', () => {
    const missed = SCHEMA_GATE_REPHRASINGS.filter((s) => schemaWholeGateClaims(s).length === 0);
    expect(
      missed,
      `${SCHEMA_GATE_REPHRASINGS.length - missed.length}/${SCHEMA_GATE_REPHRASINGS.length} caught.`,
    ).toEqual([]);
  });
});

// --- §5c the bans, applied to the shipped panel -----------------------------

describe('UX-003/UX-004 §5c · the shipped panel makes neither claim', () => {
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
      'ok = schema_ok AND exactness_ok. The schema is upstream-owned and the ' +
        "exactness rule is ISAAC's; no surface may conflate them (CLAUDE.md §11).",
    ).toEqual([]);
  });
});

// --- §5d no false positives on correct copy ---------------------------------

/**
 * The correct copy must NOT trip either family.
 *
 * This is not a decoration. §5c already reads the shipped panel, but it reads it
 * as a whole; these fixtures isolate the sentences most likely to be flagged —
 * the ones that mention files, reading, fields and gating BECAUSE they are
 * denying or scoping exactly the claims banned above. A false positive here is
 * the outcome `upload-claim-parity.test.tsx` §3b warns about: it teaches the
 * next reader to weaken the guard rather than fix the copy.
 */
const CORRECT_COPY_FIXTURES: [string, string][] = [
  [
    'the file-to-field denial',
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
    'the two-gate statement',
    "Export is gated on the official ISAAC v1.05 schema and on ISAAC's own anchored-pattern " +
      "exactness check. A refusal by that check is ISAAC's, not the schema's: the record can " +
      'be valid against official ISAAC v1.05 and still be refused here, and no screen reports ' +
      'such a refusal as a schema error.',
  ],
  [
    'the signals paragraph',
    'Evidence Audit is a deterministic evidence-coverage count. Official Validation is the ' +
      "ISAAC v1.05 schema verdict. Advisory review is a set of deterministic local checks " +
      "over the record's own content; it never blocks or authorizes anything. Neither the " +
      'evidence audit nor advisory review gates anything.',
  ],
  [
    'the validator screen’s own legitimate line',
    'Checked against official ISAAC schema v1.05',
  ],
];

describe('UX-003/UX-004 §5d · neither family fires on correct copy', () => {
  it.each(CORRECT_COPY_FIXTURES)('%s trips no ban', (_what, text) => {
    expect(fileToFieldClaims(text)).toEqual([]);
    expect(schemaWholeGateClaims(text)).toEqual([]);
  });
});
