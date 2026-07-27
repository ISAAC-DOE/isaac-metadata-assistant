/*
 * Display-only titles for graph-derived labels (P36V PR2 slice A).
 *
 * Project memory's concept labels are authored for a knowledge graph, not for a
 * reading surface: they routinely carry a trailing code qualifier
 * (`AI scientific consistency review (review.py NoOpReviewer)`). This module
 * derives a READABLE title for the one place a human reads it first — the
 * Concepts master row and the detail pane heading.
 *
 * Three rules govern everything here:
 *
 *   1. PRESENTATION ONLY. Nothing in this module mutates a label, and no caller
 *      may store its output. The raw label stays in state, stays searchable, and
 *      stays REACHABLE wherever a derived title is shown — verbatim in the
 *      Concepts detail pane's Technical Details disclosure, and on `title` for
 *      the Sources tab's related-concept rows, which have no detail pane of
 *      their own — so the derivation is lossless from the reader's point of view.
 *   2. DETERMINISTIC. Same input, same output, no locale, no `Intl`, no data.
 *   3. LOSS-AVERSE. A trailing group is dropped ONLY when every word inside it is
 *      a code token. If the group mixes an identifier with prose, it is KEPT —
 *      leaving an identifier on screen is strictly better than deleting meaning.
 *
 * Casing comes from `lib/labels.ts::titleCase`, which is the single source of
 * truth for "Title Case, but never re-case a technical token". Neither
 * `titleCase()` nor `isTechnical()` is modified here; both are imported.
 */
import { isTechnical, titleCase } from './labels';

const OPENERS = new Set(['(', '[', '{']);
const CLOSERS = new Set([')', ']', '}']);
/** Which opener closes which closer — a mismatched pair is not a group. */
const PAIR: Record<string, string> = { ')': '(', ']': '[', '}': '{' };

/**
 * Structural punctuation that only ever appears inside code: a brace/bracket
 * list, a generic parameter, an assignment, an enum separator. Checked AFTER the
 * token's outer wrappers and trailing sentence punctuation are trimmed, so a
 * prose word followed by a comma (`deterministic,`) is NOT caught by it.
 */
const STRUCTURAL = /[[\]{}<>,;=|]/;
/** `NoOpReviewer`, `titleCase`, `buildGraph` — an interior capital marks a code identifier. */
const CAMEL_CASE = /^[A-Za-z][a-z0-9]*(?:[A-Z][a-z0-9]*)+$/;
/** A word made only of letters — `intake`, `Graphify`, `XANES`, `NoOpReviewer`. */
const PLAIN_WORD = /^[A-Za-z]+$/;
/** A bare connector (`+`, `·`, `—`): neither code nor prose, so it decides nothing. */
const CONNECTOR_ONLY = /^[^A-Za-z0-9]+$/;

export interface TrailingGroup {
  /** Everything before the group, right-trimmed. Never empty. */
  head: string;
  /** The opening delimiter actually used — `(`, `[` or `{`. */
  open: string;
  /** The group's contents, delimiters excluded, exactly as written. */
  inner: string;
  /** The matching closing delimiter. */
  close: string;
}

/**
 * Split a label into `head` + a balanced trailing `(…)` / `[…]` / `{…}` group.
 *
 * Scans right-to-left with depth counting so a nested group is handled as one
 * unit (`Draft envelope format {value,status,evidence[]}` → inner
 * `value,status,evidence[]`). Returns `null` — meaning "no trailing group, treat
 * the whole label as the head" — when the label does not end in a closer, when
 * the delimiters are unbalanced or mismatched, or when the group IS the whole
 * label (there would be no head left to show).
 */
export function splitTrailingGroup(label: string): TrailingGroup | null {
  const s = label.trimEnd();
  if (s.length < 2) return null;
  const close = s[s.length - 1];
  if (!CLOSERS.has(close)) return null;

  let depth = 0;
  for (let i = s.length - 1; i >= 0; i -= 1) {
    const ch = s[i];
    if (CLOSERS.has(ch)) {
      depth += 1;
    } else if (OPENERS.has(ch)) {
      depth -= 1;
      if (depth === 0) {
        if (PAIR[close] !== ch) return null; // e.g. "Foo (bar]" — not a group
        const head = s.slice(0, i).trimEnd();
        if (head === '') return null; // the label is nothing but the group
        return { head, open: ch, inner: s.slice(i + 1, s.length - 1), close };
      }
    }
  }
  return null; // unbalanced — an opener is missing
}

/**
 * Is one word inside a trailing group a CODE token (safe to hide) rather than
 * prose (never safe to hide)?
 *
 * `isTechnical()` is the authority for the structural forms — a path, a dotted
 * path, `snake_case`, a version, a hash. It ALSO returns true for curated
 * vocabulary words (`Graphify`, `spreadsheet`, `derivation`) because those must
 * never be re-cased; that is the right answer for CASING and the wrong answer
 * for "safe to delete from the visible title". So a plain alphabetic word is
 * treated as code only when its own shape says so: an ALLCAPS acronym (`XANES`)
 * or a CamelCase identifier (`NoOpReviewer`). Every other plain word — including
 * a curated one — counts as prose and protects its group.
 */
