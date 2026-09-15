/*
 * AUTHORING A PROPOSAL BY HAND — the vocabulary and the parsing, in ONE place.
 *
 * WHY THIS MODULE EXISTS. Two surfaces now mint a proposal from a note a scientist
 * chose: `UnmappedNotesPanel`'s per-note "Propose a Value from This Note", and
 * `NewProposalForm`'s "New Proposal" on the Ingestion Proposals surface itself. They
 * are the SAME ACT reached from two places, so they must store the same `rule`
 * sentence, compute the same `client_request_key` digest, and refuse the same values
 * with the same words. `CLAUDE.md`'s "one vocabulary, three copies" entry records
 * what happens when a rename strands one of several copies; the cheapest defence is
 * for there to be one copy.
 *
 * EVERY SYMBOL HERE WAS MOVED, NOT WRITTEN. `HUMAN_PROPOSED_RULE`,
 * `stableValueDigest` and the parsing/refusal strings in `parseProposedValue` are
 * `UnmappedNotesPanel`'s, verbatim, including their original reasoning comments. The
 * move is behaviour-preserving by construction: that panel now imports them.
 *
 * NOTHING HERE TALKS TO THE SERVER, and nothing here decides a target, a run, or a
 * scope. Those come from `GET .../proposals`'s own `target_field_paths` and
 * `record_scoped_target_field_paths` at runtime and are never transcribed into this
 * bundle.
 */
import { RUN_FIELDS, parseRunField, type RunFieldSpec } from './runFields';

/**
 * THE RULE SENTENCE FOR A HUMAN-MAPPED PROPOSAL. `rule` is required by the server
 * and must be "the sentence that produced this value and this target, not an
 * identifier" — for an extracted candidate that sentence describes the extraction
 * rule; for this act there is no extraction rule, and the honest sentence says
 * exactly that: a person read the note and chose the value directly. It is a FIXED
 * constant rather than something a scientist types, because composing a provenance
 * sentence is a burden this act does not need to impose — the act itself IS the
 * provenance.
 *
 * IT IS SHOWN, NOT HIDDEN. `NewProposalForm` renders this string read-only, labelled
 * as the explanation that will be stored, so a scientist sees the exact sentence
 * their proposal will carry rather than discovering it on the review card. A
 * free-text box here was considered and declined: two surfaces performing one act
 * must not store two different provenance sentences, and a box a reader must fill
 * before they may propose is a burden with no truth gained — the sentence is
 * already, and only, true.
 */
export const HUMAN_PROPOSED_RULE =
  'A person read this note directly and entered this value for the field by hand; ' +
  'no automated rule matched it.';

/**
 * A short, deterministic, NON-cryptographic digest of a proposed value — used only
 * to build `client_request_key` so an accidental double click on the submit control
 * dedupes to one proposal rather than two. It carries no security property;
 * exactly-once enforcement is the server's, inside `record_lock` (contract §2,
 * DEC-13) — this only has to be STABLE for the same (note, path, value) triple
 * within one click, which a plain hash over the value's JSON serialisation is.
 *
 * THE COLLISION BEHAVIOUR, NAMED RATHER THAN LEFT IMPLICIT (m8, independent review
 * of PR-D). This is a 32-bit hash (`hash >>> 0`), not a cryptographic one, so two
 * DIFFERENT values for the SAME (note, path) CAN — with vanishing but non-zero
 * probability — produce the SAME `client_request_key`. If that ever happens:
 * proposing value A stores it under key K; proposing DIFFERENT value B for the same
 * note+path later computes the SAME key K, and the server's dedup returns A's
 * proposal with `deduplicated: true` — the reader is told "already proposed" while
 * the record still holds A, not B. Nothing is corrupted (A is a real, previously
 * confirmed proposal; B is simply not stored), but the CONFIRMATION is misleading
 * for that one request. Two things bound the risk to theoretical: the key space is
 * scoped to ONE (note_id, field_path) pair — not the record, not the experiment —
 * and a real note is proposed against a handful of paths at most, nowhere near the
 * ~2^16 distinct values against one pair before a birthday-bound collision becomes
 * plausible. The risk this function actually has to cover — an accidental double
 * click on the SAME value — cannot manifest it at all (identical value ⇒ identical
 * digest by construction).
 */
export function stableValueDigest(value: unknown): string {
  const json = JSON.stringify(value) ?? 'undefined';
  let hash = 5381;
  for (let index = 0; index < json.length; index += 1) {
    hash = (Math.imul(hash, 33) + json.charCodeAt(index)) | 0;
  }
  return (hash >>> 0).toString(16);
}

