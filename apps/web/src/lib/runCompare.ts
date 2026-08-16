/*
 * TWO RUNS, SIDE BY SIDE — the pure half.
 *
 * WHAT THIS FILE IS ALLOWED TO SAY, and it is a much shorter list than a
 * comparison invites. It may say that two runs hold different values at an
 * address, that only one of them holds a value there, that they hold the same
 * value from different sources, or that this surface cannot compare what is
 * there. It may NOT say why, may not say which of the two is preferable, and may
 * not connect a difference at one address to anything at another. A comparison
 * screen is the easiest place in this product to do science on the scientist's
 * behalf, and every function below is written so that the only sentences it can
 * produce are statements of what two documents contain.
 *
 * IT COMPUTES NOTHING ABOUT INHERITANCE, exactly as `runOverrides.ts` does not.
 * The three resolution states are the SERVER's (`routes._resolution_state`); this
 * file reads `run.inherited[address].state` and compares the two answers. It never
 * decides which of a record value and a run value "wins", never merges them, and
 * never resolves an address the server did not resolve.
 *
 * THREE AXES, DELIBERATELY NOT ONE. Flattening them is the defect this model
 * exists to prevent, and each of the three was a real way to state something
 * false:
 *
 *   1. VALUE — what the two runs hold. `equal`, `differs`, `one-absent`,
 *      `both-absent`, `incomparable`.
 *   2. PROVENANCE — where each value came from, in `RunInheritedPanel`'s OWN
 *      vocabulary (inherited / overridden / absent). Two runs can hold the same
 *      value with different provenance, and that is a fact about the record, not
 *      a non-event: one of them follows the record and the other does not.
 *   3. EVIDENCE — how many evidence entries and what draft status each run
 *      records BESIDE the value. Counted, never judged. A larger count is not a
 *      better value; see PROVENANCE IS NOT VERIFICATION in `RunInheritedPanel`.
 *
 * ABSENCE IS NOT A VALUE, and it gets its own relation rather than being rendered
 * as a difference with one side blank. "Run 2 records nothing here" and "Run 2
 * records something else here" are different facts about a scientist's record and
 * only one of them is a disagreement.
 *
 * AND `unresolved` IS NOT `absent`. `absent` is the server saying it resolved the
 * address and neither side carries anything; `unresolved` is the address not being
 * in that run's resolution map at all. The two cannot both be called "no value"
 * without asserting a resolution that was never reported.
 */

import { RUN_FIELDS } from './runFields';
import {
  BLOCK_ADDRESS_PREFIX,
  FIELD_ADDRESS_PREFIX,
  isUnrenderableValue,
  payloadValue,
  valueText,
} from './runOverrides';
import type { ApiRunFieldEnvelope, ApiRunView } from './types';

/* ── one side of one row ───────────────────────────────────────────────────── */

/**
 * WHERE THIS RUN'S VALUE AT THIS ADDRESS CAME FROM.
 *
 * `own` is a run-level field the run holds itself — the addresses `RUN_FIELDS`
 * covers, which have no inheritance and therefore no provenance question.
 * `inherited`, `overridden` and `absent` are the SERVER's three resolution states,
 * spelt as it spells them. `unresolved` is this file's own fifth answer and means
 * the run's resolution map has no entry for the address at all — see the header.
 */
export type CompareOrigin = 'own' | 'inherited' | 'overridden' | 'absent' | 'unresolved';

export interface CompareSide {
  origin: CompareOrigin;
  /** True when this run carries SOMETHING at the address, renderable or not. */
  present: boolean;
  /** The value as one line, or `null` for absent AND for unrenderable. */
  text: string | null;
  /** True when a value IS there and cannot be shown in one line (object/array). */
  unrenderable: boolean;
  /** The raw value, for the equality test. Never rendered. */
  value: unknown;
  /** What the RECORD carries at this address now. Record-level rows only. */
  recordText: string | null;
  /** The draft envelope's `status`, verbatim. `null` when it carries none. */
  status: string | null;
  /** How many evidence entries the envelope carries. `null` when absent. */
  evidenceCount: number | null;
}

/* ── the three relations, and the one category the row is rendered from ────── */

export type ValueRelation = 'equal' | 'differs' | 'one-absent' | 'both-absent' | 'incomparable';
export type ProvenanceRelation = 'not-applicable' | 'same' | 'differs';
export type EvidenceRelation = 'not-applicable' | 'same' | 'differs';

