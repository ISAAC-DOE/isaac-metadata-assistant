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
 *
 * ── WHAT WAS ADDED, AND THE ONE DISTINCTION THE WIDENING TURNS ON ────────────
 *
 * TWO MORE AXES, and the reason they are axes rather than columns is the reason
 * the first three are:
 *
 *   4. REVIEW — what, if anything, ESTABLISHES the value, in `lib/provenance.ts`'s
 *      own vocabulary. It is a display MIRROR of the server's rule, computed from
 *      citations the run view already carries, exactly as that module's header
 *      says a surface holding an evidence entry may do. It is never a second
 *      source of truth, and it cannot report `resolved` — see `reviewStateFor`.
 *   5. SUPPORT, folded into the existing EVIDENCE axis. The axis used to compare a
 *      COUNT and a status; it now also compares WHICH entries are cited — source
 *      kind, source file, locator, derivation rule. Still counted and described,
 *      NEVER judged: a `user_confirmation` beside a `spreadsheet` is two different
 *      records of support, not a better one and a worse one.
 *
 * AND ONE THING THAT IS DELIBERATELY NOT AN AXIS: A RECORDED CONFLICT.
 *
 * `CompareRow.conflict` carries what `GET .../conflicts?run=` stored about the
 * address, and it is kept OUT of the value/provenance/evidence partition on
 * purpose. A value difference and a recorded conflict are different things and
 * this file must never let one become the other:
 *
 *   · A VALUE DIFFERENCE is BETWEEN THE TWO RUNS — two documents holding different
 *     answers at one address. It is not a fault, nobody recorded it, and calling it
 *     a "conflict" is the exact characterisation `categoryWord` refuses.
 *   · A RECORDED CONFLICT is WITHIN ONE RUN'S OWN EVIDENCE at one address — the
 *     server's finding that the citations stored there assert more than one
 *     distinct answer — together with whatever decision a person recorded about it.
 *     It exists whether or not the other run agrees, and it can sit on a row where
 *     the two runs are identical.
 *
 * So a conflict never changes a row's category, is never counted in
 * {@link CompareTally.differing}, and gets its own number. It does make a row
 * LISTED — an address where a decision is outstanding must not be hidden behind a
 * "same on both runs" filter — and {@link CompareTally.conflictedAgreeing} is how
 * the surface says why an agreeing row is on screen.
 *
 * BLOCK ADDRESSES ARE STILL NOT COMPARED, and the disclosure now says what is in
 * them. A block payload is an object; there is still no honest one-line rendering
 * of one and this file still refuses to diff two. What it CAN state is which
 * top-level KEYS each run's payload carries, which is a fact the reader can check
 * by opening either run — see {@link CompareBlock}.
 */

import { RUN_FIELDS } from './runFields';
import {
  BLOCK_ADDRESS_PREFIX,
  FIELD_ADDRESS_PREFIX,
  isUnrenderableValue,
  payloadValue,
  valueText,
} from './runOverrides';
import {
  ORIGIN_LABEL,
  PROVENANCE_ORIGINS,
  REVIEW_STATE_LABEL,
  originsFromEvidence,
  primaryOrigin,
  reviewStateFor,
  type ProvenanceOrigin,
  type ProvenanceReviewState,
} from './provenance';
import type { ApiConflict, ApiRunFieldEnvelope, ApiRunView, FieldEvidence } from './types';

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

/**
 * ONE CITED SUPPORT ENTRY, DESCRIBED — and description is the whole permission.
 *
 * Every field here is copied out of a stored evidence entry verbatim or left
 * `null`. Nothing is scored, ranked, weighted or preferred, and there is
 * deliberately no `strength`, `quality` or `kind` ordering: `user_confirmation`
 * beside `spreadsheet` is two different records of what a value rests on, and
 * saying which of them is better is the scientist's call, not this table's.
 *
 * `undescribable` is the honest arm for an entry this build cannot read as an
 * evidence object at all. It is KEPT AND COUNTED rather than dropped, the same
 * rule `RunCompare.findingTexts` applies to a finding it cannot describe — the
 * number of things recorded beside a value must never quietly shrink.
 */
export interface CompareSupport {
  /**
   * The identity used to compare the two SETS of support. Never rendered.
   *
   * Every undescribable entry shares one key on purpose: an entry this build
   * cannot read carries no distinguishing content, so the only honest claim is
   * how MANY there are, and the signature counts rather than distinguishes them.
   */
  key: string;
  /** The evidence `source_type`, verbatim, or `null` when it records none. */
  sourceType: string | null;
  sourceFile: string | null;
  locator: string | null;
  /** The derivation rule, for a `derivation` entry. A mechanism, not an approval. */
  rule: string | null;
  /** True for `user_confirmation` — the one evidence type minted for a human act. */
  confirmation: boolean;
  /** True when nothing in the entry could be read as a citation. */
  undescribable: boolean;
}

