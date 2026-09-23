import { useCallback, useEffect, useRef, useState } from 'react';
import './activityHistory.css';
import { Disclosure } from './Disclosure';
import { api } from '../lib/api';
import { LABELS, humanizeActivityToken as humanizeToken } from '../lib/labels';
import type { ApiActivityEvent, ApiActivityResponse } from '../lib/types';

/**
 * THE APPEND-ONLY ACTIVITY HISTORY, FOR A SCIENTIST — `ACT-003`, against `DEC-44`.
 *
 * ── WHAT THIS SURFACE IS FOR ────────────────────────────────────────────────
 *
 * One question: *what happened to this record, and in what order?* It is a
 * destination, not a workflow step — there is no derivable criterion for "the
 * history is finished", so it carries no tick, no lock and no `aria-current="step"`.
 * That is the same argument `workflow.py:128-149` makes for submission and the
 * capture group makes for itself, and it is why this lives in the sidebar's
 * destination list rather than in the workflow spine.
 *
 * ── READ-ONLY, STRUCTURALLY ─────────────────────────────────────────────────
 *
 * There is no control on this panel that writes anything, and there is no client
 * method that could: `api.listActivity` has no sibling mutator because
 * `activity.py` exposes none. An event is recorded by the act it describes.
 *
 * `ACT-003b` ADDED TWO DISCLOSURES AND NO WRITE, and the test that says so was
 * STRENGTHENED rather than left alone. They were native `<details>`; since the final
 * review of #279 they are the shared `Disclosure` — the native 11px triangles were the
 * last ones on the record screen — so each is now a real `<button>` whose only act is
 * to show or hide a body that is already in the DOM. The test therefore asserts over
 * STRUCTURE, which no role mapping can soften: on a row with a structured change the
 * ONLY `<button>` elements are the two disclosure toggles (each `type="button"`,
 * carrying `aria-expanded` and an `aria-controls` that names its own hidden body),
 * there are ZERO `input`/`textarea`/`select`/`form` elements, and `api` still
 * exposes no activity mutator. Structure, not a promise — and the description above
 * is the assertion list the test body actually makes.
 *
 * ── THE FOUR COUNTS ARE NEVER COLLAPSED ─────────────────────────────────────
 *
 * `total` (every act on the record), `matched` (those satisfying the filter) and
 * `returned` (those on this page) are three different facts, and every number
 * rendered here reads the SERVER's field — never `events.length`. `CLAUDE.md` §11
 * records the defect that rule exists for: a count taken from a fetched array
 * understates the truth the moment a page is smaller than the whole. A separate
 * `unreadable_entries` is disclosed rather than hidden, because a stored event this
 * build cannot parse must be counted; rendering it would mean inventing its content.
 *
 * TWO NEW KINDS OF NUMBER ARRIVE WITH `ACT-003b`, AND NEITHER IS A HISTORY COUNT.
 * A structured value's "6 fields", an array's "1024 values" and a truncation
 * notice's character counts are all counted off the ONE stored value in front of
 * the reader. None of them is a claim about how much history exists, which is the
 * only claim the server's fields are authoritative for — so the rule that a count
 * comes from the server is untouched, not widened and not weakened.
 *
 * ── `unattributed` IS SHOWN, NOT HIDDEN ─────────────────────────────────────
 *
 * `ACT-003`'s own requirement. Every event in every deployment of this build reads
 * `actor: "unattributed"`, because no trusted authentication boundary exists
 * (`EXT-01`) and a name read from a forwarded header would be a forgeable claim
 * rendered as a fact. Confirmed on the hosted deployment on 2026-09-17:
 * `actor_trust_basis: null`, `verifier_id: "unconfigured"`. So the panel says so in
 * words, once, at the top — rather than printing a literal nobody can interpret
 * beside every row, and rather than dropping the rows that "lack" an actor.
 *
 * See `PER_ROW_ACTOR` below for the `ACT-003b` judgement call this forced, stated
 * rather than picked silently.
 */

/* THE HUMANIZER MOVED TO `lib/labels.ts`, and this note is why rather than a
 * silent import.
 *
 * It was defined HERE, with a comment saying "this is the ONLY place they are
 * turned into words" — true when it was written, and it stopped being true the
 * moment a SECOND surface rendered the same server vocabularies (`ACT-004`'s
 * activity summary on the Statistics Overview tab). Copying six lines would have
 * made two functions that agree today and are free to disagree later, which is
 * the defect this repository records as "one vocabulary, three copies": a rename
 * strands every copy but the one the author was looking at.
 *
 * So there is still exactly ONE humanizer for these tokens, and it is now
 * somewhere both surfaces can reach.
 *
 * ~~Its behaviour is unchanged — the `activity-history-panel` suite passes against
 * it untouched, which is the check that matters for a move.~~ **FALSE, and
 * corrected rather than deleted, because "behaviour is unchanged" is exactly the
 * claim a future session would rely on when judging whether this move was safe.**
 * The shared version added an initialism map, so a row on the `mcp` channel moved
 * **"Mcp" -> "MCP"** on THIS panel as well as on the Statistics summary that
 * prompted the map. The change is an improvement and is deliberate; the suite
 * passing is true and was never evidence of no change, because no test named
 * either spelling. What IS unchanged: every other token, and the fact that every
 * output word is an input word — casing only, so no name is invented.
 *
 * ── THE WHOLE DELTA, MEASURED, AND IT REACHES `humanizeKeyName` BELOW ──────
 *
 * Both implementations were run over all 20 actions, all 10 object types, all 4
 * channels and 7 plausible structured-value keys — 41 tokens. **3 differ, and all
 * 3 are the `mcp` segment:** `mcp` -> "Mcp"/"MCP" (the channel, and a key of that
 * name) and `mcp_tool` -> "Mcp Tool"/"MCP Tool". Nothing else moves.
 *
 * That last one is the part a future session meets HERE rather than on the
 * Statistics summary: `humanizeKeyName` just below gates on `BARE_IDENTIFIER` and
 * then calls this humanizer, so a KEY inside a stored structured value named `mcp`
 * or `mcp_*` now renders with the initialism too. That is a change to the caller
 * this file gained in the same week, it is deliberate, and it is casing-only — but
 * it is a change, and this block exists because the previous sentence claiming
 * otherwise was false. */