/**
 * The client-side spec for a target path's SHAPE, or `null` when none exists.
 *
 * `RUN_FIELDS` is `RunCard`'s own closed, server-verified writable set, each entry
 * backed by the official schema's declared type (an enum, a number, or an ISO
 * date-time). A proposal target that happens to be one of those paths gets the SAME
 * typed control a run editor would give it. A target OUTSIDE that set —
 * `system.technique`, `sample.*`, `system.facility.*`, and anything future the
 * server's `target_field_paths` widens to — has no client-side spec for its shape at
 * all, and the honest fallback for a shape this bundle does not know is JSON text:
 * never a guess at a type the schema did not confirm.
 */
export function proposalFieldSpec(path: string): RunFieldSpec | null {
  return RUN_FIELDS.find((spec) => spec.path === path) ?? null;
}

/**
 * The human label for a target path. THE PATH IS NEVER REPLACED BY IT — every caller
 * renders the dotted path beside this, demoted, per `UX-014`.
 *
 * TWO SOURCES, IN ORDER, AND NEITHER IS INVENTED HERE. When `RUN_FIELDS` declares a
 * label for the path, that label is used: it is this client's existing vocabulary
 * for that field, already on screen in `RunCard` and in the sibling propose form, and
 * a second wording for one field is exactly the drift this module exists to avoid.
 * Otherwise the LAST path segment is title-cased, which mirrors the server's own
 * `assistant_query._humanize` (`sample.material.formula` -> `Formula`) — the
 * vocabulary every assistant answer in this product already uses for a schema path.
 *
 * IT IS A CASING TRANSFORM AND NOTHING ELSE. Every word it emits is a word the path
 * already contained; no token is translated, expanded or dropped, so it cannot name
 * a field something the schema does not call it. A test asserts that property over
 * every path the server serves. There is deliberately NO acronym table here: the one
 * in `adapt.blockerDisplayName` exists for bare blocker keys, and widening a recasing
 * to schema paths is precisely what `assistant_query._humanize`'s own docstring
 * records declining, because it would silently restyle field names everywhere.
 */
export function proposalFieldLabel(path: string): string {
  const spec = proposalFieldSpec(path);
  if (spec !== null) return spec.label;
  const last = path.split(/[.:]/).pop() ?? path;
  const titled = last.replace(/_/g, ' ').trim().replace(/\b[a-z]/g, (c) => c.toUpperCase());
  return titled === '' ? path : titled;
}

/**
 * The top-level block a target path belongs to, title-cased — `context`, `sample`,
 * `system`, `timestamps`. Used only to GROUP the picker's options; it names no field
 * and is never stored or sent. A path with no dot is its own group.
 */
export function proposalFieldGroup(path: string): string {
  const first = path.split('.')[0] ?? path;
  return first.replace(/_/g, ' ').replace(/\b[a-z]/g, (c) => c.toUpperCase());
}

/** What a scientist typed, turned into the JSON value that will be proposed. */
export type ParsedProposedValue =
  | { ok: true; value: unknown }
  | { ok: false; error: string };

/**
 * Parse the value box for one target path — typed where a spec exists, JSON where
 * none does, and a REFUSAL for `null` either way.
 *
 * THE `null` REFUSAL IS NOT A VALIDATION NICETY. `parseRunField` returns
 * `{ok: true, value: null}` for an empty box, and `JSON.parse('null')` is `null`.
 * Proposing `null` would be proposing to CLEAR a field, which is a different act
 * with its own questions, so it is refused here rather than sent — in both branches,
 * because the two ways of reaching it are equally reachable.
 */
export function parseProposedValue(path: string, raw: string): ParsedProposedValue {
  const spec = proposalFieldSpec(path);
  let parsed: unknown;
  if (spec !== null) {
    const typed = parseRunField(spec, raw);
    if (!typed.ok) return { ok: false, error: typed.error };
    parsed = typed.value;
  } else {
    try {
      parsed = JSON.parse(raw) as unknown;
    } catch {
      return {
        ok: false,
        error:
          'That is not valid JSON, so it was not sent and nothing was written. A text ' +
          'value needs quotes around it, for example "CuO".',
      };
    }
  }
  if (parsed === null) {
    return {
      ok: false,
      error:
        'A null value cannot be proposed here — clearing a field is a different act ' +
        'with its own questions. Nothing was sent.',
    };
  }
  return { ok: true, value: parsed };
}