/**
 * WHAT THE SERVER RECORDED ABOUT A CONFLICT AT ONE ADDRESS ON ONE RUN.
 *
 * READ THE HEADER BEFORE ADDING A FIELD. This is not "these two runs disagree";
 * it is `GET .../conflicts?run=`'s finding that ONE run's own citations at ONE
 * address assert more than one distinct answer, plus the decision — if any — a
 * person recorded about it.
 *
 * THE COMPETING VALUES ARE NOT CARRIED HERE, and that is a boundary rather than
 * an omission. Choosing between them is `ConflictResolutionPanel`'s act on its own
 * surface with the record's version token; a read-only comparison that displayed
 * the candidates would be inviting a decision it cannot record. The server's own
 * `explanation` is carried because it is deterministic and quotes no value.
 */
export interface CompareConflict {
  distinctValueCount: number;
  evidenceCount: number;
  /** The server's own deterministic sentence. It quotes no value. */
  explanation: string;
  /** `absent` | `current` | `stale` | `deferred` — the server's own vocabulary. */
  resolutionState: string;
  resolved: boolean;
  resolutionStale: boolean;
  /** Part of this address's stored evidence could not be read. */
  unavailable: boolean;
  /** The recorded decision's outcome, or `null` when nobody has decided. */
  outcome: string | null;
}

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
  /** Every cited entry beside the value, described. Empty when absent. */
  support: CompareSupport[];
  /** The sorted support keys, joined. The EVIDENCE axis's set comparison. */
  supportSignature: string;
  /** How many of {@link support} this build could not read. */
  undescribableSupport: number;
  /**
   * WHERE THE CITATIONS SAY THE VALUE CAME FROM — `lib/provenance.ts`'s mirror,
   * computed from evidence the run view already carries. Empty when absent.
   *
   * `inherited` is added for an address this run reads from the record, which is
   * what the server's own describer does. Nothing else is added: `assistant` has
   * no producer in this build and no mapping can emit it.
   */
  origins: ProvenanceOrigin[];
  /** The headline origin by `ORIGIN_PRECEDENCE`, never by array position. */
  primaryOrigin: ProvenanceOrigin | null;
  /**
   * WHAT ESTABLISHES THE VALUE — the same mirror, and it can never say `resolved`.
   *
   * A recorded decision does not live in the citations this is computed from, so
   * `reviewStateFor` deliberately never returns `resolved`; {@link CompareRow.conflict}
   * is where a decision reaches this surface. Do not paper over the gap.
   */
  reviewState: ProvenanceReviewState | null;
  /** The server's recorded conflict at this address on this run, if any. */
  conflict: CompareConflict | null;
  /** False when `GET .../conflicts?run=` was not obtained for this run at all. */
  conflictsKnown: boolean;
}

/* ── the three relations, and the one category the row is rendered from ────── */

export type ValueRelation = 'equal' | 'differs' | 'one-absent' | 'both-absent' | 'incomparable';
export type ProvenanceRelation = 'not-applicable' | 'same' | 'differs';
export type EvidenceRelation = 'not-applicable' | 'same' | 'differs';
export type ReviewRelation = 'not-applicable' | 'same' | 'differs';

/**
 * WHETHER A RECORDED CONFLICT IS STORED AT THIS ADDRESS — a PRESENCE, not a
 * relation between the two runs, and the name says so.
 *
 * `unknown` is a real answer and is why this is not a boolean: the conflicts read
 * is a request, it can fail, and a row that silently reported `neither` in that
 * case would be asserting that nothing is stored when nothing was looked at.
 */
export type ConflictPresence = 'unknown' | 'neither' | 'one' | 'both';

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
 * then value, then review, then provenance, then evidence — narrowing from what
 * the run holds to what is recorded about it.
 *
 * `review` WAS INSERTED between value and provenance, and the insertion is a
 * decision rather than an appendix. What ESTABLISHES a value outranks where it
 * came from and what is counted beside it: two runs agreeing on a value where one
 * side is supported and the other is awaiting review is the more consequential
 * fact, and burying it under "different record-keeping" would understate it.
 *
 * A RECORDED CONFLICT IS NOT IN THIS PARTITION AT ALL — see the file header.
 */