/**
 * A BARE INTERNAL IDENTIFIER, AND NOTHING ELSE.
 *
 * `CLAUDE.md` §11 records this exact predicate and the measurement behind it: the
 * humanizer is applied ONLY to a name shaped like an internal key, because the same
 * function turns `ssrl-archive://BL15-2/2099_run_000/x.xdi` into "Xdi" — replacing
 * information with a guess. Anything not of this shape is rendered verbatim.
 *
 * A key inside a stored structured value is arbitrary, so it gets this gate. The
 * server's OWN vocabularies (`action`, `object_type`, `channel`) are closed sets
 * declared by `activity.py` and deliberately do not.
 */
const BARE_IDENTIFIER = /^[a-z][a-z0-9]*(_[a-z0-9]+)*$/;

function humanizeKeyName(key: string): string {
  return BARE_IDENTIFIER.test(key) ? humanizeToken(key) : key;
}

/** One side of the server's `{present, value}` envelope. */
type Side = { present: boolean; value: unknown };

/** `{present: false}` and `{present: true, value: null}` are DIFFERENT FACTS and are
 *  rendered differently. Branching on `value` instead of `present` would collapse
 *  "there was nothing here" into "it was empty", which is the distinction the
 *  server's envelope exists to carry.
 *
 *  A `null` RETURN MEANS "this side is not something a sentence can contain" — an
 *  object or an array — and is the signal the structured branch keys on. It does NOT
 *  mean the stored value was null; that case returns `LABELS.activityNull`.
 *
 *  THIS REPLACES `describeSide`, whose fall-through was `JSON.stringify(value)`
 *  rendered at 11px as the DEFAULT scientist view of any structured change —
 *  `ACT-003b`'s defect C. The raw document is not deleted; it moved behind the
 *  disclosure `storedText` feeds, where it is labelled as the stored value. */