/**
 * THE ONE LABEL A ROW IS RENDERED FROM, chosen from the three relations by a fixed
 * priority so that the breakdown counts PARTITION the differing rows rather than
 * overlapping. A row that differs in value AND in provenance is counted once, as
 * `value`, and its cell states both facts — the count is a partition, the sentence
 * is not a summary.
 *
 * The priority, and why it is this order: `incomparable` first because nothing
 * else can be asserted once a side cannot be read; `absent-on-one` next because
 * absence is not a value and must never be counted among value differences;
 * then value, then provenance, then evidence — narrowing from what the run holds
 * to what is recorded about it.
 */
export type CompareCategory =
  | 'same'
  | 'value'
  | 'absent-on-one'
  | 'provenance'
  | 'evidence'
  | 'incomparable';

export interface CompareRow {
  /** Stable react key. `scope` is part of it because the two spaces can collide. */
  key: string;
  /** The address as the server spells it (`field:…`) or the dotted run-field path. */
  address: string;
  /** The dotted official path, with any namespace removed. */
  path: string;
  scope: 'run-field' | 'record-level';
  /** The group this row is rendered under. See {@link SECTION_TITLES}. */
  section: string;
  a: CompareSide;
  b: CompareSide;
  value: ValueRelation;
  provenance: ProvenanceRelation;
  evidence: EvidenceRelation;
  category: CompareCategory;
  /**
   * TRUE WHEN THIS ROW IS NOT KNOWN TO BE THE SAME ON BOTH RUNS — which is what
   * decides whether it appears in the default, differences-only view.
   *
   * IT IS DELIBERATELY NOT CALLED `differs`, and the distinction is the whole
   * reason this field was renamed. An `incomparable` row is listed — the reader
   * should see that an address exists which this table cannot show — but the app
   * does NOT know that the two runs differ there. Calling one boolean `differs`
   * made "is it listed?" and "does it differ?" the same question, and the summary
   * then counted an address it could not read as an address that disagreed.
   * {@link CompareTally.differing} answers the second question strictly; this
   * field answers only the first.
   */
  listed: boolean;
  /**
   * True when the two sides render as the SAME TEXT but hold different JSON
   * types — `300` and `"300"`. Stated rather than shown as two identical strings
   * flagged "different", which reads as a rendering fault.
   */
  sameTextDifferentType: boolean;
}

export interface CompareGroup {
  id: string;
  title: string;
  rows: CompareRow[];
}

/**
 * EVERY NUMBER HERE IS A COUNT OF ROWS THIS TABLE RENDERS — never a score, never a
 * percentage, and never a figure with a denominator nobody enumerated. There is no
 * "how similar are these runs" number and there must not be one: similarity has no
 * denominator, and a percentage would be exactly the invented figure `CLAUDE.md` §5
 * and this repo's denominator rule forbid.
 */
export interface CompareTally {
  /** Every row in the table, whether or not it could be compared. */
  compared: number;
  /**
   * Rows where the two runs are KNOWN to disagree on some axis.
   *
   * `incomparable` is excluded, and that exclusion is the point. A row this table
   * cannot read is not a row where the runs differ — it is a row where nothing is
   * known — and counting it among the differences puts a number on screen that
   * asserts a disagreement nobody observed. So the three headline numbers do NOT
   * sum to `compared` whenever `incomparable` is non-zero, and the surface states
   * the third number rather than hiding the gap.
   */
  differing: number;
  /** Rows where the runs agree on all three axes. Excludes `incomparable`. */
  agreeing: number;
  /** The breakdown. These four sum to {@link differing}, by construction. */
  value: number;
  absentOnOne: number;
  provenance: number;
  evidence: number;
  /** Rows that are neither `differing` nor `agreeing`. Counted on its own. */
  incomparable: number;
  /** Agreeing rows where NEITHER run records anything. Part of `agreeing`. */
  bothAbsent: number;
}

export interface RunComparison {
  groups: CompareGroup[];
  tally: CompareTally;
  /**
   * `block:` ADDRESSES, BY NAME, NOT COMPARED — the same boundary
   * `runOverrides.overrideRows` draws, for the same reason. A block payload is a
   * whole object or list; this table has no honest one-line rendering for one, and
   * a diff of two objects it cannot show is a claim the reader cannot check.
   */
  blocks: string[];
}

/* ── sections ──────────────────────────────────────────────────────────────── */