export type CompareCategory =
  | 'same'
  | 'value'
  | 'absent-on-one'
  | 'review'
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
  review: ReviewRelation;
  /**
   * WHETHER A RECORDED CONFLICT IS STORED HERE, on either run.
   *
   * Read the file header before using this for anything. It is not a relation
   * between the two runs and it never sets {@link category}; it makes the row
   * LISTED and it is counted separately. `unknown` means the conflicts read was
   * not obtained, which is never rendered as "there is none".
   */
  conflict: ConflictPresence;
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
   *
   * A ROW CARRYING A RECORDED CONFLICT IS LISTED EVEN WHEN THE TWO RUNS AGREE,
   * and that is the second reason "listed" and "differs" had to stop being one
   * word. An address where citations disagree with themselves and nobody has
   * decided is exactly what a reader must not have hidden behind a filter whose
   * label says "the same on both runs" — and it IS the same on both runs, so the
   * filter is not lying either. {@link CompareTally.conflictedAgreeing} is how
   * the surface says why such a row is on screen.
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
  /** The breakdown. These FIVE sum to {@link differing}, by construction. */
  value: number;
  absentOnOne: number;
  review: number;
  provenance: number;
  evidence: number;
  /** Rows that are neither `differing` nor `agreeing`. Counted on its own. */
  incomparable: number;
  /** Agreeing rows where NEITHER run records anything. Part of `agreeing`. */
  bothAbsent: number;
  /**
   * Rows where the server recorded a conflict on at least one run.
   *
   * A SIXTH NUMBER THAT IS IN NEITHER OF THE OTHER TWO GROUPS, and deliberately
   * does not sum with anything. A recorded conflict is not a difference between
   * the runs, so adding it to `differing` would put a disagreement on screen that
   * nobody observed — the identical mistake `incomparable` is excluded to avoid.
   * It is not an agreement either. It is its own fact and it is stated as one.
   */
  conflicted: number;
  /** How many of {@link conflicted} are rows the three axes call AGREEING. */
  conflictedAgreeing: number;
  /** Rows still awaiting a decision — `absent`, `stale` or `deferred`. */
  conflictedUnresolved: number;
  /** True when the conflicts read was not obtained for at least one run. */
  conflictsUnknown: boolean;
}

/**
 * ONE `block:` ADDRESS THAT IS NOT COMPARED, and what can honestly be said about
 * it anyway.
 *
 * The exclusion is the same boundary `runOverrides.overrideRows` draws and it is
 * KEPT: a block payload is a whole object or list, this table has no honest
 * one-line rendering for one, and a diff of two objects it cannot show is a claim
 * the reader cannot check. Deep-equalling the two payloads into `equal`/`differs`
 * was considered and refused for exactly that reason — the verdict would be
 * unverifiable on the screen that stated it.
 *
 * WHAT IS STATED INSTEAD IS KEY PRESENCE, which is a different kind of claim. "Run
 * 1's `measurement` block carries a `series` key and Run 2's does not" is checkable
 * by opening either run, says nothing about what is inside either key, and is the
 * fact a reader most often opened the comparison to find. No value, no count of
 * anything below the top level, and no ordering.
 */
export interface CompareBlock {
  /** The block name, without the `block:` prefix. */
  name: string;
  /** True when this run's resolution carries the address at all. */
  presentOnA: boolean;
  presentOnB: boolean;
  /** The top-level keys of each side's payload, sorted. Empty when unnamed. */
  keysA: string[];
  keysB: string[];
  /** Keys on exactly one side. Never a statement about the values under them. */
  onlyA: string[];
  onlyB: string[];
  /**
   * True when a side carries the address but its payload is not an object whose
   * keys can be named — a list, a scalar, or nothing. Stated, never guessed past.
   */
  unnamedA: boolean;
  unnamedB: boolean;
}

