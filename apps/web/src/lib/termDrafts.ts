/*
 * A LOCAL IMPORT'S DRAFTS FILE, READ IN THE BROWSER.
 *
 * `isaac bundle propose-terms <bundle> --out <file.json>` writes, on the scientist's own
 * computer, every value in a bundle that is outside a fixed list, grouped by field and term,
 * with counts, file-and-place citations and — for a term the website would accept — a draft
 * in the website's own portal-payload format with an EMPTY description
 * (`apps/api/isaac_api/local_import/propose_terms.py`, `docs/local-import-bundle-contract.md` §24).
 *
 * The Schema Proposals page reads that file HERE, with the browser's own file reader. Nothing
 * in this module sends anything, and the page sends nothing either until the scientist saves
 * one draft as a proposal; that one proposal goes to the ISAAC server this page is talking to.
 *
 * WHAT IS READ, AND WHAT IS NEVER MADE UP:
 *   - the field, the term, the counts (`count`, `by_origin`), the citations (`file`, `locator`)
 *     and whether the file drafted the term, with its reason and problems when it did not;
 *   - runs: the file's own `runs` when it has one; otherwise the distinct `ref.run_id` of the
 *     citations, but only when EVERY citation names its run and none were left out. Anything
 *     else is "not stated" — an AI reading's citation points at a question, not a run;
 *   - the scientist's own words: a term's `scientist_notes` (strings, or objects with a `note`
 *     or `text`) when the file has them. The format at version 1 carries none, and then the
 *     page says the file has none rather than offering a sentence in their place;
 *   - the reviewer notes (`gate0`) are built from those facts only. A note the file has no fact
 *     for is left empty and named as missing; the description is ALWAYS left empty.
 */

import type { ApiSchemaProposalGate0, ApiSchemaProposalSourceInput } from './schemaProposals';

export const TERM_DRAFTS_FORMAT = 'isaac.term-proposal-drafts';
export const TERM_DRAFTS_FORMAT_VERSION = '1';
/** A drafts file is a short JSON report; anything far larger is not one. */
export const TERM_DRAFTS_MAX_BYTES = 5 * 1024 * 1024;

export type DraftOrigin = 'scientist_confirmed' | 'parser_reading' | 'ai_reading';

export const ORIGIN_LABEL: Record<DraftOrigin, string> = {
  scientist_confirmed: 'confirmed by you',
  parser_reading: 'parser reading',
  ai_reading: 'AI reading',
};

export interface DraftCitation {
  file: string | null;
  locator: string | null;
  origin: DraftOrigin | null;
}

export interface DraftProblem {
  field: string | null;
  code: string | null;
  message: string;
}

export interface LocalTermDraft {
  /** Stable within one file: the field and the term. */
  key: string;
  fieldPath: string;
  /** The portal's category key: the field path with `[]` dropped. */
  category: string;
  term: string;
  count: number | null;
  byOrigin: Record<DraftOrigin, number>;
  runs: number | null;
  missingFrom: string[];
  citations: DraftCitation[];
  citationsTotal: number | null;
  citationsTruncated: boolean;
  scientistNotes: string[];
  drafted: boolean;
  /** The file's own sentence for a term it did not draft. */
  reason: string | null;
  problems: DraftProblem[];
  /** The draft's portal body, for a drafted term (its description is empty by design). */
  body: { proposal_type: string; section: string; category: string; term: string } | null;
}

export interface LocalTermDraftsFile {
  bundleId: string | null;
  notice: string | null;
  drafts: LocalTermDraft[];
}

export type ParseResult = { ok: true; file: LocalTermDraftsFile } | { ok: false; message: string };

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === 'string' ? v : null);
const count = (v: unknown): number | null =>
  typeof v === 'number' && Number.isInteger(v) && v >= 0 ? v : null;

function origin(v: unknown): DraftOrigin | null {
  return v === 'scientist_confirmed' || v === 'parser_reading' || v === 'ai_reading' ? v : null;
}

function notesOf(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  const out: string[] = [];
  for (const n of raw) {
    const text = typeof n === 'string' ? n : isObj(n) ? str(n.note) ?? str(n.text) : null;
    if (text && text.trim()) out.push(text.trim());
  }
  return out;
}