/**
 * The group a record-level address belongs to, keyed by the first segment of its
 * official path. The titles are the schema's own top-level property names in
 * product words; an unrecognised segment is titled from the segment itself rather
 * than swept into "Other", so a schema addition is visible instead of hidden.
 */
const SECTION_TITLES: Record<string, string> = {
  context: 'Context',
  measurement: 'Measurements',
  descriptors: 'Descriptors',
  assets: 'Assets',
  sample: 'Sample',
  system: 'System and instrument',
  timestamps: 'Timing',
  links: 'Links',
  computation: 'Computation',
  attribution: 'Attribution',
  tags: 'Tags',
};

/** The order groups are rendered in. Anything unlisted follows, alphabetically. */
const SECTION_ORDER = [
  'run-fields',
  'context',
  'measurement',
  'descriptors',
  'assets',
  'sample',
  'system',
  'timestamps',
  'links',
  'computation',
  'attribution',
  'tags',
];

export const RUN_FIELD_SECTION = 'run-fields';

/**
 * The title of the run's-own-fields group.
 *
 * IT NAMES ITS SCOPE, like every other count and heading on this surface: these
 * are the addresses a RUN may hold itself, not the whole of what distinguishes two
 * runs. Everything else on this screen is record-level and is read by both runs.
 */
export const RUN_FIELD_SECTION_TITLE = 'Conditions recorded on the run itself';

function sectionOf(path: string): string {
  const head = path.split('.')[0] ?? '';
  return head;
}

function sectionTitle(id: string): string {
  if (id === RUN_FIELD_SECTION) return RUN_FIELD_SECTION_TITLE;
  return SECTION_TITLES[id] ?? id;
}

/* ── reading one side ──────────────────────────────────────────────────────── */

function envelopeStatus(payload: unknown): string | null {
  if (payload === null || typeof payload !== 'object') return null;
  const status = (payload as { status?: unknown }).status;
  return typeof status === 'string' && status.trim() !== '' ? status.trim() : null;
}

function envelopeEvidenceCount(payload: unknown): number | null {
  if (payload === null || typeof payload !== 'object') return null;
  const evidence = (payload as { evidence?: unknown }).evidence;
  return Array.isArray(evidence) ? evidence.length : null;
}

/** One side of a RUN-LEVEL field row. There is no provenance question here. */
function ownSide(env: ApiRunFieldEnvelope | undefined): CompareSide {
  const value = env === undefined || env === null ? null : (env.value ?? null);
  const present = value !== null && value !== undefined;
  return {
    origin: present ? 'own' : 'absent',
    present,
    text: valueText(value),
    unrenderable: isUnrenderableValue(value),
    value: present ? value : null,
    recordText: null,
    status: env === undefined ? null : envelopeStatus(env),
    evidenceCount: env === undefined ? null : envelopeEvidenceCount(env),
  };
}

/** One side of a RECORD-LEVEL row, read entirely from the server's resolution. */
function inheritedSide(run: ApiRunView, address: string): CompareSide {
  const resolution = run.inherited?.[address];
  if (!resolution) {
    return {
      origin: 'unresolved',
      present: false,
      text: null,
      unrenderable: false,
      value: null,
      recordText: null,
      status: null,
      evidenceCount: null,
    };
  }
  const value = payloadValue(resolution.payload);
  const present = value !== null && value !== undefined;
  return {
    // The server's own word, and `absent` is its word too — not a stand-in for
    // "the payload was empty". A state of `inherited` or `overridden` carrying no
    // value keeps its state; the value relation says the value is missing.
    origin: resolution.state,
    present,
    text: valueText(value),
    unrenderable: isUnrenderableValue(value),
    value: present ? value : null,
    recordText: valueText(payloadValue(resolution.inherited_payload)),
    status: envelopeStatus(resolution.payload),
    evidenceCount: envelopeEvidenceCount(resolution.payload),
  };
}

/* ── comparing two sides ───────────────────────────────────────────────────── */

/**
 * Are these the same value?
 *
 * SCALARS ONLY, AND THAT IS THE POINT. Anything that is not a string, number or
 * boolean is refused by `valueText` upstream and lands in `incomparable`, so this
 * never performs a structural diff of two objects — a claim of equality (or of
 * difference) between two things the table cannot show is a claim the reader
 * cannot check. `Object.is` rather than `===` so `NaN` compares equal to itself
 * instead of making an address permanently "different" from a copy of itself.
 */