export interface RunComparison {
  groups: CompareGroup[];
  tally: CompareTally;
  /** `block:` addresses, NOT compared, with what can be said about them anyway. */
  blocks: CompareBlock[];
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

/**
 * ONE STORED EVIDENCE ENTRY, DESCRIBED. Copies four strings and asserts nothing.
 *
 * An entry that yields none of the four is `undescribable` — not "empty", and not
 * dropped. Stored documents are untrusted input everywhere else in this package,
 * and an element of `evidence[]` is typed `unknown` for that reason.
 */
export function describeSupport(entry: unknown): CompareSupport {
  const blank: CompareSupport = {
    key: 'undescribable',
    sourceType: null,
    sourceFile: null,
    locator: null,
    rule: null,
    confirmation: false,
    undescribable: true,
  };
  if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) return blank;
  const rec = entry as Record<string, unknown>;
  const str = (k: string): string | null => {
    const v = rec[k];
    return typeof v === 'string' && v.trim() !== '' ? v.trim() : null;
  };
  const sourceType = str('source_type');
  const sourceFile = str('source_file');
  const locator = str('locator');
  const rule = str('rule');
  if (sourceType === null && sourceFile === null && locator === null && rule === null) {
    return blank;
  }
  return {
    // `\u0001` is a separator none of the four can contain after trimming, so two
    // entries cannot collide by concatenation.
    key: [sourceType ?? '', sourceFile ?? '', locator ?? '', rule ?? ''].join('\u0001'),
    sourceType,
    sourceFile,
    locator,
    rule,
    confirmation: sourceType === 'user_confirmation',
    undescribable: false,
  };
}

interface SupportRead {
  support: CompareSupport[];
  signature: string;
  undescribable: number;
}

function supportOf(payload: unknown): SupportRead {
  const raw =
    payload !== null && typeof payload === 'object'
      ? (payload as { evidence?: unknown }).evidence
      : undefined;
  if (!Array.isArray(raw)) return { support: [], signature: '', undescribable: 0 };
  const support = raw.map(describeSupport);
  return {
    support,
    // SORTED, so that two runs citing the same two sources in a different stored
    // order are not reported as differing. It is an array and not a Set: two
    // identical citations are two citations, and collapsing them would make a
    // count and a signature disagree about the same evidence list.
    signature: [...support.map((entry) => entry.key)].sort().join('\u0002'),
    undescribable: support.filter((entry) => entry.undescribable).length,
  };
}

/**
 * THE TWO PROVENANCE DIMENSIONS FOR ONE SIDE — `lib/provenance.ts`'s mirror.
 *
 * That module's header is the licence for this: a surface that ALREADY holds an
 * evidence entry may show the same two dimensions without a second request. It is
 * a display mirror and never a second source of truth, and `provenance.test.ts`
 * already pins the two vocabularies against the Python source.
 *
 * `inherited` is added as an extra origin exactly where the server's own describer
 * adds it (`provenance._describe`, `extra_origins=(ORIGIN_INHERITED,)`). Nothing
 * else is: `assistant` has no producer in this build.
 *
 * BOTH DIMENSIONS ARE READ FROM THE ENTRIES THE SERVER WOULD HAVE READ, and that
 * qualification is not pedantry — it was measured to change an answer.
 * `serialize._readable_evidence` drops every element of a stored `evidence` list
 * that is not an evidence OBJECT and reports the payload as `unavailable`, and
 * `provenance.review_state` then DEMOTES it: "A PARTIALLY UNREADABLE PAYLOAD IS
 * NEVER SUPPORT" (`provenance.py:425-441`), whose own comment records the shipped
 * defect it closed — a green Supported chip painted directly beneath a row already
 * marked unavailable.
 *
 * `lib/provenance.ts`'s `reviewStateFor` takes no `unavailable` parameter, so the
 * mirror cannot express that arm and, handed the raw list, answered `supported`
 * for `[{…}, 7, null]` where the server answers `needs_review`. Rather than a
 * second, differently-wrong rule, the SAME split is applied here first and the
 * mirror is handed the readable half — so `supported` requires a readable
 * citation, exactly as it does on the server, and an unreadable entry beside a
 * readable one demotes exactly as it does there. Conflict still outranks the
 * demotion, which is the server's precedence and not a choice made here.
 *
 * WHAT THIS DOES NOT TOUCH: {@link CompareSide.evidenceCount}. It counts what is
 * STORED, and {@link CompareSide.undescribableSupport} says how much of it this
 * build could not describe. The server's own `evidence_count` is the readable
 * count; the two are different numbers answering different questions, and the
 * rule here is that the number of things recorded beside a value never quietly
 * shrinks.
 */
