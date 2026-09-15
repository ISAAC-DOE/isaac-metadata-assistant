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

/**
 * THE SERVER'S SENTINEL FOR "THE WHOLE DOCUMENT, NO FIELD" — and the reason
 * this constant exists at all is that a browser caught it being rendered as a
 * subject.
 *
 * `official.py:98` builds a finding's path as
 * `".".join(str(p) for p in err.absolute_path) or "$"` — so `$` is what an
 * error with an EMPTY path becomes, which is every whole-document error
 * (`'descriptors' is a required property` is the commonest one in this
 * product). `routes.py` additionally writes `{"path": "$"}` at seven sites for
 * its fail-closed "Validation could not be completed" branch.
 *
 * MEASURED ON THE RUNNING APP, 2026-09-15: a Check Run on a real record
 * rendered a subject line reading exactly `$` above
 * `'descriptors' is a required property`. That is worse than no subject — it
 * looks like a variable name, it names no field, and it is the shape of defect
 * this whole slice exists to remove. A whole-document finding HAS no subject,
 * and saying nothing is the honest rendering of that.
 */
const ROOT_PATH = '$';

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
  if (typeof path === 'string' && path.trim() !== '' && path.trim() !== ROOT_PATH) {
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
  /* `$` could never match a member of the five, so excluding it changes no
     outcome here — it is excluded anyway, so both readers of a finding's path
     agree on what a path IS rather than agreeing by coincidence. */
  if (trimmed === ROOT_PATH) return null;
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
  /**
   * The finding's run-field path, when it has one — the SAME value that gates
   * `Go to field`, passed in rather than re-derived so the button and the
   * question cannot disagree about whether a field is known.
   */
  fieldPath: string | null = null,
): string {
  const parts: string[] = [];
  /*
   * *** THE OPENING SENTENCE DECIDES WHETHER THIS QUESTION IS ANSWERABLE AT
   * ALL, AND THE FIRST VERSION OF IT WAS REFUSED 100% OF THE TIME. ***
   *
   * It read `What does this <state> finding [about <subject>] mean?`. Measured
   * against the real resolver — `assistant_query.classify`, not a guess — every
   * variant of that sentence returns `intent='unsupported', confidence='none'`:
   * all four states, with and without a subject, with and without the context
   * clause. The catalog has eight intents and "explain this finding" is not one
   * of them.
   *
   * So the control the owner asked for — *"a button right next to it that points
   * to the agent, and then the agent will have the context"* — handed the agent
   * context it could not use, and a reader who pressed Send got a refusal every
   * time. Found by independent review, not by a test: nothing here asserted that
   * the composed string is one the resolver accepts.
   *
   * IT ALSO BROKE THIS REPOSITORY'S OWN RULE, cited one file away. `assistantAsk`
   * withholds the button when there is no context because "a control never
   * appears where pressing it would do nothing — the same rule the run editor
   * follows for a field whose only possible outcome is a refusal". That rule was
   * being applied to the wrong axis: whether an Assistant is mounted, rather
   * than whether the question can be answered.
   *
   * THE TWO OPENINGS BELOW BOTH CLASSIFY `high`, verified the same way:
   *   `Where did <path> come from?`  -> field_provenance  (high)
   *   `What is blocking export?`     -> export_blockers   (high)
   * The `On …` clause and the validator's verbatim sentence survive
   * classification untouched, so no context is given up to gain an answer.
   *
   * WHICH ONE IS CHOSEN IS A QUESTION OF WHAT IS TRUE, not of what classifies.
   * Provenance is only a sensible question about a value that EXISTS, so a
   * `Missing` finding asks what is blocking export even when its path is known —
   * asking where an absent value came from would be a question with no answer,
   * which is the defect this comment exists to record.
   */
  const askProvenance = fieldPath !== null && state !== 'Missing';
  parts.push(
    askProvenance ? `Where did ${fieldPath} come from?` : 'What is blocking export?',
  );
  /* The subject is still named, after the answerable opening rather than inside
     it — a reader sees which finding they asked about, and the resolver still
     matches on the opening. */
  if (!askProvenance && subject !== null) {
    parts.push(`I am looking at the ${state.toLowerCase()} finding about ${subject.text}.`);
  }
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