function problemsOf(raw: unknown): DraftProblem[] {
  if (!Array.isArray(raw)) return [];
  const out: DraftProblem[] = [];
  for (const p of raw) {
    if (!isObj(p) || typeof p.message !== 'string') continue;
    out.push({ field: str(p.field), code: str(p.code), message: p.message });
  }
  return out;
}

function runsOf(term: Record<string, unknown>, citations: DraftCitation[], refs: unknown[], truncated: boolean): number | null {
  const own = count(term.runs);
  if (own !== null) return own;
  if (Array.isArray(term.run_ids)) return new Set(term.run_ids.filter((r) => typeof r === 'string')).size;
  if (truncated || citations.length === 0) return null;
  const ids = refs.map((r) => (isObj(r) ? str(r.run_id) : null));
  if (ids.some((id) => id === null)) return null;
  return new Set(ids).size;
}

/** Read the text of a drafts file. Never throws; a file that is not one says why. */
export function parseTermDraftsFile(text: string): ParseResult {
  let doc: unknown;
  try {
    doc = JSON.parse(text);
  } catch {
    return { ok: false, message: 'This file is not JSON, so it is not a drafts file from `isaac bundle propose-terms`.' };
  }
  if (!isObj(doc) || doc.format !== TERM_DRAFTS_FORMAT) {
    return {
      ok: false,
      message: `This JSON file is not a drafts file: its format is not ${TERM_DRAFTS_FORMAT}. Write one with \`isaac bundle propose-terms <bundle> --out <file.json>\`.`,
    };
  }
  if (doc.format_version !== TERM_DRAFTS_FORMAT_VERSION) {
    return {
      ok: false,
      message: `This drafts file is format version ${String(doc.format_version)}; this page reads version ${TERM_DRAFTS_FORMAT_VERSION}. Nothing was read from it.`,
    };
  }
  if (!Array.isArray(doc.fields)) {
    return { ok: false, message: 'This drafts file has no list of fields, so nothing could be read from it.' };
  }
  const drafts: LocalTermDraft[] = [];
  for (const field of doc.fields) {
    if (!isObj(field) || typeof field.field_path !== 'string' || !Array.isArray(field.terms)) continue;
    const fieldPath = field.field_path;
    for (const t of field.terms) {
      if (!isObj(t) || typeof t.term !== 'string') continue;
      const rawCitations = Array.isArray(t.citations) ? t.citations.filter(isObj) : [];
      const citations: DraftCitation[] = rawCitations.map((c) => ({
        file: str(c.file),
        locator: str(c.locator),
        origin: origin(c.origin),
      }));
      const truncated = t.citations_truncated === true;
      const by = isObj(t.by_origin) ? t.by_origin : {};
      const draft = isObj(t.draft) ? t.draft : {};
      const payload = isObj(draft.portal_payload) ? draft.portal_payload : null;
      const body = payload && isObj(payload.body) ? payload.body : null;
      const goodBody =
        body &&
        typeof body.proposal_type === 'string' &&
        typeof body.section === 'string' &&
        typeof body.category === 'string' &&
        typeof body.term === 'string'
          ? {
              proposal_type: body.proposal_type,
              section: body.section,
              category: body.category,
              term: body.term,
            }
          : null;
      drafts.push({
        key: `${fieldPath}\u0000${t.term}`,
        fieldPath,
        category: fieldPath.replace(/\[\]/g, ''),
        term: t.term,
        count: count(t.count),
        byOrigin: {
          scientist_confirmed: count(by.scientist_confirmed) ?? 0,
          parser_reading: count(by.parser_reading) ?? 0,
          ai_reading: count(by.ai_reading) ?? 0,
        },
        runs: runsOf(t, citations, rawCitations.map((c) => c.ref), truncated),
        missingFrom: Array.isArray(t.missing_from) ? t.missing_from.filter((m): m is string => typeof m === 'string') : [],
        citations,
        citationsTotal: count(t.citations_total),
        citationsTruncated: truncated,
        scientistNotes: notesOf(t.scientist_notes),
        drafted: draft.drafted === true && goodBody !== null,
        reason: str(draft.reason),
        problems: problemsOf(draft.problems),
        body: draft.drafted === true ? goodBody : null,
      });
    }
  }
  return { ok: true, file: { bundleId: str(doc.bundle_id), notice: str(doc.notice), drafts } };
}