function provenanceOf(
  payload: unknown,
  present: boolean,
  inherited: boolean,
): { origins: ProvenanceOrigin[]; primary: ProvenanceOrigin | null; review: ProvenanceReviewState | null } {
  if (!present) return { origins: [], primary: null, review: null };
  const env =
    payload !== null && typeof payload === 'object'
      ? (payload as { status?: unknown; evidence?: unknown })
      : {};
  const stored: unknown[] = Array.isArray(env.evidence) ? (env.evidence as unknown[]) : [];
  // `isinstance(e, dict)` in `serialize._readable_evidence`, spelt in JavaScript.
  // An array element deserialises to a Python list and is dropped there, so it is
  // dropped here too.
  const readable = stored.filter(
    (entry): entry is FieldEvidence =>
      entry !== null && typeof entry === 'object' && !Array.isArray(entry),
  );
  // TRUE FOR A PARTIALLY READABLE PAYLOAD, which is the server's `unavailable`.
  // An empty list is NOT unavailable — a field legitimately carries no citation,
  // and calling that unreadable would cry wolf on every uncited entry.
  const unreadable = readable.length !== stored.length;
  const found = new Set<ProvenanceOrigin>(originsFromEvidence(readable));
  if (inherited) found.add('inherited');
  // `unknown` when nothing stored says where the value came from — the server's own
  // answer, and a statement about the record rather than a plausible default.
  const origins: ProvenanceOrigin[] =
    found.size === 0 ? ['unknown'] : PROVENANCE_ORIGINS.filter((o) => found.has(o)).sort();
  const mirrored = reviewStateFor({
    status: typeof env.status === 'string' ? env.status : null,
    evidence: readable,
  });
  return {
    origins,
    primary: primaryOrigin(origins),
    // The server reads `resolution_state` only under the conflict arm and reads
    // `unavailable` only below it; the order below is that order.
    review: mirrored === 'conflict' ? 'conflict' : unreadable ? 'needs_review' : mirrored,
  };
}

/** One side of a RUN-LEVEL field row. There is no INHERITANCE question here. */
function ownSide(
  env: ApiRunFieldEnvelope | undefined,
  conflicts: ConflictIndex,
  path: string,
): CompareSide {
  const value = env === undefined || env === null ? null : (env.value ?? null);
  const present = value !== null && value !== undefined;
  const support = supportOf(env);
  const prov = provenanceOf(env, present, false);
  return {
    origin: present ? 'own' : 'absent',
    present,
    text: valueText(value),
    unrenderable: isUnrenderableValue(value),
    value: present ? value : null,
    recordText: null,
    status: env === undefined ? null : envelopeStatus(env),
    evidenceCount: env === undefined ? null : envelopeEvidenceCount(env),
    support: support.support,
    supportSignature: support.signature,
    undescribableSupport: support.undescribable,
    origins: prov.origins,
    primaryOrigin: prov.primary,
    reviewState: prov.review,
    conflict: conflicts.at(path),
    conflictsKnown: conflicts.known,
  };
}

/** One side of a RECORD-LEVEL row, read entirely from the server's resolution. */
function inheritedSide(run: ApiRunView, address: string, conflicts: ConflictIndex): CompareSide {
  const resolution = run.inherited?.[address];
  const path = address.slice(FIELD_ADDRESS_PREFIX.length);
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
      support: [],
      supportSignature: '',
      undescribableSupport: 0,
      origins: [],
      primaryOrigin: null,
      reviewState: null,
      conflict: conflicts.at(path),
      conflictsKnown: conflicts.known,
    };
  }
  const value = payloadValue(resolution.payload);
  const present = value !== null && value !== undefined;
  const support = supportOf(resolution.payload);
  const prov = provenanceOf(resolution.payload, present, resolution.state !== 'overridden');
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
    support: support.support,
    supportSignature: support.signature,
    undescribableSupport: support.undescribable,
    origins: prov.origins,
    primaryOrigin: prov.primary,
    reviewState: prov.review,
    conflict: conflicts.at(path),
    conflictsKnown: conflicts.known,
  };
}

/* ── the recorded conflicts one run carries ────────────────────────────────── */

/**
 * `GET .../conflicts?run=` FOR ONE RUN, INDEXED BY THE ADDRESS IT USES.
 *
 * THE KEY IS THE BARE DOTTED PATH, not the `field:`-namespaced address. That is
 * the server's own key here: `conflict_resolution.conflict_report` walks
 * `serialize.evidence_trail_from_draft`, whose `path` is the draft's own key, and
 * `provenance` does the same. Prefixing would silently index nothing.
 */
export interface ConflictIndex {
  /** False when the read was not obtained. Never rendered as "there are none". */
  known: boolean;
  at(path: string): CompareConflict | null;
}

const NO_CONFLICTS: ConflictIndex = { known: false, at: () => null };

/**
 * Index one run's conflicts. `undefined` means the read was not obtained, which is
 * a different answer from an empty list and is carried as `known: false`.
 */