function sameScalar(a: unknown, b: unknown): boolean {
  return Object.is(a, b);
}

function valueRelation(a: CompareSide, b: CompareSide): ValueRelation {
  if (a.unrenderable || b.unrenderable) return 'incomparable';
  if (!a.present && !b.present) return 'both-absent';
  if (!a.present || !b.present) return 'one-absent';
  return sameScalar(a.value, b.value) ? 'equal' : 'differs';
}

function provenanceRelation(
  scope: 'run-field' | 'record-level',
  a: CompareSide,
  b: CompareSide,
): ProvenanceRelation {
  if (scope === 'run-field') return 'not-applicable';
  /*
   * PROVENANCE IS ONLY A QUESTION WHERE BOTH RUNS HAVE SOMETHING. With one side
   * absent, "these came from different places" would be a second reading of the
   * same absence the value relation already reports — and it would double-count
   * one fact as two differences.
   */
  if (!a.present || !b.present) return 'not-applicable';
  return a.origin === b.origin ? 'same' : 'differs';
}

function evidenceRelation(a: CompareSide, b: CompareSide): EvidenceRelation {
  if (!a.present || !b.present) return 'not-applicable';
  if (a.status === b.status && a.evidenceCount === b.evidenceCount) return 'same';
  return 'differs';
}

function categoryOf(
  value: ValueRelation,
  provenance: ProvenanceRelation,
  evidence: EvidenceRelation,
): CompareCategory {
  if (value === 'incomparable') return 'incomparable';
  if (value === 'one-absent') return 'absent-on-one';
  if (value === 'differs') return 'value';
  if (provenance === 'differs') return 'provenance';
  if (evidence === 'differs') return 'evidence';
  return 'same';
}

function buildRow(
  scope: 'run-field' | 'record-level',
  address: string,
  path: string,
  section: string,
  a: CompareSide,
  b: CompareSide,
): CompareRow {
  const value = valueRelation(a, b);
  const provenance = provenanceRelation(scope, a, b);
  const evidence = evidenceRelation(a, b);
  const category = categoryOf(value, provenance, evidence);
  return {
    key: `${scope}:${address}`,
    address,
    path,
    scope,
    section,
    a,
    b,
    value,
    provenance,
    evidence,
    category,
    listed: category !== 'same',
    sameTextDifferentType:
      value === 'differs' &&
      a.text !== null &&
      a.text === b.text &&
      typeof a.value !== typeof b.value,
  };
}

/* ── the comparison ────────────────────────────────────────────────────────── */

/**
 * THE ADDRESS SPACE IS A UNION, NEVER ONE RUN'S KEYS. Comparing run A's addresses
 * against run B would make the comparison asymmetric: an address only B carries
 * would simply not appear, and the reader would be shown a table that omits, in
 * silence, the very rows they opened it to find. `RUN_FIELDS` is unioned in as well
 * so the five run-level addresses are always rows — a `both-absent` row for
 * temperature is a fact ("neither run records one"), and it is the fact a reader
 * asking "are these the same apart from temperature?" needs.
 */