const LIST_WORDS: Record<string, string> = { schema: "the ISAAC schema's list", portal: "the portal's list" };

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** "2 readings (2 AI readings) in 2 runs" — the file's counts, and nothing else. */
export function countsSentence(d: LocalTermDraft): string | null {
  if (d.count === null) return null;
  const parts = (Object.keys(ORIGIN_LABEL) as DraftOrigin[])
    .filter((o) => d.byOrigin[o] > 0)
    .map((o) => `${d.byOrigin[o]} ${ORIGIN_LABEL[o]}${o === 'scientist_confirmed' ? '' : d.byOrigin[o] === 1 ? '' : 's'}`);
  const runs = d.runs === null ? '' : ` in ${plural(d.runs, 'run', 'runs')}`;
  return `${plural(d.count, 'reading', 'readings')}${parts.length ? ` (${parts.join(', ')})` : ''}${runs}`;
}

export function citationLine(c: DraftCitation): string {
  const where = [c.file, c.locator].filter((x): x is string => !!x).join(' · ') || 'no file or place given';
  return c.origin ? `${where} (${ORIGIN_LABEL[c.origin]})` : where;
}

/**
 * The reviewer notes a draft's facts can fill, each within its limit, and the names of those
 * the file has no fact for. `flip_list` ("what would change") is never filled: the file does
 * not say it.
 */
export function gate0FromDraft(
  d: LocalTermDraft,
  bundleId: string | null,
  limits: { problem_max: number; examples_max: number; affected_records_estimate_max: number },
): { gate0: ApiSchemaProposalGate0; missing: (keyof ApiSchemaProposalGate0)[] } {
  const gate0: ApiSchemaProposalGate0 = {};
  const missing: (keyof ApiSchemaProposalGate0)[] = [];
  const lists = d.missingFrom.map((m) => LIST_WORDS[m] ?? m);
  if (d.count !== null) {
    const where = bundleId ? `the local import ${bundleId}` : 'a local import';
    const problem =
      `"${d.term}" was read ${plural(d.count, 'time', 'times')} for ${d.fieldPath} in ${where}` +
      (lists.length ? `, and it is not on ${lists.join(' or ')}.` : '.');
    if (problem.length <= limits.problem_max) gate0.problem = problem;
  }
  if (d.citations.length > 0) {
    const total = d.citationsTotal ?? d.citations.length;
    const lines: string[] = [];
    for (const c of d.citations) {
      const next = [...lines, citationLine(c)];
      const rest = total - next.length;
      const tail = rest > 0 ? `\nand ${rest} more in the drafts file` : '';
      if (next.join('\n').length + tail.length > limits.examples_max) break;
      lines.push(citationLine(c));
    }
    const rest = total - lines.length;
    if (lines.length > 0) gate0.examples = lines.join('\n') + (rest > 0 ? `\nand ${rest} more in the drafts file` : '');
  }
  if (!gate0.examples) missing.push('examples');
  const counts = countsSentence(d);
  if (counts && counts.length <= limits.affected_records_estimate_max) gate0.affected_records_estimate = counts;
  else missing.push('affected_records_estimate');
  return { gate0, missing };
}

/** The `source` block the server takes for a proposal filed from this draft. */
export function sourceFromDraft(d: LocalTermDraft, bundleId: string | null): ApiSchemaProposalSourceInput | null {
  if (d.count === null || d.count < 1) return null;
  return {
    kind: 'local_import',
    format: TERM_DRAFTS_FORMAT,
    ...(bundleId ? { bundle_id: bundleId } : {}),
    field_path: d.fieldPath,
    term: d.term,
    occurrences: d.count,
    ...(d.runs !== null ? { runs: d.runs } : {}),
    citations_total: d.citationsTotal ?? d.citations.length,
  };
}