export function conflictIndex(conflicts: readonly ApiConflict[] | undefined): ConflictIndex {
  if (conflicts === undefined) return NO_CONFLICTS;
  const byAddress = new Map<string, CompareConflict>();
  for (const entry of conflicts) {
    if (entry === null || typeof entry !== 'object') continue;
    byAddress.set(entry.address, {
      distinctValueCount: entry.distinct_value_count,
      evidenceCount: entry.evidence_count,
      explanation: entry.explanation,
      resolutionState: entry.resolution_state,
      resolved: entry.resolved === true,
      resolutionStale: entry.resolution_stale === true,
      unavailable: entry.unavailable === true,
      outcome: entry.resolution?.outcome ?? null,
    });
  }
  return { known: true, at: (path) => byAddress.get(path) ?? null };
}

/**
 * THE RECORD CONTEXT A COMPARISON IS READ AGAINST — one entry per run, and every
 * field of it OPTIONAL because every one of them is a request that can fail.
 *
 * WHAT IS NOT HERE, NAMED RATHER THAN LEFT TO BE DISCOVERED:
 *
 *   · RECORD-SCOPE CONFLICTS. `GET .../conflicts?run=` describes a run's OWN
 *     fields; a conflict at an address the run INHERITS is stored once, at the
 *     record, and is decided there. It is therefore identical for both runs and
 *     cannot distinguish them, which is why this surface does not read it — and
 *     why it must not report "no conflict" about an inherited address. The panel
 *     says so on screen rather than leaving the gap silent.
 *   · A PROVENANCE READ. `GET .../provenance?run=` would answer the origin and
 *     review dimensions, and it is not called: the run view already carries the
 *     citations both dimensions are computed from, and `lib/provenance.ts` exists
 *     precisely so a surface holding them can mirror the server's rule without a
 *     second request. The mirror cannot report `resolved`, which is the one thing
 *     the conflicts read supplies.
 */
export interface CompareContext {
  a?: { conflicts?: readonly ApiConflict[] };
  b?: { conflicts?: readonly ApiConflict[] };
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

/**
 * WHERE THE TWO VALUES CAME FROM — inheritance state AND cited origins.
 *
 * WIDENED, AND THE RUN-FIELD ARM CHANGED FROM `not-applicable` TO A REAL ANSWER.
 * It used to short-circuit on scope, because a run-level field has no inheritance
 * and inheritance was the only thing this axis compared. Origins are not about
 * inheritance: one run's temperature can be a person's answer and the other's can
 * be read out of a spreadsheet, at the same address, with the same value — which
 * is a difference in source and was previously reported as no difference at all.
 */
function provenanceRelation(
  scope: 'run-field' | 'record-level',
  a: CompareSide,
  b: CompareSide,
): ProvenanceRelation {
  /*
   * PROVENANCE IS ONLY A QUESTION WHERE BOTH RUNS HAVE SOMETHING. With one side
   * absent, "these came from different places" would be a second reading of the
   * same absence the value relation already reports — and it would double-count
   * one fact as two differences.
   */
  if (!a.present || !b.present) return 'not-applicable';
  if (scope === 'record-level' && a.origin !== b.origin) return 'differs';
  return a.origins.join('\u0001') === b.origins.join('\u0001') ? 'same' : 'differs';
}

/**
 * WHAT IS RECORDED BESIDE THE VALUE — status, how many entries, and WHICH.
 *
 * The third comparison is the widening. Two runs can carry one citation each,
 * with the same status, where one is a person's own confirmation and the other is
 * a row of a spreadsheet; the count and the status are identical and the record
 * of what the value rests on is not. `supportSignature` is a sorted set of
 * described entries, so stored order never manufactures a difference.
 *
 * IT IS STILL A COMPARISON AND NEVER A VERDICT. Nothing here or downstream ranks
 * a `user_confirmation` above a `spreadsheet`, prefers more entries to fewer, or
 * calls either side better supported.
 */
function evidenceRelation(a: CompareSide, b: CompareSide): EvidenceRelation {
  if (!a.present || !b.present) return 'not-applicable';
  if (
    a.status === b.status &&
    a.evidenceCount === b.evidenceCount &&
    a.supportSignature === b.supportSignature
  ) {
    return 'same';
  }
  return 'differs';
}

/** What, if anything, ESTABLISHES each value — the provenance mirror's answer. */
function reviewRelation(a: CompareSide, b: CompareSide): ReviewRelation {
  // Same rule as provenance: with one side absent there is nothing to establish,
  // and the value relation has already reported the absence.
  if (!a.present || !b.present) return 'not-applicable';
  return a.reviewState === b.reviewState ? 'same' : 'differs';
}

/**
 * IS A RECORDED CONFLICT STORED HERE — and was anybody in a position to say?
 *
 * `unknown` whenever EITHER read is missing, deliberately: with one run's
 * conflicts unread, "one of them has a conflict" is a claim about a set that was
 * never looked at, and "neither" is worse.
 */
function conflictPresence(a: CompareSide, b: CompareSide): ConflictPresence {
  if (!a.conflictsKnown || !b.conflictsKnown) return 'unknown';
  const count = (a.conflict !== null ? 1 : 0) + (b.conflict !== null ? 1 : 0);
  if (count === 0) return 'neither';
  return count === 1 ? 'one' : 'both';
}

function categoryOf(
  value: ValueRelation,
  review: ReviewRelation,
  provenance: ProvenanceRelation,
  evidence: EvidenceRelation,
): CompareCategory {
  if (value === 'incomparable') return 'incomparable';
  if (value === 'one-absent') return 'absent-on-one';
  if (value === 'differs') return 'value';
  if (review === 'differs') return 'review';
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
  const review = reviewRelation(a, b);
  const conflict = conflictPresence(a, b);
  const category = categoryOf(value, review, provenance, evidence);
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
    review,
    conflict,
    category,
    // A RECORDED CONFLICT LISTS THE ROW WITHOUT MAKING IT A DIFFERENCE. See the
    // field's own doc comment and the file header.
    listed: category !== 'same' || conflict === 'one' || conflict === 'both',
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
export function buildRunComparison(
  a: ApiRunView,
  b: ApiRunView,
  context: CompareContext = {},
): RunComparison {
  const rows: CompareRow[] = [];
  const conflictsA = conflictIndex(context.a?.conflicts);
  const conflictsB = conflictIndex(context.b?.conflicts);

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
        ownSide(a.fields?.[path], conflictsA, path),
        ownSide(b.fields?.[path], conflictsB, path),
      ),
    );
  }

  const addresses = new Set<string>();
  const blockNames = new Set<string>();
  for (const run of [a, b]) {
    for (const address of Object.keys(run.inherited ?? {})) {
      if (address.startsWith(BLOCK_ADDRESS_PREFIX)) {
        blockNames.add(address.slice(BLOCK_ADDRESS_PREFIX.length));
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
        inheritedSide(a, address, conflictsA),
        inheritedSide(b, address, conflictsB),
      ),
    );
  }

  const blocks = [...blockNames]
    .sort((x, y) => x.localeCompare(y))
    .map((name) => describeBlock(name, a, b));

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

  return { groups, tally: tallyOf(rows), blocks };
}