export function buildRunComparison(a: ApiRunView, b: ApiRunView): RunComparison {
  const rows: CompareRow[] = [];

  const fieldPaths = new Set<string>(RUN_FIELDS.map((spec) => spec.path));
  for (const path of Object.keys(a.fields ?? {})) fieldPaths.add(path);
  for (const path of Object.keys(b.fields ?? {})) fieldPaths.add(path);

  const runFieldOrder = new Map(RUN_FIELDS.map((spec, i) => [spec.path, i]));
  const sortedFieldPaths = [...fieldPaths].sort((x, y) => {
    const ix = runFieldOrder.get(x);
    const iy = runFieldOrder.get(y);
    if (ix !== undefined && iy !== undefined) return ix - iy;
    // A path the run workspace does not offer a control for still belongs in the
    // table — the run may carry it — and it sorts after the five it does offer.
    if (ix !== undefined) return -1;
    if (iy !== undefined) return 1;
    return x.localeCompare(y);
  });

  for (const path of sortedFieldPaths) {
    rows.push(
      buildRow(
        'run-field',
        path,
        path,
        RUN_FIELD_SECTION,
        ownSide(a.fields?.[path]),
        ownSide(b.fields?.[path]),
      ),
    );
  }

  const addresses = new Set<string>();
  const blocks = new Set<string>();
  for (const run of [a, b]) {
    for (const address of Object.keys(run.inherited ?? {})) {
      if (address.startsWith(BLOCK_ADDRESS_PREFIX)) {
        blocks.add(address.slice(BLOCK_ADDRESS_PREFIX.length));
        continue;
      }
      if (!address.startsWith(FIELD_ADDRESS_PREFIX)) continue;
      addresses.add(address);
    }
  }

  for (const address of [...addresses].sort((x, y) => x.localeCompare(y))) {
    const path = address.slice(FIELD_ADDRESS_PREFIX.length);
    rows.push(
      buildRow(
        'record-level',
        address,
        path,
        sectionOf(path),
        inheritedSide(a, address),
        inheritedSide(b, address),
      ),
    );
  }

  const bySection = new Map<string, CompareRow[]>();
  for (const row of rows) {
    const list = bySection.get(row.section);
    if (list === undefined) bySection.set(row.section, [row]);
    else list.push(row);
  }
  const groups: CompareGroup[] = [...bySection.entries()]
    .map(([id, groupRows]) => ({ id, title: sectionTitle(id), rows: groupRows }))
    .sort((x, y) => {
      const ix = SECTION_ORDER.indexOf(x.id);
      const iy = SECTION_ORDER.indexOf(y.id);
      if (ix !== -1 && iy !== -1) return ix - iy;
      if (ix !== -1) return -1;
      if (iy !== -1) return 1;
      return x.title.localeCompare(y.title);
    });

  return { groups, tally: tallyOf(rows), blocks: [...blocks].sort((x, y) => x.localeCompare(y)) };
}

function tallyOf(rows: CompareRow[]): CompareTally {
  const count = (category: CompareCategory) =>
    rows.filter((row) => row.category === category).length;
  const incomparable = count('incomparable');
  // STRICT: a row this table could not read is in neither of the first two
  // numbers. See {@link CompareTally.differing}.
  const differing = rows.filter(
    (row) => row.listed && row.category !== 'incomparable',
  ).length;
  return {
    compared: rows.length,
    differing,
    agreeing: rows.length - differing - incomparable,
    value: count('value'),
    absentOnOne: count('absent-on-one'),
    provenance: count('provenance'),
    evidence: count('evidence'),
    incomparable,
    bothAbsent: rows.filter((row) => row.value === 'both-absent').length,
  };
}

/* ── words ─────────────────────────────────────────────────────────────────── */

/**
 * THE PROVENANCE WORD FOR ONE SIDE — `RunInheritedPanel`'s vocabulary, reused
 * rather than reinvented.
 *
 * That panel already says "Inherited from record" and "Overridden on this run",
 * and a second surface inventing "shared"/"local" for the same two states would
 * make a scientist learn the distinction twice and reconcile the two names
 * themselves. The strings differ only where this table's column context makes the
 * panel's trailing words redundant.
 */
export function originWord(origin: CompareOrigin): string {
  switch (origin) {
    case 'own':
      return 'Recorded on this run';
    case 'inherited':
      return 'Inherited from record';
    case 'overridden':
      return 'Overridden on this run';
    case 'absent':
      return 'No value recorded';
    case 'unresolved':
      return 'Address not resolved for this run';
  }
}

/**
 * THE CATEGORY WORD — the text half of the glyph-plus-word-plus-surface rule this
 * repo applies to every state it renders (see `runs.css`, "distinguishable WITHOUT
 * COLOUR"). Colour is never the carrier here either.
 *
 * NOT ONE OF THESE IS EVALUATIVE. There is no "conflict", no "mismatch", no
 * "problem" and no "unexpected": all four would characterise a difference the
 * scientist has not yet explained, and characterising it is not this table's job.
 */
export function categoryWord(category: CompareCategory): string {
  switch (category) {
    case 'same':
      return 'Same';
    case 'value':
      return 'Different values';
    case 'absent-on-one':
      return 'On one run only';
    case 'provenance':
      return 'Same value, different source';
    case 'evidence':
      return 'Same value, different record-keeping';
    case 'incomparable':
      return 'Not compared here';
  }
}

/** How many evidence entries a side records, as words. Counted, never judged. */
export function evidenceWord(side: CompareSide): string {
  if (side.evidenceCount === null) return 'no evidence list recorded';
  if (side.evidenceCount === 0) return 'no evidence entries';
  return `${side.evidenceCount} evidence ${side.evidenceCount === 1 ? 'entry' : 'entries'}`;
}