export function isCodeToken(raw: string): boolean {
  const token = raw.replace(/^[([{<'"]+/, '').replace(/[)\]}>,;:.!?'"]+$/, '');
  if (token === '') return false;
  if (PLAIN_WORD.test(token)) {
    const allCaps = token.length > 1 && token === token.toUpperCase();
    return allCaps || CAMEL_CASE.test(token);
  }
  return isTechnical(token) || STRUCTURAL.test(token);
}

/**
 * Does a trailing group contain code and nothing but code?
 *
 * At least one code token must be present, no prose word may be, and bare
 * connectors abstain. An empty group (`Foo ()`) carries no content at all, so
 * there is nothing to lose by dropping it.
 */
export function isCodeOnlyGroup(inner: string): boolean {
  const tokens = inner.split(/\s+/).filter((t) => t.length > 0);
  if (tokens.length === 0) return true;
  let code = 0;
  for (const token of tokens) {
    if (CONNECTOR_ONLY.test(token)) continue;
    if (!isCodeToken(token)) return false;
    code += 1;
  }
  return code > 0;
}

/**
 * The readable display title for a project-memory concept label.
 *
 * `AI scientific consistency review (review.py NoOpReviewer)`
 *   → `AI Scientific Consistency Review`      (code-only group dropped)
 * `Accepted artifact types (XANES intake)`
 *   → `Accepted Artifact Types (XANES intake)` (group mixes code with prose — KEPT)
 *
 * A KEPT group is re-emitted exactly as authored, delimiters and casing
 * included: its contents are prose the author wrote, and re-casing prose that
 * sits beside an identifier would be a second guess on top of the first.
 * Technical tokens in the head survive verbatim through `titleCase()`.
 */
export function conceptDisplayTitle(label: string): string {
  const raw = label.trim();
  if (raw === '') return '';
  const group = splitTrailingGroup(raw);
  if (!group) return titleCase(raw);
  if (isCodeOnlyGroup(group.inner)) return titleCase(group.head);
  return `${titleCase(group.head)} ${group.open}${group.inner}${group.close}`;
}

/* ---------------------------------------------------------------------------
 * Relationship-type display labels (P36V PR2 slice B).
 *
 * Graph relation values are a CLOSED set in the served projection. Measured
 * against the committed snapshot
 * (`apps/api/isaac_api/data/memory-snapshot.json` → every
 * `file_detail[*].related.files[*].relation`) there are EXACTLY five, and every
 * occurrence is one of them:
 *
 *   references 389 · imports 382 · calls 160 · imports_from 69 · shares_data_with 2
 *
 * Because the set is closed and enumerable, each member gets an EXPLICIT,
 * hand-checked display label below. That is the whole reason humanising these is
 * safe while humanising cluster names is not: a cluster name is arbitrary data
 * (104 distinct values in the same snapshot, including `SHE_work_function_eV`,
 * `test_export.py` and `record_id`), so a mechanical snake_case → Title Case
 * rule would fabricate "She Work Function Ev" and "Test Export.py". Cluster
 * names therefore render VERBATIM everywhere; only this closed five-value
 * vocabulary is relabelled.
 *
 * A value that is NOT in the map passes through UNCHANGED — never guessed, never
 * mechanically re-cased. `relates_to` (the concept↔concept relation carried by
 * the Concepts tab, which the snapshot's served concept payloads do not
 * populate at all) is exactly such a value: its vocabulary was never measured,
 * so it is displayed as the backend wrote it.
 * ------------------------------------------------------------------------- */

/**
 * The five relation values present in the served projection, each with its
 * hand-checked display label. Exhaustive for this payload by measurement — and
 * `relationDisplayLabel` degrades to verbatim for anything else.
 */
/* `Object.freeze`, not only `Readonly<…>`: the type annotation is erased at
 * runtime, so a stray `RELATION_DISPLAY_LABELS.calls = '…'` from any caller
 * would have silently rewritten the shared vocabulary — and the immutability
 * test could never have caught it. Frozen, that write is a no-op (and throws in
 * strict-mode modules, which every ES module is). */
export const RELATION_DISPLAY_LABELS: Readonly<Record<string, string>> = Object.freeze({
  references: 'References',
  imports: 'Imports',
  calls: 'Calls',
  imports_from: 'Imports From',
  shares_data_with: 'Shares Data With',
});

/** A `Map`, not a bare object lookup: `labels['constructor']` on a plain object
 *  resolves up the prototype chain and would return a function for a relation
 *  value called `constructor`. A Map has no inherited keys. */
const RELATION_LABEL_MAP: ReadonlyMap<string, string> = new Map(
  Object.entries(RELATION_DISPLAY_LABELS),
);

/**
 * The readable label for ONE relation value.
 *
 * In the map → its checked label. Not in the map → the value itself, verbatim.
 * Never mechanically transformed, never title-cased, never abbreviated: an
 * unmeasured vocabulary is not ours to rename.
 */
export function relationDisplayLabel(relation: string): string {
  return RELATION_LABEL_MAP.get(relation) ?? relation;
}

/** `relationDisplayLabel` over a list, order preserved, nothing de-duplicated
 *  (the caller's list is already the de-duplicated payload order). */
export function relationDisplayLabels(relations: readonly string[]): string[] {
  return relations.map(relationDisplayLabel);
}