/* ── the blocks this table does not compare ────────────────────────────────── */

/** The top-level keys of one side's block payload, or `null` when it has none. */
function blockKeys(run: ApiRunView, address: string): string[] | null {
  const resolution = run.inherited?.[address];
  if (resolution === undefined) return null;
  const payload = resolution.payload;
  // A LIST OR A SCALAR HAS NO KEYS TO NAME, and `Object.keys` on either would
  // produce indices or nothing — a shape claim the payload never made.
  if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) return null;
  return Object.keys(payload as Record<string, unknown>).sort((x, y) => x.localeCompare(y));
}

function describeBlock(name: string, a: ApiRunView, b: ApiRunView): CompareBlock {
  const address = `${BLOCK_ADDRESS_PREFIX}${name}`;
  const presentOnA = a.inherited?.[address] !== undefined;
  const presentOnB = b.inherited?.[address] !== undefined;
  const rawA = blockKeys(a, address);
  const rawB = blockKeys(b, address);
  const keysA = rawA ?? [];
  const keysB = rawB ?? [];
  const setA = new Set(keysA);
  const setB = new Set(keysB);
  return {
    name,
    presentOnA,
    presentOnB,
    keysA,
    keysB,
    // ONLY MEANINGFUL WHERE BOTH SIDES COULD BE NAMED. With one payload unnamed,
    // "only Run 1 carries `series`" would be read off a comparison with nothing on
    // the other side, and would be a claim about a shape nobody read.
    onlyA: rawA !== null && rawB !== null ? keysA.filter((k) => !setB.has(k)) : [],
    onlyB: rawA !== null && rawB !== null ? keysB.filter((k) => !setA.has(k)) : [],
    unnamedA: presentOnA && rawA === null,
    unnamedB: presentOnB && rawB === null,
  };
}

