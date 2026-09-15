/*
 * HOW ONE CHECK FINDING IS PRESENTED — subject, state word, destination.
 *
 * The project owner, 2026-09-15, on the Runs screen: *"in regards to the check
 * failed — I don't even know what it's asking. What does it mean? I think you
 * should point to the specific field that it's talking about … And if they want
 * more information, then they can ask the agent."*
 *
 * A finding used to render as one bare sentence. It now renders as SUBJECT ·
 * STATE over the server's own sentence, with a destination when one really
 * exists. Every one of those four parts is either read from the payload or
 * supplied by the caller; NOTHING here composes a finding, re-words one, or
 * decides a severity.
 *
 * ── THE STATE WORD IS THE CALLER'S, NOT THIS MODULE'S ──────────────────────
 *
 * `FindingList`'s own header says it computes nothing: "no severity is decided
 * here, no verdict is derived". That stays true. The word comes from WHICH LIST
 * the caller is rendering — a fact the caller already knows and already states
 * in its heading — so the two can never disagree, and this module cannot invent
 * a taxonomy the server did not give it.
 *
 * ── THE SUBJECT IS READ, NEVER INFERRED ────────────────────────────────────
 *
 * `kind` is the server's own blocker taxonomy and `ApiRunCheckFinding` declares
 * it OPTIONAL with an explicit instruction: "a reader groups by it when it is
 * there and says nothing when it is not — it is never defaulted, and no kind is
 * inferred from the message text." So an entry with neither a recognised `kind`
 * nor a `path` gets NO subject line at all, rather than a subject guessed from
 * its prose.
 */

import { blockerKindLabel } from './adapt';
import { RUN_FIELDS } from './runFields';
import type { ApiRunCheckFinding } from './types';

/**
 * The short state word on a finding row.
 *
 * Four members, each tied to one list a caller renders:
 *
 *   `Missing`      `blockers` — an OPEN QUESTION. `serialize.pending_to_list`
 *                  entries are questions nobody has answered yet, so the record
 *                  does not carry the thing the finding names.
 *   `Needs Review` `draft.errors` — the NO-GUESSING validator objected. It is
 *                  not a schema verdict and must not read as one.
 *   `Invalid`      `official.errors` — the official-schema dry run (or ISAAC's
 *                  own exactness gate, which the caller's heading names)
 *                  refused the document. "Invalid" is that gate's own word.
 *   `Advisory`     `draft.warnings` — `DraftReport.ok` does not read this list,
 *                  so it gates nothing. None of the three words above would be
 *                  true of it, which is why there is a fourth.
 */
export type FindingState = 'Missing' | 'Needs Review' | 'Invalid' | 'Advisory';

/** What a finding is ABOUT, when it says. */
export interface FindingSubject {
  text: string;
  /**
   * True when `text` is a raw official PATH rather than a human name — the
   * caller renders it in mono, the way every other path in this app is
   * demoted. `UX-014`'s rule is that a schema path is never removed.
   */
  mono: boolean;
}

/**
 * The subject of one finding, or `null` when the payload names none.
 *
 * ORDER: a recognised `kind` first (a human name a scientist already reads
 * elsewhere in this product), then `path` (exact, and therefore never wrong
 * even when it is jargon), then nothing.
 */
export function findingSubject(finding: ApiRunCheckFinding): FindingSubject | null {
  if (typeof finding !== 'object' || finding === null) return null;
  const label = blockerKindLabel(finding.kind);
  if (label !== null) return { text: label, mono: false };
  const path = finding.path;
  if (typeof path === 'string' && path.trim() !== '') {
    return { text: path.trim(), mono: true };
  }
  return null;
}

/** Every path the run editor on this screen actually offers a control for. */
const RUN_FIELD_PATHS = new Set(RUN_FIELDS.map((spec) => spec.path));

/**
 * The run-level field this finding can send a reader to, or `null`.
 *
 * DELIBERATELY NARROW. It answers only for the five paths `RUN_FIELDS` renders
 * an input for, because those are the only destinations that exist ON THIS
 * SCREEN, and a control offering to "go to" somewhere that is not there is
 * worse than no control. A blocker carries a `kind` and no `path`, so a blocker
 * never resolves here — its home is Complete Metadata, which this slice does
 * not link to (see the component's own note on why).
 *
 * The match is EXACT. `timestamps` does not resolve to
 * `timestamps.acquired_start_utc`: "the timestamps block has a problem" is a
 * different statement from "this field has a problem", and only the server can
 * tell them apart.
 */
export function findingRunFieldPath(finding: ApiRunCheckFinding): string | null {
  if (typeof finding !== 'object' || finding === null) return null;
  const path = finding.path;
  if (typeof path !== 'string') return null;
  const trimmed = path.trim();
  return RUN_FIELD_PATHS.has(trimmed) ? trimmed : null;
}

/** Everything the composed question is allowed to name. All of it is read. */
export interface AskContext {
  experimentId?: string;
  runId?: string;
  runLabel?: string;
}

/**
 * The question an `Ask ISAAC` control puts in the Assistant's composer.
 *
 * IT IS NOT SENT, AND IT IS NOT AN ANSWER. It is the sentence a scientist would
 * otherwise have to retype: what the finding is about, which run and record it
 * is on, and the validator's own words. The Assistant it lands in is the
 * deterministic bounded-intent resolver — `ASSISTANT_NO_MODEL_CLAIM` states in
 * that panel's own dock that no language model is involved in any deployment —
 * and it refuses honestly when the question is outside its catalog. Nothing
 * here promises an answer, and nothing here fills a field, validates, accepts
 * or submits.
 *
 * THE VALIDATOR'S SENTENCE IS QUOTED VERBATIM, never paraphrased, which is the
 * same rule the row itself follows.
 */
export function composeFindingQuestion(
  state: FindingState,
  subject: FindingSubject | null,
  message: string | null,
  context: AskContext,
): string {
  const parts: string[] = [];
  parts.push(
    subject === null
      ? `What does this ${state.toLowerCase()} finding mean?`
      : `What does this ${state.toLowerCase()} finding about ${subject.text} mean?`,
  );
  const where: string[] = [];
  if (context.runLabel !== undefined && context.runLabel !== '') {
    where.push(
      context.runId === undefined || context.runId === ''
        ? context.runLabel
        : `${context.runLabel} (${context.runId})`,
    );
  } else if (context.runId !== undefined && context.runId !== '') {
    where.push(context.runId);
  }
  if (context.experimentId !== undefined && context.experimentId !== '') {
    where.push(`record ${context.experimentId}`);
  }
  if (where.length > 0) parts.push(`On ${where.join(', ')}.`);
  if (message !== null && message !== '') parts.push(`The check reported: “${message}”`);
  return parts.join(' ');
}