function primitiveText(side: Side): string | null {
  if (!side.present) return LABELS.activityAbsent;
  const { value } = side;
  if (value === null) return LABELS.activityNull;
  if (typeof value === 'string') return value === '' ? LABELS.activityEmptyString : value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return null;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * THE STORED VALUE, VERBATIM — the raw detail `ACT-003b` requires stay reachable.
 *
 * `JSON.stringify` PRESERVES KEY INSERTION ORDER, which is why it is used here and
 * why nothing sorts: §5 forbids reordering or normalising a stored value in a way
 * that changes what it says, and a curator reading an audit row needs the document
 * as it was written. Indentation is added; nothing else is.
 */
function storedText(side: Side): string {
  if (!side.present) return LABELS.activityAbsent;
  if (side.value === null) return LABELS.activityNull;
  if (typeof side.value === 'string') {
    return side.value === '' ? LABELS.activityEmptyString : side.value;
  }
  return JSON.stringify(side.value, null, 2) ?? String(side.value);
}

/** Two stored values compared as DOCUMENTS: `JSON.stringify` with no replacer is a
 *  mechanical text comparison that interprets nothing. */
function sameStored(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * THE SAME VALUE, WRITTEN IN A DIFFERENT KEY ORDER — at ANY depth.
 *
 * `sameStored` is text equality over `JSON.stringify`, so it is key-order sensitive
 * all the way down. THAT IS RIGHT for deciding whether a document was rewritten, and
 * it is WRONG for deciding what to tell a reader: `{asset: {uri, sha256}}` becoming
 * `{asset: {sha256, uri}}` is a real difference in the stored document and NOT a
 * difference a curator can act on. Without this, that change rendered as "Asset
 * changed — the stored values are below", and the reader opened the disclosure to
 * find two documents that say the same thing, hunting for a difference that is not
 * there. That is the exact outcome the top-level order-only note exists to prevent,
 * and it was prevented at the top level only — found by independent review.
 *
 * ARRAY ORDER IS COMPARED POSITIONALLY AND DELIBERATELY SO. An object's key order
 * carries no meaning a reader can act on; an array's order IS data — a reordered
 * `detached_run_ids` is a different statement, and `assets.detach_everywhere` returns
 * its runs "IN RUN ORDER, NOT SORTED" for precisely that reason. Treating the two
 * the same would have this function report a real change as cosmetic.
 *
 * NOTHING IS REWRITTEN OR NORMALISED BY THIS. It is a comparison; the documents
 * under the disclosure are still `JSON.stringify` of the stored values in the order
 * they were stored, which is §5's requirement.
 */
function sameIgnoringKeyOrder(a: unknown, b: unknown): boolean {
  if (sameStored(a, b)) return true;
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((item, i) => sameIgnoringKeyOrder(item, b[i]));
  }
  if (isPlainObject(a) && isPlainObject(b)) {
    const ka = Object.keys(a);
    if (ka.length !== Object.keys(b).length) return false;
    return ka.every(
      (k) => Object.prototype.hasOwnProperty.call(b, k) && sameIgnoringKeyOrder(a[k], b[k]),
    );
  }
  return false;
}

function countPhrase(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/**
 * WHAT A STRUCTURED SIDE IS, IN WORDS THE VALUE ITSELF SUPPLIES.
 *
 * An object is described by how many fields it holds, an array by how many values.
 * Both are counted off the value in front of the reader. NOTHING here says what the
 * value MEANS — calling one a spectrum, a digest or a unit would be exactly the
 * scientific interpretation §5 forbids. The keys are NAMED individually in the diff
 * below, so a reader sees them rather than being told about them.
 */
function structuredSummary(value: unknown): string {
  if (Array.isArray(value)) {
    return countPhrase(value.length, LABELS.activityValueSingular, LABELS.activityValuePlural);
  }
  if (isPlainObject(value)) {
    return countPhrase(
      Object.keys(value).length,
      LABELS.activityFieldSingular,
      LABELS.activityFieldPlural,
    );
  }
  /* Unreachable from `sideLabel`, which only asks about a non-primitive. Kept as an
     honest answer rather than a throw: a persisted value this build did not
     anticipate must be READ, not refused — §11's persisted-value rule, which is
     about a reader who did nothing wrong and whose row would otherwise vanish. */
  return storedText({ present: true, value });
}

/** One side of the change as a phrase: its text if it has one, else its shape. */
function sideLabel(side: Side): string {
  return primitiveText(side) ?? structuredSummary(side.value);
}

/**
 * THE INLINE THRESHOLD, AND WHY IT IS 40 — with the one thing it is NOT.
 *
 * `activityHistory.css` declares this panel's reading measure as `68ch`
 * (`.activity-lead`, `.activity-actor-note`). An inline change is two values plus a
 * three-character arrow on one line, so 40 characters on ONE side already exceeds
 * half that measure: the second value starts on a new line and the arrow lands at
 * the end of a paragraph, where it reads as punctuation rather than as a relation
 * between two things. Below 40, both values and the arrow stay adjacent.
 *
 * WHAT THIS IS NOT, stated because the first draft of this comment overstated it:
 * `.activity-change` itself carries NO `max-width`, so 68ch is the measure this
 * panel DECLARES for prose, not a measured width of the change line — which is as
 * wide as the record content column at whatever viewport the reader has. The
 * threshold is derived from the panel's own declared measure, which is a checkable
 * property of the stylesheet beside it; it is not a browser measurement, and no
 * browser measurement was taken for it.
 */
const INLINE_MAX_CHARS = 40;

/**
 * THE BLOCK CAP, AND WHY IT IS 400.
 *
 * About six lines at the declared `68ch` measure — enough to see WHAT changed in a
 * long text without one audit row becoming a page. The same caveat as above applies
 * to "six lines": it is arithmetic over the declared measure, not a rendered count.
 * A longer value is cut, the reader is TOLD the exact character counts, and the
 * whole value sits under the disclosure unchanged. `ACT-003b`'s rule is that
 * nothing is truncated SILENTLY; it is not that nothing is ever truncated.
 */
const BLOCK_MAX_CHARS = 400;

function inlinePair(before: Side, after: Side): { before: string; after: string } | null {
  const b = primitiveText(before);
  const a = primitiveText(after);
  if (b === null || a === null) return null;
  if (b.length > INLINE_MAX_CHARS || a.length > INLINE_MAX_CHARS) return null;
  return { before: b, after: a };
}

/**
 * THE FIELD-LEVEL DIFF, WHEN AND ONLY WHEN BOTH SIDES ARE OBJECTS.
 *
 * Keys are reported in the order the stored documents list them — `after`'s order
 * for what is there now, `before`'s for what is gone — because sorting would
 * replace the record's own order with a lexical one, and this panel's whole job is
 * to report what the record says.
 *
 * A key whose two values are short primitives is shown as a value change. A key
 * whose values are not — an object, an array, a long string — is NAMED and nothing
 * more, with both stored documents under the disclosure. That is the fallback
 * `ACT-003b` requires: an object whose keys this build cannot interpret gets its
 * changed keys named, never a guess at their meaning.
 */
interface KeyChange {
  readonly key: string;
  readonly kind: 'added' | 'removed' | 'changed';
  /** The inline `a -> b` pair, or `null` when the values are not sentence-sized. */
  readonly pair: { before: string; after: string } | null;
  /** This key's two values say the same thing in a different stored key order. See
   *  `sameIgnoringKeyOrder`: without this the row read "changed — the values are
   *  below" and the disclosure held two documents a reader could not tell apart. */
  readonly orderOnly: boolean;
}

function keyChanges(before: Record<string, unknown>, after: Record<string, unknown>): KeyChange[] {
  const changes: KeyChange[] = [];
  const has = (o: Record<string, unknown>, k: string): boolean =>
    Object.prototype.hasOwnProperty.call(o, k);
  for (const key of Object.keys(after)) {
    const present = has(before, key);
    if (present && sameStored(before[key], after[key])) continue;
    changes.push({
      key,
      kind: present ? 'changed' : 'added',
      pair: inlinePair(
        present ? { present: true, value: before[key] } : { present: false, value: null },
        { present: true, value: after[key] },
      ),
      orderOnly: present && sameIgnoringKeyOrder(before[key], after[key]),
    });
  }
  for (const key of Object.keys(before)) {
    if (has(after, key)) continue;
    changes.push({
      key,
      kind: 'removed',
      pair: inlinePair({ present: true, value: before[key] }, { present: false, value: null }),
      /* A key that is GONE cannot be an order-only difference: there is no second
         document to have written it in another order. Stated rather than left to
         the reader of `false`. */
      orderOnly: false,
    });
  }
  return changes;
}

/** How the change of ONE event should be presented. Derived from the two stored
 *  sides and nothing else — never from the action name, which would be a guess
 *  about a vocabulary the server owns. */
type ChangeShape =
  | { mode: 'inline'; before: string; after: string }
  | { mode: 'blocks'; before: string; after: string; beforeFull: string; afterFull: string }
  | {
      mode: 'structured';
      before: string;
      after: string;
      /** `null` unless BOTH sides are plain objects — the only case a key-level
       *  diff is a statement about the document rather than an inference. */
      keys: KeyChange[] | null;
      /** Stated only when it is true and mechanically checkable. */
      note: string | null;
    };

function truncate(text: string): { shown: string; truncated: boolean } {
  if (text.length <= BLOCK_MAX_CHARS) return { shown: text, truncated: false };
  return { shown: text.slice(0, BLOCK_MAX_CHARS), truncated: true };
}

function changeShape(before: Side, after: Side): ChangeShape {
  const b = primitiveText(before);
  const a = primitiveText(after);
  if (b === null || a === null) {
    let keys: KeyChange[] | null = null;
    if (isPlainObject(before.value) && isPlainObject(after.value) && before.present && after.present) {
      keys = keyChanges(before.value, after.value);
    }
    /* THE NOTES ARE EACH A MECHANICAL FACT, not a reading of the science. The
       order-only one is reachable: an asset entry rewritten whole can produce two
       documents with the same fields in a different stored order, and saying "no
       field differs" without saying why would leave a reader hunting for a change
       that is not there. The identical one covers a pair that is the same document —
       the write paths gate on a change, so it should not occur, and if it ever does
       the honest answer is to say so rather than to render an empty diff.

       THE THIRD CASE WAS MISSING AND IS WHY THIS BLOCK CHANGED (independent review,
       Minor 5). `keys.length === 0` only catches a reordering of the TOP-LEVEL keys.
       A reordering one level down — `{asset: {uri, sha256}}` -> `{asset: {sha256,
       uri}}` — produces exactly one changed key and so fell straight past this,
       rendering "Asset changed — the stored values are below" over two documents a
       curator cannot tell apart. When every changed key is order-only, the summary
       now says so, and each such row says so for itself. */
    let note: string | null = null;
    if (keys !== null && keys.length === 0) {
      note = sameStored(before.value, after.value)
        ? LABELS.activityStoredIdentical
        : LABELS.activityStoredOrderOnly;
    } else if (keys !== null && keys.every((change) => change.orderOnly)) {
      note = LABELS.activityStoredOrderOnly;
    }
    return { mode: 'structured', before: sideLabel(before), after: sideLabel(after), keys, note };
  }
  if (b.length > INLINE_MAX_CHARS || a.length > INLINE_MAX_CHARS) {
    const tb = truncate(b);
    const ta = truncate(a);
    return {
      mode: 'blocks',
      before: tb.shown,
      after: ta.shown,
      beforeFull: tb.truncated ? b : '',
      afterFull: ta.truncated ? a : '',
    };
  }
  return { mode: 'inline', before: b, after: a };
}

/**
 * THE RELATIVE DAY NAMES ARE RECOMPUTED ON EVERY RENDER, DELIBERATELY.
 *
 * "Today" and "Yesterday" are claims about the clock at the moment of reading, so
 * `now` is taken inside the render body and threaded down; nothing memoises it. A
 * value captured at mount would be wrong on the NEXT RENDER after midnight — the
 * panel would assert that yesterday's acts happened today, while the reader watched
 * it repaint. This panel holds no unsaved state and re-reads on open, so
 * recomputing costs one `Date` per render.
 *
 * ── WHAT THIS DOES NOT FIX, AND THE CLAIM THAT WAS WITHDRAWN ───────────────
 *
 * An earlier version of this note, and of its test's title, said "a tab left open
 * overnight does not lie". **That overstated it and is withdrawn** (independent
 * review, Minor 4 — and the reviewer flagged it as a reading rather than a
 * reproduction, which is why it was re-derived here before being accepted).
 *
 * Re-derived: this panel has NO timer, NO poller and NO change-feed subscription —
 * `useEffect(load, [load])` fires on mount and on an `experimentId` change, and
 * nothing else schedules work. So an IDLE tab opened at 23:50 still reads "Today"
 * at 09:00, and will go on doing so until something causes a render. What the
 * mechanism actually delivers is narrower and is what the test now says: **the next
 * render uses the clock at that moment, not the clock at mount.**
 *
 * A TIMER WAS DELIBERATELY NOT ADDED. It would be a background render on a
 * read-only destination to correct one word, and it would be the first scheduled
 * work on this panel — a cost with a real failure mode (a re-render while a reader
 * has a disclosure open) against a label that the group's own absolute date already
 * disambiguates for anyone who looks twice.
 */
function calendarDay(at: Date): string {
  /* The reader's LOCAL calendar day, not the UTC one: "Today" has to mean today
     where the scientist is standing. The machine value stays exact in `dateTime`. */
  return `${at.getFullYear()}-${at.getMonth()}-${at.getDate()}`;
}

function dayKey(iso: string): string | null {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return null;
  return calendarDay(at);
}

function dayHeading(iso: string, now: Date): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  const key = calendarDay(at);
  if (key === calendarDay(now)) return LABELS.activityToday;
  const yesterday = new Date(now.getTime());
  yesterday.setDate(yesterday.getDate() - 1);
  if (key === calendarDay(yesterday)) return LABELS.activityYesterday;
  /* THE YEAR IS KEPT. `ACT-003b`'s sketch shows "September 14"; a history that
     spans a year boundary would then carry two indistinguishable headings, and
     ordering is the one thing this panel exists to make legible. `toLocaleDateString`
     with an explicit option set invents no date vocabulary. */
  return at.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
}

interface DayGroup {
  readonly key: string;
  readonly heading: string;
  readonly events: ApiActivityEvent[];
}

/**
 * CONSECUTIVE RUNS OF ONE CALENDAR DAY — not a bucket-by-key regrouping.
 *
 * Two properties this shape has and a keyed grouping does not:
 *
 *  1. IT NEVER REORDERS. The server orders by `seq`, a durable position, and
 *     `recorded_utc` is not guaranteed to be monotonic in it. Bucketing by day would
 *     move an out-of-order event to sit with its calendar neighbours, which is a
 *     claim about ordering the record does not make.
 *  2. A GROUP SPANNING A PAGE BOUNDARY STAYS ONE GROUP. Pages are appended to the
 *     tail of one array and grouping runs over the concatenation, so a day opened by
 *     page 1 and continued by page 2 is one contiguous run and renders ONE heading.
 *     `ACT-003b` asks for that to be measured, and it is — with a fixture whose page
 *     boundary falls inside a day.
 *
 * An UNPARSEABLE timestamp gets a group of its own, keyed by the event id, because
 * merging it with a real day would assert a date the stored value does not carry.
 */
function groupByDay(events: readonly ApiActivityEvent[], now: Date): DayGroup[] {
  const groups: DayGroup[] = [];
  for (const event of events) {
    const parsed = dayKey(event.recorded_utc);
    const key = parsed === null ? `unparseable:${event.id}` : parsed;
    const last = groups[groups.length - 1];
    if (last !== undefined && last.key === key) last.events.push(event);
    else groups.push({ key, heading: dayHeading(event.recorded_utc, now), events: [event] });
  }
  return groups;
}

/**
 * A timestamp a scientist reads, with the machine value kept where machines look.
 *
 * TWO DEFECTS IN ONE, both found by registering this surface for the responsive
 * sweep (`ACT-003`'s own accepted round trip), and both mine:
 *
 *  1. LAYOUT. The raw `recorded_utc` is an unbreakable ~20-character token
 *     (`2099-01-01T00:00:00Z`) in a `flex-wrap` row with no `overflow-wrap`, so it
 *     sets a min-content floor that widened the content column and squeezed the
 *     workflow spine's own flex children — CI reported `scrollWidth 200 vs
 *     clientWidth 1` on `span.spine-meta`, a sibling ABOVE this panel. A too-wide
 *     child clips its neighbours, not itself.
 *  2. COPY. An ISO-8601 string with a `T` and a `Z` is a WIRE FORMAT. Rendering it
 *     at a scientist is the same defect class as rendering `Q6` — `CLAUDE.md` §11's
 *     rule — and it was hiding behind a real layout failure.
 *
 * `toLocaleString` is used with an explicit option set rather than a hand-rolled
 * format, so this invents no date vocabulary; an unparseable value falls back to the
 * stored string rather than to a guess or an empty cell.
 *
 * `ACT-003b` SPLIT IT IN TWO AND KEPT BOTH. The row now renders the time of day and
 * its group heading carries the date, which is the hierarchy defect A is about — but
 * the full readable timestamp is NOT deleted: it is the `<time>`'s `title`, so a
 * reader who wants the absolute value on one row can reach it without leaving the
 * page, and `dateTime` still carries the exact machine value it always did.
 */
function readableWhen(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  return at.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function readableTimeOfDay(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  return at.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

/**
 * THE PER-ROW ACTOR — `ACT-003b`'s judgement call, recorded rather than picked
 * silently, because the brief asked for the reasoning and not only the outcome.
 *
 * WHAT I CHOSE. The actor is rendered on every row's metadata line if and only if
 * the loaded history contains at least one event whose actor is not the
 * `unattributed` sentinel. In every deployment of this build that condition is
 * false, so no row shows an actor and the panel's existing `<details>` carries the
 * fact once, in words, with its reason.
 *
 * WHY, AND WHAT THE ALTERNATIVES COST.
 *
 *  · ALWAYS SHOWING IT is noise today and slightly worse than noise: a column
 *    reading "Unattributed" on every row of every record is a repeated non-answer
 *    competing with the action for the reader's attention, which is exactly the
 *    hierarchy defect B exists to fix. `ACT-003`'s requirement is that
 *    `unattributed` be rendered HONESTLY — it is, once, where a reader meets it with
 *    the reason attached rather than as a bare token beside 200 rows. `CLAUDE.md`
 *    §11 records the same asymmetry being chosen deliberately for the blocker keys:
 *    suppressed where a correct label already sits beside them, spelled out in a
 *    sentence where the token IS the name.
 *
 *  · NEVER SHOWING IT would be wrong the moment a deployment can attribute an act.
 *    Dropping a real name from an audit history is not a tidier surface, it is a
 *    missing fact — so the suppression is CONDITIONAL on the value, not hard-coded.
 *
 *  · SUPPRESSING ONLY THE SENTINEL ROWS, in a history that mixed both, would make
 *    an unattributed row indistinguishable from a row whose actor this build failed
 *    to read. So the gate is per-LIST rather than per-row: once any actor is named,
 *    every row says who — including the honest "Unattributed" ones.
 *
 * `DEC-45` requires that a name never travel unqualified. `actorBasisNote` is
 * `revisionHistory.actorBasisNote`'s rule reused rather than re-invented: a
 * qualification is rendered exactly when the basis is one a reader would otherwise
 * take at face value.
 *
 * ── THE STANDING DISCLOSURE MOVES WITH THIS, AND DID NOT AT FIRST ───────────
 *
 * INDEPENDENT REVIEW, Important 1: this argument spends four paragraphs on why the
 * suppression must be conditional on the value, and then left its COUNTERPART hard
 * coded — the `<details>` rendered unconditionally. A history with one attributed
 * act therefore showed a row naming a person directly beneath a sentence reading
 * *"Entries are not attributed to a person. This deployment has no verified sign-in
 * boundary…"*: two contradictory claims about the deployment on one screen. Not
 * reachable in a default build, reachable under `ISAAC_EDGE_TRUST_VERIFIER=
 * test_fixture` — which is exactly the future the conditional exists for. The
 * reviewer reproduced it by adding ONE assertion to my own mixed-history test,
 * whose fixture already built the state; the test simply never looked.
 *
 * `attributionNote` is the fix, and it is derived from the loaded events rather
 * than from a belief about the deployment, which is the property the old sentence
 * lacked:
 *
 *   nothing named   -> the original sentence, unchanged
 *   some named      -> a sentence about THOSE entries, asserting nothing about the
 *                      deployment as a whole
 *   all named       -> no disclosure; there is nothing to explain
 */
/* THE TWO SERVER CONSTANTS, TRANSCRIBED — and now guarded rather than trusted.
   `activity.ACTOR_UNATTRIBUTED` and `identity.TRUST_BASIS_TEST_FIXTURE` are the
   authorities; these are copies, because the frontend has no import path to Python.
   `apps/api/tests/test_activity_model.py` re-reads BOTH lines below and fails if
   either spelling drifts from the constant it mirrors — a drift would silently
   un-suppress every actor or silently drop `DEC-45`'s qualification, and neither
   would fail any frontend test. The declarations are kept one per line, in this
   exact form, because that parity test matches on them. */
const ACTOR_UNATTRIBUTED = 'unattributed';
const TRUST_BASIS_TEST_FIXTURE = 'test_fixture';

function PER_ROW_ACTOR(events: readonly ApiActivityEvent[]): boolean {
  return events.some((e) => e.actor !== ACTOR_UNATTRIBUTED);
}

/**
 * THE ACTOR IS RENDERED VERBATIM. It is a NAME, not a vocabulary token.
 *
 * INDEPENDENT REVIEW, Important 2, and the finding is right: this used to be
 * `humanizeToken(event.actor)`, so an audit row for `k_verma` displayed
 * **"K Verma"** and `svc_import_bot` displayed "Svc Import Bot". That is not the
 * recorded actor. It is not searchable, not copyable and not correlatable back to
 * the identity system — in the one surface whose entire job is saying who did what.
 * `CLAUDE.md` §15 (Dean, 2026-08-12) makes the canonical actor the Authentik
 * **username**, and a username is a literal.
 *
 * `humanizeKeyName`'s own docstring already stated the rule this broke: the
 * humanizer applies to a BARE INTERNAL IDENTIFIER only, because otherwise it
 * "replaces information with a guess". `action`, `object_type` and `channel` are
 * exempt as closed server vocabularies declared by `activity.py`. An actor is
 * neither — and note that routing it through `humanizeKeyName` would NOT have
 * fixed it, because `BARE_IDENTIFIER` matches `k_verma` and would mangle it just
 * the same. The only correct answer is not to humanize it at all.
 *
 * THE ONE EXCEPTION IS THE SENTINEL, which is not a name: `unattributed` is this
 * application's own word for nobody, so it gets a display form from `LABELS` —
 * one value, mapped explicitly, rather than a transformation applied to a class.
 */
function actorDisplay(actor: string): string {
  return actor === ACTOR_UNATTRIBUTED ? LABELS.activityActorSentinel : actor;
}

function actorBasisNote(event: ApiActivityEvent): string | null {
  if (event.actor === ACTOR_UNATTRIBUTED) return null;
  if (event.actor_trust_basis === TRUST_BASIS_TEST_FIXTURE) return LABELS.activityTrustFixture;
  return null;
}

/**
 * WHICH STANDING ATTRIBUTION SENTENCE IS TRUE OF WHAT IS ON SCREEN, if any.
 *
 * Derived from the loaded events. See `PER_ROW_ACTOR`'s note for the defect this
 * closes: the old code rendered the "no verified sign-in boundary" sentence
 * unconditionally, including beside a row that named somebody.
 *
 * THE `nothing named` BRANCH ALSO COVERS AN EMPTY, LOADING OR FAILED LIST, and that
 * is deliberate rather than incidental: with nothing loaded the panel knows nothing
 * that contradicts the sentence, and dropping the standing explanation from the
 * empty state would remove the one place a reader meets it before there is any
 * history to read.
 */
function attributionNote(events: readonly ApiActivityEvent[]): { summary: string; body: string } | null {
  const named = events.some((e) => e.actor !== ACTOR_UNATTRIBUTED);
  const unnamed = events.some((e) => e.actor === ACTOR_UNATTRIBUTED);
  if (!named) {
    return {
      summary: LABELS.activityWhyUnattributed,
      body: LABELS.activityActorUnattributed,
    };
  }
  if (unnamed) {
    return {
      summary: LABELS.activityWhySomeUnattributed,
      body: LABELS.activityActorSomeUnattributed,
    };
  }
  return null;
}

/** The stored documents, behind the shared `Disclosure` (final review of #279 — a
 *  native `<details>` before, the last 11px triangle on the record screen). Closed
 *  by default; the body stays in the DOM while closed, so the documents are still
 *  reachable by `querySelectorAll`, and a keyboard reader opens it with the button. */
function StoredValues({ before, after }: { before: Side; after: Side }) {
  return (
    <Disclosure
      summary={<span className="activity-stored-summary">{LABELS.activityShowStored}</span>}
      className="activity-stored"
    >
      <div className="activity-stored-body">
        <p className="activity-stored-label">{LABELS.activityBefore}</p>
        <pre className="activity-stored-pre">{storedText(before)}</pre>
        <p className="activity-stored-label">{LABELS.activityAfter}</p>
        <pre className="activity-stored-pre">{storedText(after)}</pre>
      </div>
    </Disclosure>
  );
}

function TruncationNotice({ shown, total }: { shown: number; total: number }) {
  return (
    <p className="activity-truncated">
      {LABELS.activityTruncatedShown} {shown} {LABELS.activityOf} {total}{' '}
      {LABELS.activityCharacters} {LABELS.activityTruncatedRest}
    </p>
  );
}

function ChangeBody({ event }: { event: ApiActivityEvent }) {
  const shape = changeShape(event.before, event.after);

  if (shape.mode === 'inline') {
    return (
      <p className="activity-change">
        <span className="activity-before">{shape.before}</span>
        <span className="activity-arrow" aria-hidden="true">
          {' → '}
        </span>
        {/* The global utility from `styles/base.css`, not a local copy. */}
        <span className="sr-only">{LABELS.activityChangedTo}</span>
        <span className="activity-after">{shape.after}</span>
      </p>
    );
  }

  if (shape.mode === 'blocks') {
    /* LABELLED BLOCKS RATHER THAN AN INLINE ARROW, which is defect C's second half:
       two long values joined by ` → ` wrap into one another and the reader cannot
       tell where the old value ended. The labels are visible, so no `sr-only`
       "changed to" is needed here — the relation is stated, not implied. */
    const truncated = shape.beforeFull !== '' || shape.afterFull !== '';
    return (
      <div className="activity-change-blocks">
        <p className="activity-change-side">
          <span className="activity-change-label">{LABELS.activityBefore}</span>
          <span className="activity-before">{shape.before}</span>
        </p>
        {shape.beforeFull !== '' && (
          <TruncationNotice shown={shape.before.length} total={shape.beforeFull.length} />
        )}
        <p className="activity-change-side">
          <span className="activity-change-label">{LABELS.activityAfter}</span>
          <span className="activity-after">{shape.after}</span>
        </p>
        {shape.afterFull !== '' && (
          <TruncationNotice shown={shape.after.length} total={shape.afterFull.length} />
        )}
        {truncated && <StoredValues before={event.before} after={event.after} />}
      </div>
    );
  }

  return (
    <div className="activity-change-structured">
      <p className="activity-change">
        <span className="activity-before">{shape.before}</span>
        <span className="activity-arrow" aria-hidden="true">
          {' → '}
        </span>
        <span className="sr-only">{LABELS.activityChangedTo}</span>
        <span className="activity-after">{shape.after}</span>
      </p>
      {shape.note !== null && <p className="activity-change-note">{shape.note}</p>}
      {shape.keys !== null && shape.keys.length > 0 && (
        <ul className="activity-diff">
          {shape.keys.map((change) => (
            <li className="activity-diff-row" key={change.key}>
              <span className="activity-diff-key">{humanizeKeyName(change.key)}</span>
              {change.pair === null ? (
                <span className="activity-diff-opaque">
                  {change.orderOnly
                    ? LABELS.activityStoredOrderOnlyField
                    : LABELS.activityChangedSeeBelow}
                </span>
              ) : (
                <span className="activity-diff-pair">
                  <span className="activity-before">{change.pair.before}</span>
                  <span className="activity-arrow" aria-hidden="true">
                    {' → '}
                  </span>
                  <span className="sr-only">{LABELS.activityChangedTo}</span>
                  <span className="activity-after">{change.pair.after}</span>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      <StoredValues before={event.before} after={event.after} />
    </div>
  );
}

function EventRow({ event, showActor }: { event: ApiActivityEvent; showActor: boolean }) {
  const showsChange = event.before.present || event.after.present;
  const basis = showActor ? actorBasisNote(event) : null;
  return (
    <li className="activity-row">
      {/* THE PRIMARY LINE IS THE ACT AND ITS OBJECT, AND NOTHING ELSE — defect B.
          Before `ACT-003b` the action, the object, the CHANNEL and the timestamp
          were four sibling spans at roughly equal weight, so "Web" competed with
          "Updated" for the first thing a reader saw. The channel and the time are
          secondary metadata and have moved to their own demoted line below. */}
      <p className="activity-row-head">
        <span className="activity-action">{humanizeToken(event.action)}</span>
        <span className="activity-object">{humanizeToken(event.object_type)}</span>
      </p>
      {event.field_path && <p className="activity-field">{event.field_path}</p>}
      {showsChange && <ChangeBody event={event} />}
      {/* THE METADATA LINE. Order follows the scan ranking `ACT-003b` states —
          actor, then time, then channel — rather than the sketch beside it, which
          puts the channel before the time and so contradicts its own ranking. That
          contradiction is reported rather than resolved silently; what both agree
          on, and what this line delivers, is that none of the three competes with
          the action above. The separator is a CSS `::before` — which keeps it out
          of `textContent` and out of the label vocabulary, and does NOT make it
          silent: Chrome and Firefox expose CSS generated content in the
          accessibility tree. See `activityHistory.css` for the narrowed claim. */}
      <p className="activity-meta">
        {showActor && <span className="activity-actor">{actorDisplay(event.actor)}</span>}
        {basis !== null && <span className="activity-trust">{basis}</span>}
        {/* The machine value stays in `dateTime` — that attribute exists for it —
            and the full absolute timestamp stays in `title`, so splitting the date
            onto the group heading loses nothing. */}
        <time
          className="activity-when"
          dateTime={event.recorded_utc}
          title={readableWhen(event.recorded_utc)}
        >
          {readableTimeOfDay(event.recorded_utc)}
        </time>
        {/* The channel is the half of `DEC-44` that is knowable today, so it is
            still shown plainly: a scientist can tell their own typing from an
            agent's write and from an archive import. It is demoted, not dropped. */}
        <span className="activity-channel">{humanizeToken(event.channel)}</span>
      </p>
    </li>
  );
}

export function ActivityHistoryPanel({ experimentId }: { experimentId: string }) {
  const [state, setState] = useState<
    { status: 'loading' } | { status: 'error' } | { status: 'data'; body: ApiActivityResponse }
  >({ status: 'loading' });
  /*
   * PAGES ALREADY READ, oldest-appended. The server answers newest-first and hands
   * back `next_before_seq`, so "older" is a cursor walk rather than an offset — the
   * same shape the proposals list uses, and it cannot skip or duplicate an entry when
   * a new act lands between two reads.
   *
   * WHY THIS EXISTS AT ALL: the first version rendered one page and reported
   * "50 of 200", which named 150 facts a reader could not reach. A count that
   * advertises hidden content with no control to reach it is a dead end, not a
   * deliberate scope boundary — found by an Impeccable pass over this panel.
   */
  const [older, setOlder] = useState<ApiActivityEvent[]>([]);

  const [cursor, setCursor] = useState<number | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  /*
   * A FAILED OLDER PAGE, VISIBLE TO EVERYONE — independent review, Important 3.
   *
   * The `.catch` below announced into the `sr-only` live region and cleared the
   * spinner, and correctly did NOT set `status: 'error'`: that would have destroyed
   * the list, which is §11's rule for exactly this shape. But `status: 'error'` was
   * the ONLY path rendering anything visible, so a sighted scientist saw the button
   * flicker and come back, no new rows, and no reason — unable to tell "the read
   * failed" from "there was nothing more". The SCREEN-READER USER WAS BETTER
   * INFORMED THAN THE SIGHTED ONE, which is the same inversion §11 records for the
   * recording state, and it is half of a pattern: `IngestionProposalsPanel` and
   * `UnmappedNotesPanel` — the two panels this module's own docstring cites — were
   * both fixed to DISCLOSE INLINE rather than merely announce.
   *
   * So: a flag beside the list, never a replacement for it. It is cleared by the
   * next successful page and by a fresh read, so a transient failure does not leave
   * a permanent warning over a list that has since grown.
   */
  const [olderFailed, setOlderFailed] = useState(false);
  /* Announced to screen readers, which otherwise hear NOTHING when a read finishes or
     a page arrives — the panel's own status text is not a live region. The alternating
     NBSP is `IngestionProposalsPanel.announce()`'s idiom: an identical string is not
     re-announced, so the toggle forces it. */
  const [announcement, setAnnouncement] = useState('');
  const announce = useCallback((sentence: string) => {
    setAnnouncement((prev) => (prev.endsWith('\u00a0') ? sentence : `${sentence}\u00a0`));
  }, []);
  /* Guards a response from a PREVIOUS experiment id landing after a switch. The
     record screen unmounts this panel on a switch, so React would no-op the late
     setState anyway — this is hazard-class defence, and it is labelled as such
     rather than as a regression guard, exactly as the capture panel's are. */
  const wanted = useRef(experimentId);

  const load = useCallback(() => {
    wanted.current = experimentId;
    setState({ status: 'loading' });
    setOlder([]);
    setCursor(null);
    setOlderFailed(false);
    api
      .listActivity(experimentId)
      .then((body) => {
        if (wanted.current !== experimentId) return;
        setState({ status: 'data', body });
        setCursor(body.next_before_seq);
        announce(
          body.total === 0
            ? LABELS.activityEmpty
            : `${LABELS.activityShowing} ${body.returned} ${LABELS.activityOf} ${body.total} ${LABELS.activityEntries}.`,
        );
      })
      .catch(() => {
        if (wanted.current !== experimentId) return;
        setState({ status: 'error' });
        announce(LABELS.activityUnavailable);
      });
  }, [experimentId, announce]);

  /*
   * ONE PAGE OLDER. Appends rather than replaces, so the reader never loses what they
   * were looking at — and a failed page leaves the list exactly as it was, which is
   * the destructive-silent-failure rule §11 records for the proposals and notes
   * panels: a background failure must not destroy what is on screen.
   */
  const loadOlder = useCallback(() => {
    if (cursor === null || loadingOlder) return;
    setLoadingOlder(true);
    api
      .listActivity(experimentId, { beforeSeq: cursor })
      .then((body) => {
        if (wanted.current !== experimentId) return;
        setOlder((prev) => [...prev, ...body.events]);
        setCursor(body.next_before_seq);
        setLoadingOlder(false);
        setOlderFailed(false);
        announce(`${LABELS.activityShowing} ${body.returned} ${LABELS.activityEntries}.`);
      })
      .catch(() => {
        if (wanted.current !== experimentId) return;
        setLoadingOlder(false);
        /* VISIBLE, AND NOT INSTEAD OF THE LIST. `setState` is deliberately NOT
           touched here: `status: 'error'` would replace the rows the reader is
           looking at, which is the destructive-silent-failure defect, not the fix
           for it. The announcement is the SAME sentence the flag renders, so the
           screen-reader user and the sighted one are now told the same thing. */
        setOlderFailed(true);
        announce(LABELS.activityOlderFailed);
      });
  }, [cursor, experimentId, loadingOlder, announce]);

  useEffect(load, [load]);

  /*
   * HOW MANY ROWS THE READER CAN SEE — counted from the rendered rows, deliberately.
   *
   * I FIRST WROTE THIS AS A SUM OF THE SERVER'S `returned` VALUES, with a comment
   * citing §11's `pendingTotal` rule, and a negative control proved that guard was an
   * EQUIVALENT MUTANT: swapping it back to array lengths failed no test, because in
   * every fixture `returned` equals `events.length`.
   *
   * The mutant passing was informative rather than merely embarrassing — it showed the
   * rule was MIS-APPLIED. §11's defect is taking the TOTAL from a fetched page, which
   * understates outstanding work; that rule is honoured two lines below, where the
   * total is `state.body.total` and never a length. But `shown` is a claim about WHAT
   * IS ON SCREEN, so the rendered rows are its only honest source: a server `returned`
   * that disagreed with the rows delivered would make this sentence describe a list
   * the reader is not looking at.
   *
   * So: TOTAL from the server, always. SHOWN from the DOM's own content, always.
   */
  const rendered = state.status === 'data' ? [...state.body.events, ...older] : [];
  const shown = rendered.length;
  /* Taken HERE, in the render body, and threaded down — see `calendarDay`'s note: a
     "Today" captured once at mount is wrong on the next render after midnight. It
     does NOT rescue an idle tab; that claim was withdrawn, and the note says why. */
  const groups = groupByDay(rendered, new Date());
  const showActor = PER_ROW_ACTOR(rendered);
  /* The standing attribution sentence, chosen from what is LOADED — see
     `attributionNote`. Computed beside `showActor` from the same array, so the two
     cannot disagree about the same history, which is the defect they had. */
  const attribution = attributionNote(rendered);

  return (
    <section className="activity-panel" aria-labelledby="activity-heading">
      <h2 id="activity-heading" className="activity-heading">
        {LABELS.activityTitle}
      </h2>
      <p className="activity-lead">{LABELS.activityLead}</p>
      {/* THE ACTOR DISCLOSURE, BEHIND A NATIVE `<details>` — the repo idiom
          (`HelpPanel`, `AssistantPanel`, `FetchStates`, `SchemaBrowser`):
          keyboard-operable with no ARIA and announced as a disclosure.
          `ACT-003`'s requirement is that `unattributed` be rendered HONESTLY, and
          the sentence behind this is UNCHANGED and still in the DOM — a closed
          `<details>` is reachable by `querySelectorAll`, by find-in-page and by a
          screen reader. What changed is that ~40 words of standing explanation
          stop being permanent furniture for a reader who has met them once, which
          is the owner's own direction: honest prose goes behind a collapsible
          rather than being capped or deleted. The SUMMARY still states the fact,
          so nothing is hidden behind a neutral label.

          CONDITIONAL SINCE THE `ACT-003b` REVIEW (Important 1). It used to render
          unconditionally, so a history containing one attributed act showed a row
          naming a person above a sentence saying nobody can be named. Which
          sentence appears — or whether any does — is now derived from the loaded
          events by `attributionNote`, from the same array `showActor` reads. */}
      {attribution !== null && (
        <Disclosure
          summary={<span className="activity-actor-summary">{attribution.summary}</span>}
          className="activity-actor-details"
        >
          <p className="activity-actor-note">{attribution.body}</p>
        </Disclosure>
      )}
      {/* The only live region on this panel. Without it a screen-reader user hears
          nothing when a read finishes or an older page arrives, because the status
          text below is static. */}
      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>

      {state.status === 'loading' && <p className="activity-status">{LABELS.activityLoading}</p>}
      {state.status === 'error' && (
        <p className="activity-status activity-status-error">{LABELS.activityUnavailable}</p>
      )}
      {state.status === 'data' && (
        <>
          <p className="activity-counts">
            {/* THE TOTAL IS THE SERVER'S, ALWAYS — `state.body.total`, never a page
                length, which is §11's `pendingTotal` rule. `shown` is the opposite and
                deliberately so: it counts the rendered rows, because it describes what
                the reader is looking at (see `shown`'s own note). A NOUN is attached,
                because "50 of 200" is a bare fraction and a reader mid-task should not
                have to infer what it counts. */}
            {state.body.total === 0
              ? LABELS.activityEmpty
              : `${LABELS.activityShowing} ${shown} ${LABELS.activityOf} ${state.body.total} ${LABELS.activityEntries}.`}
            {state.body.unreadable_entries > 0 && (
              <span className="activity-unreadable">
                {' '}
                {LABELS.activityUnreadable} {state.body.unreadable_entries}
              </span>
            )}
          </p>
          {state.body.total > 0 && (
            <>
              {/* GROUPED BY CALENDAR DAY, AS NESTED LISTS — defect A. The outer list
                  holds one item per day and each carries its own heading plus its own
                  list of rows, which keeps the whole thing a valid, screen-reader
                  coherent list: a bare `<div>` between `<li>`s would break the outer
                  list's semantics, and a heading floating beside the list would not be
                  associated with the rows it names. The heading level is `h3` under this
                  panel's own `h2`, so the document outline does not skip. */}
              <ol className="activity-list">
                {groups.map((group) => (
                  <li className="activity-group" key={`${group.key}:${group.events[0].id}`}>
                    <h3 className="activity-group-heading">{group.heading}</h3>
                    <ol className="activity-group-list">
                      {group.events.map((e) => (
                        <EventRow key={e.id} event={e} showActor={showActor} />
                      ))}
                    </ol>
                  </li>
                ))}
              </ol>
              {/* VISIBLE, BESIDE THE LIST THAT SURVIVED — see `olderFailed`. Before
                  this, the only rendered account of a failed older-page read lived in
                  the `sr-only` live region, so a sighted reader saw the button
                  flicker and return with no new rows and no reason, unable to tell a
                  failure from "there is nothing more". It is placed ABOVE the paging
                  control because the control is what they will reach for next. */}
              {olderFailed && (
                <p className="activity-status activity-status-error activity-older-error">
                  {LABELS.activityOlderFailed}
                </p>
              )}
              {cursor !== null ? (
                <button
                  type="button"
                  className="btn btn-secondary activity-older"
                  onClick={loadOlder}
                  disabled={loadingOlder}
                >
                  {loadingOlder ? LABELS.activityLoadingOlder : LABELS.activityShowOlder}
                </button>
              ) : (
                /* Said explicitly rather than by the control simply vanishing: a
                   missing button is ambiguous between "no more" and "broken". */
                <p className="activity-counts">{LABELS.activityAllShown}</p>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