function tallyOf(rows: CompareRow[]): CompareTally {
  const count = (category: CompareCategory) =>
    rows.filter((row) => row.category === category).length;
  const incomparable = count('incomparable');
  /*
   * STRICT, AND NO LONGER DERIVED FROM `listed`.
   *
   * It used to read `row.listed && row.category !== 'incomparable'`, which was
   * exactly right while `listed` meant "not the same". It stopped being right the
   * moment a recorded conflict could list an agreeing row: that row would have
   * been counted as a difference, which is the precise mistake `incomparable`'s
   * exclusion exists to prevent, arriving through a second door. Stated over the
   * category directly so the two can never drift again.
   */
  const differing = rows.filter(
    (row) => row.category !== 'same' && row.category !== 'incomparable',
  ).length;
  const conflicted = rows.filter(
    (row) => row.conflict === 'one' || row.conflict === 'both',
  );
  const unresolvedConflict = (side: CompareSide) =>
    side.conflict !== null && side.conflict.resolutionState !== 'current';
  return {
    compared: rows.length,
    differing,
    agreeing: rows.length - differing - incomparable,
    value: count('value'),
    absentOnOne: count('absent-on-one'),
    review: count('review'),
    provenance: count('provenance'),
    evidence: count('evidence'),
    incomparable,
    bothAbsent: rows.filter((row) => row.value === 'both-absent').length,
    conflicted: conflicted.length,
    conflictedAgreeing: conflicted.filter((row) => row.category === 'same').length,
    conflictedUnresolved: conflicted.filter(
      (row) => unresolvedConflict(row.a) || unresolvedConflict(row.b),
    ).length,
    conflictsUnknown: rows.some((row) => row.conflict === 'unknown'),
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
    case 'review':
      return 'Same value, different review state';
    case 'provenance':
      return 'Same value, different source';
    case 'evidence':
      return 'Same value, different record-keeping';
    case 'incomparable':
      return 'Not compared here';
  }
}

/**
 * ONE SUPPORT ENTRY AS ONE LINE. Describes; does not rank.
 *
 * The words are the ones `EvidenceRow` and `lib/provenance.ts` already use, so a
 * reader meets one vocabulary for citations across the product. An entry this
 * build cannot read says exactly that.
 */
export function supportWord(entry: CompareSupport): string {
  if (entry.undescribable) return 'an entry this build could not read';
  const head = entry.confirmation
    ? 'answered in this application'
    : entry.sourceType !== null
      ? entry.sourceType.replace(/_/g, ' ')
      : 'a citation naming no source kind';
  const tail: string[] = [];
  if (entry.sourceFile !== null) tail.push(entry.sourceFile);
  if (entry.locator !== null) tail.push(entry.locator);
  if (entry.rule !== null) tail.push(`rule ${entry.rule}`);
  return tail.length === 0 ? head : `${head} — ${tail.join(' · ')}`;
}

/** The origin words, from `lib/provenance.ts`. Never a second vocabulary. */
export function originsWord(side: CompareSide): string {
  if (side.origins.length === 0) return 'no citation recorded';
  return side.origins.map((origin) => ORIGIN_LABEL[origin]).join(', ');
}

/** The review-state word, from `lib/provenance.ts`. */
export function reviewWord(state: ProvenanceReviewState | null): string {
  return state === null ? 'nothing recorded' : REVIEW_STATE_LABEL[state];
}

/**
 * A RECORDED CONFLICT, IN WORDS — and none of them is "these runs disagree".
 *
 * The sentence is about ONE run's own citations at ONE address. It never names
 * the other run, never quotes a competing value, and never says which answer is
 * right: this surface is read-only and the decision belongs on the surface that
 * can record one.
 */
export function conflictWord(conflict: CompareConflict): string {
  const head = `${conflict.distinctValueCount} different answers are cited here, across ${conflict.evidenceCount} ${conflict.evidenceCount === 1 ? 'entry' : 'entries'}`;
  switch (conflict.resolutionState) {
    case 'current':
      return `${head}. A person recorded which one they stand behind, and that decision still covers exactly these answers.`;
    case 'stale':
      return `${head}. A decision was recorded over a different set of answers, so it no longer covers these.`;
    case 'deferred':
      return `${head}. A person looked and recorded that they were not deciding yet.`;
    default:
      return `${head}. No decision is recorded.`;
  }
}

/** How many evidence entries a side records, as words. Counted, never judged. */
export function evidenceWord(side: CompareSide): string {
  if (side.evidenceCount === null) return 'no evidence list recorded';
  if (side.evidenceCount === 0) return 'no evidence entries';
  return `${side.evidenceCount} evidence ${side.evidenceCount === 1 ? 'entry' : 'entries'}`;
}
